package setup

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"
	"unsafe"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
)

// The test binary stands in for the makers' installers and logins (QUIRED_FAKE).
func TestMain(m *testing.M) {
	switch os.Getenv("QUIRED_FAKE") {
	case "":
		os.Exit(m.Run())
	case "install":
		fmt.Println("Downloading fakeagent 1.2.3")
		fmt.Print("progress 10%\rprogress 50%\rprogress 100%\n")
		dir := filepath.Join(os.Getenv("HOME"), ".local", "bin")
		_ = os.MkdirAll(dir, 0o755)
		_ = os.WriteFile(filepath.Join(dir, os.Getenv("FAKE_BIN")), []byte("#!/bin/sh\necho fake 1.2.3\n"), 0o755)
		fmt.Println("Installed.")
	case "fail":
		fmt.Println("boom line 1")
		fmt.Fprintln(os.Stderr, "error: no network")
		os.Exit(3)
	case "sleep":
		time.Sleep(60 * time.Second)
	case "stubborn":
		signal.Ignore(syscall.SIGTERM)
		fmt.Println("ignoring SIGTERM")
		time.Sleep(60 * time.Second)
	case "env":
		fmt.Println("PATH=" + os.Getenv("PATH"))
		fmt.Println("HOME=" + os.Getenv("HOME"))
	case "device":
		fmt.Println("To sign in, open https://github.com/login/device")
		fmt.Println("and enter the code: ABCD-1234")
		time.Sleep(300 * time.Millisecond)
		fmt.Println("Signed in.")
	case "paste":
		fmt.Println("Browser didn't open? Use the url below to sign in (c to copy)")
		fmt.Println("https://claude.ai/oauth/authorize?code=true&client_id=x&state=abc")
		fmt.Print("Paste code here if prompted > ")
		// A terminal in canonical mode turns the \r quired writes into \n.
		in, _ := bufio.NewReader(os.Stdin).ReadString('\n')
		in = strings.TrimSpace(in)
		fmt.Printf("\nreceived %s\n", in) // a TUI that echoes what it read
		fmt.Println("ANTHROPIC_API_KEY=sk-ant-abcdefghijklmnopqrstuvwx")
		if in != "the-secret-code" {
			os.Exit(1)
		}
		fmt.Println("Login successful.")
	case "tty":
		var t syscall.Termios
		_, _, e := syscall.Syscall(syscall.SYS_IOCTL, 0, syscall.TCGETS, uintptr(unsafe.Pointer(&t)))
		fmt.Printf("tty=%v\n", e == 0)
	}
	os.Exit(0)
}

func fake(mode string, env ...string) agents.Command {
	return agents.Command{Argv: []string{os.Args[0]}, Env: append([]string{"QUIRED_FAKE=" + mode}, env...)}
}

// fixture is a Service over a temporary home with one fake agent.
type fixture struct {
	t    *testing.T
	home string
	s    *Service

	mu    sync.Mutex
	notes []note
}

type note struct {
	method string
	params json.RawMessage
}

func newFixture(t *testing.T, st agents.Setup) *fixture {
	t.Helper()
	fx := &fixture{t: t, home: t.TempDir()}
	spec := agents.Spec{ID: "fake", Name: "Fake Agent", Maker: "Test", Needs: "nothing", Binaries: []string{"fakeagent"},
		Protocol: agents.ACP, Args: []string{"acp"}, Setup: &st}
	other := agents.Spec{ID: "other", Name: "Other", Binaries: []string{"other"}, Protocol: agents.ACP, Args: []string{"acp"},
		Setup: &agents.Setup{Keys: []agents.Key{{Name: "OTHER_API_KEY"}}}}
	fx.s = &Service{Home: fx.home, Version: "test", Catalog: []agents.Spec{spec, other},
		Discover: func(context.Context) []agents.Found {
			p := filepath.Join(fx.home, ".local", "bin", "fakeagent")
			if _, err := os.Stat(p); err != nil {
				return nil
			}
			return []agents.Found{{Spec: spec, Path: p, Version: "fake 1.2.3", Supported: true}}
		},
		Missing:   func(context.Context, []string) []string { return nil },
		KillGrace: 500 * time.Millisecond,
	}
	return fx
}

func (fx *fixture) notify(m string, p any) {
	b, _ := json.Marshal(p)
	fx.mu.Lock()
	fx.notes = append(fx.notes, note{m, b})
	fx.mu.Unlock()
}

