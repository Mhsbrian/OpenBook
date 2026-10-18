#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The OTA rehearsal (ANAL-223): A/B image updates of an installed OpenBook disk over adb, in QEMU/KVM + OVMF, before
the G14. Runs on the host; QEMU runs in the openbook-installer container on the host's network, so adb reaches the VM
at 127.0.0.1:PORT (QEMU's user network forwards it to adbd's tcp:5555 over an emulated USB Ethernet adapter, the
same GKI cdc_ether driver a USB dongle on the G14 would use; the G14 itself is reached over Wi-Fi). The serial console
(the installed entry with console=ttyS0 added) shows every boot, systemd-boot's fallbacks included.

The disk is the installer's own end-to-end result: scripts/installer/e2e-qemu.sh's `install` case (the unattended
engine from the stick, whole disk) on the stick image the G14 was installed from, so the GPT, ESP, loader.conf and
entry are the G14's. The updates are sent with the real command, scripts/g14-adb.sh ota (AOSP's update_device.py).

usage: ota-qemu.py prep  --run RUN --installed DISK            the base state: the installed disk, its console entry,
                                                                its first boot, setup done the way the installer's
                                                                setup does it, a PIN, an app, a setting and a file
       ota-qemu.py case CASE --run RUN --ota PKG [--broken PKG]
         ab        the first update, A -> B over adb (the running image has no bootsync: the package's copy runs as
                   root); reboot; B boots, keeps /data (PIN, app, setting, file), is marked good, the merge completes
         rollback  a package whose kernel cannot start (--broken): A -> B, reboot; B fails three times, systemd-boot
                   starts A again by itself, /data intact; then the good package from there
         cut       a power cut while update_engine writes slot B: A boots with /data intact; the update re-run completes
         ba        the second update, B -> A, from ab's disk: this time the boot HAL on B moves the ESP entry
       ota-qemu.py check --run RUN                              results.json and SUMMARY.md from the cases' checks
Results: <data dir>/logs/installer/ota/RUN/<case>/ (serial.log, adb logs, checks.json); disks in
<data dir>/installer/ota/RUN/.
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time

A = os.path.expanduser(os.environ.get("OPENBOOK_HOME", os.environ.get("ANYBOOK_HOME", "~/anybook")))
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ADB = os.environ.get("ADB", f"{A}/android-sdk/platform-tools/adb")
ADB_PORT = os.environ.get("OPENBOOK_OTA_ADB_SERVER_PORT", "5223")  # a private adb server, not the G14's (5222)
OVMF_CODE, OVMF_VARS = "/usr/share/edk2/x64/OVMF_CODE.4m.fd", "/usr/share/edk2/x64/OVMF_VARS.4m.fd"
PROMPT = "console:/ # "
CONSOLE = "console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on"
PROBE_APK = f"{A}/compat/out/probes/anybook-probe-x86_64.apk"
PIN = "1234"


def log(msg):
    print(f"[{time.strftime('%H:%M:%S', time.gmtime())}] {msg}", flush=True)


def run(*cmd, timeout=600, env=None, check=False):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, **(env or {})})
    if check and r.returncode:
        raise RuntimeError(f"{cmd[0]} failed ({r.returncode}): {r.stderr[-500:]}")
    return r


# ------------------------------------------------------------------------------------------- the VM
class Timeout(Exception):
    pass


