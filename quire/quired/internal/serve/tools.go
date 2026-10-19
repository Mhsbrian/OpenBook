package serve

// Quire's OS tools in the Linux environment (Q6, docs/quire.md §4.2).
//
// Quire core serves OpenBook's tools (apps, the web, the screen, settings, files, windows, computer
// control) and decides every call itself: it runs what is safe, asks the person in the note before
// anything destructive, and refuses the never tier. The agents run here, in the guest, and reach
// tools over MCP. So when Quire core asks for its tools in session/new (_meta.quire.tools), quired
// adds one stdio MCP server to the session, `quired tools-mcp`, and relays what that server is
// asked to Quire core over the ACP connection it already has, with two extension methods in the
// agent-to-client direction:
//
//	_quire/tools/list  {sessionId}                    → {tools: [...], instructions: "..."}
//	_quire/tools/call  {sessionId, name, arguments}   → an MCP CallToolResult
//
// No new channel to Android is opened. Between the MCP server and quired there is a private unix
// socket per session (0600 in a 0700 folder), as for Claude Code's permission bridge.
//
// A call is relayed only while a turn runs in its session, and it is cancelled with the turn: tools
// act for the person's request, never on their own. Listing is allowed at any time, since agents
// list a server's tools when they start it.

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/harness"
)

// Extension methods quired calls on Quire core for its tools.
const (
	MethodToolsList = "_quire/tools/list"
	MethodToolsCall = "_quire/tools/call"
)

// listTimeout bounds a tools/list relay. A call has no fixed bound: the person may take their time
// on a confirmation; it ends with the turn.
var listTimeout = 20 * time.Second

// toolRequest is one question from `quired tools-mcp` to quired, a line of JSON on the bridge.
type toolRequest struct {
	Method string          `json:"method"` // "tools/list" or "tools/call"
	Params json.RawMessage `json:"params,omitempty"`
}

type toolResponse struct {
	Result json.RawMessage `json:"result,omitempty"`
	Error  *acp.RPCError   `json:"error,omitempty"`
}

type toolsListParams struct {
	SessionID string `json:"sessionId"`
}

type toolsCallParams struct {
	SessionID string          `json:"sessionId"`
	Name      string          `json:"name"`
	Arguments json.RawMessage `json:"arguments,omitempty"`
}

// toolBridge is one session's socket. close stops it and waits for its connections.
type toolBridge struct {
	dir    string
	socket string
	l      net.Listener
	cancel context.CancelFunc
	wg     sync.WaitGroup
	once   sync.Once
}

// openTools listens for se's tools-mcp server and returns the MCP server entry for session/new.
func (c *conn) openTools(se *session) (*toolBridge, acp.McpServer, error) {
	dir, err := os.MkdirTemp("", "quired-tools-")
	if err != nil {
		return nil, acp.McpServer{}, err
	}
	socket := filepath.Join(dir, "s")
	old := syscall.Umask(0o177)
	l, err := net.Listen("unix", socket)
	syscall.Umask(old)
	if err != nil {
		os.RemoveAll(dir)
		return nil, acp.McpServer{}, err
	}
	ctx, cancel := context.WithCancel(c.ctx)
	b := &toolBridge{dir: dir, socket: socket, l: l, cancel: cancel}
	b.wg.Add(1)
	go func() {
		defer b.wg.Done()
		for {
			nc, err := l.Accept()
			if err != nil {
				return
			}
			b.wg.Add(1)
			go func() {
				defer b.wg.Done()
				defer nc.Close()
				defer context.AfterFunc(ctx, func() { nc.Close() })()
				c.answerTool(ctx, se, nc)
			}()
		}
	}()
	self := c.s.Self
	if self == "" {
		if self, err = os.Executable(); err != nil {
			b.close()
			return nil, acp.McpServer{}, err
		}
	}
	return b, acp.McpServer{Name: harness.ToolServer, Command: self, Args: []string{"tools-mcp", "--socket", socket}, Env: []acp.EnvVariable{}}, nil
}

func (b *toolBridge) close() {
	b.once.Do(func() {
		b.cancel()
		b.l.Close()
		b.wg.Wait()
		os.RemoveAll(b.dir)
	})
}

// answerTool reads one request from the tools-mcp server and relays it.
func (c *conn) answerTool(ctx context.Context, se *session, nc net.Conn) {
	var req toolRequest
	if err := json.NewDecoder(bufio.NewReader(nc)).Decode(&req); err != nil {
		return
	}
	res, err := c.relayTool(ctx, se, req)
	out := toolResponse{Result: res}
	if err != nil {
		var re *acp.RPCError
		if !errors.As(err, &re) {
			re = acp.Errorf(acp.CodeInternalError, "%v", err)
		}
		out = toolResponse{Error: re}
	}
	_ = json.NewEncoder(nc).Encode(out)
}

