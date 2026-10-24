// SPDX-License-Identifier: Apache-2.0

// Payload (phase 4): an update_engine payload (major version 2, Virtual A/B with lz4 snapshot compression)
// that installs an adapted release into the other slot. The partitions the adaptation changed are written
// in full (2 MiB REPLACE operations, all-zero chunks as ZERO); every other partition is an identity
// SOURCE_COPY, which Virtual A/B satisfies without writing anything (the snapshot reads those blocks from
// the installed slot) and which update_engine then verifies against the installed release's hash. Every
// dynamic partition is listed, as update_engine rebuilds the new slot's partition table from exactly the
// payload's list. Signing is two-step so the private key can stay in Android Keystore: the payload is
// written with signature space reserved and its two hashes; the signatures are then inserted.
package main

import (
	"bytes"
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

const (
	payloadMinorVersion = 8          // the host's deltas (kZucchiniMinorPayloadVersion); SOURCE_COPY needs >= 2
	payloadMaxTimestamp = 4102444800 // 2100-01-01, as the host builds (anti-downgrade)
	chunkBlocks         = 512        // 2 MiB per REPLACE operation, as delta_generator's default chunk
	groupName           = "google_dynamic_partitions"
	groupSize           = 12880707584
	rsaSignatureBytes   = 512 // RSA-4096
)

var (
	dynamicPartitions = []string{"system", "system_ext", "product", "vendor", "vendor_dlkm", "system_dlkm"}
	payloadOrder      = []string{"system", "system_ext", "product", "vendor", "vendor_dlkm", "system_dlkm", "boot", "init_boot", "vendor_boot", "vbmeta"}
)

// A minimal protobuf (proto2) encoder: varints, length-delimited fields and fixed32.
type pb struct{ bytes.Buffer }

func (p *pb) varint(v uint64) {
	var b [binary.MaxVarintLen64]byte
	p.Write(b[:binary.PutUvarint(b[:], v)])
}
func (p *pb) key(field, wire int)           { p.varint(uint64(field<<3 | wire)) }
func (p *pb) u(field int, v uint64)         { p.key(field, 0); p.varint(v) }
func (p *pb) b(field int, v []byte)         { p.key(field, 2); p.varint(uint64(len(v))); p.Write(v) }
func (p *pb) s(field int, v string)         { p.b(field, []byte(v)) }
func (p *pb) msg(field int, m *pb)          { p.b(field, m.Bytes()) }
func (p *pb) f32(field int, v uint32)       { p.key(field, 5); binary.Write(p, binary.LittleEndian, v) }
func extent(start, n uint64) *pb            { e := &pb{}; e.u(1, start); e.u(2, n); return e }
func partInfo(size uint64, hash []byte) *pb { i := &pb{}; i.u(1, size); i.b(2, hash); return i }

// signatureBlob is a Signatures message holding one signature (the encoding update_engine reads).
func signatureBlob(sig []byte) []byte {
	s := &pb{}
	s.b(2, sig)
	s.f32(3, uint32(len(sig)))
	out := &pb{}
	out.msg(1, s)
	return out.Bytes()
}

type PayloadPart struct {
	Name     string `json:"name"`
	Image    string `json:"-"`             // the new image, for a written partition
	Size     uint64 `json:"size"`          // new size
	SHA256   string `json:"sha256"`        // new hash
	Copy     bool   `json:"identity_copy"` // unchanged: the installed image, copied in place
	CowBytes uint64 `json:"estimate_cow_size,omitempty"`
	Replaced uint64 `json:"replaced_blocks"`
	Zeroed   uint64 `json:"zero_blocks"`
}

type PayloadResult struct {
	Schema       string        `json:"schema"`
	Parts        []PayloadPart `json:"partitions"`
	MetadataSize uint64        `json:"metadata_size"`
	SignaturesAt uint64        `json:"payload_signature_offset"`
	MetadataHash string        `json:"metadata_hash_to_sign"`
	PayloadHash  string        `json:"payload_hash_to_sign"`
	Signed       bool          `json:"signed"`
	Properties   []string      `json:"properties,omitempty"`
}

// writePayload writes an unsigned payload (signature space reserved) and returns the two hashes to sign.
func writePayload(path string, parts []PayloadPart) (*PayloadResult, error) {
	sigBlob := signatureBlob(make([]byte, rsaSignatureBytes))
	type op struct {
		zero     bool
		start, n uint64
		data     []byte
		image    string
		offset   int64
	}
	man := &pb{}
	man.u(3, 4096)
	var dataLen uint64
	var ops [][]op
	res := &PayloadResult{Schema: "openbook-payload/1"}
	for i := range parts {
		p := &parts[i]
		var list []op
		if !p.Copy {
			f, err := os.Open(p.Image)
			if err != nil {
				return nil, err
			}
			blocks := (p.Size + 4095) / 4096
			buf := make([]byte, chunkBlocks*4096)
			for first := uint64(0); first < blocks; first += chunkBlocks {
				n := min(uint64(chunkBlocks), blocks-first)
				b := buf[:n*4096]
				clear(b)
				if _, err := f.ReadAt(b[:min(n*4096, p.Size-first*4096)], int64(first*4096)); err != nil && err != io.EOF {
					f.Close()
					return nil, err
				}
				if bytes.Count(b, []byte{0}) == len(b) {
					list = append(list, op{zero: true, start: first, n: n})
					p.Zeroed += n
				} else {
					sum := sha256.Sum256(b)
					list = append(list, op{start: first, n: n, data: sum[:], image: p.Image, offset: int64(first * 4096)})
					p.Replaced += n
					dataLen += n * 4096
				}
			}
			f.Close()
			if p.Size%4096 != 0 {
				return nil, fmt.Errorf("%s: size is not a multiple of 4096", p.Name)
			}
		}
		ops = append(ops, list)
		if contains(dynamicPartitions, p.Name) {
			// Snapshot space for this partition's writes (COW v2: data plus an operation per block); libsnapshot
			// adds 2 MiB. More than needed only reserves more of super's free space; less fails the update safely.
			p.CowBytes = p.Replaced*(4096+64) + p.Zeroed*64 + 1<<20
		}
	}
	// Second pass: the manifest, with data offsets in payload order.
	var at uint64
	for i, p := range parts {
		pu := &pb{}
		pu.s(1, p.Name)
		h, err := hex.DecodeString(p.SHA256)
		if err != nil || len(h) != 32 {
			return nil, fmt.Errorf("%s: bad hash", p.Name)
		}
		if p.Copy {
			pu.msg(6, partInfo(p.Size, h))
		}
		pu.msg(7, partInfo(p.Size, h))
		if p.Copy {
			o := &pb{}
			o.u(1, 4) // SOURCE_COPY
			o.msg(4, extent(0, p.Size/4096))
			o.msg(6, extent(0, p.Size/4096))
			pu.msg(8, o)
		}
		for _, x := range ops[i] {
			o := &pb{}
			if x.zero {
				o.u(1, 6) // ZERO
				o.msg(6, extent(x.start, x.n))
			} else {
				o.u(1, 0) // REPLACE
				o.u(2, at)
				o.u(3, x.n*4096)
				o.msg(6, extent(x.start, x.n))
				o.b(8, x.data)
				at += x.n * 4096
			}
			pu.msg(8, o)
		}
		if p.CowBytes > 0 {
			pu.u(19, p.CowBytes)
		}
		man.msg(13, pu)
	}
	man.u(4, dataLen)              // signatures_offset: after all data
	man.u(5, uint64(len(sigBlob))) // signatures_size
	man.u(12, payloadMinorVersion)
	man.u(14, payloadMaxTimestamp)
	dyn := &pb{}
	g := &pb{}
	g.s(1, groupName)
	g.u(2, groupSize)
	for _, n := range dynamicPartitions {
		g.s(3, n)
	}
	dyn.msg(1, g)
	dyn.u(2, 1) // snapshot_enabled
	dyn.u(3, 1) // vabc_enabled
	dyn.s(4, "lz4")
	dyn.u(5, 2) // COW version 2, as the host's payloads
	man.msg(15, dyn)
	manifest := man.Bytes()

	out, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o600)
	if err != nil {
		return nil, err
	}
	defer out.Close()
	hdr := make([]byte, 24)
	copy(hdr, "CrAU")
	binary.BigEndian.PutUint64(hdr[4:], 2)
	binary.BigEndian.PutUint64(hdr[12:], uint64(len(manifest)))
	binary.BigEndian.PutUint32(hdr[20:], uint32(len(sigBlob)))
	meta := append(hdr, manifest...)
	mh := sha256.Sum256(meta)
	ph := sha256.New()
	ph.Write(meta)
	w := io.MultiWriter(out, ph)
	if _, err := out.Write(meta); err != nil {
		return nil, err
	}
	if _, err := out.Write(sigBlob); err != nil { // metadata signature space (not in the payload hash)
		return nil, err
	}
	buf := make([]byte, chunkBlocks*4096)
	for i := range parts {
		var f *os.File
		for _, x := range ops[i] {
			if x.zero {
				continue
			}
			if f == nil {
				if f, err = os.Open(x.image); err != nil {
					return nil, err
				}
			}
			b := buf[:x.n*4096]
			if _, err := f.ReadAt(b, x.offset); err != nil && err != io.EOF {
				f.Close()
				return nil, err
			}
			if s := sha256.Sum256(b); !bytes.Equal(s[:], x.data) {
				f.Close()
				return nil, fmt.Errorf("%s changed while the payload was written", parts[i].Name)
			}
			if _, err := w.Write(b); err != nil {
				f.Close()
				return nil, err
			}
		}
		if f != nil {
			f.Close()
		}
	}
	if _, err := out.Write(sigBlob); err != nil { // payload signature space
		return nil, err
	}
	if err := out.Sync(); err != nil {
		return nil, err
	}
	res.Parts = parts
	res.MetadataSize = uint64(len(meta))
	res.SignaturesAt = uint64(len(meta)) + uint64(len(sigBlob)) + dataLen
	res.MetadataHash = hex.EncodeToString(mh[:])
	res.PayloadHash = hex.EncodeToString(ph.Sum(nil))
	return res, nil
}

