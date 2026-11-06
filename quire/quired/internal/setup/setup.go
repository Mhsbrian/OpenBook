// Package setup is quired's side of Quire's setup wizard (docs/quire-setup.md §4.2): it lists
// the agents Quire can install, installs, updates and removes them with their makers' own
// installers, runs their sign-in on a terminal, and keeps their API keys.
//
// Everything runs as quired's own user, under quired.service's NoNewPrivileges: no step can
// gain root. Debian prerequisites come from the admin worker (`quired admin`), which Quire core
// asks before it asks for an install. Every command is fixed in the catalog; request data is
// only ever an agent id, a method id, a job id, or the text of a login's input or a key, never
// part of a command line.
//
// The methods are ACP extension methods of `quired serve`:
//
//	_quire/catalog     {}                               → {"quired", "agents": [CatalogAgent...]}
//	_quire/install     {"agent", "job"}                 → {"version", "path"}     (+ _quire/progress)
//	_quire/update      {"agent", "job"}                 → {"version", "path"}     (+ _quire/progress)
//	_quire/remove      {"agent", "job", "settings"}     → {"removed": [...]}      (+ _quire/progress)
//	_quire/login       {"agent", "method", "job"}       → {"signedIn"}            (+ _quire/login/prompt)
//	_quire/login/input {"job", "text"}                  → {"answer": [...]}
//	_quire/key         {"agent", "name", "value"}       → {}
//	_quire/signout     {"agent"}                        → {"ran", "removed"}
//	_quire/signin      {"agent"}                        → {"signedIn", "detail"}
//	_quire/cancel      {"job"}                          → {}
//
// A failed job is a JSON-RPC error whose data is {"step", "output"} (the last lines, redacted);
// a cancelled one has code CodeCancelled. _quire/login/input refuses a code that isn't the shape
// the agent's prompt accepts (its message says what to paste), and answers with the lines the
// agent printed after it, redacted: its own word on the code while the login runs on.
package setup

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/Mhsbrian/OpenBook/quire/quired/internal/acp"
	"github.com/Mhsbrian/OpenBook/quire/quired/internal/agents"
)

// The methods.
const (
	MethodCatalog     = "_quire/catalog"
	MethodInstall     = "_quire/install"
	MethodUpdate      = "_quire/update"
	MethodRemove      = "_quire/remove"
	MethodLogin       = "_quire/login"
	MethodLoginInput  = "_quire/login/input"
	MethodKey         = "_quire/key"
	MethodSignout     = "_quire/signout"
	MethodSignin      = "_quire/signin"
	MethodCancel      = "_quire/cancel"
	NotifyProgress    = "_quire/progress"
	NotifyLoginPrompt = "_quire/login/prompt"
)

// Methods are the methods Handle answers, for initialize's _meta.
var Methods = []string{MethodCatalog, MethodInstall, MethodUpdate, MethodRemove, MethodLogin, MethodLoginInput,
	MethodKey, MethodSignout, MethodSignin, MethodCancel}

// CredentialsChanged reports whether a setup call changed agent's credentials, so quired must
// stop the agent's running processes: a key stored, a login that finished, or any sign-out (it
// may have removed the key file even if the maker's logout then failed).
func CredentialsChanged(method string, params json.RawMessage, err error) (agent string, changed bool) {
	switch method {
	case MethodSignout:
	case MethodKey, MethodLogin:
		if err != nil {
			return "", false
		}
	default:
		return "", false
	}
	var p struct {
		Agent string `json:"agent"`
	}
	if json.Unmarshal(params, &p) != nil || p.Agent == "" {
		return "", false
	}
	return p.Agent, true
}

// CodeCancelled is the error code of a job that was cancelled (LSP's RequestCancelled).
const CodeCancelled = -32800

// Deadlines bound each kind of job.
type Deadlines struct {
	Step   time.Duration // each install or update step
	Remove time.Duration
	Login  time.Duration
	Status time.Duration
	Answer time.Duration // how long _quire/login/input waits for the agent's answer
}

// DefaultDeadlines are generous: a maker's installer on a slow connection, a person finding
// their password.
var DefaultDeadlines = Deadlines{Step: 15 * time.Minute, Remove: 5 * time.Minute, Login: 10 * time.Minute, Status: 30 * time.Second,
	Answer: 3 * time.Second}

