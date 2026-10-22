#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage Google's stock partitions for one build, named as an OTA payload names them.

An incremental Google OTA is computed against the exact stock partitions of its
source build. This extracts every slot-A partition from Google's recovery image
for that build (boot_a -> boot.img, vbmeta_a -> vbmeta.img, pvmfw_a, ...) and the
dynamic partitions from its super (lpunpack slot 0: system_a -> system.img, ...),
so reconstruct-google-release.py can apply Google's payload on the host. Records
every SHA-256 with the build in OUT/stock.json.

Google's images are for the owner's own device: OUT is private (0700/0600) and
never committed or redistributed.

usage: stage-stock-source.py --recovery-image android-desktop_signed_recovery_image.bin --build 16452207
                             --lp-tools DIR --out DIR
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess


def gpt(path):
    with open(path, "rb") as f:
        f.seek(512)
        h = f.read(92)
        if h[:8] != b"EFI PART":
            raise ValueError("no GPT")
        lba, n, sz = struct.unpack_from("<QII", h, 72)
        f.seek(lba * 512)
        raw = f.read(n * sz)
    rows = []
    for i in range(n):
        e = raw[i * sz:(i + 1) * sz]
        if e[:16] == b"\0" * 16:
            continue
        first, last = struct.unpack_from("<QQ", e, 32)
        rows.append(dict(name=e[56:128].decode("utf-16-le").rstrip("\0"), offset=first * 512,
                         length=(last - first + 1) * 512))
    return rows


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_range(src, off, n, dst):
    with open(src, "rb") as s, open(dst, "wb") as d:
        s.seek(off)
        left = n
        while left:
            b = s.read(min(left, 8 << 20))
            d.write(b)
            left -= len(b)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--recovery-image", type=Path, required=True)
    p.add_argument("--build", required=True, help="Google build id of the recovery image, e.g. 16452207")
    p.add_argument("--lp-tools", type=Path, required=True, help="dir with lpunpack")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    a.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    rows = gpt(a.recovery_image)
    staged = {}
    for r in rows:
        if not r["name"].endswith("_a") or r["name"] == "super":
            continue
        name = r["name"][:-2]
        copy_range(a.recovery_image, r["offset"], r["length"], a.out / f"{name}.img")
        staged[name] = dict(source=f"GPT {r['name']}", bytes=r["length"])
    sup = next(r for r in rows if r["name"] == "super")
    tmp = a.out / ".super.img"
    copy_range(a.recovery_image, sup["offset"], sup["length"], tmp)
    unpack = a.out / ".logical"
    unpack.mkdir()
    subprocess.run([str(a.lp_tools / "lpunpack"), "--slot=0", str(tmp), str(unpack)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for img in sorted(unpack.glob("*_a.img")):
        name = img.name[:-len("_a.img")]
        img.rename(a.out / f"{name}.img")
        staged[name] = dict(source=f"super {img.name[:-4]}", bytes=(a.out / f"{name}.img").stat().st_size)
    shutil.rmtree(unpack)
    tmp.unlink()
    for name in staged:
        staged[name]["sha256"] = sha(a.out / f"{name}.img")
    record = dict(schema="openbook-google-stock-source/1", build=a.build, recovery_image=a.recovery_image.name,
                  recovery_image_sha256=sha(a.recovery_image), partitions=staged)
    (a.out / "stock.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(dict(build=a.build, partitions=sorted(staged)), indent=1))


if __name__ == "__main__":
    main()
