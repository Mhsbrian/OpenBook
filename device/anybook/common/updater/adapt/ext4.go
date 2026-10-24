// SPDX-License-Identifier: Apache-2.0

// A read-only ext4 reader, just enough for the firmware-safety check to read the init scripts inside an
// APEX whose payload is ext4 (Google's images carry one: the CTS shim). It lists directories and reads
// files mapped by extents. Anything else (block-mapped or inline-data files, an unknown incompatible
// feature) is refused rather than guessed.
package main

import (
	"fmt"
	"io"
	"sort"
)

const (
	ext4Magic     = 0xEF53
	ext4RootInode = 2
	ext4Extents   = 0x80000    // inode flag: mapped by an extent tree
	ext4Inline    = 0x10000000 // inode flag: data in the inode
	// filetype, mmp, extents, 64bit, flex_bg, ea_inode, csum_seed, largedir, casefold: none changes where
	// directory entries or extent-mapped file data are
	ext4KnownIncompat = 0x2 | 0x100 | 0x40 | 0x80 | 0x200 | 0x400 | 0x2000 | 0x4000 | 0x20000
	sIFREG, sIFLNK    = 0o100000, 0o120000
)

type ext4FS struct {
	r                      io.ReaderAt
	bs                     uint64
	inodeSize, descSize    uint64
	inodesPerGroup, inodes uint64
	gdt                    uint64 // byte offset of the group descriptor table
	is64                   bool
}

type ext4Inode struct {
	mode  uint16
	size  uint64
	flags uint32
	block []byte // i_block: the extent tree's root
}

type ext4Extent struct {
	logical, length, physical uint64
	unwritten                 bool
}

func openExt4(r io.ReaderAt) (*ext4FS, error) {
	sb := make([]byte, 1024)
	if _, err := r.ReadAt(sb, 1024); err != nil {
		return nil, err
	}
	if le.Uint16(sb[56:]) != ext4Magic {
		return nil, errFormat("not an ext4 image")
	}
	logBS := le.Uint32(sb[24:])
	if logBS > 6 {
		return nil, errFormat("unsupported ext4 block size")
	}
	incompat := le.Uint32(sb[96:])
	if incompat&^uint32(ext4KnownIncompat) != 0 {
		return nil, errFormat("ext4 incompatible features %#x are not supported", incompat)
	}
	fs := &ext4FS{r: r, bs: 1024 << logBS, inodeSize: 128, descSize: 32, inodesPerGroup: uint64(le.Uint32(sb[40:])),
		inodes: uint64(le.Uint32(sb)), is64: incompat&0x80 != 0}
	if le.Uint32(sb[76:]) >= 1 { // dynamic revision: the inode size is recorded
		fs.inodeSize = uint64(le.Uint16(sb[88:]))
	}
	if fs.is64 {
		fs.descSize = uint64(le.Uint16(sb[254:]))
	}
	if fs.inodeSize < 128 || fs.descSize < 32 || fs.inodesPerGroup == 0 {
		return nil, errFormat("malformed ext4 superblock")
	}
	fs.gdt = (uint64(le.Uint32(sb[20:])) + 1) * fs.bs
	return fs, nil
}

func (fs *ext4FS) inode(ino uint64) (*ext4Inode, error) {
	if ino == 0 || ino > fs.inodes {
		return nil, errFormat("ext4 inode %d out of range", ino)
	}
	group, index := (ino-1)/fs.inodesPerGroup, (ino-1)%fs.inodesPerGroup
	d := make([]byte, fs.descSize)
	if _, err := fs.r.ReadAt(d, int64(fs.gdt+group*fs.descSize)); err != nil {
		return nil, err
	}
	table := uint64(le.Uint32(d[8:]))
	if fs.is64 && fs.descSize >= 64 {
		table |= uint64(le.Uint32(d[0x28:])) << 32
	}
	b := make([]byte, 128)
	if _, err := fs.r.ReadAt(b, int64(table*fs.bs+index*fs.inodeSize)); err != nil {
		return nil, err
	}
	return &ext4Inode{mode: le.Uint16(b), size: uint64(le.Uint32(b[4:])) | uint64(le.Uint32(b[108:]))<<32,
		flags: le.Uint32(b[32:]), block: b[40:100]}, nil
}

