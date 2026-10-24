// SPDX-License-Identifier: Apache-2.0

// Firmware safety on the laptop (ANAL-251). Googlebook images assume Google hardware: init scripts start
// the security chip's firmware tools, and Google's update postinstall flashes security chip, BIOS and EC
// firmware. OpenBook neutralises those, and scripts/googlebook/check-firmware-safety.py checks every image
// against device/anybook/common/safety/firmware-safety.json. This is that check, ported, run on every
// release the laptop adapts, before it is built: the adapted system, Google's new system_ext and product,
// and the init scripts inside every APEX. Any finding holds the release, with the reason.
//
// The rules are the running release's own (/system/etc/openbook/firmware-safety.json): OpenBook's file,
// carried into the adapted system and checked against the layer byte for byte. A release without them is
// held.
//
// The port reads everything the host check reads, and also what Android's init reads beyond it, so it can
// only hold more, never less: every regular file in an etc/init directory whatever its name, an APEX's
// versioned init scripts (etc/*rc, e.g. foo.34rc), and a compressed APEX (.capex), which it holds rather
// than skips. A symlink is checked for a forbidden name wherever it points. Its \b is ASCII (RE2), where
// Python's is Unicode: on non-ASCII text it can only match more.
package main

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode"
	"unicode/utf8"
)

const (
	safetySchema       = "openbook-firmware-safety/1"
	safetyResultSchema = "openbook-firmware-safety-result/1"
	safetyRulesPath    = "system/etc/openbook/firmware-safety.json" // in a system tree
	maxCheckedFile     = 64 << 20
)

// Where each partition is mounted; system is system-as-root (check-firmware-safety.py's MOUNTS).
var safetyMounts = map[string]string{"system": "/", "system_ext": "/system_ext", "product": "/product",
	"vendor": "/vendor", "odm": "/odm", "vendor_dlkm": "/vendor_dlkm", "system_dlkm": "/system_dlkm",
	"odm_dlkm": "/odm_dlkm"}

// The directories init parses every regular file of, whatever its name.
var initDirs = map[string]bool{"/system/etc/init": true, "/system_ext/etc/init": true, "/product/etc/init": true,
	"/vendor/etc/init": true, "/odm/etc/init": true}

var hex64 = regexp.MustCompile(`^[0-9a-f]{64}$`)

// errFormat: content this check cannot read. Google's partitions were verified moments before (its
// signature and dm-verity roots), so this is a format OpenBook has to review, not a passing fault.
type errFormatT struct{ msg string }

func (e errFormatT) Error() string { return e.msg }

func errFormat(format string, args ...any) error { return errFormatT{fmt.Sprintf(format, args...)} }

type neutralRule struct {
	Replacement  string `json:"replacement"`
	SHA256       string `json:"sha256"`
	GoogleSHA256 string `json:"google_sha256"`
}

type reviewedRule struct {
	SHA256  string `json:"sha256"`
	Verdict string `json:"verdict"`
}

type safetyPolicy struct {
	Schema           string                  `json:"schema"`
	RCPattern        string                  `json:"rc_pattern"`
	BinaryPattern    string                  `json:"binary_pattern"`
	ForbiddenNames   []string                `json:"forbidden_names"`
	Neutralised      map[string]neutralRule  `json:"neutralised"`
	ReviewedRC       map[string]reviewedRule `json:"reviewed_rc"`
	ReviewedBinaries map[string]string       `json:"reviewed_binaries"`
	neutralOrder     []string
	rc, bin          *regexp.Regexp
	sha256           string
}

