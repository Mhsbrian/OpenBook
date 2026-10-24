#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Capture private, bounded Settings search diagnostics from an explicit adb device.

No root, UI actions, installs, settings writes, log clearing or reboot. Reproduce
the failure manually before collection. An empty crash buffer is NOT a pass.
Raw logs and package dumps are private; review summary.json before sharing it.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

PACKAGE = "com.google.android.settings.intelligence"
LOG = re.compile(
    r"^(\d\d-\d\d \d\d:\d\d:\d\d\.\d+)\s+(\d+)\s+\d+\s+[VDIWEF]\s+([^:]+):\s?(.*)$"
)


def command_denied(data):
    # Logcat may contain historical permission errors in other apps. Only a
    # command-level error at the beginning of a line makes this capture denied.
    return bool(re.search(rb"(?m)^(?:Permission denied|Permission Denial:|java.lang.SecurityException:)", data))


def analyze(logs):
    """Only associate a failure with a process explicitly identified in these logs."""
    rows = [m.groups() for text in logs for line in text.splitlines()
            if (m := LOG.match(line))]
    processes = {}
    for timestamp, pid, tag, message in rows:
        if tag.strip() == "AndroidRuntime" and message == f"Process: {PACKAGE}, PID: {pid}":
            processes[(timestamp, pid)] = PACKAGE
    crashes = set()
    for timestamp, pid, tag, message in rows:
        if (timestamp, pid) in processes and tag.strip() == "AndroidRuntime" and all(
            word in message for word in ("UnsatisfiedLinkError", "libicing.so",
                                        "EM_AARCH64 (183)", "EM_X86_64 (62)")
        ):
            crashes.add((timestamp, pid))
    # A successful process start log alone is not an initialization pass. Keep
    # failures separate: PID reuse across a long buffer prevents proving causality
    # solely by matching the PID here. The reviewed timeline establishes ordering.
    bridge_failures = sorted({(timestamp, pid) for timestamp, pid, tag, message in rows
                              if tag.strip() == "houdini" and
                              "Initialize library(" in message and "failed(" in message})
    return {
        "scope": "Historical ring-buffer observations; not a fresh test or fix verdict",
        "settings_search_icing_architecture_crashes": [
            {"device_log_time": t, "pid": int(p)} for t, p in sorted(crashes)],
        "houdini_initialization_failures_all_processes": [
            {"device_log_time": t, "pid": int(p)} for t, p in bridge_failures],
        "diagnosis": "settings_search_arm64_load_failure_observed" if crashes else "inconclusive",
        "fix_validated": False,
    }


def commands():
    yield "identity", "date -u; getprop persist.sys.timezone; cat /proc/uptime; am get-current-user; getenforce"
    props = ("ro.build.fingerprint", "ro.bootimage.build.fingerprint", "ro.product.cpu.abilist",
             "ro.boot.openbook.live", "ro.dalvik.vm.native.bridge", "ro.dalvik.vm.isa.arm64",
             "ro.berberis.is_2nd_native_bridge")
    yield "properties", "; ".join(f'echo "{p}=$(getprop {p})"' for p in props)
    yield "crash", "logcat -d -b crash -v threadtime -t 4000"
    yield "runtime", "logcat -d -b main -b system -v threadtime -t 10000"
    yield "events", "logcat -d -b events -v threadtime -t 4000"
    for package in (PACKAGE, "com.android.settings"):
        name = "search" if package == PACKAGE else "settings"
        yield f"{name}-package", f"dumpsys package {package}"
        yield f"{name}-exit", f"dumpsys activity exit-info {package}"
    yield "resolve", "cmd package query-activities --brief --user current -a com.android.settings.action.SETTINGS_SEARCH"
    yield "processes", "ps -A -o PID,NAME"


def capture(adb, serial, out):
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    if shutil.disk_usage(out).free < 40 * 1024**3 + 128 * 1024**2:
        raise RuntimeError("Collection needs 128 MiB budget above the 40 GiB host reserve")
    report = {"schema": "openbook-settings-search-capture/1", "complete": False,
              "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "commands": [], "free_bytes_before": shutil.disk_usage(out).free}
    base = [adb, "-s", serial]

    def save():
        (out / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(name, argv):
        with (out / f"{name}.txt").open("xb") as stdout, (out / f"{name}.stderr.txt").open("xb") as stderr:
            try:
                result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=stdout,
                                        stderr=stderr, timeout=25, check=False)
                status, code = ("ok" if result.returncode == 0 else "failed"), result.returncode
            except subprocess.TimeoutExpired:
                status, code = "timeout", None
            except OSError as exc:
                stderr.write(str(exc).encode())
                status, code = "launch_failed", None
        files = [out / f"{name}.txt", out / f"{name}.stderr.txt"]
        if status == "ok" and any(command_denied(p.read_bytes()) for p in files):
            status = "access_denied"
        report["commands"].append({"name": name, "status": status, "exit_code": code,
                                   "files": [{"name": p.name, "bytes": p.stat().st_size,
                                              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]})
        save()
        return status == "ok"

    if not run("adb-state", base + ["get-state"]) or (out / "adb-state.txt").read_text().strip() != "device":
        return 2
    for name, command in commands():
        run(name, base + ["shell", command])
    report["complete"] = True
    report["free_bytes_after"] = shutil.disk_usage(out).free
    save()
    summary = analyze([(out / f"{name}.txt").read_text(errors="replace") for name in ("crash", "runtime")])
    summary["capture_complete_without_errors"] = all(r["status"] == "ok" for r in report["commands"])
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if summary["capture_complete_without_errors"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial", required=True, help="Exact authorized device serial from adb devices -l")
    parser.add_argument("--out", required=True, type=Path, help="New private output directory outside the repository")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", args.serial):
        parser.error("Invalid explicit adb device serial")
    os.umask(0o077)
    code = capture(args.adb, args.serial, args.out)
    print(f"Capture exit {code}; raw evidence is private. Capture success is not a search pass.")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
