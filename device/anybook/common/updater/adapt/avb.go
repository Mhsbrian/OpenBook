// SPDX-License-Identifier: Apache-2.0

// Android Verified Boot (AVB) structures, as external/avb/avbtool.py (1.4.0) writes them: dm-verity hash
// trees, image footers, descriptors and signed vbmeta images. Byte-for-byte compatible with avbtool for the
// operations OpenBook uses (add_hashtree_footer without FEC, make_vbmeta_image with SHA256_RSA4096 and
// --include_descriptors_from_image), so the laptop builds exactly what the host build would.
package main

import (
	"bytes"
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/subtle"
	"crypto/x509"
	"encoding/binary"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"math/big"
	"os"
	"runtime"
	"sort"
	"sync"
)

const (
	avbFooterSize     = 64
	avbHeaderSize     = 256
	avbMaxVBMetaSize  = 64 * 1024
	avbMaxFooterSize  = 4096
	avbBlockSize      = 4096
	avbReleaseString  = "avbtool 1.4.0"
	algNone           = 0
	algSHA256RSA4096  = 2
	tagProperty       = 0
	tagHashtree       = 1
	tagHash           = 2
	tagKernelCmdline  = 3
	tagChainPartition = 4
)

var be = binary.BigEndian

func roundUp(n, m uint64) uint64 { return (n + m - 1) / m * m }

// Descriptor is one AVB descriptor. Raw is its exact encoding; hash and hashtree descriptors are also parsed.
type Descriptor struct {
	Tag       uint64
	Raw       []byte
	Partition string // hash, hashtree and chain-partition descriptors
	Hashtree  *HashtreeDesc
	Hash      *HashDesc
}

type HashtreeDesc struct {
	DmVerityVersion                           uint32
	ImageSize, TreeOffset, TreeSize           uint64
	DataBlockSize, HashBlockSize, FECNumRoots uint32
	FECOffset, FECSize                        uint64
	HashAlgorithm, PartitionName              string
	Salt, RootDigest                          []byte
	Flags                                     uint32
}

type HashDesc struct {
	ImageSize                    uint64
	HashAlgorithm, PartitionName string
	Salt, Digest                 []byte
	Flags                        uint32
}

func cstr(b []byte) string { return string(bytes.TrimRight(b, "\x00")) }

func pad32(s string) []byte {
	b := make([]byte, 32)
	copy(b, s)
	return b
}

// Encode is avbtool's AvbHashtreeDescriptor.encode().
func (d *HashtreeDesc) Encode() []byte {
	const size = 120 + 60
	nbf := uint64(size + len(d.PartitionName) + len(d.Salt) + len(d.RootDigest) - 16)
	padded := roundUp(nbf, 8)
	var b bytes.Buffer
	for _, v := range []any{uint64(tagHashtree), padded, d.DmVerityVersion, d.ImageSize, d.TreeOffset, d.TreeSize,
		d.DataBlockSize, d.HashBlockSize, d.FECNumRoots, d.FECOffset, d.FECSize} {
		binary.Write(&b, be, v)
	}
	b.Write(pad32(d.HashAlgorithm))
	for _, v := range []uint32{uint32(len(d.PartitionName)), uint32(len(d.Salt)), uint32(len(d.RootDigest)), d.Flags} {
		binary.Write(&b, be, v)
	}
	b.Write(make([]byte, 60))
	b.WriteString(d.PartitionName)
	b.Write(d.Salt)
	b.Write(d.RootDigest)
	b.Write(make([]byte, padded-nbf))
	return b.Bytes()
}

