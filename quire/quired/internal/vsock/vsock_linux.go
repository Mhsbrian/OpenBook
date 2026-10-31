// Package vsock is the AF_VSOCK transport between the Linux environment (an AVF guest) and
// Android: `quired serve` listens in the guest, and Quire core connects from the host.
//
// The standard library's syscall package can't decode a vsock address (Accept4 closes the new
// socket and fails), so bind, connect and accept4 are called directly. Sockets are non-blocking
// and wrapped in os.File, which puts them on Go's poller: reads, writes and accepts park the
// goroutine, and closing the listener wakes a pending Accept.
package vsock

import (
	"errors"
	"fmt"
	"os"
	"syscall"
	"unsafe"
)

const (
	afVsock = 40 // AF_VSOCK

	// CIDAny binds every local CID. CIDHost is the host as a guest sees it: for the Linux
	// environment, that is Android. CIDLocal is loopback (vsock_loopback).
	CIDAny   = 0xFFFFFFFF
	CIDHost  = 2
	CIDLocal = 1
)

// rawSockaddrVM is struct sockaddr_vm from <linux/vm_sockets.h>.
type rawSockaddrVM struct {
	Family    uint16
	Reserved1 uint16
	Port      uint32
	CID       uint32
	Flags     uint8
	Zero      [3]uint8
}

// Addr is a vsock address.
type Addr struct {
	CID  uint32
	Port uint32
}

func (a Addr) Network() string { return "vsock" }
func (a Addr) String() string  { return fmt.Sprintf("vsock:%d:%d", a.CID, a.Port) }

// Conn is a connected vsock stream.
type Conn struct {
	*os.File
	Local, Remote Addr
}

// CloseWrite half-closes the stream, so the peer reads EOF while replies can still arrive.
func (c *Conn) CloseWrite() error {
	rc, err := c.SyscallConn()
	if err != nil {
		return err
	}
	var serr error
	if err := rc.Control(func(fd uintptr) { serr = syscall.Shutdown(int(fd), syscall.SHUT_WR) }); err != nil {
		return err
	}
	return serr
}

// Listener accepts vsock connections.
type Listener struct {
	f    *os.File
	addr Addr
}

func socket() (int, error) {
	fd, err := syscall.Socket(afVsock, syscall.SOCK_STREAM|syscall.SOCK_NONBLOCK|syscall.SOCK_CLOEXEC, 0)
	if err != nil {
		return -1, os.NewSyscallError("socket(AF_VSOCK)", err)
	}
	return fd, nil
}

func sockaddr(cid, port uint32) rawSockaddrVM {
	return rawSockaddrVM{Family: afVsock, Port: port, CID: cid}
}

func sockcall(trap uintptr, fd int, sa *rawSockaddrVM) error {
	_, _, e := syscall.Syscall(trap, uintptr(fd), uintptr(unsafe.Pointer(sa)), unsafe.Sizeof(*sa))
	if e != 0 {
		return e
	}
	return nil
}

func name(fd int, peer bool) (Addr, error) {
	var sa rawSockaddrVM
	l := uint32(unsafe.Sizeof(sa))
	trap := uintptr(syscall.SYS_GETSOCKNAME)
	if peer {
		trap = syscall.SYS_GETPEERNAME
	}
	_, _, e := syscall.Syscall(trap, uintptr(fd), uintptr(unsafe.Pointer(&sa)), uintptr(unsafe.Pointer(&l)))
	if e != 0 {
		return Addr{}, e
	}
	return Addr{CID: sa.CID, Port: sa.Port}, nil
}

// Listen listens on port on every local CID.
func Listen(port uint32) (*Listener, error) {
	fd, err := socket()
	if err != nil {
		return nil, err
	}
	sa := sockaddr(CIDAny, port)
	if err := sockcall(syscall.SYS_BIND, fd, &sa); err != nil {
		syscall.Close(fd)
		return nil, os.NewSyscallError("bind", err)
	}
	if err := syscall.Listen(fd, 16); err != nil {
		syscall.Close(fd)
		return nil, os.NewSyscallError("listen", err)
	}
	addr, _ := name(fd, false)
	return &Listener{f: os.NewFile(uintptr(fd), "vsock-listener"), addr: addr}, nil
}

func (l *Listener) Addr() Addr { return l.addr }

// Close stops the listener; a pending Accept returns an error wrapping os.ErrClosed.
func (l *Listener) Close() error { return l.f.Close() }

// Accept waits for the next connection.
func (l *Listener) Accept() (*Conn, error) {
	rc, err := l.f.SyscallConn()
	if err != nil {
		return nil, err
	}
	var nfd int
	var sa rawSockaddrVM
	var aerr error
	err = rc.Read(func(fd uintptr) bool {
		sl := uint32(unsafe.Sizeof(sa))
		r, _, e := syscall.Syscall6(syscall.SYS_ACCEPT4, fd, uintptr(unsafe.Pointer(&sa)), uintptr(unsafe.Pointer(&sl)),
			syscall.SOCK_NONBLOCK|syscall.SOCK_CLOEXEC, 0, 0)
		if e == syscall.EAGAIN || e == syscall.EINTR || e == syscall.ECONNABORTED {
			return false // wait for the next connection
		}
		nfd, aerr = int(r), nil
		if e != 0 {
			aerr = os.NewSyscallError("accept4", e)
		}
		return true
	})
	if err != nil {
		return nil, err
	}
	if aerr != nil {
		return nil, aerr
	}
	return &Conn{File: os.NewFile(uintptr(nfd), "vsock"), Local: l.addr, Remote: Addr{CID: sa.CID, Port: sa.Port}}, nil
}

// Dial connects to port on cid. The kernel's vsock connect timeout (2 s by default) bounds it.
func Dial(cid, port uint32) (*Conn, error) {
	fd, err := socket()
	if err != nil {
		return nil, err
	}
	f := os.NewFile(uintptr(fd), "vsock")
	rc, err := f.SyscallConn()
	if err != nil {
		f.Close()
		return nil, err
	}
	sa := sockaddr(cid, port)
	var cerr error
	started := false
	// A non-blocking connect returns EINPROGRESS; the socket becomes writable when it is done,
	// and SO_ERROR then says how it went.
	err = rc.Write(func(fd uintptr) bool {
		if !started {
			started = true
			cerr = sockcall(syscall.SYS_CONNECT, int(fd), &sa)
			if cerr == syscall.EINPROGRESS || cerr == syscall.EINTR {
				return false
			}
			return true
		}
		v, e := syscall.GetsockoptInt(int(fd), syscall.SOL_SOCKET, syscall.SO_ERROR)
		if e != nil {
			cerr = e
		} else if v != 0 {
			cerr = syscall.Errno(v)
		} else {
			cerr = nil
		}
		return true
	})
	if err == nil {
		err = cerr
	}
	if err != nil {
		f.Close()
		return nil, &os.SyscallError{Syscall: fmt.Sprintf("connect(vsock:%d:%d)", cid, port), Err: err}
	}
	c := &Conn{File: f, Remote: Addr{CID: cid, Port: port}}
	_ = rc.Control(func(fd uintptr) { c.Local, _ = name(int(fd), false) })
	return c, nil
}

// Available reports whether this kernel can make vsock sockets at all.
func Available() bool {
	fd, err := socket()
	if err != nil {
		return false
	}
	syscall.Close(fd)
	return true
}

// IsClosed reports whether err came from using a closed listener or connection.
func IsClosed(err error) bool { return errors.Is(err, os.ErrClosed) }
