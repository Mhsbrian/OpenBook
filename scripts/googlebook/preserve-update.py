#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare a PRIVATE updated clone of an offline Ruby live USB backup.

Regular files only; no physical device writes. Limited to vendor-only updates
with identical framework, kernel, boot partitions and layout, or one explicitly
reviewed system/vendor_dlkm image change (--allow-logical), whose output stays
incomplete until the USB installer is re-pinned. Requires a verified backup and
a separately reviewed vendor/security compatibility check.
Single slot: this is not an atomic OTA or automatic rollback mechanism.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import uuid
import zlib

spec = importlib.util.spec_from_file_location("live", Path(__file__).with_name("live-image.py"))
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)
h = live.h
WRITABLE = ("EFI", "super", "vbmeta_a")
BOOT = ("boot_a", "init_boot_a", "vendor_boot_a")


def regular(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError(f"Requires a regular file, not a device or symlink: {path.name}")
    return path.resolve(strict=True)


def digest_range(path, offset, length):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        f.seek(offset)
        while length:
            data = f.read(min(length, 4 << 20))
            if not data:
                raise ValueError("Truncated range")
            digest.update(data)
            length -= len(data)
    return digest.hexdigest()


def read_gpt(path):
    """Accept only the fixed 512-byte, 128-entry layout emitted by live-image."""
    size = path.stat().st_size
    if size % 512:
        raise ValueError("Unaligned image size")
    with path.open("rb") as f:
        mbr = f.read(512)
        if mbr[510:] != b"\x55\xaa" or mbr[450] != 0xee:
            raise ValueError("Missing protective MBR")

        def header(lba, alternate, entries_lba):
            f.seek(lba * 512); raw = f.read(512)
            if raw[:8] != b"EFI PART" or struct.unpack_from("<II", raw, 8) != (0x10000, 92):
                raise ValueError("Unsupported GPT header")
            crc = struct.unpack_from("<I", raw, 16)[0]
            if zlib.crc32(raw[:16] + bytes(4) + raw[20:92]) != crc:
                raise ValueError("GPT header CRC mismatch")
            if struct.unpack_from("<QQ", raw, 24) != (lba, alternate):
                raise ValueError("GPT header location mismatch")
            table_lba, count, width, table_crc = struct.unpack_from("<QIII", raw, 72)
            if (table_lba, count, width) != (entries_lba, 128, 128):
                raise ValueError("Unexpected GPT table geometry")
            f.seek(table_lba * 512); table = f.read(count * width)
            if len(table) != count * width or zlib.crc32(table) != table_crc:
                raise ValueError("GPT entries CRC mismatch")
            return raw, table

        end = size // 512 - 1
        primary, table = header(1, end, 2)
        backup, other = header(end, 1, end - 32)
        if primary[40:72] != backup[40:72] or table != other:
            raise ValueError("GPT copies disagree")
        first, last = struct.unpack_from("<QQ", primary, 40)
        if not 34 <= first <= last < end - 32:
            raise ValueError("Invalid GPT usable extent")
        rows, previous = [], first - 1
        for i in range(128):
            entry = table[i * 128:(i + 1) * 128]
            if entry == bytes(128):
                continue
            start, stop, attrs = struct.unpack_from("<QQQ", entry, 32)
            if not previous < start <= stop <= last or attrs != 0:
                raise ValueError("Overlapping or unsupported GPT partition")
            previous = stop
            rows.append(dict(name=entry[56:128].decode("utf-16-le").rstrip("\0"),
                             first_lba=start, last_lba=stop,
                             partuuid=str(uuid.UUID(bytes_le=entry[16:32]))))
        if tuple(r["name"] for r in rows) != ("EFI", *live.NAMES):
            raise ValueError("Unexpected partition set/order")
        if len({r["partuuid"] for r in rows}) != len(rows):
            raise ValueError("Duplicate partition UUID")
        return rows


def extent(row):
    return row["first_lba"] * 512, (row["last_lba"] - row["first_lba"] + 1) * 512


def verify_manifest(manifest, table, size):
    if (manifest.get("schema") != "openbook-ruby-live-research/1"
            or manifest.get("module_variant") != "bm" or manifest.get("installable") is not False
            or manifest.get("gpt") != table or manifest.get("image_bytes") != size):
        raise ValueError("Live manifest/geometry mismatch")


# Logical images that may change only through an explicit --allow-logical review.
# Their outputs stay incomplete until the USB's installer is re-pinned.
# system: RB-20261021-02 replaces only native-bridge files (ANAL-234 Digitalis);
# APKs, framework, ART, policy and data formats are unchanged.
REVIEWABLE_LOGICAL = ("system", "vendor_dlkm")


def compatible(old, new, allow_logical=()):
    if allow_logical:
        if not set(allow_logical) <= set(REVIEWABLE_LOGICAL):
            raise ValueError("Only system or vendor_dlkm can be reviewed with --allow-logical")
        changed = sorted(n for n, v in new["logical_sha256"].items() if old["logical_sha256"].get(n) != v)
        if changed != sorted(set(allow_logical)):
            raise ValueError(f"Reviewed logical changes differ: {changed}")
        new = copy.deepcopy(new)
        for name in allow_logical:
            new["logical_sha256"][name] = old["logical_sha256"][name]
    if [(r["name"], *extent(r)) for r in old["gpt"]] != [(r["name"], *extent(r)) for r in new["gpt"]]:
        raise ValueError("Partition layout changed")
    for key in ("kernel_sha256", "vendor_cmdline"):
        if old[key] != new[key]:
            raise ValueError(f"Unsupported change: {key}")
    if set(old["logical_sha256"]) != set(new["logical_sha256"]):
        raise ValueError("Logical partition set changed")
    for name, digest in old["logical_sha256"].items():
        if name != "vendor" and new["logical_sha256"][name] != digest:
            raise ValueError(f"Unsupported framework/module change: {name}")
    for name in BOOT:
        if old["payload_readback"][name] != new["payload_readback"][name]:
            raise ValueError(f"Unsupported boot change: {name}")
    if set(old["entries"]) != {"live", "logs", "safe-logs", "serial", "serial-logs"} or set(old["entries"]) != set(new["entries"]):
        raise ValueError("Boot entry set changed")
    for mode, before in old["entries"].items():
        after = new["entries"][mode]
        for key in ("androidboot.selinux", "androidboot.veritymode"):
            if before.get(key) != "enforcing" or after.get(key) != "enforcing":
                raise ValueError("Requires enforcing boot")
        allowed = {"androidboot.boot_part_uuid", "androidboot.vbmeta.digest", "androidboot.vbmeta.size"}
        if {k: v for k, v in before.items() if k not in allowed} != {k: v for k, v in after.items() if k not in allowed}:
            raise ValueError("Boot identity/security parameters changed")


def verify_vbmeta_bootconfig(image, table, entries):
    """Check this hybrid's single-root AVB digest/size, not signing authority."""
    if not entries:
        raise ValueError("Missing bootconfig entries")
    row = next(r for r in table if r["name"] == "vbmeta_a")
    offset, capacity = extent(row)
    with image.open("rb") as f:
        f.seek(offset); header = f.read(256)
        if len(header) != 256 or header[:4] != b"AVB0":
            raise ValueError("Unsupported vbmeta header")
        size = 256 + sum(struct.unpack_from(">QQ", header, 12))
        if not 256 <= size <= capacity:
            raise ValueError("Invalid vbmeta size")
        f.seek(offset); data = f.read(size)
    if len(data) != size:
        raise ValueError("Truncated vbmeta")
    digest = hashlib.sha256(data).hexdigest()
    for params in entries.values():
        if params.get("androidboot.vbmeta.size") != str(size):
            raise ValueError("Bootconfig vbmeta size differs from image")
        if params.get("androidboot.vbmeta.hash_alg") != "sha256" or params.get("androidboot.vbmeta.digest") != digest:
            raise ValueError("Bootconfig vbmeta digest differs from image")


def split_initrd(data):
    if len(data) < 20 or not data.endswith(h.bc.MAGIC):
        raise ValueError("Missing bootconfig trailer")
    size = struct.unpack_from("<I", data, len(data) - 20)[0]
    if not 0 < size <= min(32768, len(data) - 20):
        raise ValueError("Invalid bootconfig length")
    return data[:-size - 20], h.bc.parse_text(h.bc.read_trailer(data))


def tree_hashes(root):
    return {str(p.relative_to(root)): h.audit.sha(p) for p in root.rglob("*") if p.is_file()}


def protected_ranges(table, size):
    """Hash everything outside writable partitions, including GPT and padding."""
    cursor = 0
    for row in sorted((r for r in table if r["name"] in WRITABLE), key=lambda r: r["first_lba"]):
        offset, length = extent(row)
        if offset > cursor:
            yield cursor, offset - cursor
        cursor = offset + length
    if cursor < size:
        yield cursor, size - cursor


def prepare(snapshot, snapshot_sha, base, candidate, out, *, experiment_validator=None, allow_logical=()):
    snapshot = regular(snapshot)
    image = regular(candidate / "ruby-live.img")
    old = json.loads(regular(base).read_text())
    new = json.loads(regular(candidate / "manifest.json").read_text())
    if h.audit.sha(snapshot) != snapshot_sha:
        raise ValueError("Backup checksum mismatch")
    if h.audit.sha(image) != new["image_sha256"]:
        raise ValueError("Candidate checksum mismatch")
    table = read_gpt(snapshot)
    verify_manifest(old, table, snapshot.stat().st_size)
    verify_manifest(new, read_gpt(image), image.stat().st_size)
    if experiment_validator is None:
        compatible(old, new, allow_logical)
    else:
        # Internal VM API only, deliberately absent from the CLI. Its output
        # uses a different schema, rejected by the physical apply validator.
        experiment_validator(old, new)
    verify_vbmeta_bootconfig(snapshot, table, old["entries"])
    verify_vbmeta_bootconfig(image, new["gpt"], new["entries"])
    for src, manifest, rows in ((snapshot, old, table), (image, new, new["gpt"])):
        for row in rows:
            if row["name"] in (*BOOT, "super", "vbmeta_a"):
                if digest_range(src, *extent(row)) != manifest["payload_readback"][row["name"]]:
                    raise ValueError(f"System partition differs from manifest: {row['name']}")
    w = h.new_output(out, (snapshot.parent, candidate))
    w.chmod(0o700)
    report = {"schema": ("openbook-ruby-experimental-clone/1" if experiment_validator
                         else "openbook-ruby-preserving-update/1"), "complete": False,
              "backup_sha256": snapshot_sha, "candidate_sha256": new["image_sha256"],
              "physical_device_written": False, "data_unlock_verified": False}
    (w / "update.json").write_text(json.dumps(report, indent=2) + "\n")
    esp = w / "esp.img"
    live.copy_range(snapshot, esp, *extent(table[0]))
    # Check FAT before modification. Never auto-repair a configured source.
    h.run("fsck.fat", "-n", esp)
    tree = w / "esp-before"; tree.mkdir()
    h.run("mcopy", "-s", "-i", esp, "::*", tree)
    before_files = tree_hashes(tree)
    updated = copy.deepcopy(new)
    updated["gpt"] = table
    updated["preserved_from_sha256"] = snapshot_sha
    updated["scope"] += " Preserved private user data; never redistribute."
    changed_files = {"ruby/RESEARCH.json"}
    for mode, params in updated["entries"].items():
        filename = f"ruby/initrd-{mode}.img"
        local = w / f"initrd-{mode}.img"
        h.run("mcopy", "-i", f"{image}@@{extent(new['gpt'][0])[0]}", f"::/{filename}", local)
        body, parsed = split_initrd(local.read_bytes())
        old_body, old_parsed = split_initrd((tree / filename).read_bytes())
        if parsed != new["entries"][mode] or old_parsed != old["entries"][mode] or body != old_body:
            raise ValueError("Initrd body or bootconfig differs from reviewed baseline")
        if params["androidboot.boot_part_uuid"] != new["gpt"][0]["partuuid"]:
            raise ValueError("Candidate boot UUID mismatch")
        params["androidboot.boot_part_uuid"] = table[0]["partuuid"]
        local.write_bytes(body + h.gpt.bootconfig_trailer(h.bc.render(params).decode(), len(body)))
        if split_initrd(local.read_bytes())[1] != params:
            raise ValueError("Rebuilt bootconfig failed readback")
        h.run("mcopy", "-o", "-i", esp, local, f"::/{filename}")
        changed_files.add(filename)
    embedded = w / "RESEARCH.json"
    embedded.write_text(json.dumps({k: v for k, v in updated.items()
                                   if k not in ("image_sha256", "payload_readback")}, indent=2) + "\n")
    h.run("mcopy", "-o", "-i", esp, embedded, "::/ruby/RESEARCH.json")
    h.run("fsck.fat", "-n", esp)
    after_tree = w / "esp-after"; after_tree.mkdir()
    h.run("mcopy", "-s", "-i", esp, "::*", after_tree)
    after_files = tree_hashes(after_tree)
    if {k: v for k, v in before_files.items() if k not in changed_files} != {
            k: v for k, v in after_files.items() if k not in changed_files}:
        raise ValueError("Unrelated ESP files changed (including logs/menu)")
    for mode, params in updated["entries"].items():
        actual = (after_tree / f"ruby/initrd-{mode}.img").read_bytes()
        if actual != (w / f"initrd-{mode}.img").read_bytes() or split_initrd(actual)[1] != params:
            raise ValueError("ESP initrd readback mismatch")
    if (after_tree / "ruby/RESEARCH.json").read_bytes() != embedded.read_bytes():
        raise ValueError("ESP manifest readback mismatch")
    output = w / "ruby-live.img"
    h.run("cp", "--reflink=auto", "--sparse=always", snapshot, output)
    output.chmod(0o600)
    writes = []
    with output.open("r+b") as dst:
        for row in table:
            name = row["name"]
            if name not in WRITABLE:
                continue
            offset, length = extent(row)
            src, source_offset = (esp, 0) if name == "EFI" else (image, offset)
            wanted = digest_range(src, source_offset, length)
            with src.open("rb") as inp:
                inp.seek(source_offset); dst.seek(offset); left = length
                while left:
                    data = inp.read(min(left, 4 << 20))
                    if not data:
                        raise ValueError("Truncated update payload")
                    dst.write(data); left -= len(data)
            dst.flush(); os.fsync(dst.fileno())
            if digest_range(output, offset, length) != wanted:
                raise ValueError("Updated partition readback mismatch")
            writes.append(dict(name=name, offset=offset, length=length, sha256=wanted))
    protected = []
    for offset, length in protected_ranges(table, snapshot.stat().st_size):
        expected = digest_range(snapshot, offset, length)
        if digest_range(output, offset, length) != expected:
            raise ValueError("Protected data/identity range changed")
        protected.append(dict(offset=offset, length=length, sha256=expected))
    if read_gpt(output) != table or h.audit.sha(snapshot) != snapshot_sha or h.audit.sha(image) != new["image_sha256"]:
        raise ValueError("Source or GPT changed")
    updated["payload_readback"].update({r["name"]: r["sha256"] for r in writes})
    updated["image_sha256"] = h.audit.sha(output)
    (w / "manifest.json").write_text(json.dumps(updated, indent=2) + "\n")
    if allow_logical:
        # A system change invalidates the USB installer's source pin: the
        # physical writer accepts this only after an installer rebind stage.
        report.update(complete=False, requires_installer_rebind=True, reviewed_logical=sorted(allow_logical),
                      image_sha256=updated["image_sha256"], writes=writes, protected=protected,
                      sources_unchanged=True, unrelated_esp_files_unchanged=True)
        (w / "update.json").write_text(json.dumps(report, indent=2) + "\n")
        print("Verified private system stage; installer rebind still required.")
        return
    report.update(complete=True, image_sha256=updated["image_sha256"], writes=writes,
                  protected=protected, sources_unchanged=True, unrelated_esp_files_unchanged=True)
    (w / "update.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Verified disposable clone; physical writer rejects this experimental plan."
          if experiment_validator else
          "Verified private updated clone; physical USB unchanged. G14 unlock still requires testing.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "base-manifest", "candidate", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--snapshot-sha256", required=True)
    p.add_argument("--allow-logical", action="append", default=[], choices=REVIEWABLE_LOGICAL,
                   help="Reviewed logical image change; output requires an installer rebind")
    a = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Run through inst-docker.sh; no physical devices")
    os.umask(0o077)
    prepare(a.snapshot, a.snapshot_sha256, a.base_manifest, a.candidate, a.out, allow_logical=tuple(a.allow_logical))


if __name__ == "__main__":
    main()
