package harness

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
)

// The test binary doubles as the agents under test: QUIRED_FAKE picks which one it plays.
func TestMain(m *testing.M) {
	if len(os.Args) > 1 && os.Args[1] == "permission-mcp" { // what the Claude adapter starts as opts.Self
		fs := flag.NewFlagSet("permission-mcp", flag.ExitOnError)
		socket := fs.String("socket", "", "")
		_ = fs.Parse(os.Args[2:])
		if err := ServePermissionMCP(os.Stdin, os.Stdout, *socket, "test"); err != nil {
			os.Exit(1)
		}
		os.Exit(0)
	}
	switch os.Getenv("QUIRED_FAKE") {
	case "acp":
		fakeACP()
		os.Exit(0)
	case "claude":
		fakeClaude()
		os.Exit(0)
	case "stuck":
		fakeStuck()
		os.Exit(0)
	}
	os.Exit(m.Run())
}

// recorder is a Client that keeps every update and answers permissions with a fixed option kind.
type recorder struct {
	mu      sync.Mutex
	updates []acp.SessionUpdate
	asked   []acp.RequestPermissionRequest
	answer  string // option kind to pick; "" cancels
	block   bool   // wait for ctx to end instead of answering, like a person who walked away
}

func (r *recorder) Update(_ string, raw json.RawMessage) {
	var u acp.SessionUpdate
	if err := json.Unmarshal(raw, &u); err != nil {
		panic(err)
	}
	r.mu.Lock()
	r.updates = append(r.updates, u)
	r.mu.Unlock()
}

func (r *recorder) RequestPermission(ctx context.Context, req acp.RequestPermissionRequest) (acp.RequestPermissionResponse, error) {
	r.mu.Lock()
	r.asked = append(r.asked, req)
	r.mu.Unlock()
	if r.block {
		<-ctx.Done()
		return acp.RequestPermissionResponse{}, ctx.Err()
	}
	for _, o := range req.Options {
		if o.Kind == r.answer {
			return acp.Selected(o.OptionID), nil
		}
	}
	return acp.Cancelled(), nil
}

func (r *recorder) text() string {
	r.mu.Lock()
	defer r.mu.Unlock()
	var b strings.Builder
	for _, u := range r.updates {
		if u.Kind == acp.UpdateAgentMessageChunk {
			b.WriteString(u.ChunkText())
		}
	}
	return b.String()
}

// tool returns the sequence of statuses and the last title seen for one tool call.
func (r *recorder) tool(id string) (statuses []string, title string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	for _, u := range r.updates {
		if u.ToolCallID == id {
			statuses = append(statuses, u.Status)
			if u.Title != "" {
				title = u.Title
			}
		}
	}
	return statuses, title
}

func self(t *testing.T) string {
	t.Helper()
	p, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	return p
}

func startFake(t *testing.T, kind string, spec agents.Spec, r *recorder, env ...string) Agent {
	t.Helper()
	a, err := Start(context.Background(), spec, r, Options{Path: self(t), Self: self(t), FS: true,
		ClientInfo: acp.Implementation{Name: "test"}, Env: append([]string{"QUIRED_FAKE=" + kind}, env...)})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { a.Close() })
	return a
}

var acpSpec = agents.Spec{ID: "fake", Name: "Fake", Protocol: agents.ACP, Args: []string{"acp"}}

func TestACPAgentTurnWithFilesAndPermission(t *testing.T) {
	r := &recorder{answer: acp.AllowOnce}
	a := startFake(t, "acp", acpSpec, r)
	if info := a.Info(); info.AgentInfo == nil || info.AgentInfo.Name != "fake-acp" || !info.AgentCapabilities.LoadSession {
		t.Fatalf("initialize: %+v", info)
	}
	dir := t.TempDir()
	sid, err := a.NewSession(context.Background(), dir, nil)
	if err != nil {
		t.Fatal(err)
	}
	stop, err := a.Prompt(context.Background(), sid, []acp.ContentBlock{acp.TextBlock("write")})
	if err != nil || stop != acp.StopEndTurn {
		t.Fatalf("prompt: %q, %v", stop, err)
	}
	if got, _ := os.ReadFile(filepath.Join(dir, "out.txt")); string(got) != "from fake" {
		t.Fatalf("out.txt = %q", got)
	}
	if st, title := r.tool("t1"); strings.Join(st, ",") != "pending,completed" || title != "Write out.txt" {
		t.Fatalf("tool t1: %v %q", st, title)
	}
	// The fake also tries to read /etc/hostname and a symlink out of the folder: both must fail.
	if txt := r.text(); txt != "Hello read-back=from fake outside=refused symlink=refused" {
		t.Fatalf("text = %q", txt)
	}
	if len(r.asked) != 1 || r.asked[0].ToolCall.Kind != acp.KindEdit {
		t.Fatalf("permission requests: %+v", r.asked)
	}
}

