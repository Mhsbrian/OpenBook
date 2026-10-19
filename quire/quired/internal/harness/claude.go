package harness

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
)

// The tool Claude Code asks before running anything its own settings don't already allow. It is
// served by `quired permission-mcp`, which hands each question back to this process.
const (
	permServer = "quire"
	permTool   = "approve"
)

// claudeAgent adapts Claude Code's print mode to ACP. Each prompt is one `claude -p` run; the
// first creates the conversation with --session-id and later ones continue it with --resume.
type claudeAgent struct {
	spec   agents.Spec
	client Client
	opts   Options
	stderr *ring

	mu       sync.Mutex
	sessions map[string]*claudeSession
}

type claudeSession struct {
	cwd     string
	mcp     []acp.McpServer
	started bool            // Claude has recorded the conversation, so --resume works
	always  map[string]bool // tools the person allowed for the rest of the session
	busy    bool
}

func newClaude(spec agents.Spec, client Client, opts Options) *claudeAgent {
	return &claudeAgent{spec: spec, client: client, opts: opts, stderr: newRing(64 << 10), sessions: map[string]*claudeSession{}}
}

func (c *claudeAgent) Info() acp.InitializeResponse {
	return acp.InitializeResponse{
		ProtocolVersion:   acp.ProtocolVersion,
		AgentCapabilities: acp.AgentCapabilities{LoadSession: true},
		AuthMethods:       []acp.AuthMethod{},
		AgentInfo:         &acp.Implementation{Name: "claude-code", Title: c.spec.Name + " (adapted by quired)", Version: c.opts.Version},
	}
}

func (c *claudeAgent) Diagnostics() string { return c.stderr.String() }
func (c *claudeAgent) Close() error        { return nil } // nothing runs between prompts

// Authenticate: Claude Code keeps its own sign-in (`claude` then /login, in a terminal), so the
// adapter offers no ACP methods.
func (c *claudeAgent) Authenticate(context.Context, string) error {
	return acp.Errorf(acp.CodeInvalidParams, "Claude Code signs in from a terminal: run claude, then /login")
}

func (c *claudeAgent) NewSession(_ context.Context, cwd string, mcp []acp.McpServer) (string, error) {
	if !filepath.IsAbs(cwd) {
		return "", acp.Errorf(acp.CodeInvalidParams, "cwd must be absolute: %s", cwd)
	}
	id, err := uuid4()
	if err != nil {
		return "", err
	}
	c.mu.Lock()
	c.sessions[id] = &claudeSession{cwd: cwd, mcp: mcp, always: map[string]bool{}}
	c.mu.Unlock()
	return id, nil
}

