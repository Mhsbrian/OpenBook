package setup

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
)

// ErrCancelled is returned by a job stopped by _quire/cancel or by its connection closing.
var ErrCancelled = errors.New("cancelled")

// job is one running install, update, remove or login.
type job struct {
	id    string
	agent string
	kind  string

	cancel context.CancelFunc
	red    *redactor
	log    *jobLog

	mu    sync.Mutex
	code  *regexp.Regexp // a paste-back login's code shape, or nil
	hint  string         // what to say when the input isn't that shape
	tail  []string       // the last lines, redacted, for an error's data
	lines int            // how many lines the job has printed
	ended bool           // its command has exited
	input io.Writer
	quiet time.Time // don't flush a partial line before this (an echo may still be arriving)
}

const tailLines = 40

func (j *job) keep(line string) {
	j.mu.Lock()
	j.tail = append(j.tail, line)
	j.lines++
	if len(j.tail) > tailLines {
		j.tail = j.tail[len(j.tail)-tailLines:]
	}
	j.mu.Unlock()
}

// answer returns what the job printed after its first `from` lines: once it has printed
// something, the lines that came before it went quiet for settle, or before wait ran out or its
// command exited. Echoes of the input (lines holding the mask) aren't an answer.
func (j *job) answer(from int, wait, settle time.Duration) []string {
	deadline := time.Now().Add(wait)
	last, lastAt := from, time.Now()
	for {
		j.mu.Lock()
		n, ended := j.lines, j.ended
		j.mu.Unlock()
		if n != last {
			last, lastAt = n, time.Now()
		}
		now := time.Now()
		if ended || now.After(deadline) || (last > from && now.Sub(lastAt) >= settle && len(j.since(from)) > 0) {
			return j.since(from)
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func (j *job) since(from int) []string {
	j.mu.Lock()
	defer j.mu.Unlock()
	k := j.lines - from
	if k > len(j.tail) {
		k = len(j.tail)
	}
	var out []string
	for _, l := range j.tail[len(j.tail)-k:] {
		if !strings.Contains(l, mask) {
			out = append(out, l)
		}
	}
	return out
}

func (j *job) output() string {
	j.mu.Lock()
	defer j.mu.Unlock()
	return strings.Join(j.tail, "\n")
}

// write sends text to a login's terminal, with Enter, and returns how many lines the job had
// printed before it. The text becomes a secret first, so its echo is cut.
func (j *job) write(text string) (int, error) {
	j.mu.Lock()
	w, n := j.input, j.lines
	j.quiet = time.Now().Add(1500 * time.Millisecond)
	j.mu.Unlock()
	if w == nil {
		return n, errors.New("this job takes no input")
	}
	j.red.add(text)
	_, err := io.WriteString(w, text+"\r")
	return n, err
}

// env is the environment of every command quired runs for setup: its own, with HOME and a PATH
// that includes the makers' folders.
func (s *Service) env(extra []string) []string {
	var env []string
	for _, e := range os.Environ() {
		if strings.HasPrefix(e, "HOME=") || strings.HasPrefix(e, "PATH=") {
			continue
		}
		env = append(env, e)
	}
	env = append(env, "HOME="+s.Home, "PATH="+agents.PathWithMakerDirs(os.Getenv("PATH"), s.Home))
	return append(env, extra...)
}

// command builds c for bin, in its own process group, in HOME.
func (s *Service) command(c agents.Command, bin string) (*exec.Cmd, error) {
	var cmd *exec.Cmd
	switch {
	case c.Shell != "":
		cmd = exec.Command("bash", "-o", "pipefail", "-c", c.Shell)
	case len(c.Argv) > 0:
		argv := c.Resolve(bin, s.Home)
		if c.NeedsBin() && bin == "" {
			return nil, errors.New("the agent isn't installed")
		}
		cmd = exec.Command(argv[0], argv[1:]...)
	default:
		return nil, errors.New("empty command")
	}
	cmd.Dir = s.Home
	cmd.Env = s.env(c.Env)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	// An installer may leave a helper running that keeps the output open; the command is done
	// when its own process is.
	cmd.WaitDelay = 5 * time.Second
	return cmd, nil
}

// stopGroup ends a process group: SIGTERM, then SIGKILL after grace. It returns once waited
// is closed.
func stopGroup(pid int, waited <-chan struct{}, grace time.Duration) {
	_ = syscall.Kill(-pid, syscall.SIGTERM)
	select {
	case <-waited:
	case <-time.After(grace):
		_ = syscall.Kill(-pid, syscall.SIGKILL)
		<-waited
	}
}

// lines splits a stream into lines on \n and \r, as terminals and progress bars write them.
// A partial line is flushed after idle, so a prompt with no newline ("Paste code here > ")
// reaches the person, unless the job is quiet (an echo may still be arriving).
type lines struct {
	j     *job
	emit  func(raw string)
	idle  time.Duration
	mu    sync.Mutex
	buf   []byte
	timer *time.Timer
}

func (l *lines) Write(p []byte) (int, error) {
	l.mu.Lock()
	defer l.mu.Unlock()
	l.buf = append(l.buf, p...)
	for {
		i := bytes.IndexAny(l.buf, "\r\n")
		if i < 0 {
			break
		}
		line := string(l.buf[:i])
		l.buf = l.buf[i+1:]
		if line != "" {
			l.emit(line)
		}
	}
	if len(l.buf) > 0 && l.idle > 0 {
		if l.timer == nil {
			l.timer = time.AfterFunc(l.idle, l.flushIdle)
		} else {
			l.timer.Reset(l.idle)
		}
	}
	return len(p), nil
}

func (l *lines) flushIdle() {
	l.mu.Lock()
	defer l.mu.Unlock()
	if len(l.buf) == 0 {
		return
	}
	if l.j != nil {
		l.j.mu.Lock()
		wait := time.Until(l.j.quiet)
		l.j.mu.Unlock()
		if wait > 0 {
			l.timer.Reset(wait)
			return
		}
	}
	line := string(l.buf)
	l.buf = nil
	l.emit(line)
}

func (l *lines) close() {
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.timer != nil {
		l.timer.Stop()
	}
	if len(l.buf) > 0 {
		line := string(l.buf)
		l.buf = nil
		l.emit(line)
	}
}

// run runs c to the end, or until ctx ends, and passes each output line, cleaned and redacted,
// to out. With pty, the command gets a terminal and j's input is written to it.
func (s *Service) run(ctx context.Context, j *job, c agents.Command, bin string, pty bool, out func(line string, links []string)) error {
	cmd, err := s.command(c, bin)
	if err != nil {
		return err
	}
	j.log.printf("$ %s", c.Shown(bin, s.Home))
	emit := func(raw string) {
		text, links := clean(raw)
		text = j.red.line(text)
		for i := range links {
			links[i] = j.red.line(links[i])
		}
		if text == "" && len(links) == 0 {
			return
		}
		j.keep(text)
		j.log.printf("%s", text)
		out(text, links)
	}
	lw := &lines{j: j, emit: emit}
	var master *os.File
	if pty {
		m, sl, err := openPTY(160, 40)
		if err != nil {
			return fmt.Errorf("no terminal for the login: %w", err)
		}
		master = m
		cmd.Stdin, cmd.Stdout, cmd.Stderr = sl, sl, sl
		cmd.Env = append(cmd.Env, "TERM=xterm-256color", "COLUMNS=160", "LINES=40")
		cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true, Setctty: true, Ctty: 0}
		lw.idle = 300 * time.Millisecond
		if err := cmd.Start(); err != nil {
			sl.Close()
			m.Close()
			return err
		}
		sl.Close()
		j.mu.Lock()
		j.input = m
		j.mu.Unlock()
	} else {
		cmd.Env = append(cmd.Env, "TERM=dumb", "NO_COLOR=1", "CI=1")
		cmd.Stdout, cmd.Stderr = lw, lw
		if err := cmd.Start(); err != nil {
			return err
		}
	}
	waited := make(chan struct{})
	var werr error
	copied := make(chan struct{})
	if master != nil {
		go func() { _, _ = io.Copy(lw, master); close(copied) }()
	} else {
		close(copied)
	}
	go func() { werr = cmd.Wait(); close(waited) }()
	select {
	case <-waited:
	case <-ctx.Done():
		stopGroup(cmd.Process.Pid, waited, s.killGrace())
	}
	if master != nil {
		// The terminal's reader ends once every process holding the other side has gone; a
		// child that kept it open is in the same session, which was just stopped.
		select {
		case <-copied:
		case <-time.After(2 * time.Second):
			master.Close()
			<-copied
		}
		j.mu.Lock()
		j.input = nil
		j.mu.Unlock()
		master.Close()
	}
	lw.close()
	j.mu.Lock()
	j.ended = true
	j.mu.Unlock()
	if ctx.Err() != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return errors.New("it took too long and was stopped")
		}
		return ErrCancelled
	}
	return werr
}