func TestACPAgentDenied(t *testing.T) {
	r := &recorder{answer: acp.RejectOnce}
	a := startFake(t, "acp", acpSpec, r)
	dir := t.TempDir()
	sid, err := a.NewSession(context.Background(), dir, nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := a.Prompt(context.Background(), sid, []acp.ContentBlock{acp.TextBlock("write")}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir, "out.txt")); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("out.txt should not exist: %v", err)
	}
	if st, _ := r.tool("t1"); strings.Join(st, ",") != "pending,failed" {
		t.Fatalf("tool t1: %v", st)
	}
}

func TestACPAgentCancel(t *testing.T) {
	r := &recorder{}
	a := startFake(t, "acp", acpSpec, r)
	sid, err := a.NewSession(context.Background(), t.TempDir(), nil)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	start := time.Now()
	stop, err := a.Prompt(ctx, sid, []acp.ContentBlock{acp.TextBlock("wait")})
	if err != nil || stop != acp.StopCancelled {
		t.Fatalf("prompt: %q, %v", stop, err)
	}
	if d := time.Since(start); d > 5*time.Second {
		t.Fatalf("cancel took %s", d)
	}
}

func TestACPCancelAnswersOpenPermissionRequest(t *testing.T) {
	r := &recorder{block: true}
	a := startFake(t, "acp", acpSpec, r)
	dir := t.TempDir()
	sid, err := a.NewSession(context.Background(), dir, nil)
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	start := time.Now()
	stop, err := a.Prompt(ctx, sid, []acp.ContentBlock{acp.TextBlock("write")})
	if err != nil || stop != acp.StopCancelled {
		t.Fatalf("prompt: %q, %v", stop, err)
	}
	if d := time.Since(start); d > 5*time.Second {
		t.Fatalf("cancel took %s", d)
	}
	if _, err := os.Stat(filepath.Join(dir, "out.txt")); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("a cancelled permission request let the write run")
	}
}

func TestStartFailureCarriesStderr(t *testing.T) {
	_, err := Start(context.Background(), acpSpec, &recorder{}, Options{Path: self(t), Self: self(t),
		Env: []string{"QUIRED_FAKE=acp", "FAKE_ACP_DIE=1"}})
	if err == nil || !strings.Contains(err.Error(), "fake agent: no credentials") {
		t.Fatalf("want the agent's stderr in the error, got %v", err)
	}
}

var claudeSpec = agents.Spec{ID: "claude", Name: "Claude Code", Protocol: agents.ClaudeStream}

func TestClaudeAdapterAllowsThroughBridge(t *testing.T) {
	r := &recorder{answer: acp.AllowOnce}
	a := startFake(t, "claude", claudeSpec, r)
	dir := t.TempDir()
	sid, err := a.NewSession(context.Background(), dir, nil)
	if err != nil {
		t.Fatal(err)
	}
	for turn := 1; turn <= 2; turn++ {
		stop, err := a.Prompt(context.Background(), sid, []acp.ContentBlock{acp.TextBlock("make hello")})
		if err != nil || stop != acp.StopEndTurn {
			t.Fatalf("turn %d: %q, %v\n%s", turn, stop, err, a.Diagnostics())
		}
	}
	if got, _ := os.ReadFile(filepath.Join(dir, "hello.txt")); string(got) != "hi" {
		t.Fatalf("hello.txt = %q", got)
	}
	args := readArgs(t, dir)
	if len(args) != 2 || !contains(args[0], "--session-id", sid) || !contains(args[1], "--resume", sid) {
		t.Fatalf("first turn must create the session and the second resume it: %q", args)
	}
	if st, title := r.tool("toolu_w"); strings.Join(st, ",") != "pending,in_progress,completed,pending,in_progress,completed" || title != "Write hello.txt" {
		t.Fatalf("tool: %v %q", st, title)
	}
	if txt := r.text(); txt != "Done.Done." { // deltas only: the assembled message must not repeat them
		t.Fatalf("text = %q", txt)
	}
	var plans int
	for _, u := range r.updates {
		if u.Kind == acp.UpdatePlan && len(u.Entries) == 2 && u.Entries[1].Status == "in_progress" {
			plans++
		}
		if u.ToolCallID == "toolu_todo" {
			t.Fatalf("TodoWrite must show as a plan, not a tool call: %+v", u)
		}
	}
	if plans != 2 {
		t.Fatalf("want one plan per turn, got %d", plans)
	}
	if len(r.asked) != 2 || r.asked[0].ToolCall.Title != "Write hello.txt" {
		t.Fatalf("permission requests: %+v", r.asked)
	}
}

