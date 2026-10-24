// SPDX-License-Identifier: Apache-2.0

// The carry rules of scripts/googlebook/rebase-google-build.py, ported exactly: a line-level three-way merge
// (with Python difflib's SequenceMatcher, so the laptop and the host merge identically), the re-append of an
// appended tail, and the re-insertion of a block before a closing marker.
package main

import (
	"bytes"
	"errors"
	"fmt"
	"sort"
	"strings"
)

type match struct{ a, b, size int }

// matcher is difflib.SequenceMatcher(None, a, b, autojunk=False) over lines.
type matcher struct {
	a, b []string
	b2j  map[string][]int
}

func newMatcher(a, b []string) *matcher {
	m := &matcher{a: a, b: b, b2j: map[string][]int{}}
	for j, s := range b {
		m.b2j[s] = append(m.b2j[s], j)
	}
	return m
}

func (m *matcher) longest(alo, ahi, blo, bhi int) match {
	besti, bestj, best := alo, blo, 0
	j2len := map[int]int{}
	for i := alo; i < ahi; i++ {
		next := map[int]int{}
		for _, j := range m.b2j[m.a[i]] {
			if j < blo {
				continue
			}
			if j >= bhi {
				break
			}
			k := j2len[j-1] + 1
			next[j] = k
			if k > best {
				besti, bestj, best = i-k+1, j-k+1, k
			}
		}
		j2len = next
	}
	// No junk: difflib's extension loops only apply to non-junk equal neighbours.
	for besti > alo && bestj > blo && m.a[besti-1] == m.b[bestj-1] {
		besti, bestj, best = besti-1, bestj-1, best+1
	}
	for besti+best < ahi && bestj+best < bhi && m.a[besti+best] == m.b[bestj+best] {
		best++
	}
	return match{besti, bestj, best}
}

func (m *matcher) blocks() []match {
	type span struct{ alo, ahi, blo, bhi int }
	queue := []span{{0, len(m.a), 0, len(m.b)}}
	var found []match
	for len(queue) > 0 {
		s := queue[len(queue)-1]
		queue = queue[:len(queue)-1]
		x := m.longest(s.alo, s.ahi, s.blo, s.bhi)
		if x.size > 0 {
			found = append(found, x)
			if s.alo < x.a && s.blo < x.b {
				queue = append(queue, span{s.alo, x.a, s.blo, x.b})
			}
			if x.a+x.size < s.ahi && x.b+x.size < s.bhi {
				queue = append(queue, span{x.a + x.size, s.ahi, x.b + x.size, s.bhi})
			}
		}
	}
	sort.Slice(found, func(i, j int) bool {
		if found[i].a != found[j].a {
			return found[i].a < found[j].a
		}
		if found[i].b != found[j].b {
			return found[i].b < found[j].b
		}
		return found[i].size < found[j].size
	})
	var out []match
	i1, j1, k1 := 0, 0, 0
	for _, x := range found {
		if i1+k1 == x.a && j1+k1 == x.b {
			k1 += x.size
		} else {
			if k1 > 0 {
				out = append(out, match{i1, j1, k1})
			}
			i1, j1, k1 = x.a, x.b, x.size
		}
	}
	if k1 > 0 {
		out = append(out, match{i1, j1, k1})
	}
	return append(out, match{len(m.a), len(m.b), 0})
}

type opcode struct {
	tag            string
	i1, i2, j1, j2 int
}

func (m *matcher) opcodes() []opcode {
	var out []opcode
	i, j := 0, 0
	for _, x := range m.blocks() {
		tag := ""
		switch {
		case i < x.a && j < x.b:
			tag = "replace"
		case i < x.a:
			tag = "delete"
		case j < x.b:
			tag = "insert"
		}
		if tag != "" {
			out = append(out, opcode{tag, i, x.a, j, x.b})
		}
		i, j = x.a+x.size, x.b+x.size
		if x.size > 0 {
			out = append(out, opcode{"equal", x.a, i, x.b, j})
		}
	}
	return out
}