func (c *claudeAgent) Prompt(ctx context.Context, sid string, prompt []acp.ContentBlock) (string, error) {
	c.mu.Lock()
	s, ok := c.sessions[sid]
	if ok && s.busy {
		c.mu.Unlock()
		return "", acp.Errorf(acp.CodeInvalidRequest, "session %s already has a turn running", sid)
	}
	if ok {
		s.busy = true
	}
	c.mu.Unlock()
	if !ok {
		return "", acp.Errorf(acp.CodeInvalidParams, "unknown session %s", sid)
	}
	defer func() { c.mu.Lock(); s.busy = false; c.mu.Unlock() }()

	bridge, err := c.listenPermissions(ctx, sid, s)
	if err != nil {
		return "", err
	}
	defer bridge.close()

	args := []string{"-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
		"--mcp-config", c.mcpConfig(s, bridge.socket), "--permission-prompt-tool", "mcp__" + permServer + "__" + permTool}
	if s.started {
		args = append(args, "--resume", sid)
	} else {
		args = append(args, "--session-id", sid)
	}
	args = append(append(args, c.spec.Args...), c.opts.Args...)

	cmd := command(c.opts.Path, args, s.cwd, c.opts.Env)
	cmd.Stdin = strings.NewReader(promptText(prompt))
	cmd.Stderr = c.stderr
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return "", err
	}
	if err := cmd.Start(); err != nil {
		return "", fmt.Errorf("start %s: %w", c.opts.Path, err)
	}
	waited := make(chan struct{})
	turn := &claudeTurn{sid: sid, client: c.client, texted: map[string]bool{}, tools: map[string]string{}, hidden: map[string]bool{}}
	parsed := make(chan struct{})
	go func() {
		defer close(parsed)
		turn.read(stdout, c.stderr)
	}()
	go func() { <-parsed; _ = cmd.Wait(); close(waited) }()

	select {
	case <-waited:
	case <-ctx.Done():
		// Claude Code stops its turn on SIGINT, as it does for Ctrl-C.
		_ = syscall.Kill(-cmd.Process.Pid, syscall.SIGINT)
		select {
		case <-waited:
		case <-time.After(cancelTimeout):
			stop(cmd, waited, 5*time.Second)
		}
		if turn.sawInit {
			c.mark(s)
		}
		return acp.StopCancelled, nil
	}
	if turn.sawInit {
		c.mark(s)
	}
	if turn.err != nil {
		return "", c.wrap(turn.err)
	}
	if !turn.done {
		return "", c.wrap(fmt.Errorf("claude exited (%v) without a result", cmd.ProcessState))
	}
	return turn.stop, nil
}

func (c *claudeAgent) mark(s *claudeSession) {
	c.mu.Lock()
	s.started = true
	c.mu.Unlock()
}

func (c *claudeAgent) wrap(err error) error {
	if d := c.Diagnostics(); d != "" {
		return fmt.Errorf("%w\nclaude stderr (tail):\n%s", err, tail(d, 12))
	}
	return err
}

// mcpConfig lists the session's MCP servers plus the permission bridge, in Claude's --mcp-config form.
func (c *claudeAgent) mcpConfig(s *claudeSession, socket string) string {
	type server struct {
		Type    string            `json:"type"`
		Command string            `json:"command"`
		Args    []string          `json:"args"`
		Env     map[string]string `json:"env,omitempty"`
	}
	servers := map[string]server{permServer: {Type: "stdio", Command: c.opts.Self, Args: []string{"permission-mcp", "--socket", socket}}}
	for _, m := range s.mcp {
		env := map[string]string{}
		for _, e := range m.Env {
			env[e.Name] = e.Value
		}
		servers[m.Name] = server{Type: "stdio", Command: m.Command, Args: m.Args, Env: env}
	}
	b, _ := json.Marshal(map[string]any{"mcpServers": servers})
	return string(b)
}

func promptText(blocks []acp.ContentBlock) string {
	var parts []string
	for _, b := range blocks {
		switch b.Type {
		case "text":
			parts = append(parts, b.Text)
		case "resource_link":
			parts = append(parts, b.URI)
		}
	}
	return strings.Join(parts, "\n\n")
}

// claudeTurn turns one run's stream-json into ACP session updates.
type claudeTurn struct {
	sid    string
	client Client

	texted  map[string]bool   // message ids whose text already arrived as deltas
	lastMsg string            // the message the last text chunk belonged to
	tools   map[string]string // tool_use id → tool name, for tool calls already announced
	hidden  map[string]bool   // tool_use ids shown another way (TodoWrite becomes a plan)
	sawInit bool

	done bool
	stop string
	err  error
}

type cEvent struct {
	Type      string `json:"type"`
	Subtype   string `json:"subtype"`
	SessionID string `json:"session_id"`
	Event     *struct {
		Type         string  `json:"type"`
		ContentBlock *cBlock `json:"content_block"`
		Delta        *struct {
			Type     string `json:"type"`
			Text     string `json:"text"`
			Thinking string `json:"thinking"`
		} `json:"delta"`
	} `json:"event"`
	APIMessageID string `json:"api_message_id"`
	Message      *struct {
		ID      string   `json:"id"`
		Content []cBlock `json:"content"`
	} `json:"message"`
	Result     string `json:"result"`
	IsError    bool   `json:"is_error"`
	StopReason string `json:"stop_reason"`
}

