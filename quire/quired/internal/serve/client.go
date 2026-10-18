package serve

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"sync"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/harness"
)

// CancelTimeout bounds how long a cancelled turn may take to end after session/cancel.
var CancelTimeout = 20 * time.Second

// Remote is a `quired serve` seen from its client. Quire core does the same in Kotlin; this one
// serves `quired run --connect` and the tests.
type Remote struct {
	rpc    *acp.Conn
	closer io.Closer
	info   acp.InitializeResponse

	mu      sync.Mutex
	clients map[string]harness.Client    // quired session id → who shows it
	early   map[string][]json.RawMessage // updates that came before session/new's reply
}

// Connect speaks ACP over r and w and initializes. closer (may be nil) is closed by Close.
func Connect(ctx context.Context, r io.Reader, w io.Writer, closer io.Closer, clientInfo acp.Implementation) (*Remote, error) {
	rm := &Remote{closer: closer, clients: map[string]harness.Client{}, early: map[string][]json.RawMessage{}}
	rm.rpc = acp.NewConn(r, w, acp.Handlers{Request: rm.handle, Notification: rm.notify}, nil)
	req := acp.InitializeRequest{ProtocolVersion: acp.ProtocolVersion, ClientInfo: &clientInfo}
	if err := rm.rpc.Call(ctx, acp.MethodInitialize, req, &rm.info); err != nil {
		rm.Close()
		return nil, err
	}
	if rm.info.ProtocolVersion != acp.ProtocolVersion {
		rm.Close()
		return nil, errors.New("quired serve chose an ACP version this client doesn't support")
	}
	return rm, nil
}

func (rm *Remote) Info() acp.InitializeResponse { return rm.info }
func (rm *Remote) Done() <-chan struct{}        { return rm.rpc.Done() }

// Close ends the connection; quired serve then stops every agent it started for it.
func (rm *Remote) Close() error {
	if rm.closer != nil {
		return rm.closer.Close()
	}
	return nil
}

// Agents lists the agents installed where quired serve runs.
func (rm *Remote) Agents(ctx context.Context) ([]Agent, error) {
	var res agentsResult
	if err := rm.rpc.Call(ctx, MethodAgents, struct{}{}, &res); err != nil {
		return nil, err
	}
	return res.Agents, nil
}

// Agent starts (or reuses) agent id on the serving side and returns it as a harness.Agent.
func (rm *Remote) Agent(ctx context.Context, id string, client harness.Client) (harness.Agent, error) {
	var info acp.InitializeResponse
	if err := rm.rpc.Call(ctx, MethodDescribe, agentParam{Agent: id}, &info); err != nil {
		return nil, err
	}
	return &remoteAgent{rm: rm, id: id, client: client, info: info}, nil
}

func (rm *Remote) notify(method string, params json.RawMessage) {
	if method != acp.MethodSessionUpdate {
		return
	}
	var n acp.SessionNotification
	if json.Unmarshal(params, &n) != nil {
		return
	}
	rm.mu.Lock()
	c := rm.clients[n.SessionID]
	if c == nil {
		if len(rm.early[n.SessionID]) < maxEarly {
			rm.early[n.SessionID] = append(rm.early[n.SessionID], n.Update)
		}
		rm.mu.Unlock()
		return
	}
	rm.mu.Unlock()
	c.Update(n.SessionID, n.Update)
}

func (rm *Remote) handle(ctx context.Context, method string, params json.RawMessage) (any, error) {
	if method != acp.MethodRequestPermission {
		return nil, acp.Errorf(acp.CodeMethodNotFound, "%s", method)
	}
	var req acp.RequestPermissionRequest
	if err := json.Unmarshal(params, &req); err != nil {
		return nil, invalid(err)
	}
	rm.mu.Lock()
	c := rm.clients[req.SessionID]
	rm.mu.Unlock()
	if c == nil {
		return refuse(req.Options), nil
	}
	return c.RequestPermission(ctx, req)
}

// register routes a session's updates to c, after any that arrived before session/new's reply.
// It runs on the caller's goroutine while the read loop may deliver more, so the early ones are
// handed over under the lock, in order, before the session becomes visible to notify.
func (rm *Remote) register(sid string, c harness.Client) {
	rm.mu.Lock()
	early := rm.early[sid]
	delete(rm.early, sid)
	for _, u := range early {
		c.Update(sid, u)
	}
	rm.clients[sid] = c
	rm.mu.Unlock()
}

type remoteAgent struct {
	rm     *Remote
	id     string
	client harness.Client
	info   acp.InitializeResponse
}

func (a *remoteAgent) Info() acp.InitializeResponse { return a.info }
func (a *remoteAgent) Diagnostics() string          { return "" }
func (a *remoteAgent) Close() error                 { return nil } // the connection owns the agent

func (a *remoteAgent) Authenticate(ctx context.Context, methodID string) error {
	return a.rm.rpc.Call(ctx, acp.MethodAuthenticate, acp.AuthenticateRequest{MethodID: methodID, Meta: withMeta(quireMeta{Agent: a.id})}, nil)
}

func (a *remoteAgent) NewSession(ctx context.Context, cwd string, mcp []acp.McpServer) (string, error) {
	if mcp == nil {
		mcp = []acp.McpServer{}
	}
	var res newSessionResult
	if err := a.rm.rpc.Call(ctx, acp.MethodSessionNew, acp.NewSessionRequest{Cwd: cwd, McpServers: mcp, Meta: withMeta(quireMeta{Agent: a.id})}, &res); err != nil {
		return "", err
	}
	a.rm.register(res.SessionID, a.client)
	return res.SessionID, nil
}

// SessionFolder returns the folder quired serve gave a session, from session/new's _meta.
func SessionFolder(meta json.RawMessage) string {
	var m map[string]quireMeta
	_ = json.Unmarshal(meta, &m)
	return m[MetaKey].Cwd
}

func (a *remoteAgent) Prompt(ctx context.Context, sid string, prompt []acp.ContentBlock) (string, error) {
	type result struct {
		stop string
		err  error
	}
	done := make(chan result, 1)
	go func() {
		var res acp.PromptResponse
		err := a.rm.rpc.Call(context.Background(), acp.MethodPrompt, acp.PromptRequest{SessionID: sid, Prompt: prompt}, &res)
		done <- result{res.StopReason, err}
	}()
	select {
	case r := <-done:
		return r.stop, r.err
	case <-ctx.Done():
	}
	cctx, cancel := context.WithTimeout(context.Background(), CancelTimeout)
	defer cancel()
	_ = a.rm.rpc.Notify(cctx, acp.MethodCancel, acp.CancelNotification{SessionID: sid})
	select {
	case r := <-done:
		if r.err != nil {
			return acp.StopCancelled, r.err
		}
		return acp.StopCancelled, nil
	case <-cctx.Done():
		return acp.StopCancelled, errors.New("quired serve did not end the turn after session/cancel")
	}
}
