// Package agents knows which coding agents quired can drive, how to start each one, how to
// find the ones installed on this machine, and how to install, update, remove and sign in each
// one (setup.go).
package agents

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

// Protocol is how quired talks to an agent.
type Protocol string

const (
	// ACP: the agent is an Agent Client Protocol server on stdio. No adapter needed.
	ACP Protocol = "acp"
	// ClaudeStream: Claude Code's print mode with --output-format stream-json, adapted to ACP by
	// package harness.
	ClaudeStream Protocol = "claude-stream"
	// Planned protocols: recognised, but quired has no adapter yet.
	CodexAppServer Protocol = "codex-app-server"
	None           Protocol = "none"
)

// Supported reports whether quired can run agents that speak p.
func (p Protocol) Supported() bool { return p == ACP || p == ClaudeStream }

// Spec describes one agent CLI.
type Spec struct {
	ID       string   `json:"id"`
	Name     string   `json:"name"`
	Binaries []string `json:"binaries"` // the first one found on PATH wins
	Protocol Protocol `json:"protocol"`
	Args     []string `json:"args,omitempty"` // ACP: what starts the server; adapters: added to their own
	// Checked records the CLI version this entry was last run against, or "" if it never was.
	Checked string `json:"checked,omitempty"`
	Note    string `json:"note,omitempty"`
	// Maker and Needs are what the setup wizard's card says: who makes it, and what it takes.
	Maker string `json:"maker,omitempty"`
	Needs string `json:"needs,omitempty"`
	// Setup is how quired installs, updates, removes and signs in this agent; nil if it can't.
	Setup *Setup `json:"-"`
}

// Recipe sources were read on 2026-11-06 (docs/quire-setup.md §5). Where a fact rests on an
// agent's own --help, the version is the one installed on the OpenBook dev host then.
const recipesChecked = "2026-11-06"

// Script installers fetch the maker's script with curl, as the maker documents; Debian's curl and
// CA certificates come from the admin worker first (setup.go, DebianAllowlist).
var scriptDeps = []string{"ca-certificates", "curl"}

// claudeCode is the code Claude Code's `auth login` reads (2.1.319): two parts joined by #, the
// first two of which must not be empty (it splits the line on # and checks both). Anything else
// gets "Invalid code. Please make sure the full code was copied." and the prompt waits on.
var claudeCode = &CodeShape{Pattern: `^[^#]+#[^#]`,
	Hint: "That isn't the whole code. Claude's code has two parts joined by #. Copy it with the button on the sign-in page, then paste it here."}