func TestClaudeAdapterAlwaysAndDeny(t *testing.T) {
	r := &recorder{answer: acp.AllowAlways}
	a := startFake(t, "claude", claudeSpec, r)
	dir := t.TempDir()
	sid, _ := a.NewSession(context.Background(), dir, nil)
	for i := 0; i < 2; i++ {
		if _, err := a.Prompt(context.Background(), sid, []acp.ContentBlock{acp.TextBlock("make hello")}); err != nil {
			t.Fatal(err)
		}
	}
	if len(r.asked) != 1 {
		t.Fatalf("\"allow for this session\" should be asked once, was asked %d times", len(r.asked))
	}

	r2 := &recorder{answer: acp.RejectOnce}
	b := startFake(t, "claude", claudeSpec, r2)
	dir2 := t.TempDir()
	sid2, _ := b.NewSession(context.Background(), dir2, nil)
	if _, err := b.Prompt(context.Background(), sid2, []acp.ContentBlock{acp.TextBlock("make hello")}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(filepath.Join(dir2, "hello.txt")); !errors.Is(err, os.ErrNotExist) {
		t.Fatal("a denied Write ran")
	}
	if st, _ := r2.tool("toolu_w"); st[len(st)-1] != acp.StatusFailed {
		t.Fatalf("denied tool should fail: %v", st)
	}
}

func TestClaudeAdapterCancel(t *testing.T) {
	r := &recorder{}
	a := startFake(t, "claude", claudeSpec, r)
	sid, _ := a.NewSession(context.Background(), t.TempDir(), nil)
	ctx, cancel := context.WithTimeout(context.Background(), 300*time.Millisecond)
	defer cancel()
	stop, err := a.Prompt(ctx, sid, []acp.ContentBlock{acp.TextBlock("wait")})
	if err != nil || stop != acp.StopCancelled {
		t.Fatalf("prompt: %q, %v", stop, err)
	}
}

// The adapter against a real Claude Code 2.1.301 stream (haiku reading a file), paths sanitized.
func TestClaudeRecordedStream(t *testing.T) {
	f, err := os.Open("testdata/claude-2.1.301-read.ndjson")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	r := &recorder{}
	turn := &claudeTurn{sid: "11111111-2222-4333-8444-555555555555", client: r, texted: map[string]bool{}, tools: map[string]string{}, hidden: map[string]bool{}}
	turn.read(f, io.Discard)
	if !turn.done || turn.err != nil || turn.stop != acp.StopEndTurn || !turn.sawInit {
		t.Fatalf("turn: done=%v err=%v stop=%q init=%v", turn.done, turn.err, turn.stop, turn.sawInit)
	}
	if txt := r.text(); txt != "LANTERN-7" {
		t.Fatalf("text = %q", txt)
	}
	st, title := r.tool("toolu_011RQp6PmkcpBrSAwqTRzeGQ")
	if strings.Join(st, ",") != "pending,in_progress,completed" || title != "Read note.txt" {
		t.Fatalf("tool: %v %q", st, title)
	}
}

func TestClaudeSeparateMessagesAreSeparateParagraphs(t *testing.T) {
	r := &recorder{}
	turn := &claudeTurn{sid: "s", client: r, texted: map[string]bool{}, tools: map[string]string{}, hidden: map[string]bool{}}
	stream := `{"type":"stream_event","api_message_id":"m1","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"Trying another way."}}}
{"type":"assistant","message":{"id":"m1","content":[{"type":"text","text":"Trying another way."}]}}
{"type":"assistant","message":{"id":"m2","content":[{"type":"text","text":"Done."}]}}
{"type":"result","subtype":"success","stop_reason":"end_turn"}
`
	turn.read(strings.NewReader(stream), io.Discard)
	if txt := r.text(); txt != "Trying another way.\n\nDone." {
		t.Fatalf("text = %q", txt)
	}
}

func TestFileConfinement(t *testing.T) {
	root, outside := t.TempDir(), t.TempDir()
	if err := os.WriteFile(filepath.Join(outside, "secret.txt"), []byte("secret"), 0o600); err != nil {
		t.Fatal(err)
	}
	for link, target := range map[string]string{
		"link":        outside,                                     // a folder outside
		"dangling":    filepath.Join(outside, "new.txt"),           // a file outside that doesn't exist yet
		"danglingdir": filepath.Join(outside, "nodir"),             // a folder outside that doesn't exist yet
		"alias.txt":   "inside.txt",                                // stays inside, target not there yet
		"up":          filepath.Join("..", filepath.Base(outside)), // relative, leads out
	} {
		if err := os.Symlink(target, filepath.Join(root, link)); err != nil {
			t.Fatal(err)
		}
	}
	if err := syscall.Mkfifo(filepath.Join(root, "fifo"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "private.txt"), []byte("x"), 0o600); err != nil {
		t.Fatal(err)
	}

	for _, c := range []struct {
		path string
		ok   bool
	}{
		{filepath.Join(root, "a.txt"), true},
		{filepath.Join(root, "new", "dir", "b.txt"), true},
		{filepath.Join(root, "alias.txt"), true}, // creates inside.txt
		{filepath.Join(root, "private.txt"), true},
		{filepath.Join(root, "..", filepath.Base(outside), "x"), false},
		{filepath.Join(root, "link", "x"), false},
		{filepath.Join(root, "dangling"), false},
		{filepath.Join(root, "danglingdir", "x.txt"), false},
		{filepath.Join(root, "up", "x"), false},
		{filepath.Join(root, "fifo"), false}, // refused, and must not hang
		{"relative.txt", false},
		{"/etc/hostname", false},
	} {
		err := writeText(root, acp.WriteTextFileRequest{Path: c.path, Content: "data"})
		if (err == nil) != c.ok {
			t.Errorf("writeText(%q) err=%v, want ok=%v", c.path, err, c.ok)
		}
	}
	if entries, _ := os.ReadDir(outside); len(entries) != 1 {
		t.Fatalf("a write escaped the session folder: %v", entries)
	}
	if got, _ := os.ReadFile(filepath.Join(root, "inside.txt")); string(got) != "data" {
		t.Fatalf("write through an inside symlink: inside.txt = %q", got)
	}
	if fi, _ := os.Stat(filepath.Join(root, "private.txt")); fi.Mode().Perm() != 0o600 {
		t.Fatalf("an existing file must keep its mode, got %v", fi.Mode().Perm())
	}

	for _, c := range []struct {
		path string
		ok   bool
	}{
		{filepath.Join(root, "alias.txt"), true},
		{filepath.Join(root, "link", "secret.txt"), false},
		{filepath.Join(root, "up", "secret.txt"), false},
		{filepath.Join(outside, "secret.txt"), false},
		{filepath.Join(root, "fifo"), false},
	} {
		res, err := readText(root, acp.ReadTextFileRequest{Path: c.path})
		if (err == nil) != c.ok || strings.Contains(res.Content, "secret") {
			t.Errorf("readText(%q) = %q, %v; want ok=%v", c.path, res.Content, err, c.ok)
		}
	}

	// A session folder reached through a symlink may be named by either path.
	real := t.TempDir()
	alias := filepath.Join(t.TempDir(), "project")
	if err := os.Symlink(real, alias); err != nil {
		t.Fatal(err)
	}
	for _, p := range []string{filepath.Join(alias, "c.txt"), filepath.Join(real, "d.txt")} {
		if err := writeText(alias, acp.WriteTextFileRequest{Path: p, Content: "ok"}); err != nil {
			t.Errorf("writeText(%q) in a symlinked session folder: %v", p, err)
		}
	}
}

func TestStartRejectsUnsupportedProtocolVersion(t *testing.T) {
	_, err := Start(context.Background(), acpSpec, &recorder{}, Options{Path: self(t), Self: self(t),
		Env: []string{"QUIRED_FAKE=acp", "FAKE_ACP_VERSION=999"}})
	if err == nil || !strings.Contains(err.Error(), "protocol version 999") {
		t.Fatalf("want version 999 refused, got %v", err)
	}
}

// shortTimeouts makes the cancel grace and exit grace short for one test.
func shortTimeouts(t *testing.T, cancel, exit time.Duration) {
	oldCancel, oldExit := cancelTimeout, exitGrace
	cancelTimeout, exitGrace = cancel, exit
	t.Cleanup(func() { cancelTimeout, exitGrace = oldCancel, oldExit })
}

// An agent that ignores session/cancel, or stops reading stdin altogether and ignores SIGTERM,
// is stopped once the cancel grace ends: Prompt returns within its bounds and the process is gone.
func TestACPCancelStopsUnresponsiveAgent(t *testing.T) {
	for _, mode := range []string{"ignore", "deaf"} {
		t.Run(mode, func(t *testing.T) {
			shortTimeouts(t, 300*time.Millisecond, 300*time.Millisecond)
			a := startFake(t, "stuck", acpSpec, &recorder{}, "FAKE_STUCK="+mode)
			sid, err := a.NewSession(context.Background(), t.TempDir(), nil)
			if err != nil {
				t.Fatal(err)
			}
			// Bigger than a pipe's buffer, so writing it blocks once the agent stops reading.
			big := strings.Repeat("x", 1<<20)
			ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
			defer cancel()
			start := time.Now()
			stop, err := a.Prompt(ctx, sid, []acp.ContentBlock{acp.TextBlock(big)})
			if stop != acp.StopCancelled || err == nil || !strings.Contains(err.Error(), "quired stopped it") {
				t.Fatalf("prompt: %q, %v", stop, err)
			}
			if d := time.Since(start); d > 5*time.Second {
				t.Fatalf("cancel took %s", d)
			}
			pid := a.(*acpAgent).cmd.Process.Pid
			if err := syscall.Kill(pid, 0); !errors.Is(err, syscall.ESRCH) {
				t.Fatalf("agent %d still exists after Prompt returned: %v", pid, err)
			}
			if _, err := a.NewSession(context.Background(), t.TempDir(), nil); err == nil {
				t.Fatal("a stopped agent accepted session/new")
			}
		})
	}
}

// close must not wait on a peer that sent half a question, or on a question nobody is answering.
func TestPermissionBridgeCloseFreesStalledConnections(t *testing.T) {
	r := &recorder{block: true}
	c := newClaude(claudeSpec, r, Options{})
	bridge, err := c.listenPermissions(context.Background(), "s", &claudeSession{always: map[string]bool{}})
	if err != nil {
		t.Fatal(err)
	}
	for p, want := range map[string]os.FileMode{bridge.dir: 0o700, bridge.socket: 0o600} {
		if fi, err := os.Stat(p); err != nil || fi.Mode().Perm() != want {
			t.Fatalf("%s: want mode %v, got %v (%v)", p, want, fi.Mode().Perm(), err)
		}
	}
	half, err := net.Dial("unix", bridge.socket)
	if err != nil {
		t.Fatal(err)
	}
	defer half.Close()
	if _, err := half.Write([]byte(`{"tool_name":`)); err != nil {
		t.Fatal(err)
	}
	whole, err := net.Dial("unix", bridge.socket)
	if err != nil {
		t.Fatal(err)
	}
	defer whole.Close()
	if err := json.NewEncoder(whole).Encode(permQuestion{ToolName: "Write", Input: json.RawMessage(`{}`)}); err != nil {
		t.Fatal(err)
	}
	for deadline := time.Now().Add(5 * time.Second); ; time.Sleep(5 * time.Millisecond) {
		r.mu.Lock()
		n := len(r.asked)
		r.mu.Unlock()
		if n == 1 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("the whole question never reached the client")
		}
	}

	closed := make(chan struct{})
	go func() { bridge.close(); close(closed) }()
	select {
	case <-closed:
	case <-time.After(5 * time.Second):
		t.Fatal("bridge.close hung on stalled connections")
	}
	for name, conn := range map[string]net.Conn{"half": half, "whole": whole} {
		_ = conn.SetReadDeadline(time.Now().Add(5 * time.Second))
		b, err := io.ReadAll(conn)
		var a permAnswer
		if err != nil || (len(b) > 0 && (json.Unmarshal(b, &a) != nil || a.Behavior != "deny")) {
			t.Fatalf("%s: want hang-up or deny, got %q, %v", name, b, err)
		}
	}
	if _, err := os.Stat(bridge.dir); !errors.Is(err, os.ErrNotExist) {
		t.Fatalf("socket folder left behind: %v", err)
	}
}

