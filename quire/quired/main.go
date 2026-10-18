// quired is Quire's harness host: it finds the coding agents installed on a machine, runs them,
// and speaks the Agent Client Protocol (ACP) with every one of them, adapting those that don't.
//
// On OpenBook it runs where the agents live (the Linux environment, or a computer you pair) and
// Quire, the system surface, is its client. This command line is the same client in a terminal.
// See docs/quire.md.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"text/tabwriter"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/harness"
)

const version = "0.2.0"

var clientInfo = acp.Implementation{Name: "quired", Title: "Quire harness host (OpenBook)", Version: version}

const usageText = `quired: Quire's harness host. Runs coding agents and speaks ACP with them.

Usage:
  quired agents [--json] [--connect ADDR]      list the agents installed here (or where ADDR serves)
  quired probe [--json] (--all | AGENT...)     start agents and open a session, without prompting
  quired run [flags] AGENT PROMPT...           run one turn (PROMPT "-" reads stdin)
  quired serve [serve flags]                   serve Quire core over ACP (vsock by default)
  quired version

run flags:
  --cwd DIR          the session's folder (default: a new empty folder)
  --approve MODE     ask (default; needs a terminal), read (reads and searches only), all, none
  --json             print ACP session/update notifications as NDJSON instead of text
  --fs               serve file reads and writes to ACP agents, confined to --cwd (default true)
  --agent-arg ARG    pass ARG to the agent's command line (repeatable), e.g. --agent-arg=--model --agent-arg=haiku
  --timeout DUR      cancel the turn after DUR (default: none)
  --connect ADDR     run the turn through a quired serve at ADDR instead of here

serve flags:
  --vsock PORT       listen on this vsock port, for Android (default 7690)
  --unix PATH        listen on a unix socket instead (0600; same-user peers only)
  --stdio            serve one client on stdin/stdout instead
  --root DIR         sessions' folders live inside DIR (default: $HOME)
  --any-cid          accept vsock peers other than the host (testing only)
  --max-conns N      at most N clients at once (default 4)

ADDR is vsock:CID:PORT or unix:PATH.
`

func main() {
	if len(os.Args) < 2 {
		fmt.Fprint(os.Stderr, usageText)
		os.Exit(2)
	}
	ctx, stopSignals := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stopSignals()

	var err error
	switch os.Args[1] {
	case "agents":
		err = cmdAgents(ctx, os.Args[2:])
	case "probe":
		err = cmdProbe(ctx, os.Args[2:])
	case "run":
		err = cmdRun(ctx, os.Args[2:])
	case "serve":
		err = cmdServe(ctx, os.Args[2:])
	case "permission-mcp": // started by the Claude Code adapter, not by people
		err = cmdPermissionMCP(os.Args[2:])
	case "version", "--version":
		fmt.Println("quired", version)
	case "help", "-h", "--help":
		fmt.Print(usageText)
	default:
		fmt.Fprintf(os.Stderr, "quired: unknown command %q\n\n%s", os.Args[1], usageText)
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "quired:", err)
		os.Exit(1)
	}
}