// Catalog lists the agents quired knows, in display order.
var Catalog = []Spec{
	{ID: "claude", Name: "Claude Code", Maker: "Anthropic", Needs: "A Claude plan or an API key",
		Binaries: []string{"claude"}, Protocol: ClaudeStream, Checked: "2.1.318",
		Note: "adapted: print mode, stream-json; resumes with --resume",
		Setup: &Setup{
			Source: "https://code.claude.com/docs/en/setup",
			Debian: scriptDeps,
			Install: []Step{{Title: "Install Claude Code with Anthropic's installer",
				Run: Command{Shell: "curl -fsSL https://claude.ai/install.sh | bash"}, Source: "https://code.claude.com/docs/en/setup"}},
			Update: []Step{{Title: "Update Claude Code", Run: Command{Argv: []string{BinToken, "update"}}}},
			Remove: Removal{Paths: []string{".local/bin/claude", ".local/share/claude"}, Settings: []string{".claude", ".claude.json"}},
			SignIn: []SignIn{
				{ID: "claude-ai", Kind: KindPaste, Label: "Claude account", Run: Command{Argv: []string{BinToken, "auth", "login", "--claudeai"}}, Code: claudeCode},
				{ID: "console", Kind: KindPaste, Label: "Anthropic Console", Run: Command{Argv: []string{BinToken, "auth", "login", "--console"}}, Code: claudeCode},
				{ID: "key", Kind: KindKey, Label: "Anthropic API key"},
			},
			Keys:   []Key{{Name: "ANTHROPIC_API_KEY", Label: "Anthropic API key"}},
			Status: &Status{Run: Command{Argv: []string{BinToken, "auth", "status", "--json"}}, Yes: `"loggedIn"\s*:\s*true`, No: `"loggedIn"\s*:\s*false|[Nn]ot logged in`},
			Logout: &Command{Argv: []string{BinToken, "auth", "logout"}}, // local --help 2.1.318
			// Where Claude Code keeps its login on Linux: unconfirmed which file.
			LoginFiles: []string{".claude", ".claude.json"},
		}},
	{ID: "opencode", Name: "opencode", Maker: "Open source", Needs: "Free models, no account",
		Binaries: []string{"opencode"}, Protocol: ACP, Args: []string{"acp"}, Checked: "2.2.5",
		Setup: &Setup{
			Source: "https://opencode.ai/v2/docs",
			Debian: scriptDeps,
			// opencode.ai/install installs v1; v2 has its own script.
			Install: []Step{{Title: "Install opencode with its installer",
				Run: Command{Shell: "curl -fsSL https://opencode.ai/v2/install | bash -s -- --no-modify-path"}, Source: "https://opencode.ai/v2/install"}},
			Update: []Step{{Title: "Update opencode", Run: Command{Argv: []string{BinToken, "upgrade"}}}},
			Remove: Removal{Run: &Command{Argv: []string{BinToken, "uninstall"}}, Paths: []string{".opencode/bin/opencode"},
				Settings: []string{".config/opencode", ".local/share/opencode"}},
			SignIn: []SignIn{{ID: "none", Kind: KindNone, Label: "Free models, no account"}},
			// `opencode auth logout` exists (local --help 2.2.5) but opens a picker without an account
			// named, so quired doesn't run it. Where v2 keeps providers' logins: unconfirmed.
			LoginFiles:  []string{".local/share/opencode"},
			SignoutNote: "opencode's free models use no account. Providers you added in opencode itself stay; remove them in Terminal with `opencode auth logout`.",
		}},
	{ID: "copilot", Name: "GitHub Copilot CLI", Maker: "GitHub", Needs: "A GitHub account with Copilot",
		Binaries: []string{"copilot"}, Protocol: ACP, Args: []string{"--acp"}, Checked: "1.0.106",
		Setup: &Setup{
			Source: "https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli",
			Debian: scriptDeps,
			Install: []Step{{Title: "Install Copilot CLI with GitHub's installer",
				Run: Command{Shell: "curl -fsSL https://gh.io/copilot-install | bash"}, Source: "https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli"}},
			Update: []Step{{Title: "Update Copilot CLI", Run: Command{Argv: []string{BinToken, "update"}}}},
			Remove: Removal{Paths: []string{".local/bin/copilot"}, Settings: []string{".copilot"}},
			SignIn: []SignIn{
				// Its default on a desktop waits on a local port; the device code works from Android's browser.
				{ID: "device", Kind: KindDevice, Label: "GitHub account", Run: Command{Argv: []string{BinToken, "login", "--device-code"}}},
				{ID: "key", Kind: KindKey, Label: "Fine-grained token"},
			},
			Keys: []Key{{Name: "COPILOT_GITHUB_TOKEN", Label: "GitHub fine-grained token with Copilot Requests"}},
			// No logout command (local --help 1.0.106). Without a system keychain its token is "stored
			// in a plain text config file under ~/.copilot/" (copilot login --help).
			LoginFiles:  []string{".copilot"},
			SignoutNote: "Copilot CLI has no sign-out command. To sign it out, delete ~/.copilot in Terminal (rm -r ~/.copilot), which also deletes its settings and sessions, and revoke its access in GitHub's settings (github.com/settings/applications).",
		}},
	{ID: "antigravity", Name: "Antigravity CLI", Maker: "Google", Needs: "A Google account",
		Binaries: []string{"agy", "antigravity"}, Protocol: ACP, Args: []string{"acp"}, Checked: "1.5.2",
		Note: "ACP server (agy acp); signs in through ACP's authenticate",
		Setup: &Setup{
			Source: "https://antigravity.google/docs/getting-started",
			Debian: scriptDeps,
			Install: []Step{{Title: "Install Antigravity CLI with Google's installer",
				Run: Command{Shell: "curl -fsSL https://antigravity.google/cli/install.sh | bash"}, Source: "https://antigravity.google/docs/getting-started"}},
			Update: []Step{{Title: "Update Antigravity CLI", Run: Command{Argv: []string{BinToken, "update"}}}},
			Remove: Removal{Paths: []string{".local/bin/agy"}, Settings: []string{".gemini/antigravity-cli"}},
			// No login command or flag that forces a code flow; its ACP server offers authMethods.
			SignIn: []SignIn{{ID: "acp", Kind: KindACP, Label: "Google account"}},
			// No logout subcommand (local --help 1.5.2). Its application data folder defaults to
			// ~/.gemini/antigravity-cli (agy acp --help); which file holds the login: unconfirmed.
			LoginFiles:  []string{".gemini/antigravity-cli"},
			SignoutNote: "Antigravity CLI has no sign-out command. To sign it out, delete ~/.gemini/antigravity-cli in Terminal (rm -r ~/.gemini/antigravity-cli), which also deletes its conversations and settings, and remove its access in your Google Account (myaccount.google.com/connections).",
		}},
	{ID: "gemini", Name: "Gemini CLI", Maker: "Google", Needs: "A Gemini API key",
		Binaries: []string{"gemini"}, Protocol: ACP, Args: []string{"--acp"},
		Note: "the ACP flag is from Gemini CLI's docs (geminicli.com/docs/cli/acp-mode); not yet run",
		Setup: &Setup{
			Source: "https://www.geminicli.com/docs/get-started/installation",
			Debian: []string{"nodejs", "npm"},
			Install: []Step{{Title: "Install Gemini CLI from npm",
				Run: Command{Argv: []string{"npm", "install", "-g", "--prefix", HomeToken + "/.local", "@google/gemini-cli"}}, Source: "https://www.geminicli.com/docs/get-started/installation"}},
			Update: []Step{{Title: "Update Gemini CLI", Run: Command{Argv: []string{"npm", "install", "-g", "--prefix", HomeToken + "/.local", "@google/gemini-cli@latest"}}}},
			Remove: Removal{Run: &Command{Argv: []string{"npm", "uninstall", "-g", "--prefix", HomeToken + "/.local", "@google/gemini-cli"}}, Settings: []string{".gemini"}},
			// Free-tier Google sign-in moved to Antigravity CLI on 2026-06-18 (geminicli.com auth docs).
			SignIn: []SignIn{{ID: "key", Kind: KindKey, Label: "Gemini API key"}},
			Keys:   []Key{{Name: "GEMINI_API_KEY", Label: "Gemini API key"}},
			// A Google sign-in made in Terminal lives here; Quire only ever stores the key.
			LoginFiles: []string{".gemini"},
		}},
	{ID: "cursor", Name: "Cursor Agent", Maker: "Cursor", Needs: "A Cursor account",
		Binaries: []string{"cursor-agent"}, Protocol: ACP, Args: []string{"acp"}, Checked: "2026.11.05",
		Setup: &Setup{
			Source: "https://cursor.com/docs/cli/installation",
			Debian: scriptDeps,
			Install: []Step{{Title: "Install Cursor Agent with Cursor's installer",
				Run: Command{Shell: "curl https://cursor.com/install -fsS | bash"}, Source: "https://cursor.com/docs/cli/installation"}},
			Update: []Step{{Title: "Update Cursor Agent", Run: Command{Argv: []string{BinToken, "update"}}}},
			Remove: Removal{Paths: []string{".local/bin/agent", ".local/bin/cursor-agent", ".local/share/cursor-agent"}, Settings: []string{".cursor"}},
			SignIn: []SignIn{
				// Prints a link and polls; nothing to copy.
				{ID: "link", Kind: KindLink, Label: "Cursor account", Run: Command{Argv: []string{BinToken, "login"}, Env: []string{"NO_OPEN_BROWSER=1"}}},
				{ID: "key", Kind: KindKey, Label: "Cursor API key"},
			},
			Keys:   []Key{{Name: "CURSOR_API_KEY", Label: "Cursor API key"}},
			Status: &Status{Run: Command{Argv: []string{BinToken, "status", "--format", "json"}}, Yes: `"(isAuthenticated|authenticated|loggedIn)"\s*:\s*true|"email"\s*:\s*"[^"]+"`, No: `"(isAuthenticated|authenticated|loggedIn)"\s*:\s*false|[Nn]ot (logged|signed) in`},
			Logout: &Command{Argv: []string{BinToken, "logout"}}, // "Sign out and clear stored authentication" (local --help)
			// Which of these holds the login: unconfirmed.
			LoginFiles: []string{".cursor", ".config/cursor"},
		}},
	{ID: "kimi", Name: "Kimi Code", Maker: "Moonshot AI", Needs: "A Kimi account or an API key",
		Binaries: []string{"kimi"}, Protocol: ACP, Args: []string{"acp"}, Checked: "2.4.1",
		Setup: &Setup{
			Source: "https://moonshotai.github.io/kimi-code/en/guides/getting-started",
			Debian: scriptDeps,
			Install: []Step{{Title: "Install Kimi Code with its installer",
				Run: Command{Shell: "curl -fsSL https://code.kimi.com/kimi-code/install.sh | KIMI_NO_MODIFY_PATH=1 bash"}, Source: "https://moonshotai.github.io/kimi-code/en/guides/getting-started"}},
			Update: []Step{{Title: "Update Kimi Code", Run: Command{Argv: []string{BinToken, "upgrade"}}}},
			// The installer puts the binary in ~/.kimi-code/bin; ~/.kimi-code also holds its
			// config.toml and data (seen on the dev host), so only bin/ goes without the settings.
			Remove: Removal{Paths: []string{".kimi-code/bin"}, Settings: []string{".kimi-code"}},
			SignIn: []SignIn{
				{ID: "device", Kind: KindDevice, Label: "Kimi account", Run: Command{Argv: []string{BinToken, "login"}}},
				{ID: "key", Kind: KindKey, Label: "Kimi Platform API key"},
			},
			Keys: []Key{{Name: "KIMI_MODEL_API_KEY", Label: "Kimi Platform API key"}},
			// No logout command (local --help 2.4.1 lists login only). Its config lives in
			// ~/.kimi-code (config.toml on the dev host); which file holds the login: unconfirmed.
			LoginFiles:  []string{".kimi-code"},
			SignoutNote: "Kimi Code has no sign-out command. To sign it out, delete ~/.kimi-code in Terminal (rm -r ~/.kimi-code), which also deletes its settings and sessions, and Kimi Code itself when Quire installed it there.",
		}},
	{ID: "grok", Name: "Grok CLI", Maker: "xAI", Needs: "An xAI account or an API key",
		Binaries: []string{"grok"}, Protocol: ACP, Args: []string{"agent", "stdio"}, Checked: "1.0.77",
		Setup: &Setup{
			Source: "https://docs.x.ai/build/overview",
			Debian: scriptDeps,
			// The installer also links `agent`, which clashes with Cursor's; quired runs both by full name.
			Install: []Step{{Title: "Install Grok CLI with xAI's installer",
				Run: Command{Shell: "curl -fsSL https://x.ai/cli/install.sh | bash"}, Source: "https://docs.x.ai/build/overview"}},
			Update: []Step{{Title: "Update Grok CLI", Run: Command{Argv: []string{BinToken, "update"}}}},
			Remove: Removal{Paths: []string{".grok/bin"}, Settings: []string{".grok"}},
			SignIn: []SignIn{
				{ID: "device", Kind: KindDevice, Label: "xAI account", Run: Command{Argv: []string{BinToken, "login", "--device-auth"}}},
				{ID: "key", Kind: KindKey, Label: "xAI API key"},
			},
			Keys:       []Key{{Name: "XAI_API_KEY", Label: "xAI API key"}},
			Logout:     &Command{Argv: []string{BinToken, "logout"}}, // "Sign out and clear cached credentials" (local --help 1.0.77)
			LoginFiles: []string{".grok"},
		}},
	{ID: "hermes", Name: "Hermes Agent", Maker: "Nous Research", Needs: "A model provider you choose",
		Binaries: []string{"hermes"}, Protocol: ACP, Args: []string{"acp"}, Checked: "0.20.5",
		Setup: &Setup{
			Source: "https://hermes-agent.nousresearch.com/docs/getting-started/installation",
			// It calls `sudo -n` for libatomic1 itself, which can't work under NoNewPrivileges.
			Debian: []string{"ca-certificates", "curl", "git", "tar", "xz-utils", "libatomic1"},
			Install: []Step{{Title: "Install Hermes Agent with its installer",
				Run: Command{Shell: "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"}, Source: "https://hermes-agent.nousresearch.com/docs/getting-started/installation"}},
			Update: []Step{{Title: "Update Hermes Agent", Run: Command{Argv: []string{BinToken, "update"}}}},
			Remove: Removal{Run: &Command{Argv: []string{BinToken, "uninstall"}}, Paths: []string{".local/bin/hermes"}, Settings: []string{".hermes"}},
			SignIn: []SignIn{
				{ID: "portal", Kind: KindDevice, Label: "Nous Portal", Run: Command{Argv: []string{BinToken, "portal", "login"}}},
				{ID: "key", Kind: KindKey, Label: "A provider's API key"},
			},
			Keys: []Key{
				{Name: "OPENROUTER_API_KEY", Label: "OpenRouter API key"},
				{Name: "ANTHROPIC_API_KEY", Label: "Anthropic API key"},
				{Name: "OPENAI_API_KEY", Label: "OpenAI API key"},
			},
			// "Remove stored credentials and reset provider config", for the active provider (local --help 0.20.5).
			Logout:     &Command{Argv: []string{BinToken, "logout"}},
			LoginFiles: []string{".hermes"},
		}},
	{ID: "omp", Name: "Oh My Pi", Maker: "Open source", Needs: "A model provider you choose",
		Binaries: []string{"omp"}, Protocol: ACP, Args: []string{"acp"}, Checked: "18.11.2",
		Setup: &Setup{
			Source: "https://github.com/can1357/oh-my-pi",
			Debian: scriptDeps,
			Install: []Step{{Title: "Install Oh My Pi with its installer",
				Run: Command{Shell: "curl -fsSL https://omp.sh/install | sh"}, Source: "https://github.com/can1357/oh-my-pi"}},
			Update: []Step{{Title: "Update Oh My Pi", Run: Command{Argv: []string{BinToken, "update"}}}},
			Remove: Removal{Paths: []string{".local/bin/omp"}, Settings: []string{".omp"}},
			SignIn: []SignIn{
				{ID: "anthropic", Kind: KindPaste, Label: "Claude account", Run: Command{Argv: []string{BinToken, "login", "anthropic"}}},
				{ID: "key", Kind: KindKey, Label: "A provider's API key"},
			},
			Keys: []Key{
				{Name: "ANTHROPIC_API_KEY", Label: "Anthropic API key"},
				{Name: "OPENROUTER_API_KEY", Label: "OpenRouter API key"},
				{Name: "OPENAI_API_KEY", Label: "OpenAI API key"},
				{Name: "GEMINI_API_KEY", Label: "Gemini API key"},
				{Name: "XAI_API_KEY", Label: "xAI API key"},
			},
			// No logout command (local --help 18.11.2: login, auth export/import, auth-broker). Its
			// data lives in ~/.omp (agent/agent.db on the dev host); which file holds the login: unconfirmed.
			LoginFiles:  []string{".omp"},
			SignoutNote: "Oh My Pi has no sign-out command. To sign it out, delete ~/.omp in Terminal (rm -r ~/.omp), which also deletes its settings and sessions.",
		}},
	{ID: "codex", Name: "Codex CLI", Maker: "OpenAI", Needs: "A ChatGPT plan or an API key",
		Binaries: []string{"codex"}, Protocol: CodexAppServer, Checked: "0.167.0",
		Note: "speaks its own JSON-RPC (codex app-server); adapter planned"},
	{ID: "pi", Name: "Pi", Binaries: []string{"pi"}, Protocol: None, Checked: "1.5.0",
		Note: "no ACP or machine-readable stream found in --help"},
}