type cBlock struct {
	Type      string          `json:"type"`
	Text      string          `json:"text"`
	Thinking  string          `json:"thinking"`
	ID        string          `json:"id"`
	Name      string          `json:"name"`
	Input     json.RawMessage `json:"input"`
	ToolUseID string          `json:"tool_use_id"`
	Content   json.RawMessage `json:"content"`
	IsError   bool            `json:"is_error"`
}

func (t *claudeTurn) read(r io.Reader, junk io.Writer) {
	br := bufio.NewReaderSize(r, 1<<16)
	for {
		line, err := br.ReadBytes('\n')
		if s := strings.TrimSpace(string(line)); s != "" {
			var e cEvent
			if json.Unmarshal([]byte(s), &e) != nil {
				fmt.Fprintf(junk, "stdout: %s\n", s)
			} else {
				t.event(e)
			}
		}
		if err != nil {
			return
		}
	}
}

func (t *claudeTurn) send(u acp.SessionUpdate) { t.client.Update(t.sid, u.Marshal()) }

// say sends message or thought text, starting a new paragraph when a new message begins, so that
// "I'll try another way." and "Done." don't run together.
func (t *claudeTurn) say(kind, msgID, text string) {
	if kind == acp.UpdateAgentMessageChunk {
		if t.lastMsg != "" && t.lastMsg != msgID {
			text = "\n\n" + text
		}
		t.lastMsg = msgID
	}
	t.send(acp.ChunkUpdate(kind, text))
}

func (t *claudeTurn) event(e cEvent) {
	switch e.Type {
	case "system":
		if e.Subtype == "init" && e.SessionID == t.sid {
			t.sawInit = true
		}
	case "stream_event":
		t.streamEvent(e)
	case "assistant":
		if e.Message == nil {
			return
		}
		for _, b := range e.Message.Content {
			t.assistantBlock(e.Message.ID, b)
		}
	case "user":
		if e.Message == nil {
			return
		}
		for _, b := range e.Message.Content {
			if b.Type == "tool_result" {
				t.toolResult(b)
			}
		}
	case "result":
		t.done = true
		switch {
		case e.Subtype == "error_max_turns":
			t.stop = acp.StopMaxTurnRequests
		case e.Subtype != "success" || e.IsError:
			t.err = fmt.Errorf("claude: %s: %s", e.Subtype, e.Result)
		case e.StopReason == acp.StopMaxTokens || e.StopReason == acp.StopRefusal:
			t.stop = e.StopReason
		default:
			t.stop = acp.StopEndTurn
		}
	}
}

func (t *claudeTurn) streamEvent(e cEvent) {
	ev := e.Event
	if ev == nil {
		return
	}
	switch {
	case ev.Type == "content_block_delta" && ev.Delta != nil && ev.Delta.Type == "text_delta":
		t.texted[e.APIMessageID] = true
		t.say(acp.UpdateAgentMessageChunk, e.APIMessageID, ev.Delta.Text)
	case ev.Type == "content_block_delta" && ev.Delta != nil && ev.Delta.Type == "thinking_delta":
		t.texted[e.APIMessageID] = true
		t.say(acp.UpdateAgentThoughtChunk, e.APIMessageID, ev.Delta.Thinking)
	case ev.Type == "content_block_start" && ev.ContentBlock != nil && ev.ContentBlock.Type == "tool_use":
		b := ev.ContentBlock
		if b.Name == "TodoWrite" {
			t.hidden[b.ID] = true
			return
		}
		t.tools[b.ID] = b.Name
		t.send(acp.SessionUpdate{Kind: acp.UpdateToolCall, ToolCallID: b.ID, Title: b.Name, ToolKind: toolKind(b.Name), Status: acp.StatusPending})
	}
}