// Encode is avbtool's AvbHashDescriptor.encode().
func (d *HashDesc) Encode() []byte {
	const size = 72 + 60
	nbf := uint64(size + len(d.PartitionName) + len(d.Salt) + len(d.Digest) - 16)
	padded := roundUp(nbf, 8)
	var b bytes.Buffer
	binary.Write(&b, be, uint64(tagHash))
	binary.Write(&b, be, padded)
	binary.Write(&b, be, d.ImageSize)
	b.Write(pad32(d.HashAlgorithm))
	for _, v := range []uint32{uint32(len(d.PartitionName)), uint32(len(d.Salt)), uint32(len(d.Digest)), d.Flags} {
		binary.Write(&b, be, v)
	}
	b.Write(make([]byte, 60))
	b.WriteString(d.PartitionName)
	b.Write(d.Salt)
	b.Write(d.Digest)
	b.Write(make([]byte, padded-nbf))
	return b.Bytes()
}

func parseDescriptors(data []byte) ([]Descriptor, error) {
	var out []Descriptor
	for at := 0; at < len(data); {
		if len(data)-at < 16 {
			return nil, errors.New("truncated AVB descriptor")
		}
		tag, nbf := be.Uint64(data[at:]), be.Uint64(data[at+8:])
		if nbf%8 != 0 || nbf > uint64(len(data)-at-16) {
			return nil, errors.New("malformed AVB descriptor length")
		}
		raw := data[at : at+16+int(nbf)]
		d := Descriptor{Tag: tag, Raw: append([]byte(nil), raw...)}
		switch tag {
		case tagHashtree:
			if len(raw) < 180 {
				return nil, errors.New("short hashtree descriptor")
			}
			h := &HashtreeDesc{
				DmVerityVersion: be.Uint32(raw[16:]), ImageSize: be.Uint64(raw[20:]), TreeOffset: be.Uint64(raw[28:]),
				TreeSize: be.Uint64(raw[36:]), DataBlockSize: be.Uint32(raw[44:]), HashBlockSize: be.Uint32(raw[48:]),
				FECNumRoots: be.Uint32(raw[52:]), FECOffset: be.Uint64(raw[56:]), FECSize: be.Uint64(raw[64:]),
				HashAlgorithm: cstr(raw[72:104]), Flags: be.Uint32(raw[116:]),
			}
			nl, sl, rl := int(be.Uint32(raw[104:])), int(be.Uint32(raw[108:])), int(be.Uint32(raw[112:]))
			if 180+nl+sl+rl > len(raw) {
				return nil, errors.New("hashtree descriptor overflows")
			}
			p := raw[180:]
			h.PartitionName, h.Salt, h.RootDigest = string(p[:nl]), append([]byte(nil), p[nl:nl+sl]...),
				append([]byte(nil), p[nl+sl:nl+sl+rl]...)
			d.Hashtree, d.Partition = h, h.PartitionName
		case tagHash:
			if len(raw) < 132 {
				return nil, errors.New("short hash descriptor")
			}
			h := &HashDesc{ImageSize: be.Uint64(raw[16:]), HashAlgorithm: cstr(raw[24:56]), Flags: be.Uint32(raw[68:])}
			nl, sl, dl := int(be.Uint32(raw[56:])), int(be.Uint32(raw[60:])), int(be.Uint32(raw[64:]))
			if 132+nl+sl+dl > len(raw) {
				return nil, errors.New("hash descriptor overflows")
			}
			p := raw[132:]
			h.PartitionName, h.Salt, h.Digest = string(p[:nl]), append([]byte(nil), p[nl:nl+sl]...),
				append([]byte(nil), p[nl+sl:nl+sl+dl]...)
			d.Hash, d.Partition = h, h.PartitionName
		case tagChainPartition:
			if len(raw) < 92 {
				return nil, errors.New("short chain partition descriptor")
			}
			nl := int(be.Uint32(raw[20:]))
			if 92+nl > len(raw) {
				return nil, errors.New("chain partition descriptor overflows")
			}
			d.Partition = string(raw[92 : 92+nl])
		}
		out = append(out, d)
		at += len(raw)
	}
	return out, nil
}

// avbtool re-encodes included descriptors; for the kinds it parses, the re-encoding must be the stored bytes.
func canonical(d Descriptor) ([]byte, error) {
	var enc []byte
	switch {
	case d.Hashtree != nil:
		enc = d.Hashtree.Encode()
	case d.Hash != nil:
		enc = d.Hash.Encode()
	default:
		return d.Raw, nil
	}
	if !bytes.Equal(enc, d.Raw) {
		return nil, fmt.Errorf("%s descriptor is not in avbtool's canonical encoding", d.Partition)
	}
	return enc, nil
}

