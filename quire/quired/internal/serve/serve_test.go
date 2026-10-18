package serve

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/harness"
)

// The test binary doubles as a real ACP agent process for the end-to-end test.
func TestMain(m *testing.M) {
	if os.Getenv("QUIRED_FAKE") == "acp-auth" {
		fakeAuthAgent()
		os.Exit(0)
	}
	os.Exit(m.Run())
}

// fakeAgent is an in-process harness.Agent.
type fakeAgent struct {
	client   harness.Client
	needAuth bool
	authed   atomic.Bool
	closed   atomic.Bool

	mu   sync.Mutex
	n    int
	cwds map[string]string
}

func (f *fakeAgent) Info() acp.InitializeResponse {
	return acp.InitializeResponse{ProtocolVersion: 1, AuthMethods: []acp.AuthMethod{{ID: "token", Name: "Token"}, {ID: "login", Name: "Log in", Type: acp.AuthTerminal, Args: []string{"--login"}}},
		AgentInfo: &acp.Implementation{Name: "fake"}}
}
func (f *fakeAgent) Diagnostics() string { return "" }
func (f *fakeAgent) Close() error        { f.closed.Store(true); return nil }
func (f *fakeAgent) Authenticate(_ context.Context, id string) error {
	if id != "token" {
		return acp.Errorf(acp.CodeInvalidParams, "no method %s", id)
	}
	f.authed.Store(true)
	return nil
}

func (f *fakeAgent) NewSession(_ context.Context, cwd string, _ []acp.McpServer) (string, error) {
	if f.needAuth && !f.authed.Load() {
		return "", acp.Errorf(acp.CodeAuthRequired, "Authentication required")
	}
	f.mu.Lock()
	f.n++
	sid := fmt.Sprintf("a%d", f.n)
	f.cwds[sid] = cwd
	f.mu.Unlock()
	// Real agents announce things about a session before session/new's reply is handled.
	f.client.Update(sid, acp.ChunkUpdate(acp.UpdateAgentThoughtChunk, "early").Marshal())
	return sid, nil
}

func (f *fakeAgent) Prompt(ctx context.Context, sid string, prompt []acp.ContentBlock) (string, error) {
	say := func(s string) { f.client.Update(sid, acp.ChunkUpdate(acp.UpdateAgentMessageChunk, s).Marshal()) }
	switch prompt[0].Text {
	case "hello":
		f.mu.Lock()
		cwd := f.cwds[sid]
		f.mu.Unlock()
		say("Hi ")
		say("from " + filepath.Base(filepath.Dir(cwd)))
		return acp.StopEndTurn, nil
	case "write":
		res, err := f.client.RequestPermission(ctx, acp.RequestPermissionRequest{SessionID: sid,
			ToolCall: acp.ToolCallRef{ToolCallID: "t1", Title: "Write a.txt", Kind: acp.KindEdit},
			Options:  []acp.PermissionOption{{OptionID: "y", Name: "Allow", Kind: acp.AllowOnce}, {OptionID: "n", Name: "Don't allow", Kind: acp.RejectOnce}}})
		if err != nil {
			say("error")
		} else if res.Outcome.Outcome == acp.OutcomeSelected {
			say("outcome=" + res.Outcome.OptionID)
		} else {
			say("outcome=cancelled")
		}
		return acp.StopEndTurn, nil
	case "wait":
		<-ctx.Done()
		return acp.StopCancelled, nil
	}
	return acp.StopRefusal, nil
}

// person is the client's side: it records text and answers permissions with answer.
type person struct {
	mu     sync.Mutex
	text   strings.Builder
	kinds  []string
	asked  int
	answer func(acp.RequestPermissionRequest) acp.RequestPermissionResponse
	block  chan struct{} // if set, RequestPermission waits on it (or ctx)
}

func (p *person) Update(_ string, raw json.RawMessage) {
	var u acp.SessionUpdate
	_ = json.Unmarshal(raw, &u)
	p.mu.Lock()
	defer p.mu.Unlock()
	p.kinds = append(p.kinds, u.Kind)
	if u.Kind == acp.UpdateAgentMessageChunk {
		p.text.WriteString(u.ChunkText())
	}
}