// Lookup finds a catalog entry by ID.
func Lookup(id string) (Spec, bool) {
	for _, s := range Catalog {
		if s.ID == id {
			return s, true
		}
	}
	return Spec{}, false
}

// Found is an agent installed on this machine.
type Found struct {
	Spec
	Path      string `json:"path"`
	Version   string `json:"version,omitempty"`
	Supported bool   `json:"supported"`
}

// Env abstracts the machine for tests.
type Env struct {
	LookPath func(file string) (string, error)
	// Version runs `path --version` and returns its first line.
	Version func(ctx context.Context, path string) (string, error)
}

// HostEnv is the real machine.
var HostEnv = Env{LookPath: LookPath, Version: runVersion}

// MakerDirs are the folders, under $HOME, that the makers' installers put agents in. They are
// searched after PATH, so an agent installed a moment ago is found without a restart.
var MakerDirs = []string{".local/bin", ".opencode/bin", ".kimi-code/bin", ".grok/bin"}

// LookPath is exec.LookPath, then the makers' folders under $HOME.
func LookPath(file string) (string, error) {
	p, err := exec.LookPath(file)
	if err == nil {
		return p, nil
	}
	home, herr := os.UserHomeDir()
	if herr != nil {
		return "", err
	}
	for _, d := range MakerDirs {
		c := filepath.Join(home, d, file)
		if fi, serr := os.Stat(c); serr == nil && fi.Mode().IsRegular() && fi.Mode().Perm()&0o111 != 0 {
			return c, nil
		}
	}
	return "", err
}

