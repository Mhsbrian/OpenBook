package serve

import (
	"context"
	"encoding/json"
	"io"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/harness"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/setup"
)

// The setup methods are quired serve's, on the same connection, and a stored key reaches only
// the agent it belongs to.
func TestServeRoutesSetupAndPassesKeysOnlyToTheirAgent(t *testing.T) {
	home := t.TempDir()
	specs := []agents.Spec{
		{ID: "fake", Name: "Fake", Protocol: agents.ACP, Args: []string{"acp"}, Setup: &agents.Setup{Keys: []agents.Key{{Name: "FAKE_API_KEY", Label: "k"}}}},
		{ID: "other", Name: "Other", Protocol: agents.ACP, Args: []string{"acp"}, Setup: &agents.Setup{}},
	}
	discover := func(context.Context) []agents.Found {
		return []agents.Found{{Spec: specs[0], Path: "/bin/true", Supported: true}, {Spec: specs[1], Path: "/bin/true", Supported: true}}
	}
	var mu sync.Mutex
	envs := map[string][]string{}
	srv := &Server{Version: "test", Root: t.TempDir(), Discover: discover,
		Setup: &setup.Service{Home: home, Version: "test", Catalog: specs, Discover: discover},
		Start: func(_ context.Context, spec agents.Spec, c harness.Client, o harness.Options) (harness.Agent, error) {
			mu.Lock()
			envs[spec.ID] = o.Env
			mu.Unlock()
			return &fakeAgent{client: c, cwds: map[string]string{}}, nil
		}}
	sr, cw := io.Pipe()
	cr, sw := io.Pipe()
	done := make(chan struct{})
	go func() { _ = srv.Serve(context.Background(), "test", sr, sw); sw.Close(); close(done) }()
	defer func() { cw.Close(); <-done }()
	c := acp.NewConn(cr, cw, acp.Handlers{}, nil)
	ctx := ctxT(t)
	var info acp.InitializeResponse
	if err := c.Call(ctx, acp.MethodInitialize, acp.InitializeRequest{ProtocolVersion: 1}, &info); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(info.AgentCapabilities.Meta), setup.MethodInstall) {
		t.Errorf("initialize doesn't name the setup methods: %s", info.AgentCapabilities.Meta)
	}
	var cat json.RawMessage
	if err := c.Call(ctx, setup.MethodCatalog, struct{}{}, &cat); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(cat), `"id":"fake"`) || !strings.Contains(string(cat), `"installed":true`) {
		t.Fatalf("catalog = %s", cat)
	}
	if err := c.Call(ctx, setup.MethodKey, map[string]string{"agent": "fake", "name": "FAKE_API_KEY", "value": "k-1"}, nil); err != nil {
		t.Fatal(err)
	}
	for _, id := range []string{"fake", "other"} {
		if err := c.Call(ctx, MethodDescribe, agentParam{Agent: id}, nil); err != nil {
			t.Fatal(err)
		}
	}
	mu.Lock()
	defer mu.Unlock()
	if strings.Join(envs["fake"], " ") != "FAKE_API_KEY=k-1" || len(envs["other"]) != 0 {
		t.Fatalf("envs = %v", envs)
	}
}

// credFixture is a quired serve with a setup service, one agent "fake" that takes FAKE_API_KEY,
// and a record of every process start: the environment it got, and the agent it was.
type credFixture struct {
	t    *testing.T
	srv  *Server
	mu   sync.Mutex
	runs []credRun
}

type credRun struct {
	env  []string
	fake *fakeAgent
}

func newCredFixture(t *testing.T) *credFixture {
	fx := &credFixture{t: t}
	home := t.TempDir()
	spec := agents.Spec{ID: "fake", Name: "Fake", Protocol: agents.ACP, Args: []string{"acp"},
		Setup: &agents.Setup{SignIn: []agents.SignIn{{ID: "key", Kind: agents.KindKey, Label: "k"}}, Keys: []agents.Key{{Name: "FAKE_API_KEY", Label: "k"}}}}
	discover := func(context.Context) []agents.Found {
		return []agents.Found{{Spec: spec, Path: "/bin/true", Supported: true}}
	}
	fx.srv = &Server{Version: "test", Root: t.TempDir(), Discover: discover,
		Setup: &setup.Service{Home: home, Version: "test", Catalog: []agents.Spec{spec}, Discover: discover},
		Start: func(_ context.Context, _ agents.Spec, c harness.Client, o harness.Options) (harness.Agent, error) {
			f := &fakeAgent{client: c, cwds: map[string]string{}}
			fx.mu.Lock()
			fx.runs = append(fx.runs, credRun{env: append([]string{}, o.Env...), fake: f})
			fx.mu.Unlock()
			return f, nil
		}}
	return fx
}

func (fx *credFixture) run(i int) credRun {
	fx.mu.Lock()
	defer fx.mu.Unlock()
	if i >= len(fx.runs) {
		fx.t.Fatalf("only %d agent starts, want #%d", len(fx.runs), i+1)
	}
	return fx.runs[i]
}

// client connects one client and records the agents quired says it stopped.
type credClient struct {
	c       *acp.Conn
	mu      sync.Mutex
	stopped []json.RawMessage
}

