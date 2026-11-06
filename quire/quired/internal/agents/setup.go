package agents

import (
	"strings"
)

// Setup is how quired installs, updates, removes and signs in one agent, from its maker's own
// instructions (docs/quire-setup.md §5). Everything here runs as the service's user, without
// root: Debian prerequisites come from the admin worker (`quired admin`) before Install.
type Setup struct {
	Source  string   // the maker's install instructions
	Debian  []string // Debian packages the recipe needs, each one in DebianAllowlist
	Install []Step
	Update  []Step
	Remove  Removal
	SignIn  []SignIn
	Keys    []Key    // environment variables the agent takes a key or token from
	Status  *Status  // how to tell whether it is signed in; nil if the maker has no command
	Logout  *Command // the maker's own sign-out; nil if there is none
	// LoginFiles are where, under $HOME, the maker keeps its own login, for the person to clean
	// up when there is no sign-out command (or it couldn't run).
	LoginFiles []string
	// SignoutNote tells the person how to sign the agent out when quired can't: no logout
	// command, or one that needs a choice made in Terminal.
	SignoutNote string
}

// OnlyKey reports whether every way to sign the agent in is a key Quire stores, so deleting
// Quire's key file signs it out.
func (s *Setup) OnlyKey() bool {
	if s == nil || len(s.SignIn) == 0 {
		return false
	}
	for _, m := range s.SignIn {
		if m.Kind != KindKey {
			return false
		}
	}
	return true
}

// MakerLogin reports whether the agent has a sign-in of its maker's own (a login command or
// ACP's authenticate), which Quire's key file doesn't cover.
func (s *Setup) MakerLogin() bool {
	if s == nil {
		return false
	}
	for _, m := range s.SignIn {
		switch m.Kind {
		case KindDevice, KindPaste, KindLink, KindACP:
			return true
		}
	}
	return false
}

// Step is one command of a recipe.
type Step struct {
	Title  string
	Run    Command
	Source string // where the command comes from, shown before it runs
}

// Command is a fixed command line from the catalog. Request data is never put into one.
//
// Argv runs directly; BinToken and HomeToken in it are replaced by the agent's binary and
// $HOME. Shell is a pipeline exactly as the maker documents it (`curl … | bash`), run with
// `bash -o pipefail -c`, so what the person reads is what runs.
type Command struct {
	Argv  []string
	Shell string
	Env   []string // added to the environment
}

// Placeholders in Command.Argv.
const (
	BinToken  = "{bin}"
	HomeToken = "{home}"
)

// Shown is the command as the person reads it, before and while it runs.
func (c Command) Shown(bin, home string) string {
	if c.Shell != "" {
		return strings.TrimSpace(strings.Join(c.Env, " ") + " " + c.Shell)
	}
	argv := c.Resolve(bin, home)
	if len(argv) > 0 && bin != "" && argv[0] == bin {
		argv[0] = shortBin(bin, home)
	}
	parts := append(append([]string{}, c.Env...), argv...)
	for i, p := range parts {
		if strings.ContainsAny(p, " \t\"'$") {
			parts[i] = "'" + strings.ReplaceAll(p, "'", `'\''`) + "'"
		}
	}
	return strings.Join(parts, " ")
}

func shortBin(bin, home string) string {
	if home != "" && strings.HasPrefix(bin, home+"/") {
		return "~/" + strings.TrimPrefix(bin, home+"/")
	}
	return bin
}

// Resolve returns Argv with the placeholders replaced.
func (c Command) Resolve(bin, home string) []string {
	out := make([]string, len(c.Argv))
	for i, a := range c.Argv {
		a = strings.ReplaceAll(a, BinToken, bin)
		out[i] = strings.ReplaceAll(a, HomeToken, home)
	}
	return out
}

// NeedsBin reports whether the command runs the agent's own binary, which must be installed.
func (c Command) NeedsBin() bool {
	for _, a := range c.Argv {
		if strings.Contains(a, BinToken) {
			return true
		}
	}
	return false
}

// Removal is how an agent is removed: the maker's own command if there is one, else the paths
// its installer made (relative to $HOME). Settings are the agent's own settings and history,
// removed only when the person asks.
type Removal struct {
	Run      *Command
	Paths    []string
	Settings []string
}

// Sign-in kinds, as the wizard shows them.
const (
	KindDevice = "device" // the agent prints a URL and a one-time code to enter there
	KindPaste  = "paste"  // the agent prints a URL; the page shows a code to paste back
	KindLink   = "link"   // the agent prints a URL and waits; nothing to copy
	KindKey    = "key"    // an API key or token, stored by quired for this agent only
	KindACP    = "acp"    // the agent's own ACP authMethods (authenticate)
	KindNone   = "none"   // nothing to sign in to
)

// SignIn is one way to sign an agent in. Run is set for the kinds that run a login command.
// Code, for a paste-back login, is the shape of the code its prompt accepts.
type SignIn struct {
	ID    string
	Kind  string
	Label string
	Run   Command
	Code  *CodeShape
}

// CodeShape is what a paste-back prompt accepts: Pattern, a regular expression the pasted text
// (trimmed) must match. Other text is refused with Hint, which says what to paste instead,
// before it reaches the prompt: Claude Code's prompt only prints an error for it and keeps
// waiting (ANAL-395).
type CodeShape struct {
	Pattern string
	Hint    string
}

// Key is an environment variable an agent reads a key or token from.
type Key struct {
	Name  string
	Label string
}

// Status runs a command and matches its output: Yes means signed in, No means not; neither (or
// a failure to run) means quired can't tell.
type Status struct {
	Run Command
	Yes string
	No  string
}

// DebianAllowlist is every Debian package the admin worker installs, for any recipe. It
// refuses all others.
var DebianAllowlist = []string{"ca-certificates", "curl", "git", "tar", "xz-utils", "unzip", "libatomic1", "nodejs", "npm"}

// FindSignIn returns the agent's sign-in method id.
func (s *Setup) FindSignIn(id string) (SignIn, bool) {
	if s == nil {
		return SignIn{}, false
	}
	for _, m := range s.SignIn {
		if m.ID == id {
			return m, true
		}
	}
	return SignIn{}, false
}

// HasKey reports whether name is one of the agent's key variables.
func (s *Setup) HasKey(name string) bool {
	if s == nil {
		return false
	}
	for _, k := range s.Keys {
		if k.Name == name {
			return true
		}
	}
	return false
}
