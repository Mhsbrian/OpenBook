package acp

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"sync"
)

// JSON-RPC 2.0 error codes, plus the ones ACP adds.
const (
	CodeParseError       = -32700
	CodeInvalidRequest   = -32600
	CodeMethodNotFound   = -32601
	CodeInvalidParams    = -32602
	CodeInternalError    = -32603
	CodeAuthRequired     = -32000
	CodeResourceNotFound = -32002
)

// RPCError is a JSON-RPC error object. Handlers return one to choose the code the peer sees;
// any other error becomes CodeInternalError.
type RPCError struct {
	Code    int             `json:"code"`
	Message string          `json:"message"`
	Data    json.RawMessage `json:"data,omitempty"`
}

func (e *RPCError) Error() string { return fmt.Sprintf("acp error %d: %s", e.Code, e.Message) }

func Errorf(code int, format string, args ...any) *RPCError {
	return &RPCError{Code: code, Message: fmt.Sprintf(format, args...)}
}

// ErrClosed is returned by calls on a connection whose peer has gone away.
var ErrClosed = errors.New("acp: connection closed")

// Handlers answer what the peer sends.
type Handlers struct {
	// Request answers a request. Each request runs on its own goroutine, so a handler may block,
	// for example on a person deciding a permission prompt. ctx ends when the connection closes.
	Request func(ctx context.Context, method string, params json.RawMessage) (any, error)
	// Notification runs on the read loop, in arrival order, so it must return quickly.
	Notification func(method string, params json.RawMessage)
}

type message struct {
	JSONRPC string           `json:"jsonrpc"`
	ID      *json.RawMessage `json:"id,omitempty"`
	Method  string           `json:"method,omitempty"`
	Params  json.RawMessage  `json:"params,omitempty"`
	Result  json.RawMessage  `json:"result,omitempty"`
	Error   *RPCError        `json:"error,omitempty"`
}

// Conn is one JSON-RPC 2.0 connection framed as newline-delimited JSON, the framing ACP uses on stdio.
type Conn struct {
	w   io.Writer
	wmu sync.Mutex
	h   Handlers

	mu      sync.Mutex
	next    int64
	pending map[int64]chan message
	err     error

	ctx    context.Context
	cancel context.CancelFunc
	done   chan struct{}
	// Junk receives lines that are not JSON-RPC (some agents log to stdout). Optional.
	junk func(line []byte)
}

// NewConn starts reading r. junk, if set, is given every line that isn't a JSON object.
func NewConn(r io.Reader, w io.Writer, h Handlers, junk func(line []byte)) *Conn {
	ctx, cancel := context.WithCancel(context.Background())
	c := &Conn{w: w, h: h, pending: map[int64]chan message{}, ctx: ctx, cancel: cancel, done: make(chan struct{}), junk: junk}
	go c.readLoop(r)
	return c
}

// Done is closed when the peer's stream ends.
func (c *Conn) Done() <-chan struct{} { return c.done }

// Err is why the connection ended: nil for a clean EOF.
func (c *Conn) Err() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	return c.err
}

// Call sends a request and decodes the result into result (which may be nil).
func (c *Conn) Call(ctx context.Context, method string, params, result any) error {
	c.mu.Lock()
	if c.pending == nil {
		c.mu.Unlock()
		return ErrClosed
	}
	c.next++
	id := c.next
	ch := make(chan message, 1)
	c.pending[id] = ch
	c.mu.Unlock()

	raw := json.RawMessage(fmt.Sprint(id))
	if err := c.send(message{ID: &raw, Method: method, Params: mustMarshal(params)}); err != nil {
		c.forget(id)
		return err
	}
	select {
	case m, ok := <-ch:
		if !ok {
			return ErrClosed
		}
		if m.Error != nil {
			return m.Error
		}
		if result != nil && len(m.Result) > 0 {
			if err := json.Unmarshal(m.Result, result); err != nil {
				return fmt.Errorf("acp: %s: bad result: %w", method, err)
			}
		}
		return nil
	case <-ctx.Done():
		c.forget(id)
		return ctx.Err()
	}
}

// Notify sends a notification.
func (c *Conn) Notify(method string, params any) error {
	return c.send(message{Method: method, Params: mustMarshal(params)})
}

func (c *Conn) forget(id int64) {
	c.mu.Lock()
	delete(c.pending, id)
	c.mu.Unlock()
}

func (c *Conn) send(m message) error {
	m.JSONRPC = "2.0"
	b, err := json.Marshal(m)
	if err != nil {
		return err
	}
	b = append(b, '\n')
	c.wmu.Lock()
	defer c.wmu.Unlock()
	if _, err := c.w.Write(b); err != nil {
		return fmt.Errorf("acp: write: %w", err)
	}
	return nil
}

func (c *Conn) readLoop(r io.Reader) {
	br := bufio.NewReaderSize(r, 1<<16)
	var err error
	for {
		var line []byte
		line, err = br.ReadBytes('\n') // no line limit: tool output can be large
		if t := bytes.TrimSpace(line); len(t) > 0 {
			c.dispatch(t)
		}
		if err != nil {
			break
		}
	}
	c.mu.Lock()
	if !errors.Is(err, io.EOF) {
		c.err = err
	}
	for _, ch := range c.pending {
		close(ch)
	}
	c.pending = nil
	c.mu.Unlock()
	c.cancel()
	close(c.done)
}

func (c *Conn) dispatch(line []byte) {
	var m message
	if line[0] != '{' || json.Unmarshal(line, &m) != nil {
		if c.junk != nil {
			c.junk(line)
		}
		return
	}
	switch {
	case m.Method != "" && m.ID == nil:
		if c.h.Notification != nil {
			c.h.Notification(m.Method, m.Params)
		}
	case m.Method != "":
		go c.answer(m)
	case m.ID != nil:
		var id int64
		if json.Unmarshal(*m.ID, &id) != nil {
			return // not one of ours
		}
		c.mu.Lock()
		ch := c.pending[id]
		delete(c.pending, id)
		c.mu.Unlock()
		if ch != nil {
			ch <- m
		}
	}
}

func (c *Conn) answer(req message) {
	reply := message{ID: req.ID}
	if c.h.Request == nil {
		reply.Error = Errorf(CodeMethodNotFound, "method not found: %s", req.Method)
	} else if res, err := c.h.Request(c.ctx, req.Method, req.Params); err != nil {
		var re *RPCError
		if !errors.As(err, &re) {
			re = &RPCError{Code: CodeInternalError, Message: err.Error()}
		}
		reply.Error = re
	} else {
		reply.Result = mustMarshal(res)
	}
	_ = c.send(reply) // a peer that has gone away can't be told anything
}

func mustMarshal(v any) json.RawMessage {
	if v == nil {
		return json.RawMessage("null")
	}
	if raw, ok := v.(json.RawMessage); ok {
		return raw
	}
	b, err := json.Marshal(v)
	if err != nil {
		panic(fmt.Sprintf("acp: marshal %T: %v", v, err))
	}
	return b
}