// askBridge has no fixed timeout (a person may take a while), so it must end with its context.
func TestAskBridgeEndsWithContext(t *testing.T) {
	socket := filepath.Join(t.TempDir(), "s")
	l, err := listenUnix(socket)
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	held := make(chan net.Conn, 1)
	go func() {
		if conn, err := l.Accept(); err == nil {
			held <- conn // accepted, never answered
		}
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
	defer cancel()
	start := time.Now()
	_, err = askBridge(ctx, socket, permQuestion{ToolName: "Write", Input: json.RawMessage(`{}`)})
	if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) > 5*time.Second {
		t.Fatalf("want deadline exceeded promptly, got %v after %s", err, time.Since(start))
	}
	(<-held).Close()
}

func readArgs(t *testing.T, dir string) [][]string {
	t.Helper()
	b, err := os.ReadFile(filepath.Join(dir, ".fake-claude-args"))
	if err != nil {
		t.Fatal(err)
	}
	var out [][]string
	for _, l := range strings.Split(strings.TrimSpace(string(b)), "\n") {
		var a []string
		_ = json.Unmarshal([]byte(l), &a)
		out = append(out, a)
	}
	return out
}

func contains(args []string, flag, value string) bool {
	for i := 0; i+1 < len(args); i++ {
		if args[i] == flag && args[i+1] == value {
			return true
		}
	}
	return false
}

