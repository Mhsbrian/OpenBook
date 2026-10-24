// SPDX-License-Identifier: Apache-2.0
package main

import (
	"bytes"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// Reference values computed with CPython 3 (json.dumps, uuid.uuid5, re.escape), which the host build uses.
func TestPythonCompatibleEncodings(t *testing.T) {
	got := pyContentsJSON(map[string]Entry{
		"/b":           {"file", "x"},
		"/a\u00e9\"\\": {"symlink", "tab\there\u0001"},
		"/z\U0001F600": {"file", "\x7f"},
	})
	want := `{"/a\u00e9\"\\": ["symlink", "tab\there\u0001"], "/b": ["file", "x"], "/z\ud83d\ude00": ["file", "\u007f"]}`
	if got != want {
		t.Fatalf("json.dumps:\n got %s\nwant %s", got, want)
	}
	if u := uuid5URL("openbook-erofs:abc"); u != "7a645b5a-2a32-5cbd-9210-41e167cce05b" {
		t.Fatalf("uuid5: %s", u)
	}
	if e := reEscape("/system/lib64/libfoo-bar.so#1 &x~y"); e != `/system/lib64/libfoo\-bar\.so\#1\ \&x\~y` {
		t.Fatalf("re.escape: %s", e)
	}
}

func lines(items ...string) []string {
	var out []string
	for _, x := range items {
		out = append(out, x+"\n")
	}
	return out
}

// The cases of scripts/googlebook/rebase-google-build-test.py.
func TestMerge3(t *testing.T) {
	old := lines("ro.build.id=OLD", "ro.build.date=1", "a=1", "ro.dalvik.vm.native.bridge=libhoudini.so",
		"ro.berberis.is_2nd_native_bridge=true", "ro.berberis.version=16.0.0", "b=2", "c=3")
	nw := lines("ro.build.id=NEW", "ro.build.date=2", "a=1", "ro.dalvik.vm.native.bridge=libhoudini.so",
		"ro.berberis.is_2nd_native_bridge=true", "ro.berberis.version=16.0.0", "b=2", "c=3")
	ours := lines("ro.build.id=OLD", "ro.build.date=1", "a=1", "ro.dalvik.vm.native.bridge=libberberis_arm64.so",
		"ro.berberis.is_2nd_native_bridge=false", "b=2", "ro.berberis.flags=disable-ir-check", "c=3")
	got, err := merge3(old, ours, nw)
	want := lines("ro.build.id=NEW", "ro.build.date=2", "a=1", "ro.dalvik.vm.native.bridge=libberberis_arm64.so",
		"ro.berberis.is_2nd_native_bridge=false", "b=2", "ro.berberis.flags=disable-ir-check", "c=3")
	if err != nil || strings.Join(got, "") != strings.Join(want, "") {
		t.Fatalf("edits on the new build: %v %q", err, got)
	}
	got, err = merge3(old, append(append([]string{}, old...), "z=9\n"), nw)
	if err != nil || strings.Join(got, "") != strings.Join(append(append([]string{}, nw...), "z=9\n"), "") {
		t.Fatalf("append at end: %v %q", err, got)
	}
	if _, err := merge3(old, append(lines("ro.build.id=OURS"), old[1:]...), nw); err == nil || !strings.Contains(err.Error(), "overlaps an upstream change") {
		t.Fatalf("edit of a changed line: %v", err)
	}
	ours2 := append(append(append([]string{}, old[:2]...), "inserted=1\n"), old[2:]...)
	new2 := append(append(append([]string{}, old[:2]...), "a=CHANGED\n"), old[3:]...)
	if _, err := merge3(old, ours2, new2); err == nil || !strings.Contains(err.Error(), "overlaps an upstream change") {
		t.Fatalf("edit next to a change: %v", err)
	}
	if _, err := textLines([]byte("a=1\r\nb=2\n")); err == nil {
		t.Fatal("CRLF must be refused")
	}
}

func TestReinsert(t *testing.T) {
	old := []byte("<policy>\n<signer signature=\"00\"/>\n</policy>\n")
	block := []byte("<signer signature=\"ab\"><seinfo value=\"openbook\"/></signer>\n")
	ours := append(append(append([]byte{}, old[:bytes.LastIndex(old, []byte("</policy>"))]...), block...), []byte("</policy>\n")...)
	got, err := insertedBlock(old, ours, []byte("</policy>"))
	if err != nil || !bytes.Equal(got, block) {
		t.Fatalf("block: %v %q", err, got)
	}
	nw := []byte("<policy>\n<signer signature=\"00\"/>\n<signer signature=\"01\"/>\n</policy>\n")
	merged, err := reinsertBlock(nw, block, []byte("</policy>"))
	if err != nil || !bytes.Equal(merged, []byte("<policy>\n<signer signature=\"00\"/>\n<signer signature=\"01\"/>\n"+string(block)+"</policy>\n")) {
		t.Fatalf("reinsert: %v %q", err, merged)
	}
	if err := checkSigners(merged, "ab"); err != nil {
		t.Fatalf("signer: %v", err)
	}
	if err := checkSigners(merged, "cd"); err == nil {
		t.Fatal("a different certificate must be refused")
	}
	if _, err := insertedBlock(old, append([]byte("x"), ours...), []byte("</policy>")); err == nil {
		t.Fatal("an edit elsewhere must be refused")
	}
	if _, err := reinsertBlock(merged, block, []byte("</policy>")); err == nil {
		t.Fatal("NEW already holding the block must be refused")
	}
	if _, err := reinsertBlock(append(nw, []byte("<!-- </policy> -->")...), block, []byte("</policy>")); err == nil {
		t.Fatal("two markers must be refused")
	}
}

func TestSubDomain(t *testing.T) {
	for in, want := range map[string]string{
		"(allow priv_app x (file (read)))":                  "(allow @D@ x (file (read)))",
		"(typetransition priv_app_userfaultfd y)":           "(typetransition @D@_userfaultfd y)",
		"(allow priv_app_36 z)":                             "(allow priv_app_36 z)",
		"(allow priv_apps z)":                               "(allow priv_apps z)",
		"(allow xpriv_app z)":                               "(allow xpriv_app z)",
		"(allow priv_app_wrapfd priv_app_block_io_uring q)": "(allow @D@_wrapfd @D@_block_io_uring q)",
		"(allow priv_app_userfaultfdx z)":                   "(allow priv_app_userfaultfdx z)",
	} {
		if got := subDomain(in, "priv_app", "@D@"); got != want {
			t.Errorf("%s: got %s", in, got)
		}
	}
}

func TestAppDomainStatements(t *testing.T) {
	var plat strings.Builder
	for i, d := range templateDomains {
		plat.WriteString("(type " + d + ")\n(typetransition " + d + " tmpfs file appdomain_tmpfs)\n")
		plat.WriteString("(allow " + d + " appdomain_tmpfs (file (read write getattr map execute)))\n")
		plat.WriteString("(typeattributeset base_typeattr_" + string(rune('1'+i)) + " (and (domain) (not (" + d + "))))\n")
		plat.WriteString("(neverallow base_typeattr_" + string(rune('1'+i)) + " " + d + " (process (ptrace)))\n")
	}
	plat.WriteString("(allow gmscore_app extra (file (read)))\n")
	got, err := appDomainStatements(plat.String())
	if err != nil {
		t.Fatal(err)
	}
	want := []string{
		"(allow openbook_update_app appdomain_tmpfs (file (read write getattr map execute)))",
		"(typeattribute openbook_update_app_x1)",
		"(typeattributeset openbook_update_app_x1 (and (domain) (not (openbook_update_app))))",
		"(neverallow openbook_update_app_x1 openbook_update_app (process (ptrace)))",
		"(type openbook_update_app)",
		"(typetransition openbook_update_app tmpfs file appdomain_tmpfs)",
	}
	if strings.Join(got, "\n") != strings.Join(want, "\n") {
		t.Fatalf("got:\n%s", strings.Join(got, "\n"))
	}
	var h errHeld
	if _, err := appDomainStatements("(type priv_app)\n"); !errors.As(err, &h) {
		t.Fatalf("missing shared statements must hold: %v", err)
	}
}

func naiveTree(data, salt []byte) []byte {
	level := data
	for {
		var next []byte
		for i := 0; i < len(level); i += 4096 {
			blk := make([]byte, 4096)
			copy(blk, level[i:min(i+4096, len(level))])
			s := sha256.Sum256(append(append([]byte{}, salt...), blk...))
			next = append(next, s[:]...)
		}
		if len(next) <= 32 {
			return next
		}
		if len(next)%4096 != 0 {
			next = append(next, make([]byte, 4096-len(next)%4096)...)
		}
		level = next
		if len(level) == 4096 {
			s := sha256.Sum256(append(append([]byte{}, salt...), level...))
			return s[:]
		}
	}
}

func TestHashTree(t *testing.T) {
	salt := []byte("salt")
	for _, n := range []int{4096, 8192, 4096*129 + 7, 1 << 20, 4096 * 4096 * 2} {
		data := make([]byte, n)
		rand.Read(data)
		root, _, err := hashTree(bytes.NewReader(data), uint64(n), salt)
		if err != nil {
			t.Fatal(err)
		}
		if want := naiveTree(data, salt); !bytes.Equal(root, want) {
			t.Fatalf("size %d: root %x, want %x", n, root, want)
		}
	}
}

func testKey(t *testing.T) (*rsa.PrivateKey, string) {
	t.Helper()
	k, err := rsa.GenerateKey(rand.Reader, 4096)
	if err != nil {
		t.Fatal(err)
	}
	return k, ""
}

func TestFooterAndVBMeta(t *testing.T) {
	dir := t.TempDir()
	img := filepath.Join(dir, "system.img")
	data := make([]byte, 3<<20+100)
	rand.Read(data)
	if err := os.WriteFile(img, data, 0o600); err != nil {
		t.Fatal(err)
	}
	salt := bytes.Repeat([]byte{7}, 32)
	if _, err := addHashtreeFooter(img, 8<<20, "system", salt); err != nil {
		t.Fatal(err)
	}
	st, _ := os.Stat(img)
	if st.Size() != 8<<20 {
		t.Fatalf("image size %d", st.Size())
	}
	v, foot, err := readImageVBMeta(img)
	if err != nil || foot == nil || foot.OriginalSize != uint64(len(data)) {
		t.Fatalf("footer: %v %+v", err, foot)
	}
	if len(v.Descriptors) != 1 || v.Descriptors[0].Hashtree == nil || v.Descriptors[0].Hashtree.ImageSize != roundUp(uint64(len(data)), 4096) {
		t.Fatalf("descriptor: %+v", v.Descriptors)
	}
	if err := verifyHashtree(img, v.Descriptors[0].Hashtree); err != nil {
		t.Fatal(err)
	}
	if _, err := addHashtreeFooter(img, 8<<20, "system", salt); err == nil {
		t.Fatal("a second footer must be refused")
	}
	small := filepath.Join(dir, "small.img")
	os.WriteFile(small, data, 0o600)
	if _, err := addHashtreeFooter(small, 3<<20, "system", salt); err == nil {
		t.Fatal("an image too large for its partition must be refused")
	}
	key, _ := testKey(t)
	blob, err := makeVBMeta([]*VBMeta{v}, key)
	if err != nil {
		t.Fatal(err)
	}
	if len(blob)%4096 != 0 {
		t.Fatal("vbmeta is padded to 4096")
	}
	top, err := parseVBMeta(blob)
	if err != nil {
		t.Fatal(err)
	}
	if err := top.Verify(); err != nil {
		t.Fatal(err)
	}
	if pub, _ := decodeAVBPublicKey(top.PublicKey); pub.N.Cmp(key.N) != 0 || !bytes.Equal(encodeAVBPublicKey(pub), top.PublicKey) {
		t.Fatal("public key round trip")
	}
	tampered := append([]byte{}, blob...)
	tampered[256+576+40] ^= 1 // inside the auxiliary block (the descriptor)
	if bad, err := parseVBMeta(tampered); err == nil && bad.Verify() == nil {
		t.Fatal("a modified vbmeta must not verify")
	}
	// Corrupt one data block: the root digest no longer matches.
	f, _ := os.OpenFile(img, os.O_RDWR, 0)
	f.WriteAt([]byte{0xff}, 12345)
	f.Close()
	if err := verifyHashtree(img, v.Descriptors[0].Hashtree); err == nil {
		t.Fatal("a modified image must not verify")
	}
}

func TestDescriptorOrderAndDedup(t *testing.T) {
	mk := func(name string) Descriptor {
		h := &HashDesc{ImageSize: 4096, HashAlgorithm: "sha256", PartitionName: name, Salt: []byte{1}, Digest: make([]byte, 32)}
		return Descriptor{Tag: tagHash, Raw: h.Encode(), Partition: name, Hash: h}
	}
	ht := &HashtreeDesc{DmVerityVersion: 1, ImageSize: 4096, TreeOffset: 4096, DataBlockSize: 4096, HashBlockSize: 4096,
		HashAlgorithm: "sha256", PartitionName: "product", RootDigest: make([]byte, 32)}
	prop := []byte{0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 24, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 'k', 0, 'v', 0, 0, 0, 0, 0}
	parsed, err := parseDescriptors(prop)
	if err != nil {
		t.Fatal(err)
	}
	a := &VBMeta{Descriptors: append([]Descriptor{{Tag: tagHashtree, Raw: ht.Encode(), Partition: "product", Hashtree: ht}}, parsed...)}
	b := &VBMeta{Descriptors: []Descriptor{mk("boot"), mk("boot")}}
	key, _ := testKey(t)
	blob, err := makeVBMeta([]*VBMeta{a, b}, key)
	if err != nil {
		t.Fatal(err)
	}
	v, _ := parseVBMeta(blob)
	var names []string
	for _, d := range v.Descriptors {
		names = append(names, map[uint64]string{0: "prop", 1: "tree:", 2: "hash:"}[d.Tag]+d.Partition)
	}
	// Properties keep their order; named descriptors once each, sorted by kind and name (hash before tree).
	if strings.Join(names, ",") != "prop,hash:boot,tree:product" {
		t.Fatalf("order: %v", names)
	}
}

func TestParseGPTAndLP(t *testing.T) {
	head := make([]byte, 1<<20)
	copy(head[512:], "EFI PART")
	le.PutUint64(head[512+72:], 2)
	le.PutUint32(head[512+80:], 4)
	le.PutUint32(head[512+84:], 128)
	ent := head[1024:]
	le.PutUint64(ent[32:], 2048)
	le.PutUint64(ent[40:], 4095)
	ent[0] = 1
	for i, r := range "super" {
		le.PutUint16(ent[56+2*i:], uint16(r))
	}
	parts, err := parseGPT(head)
	if err != nil || len(parts) != 1 || parts[0].Name != "super" || parts[0].Offset != 2048*512 || parts[0].Length != 2048*512 {
		t.Fatalf("gpt: %v %+v", err, parts)
	}
	// A minimal liblp metadata region: one partition with one linear extent.
	region := make([]byte, 4096+2*4096+65536)
	g := region[4096:]
	le.PutUint32(g, 0x616c4467)
	le.PutUint32(g[4:], 52)
	le.PutUint32(g[40:], 65536)
	le.PutUint32(g[44:], 2)
	le.PutUint32(g[48:], 4096)
	sum := sha256.Sum256(g[:52])
	copy(g[8:40], sum[:])
	h := region[12288:]
	le.PutUint32(h, 0x414C5030)
	le.PutUint16(h[4:], 10)
	le.PutUint32(h[8:], 128)
	tables := make([]byte, 52+24)
	copy(tables, "system_a")
	le.PutUint32(tables[40:], 0)
	le.PutUint32(tables[44:], 1)
	le.PutUint64(tables[52:], 8)
	le.PutUint64(tables[52+12:], 2048)
	le.PutUint32(h[44:], uint32(len(tables)))
	ts := sha256.Sum256(tables)
	copy(h[48:80], ts[:])
	le.PutUint32(h[80:], 0)
	le.PutUint32(h[84:], 1)
	le.PutUint32(h[88:], 52)
	le.PutUint32(h[92:], 52)
	le.PutUint32(h[96:], 1)
	le.PutUint32(h[100:], 24)
	copy(h[128:], tables)
	hs := sha256.Sum256(h[:128])
	copy(h[12:44], hs[:])
	lp, err := parseLP(region)
	if err != nil || len(lp["system_a"]) != 1 || lp["system_a"][0] != (lpExtent{8, 2048}) {
		t.Fatalf("lp: %v %+v", err, lp)
	}
	h[128] ^= 1
	if _, err := parseLP(region); err == nil {
		t.Fatal("a corrupted table must be refused")
	}
}

// A layer checked against a synthetic NEW tree: each fail-closed rule holds.
func TestPlanDeltaHolds(t *testing.T) {
	root := t.TempDir()
	write := func(p, s string) {
		os.MkdirAll(filepath.Dir(filepath.Join(root, p)), 0o755)
		os.WriteFile(filepath.Join(root, p), []byte(s), 0o644)
	}
	row := func(p string, size int) []string {
		hp := hex.EncodeToString([]byte(p))
		return []string{"I " + hp + " 33188 0 0 1 " + itoa(size) + " 1230768000 0", "X " + hp + " 73656c " + "6c"}
	}
	write("/system/lib/a.so", "google")
	write("/system/lib/gone.so", "google")
	sha := func(s string) string { x := sha256.Sum256([]byte(s)); return hex.EncodeToString(x[:]) }
	newRows := map[string][]string{"/system/lib/a.so": row("/system/lib/a.so", 6), "/system/lib/gone.so": row("/system/lib/gone.so", 6)}
	base := func() *Layer {
		return &Layer{Schema: layerSchema, Data: map[string]string{}, Paths: map[string]*LayerPath{
			"/system/lib/a.so":    {Old: row("/system/lib/a.so", 6), OldEntry: Entry{"file", sha("google")}, Ours: row("/system/lib/a.so", 4), OursEntry: Entry{"file", sha("ours")}, Carry: "changed"},
			"/system/lib/gone.so": {Old: row("/system/lib/gone.so", 6), OldEntry: Entry{"file", sha("google")}, Carry: "removed"},
			"/system/lib/new.so":  {Ours: row("/system/lib/new.so", 3), OursEntry: Entry{"file", sha("new")}, Carry: "added"},
		}}
	}
	pl, err := planDelta(base(), newRows, root)
	if err != nil {
		t.Fatal(err)
	}
	if len(pl.added) != 1 || len(pl.removed) != 1 || len(pl.changed) != 1 || pl.expected["/system/lib/gone.so"] != nil {
		t.Fatalf("plan: %+v", pl)
	}
	var h errHeld
	write("/system/lib/a.so", "google2")
	if _, err := planDelta(base(), newRows, root); !errors.As(err, &h) {
		t.Fatalf("Google changing a file OpenBook changes must hold: %v", err)
	}
	write("/system/lib/a.so", "google")
	nr := map[string][]string{"/system/lib/new.so": row("/system/lib/new.so", 1)}
	for k, v := range newRows {
		nr[k] = v
	}
	if _, err := planDelta(base(), nr, root); !errors.As(err, &h) {
		t.Fatalf("Google adding a path OpenBook adds must hold: %v", err)
	}
	write("/system/lib/gone.so", "google, changed")
	if _, err := planDelta(base(), newRows, root); !errors.As(err, &h) {
		t.Fatalf("Google changing a file OpenBook removes must hold: %v", err)
	}
}

func itoa(n int) string { return strconv.Itoa(n) }
