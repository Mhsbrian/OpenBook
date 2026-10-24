// SPDX-License-Identifier: Apache-2.0

// The OpenBook layer: OpenBook's exact delta against the Google build a release was made from, which the
// laptop re-applies to Google's next build. It lists every path OpenBook adds, removes or changes with its
// inode rows (erofs-inventory) and content, the data the carry rules need (the old and OpenBook build.prop,
// appended tails, the inserted block), and what the release's vbmeta takes from partitions the adaptation
// leaves alone. The bytes of OpenBook's own files are not in it: the laptop reads them from the running
// system and checks each against the layer before use. A release ships its layer in its system image, and
// the adaptation writes the layer for the next round (against the new Google build) into the new system.
package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const (
	layerSchema = "openbook-layer/1"
	// Where a release keeps its layer; these paths are regenerated, never carried.
	layerDir = "/system/etc/openbook/layer"
	// The carry rules (rebase-google-build.py).
	buildProp  = "/system/build.prop"
	policyHash = "/system/etc/selinux/plat_sepolicy_and_mapping.sha256"
	platCil    = "/system/etc/selinux/plat_sepolicy.cil"
	seappPath  = "/system/etc/selinux/plat_seapp_contexts"
	macPerms   = "/system/etc/selinux/plat_mac_permissions.xml"
)

var (
	mergeable = map[string]bool{buildProp: true}
	appended  = map[string]bool{platCil: true, "/system/etc/selinux/plat_file_contexts": true, seappPath: true}
	inserted  = map[string][]byte{macPerms: []byte("</policy>")}
	// Partitions an adaptation rebuilds or takes from Google; the rest of a release is left as installed.
	adaptedPartitions = []string{"system", "system_ext", "product"}
	// The release vbmeta's sources, in the order the host's release build includes them.
	vbmetaOrder = []string{"system", "system_ext", "product", "vendor", "vendor_dlkm", "system_dlkm", "boot", "init_boot", "vendor_boot"}
)

// Entry is a path's content: ["file", sha256], ["symlink", target] or ["dir"].
type Entry []string

type LayerPath struct {
	Old       []string `json:"old,omitempty"`  // OLD's inventory rows
	Ours      []string `json:"ours,omitempty"` // the release's rows
	OldEntry  Entry    `json:"old_entry,omitempty"`
	OursEntry Entry    `json:"ours_entry,omitempty"`
	Carry     string   `json:"carry"` // added, removed, changed, merge3, append, insert, policy_hash
}

type Layer struct {
	Schema string `json:"schema"`
	Google struct {
		Build        string `json:"build"`
		Fingerprint  string `json:"fingerprint"`
		SystemSHA256 string `json:"system_sha256"`
		AVBKeySHA256 string `json:"avb_key_sha256"`
		// OLD's policy inputs outside the system image (system_ext, product): unchanged means the merged
		// policy needs no new compile.
		PolicySHA256 map[string]string `json:"policy_sha256"`
	} `json:"google"`
	Release struct {
		// The release's partitions an adaptation leaves alone (its system and vbmeta cannot be named from
		// inside the system that carries this layer).
		Partitions map[string]string `json:"partitions_sha256"`
		Sizes      map[string]uint64 `json:"partitions_bytes"`
		// vbmeta blobs of the partitions the adaptation leaves alone, from their footers (hex).
		VBMeta map[string]string `json:"vbmeta"`
	} `json:"release"`
	Paths        map[string]*LayerPath `json:"paths"`
	MappingCil   string                `json:"policy_mapping"` // mapping/<version>.cil the policy hash covers
	OpenBookCert string                `json:"openbook_app_cert_der"`
	// Small carry data, by name: build.prop.old, build.prop.ours, <path>.tail, <path>.block.
	Data map[string]string `json:"data"`
	// The partner policy inputs from the release's vendor partition (unchanged by an adaptation).
	VendorPolicy map[string]string `json:"vendor_policy"`
}

func entryOf(root, p string) (Entry, error) {
	local := filepath.Join(root, p)
	st, err := os.Lstat(local)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}
	switch {
	case st.Mode()&os.ModeSymlink != 0:
		t, err := os.Readlink(local)
		return Entry{"symlink", t}, err
	case st.Mode().IsRegular():
		sum, err := fileSHA256(local)
		return Entry{"file", sum}, err
	case st.IsDir():
		return Entry{"dir"}, nil
	}
	return nil, fmt.Errorf("%s: unsupported file type", p)
}

