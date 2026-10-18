// Package serve is `quired serve`: one ACP connection from Quire core (the client) to every agent
// installed here.
//
// Towards Quire core, quired is a single ACP agent. The client picks the real agent for each
// session in session/new's _meta ({"quire": {"agent": "opencode"}}) and lists or describes the
// agents with two extension methods, as ACP's extensibility rules allow:
//
//	_quire/agents    {}                  → {"agents": [Agent...]}
//	_quire/describe  {"agent": "kimi"}   → the agent's own initialize response (authMethods...)
//
// authenticate carries the agent the same way. session/prompt, session/cancel, session/update and
// session/request_permission are relayed with quired's session ids. File reads and writes stay
// here, confined to the session's folder (package harness), because the files live here.
//
// What serve refuses, on top of package harness: session folders outside Root, and MCP servers
// supplied by the client (a stdio MCP server is a command line quired would run; Quire's OS tools
// get their own shim in Q6). A permission request the client can't answer is refused.
package serve

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/harness"
)

// Extension methods and the _meta key quired serve uses.
const (
	MethodAgents   = "_quire/agents"
	MethodDescribe = "_quire/describe"
	MetaKey        = "quire"
)

// Server answers Quire core's connections.
type Server struct {
	Version    string
	ClientInfo acp.Implementation // what quired tells the agents it starts
	// Root holds every session's folder. A session/new without cwd gets a new folder under
	// Root/Quire; one with cwd must name a folder inside Root.
	Root     string
	FS       bool // serve fs/read_text_file and fs/write_text_file to ACP agents
	Discover func(context.Context) []agents.Found
	Start    func(context.Context, agents.Spec, harness.Client, harness.Options) (harness.Agent, error)
	Log      *log.Logger
}

// Agent is one row of _quire/agents.
type Agent struct {
	ID        string                  `json:"id"`
	Name      string                  `json:"name"`
	Version   string                  `json:"version,omitempty"`
	Protocol  string                  `json:"protocol"`
	Supported bool                    `json:"supported"`
	Note      string                  `json:"note,omitempty"`
	Running   bool                    `json:"running"`
	Info      *acp.InitializeResponse `json:"initialize,omitempty"` // once started on this connection
}

type agentsResult struct {
	Agents []Agent `json:"agents"`
}

type quireMeta struct {
	Agent string `json:"agent,omitempty"`
	Cwd   string `json:"cwd,omitempty"`
}

type agentParam struct {
	Agent string          `json:"agent"`
	Meta  json.RawMessage `json:"_meta,omitempty"`
}

// metaAgent reads {"quire": {"agent": ...}} from a _meta object.
func metaAgent(meta json.RawMessage) string {
	var m map[string]json.RawMessage
	if len(meta) == 0 || json.Unmarshal(meta, &m) != nil {
		return ""
	}
	var q quireMeta
	_ = json.Unmarshal(m[MetaKey], &q)
	return q.Agent
}

func withMeta(q quireMeta) json.RawMessage {
	b, _ := json.Marshal(map[string]quireMeta{MetaKey: q})
	return b
}

// session/new's response, with quired's _meta (the agent and the folder).
type newSessionResult struct {
	SessionID string          `json:"sessionId"`
	Meta      json.RawMessage `json:"_meta,omitempty"`
}

// Serve runs one client connection until it closes or ctx ends. It returns once every agent the
// connection started has been stopped.
func (s *Server) Serve(ctx context.Context, peer string, r io.Reader, w io.Writer) error {
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()
	c := &conn{s: s, peer: peer, ctx: ctx, agents: map[string]*running{}, sessions: map[string]*session{}, ready: make(chan struct{})}
	c.rpc = acp.NewConn(r, w, acp.Handlers{Request: c.handle, Notification: c.notify}, nil)
	close(c.ready)
	s.logf("%s: connected", peer)
	select {
	case <-c.rpc.Done():
	case <-ctx.Done():
	}
	cancel()
	c.shutdown()
	err := c.rpc.Err()
	s.logf("%s: closed (%d sessions)", peer, c.count())
	return err
}

func (s *Server) logf(format string, args ...any) {
	if s.Log != nil {
		s.Log.Printf(format, args...)
	}
}