// PathWithMakerDirs returns path with the makers' folders under home appended, for commands
// quired starts.
func PathWithMakerDirs(path, home string) string {
	parts := []string{}
	if path != "" {
		parts = strings.Split(path, string(os.PathListSeparator))
	}
	have := map[string]bool{}
	for _, p := range parts {
		have[p] = true
	}
	for _, d := range MakerDirs {
		if p := filepath.Join(home, d); !have[p] {
			parts = append(parts, p)
		}
	}
	return strings.Join(parts, string(os.PathListSeparator))
}

func runVersion(ctx context.Context, path string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, path, "--version")
	var out bytes.Buffer
	cmd.Stdout = &out
	cmd.Stderr = &out
	cmd.Stdin = nil
	err := cmd.Run()
	line, _, _ := strings.Cut(strings.TrimSpace(out.String()), "\n")
	return strings.TrimSpace(line), err
}

// Discover finds the catalog's agents on this machine. It never starts an agent session: it
// only resolves binaries and asks each for its version.
func Discover(ctx context.Context, env Env) []Found {
	var (
		mu    sync.Mutex
		found []Found
		wg    sync.WaitGroup
		order = map[string]int{}
	)
	for i, s := range Catalog {
		order[s.ID] = i
		for _, bin := range s.Binaries {
			path, err := env.LookPath(bin)
			if err != nil {
				continue
			}
			wg.Add(1)
			go func(s Spec, path string) {
				defer wg.Done()
				v, _ := env.Version(ctx, path)
				mu.Lock()
				found = append(found, Found{Spec: s, Path: path, Version: v, Supported: s.Protocol.Supported()})
				mu.Unlock()
			}(s, path)
			break
		}
	}
	wg.Wait()
	sort.Slice(found, func(i, j int) bool { return order[found[i].ID] < order[found[j].ID] })
	return found
}
