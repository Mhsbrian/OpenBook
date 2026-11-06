package main

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/admin"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/vsock"
)

// AdminPort is the admin worker's vsock port (quire-admin.socket).
const AdminPort = 7691

// cmdAdmin is the root worker, started by systemd once per connection (socket activation,
// Accept=yes: the connection is file descriptor 3). Subcommands: apply-update (the update unit's
// work) and call (a client, for checks).
func cmdAdmin(ctx context.Context, args []string) error {
	if len(args) > 0 {
		switch args[0] {
		case "apply-update":
			return adminApply(ctx, args[1:])
		case "call":
			return adminCall(ctx, args[1:])
		}
	}
	fs := flag.NewFlagSet("admin", flag.ContinueOnError)
	unixPath := fs.String("unix", "", "listen on a unix socket instead (same-user peers; for checks on a host)")
	state := fs.String("state", "/var/lib/quire", "where update records live")
	if err := fs.Parse(args); err != nil {
		return err
	}
	lg := log.New(os.Stderr, "", log.LstdFlags|log.Lmicroseconds)
	w := admin.New(version, lg)
	w.State = *state
	if *unixPath != "" {
		return adminUnix(ctx, w, *unixPath, lg)
	}
	// systemd: LISTEN_PID is this process and LISTEN_FDS counts the descriptors from 3.
	if os.Getenv("LISTEN_PID") != strconv.Itoa(os.Getpid()) || os.Getenv("LISTEN_FDS") != "1" {
		return errors.New("admin: start it from quire-admin.socket (socket activation with Accept=yes)")
	}
	const fd = 3
	syscall.CloseOnExec(fd)
	family, addr, err := vsock.Peer(fd)
	if err != nil {
		return fmt.Errorf("admin: %w", err)
	}
	peer := admin.Describe(family, addr)
	if !admin.PeerAllowed(family, addr) {
		lg.Printf("admin: refused %s (not the host)", peer)
		syscall.Close(fd)
		return nil
	}
	f := os.NewFile(fd, "quire-admin")
	defer f.Close()
	lg.Printf("admin: %s connected", peer)
	return w.Serve(ctx, peer, f, f)
}

func adminUnix(ctx context.Context, w *admin.Worker, path string, lg *log.Logger) error {
	_ = os.Remove(path)
	old := syscall.Umask(0o177)
	l, err := net.Listen("unix", path)
	syscall.Umask(old)
	if err != nil {
		return err
	}
	defer os.Remove(path)
	go func() { <-ctx.Done(); l.Close() }()
	for {
		c, err := l.Accept()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		uid, err := peerUID(c.(*net.UnixConn))
		if err != nil || uid != os.Getuid() {
			lg.Printf("admin: refused a unix peer with uid %d", uid)
			c.Close()
			continue
		}
		go func() { defer c.Close(); _ = w.Serve(ctx, "unix", c, c) }()
	}
}

func adminApply(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("admin apply-update", flag.ContinueOnError)
	job := fs.String("job", "", "the update's job id")
	state := fs.String("state", "/var/lib/quire", "where update records live")
	if err := fs.Parse(args); err != nil {
		return err
	}
	w := admin.New(version, log.New(os.Stderr, "", log.LstdFlags))
	w.State = *state
	return w.ApplyUpdate(ctx, *job)
}

// adminCall sends one request to an admin worker and prints its notifications and result.
func adminCall(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("admin call", flag.ContinueOnError)
	connect := fs.String("connect", "", "vsock:CID:PORT or unix:PATH")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *connect == "" || fs.NArg() < 1 {
		return errors.New("usage: quired admin call --connect ADDR METHOD [JSON]")
	}
	rwc, err := dialRaw(*connect)
	if err != nil {
		return err
	}
	defer rwc.Close()
	return callPrint(ctx, rwc, fs.Arg(0), fs.Arg(1))
}

// dialRaw connects to vsock:CID:PORT or unix:PATH.
func dialRaw(addr string) (io.ReadWriteCloser, error) {
	switch {
	case strings.HasPrefix(addr, "vsock:"):
		parts := strings.Split(strings.TrimPrefix(addr, "vsock:"), ":")
		if len(parts) != 2 {
			return nil, fmt.Errorf("bad address %q", addr)
		}
		cid, err1 := strconv.ParseUint(parts[0], 10, 32)
		port, err2 := strconv.ParseUint(parts[1], 10, 32)
		if err1 != nil || err2 != nil {
			return nil, fmt.Errorf("bad address %q", addr)
		}
		return vsock.Dial(uint32(cid), uint32(port))
	case strings.HasPrefix(addr, "unix:"):
		return net.Dial("unix", strings.TrimPrefix(addr, "unix:"))
	}
	return nil, fmt.Errorf("bad address %q: want vsock:CID:PORT or unix:PATH", addr)
}

