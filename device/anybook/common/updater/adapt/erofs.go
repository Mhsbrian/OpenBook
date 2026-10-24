// SPDX-License-Identifier: Apache-2.0

// A read-only EROFS reader: the inode/xattr inventory of an image, in exactly the rows
// scripts/googlebook/erofs-inventory.c (liberofs) prints, so the laptop checks a rebuilt system the way the
// host does, and uncompressed file data for the firmware-safety check (compressed data stays to
// fsck.erofs). Anything this reader does not know (an unknown incompatible feature, a compressed or chunked
// directory, a long xattr name prefix) is refused rather than guessed.
package main

import (
	"encoding/binary"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"sort"
	"strings"
)

var le = binary.LittleEndian

const (
	erofsMagic       = 0xE0F5E1E2
	erofsSuperOffset = 1024
	layoutFlatPlain  = 0
	layoutFlatInline = 2
	erofsDirentSize  = 12
	sIFMT, sIFDIR    = 0o170000, 0o040000
	// zero padding, compression configs/big pclusters, chunked files, device table/compression head 2,
	// ztailpacking, fragments/dedupe, and the xattr prefix table (refused below unless it is empty)
	knownIncompat = 0x1 | 0x2 | 0x4 | 0x8 | 0x10 | 0x20 | 0x40
)

var xattrPrefixes = map[byte]string{1: "user.", 2: "system.posix_acl_access", 3: "system.posix_acl_default",
	4: "trusted.", 5: "lustre.", 6: "security."}

type erofsFS struct {
	r                 io.ReaderAt
	blkszbits         uint
	metaBlk, xattrBlk uint64
	buildTime         uint64
	buildTimeNsec     uint32
	rootNid           uint64
	dirblkbits        uint
}

type erofsInode struct {
	nid             uint64
	format, mode    uint16
	xattrIcount     uint16
	size            uint64
	rawBlk          uint32
	uid, gid, nlink uint32
	mtime           uint64
	mtimeNsec       uint32
	inodeSize       uint64
}

func openErofs(r io.ReaderAt) (*erofsFS, error) {
	sb := make([]byte, 128)
	if _, err := r.ReadAt(sb, erofsSuperOffset); err != nil {
		return nil, err
	}
	if le.Uint32(sb) != erofsMagic {
		return nil, errors.New("not an EROFS image")
	}
	incompat := le.Uint32(sb[80:])
	if incompat&^uint32(knownIncompat) != 0 {
		return nil, fmt.Errorf("EROFS incompatible features %#x are not supported", incompat)
	}
	fs := &erofsFS{r: r, blkszbits: uint(sb[12]), rootNid: uint64(le.Uint16(sb[14:])), buildTime: le.Uint64(sb[24:]),
		buildTimeNsec: le.Uint32(sb[32:]), metaBlk: uint64(le.Uint32(sb[40:])), xattrBlk: uint64(le.Uint32(sb[44:])),
		dirblkbits: uint(sb[90])}
	if fs.blkszbits < 9 || fs.blkszbits > 16 || fs.dirblkbits != 0 {
		return nil, errors.New("unsupported EROFS block size")
	}
	if sb[91] != 0 {
		return nil, errors.New("EROFS long xattr name prefixes are not supported")
	}
	return fs, nil
}

func (fs *erofsFS) blksz() uint64 { return 1 << fs.blkszbits }

func (fs *erofsFS) inodeOffset(nid uint64) uint64 { return fs.metaBlk<<fs.blkszbits + nid*32 }

func (fs *erofsFS) readInode(nid uint64) (*erofsInode, error) {
	b := make([]byte, 64)
	if _, err := fs.r.ReadAt(b, int64(fs.inodeOffset(nid))); err != nil && err != io.EOF {
		return nil, err
	}
	in := &erofsInode{nid: nid, format: le.Uint16(b), xattrIcount: le.Uint16(b[2:]), mode: le.Uint16(b[4:])}
	if in.format&1 == 0 { // compact
		in.nlink, in.size = uint32(le.Uint16(b[6:])), uint64(le.Uint32(b[8:]))
		in.rawBlk = le.Uint32(b[16:])
		in.uid, in.gid = uint32(le.Uint16(b[24:])), uint32(le.Uint16(b[26:]))
		in.mtime, in.mtimeNsec, in.inodeSize = fs.buildTime, fs.buildTimeNsec, 32
	} else {
		in.size, in.rawBlk = le.Uint64(b[8:]), le.Uint32(b[16:])
		in.uid, in.gid = le.Uint32(b[24:]), le.Uint32(b[28:])
		in.mtime, in.mtimeNsec, in.nlink = le.Uint64(b[32:]), le.Uint32(b[40:]), le.Uint32(b[44:])
		in.inodeSize = 64
	}
	if in.format>>1&0x7 > 4 || in.format>>4 != 0 {
		return nil, fmt.Errorf("nid %d: unknown inode format %#x", nid, in.format)
	}
	return in, nil
}

