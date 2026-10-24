// SPDX-License-Identifier: Apache-2.0

// OpenBook Update's SELinux app-domain statements, derived from a policy exactly as
// scripts/googlebook/build-update-app-candidate.py app_domain_statements() derives them: the statements all
// of Google's template app domains share, instantiated for openbook_update_app.
package main

import (
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"
)

const (
	derivedHeader = "; Every app domain's own statements, as this image's policy gives Google's app domains (derived):\n"
	appDomain     = "openbook_update_app"
)

var (
	templateDomains = []string{"vmlauncher_app", "priv_app", "priv_app_36", "untrusted_app", "platform_app", "gmscore_app"}
	operators       = map[string]bool{"and": true, "or": true, "not": true, "xor": true, "all": true}
	reAttrSet       = regexp.MustCompile(`^\(typeattributeset (base_typeattr_\d+) (.+)\)$`)
	reToken         = regexp.MustCompile(`\(|\)|"[^"]*"|[^\s()]+`)
	reBaseAttr      = regexp.MustCompile(`base_typeattr_\d+`)
	reBraced        = regexp.MustCompile(`\{(.+?\))\}`)
)

type sexpNode struct {
	atom string
	kids []*sexpNode // nil for an atom
	list bool
}

func parseSexp(text string) *sexpNode {
	stack := []*sexpNode{{list: true}}
	for _, t := range reToken.FindAllString(text, -1) {
		switch t {
		case "(":
			stack = append(stack, &sexpNode{list: true})
		case ")":
			if len(stack) < 2 {
				continue
			}
			done := stack[len(stack)-1]
			stack = stack[:len(stack)-1]
			top := stack[len(stack)-1]
			top.kids = append(top.kids, done)
		default:
			top := stack[len(stack)-1]
			top.kids = append(top.kids, &sexpNode{atom: t})
		}
	}
	if len(stack[0].kids) == 1 {
		return stack[0].kids[0]
	}
	return stack[0]
}

func (n *sexpNode) render() string {
	if !n.list {
		return n.atom
	}
	parts := make([]string, len(n.kids))
	for i, k := range n.kids {
		parts[i] = k.render()
	}
	return "(" + strings.Join(parts, " ") + ")"
}

func (n *sexpNode) normalize() *sexpNode {
	if !n.list {
		return n
	}
	kids := make([]*sexpNode, len(n.kids))
	allAtoms := true
	for i, k := range n.kids {
		kids[i] = k.normalize()
		if kids[i].list {
			allAtoms = false
		}
	}
	if len(kids) > 0 && allAtoms && !operators[kids[0].atom] {
		sort.SliceStable(kids, func(i, j int) bool { return kids[i].atom < kids[j].atom })
	}
	return &sexpNode{list: true, kids: kids}
}

func isWord(c byte) bool {
	return c == '_' || c >= '0' && c <= '9' || c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z'
}

// subDomain replaces the domain (alone, or before _userfaultfd, _wrapfd or _block_io_uring) with repl, as
// the Python regex (?<![A-Za-z0-9_])DOMAIN(?=(?:_userfaultfd|_wrapfd|_block_io_uring)?(?![A-Za-z0-9_])) does.
func subDomain(s, domain, repl string) string {
	var b strings.Builder
	for i := 0; i < len(s); {
		if strings.HasPrefix(s[i:], domain) && (i == 0 || !isWord(s[i-1])) {
			rest := s[i+len(domain):]
			ok := rest == "" || !isWord(rest[0])
			for _, suf := range []string{"_userfaultfd", "_wrapfd", "_block_io_uring"} {
				if strings.HasPrefix(rest, suf) && (len(rest) == len(suf) || !isWord(rest[len(suf)])) {
					ok = true
				}
			}
			if ok {
				b.WriteString(repl)
				i += len(domain)
				continue
			}
		}
		b.WriteByte(s[i])
		i++
	}
	return b.String()
}

func pySplitLines(s string) []string {
	// str.splitlines() for a policy file: refuse the rare boundaries rather than mis-split.
	s = strings.TrimSuffix(s, "\n")
	if s == "" {
		return nil
	}
	return strings.Split(s, "\n")
}

func sharedAppStatements(plat string) ([]string, error) {
	if strings.ContainsAny(plat, "\r\v\f\x1c\x1d\x1e\u0085  ") {
		return nil, errors.New("unsupported line boundary in the platform policy")
	}
	lines := pySplitLines(plat)
	attrs := map[string]string{}
	for _, line := range lines {
		if m := reAttrSet.FindStringSubmatch(line); m != nil {
			attrs[m[1]] = m[2]
		}
	}
	var common map[string]bool
	for _, d := range templateDomains {
		found := map[string]bool{}
		for _, line := range lines {
			if strings.HasPrefix(line, "(typeattributeset") || strings.HasPrefix(line, "(typeattribute ") || strings.HasPrefix(line, ";") {
				continue
			}
			out := reBaseAttr.ReplaceAllStringFunc(line, func(name string) string {
				expr, ok := attrs[name]
				if !ok {
					return name
				}
				return "{" + parseSexp(subDomain(expr, d, "@D@")).normalize().render() + "}"
			})
			out = subDomain(out, d, "@D@")
			if strings.Contains(out, "@D@") {
				found[out] = true
			}
		}
		if common == nil {
			common = found
		} else {
			for k := range common {
				if !found[k] {
					delete(common, k)
				}
			}
		}
	}
	out := make([]string, 0, len(common))
	for k := range common {
		out = append(out, k)
	}
	sort.Strings(out)
	return out, nil
}

func appDomainStatements(plat string) ([]string, error) {
	shared, err := sharedAppStatements(plat)
	if err != nil {
		return nil, err
	}
	have := map[string]bool{}
	for _, s := range shared {
		have[s] = true
	}
	for _, r := range []string{"(type @D@)", "(typetransition @D@ tmpfs file appdomain_tmpfs)",
		"(allow @D@ appdomain_tmpfs (file (read write getattr map execute)))"} {
		if !have[r] {
			return nil, held("Google's app domains no longer share the expected statements")
		}
	}
	var out []string
	names := map[string]string{}
	for _, st := range shared {
		line := reBraced.ReplaceAllStringFunc(st, func(m string) string {
			expr := strings.ReplaceAll(reBraced.FindStringSubmatch(m)[1], "@D@", appDomain)
			if _, ok := names[expr]; !ok {
				names[expr] = fmt.Sprintf("%s_x%d", appDomain, len(names)+1)
				out = append(out, "(typeattribute "+names[expr]+")", "(typeattributeset "+names[expr]+" "+expr+")")
			}
			return names[expr]
		})
		out = append(out, strings.ReplaceAll(line, "@D@", appDomain))
	}
	return out, nil
}

// rederiveTail is rederive_app_domain(): OpenBook's carried policy tail with its derived block taken again
// from NEW's policy. The repository's own part (before the header) is carried verbatim.
func rederiveTail(newPlat, tail []byte) ([]byte, error) {
	text := string(tail)
	at := strings.Index(text, derivedHeader)
	if at < 0 {
		if strings.Contains(text, appDomain) {
			return nil, errors.New("OpenBook's app domain is carried without its derived app-domain block")
		}
		return tail, nil
	}
	derived, err := appDomainStatements(string(newPlat))
	if err != nil {
		return nil, err
	}
	return []byte(text[:at] + derivedHeader + strings.Join(derived, "\n") + "\n"), nil
}