class VM:
    def __init__(self, out, disk, vars_file, port, name):
        self.out, self.disk, self.vars, self.port, self.name = out, disk, vars_file, port, name
        os.makedirs(out, exist_ok=True)
        self.buf, self.pos, self.lock, self.proc, self.n = b"", 0, threading.Lock(), None, 0
        self.serial_log = open(f"{out}/serial.log", "ab")

    def start(self):
        ser = f"{self.out}/serial"
        for p in (ser + ".in", ser + ".out", f"{self.out}/monitor.sock"):
            if os.path.exists(p):
                os.remove(p)
        os.mkfifo(ser + ".in")
        os.mkfifo(ser + ".out")
        if not os.path.exists(self.vars):
            run(f"{R}/scripts/installer/inst-docker.sh", "cp", OVMF_VARS, self.vars, check=True)
        cmd = ["qemu-system-x86_64", "-machine", "q35,accel=kvm", "-cpu", "host", "-smp", "8", "-m", "8192",
               "-nodefaults", "-display", "none",
               "-drive", f"if=pflash,format=raw,readonly=on,file={OVMF_CODE}",
               "-drive", f"if=pflash,format=raw,file={self.vars}",
               "-device", "qemu-xhci,id=xhci",
               "-drive", f"if=none,id=internal,format=raw,cache=unsafe,file={self.disk}",
               "-device", "nvme,drive=internal,serial=internal0,bootindex=1",
               "-netdev", f"user,id=n0,hostfwd=tcp:127.0.0.1:{self.port}-:5555",
               "-device", "usb-net,netdev=n0,bus=xhci.0",
               "-vga", "none", "-device", "virtio-vga,xres=1920,yres=1200",
               "-device", "usb-kbd,bus=xhci.0", "-device", "usb-tablet,bus=xhci.0",
               "-chardev", f"pipe,id=ser0,path={ser}", "-serial", "chardev:ser0",
               "-monitor", f"unix:{self.out}/monitor.sock,server=on,wait=off"]
        open(f"{self.out}/qemu-cmd.txt", "a").write(" ".join(cmd) + "\n")
        self.proc = subprocess.Popen([f"{R}/scripts/installer/inst-docker.sh"] + cmd,
                                     env={**os.environ, "OPENBOOK_INSTALLER_NET": "host",
                                          "OPENBOOK_INSTALLER_NAME": self.name},
                                     stdin=subprocess.DEVNULL, stdout=open(f"{self.out}/qemu.log", "a"),
                                     stderr=subprocess.STDOUT)
        self.rd = os.open(ser + ".out", os.O_RDONLY | os.O_NONBLOCK)
        self.wr = os.open(ser + ".in", os.O_RDWR)
        self.alive = True
        threading.Thread(target=self._reader, daemon=True).start()
        log(f"{self.name}: QEMU started (disk {os.path.basename(self.disk)}, adb on 127.0.0.1:{self.port})")

    def _reader(self):
        while self.alive:
            try:
                d = os.read(self.rd, 65536)
            except BlockingIOError:
                time.sleep(0.05)
                continue
            except OSError:
                break
            if not d:
                time.sleep(0.05)
                if self.proc.poll() is not None:
                    break
                continue
            self.serial_log.write(d)
            self.serial_log.flush()
            with self.lock:
                self.buf += d

    def running(self):
        return self.proc and self.proc.poll() is None

    def wait(self, pattern, timeout, fail=None):
        """Wait for regex pattern in the serial output after the last match; returns the match. fail: a regex that
        ends the wait early with the match of that instead (returned as ('fail', m))."""
        t0 = time.time()
        rx, fx = re.compile(pattern.encode()), re.compile(fail.encode()) if fail else None
        while True:
            with self.lock:
                b = self.buf[self.pos:]
            m = rx.search(b)
            f = fx.search(b) if fx else None
            if f and (not m or f.start() < m.start()):
                self.pos += f.end()
                return ("fail", f)
            if m:
                self.pos += m.end()
                return m
            if not self.running():
                raise Timeout(f"QEMU exited while waiting for {pattern!r}")
            if time.time() - t0 > timeout:
                raise Timeout(f"no {pattern!r} within {timeout} s")
            time.sleep(0.1)

    def send(self, text):
        for ch in text:  # slow typing: the guest console has no flow control
            os.write(self.wr, ch.encode())
            time.sleep(0.01)

    def sh(self, cmd, timeout=120):
        """A command in the console's root shell; its output."""
        self.n += 1
        self.send(f"echo @@B$(({self.n}+0))@@; {cmd}; echo @@E$(({self.n}+0))@@ rc=$?\n")
        self.wait(rf"@@B{self.n}@@", 30)  # kernel messages may follow on the same line until dmesg -n 1
        start = self.pos
        m = self.wait(rf"@@E{self.n}@@ rc=(\d+)", timeout)
        with self.lock:
            out = self.buf[start:self.pos - len(m.group(0))].decode(errors="replace")
        self.wait(re.escape(PROMPT), 30)
        return out.replace("\r", ""), int(m.group(1))

    def monitor(self, cmd):
        s = socket.socket(socket.AF_UNIX)
        s.connect(f"{self.out}/monitor.sock")
        s.settimeout(3)
        s.sendall((cmd + "\n").encode())
        time.sleep(0.5)
        s.close()

    def stop(self, how="quit", timeout=60):
        """quit: a power cut (QEMU stops; what the guest had not written yet is lost)."""
        if self.running():
            try:
                self.monitor(how)
            except OSError:
                pass
            try:
                self.proc.wait(timeout)
            except subprocess.TimeoutExpired:
                run("docker", "kill", self.name)
                self.proc.wait(30)
        self.alive = False
        for fd in (self.rd, self.wr):
            try:
                os.close(fd)
            except OSError:
                pass
        log(f"{self.name}: QEMU stopped ({how})")

    def wait_exit(self, timeout):
        try:
            self.proc.wait(timeout)
            self.alive = False
            return True
        except subprocess.TimeoutExpired:
            return False