func (t *claudeTurn) assistantBlock(msgID string, b cBlock) {
	switch b.Type {
	case "text":
		if !t.texted[msgID] && b.Text != "" {
			t.say(acp.UpdateAgentMessageChunk, msgID, b.Text)
		}
	case "thinking":
		if !t.texted[msgID] && b.Thinking != "" {
			t.say(acp.UpdateAgentThoughtChunk, msgID, b.Thinking)
		}
	case "tool_use":
		if b.Name == "TodoWrite" {
			t.hidden[b.ID] = true
			if entries := todoPlan(b.Input); entries != nil {
				t.send(acp.SessionUpdate{Kind: acp.UpdatePlan, Entries: entries})
			}
			return
		}
		kind := acp.UpdateToolCallUpdate
		if _, seen := t.tools[b.ID]; !seen {
			kind = acp.UpdateToolCall
			t.tools[b.ID] = b.Name
		}
		t.send(acp.SessionUpdate{Kind: kind, ToolCallID: b.ID, Title: toolTitle(b.Name, b.Input), ToolKind: toolKind(b.Name),
			Status: acp.StatusInProgress, RawInput: b.Input})
	}
}

func (t *claudeTurn) toolResult(b cBlock) {
	if t.hidden[b.ToolUseID] {
		return
	}
	status := acp.StatusCompleted
	if b.IsError {
		status = acp.StatusFailed
	}
	text := truncate(resultText(b.Content), 4000)
	t.send(acp.SessionUpdate{Kind: acp.UpdateToolCallUpdate, ToolCallID: b.ToolUseID, Status: status,
		Content: acp.ToolContent(acp.ToolCallContent{Type: "content", Content: &acp.ContentBlock{Type: "text", Text: text}})})
}

// resultText flattens a tool_result's content, which is a string or a list of blocks.
func resultText(raw json.RawMessage) string {
	var s string
	if json.Unmarshal(raw, &s) == nil {
		return s
	}
	var blocks []cBlock
	if json.Unmarshal(raw, &blocks) == nil {
		var parts []string
		for _, b := range blocks {
			if b.Type == "text" {
				parts = append(parts, b.Text)
			}
		}
		return strings.Join(parts, "\n")
	}
	return ""
}

func todoPlan(input json.RawMessage) []acp.PlanEntry {
	var in struct {
		Todos []struct {
			Content string `json:"content"`
			Status  string `json:"status"`
		} `json:"todos"`
	}
	if json.Unmarshal(input, &in) != nil || in.Todos == nil {
		return nil
	}
	entries := make([]acp.PlanEntry, 0, len(in.Todos))
	for _, td := range in.Todos {
		entries = append(entries, acp.PlanEntry{Content: td.Content, Priority: "medium", Status: td.Status})
	}
	return entries
}

func toolKind(name string) string {
	switch name {
	case "Read", "NotebookRead":
		return acp.KindRead
	case "Edit", "MultiEdit", "Write", "NotebookEdit":
		return acp.KindEdit
	case "Bash", "BashOutput", "KillShell", "KillBash":
		return acp.KindExecute
	case "Grep", "Glob", "LS":
		return acp.KindSearch
	case "WebFetch", "WebSearch":
		return acp.KindFetch
	case "Task", "Agent":
		return acp.KindThink
	}
	return acp.KindOther
}

// toolTitle is the one line a person reads for a tool call: "Read notes.txt", "Run make test".
func toolTitle(name string, input json.RawMessage) string {
	var in map[string]any
	_ = json.Unmarshal(input, &in)
	str := func(k string) string { s, _ := in[k].(string); return s }
	switch name {
	case "Read", "Edit", "MultiEdit", "Write", "NotebookEdit":
		if p := str("file_path"); p != "" {
			return name + " " + filepath.Base(p)
		}
	case "Bash":
		if cmd := str("command"); cmd != "" {
			return "Run " + truncate(firstLine(cmd), 80)
		}
	case "Grep", "Glob":
		if p := str("pattern"); p != "" {
			return name + " " + truncate(p, 60)
		}
	case "WebFetch":
		if u := str("url"); u != "" {
			return "Fetch " + truncate(u, 80)
		}
	case "WebSearch":
		if q := str("query"); q != "" {
			return "Search the web for " + truncate(q, 60)
		}
	}
	return name
}

