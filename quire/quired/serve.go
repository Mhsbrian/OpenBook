package main

import (
	"context"
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
	"text/tabwriter"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/harness"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/serve"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/vsock"
)

// DefaultPort is quired's vsock port in the Linux environment. AVF's guest already uses 4000
// (DebianService) and 7681 (ttyd).
const DefaultPort = 7690

func cmdServe(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("serve", flag.ContinueOnError)
	port := fs.Uint("vsock", DefaultPort, "vsock port")
	unixPath := fs.String("unix", "", "unix socket path")
	stdio := fs.Bool("stdio", false, "serve one client on stdin/stdout")
	root := fs.String("root", os.Getenv("HOME"), "sessions' folders live inside this folder")
	anyCID := fs.Bool("any-cid", false, "accept vsock peers other than the host")
	maxConns := fs.Int("max-conns", 4, "clients at once")
	fsOn := fs.Bool("fs", true, "serve file access to ACP agents, confined to each session's folder")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *root == "" {
		return errors.New("serve: --root is required when $HOME is unset")
	}
	if fi, err := os.Stat(*root); err != nil || !fi.IsDir() {
		return fmt.Errorf("serve: --root %s is not a folder", *root)
	}
	// Logs go to stderr (the journal, under systemd): connections, agents, sessions and stop
	// reasons. Never prompts, answers or the environment.
	lg := log.New(os.Stderr, "", log.LstdFlags|log.Lmicroseconds)
	srv := &serve.Server{
		Version: version, ClientInfo: clientInfo, Root: *root, FS: *fsOn, Log: lg,
		Discover: func(ctx context.Context) []agents.Found { return agents.Discover(ctx, agents.HostEnv) },
		Start:    harness.Start,
	}
	if *stdio {
		return srv.Serve(ctx, "stdio", os.Stdin, os.Stdout)
	}

	type conn struct {
		io.ReadWriteCloser
		peer string
	}
	var accept func() (conn, error)
	var closeL func() error
	if *unixPath != "" {
		_ = os.Remove(*unixPath)
		old := syscall.Umask(0o177)
		l, err := net.Listen("unix", *unixPath)
		syscall.Umask(old)
		if err != nil {
			return err
		}
		defer os.Remove(*unixPath)
		lg.Printf("serve: listening on unix:%s", *unixPath)
		closeL = l.Close
		accept = func() (conn, error) {
			for {
				c, err := l.Accept()
				if err != nil {
					return conn{}, err
				}
				uid, err := peerUID(c.(*net.UnixConn))
				if err != nil || uid != os.Getuid() {
					lg.Printf("serve: refused a unix peer with uid %d", uid)
					c.Close()
					continue
				}
				return conn{c, "unix"}, nil
			}
		}
	} else {
		l, err := vsock.Listen(uint32(*port))
		if err != nil {
			return fmt.Errorf("serve: %w (is this a VM with virtio-vsock?)", err)
		}
		lg.Printf("serve: listening on vsock port %d (peers: %s)", *port, map[bool]string{true: "any CID", false: "the host only"}[*anyCID])
		closeL = l.Close
		accept = func() (conn, error) {
			for {
				c, err := l.Accept()
				if err != nil {
					return conn{}, err
				}
				// From the guest, CID 2 is the host: Android, where only AVF's own domains may
				// open vsock connections. Anything else (vsock loopback, a sibling VM) is refused.
				if !*anyCID && c.Remote.CID != vsock.CIDHost {
					lg.Printf("serve: refused %s (not the host)", c.Remote)
					c.Close()
					continue
				}
				return conn{c, c.Remote.String()}, nil
			}
		}
	}
	go func() { <-ctx.Done(); _ = closeL() }()

	sem := make(chan struct{}, *maxConns)
	var wg sync.WaitGroup
	defer wg.Wait()
	for {
		c, err := accept()
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		select {
		case sem <- struct{}{}:
		default:
			lg.Printf("serve: refused %s: %d clients already", c.peer, *maxConns)
			c.Close()
			continue
		}
		wg.Add(1)
		go func() {
			defer wg.Done()
			defer func() { <-sem }()
			defer c.Close()
			if err := srv.Serve(ctx, c.peer, c, c); err != nil {
				lg.Printf("%s: %v", c.peer, err)
			}
		}()
	}
}

func peerUID(c *net.UnixConn) (int, error) {
	rc, err := c.SyscallConn()
	if err != nil {
		return -1, err
	}
	var cred *syscall.Ucred
	var cerr error
	if err := rc.Control(func(fd uintptr) { cred, cerr = syscall.GetsockoptUcred(int(fd), syscall.SOL_SOCKET, syscall.SO_PEERCRED) }); err != nil {
		return -1, err
	}
	if cerr != nil {
		return -1, cerr
	}
	return int(cred.Uid), nil
}

// dialRemote connects to a quired serve: vsock:CID:PORT or unix:PATH.
func dialRemote(ctx context.Context, addr string) (*serve.Remote, error) {
	var rwc io.ReadWriteCloser
	switch {
	case strings.HasPrefix(addr, "vsock:"):
		parts := strings.Split(strings.TrimPrefix(addr, "vsock:"), ":")
		if len(parts) != 2 {
			return nil, fmt.Errorf("bad address %q: want vsock:CID:PORT", addr)
		}
		cid, err1 := strconv.ParseUint(parts[0], 10, 32)
		port, err2 := strconv.ParseUint(parts[1], 10, 32)
		if err1 != nil || err2 != nil {
			return nil, fmt.Errorf("bad address %q: want vsock:CID:PORT", addr)
		}
		c, err := vsock.Dial(uint32(cid), uint32(port))
		if err != nil {
			return nil, err
		}
		rwc = c
	case strings.HasPrefix(addr, "unix:"):
		c, err := net.Dial("unix", strings.TrimPrefix(addr, "unix:"))
		if err != nil {
			return nil, err
		}
		rwc = c
	default:
		return nil, fmt.Errorf("bad address %q: want vsock:CID:PORT or unix:PATH", addr)
	}
	return serve.Connect(ctx, rwc, rwc, rwc, clientInfo)
}

func remoteAgents(ctx context.Context, addr string, asJSON bool) error {
	rm, err := dialRemote(ctx, addr)
	if err != nil {
		return err
	}
	defer rm.Close()
	list, err := rm.Agents(ctx)
	if err != nil {
		return err
	}
	if asJSON {
		return printJSON(list)
	}
	w := tabwriter.NewWriter(os.Stdout, 0, 4, 2, ' ', 0)
	fmt.Fprintln(w, "AGENT\tNAME\tVERSION\tPROTOCOL\tSTATE")
	for _, a := range list {
		state := "ready"
		if !a.Supported {
			state = "not yet: " + a.Note
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\n", a.ID, a.Name, a.Version, a.Protocol, state)
	}
	return w.Flush()
}
