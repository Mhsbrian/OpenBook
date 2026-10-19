// Package agents knows which coding agents quired can drive, how to start each one, and how to
// find the ones installed on this machine.
package agents

import (
	"bytes"
	"context"
	"os/exec"
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
	GrokHeadless   Protocol = "grok-headless"
	AgyStream      Protocol = "agy-stream"
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
}

// Catalog lists the agents quired knows, in display order.
var Catalog = []Spec{
	{ID: "claude", Name: "Claude Code", Binaries: []string{"claude"}, Protocol: ClaudeStream,
		Checked: "2.1.301", Note: "adapted: print mode, stream-json; resumes with --resume"},
	{ID: "opencode", Name: "opencode", Binaries: []string{"opencode"}, Protocol: ACP, Args: []string{"acp"}, Checked: "2.0.31"},
	{ID: "copilot", Name: "GitHub Copilot CLI", Binaries: []string{"copilot"}, Protocol: ACP, Args: []string{"--acp"}, Checked: "1.0.98"},
	{ID: "cursor", Name: "Cursor Agent", Binaries: []string{"cursor-agent"}, Protocol: ACP, Args: []string{"acp"}, Checked: "2026.10.14"},
	{ID: "kimi", Name: "Kimi Code", Binaries: []string{"kimi"}, Protocol: ACP, Args: []string{"acp"}, Checked: "2.2.0"},
	{ID: "hermes", Name: "Hermes Agent", Binaries: []string{"hermes"}, Protocol: ACP, Args: []string{"acp"}, Checked: "0.20.5"},
	{ID: "omp", Name: "Oh My Pi", Binaries: []string{"omp"}, Protocol: ACP, Args: []string{"acp"}, Checked: "18.11.2"},
	{ID: "gemini", Name: "Gemini CLI", Binaries: []string{"gemini"}, Protocol: ACP, Args: []string{"--experimental-acp"},
		Note: "not installed on the test host; the ACP flag is unverified"},
	{ID: "grok", Name: "Grok CLI", Binaries: []string{"grok"}, Protocol: GrokHeadless, Checked: "1.0.62",
		Note: "no ACP server; headless --output-format streaming-json emits ACP session updates (adapter planned)"},
	{ID: "codex", Name: "Codex CLI", Binaries: []string{"codex"}, Protocol: CodexAppServer, Checked: "0.163.0",
		Note: "speaks its own JSON-RPC (codex app-server); adapter planned"},
	{ID: "antigravity", Name: "Antigravity CLI", Binaries: []string{"agy", "antigravity"}, Protocol: AgyStream, Checked: "1.4.0",
		Note: "print mode with stream-json; adapter planned"},
	{ID: "pi", Name: "Pi", Binaries: []string{"pi"}, Protocol: None, Checked: "1.3.0",
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
var HostEnv = Env{LookPath: exec.LookPath, Version: runVersion}

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
