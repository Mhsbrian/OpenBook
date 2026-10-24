// SPDX-License-Identifier: Apache-2.0
package main

import (
	"archive/zip"
	"bytes"
	"compress/gzip"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

// Reference values computed with CPython 3 and check-firmware-safety.py's rc_hits, on the real rc_pattern.
func TestRCHitsMatchPython(t *testing.T) {
	data, err := os.ReadFile("../../safety/firmware-safety.json")
	if err != nil {
		t.Fatal(err)
	}
	p, err := loadSafetyPolicy(data)
	if err != nil {
		t.Fatal(err)
	}
	for _, c := range []struct {
		in   string
		want []string
	}{
		{"service gscd /system/bin/gscd\n    user hsm\n    # tpm here is a comment\n", []string{"gsc", "hsm"}},
		{"\x1c# tpm after a separator\n  \t# TPM\nwrite /dev/TPM0 1\r\nexec FlashRom\x0bvpd crossystem\n", []string{"crossystem", "flashrom", "tpm", "vpd"}},
		{"firmware\xe2\x82updat\n", []string{"firmware\ufffdupdat"}},
		{"firmware\xff\xfeupdat\n", []string{}},
		{"x\u2028tpm\u2029 # \u0085gsc", []string{"gsc", "tpm"}},
		{"on boot\n\u00a0# hsm after nbsp\n", []string{}},
	} {
		if got := rcHits([]byte(c.in), p.rc); !reflect.DeepEqual(got, c.want) {
			t.Errorf("rcHits(%q) = %q, want %q", c.in, got, c.want)
		}
	}
	for _, c := range []struct {
		in   []string
		want string
	}{
		{nil, "[]"}, {[]string{"gsc", "tpm"}, "['gsc', 'tpm']"}, {[]string{"it's"}, `["it's"]`},
		{[]string{`a'b"c`}, `['a\'b"c']`}, {[]string{"firmware\ufffdupdat"}, "['firmware\ufffdupdat']"},
		{[]string{"tab\there"}, `['tab\there']`}, {[]string{"\u0085x"}, `['\x85x']`}, {[]string{"\u200bz"}, `['\u200bz']`},
		{[]string{`\x`}, `['\\x']`},
	} {
		if got := pyList(c.in); got != c.want {
			t.Errorf("pyList(%q) = %s, want %s", c.in, got, c.want)
		}
	}
}

func TestSafetyPolicyRefusals(t *testing.T) {
	data, err := os.ReadFile("../../safety/firmware-safety.json")
	if err != nil {
		t.Fatal(err)
	}
	p, err := loadSafetyPolicy(data)
	if err != nil {
		t.Fatal(err)
	}
	if want := []string{"/system/etc/init/gscutil.rc", "/system/etc/init/gscutil-executor.rc"}; !reflect.DeepEqual(p.neutralOrder, want) {
		t.Fatalf("neutralised order %q", p.neutralOrder)
	}
	s := string(data)
	gscd := p.ReviewedRC["/system/etc/init/gscd.rc"].SHA256
	google := p.Neutralised["/system/etc/init/gscutil.rc"].GoogleSHA256
	for name, bad := range map[string]string{
		"schema":    strings.Replace(s, safetySchema, "openbook-firmware-safety/2", 1),
		"no key":    strings.Replace(s, `"reviewed_binaries"`, `"reviewed_binaries_x"`, 1),
		"regex":     strings.Replace(s, `"rc_pattern": "`, `"rc_pattern": "(?=x)`, 1),
		"verdict":   strings.Replace(s, `"verdict": "inert"`, `"verdict": "fine"`, 1),
		"short sha": strings.Replace(s, gscd, gscd[:63], 1),
		"no google": strings.Replace(s, google, "", 1),
		"overlap":   strings.Replace(s, `"/system/etc/init/gscd.rc"`, `"/system/etc/init/gscutil.rc"`, 1),
		"twice": strings.Replace(s, `"/system/etc/init/gscutil-executor.rc": {`,
			`"/system/etc/init/gscutil.rc": {"sha256": "`+gscd+`", "google_sha256": "`+gscd+`"}, "/system/etc/init/gscutil-executor.rc": {`, 1),
	} {
		if bad == s {
			t.Fatalf("%s: the test did not change the rules", name)
		}
		if _, err := loadSafetyPolicy([]byte(bad)); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
}

func gunzipFile(t *testing.T, path string) []byte {
	t.Helper()
	f, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	z, err := gzip.NewReader(f)
	if err != nil {
		t.Fatal(err)
	}
	b, err := io.ReadAll(z)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

// The test images (testdata/) hold the same synthetic APEX payload as EROFS (flat plain, flat inline with
// and without whole blocks) and as ext4 (extents, a hashed 300-entry directory).
func TestPayloadReaders(t *testing.T) {
	ero, err := os.ReadFile("testdata/apex-payload.erofs")
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]string{
		"etc/blocktail.rc":     "585db8db1cb93b7762246a0e7685439b9192be64ce051d21e33ec9b1362d38c8",
		"etc/plain.rc":         "062050c146dd67e2b152f1834847fec6c579a40e0ceaf94e1e3163d0170a20be",
		"etc/foo.34rc":         "333987ca90bc21ccb2534ec25a281dde1faf556167810f9ac00871d82b514fab",
		"etc/foo.rc":           "048b8ce6b6d8b319f4d38b238655fba2469849e76c691c4073ec9c6be48ec3dd",
		"lib/many/nested.rc":   "e83e4b3af9ef6eae6f79fbea3f0bcc7f16f62636367ef606a6f3a6108768ac45",
		"lib/many/file-300.so": "",
	}
	c := &safetyCheck{}
	e, err := newErofsFiles(c, bytes.NewReader(ero), nil)
	if err != nil {
		t.Fatal(err)
	}
	x4, err := openExt4(bytes.NewReader(gunzipFile(t, "testdata/apex-payload.ext4.gz")))
	if err != nil {
		t.Fatal(err)
	}
	for name, files := range map[string]partFiles{"erofs": e, "ext4": &ext4Files{fs: x4}} {
		var order []string
		if err := files.walk(func(rel string, kind byte) error {
			if kind == 'f' {
				order = append(order, rel)
			}
			return nil
		}); err != nil {
			t.Fatalf("%s: %v", name, err)
		}
		// os.walk's order: a directory's files, then its subdirectories.
		if len(order) != 308 || order[0] != "apex_manifest.pb" || order[1] != "bin/tpm_tool" || order[2] != "etc/blocktail.rc" {
			t.Fatalf("%s: %d files, first %q", name, len(order), order[:3])
		}
		for rel, sum := range want {
			b, err := readFile(files, rel)
			if err != nil {
				t.Fatalf("%s %s: %v", name, rel, err)
			}
			if sum == "" {
				if string(b) != "x300\n" {
					t.Errorf("%s %s: %q", name, rel, b)
				}
			} else if got := sha256Hex(b); got != sum {
				t.Errorf("%s %s: %s", name, rel, got)
			}
		}
	}
	// A compressed file is not read in place.
	comp, err := os.ReadFile("testdata/compressed.erofs")
	if err != nil {
		t.Fatal(err)
	}
	ce, err := newErofsFiles(c, bytes.NewReader(comp), nil)
	if err != nil {
		t.Fatal(err)
	}
	if err := ce.walk(func(string, byte) error { return nil }); err != nil {
		t.Fatal(err)
	}
	in, _ := ce.fs.readInode(ce.nids["etc/init/big.rc"])
	if _, err := ce.fs.fileReader(in); !errors.Is(err, errNotFlat) {
		t.Fatalf("compressed big.rc: %v", err)
	}
	if b, err := readFile(ce, "etc/init/small.rc"); err != nil || string(b) != "service small /system/bin/small\n" {
		t.Fatalf("small.rc: %q %v", b, err)
	}
}

func apexZip(t *testing.T, payload []byte, method uint16) []byte {
	t.Helper()
	var buf bytes.Buffer
	z := zip.NewWriter(&buf)
	for _, f := range []struct {
		name string
		data []byte
	}{{"apex_manifest.pb", []byte("m")}, {"apex_payload.img", payload}} {
		w, err := z.CreateHeader(&zip.FileHeader{Name: f.name, Method: method})
		if err != nil {
			t.Fatal(err)
		}
		w.Write(f.data)
	}
	if err := z.Close(); err != nil {
		t.Fatal(err)
	}
	return buf.Bytes()
}

func writeTree(t *testing.T, root string, files map[string]string) {
	t.Helper()
	for rel, data := range files {
		p := filepath.Join(root, rel)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if strings.HasPrefix(data, "->") {
			if err := os.Symlink(data[2:], p); err != nil {
				t.Fatal(err)
			}
		} else if err := os.WriteFile(p, []byte(data), 0o644); err != nil {
			t.Fatal(err)
		}
	}
}

const (
	testOurs   = "on post-fs\n    mkdir /metadata/gscutil 775 hsm hsm\n"
	testGoogle = "service gscutil /system/bin/gscutil perform-os-startup\n"
	testGscd   = "service gscd /system/bin/gscd\n    user hsm\n"
)

func testRules(extra string) string {
	return fmt.Sprintf(`{"schema": "openbook-firmware-safety/1",
 "rc_pattern": "(?i)(tpm|gsc|hsm|/sys/firmware/efi)", "binary_pattern": "(?i)(tpm|gsc|flash)",
 "forbidden_names": ["fwupd", "flashrom"], "payload": {"postinstall": "forbidden"},
 "neutralised": {
  "/system/etc/init/gscutil.rc": {"replacement": "gscutil.rc", "sha256": "%s", "google_sha256": "%s"}%s},
 "reviewed_rc": {
  "/system/etc/init/gscd.rc": {"sha256": "%s", "verdict": "allowed"},
  "/system/etc/init/old.rc": {"sha256": "%s", "verdict": "inert"},
  "/system_ext/etc/init/gone.rc": {"sha256": "%s", "verdict": "inert"},
  "/vendor/etc/ueventd.rc": {"sha256": "%s", "verdict": "openbook"},
  "/apex/com.test/etc/foo.rc": {"sha256": "048b8ce6b6d8b319f4d38b238655fba2469849e76c691c4073ec9c6be48ec3dd", "verdict": "inert"}},
 "reviewed_binaries": {"/system/bin/gscd": "reviewed"}}`,
		sha256Hex([]byte(testOurs)), sha256Hex([]byte(testGoogle)), extra, sha256Hex([]byte(testGscd)),
		sha256Hex([]byte("old")), sha256Hex([]byte("gone")), sha256Hex([]byte("v")))
}

func TestCheckTree(t *testing.T) {
	ero, err := os.ReadFile("testdata/apex-payload.erofs")
	if err != nil {
		t.Fatal(err)
	}
	ext := gunzipFile(t, "testdata/apex-payload.ext4.gz")
	root := t.TempDir()
	writeTree(t, root, map[string]string{
		"system/etc/init/gscutil.rc":    testOurs,
		"system/etc/init/gscd.rc":       testGscd,
		"system/etc/init/old.rc":        "service old /system/bin/old\n    user hsm\n",
		"system/etc/init/new.rc":        "service tpmd /system/bin/tpmd\n",
		"system/etc/init/quiet.rc":      "# tpm\n",
		"system/etc/init/README":        "exec /system/bin/gsctool\n",
		"system/etc/init/hw/init.rc":    "import /system/etc/init/hw/gsc.rc\n",
		"system/bin/gscd":               "elf",
		"system/bin/tpm_helper":         "elf",
		"system/bin/fwupd":              "elf",
		"system/bin/flashrom":           "->gscd",
		"system/lib64/libflash.so":      "elf",
		"system/xbin/sub/flash_it":      "elf",
		"system/apex/com.test.apex":     string(apexZip(t, ero, zip.Store)),
		"system/apex/com.ext.apex":      string(apexZip(t, ext, zip.Deflate)),
		"system/apex/com.packed.capex":  "zip",
		"system/apex/com.link.apex":     "->com.test.apex",
		"system/etc/init/other/note.rc": "# only comments\n",
	})
	data := testRules(`,
  "/system/etc/init/zzz.rc": {"replacement": "zzz.rc", "sha256": "` + strings.Repeat("a", 64) + `", "google_sha256": "` + strings.Repeat("b", 64) + `"}`)
	p, err := loadSafetyPolicy([]byte(data))
	if err != nil {
		t.Fatal(err)
	}
	c := &safetyCheck{p: p, work: filepath.Join(t.TempDir(), "w")}
	defer c.close()
	res, err := c.check([]safetyPart{{"system", treeFiles{c, root}}, {"system_ext", treeFiles{c, t.TempDir()}}})
	if err != nil {
		t.Fatal(err)
	}
	var got []string
	for _, f := range res.Findings {
		got = append(got, f.Kind+" "+f.Path+": "+f.Detail)
	}
	want := []string{
		"unchecked-apex /system/apex/com.packed.capex: a compressed APEX: the laptop does not read its init scripts",
		"forbidden /system/bin/flashrom: flashrom must not be in an OpenBook image",
		"forbidden /system/bin/fwupd: fwupd must not be in an OpenBook image",
		"unreviewed-binary /system/bin/tpm_helper: a firmware/TPM/EC tool by name; review it and list it in reviewed_binaries",
		"unreviewed-binary /system/xbin/sub/flash_it: a firmware/TPM/EC tool by name; review it and list it in reviewed_binaries",
		"not-neutralised /system/etc/init/zzz.rc: absent: Google removed or moved it; review the rule",
		"unreviewed-rc /apex/com.ext/etc/blocktail.rc: matches ['hsm']",
		"unreviewed-rc /apex/com.ext/etc/foo.34rc: matches ['/sys/firmware/efi']",
		"unreviewed-rc /apex/com.ext/lib/many/nested.rc: matches ['hsm']",
		"unreviewed-rc /apex/com.test/etc/blocktail.rc: matches ['hsm']",
		"unreviewed-rc /apex/com.test/etc/foo.34rc: matches ['/sys/firmware/efi']",
		"unreviewed-rc /apex/com.test/lib/many/nested.rc: matches ['hsm']",
		"unreviewed-rc /system/etc/init/README: matches ['gsc']",
		"unreviewed-rc /system/etc/init/hw/init.rc: matches ['gsc']",
		"unreviewed-rc /system/etc/init/new.rc: matches ['tpm']",
		"changed-rc /system/etc/init/old.rc: reviewed at " + sha256Hex([]byte("old"))[:12] + ", now " +
			sha256Hex([]byte("service old /system/bin/old\n    user hsm\n"))[:12] + "; matches ['hsm']",
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("findings:\n%s\nwant:\n%s", strings.Join(got, "\n"), strings.Join(want, "\n"))
	}
	inv := res.Inventory
	if res.Passed || inv.APEXRCFiles != 8 || !reflect.DeepEqual(inv.Partitions, []string{"system", "system_ext"}) {
		t.Fatalf("passed %v, apex rc %d, partitions %q", res.Passed, inv.APEXRCFiles, inv.Partitions)
	}
	if !reflect.DeepEqual(inv.Neutralised, map[string]string{"/system/etc/init/gscutil.rc": "neutralised", "/system/etc/init/zzz.rc": "missing"}) {
		t.Fatalf("neutralised %v", inv.Neutralised)
	}
	if !reflect.DeepEqual(inv.ReviewedRC, map[string]string{"/system/etc/init/gscd.rc": "allowed", "/apex/com.test/etc/foo.rc": "inert"}) {
		t.Fatalf("reviewed %v", inv.ReviewedRC)
	}
	if !reflect.DeepEqual(inv.AbsentReviewedRC, []string{"/system_ext/etc/init/gone.rc"}) {
		t.Fatalf("absent %q", inv.AbsentReviewedRC)
	}
	if !reflect.DeepEqual(inv.Binaries, []string{"/system/bin/gscd", "/system/bin/tpm_helper", "/system/xbin/sub/flash_it"}) {
		t.Fatalf("binaries %q", inv.Binaries)
	}
	if !reflect.DeepEqual(inv.BeyondHost, []string{"/apex/com.ext/etc/foo.34rc", "/apex/com.test/etc/foo.34rc", "/system/etc/init/README"}) {
		t.Fatalf("beyond host %q", inv.BeyondHost)
	}
	// The same APEX payloads as partition images: read in place.
	c2 := &safetyCheck{p: p}
	img := filepath.Join(t.TempDir(), "product.img")
	os.WriteFile(img, ero, 0o600)
	f, _ := os.Open(img)
	defer f.Close()
	pe, err := newErofsFiles(c2, f, func() (string, error) { return img, nil })
	if err != nil {
		t.Fatal(err)
	}
	res2, err := c2.check([]safetyPart{{"product", pe}})
	if err != nil {
		t.Fatal(err)
	}
	if len(res2.Findings) != 3 || res2.Findings[0].Path != "/product/bin/tpm_tool" ||
		res2.Findings[1].Path != "/product/etc/blocktail.rc" || res2.Findings[2].Path != "/product/lib/many/nested.rc" {
		t.Fatalf("product image findings %v", res2.Findings)
	}
}

// A compressed init script is read through fsck.erofs (OPENBOOK_TEST_FSCK); without it the check cannot
// read it, which holds the release.
func TestCompressedNeedsFsck(t *testing.T) {
	p, err := loadSafetyPolicy([]byte(testRules("")))
	if err != nil {
		t.Fatal(err)
	}
	fsck := os.Getenv("OPENBOOK_TEST_FSCK")
	c := &safetyCheck{p: p, fsck: fsck, work: filepath.Join(t.TempDir(), "w")}
	defer c.close()
	f, err := os.Open("testdata/compressed.erofs")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	e, err := newErofsFiles(c, f, func() (string, error) { return "testdata/compressed.erofs", nil })
	if err != nil {
		t.Fatal(err)
	}
	res, err := c.check([]safetyPart{{"product", e}})
	if fsck == "" {
		var fe errFormatT
		if !errors.As(err, &fe) {
			t.Fatalf("without fsck.erofs: %v", err)
		}
		t.Skip("set OPENBOOK_TEST_FSCK to fsck.erofs to read the compressed script")
	}
	if err != nil {
		t.Fatal(err)
	}
	seen := res.Inventory.RCMatches["/product/etc/init/big.rc"]
	if seen.SHA256 != "9a3f5cdd1ff322cf390e14cb7bb5f2950279542f24d77b58dd7f97c1599d1177" || !reflect.DeepEqual(seen.Matches, []string{"tpm"}) {
		t.Fatalf("big.rc %+v", seen)
	}
}

func TestAdaptedReleaseSafety(t *testing.T) {
	ero, err := os.ReadFile("testdata/apex-payload.erofs")
	if err != nil {
		t.Fatal(err)
	}
	newDir, tree := t.TempDir(), t.TempDir()
	for _, n := range []string{"system_ext", "product"} {
		os.WriteFile(filepath.Join(newDir, n+".img"), ero, 0o600)
	}
	writeTree(t, tree, map[string]string{"system/etc/init/gscutil.rc": testGoogle, "system/etc/init/gscd.rc": testGscd})
	work := filepath.Join(t.TempDir(), "w")
	var h errHeld
	if _, err := checkFirmwareSafety("", tree, newDir, "", work); !errors.As(err, &h) || !strings.Contains(h.reason, "carries no firmware-safety rules") {
		t.Fatalf("without rules: %v", err)
	}
	writeTree(t, tree, map[string]string{safetyRulesPath: testRules("")})
	res, err := checkFirmwareSafety("", tree, newDir, "", work)
	if !errors.As(err, &h) || res == nil || res.Passed {
		t.Fatalf("Google's gscutil.rc: %v", err)
	}
	if !strings.HasPrefix(h.reason, "firmware safety: unreviewed-binary /system_ext/bin/tpm_tool (") || !strings.HasSuffix(h.reason, " and 6 more") {
		t.Fatalf("reason %q", h.reason)
	}
	if f := res.Findings[2]; f.Kind != "not-neutralised" || f.Path != "/system/etc/init/gscutil.rc" || res.Inventory.Neutralised[f.Path] != "google" {
		t.Fatalf("finding %+v", f)
	}
	if _, err := os.Stat(work); !os.IsNotExist(err) {
		t.Fatalf("scratch left: %v", err)
	}
}

func TestPayloadHasNoPostinstall(t *testing.T) {
	dir := t.TempDir()
	img := filepath.Join(dir, "system.img")
	os.WriteFile(img, bytes.Repeat([]byte{1}, 8192), 0o600)
	res, err := writePayload(filepath.Join(dir, "payload.bin"), []PayloadPart{{Name: "system", Image: img, Size: 8192,
		SHA256: sha256Hex(bytes.Repeat([]byte{1}, 8192))}}, 1, "")
	if err != nil {
		t.Fatal(err)
	}
	b, _ := os.ReadFile(filepath.Join(dir, "payload.bin"))
	manifest := b[24 : 24+binary.BigEndian.Uint64(b[12:])]
	if err := checkNoPostinstall(manifest); err != nil || res.Postinstall != "none" {
		t.Fatalf("our payload: %v %q", err, res.Postinstall)
	}
	part := func(fields func(*pb)) []byte {
		m, pu := &pb{}, &pb{}
		pu.s(1, "vendor")
		fields(pu)
		m.msg(13, pu)
		return m.Bytes()
	}
	for name, m := range map[string][]byte{
		"run_postinstall":  part(func(p *pb) { p.u(2, 1) }),
		"postinstall_path": part(func(p *pb) { p.s(3, "bin/updater-wrapper-vendor") }),
		"no partitions":    {},
		"truncated":        manifest[:len(manifest)-1],
	} {
		if err := checkNoPostinstall(m); err == nil {
			t.Errorf("%s: accepted", name)
		}
	}
	if err := checkNoPostinstall(part(func(p *pb) { p.u(2, 0) })); err != nil {
		t.Errorf("run_postinstall false: %v", err)
	}
}