// insertSignatures writes the two signatures into a payload's reserved space and returns the properties
// update_engine takes with it (FILE_HASH, FILE_SIZE, METADATA_HASH, METADATA_SIZE).
func insertSignatures(path string, res *PayloadResult, metaSig, payloadSig []byte) ([]string, error) {
	if len(metaSig) != rsaSignatureBytes || len(payloadSig) != rsaSignatureBytes {
		return nil, errors.New("signatures must be RSA-4096 (512 bytes)")
	}
	f, err := os.OpenFile(path, os.O_RDWR, 0)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	if _, err := f.WriteAt(signatureBlob(metaSig), int64(res.MetadataSize)); err != nil {
		return nil, err
	}
	if _, err := f.WriteAt(signatureBlob(payloadSig), int64(res.SignaturesAt)); err != nil {
		return nil, err
	}
	if err := f.Sync(); err != nil {
		return nil, err
	}
	if _, err := f.Seek(0, io.SeekStart); err != nil {
		return nil, err
	}
	h := sha256.New()
	n, err := io.Copy(h, f)
	if err != nil {
		return nil, err
	}
	meta := make([]byte, res.MetadataSize)
	if _, err := f.ReadAt(meta, 0); err != nil {
		return nil, err
	}
	mh := sha256.Sum256(meta)
	return []string{
		"FILE_HASH=" + base64.StdEncoding.EncodeToString(h.Sum(nil)),
		fmt.Sprintf("FILE_SIZE=%d", n),
		"METADATA_HASH=" + base64.StdEncoding.EncodeToString(mh[:]),
		fmt.Sprintf("METADATA_SIZE=%d", res.MetadataSize),
	}, nil
}