func (fx *fixture) call(ctx context.Context, method string, params any) (json.RawMessage, error) {
	b, _ := json.Marshal(params)
	res, err, ok := fx.s.Handle(ctx, method, b, fx.notify)
	if !ok {
		fx.t.Fatalf("%s not handled", method)
	}
	if err != nil {
		return nil, err
	}
	out, _ := json.Marshal(res)
	return out, nil
}

func (fx *fixture) lines(method string) []string {
	fx.mu.Lock()
	defer fx.mu.Unlock()
	var out []string
	for _, n := range fx.notes {
		if n.method != method {
			continue
		}
		var p struct {
			Line string `json:"line"`
		}
		_ = json.Unmarshal(n.params, &p)
		if p.Line != "" {
			out = append(out, p.Line)
		}
	}
	return out
}

func ctxT(t *testing.T) context.Context {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	t.Cleanup(cancel)
	return ctx
}

func rpcErr(t *testing.T, err error) *acp.RPCError {
	t.Helper()
	var re *acp.RPCError
	if !errors.As(err, &re) {
		t.Fatalf("want an RPC error, got %v", err)
	}
	return re
}

func TestCatalogShowsTheRecipeBeforeInstall(t *testing.T) {
	fx := newFixture(t, agents.Setup{Debian: []string{"curl"},
		Install: []agents.Step{{Title: "Install Fake", Run: agents.Command{Shell: "curl -fsSL https://example.invalid/install.sh | bash"}, Source: "https://example.invalid/docs"}},
		SignIn:  []agents.SignIn{{ID: "device", Kind: agents.KindDevice, Label: "Fake account", Run: fake("device")}},
		Keys:    []agents.Key{{Name: "FAKE_API_KEY", Label: "Fake key"}}})
	raw, err := fx.call(ctxT(t), MethodCatalog, struct{}{})
	if err != nil {
		t.Fatal(err)
	}
	var res catalogResult
	if err := json.Unmarshal(raw, &res); err != nil {
		t.Fatal(err)
	}
	if res.Quired != "test" || len(res.Agents) != 2 {
		t.Fatalf("catalog = %s", raw)
	}
	a := res.Agents[0]
	if a.ID != "fake" || a.Installed || !a.Supported || a.Maker != "Test" || a.Needs != "nothing" {
		t.Errorf("agent = %+v", a)
	}
	if len(a.Recipe.Steps) != 1 || a.Recipe.Steps[0].Command != "curl -fsSL https://example.invalid/install.sh | bash" ||
		a.Recipe.Steps[0].Source != "https://example.invalid/docs" || len(a.Recipe.Debian) != 1 {
		t.Errorf("recipe = %+v", a.Recipe)
	}
	if len(a.SignIn) != 1 || a.SignIn[0].Kind != "device" || len(a.Keys) != 1 || a.HasKey {
		t.Errorf("sign-in = %+v keys = %+v", a.SignIn, a.Keys)
	}
}

func TestInstallRunsTheRecipeAndFindsTheAgent(t *testing.T) {
	fx := newFixture(t, agents.Setup{Install: []agents.Step{
		{Title: "Install Fake", Run: fake("install", "FAKE_BIN=fakeagent")},
		{Title: "Check PATH", Run: fake("env")},
	}})
	raw, err := fx.call(ctxT(t), MethodInstall, map[string]string{"agent": "fake", "job": "j1"})
	if err != nil {
		t.Fatal(err)
	}
	var res installResult
	_ = json.Unmarshal(raw, &res)
	if res.Version != "fake 1.2.3" || !strings.HasSuffix(res.Path, "/.local/bin/fakeagent") {
		t.Fatalf("result = %s", raw)
	}
	var steps []progress
	fx.mu.Lock()
	for _, n := range fx.notes {
		var p progress
		_ = json.Unmarshal(n.params, &p)
		if n.method == NotifyProgress && p.Line == "" {
			steps = append(steps, p)
		}
	}
	fx.mu.Unlock()
	if len(steps) != 2 || steps[0].Step != 1 || steps[0].Steps != 2 || steps[1].Title != "Check PATH" || steps[0].Job != "j1" {
		t.Fatalf("steps = %+v", steps)
	}
	// The job's log has every line, in the guest's state folder; the PATH had the makers' folders.
	logs, _ := filepath.Glob(filepath.Join(fx.home, ".local/state/quire/jobs/fake-install-*.log"))
	if len(logs) != 1 {
		t.Fatalf("logs = %v", logs)
	}
	b, _ := os.ReadFile(logs[0])
	for _, want := range []string{"Downloading fakeagent", "progress 100%", "Installed.", fx.home + "/.grok/bin", fx.home + "/.kimi-code/bin", "HOME=" + fx.home} {
		if !strings.Contains(string(b), want) {
			t.Errorf("log lacks %q:\n%s", want, b)
		}
	}
	if fi, _ := os.Stat(logs[0]); fi.Mode().Perm() != 0o600 {
		t.Errorf("log mode %v", fi.Mode().Perm())
	}
}