type conn struct {
	s     *Server
	peer  string
	ctx   context.Context
	rpc   *acp.Conn
	ready chan struct{} // closed once rpc is set; the handlers may run before that

	sendMu sync.Mutex // keeps session/update notifications in order across register and relay

	mu          sync.Mutex
	initialized bool
	closed      bool // set by shutdown: no agent may start after it
	next        int
	agents      map[string]*running
	sessions    map[string]*session
}

type running struct {
	id     string
	ready  chan struct{} // closed once start has finished
	agent  harness.Agent // nil if start failed
	err    error
	client *agentClient
}

type session struct {
	id       string // quired's id, the one the client sees
	agentID  string
	agentSID string
	cwd      string

	mu   sync.Mutex
	turn context.CancelFunc // the running turn's cancel, or nil
}

// out is the connection to the client, for the handlers and the agents' relays.
func (c *conn) out() *acp.Conn { <-c.ready; return c.rpc }

func (c *conn) count() int {
	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.sessions)
}

func (c *conn) shutdown() {
	c.mu.Lock()
	c.closed = true
	var rs []*running
	for _, r := range c.agents {
		rs = append(rs, r)
	}
	for _, se := range c.sessions {
		se.mu.Lock()
		if se.turn != nil {
			se.turn()
		}
		se.mu.Unlock()
	}
	c.mu.Unlock()
	var wg sync.WaitGroup
	for _, r := range rs {
		wg.Add(1)
		go func() {
			defer wg.Done()
			<-r.ready
			if r.agent != nil {
				_ = r.agent.Close()
			}
		}()
	}
	wg.Wait()
}

func (c *conn) notify(method string, params json.RawMessage) {
	if method != acp.MethodCancel {
		return // ACP: unknown notifications are ignored
	}
	var n acp.CancelNotification
	if json.Unmarshal(params, &n) != nil {
		return
	}
	c.mu.Lock()
	se := c.sessions[n.SessionID]
	c.mu.Unlock()
	if se == nil {
		return
	}
	se.mu.Lock()
	if se.turn != nil {
		se.turn()
	}
	se.mu.Unlock()
}

func invalid(err error) error { return acp.Errorf(acp.CodeInvalidParams, "%v", err) }

func (c *conn) handle(ctx context.Context, method string, params json.RawMessage) (any, error) {
	if method == acp.MethodInitialize {
		var req acp.InitializeRequest
		if err := json.Unmarshal(params, &req); err != nil {
			return nil, invalid(err)
		}
		c.mu.Lock()
		c.initialized = true
		c.mu.Unlock()
		return c.initializeResult(), nil
	}
	c.mu.Lock()
	ok := c.initialized
	c.mu.Unlock()
	if !ok {
		return nil, acp.Errorf(acp.CodeInvalidRequest, "initialize first")
	}
	switch method {
	case MethodAgents:
		return c.listAgents(ctx), nil
	case MethodDescribe:
		var p agentParam
		if err := json.Unmarshal(params, &p); err != nil {
			return nil, invalid(err)
		}
		r, err := c.agent(ctx, p.Agent)
		if err != nil {
			return nil, err
		}
		info := r.agent.Info()
		return info, nil
	case acp.MethodAuthenticate:
		var req acp.AuthenticateRequest
		if err := json.Unmarshal(params, &req); err != nil {
			return nil, invalid(err)
		}
		id := metaAgent(req.Meta)
		r, err := c.agent(ctx, id)
		if err != nil {
			return nil, err
		}
		if err := r.agent.Authenticate(ctx, req.MethodID); err != nil {
			c.s.logf("%s: authenticate %s %s: %s", c.peer, id, req.MethodID, firstLine(err.Error()))
			return nil, err
		}
		c.s.logf("%s: authenticate %s %s: ok", c.peer, id, req.MethodID)
		return struct{}{}, nil
	case acp.MethodSessionNew:
		var req acp.NewSessionRequest
		if err := json.Unmarshal(params, &req); err != nil {
			return nil, invalid(err)
		}
		return c.newSession(ctx, req)
	case acp.MethodPrompt:
		var req acp.PromptRequest
		if err := json.Unmarshal(params, &req); err != nil {
			return nil, invalid(err)
		}
		return c.prompt(req)
	}
	return nil, acp.Errorf(acp.CodeMethodNotFound, "quired serve does not offer %s", method)
}