# ------------------------------------------------------------------------------------------- one boot of Android
def boot(vm, timeout=420, expect_fail=False):
    """Wait for Android on the console, become root, wait for boot_completed, bring the VM's network up. Returns the
    slot that booted. A kernel panic (a slot that cannot start) is returned as 'panic'."""
    m = vm.wait(r"init: init second stage started", 240, fail=r"Kernel panic - not syncing[^\r\n]*")
    if isinstance(m, tuple):
        log(f"boot: {m[1].group(0).decode(errors='replace')}")
        return "panic"
    t0 = time.time()
    while True:  # the console service starts with the shell's prompt; Enter shows it again
        vm.send("\n")
        try:
            vm.wait(r"console:/ \$ ", 5)
            break
        except Timeout:
            if time.time() - t0 > timeout:
                raise
    vm.send("su\n")
    vm.wait(re.escape(PROMPT), 30)
    vm.sh("dmesg -n 1; stty cols 300", 30)
    out, _ = vm.sh("while [ \"$(getprop sys.boot_completed)\" != 1 ]; do sleep 2; done; "
                   "echo SLOT=$(getprop ro.boot.slot_suffix) UP=$(cut -d' ' -f1 /proc/uptime)", timeout)
    slot = re.search(r"SLOT=_?(\w)", out).group(1)
    # adb over the VM's USB Ethernet adapter (GKI cdc_ether from system_dlkm); EthernetService takes DHCP from QEMU.
    out, rc = vm.sh("modprobe -d /system/lib/modules -a mii usbnet cdc_ether; i=0; "
                    "while [ $i -lt 90 ] && ! ip -4 addr | grep -q 'inet 10.0.2.15'; do sleep 1; i=$((i+1)); done; "
                    "ip -4 addr | grep 'inet 10.0.2'", 150)
    if "10.0.2.15" not in out:
        raise RuntimeError(f"no network in the VM: {out[-300:]}")
    log(f"boot: slot {slot} up ({out.split()[1] if out.split() else '?'})")
    return slot


class Adb:
    def __init__(self, port, logdir):
        self.serial, self.logdir = f"127.0.0.1:{port}", logdir
        self.env = {"ANDROID_ADB_SERVER_PORT": ADB_PORT}

    def connect(self, timeout=120):
        t0 = time.time()
        while time.time() - t0 < timeout:
            run(ADB, "disconnect", self.serial, env=self.env, timeout=20)
            run(ADB, "connect", self.serial, env=self.env, timeout=20)
            if run(ADB, "-s", self.serial, "get-state", env=self.env, timeout=20).stdout.strip() == "device":
                return True
            time.sleep(3)
        raise RuntimeError(f"adb: no device at {self.serial}")

    def root(self):
        run(ADB, "-s", self.serial, "root", env=self.env, timeout=30)
        time.sleep(3)
        self.connect()

    def sh(self, cmd, timeout=300):
        r = run(ADB, "-s", self.serial, "shell", cmd, env=self.env, timeout=timeout)
        return r.stdout.replace("\r", ""), r.returncode

    def __call__(self, *args, timeout=600):
        return run(ADB, "-s", self.serial, *args, env=self.env, timeout=timeout)


