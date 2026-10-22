#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compute the Ruby A/B whole-disk layout from a reviewed single-slot Ruby candidate.

The installed laptop runs a single-slot Ruby image (one each of boot/init_boot/
vendor_boot/vbmeta, one super, one userdata). OpenBook updates through the stock
update_engine need a second slot: update_engine writes the *other* slot's
boot/vbmeta and a Virtual A/B snapshot of super, then one reboot switches. This
tool turns the single-slot candidate into a two-slot whole-disk plan:

  EFI(512M) misc boot_a boot_b init_boot_a init_boot_b vendor_boot_a vendor_boot_b
  vbmeta_a vbmeta_b metadata super(VAB, both slots) userdata(rest)

Slot A is populated from the candidate; slot B starts blank (update_engine fills
it on the first OTA). userdata is blank and gets all remaining space — this is
what frees the G14 from its fixed ~8 GiB data partition. This is the planning
and validation step only: offsets, sizes, sources and a disk-fits check. It
writes no image and touches no device. The layout matches docs/installer.md 3.2,
anchored to the candidate's real partition sizes.
"""
import argparse
import json
from pathlib import Path

SECTOR = 512
MiB = 1024 * 1024
GiB = 1024 * MiB
ALIGN = MiB
GPT_RESERVE_SECTORS = 34          # protective MBR + header + 128 entries, each end
EFI_BYTES = 512 * MiB             # two slots of ESP boot artifacts + headroom
SUPER_BYTES = 12 * GiB            # Virtual A/B, same size class as Googlebook's
# Per-slot static partitions; sizes are asserted against the candidate.
SLOTTED = ("boot", "init_boot", "vendor_boot", "vbmeta")
SINGLE = ("EFI", "misc", "metadata")


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
    sizes = {"EFI": EFI_BYTES, "misc": src["misc"]}
    for base in ("boot", "init_boot", "vendor_boot", "vbmeta"):
        a = f"{base}_a"
        if a not in src:
            raise ValueError(f"Candidate is missing {a}")
        for slot in ("a", "b"):
            name = f"{base}_{slot}"
            order.append(name)
            sizes[name] = src[a]
    order += ["metadata", "super", "userdata"]
    sizes["metadata"] = src["metadata"]
    sizes["super"] = SUPER_BYTES
    if SUPER_BYTES < src["super"]:
        raise ValueError("12 GiB super is smaller than the candidate's super content")

    first_usable = GPT_RESERVE_SECTORS * SECTOR
    backup_gpt = GPT_RESERVE_SECTORS * SECTOR
    fixed = align_up(first_usable)
    rows, offset = [], fixed
    for name in order[:-1]:  # everything but userdata
        length = align_up(sizes[name])
        rows.append(dict(name=name, offset=offset, length=length,
                         slot=name[-1] if name.endswith(("_a", "_b")) else None,
                         source="candidate" if name.endswith("_a") or name in ("EFI", "super") else "blank"))
        offset += length
    data_start = offset
    data_end = (disk_bytes - backup_gpt) // ALIGN * ALIGN
    userdata = data_end - data_start
    if userdata < 8 * GiB:
        raise ValueError(f"Disk too small: userdata would be {userdata} bytes (< 8 GiB) after the A/B system")
    rows.append(dict(name="userdata", offset=data_start, length=userdata, slot=None, source="blank"))

    fixed_total = sum(r["length"] for r in rows if r["name"] != "userdata")
    return dict(
        schema="openbook-ruby-ab-layout/1",
        source_image_sha256=manifest["image_sha256"],
        disk_bytes=disk_bytes,
        a_slot_source="the reviewed single-slot candidate",
        b_slot="blank; update_engine writes it on the first OpenBook OTA, then one reboot switches",
        userdata="blank; formatted on first boot; takes all remaining space",
        fixed_system_bytes=fixed_total,
        userdata_bytes=userdata,
        partitions=rows,
        notes=[
            "boot/init_boot/vendor_boot are NOT covered by Ruby's vbmeta; the ESP/loader verifies them, "
            "so the A/B boot chain and bootsync need a Ruby verification mode (tracked, not in this plan).",
            "super is Virtual A/B: one copy, the OTA's snapshot lives in its free space and in /data.",
        ],
    )


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
    for base in SLOTTED:
        if f"{base}_a" not in names or f"{base}_b" not in names:
            raise ValueError(f"Missing a slot for {base}")
        if dict((r["name"], r["length"]) for r in rows)[f"{base}_a"] != \
           dict((r["name"], r["length"]) for r in rows)[f"{base}_b"]:
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
