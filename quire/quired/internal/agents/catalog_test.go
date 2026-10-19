package agents

import (
	"context"
	"errors"
	"testing"
)

func TestDiscoverKeepsCatalogOrderAndFirstBinary(t *testing.T) {
	installed := map[string]string{
		"kimi":        "/opt/bin/kimi",
		"claude":      "/opt/bin/claude",
		"antigravity": "/opt/bin/antigravity", // agy missing: the second name is used
		"pi":          "/opt/bin/pi",
	}
	env := Env{
		LookPath: func(f string) (string, error) {
			if p, ok := installed[f]; ok {
				return p, nil
			}
			return "", errors.New("not found")
		},
		Version: func(_ context.Context, path string) (string, error) { return "v-" + path, nil },
	}
	got := Discover(context.Background(), env)
	want := []struct {
		id, path  string
		supported bool
	}{
		{"claude", "/opt/bin/claude", true},
		{"kimi", "/opt/bin/kimi", true},
		{"antigravity", "/opt/bin/antigravity", false},
		{"pi", "/opt/bin/pi", false},
	}
	if len(got) != len(want) {
		t.Fatalf("got %d agents, want %d: %+v", len(got), len(want), got)
	}
	for i, w := range want {
		if got[i].ID != w.id || got[i].Path != w.path || got[i].Supported != w.supported || got[i].Version != "v-"+w.path {
			t.Errorf("agent %d = %+v, want %+v", i, got[i], w)
		}
	}
}

func TestCatalogIsConsistent(t *testing.T) {
	seen := map[string]bool{}
	for _, s := range Catalog {
		if s.ID == "" || s.Name == "" || len(s.Binaries) == 0 {
			t.Errorf("incomplete entry %+v", s)
		}
		if seen[s.ID] {
			t.Errorf("duplicate id %q", s.ID)
		}
		seen[s.ID] = true
		if s.Protocol == ACP && len(s.Args) == 0 {
			t.Errorf("%s: an ACP agent needs the arguments that start its server", s.ID)
		}
		if !s.Protocol.Supported() && s.Note == "" {
			t.Errorf("%s: unsupported agents must say why", s.ID)
		}
	}
	if _, ok := Lookup("claude"); !ok {
		t.Error("Lookup(claude) failed")
	}
	if _, ok := Lookup("nope"); ok {
		t.Error("Lookup(nope) succeeded")
	}
}