// loadSafetyPolicy reads and checks the rules as check-firmware-safety.py's load_policy does. (OpenBook's
// replacement files are not beside the rules on the laptop: the check finds them at their paths instead.)
func loadSafetyPolicy(data []byte) (*safetyPolicy, error) {
	var top map[string]json.RawMessage
	if err := json.Unmarshal(data, &top); err != nil {
		return nil, fmt.Errorf("firmware-safety rules: %v", err)
	}
	for _, k := range []string{"schema", "rc_pattern", "binary_pattern", "forbidden_names", "neutralised", "reviewed_rc", "reviewed_binaries"} {
		if top[k] == nil {
			return nil, fmt.Errorf("firmware-safety rules: no %s", k)
		}
	}
	p := &safetyPolicy{}
	if err := json.Unmarshal(data, p); err != nil {
		return nil, fmt.Errorf("firmware-safety rules: %v", err)
	}
	if p.Schema != safetySchema {
		return nil, fmt.Errorf("firmware-safety rules: not a %s file", safetySchema)
	}
	var err error
	if p.rc, err = regexp.Compile(p.RCPattern); err != nil {
		return nil, fmt.Errorf("firmware-safety rules: rc_pattern: %v", err)
	}
	if p.bin, err = regexp.Compile(p.BinaryPattern); err != nil {
		return nil, fmt.Errorf("firmware-safety rules: binary_pattern: %v", err)
	}
	if p.neutralOrder, err = objectKeys(top["neutralised"]); err != nil {
		return nil, fmt.Errorf("firmware-safety rules: neutralised: %v", err)
	}
	for _, k := range p.neutralOrder {
		if r := p.Neutralised[k]; !hex64.MatchString(r.SHA256) || !hex64.MatchString(r.GoogleSHA256) {
			return nil, fmt.Errorf("%s: neutralised rule needs sha256 and google_sha256", k)
		}
	}
	for k, r := range p.ReviewedRC {
		if !hex64.MatchString(r.SHA256) || (r.Verdict != "allowed" && r.Verdict != "inert" && r.Verdict != "openbook") {
			return nil, fmt.Errorf("%s: reviewed rc rule needs sha256 and a verdict", k)
		}
		if _, ok := p.Neutralised[k]; ok {
			return nil, fmt.Errorf("%s is both neutralised and reviewed", k)
		}
	}
	sum := sha256.Sum256(data)
	p.sha256 = hex.EncodeToString(sum[:])
	return p, nil
}

// objectKeys returns a JSON object's keys in file order (Python keeps it; the findings follow it).
func objectKeys(raw json.RawMessage) ([]string, error) {
	d := json.NewDecoder(bytes.NewReader(raw))
	if t, err := d.Token(); err != nil || t != json.Delim('{') {
		return nil, errors.New("not an object")
	}
	var keys []string
	seen := map[string]bool{}
	for d.More() {
		t, err := d.Token()
		if err != nil {
			return nil, err
		}
		k := t.(string)
		if seen[k] {
			return nil, fmt.Errorf("%s twice", k)
		}
		seen[k] = true
		keys = append(keys, k)
		var skip json.RawMessage
		if err := d.Decode(&skip); err != nil {
			return nil, err
		}
	}
	return keys, nil
}

type safetyFinding struct {
	Kind   string `json:"kind"`
	Path   string `json:"path"`
	Detail string `json:"detail"`
}

type rcSeen struct {
	SHA256  string   `json:"sha256"`
	Matches []string `json:"matches"`
}

// The host check's inventory, key for key.
type safetyInventory struct {
	Neutralised      map[string]string `json:"neutralised"`
	ReviewedRC       map[string]string `json:"reviewed_rc"`
	AbsentReviewedRC []string          `json:"absent_reviewed_rc"`
	RCMatches        map[string]rcSeen `json:"rc_matches"`
	Binaries         []string          `json:"binaries"`
	Partitions       []string          `json:"partitions"`
	APEXRCFiles      int               `json:"apex_rc_files"`
	// Read beyond the host check's *.rc set: other files in etc/init, versioned APEX scripts.
	BeyondHost []string `json:"init_files_beyond_host_check"`
}

type SafetyResult struct {
	Schema       string          `json:"schema"`
	Mode         string          `json:"mode"`
	Passed       bool            `json:"passed"`
	PolicySHA256 string          `json:"policy_sha256"`
	Findings     []safetyFinding `json:"findings"`
	Inventory    safetyInventory `json:"inventory"`
}

// partFiles is a partition's files as the check reads them.
type partFiles interface {
	// walk calls fn for every entry that is not a directory, in os.walk's order (a directory's entries by
	// name, then its subdirectories by name). kind: 'f' regular file, 'l' symlink, 'o' anything else.
	walk(fn func(rel string, kind byte) error) error
	// open returns a regular file for reading.
	open(rel string) (io.ReaderAt, int64, error)
}