// Service answers the setup methods.
type Service struct {
	Home     string
	Version  string // quired's
	Catalog  []agents.Spec
	Discover func(context.Context) []agents.Found
	// Missing returns the Debian packages of pkgs that aren't installed. Default: dpkg-query.
	Missing   func(ctx context.Context, pkgs []string) []string
	Deadlines Deadlines
	KillGrace time.Duration // between SIGTERM and SIGKILL; default 3 s
	Log       *log.Logger

	mu   sync.Mutex
	jobs map[string]*job
	busy map[string]string // agent → the job working on it
}

// Notifier sends a notification to the client that asked.
type Notifier func(method string, params any)

func (s *Service) killGrace() time.Duration {
	if s.KillGrace > 0 {
		return s.KillGrace
	}
	return 3 * time.Second
}

func (s *Service) deadlines() Deadlines {
	d := s.Deadlines
	if d.Step == 0 {
		d.Step = DefaultDeadlines.Step
	}
	if d.Remove == 0 {
		d.Remove = DefaultDeadlines.Remove
	}
	if d.Login == 0 {
		d.Login = DefaultDeadlines.Login
	}
	if d.Answer == 0 {
		d.Answer = DefaultDeadlines.Answer
	}
	if d.Status == 0 {
		d.Status = DefaultDeadlines.Status
	}
	return d
}

func (s *Service) catalog() []agents.Spec {
	if s.Catalog != nil {
		return s.Catalog
	}
	return agents.Catalog
}

func (s *Service) logf(format string, args ...any) {
	if s.Log != nil {
		s.Log.Printf(format, args...)
	}
}

func (s *Service) keys() Keys { return Keys{Home: s.Home} }

// KeyEnv is what quired adds to agent's environment when it starts it: that agent's keys only.
func (s *Service) KeyEnv(agent string) []string {
	env, err := s.keys().Env(agent)
	if err != nil {
		s.logf("keys: %s: %v", agent, err)
		return nil
	}
	return env
}

// Handle answers method if it is one of the setup methods; ok is false otherwise.
func (s *Service) Handle(ctx context.Context, method string, params json.RawMessage, notify Notifier) (res any, err error, ok bool) {
	switch method {
	case MethodCatalog:
		return s.list(ctx), nil, true
	case MethodInstall, MethodUpdate:
		var p jobParams
		if err := decode(params, &p); err != nil {
			return nil, err, true
		}
		res, err := s.install(ctx, p, method == MethodUpdate, notify)
		return res, err, true
	case MethodRemove:
		var p jobParams
		if err := decode(params, &p); err != nil {
			return nil, err, true
		}
		res, err := s.remove(ctx, p, notify)
		return res, err, true
	case MethodLogin:
		var p jobParams
		if err := decode(params, &p); err != nil {
			return nil, err, true
		}
		res, err := s.login(ctx, p, notify)
		return res, err, true
	case MethodLoginInput:
		var p struct {
			Job  string `json:"job"`
			Text string `json:"text"`
		}
		if err := decode(params, &p); err != nil {
			return nil, err, true
		}
		res, err := s.input(p.Job, p.Text)
		return res, err, true
	case MethodKey:
		var p struct {
			Agent string `json:"agent"`
			Name  string `json:"name"`
			Value string `json:"value"`
		}
		if err := decode(params, &p); err != nil {
			return nil, err, true
		}
		return struct{}{}, s.setKey(p.Agent, p.Name, p.Value), true
	case MethodSignout:
		var p jobParams
		if err := decode(params, &p); err != nil {
			return nil, err, true
		}
		res, err := s.signout(ctx, p.Agent)
		return res, err, true
	case MethodSignin:
		var p jobParams
		if err := decode(params, &p); err != nil {
			return nil, err, true
		}
		res, err := s.signin(ctx, p.Agent)
		return res, err, true
	case MethodCancel:
		var p jobParams
		if err := decode(params, &p); err != nil {
			return nil, err, true
		}
		return struct{}{}, s.cancelJob(p.Job), true
	}
	return nil, nil, false
}

type jobParams struct {
	Agent    string `json:"agent"`
	Job      string `json:"job"`
	Method   string `json:"method"`
	Settings bool   `json:"settings"`
}

func decode(params json.RawMessage, v any) error {
	if len(params) == 0 {
		params = []byte("{}")
	}
	if err := json.Unmarshal(params, v); err != nil {
		return acp.Errorf(acp.CodeInvalidParams, "%v", err)
	}
	return nil
}

