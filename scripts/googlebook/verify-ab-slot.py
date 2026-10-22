#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that one slot of a Ruby A/B disk image holds exactly a release's partition images.

Reads the slot's logical partitions out of the disk's `super` through that
slot's metadata (lpunpack --slot), and the slot's static boot partitions at
their GPT offsets, and compares each with the release's <name>.img byte for
byte. After an OTA has merged, slot B must equal the release it was updated
to. Read-only on the disk image; the extracted copies are removed.

usage: verify-ab-slot.py --disk DISK --layout IMAGE_DIR/result.json --slot b
                         --release DIR --lp-tools DIR --work DIR [--out result.json]
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

DYNAMIC = ("system", "system_ext", "product", "vendor", "vendor_dlkm", "system_dlkm")
STATIC = ("boot", "init_boot", "vendor_boot", "vbmeta")


def sha_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("disk", "layout", "release", "lp-tools", "work"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--slot", choices=("a", "b"), required=True)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    layout = {r["name"]: r for r in json.loads(a.layout.read_text())["layout"]}
    a.work.mkdir(mode=0o700, parents=True, exist_ok=False)
    try:
        sup = a.work / "super.img"
        subprocess.run(["dd", f"if={a.disk}", f"of={sup}", "bs=4M", "iflag=skip_bytes,count_bytes",
                        f"skip={layout['super']['offset']}", f"count={layout['super']['length']}",
                        "conv=sparse", "status=none"], check=True)
        unpacked = a.work / "logical"
        unpacked.mkdir()
        index = "ab".index(a.slot)
        dump = subprocess.run([str(a.lp_tools / "lpdump"), f"--slot={index}", str(sup)],
                              capture_output=True, text=True, check=True).stdout
        cow = sorted({line.split()[-1] for line in dump.splitlines()
                      if line.strip().startswith("Name:") and line.strip().endswith("-cow")})
        subprocess.run([str(a.lp_tools / "lpunpack"), f"--slot={index}", str(sup), str(unpacked)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        results = {}
        for n in DYNAMIC:
            got = unpacked / f"{n}_{a.slot}.img"
            results[n] = dict(present=got.is_file(), equal=got.is_file() and
                              sha_file(got) == sha_file(a.release / f"{n}.img"))
        for n in STATIC:
            want = (a.release / f"{n}.img").read_bytes()
            with open(a.disk, "rb") as f:
                f.seek(layout[f"{n}_{a.slot}"]["offset"])
                results[n] = dict(present=True, equal=f.read(len(want)) == want)
    finally:
        shutil.rmtree(a.work, ignore_errors=True)
    # COW partitions stay listed after a merge: libsnapshot reclaims them only when the next update
    # starts (SnapshotManager::CreateUpdateSnapshots -> UnmapAndDeleteCowPartition). Content decides.
    out = dict(schema="openbook-ab-slot-verify/1", slot=a.slot, partitions=results,
               cow_partitions_listed=cow, passed=all(r["equal"] for r in results.values()))
    text = json.dumps(out, indent=2) + "\n"
    if a.out:
        a.out.write_text(text)
    print(text, end="")
    raise SystemExit(0 if out["passed"] else 1)


if __name__ == "__main__":
    main()