// textLines is str.splitlines(keepends=True) for text the host reads with universal newlines. Line
// boundaries other than "\n" (which the host would translate or split on) are refused, not guessed.
func textLines(b []byte) ([]string, error) {
	if bytes.ContainsAny(b, "\r\v\f\x1c\x1d\x1e") || bytes.Contains(b, []byte("\u0085")) ||
		bytes.Contains(b, []byte(" ")) || bytes.Contains(b, []byte(" ")) {
		return nil, errors.New("unsupported line boundary")
	}
	s := string(b)
	var out []string
	for s != "" {
		i := strings.IndexByte(s, '\n')
		if i < 0 {
			out = append(out, s)
			break
		}
		out = append(out, s[:i+1])
		s = s[i+1:]
	}
	return out, nil
}

// merge3 applies ours' edits of old onto new, line by line, refusing edits that touch lines new changed.
func merge3(old, ours, nw []string) ([]string, error) {
	oldToNew := map[int]int{}
	for _, x := range newMatcher(old, nw).blocks() {
		for k := 0; k < x.size; k++ {
			oldToNew[x.a+k] = x.b + k
		}
	}
	out := append([]string(nil), nw...)
	var hunks []opcode
	for _, op := range newMatcher(old, ours).opcodes() {
		if op.tag != "equal" {
			hunks = append(hunks, op)
		}
	}
	for h := len(hunks) - 1; h >= 0; h-- {
		op := hunks[h]
		lo, hi := max(op.i1-1, 0), min(op.i2+1, len(old))
		if lo >= hi {
			return nil, errors.New("edit without context")
		}
		var mapped []int
		for k := lo; k < hi; k++ {
			v, ok := oldToNew[k]
			if !ok {
				return nil, fmt.Errorf("edit at line %d overlaps an upstream change", op.i1+1)
			}
			mapped = append(mapped, v)
		}
		for n, v := range mapped {
			if v != mapped[0]+n {
				return nil, fmt.Errorf("upstream moved the context of the edit at line %d", op.i1+1)
			}
		}
		at := len(nw)
		if op.i1 < len(old) {
			at = oldToNew[op.i1]
		}
		if op.i1 == op.i2 && op.i1 > 0 {
			at = oldToNew[op.i1-1] + 1
		}
		end := min(at+(op.i2-op.i1), len(out))
		repl := append([]string(nil), ours[op.j1:op.j2]...)
		out = append(out[:at], append(repl, out[end:]...)...)
	}
	return out, nil
}

// reinsertBlock places OpenBook's block (inserted before OLD's closing marker) before NEW's marker.
func reinsertBlock(nw, block, marker []byte) ([]byte, error) {
	if bytes.Count(nw, marker) != 1 {
		return nil, fmt.Errorf("not exactly one %s to insert before", marker)
	}
	if bytes.Contains(nw, block) {
		return nil, errors.New("NEW already contains OpenBook's block")
	}
	j := bytes.LastIndex(nw, marker)
	return append(append(append([]byte(nil), nw[:j]...), block...), nw[j:]...), nil
}

// insertedBlock is the layer side of reinsert(): OpenBook's one block before OLD's marker.
func insertedBlock(old, ours, marker []byte) ([]byte, error) {
	if bytes.Count(old, marker) != 1 {
		return nil, fmt.Errorf("not exactly one %s to insert before", marker)
	}
	at := bytes.LastIndex(old, marker)
	n := len(ours) - len(old)
	if n <= 0 || !bytes.Equal(ours[:at], old[:at]) || !bytes.Equal(ours[at+n:], old[at:]) {
		return nil, errors.New("OpenBook's change is not one block before the closing marker; cannot carry it")
	}
	return append([]byte(nil), ours[at:at+n]...), nil
}
