package harness

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os/exec"
	"strings"
	"sync"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
)

// How long an agent gets to start and answer initialize, to stop after a cancel, and to exit
// once told to (stdin closed, then SIGTERM) before it is killed.
var (
	initTimeout   = 60 * time.Second
	cancelTimeout = 15 * time.Second
	exitGrace     = 3 * time.Second
)

type acpAgent struct {
	cmd    *exec.Cmd
	waited chan struct{} // closed once the process has been reaped
	conn   *acp.Conn
	stdin  io.Closer
	stderr *ring
	client Client
	opts   Options
	info   acp.InitializeResponse

	mu    sync.Mutex
	roots map[string]string          // session id → cwd, for fs confinement
	turns map[string]context.Context // session id → the running turn's context
}

func startACP(ctx context.Context, spec agents.Spec, client Client, opts Options) (Agent, error) {
	cmd := command(opts.Path, append(append([]string{}, spec.Args...), opts.Args...), "", opts.Env)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	a := &acpAgent{cmd: cmd, waited: make(chan struct{}), stdin: stdin, stderr: newRing(64 << 10), client: client, opts: opts, roots: map[string]string{}, turns: map[string]context.Context{}}
	cmd.Stderr = a.stderr
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("start %s: %w", opts.Path, err)
	}
	a.conn = acp.NewConn(stdout, stdin, acp.Handlers{Request: a.handle, Notification: a.notify},
		func(line []byte) { _, _ = a.stderr.Write(append(append([]byte("stdout: "), line...), '\n')) })
	// Wait closes stdout, so it may only run once everything on it has been read.
	go func() { <-a.conn.Done(); _ = cmd.Wait(); close(a.waited) }()

	ictx, cancel := context.WithTimeout(ctx, initTimeout)
	defer cancel()
	req := acp.InitializeRequest{
		ProtocolVersion:    acp.ProtocolVersion,
		ClientCapabilities: acp.ClientCapabilities{FS: acp.FileSystemCapability{ReadTextFile: opts.FS, WriteTextFile: opts.FS}},
		ClientInfo:         &opts.ClientInfo,
	}
	if err := a.conn.Call(ictx, acp.MethodInitialize, req, &a.info); err != nil {
		a.Close()
		return nil, a.wrap("initialize", err)
	}
	// ACP: the agent answers with the version it chose; a client that doesn't support it closes.
	if a.info.ProtocolVersion != acp.ProtocolVersion {
		a.Close()
		return nil, fmt.Errorf("initialize: %s chose ACP protocol version %d; quired supports %d", spec.ID, a.info.ProtocolVersion, acp.ProtocolVersion)
	}
	return a, nil
}

func (a *acpAgent) Info() acp.InitializeResponse { return a.info }
func (a *acpAgent) Diagnostics() string          { return a.stderr.String() }

func (a *acpAgent) Authenticate(ctx context.Context, methodID string) error {
	for _, m := range a.info.AuthMethods {
		if m.ID != methodID {
			continue
		}
		if m.Type == acp.AuthTerminal {
			return acp.Errorf(acp.CodeInvalidParams, "%s is signed in from a terminal, not through authenticate", methodID)
		}
		return a.wrap("authenticate", a.conn.Call(ctx, acp.MethodAuthenticate, acp.AuthenticateRequest{MethodID: methodID}, nil))
	}
	return acp.Errorf(acp.CodeInvalidParams, "the agent offers no sign-in method %q", methodID)
}

func (a *acpAgent) NewSession(ctx context.Context, cwd string, mcp []acp.McpServer) (string, error) {
	if mcp == nil {
		mcp = []acp.McpServer{}
	}
	var res acp.NewSessionResponse
	if err := a.conn.Call(ctx, acp.MethodSessionNew, acp.NewSessionRequest{Cwd: cwd, McpServers: mcp}, &res); err != nil {
		return "", a.wrap("session/new", err)
	}
	a.mu.Lock()
	a.roots[res.SessionID] = cwd
	a.mu.Unlock()
	return res.SessionID, nil
}

