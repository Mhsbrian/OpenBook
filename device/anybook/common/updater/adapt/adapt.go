// SPDX-License-Identifier: Apache-2.0

// Adapt: Google's new system with the OpenBook layer re-applied, rebuilt exactly as the host's rebase builds
// it (scripts/googlebook/rebase-google-build.py with build-input-candidate.rebuild_erofs), then the release's
// vbmeta. It fails closed: a path OpenBook changes that Google changed too stops it as "held", with the
// reason, and nothing is written for installation.
package main

import (
	"bytes"
	"crypto/sha1"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"encoding/xml"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"unsafe"
)

const (
	erofsTimestamp = "1230768000"
	addedContext   = "u:object_r:system_file:s0"
)

func run(name string, args ...string) error {
	cmd := exec.Command(name, args...)
	var out bytes.Buffer
	cmd.Stdout, cmd.Stderr = &out, &out
	if err := cmd.Run(); err != nil {
		tail := out.String()
		if len(tail) > 2000 {
			tail = tail[len(tail)-2000:]
		}
		return fmt.Errorf("%s %s: %v\n%s", filepath.Base(name), strings.Join(args, " "), err, tail)
	}
	return nil
}

func pemDER(path string) ([]byte, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	blk, _ := pem.Decode(b)
	if blk == nil {
		return nil, fmt.Errorf("%s: no PEM block", path)
	}
	return blk.Bytes, nil
}

// contents maps every file and symlink under root to its Entry (as build-input-candidate.contents()).
func contents(root string) (map[string]Entry, error) {
	out := map[string]Entry{}
	err := filepath.Walk(root, func(p string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if p == root || info.IsDir() {
			return nil
		}
		rel, _ := filepath.Rel(root, p)
		e, err := entryOf(root, "/"+rel)
		if err != nil {
			return err
		}
		out["/"+rel] = e
		return nil
	})
	return out, err
}

// pyString is Python's json.dumps() of a string (ensure_ascii).
func pyString(s string) string {
	var b strings.Builder
	b.WriteByte('"')
	for _, r := range s {
		switch {
		case r == '"':
			b.WriteString(`\"`)
		case r == '\\':
			b.WriteString(`\\`)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r == '\t':
			b.WriteString(`\t`)
		case r == '\b':
			b.WriteString(`\b`)
		case r == '\f':
			b.WriteString(`\f`)
		case r < 0x20 || (r > 0x7e && r < 0x10000):
			fmt.Fprintf(&b, `\u%04x`, r)
		case r >= 0x10000:
			r -= 0x10000
			fmt.Fprintf(&b, `\u%04x\u%04x`, 0xd800+(r>>10), 0xdc00+(r&0x3ff))
		default:
			b.WriteRune(r)
		}
	}
	b.WriteByte('"')
	return b.String()
}

// pyContentsJSON is json.dumps(expected, sort_keys=True) of a path -> entry map.
func pyContentsJSON(m map[string]Entry) string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	parts := make([]string, len(keys))
	for i, k := range keys {
		vs := make([]string, len(m[k]))
		for j, v := range m[k] {
			vs[j] = pyString(v)
		}
		parts[i] = pyString(k) + ": [" + strings.Join(vs, ", ") + "]"
	}
	return "{" + strings.Join(parts, ", ") + "}"
}

// uuid5URL is Python's uuid.uuid5(uuid.NAMESPACE_URL, name).
func uuid5URL(name string) string {
	ns, _ := hex.DecodeString("6ba7b8119dad11d180b400c04fd430c8")
	h := sha1.Sum(append(ns, name...))
	u := h[:16]
	u[6] = u[6]&0x0f | 0x50
	u[8] = u[8]&0x3f | 0x80
	x := hex.EncodeToString(u)
	return x[:8] + "-" + x[8:12] + "-" + x[12:16] + "-" + x[16:20] + "-" + x[20:]
}

// reEscape is Python 3.7+ re.escape().
func reEscape(s string) string {
	var b strings.Builder
	for _, r := range s {
		if strings.ContainsRune("()[]{}?*+-|^$\\.&~# \t\n\r\v\f", r) {
			b.WriteByte('\\')
		}
		b.WriteRune(r)
	}
	return b.String()
}

const atSymlinkNofollow = 0x100

var atFDCWD = -100

func lutimesNano(path string, ns int64) error {
	p, err := syscall.BytePtrFromString(path)
	if err != nil {
		return err
	}
	ts := [2]syscall.Timespec{syscall.NsecToTimespec(ns), syscall.NsecToTimespec(ns)}
	_, _, e := syscall.Syscall6(syscall.SYS_UTIMENSAT, uintptr(atFDCWD), uintptr(unsafe.Pointer(p)),
		uintptr(unsafe.Pointer(&ts[0])), atSymlinkNofollow, 0, 0)
	if e != 0 {
		return &os.PathError{Op: "utimensat", Path: path, Err: e}
	}
	return nil
}