func (p *person) RequestPermission(ctx context.Context, req acp.RequestPermissionRequest) (acp.RequestPermissionResponse, error) {
	p.mu.Lock()
	p.asked++
	p.mu.Unlock()
	if p.block != nil {
		select {
		case <-p.block:
		case <-ctx.Done():
		}
		return acp.Cancelled(), nil
	}
	return p.answer(req), nil
}

func (p *person) String() string { p.mu.Lock(); defer p.mu.Unlock(); return p.text.String() }

type fixture struct {
	t      *testing.T
	root   string
	srv    *Server
	rm     *Remote
	closeC func()
	done   chan error
	mu     sync.Mutex
	fakes  map[string]*fakeAgent
	starts atomic.Int32
}

func newFixture(t *testing.T, needAuth bool) *fixture {
	t.Helper()
	fx := &fixture{t: t, root: t.TempDir(), fakes: map[string]*fakeAgent{}, done: make(chan error, 1)}
	fx.srv = &Server{
		Version: "test", Root: fx.root,
		Discover: func(context.Context) []agents.Found {
			return []agents.Found{
				{Spec: agents.Spec{ID: "fake", Name: "Fake", Protocol: agents.ACP}, Path: "/bin/true", Version: "1", Supported: true},
				{Spec: agents.Spec{ID: "grok", Name: "Grok CLI", Protocol: agents.GrokHeadless, Note: "no adapter"}, Path: "/bin/true", Supported: false},
			}
		},
		Start: func(_ context.Context, spec agents.Spec, c harness.Client, _ harness.Options) (harness.Agent, error) {
			fx.starts.Add(1)
			f := &fakeAgent{client: c, needAuth: needAuth, cwds: map[string]string{}}
			fx.mu.Lock()
			fx.fakes[spec.ID] = f
			fx.mu.Unlock()
			return f, nil
		},
	}
	sr, cw := io.Pipe() // client → server
	cr, sw := io.Pipe() // server → client
	go func() { fx.done <- fx.srv.Serve(context.Background(), "test", sr, sw); sw.Close() }()
	fx.closeC = func() { cw.Close() }
	rm, err := Connect(context.Background(), cr, cw, nil, acp.Implementation{Name: "test-client"})
	if err != nil {
		t.Fatal(err)
	}
	fx.rm = rm
	t.Cleanup(func() { fx.closeC(); <-fx.done })
	return fx
}

func (fx *fixture) fake(id string) *fakeAgent {
	fx.mu.Lock()
	defer fx.mu.Unlock()
	return fx.fakes[id]
}

func ctxT(t *testing.T) context.Context {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	t.Cleanup(cancel)
	return ctx
}

func allow(req acp.RequestPermissionRequest) acp.RequestPermissionResponse { return acp.Selected("y") }

