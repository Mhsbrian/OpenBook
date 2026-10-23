#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rehearse the stick's two-slot fresh install end to end, then boot what it installed.

1. Boot the packaged USB image's "Fresh install Googlebook to SSD (two slots)"
   entry (its VM serial variant) with a blank NVMe of --target-bytes and a decoy
   NVMe. The serial driver types the disk number and the exact
   "FRESH ERASE <serial>" phrase, as a person would.
2. Compare the installed NVMe with the hardware reference image the plan was
   built from: every byte outside userdata's interior must be identical.
3. Boot the installed NVMe with ab-qemu.py's nine A/B checks. Test fixture only:
   on a reflink copy, the installed entry gets a serial console so the VM can be
   observed; production keeps the hardware entry.

Container only (scripts/installer/inst-docker.sh). Regular image files, no network.
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


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = load("migration", "migrate.py")
mq = load("migration_qemu", "migration-qemu.py")
SERIAL = "MIGRATIONTEST"
VM_OPTIONS = "console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on"


def install(usb, target, decoy, w, seconds):
    vars_file = w / "vars.fd"
    shutil.copyfile("/usr/share/edk2/x64/OVMF_VARS.4m.fd", vars_file)
    cmd = ["qemu-system-x86_64", "-accel", "kvm", "-cpu", "host", "-machine", "q35", "-smp", "4", "-m", "8192",
           "-display", "none", "-nic", "none", "-monitor", "none", "-no-reboot",
           "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd",
           "-drive", f"if=pflash,format=raw,file={vars_file}",
           "-device", "virtio-vga", "-device", "qemu-xhci,id=xhci", "-device", "usb-kbd,bus=xhci.0",
           "-drive", f"file={usb},format=raw,readonly=on,if=none,id=usb",
           # NVMe write-zeroes become holes, so the sparse 1 TB target stays small on the host.
           "-drive", f"file={target},format=raw,if=none,id=target,discard=unmap,detect-zeroes=unmap",
           "-device", f"nvme,drive=target,serial={SERIAL},bootindex=2",
           "-device", "usb-storage,drive=usb,bootindex=1",
           "-drive", f"file={decoy},format=raw,if=none,id=decoy",
           "-device", "nvme,drive=decoy,serial=KEEPDECOY",
           "-smbios", "type=1,product=ROG Zephyrus G14 GA403WR_VM_TEST",
           "-qmp", "unix:qmp.sock,server=on,wait=off",
           "-chardev", "socket,id=serial,path=serial.sock,server=on,wait=off", "-serial", "chardev:serial"]
    (w / "install-command.json").write_text(json.dumps(cmd, indent=2) + "\n")
    text, sent = "", set()
    phrase = m.confirmation_phrase(SERIAL, fresh=True)
    with (w / "install-qemu.log").open("wb") as log, (w / "install-serial.log").open("wb") as serial_log:
        proc = subprocess.Popen(cmd, cwd=w, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + seconds
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
                        sock.sendall(b"1\n"); sent.add("disk")
                    if f"Type exactly '{phrase}'" in text and "confirm" not in sent:
                        sock.sendall((phrase + "\n").encode()); sent.add("confirm")
                    if "Press Enter to power off." in text and "poweroff" not in sent:
                        sock.sendall(b"\n"); sent.add("poweroff")
                proc.wait(timeout=30)
        finally:
            mq.stop(proc)
    return proc.returncode, text, sent


def compare(target, reference, layout):
    """Regions outside userdata's interior that differ between the installed disk and the reference."""
    size = os.path.getsize(target)
    regions = [(0, 34 * 512), (size - 33 * 512, 33 * 512)]
    for r in layout:
        if r["name"] == "userdata":
            regions += [(r["offset"], 4 * m.MIB), (r["offset"] + r["length"] - 4 * m.MIB, 4 * m.MIB)]
        else:
            regions.append((r["offset"], r["length"]))
    t, ref = os.open(target, os.O_RDONLY), os.open(reference, os.O_RDONLY)
    try:
        return [dict(offset=o, length=n) for o, n in regions if m.digest(t, o, n) != m.digest(ref, o, n)], \
            sum(n for _, n in regions)
    finally:
        os.close(t); os.close(ref)


def serial_entry(disk, esp_offset, w):
    """Fixture: add the VM serial console to the installed entry on a copy."""
    entry = w / "openbook-a.conf"
    m.run("mcopy", "-i", f"{disk}@@{esp_offset}", "::/loader/entries/openbook-a.conf", entry)
    lines = entry.read_text().splitlines()
    m.require(sum(l.startswith("options ") for l in lines) == 1, "Unexpected installed entry")
    entry.write_text("\n".join(l + f" {VM_OPTIONS}" if l.startswith("options ") else l for l in lines) + "\n")
    m.run("mcopy", "-o", "-i", f"{disk}@@{esp_offset}", entry, "::/loader/entries/openbook-a.conf")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", type=Path, required=True, help="packaged USB directory (ruby-live.img)")
    p.add_argument("--reference", type=Path, required=True, help="hardware A/B reference image dir")
    p.add_argument("--target-bytes", type=int, default=1000204886016)
    p.add_argument("--android-qemu", type=Path, required=True)
    p.add_argument("--bootsync", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--install-seconds", type=int, default=2400)
    p.add_argument("--boot-seconds", type=int, default=900)
    a = p.parse_args()
    m.require(Path("/.dockerenv").exists(), "Run inside inst-docker.sh; never pass a physical device")
    os.umask(0o077)
    a.out.mkdir(mode=0o700)
    w = a.out.resolve()
    source = a.source / "ruby-live.img"
    m.require(m.stat.S_ISREG(source.lstat().st_mode), "Regular packaged USB image required")
    original = mq.sha(source)
    usb = w / "source-usb.img"
    m.run("cp", "--reflink=auto", "--sparse=always", source, usb)
    mq.menu_default(usb, "ruby-fresh-serial.conf", w)  # select the two-slot entry; the image itself is unchanged
    usb_sha = mq.sha(usb)
    target = w / "installed.img"
    with target.open("xb") as f:
        f.truncate(a.target_bytes)
    decoy = w / "decoy.img"
    with decoy.open("xb") as f:
        f.write(b"DO NOT MODIFY OTHER DISKS\n")
        f.truncate(32 << 20)
    decoy_sha = mq.sha(decoy)
    start = time.monotonic()
    rc, text, sent = install(usb, target, decoy, w, a.install_seconds)
    install_s = round(time.monotonic() - start, 1)
    installed = all(s in text for s in ("Fresh Googlebook install (two slots)", "Installing two slots",
                                        "INSTALL VERIFIED. Original USB unchanged.",
                                        "Firmware boot entry created: OpenBook Googlebook.")) and "STOPPED:" not in text
    reference = json.loads((a.reference / "result.json").read_text())
    fd = os.open(target, os.O_RDONLY)
    try:
        gpt = m.read_gpt(fd, names=tuple(r["name"] for r in reference["layout"])) if installed else None
    finally:
        os.close(fd)
    layout = [dict(name=r["name"], offset=r["first_lba"] * 512, length=(r["last_lba"] - r["first_lba"] + 1) * 512)
              for r in gpt["rows"]] if gpt else []
    diffs, compared = compare(target, a.reference / "disk.img", layout) if gpt else (None, 0)
    unchanged = mq.sha(usb) == usb_sha and mq.sha(source) == original and mq.sha(decoy) == decoy_sha
    record = dict(schema="openbook-ruby-ab-install-rehearsal/1", installer_exit=rc, install_s=install_s,
                  prompts_answered=sorted(sent), installed_and_verified=installed, target_bytes=a.target_bytes,
                  layout_matches_reference=layout == [dict(name=r["name"], offset=r["offset"], length=r["length"])
                                                      for r in reference["layout"]] if gpt else False,
                  bytes_compared=compared, differing_regions=diffs,
                  identical_to_reference_outside_userdata_interior=diffs == [] if gpt else False,
                  usb_and_decoy_unchanged=unchanged)
    (w / "install-result.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)
    m.require(rc == 0 and installed and sent == {"disk", "confirm", "poweroff"}
              and record["identical_to_reference_outside_userdata_interior"]
              and record["layout_matches_reference"] and unchanged, "Two-slot install rehearsal failed")
    # Boot what was installed.
    boot = w / "boot-image"
    boot.mkdir()
    m.run("cp", "--reflink=auto", "--sparse=always", target, boot / "disk.img")
    serial_entry(boot / "disk.img", layout[0]["offset"], w)
    (boot / "result.json").write_text(json.dumps(dict(reference, layout=layout, installed_by="ab-install-qemu.py"),
                                                 indent=2) + "\n")
    subprocess.run(["python3", str(HERE / "ab-qemu.py"), "--image-dir", str(boot), "--qemu", str(a.android_qemu),
                    "--bootsync", str(a.bootsync), "--out", str(w / "boot-run"), "--seconds", str(a.boot_seconds)],
                   check=False)
    booted = json.loads((w / "boot-run" / "result.json").read_text())
    record.update(boot_checks=booted["checks"], boot_passed=booted["passed"], boot_elapsed_s=booted["elapsed_s"])
    (w / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(dict(boot_passed=booted["passed"], checks=booted["checks"]), indent=2))
    m.require(booted["passed"], "Installed disk did not pass the A/B boot checks")


if __name__ == "__main__":
    main()