func sameEntry(a, b Entry) bool {
	return strings.Join(a, "\x00") == strings.Join(b, "\x00") && (a == nil) == (b == nil)
}

func sameRows(a, b []string) bool { return strings.Join(a, "\n") == strings.Join(b, "\n") }

// byPath groups inventory rows by path.
func byPath(rows []string) (map[string][]string, error) {
	out := map[string][]string{}
	for _, r := range rows {
		f := strings.SplitN(r, " ", 3)
		if len(f) < 3 {
			return nil, fmt.Errorf("malformed inventory row %q", r)
		}
		p, err := hex.DecodeString(f[1])
		if err != nil {
			return nil, err
		}
		out[string(p)] = append(out[string(p)], r)
	}
	for k := range out {
		sort.Strings(out[k])
	}
	return out, nil
}

// withSize sets the size field of a path's inode row (rows are kept sorted).
func withSize(rows []string, size int) []string {
	out := make([]string, len(rows))
	for i, r := range rows {
		f := strings.Split(r, " ")
		if f[0] == "I" {
			f[6] = fmt.Sprint(size)
		}
		out[i] = strings.Join(f, " ")
	}
	sort.Strings(out)
	return out
}

func inLayerDir(p string) bool { return p == layerDir || strings.HasPrefix(p, layerDir+"/") }

// buildLayer computes OpenBook's delta of OURS (a release system, extracted at oursTree) against OLD (the
// Google system it was made from, extracted at oldTree), refusing anything the carry rules cannot carry.
func buildLayer(oldRows, oursRows map[string][]string, oldTree, oursTree string) (*Layer, error) {
	l := &Layer{Schema: layerSchema, Paths: map[string]*LayerPath{}, Data: map[string]string{}}
	paths := map[string]bool{}
	for p := range oldRows {
		paths[p] = true
	}
	for p := range oursRows {
		paths[p] = true
	}
	for p := range paths {
		if inLayerDir(p) {
			continue
		}
		o, u := oldRows[p], oursRows[p]
		oe, err := entryOf(oldTree, p)
		if err != nil {
			return nil, err
		}
		ue, err := entryOf(oursTree, p)
		if err != nil {
			return nil, err
		}
		lp := &LayerPath{Old: o, Ours: u, OldEntry: oe, OursEntry: ue}
		switch {
		case o == nil:
			lp.Carry = "added"
		case u == nil:
			lp.Carry = "removed"
		case sameRows(o, u) && sameEntry(oe, ue):
			continue
		default:
			lp.Carry = "changed"
		}
		if lp.Carry == "changed" {
			if err := classifyChange(l, lp, p, oldTree, oursTree); err != nil {
				return nil, err
			}
		}
		l.Paths[p] = lp
	}
	return l, nil
}

func classifyChange(l *Layer, lp *LayerPath, p, oldTree, oursTree string) error {
	special := p == policyHash || mergeable[p] || appended[p] || inserted[p] != nil
	if !special {
		return nil
	}
	if !sameRows(withSize(lp.Old, 0), withSize(lp.Ours, 0)) {
		return fmt.Errorf("%s: carrying it needs unchanged ownership, mode and labels", p)
	}
	o, err := os.ReadFile(filepath.Join(oldTree, p))
	if err != nil {
		return err
	}
	u, err := os.ReadFile(filepath.Join(oursTree, p))
	if err != nil {
		return err
	}
	switch {
	case p == policyHash:
		lp.Carry = "policy_hash"
		se := filepath.Join(oursTree, "system/etc/selinux")
		plat, err := os.ReadFile(filepath.Join(se, "plat_sepolicy.cil"))
		if err != nil {
			return err
		}
		maps, _ := filepath.Glob(filepath.Join(se, "mapping", "*.cil"))
		sort.Strings(maps)
		var found []string
		for _, m := range maps {
			mb, err := os.ReadFile(m)
			if err != nil {
				return err
			}
			if fmt.Sprintf("%x\n", sha256.Sum256(append(append([]byte(nil), plat...), mb...))) == string(u) {
				found = append(found, filepath.Base(m))
			}
		}
		if len(found) != 1 {
			return errors.New("cannot tell which mapping version the platform policy hash covers")
		}
		l.MappingCil = found[0]
	case mergeable[p]:
		lp.Carry = "merge3"
		if _, err := textLines(o); err != nil {
			return fmt.Errorf("%s: %v", p, err)
		}
		if _, err := textLines(u); err != nil {
			return fmt.Errorf("%s: %v", p, err)
		}
		l.Data[p+".old"], l.Data[p+".ours"] = string(o), string(u)
	case appended[p]:
		lp.Carry = "append"
		if !bytes.HasPrefix(u, o) {
			return fmt.Errorf("%s: OpenBook's change is not a pure append; cannot carry it", p)
		}
		l.Data[p+".tail"] = string(u[len(o):])
	default:
		lp.Carry = "insert"
		block, err := insertedBlock(o, u, inserted[p])
		if err != nil {
			return fmt.Errorf("%s: %v", p, err)
		}
		l.Data[p+".block"] = string(block)
	}
	return nil
}

