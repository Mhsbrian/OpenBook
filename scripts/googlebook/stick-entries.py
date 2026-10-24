#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Add reviewed boot-menu entries to a Ruby USB without changing its system.

Regular files only. Each new entry copies an existing entry's kernel and initrd
and appends kernel parameters from a short allowlist (sleep/wake diagnostics and
lid handling). Only new `loader/entries/*.conf` files are added to EFI; every
existing EFI file and every non-EFI byte is preserved. The output is a
preserving-update plan for the existing guarded `apply-preserved-update.py`.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


m = module("migrate", "migrate.py")
u = module("preserve", "preserve-update.py")

NAME = re.compile(r"ruby-[a-z0-9-]{1,40}\.conf")
TITLE = re.compile(r"[A-Za-z0-9 ().,+/_-]{4,90}")
# Diagnostics and lid/wake handling only. No security, verity, SELinux or init changes.
ALLOWED = (re.compile(r"pm_debug_messages"),
           re.compile(r"acpi\.debug_layer=0x[0-9a-fA-F]{1,8}"),
           re.compile(r"acpi\.debug_level=0x[0-9a-fA-F]{1,8}"),
           re.compile(r"button\.lid_init_state=(method|open|ignore)"),
           re.compile(r"button\.lid_report_interval=[0-9]{1,5}"),
           re.compile(r"gpiolib_acpi\.ignore_wake=[A-Z0-9]{4,8}:[0-9]{2}@[0-9]{1,3}"))


def parse_entry(text):
    rows = {}
    for line in text.splitlines():
        key, _, value = line.partition(" ")
        m.require(key in ("title", "linux", "initrd", "options") and key not in rows and value,
                  "Unfamiliar boot entry format")
        rows[key] = value
    m.require(set(rows) == {"title", "linux", "initrd", "options"}, "Incomplete boot entry")
    return rows


def check_spec(spec):
    m.require(spec.get("schema") == "openbook-ruby-stick-entries/1", "Unknown entry spec")
    m.require(spec["entries"] and len(spec["entries"]) <= 4, "Between one and four entries")
    names = set()
    for entry in spec["entries"]:
        m.require(NAME.fullmatch(entry["name"]) and entry["name"] not in names, "Invalid or duplicate entry name")
        names.add(entry["name"])
        m.require(NAME.fullmatch(entry["base"]) or entry["base"] == "openbook-a.conf", "Invalid base entry")
        m.require(TITLE.fullmatch(entry["title"]), "Invalid entry title")
        m.require(entry["add_options"] and all(any(p.fullmatch(o) for p in ALLOWED) for o in entry["add_options"]),
                  "Kernel parameter is not on the reviewed allowlist")
        m.require(len(set(o.split("=")[0] for o in entry["add_options"])) == len(entry["add_options"]),
                  "Duplicate kernel parameter")


def render(base_text, entry):
    rows = parse_entry(base_text)
    existing = rows["options"].split()
    for option in entry["add_options"]:
        m.require(not any(o.split("=")[0] == option.split("=")[0] for o in existing),
                  f"Base entry already sets {option.split('=')[0]}")
    return (f"title {entry['title']}\nlinux {rows['linux']}\ninitrd {rows['initrd']}\n"
            f"options {rows['options']} {' '.join(entry['add_options'])}\n")


