#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual offline installer UI on synthetic disks, then NVMe boot.

Container only. No real block devices or networking. Never supply owner userdata.
The serial driver types the same disk selection and exact serial confirmation
as a human; there is no unattended-write switch in the shipped installer.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


m = load("migration", HERE / "migrate.py")
r = load("probe", HERE / "run-probe.py")


def sha(path):
    with path.open("rb") as f:
        return m.hashlib.file_digest(f, "sha256").hexdigest()


def stop(proc):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait()


def observe(proc, qmp, seconds, work):
    """Retain shutdown/reset evidence instead of losing an early VM exit."""
    deadline = time.monotonic() + seconds
    while not qmp.exists():
        m.require(proc.poll() is None and time.monotonic() < deadline, "Android QMP did not start")
        time.sleep(0.1)
    events = []
    pending = b""
    with socket.socket(socket.AF_UNIX) as sock, (work / "android-qmp-events.jsonl").open("w") as log:
        sock.settimeout(1)
        sock.connect(str(qmp))
        sock.sendall(b'{"execute":"qmp_capabilities"}\n')
        while time.monotonic() < deadline:
            try:
                data = sock.recv(65536)
            except socket.timeout:
                if proc.poll() is not None:
                    break
                continue
            if not data:
                break
            pending += data
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                row = json.loads(line)
                log.write(json.dumps(row) + "\n"); log.flush()
                if "event" in row:
                    events.append(row)
    completed = time.monotonic() >= deadline and proc.poll() is None
    return completed, events


def menu_default(image, entry, work, installed_alias=False):
    fd = os.open(image, os.O_RDONLY)
    try:
        gpt = m.read_gpt(fd)
    finally:
        os.close(fd)
    conf = work / "loader.conf"
    conf.write_text(f"timeout 1\ndefault {entry}\neditor no\nconsole-mode keep\n")
    m.run("mcopy", "-o", "-i", f"{image}@@{m.extent(gpt['rows'][0])[0]}",
          conf, "::/loader/loader.conf")
    if installed_alias:
        # Test fixture only: retain serial observation on the automatic second
        # boot after boot-control selects openbook-a.conf. Production uses live.
        alias = work / "serial-alias.conf"
        m.run("mcopy", "-i", f"{image}@@{m.extent(gpt['rows'][0])[0]}",
              f"::/loader/entries/{entry}", alias)
        m.run("mcopy", "-o", "-i", f"{image}@@{m.extent(gpt['rows'][0])[0]}",
              alias, "::/loader/entries/openbook-a.conf")


def console_screenshot(work, name):
    # Freeze guest framebuffer writes while QEMU reads the display surface.
    r.qmp(work / "qmp.sock", {"execute": "stop"})
    try:
        # Native PNG avoids the row-by-row yielding PPM export path.
        r.qmp(work / "qmp.sock", {"execute": "screendump",
              "arguments": {"filename": str(work / name), "format": "png"}})
    finally:
        r.qmp(work / "qmp.sock", {"execute": "cont"})