func readLayer(dir string) (*Layer, error) {
	b, err := os.ReadFile(filepath.Join(dir, "layer.json"))
	if err != nil {
		return nil, err
	}
	l := &Layer{}
	if err := json.Unmarshal(b, l); err != nil {
		return nil, err
	}
	if l.Schema != layerSchema {
		return nil, fmt.Errorf("layer schema %q is not %s", l.Schema, layerSchema)
	}
	return l, nil
}

// encodeLayer is the layer file's exact bytes (Go's JSON encoding sorts map keys).
func encodeLayer(l *Layer) ([]byte, error) {
	b, err := json.MarshalIndent(l, "", " ")
	if err != nil {
		return nil, err
	}
	return append(b, '\n'), nil
}

// cmdLayer writes a release's layer, on the build host: OpenBook's delta of the release's system against the
// Google system it was made from.
func cmdLayer(fl *flag.FlagSet, args []string) error {
	oldSystem := fl.String("old-system", "", "Google's system image the release was made from")
	oldStock := fl.String("old-stock", "", "directory with Google's system_ext.img, product.img and vbmeta.img of that build")
	oldBuild := fl.String("old-build", "", "that Google build number")
	release := fl.String("release-dir", "", "the release's ten partition images")
	certPEM := fl.String("app-cert", "", "OpenBook Update's certificate (PEM), the signer the carried mac_permissions must hold")
	fsck := fl.String("fsck", "fsck.erofs", "")
	work := fl.String("work", "", "new scratch directory")
	out := fl.String("out", "", "new directory for the layer")
	fl.Parse(args)
	if *oldSystem == "" || *oldStock == "" || *oldBuild == "" || *release == "" || *work == "" || *out == "" {
		usage()
	}
	if err := os.Mkdir(*work, 0o700); err != nil {
		return err
	}
	ours := filepath.Join(*release, "system.img")
	trees := map[string]string{}
	rows := map[string]map[string][]string{}
	for label, img := range map[string]string{"old": *oldSystem, "ours": ours} {
		trees[label] = filepath.Join(*work, "tree-"+label)
		if err := run(*fsck, "--extract="+trees[label], img); err != nil {
			return err
		}
		r, err := inventory(img)
		if err != nil {
			return err
		}
		if rows[label], err = byPath(r); err != nil {
			return err
		}
	}
	l, err := buildLayer(rows["old"], rows["ours"], trees["old"], trees["ours"])
	if err != nil {
		return err
	}
	l.Google.Build = *oldBuild
	if l.Google.SystemSHA256, err = fileSHA256(*oldSystem); err != nil {
		return err
	}
	gv, _, err := readImageVBMeta(filepath.Join(*oldStock, "vbmeta.img"))
	if err != nil {
		return err
	}
	if err := gv.Verify(); err != nil {
		return fmt.Errorf("Google's vbmeta: %v", err)
	}
	ks := sha256.Sum256(gv.PublicKey)
	l.Google.AVBKeySHA256 = hex.EncodeToString(ks[:])
	l.Google.Fingerprint = vbmetaProperty(gv, "com.android.build.system.fingerprint")
	if l.Google.PolicySHA256, err = policyInputHashes(l, *fsck, *work, *oldStock, trees["old"]); err != nil {
		return err
	}
	l.Release.Partitions, l.Release.Sizes, l.Release.VBMeta = map[string]string{}, map[string]uint64{}, map[string]string{}
	for _, n := range vbmetaOrder {
		if n == "system" {
			continue // cannot be named from inside itself
		}
		img := filepath.Join(*release, n+".img")
		if l.Release.Partitions[n], err = fileSHA256(img); err != nil {
			return err
		}
		st, err := os.Stat(img)
		if err != nil {
			return err
		}
		l.Release.Sizes[n] = uint64(st.Size())
		if contains(adaptedPartitions, n) {
			continue
		}
		v, _, err := readImageVBMeta(img)
		if err != nil {
			return err
		}
		l.Release.VBMeta[n] = hex.EncodeToString(v.Blob)
	}
	vendorTree := filepath.Join(*work, "vendor")
	if err := run(*fsck, "--extract="+vendorTree, filepath.Join(*release, "vendor.img")); err != nil {
		return err
	}
	l.VendorPolicy = map[string]string{}
	for _, n := range []string{"plat_sepolicy_vers.txt", "genfs_labels_version.txt", "plat_pub_versioned.cil", "vendor_sepolicy.cil"} {
		b, err := os.ReadFile(filepath.Join(vendorTree, "etc/selinux", n))
		if err != nil {
			return err
		}
		l.VendorPolicy[n] = string(b)
	}
	if *certPEM != "" {
		der, err := pemDER(*certPEM)
		if err != nil {
			return err
		}
		l.OpenBookCert = hex.EncodeToString(der)
	}
	if err := os.Mkdir(*out, 0o755); err != nil {
		return err
	}
	b, err := encodeLayer(l)
	if err != nil {
		return err
	}
	fmt.Printf("layer: %d paths (google %s)\n", len(l.Paths), l.Google.Build)
	return os.WriteFile(filepath.Join(*out, "layer.json"), b, 0o644)
}