func TestServeListsAgentsAndRunsATurn(t *testing.T) {
	fx := newFixture(t, false)
	ctx := ctxT(t)
	if !strings.Contains(string(fx.rm.Info().AgentCapabilities.Meta), MethodAgents) {
		t.Fatalf("initialize doesn't advertise %s: %s", MethodAgents, fx.rm.Info().AgentCapabilities.Meta)
	}
	list, err := fx.rm.Agents(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(list) != 2 || list[0].ID != "fake" || !list[0].Supported || list[1].Supported || list[1].Note == "" {
		t.Fatalf("agents: %+v", list)
	}
	p := &person{answer: allow}
	a, err := fx.rm.Agent(ctx, "fake", p)
	if err != nil {
		t.Fatal(err)
	}
	if len(a.Info().AuthMethods) != 2 || a.Info().AuthMethods[1].Type != acp.AuthTerminal {
		t.Fatalf("describe lost the auth methods: %+v", a.Info().AuthMethods)
	}
	sid, err := a.NewSession(ctx, "", nil)
	if err != nil {
		t.Fatal(err)
	}
	stop, err := a.Prompt(ctx, sid, []acp.ContentBlock{acp.TextBlock("hello")})
	if err != nil || stop != acp.StopEndTurn {
		t.Fatalf("prompt: %q %v", stop, err)
	}
	if got := p.String(); got != "Hi from Quire" {
		t.Fatalf("text = %q", got)
	}
	p.mu.Lock()
	kinds := strings.Join(p.kinds, ",")
	p.mu.Unlock()
	if !strings.HasPrefix(kinds, acp.UpdateAgentThoughtChunk+",") {
		t.Fatalf("the update sent before session/new's reply was lost or reordered: %s", kinds)
	}
	if fx.starts.Load() != 1 {
		t.Fatalf("agent started %d times", fx.starts.Load())
	}
	// A second session reuses the running agent.
	if _, err := a.NewSession(ctx, "", nil); err != nil || fx.starts.Load() != 1 {
		t.Fatalf("second session: %v, starts=%d", err, fx.starts.Load())
	}
}

func TestServePermissionRelayAndRefusals(t *testing.T) {
	fx := newFixture(t, false)
	ctx := ctxT(t)
	for _, tc := range []struct {
		name   string
		answer func(acp.RequestPermissionRequest) acp.RequestPermissionResponse
		want   string
	}{
		{"allowed", allow, "outcome=y"},
		{"denied", func(acp.RequestPermissionRequest) acp.RequestPermissionResponse { return acp.Selected("n") }, "outcome=n"},
		// An answer that isn't one of the agent's options is refused, not passed on.
		{"forged option", func(acp.RequestPermissionRequest) acp.RequestPermissionResponse {
			return acp.Selected("allow_everything")
		}, "outcome=n"},
		{"cancelled", func(acp.RequestPermissionRequest) acp.RequestPermissionResponse { return acp.Cancelled() }, "outcome=cancelled"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			p := &person{answer: tc.answer}
			a, err := fx.rm.Agent(ctx, "fake", p)
			if err != nil {
				t.Fatal(err)
			}
			sid, err := a.NewSession(ctx, "", nil)
			if err != nil {
				t.Fatal(err)
			}
			if _, err := a.Prompt(ctx, sid, []acp.ContentBlock{acp.TextBlock("write")}); err != nil {
				t.Fatal(err)
			}
			if got := p.String(); got != tc.want {
				t.Fatalf("got %q, want %q", got, tc.want)
			}
		})
	}
}

func TestServeCancel(t *testing.T) {
	fx := newFixture(t, false)
	ctx := ctxT(t)
	p := &person{answer: allow}
	a, _ := fx.rm.Agent(ctx, "fake", p)
	sid, err := a.NewSession(ctx, "", nil)
	if err != nil {
		t.Fatal(err)
	}
	tctx, cancel := context.WithTimeout(ctx, 200*time.Millisecond)
	defer cancel()
	stop, err := a.Prompt(tctx, sid, []acp.ContentBlock{acp.TextBlock("wait")})
	if err != nil || stop != acp.StopCancelled {
		t.Fatalf("cancel: %q %v", stop, err)
	}
	// The session is usable again.
	if stop, err := a.Prompt(ctx, sid, []acp.ContentBlock{acp.TextBlock("hello")}); err != nil || stop != acp.StopEndTurn {
		t.Fatalf("after cancel: %q %v", stop, err)
	}
}

func TestServeDisconnectStopsAgentsAndRefusesOpenQuestion(t *testing.T) {
	fx := newFixture(t, false)
	ctx := ctxT(t)
	p := &person{block: make(chan struct{})}
	a, _ := fx.rm.Agent(ctx, "fake", p)
	sid, err := a.NewSession(ctx, "", nil)
	if err != nil {
		t.Fatal(err)
	}
	go func() { _, _ = a.Prompt(context.Background(), sid, []acp.ContentBlock{acp.TextBlock("write")}) }()
	deadline := time.Now().Add(5 * time.Second)
	for {
		p.mu.Lock()
		n := p.asked
		p.mu.Unlock()
		if n > 0 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatal("the permission request never reached the client")
		}
		time.Sleep(10 * time.Millisecond)
	}
	fx.closeC() // Quire core goes away mid-question
	select {
	case <-fx.done:
		fx.done <- nil // for Cleanup
	case <-time.After(5 * time.Second):
		t.Fatal("Serve did not return after the client left")
	}
	if !fx.fake("fake").closed.Load() {
		t.Fatal("the agent was not stopped when its client left")
	}
}