// callPrint sends one JSON-RPC request on rwc and prints, as JSON lines, every notification
// and then {"quired": "result", "result"|"error"}.
func callPrint(ctx context.Context, rwc io.ReadWriteCloser, method, params string) error {
	params, err := readParams(params)
	if err != nil {
		return err
	}
	if !json.Valid([]byte(params)) {
		return fmt.Errorf("params are not JSON: %s", params)
	}
	out := json.NewEncoder(os.Stdout)
	conn := acp.NewConn(rwc, rwc, acp.Handlers{Notification: func(m string, p json.RawMessage) {
		_ = out.Encode(map[string]any{"method": m, "params": p})
	}}, nil)
	var res json.RawMessage
	err = conn.Call(ctx, method, json.RawMessage(params), &res)
	if err != nil {
		var re *acp.RPCError
		if errors.As(err, &re) {
			_ = out.Encode(map[string]any{"quired": "result", "error": re})
			return fmt.Errorf("%s: %s", method, re.Message)
		}
		return err
	}
	return out.Encode(map[string]any{"quired": "result", "result": res})
}

// cmdSetup is a client of quired serve's setup methods, for checks: it initializes as Quire core
// would, sends one request, and prints the notifications and the result. For _quire/login, each
// line of stdin is sent to the running login as _quire/login/input, and its answer printed.
func cmdSetup(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("setup", flag.ContinueOnError)
	connect := fs.String("connect", "", "vsock:CID:PORT or unix:PATH of a quired serve")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *connect == "" || fs.NArg() < 1 {
		return errors.New("usage: quired setup --connect ADDR METHOD [JSON]")
	}
	rwc, err := dialRaw(*connect)
	if err != nil {
		return err
	}
	defer rwc.Close()
	enc := json.NewEncoder(os.Stdout)
	var outMu sync.Mutex
	emit := func(v any) error { outMu.Lock(); defer outMu.Unlock(); return enc.Encode(v) }
	var conn *acp.Conn
	conn = acp.NewConn(rwc, rwc, acp.Handlers{Notification: func(m string, p json.RawMessage) {
		_ = emit(map[string]any{"method": m, "params": p})
	}}, nil)
	init := acp.InitializeRequest{ProtocolVersion: acp.ProtocolVersion, ClientInfo: &clientInfo}
	var info acp.InitializeResponse
	if err := conn.Call(ctx, acp.MethodInitialize, init, &info); err != nil {
		return err
	}
	method := fs.Arg(0)
	params, perr := readParams(fs.Arg(1))
	if perr != nil {
		return perr
	}
	if !json.Valid([]byte(params)) {
		return fmt.Errorf("params are not JSON: %s", params)
	}
	var inputs sync.WaitGroup
	if method == "_quire/login" {
		var p struct {
			Job string `json:"job"`
		}
		_ = json.Unmarshal([]byte(params), &p)
		// Each line of stdin is one input; its answer (or refusal) is printed as {"quired": "input", ...},
		// before the login's result if the code ends the login.
		go func() {
			sc := bufio.NewScanner(os.Stdin)
			for sc.Scan() {
				inputs.Add(1)
				var res json.RawMessage
				err := conn.Call(ctx, "_quire/login/input", map[string]string{"job": p.Job, "text": sc.Text()}, &res)
				var re *acp.RPCError
				switch {
				case err == nil:
					_ = emit(map[string]any{"quired": "input", "result": res})
				case errors.As(err, &re):
					_ = emit(map[string]any{"quired": "input", "error": re})
				default:
					_ = emit(map[string]any{"quired": "input", "error": map[string]string{"message": err.Error()}})
				}
				inputs.Done()
			}
		}()
	}
	var res json.RawMessage
	err = conn.Call(ctx, method, json.RawMessage(params), &res)
	waitInputs(&inputs, 10*time.Second)
	if err != nil {
		var re *acp.RPCError
		if errors.As(err, &re) {
			_ = emit(map[string]any{"quired": "result", "error": re})
			return fmt.Errorf("%s: %s", method, re.Message)
		}
		return err
	}
	return emit(map[string]any{"quired": "result", "result": res})
}

// waitInputs waits up to d for inputs still being answered.
func waitInputs(wg *sync.WaitGroup, d time.Duration) {
	done := make(chan struct{})
	go func() { wg.Wait(); close(done) }()
	select {
	case <-done:
	case <-time.After(d):
	}
}

// readParams returns JSON params: the argument itself, "{}" if empty, or a file's contents for
// @PATH (a quired package in base64 is larger than one argument may be).
func readParams(arg string) (string, error) {
	if arg == "" {
		return "{}", nil
	}
	if strings.HasPrefix(arg, "@") {
		b, err := os.ReadFile(strings.TrimPrefix(arg, "@"))
		if err != nil {
			return "", err
		}
		arg = string(b)
	}
	return arg, nil
}
