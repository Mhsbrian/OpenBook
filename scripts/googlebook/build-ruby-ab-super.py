#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the Ruby A/B `super` from reviewed slot-A logical images, matching Googlebook's geometry.

The installed laptop needs a two-slot Virtual A/B `super`: slot A holds the
system we ship, slot B is empty until the first OpenBook OTA fills it by
snapshot. The geometry (super size, metadata slot count, the VIRTUAL_AB_DEVICE
flag, the group names and their maximum size) is read from a pristine Googlebook
Ruby `super` passed as --reference-super, so nothing about the layout is guessed:
the build reproduces Google's own dynamic-partition layout, only substituting our
slot-A partition contents.

lpmake writes `super`; this tool then reads it back with lpdump and lpunpack and
checks slot A byte-for-byte against the inputs, and that slot B is an empty group.
Regular image files only; no device, no mounts.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

RUBY_PARTS = ("system", "system_ext", "product", "vendor", "vendor_dlkm", "system_dlkm")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_geometry(lpdump, reference):
    """Super size, metadata slots/size, VAB flag and group name+max from a reference super."""
    text = subprocess.check_output([str(lpdump), str(reference)], text=True, stderr=subprocess.DEVNULL)
    def one(pat):
        m = re.search(pat, text)
        if not m:
            raise ValueError(f"reference super: could not read {pat!r}")
        return m.group(1)
    # Group names are the partitions' "Group:" references; an A/B layout has one
    # base present as both <base>_a and <base>_b.
    a_bases = set(re.findall(r"Group:\s+(\S+)_a\b", text))
    b_bases = set(re.findall(r"Group:\s+(\S+)_b\b", text))
    both = sorted(a_bases & b_bases)
    if len(both) != 1:
        raise ValueError(f"expected one A/B group base present as _a and _b, found {both}")
    group = both[0]
    gmax = re.search(rf"Name:\s+{re.escape(group)}_a\s*\n\s+Maximum size:\s+(\d+)", text)
    return dict(
        super_size=int(one(r"Partition name:\s+super\b[\s\S]{0,120}?Size:\s+(\d+)")),
        metadata_size=int(one(r"Metadata max size:\s+(\d+)")),
        metadata_slots=int(one(r"Metadata slot count:\s+(\d+)")),
        virtual_ab="virtual_ab_device" in one(r"Header flags:\s+(.+)"),
        group=group,
        group_max=int(gmax.group(1)) if gmax else None,
    )


def build(a):
    geo = read_geometry(a.tools / "lpdump", a.reference_super)
    if not geo["virtual_ab"] or geo["group_max"] is None:
        raise ValueError("reference super is not a Virtual A/B super with a sized A/B group")
    images = {}
    for name in RUBY_PARTS:
        img = a.logical / f"{name}_a.img"
        if not img.is_file():
            raise ValueError(f"missing slot-A image {img}")
        images[name] = img
    a.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    super_img = a.out / "super.img"
    cmd = [str(a.tools / "lpmake"), "--metadata-size", str(geo["metadata_size"]),
           "--metadata-slots", str(geo["metadata_slots"]), "--virtual-ab",
           "--device", f"super:{geo['super_size']}",
           "--group", f"{geo['group']}_a:{geo['group_max']}",
           "--group", f"{geo['group']}_b:{geo['group_max']}",
           "--output", str(super_img)]
    sizes = {}
    for name, img in images.items():
        sizes[name] = img.stat().st_size
        cmd += ["--partition", f"{name}_a:readonly:{sizes[name]}:{geo['group']}_a",
                "--image", f"{name}_a={img}"]
    # slot B: the group exists, no partitions; update_engine fills it on the first OTA.
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)

    # Read back and verify.
    dump = subprocess.check_output([str(a.tools / "lpdump"), str(super_img)], text=True)
    checks = {
        "virtual_ab_flag": "virtual_ab_device" in dump,
        "metadata_slots": f"Metadata slot count: {geo['metadata_slots']}" in dump,
        "both_groups": f"{geo['group']}_a" in dump and f"{geo['group']}_b" in dump,
        # A partition entry has a "Group:" line; the empty _b group does not. So
        # match only _b *partitions*, not the _b group name.
        "slotB_empty": not re.search(r"Name:\s+\w+_b\s*\n\s+Group:", dump),
    }
    extract = a.out / "verify-a"
    subprocess.run([str(a.tools / "lpunpack"), "--slot=0", str(super_img), str(extract)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    readback = {}
    for name, img in images.items():
        out = extract / f"{name}_a.img"
        readback[name] = (out.is_file() and out.stat().st_size == sizes[name] and sha(out) == sha(img))
    checks["slotA_bytes_identical"] = all(readback.values())
    for f in extract.glob("*"):
        f.unlink()
    extract.rmdir()

    result = dict(schema="openbook-ruby-ab-super/1", super_sha256=sha(super_img),
                  super_bytes=super_img.stat().st_size, geometry=geo,
                  slotA=sorted(images), slotA_source_sha256={n: sha(p) for n, p in images.items()},
                  checks=checks, passed=all(checks.values()))
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(passed=result["passed"], checks=checks, super_bytes=result["super_bytes"])))
    if not result["passed"]:
        raise SystemExit("A/B super verification failed")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--logical", type=Path, required=True, help="dir with <name>_a.img for the six Ruby partitions")
    p.add_argument("--reference-super", type=Path, required=True, help="pristine Googlebook Ruby super for geometry")
    p.add_argument("--tools", type=Path, required=True, help="dir with lpmake, lpdump, lpunpack")
    p.add_argument("--out", type=Path, required=True)
    build(p.parse_args())
