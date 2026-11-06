package setup

import (
	"fmt"
	"os"
	"syscall"
	"unsafe"
)

// openPTY opens a new pseudo-terminal pair with the standard library only: /dev/ptmx, unlocked
// with TIOCSPTLCK, its number from TIOCGPTN, and a size, so a login command that wants a terminal
// gets one.
func openPTY(cols, rows uint16) (master, slave *os.File, err error) {
	m, err := os.OpenFile("/dev/ptmx", os.O_RDWR|syscall.O_NOCTTY|syscall.O_CLOEXEC, 0)
	if err != nil {
		return nil, nil, err
	}
	fail := func(e error) (*os.File, *os.File, error) { m.Close(); return nil, nil, e }
	var unlock int32
	if _, _, e := syscall.Syscall(syscall.SYS_IOCTL, m.Fd(), syscall.TIOCSPTLCK, uintptr(unsafe.Pointer(&unlock))); e != 0 {
		return fail(os.NewSyscallError("TIOCSPTLCK", e))
	}
	var n uint32
	if _, _, e := syscall.Syscall(syscall.SYS_IOCTL, m.Fd(), syscall.TIOCGPTN, uintptr(unsafe.Pointer(&n))); e != 0 {
		return fail(os.NewSyscallError("TIOCGPTN", e))
	}
	s, err := os.OpenFile(fmt.Sprintf("/dev/pts/%d", n), os.O_RDWR|syscall.O_NOCTTY|syscall.O_CLOEXEC, 0)
	if err != nil {
		return fail(err)
	}
	ws := struct{ Row, Col, X, Y uint16 }{rows, cols, 0, 0}
	_, _, _ = syscall.Syscall(syscall.SYS_IOCTL, s.Fd(), syscall.TIOCSWINSZ, uintptr(unsafe.Pointer(&ws)))
	return m, s, nil
}
