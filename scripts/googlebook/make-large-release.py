#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Test fixture: a "large" release for OTA testing, from a real one.

Copies a release's ten partition images (the six dynamic ones and the boot
chain) and grows `system` by --grow-bytes of incompressible data, the way a much
bigger system release would. The added bytes come after the filesystem, so the
system still boots unchanged, but dm-verity covers them and the OTA must carry
and write every one. They are an AES-256-CTR keystream from a fixed key:
reproducible, and as hard to compress as new content can be.

`system` gets a fresh hashtree footer in the release's format (sha256, 4 KiB
blocks, the same salt, no FEC), and vbmeta is rebuilt from all nine images' own
descriptors, signed with --key. Regular files only.

usage: make-large-release.py --release DIR --grow-bytes N --avbtool PATH --key PEM --out DIR
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

DYNAMIC = ("system", "system_ext", "product", "vendor", "vendor_dlkm", "system_dlkm")
BOOT = ("boot", "init_boot", "vendor_boot")
KEYSTREAM = dict(key="4f70656e426f6f6b206c617267652d4f544120746573742066697874757265",  # fixed: reproducible
                 iv="00000000000000000000000000000000")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def avb_info(avbtool, image):
    return subprocess.check_output([str(avbtool), "info_image", "--image", str(image)], text=True)


def partition_size_for(avbtool, data):
    """Smallest MiB-aligned partition size whose hashtree + footer leave room for DATA bytes (asks avbtool)."""
    size = (data + data // 120 + (1 << 20) + (1 << 20) - 1) // (1 << 20) * (1 << 20)
    while True:
        cap = int(subprocess.check_output([str(avbtool), "add_hashtree_footer", "--partition_size", str(size),
                                           "--calc_max_image_size", "--do_not_generate_fec"], text=True))
        if cap >= data:
            return size
        size += 1 << 20


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("release", "avbtool", "key", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--grow-bytes", type=int, required=True, help="bytes to add to system (multiple of 4096)")
    a = p.parse_args()
    if a.grow_bytes <= 0 or a.grow_bytes % 4096:
        p.error("--grow-bytes must be a positive multiple of 4096")
    a.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    for n in (*DYNAMIC, *BOOT, "vbmeta"):
        subprocess.run(["cp", "--reflink=auto", str(a.release / f"{n}.img"), str(a.out / f"{n}.img")], check=True)

    system = a.out / "system.img"
    info = avb_info(a.avbtool, system)
    salt = re.search(r"Salt:\s+([0-9a-f]+)", info).group(1)
    original = int(re.search(r"Original image size:\s+(\d+)", info).group(1))
    subprocess.run([str(a.avbtool), "erase_footer", "--image", str(system)], check=True)
    with open(system, "r+b") as f:
        f.truncate(original)
        f.seek(original)
        ks = subprocess.Popen(["openssl", "enc", "-aes-256-ctr", "-K", KEYSTREAM["key"], "-iv", KEYSTREAM["iv"],
                               "-in", "/dev/zero"], stdout=subprocess.PIPE)
        left = a.grow_bytes
        while left:
            chunk = ks.stdout.read(min(left, 8 << 20))
            f.write(chunk)
            left -= len(chunk)
        ks.kill()
        ks.wait()
    data = original + a.grow_bytes
    size = partition_size_for(a.avbtool, data)
    subprocess.run([str(a.avbtool), "add_hashtree_footer", "--image", str(system), "--partition_name", "system",
                    "--partition_size", str(size), "--hash_algorithm", "sha256", "--salt", salt,
                    "--do_not_generate_fec"], check=True)

    vbmeta = a.out / "vbmeta.img"
    cmd = [str(a.avbtool), "make_vbmeta_image", "--algorithm", "SHA256_RSA4096", "--key", str(a.key),
           "--padding_size", "4096", "--output", str(vbmeta)]
    for n in (*BOOT, *DYNAMIC):
        cmd += ["--include_descriptors_from_image", str(a.out / f"{n}.img")]
    subprocess.run(cmd, check=True)

    result = dict(schema="openbook-large-release-fixture/1", source_release=str(a.release),
                  grow_bytes=a.grow_bytes, system_original_fs_bytes=original,
                  sizes={n: (a.out / f"{n}.img").stat().st_size for n in (*DYNAMIC, *BOOT, "vbmeta")},
                  sha256={n: sha(a.out / f"{n}.img") for n in (*DYNAMIC, *BOOT, "vbmeta")},
                  keystream="AES-256-CTR, fixed key and IV (reproducible, incompressible)")
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(system_bytes=result["sizes"]["system"], grow_bytes=a.grow_bytes,
                          dynamic_total=sum(result["sizes"][n] for n in DYNAMIC))))


if __name__ == "__main__":
    main()
