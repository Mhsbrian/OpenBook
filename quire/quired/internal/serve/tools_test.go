package serve

import (
	"context"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/harness"
)

const testSkill = "# You are Quire on OpenBook\n"

// toolsClient is Quire core's side of the tools: it records the calls and answers them.
type toolsClient struct {
	mu    sync.Mutex
	calls []toolsCallParams
	lists int
	hold  chan struct{} // if set, a call waits on it (or its ctx)
	ended chan string   // receives "cancelled" when a held call's ctx ends
}

func (tc *toolsClient) handle(ctx context.Context, method string, params json.RawMessage) (any, error) {
	switch method {
	case MethodToolsList:
		tc.mu.Lock()
		tc.lists++
		tc.mu.Unlock()
		return map[string]any{"instructions": "Use these to act on the laptop.",
			"tools": []any{map[string]any{"name": "open_url", "description": "Open a web page", "inputSchema": map[string]any{"type": "object"}}}}, nil
	case MethodToolsCall:
		var p toolsCallParams
		_ = json.Unmarshal(params, &p)
		tc.mu.Lock()
		tc.calls = append(tc.calls, p)
		tc.mu.Unlock()
		if tc.hold != nil {
			select {
			case <-tc.hold:
			case <-ctx.Done():
				tc.ended <- "cancelled"
				return nil, ctx.Err()
			}
		}
		return map[string]any{"content": []any{map[string]any{"type": "text", "text": "opened " + string(p.Arguments)}}}, nil
	}
	return nil, acp.Errorf(acp.CodeMethodNotFound, "%s", method)
}

// mcpClient is an agent's MCP client talking to `quired tools-mcp`, run in-process on pipes.
type mcpClient struct {
	rpc *acp.Conn
}

func startToolsMCP(t *testing.T, socket string) *mcpClient {
	t.Helper()
	sr, cw := io.Pipe()
	cr, sw := io.Pipe()
	done := make(chan struct{})
	go func() { _ = ServeToolsMCP(sr, sw, socket, "test"); sw.Close(); close(done) }()
	c := &mcpClient{rpc: acp.NewConn(cr, cw, acp.Handlers{}, nil)}
	t.Cleanup(func() { cw.Close(); <-done })
	return c
}

func (m *mcpClient) call(ctx context.Context, method string, params any) (map[string]any, error) {
	var res map[string]any
	err := m.rpc.Call(ctx, method, params, &res)
	return res, err
}

func toolsSession(t *testing.T, fx *fixture, tc *toolsClient, skill string) (harness.Agent, string, map[string]quireMeta, acp.McpServer) {
	t.Helper()
	ctx := ctxT(t)
	fx.rm.Tools = tc.handle
	a, err := fx.rm.Agent(ctx, "fake", &person{answer: allow})
	if err != nil {
		t.Fatal(err)
	}
	sid, meta, err := NewQuireSession(ctx, a, true, skill)
	if err != nil {
		t.Fatal(err)
	}
	var m map[string]quireMeta
	if err := json.Unmarshal(meta, &m); err != nil {
		t.Fatal(err)
	}
	f := fx.fake("fake")
	f.mu.Lock()
	var mcp []acp.McpServer
	for asid := range f.mcps {
		mcp = f.mcps[asid]
	}
	f.mu.Unlock()
	if len(mcp) != 1 {
		t.Fatalf("the agent got %d MCP servers, want Quire's tools only: %+v", len(mcp), mcp)
	}
	return a, sid, m, mcp[0]
}

func TestServeSkillFiles(t *testing.T) {
	fx := newFixture(t, false)
	_, _, m, _ := toolsSession(t, fx, &toolsClient{}, testSkill)
	q := m[MetaKey]
	if !q.Tools || strings.Join(q.Files, ",") != "AGENTS.md,CLAUDE.md,GEMINI.md" {
		t.Fatalf("reply: %+v", q)
	}
	for _, f := range SkillFiles {
		b, err := os.ReadFile(filepath.Join(q.Cwd, f))
		if err != nil || string(b) != testSkill {
			t.Fatalf("%s: %q %v", f, b, err)
		}
	}
	// A folder the client names may be the person's own: nothing is written there.
	ctx := ctxT(t)
	own := filepath.Join(fx.root, "own")
	if err := os.Mkdir(own, 0o755); err != nil {
		t.Fatal(err)
	}
	var res newSessionResult
	if err := fx.rm.rpc.Call(ctx, acp.MethodSessionNew, acp.NewSessionRequest{Cwd: own, McpServers: []acp.McpServer{},
		Meta: withMeta(quireMeta{Agent: "fake", Skill: testSkill})}, &res); err != nil {
		t.Fatal(err)
	}
	if entries, _ := os.ReadDir(own); len(entries) != 0 || len(readMeta(res.Meta).Files) != 0 {
		t.Fatalf("wrote into the client's folder: %v %s", entries, res.Meta)
	}
	// A skill too long for a folder is refused before anything is made.
	err := fx.rm.rpc.Call(ctx, acp.MethodSessionNew, acp.NewSessionRequest{McpServers: []acp.McpServer{},
		Meta: withMeta(quireMeta{Agent: "fake", Skill: strings.Repeat("x", maxSkill+1)})}, &res)
	if err == nil {
		t.Fatal("an oversized skill was accepted")
	}
}