def add(snapshot, snapshot_sha, base_manifest, spec_path, out):
    snapshot = u.regular(snapshot)
    old = json.loads(u.regular(base_manifest).read_text())
    spec = json.loads(u.regular(spec_path).read_text())
    check_spec(spec)
    m.require(not any(k.startswith("experimental_") for k in old), "Disposable OTA experiment cannot be packaged")
    m.require(u.h.audit.sha(snapshot) == snapshot_sha, "Snapshot checksum mismatch")
    m.require(not out.exists(), "New output required")
    table = u.read_gpt(snapshot)
    u.verify_manifest(old, table, snapshot.stat().st_size)
    for row in table:
        if row["name"] in m.STATIC:
            m.require(u.digest_range(snapshot, *u.extent(row)) == old["payload_readback"][row["name"]],
                      f"Snapshot system differs from its manifest: {row['name']}")
    out.mkdir(mode=0o700)
    esp = out / "esp.img"
    u.live.copy_range(snapshot, esp, *u.extent(table[0]))
    m.run("fsck.fat", "-n", esp)
    before = out / "efi-before"
    before.mkdir()
    m.run("mcopy", "-s", "-i", esp, "::*", before)
    added = {}
    for entry in spec["entries"]:
        name = f"loader/entries/{entry['name']}"
        m.require(not (before / name).exists(), f"Entry already exists: {entry['name']}")
        base = before / "loader/entries" / entry["base"]
        m.require(base.is_file(), f"Base entry missing: {entry['base']}")
        text = render(base.read_text(), entry)
        rows = parse_entry(text)
        for key in ("linux", "initrd"):
            m.require((before / rows[key].lstrip("/")).is_file(), f"Entry references a missing file: {rows[key]}")
        conf = out / entry["name"]
        conf.write_text(text)
        m.run("mcopy", "-i", esp, conf, f"::/{name}")
        added[name] = text
    m.run("fsck.fat", "-n", esp)
    after = out / "efi-after"
    after.mkdir()
    m.run("mcopy", "-s", "-i", esp, "::*", after)
    old_files = u.tree_hashes(before)
    new_files = u.tree_hashes(after)
    m.require(set(new_files) == set(old_files) | set(added), "Unexpected EFI file added or removed")
    for name, sha in old_files.items():
        m.require(new_files[name] == sha, f"Existing EFI file changed: {name}")
    for name, text in added.items():
        m.require((after / name).read_text() == text, "Boot entry readback failed")
    output = out / "ruby-live.img"
    m.run("cp", "--reflink=auto", "--sparse=always", snapshot, output)
    output.chmod(0o600)
    fd = os.open(output, os.O_RDWR)
    try:
        offset, _ = u.extent(table[0])
        with esp.open("rb") as f:
            while data := f.read(4 * m.MIB):
                m.write_at(fd, offset, data)
                offset += len(data)
        os.fsync(fd)
    finally:
        os.close(fd)
    writes = [dict(name=r["name"], offset=u.extent(r)[0], length=u.extent(r)[1],
                   sha256=u.digest_range(output, *u.extent(r))) for r in table if r["name"] in u.WRITABLE]
    protected = []
    for offset, length in u.protected_ranges(table, snapshot.stat().st_size):
        sha = u.digest_range(snapshot, offset, length)
        m.require(u.digest_range(output, offset, length) == sha, "Protected bytes changed")
        protected.append(dict(offset=offset, length=length, sha256=sha))
    for row in table[1:]:
        m.require(u.digest_range(snapshot, *u.extent(row)) == u.digest_range(output, *u.extent(row)),
                  "Non-EFI partition changed")
    m.require(u.read_gpt(output) == table and u.h.audit.sha(snapshot) == snapshot_sha, "Source or GPT changed")
    spec_sha = hashlib.sha256(Path(spec_path).read_bytes()).hexdigest()
    updated = copy.deepcopy(old)
    updated["image_sha256"] = u.h.audit.sha(output)
    updated["preserved_from_sha256"] = snapshot_sha
    updated["payload_readback"].update({r["name"]: r["sha256"] for r in writes})
    updated["added_boot_entries"] = dict(spec_sha256=spec_sha, entries=sorted(added))
    (out / "manifest.json").write_text(json.dumps(updated, indent=2) + "\n")
    plan = dict(schema="openbook-ruby-preserving-update/1", complete=True,
                backup_sha256=snapshot_sha, candidate_sha256=spec_sha,
                image_sha256=updated["image_sha256"], writes=writes, protected=protected,
                sources_unchanged=True, unrelated_esp_files_unchanged=True,
                physical_device_written=False, data_unlock_verified=False,
                operation="AddBootEntries", added_entries=sorted(added))
    (out / "update.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({"added": sorted(added), "image_sha256": updated["image_sha256"]}))
    return plan


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("snapshot", "base-manifest", "spec", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--snapshot-sha256", required=True)
    a = p.parse_args()
    m.require(Path("/.dockerenv").exists(), "Use inst-docker.sh; no physical devices")
    add(a.snapshot, a.snapshot_sha256, a.base_manifest, a.spec, a.out)


if __name__ == "__main__":
    main()
