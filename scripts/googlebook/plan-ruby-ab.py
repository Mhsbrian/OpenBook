#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compute the Ruby A/B whole-disk layout from a reviewed single-slot Ruby candidate.

The installed laptop runs a single-slot Ruby image (one each of boot/init_boot/
vendor_boot/vbmeta, one super, one userdata). OpenBook updates through the stock
update_engine need a second slot: update_engine writes the *other* slot's
boot/vbmeta and a Virtual A/B snapshot of super, then one reboot switches. This
tool turns the single-slot candidate into a two-slot whole-disk plan:

  EFI misc {boot,init_boot,vendor_boot,vbmeta,pvmfw,recovery,ota_recovery}_{a,b}
  metadata super(Virtual A/B, both slots) userdata(rest)

Slot A is populated from the candidate; slot B starts blank (update_engine fills
it on the first OTA). userdata is blank and gets all remaining space — this is
what frees the G14 from its fixed ~8 GiB data partition. This is the planning
and validation step only: offsets, sizes, sources and a disk-fits check. It
writes no image and touches no device.

Sizing (layout v2, "OTA-ready"). Partition sizes are fixed once installed, so they
are chosen for the largest update the laptop should ever take, not for today's
content:
  - Every A/B partition of Google's Ruby layout exists, at least at Google's size
    (read from Google's recovery image GPT), so any payload built for Google's
    partition set finds every target partition.
  - Partitions holding OpenBook content (our AMD kernel in boot, our ramdisks) get
    at least 2x headroom over today's content.
  - super is twice Google's dynamic-partition group cap: even an update that
    rewrites the whole group keeps its Virtual A/B snapshot inside super, so an
    OTA never depends on free space in /data (which reached 98% on the G14).
  - The ESP holds both slots' boot files at their partitions' maximum sizes.
validate() enforces these rules.
"""
import argparse
import json
from pathlib import Path

SECTOR = 512
MiB = 1024 * 1024
GiB = 1024 * MiB
ALIGN = MiB
GPT_RESERVE_SECTORS = 34          # protective MBR + header + 128 entries, each end
# Google's Ruby dynamic-partition group cap (google_dynamic_partitions max size in Google's super).
GOOGLE_GROUP_MAX = 12_880_707_584
SUPER_BYTES = 24 * GiB            # >= 2 x GOOGLE_GROUP_MAX: a whole-group rewrite's snapshot fits in super
EFI_BYTES = 1 * GiB               # both slots' boot files at maximum size, with margin (see validate)
# Per-slot static partitions: (bytes, Google's size, why).
SLOT_SIZES = {
    "boot":         (128 * MiB, 64 * MiB, "OpenBook AMD kernel (25.6 MiB today): 2x Google, 5x today"),
    "init_boot":    (16 * MiB,  8 * MiB,  "OpenBook generic ramdisk (2.9 MiB today): 2x Google"),
    "vendor_boot":  (64 * MiB,  32 * MiB, "Google's own vendor_boot needs 30.3 MiB: 2x Google"),
    "vbmeta":       (4 * MiB,   4 * MiB,  "Google's size"),
    "pvmfw":        (4 * MiB,   4 * MiB,  "Google's size; in Google's vbmeta, so Google payloads may carry it"),
    "recovery":     (32 * MiB,  32 * MiB, "Google's size; present so Google-shaped payloads apply"),
    "ota_recovery": (128 * MiB, 128 * MiB, "Google's size; present so Google-shaped payloads apply"),
}
SLOTTED = tuple(SLOT_SIZES)
SINGLE_SIZES = {"misc": 4 * MiB, "metadata": 64 * MiB}  # Google's sizes
# Filled from the candidate on slot A; the others start blank on both slots.
FROM_CANDIDATE = ("boot", "init_boot", "vendor_boot", "vbmeta")


def align_up(value, alignment=ALIGN):
    return (value + alignment - 1) // alignment * alignment


def candidate_sizes(manifest):
    rows = {r["name"]: (r["last_lba"] - r["first_lba"] + 1) * SECTOR for r in manifest["gpt"]}
    return rows


def plan(manifest, disk_bytes):
    if disk_bytes % SECTOR:
        raise ValueError("Disk size must be a whole number of 512-byte sectors")
    src = candidate_sizes(manifest)
    # Order on disk. Every slotted partition appears as _a and _b at the same size.
    order = ["EFI", "misc"]
    sizes = {"EFI": EFI_BYTES, "misc": SINGLE_SIZES["misc"]}
    sources = {}
    for base, (size, _google, _why) in SLOT_SIZES.items():
        a = f"{base}_a"
        if base in FROM_CANDIDATE:
            if a not in src:
                raise ValueError(f"Candidate is missing {a}")
            if src[a] > size:
                raise ValueError(f"Candidate {a} ({src[a]} bytes) is larger than the planned {size}")
        for slot in ("a", "b"):
            name = f"{base}_{slot}"
            order.append(name)
            sizes[name] = size
            sources[name] = "candidate" if slot == "a" and base in FROM_CANDIDATE else "blank"
    order += ["metadata", "super", "userdata"]
    sizes["metadata"] = SINGLE_SIZES["metadata"]
    sizes["super"] = SUPER_BYTES
    if SUPER_BYTES < src["super"]:
        raise ValueError("The planned super is smaller than the candidate's super content")
    sources.update(EFI="candidate", super="candidate", misc="blank", metadata="blank")

    first_usable = GPT_RESERVE_SECTORS * SECTOR
    backup_gpt = GPT_RESERVE_SECTORS * SECTOR
    fixed = align_up(first_usable)
    rows, offset = [], fixed
    for name in order[:-1]:  # everything but userdata
        length = align_up(sizes[name])
        rows.append(dict(name=name, offset=offset, length=length,
                         slot=name[-1] if name.endswith(("_a", "_b")) else None, source=sources[name]))
        offset += length
    data_start = offset
    data_end = (disk_bytes - backup_gpt) // ALIGN * ALIGN
    userdata = data_end - data_start
    if userdata < 8 * GiB:
        raise ValueError(f"Disk too small: userdata would be {userdata} bytes (< 8 GiB) after the A/B system")
    rows.append(dict(name="userdata", offset=data_start, length=userdata, slot=None, source="blank"))

    fixed_total = sum(r["length"] for r in rows if r["name"] != "userdata")
    return dict(
        schema="openbook-ruby-ab-layout/2",
        source_image_sha256=manifest["image_sha256"],
        disk_bytes=disk_bytes,
        a_slot_source="the reviewed single-slot candidate",
        b_slot="blank; update_engine writes it on the first OpenBook OTA, then one reboot switches",
        userdata="blank; formatted on first boot; takes all remaining space",
        fixed_system_bytes=fixed_total,
        userdata_bytes=userdata,
        partitions=rows,
        ota_capacity=dict(
            super_bytes=SUPER_BYTES, group_max_bytes=GOOGLE_GROUP_MAX,
            worst_case_update_bytes=2 * GOOGLE_GROUP_MAX,
            slotted={b: dict(bytes=v[0], google_bytes=v[1], why=v[2]) for b, v in SLOT_SIZES.items()},
            esp_bytes=EFI_BYTES, esp_two_slot_max_bytes=2 * esp_slot_max()),
        notes=[
            "vbmeta_a is rebuilt to cover the boot chain (boot, init_boot, vendor_boot) and the six "
            "super partitions, so openbook-bootsync verifies each slot as on the AOSP track.",
            "super is Virtual A/B with room for a whole-group update's snapshot; /data is never needed for it.",
        ],
    )


def esp_slot_max():
    """One slot's ESP files at most: kernel (<= boot), vendor ramdisk (<= vendor_boot), ramdisk (<= init_boot)."""
    return sum(SLOT_SIZES[b][0] for b in ("boot", "vendor_boot", "init_boot")) + MiB  # + bootconfig


def validate(layout):
    rows = layout["partitions"]
    # Contiguous, aligned, within the disk, userdata last.
    expect = GPT_RESERVE_SECTORS * SECTOR
    expect = align_up(expect)
    for r in rows:
        if r["offset"] != expect:
            raise ValueError(f"{r['name']}: gap or overlap at {r['offset']} (expected {expect})")
        if r["offset"] % ALIGN or r["length"] % ALIGN:
            raise ValueError(f"{r['name']}: not MiB-aligned")
        expect = r["offset"] + r["length"]
    if rows[-1]["name"] != "userdata":
        raise ValueError("userdata must be the last partition")
    if expect > layout["disk_bytes"] - GPT_RESERVE_SECTORS * SECTOR:
        raise ValueError("Layout overruns the disk's backup GPT reserve")
    names = [r["name"] for r in rows]
    size = dict((r["name"], r["length"]) for r in rows)
    # OTA capacity rules (layout v2).
    if size["super"] < 2 * GOOGLE_GROUP_MAX:
        raise ValueError("super must hold a whole-group update's snapshot (2 x the group cap)")
    if size["EFI"] < 2 * esp_slot_max():
        raise ValueError("The ESP cannot hold both slots' boot files at their maximum sizes")
    for base, (planned, google, _why) in SLOT_SIZES.items():
        if f"{base}_a" in size and size[f"{base}_a"] < google:
            raise ValueError(f"{base} is smaller than Google's {google} bytes")
    for base in SLOTTED:
        if f"{base}_a" not in names or f"{base}_b" not in names:
            raise ValueError(f"Missing a slot for {base}")
        if size[f"{base}_a"] != size[f"{base}_b"]:
            raise ValueError(f"{base} slots differ in size")
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", type=Path, required=True, help="dir with manifest.json of the single-slot Ruby candidate")
    p.add_argument("--disk-bytes", type=int, required=True, help="target SSD size in bytes")
    p.add_argument("--out", type=Path, help="write the layout JSON here")
    a = p.parse_args()
    manifest = json.loads((a.candidate / "manifest.json").read_text())
    layout = plan(manifest, a.disk_bytes)
    validate(layout)
    text = json.dumps(layout, indent=2) + "\n"
    if a.out:
        a.out.write_text(text)
    gib = layout["userdata_bytes"] / GiB
    print(f"Ruby A/B layout for {a.disk_bytes/GiB:.0f} GiB disk: {len(layout['partitions'])} partitions, "
          f"userdata {gib:.1f} GiB (was ~8.0 GiB single-slot). Validated.")


if __name__ == "__main__":
    main()
