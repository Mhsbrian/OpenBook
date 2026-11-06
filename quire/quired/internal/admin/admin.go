// Package admin is `quired admin`, the narrow root worker of the Linux environment
// (docs/quire-setup.md §4.3). It does what quired and the agents can't, under quired.service's
// NoNewPrivileges, and nothing else:
//
//	debian-install {"packages": [...]}         → {"installed": [...]}   (+ "progress" {"line"})
//	quired-update  {"deb": base64, "sha256"}   → {"job"}                dpkg runs in its own unit
//	job            {"id"}                      → {"state", "version"?, "error"?}
//	version        {}                          → {"version"}
//
// systemd starts one worker per connection (quire-admin.socket, vsock port 7691, Accept=yes),
// and the worker serves it only if the peer is the host (CID 2: Android, where only Quire core can
// reach this port through the Terminal app's bridge). Agents in the guest reach vsock only
// locally (CID 1) and are refused. Requests are newline-delimited JSON-RPC 2.0, ACP's framing.
//
// No request data reaches a shell: package names must be on DebianAllowlist, a package update
// must match its hash, be named quired, be built for this architecture and be newer than the
// installed one, and every command is an argument vector.
package admin

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"slices"
	"strings"
	"sync"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/vsock"
)

const (
	MethodDebianInstall = "debian-install"
	MethodQuiredUpdate  = "quired-update"
	MethodJob           = "job"
	MethodVersion       = "version"
	NotifyProgress      = "progress"
)

// MaxDeb bounds a quired package sent for an update.
const MaxDeb = 64 << 20

// Runner runs a command (an argument vector, never a shell line). line, if set, receives each
// line of its combined output as it arrives; the whole output is returned too.
type Runner interface {
	Run(ctx context.Context, argv []string, env []string, line func(string)) ([]byte, error)
}

// Worker serves one connection.
type Worker struct {
	Version  string
	State    string // /var/lib/quire: updates/ and jobs/, root only
	Allow    []string
	Run      Runner
	Self     string // quired's own executable, which the update unit runs
	Lists    string // /var/lib/apt/lists
	MaxAge   time.Duration
	Now      func() time.Time
	NewID    func() string
	Log      *log.Logger
	Timeouts Timeouts
}

type Timeouts struct {
	Apt  time.Duration
	Dpkg time.Duration
}

// New returns a worker with the real machine's defaults.
func New(version string, lg *log.Logger) *Worker {
	self, _ := os.Executable()
	return &Worker{Version: version, State: "/var/lib/quire", Allow: agents.DebianAllowlist, Run: ExecRunner{},
		Self: self, Lists: "/var/lib/apt/lists", MaxAge: 24 * time.Hour, Now: time.Now, NewID: randomID, Log: lg,
		Timeouts: Timeouts{Apt: 20 * time.Minute, Dpkg: 5 * time.Minute}}
}

func randomID() string {
	var b [8]byte
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}

func (w *Worker) logf(format string, args ...any) {
	if w.Log != nil {
		w.Log.Printf(format, args...)
	}
}

// PeerAllowed reports whether a connection's peer may use the worker: a vsock peer whose CID is
// the host's. Any other family (a unix socket, an inet socket) and any other CID is refused.
func PeerAllowed(family uint16, addr vsock.Addr) bool {
	return family == vsock.AF_VSOCK && addr.CID == vsock.CIDHost
}

// Serve answers requests on one connection until it closes.
//
// A request keeps running if the connection ends: apt or dpkg stopped half-way would leave
// Debian's package database interrupted. Serve returns once every request has finished, so
// systemd doesn't stop the worker's unit (and its children) under them.
func (w *Worker) Serve(ctx context.Context, peer string, r io.Reader, wr io.Writer) error {
	var conn *acp.Conn
	var inflight sync.WaitGroup
	conn = acp.NewConn(r, wr, acp.Handlers{Request: func(ctx context.Context, method string, params json.RawMessage) (any, error) {
		inflight.Add(1)
		defer inflight.Done()
		notify := func(line string) { _ = conn.Notify(ctx, NotifyProgress, map[string]string{"line": line}) }
		res, err := w.handle(context.WithoutCancel(ctx), method, params, notify)
		if err != nil {
			w.logf("%s: %s: %v", peer, method, err)
		}
		return res, err
	}}, nil)
	select {
	case <-conn.Done():
	case <-ctx.Done():
	}
	inflight.Wait()
	return conn.Err()
}