type safetyPart struct {
	name  string
	files partFiles
}

type safetyCheck struct {
	p          *safetyPolicy
	fsck, work string
	scratchN   int
	closers    []io.Closer
}

func (c *safetyCheck) close() {
	for _, x := range c.closers {
		x.Close()
	}
	c.closers = nil
}

// scratch names a new path in the work directory (for fsck.erofs, only when a file is compressed).
func (c *safetyCheck) scratch(name string) (string, error) {
	if c.work == "" {
		return "", errors.New("a compressed file needs fsck.erofs and a work directory")
	}
	if err := os.MkdirAll(c.work, 0o700); err != nil {
		return "", err
	}
	c.scratchN++
	return filepath.Join(c.work, fmt.Sprintf("%s-%d", name, c.scratchN)), nil
}

// treeFiles: an extracted partition (the adapted system).
type treeFiles struct {
	c    *safetyCheck
	root string
}

func (t treeFiles) walk(fn func(string, byte) error) error {
	var visit func(rel string) error
	visit = func(rel string) error {
		ents, err := os.ReadDir(filepath.Join(t.root, rel))
		if err != nil {
			return err
		}
		var dirs []string
		for _, e := range ents {
			p := path.Join(rel, e.Name())
			switch m := e.Type(); {
			case m.IsDir():
				dirs = append(dirs, p)
			case m.IsRegular():
				err = fn(p, 'f')
			case m&os.ModeSymlink != 0:
				err = fn(p, 'l')
			default:
				err = fn(p, 'o')
			}
			if err != nil {
				return err
			}
		}
		for _, d := range dirs {
			if err := visit(d); err != nil {
				return err
			}
		}
		return nil
	}
	return visit("")
}

func (t treeFiles) open(rel string) (io.ReaderAt, int64, error) {
	f, err := os.Open(filepath.Join(t.root, rel))
	if err != nil {
		return nil, 0, err
	}
	t.c.closers = append(t.c.closers, f)
	st, err := f.Stat()
	if err != nil {
		return nil, 0, err
	}
	return f, st.Size(), nil
}

// erofsFiles: an EROFS image read in place. A compressed file is read through fsck.erofs, extracting its
// directory (Google's system_ext and product store init scripts and APEXes uncompressed).
type erofsFiles struct {
	c         *safetyCheck
	fs        *erofsFS
	image     func() (string, error) // the image as a file, for fsck.erofs
	nids      map[string]uint64
	extracted map[string]string
}

func newErofsFiles(c *safetyCheck, r io.ReaderAt, image func() (string, error)) (*erofsFiles, error) {
	fs, err := openErofs(r)
	if err != nil {
		return nil, errFormat("%v", err)
	}
	return &erofsFiles{c: c, fs: fs, image: image, nids: map[string]uint64{}, extracted: map[string]string{}}, nil
}

func (e *erofsFiles) walk(fn func(string, byte) error) error {
	seen := map[uint64]bool{}
	var visit func(nid uint64, rel string) error
	visit = func(nid uint64, rel string) error {
		if seen[nid] {
			return errFormat("%s: directory loop", rel)
		}
		seen[nid] = true
		in, err := e.fs.readInode(nid)
		if err != nil {
			return err
		}
		ents, err := e.fs.readDir(in)
		if err != nil {
			return errFormat("/%s: %v", rel, err)
		}
		sort.Slice(ents, func(i, j int) bool { return ents[i].name < ents[j].name })
		var dirs []dirent
		for _, d := range ents {
			if d.name == "." || d.name == ".." {
				continue
			}
			child, err := e.fs.readInode(d.nid)
			if err != nil {
				return err
			}
			p := path.Join(rel, d.name)
			switch uint32(child.mode) & sIFMT {
			case sIFDIR:
				dirs = append(dirs, dirent{d.nid, p})
				continue
			case sIFREG:
				e.nids[p] = d.nid
				err = fn(p, 'f')
			case sIFLNK:
				err = fn(p, 'l')
			default:
				err = fn(p, 'o')
			}
			if err != nil {
				return err
			}
		}
		for _, d := range dirs {
			if err := visit(d.nid, d.name); err != nil {
				return err
			}
		}
		return nil
	}
	return visit(e.fs.rootNid, "")
}

