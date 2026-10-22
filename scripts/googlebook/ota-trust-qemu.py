#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run an OTA trust test image in a disposable VM and judge what update_engine did.

The image comes from build-ota-trust-candidate.py --vm-test. After boot, its
harness drives the stock update_engine_client through verify, allocate and
update for each test payload. This runner boots a private copy (run-probe.py,
no NIC, synthetic decoy disk), then compares the disk before and after:
- the single-slot boot partitions,
- the misc boot-control block,
- each super metadata slot,
- /metadata/ota.
It writes result.json. No physical device or owner data is an input.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess

HERE = Path(__file__).resolve().parent


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = load("preserve", "preserve-update.py")
r = load("probe", "run-probe.py")
STATIC = ("boot_a", "init_boot_a", "vendor_boot_a", "vbmeta_a")
CASES = ("foreign-static", "openbook-static", "openbook-vab")
SIGNATURE = "kDownloadMetadataSignatureMismatch"
BARRIER = "kInstallDeviceOpenError"
# update_engine milestones kept per case, in order, as evidence.
KEY_LINES = re.compile(
    r"Received a request|ApplyPayload\(|Verified correct signature|Failed to verify the signature"
    r"|Failed to validate metadata signature|Mandatory metadata signature|timestamp|ResetUpdate"
    r"|MarkSlotUnbootable|Unable to mark new slot|PreparePartitionsForUpdate done|Updated logical partition table"
    r"|Successfully created all snapshots|Successfully created snapshot for|Remaining free space for COW"
    r"|does not exist|Unable to determine|Failed to get partition device|finished \w+Action with code"
    r"|onPayloadApplicationComplete|allocated space|Allocation failed|Payload is (?:not )?applicable"
    r"|SetActiveBootSlot|[Ss]witch(?:ing)? slot")


def boot_control(disk, table):
    """bootloader_control from misc (offset 2048): suffix, slot count and per-slot priority."""
    offset, _ = p.extent(next(row for row in table if row["name"] == "misc"))
    with disk.open("rb") as f:
        f.seek(offset + 2048)
        raw = f.read(32)
    flags = int.from_bytes(raw[9:11], "little")
    slots = [dict(priority=raw[12 + 2 * i] & 0xF, tries=(raw[12 + 2 * i] >> 4) & 0x7,
                  successful=bool(raw[12 + 2 * i] >> 7)) for i in range(2)]
    return dict(raw=raw.hex(), suffix=raw[:4].rstrip(b"\0").decode(errors="replace"),
                magic_ok=raw[4:8] == b"BCAB", nb_slot=flags & 0x7, slots=slots)


def super_slots(disk, table):
    """Digests of the primary and backup copy of every LP metadata slot."""
    offset, _ = p.extent(next(row for row in table if row["name"] == "super"))
    with disk.open("rb") as f:
        f.seek(offset + 4096)
        geometry = f.read(52)
    magic, _, max_size, count, _ = struct.unpack_from("<II32xIII", geometry)
    if magic != 0x616C4467:
        raise ValueError("No LP geometry in super")
    first = offset + 3 * 4096
    return {f"slot{n}": dict(primary=p.digest_range(disk, first + n * max_size, max_size),
                             backup=p.digest_range(disk, first + (count + n) * max_size, max_size))
            for n in range(count)}, (offset, 3 * 4096 + 2 * count * max_size)


def lpdump(tools, disk, region, work, label):
    """lpdump of each metadata slot from a copy of only the super header region."""
    head = work / f"{label}-super-head.img"
    p.live.copy_range(disk, head, *region)
    out = {}
    for slot in (0, 1):
        run = subprocess.run([str(tools / "lpdump"), f"--slot={slot}", str(head)], capture_output=True, text=True)
        out[f"slot{slot}"] = run.stdout if run.returncode == 0 else f"lpdump exit {run.returncode}: {run.stderr.strip()}"
    head.unlink()
    return out


def ota_state(disk, table, work, label):
    """Listing of /metadata/ota (snapshot state only; no key material is read)."""
    offset, length = p.extent(next(row for row in table if row["name"] == "metadata"))
    image = work / f"{label}-metadata.img"
    p.live.copy_range(disk, image, offset, length)
    listing = {}
    for path in ("/ota", "/ota/snapshots"):
        run = subprocess.run(["debugfs", "-R", f"ls -l {path}", str(image)], capture_output=True, text=True)
        # debugfs ls -l: inode mode (links) uid gid size date time name
        listing[path] = sorted(f"{parts[-1]} {parts[-4]}" for parts in map(str.split, run.stdout.splitlines())
                               if len(parts) >= 9 and parts[-1] not in (".", ".."))
    image.unlink()
    return listing