// rebuildErofs is build-input-candidate.rebuild_erofs(): set modes and times, write fs_config and file
// contexts from the expected rows, run mkfs.erofs, and prove the image's inventory and contents.
func rebuildErofs(mkfs, fsck, work, source string, expected []string, want map[string]Entry) (string, error) {
	rows := map[string][]string{}
	for _, r := range expected {
		f := strings.SplitN(r, " ", 3)
		rows[f[1]] = append(rows[f[1]], r)
	}
	var fsconfig, ctxs []string
	for _, r := range expected {
		if !strings.HasPrefix(r, "I ") {
			continue
		}
		f := strings.Split(r, " ")
		if len(f) != 9 {
			return "", fmt.Errorf("malformed inventory row %q", r)
		}
		pb, err := hex.DecodeString(f[1])
		if err != nil {
			return "", err
		}
		p := string(pb)
		if strings.ContainsAny(p, " \t\n\r\v\f") {
			return "", errors.New("unsupported whitespace in fs_config path")
		}
		mode, _ := strconv.ParseUint(f[2], 10, 32)
		nlink, _ := strconv.ParseUint(f[5], 10, 32)
		sec, _ := strconv.ParseInt(f[7], 10, 64)
		nsec, _ := strconv.ParseInt(f[8], 10, 64)
		if nlink != 1 && mode&sIFMT != sIFDIR {
			return "", errors.New("hardlinks require explicit topology preservation")
		}
		local := filepath.Join(source, p)
		st, err := os.Lstat(local)
		if err != nil {
			return "", err
		}
		if st.Mode()&os.ModeSymlink == 0 {
			if err := syscall.Chmod(local, uint32(mode&0o7777)); err != nil {
				return "", err
			}
		}
		if err := lutimesNano(local, sec*1e9+nsec); err != nil {
			return "", err
		}
		attrs := map[string][]byte{}
		for _, x := range rows[f[1]] {
			xf := strings.Split(x, " ")
			if xf[0] != "X" {
				continue
			}
			k, _ := hex.DecodeString(xf[2])
			v, _ := hex.DecodeString(xf[3])
			attrs[string(k)] = v
		}
		if _, ok := attrs["security.selinux"]; !ok {
			return "", fmt.Errorf("%s: no SELinux label", p)
		}
		for k := range attrs {
			if k != "security.selinux" && k != "security.capability" {
				return "", fmt.Errorf("%s: unexpected xattr %s", p, k)
			}
		}
		var caps uint64
		if blob, ok := attrs["security.capability"]; ok {
			if len(blob) != 20 {
				return "", errors.New("unsupported capability encoding")
			}
			if le.Uint32(blob) != 0x02000001 || le.Uint32(blob[8:]) != 0 || le.Uint32(blob[16:]) != 0 {
				return "", errors.New("unsupported capability flags")
			}
			caps = uint64(le.Uint32(blob[4:])) | uint64(le.Uint32(blob[12:]))<<32
		}
		fsconfig = append(fsconfig, fmt.Sprintf("%s %s %s %04o capabilities=%#x", strings.TrimLeft(p, "/"), f[3], f[4], mode&0o7777, caps))
		label := string(bytes.TrimRight(attrs["security.selinux"], "\x00"))
		key := "/"
		if p != "" {
			key = reEscape(p)
		}
		ctxs = append(ctxs, key+" "+label)
	}
	if err := os.WriteFile(filepath.Join(work, "expected.metadata"), []byte(strings.Join(expected, "\n")+"\n"), 0o600); err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(work, "fs_config"), []byte(strings.Join(fsconfig, "\n")+"\n"), 0o600); err != nil {
		return "", err
	}
	if err := os.WriteFile(filepath.Join(work, "contexts"), []byte(strings.Join(ctxs, "\n")+"\n"), 0o600); err != nil {
		return "", err
	}
	digest := sha256.Sum256([]byte(strings.Join(expected, "\n") + "\n" + pyContentsJSON(want)))
	fsUUID := uuid5URL("openbook-erofs:" + hex.EncodeToString(digest[:]))
	img := filepath.Join(work, "system.img")
	if err := run(mkfs, "-zlz4hc,9", "-C65536", "-T", erofsTimestamp, "-U", fsUUID, "--preserve-mtime",
		"--fs-config-file="+filepath.Join(work, "fs_config"), "--file-contexts="+filepath.Join(work, "contexts"), img, source); err != nil {
		return "", err
	}
	after, err := inventory(img)
	if err != nil {
		return "", err
	}
	if !sameRows(after, expected) {
		os.WriteFile(filepath.Join(work, "after.metadata"), []byte(strings.Join(after, "\n")+"\n"), 0o600)
		return "", errors.New("the rebuilt system's EROFS metadata differs from the expected rows")
	}
	extracted := filepath.Join(work, "rebuilt")
	if err := run(fsck, "--extract="+extracted, img); err != nil {
		return "", err
	}
	got, err := contents(extracted)
	if err != nil {
		return "", err
	}
	if pyContentsJSON(got) != pyContentsJSON(want) {
		var diff []string
		for k, v := range want {
			if !sameEntry(got[k], v) {
				diff = append(diff, fmt.Sprintf("%s: expected %v, built %v", k, v, got[k]))
			}
		}
		for k, v := range got {
			if want[k] == nil {
				diff = append(diff, fmt.Sprintf("%s: unexpected %v", k, v))
			}
		}
		sort.Strings(diff)
		os.WriteFile(filepath.Join(work, "contents.diff"), []byte(strings.Join(diff, "\n")+"\n"), 0o600)
		return "", fmt.Errorf("the rebuilt system's files differ from the expected contents (%d paths; contents.diff)", len(diff))
	}
	return img, os.RemoveAll(extracted)
}