func (in *erofsInode) layout() uint16 { return in.format >> 1 & 0x7 }

func (in *erofsInode) xattrSize() uint64 {
	if in.xattrIcount == 0 {
		return 0
	}
	return 12 + uint64(in.xattrIcount-1)*4
}

type xattr struct{ name, value []byte }

func (fs *erofsFS) readEntry(off uint64) (xattr, uint64, error) {
	h := make([]byte, 4)
	if _, err := fs.r.ReadAt(h, int64(off)); err != nil {
		return xattr{}, 0, err
	}
	nameLen, index, valueLen := uint64(h[0]), h[1], uint64(le.Uint16(h[2:]))
	if index&0x80 != 0 {
		return xattr{}, 0, errors.New("EROFS long xattr name prefixes are not supported")
	}
	prefix, ok := xattrPrefixes[index]
	if !ok {
		return xattr{}, 0, fmt.Errorf("unknown xattr name index %d", index)
	}
	body := make([]byte, nameLen+valueLen)
	if _, err := fs.r.ReadAt(body, int64(off+4)); err != nil {
		return xattr{}, 0, err
	}
	return xattr{append([]byte(prefix), body[:nameLen]...), body[nameLen:]}, roundUp(4+nameLen+valueLen, 4), nil
}

func (fs *erofsFS) xattrs(in *erofsInode) ([]xattr, error) {
	size := in.xattrSize()
	if size == 0 {
		return nil, nil
	}
	base := fs.inodeOffset(in.nid) + in.inodeSize
	h := make([]byte, 12)
	if _, err := fs.r.ReadAt(h, int64(base)); err != nil {
		return nil, err
	}
	shared := uint64(h[4])
	var out []xattr
	ids := make([]byte, shared*4)
	if _, err := fs.r.ReadAt(ids, int64(base+12)); err != nil {
		return nil, err
	}
	for i := uint64(0); i < shared; i++ {
		x, _, err := fs.readEntry(fs.xattrBlk<<fs.blkszbits + uint64(le.Uint32(ids[i*4:]))*4)
		if err != nil {
			return nil, err
		}
		out = append(out, x)
	}
	for at, end := base+12+shared*4, base+size; at < end; {
		x, n, err := fs.readEntry(at)
		if err != nil {
			return nil, err
		}
		out = append(out, x)
		at += n
	}
	return out, nil
}

// dirData returns a directory's bytes (flat plain or flat inline layout only).
func (fs *erofsFS) dirData(in *erofsInode) ([]byte, error) {
	if in.size > maxCheckedFile {
		return nil, fmt.Errorf("nid %d: a %d-byte directory", in.nid, in.size)
	}
	if in.layout() == layoutFlatInline && in.size > 0 && in.size%fs.blksz() == 0 {
		return nil, fmt.Errorf("nid %d: inline data across blocks", in.nid) // as the kernel and liberofs refuse it
	}
	data := make([]byte, in.size)
	bs := fs.blksz()
	switch in.layout() {
	case layoutFlatPlain:
		if _, err := fs.r.ReadAt(data, int64(uint64(in.rawBlk)<<fs.blkszbits)); err != nil && err != io.EOF {
			return nil, err
		}
	case layoutFlatInline:
		full := in.size / bs * bs
		if full > 0 {
			if _, err := fs.r.ReadAt(data[:full], int64(uint64(in.rawBlk)<<fs.blkszbits)); err != nil {
				return nil, err
			}
		}
		if tail := in.size - full; tail > 0 {
			off := fs.inodeOffset(in.nid) + in.inodeSize + in.xattrSize()
			if _, err := fs.r.ReadAt(data[full:], int64(off)); err != nil && err != io.EOF {
				return nil, err
			}
		}
	default:
		return nil, fmt.Errorf("nid %d: directory layout %d is not supported", in.nid, in.layout())
	}
	return data, nil
}

// errNotFlat: a file whose data is compressed or chunked; fsck.erofs reads those.
var errNotFlat = errors.New("EROFS file data is not stored flat")

