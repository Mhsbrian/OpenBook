#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded direct-kernel or UEFI/USB observation of local Ruby research images.

Runs inside inst-docker.sh. No network, physical disk, writable input or firmware
NVRAM. Each guest writes a disposable snapshot. The synthetic internal decoy is
hashed before and after. A zero exit means observation completed, not boot passed.
"""
import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("hybrid", HERE / "hybrid-probe.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)


def runtime_findings(serial):
    """Boot completion can coexist with later crashes; retain both facts."""
    return {
        "setup_welcome_activity_seen": "desktop.setupwizard/.user.DesktopWelcomeActivity" in serial,
        "system_server_fatal_signals": sorted(set(line.strip() for line in serial.splitlines()
            if "Fatal signal" in line and "(system_server)" in line)),
        "zygote_exit_events": len(re.findall(r"Service 'zygote' \(pid [0-9]+\) (?:received|exited)", serial)),
        "system_server_execmem_denial_seen": any("execmem" in line and "scontext=u:r:system_server:s0" in line
                                                 for line in serial.splitlines()),
        "mmd_setup_abort_seen": bool(re.search(r"Service 'mmd_setup' \(pid [0-9]+\) received SIGABRT", serial)),
    }


def qmp(path, command):
    with socket.socket(socket.AF_UNIX) as sock:
        sock.settimeout(15)
        sock.connect(str(path))
        stream = sock.makefile("rwb")
        stream.readline()
        for request in ({"execute": "qmp_capabilities"}, command):
            stream.write(json.dumps(request).encode() + b"\n")
            stream.flush()
            while True:
                answer = json.loads(stream.readline())
                if "error" in answer:
                    raise RuntimeError(answer["error"])
                if "return" in answer:
                    break


def screenshot(path, target):
    qmp(path, {"execute": "screendump", "arguments": {"filename": str(target)}})


@contextmanager
def tpm_backend(w, enabled):
    if not enabled:
        yield
        return
    (w / "tpm-state").mkdir()
    with (w / "swtpm.log").open("wb") as log:
        proc = subprocess.Popen(["swtpm", "socket", "--tpm2", "--tpmstate", "dir=tpm-state",
                                 "--ctrl", "type=unixio,path=tpm.sock", "--flags", "not-need-init"],
                                cwd=w, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 10
            while not (w / "tpm.sock").exists():
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("Software TPM did not become ready; see swtpm.log")
                time.sleep(0.05)
            yield
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--qemu", default="qemu-system-x86_64")
    p.add_argument("--accel", choices=("kvm", "tcg"), default="kvm")
    p.add_argument("--uefi-usb", action="store_true")
    p.add_argument("--tpm", action="store_true", help="Use a new disposable software TPM over CRB; no hardware attestation claim")
    p.add_argument("--wake-display", action="store_true", help="After the observation, capture, send the wake key, wait 15 seconds and capture again")
    p.add_argument("--timeout", type=int, default=180, choices=range(30, 1801), metavar="30..1800")
    a = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Run through inst-docker.sh")
    qemu = shutil.which(a.qemu)
    if not qemu:
        p.error("QEMU executable not found")
    qemu_sha = h.audit.sha(Path(qemu))
    src = a.input.resolve(strict=True)
    disk = src / ("ruby-live.img" if a.uefi_usb else "probe.img")
    if not disk.is_file() or disk.is_symlink() or any(c in str(src) for c in ",\n\r"):
        p.error("Expected a regular image under an input path without QEMU delimiters")
    w = h.new_output(a.out, (src,))
    before = h.audit.sha(disk)
    guest_disk = disk
    if a.uefi_usb:
        # Change only the menu default in a private copy to exercise the serial
        # diagnostic entry shipped in the actual candidate. Retain source bytes.
        guest_disk = w / "usb-test.img"
        h.run("cp", "--reflink=auto", "--sparse=always", disk, guest_disk)
        manifest = json.loads((src / "manifest.json").read_text())
        esp = manifest["gpt"][0]
        if esp["name"] != "EFI" or manifest["image_sha256"] != before:
            p.error("Live image manifest does not match the input")
        (w / "loader.conf").write_text("timeout 1\ndefault ruby-serial.conf\neditor no\nconsole-mode keep\n")
        h.run("mcopy", "-o", "-i", f"{guest_disk}@@{esp['first_lba'] * 512}", w / "loader.conf", "::/loader/loader.conf")
    guest_sha = h.audit.sha(guest_disk)
    # Linux AF_UNIX has a short pathname limit; use the new workdir as cwd.
    cmd = [a.qemu, "-machine", "q35", "-accel", a.accel, "-cpu", "host" if a.accel == "kvm" else "max",
           "-smp", "4", "-m", "8192", "-display", "none", "-nic", "none",
           "-serial", f"file:{w}/serial.log", "-monitor", "none", "-no-reboot",
           "-qmp", "unix:qmp.sock,server=on,wait=off",
           "-drive", f"file={guest_disk},format=raw,if=none,id=d0,snapshot=on", "-device", "virtio-vga"]
    decoy = None
    if a.uefi_usb:
        shutil.copyfile("/usr/share/edk2/x64/OVMF_VARS.4m.fd", w / "vars.fd")
        cmd += ["-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd",
                "-drive", f"if=pflash,format=raw,file={w}/vars.fd",
                "-device", "qemu-xhci,id=xhci", "-device", "usb-storage,drive=d0,bootindex=1",
                "-device", "usb-kbd,bus=xhci.0", "-device", "usb-tablet,bus=xhci.0"]
        # Same names, different UUIDs; no physical disk is passed to QEMU.
        parts = [(n, 2 * h.MiB, h.gpt.LINUX_DATA, None)
                 for n in ("misc", "boot_a", "init_boot_a", "vendor_boot_a", "vbmeta_a", "metadata", "super", "userdata")]
        decoy = w / "internal-decoy.img"
        h.gpt.Gpt(parts, str(w)).write(str(decoy))
        decoy_sha = h.audit.sha(decoy)
        cmd += ["-drive", f"file={decoy},format=raw,if=none,id=internal",
                "-device", "nvme,drive=internal,serial=SYNTHETICINTERNAL"]
    else:
        cmd += ["-kernel", str(src / "boot/kernel"), "-initrd", str(src / "initrd.img"),
                "-append", "bootconfig console=ttyS0,115200 8250.nr_uarts=1 earlycon=uart8250,io,0x3f8,115200 printk.devkmsg=on panic=-1",
                "-device", "nvme,drive=d0,serial=RUBYPROBE,addr=0x4"]
    if a.tpm:
        cmd += ["-chardev", "socket,id=chrtpm,path=tpm.sock", "-tpmdev", "emulator,id=tpm0,chardev=chrtpm",
                "-device", "tpm-crb,tpmdev=tpm0"]
    (w / "command.json").write_text(json.dumps(cmd, indent=2) + "\n")
    start = time.monotonic()
    with tpm_backend(w, a.tpm), (w / "qemu.log").open("wb") as log:
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=w)
        elapsed = False
        screen_error = None
        try:
            proc.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            elapsed = True
            try:
                screenshot(w / "qmp.sock", w / "screen.ppm")
                if a.wake_display:
                    qmp(w / "qmp.sock", {"execute": "send-key", "arguments": {
                        "keys": [{"type": "qcode", "data": "wake"}], "hold-time": 100}})
                    time.sleep(15)
                    screenshot(w / "qmp.sock", w / "screen-after-wake.ppm")
            except (OSError, ValueError, RuntimeError) as exc:
                screen_error = str(exc)
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    serial = (w / "serial.log").read_text(errors="replace") if (w / "serial.log").exists() else ""
    result = {"schema": "openbook-ruby-observation/1", "accel": a.accel, "uefi_usb": a.uefi_usb,
              "software_tpm": a.tpm,
              "qemu_sha256": qemu_sha,
              "qemu_exit": proc.returncode, "elapsed_s": round(time.monotonic() - start, 1),
              "observation_window_elapsed": elapsed, "input_sha256": before,
              "input_unchanged": h.audit.sha(disk) == before,
              "guest_disk_unchanged": h.audit.sha(guest_disk) == guest_sha,
              "test_entry": "serial" if a.uefi_usb else "direct kernel",
              "wake_display_requested": a.wake_display,
              "screenshots": [f.name for f in sorted(w.glob("screen*.ppm"))],
              "screenshot_error": screen_error,
              "decoy_unchanged": h.audit.sha(decoy) == decoy_sha if decoy else None,
              "second_stage_init": "init second stage started" in serial,
              "diagnostics_completed": "OPENBOOK_RUBY_PROBE_END" in serial,
              "boot_completed_reported": "OPENBOOK_RUBY_BOOT_COMPLETED=1" in serial,
              "kernel_panic": "Kernel panic" in serial,
              "sigill": "signal 4 (SIGILL)" in serial,
              "runtime_findings": runtime_findings(serial),
              "scope": "Observation only. Review original logs; no hardware or installation claim."}
    (w / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if not result["input_unchanged"] or not result["guest_disk_unchanged"] or result["decoy_unchanged"] is False or (not elapsed and proc.returncode):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
