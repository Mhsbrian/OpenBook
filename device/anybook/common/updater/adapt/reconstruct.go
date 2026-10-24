// SPDX-License-Identifier: Apache-2.0

// Reconstruct: Google's release partitions from its recovery image, on the laptop. The recovery zip holds one
// disk image (GPT; a super partition with logical partitions described by liblp metadata). It is read once,
// front to back, straight from the zip (the 19 GB image is never written out); only the requested partitions
// are kept. Each one is then proven against Google's own signed vbmeta: the signature verifies with Google's
// key (pinned by the layer), and every partition's dm-verity root digest is recomputed.
package main

import (
	"archive/zip"
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode/utf16"
)

type gptPart struct {
	Name           string
	Offset, Length uint64
}

func parseGPT(head []byte) ([]gptPart, error) {
	if len(head) < 1024 || string(head[512:520]) != "EFI PART" {
		return nil, errors.New("no GPT")
	}
	lba, n, size := le.Uint64(head[512+72:]), uint64(le.Uint32(head[512+80:])), uint64(le.Uint32(head[512+84:]))
	if size < 128 || n > 1024 || lba*512+n*size > uint64(len(head)) {
		return nil, errors.New("GPT entries out of range")
	}
	var out []gptPart
	for i := uint64(0); i < n; i++ {
		e := head[lba*512+i*size:][:size]
		if bytes.Equal(e[:16], make([]byte, 16)) {
			continue
		}
		first, last := le.Uint64(e[32:]), le.Uint64(e[40:])
		u := make([]uint16, 36)
		for j := range u {
			u[j] = le.Uint16(e[56+2*j:])
		}
		name := strings.TrimRight(string(utf16.Decode(u)), "\x00")
		out = append(out, gptPart{name, first * 512, (last - first + 1) * 512})
	}
	return out, nil
}

type lpExtent struct{ sectors, physSector uint64 }

// parseLP reads slot 0 of a super's liblp metadata (the region from the super's start) and returns each
// logical partition's linear extents, in sectors relative to the super.
func parseLP(region []byte) (map[string][]lpExtent, error) {
	const reserved, geoSize = 4096, 4096
	if len(region) < reserved+geoSize {
		return nil, errors.New("short super metadata")
	}
	g := region[reserved:]
	if le.Uint32(g) != 0x616c4467 || le.Uint32(g[4:]) != 52 {
		return nil, errors.New("no liblp geometry")
	}
	geo := append([]byte(nil), g[:52]...)
	clear(geo[8:40])
	if sum := sha256.Sum256(geo); !bytes.Equal(sum[:], g[8:40]) {
		return nil, errors.New("liblp geometry checksum mismatch")
	}
	maxSize := uint64(le.Uint32(g[40:]))
	start := uint64(reserved + 2*geoSize)
	if uint64(len(region)) < start+maxSize {
		return nil, errors.New("short super metadata slot")
	}
	h := region[start : start+maxSize]
	if le.Uint32(h) != 0x414C5030 || le.Uint16(h[4:]) != 10 || le.Uint16(h[6:]) > 2 {
		return nil, errors.New("unsupported liblp metadata header")
	}
	hsize, tsize := uint64(le.Uint32(h[8:])), uint64(le.Uint32(h[44:]))
	if hsize < 128 || hsize+tsize > maxSize {
		return nil, errors.New("liblp metadata sizes out of range")
	}
	hdr := append([]byte(nil), h[:hsize]...)
	clear(hdr[12:44])
	if sum := sha256.Sum256(hdr); !bytes.Equal(sum[:], h[12:44]) {
		return nil, errors.New("liblp header checksum mismatch")
	}
	tables := h[hsize : hsize+tsize]
	if sum := sha256.Sum256(tables); !bytes.Equal(sum[:], h[48:80]) {
		return nil, errors.New("liblp tables checksum mismatch")
	}
	table := func(at int) (uint64, uint64, uint64) {
		return uint64(le.Uint32(h[at:])), uint64(le.Uint32(h[at+4:])), uint64(le.Uint32(h[at+8:]))
	}
	po, pn, ps := table(80)
	eo, en, es := table(92)
	if ps != 52 || es != 24 || po+pn*ps > tsize || eo+en*es > tsize {
		return nil, errors.New("liblp tables malformed")
	}
	out := map[string][]lpExtent{}
	for i := uint64(0); i < pn; i++ {
		p := tables[po+i*ps:]
		name := strings.TrimRight(string(p[:36]), "\x00")
		first, num := uint64(le.Uint32(p[40:])), uint64(le.Uint32(p[44:]))
		if first+num > en {
			return nil, fmt.Errorf("%s: extents out of range", name)
		}
		var exts []lpExtent
		for j := first; j < first+num; j++ {
			e := tables[eo+j*es:]
			if le.Uint32(e[8:]) != 0 || le.Uint32(e[20:]) != 0 {
				return nil, fmt.Errorf("%s: only linear extents on the super device are supported", name)
			}
			exts = append(exts, lpExtent{le.Uint64(e), le.Uint64(e[12:])})
		}
		out[name] = exts
	}
	return out, nil
}