func (e *erofsFiles) open(rel string) (io.ReaderAt, int64, error) {
	nid, ok := e.nids[rel]
	if !ok {
		return nil, 0, fmt.Errorf("/%s: not a regular file", rel)
	}
	in, err := e.fs.readInode(nid)
	if err != nil {
		return nil, 0, err
	}
	r, err := e.fs.fileReader(in)
	if err == nil {
		return r, int64(in.size), nil
	}
	if !errors.Is(err, errNotFlat) {
		return nil, 0, errFormat("/%s: %v", rel, err)
	}
	dir := path.Dir(rel)
	if dir == "." {
		dir = ""
	}
	loc, ok := e.extracted[dir]
	if !ok {
		img, err := e.image()
		if err != nil {
			return nil, 0, err
		}
		dest, err := e.c.scratch("extract")
		if err != nil {
			return nil, 0, err
		}
		if loc, err = extractSubtree(e.c.fsck, img, dir, dest); err != nil {
			return nil, 0, errFormat("/%s: %v", rel, err)
		}
		e.extracted[dir] = loc
	}
	t := treeFiles{e.c, loc}
	return t.open(path.Base(rel))
}

// ext4Files: an ext4 APEX payload.
type ext4Files struct {
	fs    *ext4FS
	files map[string]*ext4Inode
}

func (e *ext4Files) walk(fn func(string, byte) error) error {
	e.files = map[string]*ext4Inode{}
	seen := map[uint64]bool{}
	var visit func(ino uint64, rel string) error
	visit = func(ino uint64, rel string) error {
		if seen[ino] {
			return errFormat("%s: directory loop", rel)
		}
		seen[ino] = true
		in, err := e.fs.inode(ino)
		if err != nil {
			return err
		}
		ents, err := e.fs.readDir(in)
		if err != nil {
			return err
		}
		sort.Slice(ents, func(i, j int) bool { return ents[i].name < ents[j].name })
		var dirs []dirent
		for _, d := range ents {
			if d.name == "." || d.name == ".." {
				continue
			}
			child, err := e.fs.inode(d.nid)
			if err != nil {
				return err
			}
			p := path.Join(rel, d.name)
			switch uint32(child.mode) & sIFMT {
			case sIFDIR:
				dirs = append(dirs, dirent{d.nid, p})
				continue
			case sIFREG:
				e.files[p] = child
				err = fn(p, 'f')
			case sIFLNK:
				err = fn(p, 'l')
			default:
				err = fn(p, 'o')
			}
			if err != nil {
				return err
			}
		}
		for _, d := range dirs {
			if err := visit(d.nid, d.name); err != nil {
				return err
			}
		}
		return nil
	}
	return visit(ext4RootInode, "")
}

func (e *ext4Files) open(rel string) (io.ReaderAt, int64, error) {
	in, ok := e.files[rel]
	if !ok {
		return nil, 0, fmt.Errorf("/%s: not a regular file", rel)
	}
	r, err := e.fs.reader(in)
	return r, int64(in.size), err
}

func readFile(files partFiles, rel string) ([]byte, error) {
	r, size, err := files.open(rel)
	if err != nil {
		return nil, err
	}
	return readAllAt(r, size)
}

type rcFile struct {
	runtime string
	data    []byte
}