func (c *conn) initializeResult() acp.InitializeResponse {
	meta, _ := json.Marshal(map[string]any{MetaKey: map[string]any{
		"router":  true,
		"methods": []string{MethodAgents, MethodDescribe},
	}})
	return acp.InitializeResponse{
		ProtocolVersion: acp.ProtocolVersion,
		// Prompt capabilities are each agent's own (_quire/describe); none are promised here.
		AgentCapabilities: acp.AgentCapabilities{Meta: meta},
		AuthMethods:       []acp.AuthMethod{},
		AgentInfo:         &acp.Implementation{Name: "quired", Title: "Quire harness host (OpenBook)", Version: c.s.Version},
	}
}

func (c *conn) listAgents(ctx context.Context) agentsResult {
	found := c.s.Discover(ctx)
	out := agentsResult{Agents: []Agent{}}
	for _, f := range found {
		a := Agent{ID: f.ID, Name: f.Name, Version: f.Version, Protocol: string(f.Protocol), Supported: f.Supported, Note: f.Note}
		c.mu.Lock()
		r := c.agents[f.ID]
		c.mu.Unlock()
		if r != nil {
			select {
			case <-r.ready:
				if r.agent != nil {
					info := r.agent.Info()
					a.Running, a.Info = true, &info
				}
			default:
			}
		}
		out.Agents = append(out.Agents, a)
	}
	return out
}

// agent returns the running agent id, starting it if this connection hasn't yet.
func (c *conn) agent(ctx context.Context, id string) (*running, error) {
	if id == "" {
		return nil, acp.Errorf(acp.CodeInvalidParams, `name the agent in _meta: {"%s": {"agent": "..."}}`, MetaKey)
	}
	c.mu.Lock()
	if c.closed {
		c.mu.Unlock()
		return nil, acp.ErrClosed
	}
	r := c.agents[id]
	if r == nil {
		r = &running{id: id, ready: make(chan struct{}), client: &agentClient{c: c, agent: id, pending: map[string][]json.RawMessage{}}}
		c.agents[id] = r
		c.mu.Unlock()
		r.agent, r.err = c.start(id, r.client)
		c.mu.Lock()
		if r.err == nil && c.closed {
			// The connection ended while the agent started; shutdown may not have seen it.
			r.err = acp.ErrClosed
			go r.agent.Close()
			r.agent = nil
		}
		if r.err != nil {
			delete(c.agents, id) // a later call may try again (after a sign-in, an install...)
		}
		c.mu.Unlock()
		close(r.ready)
	} else {
		c.mu.Unlock()
		select {
		case <-r.ready:
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
	if r.err != nil {
		return nil, r.err
	}
	return r, nil
}

func (c *conn) start(id string, client harness.Client) (harness.Agent, error) {
	var f *agents.Found
	for _, x := range c.s.Discover(c.ctx) {
		if x.ID == id {
			f = &x
			break
		}
	}
	if f == nil {
		return nil, acp.Errorf(acp.CodeInvalidParams, "%s is not installed here (see _quire/agents)", id)
	}
	if !f.Supported {
		return nil, acp.Errorf(acp.CodeInvalidParams, "quired has no adapter for %s yet: %s", id, f.Note)
	}
	t0 := time.Now()
	a, err := c.s.Start(c.ctx, f.Spec, client, harness.Options{Path: f.Path, Version: f.Version, ClientInfo: c.s.ClientInfo, FS: c.s.FS})
	if err != nil {
		c.s.logf("%s: start %s: %s", c.peer, id, firstLine(err.Error()))
		return nil, err
	}
	c.s.logf("%s: started %s %s in %d ms", c.peer, id, f.Version, time.Since(t0).Milliseconds())
	return a, nil
}

// dropIfDead forgets an agent whose process has gone, so the next call starts it again.
func (c *conn) dropIfDead(r *running, err error) {
	if errors.Is(err, acp.ErrClosed) {
		c.mu.Lock()
		if c.agents[r.id] == r {
			delete(c.agents, r.id)
		}
		c.mu.Unlock()
	}
}

func (c *conn) sessionDir(cwd string) (string, error) {
	root, err := filepath.Abs(c.s.Root)
	if err != nil {
		return "", err
	}
	if cwd == "" {
		base := filepath.Join(root, "Quire")
		if err := os.MkdirAll(base, 0o700); err != nil {
			return "", err
		}
		return os.MkdirTemp(base, time.Now().Format("2006-01-02")+"-")
	}
	if !filepath.IsAbs(cwd) {
		return "", acp.Errorf(acp.CodeInvalidParams, "cwd must be absolute: %s", cwd)
	}
	// Compare real paths, so a symlink inside Root can't name a folder outside it.
	realRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return "", err
	}
	real, err := filepath.EvalSymlinks(cwd)
	if err != nil {
		return "", acp.Errorf(acp.CodeInvalidParams, "no such folder: %s", cwd)
	}
	if rel, err := filepath.Rel(realRoot, real); err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", acp.Errorf(acp.CodeInvalidParams, "cwd is outside %s: %s", root, cwd)
	}
	if fi, err := os.Stat(real); err != nil || !fi.IsDir() {
		return "", acp.Errorf(acp.CodeInvalidParams, "not a folder: %s", cwd)
	}
	return cwd, nil
}

