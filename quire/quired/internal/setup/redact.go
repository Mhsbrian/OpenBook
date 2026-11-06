package setup

import (
	"regexp"
	"strings"
	"sync"
)

// redactor removes secrets from a job's output before it reaches a log or Quire: the exact text
// the person typed into a login (and so its echo), and values that look like keys or tokens.
type redactor struct {
	mu      sync.Mutex
	secrets []string
}

const mask = "•••"

var (
	// NAME=value or NAME: value for variables that hold secrets.
	envSecret = regexp.MustCompile(`(?i)\b([A-Z0-9_]*(?:API_KEY|_TOKEN|TOKEN|SECRET|PASSWORD))(\s*[=:]\s*)("?)[^\s"']+`)
	// Shapes of the makers' keys and tokens: OpenAI and Anthropic (sk-, sk-ant-), GitHub
	// (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_), xAI (xai-), Google (AIza…), and JWTs.
	keyShapes = regexp.MustCompile(`sk-(?:ant-)?[A-Za-z0-9_\-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xai-[A-Za-z0-9_\-]{20,}|AIza[0-9A-Za-z_\-]{30,}|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}`)
)

// add makes s a secret for the rest of the job. Short strings are ignored: cutting every "y"
// from the output would say more than it hides.
func (r *redactor) add(s string) {
	s = strings.TrimSpace(s)
	if len(s) < 4 {
		return
	}
	r.mu.Lock()
	r.secrets = append(r.secrets, s)
	r.mu.Unlock()
}

func (r *redactor) line(s string) string {
	r.mu.Lock()
	for _, sec := range r.secrets {
		s = strings.ReplaceAll(s, sec, mask)
	}
	r.mu.Unlock()
	s = envSecret.ReplaceAllString(s, "${1}${2}${3}"+mask)
	return keyShapes.ReplaceAllString(s, mask)
}

var (
	// CSI sequences, other two-byte escapes, and OSC strings; OSC 8 hyperlinks keep their URL
	// (found by detect first).
	ansiCSI = regexp.MustCompile("\x1b\\[[0-9;?<=>!]*[ -/]*[@-~]")
	ansiOSC = regexp.MustCompile("\x1b\\][^\x07\x1b]*(?:\x07|\x1b\\\\)")
	ansiTwo = regexp.MustCompile("\x1b[@-Z\\\\-_]")
	osc8    = regexp.MustCompile("\x1b\\]8;[^;\x07\x1b]*;([^\x07\x1b]*)(?:\x07|\x1b\\\\)")
)

// clean returns the text of a terminal line without escapes and control characters, and the
// URLs of its OSC 8 hyperlinks.
func clean(s string) (string, []string) {
	var links []string
	for _, m := range osc8.FindAllStringSubmatch(s, -1) {
		if m[1] != "" {
			links = append(links, m[1])
		}
	}
	s = ansiOSC.ReplaceAllString(s, "")
	s = ansiCSI.ReplaceAllString(s, "")
	s = ansiTwo.ReplaceAllString(s, "")
	s = strings.Map(func(r rune) rune {
		if r == '\t' {
			return ' '
		}
		if r < 0x20 || r == 0x7f {
			return -1
		}
		return r
	}, s)
	return strings.TrimRight(s, " "), links
}

// Prompt is what a login asks the person for, as far as quired can read it from the output.
type Prompt struct {
	URL   string `json:"url,omitempty"`
	Code  string `json:"code,omitempty"`
	Paste bool   `json:"paste"`
}

var (
	urlRe = regexp.MustCompile(`https?://[^\s"'<>` + "`" + `\x1b]+`)
	// One-time device codes: GitHub's XXXX-XXXX, and codes printed after "code".
	dashCode  = regexp.MustCompile(`\b([A-Z0-9]{4,5}-[A-Z0-9]{4,5})\b`)
	codeAfter = regexp.MustCompile(`(?i)\b(?:code|enter)\b[^A-Za-z0-9\n]{1,6}([A-Z0-9]{6,10})\b`)
	codeWord  = regexp.MustCompile(`(?i)\bcode\b`)
	pasteRe   = regexp.MustCompile(`(?i)paste (?:the |your |in )?(?:authori[sz]ation |auth |verification |login )?(?:code|url|link|token|redirect)|(?:enter|input) (?:the |your )?(?:authori[sz]ation|verification|auth) code|code here`)
)

// preferred URLs are the ones a login means: its sign-in or device page.
var loginWords = []string{"login", "device", "oauth", "auth", "activate", "signin", "sign-in", "verify"}

// detect reads one cleaned line (and its hyperlinks) and returns what it found.
func detect(line string, links []string) (url, code string, paste bool) {
	cands := append(append([]string{}, links...), urlRe.FindAllString(line, -1)...)
	for _, u := range cands {
		u = strings.TrimRight(u, ".,;:)]}>'\"")
		if url == "" {
			url = u
		}
		lu := strings.ToLower(u)
		for _, w := range loginWords {
			if strings.Contains(lu, w) {
				url = u
				break
			}
		}
	}
	rest := urlRe.ReplaceAllString(line, " ")
	if m := dashCode.FindStringSubmatch(rest); m != nil && (hasLetter(m[1]) || codeWord.MatchString(rest)) {
		code = m[1]
	} else if m := codeAfter.FindStringSubmatch(rest); m != nil && hasDigit(m[1]) {
		code = m[1]
	}
	paste = pasteRe.MatchString(line)
	return url, code, paste
}

func hasDigit(s string) bool { return strings.ContainsAny(s, "0123456789") }

// hasLetter: a code of digits only ("2026-1105") counts only on a line that says "code".
func hasLetter(s string) bool { return strings.ContainsAny(s, "ABCDEFGHIJKLMNOPQRSTUVWXYZ") }
