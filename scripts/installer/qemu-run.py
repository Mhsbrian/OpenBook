#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Boot a disk image in QEMU/KVM + OVMF as a USB stick (xHCI + usb-storage), optionally with a second disk on NVMe
playing the laptop's internal drive. Logs the serial console, can type into it, takes screenshots, and stops on a
timeout. Runs inside the openbook-installer container. Image files only; never a host block device.

usage: qemu-run.py --usb IMG [--nvme IMG] --out DIR [--timeout S] [--expect STEPS.json] [--shot SECONDS ...]
                   [--mem MiB] [--smp N] [--vars FILE] [--pause-on-reset] [--vga MODEL] [--gpu DEVICE]
                   [--usb-input] [--tpm] [--detach-test-device] [--trace] [--audio WAV] [--extra-usb IMG]

STEPS.json: [{"wait": "regex", "timeout": 120}, {"send": "text\\n"}, {"shot": "name"}, ...]; steps run in order
on the serial stream; "shot" saves the screen as DIR/shot-<name>.png at that point. The run ends when the steps
are done (plus --linger seconds), the guest powers off, or --timeout hits.
Writes DIR/serial.log, DIR/qemu.log, DIR/result.json and DIR/shot-<t>.png.
"""
import argparse
import json
import os
import re
import shutil
import socket
import stat
import struct
import subprocess
import sys
import time
import zlib

OVMF_CODE = "/usr/share/edk2/x64/OVMF_CODE.4m.fd"
OVMF_VARS = "/usr/share/edk2/x64/OVMF_VARS.4m.fd"


def ppm_to_png(ppm, png):
    data = open(ppm, "rb").read()
    parts, i = [], 0
    while len(parts) < 4:  # magic, width, height, maxval (no comments in QEMU's output)
        while data[i:i + 1].isspace():
            i += 1
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        parts.append(data[i:j])
        i = j
    i += 1
    w, h = int(parts[1]), int(parts[2])
    px = data[i:i + w * h * 3]
    raw = b"".join(b"\0" + px[y * w * 3:(y + 1) * w * 3] for y in range(h))
    chunk = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    open(png, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
                          chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usb", required=True)
    ap.add_argument("--nvme")
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--linger", type=int, default=3)
    ap.add_argument("--expect")
    ap.add_argument("--shot", type=float, nargs="*", default=[])
    ap.add_argument("--mem", type=int, default=4096)
    ap.add_argument("--smp", type=int, default=4)
    ap.add_argument("--vars", help="OVMF vars file to use (kept, so NVRAM persists across runs)")
    ap.add_argument("--pause-on-reset", action="store_true")
    ap.add_argument("--vga", default="std", help="QEMU -vga model; 'none' leaves the serial port as the only console")
    ap.add_argument("--gpu", help="display device instead of -vga, e.g. virtio-vga,xres=1920,yres=1200")
    ap.add_argument("--usb-input", action="store_true", help="add a USB keyboard and tablet on the xHCI bus")
    ap.add_argument("--tpm", action="store_true",
                    help="TPM 2.0 on CRB (ACPI MSFT0101, like a Pluton/fTPM laptop), backed by swtpm in DIR/tpm")
    ap.add_argument("--detach-test-device", action="store_true",
                    help="add a virtio-rng (1af4) behind a PCIe root port, a stand-in for the dGPU detach test")
    ap.add_argument("--trace", action="store_true", help="log CPU resets and guest errors to DIR/qemu-debug.log")
    ap.add_argument("--audio", help="an ICH9 HDA controller with QEMU's duplex codec; what the guest plays goes to "
                    "this WAV file (48 kHz stereo); the guest records silence")
    ap.add_argument("--extra-usb", help="a second USB disk (image file), e.g. test files for the guest")
    args = ap.parse_args()

    for img in (args.usb, args.nvme, args.extra_usb):  # image files only: refuse anything that is a real block device
        if img and (not os.path.isfile(img) or stat.S_ISBLK(os.stat(img).st_mode)):
            sys.exit(f"refusing {img}: not a regular image file")
    os.makedirs(args.out, exist_ok=True)
    # Serial console on a FIFO pair (-chardev pipe). With a socket chardev, GBL's per-character ConOut writes
    # failed on OVMF (TerminalDxe returned an error) and GBL panicked in its own error printer; a FIFO or a file
    # does not show that.
    ser_base, mon_path = f"{args.out}/serial", f"{args.out}/monitor.sock"
    for p in (ser_base + ".in", ser_base + ".out", mon_path):
        if os.path.exists(p):
            os.remove(p)
    os.mkfifo(ser_base + ".in")
    os.mkfifo(ser_base + ".out")
    ser_rd = os.open(ser_base + ".out", os.O_RDONLY | os.O_NONBLOCK)
    ser_wr = os.open(ser_base + ".in", os.O_RDWR)
    vars_fd = args.vars or f"{args.out}/OVMF_VARS.fd"
    if not os.path.exists(vars_fd):
        shutil.copy(OVMF_VARS, vars_fd)

    cmd = ["qemu-system-x86_64", "-machine", "q35,accel=kvm", "-cpu", "host", "-smp", str(args.smp),
           "-m", str(args.mem), "-no-reboot", "-nodefaults", "-nic", "none",
           "-drive", f"if=pflash,format=raw,readonly=on,file={OVMF_CODE}",
           "-drive", f"if=pflash,format=raw,file={vars_fd}",
           "-device", "qemu-xhci,id=xhci",
           "-drive", f"if=none,id=stick,format=raw,cache=unsafe,file={args.usb}",
           "-device", "usb-storage,bus=xhci.0,drive=stick,removable=on,bootindex=1",
           "-display", "none",
           "-chardev", f"pipe,id=ser0,path={ser_base}", "-serial", "chardev:ser0",
           "-monitor", f"unix:{mon_path},server=on,wait=off"]
    cmd += ["-vga", "none", "-device", args.gpu] if args.gpu else ["-vga", args.vga]
    if args.usb_input:
        cmd += ["-device", "usb-kbd,bus=xhci.0", "-device", "usb-tablet,bus=xhci.0"]
    if args.tpm:  # swtpm exits by itself when QEMU closes the control socket (--terminate)
        tpm_dir, tpm_sock = f"{args.out}/tpm", f"{args.out}/swtpm.sock"
        os.makedirs(tpm_dir, exist_ok=True)
        subprocess.run(["swtpm", "socket", "--tpm2", "--tpmstate", f"dir={tpm_dir}", "--ctrl",
                        f"type=unixio,path={tpm_sock}", "--terminate", "--daemon"], check=True)
        cmd += ["-chardev", f"socket,id=chrtpm,path={tpm_sock}", "-tpmdev", "emulator,id=tpm0,chardev=chrtpm",
                "-device", "tpm-crb,tpmdev=tpm0"]
    if args.nvme:
        cmd += ["-drive", f"if=none,id=internal,format=raw,cache=unsafe,file={args.nvme}",
                "-device", "nvme,drive=internal,serial=internal0,bootindex=2"]
    if args.audio:
        cmd += ["-audiodev", f"wav,id=snd0,path={args.audio},out.frequency=48000,out.channels=2",
                "-device", "ich9-intel-hda,id=hda", "-device", "hda-duplex,bus=hda.0,audiodev=snd0"]
    if args.extra_usb:
        cmd += ["-drive", f"if=none,id=extra,format=raw,cache=unsafe,file={args.extra_usb}",
                "-device", "usb-storage,bus=xhci.0,drive=extra,removable=on"]
    if args.detach_test_device:
        cmd += ["-device", "pcie-root-port,id=rpx,chassis=9,slot=9", "-device", "virtio-rng-pci,bus=rpx"]
    if args.pause_on_reset:  # freeze instead of rebooting, so a screenshot can show the last screen
        cmd = [c for c in cmd if c != "-no-reboot"] + ["-action", "reboot=shutdown", "-action", "shutdown=pause"]
    if args.trace:
        cmd += ["-d", "cpu_reset,guest_errors,unimp", "-D", f"{args.out}/qemu-debug.log"]
    qlog = open(f"{args.out}/qemu.log", "w")
    qlog.write(" ".join(cmd) + "\n")
    qlog.flush()
    t0 = time.time()
    q = subprocess.Popen(cmd, stdout=qlog, stderr=subprocess.STDOUT)


    def monitor(command):
        try:
            m = socket.socket(socket.AF_UNIX)
            m.connect(mon_path)
            m.settimeout(2)
            m.sendall((command + "\n").encode())
            time.sleep(0.5)
            m.close()
        except OSError as e:
            print(f"monitor {command!r}: {e}", file=sys.stderr)

    steps = json.load(open(args.expect)) if args.expect else []
    log = open(f"{args.out}/serial.log", "wb")
    buf, hits, shots = b"", [], sorted(args.shot)
    step_i, step_t0, reason, done_at = 0, time.time(), None, None
    while True:
        now = time.time()
        try:
            data = os.read(ser_rd, 65536)
            if data:
                log.write(data)
                log.flush()
                buf += data
            else:  # no writer yet (QEMU starting) or QEMU gone
                time.sleep(0.05)
        except BlockingIOError:
            time.sleep(0.02)
        if q.poll() is not None:
            reason = reason or f"QEMU exited ({q.returncode})"
            break
        while shots and now - t0 >= shots[0]:
            t = shots.pop(0)
            monitor(f"screendump {args.out}/shot-{int(t)}.ppm")
        while step_i < len(steps):
            st = steps[step_i]
            if "shot" in st:
                monitor(f"screendump {args.out}/shot-{st['shot']}.ppm")
                step_i, step_t0 = step_i + 1, now
                continue
            if "send" in st:
                for ch in st["send"]:  # slow typing: the guest console has no flow control
                    os.write(ser_wr, ch.encode())
                    time.sleep(0.01)
                step_i, step_t0 = step_i + 1, now
                continue
            m = re.search(st["wait"].encode(), buf)
            if m:
                hits.append({"step": step_i, "wait": st["wait"], "t": round(now - t0, 1)})
                buf = buf[m.end():]
                step_i, step_t0 = step_i + 1, now
                continue
            if now - step_t0 > st.get("timeout", 120):
                reason = f"step {step_i} timed out waiting for {st['wait']!r}"
            break
        if reason:
            break
        if steps and step_i == len(steps) and done_at is None:
            done_at = now
        if done_at and now - done_at > args.linger:
            reason = "all steps done"
            break
        if now - t0 > args.timeout:
            reason = f"timeout {args.timeout}s"
            break
        if len(buf) > 1 << 20:
            buf = buf[-(1 << 19):]
    if q.poll() is None:
        monitor("quit")
        try:
            q.wait(10)
        except subprocess.TimeoutExpired:
            q.kill()
    for f in os.listdir(args.out):
        if f.endswith(".ppm"):
            ppm_to_png(f"{args.out}/{f}", f"{args.out}/{f[:-4]}.png")
            os.remove(f"{args.out}/{f}")
    res = {"reason": reason, "seconds": round(time.time() - t0, 1), "steps_done": step_i, "steps": len(steps),
           "hits": hits, "qemu_rc": q.returncode, "usb": args.usb, "nvme": args.nvme}
    json.dump(res, open(f"{args.out}/result.json", "w"), indent=1)
    print(json.dumps(res))
    return 0 if step_i == len(steps) else 1


if __name__ == "__main__":
    sys.exit(main())
