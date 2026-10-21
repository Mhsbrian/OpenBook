#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rehearse this bridge on the exact retained synthetic RB01 userdata fixture.

No physical devices or owner backup accepted. Carries the VM-only probe and
keeps the old installer unusable pending rebind; this is not release packaging.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil

spec = importlib.util.spec_from_file_location("builder", Path(__file__).with_name("build-bridge-candidate.py"))
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
p = b.p
BASE_IMAGE = "3ae5daf7b45d847ebe50bb15fca0a6a272d7d402fc4467ff5d199be20caa63e2"
BASE_MANIFEST = "ed444fc3e854dfc0abaf7d85c8de09706d613d9aec948ca93882396efb9e9ea2"
EXPERIMENT = "ANAL-234-EXPERIMENT-ONLY"
original_compatible = p.compatible


def compatible(old, new, reviewed_release=None):
    if reviewed_release != EXPERIMENT or p.manifest_fingerprint(old) != BASE_MANIFEST:
        raise ValueError("Only the exact synthetic RB01 fixture is allowed")
    if (new.get("vm_instrumentation", {}).get("not_for_release") is not True or
            new.get("bridge_correction", {}).get("selected") != "libberberis_arm64.so"):
        raise ValueError("Only the instrumented Digitalis research image is allowed")
    adjusted = copy.deepcopy(new)
    adjusted["logical_sha256"]["system"] = old["logical_sha256"]["system"]
    original_compatible(old, adjusted)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "candidate", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    a = parser.parse_args()
    if not Path("/.dockerenv").exists(): parser.error("Use the installer tools container")
    os.umask(0o077)
    b.space(a.out.parent, 5 << 30)
    before = shutil.disk_usage(a.out.parent).free
    p.compatible = compatible
    p.prepare(a.base / "ruby-live.img", BASE_IMAGE, a.base / "manifest.json", a.candidate, a.out, EXPERIMENT)
    cleanup = [a.out / "esp.img", a.out / "esp-before", a.out / "esp-after"]
    (a.out / "cleanup.json").write_text(json.dumps({"removed": list(map(str, cleanup)), "free_before": before}, indent=2) + "\n")
    for path in cleanup:
        if path.is_dir(): shutil.rmtree(path)
        else: path.unlink()
    report = json.loads((a.out / "update.json").read_text())
    report.update(not_for_release=True, free_after=shutil.disk_usage(a.out).free)
    (a.out / "update.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__": main()
