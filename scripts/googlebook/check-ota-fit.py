#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Preflight: will this OTA payload apply on a Ruby A/B laptop with this layout?

Run it on every payload before it ships, small or large, OpenBook-built or a
captured Google payload being adapted. It reads the payload manifest and the
layout from plan-ruby-ab.py and checks what update_engine and libsnapshot will
need:

  partitions   every partition the payload writes exists: static ones as
               <name>_a/_b in the GPT, dynamic ones in a payload group
               (update_engine rebuilds the new slot's super metadata from exactly
               that list, so a dynamic partition left out of the payload does not
               exist in the new slot: all six installed ones must be listed)
  static fit   each new static image fits its partition
  group fit    each group's partitions fit the group size, and the groups fit
               super (UpdatePartitionMetadata / CheckSuperPartitionAllocatableSpace)
  snapshot     Virtual A/B space: the new slot's extra extents plus the
               snapshots' COW (delta_generator's estimate_cow_size, or the full
               new size when absent) must fit super's free space beside the
               installed slot; otherwise libsnapshot would need that much free
               space in /data
  esp          both slots' boot files (kernel, vendor ramdisk, ramdisk) fit the ESP
  format       major version 2, delta minor version within what the device
               supports, a known Virtual A/B compression method, not partial

The manifest is decoded from the protobuf wire format directly (the few fields
needed, numbers from update_engine's update_metadata.proto), so this has no
dependency on an AOSP checkout. Read-only.

usage: check-ota-fit.py --layout layout.json --payload payload.bin
                        [--installed-sizes sizes.json] [--out result.json]
"""
import argparse
import json
from pathlib import Path
import struct

DEVICE_DYNAMIC = ("system", "system_ext", "product", "vendor", "vendor_dlkm", "system_dlkm")
MAX_DELTA_MINOR = 9           # kZstdMinorPayloadVersion; Android 15+ update_engine
VABC_METHODS = ("none", "gz", "brotli", "lz4", "zstd")
LP_METADATA_RESERVE = 1 << 20  # LP geometry + metadata copies at the start of super (generous)


# ------------------------------------------------------------------ protobuf wire format (subset)
def fields(buf):
    """Yield (field_number, wire_type, value) for one protobuf message."""
    i = 0
    while i < len(buf):
        key, i = varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            val, i = varint(buf, i)
        elif wt == 1:
            val, i = buf[i:i + 8], i + 8
        elif wt == 2:
            n, i = varint(buf, i)
            val, i = buf[i:i + n], i + n
        elif wt == 5:
            val, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {wt}")
        yield num, wt, val


def varint(buf, i):
    out = shift = 0
    while True:
        b = buf[i]
        i += 1
        out |= (b & 0x7F) << shift
        if not b & 0x80:
            return out, i
        shift += 7


def info_size(buf):
    return next((v for n, _, v in fields(buf) if n == 1), 0)


def info_hash(buf):
    return next((v.hex() for n, _, v in fields(buf) if n == 2), None)


def parse_manifest(buf):
    m = dict(minor_version=0, partial_update=False, partitions=[], groups=[],
             vabc_enabled=False, vabc_compression=None, cow_version=None)
    for num, _, val in fields(buf):
        if num == 12:
            m["minor_version"] = val
        elif num == 16:
            m["partial_update"] = bool(val)
        elif num == 13:
            p = dict(name=None, new_size=0, old_size=0, estimate_cow_size=None, old_hash=None, new_hash=None)
            for n, _, v in fields(val):
                if n == 1:
                    p["name"] = v.decode()
                elif n == 6:
                    p["old_size"], p["old_hash"] = info_size(v), info_hash(v)
                elif n == 7:
                    p["new_size"], p["new_hash"] = info_size(v), info_hash(v)
                elif n == 19:
                    p["estimate_cow_size"] = v
            m["partitions"].append(p)
        elif num == 15:
            for n, _, v in fields(val):
                if n == 1:
                    g = dict(name=None, size=0, partition_names=[])
                    for gn, _, gv in fields(v):
                        if gn == 1:
                            g["name"] = gv.decode()
                        elif gn == 2:
                            g["size"] = gv
                        elif gn == 3:
                            g["partition_names"].append(gv.decode())
                    m["groups"].append(g)
                elif n == 3:
                    m["vabc_enabled"] = bool(v)
                elif n == 4:
                    m["vabc_compression"] = v.decode()
                elif n == 5:
                    m["cow_version"] = v
    return m


def read_payload_manifest(path):
    with open(path, "rb") as f:
        head = f.read(24)
        if head[:4] != b"CrAU":
            raise ValueError("not an update_engine payload (no CrAU magic)")
        major, manifest_size = struct.unpack(">QQ", head[4:20])
        if major != 2:
            raise ValueError(f"payload major version {major}, expected 2")
        return parse_manifest(f.read(manifest_size))


# ------------------------------------------------------------------ the checks
def check(layout, manifest, installed_sizes=None):
    rows = {r["name"]: r["length"] for r in layout["partitions"]}
    cap = layout.get("ota_capacity", {})
    super_bytes = rows["super"]
    dynamic = {n for g in manifest["groups"] for n in g["partition_names"]}
    parts = {p["name"]: p for p in manifest["partitions"]}
    problems, report = [], {}

    # partitions + static fit
    for name, p in parts.items():
        if name in dynamic:
            report[name] = dict(kind="dynamic", new_bytes=p["new_size"], cow_bytes=cow_of(p))
            continue
        slot_b = rows.get(f"{name}_b")
        ok = slot_b is not None and f"{name}_a" in rows
        fits = ok and p["new_size"] <= slot_b
        report[name] = dict(kind="static", new_bytes=p["new_size"], partition_bytes=slot_b, fits=fits)
        if not ok:
            problems.append(f"{name}: no {name}_a/{name}_b partitions on the device")
        elif not fits:
            problems.append(f"{name}: new image {p['new_size']} bytes > partition {slot_b}")
    missing_dyn = [n for n in DEVICE_DYNAMIC if n not in dynamic]
    if missing_dyn:
        problems.append("dynamic partitions missing from the payload (the new slot would lack them): "
                        + ", ".join(missing_dyn))
    for n in dynamic - set(parts):
        problems.append(f"{n}: listed in a dynamic group but not in the payload")

    # group fit
    allocatable = super_bytes - LP_METADATA_RESERVE
    for g in manifest["groups"]:
        used = sum(parts[n]["new_size"] for n in g["partition_names"] if n in parts)
        if used > g["size"]:
            problems.append(f"group {g['name']}: partitions {used} bytes > group size {g['size']}")
    if sum(g["size"] for g in manifest["groups"]) > allocatable:
        problems.append("payload groups do not fit super")

    # Virtual A/B snapshot space beside the installed slot
    new_dyn = sum(parts[n]["new_size"] for n in dynamic if n in parts)
    if installed_sizes:
        installed = sum(installed_sizes.get(n, 0) for n in DEVICE_DYNAMIC)
        basis = "installed sizes"
    elif all(parts[n]["old_size"] for n in dynamic if n in parts):
        installed = sum(parts[n]["old_size"] for n in dynamic if n in parts)
        basis = "the payload's source sizes"
    else:
        installed = cap.get("group_max_bytes", max(g["size"] for g in manifest["groups"]))
        basis = "worst case (installed slot at the group cap)"
    cow = sum(cow_of(parts[n]) for n in dynamic if n in parts)
    needed = max(0, new_dyn - installed) + cow
    free = allocatable - installed
    spill = max(0, needed - free)
    snapshot = dict(installed_dynamic_bytes=installed, installed_basis=basis, new_dynamic_bytes=new_dyn,
                    cow_bytes=cow, extra_extent_bytes=max(0, new_dyn - installed), needed_bytes=needed,
                    super_free_bytes=free, fits_in_super=spill == 0, would_need_data_bytes=spill)
    if spill:
        problems.append(f"snapshot needs {needed} bytes but super has {free} free: "
                        f"libsnapshot would need {spill} bytes free in /data")

    # ESP: both slots' boot files at the new images' sizes
    esp_need = 2 * sum(parts[n]["new_size"] for n in ("boot", "vendor_boot", "init_boot") if n in parts)
    if esp_need > rows.get("EFI", 0):
        problems.append(f"ESP: two slots of boot files need up to {esp_need} bytes > ESP {rows.get('EFI')}")

    # format
    full = all(p["old_size"] == 0 for p in parts.values())
    if not full and not 2 <= manifest["minor_version"] <= MAX_DELTA_MINOR:
        problems.append(f"delta minor version {manifest['minor_version']} outside 2..{MAX_DELTA_MINOR}")
    if full and manifest["minor_version"] != 0:
        problems.append("full payload with a non-zero minor version")
    if manifest["vabc_enabled"] and manifest["vabc_compression"] not in VABC_METHODS:
        problems.append(f"unknown Virtual A/B compression '{manifest['vabc_compression']}'")
    if manifest["partial_update"]:
        problems.append("partial update: update_engine would copy partitions not in the payload; "
                        "OpenBook payloads are complete")
    return dict(schema="openbook-ota-fit/1", kind="full" if full else "incremental",
                minor_version=manifest["minor_version"], vabc_compression=manifest["vabc_compression"],
                partitions=report, snapshot=snapshot, esp_two_slot_bytes=esp_need,
                problems=problems, fits=not problems)


def cow_of(p):
    """libsnapshot sizes the COW from estimate_cow_size; without it, assume every block is rewritten."""
    return p["estimate_cow_size"] if p["estimate_cow_size"] is not None else p["new_size"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layout", type=Path, required=True, help="layout JSON from plan-ruby-ab.py")
    ap.add_argument("--payload", type=Path, required=True)
    ap.add_argument("--installed-sizes", type=Path, help="JSON {partition: bytes} of the installed slot")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    layout = json.loads(a.layout.read_text())
    installed = json.loads(a.installed_sizes.read_text()) if a.installed_sizes else None
    result = check(layout, read_payload_manifest(a.payload), installed)
    text = json.dumps(result, indent=2) + "\n"
    if a.out:
        a.out.write_text(text)
    s = result["snapshot"]
    print(f"{result['kind']} payload, {len(result['partitions'])} partitions: "
          f"{'FITS' if result['fits'] else 'DOES NOT FIT'}; snapshot {s['needed_bytes'] / 2**30:.2f} GiB of "
          f"{s['super_free_bytes'] / 2**30:.2f} GiB free in super ({s['installed_basis']})")
    for problem in result["problems"]:
        print("  - " + problem)
    raise SystemExit(0 if result["fits"] else 1)


if __name__ == "__main__":
    main()