// stream reads an image front to back.
type stream struct {
	r   *bufio.Reader
	pos uint64
}

func (s *stream) skipTo(off uint64) error {
	if off < s.pos {
		return fmt.Errorf("image layout needs a backward read (%d < %d)", off, s.pos)
	}
	n, err := io.CopyN(io.Discard, s.r, int64(off-s.pos))
	s.pos += uint64(n)
	return err
}

func (s *stream) read(n uint64) ([]byte, error) {
	b := make([]byte, n)
	m, err := io.ReadFull(s.r, b)
	s.pos += uint64(m)
	return b, err
}

func (s *stream) copyTo(w io.Writer, n uint64) error {
	m, err := io.CopyN(w, s.r, int64(n))
	s.pos += uint64(m)
	return err
}

// openRelease returns the disk image stream inside a recovery zip (its one .bin entry), or a raw image file.
func openRelease(path string) (io.ReadCloser, string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, "", err
	}
	magic := make([]byte, 4)
	if _, err := io.ReadFull(f, magic); err != nil {
		f.Close()
		return nil, "", err
	}
	if string(magic) != "PK\x03\x04" {
		if _, err := f.Seek(0, io.SeekStart); err != nil {
			f.Close()
			return nil, "", err
		}
		return f, filepath.Base(path), nil
	}
	f.Close()
	z, err := zip.OpenReader(path)
	if err != nil {
		return nil, "", err
	}
	var bins []*zip.File
	for _, e := range z.File {
		if strings.HasSuffix(e.Name, ".bin") {
			bins = append(bins, e)
		}
	}
	if len(bins) != 1 {
		z.Close()
		return nil, "", fmt.Errorf("%s: expected one .bin image, found %d", path, len(bins))
	}
	rc, err := bins[0].Open()
	if err != nil {
		z.Close()
		return nil, "", err
	}
	return struct {
		io.Reader
		io.Closer
	}{rc, closers{rc, z}}, bins[0].Name, nil
}

type closers []io.Closer

func (c closers) Close() error {
	var first error
	for _, x := range c {
		if err := x.Close(); err != nil && first == nil {
			first = err
		}
	}
	return first
}

type ReconstructResult struct {
	Schema       string            `json:"schema"`
	Source       string            `json:"source"`
	Image        string            `json:"image"`
	GoogleKey    string            `json:"google_avb_key_sha256"`
	Fingerprint  string            `json:"fingerprint"`
	Partitions   map[string]string `json:"partitions_sha256"`
	VerifiedRoot map[string]bool   `json:"dm_verity_root_verified"`
}

type chunk struct {
	file       string
	fileOffset uint64
	abs, n     uint64
}

