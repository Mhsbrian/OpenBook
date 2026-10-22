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


def boot_completed_reported(text):
    # A parsed init trigger mentioning sys.boot_completed=1 is not a property
    # observation. Only accept complete diagnostic output lines.
    return bool(re.search(
        r"(?m)^(?:OPENBOOK_RUBY_BOOT_COMPLETED=1|\[sys.boot_completed\]: \[1\]|sys.boot_completed=1)\r?$", text))


def runtime_findings(serial):
    """Boot completion can coexist with later crashes; retain both facts."""
    return {
        "setup_welcome_activity_seen": "desktop.setupwizard/.user.DesktopWelcomeActivity" in serial,
        "system_server_fatal_signals": sorted(set(line.strip() for line in serial.splitlines()
            if "Fatal signal" in line and "(system_server)" in line)),
        "zygote_exit_events": len(set(re.findall(r"Service 'zygote' \(pid [0-9]+\) (?:received|exited)", serial))),
        "system_server_execmem_denial_seen": any("execmem" in line and "scontext=u:r:system_server:s0" in line
                                                 for line in serial.splitlines()),
        "mmd_setup_abort_seen": bool(re.search(r"Service 'mmd_setup' \(pid [0-9]+\) received SIGABRT", serial)),
        "camera_provider_running_reported": bool(re.search(
            r"(?m)^init\.svc\.vendor\.camera\.provider-ext=running\r?$", serial)),
        "camera_provider_registered_reported": bool(re.search(
            r"(?m)^Service android\.hardware\.camera\.provider\.ICameraProvider/external/0: found\r?$", serial)),
        "camera_device_counts_reported": sorted(set(map(int, re.findall(
            r"(?m)^Number of camera devices: ([0-9]+)\r?$", serial)))),
        "camera_provider_abort_seen": bool(re.search(
            r"Service 'vendor\.camera\.provider-ext' \(pid [0-9]+\) received SIGABRT", serial)),
        "camera_fmq_test_exit_statuses": sorted(set(map(int, re.findall(
            r"Service 'openbook\.camera-fmq-test' \(pid [0-9]+\) exited with status ([0-9]+)", serial)))),
        "camera_buffer_test_exit_statuses": sorted(set(map(int, re.findall(
            r"Service 'openbook\.camera-buffer-test' \(pid [0-9]+\) exited with status ([0-9]+)", serial)))),
        "camera_buffer_test_abort_seen": bool(re.search(
            r"Service 'openbook\.camera-buffer-test' \(pid [0-9]+\) received SIGABRT", serial)),
        "camera_fmq_tmpfs_denial_seen": any("avc:" in line and "denied" in line and
            "scontext=u:r:hal_camera_default:s0" in line and 'name="memfd:MessageQueue"' in line
            for line in serial.splitlines()),
        "camera_provider_default_label_denial_seen": any(
            "avc:" in line and "denied" in line and
            "name=android.hardware.camera.provider.ICameraProvider/external/0" in line and
            "tcontext=u:object_r:default_android_service:s0" in line for line in serial.splitlines()),
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
def tpm_backend(w, enabled, state_from=None):
    if not enabled:
        yield
        return
    if state_from:
        shutil.copytree(state_from, w / "tpm-state")
    else:
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
    p.add_argument("--usb-logs", action="store_true", help="Select shipped serial+USB logger; retain writes in the private USB copy")
    p.add_argument("--usb-log-entry", choices=("serial-logs", "logs", "safe-logs", "sleep-diag-serial"), default="serial-logs")
    p.add_argument("--tpm", action="store_true", help="Use a new disposable software TPM over CRB; no hardware attestation claim")
    p.add_argument("--tpm-state-from", type=Path, help="Copy a previous disposable VM's TPM state for an update rehearsal; never G14 data")
    p.add_argument("--audio", action="store_true", help="Emulated HDA codec with a silent input and no host audio device")
    p.add_argument("--wake-display", action="store_true", help="After the observation, capture, send the wake key, wait 15 seconds and capture again")
    p.add_argument("--timeout", type=int, default=180, choices=range(30, 1801), metavar="30..1800")
    a = p.parse_args()
    if a.usb_logs and not a.uefi_usb:
        p.error("--usb-logs requires --uefi-usb")
    if a.usb_log_entry != "serial-logs" and not a.usb_logs:
        p.error("--usb-log-entry requires --usb-logs")
    tpm_hashes = None
    if a.tpm_state_from:
        if not (a.tpm and a.usb_logs) or not a.tpm_state_from.is_dir() or a.tpm_state_from.is_symlink():
            p.error("TPM reuse requires --tpm --usb-logs and a regular state directory")
        state_files = list(a.tpm_state_from.iterdir())
        if not state_files or any(not f.is_file() or f.is_symlink() for f in state_files):
            p.error("TPM state must contain regular files only")
        tpm_hashes = {f.name: h.audit.sha(f) for f in state_files}
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
    w = h.new_output(a.out, (src, *([a.tpm_state_from.resolve()] if a.tpm_state_from else [])))
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
        entry = f"ruby-{a.usb_log_entry}.conf" if a.usb_logs else "ruby-serial.conf"
        (w / "loader.conf").write_text(f"timeout 1\ndefault {entry}\neditor no\nconsole-mode keep\n")
        h.run("mcopy", "-o", "-i", f"{guest_disk}@@{esp['first_lba'] * 512}", w / "loader.conf", "::/loader/loader.conf")
    guest_sha = h.audit.sha(guest_disk)
    prior_sessions = set()
    if a.usb_logs:
        # A preserved disk already has complete.txt from earlier boots. Do not
        # count those as evidence of this observation's boot or capture success.
        prior = w / "prior-logs"
        prior_copy = subprocess.run(["mcopy", "-s", "-i", f"{guest_disk}@@{esp['first_lba'] * 512}",
                                    "::/openbook/logs", str(prior)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if a.tpm_state_from and prior_copy.returncode:
            raise ValueError("Restored-state rehearsal must inventory prior logs before boot")
        if prior.is_dir():
            prior_sessions = {p.name for p in prior.iterdir()}
    # Linux AF_UNIX has a short pathname limit; use the new workdir as cwd.
    cmd = [a.qemu, "-machine", "q35", "-accel", a.accel, "-cpu", "host" if a.accel == "kvm" else "max",
           "-smp", "4", "-m", "8192", "-display", "none", "-nic", "none",
           "-serial", f"file:{w}/serial.log", "-monitor", "none", "-no-reboot",
           "-qmp", "unix:qmp.sock,server=on,wait=off",
           "-drive", f"file={guest_disk},format=raw,if=none,id=d0,snapshot={'off' if a.usb_logs else 'on'}", "-device", "virtio-vga"]
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
        recipe = json.loads((src / "recipe.json").read_text())
        vendor_cmdline = h.platform_cmdline(recipe.get("vendor_cmdline", ""))
        cmd += ["-kernel", str(src / "boot/kernel"), "-initrd", str(src / "initrd.img"),
                "-append", vendor_cmdline + " bootconfig console=ttyS0,115200 8250.nr_uarts=1 earlycon=uart8250,io,0x3f8,115200 printk.devkmsg=on panic=-1",
                "-device", "nvme,drive=d0,serial=RUBYPROBE,addr=0x4"]
    if a.tpm:
        cmd += ["-chardev", "socket,id=chrtpm,path=tpm.sock", "-tpmdev", "emulator,id=tpm0,chardev=chrtpm",
                "-device", "tpm-crb,tpmdev=tpm0"]
    if a.audio:
        cmd += ["-audiodev", "none,id=audio0", "-device", "intel-hda", "-device", "hda-duplex,audiodev=audio0"]
    (w / "command.json").write_text(json.dumps(cmd, indent=2) + "\n")
    start = time.monotonic()
    with tpm_backend(w, a.tpm, a.tpm_state_from), (w / "qemu.log").open("wb") as log:
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
    logs_rc = None
    if a.usb_logs:
        logs_rc = subprocess.run(["mcopy", "-s", "-i", f"{guest_disk}@@{esp['first_lba'] * 512}",
                                  "::/openbook/logs", str(w / "saved-logs")]).returncode
    saved_files = [f for f in sorted((w / "saved-logs").rglob("*")) if f.is_file()
                   and f.relative_to(w / "saved-logs").parts[0] not in prior_sessions]
    # USB capture is bounded to ten minutes; retain later serial evidence too.
    observed = serial + "\n" + "\n".join(f.read_text(errors="replace") for f in saved_files)
    result = {"schema": "openbook-ruby-observation/1", "accel": a.accel, "uefi_usb": a.uefi_usb,
              "software_tpm": a.tpm,
              "software_tpm_restored": bool(a.tpm_state_from),
              "source_tpm_unchanged": ({f.name: h.audit.sha(f) for f in a.tpm_state_from.iterdir()} == tpm_hashes)
                                      if a.tpm_state_from else None,
              "prior_log_sessions_excluded": len(prior_sessions),
              "emulated_audio": a.audio,
              "qemu_sha256": qemu_sha,
              "qemu_exit": proc.returncode, "elapsed_s": round(time.monotonic() - start, 1),
              "observation_window_elapsed": elapsed, "input_sha256": before,
              "input_unchanged": h.audit.sha(disk) == before,
              "guest_disk_unchanged": h.audit.sha(guest_disk) == guest_sha,
              "test_entry": a.usb_log_entry if a.usb_logs else "serial" if a.uefi_usb else "direct kernel",
              "persistent_usb_logs": a.usb_logs,
              "logs_readback_exit": logs_rc,
              "saved_log_files": [str(f.relative_to(w)) for f in saved_files],
              "usb_capture_finished": any(f.name == "complete.txt" for f in saved_files),
              "wake_display_requested": a.wake_display,
              "screenshots": [f.name for f in sorted(w.glob("screen*.ppm"))],
              "screenshot_error": screen_error,
              "decoy_unchanged": h.audit.sha(decoy) == decoy_sha if decoy else None,
              "second_stage_init": "init second stage started" in observed,
              "diagnostics_completed": "OPENBOOK_RUBY_PROBE_END" in observed or "RUBY_ANDROID_LOG_END" in observed,
              "boot_completed_reported": boot_completed_reported(observed),
              "kernel_panic": "Kernel panic" in observed,
              "sigill": "signal 4 (SIGILL)" in observed,
              "runtime_findings": runtime_findings(observed),
              "scope": "Observation only. Review original logs; no hardware or installation claim."}
    (w / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if not result["input_unchanged"] or result["source_tpm_unchanged"] is False or (not a.usb_logs and not result["guest_disk_unchanged"]) or result["decoy_unchanged"] is False or (not elapsed and proc.returncode) or (a.usb_logs and logs_rc):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