// apexInitScripts reads the init scripts inside an APEX's apex_payload.img (EROFS or ext4): every *.rc file
// (the host check's set) and every file in etc/ whose name ends in "rc" (init's own pattern, which takes
// versioned scripts such as foo.34rc). An APEX without a payload has none.
func (c *safetyCheck) apexInitScripts(name string, r io.ReaderAt, size int64) ([]rcFile, error) {
	z, err := zip.NewReader(r, size)
	if err != nil {
		return nil, errFormat("%v", err)
	}
	var pf *zip.File
	for _, f := range z.File {
		if f.Name == "apex_payload.img" {
			pf = f
		}
	}
	if pf == nil {
		return nil, nil
	}
	var payload io.ReaderAt
	psize := int64(pf.UncompressedSize64)
	var payloadFile string
	if pf.Method == zip.Store && pf.CompressedSize64 == pf.UncompressedSize64 {
		off, err := pf.DataOffset()
		if err != nil {
			return nil, errFormat("%v", err)
		}
		payload = io.NewSectionReader(r, off, psize)
	} else {
		if payloadFile, err = c.copyOut(pf.Open); err != nil {
			return nil, err
		}
		f, err := os.Open(payloadFile)
		if err != nil {
			return nil, err
		}
		c.closers = append(c.closers, f)
		payload = f
	}
	head := make([]byte, 1084)
	if _, err := payload.ReadAt(head, 0); err != nil {
		return nil, errFormat("apex_payload.img: %v", err)
	}
	var files partFiles
	switch {
	case le.Uint32(head[erofsSuperOffset:]) == erofsMagic:
		image := func() (string, error) {
			if payloadFile == "" {
				var err error
				payloadFile, err = c.copyOut(func() (io.ReadCloser, error) {
					return io.NopCloser(io.NewSectionReader(payload, 0, psize)), nil
				})
				return payloadFile, err
			}
			return payloadFile, nil
		}
		if files, err = newErofsFiles(c, payload, image); err != nil {
			return nil, err
		}
	case le.Uint16(head[1080:]) == ext4Magic:
		fs, err := openExt4(payload)
		if err != nil {
			return nil, err
		}
		files = &ext4Files{fs: fs}
	default:
		return nil, errFormat("apex_payload.img is neither EROFS nor ext4")
	}
	var out []rcFile
	err = files.walk(func(rel string, kind byte) error {
		base := path.Base(rel)
		if kind != 'f' || !(strings.HasSuffix(base, ".rc") || (path.Dir(rel) == "etc" && strings.HasSuffix(base, "rc"))) {
			return nil
		}
		data, err := readFile(files, rel)
		if err != nil {
			return err
		}
		out = append(out, rcFile{"/apex/" + name + "/" + rel, data})
		return nil
	})
	return out, err
}

// copyOut writes a stream to a new scratch file and returns its path.
func (c *safetyCheck) copyOut(open func() (io.ReadCloser, error)) (string, error) {
	dest, err := c.scratch("payload")
	if err != nil {
		return "", err
	}
	src, err := open()
	if err != nil {
		return "", errFormat("%v", err)
	}
	defer src.Close()
	f, err := os.OpenFile(dest, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return "", err
	}
	if _, err := io.Copy(f, src); err != nil {
		f.Close()
		return "", errFormat("%v", err)
	}
	return dest, f.Close()
}