// signHash is what Android Keystore does with an RSA key, digest NONE and PKCS#1 padding over a
// DigestInfo-prefixed SHA-256: the signature update_engine verifies (as openssl pkeyutl -pkeyopt digest:sha256).
func signHash(key *rsa.PrivateKey, hexHash string) ([]byte, error) {
	h, err := hex.DecodeString(hexHash)
	if err != nil || len(h) != 32 {
		return nil, errors.New("bad hash")
	}
	return rsa.SignPKCS1v15(nil, key, crypto.SHA256, h)
}

// cmdPayload builds the payload for an adapted release (adapt --out) against the installed release the
// layer describes. With --key it also signs (tests, host); otherwise the caller signs the two hashes in
// payload.json and runs `payload-sign`.
func cmdPayload(fl *flag.FlagSet, args []string) error {
	adapted := fl.String("adapted", "", "adapt --out directory")
	layerIn := fl.String("layer", "", "the installed release's layer")
	out := fl.String("out", "", "new directory for payload.bin and payload.json")
	keyPath := fl.String("key", "", "sign with this RSA-4096 key (PEM) instead of returning the hashes")
	fl.Parse(args)
	if *adapted == "" || *layerIn == "" || *out == "" {
		usage()
	}
	l, err := readLayer(*layerIn)
	if err != nil {
		return err
	}
	var ar AdaptResult
	if b, err := os.ReadFile(filepath.Join(*adapted, "adapt.json")); err != nil {
		return err
	} else if err := json.Unmarshal(b, &ar); err != nil {
		return err
	}
	if !ar.Complete {
		return errors.New("the adapted release is not complete")
	}
	var parts []PayloadPart
	for _, n := range payloadOrder {
		p := PayloadPart{Name: n}
		if sum, ok := ar.Partitions[n]; ok {
			img := filepath.Join(*adapted, n+".img")
			st, err := os.Stat(img)
			if err != nil {
				return err
			}
			if got, err := fileSHA256(img); err != nil || got != sum {
				return fmt.Errorf("%s differs from the adaptation's record", n)
			}
			p.Image, p.Size, p.SHA256 = img, uint64(st.Size()), sum
			// Google's partition unchanged from the installed one: copy it in place.
			if inst := l.Release.Partitions[n]; inst == sum && l.Release.Sizes[n] == p.Size {
				p.Copy, p.Image = true, ""
			}
		} else {
			sum, size := l.Release.Partitions[n], l.Release.Sizes[n]
			if sum == "" || size == 0 {
				return fmt.Errorf("the layer does not describe the installed %s", n)
			}
			p.Copy, p.Size, p.SHA256 = true, size, sum
		}
		parts = append(parts, p)
	}
	if err := os.Mkdir(*out, 0o700); err != nil {
		return err
	}
	bin := filepath.Join(*out, "payload.bin")
	res, err := writePayload(bin, parts)
	if err != nil {
		return err
	}
	if *keyPath != "" {
		key, err := loadRSAKey(*keyPath)
		if err != nil {
			return err
		}
		ms, err := signHash(key, res.MetadataHash)
		if err != nil {
			return err
		}
		ps, err := signHash(key, res.PayloadHash)
		if err != nil {
			return err
		}
		if res.Properties, err = insertSignatures(bin, res, ms, ps); err != nil {
			return err
		}
		res.Signed = true
	}
	return writeJSON(filepath.Join(*out, "payload.json"), res)
}

// cmdPayloadSign inserts signatures made elsewhere (Android Keystore) into a payload.
func cmdPayloadSign(fl *flag.FlagSet, args []string) error {
	dir := fl.String("dir", "", "payload directory (payload.bin, payload.json)")
	metaSig := fl.String("metadata-signature", "", "file with the metadata hash's signature")
	paySig := fl.String("payload-signature", "", "file with the payload hash's signature")
	fl.Parse(args)
	var res PayloadResult
	b, err := os.ReadFile(filepath.Join(*dir, "payload.json"))
	if err != nil {
		return err
	}
	if err := json.Unmarshal(b, &res); err != nil {
		return err
	}
	if res.Signed {
		return errors.New("the payload is already signed")
	}
	ms, err := os.ReadFile(*metaSig)
	if err != nil {
		return err
	}
	ps, err := os.ReadFile(*paySig)
	if err != nil {
		return err
	}
	if res.Properties, err = insertSignatures(filepath.Join(*dir, "payload.bin"), &res, ms, ps); err != nil {
		return err
	}
	res.Signed = true
	return writeJSON(filepath.Join(*dir, "payload.json"), res)
}