func TestInstallFailureCarriesItsOutput(t *testing.T) {
	fx := newFixture(t, agents.Setup{Install: []agents.Step{{Title: "Install Fake", Run: fake("fail")}}})
	_, err := fx.call(ctxT(t), MethodInstall, map[string]string{"agent": "fake", "job": "j1"})
	re := rpcErr(t, err)
	var data struct {
		Step   int    `json:"step"`
		Output string `json:"output"`
	}
	_ = json.Unmarshal(re.Data, &data)
	if re.Code != acp.CodeInternalError || re.Message != "Install Fake: exit status 3" || data.Step != 1 || !strings.Contains(data.Output, "error: no network") {
		t.Fatalf("error = %+v data = %+v", re, data)
	}
}

func TestInstallNeedsItsDebianPackagesFirst(t *testing.T) {
	fx := newFixture(t, agents.Setup{Debian: []string{"nodejs", "npm"}, Install: []agents.Step{{Title: "x", Run: fake("install")}}})
	fx.s.Missing = func(_ context.Context, p []string) []string { return p[:1] }
	_, err := fx.call(ctxT(t), MethodInstall, map[string]string{"agent": "fake", "job": "j1"})
	re := rpcErr(t, err)
	if re.Code != acp.CodeInvalidRequest || !strings.Contains(string(re.Data), `"missing":["nodejs"]`) {
		t.Fatalf("error = %+v %s", re, re.Data)
	}
}

func TestCancelStopsAJobAndItsProcess(t *testing.T) {
	fx := newFixture(t, agents.Setup{Install: []agents.Step{{Title: "Wait", Run: fake("sleep")}}})
	done := make(chan error, 1)
	go func() {
		_, err := fx.call(ctxT(t), MethodInstall, map[string]string{"agent": "fake", "job": "j1"})
		done <- err
	}()
	waitJob(t, fx.s, "j1")
	// One job per agent at a time.
	_, err := fx.call(ctxT(t), MethodInstall, map[string]string{"agent": "fake", "job": "j2"})
	if re := rpcErr(t, err); re.Code != acp.CodeInvalidRequest {
		t.Errorf("a second job: %+v", re)
	}
	t0 := time.Now()
	if _, err := fx.call(ctxT(t), MethodCancel, map[string]string{"job": "j1"}); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-done:
		if re := rpcErr(t, err); re.Code != CodeCancelled {
			t.Fatalf("cancelled job: %+v", re)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("the job didn't stop")
	}
	if d := time.Since(t0); d > 2*time.Second {
		t.Errorf("SIGTERM took %v", d)
	}
	if _, err := fx.call(ctxT(t), MethodCancel, map[string]string{"job": "j1"}); err == nil {
		t.Error("cancelling a finished job succeeded")
	}
}

