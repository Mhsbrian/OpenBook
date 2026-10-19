package harness

import (
	"context"
	"net"
	"os"
)

// listenUnix listens on a socket only this user can connect to. The directory it sits in is
// already private (os.MkdirTemp makes it 0700); the mode is belt and braces.
func listenUnix(path string) (net.Listener, error) {
	l, err := net.Listen("unix", path)
	if err != nil {
		return nil, err
	}
	if err := os.Chmod(path, 0o600); err != nil {
		l.Close()
		return nil, err
	}
	return l, nil
}

func dialUnix(ctx context.Context, path string) (net.Conn, error) {
	var d net.Dialer
	return d.DialContext(ctx, "unix", path)
}