func TestServeSessionFolderRules(t *testing.T) {
	fx := newFixture(t, false)
	ctx := ctxT(t)
	a, _ := fx.rm.Agent(ctx, "fake", &person{answer: allow})
	inside := filepath.Join(fx.root, "project")
	if err := os.Mkdir(inside, 0o755); err != nil {
		t.Fatal(err)
	}
	if _, err := a.NewSession(ctx, inside, nil); err != nil {
		t.Fatalf("a folder inside the root was refused: %v", err)
	}
	outside := t.TempDir()
	link := filepath.Join(fx.root, "escape")
	if err := os.Symlink(outside, link); err != nil {
		t.Fatal(err)
	}
	for _, cwd := range []string{outside, link, filepath.Join(fx.root, "..", filepath.Base(outside)), "relative", filepath.Join(fx.root, "missing")} {
		if _, err := a.NewSession(ctx, cwd, nil); err == nil {
			t.Errorf("cwd %s was accepted", cwd)
		}
	}
	_, err := a.NewSession(ctx, "", []acp.McpServer{{Name: "x", Command: "/bin/sh", Args: []string{"-c", "touch /tmp/pwned"}}})
	var re *acp.RPCError
	if !errors.As(err, &re) || re.Code != acp.CodeInvalidParams {
		t.Fatalf("a client-supplied MCP server was not refused: %v", err)
	}
}

func TestServeAuthRequiredThenAuthenticate(t *testing.T) {
	fx := newFixture(t, true)
	ctx := ctxT(t)
	a, err := fx.rm.Agent(ctx, "fake", &person{answer: allow})
	if err != nil {
		t.Fatal(err)
	}
	_, err = a.NewSession(ctx, "", nil)
	var re *acp.RPCError
	if !errors.As(err, &re) || re.Code != acp.CodeAuthRequired {
		t.Fatalf("want auth_required, got %v", err)
	}
	var data authRequired
	if json.Unmarshal(re.Data, &data) != nil || data.Agent != "fake" || len(data.AuthMethods) != 2 {
		t.Fatalf("auth_required data = %s", re.Data)
	}
	if left, _ := filepath.Glob(filepath.Join(fx.root, "Quire", "*")); len(left) != 0 {
		t.Fatalf("a failed session/new left its folder: %v", left)
	}
	if err := a.Authenticate(ctx, "nope"); err == nil {
		t.Fatal("an unknown method was accepted")
	}
	if err := a.Authenticate(ctx, "token"); err != nil {
		t.Fatal(err)
	}
	if _, err := a.NewSession(ctx, "", nil); err != nil {
		t.Fatalf("after authenticate: %v", err)
	}
}

func TestServeRefusesBeforeInitializeAndUnknownAgents(t *testing.T) {
	srv := &Server{Version: "test", Root: t.TempDir(), Discover: func(context.Context) []agents.Found {
		return []agents.Found{{Spec: agents.Spec{ID: "grok", Protocol: agents.GrokHeadless, Note: "no adapter"}, Supported: false}}
	}}
	sr, cw := io.Pipe()
	cr, sw := io.Pipe()
	done := make(chan struct{})
	go func() { _ = srv.Serve(context.Background(), "test", sr, sw); sw.Close(); close(done) }()
	defer func() { cw.Close(); <-done }()
	c := acp.NewConn(cr, cw, acp.Handlers{}, nil)
	ctx := ctxT(t)
	var re *acp.RPCError
	if err := c.Call(ctx, MethodAgents, struct{}{}, nil); !errors.As(err, &re) || re.Code != acp.CodeInvalidRequest {
		t.Fatalf("before initialize: %v", err)
	}
	if err := c.Call(ctx, acp.MethodInitialize, acp.InitializeRequest{ProtocolVersion: 1}, nil); err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{"", "missing", "grok"} {
		if err := c.Call(ctx, MethodDescribe, agentParam{Agent: id}, nil); err == nil {
			t.Errorf("describe %q succeeded", id)
		}
	}
	if err := c.Call(ctx, "session/load", struct{}{}, nil); !errors.As(err, &re) || re.Code != acp.CodeMethodNotFound {
		t.Fatalf("session/load: %v", err)
	}
}