// fakeACP is a small ACP agent: it greets, asks to write out.txt through the client, reads it
// back, and tries two reads it must be refused.
func fakeACP() {
	if os.Getenv("FAKE_ACP_DIE") != "" {
		fmt.Fprintln(os.Stderr, "fake agent: no credentials")
		os.Exit(3)
	}
	var conn *acp.Conn
	var mu sync.Mutex
	cwd := map[string]string{}
	cancelled := make(chan struct{}, 1)
	say := func(sid, s string) {
		_ = conn.Notify(context.Background(), acp.MethodSessionUpdate, acp.SessionNotification{SessionID: sid, Update: acp.ChunkUpdate(acp.UpdateAgentMessageChunk, s).Marshal()})
	}
	tool := func(sid string, u acp.SessionUpdate) {
		_ = conn.Notify(context.Background(), acp.MethodSessionUpdate, acp.SessionNotification{SessionID: sid, Update: u.Marshal()})
	}
	h := acp.Handlers{
		Notification: func(method string, _ json.RawMessage) {
			if method == acp.MethodCancel {
				cancelled <- struct{}{}
			}
		},
		Request: func(ctx context.Context, method string, params json.RawMessage) (any, error) {
			switch method {
			case acp.MethodInitialize:
				version := 1
				if v := os.Getenv("FAKE_ACP_VERSION"); v != "" {
					_ = json.Unmarshal([]byte(v), &version)
				}
				return acp.InitializeResponse{ProtocolVersion: version, AgentCapabilities: acp.AgentCapabilities{LoadSession: true},
					AuthMethods: []acp.AuthMethod{}, AgentInfo: &acp.Implementation{Name: "fake-acp", Version: "1"}}, nil
			case acp.MethodSessionNew:
				var req acp.NewSessionRequest
				_ = json.Unmarshal(params, &req)
				mu.Lock()
				cwd["s-1"] = req.Cwd
				mu.Unlock()
				return acp.NewSessionResponse{SessionID: "s-1"}, nil
			case acp.MethodPrompt:
				var req acp.PromptRequest
				_ = json.Unmarshal(params, &req)
				if req.Prompt[0].Text == "wait" {
					<-cancelled
					return acp.PromptResponse{StopReason: acp.StopCancelled}, nil
				}
				sid := req.SessionID
				mu.Lock()
				dir := cwd[sid]
				mu.Unlock()
				say(sid, "Hello ")
				tool(sid, acp.SessionUpdate{Kind: acp.UpdateToolCall, ToolCallID: "t1", Title: "Write out.txt", ToolKind: acp.KindEdit, Status: acp.StatusPending})
				var perm acp.RequestPermissionResponse
				_ = conn.Call(ctx, acp.MethodRequestPermission, acp.RequestPermissionRequest{SessionID: sid,
					ToolCall: acp.ToolCallRef{ToolCallID: "t1", Kind: acp.KindEdit, Title: "Write out.txt"},
					Options:  []acp.PermissionOption{{OptionID: "y", Name: "Yes", Kind: acp.AllowOnce}, {OptionID: "n", Name: "No", Kind: acp.RejectOnce}}}, &perm)
				if perm.Outcome.Outcome == acp.OutcomeCancelled {
					return acp.PromptResponse{StopReason: acp.StopCancelled}, nil
				}
				if perm.Outcome.OptionID != "y" {
					tool(sid, acp.SessionUpdate{Kind: acp.UpdateToolCallUpdate, ToolCallID: "t1", Status: acp.StatusFailed})
					return acp.PromptResponse{StopReason: acp.StopEndTurn}, nil
				}
				p := filepath.Join(dir, "out.txt")
				_ = conn.Call(ctx, acp.MethodWriteTextFile, acp.WriteTextFileRequest{SessionID: sid, Path: p, Content: "from fake"}, nil)
				var rd acp.ReadTextFileResponse
				_ = conn.Call(ctx, acp.MethodReadTextFile, acp.ReadTextFileRequest{SessionID: sid, Path: p}, &rd)
				tool(sid, acp.SessionUpdate{Kind: acp.UpdateToolCallUpdate, ToolCallID: "t1", Status: acp.StatusCompleted})
				say(sid, "read-back="+rd.Content)
				refused := func(path string) string {
					if err := conn.Call(ctx, acp.MethodReadTextFile, acp.ReadTextFileRequest{SessionID: sid, Path: path}, nil); err != nil {
						return "refused"
					}
					return "allowed"
				}
				_ = os.Symlink("/etc", filepath.Join(dir, "etc"))
				say(sid, " outside="+refused("/etc/hostname"))
				say(sid, " symlink="+refused(filepath.Join(dir, "etc", "hostname")))
				return acp.PromptResponse{StopReason: acp.StopEndTurn}, nil
			}
			return nil, acp.Errorf(acp.CodeMethodNotFound, "%s", method)
		},
	}
	conn = acp.NewConn(os.Stdin, os.Stdout, h, nil)
	<-conn.Done()
}