func (c *conn) relayTool(ctx context.Context, se *session, req toolRequest) (json.RawMessage, error) {
	var res json.RawMessage
	switch req.Method {
	case "tools/list":
		lctx, cancel := context.WithTimeout(ctx, listTimeout)
		defer cancel()
		if err := c.out().Call(lctx, MethodToolsList, toolsListParams{SessionID: se.id}, &res); err != nil {
			return nil, err
		}
		return res, nil
	case "tools/call":
		var p struct {
			Name      string          `json:"name"`
			Arguments json.RawMessage `json:"arguments,omitempty"`
		}
		if err := json.Unmarshal(req.Params, &p); err != nil || p.Name == "" {
			return nil, acp.Errorf(acp.CodeInvalidParams, "tools/call needs a tool name")
		}
		// Only for the person's running request, and only as long as it runs.
		se.mu.Lock()
		turn := se.turnCtx
		se.mu.Unlock()
		if turn == nil {
			c.s.logf("%s: tool %s in %s: refused, no turn running", c.peer, p.Name, se.id)
			return nil, acp.Errorf(acp.CodeInvalidRequest, "OpenBook's tools work only while the person's request is running")
		}
		cctx, cancel := context.WithCancel(ctx)
		defer cancel()
		defer context.AfterFunc(turn, cancel)()
		t0 := time.Now()
		err := c.out().Call(cctx, MethodToolsCall, toolsCallParams{SessionID: se.id, Name: p.Name, Arguments: p.Arguments}, &res)
		// Names and timings only: arguments and results can hold the person's data.
		if err != nil {
			c.s.logf("%s: tool %s in %s: %s after %d ms", c.peer, p.Name, se.id, firstLine(err.Error()), time.Since(t0).Milliseconds())
			if turn.Err() != nil {
				return nil, acp.Errorf(acp.CodeInvalidRequest, "the person's request ended, so the tool call was cancelled")
			}
			return nil, err
		}
		c.s.logf("%s: tool %s in %s: answered in %d ms", c.peer, p.Name, se.id, time.Since(t0).Milliseconds())
		return res, nil
	}
	return nil, acp.Errorf(acp.CodeMethodNotFound, "the tools bridge has no %s", req.Method)
}

// askTools sends one request to quired over the bridge socket and returns its result.
func askTools(ctx context.Context, socket string, method string, params any) (json.RawMessage, error) {
	var d net.Dialer
	nc, err := d.DialContext(ctx, "unix", socket)
	if err != nil {
		return nil, fmt.Errorf("Quire is not reachable: %w", err)
	}
	defer nc.Close()
	defer context.AfterFunc(ctx, func() { nc.Close() })()
	p, _ := json.Marshal(params)
	if err := json.NewEncoder(nc).Encode(toolRequest{Method: method, Params: p}); err != nil {
		return nil, err
	}
	var res toolResponse
	if err := json.NewDecoder(nc).Decode(&res); err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		if errors.Is(err, io.EOF) {
			return nil, errors.New("Quire ended the request")
		}
		return nil, err
	}
	if res.Error != nil {
		return nil, res.Error
	}
	return res.Result, nil
}

// ServeToolsMCP is `quired tools-mcp`: the stdio MCP server an agent starts for a Quire session.
// It holds no tools of its own; every list and call goes to quired over socket, and from there to
// Quire core. Its instructions (MCP's initialize result) are Quire core's too.
func ServeToolsMCP(in io.Reader, out io.Writer, socket, version string) error {
	h := acp.Handlers{Request: func(ctx context.Context, method string, params json.RawMessage) (any, error) {
		switch method {
		case "initialize":
			var p struct {
				ProtocolVersion string `json:"protocolVersion"`
			}
			_ = json.Unmarshal(params, &p)
			res := map[string]any{
				"protocolVersion": p.ProtocolVersion,
				"capabilities":    map[string]any{"tools": map[string]any{}},
				"serverInfo":      map[string]any{"name": harness.ToolServer, "title": "OpenBook (Quire)", "version": version},
			}
			lctx, cancel := context.WithTimeout(ctx, listTimeout)
			defer cancel()
			if raw, err := askTools(lctx, socket, "tools/list", nil); err == nil {
				var l struct {
					Instructions string `json:"instructions"`
				}
				if json.Unmarshal(raw, &l) == nil && l.Instructions != "" {
					res["instructions"] = l.Instructions
				}
			}
			return res, nil
		case "ping":
			return map[string]any{}, nil
		case "tools/list":
			raw, err := askTools(ctx, socket, "tools/list", nil)
			if err != nil {
				return nil, acp.Errorf(acp.CodeInternalError, "%v", err)
			}
			var l struct {
				Tools json.RawMessage `json:"tools"`
			}
			if err := json.Unmarshal(raw, &l); err != nil || len(l.Tools) == 0 {
				return nil, acp.Errorf(acp.CodeInternalError, "Quire sent no tools")
			}
			return map[string]any{"tools": l.Tools}, nil
		case "tools/call":
			raw, err := askTools(ctx, socket, "tools/call", params)
			if err != nil {
				// A failed call is a tool result the model can read, not a protocol error.
				text := err.Error()
				var re *acp.RPCError
				if errors.As(err, &re) {
					text = re.Message
				}
				return map[string]any{"isError": true, "content": []any{map[string]any{"type": "text", "text": text}}}, nil
			}
			return raw, nil
		}
		return nil, acp.Errorf(acp.CodeMethodNotFound, "method not found: %s", method)
	}}
	c := acp.NewConn(in, out, h, nil)
	<-c.Done()
	return c.Err()
}