func cmdAgents(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("agents", flag.ContinueOnError)
	asJSON := fs.Bool("json", false, "print JSON")
	connect := fs.String("connect", "", "list the agents of the quired serve at ADDR")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *connect != "" {
		return remoteAgents(ctx, *connect, *asJSON)
	}
	found := agents.Discover(ctx, agents.HostEnv)
	if *asJSON {
		return printJSON(found)
	}
	w := tabwriter.NewWriter(os.Stdout, 0, 4, 2, ' ', 0)
	fmt.Fprintln(w, "AGENT\tNAME\tVERSION\tPROTOCOL\tSTATE")
	for _, f := range found {
		state := "ready"
		if !f.Supported {
			state = "not yet: " + f.Note
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\n", f.ID, f.Name, f.Version, f.Protocol, state)
	}
	return w.Flush()
}

// probeResult is what `quired probe` learns about one agent without spending a model call.
type probeResult struct {
	Agent      string                  `json:"agent"`
	Version    string                  `json:"version,omitempty"`
	OK         bool                    `json:"ok"`
	Initialize *acp.InitializeResponse `json:"initialize,omitempty"`
	SessionID  string                  `json:"sessionId,omitempty"`
	Error      string                  `json:"error,omitempty"`
	Millis     int64                   `json:"ms"`
}

func cmdProbe(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("probe", flag.ContinueOnError)
	asJSON := fs.Bool("json", false, "print JSON")
	all := fs.Bool("all", false, "probe every supported agent installed here")
	if err := fs.Parse(args); err != nil {
		return err
	}
	found := agents.Discover(ctx, agents.HostEnv)
	byID := map[string]agents.Found{}
	for _, f := range found {
		byID[f.ID] = f
	}
	ids := fs.Args()
	if *all {
		ids = nil
		for _, f := range found {
			if f.Supported {
				ids = append(ids, f.ID)
			}
		}
	}
	if len(ids) == 0 {
		return errors.New("probe: name an agent, or --all")
	}
	var results []probeResult
	for _, id := range ids {
		f, ok := byID[id]
		if !ok {
			results = append(results, probeResult{Agent: id, Error: "not installed (or not in the catalog)"})
			continue
		}
		r := probe(ctx, f)
		results = append(results, r)
		if !*asJSON {
			if r.OK {
				name := "?"
				if r.Initialize.AgentInfo != nil {
					name = strings.TrimSpace(r.Initialize.AgentInfo.Name + " " + r.Initialize.AgentInfo.Version)
				}
				c := r.Initialize.AgentCapabilities
				fmt.Printf("%-9s ok    %5d ms  agent=%q acp=v%d loadSession=%v mcp(http=%v sse=%v) image=%v auth=%d session=%s\n",
					id, r.Millis, name, r.Initialize.ProtocolVersion, c.LoadSession, c.McpCapabilities.HTTP, c.McpCapabilities.SSE,
					c.PromptCapabilities.Image, len(r.Initialize.AuthMethods), r.SessionID)
			} else {
				fmt.Printf("%-9s FAIL  %5d ms  %s\n", id, r.Millis, firstLine(r.Error))
			}
		}
	}
	if *asJSON {
		return printJSON(results)
	}
	return nil
}

func probe(ctx context.Context, f agents.Found) (r probeResult) {
	r = probeResult{Agent: f.ID, Version: f.Version}
	start := time.Now()
	defer func() { r.Millis = time.Since(start).Milliseconds() }()
	ctx, cancel := context.WithTimeout(ctx, 90*time.Second)
	defer cancel()

	dir, err := os.MkdirTemp("", "quire-probe-")
	if err != nil {
		r.Error = err.Error()
		return r
	}
	defer os.RemoveAll(dir)
	a, err := harness.Start(ctx, f.Spec, refuseAll{}, harness.Options{Path: f.Path, Version: f.Version, ClientInfo: clientInfo, FS: true})
	if err != nil {
		r.Error = err.Error()
		return r
	}
	defer a.Close()
	info := a.Info()
	r.Initialize = &info
	sid, err := a.NewSession(ctx, dir, nil)
	if err != nil {
		r.Error = err.Error()
		return r
	}
	r.SessionID, r.OK = sid, true
	return r
}

// refuseAll is the client for probes: it shows nothing and allows nothing.
type refuseAll struct{}

func (refuseAll) Update(string, json.RawMessage) {}
func (refuseAll) RequestPermission(context.Context, acp.RequestPermissionRequest) (acp.RequestPermissionResponse, error) {
	return acp.Cancelled(), nil
}

type multiFlag []string

func (m *multiFlag) String() string     { return strings.Join(*m, " ") }
func (m *multiFlag) Set(v string) error { *m = append(*m, v); return nil }

func cmdRun(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("run", flag.ContinueOnError)
	cwd := fs.String("cwd", "", "session folder")
	approve := fs.String("approve", "ask", "ask, read, all or none")
	asJSON := fs.Bool("json", false, "NDJSON output")
	fsOn := fs.Bool("fs", true, "serve file access to ACP agents")
	timeout := fs.Duration("timeout", 0, "cancel the turn after this long")
	connect := fs.String("connect", "", "run through the quired serve at ADDR")
	var agentArgs multiFlag
	fs.Var(&agentArgs, "agent-arg", "extra agent argument (repeatable)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() < 2 {
		return errors.New("run: need AGENT and PROMPT")
	}
	switch *approve {
	case "ask", "read", "all", "none":
	default:
		return fmt.Errorf("run: --approve must be ask, read, all or none, not %q", *approve)
	}
	prompt := strings.Join(fs.Args()[1:], " ")
	if prompt == "-" {
		b, err := io.ReadAll(os.Stdin)
		if err != nil {
			return err
		}
		prompt = string(b)
	}
	client := newTermClient(os.Stdout, os.Stderr, *asJSON, *approve)
	var a harness.Agent
	var name, dir string
	if *connect != "" {
		// The serving side picks the folder unless --cwd names one there, and starts the agent
		// with its own catalog; --fs and --agent-arg are its decisions too.
		rm, err := dialRemote(ctx, *connect)
		if err != nil {
			return err
		}
		defer rm.Close()
		if a, err = rm.Agent(ctx, fs.Arg(0), client); err != nil {
			return err
		}
		name, dir = fs.Arg(0)+" via "+*connect, *cwd
	} else {
		spec, ok := agents.Lookup(fs.Arg(0))
		if !ok {
			return fmt.Errorf("run: unknown agent %q (see quired agents)", fs.Arg(0))
		}
		var f *agents.Found
		for _, x := range agents.Discover(ctx, agents.HostEnv) {
			if x.ID == spec.ID {
				f = &x
			}
		}
		if f == nil {
			return fmt.Errorf("run: %s is not installed here", spec.ID)
		}
		dir = *cwd
		if dir == "" {
			d, err := os.MkdirTemp("", "quire-session-")
			if err != nil {
				return err
			}
			dir = d
		}
		var err error
		if dir, err = absDir(dir); err != nil {
			return err
		}
		if a, err = harness.Start(ctx, f.Spec, client, harness.Options{Path: f.Path, Version: f.Version, ClientInfo: clientInfo, FS: *fsOn, Args: agentArgs}); err != nil {
			return err
		}
		name = f.Name
	}
	defer a.Close()
	sid, err := a.NewSession(ctx, dir, nil)
	if err != nil {
		return err
	}
	if dir == "" {
		dir = "(chosen by the server)"
	}
	client.note("%s · session %s · folder %s", name, sid, dir)

	tctx := ctx
	if *timeout > 0 {
		var cancel context.CancelFunc
		tctx, cancel = context.WithTimeout(ctx, *timeout)
		defer cancel()
	}
	start := time.Now()
	stopReason, err := a.Prompt(tctx, sid, []acp.ContentBlock{acp.TextBlock(prompt)})
	client.finish(stopReason, time.Since(start), err)
	return err
}

func absDir(p string) (string, error) {
	fi, err := os.Stat(p)
	if err != nil {
		return "", err
	}
	if !fi.IsDir() {
		return "", fmt.Errorf("%s is not a folder", p)
	}
	return filepath.Abs(p)
}

func cmdPermissionMCP(args []string) error {
	fs := flag.NewFlagSet("permission-mcp", flag.ContinueOnError)
	socket := fs.String("socket", "", "quired's permission socket")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *socket == "" {
		return errors.New("permission-mcp: --socket is required")
	}
	return harness.ServePermissionMCP(os.Stdin, os.Stdout, *socket, version)
}

// termClient renders a session in a terminal, or as NDJSON with --json, and answers permission
// requests by policy or by asking on the terminal.
type termClient struct {
	mu      sync.Mutex
	out     io.Writer
	log     io.Writer
	json    bool
	approve string
	kinds   map[string]string // tool call id → kind
	titles  map[string]string // tool call id → title
	midLine bool
}

func newTermClient(out, log io.Writer, asJSON bool, approve string) *termClient {
	return &termClient{out: out, log: log, json: asJSON, approve: approve, kinds: map[string]string{}, titles: map[string]string{}}
}

func (t *termClient) emit(v any) {
	b, _ := json.Marshal(v)
	fmt.Fprintf(t.out, "%s\n", b)
}

func (t *termClient) note(format string, args ...any) {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.json {
		t.emit(map[string]any{"quired": "note", "text": fmt.Sprintf(format, args...)})
		return
	}
	fmt.Fprintf(t.log, "\x1b[2m%s\x1b[0m\n", fmt.Sprintf(format, args...))
}

func (t *termClient) Update(sid string, raw json.RawMessage) {
	t.mu.Lock()
	defer t.mu.Unlock()
	var u acp.SessionUpdate
	_ = json.Unmarshal(raw, &u)
	if u.ToolCallID != "" {
		if u.ToolKind != "" {
			t.kinds[u.ToolCallID] = u.ToolKind
		}
		if u.Title != "" {
			t.titles[u.ToolCallID] = u.Title
		}
	}
	if t.json {
		t.emit(map[string]any{"jsonrpc": "2.0", "method": acp.MethodSessionUpdate, "params": acp.SessionNotification{SessionID: sid, Update: raw}})
		return
	}
	switch u.Kind {
	case acp.UpdateAgentMessageChunk:
		text := u.ChunkText()
		fmt.Fprint(t.out, text)
		t.midLine = !strings.HasSuffix(text, "\n")
	case acp.UpdateToolCall:
		t.line("\x1b[36m▸ %s\x1b[0m", t.titles[u.ToolCallID])
	case acp.UpdateToolCallUpdate:
		switch u.Status {
		case acp.StatusCompleted:
			t.line("\x1b[32m✓ %s\x1b[0m", t.titles[u.ToolCallID])
		case acp.StatusFailed:
			t.line("\x1b[31m✗ %s\x1b[0m", t.titles[u.ToolCallID])
		}
	case acp.UpdatePlan:
		marks := map[string]string{"completed": "x", "in_progress": "~"}
		for _, e := range u.Entries {
			m := marks[e.Status]
			if m == "" {
				m = " "
			}
			t.line("\x1b[2m[%s] %s\x1b[0m", m, e.Content)
		}
	}
}

// line writes one status line to the log, after ending any half-written message line.
func (t *termClient) line(format string, args ...any) {
	if t.midLine {
		fmt.Fprintln(t.out)
		t.midLine = false
	}
	fmt.Fprintf(t.log, format+"\n", args...)
}

func (t *termClient) RequestPermission(ctx context.Context, req acp.RequestPermissionRequest) (acp.RequestPermissionResponse, error) {
	t.mu.Lock()
	kind := req.ToolCall.Kind
	if kind == "" {
		kind = t.kinds[req.ToolCall.ToolCallID]
	}
	title := req.ToolCall.Title
	if title == "" {
		title = t.titles[req.ToolCall.ToolCallID]
	}
	t.mu.Unlock()

	var res acp.RequestPermissionResponse
	var err error
	switch t.approve {
	case "all":
		res = choose(req.Options, acp.AllowOnce, acp.AllowAlways)
	case "none":
		res = choose(req.Options, acp.RejectOnce, acp.RejectAlways)
	case "read":
		if kind == acp.KindRead || kind == acp.KindSearch || kind == acp.KindThink {
			res = choose(req.Options, acp.AllowOnce, acp.AllowAlways)
		} else {
			res = choose(req.Options, acp.RejectOnce, acp.RejectAlways)
		}
	default:
		res, err = t.ask(ctx, title, kind, req.Options)
	}
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.json {
		t.emit(map[string]any{"quired": "permission", "request": req, "response": res})
	} else {
		t.line("\x1b[33m? %s (%s) → %s\x1b[0m", title, kind, describeOutcome(req.Options, res))
	}
	return res, err
}

// ask puts the question to the person at the terminal.
func (t *termClient) ask(ctx context.Context, title, kind string, opts []acp.PermissionOption) (acp.RequestPermissionResponse, error) {
	tty, err := os.OpenFile("/dev/tty", os.O_RDWR, 0)
	if err != nil {
		return choose(opts, acp.RejectOnce, acp.RejectAlways), nil // nobody to ask
	}
	defer tty.Close()
	t.mu.Lock()
	if t.midLine {
		fmt.Fprintln(t.out)
		t.midLine = false
	}
	fmt.Fprintf(tty, "\x1b[33m? Allow %s (%s)?\x1b[0m", title, kind)
	for i, o := range opts {
		fmt.Fprintf(tty, "  [%d] %s", i+1, o.Name)
	}
	fmt.Fprint(tty, "  > ")
	t.mu.Unlock()

	answer := make(chan string, 1)
	go func() {
		s, _ := bufio.NewReader(tty).ReadString('\n')
		answer <- strings.TrimSpace(s)
	}()
	select {
	case <-ctx.Done():
		return acp.Cancelled(), nil
	case s := <-answer:
		var n int
		if _, err := fmt.Sscan(s, &n); err == nil && n >= 1 && n <= len(opts) {
			return acp.Selected(opts[n-1].OptionID), nil
		}
		return choose(opts, acp.RejectOnce, acp.RejectAlways), nil
	}
}

// choose picks the first option of the first kind present; with none, the request is cancelled.
func choose(opts []acp.PermissionOption, kinds ...string) acp.RequestPermissionResponse {
	for _, k := range kinds {
		for _, o := range opts {
			if o.Kind == k {
				return acp.Selected(o.OptionID)
			}
		}
	}
	return acp.Cancelled()
}

func describeOutcome(opts []acp.PermissionOption, res acp.RequestPermissionResponse) string {
	if res.Outcome.Outcome != acp.OutcomeSelected {
		return "cancelled"
	}
	for _, o := range opts {
		if o.OptionID == res.Outcome.OptionID {
			return o.Name
		}
	}
	return res.Outcome.OptionID
}

func (t *termClient) finish(stop string, d time.Duration, err error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	if t.json {
		r := map[string]any{"quired": "result", "stopReason": stop, "ms": d.Milliseconds()}
		if err != nil {
			r["error"] = err.Error()
		}
		t.emit(r)
		return
	}
	if t.midLine {
		fmt.Fprintln(t.out)
		t.midLine = false
	}
	if err == nil {
		fmt.Fprintf(t.log, "\x1b[2m— %s in %.1f s\x1b[0m\n", stop, d.Seconds())
	}
}

func printJSON(v any) error {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}

func firstLine(s string) string { l, _, _ := strings.Cut(s, "\n"); return l }
