package acp

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"sync"
	"testing"
	"time"
)

// pair connects two Conns back to back, as a client and an agent would be over stdio.
func pair(t *testing.T, a, b Handlers) (*Conn, *Conn, func()) {
	t.Helper()
	ar, bw := io.Pipe()
	br, aw := io.Pipe()
	ca := NewConn(ar, aw, a, nil)
	cb := NewConn(br, bw, b, nil)
	return ca, cb, func() { aw.Close(); bw.Close() }
}

func TestCallAndResult(t *testing.T) {
	agent := Handlers{Request: func(ctx context.Context, method string, params json.RawMessage) (any, error) {
		if method != MethodInitialize {
			return nil, Errorf(CodeMethodNotFound, "no %s", method)
		}
		var req InitializeRequest
		if err := json.Unmarshal(params, &req); err != nil {
			return nil, err
		}
		return InitializeResponse{ProtocolVersion: req.ProtocolVersion, AgentInfo: &Implementation{Name: "fake"}}, nil
	}}
	client, _, stop := pair(t, Handlers{}, agent)
	defer stop()

	var res InitializeResponse
	if err := client.Call(context.Background(), MethodInitialize, InitializeRequest{ProtocolVersion: ProtocolVersion}, &res); err != nil {
		t.Fatal(err)
	}
	if res.ProtocolVersion != 1 || res.AgentInfo == nil || res.AgentInfo.Name != "fake" {
		t.Fatalf("unexpected result %+v", res)
	}

	err := client.Call(context.Background(), "nope", nil, nil)
	var re *RPCError
	if !errors.As(err, &re) || re.Code != CodeMethodNotFound {
		t.Fatalf("want method-not-found, got %v", err)
	}
}

func TestNotificationsKeepOrderWhileRequestsBlock(t *testing.T) {
	var mu sync.Mutex
	var got []string
	release := make(chan struct{})
	client := Handlers{
		Notification: func(method string, params json.RawMessage) {
			var n SessionNotification
			_ = json.Unmarshal(params, &n)
			var u SessionUpdate
			_ = json.Unmarshal(n.Update, &u)
			mu.Lock()
			got = append(got, u.ChunkText())
			mu.Unlock()
		},
		Request: func(ctx context.Context, method string, params json.RawMessage) (any, error) {
			<-release // a person thinking about a permission prompt
			return Selected("allow"), nil
		},
	}
	_, agent, stop := pair(t, client, Handlers{})
	defer stop()

	perm := make(chan RequestPermissionResponse, 1)
	go func() {
		var r RequestPermissionResponse
		if err := agent.Call(context.Background(), MethodRequestPermission, RequestPermissionRequest{}, &r); err == nil {
			perm <- r
		}
	}()
	for _, w := range []string{"a", "b", "c", "d"} {
		if err := agent.Notify(context.Background(), MethodSessionUpdate, SessionNotification{SessionID: "s", Update: ChunkUpdate(UpdateAgentMessageChunk, w).Marshal()}); err != nil {
			t.Fatal(err)
		}
	}
	waitFor(t, func() bool { mu.Lock(); defer mu.Unlock(); return len(got) == 4 })
	close(release)
	select {
	case r := <-perm:
		if r.Outcome.Outcome != OutcomeSelected || r.Outcome.OptionID != "allow" {
			t.Fatalf("bad outcome %+v", r)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("permission reply never arrived")
	}
	if strings.Join(got, "") != "abcd" {
		t.Fatalf("notifications out of order: %v", got)
	}
}

func TestJunkLinesAndClose(t *testing.T) {
	r, w := io.Pipe()
	var junk []string
	var mu sync.Mutex
	c := NewConn(r, io.Discard, Handlers{}, func(l []byte) { mu.Lock(); junk = append(junk, string(l)); mu.Unlock() })
	pending := make(chan error, 1)
	go func() { pending <- c.Call(context.Background(), "x", nil, nil) }()
	time.Sleep(20 * time.Millisecond)
	_, _ = io.WriteString(w, "starting agent v1.2\n\n{not json\n")
	w.Close()
	select {
	case err := <-pending:
		if !errors.Is(err, ErrClosed) {
			t.Fatalf("want ErrClosed, got %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("call did not fail after close")
	}
	<-c.Done()
	if c.Err() != nil {
		t.Fatalf("clean EOF should leave Err nil, got %v", c.Err())
	}
	mu.Lock()
	defer mu.Unlock()
	if len(junk) != 2 {
		t.Fatalf("want 2 junk lines, got %q", junk)
	}
	if err := c.Call(context.Background(), "x", nil, nil); !errors.Is(err, ErrClosed) {
		t.Fatalf("call after close: %v", err)
	}
}

func TestCallHonoursContext(t *testing.T) {
	client, _, stop := pair(t, Handlers{}, Handlers{Request: func(ctx context.Context, _ string, _ json.RawMessage) (any, error) {
		<-ctx.Done()
		return nil, ctx.Err()
	}})
	defer stop()
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	if err := client.Call(ctx, MethodPrompt, nil, nil); !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("want deadline exceeded, got %v", err)
	}
}

// A peer that stops reading must not hold a caller past its context, whether the caller's write
// is the one stuck in the pipe or is waiting behind it; closing the pipe then ends the connection.
func TestSendsHonourContextWhenPeerStopsReading(t *testing.T) {
	inR, inW := io.Pipe()
	outR, outW := io.Pipe() // nobody reads outR
	c := NewConn(inR, outW, Handlers{}, nil)
	defer inW.Close()

	sends := map[string]func(context.Context) error{
		"call (write stuck)":   func(ctx context.Context) error { return c.Call(ctx, MethodInitialize, nil, nil) },
		"call (queued behind)": func(ctx context.Context) error { return c.Call(ctx, MethodPrompt, nil, nil) },
		"notify (queued)": func(ctx context.Context) error {
			return c.Notify(ctx, MethodCancel, CancelNotification{SessionID: "s"})
		},
	}
	for _, name := range []string{"call (write stuck)", "call (queued behind)", "notify (queued)"} {
		ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
		start := time.Now()
		err := sends[name](ctx)
		cancel()
		if !errors.Is(err, context.DeadlineExceeded) || time.Since(start) > 2*time.Second {
			t.Fatalf("%s: want deadline exceeded promptly, got %v after %s", name, err, time.Since(start))
		}
	}

	pending := make(chan error, 1)
	go func() { pending <- c.Call(context.Background(), MethodSessionNew, nil, nil) }()
	time.Sleep(20 * time.Millisecond)
	outR.Close() // the stuck write fails, which ends the connection
	select {
	case err := <-pending:
		if !errors.Is(err, ErrClosed) {
			t.Fatalf("want ErrClosed once the write failed, got %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("a call without a deadline outlived the connection")
	}
	if c.Err() == nil || !strings.Contains(c.Err().Error(), "write") {
		t.Fatalf("Err should report the write failure, got %v", c.Err())
	}
	if err := c.Notify(context.Background(), MethodCancel, nil); !errors.Is(err, ErrClosed) {
		t.Fatalf("notify after the writer stopped: %v", err)
	}
}

func waitFor(t *testing.T, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for !cond() {
		if time.Now().After(deadline) {
			t.Fatal("condition not met in 5 s")
		}
		time.Sleep(5 * time.Millisecond)
	}
}
