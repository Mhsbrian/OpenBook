package admin

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"testing"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/vsock"
)

// fakeRunner answers commands by their argument vector and records every one.
type fakeRunner struct {
	mu    sync.Mutex
	calls [][]string
	envs  [][]string
	reply func(argv []string) (string, error)
}

func (f *fakeRunner) Run(_ context.Context, argv []string, env []string, line func(string)) ([]byte, error) {
	f.mu.Lock()
	f.calls = append(f.calls, append([]string{}, argv...))
	f.envs = append(f.envs, env)
	f.mu.Unlock()
	out, err := f.reply(argv)
	if line != nil {
		for _, l := range strings.Split(strings.TrimSpace(out), "\n") {
			if l != "" {
				line(l)
			}
		}
	}
	return []byte(out), err
}

func (f *fakeRunner) ran(prefix ...string) [][]string {
	f.mu.Lock()
	defer f.mu.Unlock()
	var out [][]string
	for _, c := range f.calls {
		if len(c) >= len(prefix) && strings.Join(c[:len(prefix)], " ") == strings.Join(prefix, " ") {
			out = append(out, c)
		}
	}
	return out
}

var errExit = errors.New("exit status 1")

func newWorker(t *testing.T, reply func([]string) (string, error)) (*Worker, *fakeRunner) {
	r := &fakeRunner{reply: reply}
	w := &Worker{Version: "test", State: t.TempDir(), Allow: agents.DebianAllowlist, Run: r, Self: "/usr/bin/quired",
		Lists: t.TempDir(), MaxAge: time.Hour, Now: time.Now, NewID: func() string { return "0123456789abcdef" },
		Timeouts: Timeouts{Apt: time.Minute, Dpkg: time.Minute}}
	return w, r
}

func call(t *testing.T, w *Worker, method string, params any) (json.RawMessage, error, []string) {
	t.Helper()
	b, _ := json.Marshal(params)
	var lines []string
	res, err := w.handle(context.Background(), method, b, func(l string) { lines = append(lines, l) })
	if err != nil {
		return nil, err, lines
	}
	out, _ := json.Marshal(res)
	return out, nil, lines
}

func code(t *testing.T, err error) int {
	t.Helper()
	var re *acp.RPCError
	if !errors.As(err, &re) {
		t.Fatalf("want an RPC error, got %v", err)
	}
	return re.Code
}

func TestDebianInstallOnlyTakesTheAllowlist(t *testing.T) {
	w, r := newWorker(t, func([]string) (string, error) { return "", nil })
	for _, pkgs := range [][]string{{"vim"}, {"curl", "openssh-server"}, {"curl; rm -rf /"}, {"-oDebug::pkgProblemResolver=1"}, {}} {
		_, err, _ := call(t, w, MethodDebianInstall, map[string]any{"packages": pkgs})
		if err == nil || code(t, err) != acp.CodeInvalidParams {
			t.Errorf("%q: %v", pkgs, err)
		}
	}
	if len(r.calls) != 0 {
		t.Errorf("ran commands for refused requests: %v", r.calls)
	}
}