func (fx *credFixture) connect() *credClient {
	sr, cw := io.Pipe()
	cr, sw := io.Pipe()
	done := make(chan struct{})
	go func() { _ = fx.srv.Serve(context.Background(), "test", sr, sw); sw.Close(); close(done) }()
	fx.t.Cleanup(func() { cw.Close(); <-done })
	cl := &credClient{}
	cl.c = acp.NewConn(cr, cw, acp.Handlers{Notification: func(m string, p json.RawMessage) {
		if m == NotifyAgentStopped {
			cl.mu.Lock()
			cl.stopped = append(cl.stopped, append(json.RawMessage{}, p...))
			cl.mu.Unlock()
		}
	}}, nil)
	if err := cl.c.Call(ctxT(fx.t), acp.MethodInitialize, acp.InitializeRequest{ProtocolVersion: 1}, nil); err != nil {
		fx.t.Fatal(err)
	}
	return cl
}

func (cl *credClient) session(t *testing.T) string {
	t.Helper()
	var res newSessionResult
	if err := cl.c.Call(ctxT(t), acp.MethodSessionNew, acp.NewSessionRequest{McpServers: []acp.McpServer{}, Meta: withMeta(quireMeta{Agent: "fake"})}, &res); err != nil {
		t.Fatal(err)
	}
	return res.SessionID
}

func (cl *credClient) stops() []json.RawMessage {
	cl.mu.Lock()
	defer cl.mu.Unlock()
	return append([]json.RawMessage{}, cl.stopped...)
}

func waitFor(t *testing.T, what string, ok func() bool) {
	t.Helper()
	for range 300 {
		if ok() {
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for %s", what)
}

// The Checker's first case: a running agent missed a key saved after it started.
func TestANewKeyReachesTheNextSession(t *testing.T) {
	fx := newCredFixture(t)
	a := fx.connect()
	s1 := a.session(t)
	if first := fx.run(0); len(first.env) != 0 {
		t.Fatalf("first start's env = %v", first.env)
	}
	if err := a.c.Call(ctxT(t), setup.MethodKey, map[string]string{"agent": "fake", "name": "FAKE_API_KEY", "value": "k-new"}, nil); err != nil {
		t.Fatal(err)
	}
	// The agent that started without the key is gone, with its session, and the client heard so.
	if !fx.run(0).fake.closed.Load() {
		t.Fatal("the agent that started before the key is still running")
	}
	waitFor(t, "_quire/agent/stopped", func() bool { return len(a.stops()) == 1 })
	if got := string(a.stops()[0]); !strings.Contains(got, `"agent":"fake"`) || !strings.Contains(got, `"sessions":["`+s1+`"]`) {
		t.Errorf("stopped = %s", got)
	}
	err := a.c.Call(ctxT(t), acp.MethodPrompt, acp.PromptRequest{SessionID: s1, Prompt: []acp.ContentBlock{acp.TextBlock("hello")}}, nil)
	if err == nil {
		t.Error("the ended session still takes prompts")
	}
	// The next session is a new process with the key.
	a.session(t)
	if env := fx.run(1).env; strings.Join(env, " ") != "FAKE_API_KEY=k-new" {
		t.Fatalf("second start's env = %v", env)
	}
}

// The Checker's second case: after sign-out deleted the key file, an agent on another connection
// kept running with the key. Now every connection's agent stops, a running turn ends cancelled,
// and the next start has no key.
func TestSignoutStopsTheAgentOnEveryConnection(t *testing.T) {
	fx := newCredFixture(t)
	a, b := fx.connect(), fx.connect()
	if err := a.c.Call(ctxT(t), setup.MethodKey, map[string]string{"agent": "fake", "name": "FAKE_API_KEY", "value": "k-old"}, nil); err != nil {
		t.Fatal(err)
	}
	a.session(t)
	sb := b.session(t)
	for i := range 2 {
		if env := fx.run(i).env; strings.Join(env, " ") != "FAKE_API_KEY=k-old" {
			t.Fatalf("start %d env = %v", i+1, env)
		}
	}
	turn := make(chan acp.PromptResponse, 1)
	go func() {
		var res acp.PromptResponse
		_ = b.c.Call(context.Background(), acp.MethodPrompt, acp.PromptRequest{SessionID: sb, Prompt: []acp.ContentBlock{acp.TextBlock("wait")}}, &res)
		turn <- res
	}()
	waitFor(t, "b's turn to start", func() bool {
		f := fx.run(1).fake
		f.mu.Lock()
		defer f.mu.Unlock()
		return f.waiting == 1
	})
	var out json.RawMessage
	if err := a.c.Call(ctxT(t), setup.MethodSignout, map[string]string{"agent": "fake"}, &out); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(out), `"accountSignedOut":true`) {
		t.Errorf("signout = %s", out)
	}
	for i := range 2 {
		if !fx.run(i).fake.closed.Load() {
			t.Fatalf("agent %d still runs with the old key after sign-out", i+1)
		}
	}
	select {
	case res := <-turn:
		if res.StopReason != acp.StopCancelled {
			t.Errorf("b's turn ended %q", res.StopReason)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("b's turn didn't end")
	}
	waitFor(t, "both clients told", func() bool { return len(a.stops()) == 1 && len(b.stops()) == 1 })
	b.session(t)
	if env := fx.run(2).env; len(env) != 0 {
		t.Fatalf("after sign-out the agent started with %v", env)
	}
}