// fakeStuck answers initialize and session/new and nothing else. FAKE_STUCK=ignore keeps reading
// and ignores the prompt and session/cancel; FAKE_STUCK=deaf stops reading stdin and ignores
// SIGTERM, like an agent wedged in a tool call, so only SIGKILL stops it.
func fakeStuck() {
	deaf := os.Getenv("FAKE_STUCK") == "deaf"
	if deaf {
		signal.Ignore(syscall.SIGTERM)
	}
	in := bufio.NewReader(os.Stdin)
	for {
		line, err := in.ReadBytes('\n')
		if err != nil {
			return
		}
		var m struct {
			ID     json.RawMessage `json:"id"`
			Method string          `json:"method"`
		}
		_ = json.Unmarshal(line, &m)
		var result any
		switch m.Method {
		case acp.MethodInitialize:
			result = acp.InitializeResponse{ProtocolVersion: 1, AuthMethods: []acp.AuthMethod{}}
		case acp.MethodSessionNew:
			result = acp.NewSessionResponse{SessionID: "s-1"}
		default:
			continue
		}
		b, _ := json.Marshal(map[string]any{"jsonrpc": "2.0", "id": m.ID, "result": result})
		_, _ = os.Stdout.Write(append(b, '\n'))
		if deaf && m.Method == acp.MethodSessionNew {
			time.Sleep(time.Hour)
		}
	}
}