func TestCancelKillsAStubbornProcessAfterTheGrace(t *testing.T) {
	fx := newFixture(t, agents.Setup{Install: []agents.Step{{Title: "Wait", Run: fake("stubborn")}}})
	done := make(chan error, 1)
	go func() {
		_, err := fx.call(ctxT(t), MethodInstall, map[string]string{"agent": "fake", "job": "j1"})
		done <- err
	}()
	waitLine(t, fx, NotifyProgress, "ignoring SIGTERM")
	t0 := time.Now()
	_, _ = fx.call(ctxT(t), MethodCancel, map[string]string{"job": "j1"})
	select {
	case err := <-done:
		if rpcErr(t, err).Code != CodeCancelled {
			t.Fatal(err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("SIGKILL didn't come")
	}
	if d := time.Since(t0); d < 400*time.Millisecond {
		t.Errorf("killed after %v, before the grace", d)
	}
}

func TestAStepHasADeadline(t *testing.T) {
	fx := newFixture(t, agents.Setup{Install: []agents.Step{{Title: "Wait", Run: fake("sleep")}}})
	fx.s.Deadlines = Deadlines{Step: 300 * time.Millisecond}
	_, err := fx.call(ctxT(t), MethodInstall, map[string]string{"agent": "fake", "job": "j1"})
	re := rpcErr(t, err)
	if re.Code != acp.CodeInternalError || !strings.Contains(re.Message, "took too long") {
		t.Fatalf("error = %+v", re)
	}
}

func waitJob(t *testing.T, s *Service, id string) {
	t.Helper()
	for range 200 {
		s.mu.Lock()
		_, ok := s.jobs[id]
		s.mu.Unlock()
		if ok {
			time.Sleep(100 * time.Millisecond) // and its process
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("job %s never started", id)
}

func waitLine(t *testing.T, fx *fixture, method, want string) {
	t.Helper()
	for range 500 {
		for _, l := range fx.lines(method) {
			if strings.Contains(l, want) {
				return
			}
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatalf("no line %q in %q", want, fx.lines(method))
}

func installFake(t *testing.T, fx *fixture) {
	t.Helper()
	dir := filepath.Join(fx.home, ".local", "bin")
	_ = os.MkdirAll(dir, 0o755)
	if err := os.WriteFile(filepath.Join(dir, "fakeagent"), []byte("#!/bin/sh\necho fake 1.2.3\n"), 0o755); err != nil {
		t.Fatal(err)
	}
}

func prompts(fx *fixture) []loginPrompt {
	fx.mu.Lock()
	defer fx.mu.Unlock()
	var out []loginPrompt
	for _, n := range fx.notes {
		if n.method == NotifyLoginPrompt {
			var p loginPrompt
			_ = json.Unmarshal(n.params, &p)
			out = append(out, p)
		}
	}
	return out
}

func TestLoginShowsTheDeviceCodeAndPage(t *testing.T) {
	fx := newFixture(t, agents.Setup{SignIn: []agents.SignIn{{ID: "device", Kind: agents.KindDevice, Label: "Fake account", Run: fake("device")}}})
	installFake(t, fx)
	raw, err := fx.call(ctxT(t), MethodLogin, map[string]string{"agent": "fake", "method": "device", "job": "l1"})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"signedIn":true,"detail":"the login finished"}` {
		t.Fatalf("result = %s", raw)
	}
	ps := prompts(fx)
	last := ps[len(ps)-1]
	if !last.Done || last.URL != "https://github.com/login/device" || last.Code != "ABCD-1234" || last.Paste {
		t.Fatalf("final prompt = %+v", last)
	}
}

func TestLoginRunsOnATerminal(t *testing.T) {
	fx := newFixture(t, agents.Setup{SignIn: []agents.SignIn{{ID: "t", Kind: agents.KindLink, Label: "x", Run: fake("tty")}}})
	installFake(t, fx)
	if _, err := fx.call(ctxT(t), MethodLogin, map[string]string{"agent": "fake", "method": "t", "job": "l1"}); err != nil {
		t.Fatal(err)
	}
	waitLine(t, fx, NotifyLoginPrompt, "tty=true")
}

func TestLoginPasteBackWritesTheCodeAndCutsItEverywhere(t *testing.T) {
	fx := newFixture(t, agents.Setup{SignIn: []agents.SignIn{{ID: "paste", Kind: agents.KindPaste, Label: "Fake account", Run: fake("paste")}}})
	installFake(t, fx)
	done := make(chan error, 1)
	var raw json.RawMessage
	go func() {
		var err error
		raw, err = fx.call(ctxT(t), MethodLogin, map[string]string{"agent": "fake", "method": "paste", "job": "l1"})
		done <- err
	}()
	// Wait for the paste prompt, which has no newline.
	for i := 0; ; i++ {
		ps := prompts(fx)
		if len(ps) > 0 && ps[len(ps)-1].Paste {
			break
		}
		if i > 500 {
			t.Fatalf("no paste prompt: %+v", ps)
		}
		time.Sleep(10 * time.Millisecond)
	}
	if _, err := fx.call(ctxT(t), MethodLoginInput, map[string]string{"job": "l1", "text": "bad\nline"}); err == nil {
		t.Error("multi-line input accepted")
	}
	if _, err := fx.call(ctxT(t), MethodLoginInput, map[string]string{"job": "l1", "text": "the-secret-code"}); err != nil {
		t.Fatal(err)
	}
	if err := <-done; err != nil {
		t.Fatalf("login: %v (%s)", err, fx.lines(NotifyLoginPrompt))
	}
	if string(raw) != `{"signedIn":true,"detail":"the login finished"}` {
		t.Fatalf("result = %s", raw)
	}
	ps := prompts(fx)
	if ps[len(ps)-1].URL != "https://claude.ai/oauth/authorize?code=true&client_id=x&state=abc" {
		t.Errorf("url = %q", ps[len(ps)-1].URL)
	}
	all := strings.Join(fx.lines(NotifyLoginPrompt), "\n")
	logs, _ := filepath.Glob(filepath.Join(fx.home, ".local/state/quire/jobs/fake-login-*.log"))
	b, _ := os.ReadFile(logs[0])
	for _, where := range []string{all, string(b)} {
		if strings.Contains(where, "the-secret-code") || strings.Contains(where, "sk-ant-abcdef") {
			t.Fatalf("a secret leaked:\n%s", where)
		}
		if !strings.Contains(where, "received "+mask) || !strings.Contains(where, "ANTHROPIC_API_KEY="+mask) {
			t.Errorf("redaction marks missing:\n%s", where)
		}
	}
}

func TestLoginRefusesKindsItDoesntRun(t *testing.T) {
	fx := newFixture(t, agents.Setup{SignIn: []agents.SignIn{{ID: "key", Kind: agents.KindKey, Label: "key"}}})
	installFake(t, fx)
	for _, m := range []string{"key", "nope"} {
		if _, err := fx.call(ctxT(t), MethodLogin, map[string]string{"agent": "fake", "method": m, "job": "l1"}); rpcErr(t, err).Code != acp.CodeInvalidParams {
			t.Errorf("%s: %v", m, err)
		}
	}
	if _, err := fx.call(ctxT(t), MethodLoginInput, map[string]string{"job": "nope", "text": "x"}); err == nil {
		t.Error("input to no job accepted")
	}
}

func TestDetectReadsTheMakersPrompts(t *testing.T) {
	// Synthetic transcripts, written from the makers' documented flows (docs/quire-setup.md §5),
	// not recordings.
	cases := []struct {
		name, out string
		url, code string
		paste     bool
	}{
		{"copilot", "! First copy your one-time code: 8F3A-21KD\nPress Enter to open https://github.com/login/device in your browser...", "https://github.com/login/device", "8F3A-21KD", false},
		{"kimi", "Please visit https://www.kimi.com/code/authorize_device?user_code=QWER-7788 to sign in.\nUser code: QWER-7788", "https://www.kimi.com/code/authorize_device?user_code=QWER-7788", "QWER-7788", false},
		{"grok", "Open \x1b[1mhttps://accounts.x.ai/device\x1b[0m and enter code \x1b[32mZX12-CV34\x1b[0m", "https://accounts.x.ai/device", "ZX12-CV34", false},
		{"claude", "Browser didn't open? Use the url below to sign in (c to copy)\n\x1b]8;;https://claude.ai/oauth/authorize?code=true&state=s1\x1b\\link\x1b]8;;\x1b\\\nPaste code here if prompted >", "https://claude.ai/oauth/authorize?code=true&state=s1", "", true},
		{"cursor", "Open the following URL to log in:\nhttps://cursor.com/loginDeepControl?challenge=abc&uuid=u1&mode=login\nWaiting for authentication...", "https://cursor.com/loginDeepControl?challenge=abc&uuid=u1&mode=login", "", false},
	}
	for _, c := range cases {
		var url, code string
		var paste bool
		for _, l := range strings.Split(c.out, "\n") {
			text, links := clean(l)
			u, cd, p := detect(text, links)
			if u != "" && (url == "" || betterURL(u, url)) {
				url = u
			}
			if cd != "" {
				code = cd
			}
			paste = paste || p
		}
		if url != c.url || code != c.code || paste != c.paste {
			t.Errorf("%s: url=%q code=%q paste=%v", c.name, url, code, paste)
		}
	}
	// A date or a version is not a code.
	if _, code, _ := detect("Version 2026-1105 released", nil); code != "" {
		t.Errorf("code from a date: %q", code)
	}
}

func TestRedactorMasksSecrets(t *testing.T) {
	r := &redactor{}
	r.add("my-pasted-code-123")
	in := "pasted my-pasted-code-123; OPENAI_API_KEY=sk-proj-aaaaaaaaaaaaaaaaaaaa token ghp_bbbbbbbbbbbbbbbbbbbbbbbb xai-cccccccccccccccccccccccc AIzaSyDdddddddddddddddddddddddddddddddd GITHUB_TOKEN: abc123"
	out := r.line(in)
	for _, s := range []string{"my-pasted-code-123", "sk-proj-", "ghp_bbbb", "xai-cccc", "AIzaSyD", "abc123"} {
		if strings.Contains(out, s) {
			t.Errorf("%q kept in %q", s, out)
		}
	}
	if keep := r.line("enter the code ABCD-1234 at https://github.com/login/device"); keep != "enter the code ABCD-1234 at https://github.com/login/device" {
		t.Errorf("a device code was masked: %q", keep)
	}
}

func TestKeysArePrivateAndOnlyForTheirAgent(t *testing.T) {
	fx := newFixture(t, agents.Setup{Keys: []agents.Key{{Name: "FAKE_API_KEY"}}})
	ctx := ctxT(t)
	if _, err := fx.call(ctx, MethodKey, map[string]string{"agent": "fake", "name": "OTHER_API_KEY", "value": "v"}); err == nil {
		t.Error("a key name the agent doesn't take was stored")
	}
	if _, err := fx.call(ctx, MethodKey, map[string]string{"agent": "fake", "name": "FAKE_API_KEY", "value": "two\nlines"}); err == nil {
		t.Error("a two-line key was stored")
	}
	if _, err := fx.call(ctx, MethodKey, map[string]string{"agent": "fake", "name": "FAKE_API_KEY", "value": "k-123"}); err != nil {
		t.Fatal(err)
	}
	dir := filepath.Join(fx.home, ".config/quire/keys")
	di, _ := os.Stat(dir)
	fi, _ := os.Stat(filepath.Join(dir, "fake.env"))
	if di.Mode().Perm() != 0o700 || fi.Mode().Perm() != 0o600 {
		t.Errorf("modes %v %v", di.Mode().Perm(), fi.Mode().Perm())
	}
	if env := fx.s.KeyEnv("fake"); len(env) != 1 || env[0] != "FAKE_API_KEY=k-123" {
		t.Errorf("fake's env = %v", env)
	}
	if env := fx.s.KeyEnv("other"); len(env) != 0 {
		t.Errorf("other's env = %v", env)
	}
	raw, _ := fx.call(ctx, MethodCatalog, struct{}{})
	if !strings.Contains(string(raw), `"hasKey":true`) || strings.Contains(string(raw), "k-123") {
		t.Errorf("catalog = %s", raw)
	}
	raw, err := fx.call(ctx, MethodSignout, map[string]string{"agent": "fake"})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), filepath.Join(dir, "fake.env")) {
		t.Errorf("sign-out = %s", raw)
	}
	if _, err := os.Lstat(filepath.Join(dir, "fake.env")); !os.IsNotExist(err) {
		t.Error("the key file survived sign-out")
	}
}

func TestKeysRefuseUnsafeStorage(t *testing.T) {
	setup := func(t *testing.T) (Keys, string) {
		home := t.TempDir()
		return Keys{Home: home}, filepath.Join(home, ".config/quire/keys")
	}
	t.Run("symlinked folder", func(t *testing.T) {
		k, dir := setup(t)
		elsewhere := t.TempDir()
		_ = os.MkdirAll(filepath.Dir(dir), 0o700)
		_ = os.Chmod(elsewhere, 0o700)
		_ = os.Symlink(elsewhere, dir)
		if err := k.Set("fake", "FAKE_API_KEY", "v"); !errors.Is(err, ErrUnsafe) {
			t.Fatalf("err = %v", err)
		}
		if ents, _ := os.ReadDir(elsewhere); len(ents) != 0 {
			t.Fatalf("wrote through the link: %v", ents)
		}
	})
	t.Run("open folder", func(t *testing.T) {
		k, dir := setup(t)
		_ = os.MkdirAll(dir, 0o755)
		_ = os.Chmod(dir, 0o755)
		if err := k.Set("fake", "FAKE_API_KEY", "v"); !errors.Is(err, ErrUnsafe) {
			t.Fatalf("err = %v", err)
		}
	})
	t.Run("symlinked file", func(t *testing.T) {
		k, dir := setup(t)
		_ = os.MkdirAll(dir, 0o700)
		target := filepath.Join(t.TempDir(), "target")
		_ = os.WriteFile(target, []byte("X=1\n"), 0o600)
		_ = os.Symlink(target, filepath.Join(dir, "fake.env"))
		if _, err := k.Env("fake"); !errors.Is(err, ErrUnsafe) {
			t.Errorf("read through a link: %v", err)
		}
		if err := k.Set("fake", "FAKE_API_KEY", "v"); err == nil {
			t.Error("replaced a link")
		}
		if b, _ := os.ReadFile(target); string(b) != "X=1\n" {
			t.Errorf("target changed: %q", b)
		}
	})
	t.Run("open file", func(t *testing.T) {
		k, dir := setup(t)
		if err := k.Set("fake", "FAKE_API_KEY", "v"); err != nil {
			t.Fatal(err)
		}
		_ = os.Chmod(filepath.Join(dir, "fake.env"), 0o644)
		if _, err := k.Env("fake"); !errors.Is(err, ErrUnsafe) {
			t.Errorf("read a 0644 key file: %v", err)
		}
	})
	t.Run("bad agent", func(t *testing.T) {
		k, _ := setup(t)
		if err := k.Set("../x", "FAKE_API_KEY", "v"); err == nil {
			t.Error("agent id with a path accepted")
		}
	})
}

func TestRemoveDeletesOnlyItsPathsAndSettingsWhenAsked(t *testing.T) {
	fx := newFixture(t, agents.Setup{Keys: []agents.Key{{Name: "FAKE_API_KEY"}},
		Remove: agents.Removal{Paths: []string{".local/bin/fakeagent", "../outside"}, Settings: []string{".fake"}}})
	installFake(t, fx)
	_ = os.MkdirAll(filepath.Join(fx.home, ".fake"), 0o700)
	outside := filepath.Join(filepath.Dir(fx.home), "outside")
	_ = os.WriteFile(outside, nil, 0o600)
	t.Cleanup(func() { os.Remove(outside) })
	raw, err := fx.call(ctxT(t), MethodRemove, map[string]any{"agent": "fake", "job": "r1"})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"removed":["~/.local/bin/fakeagent"]}` {
		t.Fatalf("removed = %s", raw)
	}
	if _, err := os.Stat(filepath.Join(fx.home, ".fake")); err != nil {
		t.Error("settings removed without asking")
	}
	if _, err := os.Stat(outside); err != nil {
		t.Error("a path outside home was removed")
	}
	_ = fx.s.keys().Set("fake", "FAKE_API_KEY", "v")
	raw, err = fx.call(ctxT(t), MethodRemove, map[string]any{"agent": "fake", "job": "r2", "settings": true})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(raw), "~/.fake") || !strings.Contains(string(raw), "fake.env") {
		t.Errorf("removed = %s", raw)
	}
}

func TestSigninStatus(t *testing.T) {
	fx := newFixture(t, agents.Setup{SignIn: []agents.SignIn{{ID: "none", Kind: agents.KindNone}}})
	raw, _ := fx.call(ctxT(t), MethodSignin, map[string]string{"agent": "fake"})
	if string(raw) != `{"signedIn":true,"detail":"no account needed"}` {
		t.Errorf("none: %s", raw)
	}
	fx = newFixture(t, agents.Setup{Status: &agents.Status{Run: fake("device"), Yes: `Signed in`}})
	raw, _ = fx.call(ctxT(t), MethodSignin, map[string]string{"agent": "fake"})
	if string(raw) != `{"signedIn":null,"detail":"not installed"}` {
		t.Errorf("not installed: %s", raw)
	}
	installFake(t, fx)
	raw, _ = fx.call(ctxT(t), MethodSignin, map[string]string{"agent": "fake"})
	if string(raw) != `{"signedIn":true}` {
		t.Errorf("status: %s", raw)
	}
}