func (a *acpAgent) Prompt(ctx context.Context, sessionID string, prompt []acp.ContentBlock) (string, error) {
	a.mu.Lock()
	a.turns[sessionID] = ctx
	a.mu.Unlock()
	defer func() { a.mu.Lock(); delete(a.turns, sessionID); a.mu.Unlock() }()

	type result struct {
		stop string
		err  error
	}
	done := make(chan result, 1)
	go func() {
		var res acp.PromptResponse
		err := a.conn.Call(context.Background(), acp.MethodPrompt, acp.PromptRequest{SessionID: sessionID, Prompt: prompt}, &res)
		done <- result{res.StopReason, err}
	}()
	select {
	case r := <-done:
		return r.stop, a.wrap("session/prompt", r.err)
	case <-ctx.Done():
	}
	// ACP: the client sends session/cancel and the agent ends the turn with stopReason "cancelled".
	// One deadline covers both sending the cancel (the agent may have stopped reading) and the
	// agent stopping; past it the agent is stopped, so nothing it started keeps running unseen.
	cctx, ccancel := context.WithTimeout(context.Background(), cancelTimeout)
	defer ccancel()
	_ = a.conn.Notify(cctx, acp.MethodCancel, acp.CancelNotification{SessionID: sessionID})
	select {
	case r := <-done:
		if r.err != nil {
			return acp.StopCancelled, a.wrap("session/prompt", r.err)
		}
		return acp.StopCancelled, nil
	case <-cctx.Done():
		a.terminate()
		return acp.StopCancelled, fmt.Errorf("agent did not stop within %s of session/cancel, so quired stopped it", cancelTimeout)
	}
}

// Close ends the agent: ACP agents exit when stdin closes, and the process group is stopped
// if this one doesn't within a few seconds. Closing stdin also frees a write it was refusing to read.
func (a *acpAgent) Close() error {
	_ = a.stdin.Close()
	select {
	case <-a.waited:
	case <-time.After(exitGrace):
		stop(a.cmd, a.waited, exitGrace)
	}
	return nil
}

// terminate stops an agent that has already had its grace: SIGTERM to its process group at once,
// SIGKILL if that is ignored, and it returns only once the process has been reaped.
func (a *acpAgent) terminate() {
	_ = a.stdin.Close()
	stop(a.cmd, a.waited, exitGrace)
}

func (a *acpAgent) notify(method string, params json.RawMessage) {
	if method != acp.MethodSessionUpdate {
		return
	}
	var n acp.SessionNotification
	if json.Unmarshal(params, &n) == nil {
		a.client.Update(n.SessionID, n.Update)
	}
}

func (a *acpAgent) handle(ctx context.Context, method string, params json.RawMessage) (any, error) {
	switch method {
	case acp.MethodRequestPermission:
		var req acp.RequestPermissionRequest
		if err := json.Unmarshal(params, &req); err != nil {
			return nil, acp.Errorf(acp.CodeInvalidParams, "%v", err)
		}
		// ACP: once a turn is cancelled, its open permission requests are answered "cancelled".
		a.mu.Lock()
		turn := a.turns[req.SessionID]
		a.mu.Unlock()
		if turn != nil {
			var cancel context.CancelFunc
			ctx, cancel = context.WithCancel(ctx)
			defer cancel()
			defer context.AfterFunc(turn, cancel)()
		}
		res, err := a.client.RequestPermission(ctx, req)
		if ctx.Err() != nil {
			return acp.Cancelled(), nil
		}
		return res, err
	case acp.MethodReadTextFile:
		var req acp.ReadTextFileRequest
		if err := json.Unmarshal(params, &req); err != nil {
			return nil, acp.Errorf(acp.CodeInvalidParams, "%v", err)
		}
		root, err := a.root(req.SessionID)
		if err != nil {
			return nil, err
		}
		return readText(root, req)
	case acp.MethodWriteTextFile:
		var req acp.WriteTextFileRequest
		if err := json.Unmarshal(params, &req); err != nil {
			return nil, acp.Errorf(acp.CodeInvalidParams, "%v", err)
		}
		root, err := a.root(req.SessionID)
		if err != nil {
			return nil, err
		}
		return nil, writeText(root, req)
	}
	return nil, acp.Errorf(acp.CodeMethodNotFound, "quired does not offer %s", method)
}

func (a *acpAgent) root(sessionID string) (string, error) {
	if !a.opts.FS {
		return "", acp.Errorf(acp.CodeMethodNotFound, "file access through the client is off")
	}
	a.mu.Lock()
	defer a.mu.Unlock()
	root, ok := a.roots[sessionID]
	if !ok {
		return "", acp.Errorf(acp.CodeInvalidParams, "unknown session %s", sessionID)
	}
	return root, nil
}

// wrap adds the agent's last stderr lines to an error, since that is usually where the reason is.
func (a *acpAgent) wrap(what string, err error) error {
	if err == nil {
		return nil
	}
	if d := a.Diagnostics(); d != "" {
		return fmt.Errorf("%s: %w\nagent stderr (tail):\n%s", what, err, tail(d, 12))
	}
	return fmt.Errorf("%s: %w", what, err)
}

// tail returns the last n lines of s.
func tail(s string, n int) string {
	lines := strings.Split(s, "\n")
	if len(lines) > n {
		lines = lines[len(lines)-n:]
	}
	return strings.Join(lines, "\n")
}
