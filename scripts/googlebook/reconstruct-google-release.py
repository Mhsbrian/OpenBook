#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rebuild Google's new partition images on the host from a Google OTA payload.

A full payload rebuilds every partition by itself; an incremental one is applied
to the exact stock partitions of its source build (stage-stock-source.py). This
runs AOSP's ota_extractor (update_engine's own payload consumer, so every
operation type Google uses is handled) and then checks each output against the
SHA-256 that Google's signed manifest declares for it (new_partition_info.hash).
A reconstruction that does not match is refused.

Output: OUT/<partition>.img for every partition in the payload, and
OUT/result.json. Private (0700/0600): Google's images are for the owner's own
device only.

usage: reconstruct-google-release.py --payload payload.bin --out DIR [--stock DIR]
                                     --extractor otatools/bin/ota_extractor
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fit", HERE / "check-ota-fit.py")
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)


def sha_prefix(path, n):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        left = n
        while left:
            b = f.read(min(left, 8 << 20))
            if not b:
                return None
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--payload", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--stock", type=Path, help="source build's stock images, for an incremental payload")
    p.add_argument("--extractor", type=Path, required=True)
    a = p.parse_args()
    os.umask(0o077)
    m = fit.read_payload_manifest(a.payload)
    incremental = any(x["old_size"] for x in m["partitions"])
    if incremental and not a.stock:
        sys.exit("an incremental payload needs --stock (the source build's images)")
    a.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    # Check the source first: a mismatch means the stock images are not the payload's source build.
    if incremental:
        bad = [x["name"] for x in m["partitions"] if x["old_size"] and
               sha_prefix(a.stock / f"{x['name']}.img", x["old_size"]) != x["old_hash"]]
        if bad:
            sys.exit(f"stock images do not match the payload's source build: {', '.join(bad)}")
    env = dict(os.environ, LD_LIBRARY_PATH=f"{a.extractor.parent.parent / 'lib64'}:{os.environ.get('LD_LIBRARY_PATH', '')}")
    cmd = [str(a.extractor), f"--payload={a.payload}", f"--output_dir={a.out}"]
    if incremental:
        cmd.append(f"--input_dir={a.stock}")
    log = a.out / "extract.log"
    with open(log, "w") as f:
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=env).returncode
    rows = {}
    for x in m["partitions"]:
        img = a.out / f"{x['name']}.img"
        got = sha_prefix(img, x["new_size"]) if img.is_file() else None
        rows[x["name"]] = dict(new_size=x["new_size"], matches_google_manifest=got == x["new_hash"], sha256=got)
    result = dict(schema="openbook-google-reconstruction/1", kind="incremental" if incremental else "full",
                  extractor_rc=rc, partitions=rows, passed=rc == 0 and all(r["matches_google_manifest"] for r in rows.values()))
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(kind=result["kind"], passed=result["passed"],
                          partitions={n: r["matches_google_manifest"] for n, r in rows.items()}), indent=1))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
