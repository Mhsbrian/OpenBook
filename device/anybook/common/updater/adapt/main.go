// SPDX-License-Identifier: Apache-2.0

// openbook-adapt: phase 3 of the on-laptop OpenBook updater (ANAL-229). It turns Google's new Googlebook
// release into the G14's OpenBook release on the laptop itself: reconstruct Google's partitions from the
// recovery zip the updater downloaded, re-apply the OpenBook layer to Google's new system (fail-closed),
// rebuild and verify it, and sign the release's vbmeta. One static binary with no dependencies; the
// laptop's own mkfs.erofs and fsck.erofs do the filesystem work. The same binary runs on the build host,
// where its results are compared with the host's own rebase.
//
// usage:
//
//	openbook-adapt reconstruct --release recovery.zip --out DIR [--google-key SHA256]
//	openbook-adapt layer --old-system OLD.img --ours-system OURS.img --old-build ID --release-dir DIR --out DIR
//	openbook-adapt adapt --layer DIR --new DIR --ours-root / --release-dir DIR --key AVB_KEY.pem --work DIR --out DIR
//	openbook-adapt payload --adapted DIR --layer DIR --out DIR [--key RSA_KEY.pem]
//	openbook-adapt payload-sign --dir DIR --metadata-signature FILE --payload-signature FILE
//	openbook-adapt inventory IMAGE
//	openbook-adapt hashtree-footer --image IMG --partition-size N --name NAME --salt HEX
//	openbook-adapt vbmeta --key AVB_KEY.pem --out vbmeta.img IMAGE...
//	openbook-adapt verify-vbmeta --image vbmeta.img [--images DIR]
//
// Exit status: 0 done, 1 failed (nothing usable written), 2 usage, 8 held: Google changed something OpenBook
// adapts, so this release needs an OpenBook update (the result says what).
package main

import (
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// errHeld marks a release this laptop must not adapt by itself.
type errHeld struct{ reason string }

func (e errHeld) Error() string { return "held: " + e.reason }

func held(format string, args ...any) error { return errHeld{fmt.Sprintf(format, args...)} }

func usage() {
	fmt.Fprintln(os.Stderr, "usage: openbook-adapt reconstruct|layer|adapt|inventory|hashtree-footer|vbmeta|verify-vbmeta ...")
	os.Exit(2)
}

func writeJSON(path string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(b, '\n'), 0o600)
}

func main() {
	if len(os.Args) < 2 {
		usage()
	}
	cmd, args := os.Args[1], os.Args[2:]
	fl := flag.NewFlagSet(cmd, flag.ExitOnError)
	var err error
	switch cmd {
	case "inventory":
		fl.Parse(args)
		if fl.NArg() != 1 {
			usage()
		}
		var rows []string
		if rows, err = inventory(fl.Arg(0)); err == nil {
			fmt.Println(strings.Join(rows, "\n"))
		}
	case "reconstruct":
		release := fl.String("release", "", "recovery zip or disk image")
		out := fl.String("out", "", "new directory for the partitions")
		key := fl.String("google-key", "", "expected SHA-256 of Google's AVB public key")
		fl.Parse(args)
		if *release == "" || *out == "" {
			usage()
		}
		var res *ReconstructResult
		if res, err = reconstruct(*release, *out, []string{"system", "system_ext", "product"}, nil, *key); err == nil {
			err = writeJSON(filepath.Join(*out, "reconstruct.json"), res)
		}
	case "hashtree-footer":
		image := fl.String("image", "", "")
		size := fl.Uint64("partition-size", 0, "")
		name := fl.String("name", "", "")
		salt := fl.String("salt", "", "")
		fl.Parse(args)
		var s []byte
		if s, err = hex.DecodeString(*salt); err == nil {
			_, err = addHashtreeFooter(*image, *size, *name, s)
		}
	case "vbmeta":
		keyPath := fl.String("key", "", "")
		out := fl.String("out", "", "")
		fl.Parse(args)
		err = cmdVBMeta(*keyPath, *out, fl.Args())
	case "verify-vbmeta":
		image := fl.String("image", "", "")
		images := fl.String("images", "", "directory with the partition images to check against it")
		fl.Parse(args)
		err = cmdVerifyVBMeta(*image, *images)
	case "derive-app-domain": // diagnostics: the derived statements for a platform policy
		fl.Parse(args)
		var b []byte
		if b, err = os.ReadFile(fl.Arg(0)); err == nil {
			var st []string
			if st, err = appDomainStatements(string(b)); err == nil {
				fmt.Println(strings.Join(st, "\n"))
			}
		}
	case "layer":
		err = cmdLayer(fl, args)
	case "payload":
		err = cmdPayload(fl, args)
	case "payload-sign":
		err = cmdPayloadSign(fl, args)
	case "adapt":
		err = cmdAdapt(fl, args)
	default:
		usage()
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "openbook-adapt:", err)
		var h errHeld
		if errors.As(err, &h) {
			os.Exit(8)
		}
		os.Exit(1)
	}
}

func cmdVBMeta(keyPath, out string, images []string) error {
	key, err := loadRSAKey(keyPath)
	if err != nil {
		return err
	}
	var sources []*VBMeta
	for _, img := range images {
		v, _, err := readImageVBMeta(img)
		if err != nil {
			return err
		}
		sources = append(sources, v)
	}
	blob, err := makeVBMeta(sources, key)
	if err != nil {
		return err
	}
	return os.WriteFile(out, blob, 0o600)
}

// cmdVerifyVBMeta checks a vbmeta's signature and, with --images, every hash and hash-tree descriptor
// against DIR/<partition>.img.
func cmdVerifyVBMeta(image, dir string) error {
	v, _, err := readImageVBMeta(image)
	if err != nil {
		return err
	}
	if err := v.Verify(); err != nil {
		return err
	}
	for _, d := range v.Descriptors {
		if dir == "" {
			break
		}
		img := filepath.Join(dir, d.Partition+".img")
		switch {
		case d.Hashtree != nil:
			if err := verifyHashtree(img, d.Hashtree); err != nil {
				return err
			}
		case d.Hash != nil:
			if err := verifyHash(img, d.Hash); err != nil {
				return err
			}
		default:
			continue
		}
		fmt.Println("verified", d.Partition)
	}
	return nil
}

func parseUint(s string) (uint64, error) { return strconv.ParseUint(s, 10, 64) }