// check is check-firmware-safety.py's check_tree, with the APEX scan built in.
func (c *safetyCheck) check(parts []safetyPart) (*SafetyResult, error) {
	p := c.p
	forbidden := map[string]bool{}
	for _, n := range p.ForbiddenNames {
		forbidden[n] = true
	}
	res := &SafetyResult{Schema: safetyResultSchema, PolicySHA256: p.sha256, Findings: []safetyFinding{}}
	inv := &res.Inventory
	inv.Neutralised, inv.ReviewedRC, inv.RCMatches = map[string]string{}, map[string]string{}, map[string]rcSeen{}
	inv.AbsentReviewedRC, inv.Binaries, inv.Partitions, inv.BeyondHost = []string{}, []string{}, []string{}, []string{}
	find := func(kind, path, detail string) {
		res.Findings = append(res.Findings, safetyFinding{kind, path, detail})
	}
	seen := map[string]rcSeen{}
	var apexRC []rcFile
	mounts, hasSystem := map[string]bool{}, false
	for _, part := range parts {
		mount, ok := safetyMounts[part.name]
		if !ok {
			return nil, fmt.Errorf("unknown partition %s", part.name)
		}
		mounts[mount], hasSystem = true, hasSystem || part.name == "system"
		inv.Partitions = append(inv.Partitions, part.name)
		err := part.files.walk(func(rel string, kind byte) error {
			runtime := mount + "/" + rel
			if mount == "/" {
				runtime = "/" + rel
			}
			base := path.Base(rel)
			if forbidden[base] {
				find("forbidden", runtime, base+" must not be in an OpenBook image")
			}
			if kind != 'f' {
				return nil
			}
			elems := strings.Split(runtime, "/")
			for _, d := range elems[:len(elems)-1] {
				if d == "bin" || d == "xbin" {
					if p.bin.MatchString(base) {
						inv.Binaries = append(inv.Binaries, runtime)
						if _, ok := p.ReviewedBinaries[runtime]; !ok {
							find("unreviewed-binary", runtime, "a firmware/TPM/EC tool by name; review it and list it in reviewed_binaries")
						}
					}
					break
				}
			}
			if strings.HasSuffix(base, ".rc") || initDirs[path.Dir(runtime)] {
				if !strings.HasSuffix(base, ".rc") {
					inv.BeyondHost = append(inv.BeyondHost, runtime)
				}
				data, err := readFile(part.files, rel)
				if err != nil {
					return fmt.Errorf("%s: %w", runtime, err)
				}
				_, neutral := p.Neutralised[runtime]
				_, reviewed := p.ReviewedRC[runtime]
				if hits := rcHits(data, p.rc); len(hits) > 0 || neutral || reviewed {
					seen[runtime] = rcSeen{sha256Hex(data), hits}
				}
			}
			switch {
			case strings.HasSuffix(base, ".apex"):
				r, size, err := part.files.open(rel)
				if err != nil {
					return fmt.Errorf("%s: %w", runtime, err)
				}
				files, err := c.apexInitScripts(strings.TrimSuffix(base, ".apex"), r, size)
				if err != nil {
					return fmt.Errorf("%s: %w", runtime, err)
				}
				apexRC = append(apexRC, files...)
			case strings.HasSuffix(base, ".capex"):
				find("unchecked-apex", runtime, "a compressed APEX: the laptop does not read its init scripts")
			}
			return nil
		})
		if err != nil {
			return nil, err
		}
	}
	for _, f := range apexRC {
		if strings.HasSuffix(f.runtime, ".rc") {
			inv.APEXRCFiles++
		} else {
			inv.BeyondHost = append(inv.BeyondHost, f.runtime)
		}
		_, reviewed := p.ReviewedRC[f.runtime]
		if hits := rcHits(f.data, p.rc); len(hits) > 0 || reviewed {
			seen[f.runtime] = rcSeen{sha256Hex(f.data), hits}
		}
	}
	for _, runtime := range p.neutralOrder {
		rule := p.Neutralised[runtime]
		s, ok := seen[runtime]
		state := "missing"
		switch {
		case !ok:
		case s.SHA256 == rule.SHA256:
			state = "neutralised"
		case s.SHA256 == rule.GoogleSHA256:
			state = "google"
		default:
			state = "changed"
		}
		inv.Neutralised[runtime] = state
		if state != "neutralised" && hasSystem && strings.HasPrefix(runtime, "/system/") {
			find("not-neutralised", runtime, map[string]string{
				"missing": "absent: Google removed or moved it; review the rule",
				"google":  "still Google's original: it runs on this image",
				"changed": "neither OpenBook's replacement nor the reviewed Google original"}[state])
		}
	}
	keys := make([]string, 0, len(seen))
	for k := range seen {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, runtime := range keys {
		if _, ok := p.Neutralised[runtime]; ok {
			continue
		}
		s := seen[runtime]
		rule, ok := p.ReviewedRC[runtime]
		switch {
		case !ok:
			find("unreviewed-rc", runtime, "matches "+pyList(s.Matches))
		case rule.SHA256 != s.SHA256:
			find("changed-rc", runtime, fmt.Sprintf("reviewed at %s, now %s; matches %s", rule.SHA256[:12], s.SHA256[:12], pyList(s.Matches)))
		default:
			inv.ReviewedRC[runtime] = rule.Verdict
		}
	}
	for r := range p.ReviewedRC {
		if _, ok := seen[r]; !ok && !strings.HasPrefix(r, "/apex/") && mounts[mountOf(r)] {
			inv.AbsentReviewedRC = append(inv.AbsentReviewedRC, r)
		}
	}
	sort.Strings(inv.AbsentReviewedRC)
	sort.Strings(inv.Binaries)
	sort.Strings(inv.Partitions)
	sort.Strings(inv.BeyondHost)
	inv.RCMatches = seen
	res.Passed = len(res.Findings) == 0
	return res, nil
}

func mountOf(runtime string) string {
	best := "/"
	for _, m := range safetyMounts {
		if m != "/" && (runtime == m || strings.HasPrefix(runtime, m+"/")) && len(m) > len(best) {
			best = m
		}
	}
	return best
}

func sha256Hex(b []byte) string {
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}

// rcHits: the sorted distinct matches on an init script's non-comment lines, lowercased (init treats a line
// whose first non-blank character is # as a comment), decoded and split as Python does.
func rcHits(data []byte, re *regexp.Regexp) []string {
	set := map[string]bool{}
	for _, line := range pySplitLines(pyDecode(data)) {
		s := strings.TrimFunc(line, pySpace)
		if s == "" || s[0] == '#' {
			continue
		}
		for _, m := range re.FindAllString(s, -1) {
			set[strings.ToLower(m)] = true
		}
	}
	out := make([]string, 0, len(set))
	for m := range set {
		out = append(out, m)
	}
	sort.Strings(out)
	return out
}

// pyDecode decodes like bytes.decode("utf-8", "replace"): each maximal ill-formed subpart is one U+FFFD.
func pyDecode(b []byte) string {
	var sb strings.Builder
	for len(b) > 0 {
		if r, n := utf8.DecodeRune(b); r != utf8.RuneError || n > 1 {
			sb.Write(b[:n])
			b = b[n:]
			continue
		}
		n, lo, hi := 1, byte(0x80), byte(0xBF)
		need := 0
		switch c := b[0]; {
		case c >= 0xC2 && c <= 0xDF:
			need = 1
		case c == 0xE0:
			need, lo = 2, 0xA0
		case c == 0xED:
			need, hi = 2, 0x9F
		case c >= 0xE1 && c <= 0xEF:
			need = 2
		case c == 0xF0:
			need, lo = 3, 0x90
		case c == 0xF4:
			need, hi = 3, 0x8F
		case c >= 0xF1 && c <= 0xF3:
			need = 3
		}
		for ; n <= need && n < len(b) && b[n] >= lo && b[n] <= hi; n++ {
			lo, hi = 0x80, 0xBF
		}
		sb.WriteRune(utf8.RuneError)
		b = b[n:]
	}
	return sb.String()
}

// pySplitLines splits as str.splitlines() does.
func pySplitLines(s string) []string {
	var out []string
	start := 0
	for i := 0; i < len(s); {
		r, n := utf8.DecodeRuneInString(s[i:])
		switch r {
		case '\r':
			out = append(out, s[start:i])
			if i+1 < len(s) && s[i+1] == '\n' {
				n = 2
			}
			start = i + n
		case '\n', '\v', '\f', 0x1c, 0x1d, 0x1e, 0x85, 0x2028, 0x2029:
			out = append(out, s[start:i])
			start = i + n
		}
		i += n
	}
	if start < len(s) {
		out = append(out, s[start:])
	}
	return out
}

// pySpace is str.isspace() for one character.
func pySpace(r rune) bool { return unicode.IsSpace(r) || (r >= 0x1c && r <= 0x1f) }

// pyList renders a list of strings as Python's repr does (the host check's finding details).
func pyList(items []string) string {
	parts := make([]string, len(items))
	for i, s := range items {
		q := '\''
		if strings.ContainsRune(s, '\'') && !strings.ContainsRune(s, '"') {
			q = '"'
		}
		var b strings.Builder
		b.WriteRune(q)
		for _, r := range s {
			switch {
			case r == q || r == '\\':
				b.WriteRune('\\')
				b.WriteRune(r)
			case r == '\t':
				b.WriteString(`\t`)
			case r == '\n':
				b.WriteString(`\n`)
			case r == '\r':
				b.WriteString(`\r`)
			case r < 0x20 || r == 0x7f || (r >= 0x80 && r < 0x100 && !unicode.IsPrint(r)):
				fmt.Fprintf(&b, `\x%02x`, r)
			case r >= 0x100 && !unicode.IsPrint(r) && r < 0x10000:
				fmt.Fprintf(&b, `\u%04x`, r)
			case r >= 0x10000 && !unicode.IsPrint(r):
				fmt.Fprintf(&b, `\U%08x`, r)
			default:
				b.WriteRune(r)
			}
		}
		b.WriteRune(q)
		parts[i] = b.String()
	}
	return "[" + strings.Join(parts, ", ") + "]"
}

// checkFirmwareSafety checks an adapted release: its system tree and Google's system_ext and product as
// they will be installed. rulesPath "" takes the rules from the adapted system itself. Findings, or content
// the check cannot read, hold the release.
func checkFirmwareSafety(rulesPath, systemTree, newDir, fsck, work string) (*SafetyResult, error) {
	if rulesPath == "" {
		rulesPath = filepath.Join(systemTree, safetyRulesPath)
	}
	data, err := os.ReadFile(rulesPath)
	if errors.Is(err, os.ErrNotExist) {
		return nil, held("firmware safety: this release carries no firmware-safety rules (/%s), so nothing it adapts is checked", safetyRulesPath)
	} else if err != nil {
		return nil, err
	}
	p, err := loadSafetyPolicy(data)
	if err != nil {
		return nil, held("firmware safety: %v", err)
	}
	defer os.RemoveAll(work)
	c := &safetyCheck{p: p, fsck: fsck, work: work}
	defer c.close()
	parts := []safetyPart{{"system", treeFiles{c, systemTree}}}
	for _, n := range []string{"system_ext", "product"} {
		img := filepath.Join(newDir, n+".img")
		f, err := os.Open(img)
		if err != nil {
			return nil, err
		}
		c.closers = append(c.closers, f)
		files, err := newErofsFiles(c, f, func() (string, error) { return img, nil })
		if err != nil {
			return nil, held("firmware safety: cannot check %s: %v", n, err)
		}
		parts = append(parts, safetyPart{n, files})
	}
	res, err := c.check(parts)
	if err != nil {
		var fe errFormatT
		if errors.As(err, &fe) {
			return nil, held("firmware safety: cannot check %v", err)
		}
		return nil, err
	}
	res.Mode = "adapt"
	if !res.Passed {
		return res, held("firmware safety: %s", summarizeFindings(res.Findings))
	}
	return res, nil
}

func summarizeFindings(f []safetyFinding) string {
	s := fmt.Sprintf("%s %s (%s)", f[0].Kind, f[0].Path, f[0].Detail)
	if len(f) > 1 {
		s += fmt.Sprintf(" and %d more", len(f)-1)
	}
	return s
}

// cmdFirmwareSafety checks partitions (NAME=DIR for an extracted tree, NAME=IMAGE for an EROFS image) as
// check-firmware-safety.py does, for comparing the two on the same input. Exit 8 on findings.
func cmdFirmwareSafety(rules, fsck, work, output string, args []string) error {
	data, err := os.ReadFile(rules)
	if err != nil {
		return err
	}
	p, err := loadSafetyPolicy(data)
	if err != nil {
		return err
	}
	c := &safetyCheck{p: p, fsck: fsck, work: work}
	defer c.close()
	var parts []safetyPart
	for _, a := range args {
		name, loc, ok := strings.Cut(a, "=")
		if _, known := safetyMounts[name]; !ok || !known {
			return fmt.Errorf("expected NAME=DIR or NAME=IMAGE: %s", a)
		}
		st, err := os.Stat(loc)
		if err != nil {
			return err
		}
		if st.IsDir() {
			parts = append(parts, safetyPart{name, treeFiles{c, loc}})
			continue
		}
		f, err := os.Open(loc)
		if err != nil {
			return err
		}
		c.closers = append(c.closers, f)
		files, err := newErofsFiles(c, f, func() (string, error) { return loc, nil })
		if err != nil {
			return err
		}
		parts = append(parts, safetyPart{name, files})
	}
	res, err := c.check(parts)
	if err != nil {
		return err
	}
	res.Mode = "check"
	if output != "" {
		if err := writeJSON(output, res); err != nil {
			return err
		}
	}
	for _, f := range res.Findings {
		fmt.Printf("FINDING %s: %s: %s\n", f.Kind, f.Path, f.Detail)
	}
	fmt.Printf("firmware safety: %s, %d finding(s)\n", map[bool]string{true: "PASS", false: "FAIL"}[res.Passed], len(res.Findings))
	if !res.Passed {
		return held("firmware safety: %s", summarizeFindings(res.Findings))
	}
	return nil
}
