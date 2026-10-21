#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compose verified system and installer stages against the ORIGINAL USB backup.

Regular files only. This completes packaging, not device-write authorization.
The physical writer independently verifies every range and the current USB.
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
p = load("package", "migration-package.py")
u = a.u


def compose(system, packaged):
    if (system.get("reviewed_release") != "RB-20261020-01"
            or system.get("complete") is not False or system.get("requires_installer_rebind") is not True):
        raise ValueError("Requires an incomplete reviewed system stage")
    if (packaged.get("complete") is not True
            or packaged.get("backup_sha256") != system["image_sha256"]
            or packaged.get("protected") != system.get("protected")):
        raise ValueError("Packaging chain or protected state mismatch")
    result = dict(packaged)
    result.update(backup_sha256=system["backup_sha256"],
                  candidate_sha256=system["candidate_sha256"],
                  reviewed_release=system["reviewed_release"],
                  system_stage_sha256=system["image_sha256"],
                  operation="Preserve configured USB data; update reviewed system/AVB and rebind installer",
                  automatic_rollback=False, hardware_validated=False)
    return result


def finalize(system_stage, packaged, backup, installer):
    system = json.loads(u.regular(system_stage / "update.json").read_text())
    package = json.loads(u.regular(packaged / "update.json").read_text())
    if u.h.audit.sha(u.regular(system_stage / "ruby-live.img")) != system["image_sha256"]:
        raise ValueError("System stage image changed")
    plan = compose(system, package)
    # Recompute ALL ranges against the original backup before making it usable.
    image, _ = a.validate_plan(packaged, backup, plan)
    pin = json.loads(u.regular(installer / "source.json").read_text())
    build = json.loads(u.regular(installer / "build.json").read_text())
    if u.h.audit.sha(installer / "source.json") != build["source_pin_sha256"]:
        raise ValueError("Installer pin changed")
    fd = os.open(image, os.O_RDONLY)
    try:
        p.m.check_source(fd, pin)
    finally:
        os.close(fd)
    manifest = json.loads(u.regular(packaged / "manifest.json").read_text())
    if (manifest["image_sha256"] != plan["image_sha256"]
            or manifest["offline_migration_installer"] != build or manifest.get("requires_installer_rebind")):
        raise ValueError("Final manifest mismatch")
    manifest["preserved_from_sha256"] = plan["backup_sha256"]
    plan["installer_source_pin_sha256"] = build["source_pin_sha256"]
    (packaged / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (packaged / "update.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({k: plan[k] for k in ("complete", "image_sha256", "backup_sha256")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("system-stage", "packaged", "backup", "installer"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    finalize(args.system_stage, args.packaged, args.backup, args.installer)