// extents returns a file's extents, in logical order. Each level of the tree must be one less deep than
// its parent, and the tree is bounded, so a malformed one cannot loop or grow without end.
func (fs *ext4FS) extents(in *ext4Inode) ([]ext4Extent, error) {
	if in.flags&ext4Inline != 0 {
		return nil, errFormat("ext4 inline data is not supported")
	}
	if in.flags&ext4Extents == 0 {
		return nil, errFormat("ext4 block-mapped files are not supported")
	}
	var out []ext4Extent
	nodes := 0
	var walk func(node []byte, want int) error
	walk = func(node []byte, want int) error {
		if len(node) < 12 || le.Uint16(node) != 0xF30A {
			return errFormat("bad ext4 extent header")
		}
		n, depth := int(le.Uint16(node[2:])), int(le.Uint16(node[6:]))
		if 12+n*12 > len(node) || depth > 5 || (want >= 0 && depth != want) {
			return errFormat("malformed ext4 extent tree")
		}
		for i := 0; i < n; i++ {
			e := node[12+i*12:]
			if depth == 0 {
				length := uint64(le.Uint16(e[4:]))
				x := ext4Extent{logical: uint64(le.Uint32(e)), length: length,
					physical: uint64(le.Uint16(e[6:]))<<32 | uint64(le.Uint32(e[8:]))}
				if length > 32768 { // an unwritten extent reads as zeros
					x.length, x.unwritten = length-32768, true
				}
				if out = append(out, x); len(out) > 1<<20 {
					return errFormat("too many ext4 extents")
				}
				continue
			}
			if nodes++; nodes > 1<<14 {
				return errFormat("too many ext4 extent tree nodes")
			}
			child := make([]byte, fs.bs)
			leaf := uint64(le.Uint32(e[4:])) | uint64(le.Uint16(e[8:]))<<32
			if _, err := fs.r.ReadAt(child, int64(leaf*fs.bs)); err != nil {
				return err
			}
			if err := walk(child, depth-1); err != nil {
				return err
			}
		}
		return nil
	}
	if err := walk(in.block, -1); err != nil {
		return nil, err
	}
	sort.Slice(out, func(i, j int) bool { return out[i].logical < out[j].logical })
	return out, nil
}

// extentReader reads a file through its extents; holes and unwritten extents read as zeros.
type extentReader struct {
	fs   *ext4FS
	ext  []ext4Extent
	size int64
}

func (x *extentReader) ReadAt(p []byte, off int64) (int, error) {
	n := 0
	for len(p) > 0 {
		if off >= x.size {
			return n, io.EOF
		}
		blk, in := uint64(off)/x.fs.bs, uint64(off)%x.fs.bs
		c := min(uint64(len(p)), x.fs.bs-in, uint64(x.size-off))
		i := sort.Search(len(x.ext), func(i int) bool { return x.ext[i].logical+x.ext[i].length > blk })
		if i < len(x.ext) && x.ext[i].logical <= blk && !x.ext[i].unwritten {
			at := (x.ext[i].physical+blk-x.ext[i].logical)*x.fs.bs + in
			if m, err := x.fs.r.ReadAt(p[:c], int64(at)); uint64(m) < c {
				if err == nil || err == io.EOF {
					err = io.ErrUnexpectedEOF
				}
				return n + m, err
			}
		} else {
			clear(p[:c])
		}
		n, off, p = n+int(c), off+int64(c), p[c:]
	}
	return n, nil
}

func (fs *ext4FS) reader(in *ext4Inode) (io.ReaderAt, error) {
	ext, err := fs.extents(in)
	if err != nil {
		return nil, err
	}
	return &extentReader{fs, ext, int64(in.size)}, nil
}

// readDir lists a directory's entries (inode, name). Hashed directories read the same way: their index
// blocks hold one empty entry each.
func (fs *ext4FS) readDir(in *ext4Inode) ([]dirent, error) {
	r, err := fs.reader(in)
	if err != nil {
		return nil, err
	}
	data, err := readAllAt(r, int64(in.size))
	if err != nil {
		return nil, err
	}
	var out []dirent
	for start := uint64(0); start < uint64(len(data)); start += fs.bs {
		blk := data[start:min(start+fs.bs, uint64(len(data)))]
		for off := 0; off+8 <= len(blk); {
			ino, recLen, nameLen := le.Uint32(blk[off:]), int(le.Uint16(blk[off+4:])), int(blk[off+6])
			if recLen < 8 || off+recLen > len(blk) || 8+nameLen > recLen {
				return nil, errFormat("malformed ext4 directory entry")
			}
			if ino != 0 && nameLen > 0 {
				out = append(out, dirent{uint64(ino), string(blk[off+8 : off+8+nameLen])})
			}
			off += recLen
		}
	}
	return out, nil
}

func readAllAt(r io.ReaderAt, size int64) ([]byte, error) {
	if size < 0 || size > maxCheckedFile {
		return nil, fmt.Errorf("a %d-byte file is larger than this check reads", size)
	}
	b := make([]byte, size)
	if n, err := r.ReadAt(b, 0); int64(n) < size {
		if err == nil || err == io.EOF {
			err = io.ErrUnexpectedEOF
		}
		return nil, err
	}
	return b, nil
}
