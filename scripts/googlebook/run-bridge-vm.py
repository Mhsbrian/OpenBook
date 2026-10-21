#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run the instrumented synthetic VM in the foreground, collect, then stop.

No device/network pass-through. Uses the pinned UEFI/USB runner, stops when
the guest finishes or its bounded observation expires, and watches host space.
Exit zero means collection finished; examine the tests, not just this status.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--timeout", type=int, default=1800, choices=range(60, 1801))
    a = parser.parse_args()
    if not Path("/.dockerenv").exists(): parser.error("Use the installer tools container")
    if a.out.exists(): parser.error("A new output directory is required")
    manifest = json.loads((a.input / "manifest.json").read_text())
    if manifest.get("vm_instrumentation", {}).get("not_for_release") is not True:
        parser.error("Requires an explicitly instrumented synthetic test image")
    runner = Path(os.environ["OPENBOOK_RELEASE_TOOLS"]) / "scripts/googlebook/run-probe.py"
    spec = importlib.util.spec_from_file_location("runner", runner)
    r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
    free_before = shutil.disk_usage(a.out.parent).free
    if free_before < 44 << 30: parser.error("Need 4 GiB test budget plus 40 GiB reserve")
    command = [sys.executable, str(runner), "--input", str(a.input), "--out", str(a.out),
               "--qemu", a.qemu, "--accel", "tcg", "--uefi-usb", "--usb-logs",
               "--tpm", "--audio", "--timeout", str(a.timeout)]
    stop = None
    minimum = free_before
    proc = subprocess.Popen(command)
    try:
        while proc.poll() is None:
            time.sleep(2)
            free = shutil.disk_usage(a.out.parent).free
            minimum = min(minimum, free)
            serial = a.out / "serial.log"
            text = serial.read_text(errors="replace") if serial.exists() else ""
            if not stop:
                if free < (40 << 30) + (128 << 20): stop = "space_reserve"
                elif re.search(r"(?m)^BRIDGE_VM_DONE\r?$", text): stop = "guest_finished"
                if stop:
                    try:
                        r.screenshot(a.out / "qmp.sock", a.out / "screen-final.ppm")
                    except (OSError, RuntimeError, ValueError): pass
                    r.qmp(a.out / "qmp.sock", {"execute": "quit"})
        rc = proc.wait()
    finally:
        # Never leave run-owned QEMU or TPM work behind when the wrapper fails.
        if proc.poll() is None:
            try: r.qmp(a.out / "qmp.sock", {"execute": "quit"})
            finally: proc.wait(timeout=90)
    (a.out / "observer.json").write_text(json.dumps({"stop_reason": stop or "runner_limit_or_exit",
        "runner_status": rc, "free_before": free_before, "minimum_free": minimum,
        "free_after": shutil.disk_usage(a.out.parent).free}, indent=2) + "\n")
    return 1 if stop == "space_reserve" else rc


if __name__ == "__main__":
    raise SystemExit(main())