// fakeClaude plays Claude Code's print mode: it plans with TodoWrite, asks the permission tool
// (through the MCP server named in --mcp-config, as Claude Code does) before writing hello.txt,
// and streams "Done." as deltas followed by the assembled message.
func fakeClaude() {
	args := os.Args[1:]
	wd, _ := os.Getwd()
	if f, err := os.OpenFile(filepath.Join(wd, ".fake-claude-args"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600); err == nil {
		b, _ := json.Marshal(args)
		fmt.Fprintf(f, "%s\n", b)
		f.Close()
	}
	flagValue := func(name string) string {
		for i := 0; i+1 < len(args); i++ {
			if args[i] == name {
				return args[i+1]
			}
		}
		return ""
	}
	sid := flagValue("--session-id")
	if sid == "" {
		sid = flagValue("--resume")
	}
	prompt, _ := io.ReadAll(os.Stdin)
	out := bufio.NewWriter(os.Stdout)
	emit := func(v any) {
		b, _ := json.Marshal(v)
		out.Write(append(b, '\n'))
		out.Flush()
	}
	emit(map[string]any{"type": "system", "subtype": "init", "session_id": sid})
	if strings.TrimSpace(string(prompt)) == "wait" {
		time.Sleep(time.Minute) // until SIGINT
		return
	}
	todos := map[string]any{"todos": []any{
		map[string]any{"content": "Plan", "status": "completed", "activeForm": "Planning"},
		map[string]any{"content": "Write hello.txt", "status": "in_progress", "activeForm": "Writing"},
	}}
	emit(map[string]any{"type": "stream_event", "api_message_id": "m1", "session_id": sid,
		"event": map[string]any{"type": "content_block_start", "content_block": map[string]any{"type": "tool_use", "id": "toolu_todo", "name": "TodoWrite", "input": map[string]any{}}}})
	emit(map[string]any{"type": "assistant", "session_id": sid, "message": map[string]any{"id": "m1", "content": []any{
		map[string]any{"type": "tool_use", "id": "toolu_todo", "name": "TodoWrite", "input": todos}}}})
	emit(map[string]any{"type": "user", "session_id": sid, "message": map[string]any{"content": []any{
		map[string]any{"type": "tool_result", "tool_use_id": "toolu_todo", "content": "ok"}}}})

	input := map[string]any{"file_path": filepath.Join(wd, "hello.txt"), "content": "hi"}
	emit(map[string]any{"type": "stream_event", "api_message_id": "m2", "session_id": sid,
		"event": map[string]any{"type": "content_block_start", "content_block": map[string]any{"type": "tool_use", "id": "toolu_w", "name": "Write", "input": map[string]any{}}}})
	emit(map[string]any{"type": "assistant", "session_id": sid, "message": map[string]any{"id": "m2", "content": []any{
		map[string]any{"type": "tool_use", "id": "toolu_w", "name": "Write", "input": input}}}})

	allowed, why := askPermission(flagValue("--mcp-config"), flagValue("--permission-prompt-tool"), input)
	if allowed {
		_ = os.WriteFile(filepath.Join(wd, "hello.txt"), []byte("hi"), 0o644)
		emit(map[string]any{"type": "user", "session_id": sid, "message": map[string]any{"content": []any{
			map[string]any{"type": "tool_result", "tool_use_id": "toolu_w", "content": []any{map[string]any{"type": "text", "text": "File created"}}}}}})
	} else {
		emit(map[string]any{"type": "user", "session_id": sid, "message": map[string]any{"content": []any{
			map[string]any{"type": "tool_result", "tool_use_id": "toolu_w", "is_error": true, "content": why}}}})
	}
	for _, d := range []string{"Do", "ne."} {
		emit(map[string]any{"type": "stream_event", "api_message_id": "m3", "session_id": sid,
			"event": map[string]any{"type": "content_block_delta", "delta": map[string]any{"type": "text_delta", "text": d}}})
	}
	emit(map[string]any{"type": "assistant", "session_id": sid, "message": map[string]any{"id": "m3", "content": []any{
		map[string]any{"type": "text", "text": "Done."}}}})
	emit(map[string]any{"type": "result", "subtype": "success", "is_error": false, "stop_reason": "end_turn", "session_id": sid, "result": "Done."})
}

// askPermission starts the MCP server from --mcp-config and calls the permission tool, like Claude Code.
func askPermission(mcpConfig, toolRef string, input map[string]any) (bool, string) {
	var cfg struct {
		McpServers map[string]struct {
			Command string   `json:"command"`
			Args    []string `json:"args"`
		} `json:"mcpServers"`
	}
	if err := json.Unmarshal([]byte(mcpConfig), &cfg); err != nil {
		return false, "bad --mcp-config"
	}
	parts := strings.SplitN(toolRef, "__", 3) // mcp__<server>__<tool>
	if len(parts) != 3 {
		return false, "bad --permission-prompt-tool"
	}
	srv := cfg.McpServers[parts[1]]
	cmd := exec.Command(srv.Command, srv.Args...)
	cmd.Env = os.Environ()
	in, _ := cmd.StdinPipe()
	outp, _ := cmd.StdoutPipe()
	if err := cmd.Start(); err != nil {
		return false, err.Error()
	}
	defer func() { in.Close(); _ = cmd.Wait() }()
	conn := acp.NewConn(outp, in, acp.Handlers{}, nil)
	ctx := context.Background()
	var init map[string]any
	if err := conn.Call(ctx, "initialize", map[string]any{"protocolVersion": "2025-06-18", "capabilities": map[string]any{},
		"clientInfo": map[string]any{"name": "fake-claude", "version": "0"}}, &init); err != nil {
		return false, err.Error()
	}
	_ = conn.Notify(ctx, "notifications/initialized", map[string]any{})
	var res struct {
		Content []struct {
			Text string `json:"text"`
		} `json:"content"`
	}
	if err := conn.Call(ctx, "tools/call", map[string]any{"name": parts[2], "arguments": map[string]any{
		"tool_name": "Write", "input": input, "tool_use_id": "toolu_w"}}, &res); err != nil {
		return false, err.Error()
	}
	var ans permAnswer
	if len(res.Content) == 0 || json.Unmarshal([]byte(res.Content[0].Text), &ans) != nil {
		return false, "bad answer"
	}
	return ans.Behavior == "allow", ans.Message
}