REQUEST = re.compile(r"Received a request of (verifying|allocating)[^/]*/system/etc/openbook-ota-test/([a-z-]+)\.metadata"
                     r"|ApplyPayload\(file:///system/etc/openbook-ota-test/([a-z-]+)\.payload")
PREPARED = re.compile(r"Preparing partitions for new update|PreparePartitionsForUpdate done")


def harness(serial):
    """Client exit codes from the console; per-request outcome from update_engine's own log.

    Console lines from the client can be lost or delayed among kernel output,
    so ErrorCodes and milestones come only from the ordered logcat dump.
    """
    console = "\n".join(line for line in serial.splitlines() if not line.startswith("OTALOG "))
    exits = {(m[1], m[2]): int(m[3]) for m in
             re.finditer(r"OTATRUST (verify|allocate|update) ([a-z-]+) exit=(\d+)", console)}
    segments, key = {}, None
    for line in serial.splitlines():
        if not line.startswith("OTALOG "):
            continue
        request = REQUEST.search(line)
        if request:
            key = ({"verifying": "verify", "allocating": "allocate"}[request[1]], request[2]) if request[1] \
                else ("update", request[3])
            segments[key] = []
        if key:
            segments[key].append(re.sub(r"^OTALOG \S+ \S+ +\d+ +\d+ ", "", line))
    steps = []
    for case in CASES:
        for step in ("verify", "allocate", "update"):
            lines = segments.get((step, case), [])
            text = "\n".join(lines)
            final = re.findall(r"onPayloadApplicationComplete\(ErrorCode::(k\w+)", text)
            steps.append(dict(step=step, case=case, exit=exits.get((step, case)), logged=bool(lines),
                              error_codes=sorted(set(re.findall(r"ErrorCode::(k\w+)", text)) - {"kSuccess"}),
                              final_error_code=final[-1] if final else None,
                              signature_verified="Verified correct signature" in text,
                              partitions_prepared=bool(PREPARED.search(text)),
                              snapshots_created="Successfully created all snapshots" in text,
                              target_super_metadata_written="Updated logical partition table at slot 1" in text,
                              milestones=[l[:240] for l in lines if KEY_LINES.search(l)
                                          and "onStatusUpdate" not in l]))
    begin = re.search(r"OTATRUST begin otacerts=([0-9a-f]{64})", console)
    idle = re.search(r"OTATRUST idle waited=(\d+)s", console)
    props = re.search(r"OTATRUST props slot=(\S*) secure=(\S*) vab=(\S*)", console)
    return dict(steps=steps, harness_runs=len(re.findall(r"OTATRUST begin", console)),
                updater_idle_after_s=int(idle[1]) if idle else None,
                otacerts_sha256=begin[1] if begin else None,
                props=dict(zip(("slot", "secure", "virtual_ab"), props.groups())) if props else None,
                finished=bool(re.search(r"OTATRUST end", console)))


def trusted_cases(test):
    """Cases the installed certificate should accept; older images imply it from the trust mode."""
    if "trusted_cases" in test:
        return tuple(test["trusted_cases"])
    return ("openbook-static", "openbook-vab") if test["trust"] == "openbook" else ()