func firstLine(s string) string { l, _, _ := strings.Cut(s, "\n"); return l }

func truncate(s string, n int) string {
	if r := []rune(s); len(r) > n {
		return string(r[:n-1]) + "…"
	}
	return s
}

func uuid4() (string, error) {
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	b[6] = b[6]&0x0f | 0x40
	b[8] = b[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16]), nil
}

// permBridge receives Claude Code's permission questions from `quired permission-mcp` over a
// private unix socket and asks the Client.
type permBridge struct {
	dir    string
	socket string
	close  func()
}

// A permission question from Claude Code, as its --permission-prompt-tool receives it, and the answer.
type permQuestion struct {
	ToolName  string          `json:"tool_name"`
	Input     json.RawMessage `json:"input"`
	ToolUseID string          `json:"tool_use_id"`
}

type permAnswer struct {
	Behavior     string          `json:"behavior"` // "allow" or "deny"
	UpdatedInput json.RawMessage `json:"updatedInput,omitempty"`
	Message      string          `json:"message,omitempty"`
}

func (c *claudeAgent) listenPermissions(ctx context.Context, sid string, s *claudeSession) (*permBridge, error) {
	dir, err := os.MkdirTemp("", "quired-perm-")
	if err != nil {
		return nil, err
	}
	socket := filepath.Join(dir, "s")
	l, err := listenUnix(socket)
	if err != nil {
		os.RemoveAll(dir)
		return nil, err
	}
	ctx, cancel := context.WithCancel(ctx)
	// The accept loop counts itself in wg, so a connection it takes is always counted before
	// close's Wait can see zero. Each connection is closed when ctx ends, which frees a peer
	// that sent half a question or stopped reading.
	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		for {
			conn, err := l.Accept()
			if err != nil {
				return
			}
			wg.Add(1)
			go func() {
				defer wg.Done()
				defer conn.Close()
				defer context.AfterFunc(ctx, func() { conn.Close() })()
				var q permQuestion
				if err := json.NewDecoder(conn).Decode(&q); err != nil {
					return
				}
				_ = json.NewEncoder(conn).Encode(c.decide(ctx, sid, s, q))
			}()
		}
	}()
	return &permBridge{dir: dir, socket: socket, close: func() {
		cancel()
		l.Close()
		wg.Wait()
		os.RemoveAll(dir)
	}}, nil
}

func (c *claudeAgent) decide(ctx context.Context, sid string, s *claudeSession, q permQuestion) permAnswer {
	allow := permAnswer{Behavior: "allow", UpdatedInput: q.Input}
	if len(allow.UpdatedInput) == 0 {
		allow.UpdatedInput = json.RawMessage("{}")
	}
	c.mu.Lock()
	always := s.always[q.ToolName]
	c.mu.Unlock()
	if always {
		return allow
	}
	res, err := c.client.RequestPermission(ctx, acp.RequestPermissionRequest{
		SessionID: sid,
		ToolCall: acp.ToolCallRef{ToolCallID: q.ToolUseID, Title: toolTitle(q.ToolName, q.Input), Kind: toolKind(q.ToolName),
			Status: acp.StatusPending, RawInput: q.Input},
		Options: []acp.PermissionOption{
			{OptionID: "allow", Name: "Allow", Kind: acp.AllowOnce},
			{OptionID: "always", Name: "Allow for this session", Kind: acp.AllowAlways},
			{OptionID: "deny", Name: "Don't allow", Kind: acp.RejectOnce},
		},
	})
	switch {
	case err != nil:
		return permAnswer{Behavior: "deny", Message: "Quire could not ask the person: " + err.Error()}
	case res.Outcome.Outcome != acp.OutcomeSelected:
		return permAnswer{Behavior: "deny", Message: "The turn was cancelled."}
	case res.Outcome.OptionID == "always":
		c.mu.Lock()
		s.always[q.ToolName] = true
		c.mu.Unlock()
		return allow
	case res.Outcome.OptionID == "allow":
		return allow
	}
	return permAnswer{Behavior: "deny", Message: "The person did not allow this."}
}

