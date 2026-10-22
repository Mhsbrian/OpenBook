#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Boot a Ruby A/B disk (build-ruby-ab-image.py) in QEMU as the internal NVMe and judge it.

The disk is copied first (reflink), so the built image stays pristine. The VM
gets OVMF, a fresh software TPM, no NIC and a serial log. After the run, the
copy is judged host-side:
  - boot completion, from init's kernel-log lines;
  - misc's bootloader_control, written by the A/B boot HAL: the slot suffix,
    the slot count (2 on this layout) and whether slot A was marked successful;
  - openbook-bootsync `status` on the copy (slot A in_sync, entry good);
  - userdata formatted by Android at its full planned size and mounted (it is
    metadata-encrypted, so the raw disk holds ciphertext: the evidence is
    make_f2fs's sector count and the mount of the dm device), and metadata
    formatted as ext4.
No physical device; regular image files only.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
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
EXT4_MAGIC = 0xEF53


def boot_control(disk, misc_off):
    with open(disk, "rb") as f:
        f.seek(misc_off + 2048)
        raw = f.read(32)
    flags = int.from_bytes(raw[9:11], "little")
    return dict(suffix=raw[:4].rstrip(b"\0").decode(errors="replace"), magic_ok=raw[4:8] == b"BCAB",
                nb_slot=flags & 0x7,
                slots=[dict(priority=raw[12 + 2 * i] & 0xF, tries=(raw[12 + 2 * i] >> 4) & 0x7,
                            successful=bool(raw[12 + 2 * i] >> 7)) for i in range(2)])


def magic(disk, offset, at, fmt):
    with open(disk, "rb") as f:
        f.seek(offset + at)
        return struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]


def userdata_ok(serial, built):
    """Android formatted userdata at (nearly) its full partition size and mounted it."""
    size = next(row["length"] for row in built["layout"] if row["name"] == "userdata")
    m = re.search(r"make_f2fs: Info: total sectors = (\d+)", serial)
    sector = re.search(r"make_f2fs: Info: sector size = (\d+)", serial)
    if not m or not sector:
        return False
    formatted = int(m.group(1)) * int(sector.group(1))
    mounted = bool(re.search(r"F2FS-fs \(dm-\d+\): Mounted", serial))
    return mounted and 0.95 * size <= formatted <= size


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("image-dir", "qemu", "bootsync", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--seconds", type=int, default=720)
    p.add_argument("--reevaluate", action="store_true", help="judge an existing --out run again; no VM boot")
    a = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Run in the openbook-installer container")
    os.umask(0o077)
    built = json.loads((a.image_dir / "result.json").read_text())
    offs = {row["name"]: row["offset"] for row in built["layout"]}
    disk = a.out / "disk.img"
    if a.reevaluate:
        prior = json.loads((a.out / "result.json").read_text())
        judge(a, built, offs, disk, prior["elapsed_s"], prior["observation_completed"], prior["qmp_events"])
        return
    a.out.mkdir(mode=0o700)
    subprocess.run(["cp", "--reflink=auto", str(a.image_dir / "disk.img"), str(disk)], check=True)
    vars_file = a.out / "vars.fd"
    vars_file.write_bytes(Path("/usr/share/edk2/x64/OVMF_VARS.4m.fd").read_bytes())
    cmd = [str(a.qemu), "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-smp", "4", "-m", "8192",
           "-display", "none", "-nic", "none", "-monitor", "none", "-no-reboot",
           "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd",
           "-drive", f"if=pflash,format=raw,file={vars_file}",
           "-drive", f"file={disk},format=raw,if=none,id=target",
           "-device", "nvme,drive=target,serial=RUBYABTEST,bootindex=1",
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
    elapsed = round(time.monotonic() - start, 1)
    judge(a, built, offs, disk, elapsed, completed, [e.get("event") for e in events])


def judge(a, built, offs, disk, elapsed, completed, qmp_events):
    serial = (a.out / "serial.log").read_text(errors="replace")
    status = subprocess.run([str(a.bootsync), "--disk", str(disk), "--current", "a", "--json", "status"],
                            capture_output=True, text=True)
    bs = json.loads(status.stdout) if status.stdout.strip() else {}
    bcl = boot_control(disk, offs["misc"])
    checks = {
        "boot_completed": bool(re.search(r"processing action \(sys\.boot_completed=1\)", serial)),
        "booted_slot_a": "androidboot.slot_suffix" not in serial or bcl["suffix"] == "_a",
        "boot_hal_sees_two_slots": bcl["magic_ok"] and bcl["nb_slot"] == 2,
        "slot_a_marked_successful": bcl["slots"][0]["successful"],
        "bootsync_slot_a_in_sync": bs.get("slots", {}).get("a", {}).get("esp_files") == "in_sync",
        "bootsync_entry_good": bs.get("slots", {}).get("a", {}).get("entry_state") == "good",
        "userdata_formatted_full_size_and_mounted": userdata_ok(serial, built),
        "metadata_formatted_ext4": magic(disk, offs["metadata"], 0x438, "<H") == EXT4_MAGIC,
        "no_avb_handoff_error": not any("Failed to verify vbmeta digest" in l or "vbmeta size mismatch" in l
                                        for l in serial.splitlines()),
    }
    result = dict(schema="openbook-ruby-ab-boot/1", elapsed_s=elapsed, observation_completed=completed,
                  qmp_events=qmp_events, boot_control=bcl,
                  bootsync_status_ok=bs.get("ok"), next_boot_slot=bs.get("next_boot_slot"),
                  userdata_bytes=next(rw["length"] for rw in built["layout"] if rw["name"] == "userdata"),
                  checks=checks, passed=all(checks.values()),
                  runtime_findings=r.runtime_findings(serial))
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("elapsed_s", "boot_control", "checks", "passed")}, indent=2))


if __name__ == "__main__":
    main()