// TestServeRealProcessAuthenticate runs a real ACP agent process through harness.Start, so the
// authenticate request and auth_required error cross both connections.
func TestServeRealProcessAuthenticate(t *testing.T) {
	self, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	root := t.TempDir()
	srv := &Server{Version: "test", Root: root, FS: true,
		Discover: func(context.Context) []agents.Found {
			return []agents.Found{{Spec: agents.Spec{ID: "authy", Name: "Authy", Protocol: agents.ACP}, Path: self, Supported: true}}
		},
		Start: func(ctx context.Context, spec agents.Spec, c harness.Client, o harness.Options) (harness.Agent, error) {
			o.Env = append(o.Env, "QUIRED_FAKE=acp-auth")
			return harness.Start(ctx, spec, c, o)
		},
	}
	sr, cw := io.Pipe()
	cr, sw := io.Pipe()
	done := make(chan struct{})
	go func() { _ = srv.Serve(context.Background(), "test", sr, sw); sw.Close(); close(done) }()
	defer func() { cw.Close(); <-done }()
	ctx := ctxT(t)
	rm, err := Connect(ctx, cr, cw, nil, acp.Implementation{Name: "test"})
	if err != nil {
		t.Fatal(err)
	}
	p := &person{answer: allow}
	a, err := rm.Agent(ctx, "authy", p)
	if err != nil {
		t.Fatal(err)
	}
	var re *acp.RPCError
	if _, err := a.NewSession(ctx, "", nil); !errors.As(err, &re) || re.Code != acp.CodeAuthRequired {
		t.Fatalf("want auth_required, got %v", err)
	}
	if err := a.Authenticate(ctx, "login"); err == nil {
		t.Fatal("a terminal method went through authenticate")
	}
	if err := a.Authenticate(ctx, "api-key"); err != nil {
		t.Fatal(err)
	}
	sid, err := a.NewSession(ctx, "", nil)
	if err != nil {
		t.Fatal(err)
	}
	if stop, err := a.Prompt(ctx, sid, []acp.ContentBlock{acp.TextBlock("hi")}); err != nil || stop != acp.StopEndTurn {
		t.Fatalf("prompt: %q %v", stop, err)
	}
	if got := p.String(); !strings.HasPrefix(got, "signed in; wrote ") {
		t.Fatalf("text = %q", got)
	}
	// The file the agent wrote through fs/write_text_file landed in the session's folder.
	matches, _ := filepath.Glob(filepath.Join(root, "Quire", "*", "note.txt"))
	if len(matches) != 1 {
		t.Fatalf("note.txt in the session folder: %v", matches)
	}
}

// fakeAuthAgent wants authenticate (method api-key) before session/new, then answers a prompt
// after writing note.txt through the client.
func fakeAuthAgent() {
	var conn *acp.Conn
	var authed atomic.Bool
	var cwd string
	h := acp.Handlers{Request: func(ctx context.Context, method string, params json.RawMessage) (any, error) {
		switch method {
		case acp.MethodInitialize:
			return acp.InitializeResponse{ProtocolVersion: 1, AuthMethods: []acp.AuthMethod{
				{ID: "api-key", Name: "API key"}, {ID: "login", Name: "Log in", Type: acp.AuthTerminal, Args: []string{"--login"}}},
				AgentInfo: &acp.Implementation{Name: "authy"}}, nil
		case acp.MethodAuthenticate:
			var req acp.AuthenticateRequest
			_ = json.Unmarshal(params, &req)
			if req.MethodID != "api-key" {
				return nil, acp.Errorf(acp.CodeInvalidParams, "no")
			}
			authed.Store(true)
			return struct{}{}, nil
		case acp.MethodSessionNew:
			if !authed.Load() {
				return nil, acp.Errorf(acp.CodeAuthRequired, "Authentication required")
			}
			var req acp.NewSessionRequest
			_ = json.Unmarshal(params, &req)
			cwd = req.Cwd
			return acp.NewSessionResponse{SessionID: "x"}, nil
		case acp.MethodPrompt:
			p := filepath.Join(cwd, "note.txt")
			err := conn.Call(ctx, acp.MethodWriteTextFile, acp.WriteTextFileRequest{SessionID: "x", Path: p, Content: "hi"}, nil)
			msg := "signed in; wrote " + filepath.Base(p)
			if err != nil {
				msg = "write failed: " + err.Error()
			}
			_ = conn.Notify(ctx, acp.MethodSessionUpdate, acp.SessionNotification{SessionID: "x", Update: acp.ChunkUpdate(acp.UpdateAgentMessageChunk, msg).Marshal()})
			return acp.PromptResponse{StopReason: acp.StopEndTurn}, nil
		}
		return nil, acp.Errorf(acp.CodeMethodNotFound, "%s", method)
	}}
	conn = acp.NewConn(os.Stdin, os.Stdout, h, nil)
	<-conn.Done()
}