func contains(list []string, s string) bool {
	for _, x := range list {
		if x == s {
			return true
		}
	}
	return false
}

func vbmetaProperty(v *VBMeta, key string) string {
	for _, d := range v.Descriptors {
		if d.Tag == tagProperty && bytes.HasPrefix(d.Raw[32:], []byte(key+"\x00")) {
			kl, vl := be.Uint64(d.Raw[16:]), be.Uint64(d.Raw[24:])
			return string(d.Raw[32+kl+1 : 32+kl+1+vl])
		}
	}
	return ""
}

// policyInputHashes hashes a Google build's SELinux policy files: every file under the system image's
// /system/etc/selinux that OpenBook does not change, and everything under etc/selinux of its system_ext and
// product images (extracted to work/policy-<name> for a compile).
func policyInputHashes(l *Layer, fsck, work, stock, systemTree string) (map[string]string, error) {
	out := map[string]string{}
	walk := func(dir, label string, skip func(string) bool) error {
		return filepath.Walk(dir, func(p string, info os.FileInfo, err error) error {
			if err != nil || !info.Mode().IsRegular() {
				return err
			}
			rel, _ := filepath.Rel(dir, p)
			if skip != nil && skip(rel) {
				return nil
			}
			sum, err := fileSHA256(p)
			out[label+"/"+rel] = sum
			return err
		})
	}
	se := filepath.Join(systemTree, "system/etc/selinux")
	if err := walk(se, "system", func(rel string) bool { return l.Paths["/system/etc/selinux/"+rel] != nil }); err != nil {
		return nil, err
	}
	for _, n := range []string{"system_ext", "product"} {
		dir, err := extractSubtree(fsck, filepath.Join(stock, n+".img"), "etc/selinux", filepath.Join(work, "policy-"+n))
		if err != nil {
			return nil, err
		}
		if err := walk(dir, n, nil); err != nil {
			return nil, err
		}
	}
	return out, nil
}

// extractSubtree extracts one directory of an image to dir and returns where it landed. fsck.erofs --path
// extracts just that directory (Android's build); a build without --path extracts everything.
func extractSubtree(fsck, image, sub, dir string) (string, error) {
	if err := run(fsck, "--extract="+dir, "--path=/"+sub, image); err == nil {
		if st, err := os.Stat(filepath.Join(dir, sub)); err == nil && st.IsDir() {
			return filepath.Join(dir, sub), nil
		}
		return dir, nil
	}
	os.RemoveAll(dir)
	if err := run(fsck, "--extract="+dir, image); err != nil {
		return "", err
	}
	return filepath.Join(dir, sub), nil
}