// fileReader reads an uncompressed file's data (flat plain or flat inline layout).
func (fs *erofsFS) fileReader(in *erofsInode) (io.ReaderAt, error) {
	start := int64(uint64(in.rawBlk) << fs.blkszbits)
	switch in.layout() {
	case layoutFlatPlain:
		if in.size == 0 {
			start = 0
		}
		return io.NewSectionReader(fs.r, start, int64(in.size)), nil
	case layoutFlatInline:
		full := in.size / fs.blksz() * fs.blksz()
		tail := fs.inodeOffset(in.nid) + in.inodeSize + in.xattrSize()
		// The kernel and liberofs take ceil(size/block)-1 whole blocks: a tail of a whole block cannot be inline.
		if (in.size > 0 && in.size == full) || in.size-full > fs.blksz()-tail%fs.blksz() {
			return nil, fmt.Errorf("nid %d: inline data across blocks", in.nid)
		}
		return &inlineReader{fs.r, start, int64(full), int64(tail), int64(in.size)}, nil
	}
	return nil, errNotFlat
}

// inlineReader: whole blocks from the data area, the tail from beside the inode.
type inlineReader struct {
	r                        io.ReaderAt
	blocks, full, tail, size int64
}

func (x *inlineReader) ReadAt(p []byte, off int64) (int, error) {
	n := 0
	for len(p) > 0 {
		if off >= x.size {
			return n, io.EOF
		}
		at, end := x.blocks+off, x.full
		if off >= x.full {
			at, end = x.tail+off-x.full, x.size
		}
		c := min(int64(len(p)), end-off)
		if m, err := x.r.ReadAt(p[:c], at); int64(m) < c {
			if err == nil || err == io.EOF {
				err = io.ErrUnexpectedEOF
			}
			return n + m, err
		}
		n, off, p = n+int(c), off+c, p[c:]
	}
	return n, nil
}

type dirent struct {
	nid  uint64
	name string
}

func (fs *erofsFS) readDir(in *erofsInode) ([]dirent, error) {
	data, err := fs.dirData(in)
	if err != nil {
		return nil, err
	}
	var out []dirent
	bs := fs.blksz()
	for start := uint64(0); start < uint64(len(data)); start += bs {
		blk := data[start:min(start+bs, uint64(len(data)))]
		if len(blk) < erofsDirentSize {
			return nil, errors.New("short directory block")
		}
		n := uint64(le.Uint16(blk[8:])) / erofsDirentSize
		if n == 0 || n*erofsDirentSize > uint64(len(blk)) {
			return nil, errors.New("malformed directory block")
		}
		for i := uint64(0); i < n; i++ {
			d := blk[i*erofsDirentSize:]
			nameOff := uint64(le.Uint16(d[8:]))
			end := uint64(len(blk))
			if i+1 < n {
				end = uint64(le.Uint16(blk[(i+1)*erofsDirentSize+8:]))
			}
			if nameOff > end || end > uint64(len(blk)) {
				return nil, errors.New("malformed directory entry")
			}
			name := blk[nameOff:end]
			if i+1 == n {
				if z := strings.IndexByte(string(name), 0); z >= 0 {
					name = name[:z]
				}
			}
			out = append(out, dirent{le.Uint64(d), string(name)})
		}
	}
	return out, nil
}

// inventory returns erofs-inventory's rows, sorted (as build-input-candidate.inventory() sorts them).
func inventory(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	fs, err := openErofs(f)
	if err != nil {
		return nil, fmt.Errorf("%s: %v", path, err)
	}
	var rows []string
	seenDirs := map[uint64]bool{}
	var visit func(nid uint64, p string) error
	visit = func(nid uint64, p string) error {
		in, err := fs.readInode(nid)
		if err != nil {
			return err
		}
		size := in.size
		dir := uint32(in.mode)&sIFMT == sIFDIR
		if dir {
			size = 0
		}
		hp := hex.EncodeToString([]byte(p))
		rows = append(rows, fmt.Sprintf("I %s %d %d %d %d %d %d %d", hp, in.mode, in.uid, in.gid, in.nlink, size, in.mtime, in.mtimeNsec))
		xs, err := fs.xattrs(in)
		if err != nil {
			return fmt.Errorf("%s: %v", p, err)
		}
		for _, x := range xs {
			rows = append(rows, fmt.Sprintf("X %s %s %s", hp, hex.EncodeToString(x.name), hex.EncodeToString(x.value)))
		}
		if !dir {
			return nil
		}
		if seenDirs[nid] {
			return fmt.Errorf("%s: directory loop", p)
		}
		seenDirs[nid] = true
		ents, err := fs.readDir(in)
		if err != nil {
			return fmt.Errorf("%s: %v", p, err)
		}
		for _, e := range ents {
			if e.name == "." || e.name == ".." {
				continue
			}
			if err := visit(e.nid, p+"/"+e.name); err != nil {
				return err
			}
		}
		return nil
	}
	if err := visit(fs.rootNid, ""); err != nil {
		return nil, err
	}
	sort.Strings(rows)
	return rows, nil
}