// ServePermissionMCP is `quired permission-mcp`: a one-tool MCP server on stdio that forwards
// each call to the quired process listening on socket. MCP is JSON-RPC 2.0 framed like ACP,
// so the same connection type carries it.
func ServePermissionMCP(in io.Reader, out io.Writer, socket, version string) error {
	tool := map[string]any{
		"name":        permTool,
		"description": "Asks the person at the Quire surface whether a tool call may run.",
		"inputSchema": map[string]any{
			"type": "object",
			"properties": map[string]any{
				"tool_name":   map[string]any{"type": "string"},
				"input":       map[string]any{"type": "object"},
				"tool_use_id": map[string]any{"type": "string"},
			},
			"required": []string{"tool_name", "input"},
		},
	}
	h := acp.Handlers{Request: func(ctx context.Context, method string, params json.RawMessage) (any, error) {
		switch method {
		case "initialize":
			var p struct {
				ProtocolVersion string `json:"protocolVersion"`
			}
			_ = json.Unmarshal(params, &p)
			return map[string]any{
				"protocolVersion": p.ProtocolVersion,
				"capabilities":    map[string]any{"tools": map[string]any{}},
				"serverInfo":      map[string]any{"name": "quire-permissions", "version": version},
			}, nil
		case "ping":
			return map[string]any{}, nil
		case "tools/list":
			return map[string]any{"tools": []any{tool}}, nil
		case "tools/call":
			var p struct {
				Name      string       `json:"name"`
				Arguments permQuestion `json:"arguments"`
			}
			if err := json.Unmarshal(params, &p); err != nil || p.Name != permTool {
				return nil, acp.Errorf(acp.CodeInvalidParams, "unknown tool")
			}
			ans, err := askBridge(ctx, socket, p.Arguments)
			if err != nil {
				ans = permAnswer{Behavior: "deny", Message: "Quire is not reachable: " + err.Error()}
			}
			b, _ := json.Marshal(ans)
			return map[string]any{"content": []any{map[string]any{"type": "text", "text": string(b)}}}, nil
		}
		return nil, acp.Errorf(acp.CodeMethodNotFound, "method not found: %s", method)
	}}
	conn := acp.NewConn(in, out, h, nil)
	<-conn.Done()
	return conn.Err()
}

// askBridge asks the quired process on socket. There is no fixed timeout, since a person may take
// their time; it ends when ctx does (Claude Code went away) or when quired closes the connection
// (the turn ended), and every way it can fail is answered "deny" by the caller.
func askBridge(ctx context.Context, socket string, q permQuestion) (permAnswer, error) {
	conn, err := dialUnix(ctx, socket)
	if err != nil {
		return permAnswer{}, err
	}
	defer conn.Close()
	defer context.AfterFunc(ctx, func() { conn.Close() })()
	if err := json.NewEncoder(conn).Encode(q); err != nil {
		return permAnswer{}, err
	}
	var a permAnswer
	if err := json.NewDecoder(conn).Decode(&a); err != nil {
		if ctx.Err() != nil {
			return permAnswer{}, ctx.Err()
		}
		return permAnswer{}, err
	}
	if a.Behavior != "allow" && a.Behavior != "deny" {
		return permAnswer{}, errors.New("bad answer from quired")
	}
	return a, nil
}
