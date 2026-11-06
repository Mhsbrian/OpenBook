package setup

import (
	"bufio"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"syscall"
)

// Keys stores API keys and tokens, one file per agent, in HOME/.config/quire/keys (docs/quire-setup.md
// §6): the folder is 0700, each file 0600, written as a new file renamed into place through a
// handle on the folder, so neither a symlink nor a swapped file can redirect it. A folder or file
// that isn't the user's, has looser permissions, or is a symlink is refused, never repaired.
//
// Every agent runs as the same user, so 0600 keeps the keys from other users, not from other
// agents. quired passes a key only into the environment of the agent it belongs to.
type Keys struct {
	Home string
}

var (
	agentID = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,40}$`)
	envName = regexp.MustCompile(`^[A-Z][A-Z0-9_]{0,63}$`)
)

// ErrUnsafe is returned when the keys folder or a key file isn't safe to use.
var ErrUnsafe = errors.New("unsafe key storage")

func (k Keys) dir() string { return filepath.Join(k.Home, ".config", "quire", "keys") }

// open returns a handle on the keys folder, made if missing.
func (k Keys) open(create bool) (*os.Root, error) {
	if k.Home == "" {
		return nil, errors.New("no home folder")
	}
	parent := filepath.Join(k.Home, ".config", "quire")
	if create {
		if err := os.MkdirAll(parent, 0o700); err != nil {
			return nil, err
		}
	}
	if err := checkDir(parent, false); err != nil {
		return nil, err
	}
	d := k.dir()
	if create {
		if err := os.Mkdir(d, 0o700); err != nil && !errors.Is(err, fs.ErrExist) {
			return nil, err
		}
	}
	if err := checkDir(d, true); err != nil {
		return nil, err
	}
	r, err := os.OpenRoot(d)
	if err != nil {
		return nil, err
	}
	// The folder checked is the folder opened.
	a, err1 := os.Lstat(d)
	b, err2 := r.Stat(".")
	if err1 != nil || err2 != nil || !os.SameFile(a, b) {
		r.Close()
		return nil, fmt.Errorf("%w: %s changed while it was opened", ErrUnsafe, d)
	}
	return r, nil
}

// checkDir refuses a symlink, a non-folder, a folder of another user, and (strict) one that
// others can read or enter.
func checkDir(p string, strict bool) error {
	fi, err := os.Lstat(p)
	if err != nil {
		return err
	}
	if fi.Mode()&fs.ModeSymlink != 0 || !fi.IsDir() {
		return fmt.Errorf("%w: %s is not a folder", ErrUnsafe, p)
	}
	st, ok := fi.Sys().(*syscall.Stat_t)
	if !ok || int(st.Uid) != os.Getuid() {
		return fmt.Errorf("%w: %s is not this user's", ErrUnsafe, p)
	}
	if strict && fi.Mode().Perm()&0o077 != 0 {
		return fmt.Errorf("%w: %s is open to others (%v)", ErrUnsafe, p, fi.Mode().Perm())
	}
	return nil
}

// read returns the agent's stored variables, or none.
func (k Keys) read(agent string) (map[string]string, error) {
	if !agentID.MatchString(agent) {
		return nil, fmt.Errorf("bad agent %q", agent)
	}
	if _, err := os.Lstat(k.dir()); errors.Is(err, fs.ErrNotExist) {
		return map[string]string{}, nil
	}
	r, err := k.open(false)
	if err != nil {
		return nil, err
	}
	defer r.Close()
	if fi, err := r.Lstat(agent + ".env"); errors.Is(err, fs.ErrNotExist) {
		return map[string]string{}, nil
	} else if err != nil {
		return nil, err
	} else if !fi.Mode().IsRegular() {
		return nil, fmt.Errorf("%w: %s.env is not a regular file", ErrUnsafe, agent)
	}
	f, err := r.OpenFile(agent+".env", os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return nil, fmt.Errorf("%w: %s.env: %v", ErrUnsafe, agent, err)
	}
	defer f.Close()
	fi, err := f.Stat()
	if err != nil {
		return nil, err
	}
	st, ok := fi.Sys().(*syscall.Stat_t)
	if !fi.Mode().IsRegular() || !ok || int(st.Uid) != os.Getuid() || fi.Mode().Perm()&0o077 != 0 {
		return nil, fmt.Errorf("%w: %s.env is not a private file of this user", ErrUnsafe, agent)
	}
	out := map[string]string{}
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		name, value, ok := strings.Cut(sc.Text(), "=")
		if ok && envName.MatchString(name) {
			out[name] = value
		}
	}
	return out, sc.Err()
}

// Set stores one variable for agent.
func (k Keys) Set(agent, name, value string) error {
	if !agentID.MatchString(agent) {
		return fmt.Errorf("bad agent %q", agent)
	}
	if !envName.MatchString(name) {
		return fmt.Errorf("bad variable name %q", name)
	}
	if value == "" || len(value) > 4096 || strings.ContainsAny(value, "\n\r\x00") {
		return errors.New("the key must be one line of at most 4096 characters")
	}
	vars, err := k.read(agent)
	if err != nil {
		return err
	}
	vars[name] = value
	r, err := k.open(true)
	if err != nil {
		return err
	}
	defer r.Close()
	var b strings.Builder
	names := make([]string, 0, len(vars))
	for n := range vars {
		names = append(names, n)
	}
	sort.Strings(names)
	for _, n := range names {
		fmt.Fprintf(&b, "%s=%s\n", n, vars[n])
	}
	var rnd [6]byte
	_, _ = rand.Read(rnd[:])
	tmp := "." + agent + ".env." + hex.EncodeToString(rnd[:])
	f, err := r.OpenFile(tmp, os.O_WRONLY|os.O_CREATE|os.O_EXCL|syscall.O_NOFOLLOW, 0o600)
	if err != nil {
		return err
	}
	_, werr := f.WriteString(b.String())
	if werr == nil {
		werr = f.Sync()
	}
	if cerr := f.Close(); werr == nil {
		werr = cerr
	}
	if werr != nil {
		_ = r.Remove(tmp)
		return werr
	}
	if fi, err := r.Lstat(agent + ".env"); err == nil && !fi.Mode().IsRegular() {
		_ = r.Remove(tmp)
		return fmt.Errorf("%w: %s.env is not a regular file", ErrUnsafe, agent)
	}
	if err := r.Rename(tmp, agent+".env"); err != nil {
		_ = r.Remove(tmp)
		return err
	}
	return nil
}

// Has reports whether a key file exists for agent.
func (k Keys) Has(agent string) bool {
	vars, err := k.read(agent)
	return err == nil && len(vars) > 0
}

// Env returns the agent's variables as NAME=VALUE, for its own process only.
func (k Keys) Env(agent string) ([]string, error) {
	vars, err := k.read(agent)
	if err != nil {
		return nil, err
	}
	var env []string
	for n, v := range vars {
		env = append(env, n+"="+v)
	}
	sort.Strings(env)
	return env, nil
}

// Remove deletes the agent's key file and returns its path if there was one.
func (k Keys) Remove(agent string) (string, error) {
	if !agentID.MatchString(agent) {
		return "", fmt.Errorf("bad agent %q", agent)
	}
	if _, err := os.Lstat(k.dir()); errors.Is(err, fs.ErrNotExist) {
		return "", nil
	}
	r, err := k.open(false)
	if err != nil {
		return "", err
	}
	defer r.Close()
	if err := r.Remove(agent + ".env"); err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return "", nil
		}
		return "", err
	}
	return filepath.Join(k.dir(), agent+".env"), nil
}