// authRequired is the data of an auth_required error from session/new: which agent, and how it
// can be signed in.
type authRequired struct {
	Agent       string           `json:"agent"`
	AuthMethods []acp.AuthMethod `json:"authMethods"`
}

func (c *conn) newSession(ctx context.Context, req acp.NewSessionRequest) (any, error) {
	if len(req.McpServers) > 0 {
		return nil, acp.Errorf(acp.CodeInvalidParams, "quired serve does not run MCP servers named by the client")
	}
	id := metaAgent(req.Meta)
	dir, err := c.sessionDir(req.Cwd)
	if err != nil {
		return nil, err
	}
	made := req.Cwd == "" // a folder serve made for this session, removed again if it stays empty
	r, err := c.agent(ctx, id)
	if err != nil {
		if made {
			_ = os.Remove(dir)
		}
		return nil, err
	}
	asid, err := r.agent.NewSession(ctx, dir, nil)
	if err != nil {
		if made {
			_ = os.Remove(dir)
		}
		c.dropIfDead(r, err)
		c.s.logf("%s: session/new %s: %s", c.peer, id, firstLine(err.Error()))
		var re *acp.RPCError
		if errors.As(err, &re) && re.Code == acp.CodeAuthRequired {
			data, _ := json.Marshal(authRequired{Agent: id, AuthMethods: r.agent.Info().AuthMethods})
			return nil, &acp.RPCError{Code: acp.CodeAuthRequired, Message: re.Message, Data: data}
		}
		return nil, err
	}
	c.mu.Lock()
	c.next++
	se := &session{id: fmt.Sprintf("%s-%d", id, c.next), agentID: id, agentSID: asid, cwd: dir}
	c.sessions[se.id] = se
	c.mu.Unlock()
	r.client.register(asid, se.id)
	c.s.logf("%s: session %s (%s) in %s", c.peer, se.id, id, dir)
	return newSessionResult{SessionID: se.id, Meta: withMeta(quireMeta{Agent: id, Cwd: dir})}, nil
}

func (c *conn) prompt(req acp.PromptRequest) (any, error) {
	c.mu.Lock()
	se := c.sessions[req.SessionID]
	var r *running
	if se != nil {
		r = c.agents[se.agentID]
	}
	c.mu.Unlock()
	if se == nil {
		return nil, acp.Errorf(acp.CodeInvalidParams, "unknown session %s", req.SessionID)
	}
	if r == nil || r.agent == nil {
		return nil, acp.Errorf(acp.CodeInternalError, "%s has stopped; start a new session", se.agentID)
	}
	tctx, cancel := context.WithCancel(c.ctx)
	defer cancel()
	se.mu.Lock()
	if se.turn != nil {
		se.mu.Unlock()
		return nil, acp.Errorf(acp.CodeInvalidRequest, "a turn is already running in %s", se.id)
	}
	se.turn = cancel
	se.mu.Unlock()
	defer func() { se.mu.Lock(); se.turn = nil; se.mu.Unlock() }()

	t0 := time.Now()
	stop, err := r.agent.Prompt(tctx, se.agentSID, req.Prompt)
	if err != nil {
		c.dropIfDead(r, err)
		c.s.logf("%s: prompt %s: %s after %d ms: %s", c.peer, se.id, stop, time.Since(t0).Milliseconds(), firstLine(err.Error()))
		if stop == acp.StopCancelled {
			return acp.PromptResponse{StopReason: stop}, nil
		}
		return nil, err
	}
	c.s.logf("%s: prompt %s: %s in %d ms", c.peer, se.id, stop, time.Since(t0).Milliseconds())
	return acp.PromptResponse{StopReason: stop}, nil
}