// ---- the catalog ----

// CatalogAgent is one row of _quire/catalog.
type CatalogAgent struct {
	ID        string       `json:"id"`
	Name      string       `json:"name"`
	Maker     string       `json:"maker,omitempty"`
	Needs     string       `json:"needs,omitempty"`
	Supported bool         `json:"supported"`
	Installed bool         `json:"installed"`
	Path      string       `json:"path,omitempty"`
	Version   string       `json:"version,omitempty"`
	SignIn    []SignInInfo `json:"signin"`
	Keys      []KeyInfo    `json:"keys"`
	HasKey    bool         `json:"hasKey"`
	Recipe    Recipe       `json:"recipe"`
	Checked   string       `json:"checked,omitempty"`
	Note      string       `json:"note,omitempty"`
}

type SignInInfo struct {
	ID    string `json:"id"`
	Kind  string `json:"kind"`
	Label string `json:"label"`
}

type KeyInfo struct {
	Name  string `json:"name"`
	Label string `json:"label"`
}

// Recipe is what the wizard shows before Install: the Debian packages and every command.
type Recipe struct {
	Debian []string     `json:"debian"`
	Steps  []RecipeStep `json:"steps"`
}

type RecipeStep struct {
	Title   string `json:"title"`
	Command string `json:"command"`
	Source  string `json:"source,omitempty"`
}

type catalogResult struct {
	Quired string         `json:"quired"`
	Agents []CatalogAgent `json:"agents"`
}

func (s *Service) list(ctx context.Context) catalogResult {
	found := map[string]agents.Found{}
	for _, f := range s.Discover(ctx) {
		found[f.ID] = f
	}
	out := catalogResult{Quired: s.Version, Agents: []CatalogAgent{}}
	for _, spec := range s.catalog() {
		f, installed := found[spec.ID]
		a := CatalogAgent{ID: spec.ID, Name: spec.Name, Maker: spec.Maker, Needs: spec.Needs, Supported: spec.Protocol.Supported(),
			Installed: installed, SignIn: []SignInInfo{}, Keys: []KeyInfo{}, Recipe: Recipe{Debian: []string{}, Steps: []RecipeStep{}},
			Checked: recipesCheckedFor(spec), Note: spec.Note}
		if installed {
			a.Path, a.Version = f.Path, f.Version
		}
		if st := spec.Setup; st != nil {
			for _, m := range st.SignIn {
				a.SignIn = append(a.SignIn, SignInInfo{ID: m.ID, Kind: m.Kind, Label: m.Label})
			}
			for _, k := range st.Keys {
				a.Keys = append(a.Keys, KeyInfo{Name: k.Name, Label: k.Label})
			}
			a.Recipe.Debian = append(a.Recipe.Debian, st.Debian...)
			for _, step := range st.Install {
				a.Recipe.Steps = append(a.Recipe.Steps, RecipeStep{Title: step.Title, Command: step.Run.Shown(a.Path, s.Home), Source: step.Source})
			}
			a.HasKey = s.keys().Has(spec.ID)
		}
		out.Agents = append(out.Agents, a)
	}
	return out
}

func recipesCheckedFor(spec agents.Spec) string {
	if spec.Setup == nil {
		return ""
	}
	return "2026-11-06"
}

// ---- jobs ----

var jobID = regexp.MustCompile(`^[A-Za-z0-9._:-]{1,64}$`)

func (s *Service) spec(id string) (agents.Spec, error) {
	for _, sp := range s.catalog() {
		if sp.ID == id {
			return sp, nil
		}
	}
	return agents.Spec{}, acp.Errorf(acp.CodeInvalidParams, "quired doesn't know an agent %q", id)
}

func (s *Service) installed(ctx context.Context, id string) (agents.Found, bool) {
	for _, f := range s.Discover(ctx) {
		if f.ID == id {
			return f, true
		}
	}
	return agents.Found{}, false
}