func bad(format string, args ...any) error { return acp.Errorf(acp.CodeInvalidParams, format, args...) }

func (w *Worker) handle(ctx context.Context, method string, params json.RawMessage, notify func(string)) (any, error) {
	if len(params) == 0 {
		params = []byte("{}")
	}
	switch method {
	case MethodVersion:
		return map[string]string{"version": w.Version}, nil
	case MethodDebianInstall:
		var p struct {
			Packages []string `json:"packages"`
		}
		if err := json.Unmarshal(params, &p); err != nil {
			return nil, bad("%v", err)
		}
		return w.debianInstall(ctx, p.Packages, notify)
	case MethodQuiredUpdate:
		var p struct {
			Deb    string `json:"deb"`
			SHA256 string `json:"sha256"`
		}
		if err := json.Unmarshal(params, &p); err != nil {
			return nil, bad("%v", err)
		}
		return w.quiredUpdate(ctx, p.Deb, p.SHA256)
	case MethodJob:
		var p struct {
			ID string `json:"id"`
		}
		if err := json.Unmarshal(params, &p); err != nil {
			return nil, bad("%v", err)
		}
		return w.job(p.ID)
	}
	return nil, acp.Errorf(acp.CodeMethodNotFound, "quired admin does not offer %s", method)
}

var debName = regexp.MustCompile(`^[a-z0-9][a-z0-9+.-]{0,62}$`)

func (w *Worker) installedDeb(ctx context.Context, pkg string) bool {
	out, err := w.Run.Run(ctx, []string{"dpkg-query", "-W", "-f=${Status}", pkg}, nil, nil)
	return err == nil && strings.Contains(string(out), "install ok installed")
}

// listsFresh reports whether apt's package lists were updated within MaxAge.
func (w *Worker) listsFresh() bool {
	ents, err := os.ReadDir(w.Lists)
	if err != nil {
		return false
	}
	var newest time.Time
	for _, e := range ents {
		if e.IsDir() || e.Name() == "lock" {
			continue
		}
		if fi, err := e.Info(); err == nil && fi.ModTime().After(newest) {
			newest = fi.ModTime()
		}
	}
	return !newest.IsZero() && w.Now().Sub(newest) < w.MaxAge
}

// aptLock waits for apt's lock (the person may be running apt in Terminal) instead of failing.
const aptLock = "DPkg::Lock::Timeout=120"

var aptEnv = []string{"DEBIAN_FRONTEND=noninteractive", "NEEDRESTART_MODE=a", "APT_LISTCHANGES_FRONTEND=none"}

func (w *Worker) debianInstall(ctx context.Context, pkgs []string, notify func(string)) (any, error) {
	if len(pkgs) == 0 || len(pkgs) > len(w.Allow) {
		return nil, bad("name between 1 and %d packages", len(w.Allow))
	}
	for _, p := range pkgs {
		if !debName.MatchString(p) || !slices.Contains(w.Allow, p) {
			return nil, bad("%q isn't a package quired admin installs (it installs only: %s)", p, strings.Join(w.Allow, " "))
		}
	}
	var missing []string
	for _, p := range pkgs {
		if !slices.Contains(missing, p) && !w.installedDeb(ctx, p) {
			missing = append(missing, p)
		}
	}
	res := map[string][]string{"installed": {}}
	if len(missing) == 0 {
		return res, nil
	}
	actx, cancel := context.WithTimeout(ctx, w.Timeouts.Apt)
	defer cancel()
	if !w.listsFresh() {
		if out, err := w.Run.Run(actx, []string{"apt-get", "-o", aptLock, "update"}, aptEnv, notify); err != nil {
			return nil, failed("apt-get update", err, out)
		}
	}
	argv := append([]string{"apt-get", "-o", aptLock, "install", "-y", "--no-install-recommends", "--"}, missing...)
	if out, err := w.Run.Run(actx, argv, aptEnv, notify); err != nil {
		return nil, failed("apt-get install", err, out)
	}
	w.logf("debian-install: %s", strings.Join(missing, " "))
	res["installed"] = missing
	return res, nil
}