type AdaptResult struct {
	Schema         string            `json:"schema"`
	Complete       bool              `json:"complete"`
	OldBuild       string            `json:"old_google_build"`
	NewFingerprint string            `json:"new_google_fingerprint"`
	BuildProps     map[string]string `json:"build_properties"`
	Delta          map[string]int    `json:"system_delta"`
	Merged         []string          `json:"merged"`
	PolicyCompiled bool              `json:"policy_compiled"`
	Partitions     map[string]string `json:"partitions_sha256"`
	Unchanged      map[string]string `json:"unchanged_partitions_sha256"`
	VBMetaKey      string            `json:"vbmeta_key_sha256"`
	MetadataRows   int               `json:"metadata_rows"`
	NewLayerSHA256 string            `json:"new_layer_sha256"`
	Installable    bool              `json:"installable"`
	Note           string            `json:"note"`
}

// cmdAdapt adapts a reconstructed Google release with a layer.
func cmdAdapt(fl *flag.FlagSet, args []string) error {
	layerPath := fl.String("layer", "", "the running release's layer directory")
	newDir := fl.String("new", "", "reconstructed Google release (reconstruct --out)")
	oursRoot := fl.String("ours-root", "/", "root of the running release's files")
	keyPath := fl.String("key", "", "AVB signing key (PEM)")
	mkfs := fl.String("mkfs", "mkfs.erofs", "")
	fsck := fl.String("fsck", "fsck.erofs", "")
	secilc := fl.String("secilc", "", "secilc, for a release whose policy inputs changed")
	work := fl.String("work", "", "new scratch directory")
	out := fl.String("out", "", "new directory for the adapted release")
	embed := fl.Bool("embed-layer", true, "write the next round's layer into the adapted system (off: reproduce a release built without one)")
	fl.Parse(args)
	if *layerPath == "" || *newDir == "" || *keyPath == "" || *work == "" || *out == "" {
		usage()
	}
	res, err := adapt(*layerPath, *newDir, *oursRoot, *keyPath, *mkfs, *fsck, *secilc, *work, *out, *embed)
	if res != nil {
		if *out != "" {
			os.MkdirAll(*out, 0o700)
			writeJSON(filepath.Join(*out, "adapt.json"), res)
		}
		b, _ := json.MarshalIndent(map[string]any{"complete": res.Complete, "props": res.BuildProps, "delta": res.Delta,
			"partitions": res.Partitions, "note": res.Note}, "", " ")
		fmt.Println(string(b))
	}
	return err
}

type plan struct {
	expected map[string][]string // path -> expected rows
	merged   map[string][]byte
	added    []string
	removed  []string
	changed  []string
}

func mustEncode(l *Layer) []byte {
	b, _ := encodeLayer(l)
	return b
}