// VBMeta is a parsed vbmeta blob.
type VBMeta struct {
	Blob          []byte // header + authentication + auxiliary
	MinorVersion  uint32
	Algorithm     uint32
	RollbackIndex uint64
	Flags         uint32
	Release       string
	Descriptors   []Descriptor
	PublicKey     []byte
}

func parseVBMeta(b []byte) (*VBMeta, error) {
	if len(b) < avbHeaderSize || string(b[:4]) != "AVB0" {
		return nil, errors.New("not a vbmeta image")
	}
	auth, aux := be.Uint64(b[12:]), be.Uint64(b[20:])
	total := uint64(avbHeaderSize) + auth + aux
	if auth > avbMaxVBMetaSize || aux > avbMaxVBMetaSize || total > uint64(len(b)) {
		return nil, errors.New("vbmeta sizes out of range")
	}
	v := &VBMeta{Blob: append([]byte(nil), b[:total]...), MinorVersion: be.Uint32(b[8:]), Algorithm: be.Uint32(b[28:]),
		RollbackIndex: be.Uint64(b[112:]), Flags: be.Uint32(b[120:]), Release: cstr(b[128:176])}
	field := func(off uint64) (uint64, uint64) { return be.Uint64(b[off:]), be.Uint64(b[off+8:]) }
	A := b[avbHeaderSize+auth : total]
	pko, pks := field(64)
	do, ds := field(96)
	if pko+pks > aux || do+ds > aux {
		return nil, errors.New("vbmeta offsets out of range")
	}
	v.PublicKey = append([]byte(nil), A[pko:pko+pks]...)
	var err error
	if v.Descriptors, err = parseDescriptors(A[do : do+ds]); err != nil {
		return nil, err
	}
	return v, nil
}

// Verify checks the vbmeta's hash and RSA signature against its own embedded public key.
func (v *VBMeta) Verify() error {
	b := v.Blob
	auth, aux := be.Uint64(b[12:]), be.Uint64(b[20:])
	if v.Algorithm != algSHA256RSA4096 {
		return fmt.Errorf("vbmeta algorithm %d is not SHA256_RSA4096", v.Algorithm)
	}
	ho, hs := be.Uint64(b[32:]), be.Uint64(b[40:])
	so, ss := be.Uint64(b[48:]), be.Uint64(b[56:])
	if hs != 32 || ss != 512 || ho+hs > auth || so+ss > auth {
		return errors.New("vbmeta authentication block malformed")
	}
	authBlock := b[avbHeaderSize : avbHeaderSize+auth]
	h := sha256.New()
	h.Write(b[:avbHeaderSize])
	h.Write(b[avbHeaderSize+auth : avbHeaderSize+auth+aux])
	sum := h.Sum(nil)
	if subtle.ConstantTimeCompare(sum, authBlock[ho:ho+hs]) != 1 {
		return errors.New("vbmeta hash mismatch")
	}
	pub, err := decodeAVBPublicKey(v.PublicKey)
	if err != nil {
		return err
	}
	return rsa.VerifyPKCS1v15(pub, crypto.SHA256, sum, authBlock[so:so+ss])
}

func decodeAVBPublicKey(blob []byte) (*rsa.PublicKey, error) {
	if len(blob) < 8 {
		return nil, errors.New("short AVB public key")
	}
	bits := be.Uint32(blob)
	if bits%8 != 0 || len(blob) != 8+2*int(bits/8) {
		return nil, errors.New("malformed AVB public key")
	}
	return &rsa.PublicKey{N: new(big.Int).SetBytes(blob[8 : 8+bits/8]), E: 65537}, nil
}