func failed(what string, err error, out []byte) error {
	data, _ := json.Marshal(map[string]string{"output": tail(out, 40)})
	return &acp.RPCError{Code: acp.CodeInternalError, Message: what + ": " + err.Error(), Data: data}
}

func tail(b []byte, n int) string {
	lines := strings.Split(strings.TrimRight(string(b), "\n"), "\n")
	if len(lines) > n {
		lines = lines[len(lines)-n:]
	}
	return strings.Join(lines, "\n")
}

func (w *Worker) out(ctx context.Context, argv ...string) (string, error) {
	b, err := w.Run.Run(ctx, argv, nil, nil)
	return strings.TrimSpace(string(b)), err
}

// Job is a quired update's record in State/jobs.
type Job struct {
	State   string `json:"state"` // running, done, failed
	Version string `json:"version,omitempty"`
	Error   string `json:"error,omitempty"`
	Started string `json:"started,omitempty"`
	Ended   string `json:"ended,omitempty"`
}

func (w *Worker) dirs() (updates, jobs string, err error) {
	updates, jobs = filepath.Join(w.State, "updates"), filepath.Join(w.State, "jobs")
	for _, d := range []string{w.State, updates, jobs} {
		if err := os.MkdirAll(d, 0o700); err != nil {
			return "", "", err
		}
		if err := os.Chmod(d, 0o700); err != nil {
			return "", "", err
		}
	}
	return updates, jobs, nil
}

func (w *Worker) quiredUpdate(ctx context.Context, b64, want string) (any, error) {
	want = strings.ToLower(strings.TrimSpace(want))
	if len(want) != 64 {
		return nil, bad("sha256 must be 64 hex digits")
	}
	if base64.StdEncoding.DecodedLen(len(b64)) > MaxDeb {
		return nil, bad("the package is larger than %d bytes", MaxDeb)
	}
	deb, err := base64.StdEncoding.DecodeString(b64)
	if err != nil {
		return nil, bad("deb: %v", err)
	}
	sum := sha256.Sum256(deb)
	if hex.EncodeToString(sum[:]) != want {
		return nil, bad("the package doesn't match its sha256")
	}
	updates, jobs, err := w.dirs()
	if err != nil {
		return nil, err
	}
	id := w.NewID()
	path := filepath.Join(updates, id+".deb")
	if err := os.WriteFile(path, deb, 0o600); err != nil {
		return nil, err
	}
	keep := false
	defer func() {
		if !keep {
			os.Remove(path)
		}
	}()
	field := func(f string) (string, error) { return w.out(ctx, "dpkg-deb", "-f", path, f) }
	name, err := field("Package")
	if err != nil {
		return nil, bad("not a Debian package: %v", err)
	}
	if name != "quired" {
		return nil, bad("the package is %q, not quired", name)
	}
	arch, err := field("Architecture")
	if err != nil {
		return nil, err
	}
	host, err := w.out(ctx, "dpkg", "--print-architecture")
	if err != nil {
		return nil, err
	}
	if arch != host {
		return nil, bad("the package is for %s; this is %s", arch, host)
	}
	ver, err := field("Version")
	if err != nil || ver == "" {
		return nil, bad("the package has no version")
	}
	old, _ := w.out(ctx, "dpkg-query", "-W", "-f=${Version}", "quired")
	if old != "" {
		if _, err := w.Run.Run(ctx, []string{"dpkg", "--compare-versions", ver, "gt", old}, nil, nil); err != nil {
			return nil, bad("quired %s isn't newer than the installed %s", ver, old)
		}
	}
	rec := Job{State: "running", Version: ver, Started: w.Now().UTC().Format(time.RFC3339)}
	if err := writeJob(filepath.Join(jobs, id+".json"), rec); err != nil {
		return nil, err
	}
	// dpkg runs in a transient unit of its own: quired.service restarts during it (postinst),
	// and this connection may end, but the update finishes and leaves its record.
	argv := []string{"systemd-run", "--unit=quire-update-" + id, "--collect", "--quiet", "--no-block",
		"--property=Type=oneshot", "--", w.Self, "admin", "apply-update", "--job", id, "--state", w.State}
	if out, err := w.Run.Run(ctx, argv, nil, nil); err != nil {
		_ = writeJob(filepath.Join(jobs, id+".json"), Job{State: "failed", Version: ver, Error: "systemd-run: " + err.Error() + ": " + tail(out, 5)})
		return nil, failed("systemd-run", err, out)
	}
	keep = true
	w.logf("quired-update: %s -> %s, job %s", old, ver, id)
	return map[string]string{"job": id}, nil
}