// capture runs c with no terminal and returns its output, cleaned and redacted, for status checks.
func (s *Service) capture(ctx context.Context, c agents.Command, bin string, timeout time.Duration) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	j := &job{red: &redactor{}, log: nil}
	var b strings.Builder
	err := s.run(ctx, j, c, bin, false, func(line string, _ []string) { b.WriteString(line); b.WriteByte('\n') })
	return b.String(), err
}

// jobLog is a job's log in the guest: ~/.local/state/quire/jobs/<agent>-<time>.log, redacted.
type jobLog struct {
	mu sync.Mutex
	f  *os.File
}

func (s *Service) openLog(agent, kind string) *jobLog {
	dir := filepath.Join(s.Home, ".local", "state", "quire", "jobs")
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil
	}
	name := fmt.Sprintf("%s-%s-%s.log", agent, kind, time.Now().UTC().Format("20060102T150405.000Z"))
	f, err := os.OpenFile(filepath.Join(dir, name), os.O_WRONLY|os.O_CREATE|os.O_EXCL|syscall.O_NOFOLLOW, 0o600)
	if err != nil {
		return nil
	}
	return &jobLog{f: f}
}

func (l *jobLog) printf(format string, args ...any) {
	if l == nil {
		return
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	fmt.Fprintf(l.f, "%s %s\n", time.Now().UTC().Format("15:04:05.000"), fmt.Sprintf(format, args...))
}

func (l *jobLog) close() {
	if l != nil {
		l.f.Close()
	}
}
