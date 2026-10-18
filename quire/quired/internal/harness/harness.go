// Package harness runs coding agents and presents every one of them as an ACP agent.
//
// Agents that speak ACP are started as they are (acpagent.go). Claude Code is adapted from its
// stream-json print mode (claude.go). Either way the caller sees the same Agent interface and
// receives ACP session updates and permission requests through its Client.
package harness

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
)

// Client is the person's side of a session: Quire's surface on the laptop, or quired's terminal.
type Client interface {
	// Update receives every session update, in order. It must return quickly.
	Update(sessionID string, update json.RawMessage)
	// RequestPermission asks whether a tool call may run. It may block until someone decides;
	// ctx ends if the turn is cancelled or the agent goes away.
	RequestPermission(ctx context.Context, req acp.RequestPermissionRequest) (acp.RequestPermissionResponse, error)
}

// Agent is a running agent process, seen through ACP.
type Agent interface {
	Info() acp.InitializeResponse
	NewSession(ctx context.Context, cwd string, mcp []acp.McpServer) (string, error)
	// Prompt runs one turn and returns its stop reason. Cancelling ctx cancels the turn, and
	// Prompt then returns acp.StopCancelled once the agent has stopped.
	Prompt(ctx context.Context, sessionID string, prompt []acp.ContentBlock) (string, error)
	Close() error
	// Diagnostics returns the tail of the agent's stderr, for error reports.
	Diagnostics() string
}

// Options configure Start.
type Options struct {
	Path       string             // the agent's binary; required
	Version    string             // as reported by discovery, for Info
	ClientInfo acp.Implementation // who quired says it is
	// FS lets the agent read and write text files through quired, confined to each session's cwd.
	FS bool
	// Self is quired's own executable, which adapters re-run for helpers such as the permission
	// bridge. Defaults to os.Executable().
	Self string
	Args []string // added to the agent's command line, after the catalog's own
	Env  []string // added to the agent's environment
}

// ErrUnsupported is returned for catalog agents quired has no adapter for yet.
var ErrUnsupported = errors.New("quired: no adapter for this agent yet")

// Start launches spec's agent and completes the ACP handshake.
func Start(ctx context.Context, spec agents.Spec, client Client, opts Options) (Agent, error) {
	if opts.Path == "" {
		return nil, errors.New("quired: Options.Path is required")
	}
	if opts.Self == "" {
		self, err := os.Executable()
		if err != nil {
			return nil, err
		}
		opts.Self = self
	}
	switch spec.Protocol {
	case agents.ACP:
		return startACP(ctx, spec, client, opts)
	case agents.ClaudeStream:
		return newClaude(spec, client, opts), nil
	default:
		return nil, fmt.Errorf("%w: %s (%s)", ErrUnsupported, spec.ID, spec.Protocol)
	}
}

// ring keeps the last n bytes written to it.
type ring struct {
	mu  sync.Mutex
	buf []byte
	n   int
}

func newRing(n int) *ring { return &ring{n: n} }

func (r *ring) Write(p []byte) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.buf = append(r.buf, p...)
	if over := len(r.buf) - r.n; over > 0 {
		r.buf = append(r.buf[:0], r.buf[over:]...)
	}
	return len(p), nil
}

func (r *ring) String() string {
	r.mu.Lock()
	defer r.mu.Unlock()
	return strings.TrimSpace(string(r.buf))
}

// command builds an agent process in its own process group, so that stopping it also stops
// whatever it started.
func command(path string, args []string, dir string, env []string) *exec.Cmd {
	cmd := exec.Command(path, args...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), env...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	return cmd
}

// stop asks a process group to finish, then kills it after grace.
func stop(cmd *exec.Cmd, waited <-chan struct{}, grace time.Duration) {
	if cmd.Process == nil {
		return
	}
	pgid := -cmd.Process.Pid
	_ = syscall.Kill(pgid, syscall.SIGTERM)
	select {
	case <-waited:
	case <-time.After(grace):
		_ = syscall.Kill(pgid, syscall.SIGKILL)
		<-waited
	}
}

// confine resolves path for a file operation and refuses anything outside root, following
// symlinks in the part of the path that exists.
func confine(root, path string) (string, error) {
	if !filepath.IsAbs(path) {
		return "", acp.Errorf(acp.CodeInvalidParams, "path must be absolute: %s", path)
	}
	realRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", err
	}
	real, err := resolveExisting(filepath.Clean(path))
	if err != nil {
		return "", err
	}
	rel, err := filepath.Rel(realRoot, real)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", acp.Errorf(acp.CodeInvalidParams, "outside the session's folder: %s", path)
	}
	return real, nil
}

// resolveExisting evaluates symlinks in the longest existing prefix of p and keeps the rest.
func resolveExisting(p string) (string, error) {
	var tail []string
	for cur := p; ; {
		if real, err := filepath.EvalSymlinks(cur); err == nil {
			return filepath.Join(append([]string{real}, tail...)...), nil
		} else if !errors.Is(err, os.ErrNotExist) {
			return "", err
		}
		parent := filepath.Dir(cur)
		if parent == cur {
			return p, nil
		}
		tail = append([]string{filepath.Base(cur)}, tail...)
		cur = parent
	}
}

func readText(root string, req acp.ReadTextFileRequest) (acp.ReadTextFileResponse, error) {
	p, err := confine(root, req.Path)
	if err != nil {
		return acp.ReadTextFileResponse{}, err
	}
	b, err := os.ReadFile(p)
	if errors.Is(err, os.ErrNotExist) {
		return acp.ReadTextFileResponse{}, acp.Errorf(acp.CodeResourceNotFound, "no such file: %s", req.Path)
	} else if err != nil {
		return acp.ReadTextFileResponse{}, err
	}
	text := string(b)
	if req.Line != nil || req.Limit != nil {
		lines := strings.SplitAfter(text, "\n")
		start := 0
		if req.Line != nil && *req.Line > 1 {
			start = min(*req.Line-1, len(lines))
		}
		end := len(lines)
		if req.Limit != nil && *req.Limit >= 0 {
			end = min(start+*req.Limit, len(lines))
		}
		text = strings.Join(lines[start:end], "")
	}
	return acp.ReadTextFileResponse{Content: text}, nil
}

func writeText(root string, req acp.WriteTextFileRequest) error {
	p, err := confine(root, req.Path)
	if err != nil {
		return err
	}
	mode := os.FileMode(0o644)
	if fi, err := os.Stat(p); err == nil {
		mode = fi.Mode().Perm()
	}
	if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
		return err
	}
	return os.WriteFile(p, []byte(req.Content), mode)
}
