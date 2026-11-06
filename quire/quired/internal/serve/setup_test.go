package serve

import (
	"context"
	"encoding/json"
	"io"
	"strings"
	"sync"
	"testing"

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