// ApplyUpdate is the update unit's work: dpkg -i the staged package, then record the result.
func (w *Worker) ApplyUpdate(ctx context.Context, id string) error {
	if !jobRe.MatchString(id) {
		return errors.New("bad job id")
	}
	updates, jobs, err := w.dirs()
	if err != nil {
		return err
	}
	path := filepath.Join(updates, id+".deb")
	recPath := filepath.Join(jobs, id+".json")
	var rec Job
	if b, err := os.ReadFile(recPath); err == nil {
		_ = json.Unmarshal(b, &rec)
	}
	dctx, cancel := context.WithTimeout(ctx, w.Timeouts.Dpkg)
	defer cancel()
	out, err := w.Run.Run(dctx, []string{"dpkg", "-i", path}, aptEnv, nil)
	os.Remove(path)
	rec.Ended = w.Now().UTC().Format(time.RFC3339)
	if err != nil {
		rec.State, rec.Error = "failed", "dpkg -i: "+err.Error()+"\n"+tail(out, 20)
	} else {
		rec.State = "done"
		if v, err := w.out(ctx, "dpkg-query", "-W", "-f=${Version}", "quired"); err == nil {
			rec.Version = v
		}
	}
	return writeJob(recPath, rec)
}

func writeJob(path string, rec Job) error {
	b, _ := json.Marshal(rec)
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, b, 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

var jobRe = regexp.MustCompile(`^[0-9a-f]{16}$`)

func (w *Worker) job(id string) (any, error) {
	if !jobRe.MatchString(id) {
		return nil, bad("a job id is 16 hex digits")
	}
	b, err := os.ReadFile(filepath.Join(w.State, "jobs", id+".json"))
	if err != nil {
		return nil, bad("no job %s", id)
	}
	var rec Job
	if err := json.Unmarshal(b, &rec); err != nil {
		return nil, err
	}
	return rec, nil
}

// ExecRunner runs commands on this machine.
type ExecRunner struct{}

func (ExecRunner) Run(ctx context.Context, argv []string, env []string, line func(string)) ([]byte, error) {
	cmd := exec.CommandContext(ctx, argv[0], argv[1:]...)
	cmd.Env = append(os.Environ(), env...)
	cmd.WaitDelay = 5 * time.Second
	var buf bytes.Buffer
	if line == nil {
		cmd.Stdout, cmd.Stderr = &buf, &buf
		err := cmd.Run()
		return buf.Bytes(), err
	}
	lw := &lineWriter{buf: &buf, line: line}
	cmd.Stdout, cmd.Stderr = lw, lw
	err := cmd.Run()
	lw.flush()
	return buf.Bytes(), err
}

type lineWriter struct {
	buf  *bytes.Buffer
	part []byte
	line func(string)
}

func (l *lineWriter) Write(p []byte) (int, error) {
	l.buf.Write(p)
	l.part = append(l.part, p...)
	for {
		i := bytes.IndexAny(l.part, "\r\n")
		if i < 0 {
			break
		}
		if s := strings.TrimSpace(string(l.part[:i])); s != "" {
			l.line(s)
		}
		l.part = l.part[i+1:]
	}
	return len(p), nil
}

func (l *lineWriter) flush() {
	if s := strings.TrimSpace(string(l.part)); s != "" {
		l.line(s)
	}
	l.part = nil
}

// Describe is for logs: who connected.
func Describe(family uint16, addr vsock.Addr) string {
	if family == vsock.AF_VSOCK {
		return addr.String()
	}
	return fmt.Sprintf("family %d", family)
}