func TestDebianInstallInstallsOnlyWhatIsMissing(t *testing.T) {
	w, r := newWorker(t, func(argv []string) (string, error) {
		if argv[0] == "dpkg-query" {
			if argv[3] == "curl" {
				return "install ok installed", nil
			}
			return "", errExit
		}
		return "Setting up git (1:2.47)\n", nil
	})
	// The lists are stale: apt-get update first.
	raw, err, lines := call(t, w, MethodDebianInstall, map[string]any{"packages": []string{"curl", "git"}})
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"installed":["git"]}` {
		t.Fatalf("result = %s", raw)
	}
	if len(r.ran("apt-get", "-o", aptLock, "update")) != 1 {
		t.Errorf("no apt-get update: %v", r.calls)
	}
	inst := r.ran("apt-get", "-o", aptLock, "install")
	if len(inst) != 1 || strings.Join(inst[0], " ") != "apt-get -o DPkg::Lock::Timeout=120 install -y --no-install-recommends -- git" {
		t.Errorf("install = %v", inst)
	}
	if len(lines) == 0 || !strings.Contains(lines[len(lines)-1], "Setting up git") {
		t.Errorf("progress lines = %v", lines)
	}
	if !strings.Contains(strings.Join(r.envs[len(r.envs)-1], " "), "DEBIAN_FRONTEND=noninteractive") {
		t.Errorf("env = %v", r.envs[len(r.envs)-1])
	}
	// Fresh lists: no update; nothing missing: nothing at all.
	_ = os.WriteFile(filepath.Join(w.Lists, "deb.debian.org_Packages"), nil, 0o644)
	r.calls = nil
	if _, err, _ := call(t, w, MethodDebianInstall, map[string]any{"packages": []string{"git"}}); err != nil {
		t.Fatal(err)
	}
	if len(r.ran("apt-get", "-o", aptLock, "update")) != 0 || len(r.ran("apt-get", "-o", aptLock, "install")) != 1 {
		t.Errorf("calls = %v", r.calls)
	}
	r.calls = nil
	raw, _, _ = call(t, w, MethodDebianInstall, map[string]any{"packages": []string{"curl"}})
	if string(raw) != `{"installed":[]}` || len(r.ran("apt-get")) != 0 {
		t.Errorf("already installed: %s %v", raw, r.calls)
	}
}

func TestPeerAllowedOnlyTheHost(t *testing.T) {
	cases := []struct {
		family uint16
		cid    uint32
		ok     bool
	}{
		{vsock.AF_VSOCK, vsock.CIDHost, true},
		{vsock.AF_VSOCK, vsock.CIDLocal, false}, // an agent inside the guest, over vsock loopback
		{vsock.AF_VSOCK, 3, false},              // another VM
		{syscall.AF_UNIX, vsock.CIDHost, false},
		{syscall.AF_INET, vsock.CIDHost, false},
	}
	for _, c := range cases {
		if got := PeerAllowed(c.family, vsock.Addr{CID: c.cid, Port: 1}); got != c.ok {
			t.Errorf("family %d cid %d: %v", c.family, c.cid, got)
		}
	}
	// A real socket that isn't vsock (what a confused unit or a test hook could hand over).
	fds, err := syscall.Socketpair(syscall.AF_UNIX, syscall.SOCK_STREAM, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer syscall.Close(fds[0])
	defer syscall.Close(fds[1])
	family, addr, err := vsock.Peer(fds[0])
	if err != nil {
		t.Fatal(err)
	}
	if family != syscall.AF_UNIX || PeerAllowed(family, addr) {
		t.Errorf("unix peer: family %d allowed %v", family, PeerAllowed(family, addr))
	}
}

// debReply answers dpkg-deb, dpkg and dpkg-query for a package with these fields.
func debReply(name, arch, version, installed string, newer bool) func([]string) (string, error) {
	return func(argv []string) (string, error) {
		switch {
		case argv[0] == "dpkg-deb" && argv[3] == "Package":
			return name + "\n", nil
		case argv[0] == "dpkg-deb" && argv[3] == "Architecture":
			return arch + "\n", nil
		case argv[0] == "dpkg-deb" && argv[3] == "Version":
			return version + "\n", nil
		case argv[0] == "dpkg" && argv[1] == "--print-architecture":
			return "amd64\n", nil
		case argv[0] == "dpkg-query":
			return installed, nil
		case argv[0] == "dpkg" && argv[1] == "--compare-versions":
			if newer {
				return "", nil
			}
			return "", errExit
		case argv[0] == "systemd-run":
			return "", nil
		case argv[0] == "dpkg" && argv[1] == "-i":
			return "Unpacking quired (" + version + ")\n", nil
		}
		return "", errors.New("unexpected " + strings.Join(argv, " "))
	}
}

func pkg(b []byte) map[string]string {
	s := sha256.Sum256(b)
	return map[string]string{"deb": base64.StdEncoding.EncodeToString(b), "sha256": hex.EncodeToString(s[:])}
}

func TestQuiredUpdateRefusesWhatIsntANewerQuired(t *testing.T) {
	deb := []byte("!<arch>\nfake deb")
	cases := []struct {
		name   string
		reply  func([]string) (string, error)
		params map[string]string
	}{
		{"wrong hash", debReply("quired", "amd64", "0.4.1", "0.4.0", true), map[string]string{"deb": pkg(deb)["deb"], "sha256": strings.Repeat("0", 64)}},
		{"another package", debReply("openssh-server", "amd64", "9.9", "0.4.0", true), pkg(deb)},
		{"another architecture", debReply("quired", "arm64", "0.4.1", "0.4.0", true), pkg(deb)},
		{"not newer", debReply("quired", "amd64", "0.3.0", "0.4.0", false), pkg(deb)},
		{"no base64", debReply("quired", "amd64", "0.4.1", "0.4.0", true), map[string]string{"deb": "%%%", "sha256": pkg(deb)["sha256"]}},
	}
	for _, c := range cases {
		w, r := newWorker(t, c.reply)
		_, err, _ := call(t, w, MethodQuiredUpdate, c.params)
		if err == nil || code(t, err) != acp.CodeInvalidParams {
			t.Errorf("%s: %v", c.name, err)
		}
		if len(r.ran("systemd-run")) != 0 {
			t.Errorf("%s: started an update", c.name)
		}
		if ents, _ := os.ReadDir(filepath.Join(w.State, "updates")); len(ents) != 0 {
			t.Errorf("%s: left %v", c.name, ents)
		}
	}
}

func TestQuiredUpdateRunsInItsOwnUnitAndRecordsTheResult(t *testing.T) {
	deb := []byte("!<arch>\nfake deb")
	w, r := newWorker(t, debReply("quired", "amd64", "0.4.1", "0.4.0", true))
	raw, err, _ := call(t, w, MethodQuiredUpdate, pkg(deb))
	if err != nil {
		t.Fatal(err)
	}
	if string(raw) != `{"job":"0123456789abcdef"}` {
		t.Fatalf("result = %s", raw)
	}
	run := r.ran("systemd-run")
	want := "systemd-run --unit=quire-update-0123456789abcdef --collect --quiet --no-block --property=Type=oneshot -- /usr/bin/quired admin apply-update --job 0123456789abcdef --state " + w.State
	if len(run) != 1 || strings.Join(run[0], " ") != want {
		t.Fatalf("systemd-run = %v", run)
	}
	for _, d := range []string{w.State + "/updates", w.State + "/jobs"} {
		if fi, _ := os.Stat(d); fi.Mode().Perm() != 0o700 {
			t.Errorf("%s mode %v", d, fi.Mode().Perm())
		}
	}
	raw, err, _ = call(t, w, MethodJob, map[string]string{"id": "0123456789abcdef"})
	if err != nil || !strings.Contains(string(raw), `"state":"running"`) || !strings.Contains(string(raw), `"version":"0.4.1"`) {
		t.Fatalf("job = %s %v", raw, err)
	}
	// The unit's work: dpkg -i, then the record. The installed version is now the new one.
	w.Run = &fakeRunner{reply: debReply("quired", "amd64", "0.4.1", "0.4.1", true)}
	if err := w.ApplyUpdate(context.Background(), "0123456789abcdef"); err != nil {
		t.Fatal(err)
	}
	raw, _, _ = call(t, w, MethodJob, map[string]string{"id": "0123456789abcdef"})
	if !strings.Contains(string(raw), `"state":"done"`) || !strings.Contains(string(raw), `"version":"0.4.1"`) {
		t.Fatalf("job after apply = %s", raw)
	}
	if _, err := os.Stat(filepath.Join(w.State, "updates", "0123456789abcdef.deb")); !os.IsNotExist(err) {
		t.Error("the staged package was kept")
	}
	for _, id := range []string{"../../etc/passwd", "0123", "ZZZZZZZZZZZZZZZZ"} {
		if _, err, _ := call(t, w, MethodJob, map[string]string{"id": id}); err == nil {
			t.Errorf("job %q accepted", id)
		}
	}
}

func TestApplyUpdateRecordsAFailure(t *testing.T) {
	w, _ := newWorker(t, func(argv []string) (string, error) {
		if argv[0] == "dpkg" && argv[1] == "-i" {
			return "dpkg: error processing archive\n", errExit
		}
		return "", nil
	})
	_, jobs, _ := w.dirs()
	_ = writeJob(filepath.Join(jobs, "0123456789abcdef.json"), Job{State: "running", Version: "0.4.1"})
	_ = w.ApplyUpdate(context.Background(), "0123456789abcdef")
	raw, _, _ := call(t, w, MethodJob, map[string]string{"id": "0123456789abcdef"})
	if !strings.Contains(string(raw), `"state":"failed"`) || !strings.Contains(string(raw), "error processing archive") {
		t.Fatalf("job = %s", raw)
	}
}

func TestEveryRecipeDebianPackageIsAllowed(t *testing.T) {
	for _, s := range agents.Catalog {
		if s.Setup == nil {
			continue
		}
		for _, p := range s.Setup.Debian {
			ok := false
			for _, a := range agents.DebianAllowlist {
				ok = ok || a == p
			}
			if !ok {
				t.Errorf("%s needs %s, which the worker refuses", s.ID, p)
			}
		}
	}
}

func TestARequestOutlivesItsConnection(t *testing.T) {
	release := make(chan struct{})
	started := make(chan struct{})
	w, _ := newWorker(t, func(argv []string) (string, error) {
		if argv[0] == "dpkg-query" {
			return "", errExit
		}
		if argv[0] == "apt-get" && argv[3] == "install" {
			close(started)
			<-release
		}
		return "", nil
	})
	cr, sw := io.Pipe()
	sr, cw := io.Pipe()
	done := make(chan struct{})
	go func() { _ = w.Serve(context.Background(), "test", sr, sw); close(done) }()
	c := acp.NewConn(cr, cw, acp.Handlers{}, nil)
	go func() {
		_ = c.Call(context.Background(), MethodDebianInstall, map[string]any{"packages": []string{"git"}}, nil)
	}()
	<-started
	cw.Close() // the client goes away while apt runs
	select {
	case <-done:
		t.Fatal("Serve returned while apt was still running")
	case <-time.After(200 * time.Millisecond):
	}
	close(release)
	select {
	case <-done:
	case <-time.After(5 * time.Second):
		t.Fatal("Serve didn't return after apt finished")
	}
}