// encodeAVBPublicKey is avbtool's RSAPublicKey.encode(): bits, n0inv, n and r^2 mod n, big-endian.
func encodeAVBPublicKey(pub *rsa.PublicKey) []byte {
	n := pub.N
	bits := 1
	for bits < n.BitLen() {
		bits <<= 1
	}
	b32 := new(big.Int).Lsh(big.NewInt(1), 32)
	n0inv := new(big.Int).Sub(b32, new(big.Int).ModInverse(n, b32))
	r := new(big.Int).Lsh(big.NewInt(1), uint(n.BitLen()))
	rr := new(big.Int).Mod(new(big.Int).Mul(r, r), n)
	out := make([]byte, 8+2*bits/8)
	be.PutUint32(out, uint32(bits))
	be.PutUint32(out[4:], uint32(n0inv.Uint64()))
	n.FillBytes(out[8 : 8+bits/8])
	rr.FillBytes(out[8+bits/8:])
	return out
}

func loadRSAKey(path string) (*rsa.PrivateKey, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	block, _ := pem.Decode(data)
	if block == nil {
		return nil, fmt.Errorf("%s: no PEM key", path)
	}
	if k, err := x509.ParsePKCS1PrivateKey(block.Bytes); err == nil {
		return k, nil
	}
	k, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("%s: %v", path, err)
	}
	rk, ok := k.(*rsa.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("%s: not an RSA key", path)
	}
	return rk, nil
}

// vbmetaBlob is avbtool's _generate_vbmeta_blob() for NONE (key nil) or SHA256_RSA4096.
func vbmetaBlob(descriptors []byte, key *rsa.PrivateKey, minor uint32) ([]byte, error) {
	var encKey []byte
	alg, hashBytes, sigBytes := uint32(algNone), uint64(0), uint64(0)
	if key != nil {
		if key.N.BitLen() != 4096 {
			return nil, errors.New("the vbmeta key must be RSA-4096")
		}
		encKey = encodeAVBPublicKey(&key.PublicKey)
		alg, hashBytes, sigBytes = algSHA256RSA4096, 32, 512
	}
	auxSize := roundUp(uint64(len(descriptors)+len(encKey)), 64)
	authSize := roundUp(hashBytes+sigBytes, 64)
	hdr := make([]byte, avbHeaderSize)
	copy(hdr, "AVB0")
	be.PutUint32(hdr[4:], 1)
	be.PutUint32(hdr[8:], minor)
	be.PutUint64(hdr[12:], authSize)
	be.PutUint64(hdr[20:], auxSize)
	be.PutUint32(hdr[28:], alg)
	be.PutUint64(hdr[32:], 0)                                    // hash offset
	be.PutUint64(hdr[40:], hashBytes)                            // hash size
	be.PutUint64(hdr[48:], hashBytes)                            // signature offset
	be.PutUint64(hdr[56:], sigBytes)                             // signature size
	be.PutUint64(hdr[64:], uint64(len(descriptors)))             // public key offset
	be.PutUint64(hdr[72:], uint64(len(encKey)))                  // public key size
	be.PutUint64(hdr[80:], uint64(len(descriptors)+len(encKey))) // public key metadata offset
	be.PutUint64(hdr[88:], 0)                                    // public key metadata size
	be.PutUint64(hdr[96:], 0)                                    // descriptors offset
	be.PutUint64(hdr[104:], uint64(len(descriptors)))            // descriptors size
	// rollback index 0, flags 0, rollback index location 0
	copy(hdr[128:175], avbReleaseString)
	aux := make([]byte, auxSize)
	copy(aux, descriptors)
	copy(aux[len(descriptors):], encKey)
	auth := make([]byte, authSize)
	if key != nil {
		h := sha256.New()
		h.Write(hdr)
		h.Write(aux)
		sum := h.Sum(nil)
		sig, err := rsa.SignPKCS1v15(nil, key, crypto.SHA256, sum)
		if err != nil {
			return nil, err
		}
		copy(auth, sum)
		copy(auth[32:], sig)
	}
	return append(append(hdr, auth...), aux...), nil
}