def g14adb(port, *args, logfile, timeout=3600, env=None):
    """scripts/g14-adb.sh against the VM, its output to logfile; returns its exit code."""
    cmd = [f"{R}/scripts/g14-adb.sh", "-a", f"127.0.0.1:{port}", *args]
    with open(logfile, "a") as f:
        f.write(f"$ {' '.join(cmd)}\n")
        f.flush()
        p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             env={**os.environ, "ANDROID_ADB_SERVER_PORT": ADB_PORT, **(env or {})})
        try:
            return p.wait(timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            return -1


# ------------------------------------------------------------------------------------------- checks and state
class Checks:
    def __init__(self, path, case):
        self.path, self.case, self.items = path, case, []

    def __call__(self, what, ok, detail=""):
        self.items.append({"check": what, "ok": bool(ok), "detail": str(detail)[:600]})
        log(f"[{'PASS' if ok else 'FAIL'}] {self.case}: {what}{(' - ' + str(detail)[:300]) if detail and not ok else ''}")
        json.dump({"case": self.case, "checks": self.items}, open(self.path, "w"), indent=1)


def state(adb):
    """What must survive an update: the user's PIN, an app, a setting, a file; and what tells the builds apart."""
    out, _ = adb.sh(
        "echo FP=$(getprop ro.build.fingerprint); echo DATE=$(getprop ro.build.date.utc); "
        "echo SLOT=$(getprop ro.boot.slot_suffix); echo VBMETA=$(getprop ro.boot.vbmeta.digest); "
        "echo SERIAL=$(getprop ro.boot.serialno); echo SELINUX=$(getenforce); "
        "echo MARKER=$(settings get global openbook_ota_marker); "
        "echo PROVISIONED=$(settings get global device_provisioned)/$(settings get secure user_setup_complete); "
        "echo FILE=$(sha256sum /data/media/0/Download/openbook-ota-marker.bin 2>/dev/null | cut -c1-64); "
        "echo APP=$(pm list packages --show-versioncode 2>/dev/null | grep -i anybook.probe | head -n 1); "
        "echo USERSTATE=$(am get-started-user-state 0 2>/dev/null); "
        "echo HAL=$(getprop init.svc.vendor.boot-openbook)/$(getprop init.svc.vendor.boot-default); "
        "echo TOP=$(dumpsys activity activities | grep -m1 topResumedActivity | sed 's/.* \\([^ ]*\\/[^ ]*\\).*/\\1/')")
    return dict(l.split("=", 1) for l in out.splitlines() if "=" in l and re.match(r"^[A-Z]+=", l))


def unlock(adb):
    """The PIN set in prep: credential-encrypted storage unlocks with it (as the owner's PIN does on the G14)."""
    adb.sh("input keyevent 224; sleep 1; wm dismiss-keyguard; sleep 2")
    out, rc = adb.sh(f"locksettings verify --old {PIN}")
    adb.sh(f"input keyevent 82; sleep 1; input text {PIN}; input keyevent 66; sleep 3")
    t0 = time.time()
    while time.time() - t0 < 60:
        s, _ = adb.sh("am get-started-user-state 0")
        if "RUNNING_UNLOCKED" in s:
            return True, out.strip()
        time.sleep(3)
    return False, out.strip()


def bootsync_status(adb, binary="/vendor/bin/openbook-bootsync"):
    out, rc = adb.sh(f"{binary} --json status 2>/dev/null")
    try:
        return json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {}


def wait_merge(adb, timeout=900):
    """update_engine merges the snapshots after markBootSuccessful; done when its log says so and no snapshot is left."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        out, _ = adb.sh("logcat -d -b all | grep -E 'Merge finished with state|MergeFailed|merge failed' | tail -n 3; "
                        "snapshotctl dump 2>&1 | grep -iE 'update.?state' | head -n 1")
        if "MergeCompleted" in out or re.search(r"state:\s*none", out, re.I):
            return True, out.strip(), round(time.time() - t0)
        if "MergeFailed" in out:
            return False, out.strip(), round(time.time() - t0)
        time.sleep(10)
    return False, "timeout", timeout


def avc(adb):
    """Every denial of this boot, and those that involve OpenBook's update path (bootsync, the boot HAL, the ESP)."""
    out, _ = adb.sh("logcat -d -b all | grep -E 'avc: +denied' | head -n 200")
    every = [l for l in out.splitlines() if l.strip()]
    ours = [l for l in every if re.search(r"openbook_bootsync|hal_bootctl|openbook_esp_block_device", l)]
    return ours, every


# ------------------------------------------------------------------------------------------- prep and cases
def paths(run_name):
    # Both below the openbook-installer container's writable mounts (scripts/installer/inst-docker.sh): QEMU's
    # serial FIFOs and monitor socket live in the case's log directory.
    return f"{A}/installer/ota/{run_name}", f"{A}/logs/installer/ota/{run_name}"


def esp_offset(disk):
    out = run(f"{R}/scripts/installer/inst-docker.sh", "sgdisk", "-i", "1", disk, check=True).stdout
    return int(re.search(r"First sector: (\d+)", out).group(1)) * 512


def add_console(disk):
    """The installed entry itself gets the serial console (so slot B's entry, written by bootsync from it, has it
    too); loader.conf stays as the installer wrote it."""
    off = esp_offset(disk)
    d = os.path.dirname(disk)
    script = (f"set -e; cd '{d}'; mcopy -n -o -i '{disk}@@{off}' ::/loader/entries/openbook-a.conf a.conf; "
              f"grep -q 'console=ttyS0' a.conf || sed -i 's/^options \\(.*\\)/options \\1 {CONSOLE}/' a.conf; "
              f"mcopy -o -i '{disk}@@{off}' a.conf ::/loader/entries/openbook-a.conf; cat a.conf; rm -f a.conf")
    return run(f"{R}/scripts/installer/inst-docker.sh", "bash", "-c", script, check=True).stdout


def esp_listing(disk):
    off = esp_offset(disk)
    script = (f"mdir -/ -b -i '{disk}@@{off}' ::/loader ::/openbook 2>/dev/null; echo ---; "
              f"mtype -i '{disk}@@{off}' ::/loader/loader.conf")
    return run(f"{R}/scripts/installer/inst-docker.sh", "bash", "-c", script).stdout


def reflink(src, dst):
    if os.path.exists(dst):
        os.remove(dst)
    run("cp", "--reflink=always", src, dst, check=True)


def case_dir(run_name, case):
    q, l = paths(run_name)
    out = f"{l}/{case}"
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    os.makedirs(q, exist_ok=True)
    return q, out


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def prep(a):
    q, out = case_dir(a.run, "prep")
    C = Checks(f"{out}/checks.json", "prep")
    base = f"{q}/base.img"
    reflink(a.installed, base)
    shutil.copy(a.installed + ".json", f"{q}/installed-source.json") if os.path.exists(a.installed + ".json") else None
    entry = add_console(base)
    C("the installed entry gets the serial console; loader.conf as the installer wrote it", "console=ttyS0" in entry, entry)
    open(f"{out}/esp-before.txt", "w").write(esp_listing(base))
    port = free_port()
    vm = VM(out, base, f"{q}/base.vars", port, f"ota-{a.run}-prep")
    vm.start()
    try:
        slot = boot(vm)
        C("the installed disk boots slot a", slot == "a", slot)
        adb = Adb(port, out)
        adb.connect()
        adb.root()
        # Setup, done the way the installer's setup ends (the image predates OpenBookSetup): both settings, and the
        # setup screen off.
        adb.sh("settings put global device_provisioned 1; settings put secure user_setup_complete 1; "
               "pm disable org.openbook.installer/.SetupActivity >/dev/null 2>&1; "
               "pm disable com.android.provision >/dev/null 2>&1; am start -a android.intent.action.MAIN "
               "-c android.intent.category.HOME >/dev/null 2>&1")
        marker = secrets.token_hex(8)
        adb.sh(f"settings put global openbook_ota_marker {marker}; mkdir -p /data/media/0/Download; "
               "dd if=/dev/urandom of=/data/media/0/Download/openbook-ota-marker.bin bs=1048576 count=4 2>/dev/null; "
               "chown media_rw:media_rw /data/media/0/Download/openbook-ota-marker.bin; sync")
        r = adb("install", "--no-incremental", "-r", PROBE_APK)
        C("an app installed with adb install", r.returncode == 0, r.stdout + r.stderr)
        o, _ = adb.sh(f"locksettings set-pin {PIN}")
        C("a screen-lock PIN set", "set to" in o.lower() or "pin" in o.lower(), o)
        st = state(adb)
        json.dump(st, open(f"{out}/state.json", "w"), indent=1)
        C("the base state recorded (marker, file, app, provisioned)", st.get("MARKER") == marker and len(st.get("FILE", "")) == 64
          and "anybook.probe" in st.get("APP", "") and st.get("PROVISIONED") == "1/1", st)
        C("SELinux enforcing; the image's own boot HAL (AOSP default) runs", st.get("SELINUX") == "Enforcing" and
          st.get("HAL", "").endswith("/running"), st)
        adb.sh("reboot -p")
        C("powers off", vm.wait_exit(120))
    finally:
        vm.stop()
    json.dump({"marker": marker, "state": st}, open(f"{q}/base.json", "w"), indent=1)
    return 0 if all(x["ok"] for x in C.items) else 1


def pkg_info(pkg):
    return json.load(open(pkg[:-4] + ".json"))


def after_update(C, adb, base, pkg, slot, label):
    """The checks after a reboot into an updated slot."""
    ok, how = unlock(adb)
    C(f"{label}: the PIN unlocks the user's storage", ok, how)
    st = state(adb)
    C(f"{label}: slot {slot} runs the package's build (vbmeta digest, build date)",
      st.get("SLOT") == f"_{slot}" and st.get("VBMETA") == pkg["vbmeta_digest"] and st.get("DATE") == str(pkg["build_date_utc"]),
      {k: st.get(k) for k in ("SLOT", "VBMETA", "DATE")})
    b = base["state"]
    C(f"{label}: /data intact: the setting, the 4 MiB file, the app, the serial number, provisioned",
      st.get("MARKER") == b["MARKER"] and st.get("FILE") == b["FILE"] and st.get("APP") == b["APP"] and
      st.get("SERIAL") == b["SERIAL"] and st.get("PROVISIONED") == "1/1",
      {k: (b.get(k), st.get(k)) for k in ("MARKER", "FILE", "APP", "SERIAL", "PROVISIONED") if b.get(k) != st.get(k)})
    C(f"{label}: no setup screen after the update (OpenBookSetup steps aside on a provisioned system)",
      "setup" not in st.get("TOP", "").lower(), st.get("TOP"))
    C(f"{label}: SELinux enforcing; the OpenBook boot HAL runs", st.get("SELINUX") == "Enforcing" and
      st.get("HAL", "").startswith("running"), st.get("HAL"))
    return st


def case_ab(a, from_state="base", case="ab", pkg_path=None):
    q, out = case_dir(a.run, case)
    C = Checks(f"{out}/checks.json", case)
    base = json.load(open(f"{q}/base.json"))
    pkg_path = pkg_path or a.ota
    pkg = pkg_info(pkg_path)
    disk = f"{q}/{case}.img"
    reflink(f"{q}/{from_state}.img", disk)
    shutil.copy(f"{q}/{from_state}.vars", f"{q}/{case}.vars")
    port = free_port()
    vm = VM(out, disk, f"{q}/{case}.vars", port, f"ota-{a.run}-{case}")
    vm.start()
    try:
        cur = boot(vm)
        tgt = "b" if cur == "a" else "a"
        adb = Adb(port, out)
        adb.connect()
        unlock(adb)
        rc = g14adb(port, "ota", pkg_path, "--yes", logfile=f"{out}/g14-adb-ota.log")
        text = open(f"{out}/g14-adb-ota.log").read()
        C(f"g14-adb.sh ota: slot {tgt} written over adb, verified", rc == 0 and f"verified  slot {tgt}" in text,
          text[-800:])
        C("the first update's ESP step: bootsync from the package (running image has none)" if from_state == "base" else
          "the boot HAL moved the ESP entry (no bootstrap)",
          ("from the package" in text) == (from_state == "base"), text[-400:])
        progress = re.findall(r"UPDATE_STATUS_DOWNLOADING (\d+)%", text)
        C("progress shown while update_engine writes", len(set(progress)) >= 3, progress[-5:])
        if rc:
            return 1
        adb = Adb(port, out)
        adb.connect()
        adb.root()
        adb.sh("reboot")
        slot = boot(vm)
        C(f"after the reboot systemd-boot starts slot {tgt}", slot == tgt, slot)
        adb.connect()
        adb.root()
        st = after_update(C, adb, base, pkg, tgt, "after the update")
        ok, how, secs = wait_merge(adb)
        C("the virtual A/B merge completes", ok, how)
        s = bootsync_status(adb)
        json.dump(s, open(f"{out}/bootsync-status.json", "w"), indent=1)
        other = cur
        C(f"ESP: slot {tgt}'s entry is good and the default; slot {other}'s entry is gone",
          s.get("next_boot_slot") == tgt and s.get("slots", {}).get(tgt, {}).get("entry_state") == "good" and
          s["slots"].get(other, {}).get("entry_state") == "none" and s.get("loader_conf", {}).get("default") ==
          f"openbook-{tgt}.conf", s.get("entries"))
        o, _ = adb.sh("bootctl get-current-slot; bootctl get-active-boot-slot; bootctl is-slot-marked-successful "
                      f"{0 if tgt == 'a' else 1} && echo successful")
        C(f"boot HAL (misc): current and active slot {tgt}, marked successful", o.split()[:2] == [str("ab".index(tgt))] * 2
          and "successful" in o, o)
        dn, every = avc(adb)
        C("no SELinux denial for openbook-bootsync, the boot HAL or the ESP (enforcing); the others are listed in "
          "avc.txt, not gated", not dn, dn)
        open(f"{out}/avc.txt", "w").write("\n".join(every) + "\n")
        adb.sh("logcat -d -b all > /data/local/tmp/logcat.txt")
        adb("pull", "/data/local/tmp/logcat.txt", f"{out}/logcat-after.txt")
        g14adb(port, "ota-status", logfile=f"{out}/g14-adb-ota-status.log")
        adb.sh("reboot -p")
        vm.wait_exit(120)
    finally:
        vm.stop()
    open(f"{out}/esp-after.txt", "w").write(esp_listing(disk))
    if all(x["ok"] for x in C.items):
        reflink(disk, f"{q}/after-{case}.img")
        shutil.copy(f"{q}/{case}.vars", f"{q}/after-{case}.vars")
    os.remove(disk)
    return 0 if all(x["ok"] for x in C.items) else 1


def case_rollback(a):
    q, out = case_dir(a.run, "rollback")
    C = Checks(f"{out}/checks.json", "rollback")
    base = json.load(open(f"{q}/base.json"))
    good, broken = pkg_info(a.ota), pkg_info(a.broken)
    disk = f"{q}/rollback.img"
    reflink(f"{q}/base.img", disk)
    shutil.copy(f"{q}/base.vars", f"{q}/rollback.vars")
    port = free_port()
    vm = VM(out, disk, f"{q}/rollback.vars", port, f"ota-{a.run}-rollback")
    vm.start()
    try:
        boot(vm)
        adb = Adb(port, out)
        adb.connect()
        unlock(adb)
        rc = g14adb(port, "ota", a.broken, "--yes", logfile=f"{out}/g14-adb-ota-broken.log")
        C("the broken package (its kernel cannot start: rdinit missing) installs and verifies like any other",
          rc == 0 and "verified  slot b" in open(f"{out}/g14-adb-ota-broken.log").read())
        adb.connect()
        adb.root()
        adb.sh("reboot")
        panics, slot = 0, None
        for _ in range(5):
            slot = boot(vm)
            if slot != "panic":
                break
            panics += 1
        C("slot b fails to start three times (kernel panic, reboot), then systemd-boot starts slot a by itself",
          panics == 3 and slot == "a", (panics, slot))
        adb.connect()
        adb.root()
        ok, how = unlock(adb)
        st = state(adb)
        b = base["state"]
        C("slot a is the old build, /data intact (PIN, setting, file, app)", ok and st.get("SLOT") == "_a" and
          st.get("VBMETA") == b["VBMETA"] and st.get("MARKER") == b["MARKER"] and st.get("FILE") == b["FILE"] and
          st.get("APP") == b["APP"], {k: (b.get(k), st.get(k)) for k in ("SLOT", "VBMETA", "MARKER", "FILE", "APP")})
        o, _ = adb.sh("timeout 10 update_engine_client --follow 2>&1 | grep -o 'UPDATE_STATUS_[A-Z_]*' | tail -n 1; "
                      "logcat -d -b all | grep -iE 'rollback|Cancel|snapshot' | grep -iE 'update_engine|snapshot|init' | tail -n 6")
        C("update_engine is idle again on slot a (the failed update is cancelled)", "UPDATE_STATUS_IDLE" in o, o)
        open(f"{out}/esp-fallback.txt", "w").write(o)
        # and the good package from there: the system recovers from the failed attempt by itself
        rc = g14adb(port, "ota", a.ota, "--yes", logfile=f"{out}/g14-adb-ota-good.log")
        C("then the good package from slot a: written and verified (the bad entry replaced)",
          rc == 0 and "verified  slot b" in open(f"{out}/g14-adb-ota-good.log").read())
        adb.connect()
        adb.root()
        adb.sh("reboot")
        slot = boot(vm)
        C("slot b boots the good build", slot == "b", slot)
        adb.connect()
        adb.root()
        after_update(C, adb, base, good, "b", "after the second attempt")
        ok, how, secs = wait_merge(adb)
        C("the merge completes", ok, how)
        adb.sh("reboot -p")
        vm.wait_exit(120)
    finally:
        vm.stop()
    open(f"{out}/esp-after.txt", "w").write(esp_listing(disk))
    os.remove(disk)
    return 0 if all(x["ok"] for x in C.items) else 1


def case_cut(a):
    q, out = case_dir(a.run, "cut")
    C = Checks(f"{out}/checks.json", "cut")
    base = json.load(open(f"{q}/base.json"))
    pkg = pkg_info(a.ota)
    disk = f"{q}/cut.img"
    reflink(f"{q}/base.img", disk)
    shutil.copy(f"{q}/base.vars", f"{q}/cut.vars")
    port = free_port()
    vm = VM(out, disk, f"{q}/cut.vars", port, f"ota-{a.run}-cut")
    vm.start()
    try:
        boot(vm)
        adb = Adb(port, out)
        adb.connect()
        unlock(adb)
        logf = f"{out}/g14-adb-ota-cut.log"
        p = subprocess.Popen([f"{R}/scripts/g14-adb.sh", "-a", f"127.0.0.1:{port}", "ota", a.ota, "--yes"],
                             stdout=open(logf, "w"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             env={**os.environ, "ANDROID_ADB_SERVER_PORT": ADB_PORT})
        t0, cut_at = time.time(), None
        while time.time() - t0 < 1800 and p.poll() is None:
            prog = re.findall(r"UPDATE_STATUS_DOWNLOADING (\d+)%", open(logf).read())
            if prog and int(prog[-1]) >= 40:
                cut_at = prog[-1]
                break
            time.sleep(0.5)
        vm.stop("quit")  # the power cut
        p.kill()
        C("power cut while update_engine writes slot b", cut_at is not None, f"at progress {cut_at}")
        vm = VM(out, disk, f"{q}/cut.vars", port, f"ota-{a.run}-cut-2")
        vm.start()
        slot = boot(vm)
        adb = Adb(port, out)
        adb.connect()
        adb.root()
        ok, how = unlock(adb)
        st = state(adb)
        b = base["state"]
        C("after the cut slot a boots, the old build, /data intact", slot == "a" and ok and st.get("VBMETA") == b["VBMETA"]
          and st.get("MARKER") == b["MARKER"] and st.get("FILE") == b["FILE"] and st.get("APP") == b["APP"],
          {k: (b.get(k), st.get(k)) for k in ("VBMETA", "MARKER", "FILE", "APP")})
        s = bootsync_status(adb, "/data/local/tmp/none")  # no bootsync on this image: read the ESP from outside later
        rc = g14adb(port, "ota", a.ota, "--yes", logfile=f"{out}/g14-adb-ota-rerun.log")
        text = open(f"{out}/g14-adb-ota-rerun.log").read()
        C("the update re-run completes and verifies", rc == 0 and "verified  slot b" in text, text[-600:])
        o, _ = adb.sh("logcat -d -b all | grep -iE 'resum|Resuming|interrupted|previous update' | grep -i update_engine | tail -n 5")
        open(f"{out}/resume.txt", "w").write(o)
        adb.connect()
        adb.root()
        adb.sh("reboot")
        slot = boot(vm)
        C("slot b boots", slot == "b", slot)
        adb.connect()
        adb.root()
        after_update(C, adb, base, pkg, "b", "after the re-run")
        ok, how, secs = wait_merge(adb)
        C("the merge completes", ok, how)
        adb.sh("reboot -p")
        vm.wait_exit(120)
    finally:
        vm.stop()
    open(f"{out}/esp-after.txt", "w").write(esp_listing(disk))
    os.remove(disk)
    return 0 if all(x["ok"] for x in C.items) else 1


def check(a):
    q, l = paths(a.run)
    cases, total, passed = {}, 0, 0
    for c in ("prep", "ab", "rollback", "cut", "ba"):
        f = f"{l}/{c}/checks.json"
        if os.path.exists(f):
            cases[c] = json.load(open(f))["checks"]
            total += len(cases[c])
            passed += sum(x["ok"] for x in cases[c])
    json.dump({"run": a.run, "passed": passed, "total": total, "cases": cases}, open(f"{l}/results.json", "w"), indent=1)
    with open(f"{l}/SUMMARY.md", "w") as f:
        f.write(f"# OTA rehearsal in QEMU ({a.run})\n\n{passed}/{total} checks passed.\n\n"
                "| Case | Check | Result | Detail |\n|---|---|---|---|\n")
        for c, v in cases.items():
            for x in v:
                f.write(f"| {c} | {x['check']} | {'PASS' if x['ok'] else 'FAIL'} | "
                        f"{x['detail'].replace('|', '/')[:140] if not x['ok'] else ''} |\n")
    print(f"{passed}/{total} checks passed")
    return 0 if passed == total else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["prep", "case", "check"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--run", required=True)
    ap.add_argument("--installed")
    ap.add_argument("--ota")
    ap.add_argument("--broken")
    a = ap.parse_args()
    for p in (a.ota, a.broken):
        if p and not (p.endswith(".zip") and os.path.exists(p[:-4] + ".json")):
            sys.exit(f"{p}: a package from scripts/ota/make-ota.sh (PKG.zip with PKG.json) expected")
    if a.cmd == "prep":
        return prep(a)
    if a.cmd == "check":
        return check(a)
    if a.name == "ab":
        return case_ab(a)
    if a.name == "ba":
        return case_ab(a, from_state="after-ab", case="ba")
    if a.name == "rollback":
        return case_rollback(a)
    if a.name == "cut":
        return case_cut(a)
    sys.exit(f"unknown case {a.name}")


if __name__ == "__main__":
    sys.exit(main())