def judge(trusted, observed):
    by = {(s["step"], s["case"]): s for s in observed["steps"]}

    def refused(case, step):
        s = by[(step, case)]
        return (s["logged"] and s["exit"] not in (None, 0) and SIGNATURE in s["error_codes"]
                and not s["signature_verified"] and not s["partitions_prepared"])

    checks = {f"{case} {step} refused at metadata signature, before partition preparation": refused(case, step)
              for case in CASES if case not in trusted for step in ("verify", "allocate", "update")}
    for case in trusted:
        s = by[("verify", case)]
        checks[f"{case} metadata verified"] = s["exit"] == 0 and s["signature_verified"]
    if "openbook-static" in trusted:
        s = by[("update", "openbook-static")]
        checks["openbook-static update stops at the missing second slot"] = (
            s["exit"] not in (None, 0) and s["final_error_code"] == BARRIER and s["error_codes"] == [BARRIER])
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "qemu", "tools", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=720, choices=range(300, 1801), metavar="300..1800")
    parser.add_argument("--reevaluate", action="store_true", help="Judge an existing --out run again; no VM boot")
    a = parser.parse_args()
    if not Path("/.dockerenv").exists():
        parser.error("Use inst-docker.sh; disposable VM only")
    os.umask(0o077)
    manifest = json.loads(p.regular(a.candidate / "manifest.json").read_text())
    test = manifest.get("experimental_ota_trust_test", {})
    if test.get("deployment_eligible") is not False:
        raise ValueError("Requires a disposable OTA trust test image")
    image = p.regular(a.candidate / "ruby-live.img")
    if p.h.audit.sha(image) != manifest["image_sha256"]:
        raise ValueError("Candidate hash mismatch")
    if not a.reevaluate:
        a.out.mkdir(mode=0o700)
    elif not (a.out / "run/serial.log").is_file():
        raise ValueError("--reevaluate needs a completed run")
    table = p.read_gpt(image)
    rows = {row["name"]: row for row in table}
    before = dict(static={n: p.digest_range(image, *p.extent(rows[n])) for n in STATIC},
                  boot_control=boot_control(image, table))
    before["super"], region = super_slots(image, table)
    before["lpdump"] = lpdump(a.tools, image, region, a.out, "before")
    before["metadata_ota"] = ota_state(image, table, a.out, "before")
    run = a.out / "run"
    if not a.reevaluate:
        subprocess.run(["python3", str(HERE / "run-probe.py"), "--input", str(a.candidate), "--out", str(run),
                        "--qemu", str(a.qemu), "--accel", "tcg", "--uefi-usb", "--usb-logs", "--tpm",
                        "--timeout", str(a.seconds)], check=True)
    disk = run / "usb-test.img"
    after = dict(static={n: p.digest_range(disk, *p.extent(rows[n])) for n in STATIC},
                 boot_control=boot_control(disk, table))
    after["super"], _ = super_slots(disk, table)
    after["lpdump"] = lpdump(a.tools, disk, region, a.out, "after")
    after["metadata_ota"] = ota_state(disk, table, a.out, "after")
    serial = (run / "serial.log").read_text(errors="replace").replace("\r", "")
    observed = harness(serial)
    checks = judge(trusted_cases(test), observed)
    checks["boot completed"] = r.boot_completed_reported(serial)
    checks["SELinux enforcing"] = bool(re.search(r"(?m)^Enforcing$", serial))
    # The serial diagnostics entry also runs as shell; count only the updater, its client and the harness files.
    denials = sorted(set(line.split("avc:", 1)[1][:300] for line in serial.splitlines()
                         if "avc:" in line and "denied" in line and not line.startswith("OTALOG ")
                         and re.search(r"u:r:update_engine:s0|comm=\"update_engine_c|openbook-ota-t", line)))
    checks["no update_engine or harness denials"] = not denials
    checks["harness finished"] = observed["finished"]
    checks["single-slot boot partitions unchanged"] = before["static"] == after["static"]
    # The fresh image's misc is empty; Android's boot HAL fills it on first boot.
    control = after["boot_control"]
    checks["second slot never activated"] = (control["magic_ok"] and control["suffix"] == "_a"
                                             and control["nb_slot"] == 1 and control["slots"][1]["priority"] == 0)
    checks["harness ran once"] = observed["harness_runs"] == 1
    checks["updater idle before the first request"] = (observed["updater_idle_after_s"] is not None
                                                       and observed["updater_idle_after_s"] < 300)
    checks["current super metadata slot unchanged"] = before["super"]["slot0"] == after["super"]["slot0"]
    result = dict(schema="openbook-ruby-ota-trust-rehearsal/1", trust=test["trust"],
                  trusted_cases=list(trusted_cases(test)),
                  candidate_sha256=manifest["image_sha256"], payloads=test["payloads"],
                  expected_otacerts_sha256=(manifest.get("ota_trust_anchor", {}).get("archive_sha256")
                                            or "640c923ab47c6b220263cec685de5a0deb6cdec7695742776a87719bde2d5bdb"),
                  observed=observed, checks=checks, passed=all(checks.values()),
                  disk=dict(before={k: v for k, v in before.items() if k != "lpdump"},
                            after={k: v for k, v in after.items() if k != "lpdump"},
                            target_super_slot_changed=before["super"].get("slot1") != after["super"].get("slot1")),
                  updater_denials=denials,
                  serial_sha256=p.h.audit.sha(run / "serial.log"),
                  runtime_findings=r.runtime_findings(serial),
                  deployment_eligible=False, hardware_tested=False)
    checks["trust archive on device"] = observed["otacerts_sha256"] == result["expected_otacerts_sha256"]
    result["passed"] = all(checks.values())
    (a.out / "lpdump.json").write_text(json.dumps(dict(before=before["lpdump"], after=after["lpdump"]), indent=2) + "\n")
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(trust=result["trust"], passed=result["passed"], checks=checks), indent=2))


if __name__ == "__main__":
    main()