// readImageVBMeta returns the vbmeta of an image: from its AVB footer, or at offset 0 (a vbmeta image).
func readImageVBMeta(path string) (*VBMeta, *Footer, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, nil, err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return nil, nil, err
	}
	var foot *Footer
	off, size := int64(0), int64(avbMaxVBMetaSize)
	if st.Size() >= avbFooterSize {
		tail := make([]byte, avbFooterSize)
		if _, err := f.ReadAt(tail, st.Size()-avbFooterSize); err != nil {
			return nil, nil, err
		}
		if string(tail[:4]) == "AVBf" {
			foot = &Footer{OriginalSize: be.Uint64(tail[12:]), VBMetaOffset: be.Uint64(tail[20:]), VBMetaSize: be.Uint64(tail[28:])}
			off, size = int64(foot.VBMetaOffset), int64(foot.VBMetaSize)
		}
	}
	if size > st.Size()-off {
		size = st.Size() - off
	}
	buf := make([]byte, size)
	if _, err := f.ReadAt(buf, off); err != nil && err != io.EOF {
		return nil, nil, err
	}
	v, err := parseVBMeta(buf)
	if err != nil {
		return nil, nil, fmt.Errorf("%s: %v", path, err)
	}
	return v, foot, nil
}

type Footer struct{ OriginalSize, VBMetaOffset, VBMetaSize uint64 }

func (f Footer) encode() []byte {
	b := make([]byte, avbFooterSize)
	copy(b, "AVBf")
	be.PutUint32(b[4:], 1)
	be.PutUint32(b[8:], 0)
	be.PutUint64(b[12:], f.OriginalSize)
	be.PutUint64(b[20:], f.VBMetaOffset)
	be.PutUint64(b[28:], f.VBMetaSize)
	return b
}

// hashLevelOffsets is avbtool's calc_hash_level_offsets() for 32-byte digests.
func hashLevelOffsets(imageSize, block uint64) ([]uint64, uint64) {
	var sizes []uint64
	var tree uint64
	for size := imageSize; size > block; {
		n := (size + block - 1) / block
		level := roundUp(n*32, block)
		sizes = append(sizes, level)
		tree += level
		size = level
	}
	offs := make([]uint64, len(sizes))
	for n := range sizes {
		for m := n + 1; m < len(sizes); m++ {
			offs[n] += sizes[m]
		}
	}
	return offs, tree
}

func saltedHash(salt, block []byte) [32]byte {
	h := sha256.New()
	h.Write(salt)
	h.Write(block)
	var out [32]byte
	copy(out[:], h.Sum(nil))
	return out
}

// hashTree is avbtool's generate_hash_tree() (SHA-256, 4 KiB blocks): the root digest and the tree. The first
// level hashes `size` bytes of r (zero-padded to a block); the work is split across CPUs, the result is not.
func hashTree(r io.ReaderAt, size uint64, salt []byte) ([]byte, []byte, error) {
	const block = avbBlockSize
	offs, treeSize := hashLevelOffsets(size, block)
	tree := make([]byte, treeSize)
	if size == block {
		buf := make([]byte, block)
		if n, err := r.ReadAt(buf, 0); n != block {
			if err == nil {
				err = io.ErrUnexpectedEOF
			}
			return nil, nil, err
		}
		d := saltedHash(salt, buf)
		return d[:], tree, nil
	}
	nblocks := (size + block - 1) / block
	level0 := make([]byte, nblocks*32)
	workers := runtime.NumCPU()
	const chunk = 2048 // blocks per job (8 MiB)
	jobs := make(chan uint64)
	var mu sync.Mutex
	var firstErr error
	failed := func() bool { mu.Lock(); defer mu.Unlock(); return firstErr != nil }
	var wg sync.WaitGroup
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			buf := make([]byte, chunk*block)
			for first := range jobs {
				if failed() {
					continue // drain: the first error is reported
				}
				n := min(chunk, nblocks-first)
				want := min(n*block, size-first*block)
				b := buf[:n*block]
				// The image must hold `size` bytes: a short read is an error, never stale data.
				if got, err := r.ReadAt(b[:want], int64(first*block)); uint64(got) != want {
					if err == nil {
						err = io.ErrUnexpectedEOF
					}
					mu.Lock()
					if firstErr == nil {
						firstErr = err
					}
					mu.Unlock()
					continue
				}
				clear(b[want:])
				for i := uint64(0); i < n; i++ {
					d := saltedHash(salt, b[i*block:(i+1)*block])
					copy(level0[(first+i)*32:], d[:])
				}
			}
		}()
	}
	for first := uint64(0); first < nblocks; first += chunk {
		jobs <- first
	}
	close(jobs)
	wg.Wait()
	if firstErr != nil {
		return nil, nil, firstErr
	}
	level := level0
	for n := 0; ; n++ {
		padded := make([]byte, roundUp(uint64(len(level)), block))
		copy(padded, level)
		copy(tree[offs[n]:], padded)
		if uint64(len(padded)) <= block {
			d := saltedHash(salt, padded)
			return d[:], tree, nil
		}
		next := make([]byte, 0, len(padded)/block*32)
		for i := 0; i < len(padded); i += block {
			d := saltedHash(salt, padded[i:i+block])
			next = append(next, d[:]...)
		}
		level = next
	}
}

