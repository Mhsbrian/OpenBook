#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reboot a disposable fresh-install fixture and verify its new encrypted state.

Regular sparse files only; no physical devices, owner data or networking.
"""
import argparse
import errno
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

spec = importlib.util.spec_from_file_location("uq", Path(__file__).with_name("installed-update-qemu.py"))
uq = importlib.util.module_from_spec(spec); spec.loader.exec_module(uq)
q = uq.q


def sparse_digest(path):
    """Hash logical size, data-range positions and their contents; not a raw SHA."""
    q.m.require(path.is_file() and not path.is_symlink(), "Regular fixture required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        size = os.fstat(fd).st_size
        sha = q.m.hashlib.sha256(b"openbook-sparse-map/1" + struct.pack("<Q", size))
        at = 0
        while at < size:
            try:
                start = os.lseek(fd, at, os.SEEK_DATA)
            except OSError as e:
                if e.errno == errno.ENXIO: break
                raise
            stop = min(size, os.lseek(fd, start, os.SEEK_HOLE))
            sha.update(struct.pack("<QQ", start, stop-start))
            for offset in range(start, stop, 4*q.m.MIB):
                sha.update(q.m.read_at(fd, offset, min(4*q.m.MIB, stop-offset)))
            at = stop
        return sha.hexdigest()
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--first-run", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seconds", type=int, default=300)
    a = p.parse_args()
    q.m.require(Path("/.dockerenv").exists(), "Container only")
    q.m.require(120 <= a.seconds <= 900, "Bounded observation required")
    first = json.loads((a.first_run/"result.json").read_text())
    q.m.require(first["install_mode"] == "fresh" and first["boot_completed"], "Requires a booted fresh fixture")
    source = a.first_run/"installed.img"
    before = sparse_digest(source)
    a.out.mkdir(mode=0o700); w = a.out.resolve()
    disk = w/"installed.img"
    q.m.run("cp", "--reflink=auto", "--sparse=always", source, disk)
    keys = q.metadata_key_hashes(disk, w, "before")
    identity = uq.boot_identity(disk, w, "before")
    # The production openbook-a entry boots without a serial console. Keep the
    # boot-control-selected entry name, but instrument this disposable clone
    # with the existing serial initrd. Otherwise a successful graphical boot
    # looks like missing boot evidence to the serial-only checker.
    with disk.open("rb") as f:
        gpt = q.m.read_gpt(f.fileno())
    esp = f"{disk}@@{q.m.extent(gpt['rows'][0])[0]}"
    q.m.run("mcopy", "-i", esp, "::/loader/entries/openbook-a.conf", w/"original-default.conf")
    q.m.run("mcopy", "-i", esp, "::/loader/entries/ruby-serial-logs.conf", w/"serial-default.conf")
    q.m.run("mcopy", "-o", "-i", esp, w/"serial-default.conf", "::/loader/entries/openbook-a.conf")
    shutil.copyfile(a.first_run/"vars.fd", w/"vars.fd")
    old = str(a.first_run.resolve())
    cmd = [arg.replace(old + "/", str(w) + "/") for arg in json.loads((a.first_run/"android-command.json").read_text())]
    # Do not attach the USB on the second boot: the SSD must stand alone.
    drive = next(i for i, arg in enumerate(cmd) if arg.startswith("file=") and "id=usb" in arg)
    del cmd[drive-1:drive+1]
    dev = next(i for i, arg in enumerate(cmd) if arg.startswith("usb-storage,drive=usb"))
    del cmd[dev-1:dev+1]
    (w/"command.json").write_text(json.dumps(cmd, indent=2)+"\n")
    with q.r.tpm_backend(w, True, a.first_run/"tpm-state"), (w/"qemu.log").open("wb") as log:
        proc = subprocess.Popen(cmd, cwd=w, stdout=log, stderr=subprocess.STDOUT)
        try:
            completed, events = q.observe(proc, w/"android-qmp.sock", a.seconds, w)
            if completed: q.r.screenshot(w/"android-qmp.sock", w/"android.ppm")
        finally:
            q.stop(proc)
    text = (w/"android-serial.log").read_text(errors="replace")
    result = dict(schema="openbook-fresh-reboot/1", source_sparse_map_unchanged=sparse_digest(source)==before,
        observation_completed=completed, boot_completed=q.r.boot_completed_reported(text),
        metadata_key_files=len(keys), metadata_keys_unchanged=keys==q.metadata_key_hashes(disk,w,"after"),
        boot_identity_unchanged=identity==uq.boot_identity(disk,w,"after"),
        nvme_selection=uq.nvme_selection(text), runtime_findings=q.r.runtime_findings(text),
        qmp_events=events, physical_hardware_tested=False, usb_attached=False,
        serial_default_entry_for_observation=True)
    (w/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
    q.m.require(all(result[k] for k in ("source_sparse_map_unchanged","observation_completed",
        "boot_completed","metadata_keys_unchanged","boot_identity_unchanged","nvme_selection")), "Fresh reboot failed")


if __name__ == "__main__":
    main()