// agentClient is the harness.Client for one agent: it relays the agent's updates and permission
// requests to Quire core under quired's session ids.
type agentClient struct {
	c     *conn
	agent string

	mu      sync.Mutex
	ids     map[string]string            // agent's session id → quired's
	pending map[string][]json.RawMessage // updates that arrived before session/new returned
}

const maxEarly = 256

func (a *agentClient) register(agentSID, id string) {
	a.c.sendMu.Lock()
	defer a.c.sendMu.Unlock()
	a.mu.Lock()
	if a.ids == nil {
		a.ids = map[string]string{}
	}
	a.ids[agentSID] = id
	early := a.pending[agentSID]
	delete(a.pending, agentSID)
	a.mu.Unlock()
	for _, u := range early {
		_ = a.c.out().Notify(a.c.ctx, acp.MethodSessionUpdate, acp.SessionNotification{SessionID: id, Update: u})
	}
}

func (a *agentClient) Update(agentSID string, update json.RawMessage) {
	a.c.sendMu.Lock()
	defer a.c.sendMu.Unlock()
	a.mu.Lock()
	id, ok := a.ids[agentSID]
	if !ok {
		// Agents may announce a session (available commands, modes) before session/new's reply
		// has been handled here. Keep a bounded number for register.
		if len(a.pending[agentSID]) < maxEarly {
			a.pending[agentSID] = append(a.pending[agentSID], append(json.RawMessage(nil), update...))
		}
		a.mu.Unlock()
		return
	}
	a.mu.Unlock()
	_ = a.c.out().Notify(a.c.ctx, acp.MethodSessionUpdate, acp.SessionNotification{SessionID: id, Update: update})
}

// RequestPermission asks Quire core. If it can't answer (gone, or an answer that isn't one of
// the options), the request is refused.
func (a *agentClient) RequestPermission(ctx context.Context, req acp.RequestPermissionRequest) (acp.RequestPermissionResponse, error) {
	a.mu.Lock()
	id, ok := a.ids[req.SessionID]
	a.mu.Unlock()
	if !ok {
		return refuse(req.Options), nil
	}
	req.SessionID = id
	var res acp.RequestPermissionResponse
	if err := a.c.out().Call(ctx, acp.MethodRequestPermission, req, &res); err != nil {
		if ctx.Err() != nil {
			return acp.Cancelled(), nil
		}
		a.c.s.logf("%s: permission in %s: refused, client did not answer: %s", a.c.peer, id, firstLine(err.Error()))
		return refuse(req.Options), nil
	}
	switch res.Outcome.Outcome {
	case acp.OutcomeCancelled:
		return res, nil
	case acp.OutcomeSelected:
		for _, o := range req.Options {
			if o.OptionID == res.Outcome.OptionID {
				return res, nil
			}
		}
	}
	a.c.s.logf("%s: permission in %s: refused, not one of the options", a.c.peer, id)
	return refuse(req.Options), nil
}

// refuse picks the agent's own "reject once" (or "reject always") option, else cancels.
func refuse(opts []acp.PermissionOption) acp.RequestPermissionResponse {
	for _, k := range []string{acp.RejectOnce, acp.RejectAlways} {
		for _, o := range opts {
			if o.Kind == k {
				return acp.Selected(o.OptionID)
			}
		}
	}
	return acp.Cancelled()
}

func firstLine(s string) string { l, _, _ := strings.Cut(s, "\n"); return l }