func adapt(layerIn, newDir, oursRoot, keyPath, mkfs, fsck, secilc, work, out string, embed bool) (*AdaptResult, error) {
	res := &AdaptResult{Schema: "openbook-adapt/1", Delta: map[string]int{}, Partitions: map[string]string{}}
	l, err := readLayer(layerIn)
	if err != nil {
		return nil, err
	}
	res.OldBuild = l.Google.Build
	var rec ReconstructResult
	if b, err := os.ReadFile(filepath.Join(newDir, "reconstruct.json")); err != nil {
		return nil, err
	} else if err := json.Unmarshal(b, &rec); err != nil {
		return nil, err
	}
	res.NewFingerprint = rec.Fingerprint
	if rec.GoogleKey != l.Google.AVBKeySHA256 {
		return res, held("Google's release is signed with a different key than the build this release was made from")
	}
	newSystem := filepath.Join(newDir, "system.img")
	for _, n := range adaptedPartitions {
		if sum, err := fileSHA256(filepath.Join(newDir, n+".img")); err != nil || sum != rec.Partitions[n] {
			return res, fmt.Errorf("reconstructed %s differs from its record", n)
		}
	}
	key, err := loadRSAKey(keyPath)
	if err != nil {
		return nil, err
	}
	if err := os.Mkdir(work, 0o700); err != nil {
		return nil, err
	}
	newRowsList, err := inventory(newSystem)
	if err != nil {
		return nil, err
	}
	newRows, err := byPath(newRowsList)
	if err != nil {
		return nil, err
	}
	source := filepath.Join(work, "source")
	if err := run(fsck, "--extract="+source, newSystem); err != nil {
		return nil, err
	}
	newContents, err := contents(source)
	if err != nil {
		return nil, err
	}
	pl, err := planDelta(l, newRows, source)
	if err != nil {
		return res, err
	}
	res.Delta = map[string]int{"added": len(pl.added), "removed": len(pl.removed), "changed": len(pl.changed)}
	for p := range pl.merged {
		res.Merged = append(res.Merged, p)
	}
	sort.Strings(res.Merged)
	// The policy: a new compile is needed only when Google's policy inputs changed.
	policyHashes, err := policyInputHashes(l, fsck, work, newDir, source)
	if err != nil {
		return res, err
	}
	compile, err := policyChanged(l, policyHashes, source)
	if err != nil {
		return res, err
	}
	// The next round's layer: OpenBook's delta against this new Google build.
	next, err := nextLayer(l, newRows, pl, rec, newDir, source, policyHashes)
	if err != nil {
		return res, err
	}
	nextBytes, err := encodeLayer(next)
	if err != nil {
		return res, err
	}
	layerRows := map[string][]string{}
	if embed {
		ns := sha256.Sum256(nextBytes)
		res.NewLayerSHA256 = hex.EncodeToString(ns[:])
		if layerRows, err = layerFileRows(pl.expected, len(nextBytes)); err != nil {
			return res, err
		}
		for p, r := range layerRows {
			pl.expected[p] = r
		}
	} else {
		nextBytes = nil
		if err := os.WriteFile(filepath.Join(work, "next-layer.json"), mustEncode(next), 0o600); err != nil {
			return res, err
		}
	}
	// Apply to the extracted tree.
	if err := applyDelta(l, pl, source, oursRoot, nextBytes); err != nil {
		return res, err
	}
	if compile {
		if secilc == "" {
			return res, held("Google changed the SELinux policy inputs and no policy compiler is available here")
		}
		if err := compilePolicy(l, secilc, source, work); err != nil {
			return res, held("the merged SELinux policy does not compile: %v", err)
		}
		res.PolicyCompiled = true
	}
	if err := checkSeapp(l, source, work); err != nil {
		return res, err
	}
	// Expected rows and contents, from the inputs independently of the tree just assembled.
	var expected []string
	for _, r := range pl.expected {
		expected = append(expected, r...)
	}
	sort.Strings(expected)
	want := map[string]Entry{}
	for p := range pl.expected {
		var e Entry
		switch lp := l.Paths[p]; {
		case pl.merged[p] != nil:
			e = Entry{"file", fmt.Sprintf("%x", sha256.Sum256(pl.merged[p]))}
		case p == layerDir+"/layer.json" && layerRows[p] != nil:
			e = Entry{"file", res.NewLayerSHA256}
		case layerRows[p] != nil:
			e = Entry{"dir"}
		case lp != nil && (lp.Carry == "added" || lp.Carry == "changed"):
			e = lp.OursEntry
		default:
			e = newContents[p]
			if e == nil {
				e = Entry{"dir"}
			}
		}
		if e != nil && e[0] != "dir" {
			want[p] = e
		}
	}
	res.MetadataRows = len(expected)
	img, err := rebuildErofs(mkfs, fsck, work, source, expected, want)
	if err != nil {
		return res, err
	}
	st, err := os.Stat(newSystem)
	if err != nil {
		return res, err
	}
	salt, err := fileSHA256(img)
	if err != nil {
		return res, err
	}
	saltBytes, _ := hex.DecodeString(salt)
	if _, err := addHashtreeFooter(img, uint64(st.Size()), "system", saltBytes); err != nil {
		return res, err
	}
	if err := os.Mkdir(out, 0o700); err != nil {
		return res, err
	}
	if err := os.Rename(img, filepath.Join(out, "system.img")); err != nil {
		return res, err
	}
	for _, n := range []string{"system_ext", "product"} {
		if err := copyFile(filepath.Join(newDir, n+".img"), filepath.Join(out, n+".img")); err != nil {
			return res, err
		}
	}
	// vbmeta: the adapted partitions' own descriptors, the rest from the layer, signed.
	var sources []*VBMeta
	for _, n := range vbmetaOrder {
		var v *VBMeta
		if contains(adaptedPartitions, n) {
			if v, _, err = readImageVBMeta(filepath.Join(out, n+".img")); err != nil {
				return res, err
			}
		} else {
			blob, err := hex.DecodeString(l.Release.VBMeta[n])
			if err != nil || len(blob) == 0 {
				return res, fmt.Errorf("the layer has no vbmeta for %s", n)
			}
			if v, err = parseVBMeta(blob); err != nil {
				return res, err
			}
		}
		sources = append(sources, v)
	}
	vb, err := makeVBMeta(sources, key)
	if err != nil {
		return res, err
	}
	if err := os.WriteFile(filepath.Join(out, "vbmeta.img"), vb, 0o600); err != nil {
		return res, err
	}
	check, _, err := readImageVBMeta(filepath.Join(out, "vbmeta.img"))
	if err != nil {
		return res, err
	}
	if err := check.Verify(); err != nil {
		return res, err
	}
	ks := sha256.Sum256(check.PublicKey)
	res.VBMetaKey = hex.EncodeToString(ks[:])
	for _, d := range check.Descriptors {
		if d.Hashtree != nil && contains(adaptedPartitions, d.Partition) {
			if err := verifyHashtree(filepath.Join(out, d.Partition+".img"), d.Hashtree); err != nil {
				return res, err
			}
		}
	}
	for _, n := range append(append([]string{}, adaptedPartitions...), "vbmeta") {
		if res.Partitions[n], err = fileSHA256(filepath.Join(out, n+".img")); err != nil {
			return res, err
		}
	}
	res.Unchanged = map[string]string{}
	for _, n := range vbmetaOrder {
		if !contains(adaptedPartitions, n) {
			res.Unchanged[n] = l.Release.Partitions[n]
		}
	}
	res.BuildProps = buildProperties(pl.merged[buildProp])
	res.Complete, res.Installable = true, false
	res.Note = "Adapted on this machine; installing it is a later stage (payload, signature, owner approval)."
	return res, os.RemoveAll(source)
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	o, err := os.OpenFile(dst, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	if _, err := io.Copy(o, in); err != nil {
		o.Close()
		return err
	}
	if err := o.Sync(); err != nil {
		o.Close()
		return err
	}
	return o.Close()
}

func buildProperties(prop []byte) map[string]string {
	out := map[string]string{}
	for _, line := range strings.Split(string(prop), "\n") {
		k, v, ok := strings.Cut(line, "=")
		if !ok {
			continue
		}
		switch k {
		case "ro.build.id", "ro.build.version.incremental", "ro.build.version.security_patch",
			"ro.system.build.fingerprint", "ro.dalvik.vm.native.bridge":
			out[k] = v
		}
	}
	return out
}

// planDelta is plan_delta(): the layer checked against NEW, and the merged contents.
func planDelta(l *Layer, newRows map[string][]string, newTree string) (*plan, error) {
	pl := &plan{expected: map[string][]string{}, merged: map[string][]byte{}}
	for p, r := range newRows {
		if !inLayerDir(p) {
			pl.expected[p] = r
		} else if l.Paths[p] != nil {
			return nil, fmt.Errorf("%s: the layer lists its own directory", p)
		}
	}
	paths := make([]string, 0, len(l.Paths))
	for p := range l.Paths {
		paths = append(paths, p)
	}
	sort.Strings(paths)
	newEntry := func(p string) (Entry, error) { return entryOf(newTree, p) }
	unchangedUpstream := func(p string, lp *LayerPath) error {
		ne, err := newEntry(p)
		if err != nil {
			return err
		}
		if !sameRows(newRows[p], lp.Old) || !sameEntry(ne, lp.OldEntry) {
			return held("%s: OpenBook changes it, but Google changed it too", p)
		}
		return nil
	}
	sizeOnly := func(p string, lp *LayerPath) error {
		if newRows[p] == nil || !sameRows(withSize(newRows[p], 0), withSize(lp.Old, 0)) {
			return held("%s: carrying OpenBook's change needs Google's ownership, mode and labels unchanged", p)
		}
		return nil
	}
	var plat []byte
	for _, p := range paths {
		lp := l.Paths[p]
		switch lp.Carry {
		case "removed":
			if err := unchangedUpstream(p, lp); err != nil {
				return nil, err
			}
			delete(pl.expected, p)
			pl.removed = append(pl.removed, p)
		case "added":
			if newRows[p] != nil {
				return nil, held("%s: OpenBook adds it, but Google's new build already has it", p)
			}
			pl.expected[p] = lp.Ours
			pl.added = append(pl.added, p)
		case "changed":
			if err := unchangedUpstream(p, lp); err != nil {
				return nil, err
			}
			pl.expected[p] = lp.Ours
			pl.changed = append(pl.changed, p)
		case "policy_hash":
			pl.changed = append(pl.changed, p) // computed below, after the platform policy
		case "merge3", "append", "insert":
			if err := sizeOnly(p, lp); err != nil {
				return nil, err
			}
			n, err := os.ReadFile(filepath.Join(newTree, p))
			if err != nil {
				return nil, err
			}
			var merged []byte
			switch lp.Carry {
			case "merge3":
				lines := [3][]string{}
				for i, b := range [][]byte{[]byte(l.Data[p+".old"]), []byte(l.Data[p+".ours"]), n} {
					if lines[i], err = textLines(b); err != nil {
						return nil, held("%s: %v", p, err)
					}
				}
				m, err := merge3(lines[0], lines[1], lines[2])
				if err != nil {
					return nil, held("%s: %v", p, err)
				}
				merged = []byte(strings.Join(m, ""))
			case "append":
				tail := []byte(l.Data[p+".tail"])
				if p == platCil {
					if tail, err = rederiveTail(n, tail); err != nil {
						return nil, err
					}
				}
				sep := []byte{}
				if len(tail) > 0 && len(n) > 0 && n[len(n)-1] != '\n' {
					sep = []byte("\n")
				}
				merged = append(append(append([]byte(nil), n...), sep...), tail...)
				if p == platCil {
					plat = merged
				}
			case "insert":
				if merged, err = reinsertBlock(n, []byte(l.Data[p+".block"]), inserted[p]); err != nil {
					return nil, held("%s: %v", p, err)
				}
				if err := checkSigners(merged, l.OpenBookCert); err != nil {
					return nil, held("%s: %v", p, err)
				}
			}
			pl.merged[p] = merged
			pl.expected[p] = withSize(newRows[p], len(merged))
			pl.changed = append(pl.changed, p)
		default:
			return nil, fmt.Errorf("%s: unknown carry %q", p, lp.Carry)
		}
	}
	if lp := l.Paths[policyHash]; lp != nil {
		if err := sizeOnly(policyHash, lp); err != nil {
			return nil, err
		}
		if plat == nil {
			var err error
			if plat, err = os.ReadFile(filepath.Join(newTree, platCil)); err != nil {
				return nil, err
			}
		}
		mapping, err := os.ReadFile(filepath.Join(newTree, "system/etc/selinux/mapping", l.MappingCil))
		if err != nil {
			return nil, held("Google's new build has no mapping/%s for the platform policy hash", l.MappingCil)
		}
		pl.merged[policyHash] = []byte(fmt.Sprintf("%x\n", sha256.Sum256(append(append([]byte(nil), plat...), mapping...))))
		pl.expected[policyHash] = withSize(newRows[policyHash], len(pl.merged[policyHash]))
	}
	return pl, nil
}

// checkSigners: the merged signer list parses, and its one "openbook" signer is the OpenBook certificate.
func checkSigners(x []byte, certHex string) error {
	if certHex == "" {
		return nil
	}
	var doc struct {
		Signers []struct {
			Signature string `xml:"signature,attr"`
			Seinfo    *struct {
				Value string `xml:"value,attr"`
			} `xml:"seinfo"`
		} `xml:"signer"`
	}
	dec := xml.NewDecoder(bytes.NewReader(x))
	dec.CharsetReader = func(label string, in io.Reader) (io.Reader, error) {
		switch strings.ToLower(label) {
		case "iso-8859-1", "latin-1", "latin1", "us-ascii":
			b, err := io.ReadAll(in)
			if err != nil {
				return nil, err
			}
			r := make([]rune, len(b))
			for i, c := range b {
				r[i] = rune(c)
			}
			return strings.NewReader(string(r)), nil
		}
		return nil, fmt.Errorf("unsupported XML encoding %s", label)
	}
	if err := dec.Decode(&doc); err != nil {
		return err
	}
	var ours []string
	for _, s := range doc.Signers {
		if s.Seinfo != nil && s.Seinfo.Value == "openbook" {
			ours = append(ours, s.Signature)
		}
	}
	if len(ours) != 1 || ours[0] != certHex {
		return errors.New("the merged signer list does not hold exactly the OpenBook certificate as seinfo openbook")
	}
	return nil
}

// applyDelta turns the extracted NEW tree into the adapted tree. OpenBook's own files come from the running
// release (oursRoot) and must match the layer byte for byte.
func applyDelta(l *Layer, pl *plan, source, oursRoot string, nextLayer []byte) error {
	removed := append([]string(nil), pl.removed...)
	sort.Slice(removed, func(i, j int) bool { return strings.Count(removed[i], "/") > strings.Count(removed[j], "/") })
	for _, p := range removed {
		if err := os.Remove(filepath.Join(source, p)); err != nil {
			return err
		}
	}
	var copyPaths []string
	for _, p := range append(append([]string{}, pl.added...), pl.changed...) {
		if pl.merged[p] == nil {
			copyPaths = append(copyPaths, p)
		}
	}
	sort.SliceStable(copyPaths, func(i, j int) bool { return strings.Count(copyPaths[i], "/") < strings.Count(copyPaths[j], "/") })
	for _, p := range copyPaths {
		lp := l.Paths[p]
		have, err := entryOf(oursRoot, p)
		if err != nil {
			return fmt.Errorf("%s: %v", p, err)
		}
		if !sameEntry(have, lp.OursEntry) {
			return fmt.Errorf("%s: the running release's copy differs from its layer", p)
		}
		dst := filepath.Join(source, p)
		switch lp.OursEntry[0] {
		case "symlink":
			if _, err := os.Lstat(dst); err == nil {
				if err := os.Remove(dst); err != nil {
					return err
				}
			}
			if err := os.Symlink(lp.OursEntry[1], dst); err != nil {
				return err
			}
		case "dir":
			if err := os.Mkdir(dst, 0o755); err != nil && !os.IsExist(err) {
				return err
			}
		default:
			if _, err := os.Lstat(dst); err == nil {
				if err := os.Remove(dst); err != nil {
					return err
				}
			}
			if err := copyFile(filepath.Join(oursRoot, p), dst); err != nil {
				return err
			}
			if sum, err := fileSHA256(dst); err != nil || sum != lp.OursEntry[1] {
				return fmt.Errorf("%s: copy does not match the layer", p)
			}
		}
	}
	for p, data := range pl.merged {
		if err := os.WriteFile(filepath.Join(source, p), data, 0o644); err != nil {
			return err
		}
	}
	dir := filepath.Join(source, layerDir)
	if nextLayer == nil {
		return nil
	}
	for _, d := range []string{filepath.Dir(dir), dir} {
		if err := os.Mkdir(d, 0o755); err != nil && !os.IsExist(err) {
			return err
		}
	}
	if nextLayer == nil {
		return nil
	}
	return os.WriteFile(filepath.Join(dir, "layer.json"), nextLayer, 0o644)
}

// layerFileRows adds the rows of the layer files an adaptation writes: the layer directory and its
// layer.json, and /system/etc/openbook unless the release already carries it (a new directory there also
// adds a link to /system/etc, as EROFS counts a directory's subdirectories in its link count).
func layerFileRows(expected map[string][]string, size int) (map[string][]string, error) {
	label := hex.EncodeToString([]byte(addedContext))
	sel := hex.EncodeToString([]byte("security.selinux"))
	row := func(p string, mode, nlink, size int) []string {
		h := hex.EncodeToString([]byte(p))
		return []string{fmt.Sprintf("I %s %d 0 0 %d %d %s 0", h, mode, nlink, size, erofsTimestamp),
			fmt.Sprintf("X %s %s %s", h, sel, label)}
	}
	parent := filepath.Dir(layerDir)
	if expected[layerDir] != nil || expected[layerDir+"/layer.json"] != nil {
		return nil, errors.New("the layer directory is already in the expected tree")
	}
	add := map[string][]string{
		layerDir:                 row(layerDir, sIFDIR|0o755, 2, 0),
		layerDir + "/layer.json": row(layerDir+"/layer.json", 0o100644, 1, size),
	}
	if expected[parent] == nil {
		add[parent] = row(parent, sIFDIR|0o755, 3, 0)
		grand := filepath.Dir(parent)
		rows := expected[grand]
		if rows == nil {
			return nil, fmt.Errorf("%s is missing", grand)
		}
		bumped := make([]string, len(rows))
		for i, r := range rows {
			f := strings.Split(r, " ")
			if f[0] == "I" {
				n, err := strconv.Atoi(f[5])
				if err != nil {
					return nil, err
				}
				f[5] = strconv.Itoa(n + 1)
			}
			bumped[i] = strings.Join(f, " ")
		}
		add[grand] = bumped
	} else {
		// The release carries the directory: it gains the layer subdirectory unless it already counts it.
		return nil, errors.New("a release that carries /system/etc/openbook must list the layer directory in its link count; not supported yet")
	}
	return add, nil
}

// nextLayer is OpenBook's delta against NEW, for the next adaptation.
func nextLayer(l *Layer, newRows map[string][]string, pl *plan, rec ReconstructResult, newDir, newTree string, policy map[string]string) (*Layer, error) {
	n := &Layer{Schema: layerSchema, Paths: map[string]*LayerPath{}, Data: map[string]string{},
		MappingCil: l.MappingCil, OpenBookCert: l.OpenBookCert, VendorPolicy: l.VendorPolicy}
	n.Google.Build = buildProperties(pl.merged[buildProp])["ro.build.version.incremental"]
	if n.Google.Build == "" {
		n.Google.Build = "unknown"
	}
	n.Google.Fingerprint = rec.Fingerprint
	n.Google.SystemSHA256 = rec.Partitions["system"]
	n.Google.AVBKeySHA256 = rec.GoogleKey
	n.Google.PolicySHA256 = policy
	n.Release.VBMeta, n.Release.Partitions, n.Release.Sizes = l.Release.VBMeta, map[string]string{}, map[string]uint64{}
	for k, v := range l.Release.Partitions {
		n.Release.Partitions[k] = v
		n.Release.Sizes[k] = l.Release.Sizes[k]
	}
	// Google's partitions of the new build become the installed ones.
	for _, k := range []string{"system_ext", "product"} {
		st, err := os.Stat(filepath.Join(newDir, k+".img"))
		if err != nil {
			return nil, err
		}
		n.Release.Partitions[k], n.Release.Sizes[k] = rec.Partitions[k], uint64(st.Size())
	}
	for p, lp := range l.Paths {
		np := &LayerPath{Ours: pl.expected[p], OursEntry: lp.OursEntry, Carry: lp.Carry}
		if lp.Carry != "added" {
			np.Old = newRows[p]
			ne, err := entryOf(newTree, p)
			if err != nil {
				return nil, err
			}
			np.OldEntry = ne
		}
		if lp.Carry == "removed" {
			np.Ours = nil
		}
		if b := pl.merged[p]; b != nil {
			np.OursEntry = Entry{"file", fmt.Sprintf("%x", sha256.Sum256(b))}
		}
		n.Paths[p] = np
	}
	for k, v := range l.Data {
		n.Data[k] = v
	}
	for p, lp := range l.Paths {
		if lp.Carry == "append" {
			nb, err := os.ReadFile(filepath.Join(newTree, p))
			if err != nil {
				return nil, err
			}
			n.Data[p+".tail"] = string(pl.merged[p][len(nb):])
		}
	}
	if pl.merged[buildProp] != nil {
		old, err := os.ReadFile(filepath.Join(newTree, buildProp))
		if err != nil {
			return nil, err
		}
		n.Data[buildProp+".old"], n.Data[buildProp+".ours"] = string(old), string(pl.merged[buildProp])
	}
	return n, nil
}

// policyChanged: the merged policy needs a new compile when any of Google's policy inputs differs from the
// build the running release was compiled from (the platform policy itself, the files beside it, and the
// system_ext and product policies). Otherwise the merged policy is the running one.
func policyChanged(l *Layer, got map[string]string, newTree string) (bool, error) {
	changed := len(got) != len(l.Google.PolicySHA256)
	for k, v := range got {
		if l.Google.PolicySHA256[k] != v {
			changed = true
		}
	}
	if lp := l.Paths[platCil]; lp != nil {
		e, err := entryOf(newTree, platCil)
		if err != nil {
			return false, err
		}
		if !sameEntry(e, lp.OldEntry) {
			changed = true
		}
	}
	return changed, nil
}

func compilePolicy(l *Layer, secilc, source, work string) error {
	version := strings.TrimSpace(l.VendorPolicy["plat_sepolicy_vers.txt"])
	genfs := strings.TrimSpace(l.VendorPolicy["genfs_labels_version.txt"])
	vdir := filepath.Join(work, "vendor-policy")
	if err := os.MkdirAll(vdir, 0o700); err != nil {
		return err
	}
	for _, n := range []string{"plat_pub_versioned.cil", "vendor_sepolicy.cil"} {
		if err := os.WriteFile(filepath.Join(vdir, n), []byte(l.VendorPolicy[n]), 0o600); err != nil {
			return err
		}
	}
	se := filepath.Join(source, "system/etc/selinux")
	inputs := []string{filepath.Join(se, "plat_sepolicy.cil"), filepath.Join(se, "mapping", version+".cil"),
		filepath.Join(vdir, "plat_pub_versioned.cil"), filepath.Join(vdir, "vendor_sepolicy.cil"),
		filepath.Join(se, "plat_sepolicy_genfs_"+genfs+".cil")}
	for _, n := range []string{"system_ext", "product"} {
		d := filepath.Join(work, "policy-"+n)
		if st, err := os.Stat(filepath.Join(d, "etc/selinux")); err == nil && st.IsDir() {
			d = filepath.Join(d, "etc/selinux")
		}
		inputs = append(inputs, filepath.Join(d, n+"_sepolicy.cil"), filepath.Join(d, "mapping", version+".cil"))
	}
	args := append([]string{"-m", "-M", "true", "-G", "-c", "33", "-o", filepath.Join(work, "policy.bin"), "-f", "/dev/null"}, inputs...)
	return run(secilc, args...)
}

// checkSeapp: every domain and type OpenBook's appended app contexts name is declared by the merged policy
// (the part of checkseapp that concerns OpenBook's own lines).
func checkSeapp(l *Layer, source, work string) error {
	tail := l.Data[seappPath+".tail"]
	if tail == "" {
		return nil
	}
	plat, err := os.ReadFile(filepath.Join(source, platCil))
	if err != nil {
		return err
	}
	declared := map[string]bool{}
	for _, line := range strings.Split(string(plat), "\n") {
		for _, pre := range []string{"(type ", "(typeattribute "} {
			if strings.HasPrefix(line, pre) && strings.HasSuffix(line, ")") {
				declared[strings.TrimSuffix(strings.TrimPrefix(line, pre), ")")] = true
			}
		}
	}
	for _, line := range strings.Split(tail, "\n") {
		if strings.HasPrefix(strings.TrimSpace(line), "#") {
			continue
		}
		for _, f := range strings.Fields(line) {
			k, v, ok := strings.Cut(f, "=")
			if ok && (k == "domain" || k == "type") && !declared[v] {
				return held("OpenBook's app context names %s=%s, which the merged policy does not declare", k, v)
			}
		}
	}
	return nil
}