// addHashtreeFooter is `avbtool add_hashtree_footer --partition_size P --partition_name NAME --salt SALT
// --do_not_generate_fec --hash_algorithm sha256` on a regular file that has no footer yet.
func addHashtreeFooter(path string, partitionSize uint64, name string, salt []byte) (*HashtreeDesc, error) {
	f, err := os.OpenFile(path, os.O_RDWR, 0)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return nil, err
	}
	orig := uint64(st.Size())
	if partitionSize%avbBlockSize != 0 {
		return nil, errors.New("partition size is not a multiple of 4096")
	}
	if orig >= avbFooterSize {
		tail := make([]byte, 4)
		if _, err := f.ReadAt(tail, int64(orig-avbFooterSize)); err == nil && string(tail) == "AVBf" {
			return nil, errors.New("image already has an AVB footer")
		}
	}
	_, maxTree := hashLevelOffsets(partitionSize, avbBlockSize)
	maxImage := partitionSize - (maxTree + avbMaxVBMetaSize + avbMaxFooterSize)
	size := roundUp(orig, avbBlockSize)
	if size > maxImage {
		return nil, fmt.Errorf("image of %d bytes exceeds %d to fit a %d-byte partition", size, maxImage, partitionSize)
	}
	if size > orig {
		if err := f.Truncate(int64(size)); err != nil {
			return nil, err
		}
	}
	_, treeSize := hashLevelOffsets(size, avbBlockSize)
	if size+roundUp(treeSize, avbBlockSize)+avbBlockSize > partitionSize-avbBlockSize {
		return nil, errors.New("hash tree and vbmeta do not fit the partition")
	}
	root, tree, err := hashTree(f, size, salt)
	if err != nil {
		return nil, err
	}
	desc := &HashtreeDesc{DmVerityVersion: 1, ImageSize: size, TreeOffset: size, TreeSize: uint64(len(tree)),
		DataBlockSize: avbBlockSize, HashBlockSize: avbBlockSize, HashAlgorithm: "sha256", PartitionName: name,
		Salt: salt, RootDigest: root}
	treePadded := make([]byte, roundUp(uint64(len(tree)), avbBlockSize))
	copy(treePadded, tree)
	blob, err := vbmetaBlob(desc.Encode(), nil, 0)
	if err != nil {
		return nil, err
	}
	vbOff := size + uint64(len(treePadded))
	blobPadded := make([]byte, roundUp(uint64(len(blob)), avbBlockSize))
	copy(blobPadded, blob)
	if _, err := f.WriteAt(treePadded, int64(size)); err != nil {
		return nil, err
	}
	if _, err := f.WriteAt(blobPadded, int64(vbOff)); err != nil {
		return nil, err
	}
	last := make([]byte, avbBlockSize)
	copy(last[avbBlockSize-avbFooterSize:], Footer{orig, vbOff, uint64(len(blob))}.encode())
	if vbOff+uint64(len(blobPadded)) > partitionSize-avbBlockSize {
		return nil, errors.New("hash tree and vbmeta do not fit the partition")
	}
	if err := f.Truncate(int64(partitionSize - avbBlockSize)); err != nil {
		return nil, err
	}
	if _, err := f.WriteAt(last, int64(partitionSize-avbBlockSize)); err != nil {
		return nil, err
	}
	return desc, f.Sync()
}