func TestServeToolsRelayOnlyDuringATurn(t *testing.T) {
	fx := newFixture(t, false)
	tc := &toolsClient{}
	a, sid, _, server := toolsSession(t, fx, tc, "")
	if server.Name != harness.ToolServer || len(server.Args) != 3 || server.Args[0] != "tools-mcp" || server.Args[1] != "--socket" {
		t.Fatalf("MCP server: %+v", server)
	}
	if fi, err := os.Stat(server.Args[2]); err != nil || fi.Mode().Perm()&0o077 != 0 {
		t.Fatalf("the tools socket is not private: %v %v", fi.Mode(), err)
	}
	if fi, err := os.Stat(filepath.Dir(server.Args[2])); err != nil || fi.Mode().Perm() != 0o700 {
		t.Fatalf("the tools socket's folder is not private: %v %v", fi.Mode(), err)
	}
	ctx := ctxT(t)
	m := startToolsMCP(t, server.Args[2])
	init, err := m.call(ctx, "initialize", map[string]any{"protocolVersion": "2025-06-18"})
	if err != nil || init["instructions"] != "Use these to act on the laptop." || init["protocolVersion"] != "2025-06-18" {
		t.Fatalf("initialize: %v %v", init, err)
	}
	list, err := m.call(ctx, "tools/list", map[string]any{})
	if err != nil || len(list["tools"].([]any)) != 1 {
		t.Fatalf("tools/list: %v %v", list, err)
	}
	// Outside a turn a call is refused, and Quire core never hears of it.
	res, err := m.call(ctx, "tools/call", map[string]any{"name": "open_url", "arguments": map[string]any{"url": "https://example.org"}})
	if err != nil || res["isError"] != true || !strings.Contains(res["content"].([]any)[0].(map[string]any)["text"].(string), "only while") {
		t.Fatalf("call outside a turn: %v %v", res, err)
	}
	tc.mu.Lock()
	if len(tc.calls) != 0 {
		t.Fatalf("Quire core was asked outside a turn: %+v", tc.calls)
	}
	tc.mu.Unlock()

	// During a turn it is relayed with quired's session id.
	turn, cancel := context.WithCancel(ctx)
	defer cancel()
	stopped := make(chan string, 1)
	go func() { stop, _ := a.Prompt(turn, sid, []acp.ContentBlock{acp.TextBlock("wait")}); stopped <- stop }()
	waitTurn(t, fx, sid)
	res, err = m.call(ctx, "tools/call", map[string]any{"name": "open_url", "arguments": map[string]any{"url": "https://example.org"}})
	if err != nil || res["isError"] == true || !strings.Contains(res["content"].([]any)[0].(map[string]any)["text"].(string), "example.org") {
		t.Fatalf("call in a turn: %v %v", res, err)
	}
	tc.mu.Lock()
	if len(tc.calls) != 1 || tc.calls[0].SessionID != sid || tc.calls[0].Name != "open_url" {
		t.Fatalf("relayed: %+v", tc.calls)
	}
	tc.mu.Unlock()

	// A call still open when the turn is cancelled ends at once for the agent, as an error. (Quire
	// core sent the cancel itself, so it drops its side of the call; ACP has no request cancel.)
	tc.hold, tc.ended = make(chan struct{}), make(chan string, 1)
	defer close(tc.hold)
	got := make(chan map[string]any, 1)
	go func() {
		r, _ := m.call(ctx, "tools/call", map[string]any{"name": "open_url", "arguments": map[string]any{}})
		got <- r
	}()
	for {
		tc.mu.Lock()
		n := len(tc.calls)
		tc.mu.Unlock()
		if n == 2 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	cancel()
	select {
	case r := <-got:
		if r["isError"] != true || !strings.Contains(r["content"].([]any)[0].(map[string]any)["text"].(string), "request ended") {
			t.Fatalf("a call cancelled with its turn must come back as an error: %v", r)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("the held call was not ended with the turn")
	}
	if stop := <-stopped; stop != acp.StopCancelled {
		t.Fatalf("turn: %s", stop)
	}
}

func TestServeToolsBridgeClosesWithTheConnection(t *testing.T) {
	fx := newFixture(t, false)
	_, _, _, server := toolsSession(t, fx, &toolsClient{}, testSkill)
	fx.closeC()
	<-fx.done
	fx.done <- nil // for the fixture's cleanup
	if _, err := os.Stat(filepath.Dir(server.Args[2])); !os.IsNotExist(err) {
		t.Fatalf("the tools socket outlived the connection: %v", err)
	}
}

// waitTurn waits until quired is prompting the fake agent in a "wait" turn.
func waitTurn(t *testing.T, fx *fixture, _ string) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		f := fx.fake("fake")
		f.mu.Lock()
		n := f.waiting
		f.mu.Unlock()
		if n > 0 {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("no turn started")
}
