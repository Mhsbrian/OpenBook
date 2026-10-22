#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose a reviewed system stage and its follow-on EFI stages into one USB write plan.

Regular files only. Stage 1 is preserve-update.py output with a reviewed logical
change (incomplete, requires an installer rebind). Stage 2 replaces the installer
with one pinned to that new system. Later stages may only add boot entries.
The final plan is checked against the ORIGINAL backup, so the existing
apply-preserved-update.py verifies the current USB against that backup and
writes only EFI, vbmeta_a and super. This is packaging, not write approval.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


a = load("apply_update", "apply-preserved-update.py")
m = load("migrate", "migrate.py")
u = a.u


def plan(stage):
    return json.loads(u.regular(stage / "update.json").read_text())


def compose(backup, backup_sha, stages, pin_path, out):
    m.require(len(stages) >= 2, "Need a system stage and an installer stage")
    backup = u.regular(backup)
    m.require(u.h.audit.sha(backup) == backup_sha, "Backup checksum mismatch")
    plans = [plan(s) for s in stages]
    system, installer, extras = plans[0], plans[1], plans[2:]
    m.require(system.get("schema") == "openbook-ruby-preserving-update/1" and system.get("complete") is False
              and system.get("requires_installer_rebind") is True and system.get("reviewed_logical"),
              "First stage must be a reviewed, incomplete system stage")
    m.require(system["backup_sha256"] == backup_sha, "System stage was not built from this backup")
    previous = system["image_sha256"]
    m.require(installer.get("operation") == "Replace" and installer.get("complete") is True,
              "Second stage must replace the installer")
    for stage, item in zip(stages[1:], plans[1:]):
        m.require(item["backup_sha256"] == previous, f"Stage chain broken at {stage.name}")
        previous = item["image_sha256"]
    for item in extras:
        m.require(item.get("operation") == "AddBootEntries" and item.get("complete") is True,
                  "Later stages may only add boot entries")
    for stage, item in zip(stages, plans):
        m.require(u.h.audit.sha(u.regular(stage / "ruby-live.img")) == item["image_sha256"],
                  f"Stage image changed: {stage.name}")
    final = u.regular(stages[-1] / "ruby-live.img")
    table = u.read_gpt(backup)
    m.require(u.read_gpt(final) == table and final.stat().st_size == backup.stat().st_size,
              "Disk identity or layout changed")
    protected = []
    for offset, length in u.protected_ranges(table, backup.stat().st_size):
        digest = u.digest_range(backup, offset, length)
        m.require(u.digest_range(final, offset, length) == digest, "Protected bytes changed across stages")
        protected.append(dict(offset=offset, length=length, sha256=digest))
    m.require(protected == system["protected"], "System stage protected ranges disagree")
    # The installer on the final image must be pinned to the final system.
    pin = json.loads(u.regular(pin_path).read_text())
    fd = os.open(final, os.O_RDONLY)
    try:
        m.check_source(fd, pin)
    finally:
        os.close(fd)
    manifest = json.loads(u.regular(stages[-1] / "manifest.json").read_text())
    m.require(manifest["offline_migration_installer"]["source_pin_sha256"] ==
              u.h.audit.sha(u.regular(pin_path)), "Installer is not bound to this pin")
    out.mkdir(mode=0o700)
    output = out / "ruby-live.img"
    u.h.run("cp", "--reflink=auto", "--sparse=always", final, output)
    rows = {r["name"]: r for r in table}
    writes = [dict(name=n, offset=u.extent(rows[n])[0], length=u.extent(rows[n])[1],
                   sha256=u.digest_range(output, *u.extent(rows[n]))) for n in ("EFI", "vbmeta_a", "super")]
    result = dict(schema="openbook-ruby-preserving-update/1", complete=True, backup_sha256=backup_sha,
                  candidate_sha256=system["candidate_sha256"], image_sha256=u.h.audit.sha(output),
                  writes=writes, protected=protected, sources_unchanged=True, unrelated_esp_files_unchanged=True,
                  physical_device_written=False, data_unlock_verified=False,
                  reviewed_logical=system["reviewed_logical"], installer_source_pin_sha256=u.h.audit.sha(pin_path),
                  stages=[dict(name=s.name, operation=p.get("operation", "SystemUpdate"), image_sha256=p["image_sha256"])
                          for s, p in zip(stages, plans)])
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "update.json").write_text(json.dumps(result, indent=2) + "\n")
    a.validate_plan(out, backup)
    print(json.dumps({"image_sha256": result["image_sha256"], "stages": len(stages)}))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", type=Path, required=True)
    p.add_argument("--backup-sha256", required=True)
    p.add_argument("--stage", type=Path, action="append", required=True, help="In order: system, installer, extras")
    p.add_argument("--pin", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    m.require(Path("/.dockerenv").exists(), "Use inst-docker.sh; no physical devices")
    os.umask(0o077)
    compose(args.backup, args.backup_sha256, args.stage, args.pin, args.out)


if __name__ == "__main__":
    main()