// reconstruct extracts the slot-A logical partitions `logical` and the GPT partitions `static` (names
// without the _a suffix) from a release image into dir, then proves them against Google's vbmeta_a.
func reconstruct(release, dir string, logical, static []string, googleKey string) (*ReconstructResult, error) {
	rc, name, err := openRelease(release)
	if err != nil {
		return nil, err
	}
	defer rc.Close()
	s := &stream{r: bufio.NewReaderSize(rc, 8<<20)}
	head, err := s.read(1 << 20)
	if err != nil {
		return nil, err
	}
	parts, err := parseGPT(head)
	if err != nil {
		return nil, err
	}
	gpt := map[string]gptPart{}
	for _, p := range parts {
		gpt[p.Name] = p
	}
	super, ok := gpt["super"]
	if !ok {
		return nil, errors.New("the release image has no super partition")
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return nil, err
	}
	files := map[string]*os.File{}
	open := func(n string) (*os.File, error) {
		if f := files[n]; f != nil {
			return f, nil
		}
		f, err := os.OpenFile(filepath.Join(dir, n+".img"), os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
		files[n] = f
		return f, err
	}
	defer func() {
		for _, f := range files {
			if f != nil {
				f.Close()
			}
		}
	}()
	static = append(static, "vbmeta")
	var chunks []chunk
	for _, n := range static {
		p, ok := gpt[n+"_a"]
		if !ok {
			return nil, fmt.Errorf("the release image has no %s_a", n)
		}
		chunks = append(chunks, chunk{n, 0, p.Offset, p.Length})
	}
	// Static partitions before the super, then the super's metadata, then everything after it in order.
	sort.Slice(chunks, func(i, j int) bool { return chunks[i].abs < chunks[j].abs })
	emit := func(c chunk) error {
		f, err := open(c.file)
		if err != nil {
			return err
		}
		if err := s.skipTo(c.abs); err != nil {
			return err
		}
		if _, err := f.Seek(int64(c.fileOffset), io.SeekStart); err != nil {
			return err
		}
		return s.copyTo(f, c.n)
	}
	var rest []chunk
	for _, c := range chunks {
		if c.abs < super.Offset {
			if err := emit(c); err != nil {
				return nil, err
			}
		} else {
			rest = append(rest, c)
		}
	}
	if err := s.skipTo(super.Offset); err != nil {
		return nil, err
	}
	meta, err := s.read(4096 + 2*4096 + 65536)
	if err != nil {
		return nil, err
	}
	if g := meta[4096:]; le.Uint32(g[40:]) > 65536 {
		return nil, errors.New("liblp metadata slots larger than 64 KiB are not supported")
	}
	lp, err := parseLP(meta)
	if err != nil {
		return nil, err
	}
	for _, n := range logical {
		exts, ok := lp[n+"_a"]
		if !ok || len(exts) == 0 {
			return nil, fmt.Errorf("the release's super has no %s_a", n)
		}
		at := uint64(0)
		for _, e := range exts {
			rest = append(rest, chunk{n, at, super.Offset + e.physSector*512, e.sectors * 512})
			at += e.sectors * 512
		}
	}
	sort.Slice(rest, func(i, j int) bool { return rest[i].abs < rest[j].abs })
	for i := 1; i < len(rest); i++ {
		if rest[i-1].abs+rest[i-1].n > rest[i].abs {
			return nil, errors.New("overlapping partitions in the release image")
		}
	}
	for _, c := range rest {
		if err := emit(c); err != nil {
			return nil, err
		}
	}
	// Read to the end so the zip's CRC-32 of the whole image is checked.
	if _, err := io.Copy(io.Discard, s.r); err != nil {
		return nil, fmt.Errorf("release image: %v", err)
	}
	for n, f := range files {
		if err := f.Sync(); err != nil {
			return nil, err
		}
		if err := f.Close(); err != nil {
			return nil, err
		}
		files[n] = nil
	}
	res := &ReconstructResult{Schema: "openbook-adapt-reconstruct/1", Source: filepath.Base(release), Image: name,
		Partitions: map[string]string{}, VerifiedRoot: map[string]bool{}}
	vb, _, err := readImageVBMeta(filepath.Join(dir, "vbmeta.img"))
	if err != nil {
		return nil, err
	}
	if err := vb.Verify(); err != nil {
		return nil, fmt.Errorf("Google's vbmeta: %v", err)
	}
	ks := sha256.Sum256(vb.PublicKey)
	res.GoogleKey = hex.EncodeToString(ks[:])
	if googleKey != "" && res.GoogleKey != googleKey {
		return nil, fmt.Errorf("Google's vbmeta is signed by an unexpected key %s", res.GoogleKey)
	}
	for _, d := range vb.Descriptors {
		if d.Tag == tagProperty && bytes.HasPrefix(d.Raw[32:], []byte("com.android.build.system.fingerprint\x00")) {
			kl := be.Uint64(d.Raw[16:])
			vl := be.Uint64(d.Raw[24:])
			res.Fingerprint = string(d.Raw[32+kl+1 : 32+kl+1+vl])
		}
	}
	for _, n := range logical {
		var ht *HashtreeDesc
		for _, d := range vb.Descriptors {
			if d.Hashtree != nil && d.Partition == n {
				ht = d.Hashtree
			}
		}
		if ht == nil {
			return nil, fmt.Errorf("Google's vbmeta has no hash tree for %s", n)
		}
		img := filepath.Join(dir, n+".img")
		if err := verifyHashtree(img, ht); err != nil {
			return nil, err
		}
		res.VerifiedRoot[n] = true
	}
	for _, n := range append(append([]string{}, logical...), static...) {
		sum, err := fileSHA256(filepath.Join(dir, n+".img"))
		if err != nil {
			return nil, err
		}
		res.Partitions[n] = sum
	}
	return res, nil
}

func fileSHA256(path string) (string, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}