// start registers a job for agent, one at a time per agent.
func (s *Service) start(ctx context.Context, id, agent, kind string) (*job, context.Context, error) {
	if !jobID.MatchString(id) {
		return nil, nil, acp.Errorf(acp.CodeInvalidParams, "a job needs an id of letters, digits and ._:-")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.jobs == nil {
		s.jobs, s.busy = map[string]*job{}, map[string]string{}
	}
	if _, ok := s.jobs[id]; ok {
		return nil, nil, acp.Errorf(acp.CodeInvalidParams, "job %s is already running", id)
	}
	if other, ok := s.busy[agent]; ok {
		return nil, nil, acp.Errorf(acp.CodeInvalidRequest, "%s is busy with job %s", agent, other)
	}
	jctx, cancel := context.WithCancel(ctx)
	j := &job{id: id, agent: agent, kind: kind, cancel: cancel, red: &redactor{}, log: s.openLog(agent, kind)}
	s.jobs[id], s.busy[agent] = j, id
	return j, jctx, nil
}

func (s *Service) finish(j *job) {
	j.cancel()
	j.log.close()
	s.mu.Lock()
	delete(s.jobs, j.id)
	if s.busy[j.agent] == j.id {
		delete(s.busy, j.agent)
	}
	s.mu.Unlock()
}

func (s *Service) cancelJob(id string) error {
	s.mu.Lock()
	j := s.jobs[id]
	s.mu.Unlock()
	if j == nil {
		return acp.Errorf(acp.CodeInvalidParams, "no job %s is running", id)
	}
	j.cancel()
	return nil
}

// inputResult is what the agent printed after a login's input: an error, or the next thing to
// do, which the wizard shows under the field.
type inputResult struct {
	Answer []string `json:"answer"`
}

// maxAnswer is how many of the agent's lines the wizard gets back: enough for an error and the
// prompt after it.
const maxAnswer = 4

func (s *Service) input(id, text string) (any, error) {
	if len(text) == 0 || len(text) > 4096 || strings.ContainsAny(text, "\x00\r\n") {
		return nil, acp.Errorf(acp.CodeInvalidParams, "the input must be one line of at most 4096 characters")
	}
	s.mu.Lock()
	j := s.jobs[id]
	s.mu.Unlock()
	if j == nil || j.kind != "login" {
		return nil, acp.Errorf(acp.CodeInvalidParams, "no login %s is running", id)
	}
	j.mu.Lock()
	code, hint := j.code, j.hint
	j.mu.Unlock()
	if code != nil && !code.MatchString(strings.TrimSpace(text)) {
		j.log.printf("(input refused: not the code's shape, %d characters)", len(text))
		s.logf("setup: login %s: input refused, not the code's shape", j.agent)
		return nil, acp.Errorf(acp.CodeInvalidParams, "%s", hint)
	}
	from, err := j.write(text)
	if err != nil {
		return nil, acp.Errorf(acp.CodeInvalidRequest, "%v", err)
	}
	j.log.printf("(input written, %d characters)", len(text))
	answer := j.answer(from, s.deadlines().Answer, 300*time.Millisecond)
	if len(answer) > maxAnswer {
		answer = answer[len(answer)-maxAnswer:]
	}
	// The journal says whether the agent answered, never what: that is in the job's own log.
	s.logf("setup: login %s: input written, %d lines back", j.agent, len(answer))
	return inputResult{Answer: answer}, nil
}

// failed is a job's error for the client: what failed, and the last lines of its output.
func failed(j *job, step int, title string, err error) error {
	if errors.Is(err, ErrCancelled) {
		return &acp.RPCError{Code: CodeCancelled, Message: "cancelled"}
	}
	data, _ := json.Marshal(map[string]any{"step": step, "output": j.output()})
	msg := err.Error()
	var ee *exec.ExitError
	if errors.As(err, &ee) {
		msg = fmt.Sprintf("exit status %d", ee.ExitCode())
	}
	if title != "" {
		msg = title + ": " + msg
	}
	return &acp.RPCError{Code: acp.CodeInternalError, Message: msg, Data: data}
}

type progress struct {
	Job   string `json:"job"`
	Agent string `json:"agent"`
	Step  int    `json:"step"`
	Steps int    `json:"steps"`
	Title string `json:"title"`
	Line  string `json:"line,omitempty"`
}

type installResult struct {
	Version string `json:"version"`
	Path    string `json:"path"`
}

func (s *Service) missing(ctx context.Context, pkgs []string) []string {
	if len(pkgs) == 0 {
		return nil
	}
	if s.Missing != nil {
		return s.Missing(ctx, pkgs)
	}
	var out []string
	for _, p := range pkgs {
		b, err := exec.CommandContext(ctx, "dpkg-query", "-W", "-f=${Status}", p).Output()
		if err != nil || !strings.Contains(string(b), "install ok installed") {
			out = append(out, p)
		}
	}
	return out
}

func (s *Service) install(ctx context.Context, p jobParams, update bool, notify Notifier) (any, error) {
	spec, err := s.spec(p.Agent)
	if err != nil {
		return nil, err
	}
	kind := map[bool]string{false: "install", true: "update"}[update]
	if spec.Setup == nil || len(spec.Setup.Install) == 0 {
		return nil, acp.Errorf(acp.CodeInvalidParams, "quired can't %s %s", kind, spec.Name)
	}
	if !spec.Protocol.Supported() {
		return nil, acp.Errorf(acp.CodeInvalidParams, "Quire can't run %s yet: %s", spec.Name, spec.Note)
	}
	steps := spec.Setup.Install
	var bin string
	if update {
		f, ok := s.installed(ctx, spec.ID)
		if !ok {
			return nil, acp.Errorf(acp.CodeInvalidRequest, "%s isn't installed", spec.Name)
		}
		bin, steps = f.Path, spec.Setup.Update
	}
	if miss := s.missing(ctx, spec.Setup.Debian); len(miss) > 0 {
		data, _ := json.Marshal(map[string]any{"missing": miss})
		return nil, &acp.RPCError{Code: acp.CodeInvalidRequest, Message: "needs Debian packages first: " + strings.Join(miss, " "), Data: data}
	}
	j, jctx, err := s.start(ctx, p.Job, spec.ID, kind)
	if err != nil {
		return nil, err
	}
	defer s.finish(j)
	s.logf("setup: %s %s (job %s)", kind, spec.ID, j.id)
	for i, st := range steps {
		pr := progress{Job: j.id, Agent: spec.ID, Step: i + 1, Steps: len(steps), Title: st.Title}
		notify(NotifyProgress, pr)
		sctx, cancel := context.WithTimeout(jctx, s.deadlines().Step)
		last := time.Time{}
		err := s.run(sctx, j, st.Run, bin, false, func(line string, _ []string) {
			// At most ten lines a second reach the client; the log keeps them all.
			if time.Since(last) < 100*time.Millisecond {
				return
			}
			last = time.Now()
			pr.Line = line
			notify(NotifyProgress, pr)
		})
		cancel()
		if err != nil {
			s.logf("setup: %s %s: step %d failed: %v", kind, spec.ID, i+1, err)
			if jctx.Err() != nil && !errors.Is(sctx.Err(), context.DeadlineExceeded) {
				err = ErrCancelled
			}
			return nil, failed(j, i+1, st.Title, err)
		}
	}
	f, ok := s.installed(ctx, spec.ID)
	if !ok {
		return nil, failed(j, len(steps), "", fmt.Errorf("installed, but quired can't find %s on PATH or in the makers' folders", strings.Join(spec.Binaries, " or ")))
	}
	s.logf("setup: %s %s: %s at %s", kind, spec.ID, f.Version, f.Path)
	return installResult{Version: f.Version, Path: f.Path}, nil
}

type removeResult struct {
	Removed []string `json:"removed"`
}

func (s *Service) remove(ctx context.Context, p jobParams, notify Notifier) (any, error) {
	spec, err := s.spec(p.Agent)
	if err != nil {
		return nil, err
	}
	if spec.Setup == nil {
		return nil, acp.Errorf(acp.CodeInvalidParams, "quired can't remove %s", spec.Name)
	}
	j, jctx, err := s.start(ctx, p.Job, spec.ID, "remove")
	if err != nil {
		return nil, err
	}
	defer s.finish(j)
	rm := spec.Setup.Remove
	res := removeResult{Removed: []string{}}
	if f, ok := s.installed(ctx, spec.ID); ok && rm.Run != nil {
		notify(NotifyProgress, progress{Job: j.id, Agent: spec.ID, Step: 1, Steps: 2, Title: "Remove " + spec.Name})
		rctx, cancel := context.WithTimeout(jctx, s.deadlines().Remove)
		err := s.run(rctx, j, *rm.Run, f.Path, false, func(line string, _ []string) {
			notify(NotifyProgress, progress{Job: j.id, Agent: spec.ID, Step: 1, Steps: 2, Title: "Remove " + spec.Name, Line: line})
		})
		cancel()
		if err != nil {
			if jctx.Err() != nil {
				err = ErrCancelled
			}
			return nil, failed(j, 1, "Remove "+spec.Name, err)
		}
	}
	notify(NotifyProgress, progress{Job: j.id, Agent: spec.ID, Step: 2, Steps: 2, Title: "Delete its files"})
	paths := append([]string{}, rm.Paths...)
	if p.Settings {
		paths = append(paths, rm.Settings...)
	}
	home, err := os.OpenRoot(s.Home)
	if err != nil {
		return nil, failed(j, 2, "Delete its files", err)
	}
	defer home.Close()
	for _, rel := range paths {
		rel = filepath.Clean(rel)
		if filepath.IsAbs(rel) || rel == "." || strings.HasPrefix(rel, "..") {
			continue // catalog data, but never outside $HOME
		}
		if _, err := home.Lstat(rel); err != nil {
			continue
		}
		if err := home.RemoveAll(rel); err != nil {
			return nil, failed(j, 2, "Delete ~/"+rel, err)
		}
		res.Removed = append(res.Removed, "~/"+rel)
		j.log.printf("removed ~/%s", rel)
	}
	if p.Settings {
		if path, err := s.keys().Remove(spec.ID); err == nil && path != "" {
			res.Removed = append(res.Removed, tilde(s.Home, path))
		}
	}
	s.logf("setup: removed %s: %v", spec.ID, res.Removed)
	return res, nil
}

// ---- sign-in ----

type loginPrompt struct {
	Job   string `json:"job"`
	Agent string `json:"agent"`
	Prompt
	Line string `json:"line,omitempty"`
	Done bool   `json:"done,omitempty"`
}

type signedIn struct {
	SignedIn *bool  `json:"signedIn"`
	Detail   string `json:"detail,omitempty"`
}

func boolp(b bool) *bool { return &b }

func (s *Service) login(ctx context.Context, p jobParams, notify Notifier) (any, error) {
	spec, err := s.spec(p.Agent)
	if err != nil {
		return nil, err
	}
	m, ok := spec.Setup.FindSignIn(p.Method)
	if !ok {
		return nil, acp.Errorf(acp.CodeInvalidParams, "%s has no sign-in %q", spec.Name, p.Method)
	}
	switch m.Kind {
	case agents.KindDevice, agents.KindPaste, agents.KindLink:
	default:
		return nil, acp.Errorf(acp.CodeInvalidParams, "%s's %q isn't a login quired runs (kind %s)", spec.Name, m.ID, m.Kind)
	}
	f, ok := s.installed(ctx, spec.ID)
	if !ok && m.Run.NeedsBin() {
		return nil, acp.Errorf(acp.CodeInvalidRequest, "%s isn't installed", spec.Name)
	}
	var code *regexp.Regexp
	if m.Code != nil {
		if code, err = regexp.Compile(m.Code.Pattern); err != nil {
			return nil, fmt.Errorf("%s's code shape: %w", spec.Name, err)
		}
	}
	j, jctx, err := s.start(ctx, p.Job, spec.ID, "login")
	if err != nil {
		return nil, err
	}
	defer s.finish(j)
	if code != nil {
		j.mu.Lock()
		j.code, j.hint = code, m.Code.Hint
		j.mu.Unlock()
	}
	s.logf("setup: login %s %s (job %s)", spec.ID, m.ID, j.id)
	var (
		mu  sync.Mutex
		cur Prompt
	)
	lctx, cancel := context.WithTimeout(jctx, s.deadlines().Login)
	defer cancel()
	err = s.run(lctx, j, m.Run, f.Path, true, func(line string, links []string) {
		url, code, paste := detect(line, links)
		mu.Lock()
		if url != "" && cur.URL == "" {
			cur.URL = url
		} else if url != "" && betterURL(url, cur.URL) {
			cur.URL = url
		}
		if code != "" {
			cur.Code = code
		}
		if paste {
			cur.Paste = true
		}
		pr := loginPrompt{Job: j.id, Agent: spec.ID, Prompt: cur, Line: line}
		mu.Unlock()
		notify(NotifyLoginPrompt, pr)
	})
	mu.Lock()
	final := loginPrompt{Job: j.id, Agent: spec.ID, Prompt: cur, Done: true}
	mu.Unlock()
	notify(NotifyLoginPrompt, final)
	if err != nil {
		if jctx.Err() != nil && !errors.Is(lctx.Err(), context.DeadlineExceeded) {
			err = ErrCancelled
		}
		s.logf("setup: login %s: %v", spec.ID, err)
		return nil, failed(j, 1, m.Label, err)
	}
	if st, err := s.status(ctx, spec, f.Path); err == nil && st != nil {
		return signedIn{SignedIn: st}, nil
	}
	return signedIn{SignedIn: boolp(true), Detail: "the login finished"}, nil
}

func betterURL(u, cur string) bool {
	lu := strings.ToLower(u)
	lc := strings.ToLower(cur)
	score := func(s string) int {
		n := 0
		for _, w := range loginWords {
			if strings.Contains(s, w) {
				n++
			}
		}
		return n
	}
	return score(lu) > score(lc)
}

// status runs the agent's own status command, if it has one. nil means quired can't tell.
func (s *Service) status(ctx context.Context, spec agents.Spec, bin string) (*bool, error) {
	if spec.Setup == nil || spec.Setup.Status == nil || bin == "" {
		return nil, nil
	}
	st := spec.Setup.Status
	out, _ := s.capture(ctx, st.Run, bin, s.deadlines().Status)
	if st.No != "" && regexp.MustCompile(st.No).MatchString(out) {
		return boolp(false), nil
	}
	if st.Yes != "" && regexp.MustCompile(st.Yes).MatchString(out) {
		return boolp(true), nil
	}
	return nil, nil
}

func (s *Service) signin(ctx context.Context, agent string) (any, error) {
	spec, err := s.spec(agent)
	if err != nil {
		return nil, err
	}
	if spec.Setup != nil && len(spec.Setup.SignIn) > 0 && spec.Setup.SignIn[0].Kind == agents.KindNone {
		return signedIn{SignedIn: boolp(true), Detail: "no account needed"}, nil
	}
	f, ok := s.installed(ctx, spec.ID)
	if !ok {
		return signedIn{Detail: "not installed"}, nil
	}
	if st, _ := s.status(ctx, spec, f.Path); st != nil {
		return signedIn{SignedIn: st}, nil
	}
	if s.keys().Has(spec.ID) {
		return signedIn{Detail: "a key is stored"}, nil
	}
	return signedIn{}, nil
}

func (s *Service) setKey(agent, name, value string) error {
	spec, err := s.spec(agent)
	if err != nil {
		return err
	}
	if !spec.Setup.HasKey(name) {
		return acp.Errorf(acp.CodeInvalidParams, "%s takes no key %s", spec.Name, name)
	}
	if err := s.keys().Set(spec.ID, name, value); err != nil {
		s.logf("setup: key for %s refused: %v", spec.ID, err)
		if errors.Is(err, ErrUnsafe) {
			return acp.Errorf(acp.CodeInvalidRequest, "%v", err)
		}
		return acp.Errorf(acp.CodeInvalidParams, "%v", err)
	}
	s.logf("setup: stored %s for %s", name, spec.ID)
	return nil
}

// signoutResult says what sign-out did, and what it couldn't (docs/quire-setup.md §6):
//
//   - Ran is the maker's logout command, if quired ran it; Removed the files quired deleted.
//   - AccountSignedOut is true only when the agent is signed out as far as quired can know: the
//     maker's logout ran and exited 0, or every sign-in the agent has is a key Quire stored and
//     that key is gone. False when the agent still reports an account; null when quired can't
//     tell. Removing Quire's key file alone never counts for an agent with a login of its own.
//   - Verified is true when quired checked the result: the agent's own status command says
//     signed out, or the key file is confirmed gone for a key-only agent.
//   - Manual is what the person still has to do; Cleanup where the maker keeps its login.
type signoutResult struct {
	Ran              *string  `json:"ran"`
	Removed          []string `json:"removed"`
	AccountSignedOut *bool    `json:"accountSignedOut"`
	Verified         bool     `json:"verified"`
	Manual           []string `json:"manual"`
	Cleanup          []string `json:"cleanup"`
}

func tilde(home, path string) string {
	if rel, err := filepath.Rel(home, path); err == nil && !strings.HasPrefix(rel, "..") && !filepath.IsAbs(rel) {
		return "~/" + rel
	}
	return path
}

func (s *Service) signout(ctx context.Context, agent string) (any, error) {
	spec, err := s.spec(agent)
	if err != nil {
		return nil, err
	}
	st := spec.Setup
	res := signoutResult{Removed: []string{}, Manual: []string{}, Cleanup: []string{}}
	if st != nil {
		for _, p := range st.LoginFiles {
			res.Cleanup = append(res.Cleanup, "~/"+filepath.Clean(p))
		}
	}
	path, err := s.keys().Remove(spec.ID)
	if err != nil {
		return nil, acp.Errorf(acp.CodeInvalidRequest, "the key file: %v", err)
	}
	if path != "" {
		res.Removed = append(res.Removed, tilde(s.Home, path))
	}
	keyGone := !s.keys().Has(spec.ID)
	where := strings.Join(res.Cleanup, " and ")
	switch {
	case st != nil && st.Logout != nil:
		f, ok := s.installed(ctx, spec.ID)
		if !ok {
			res.Manual = append(res.Manual, fmt.Sprintf("%s isn't installed, so its own sign-out couldn't run.", spec.Name))
			if where != "" {
				res.Manual = append(res.Manual, fmt.Sprintf("If it was signed in, its login is in %s; delete it there in Terminal.", where))
			}
			break
		}
		shown := st.Logout.Shown(f.Path, s.Home)
		res.Ran = &shown
		out, err := s.capture(ctx, *st.Logout, f.Path, time.Minute)
		if err != nil {
			msg := err.Error()
			var ee *exec.ExitError
			if errors.As(err, &ee) {
				msg = fmt.Sprintf("exit status %d", ee.ExitCode())
			}
			data, _ := json.Marshal(map[string]any{"step": 1, "output": tailLinesOf(out), "removed": res.Removed})
			s.logf("setup: sign-out of %s: %s failed: %s", spec.ID, shown, msg)
			return nil, &acp.RPCError{Code: acp.CodeInternalError, Message: shown + ": " + msg, Data: data}
		}
		res.AccountSignedOut = boolp(true)
		if status, _ := s.status(ctx, spec, f.Path); status != nil {
			res.Verified = true
			if *status {
				res.AccountSignedOut = boolp(false)
				res.Manual = append(res.Manual, fmt.Sprintf("%s still reports a signed-in account after its sign-out.", spec.Name))
				if where != "" {
					res.Manual = append(res.Manual, fmt.Sprintf("Its login is in %s; delete it there in Terminal.", where))
				}
			}
		}
	case st.OnlyKey():
		// Every way it signs in is a key Quire stores, and that key is gone.
		res.AccountSignedOut = boolp(keyGone)
		res.Verified = keyGone
	case st.MakerLogin():
		f, ok := s.installed(ctx, spec.ID)
		if ok {
			if status, _ := s.status(ctx, spec, f.Path); status != nil {
				res.Verified = true
				res.AccountSignedOut = boolp(!*status)
			}
		}
		if res.AccountSignedOut == nil || !*res.AccountSignedOut {
			res.Manual = append(res.Manual, s.signoutNote(spec, where))
		}
	default:
		res.Manual = append(res.Manual, s.signoutNote(spec, where))
	}
	s.logf("setup: sign-out of %s: ran %t, key file removed %t, account signed out %v, verified %t",
		spec.ID, res.Ran != nil, path != "", fmtBool(res.AccountSignedOut), res.Verified)
	return res, nil
}

func (s *Service) signoutNote(spec agents.Spec, where string) string {
	if spec.Setup != nil && spec.Setup.SignoutNote != "" {
		return spec.Setup.SignoutNote
	}
	if where != "" {
		return fmt.Sprintf("%s has no sign-out command. Its login is in %s; delete it there in Terminal.", spec.Name, where)
	}
	return fmt.Sprintf("%s has no sign-out command quired can run.", spec.Name)
}

func fmtBool(b *bool) string {
	if b == nil {
		return "unknown"
	}
	return fmt.Sprint(*b)
}

func tailLinesOf(out string) string {
	lines := strings.Split(strings.TrimRight(out, "\n"), "\n")
	if len(lines) > tailLines {
		lines = lines[len(lines)-tailLines:]
	}
	return strings.Join(lines, "\n")
}

// HomeDir is the user's home, for the service.
func HomeDir() string {
	if h, err := os.UserHomeDir(); err == nil {
		return h
	}
	return ""
}
