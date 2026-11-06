package agents

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"regexp"
	"strings"
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
		{"antigravity", "/opt/bin/antigravity", true},
		{"kimi", "/opt/bin/kimi", true},
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

func TestSetupRecipesAreComplete(t *testing.T) {
	kinds := map[string]bool{KindDevice: true, KindPaste: true, KindLink: true, KindKey: true, KindACP: true, KindNone: true}
	env := regexp.MustCompile(`^[A-Z][A-Z0-9_]*$`)
	for _, s := range Catalog {
		st := s.Setup
		if st == nil {
			if s.Protocol.Supported() {
				t.Errorf("%s: quired runs it, but it has no setup recipe", s.ID)
			}
			continue
		}
		if s.Maker == "" || s.Needs == "" || !strings.HasPrefix(st.Source, "https://") {
			t.Errorf("%s: maker, needs and source are what the wizard shows", s.ID)
		}
		if len(st.Install) == 0 || len(st.Update) == 0 || len(st.SignIn) == 0 {
			t.Errorf("%s: install, update and sign-in are required", s.ID)
		}
		for _, step := range append(append([]Step{}, st.Install...), st.Update...) {
			if step.Title == "" || (step.Run.Shell == "") == (len(step.Run.Argv) == 0) {
				t.Errorf("%s: step %+v needs a title and exactly one of Shell or Argv", s.ID, step)
			}
			if sh := step.Run.Shell; sh != "" && !strings.Contains(sh, "https://") {
				t.Errorf("%s: a shell step fetches the maker's script over HTTPS: %s", s.ID, sh)
			}
			if strings.Contains(step.Run.Shell, "sudo") || (len(step.Run.Argv) > 0 && step.Run.Argv[0] == "sudo") {
				t.Errorf("%s: no recipe uses sudo (Debian packages come from the admin worker)", s.ID)
			}
		}
		for _, step := range st.Install {
			if !strings.HasPrefix(step.Source, "https://") {
				t.Errorf("%s: install step %q has no source", s.ID, step.Title)
			}
		}
		for _, m := range st.SignIn {
			if !kinds[m.Kind] || m.ID == "" || m.Label == "" && m.Kind != KindNone {
				t.Errorf("%s: sign-in %+v", s.ID, m)
			}
			runs := m.Kind == KindDevice || m.Kind == KindPaste || m.Kind == KindLink
			if runs != (len(m.Run.Argv) > 0) {
				t.Errorf("%s: sign-in %s: login kinds run a command, the others don't", s.ID, m.ID)
			}
			if m.Kind == KindKey && len(st.Keys) == 0 {
				t.Errorf("%s: a key sign-in needs key variables", s.ID)
			}
		}
		for _, k := range st.Keys {
			if !env.MatchString(k.Name) || k.Label == "" {
				t.Errorf("%s: key %+v", s.ID, k)
			}
		}
		for _, p := range append(append([]string{}, st.Remove.Paths...), st.Remove.Settings...) {
			if filepath.IsAbs(p) || strings.HasPrefix(filepath.Clean(p), "..") || p == "" {
				t.Errorf("%s: removal path %q must be inside $HOME", s.ID, p)
			}
		}
	}
}

func TestShownIsWhatRuns(t *testing.T) {
	c := Command{Shell: "curl -fsSL https://claude.ai/install.sh | bash"}
	if c.Shown("", "/home/droid") != "curl -fsSL https://claude.ai/install.sh | bash" {
		t.Errorf("shell shown = %q", c.Shown("", "/home/droid"))
	}
	c = Command{Argv: []string{BinToken, "login", "--device-code"}, Env: []string{"NO_OPEN_BROWSER=1"}}
	if got := c.Shown("/home/droid/.local/bin/copilot", "/home/droid"); got != "NO_OPEN_BROWSER=1 ~/.local/bin/copilot login --device-code" {
		t.Errorf("argv shown = %q", got)
	}
	c = Command{Argv: []string{"npm", "install", "-g", "--prefix", HomeToken + "/.local", "x"}}
	if got := c.Resolve("", "/home/droid"); strings.Join(got, " ") != "npm install -g --prefix /home/droid/.local x" {
		t.Errorf("resolve = %q", got)
	}
}

func TestLookPathFindsTheMakersFolders(t *testing.T) {
	home := t.TempDir()
	t.Setenv("HOME", home)
	t.Setenv("PATH", "/nonexistent")
	dir := filepath.Join(home, ".grok", "bin")
	_ = os.MkdirAll(dir, 0o755)
	_ = os.WriteFile(filepath.Join(dir, "grok"), []byte("#!/bin/sh\n"), 0o755)
	if p, err := LookPath("grok"); err != nil || p != filepath.Join(dir, "grok") {
		t.Errorf("LookPath = %q, %v", p, err)
	}
	if _, err := LookPath("kimi"); err == nil {
		t.Error("found an agent that isn't there")
	}
	got := PathWithMakerDirs("/usr/bin", home)
	for _, d := range MakerDirs {
		if !strings.Contains(got, filepath.Join(home, d)) {
			t.Errorf("PATH %q lacks %s", got, d)
		}
	}
}