// verifyHashtree recomputes an image's dm-verity root digest against its descriptor, and the hash tree the
// image stores beside its data.
func verifyHashtree(path string, d *HashtreeDesc) error {
	if d.HashAlgorithm != "sha256" || d.DataBlockSize != avbBlockSize || d.HashBlockSize != avbBlockSize {
		return fmt.Errorf("%s: unsupported hash tree parameters", d.PartitionName)
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	root, tree, err := hashTree(f, d.ImageSize, d.Salt)
	if err != nil {
		return err
	}
	if !bytes.Equal(root, d.RootDigest) {
		return fmt.Errorf("%s: dm-verity root digest mismatch", d.PartitionName)
	}
	if d.TreeSize != uint64(len(tree)) {
		return fmt.Errorf("%s: hash tree size differs from its descriptor", d.PartitionName)
	}
	stored := make([]byte, len(tree))
	if n, _ := f.ReadAt(stored, int64(d.TreeOffset)); n != len(stored) || !bytes.Equal(stored, tree) {
		return fmt.Errorf("%s: the stored hash tree is not the image's", d.PartitionName)
	}
	return nil
}

// makeVBMeta is `avbtool make_vbmeta_image --algorithm SHA256_RSA4096 --key KEY --padding_size 4096` with
// --include_descriptors_from_image for each source in order. A source is an image's vbmeta. Descriptors
// without a partition name keep their order; the rest are kept once per (kind, partition), last seen wins,
// sorted by that key, as avbtool does.
func makeVBMeta(sources []*VBMeta, key *rsa.PrivateKey) ([]byte, error) {
	var plain bytes.Buffer
	named := map[string][]byte{}
	var minor uint32
	for _, s := range sources {
		minor = max(minor, s.MinorVersion)
		for _, d := range s.Descriptors {
			enc, err := canonical(d)
			if err != nil {
				return nil, err
			}
			switch d.Tag {
			case tagHashtree:
				named["AvbHashtreeDescriptor_"+d.Partition] = enc
			case tagHash:
				named["AvbHashDescriptor_"+d.Partition] = enc
			case tagChainPartition:
				named["AvbChainPartitionDescriptor_"+d.Partition] = enc
			default:
				plain.Write(enc)
			}
		}
	}
	keys := make([]string, 0, len(named))
	for k := range named {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		plain.Write(named[k])
	}
	blob, err := vbmetaBlob(plain.Bytes(), key, minor)
	if err != nil {
		return nil, err
	}
	out := make([]byte, roundUp(uint64(len(blob)), 4096))
	copy(out, blob)
	return out, nil
}

// verifyHash checks a hash descriptor: SHA-256 of the salt and the image's first image_size bytes.
func verifyHash(path string, d *HashDesc) error {
	if d.HashAlgorithm != "sha256" {
		return fmt.Errorf("%s: unsupported hash algorithm %s", d.PartitionName, d.HashAlgorithm)
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	h := sha256.New()
	h.Write(d.Salt)
	if n, err := io.CopyN(h, f, int64(d.ImageSize)); err != nil || uint64(n) != d.ImageSize {
		return fmt.Errorf("%s: shorter than its hash descriptor", d.PartitionName)
	}
	if !bytes.Equal(h.Sum(nil), d.Digest) {
		return fmt.Errorf("%s: digest mismatch", d.PartitionName)
	}
	return nil
}
