#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Plan the two-slot fresh install of a pinned Ruby USB system (layout v2).

The offline installer on the USB (migrate.py --fresh --ab-plan) must produce the
Ruby A/B disk that build-ruby-ab-image.py built and ab-qemu.py booted. That disk's
bytes come from three places, and this tool records which:

  usb     the boot images and the six logical partitions inside super are this
          USB's own pinned bytes (the A/B super holds them byte-identical);
  bundle  what the two-slot layout adds: the ESP (systemd-boot + slot A in
          openbook-bootsync's layout), super's LP metadata, vbmeta_a re-signed for
          the boot chain. A few MiB, embedded in the installer;
  zero    everything else: slot B, misc, metadata, super's free space, and
          userdata's two edges (Android formats it on first boot).

Every partition except userdata's interior is covered exactly, so nothing stale
survives on the SSD. The plan is bound to the USB pin's SHA-256. Before it is
written out, the real installer engine runs it into a blank disk of the reference
size and every byte outside userdata's interior must equal the reference image.

usage: build-ruby-ab-install.py --usb-image ruby-live.img --pin source.json --ab-image IMGDIR
                                --release NAME --variant hardware|vm --out DIR [--lpdump PATH]
Regular files only; writes nothing but DIR.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = load("migrate", "migrate.py")
MIB = m.MIB
USB_BOOT = ("boot_a", "init_boot_a", "vendor_boot_a")
LP_GEOMETRY_MAGIC, LP_HEADER_MAGIC = 0x616C4467, 0x414C5030


def lp_extents(fd, base):
    """{partition: [(byte offset in super, bytes)]} and the first logical byte, from LP metadata slot 0."""
    geo = m.read_at(fd, base + 4096, 52)
    magic, _size = struct.unpack_from("<II", geo, 0)
    m.require(magic == LP_GEOMETRY_MAGIC, "No LP geometry")
    hdr_at = base + 4096 + 2 * 4096
    hdr = m.read_at(fd, hdr_at, 256)
    magic, major, minor, hsize = struct.unpack_from("<IHHI", hdr, 0)
    m.require(magic == LP_HEADER_MAGIC and major == 10, "Unsupported LP metadata")
    tables_size = struct.unpack_from("<I", hdr, 44)[0]
    desc = struct.unpack_from("<12I", hdr, 80)
    tables = m.read_at(fd, hdr_at + hsize, tables_size)
    m.require(hashlib.sha256(tables).digest() == hdr[48:80], "LP tables checksum")

    def table(i):
        off, count, size = desc[3 * i:3 * i + 3]
        return [tables[off + k * size:off + (k + 1) * size] for k in range(count)]

    extents = [struct.unpack("<QIQI", e[:24]) for e in table(1)]
    first_logical = struct.unpack_from("<Q", table(3)[0], 0)[0] * 512
    parts = {}
    for p in table(0):
        name = p[:36].rstrip(b"\0").decode()
        _attrs, first, count, _group = struct.unpack_from("<IIII", p, 36)
        rows = []
        for sectors, kind, data, source in extents[first:first + count]:
            m.require(kind == 0 and source == 0, f"{name}: only linear extents on super")
            rows.append((data * 512, sectors * 512))
        parts[name] = rows
    return parts, first_logical


def lpdump_extents(lpdump, image):
    """Cross-check with AOSP's lpdump: {partition: [(byte offset, bytes)]}."""
    text = subprocess.check_output([str(lpdump), str(image)], text=True, stderr=subprocess.DEVNULL)
    out, name = {}, None
    for line in text.splitlines():
        n = re.match(r"\s+Name:\s+(\S+)$", line)
        if n:
            name = n.group(1)
            continue
        e = re.match(r"\s+(\d+) \.\. (\d+) linear \S+ (\d+)$", line)
        if e and name:
            out.setdefault(name, []).append((int(e.group(3)) * 512, (int(e.group(2)) - int(e.group(1)) + 1) * 512))
    return {k: v for k, v in out.items() if v}


def data_extents(fd, start, length):
    """Allocated (non-hole) byte ranges of a sparse file within [start, start+length)."""
    out, pos, end = [], start, start + length
    while pos < end:
        try:
            data = os.lseek(fd, pos, os.SEEK_DATA)
        except OSError:
            break
        if data >= end:
            break
        hole = min(os.lseek(fd, data, os.SEEK_HOLE), end)
        out.append((data, hole - data))
        pos = hole
    return out


def subtract(spans, cuts):
    """spans minus cuts; both lists of (start, length) in one coordinate space."""
    out = []
    for s, n in spans:
        pieces = [(s, s + n)]
        for c, k in cuts:
            nxt = []
            for a, b in pieces:
                if b <= c or a >= c + k:
                    nxt.append((a, b))
                else:
                    if a < c:
                        nxt.append((a, c))
                    if c + k < b:
                        nxt.append((c + k, b))
            pieces = nxt
        out += [(a, b - a) for a, b in pieces if b > a]
    return out


def plan_partition(name, p_len, ref, p_off, usb, usb_fd, bundle):
    """Writes tiling [0, p_len) of one partition, in order."""
    mapped = []  # (rel offset, bytes, usb partition, usb rel offset)
    if name in USB_BOOT:
        mapped.append((0, usb[name][1], name, 0))
    if name == "super":
        target, first = lp_extents(ref, p_off)
        source, _ = lp_extents(usb_fd, usb["super"][0])
        m.require(sorted(target) == sorted(source), "A/B super and USB super hold different partitions")
        mapped.append((0, first, None, None))  # LP metadata: bundle
        for part in sorted(target):
            t = target[part]
            s = [(o, n) for o, n in source[part]]
            m.require(sum(n for _, n in t) == sum(n for _, n in s), f"{part}: sizes differ")
            # Walk both extent lists in step; emit the overlapping pieces.
            ti = si = 0
            t_used = s_used = 0
            while ti < len(t):
                n = min(t[ti][1] - t_used, s[si][1] - s_used)
                mapped.append((t[ti][0] + t_used, n, "super", s[si][0] + s_used))
                t_used += n
                s_used += n
                if t_used == t[ti][1]:
                    ti, t_used = ti + 1, 0
                if si < len(s) and s_used == s[si][1]:
                    si, s_used = si + 1, 0
    data = [(o - p_off, n) for o, n in data_extents(ref, p_off, p_len)]
    leftover = subtract(data, [(o, n) for o, n, src, _ in mapped if src])
    writes = []
    for rel, n, src, src_off in mapped:
        if src is None:
            leftover = subtract(leftover, [(rel, n)])
            leftover.append((rel, n))
    for rel, n, src, src_off in mapped:
        if src:
            want = m.digest(ref, p_off + rel, n)
            m.require(m.digest(usb_fd, usb[src][0] + src_off, n) == want,
                      f"{name}+{rel}: USB bytes differ from the reference disk")
            writes.append(dict(partition=name, at=rel, length=n, **{"from": "usb"}, source=src,
                               offset=src_off, sha256=want))
    for rel, n in sorted(leftover):
        blob = m.read_at(ref, p_off + rel, n)
        writes.append(dict(partition=name, at=rel, length=n, **{"from": "bundle"}, offset=bundle.tell(),
                           sha256=hashlib.sha256(blob).hexdigest()))
        bundle.write(blob)
    for rel, n in subtract([(0, p_len)], [(w["at"], w["length"]) for w in writes]):
        writes.append(dict(partition=name, at=rel, length=n, **{"from": "zero"}))
    return sorted(writes, key=lambda w: w["at"])


def build(a):
    ref_dir = a.ab_image
    built = json.loads((ref_dir / "result.json").read_text())
    ref_path = ref_dir / "disk.img"
    a.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    raw_pin = a.pin.read_bytes()
    pin = json.loads(raw_pin)
    ref = os.open(ref_path, os.O_RDONLY)
    usb_fd = os.open(a.usb_image, os.O_RDONLY)
    try:
        layout = built["layout"]
        gpt = m.read_gpt(ref, names=tuple(r["name"] for r in layout))
        m.require([(r["name"], r["first_lba"] * 512, (r["last_lba"] - r["first_lba"] + 1) * 512) for r in gpt["rows"]]
                  == [(r["name"], r["offset"], r["length"]) for r in layout], "Reference GPT differs from its layout")
        header = m.read_at(ref, 512, 92)
        first_usable = struct.unpack_from("<Q", header, 40)[0]
        usb_gpt = m.check_source(usb_fd, pin)
        usb = {r["name"]: m.extent(r) for r in usb_gpt["rows"]}
        if a.lpdump:
            with tempfile.TemporaryDirectory(dir=a.out) as tmp:
                for label, fd, at, length in (("reference", ref, layout[[r["name"] for r in layout].index("super")]["offset"],
                                               4 * MIB), ("usb", usb_fd, *usb["super"])):
                    head = Path(tmp) / f"{label}-super-head.img"
                    head.write_bytes(m.read_at(fd, at, min(length, 4 * MIB)))
                    # lpdump reads only the metadata region; a truncated head is enough.
                    hfd = os.open(head, os.O_RDONLY)
                    try:
                        mine = lp_extents(hfd, 0)[0]
                    finally:
                        os.close(hfd)
                    m.require(lpdump_extents(a.lpdump, head) == {k: v for k, v in mine.items() if v},
                              f"{label} super: LP parser disagrees with lpdump")
        writes = []
        bundle_path = a.out / "ab-bundle.bin"
        with bundle_path.open("xb") as bundle:
            for r in layout[:-1]:
                writes += plan_partition(r["name"], r["length"], ref, r["offset"], usb, usb_fd, bundle)
        writes += [dict(partition="userdata", at=0, length=4 * MIB, **{"from": "zero"}),
                   dict(partition="userdata", at=-4 * MIB, length=4 * MIB, **{"from": "zero"})]
        bundle_bytes = bundle_path.stat().st_size
        with bundle_path.open("rb") as f:
            bundle_sha = hashlib.file_digest(f, "sha256").hexdigest()
        rows = [dict(name=r["name"], type=r["type"], partuuid=r["partuuid"], offset=r["first_lba"] * 512,
                     length=(r["last_lba"] - r["first_lba"] + 1) * 512) for r in gpt["rows"]]
        plan = dict(schema=m.AB_SCHEMA, release=a.release, variant=a.variant,
                    source_pin_sha256=hashlib.sha256(raw_pin).hexdigest(), source_build=pin["build"],
                    bundle_file=f"ab-bundle{'' if a.variant == 'hardware' else '-' + a.variant}.bin",
                    bundle_bytes=bundle_bytes, bundle_sha256=bundle_sha,
                    disk_guid=str(__import__("uuid").UUID(bytes_le=bytes.fromhex(gpt["disk_guid"]))),
                    first_usable_lba=first_usable, partitions=rows, writes=writes,
                    reference=dict(disk_bytes=built["disk_bytes"], efi_partuuid=built["efi_partuuid"],
                                   vbmeta_a=built["vbmeta_a"], options=built["options"], vm_entry=built["vm_entry"]),
                    bytes_from=dict(usb=sum(w["length"] for w in writes if w["from"] == "usb"),
                                    bundle=bundle_bytes,
                                    zero=sum(w["length"] for w in writes if w["from"] == "zero")))
        m.require(plan["variant"] == ("vm" if built["vm_entry"] else "hardware"), "Variant does not match the reference")
        if plan["bundle_file"] != bundle_path.name:
            bundle_path = bundle_path.rename(a.out / plan["bundle_file"])
        plan_path = a.out / ("ab-install.json" if a.variant == "hardware" else f"ab-install-{a.variant}.json")
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        prove(plan, plan_path, bundle_path, raw_pin, pin, a, ref, built)
    finally:
        os.close(ref)
        os.close(usb_fd)


def prove(plan, plan_path, bundle_path, raw_pin, pin, a, ref, built):
    """Run the real engine into a blank disk of the reference size; compare outside userdata's interior."""
    with tempfile.TemporaryDirectory(dir=a.scratch or a.out) as tmp:
        tmp = Path(tmp)
        target = tmp / "installed.img"
        src = os.open(a.usb_image, os.O_RDONLY)
        dst = os.open(target, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        bundle = os.open(bundle_path, os.O_RDONLY)
        try:
            os.ftruncate(dst, built["disk_bytes"])
            result = m.install_ab(src, dst, pin, plan, bundle, tmp, hashlib.sha256(raw_pin).hexdigest())
            size = built["disk_bytes"]
            regions = [(0, 34 * 512), (size - 33 * 512, 33 * 512)]
            for r in plan["partitions"]:
                if r["name"] == "userdata":
                    ud = next(x for x in result["layout"] if x["name"] == "userdata")
                    regions += [(ud["offset"], 4 * MIB), (ud["offset"] + ud["length"] - 4 * MIB, 4 * MIB)]
                else:
                    regions.append((r["offset"], r["length"]))
            diffs = [dict(offset=o, length=n) for o, n in regions if m.digest(dst, o, n) != m.digest(ref, o, n)]
            proof = dict(schema="openbook-ruby-ab-install-proof/1", plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                         engine="migrate.install_ab", target_bytes=size,
                         userdata_matches_reference=next(x for x in result["layout"] if x["name"] == "userdata")["length"]
                         == next(x for x in built["layout"] if x["name"] == "userdata")["length"],
                         regions_compared=len(regions), bytes_compared=sum(n for _, n in regions),
                         differing_regions=diffs, identical_outside_userdata_interior=not diffs)
        finally:
            os.close(src); os.close(dst); os.close(bundle)
    (plan_path.parent / plan_path.name.replace(".json", "-proof.json")).write_text(json.dumps(proof, indent=2) + "\n")
    print(json.dumps(dict(plan=plan_path.name, bundle_bytes=plan["bundle_bytes"], bytes_from=plan["bytes_from"],
                          writes=len(plan["writes"]), identical=proof["identical_outside_userdata_interior"],
                          userdata_matches_reference=proof["userdata_matches_reference"]), indent=2))
    m.require(proof["identical_outside_userdata_interior"] and proof["userdata_matches_reference"],
              "Installed disk differs from the reference image")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("usb-image", "pin", "ab-image", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--release", required=True)
    p.add_argument("--variant", choices=("hardware", "vm"), required=True)
    p.add_argument("--lpdump", type=Path, help="AOSP lpdump, to cross-check the LP metadata parser")
    p.add_argument("--scratch", type=Path, help="where the proof's blank disk goes (default: --out)")
    a = p.parse_args()
    os.umask(0o077)
    build(a)
