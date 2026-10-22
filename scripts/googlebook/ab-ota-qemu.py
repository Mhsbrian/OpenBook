#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply an OpenBook-signed OTA into slot B of a Ruby A/B disk, through the stock update_engine.

Boots a disposable A/B apply-test disk (build-ruby-ab-image.py from a
build-ota-trust-candidate.py --apply-from-drive candidate) as the internal NVMe,
with the signed payload on a second drive. Its one-shot apply service stages the
payload into /data/ota_package and runs update_engine_client --update; the boot
HAL then runs bootsync `activate b`. Afterwards the disk copy is judged:
  - update_engine reported the payload applied (UPDATED_NEED_REBOOT / kSuccess);
  - slot B boot/init_boot/vendor_boot/vbmeta went from blank to written;
  - super's slot-1 metadata changed (the system_b snapshot);
  - bootsync now boots slot B next (loader `preferred openbook-b`).
The built A/B image and the payload stay pristine (the disk is copied first).
No device, no network. This is the apply + activate proof; the reboot into
slot B and the broken-slot fallback are driven separately.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


r = load("run_probe", "run-probe.py")
mq = load("migration_qemu", "migration-qemu.py")
abq = load("ab_qemu", "ab-qemu.py")


def digest_range(disk, offset, length):
    import hashlib
    h = hashlib.sha256()
    with open(disk, "rb") as f:
        f.seek(offset)
        left = length
        while left:
            b = f.read(min(left, 8 << 20))
            if not b:
                break
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def nonzero(disk, offset, length):
    with open(disk, "rb") as f:
        f.seek(offset)
        left, seen = length, 0
        while left:
            b = f.read(min(left, 8 << 20))
            if not b:
                break
            seen += sum(1 for x in b if x)
            left -= len(b)
            if seen:
                return True
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("image-dir", "payload", "qemu", "bootsync", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--seconds", type=int, default=1500)
    p.add_argument("--payload-sha256", help="expected sha256 of payload.bin on the drive")
    p.add_argument("--reevaluate", action="store_true")
    a = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Run in the openbook-installer container")
    os.umask(0o077)
    built = json.loads((a.image_dir / "result.json").read_text())
    offs = {row["name"]: row["offset"] for row in built["layout"]}
    lens = {row["name"]: row["length"] for row in built["layout"]}
    disk = a.out / "disk.img"
    if not a.reevaluate:
        a.out.mkdir(mode=0o700)
        subprocess.run(["cp", "--reflink=auto", str(a.image_dir / "disk.img"), str(disk)], check=True)
        # blank-slot baseline before the apply
        (a.out / "before.json").write_text(json.dumps(
            {n: nonzero(disk, offs[n], lens[n]) for n in ("boot_b", "init_boot_b", "vendor_boot_b", "vbmeta_b")}
            | {"super_slot1": digest_range(disk, offs["super"] + 3 * 4096, 2 * 65536)}, indent=2) + "\n")
        vars_file = a.out / "vars.fd"
        vars_file.write_bytes(Path("/usr/share/edk2/x64/OVMF_VARS.4m.fd").read_bytes())
        cmd = [str(a.qemu), "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-smp", "4", "-m", "8192",
               "-display", "none", "-nic", "none", "-monitor", "none", "-no-reboot",
               "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd",
               "-drive", f"if=pflash,format=raw,file={vars_file}",
               "-drive", f"file={disk},format=raw,if=none,id=target",
               "-device", "nvme,drive=target,serial=RUBYABTEST,addr=0x4,bootindex=1",
               "-drive", f"file={a.payload},format=raw,if=none,id=payload,snapshot=on",
               "-device", "nvme,drive=payload,serial=OTAPAYLOAD,addr=0x5",  # higher PCI slot -> /dev/block/nvme1n1
               "-device", "virtio-vga",
               "-serial", f"file:{a.out}/serial.log", "-qmp", "unix:qmp.sock,server=on,wait=off",
               "-chardev", "socket,id=chrtpm,path=tpm.sock", "-tpmdev", "emulator,id=tpm0,chardev=chrtpm",
               "-device", "tpm-crb,tpmdev=tpm0"]
        (a.out / "command.json").write_text(json.dumps(cmd, indent=2) + "\n")
        start = time.monotonic()
        with r.tpm_backend(a.out, True), (a.out / "qemu.log").open("wb") as log:
            proc = subprocess.Popen(cmd, cwd=a.out, stdout=log, stderr=subprocess.STDOUT)
            try:
                completed, events = mq.observe(proc, a.out / "qmp.sock", a.seconds, a.out)
            finally:
                mq.stop(proc)
        (a.out / "run.json").write_text(json.dumps(
            dict(elapsed_s=round(time.monotonic() - start, 1), observation_completed=completed), indent=2) + "\n")

    run = json.loads((a.out / "run.json").read_text())
    before = json.loads((a.out / "before.json").read_text())
    serial = (a.out / "serial.log").read_text(errors="replace")
    status = subprocess.run([str(a.bootsync), "--disk", str(disk), "--current", "a", "--json", "status"],
                            capture_output=True, text=True)
    bs = json.loads(status.stdout) if status.stdout.strip() else {}
    applied = re.search(r"onPayloadApplicationComplete\(ErrorCode::(k\w+)", serial)
    apply_exit = re.search(r"OTAAPPLY update exit=(\d+)", serial)
    after = {n: nonzero(disk, offs[n], lens[n]) for n in ("boot_b", "init_boot_b", "vendor_boot_b", "vbmeta_b")}
    super_slot1_after = digest_range(disk, offs["super"] + 3 * 4096, 2 * 65536)
    on_device = (re.search(r"OTAAPPLY payload=([0-9a-f]{64})", serial) or [None, None])[1]
    checks = {
        "harness_ran": "OTAAPPLY idle" in serial,
        "payload_on_device_matches": on_device == a.payload_sha256 if a.payload_sha256 else bool(on_device),
        "update_engine_completed_success": bool(applied) and applied.group(1) in ("kSuccess", "kUpdatedButNotActive"),
        "slot_b_boot_written": after["boot_b"] and after["vbmeta_b"],
        "super_slot1_changed": super_slot1_after != before["super_slot1"],
        "bootsync_next_boot_slot_b": bs.get("next_boot_slot") == "b",
        "no_avb_handoff_error": not any("Failed to verify vbmeta digest" in l for l in serial.splitlines()),
    }
    result = dict(schema="openbook-ruby-ab-ota-apply/1", elapsed_s=run["elapsed_s"],
                  observation_completed=run["observation_completed"],
                  update_engine_final=applied.group(1) if applied else None,
                  apply_exit=int(apply_exit.group(1)) if apply_exit else None,
                  slot_b_before=before, slot_b_after=after,
                  bootsync_next_boot_slot=bs.get("next_boot_slot"),
                  bootsync_loader=bs.get("loader_conf"),
                  payload_sha256_on_device=on_device, payload_sha256_expected=a.payload_sha256,
                  checks=checks, passed=all(checks.values()),
                  runtime_findings=r.runtime_findings(serial))
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("elapsed_s", "update_engine_final", "apply_exit",
                                             "slot_b_after", "bootsync_next_boot_slot", "checks", "passed")}, indent=2))


if __name__ == "__main__":
    main()