def metadata_key_hashes(image, work, label):
    """Private synthetic VM key blobs only; never include blobs in evidence."""
    fd = os.open(image, os.O_RDONLY)
    try:
        row = next(row for row in m.read_gpt(fd)["rows"] if row["name"] == "metadata")
        offset, length = m.extent(row)
        meta = work / f"{label}-metadata.img"
        with meta.open("xb") as out:
            for at in range(0, length, 4 * m.MIB):
                out.write(m.read_at(fd, offset + at, min(4 * m.MIB, length - at)))
    finally:
        os.close(fd)
    tree = work / f"{label}-metadata-keys"
    tree.mkdir(mode=0o700)
    m.run("debugfs", "-R", f"rdump /vold {tree}", meta)
    files = {str(p.relative_to(tree)): sha(p) for p in tree.rglob("*") if p.is_file()}
    m.require(any("metadata_encryption" in name for name in files), "Expected existing VM metadata encryption keys")
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True, help="Packaged disposable VM USB directory")
    p.add_argument("--tpm-state-from", type=Path, help="Previous disposable VM software TPM; omit for fresh")
    p.add_argument("--fresh", action="store_true")
    p.add_argument("--target-bytes", type=int, default=20 << 30)
    p.add_argument("--android-qemu", required=True, help="ISA-compatible QEMU for Ruby")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seconds", type=int, default=760)
    p.add_argument("--cancel", action="store_true", help="Reject a wrong typed confirmation; do not proceed to Android")
    p.add_argument("--console-smoke", action="store_true", help="Capture the normal console UI and cancel with keyboard input")
    a = p.parse_args()
    m.require(not (a.cancel and a.console_smoke), "Choose one cancellation mode")
    m.require(a.fresh != bool(a.tpm_state_from), "Fresh needs a new TPM; migration needs an existing TPM")
    m.require(20 << 30 <= a.target_bytes <= 2_000_000_000_000, "Target size outside test bounds")
    m.require(not (a.cancel or a.console_smoke) or a.target_bytes == 20 << 30,
              "Cancellation uses the bounded 20 GiB fixture")
    m.require(Path("/.dockerenv").exists(), "Run inside inst-docker.sh; never pass a physical device")
    m.require(30 <= a.seconds <= 1800, "Observation window outside bounds")
    source = a.source / "ruby-live.img"
    m.require(m.stat.S_ISREG(source.lstat().st_mode), "Regular synthetic USB required")
    for path in (a.source, a.out, a.tpm_state_from or Path(".")):
        m.require(not any(c in str(path) for c in ",\n\r"), "Unsafe QEMU path")
    a.out.mkdir(mode=0o700)
    w = a.out.resolve()
    original_sha = sha(source)
    usb = w / "source-usb.img"
    m.run("cp", "--reflink=auto", "--sparse=always", source, usb)
    entry = "ruby-fresh" if a.fresh else "ruby-install"
    menu_default(usb, entry + (".conf" if a.console_smoke else "-serial.conf"), w)
    usb_sha = sha(usb)
    source_keys = {} if a.fresh else metadata_key_hashes(usb, w, "source")
    target = w / "installed.img"
    with target.open("xb") as f:
        f.truncate(a.target_bytes)
    decoy = w / "decoy.img"
    with decoy.open("xb") as f:
        f.write(b"DO NOT MODIFY OTHER DISKS\n")
        f.truncate(32 << 20)
    # Do not read a sparse 1 TB target just to hash known holes.
    target_before = sha(target) if a.cancel or a.console_smoke else None
    decoy_sha = sha(decoy)
    vars_file = w / "vars.fd"
    shutil.copyfile("/usr/share/edk2/x64/OVMF_VARS.4m.fd", vars_file)
    common = ["-machine", "q35", "-smp", "4", "-m", "8192", "-display", "none",
              "-nic", "none", "-monitor", "none", "-no-reboot",
              "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd",
              "-drive", f"if=pflash,format=raw,file={vars_file}",
              "-device", "VGA" if a.console_smoke else "virtio-vga",
              "-device", "qemu-xhci,id=xhci",
              "-device", "usb-kbd,bus=xhci.0"]
    disks = ["-drive", f"file={usb},format=raw,readonly=on,if=none,id=usb",
             "-drive", f"file={target},format=raw,if=none,id=target",
             "-device", "nvme,drive=target,serial=MIGRATIONTEST,bootindex=2",
             "-device", "usb-storage,drive=usb,bootindex=1",
             "-drive", f"file={decoy},format=raw,if=none,id=decoy",
             "-device", "nvme,drive=decoy,serial=KEEPDECOY"]
    cmd = ["qemu-system-x86_64", "-accel", "tcg" if a.console_smoke else "kvm",
           "-cpu", "max" if a.console_smoke else "host", *common, *disks,
           "-smbios", "type=1,product=ROG Zephyrus G14 GA403WR_VM_TEST",
           "-qmp", "unix:qmp.sock,server=on,wait=off",
           "-chardev", "socket,id=serial,path=serial.sock,server=on,wait=off",
           "-serial", "chardev:serial"]
    (w / "install-command.json").write_text(json.dumps(cmd, indent=2) + "\n")
    if a.console_smoke:
        with (w / "install-qemu.log").open("wb") as log:
            proc = subprocess.Popen(cmd, cwd=w, stdout=log, stderr=subprocess.STDOUT)
            try:
                time.sleep(40)
                m.require(proc.poll() is None, "Normal installer boot exited early")
                console_screenshot(w, "console-selection.png")
                enter = {"execute": "send-key", "arguments": {"keys": [{"type": "qcode", "data": "ret"}]}}
                r.qmp(w / "qmp.sock", enter)
                time.sleep(3)
                console_screenshot(w, "console-cancelled.png")
                r.qmp(w / "qmp.sock", enter)
                proc.wait(timeout=20)
            finally:
                stop(proc)
        m.require(proc.returncode == 0 and sha(target) == target_before
                  and sha(usb) == usb_sha and sha(source) == original_sha and sha(decoy) == decoy_sha,
                  "Normal console cancellation failed or a disk changed")
        (w / "result.json").write_text(json.dumps(dict(normal_console_keyboard_cancel=True,
            screenshots_require_visual_review=True, source_unchanged=True,
            target_unchanged=True, decoy_unchanged=True), indent=2) + "\n")
        print("Normal console cancellation passed; visually review both screenshots.")
        return
    text = ""
    sent = set()
    with (w / "install-qemu.log").open("wb") as log, (w / "install-serial.log").open("wb") as serial_log:
        proc = subprocess.Popen(cmd, cwd=w, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 900
            while not (w / "serial.sock").exists():
                m.require(proc.poll() is None and time.monotonic() < deadline, "Installer QEMU did not start")
                time.sleep(0.1)
            with socket.socket(socket.AF_UNIX) as sock:
                sock.settimeout(0.5)
                sock.connect(str(w / "serial.sock"))
                while proc.poll() is None and time.monotonic() < deadline:
                    try:
                        data = sock.recv(65536)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    serial_log.write(data); serial_log.flush()
                    text += data.decode(errors="replace")
                    if "Disk number, or Enter to cancel:" in text and "disk" not in sent:
                        r.screenshot(w / "qmp.sock", w / "installer.ppm")
                        sock.sendall(b"1\n")
                        sent.add("disk")
                    phrase = m.confirmation_phrase("MIGRATIONTEST", a.fresh)
                    if f"Type exactly '{phrase}'" in text and "confirm" not in sent:
                        sock.sendall(b"WRONG SERIAL\n" if a.cancel else (phrase + "\n").encode())
                        sent.add("confirm")
                    if "Press Enter to power off." in text and "poweroff" not in sent:
                        sock.sendall(b"\n")
                        sent.add("poweroff")
                proc.wait(timeout=20)
        finally:
            stop(proc)
    m.require(proc.returncode == 0, "Installer did not shut down cleanly")
    m.require(sha(usb) == usb_sha and sha(source) == original_sha and sha(decoy) == decoy_sha,
              "Source or decoy changed")
    if a.cancel:
        m.require("confirm" in sent and "Cancelled. No disks written." in text and sha(target) == target_before,
                  "Cancellation did not reach confirmation, or target changed")
        (w / "result.json").write_text(json.dumps(dict(cancelled=True, target_unchanged=True,
                                                      source_unchanged=True, decoy_unchanged=True), indent=2) + "\n")
        print("Cancellation passed: source, target and decoy unchanged.")
        return
    m.require("INSTALL VERIFIED. Original USB unchanged." in text
              and "Firmware boot entry created: OpenBook Googlebook." in text and "STOPPED:" not in text,
              "Interactive migration failed; inspect install-serial.log")
    src_fd, dst_fd = os.open(usb, os.O_RDONLY), os.open(target, os.O_RDONLY)
    try:
        source_gpt, target_gpt = m.read_gpt(src_fd), m.read_gpt(dst_fd)
        protected = []
        for old, new in zip(source_gpt["rows"], target_gpt["rows"]):
            m.require(old["partuuid"] != new["partuuid"], "Target identity")
            if a.fresh and new["name"] in ("misc", "metadata", "userdata"):
                start, length = m.extent(new)
                count = min(length, 4 * m.MIB)
                m.require(m.read_at(dst_fd, start, count) == bytes(count)
                          and m.read_at(dst_fd, start + length - count, count) == bytes(count), "Fresh state not reset")
                continue
            m.require(m.extent(old) == m.extent(new), "Target extent")
            if old["name"] != "EFI":
                m.require(m.digest(src_fd, *m.extent(old)) == m.digest(dst_fd, *m.extent(new)), "Copied state differs")
                protected.append(old["name"])
    finally:
        os.close(src_fd); os.close(dst_fd)
    # Source's selected menu is still the installer. Target boots serial logging;
    # attaching both proves the target UUID, not source USB order, selects Android.
    menu_default(target, "ruby-serial-logs.conf", w, installed_alias=True)
    cmd = [a.android_qemu, "-accel", "tcg", "-cpu", "max", *common,
           "-drive", f"file={target},format=raw,if=none,id=target",
           "-device", "nvme,drive=target,serial=MIGRATIONTEST,bootindex=1",
           "-drive", f"file={usb},format=raw,readonly=on,if=none,id=usb",
           "-device", "usb-storage,drive=usb,bootindex=2",
           "-serial", f"file:{w}/android-serial.log", "-qmp", "unix:android-qmp.sock,server=on,wait=off",
           "-chardev", "socket,id=chrtpm,path=tpm.sock", "-tpmdev", "emulator,id=tpm0,chardev=chrtpm",
           "-device", "tpm-crb,tpmdev=tpm0",
           "-audiodev", "none,id=audio0", "-device", "intel-hda", "-device", "hda-duplex,audiodev=audio0"]
    (w / "android-command.json").write_text(json.dumps(cmd, indent=2) + "\n")
    tpm_hashes = {p.name: sha(p) for p in a.tpm_state_from.iterdir() if p.is_file()} if a.tpm_state_from else {}
    start = time.monotonic()
    with r.tpm_backend(w, True, a.tpm_state_from), (w / "android-qemu.log").open("wb") as log:
        proc = subprocess.Popen(cmd, cwd=w, stdout=log, stderr=subprocess.STDOUT)
        try:
            observation_completed, events = observe(proc, w / "android-qmp.sock", a.seconds, w)
            if observation_completed:
                r.screenshot(w / "android-qmp.sock", w / "android.ppm")
        finally:
            stop(proc)
    serial = (w / "android-serial.log").read_text(errors="replace")
    result = dict(schema="openbook-ruby-migration-rehearsal/1", migration_verified=True,
                  firmware_boot_entry_created=True,
                  non_efi_partitions_identical_before_boot=protected,
                  source_unchanged=sha(usb) == usb_sha and sha(source) == original_sha,
                  decoy_unchanged=sha(decoy) == decoy_sha,
                  source_tpm_unchanged=tpm_hashes == ({p.name: sha(p) for p in a.tpm_state_from.iterdir() if p.is_file()} if a.tpm_state_from else {}),
                  target_esp_uuid=target_gpt["rows"][0]["partuuid"],
                  target_uuid_observed=target_gpt["rows"][0]["partuuid"].lower() in serial.lower(),
                  target_partitions_observed=all(text in serial for text in (
                      "metadata -> /dev/block/nvme0n1p7", "super -> /dev/block/nvme0n1p8",
                      "userdata -> /dev/block/nvme0n1p9", "/dev/block/nvme0n1p7 /metadata ext4")),
                  metadata_encryption_files_unchanged=(source_keys == metadata_key_hashes(target, w, "installed")) if not a.fresh else None,
                  fresh_metadata_key_files=len(metadata_key_hashes(target, w, "fresh")) if a.fresh else None,
                  install_mode="fresh" if a.fresh else "preserve-usb-data",
                  target_bytes=a.target_bytes,
                  userdata_partition_bytes=m.extent(target_gpt["rows"][-1])[1],
                  elapsed_s=round(time.monotonic() - start, 1),
                  observation_window_completed=observation_completed,
                  qemu_exit_code=proc.returncode,
                  qmp_events=events,
                  boot_completed=r.boot_completed_reported(serial),
                  runtime_findings=r.runtime_findings(serial),
                  physical_hardware_tested=False, physical_credential_unlock_verified=False)
    (w / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    required = ["source_unchanged", "decoy_unchanged", "source_tpm_unchanged",
                "target_uuid_observed", "target_partitions_observed", "observation_window_completed", "boot_completed"]
    required += ["fresh_metadata_key_files"] if a.fresh else ["metadata_encryption_files_unchanged"]
    m.require(all(result[k] for k in required), "Migration boot did not pass")


if __name__ == "__main__":
    main()
