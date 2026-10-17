#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The installer wizard end to end in QEMU/OVMF (ANAL-191), on image files only:

  dryrun     the live stick (16 GiB copy) next to a blank 64 GiB NVMe disk, SELinux enforcing: the wizard starts by
             itself after boot; Welcome, Hardware check, Try or install and Disk are captured; "View the plan" (the
             dry run through the app and the daemon) is captured; the CLI dry run (`openbook-install disks` and
             `plan`) is logged. Afterwards the NVMe file must still have no allocated block: nothing was written.
  install    the same stick and disk: the wizard again, then Confirm (the typed disk name), Install (progress) and
             Done; the daemon's log, the install report, logcat and the SELinux denials are collected. "Restart now"
             ends the run.
  installed  the NVMe disk alone (the stick removed), unchanged, as the firmware finds it (no serial console):
             screenshots for 6 minutes.
  console    a copy of the installed disk with one extra loader entry (the same entry plus a serial console):
             boot_completed, by-name links on the NVMe, boot_part_uuid, no live flags, SELinux, the installer's
             daemon not running, the launcher entry off, and the AVC denials.
Firmware boot entries (efivarfs, S11; wizard-qemu.sh runs these after install or alongside):
  nvram-boot        a copy of the whole-disk install with EFI/BOOT/BOOTX64.EFI deleted, the install's NVRAM, no
                    bootindex hints: BootCurrent must be the entry the install made (first in BootOrder).
  alongside         a Windows-like disk (mkwin) whose "Windows Boot Manager" (Boot0007) is first in BootOrder; the
                    wizard installs alongside without "Start OpenBook by default": one new entry, appended to the end
                    of BootOrder (owner decision 2026-10-17); Windows' entry byte-identical.
  alongside-default that disk with the install's NVRAM and no hints: the Windows stand-in (efi-standin.c) starts by
                    default and returns to the firmware, whose boot menu must list OpenBook (it is in BootOrder);
                    Up (the last item) and Enter start it, and Android boots from the new partitions. Then BootNext
                    is pointed at OpenBook's entry (a test step).
  alongside-boot    the same disk and NVRAM again: the firmware starts OpenBook once through BootNext.
The stick boots a test entry at 2880x1800 with density 240 (the G14's panel and scaling), virtio-vga.

usage: wizard-qemu.py expect CASE OUT.json [--target BY-ID] [--model MODEL] [--win JSON]   CASE's expect script
       wizard-qemu.py mkwin OUT.img                                              the Windows-like disk (JSON facts)
       wizard-qemu.py check --run DIR --disks DIR --image IMG                    results.json + SUMMARY.md
"""
import argparse
import base64
import gzip
import json
import os
import re
import struct
import subprocess
import sys

PROMPT = r"console:/ # "
# Shell helpers typed into the root shell: tap a node by its text or content description (prefix), wait for one.
HELPERS = r"""
while read -r k n v; do [ "$k" = export ] && export "$n=$v"; done < /data/system/environ/classpath
ui() { uiautomator dump /data/local/tmp/ui.xml >/dev/null 2>&1; }
bnd() { ui; tr '>' '\n' < /data/local/tmp/ui.xml | grep -F 'package="org.openbook.installer"' | grep -F -e "text=\"$1" -e "content-desc=\"$1" | head -n 1 | sed -n 's/.*bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]".*/\1 \2 \3 \4/p'; }
tap() { b=$(bnd "$1"); if [ -z "$b" ]; then echo "@@NOTFOUND[$1]@@"; return 1; fi; set -- $b; input tap $(( ($1+$3)/2 )) $(( ($2+$4)/2 )); echo "@@TAPPED@@"; }
bndx() { ui; tr '>' '\n' < /data/local/tmp/ui.xml | grep -F 'package="org.openbook.installer"' | grep -F -e "text=\"$1\"" | head -n 1 | sed -n 's/.*bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]".*/\1 \2 \3 \4/p'; }
tapx() { b=$(bndx "$1"); if [ -z "$b" ]; then echo "@@NOTFOUND[$1]@@"; return 1; fi; set -- $b; input tap $(( ($1+$3)/2 )) $(( ($2+$4)/2 )); echo "@@TAPPED@@"; }
waitfor() { i=0; while [ $i -lt ${2:-90} ]; do b=$(bnd "$1"); if [ -n "$b" ]; then echo "@@SEEN[$1]@@"; return 0; fi; sleep 2; i=$((i+2)); done; echo "@@TIMEOUT[$1]@@"; return 1; }
snap() { screencap -p /data/local/tmp/snap.png && sync && echo 3 > /proc/sys/vm/drop_caches && mkdir -p /mnt/obesp && mount -t vfat ${SNAPDEV:-/dev/block/sda1} /mnt/obesp && mkdir -p /mnt/obesp/openbook/shots && cp /data/local/tmp/snap.png "/mnt/obesp/openbook/shots/$1.png"; sync; umount /mnt/obesp; echo 3 > /proc/sys/vm/drop_caches; echo "@@SNAP[$1]@@"; }
"""


def steps_common_boot():
    return [
        {"wait": "init: init second stage started", "timeout": 180},
        {"wait": r"Command 'mount_all --late' action=late-fs \S+ took \d+ms and succeeded", "timeout": 300},
        {"send": "\n"},
        {"wait": r"console:/ \$ ", "timeout": 120},
        {"send": "su\n"},
        {"wait": PROMPT, "timeout": 30},
        {"send": "dmesg -n 1; stty cols 300\n"},
        {"wait": PROMPT, "timeout": 30},
        {"send": "while [ \"$(getprop sys.boot_completed)\" != 1 ]; do sleep 2; done; echo BOOTDONE=1 uptime=$(cut -d' ' -f1 /proc/uptime)\n"},
        {"wait": r"\nBOOTDONE=1 uptime=", "timeout": 600},
        {"wait": PROMPT, "timeout": 30},
        # Keep the screen on for the screenshots.
        {"send": "svc power stayon true; settings put system screen_off_timeout 3600000; input keyevent 224; wm dismiss-keyguard\n"},
        {"wait": PROMPT, "timeout": 30},
    ]


def send(cmd, timeout=120):
    return [{"send": cmd + "\n"}, {"wait": PROMPT, "timeout": timeout}]


def section(name, cmd, timeout=180):
    return [{"send": f"echo ===={name}-BEGIN===; {cmd}; echo ===={name}-END===\n".replace("====", "===")},
            {"wait": f"==={name}-END===", "timeout": timeout}, {"wait": PROMPT, "timeout": 30}]


def wait_ui(text, timeout=120):
    # A screen that never appears fails the run here (qemu-run stops at a step that times out).
    return [{"send": f"waitfor '{text}' {timeout}\n"}, {"wait": r"@@SEEN\[", "timeout": timeout + 60},
            {"wait": PROMPT, "timeout": 30}]


def tap_optional(text, settle=3):
    return [{"send": f"tap '{text}'\n"}, {"wait": r"@@(TAPPED|NOTFOUND)", "timeout": 90}, {"wait": PROMPT, "timeout": 30},
            {"pause": settle}]


def tap(text, settle=3):
    return [{"send": f"tap '{text}'\n"}, {"wait": r"@@TAPPED@@", "timeout": 90}, {"wait": PROMPT, "timeout": 30},
            {"pause": settle}]


def shot(name, snap=True):
    # Android's own screenshot (screencap), saved to the stick's ESP (openbook/shots/), and QEMU's display.
    s = [{"pause": 2}]
    if snap:
        s += [{"send": f"snap {name}\n"}, {"wait": r"@@SNAP\[", "timeout": 60}, {"wait": PROMPT, "timeout": 30}]
    return s + [{"shot": name}]


EFI_GLOBAL = "8be4df61-93ca-11d2-aa0d-00e098032b8c"
EV = "/sys/firmware/efi/efivars"


def _guid_bytes(s):
    b = bytes.fromhex(s.replace("-", ""))
    return b[3::-1] + b[5:3:-1] + b[7:5:-1] + b[8:]


def _ucs2(s):
    return s.encode("utf-16-le") + b"\0\0"


def load_option(desc, partnum, start, size, guid, path):
    """An EFI_LOAD_OPTION: HD(partnum, GPT, guid)/File(path), active."""
    hd = bytes([4, 1, 42, 0]) + struct.pack("<IQQ", partnum, start, size) + _guid_bytes(guid) + bytes([2, 2])
    fp = _ucs2(path)
    dp = hd + bytes([4, 4]) + struct.pack("<H", 4 + len(fp)) + fp + bytes([0x7F, 0xFF, 4, 0])
    return struct.pack("<IH", 1, len(dp)) + _ucs2(desc) + dp


def nvram_section(name):
    return section(name, f"openbook-install nvram; sha256sum {EV}/Boot0007-{EFI_GLOBAL} {EV}/BootOrder-{EFI_GLOBAL} 2>&1", 60)


def tapx(text, settle=3):
    return [{"send": f"tapx '{text}'\n"}, {"wait": r"@@TAPPED@@", "timeout": 90}, {"wait": PROMPT, "timeout": 30},
            {"pause": settle}]


def efi_clang():
    """A clang that can link UEFI applications (lld): $OPENBOOK_EFI_CLANG, else AOSP's newest prebuilt."""
    if os.environ.get("OPENBOOK_EFI_CLANG"):
        return os.environ["OPENBOOK_EFI_CLANG"]
    home = os.environ.get("OPENBOOK_HOME", os.path.expanduser("~/anybook"))
    base = f"{home}/aosp/src/prebuilts/clang/host/linux-x86"
    rs = sorted((d for d in os.listdir(base) if re.fullmatch(r"clang-r\d+[a-z]?", d)),
                key=lambda d: (int(re.search(r"\d+", d).group()), d))
    return f"{base}/{rs[-1]}/bin/clang"


def mkwin(out):
    """A Windows-like 300 GiB disk image: ESP (260 MiB, EFI/Microsoft/Boot/bootmgfw.efi and EFI/BOOT/BOOTX64.EFI, both
    the Windows stand-in built from efi-standin.c), MSR, a 200 GiB NTFS partition, an 800 MiB recovery partition, about
    99 GiB free. Prints the ESP's facts as JSON."""
    import tempfile
    if os.path.exists(out):
        os.remove(out)
    with open(out, "wb") as f:
        f.truncate(300 * 1024 ** 3)
    subprocess.run(["sgdisk", "-n", "1:2048:+260M", "-t", "1:ef00", "-c", "1:EFI system partition",
                    "-n", "2:0:+16M", "-t", "2:0c01", "-c", "2:Microsoft reserved partition",
                    "-n", "3:0:+200G", "-t", "3:0700", "-c", "3:Basic data partition",
                    "-n", "4:0:+800M", "-t", "4:2700", "-c", "4:", out], check=True, capture_output=True)
    with tempfile.TemporaryDirectory() as d:
        esp, fake = f"{d}/esp.img", f"{d}/bootmgfw.efi"
        subprocess.run(["mkfs.fat", "-F", "32", "-n", "SYSTEM", "-C", esp, str(260 * 1024)], check=True, capture_output=True)
        for x in ("::/EFI", "::/EFI/Microsoft", "::/EFI/Microsoft/Boot", "::/EFI/BOOT"):
            subprocess.run(["mmd", "-i", esp, x], check=True)
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "efi-standin.c")
        subprocess.run([efi_clang(), "--target=x86_64-unknown-windows", "-ffreestanding", "-fshort-wchar",
                        "-mno-red-zone", "-nostdlib", "-fuse-ld=lld", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-Wl,-entry:efi_main", "-Wl,-subsystem:efi_application",
                        "-o", fake, src], check=True)
        subprocess.run(["mcopy", "-i", esp, fake, "::/EFI/Microsoft/Boot/bootmgfw.efi"], check=True)
        subprocess.run(["mcopy", "-i", esp, fake, "::/EFI/BOOT/BOOTX64.EFI"], check=True)
        with open(out, "r+b") as f:
            f.seek(2048 * 512)
            f.write(open(esp, "rb").read())
    p = subprocess.run(["sgdisk", "-p", out], capture_output=True, text=True).stdout
    starts = [int(m.group(1)) for m in re.finditer(r"^\s+\d+\s+(\d+)\s+\d+", p, re.M)]
    with open(out, "r+b") as f:  # an NTFS boot sector on partition 3
        f.seek(starts[2] * 512 + 3)
        f.write(b"NTFS    ")
    guid = re.search(r"unique GUID: (\S+)", subprocess.run(["sgdisk", "-i", "1", out], capture_output=True,
                                                           text=True).stdout).group(1).lower()
    print(json.dumps({"esp_guid": guid, "esp_start": 2048, "esp_sectors": 260 * 2048}))


def helpers():
    out = []
    for line in HELPERS.strip().splitlines():
        out += send(line, 30)
    return out


def wizard_front(model):
    s = []
    # The app starts by itself after boot on a live stick (BootReceiver); the launcher entry is the fallback.
    s += wait_ui("Choose your language", 180)
    s += section("WIZARD-AUTOSTART", "dumpsys activity activities | grep -E 'topResumedActivity|ResumedActivity' | head -n 3")
    s += shot("1-welcome")
    s += tap("Continue", 4)
    s += wait_ui("STEP 2 OF 7", 120)
    s += [{"pause": 6}]
    s += shot("2-hardware")
    s += tap("Continue", 4)
    s += wait_ui("STEP 3 OF 7", 60)
    s += shot("3-choose")
    s += tap("Install OpenBook", 2)
    s += shot("3-choose-install")
    s += tap("Continue", 4)
    s += wait_ui("STEP 4 OF 7", 90)
    s += [{"pause": 4}]
    s += shot("4-disk")
    s += tap(model, 2)
    s += shot("4-disk-selected")
    s += tap("View the plan", 6)
    s += shot("4-plan")
    s += [{"send": "input keyevent 111\n"}, {"wait": PROMPT, "timeout": 30}, {"pause": 2}]
    return s


def expect(case, target, model, win=None):
    if case == "installed":
        return []  # no serial console on the installed entry: screenshots only (wizard-qemu.sh --shot)
    s = steps_common_boot()
    if case in ("dryrun", "install", "alongside"):
        s += helpers()
        s += section("PROPS", "getprop | grep -E 'ro.boot.(openbook|selinux|boot_part_uuid)|init.svc.openbook|ro.build.fingerprint'; getenforce")
        s += section("LABELS", "ls -lZ /dev/block | grep -E ' (sd[a-z]+|nvme0n1)$'; ls -lZ /dev/socket/openbook_installd; ps -AZ | grep -E 'openbook|installer'; grep efivarfs /proc/mounts; ls -dZ /sys/firmware/efi/efivars; ls -Z /sys/firmware/efi/efivars | head -n 3")
    if case == "dryrun":
        s += section("CLI-DISKS", "openbook-install disks", 120)
        s += section("CLI-PLAN", f"openbook-install plan --target /dev/disk/by-id/{target} --layout whole --locale en-US --keyboard us --out /data/local/tmp/plan.json", 120)
        s += wizard_front(model)
        s += section("INSTALLD-LOG", "cat /data/misc/openbook_install/installd.log")
        s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
    elif case == "install":
        s += wizard_front(model)
        s += tap("Continue", 5)
        s += wait_ui("STEP 5 OF 7", 90)
        s += shot("5-confirm")
        s += tap("Type", 2)
        s += send("input text '" + model.replace(" ", "%s") + "'", 30)
        s += [{"pause": 3}]
        s += shot("5-confirm-typed")
        s += tap("Erase and install", 1)
        s += shot("6-install-progress")
        # In QEMU the install takes about 15 s: the details may come too late (then Done is shown already).
        s += tap_optional("Show details", 2)
        s += shot("6-install-details")
        s += wait_ui("OpenBook is installed", 1500)
        s += [{"pause": 4}]
        s += shot("7-done")
        s += section("INSTALLD-LOG", "cat /data/misc/openbook_install/installd.log", 120)
        s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
        s += section("APP-LOG", "logcat -d -b main | grep -iE 'openbook|installer' | tail -n 200", 120)
        s += section("NVRAM-AFTER", "openbook-install nvram", 60)
        s += [{"send": "sync\n"}, {"wait": PROMPT, "timeout": 60}]
        # The guest reboots and QEMU (-no-reboot) exits: the tap's own marker is the last step.
        s += [{"send": "tap 'Restart now'\n"}, {"wait": r"@@TAPPED@@", "timeout": 90}]
    elif case == "alongside":
        # An installed Windows, as its firmware sees it: Boot0007 "Windows Boot Manager" -> its ESP, first in BootOrder.
        wvar = struct.pack("<I", 7) + load_option("Windows Boot Manager", 1, win["esp_start"], win["esp_sectors"],
                                                   win["esp_guid"], "\\EFI\\Microsoft\\Boot\\bootmgfw.efi")
        b64 = base64.b64encode(wvar).decode()
        s += send(f"echo {b64} | base64 -d > /data/local/tmp/w.bin; dd if=/data/local/tmp/w.bin "
                  f"of={EV}/Boot0007-{EFI_GLOBAL} bs=4096 2>/dev/null; echo winentry=$?", 30)
        s += send(f"{{ printf '\\007\\000\\000\\000\\007\\000'; tail -c +5 {EV}/BootOrder-{EFI_GLOBAL}; }} > "
                  f"/data/local/tmp/bo.bin; dd if=/data/local/tmp/bo.bin of={EV}/BootOrder-{EFI_GLOBAL} bs=4096 "
                  f"conv=notrunc 2>/dev/null; echo bootorder=$?", 30)
        s += nvram_section("NVRAM-BEFORE")
        s += wait_ui("Choose your language", 180)
        s += tap("Continue", 4)
        s += wait_ui("STEP 2 OF 7", 120)
        s += tap("Continue", 4)
        s += wait_ui("STEP 3 OF 7", 60)
        s += tap("Install OpenBook", 2)
        s += tap("Continue", 4)
        s += wait_ui("STEP 4 OF 7", 90)
        s += [{"pause": 4}]
        s += tap(model, 2)
        s += tap("Install alongside", 2)
        s += shot("a4-disk-alongside")
        s += tap("View the plan", 6)
        s += shot("a4-plan")
        s += [{"send": "input keyevent 111\n"}, {"wait": PROMPT, "timeout": 30}, {"pause": 2}]
        s += tap("Continue", 5)
        s += wait_ui("STEP 5 OF 7", 90)
        # Without "Start OpenBook by default": OpenBook goes last in the boot order (owner decision 2026-10-17).
        s += wait_ui("OpenBook is added to this laptop", 30)
        s += shot("a5-confirm")
        s += tap("Type", 2)
        s += send("input text '" + model.replace(" ", "%s") + "'", 30)
        s += [{"pause": 3}]
        s += tapx("Install", 1)
        s += wait_ui("OpenBook is installed", 1500)
        s += wait_ui("OpenBook is in this laptop", 30)
        s += [{"pause": 4}]
        s += shot("a7-done")
        s += nvram_section("NVRAM-AFTER")
        s += section("INSTALLD-LOG", "cat /data/misc/openbook_install/installd.log", 120)
        s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
        s += [{"send": "sync\n"}, {"wait": PROMPT, "timeout": 60}]
    elif case == "alongside-default":
        # The firmware alone: Windows (the stand-in) starts by default, returns, and the firmware's boot menu lists
        # OpenBook last; Up (wraps to the last item) and Enter start it.
        s = [{"wait": r"windows-standin started: BootCurrent=\w+ BootOrder=[0-9A-F,]+", "timeout": 120},
             {"wait": "Please select boot device", "timeout": 60}, {"pause": 3}, {"shot": "fw-menu"},
             {"monitor": "sendkey up"}, {"pause": 2}, {"shot": "fw-menu-openbook"}, {"monitor": "sendkey ret"}]
        s += steps_common_boot()
        s += send("mount -t efivarfs efivarfs /sys/firmware/efi/efivars 2>/dev/null; true", 30)
        s += section("NVRAM-BOOT", "openbook-install nvram; getprop ro.boot.openbook.installed; getprop ro.boot.openbook.live; "
                     "getenforce; ls -l /dev/block/by-name", 60)
        s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
        # Test step for alongside-boot: start OpenBook's entry once more through BootNext.
        s += send("n=$(openbook-install nvram | tr '{' '\\n' | grep '\"description\":\"OpenBook\"' | head -n 1 | "
                  "sed 's/.*\"num\":\"\\([0-9A-F]*\\)\".*/\\1/'); echo NEWENTRY=$n; v=$((16#$n)); "
                  "printf '07000000%02x%02x' $((v & 255)) $((v >> 8)) | xxd -r -p > /data/local/tmp/bn.bin; "
                  f"dd if=/data/local/tmp/bn.bin of={EV}/BootNext-{EFI_GLOBAL} bs=4096 2>/dev/null; echo bootnext=$?", 30)
        s += section("NVRAM-NEXT", "openbook-install nvram", 60)
        s += [{"send": "sync\n"}, {"wait": PROMPT, "timeout": 60}]
    elif case in ("nvram-boot", "alongside-boot"):
        # The installed system, started by the firmware through OpenBook's own entry (no fallback path, no stick).
        s += send("mount -t efivarfs efivarfs /sys/firmware/efi/efivars 2>/dev/null; true", 30)
        s += section("NVRAM-BOOT", "openbook-install nvram; getprop ro.boot.openbook.installed; getprop ro.boot.openbook.live; "
                     "getenforce; ls -l /dev/block/by-name", 60)
        s += [{"pause": 5}] + shot("boot-screen", snap=False)
    elif case == "console":
        s += helpers()
        s += send("export SNAPDEV=/dev/block/nvme0n1p1", 30)
        s += section("INSTALLED", "getprop | grep -E 'ro.boot.(openbook|selinux|boot_part_uuid|serialno|slot_suffix|verifiedbootstate)|init.svc.openbook|ro.build.fingerprint|sys.boot_completed'; getenforce; ls -l /dev/block/by-name; cat /proc/partitions; df -k /data /metadata")
        s += section("INSTALLER-STATE", "pm query-activities -a android.intent.action.MAIN -c android.intent.category.LAUNCHER | grep -c org.openbook.installer; echo daemon=[$(getprop init.svc.openbook_installd)]; settings get global device_provisioned; dumpsys activity activities | grep -E 'topResumedActivity' | head -n 2")
        # OpenBook setup: the first screen of the installed system (SetupActivity), then through it to the desktop.
        s += send("input keyevent 224; wm dismiss-keyguard", 30)
        s += wait_ui("Language", 120)
        s += shot("8-setup-language")
        s += tap("Continue", 3)
        s += wait_ui("Connect to Wi-Fi", 60)
        s += shot("8-setup-wifi")
        s += tap("Continue", 3)
        s += wait_ui("Protect your laptop", 60)
        s += shot("8-setup-lock")
        s += tap("Start using OpenBook", 8)
        s += shot("9-desktop")
        s += section("AFTER-SETUP", "settings get global device_provisioned; settings get secure user_setup_complete; pm query-activities -a android.intent.action.MAIN -c android.intent.category.HOME | grep -c SetupActivity; dumpsys activity activities | grep -E 'topResumedActivity' | head -n 1")
        s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
    return s


def sections(text):
    out = {}
    for m in re.finditer(r"===([A-Z0-9-]+)-BEGIN===\r?\n(.*?)===\1-END===", text, re.S):
        out[m.group(1)] = m.group(2).replace("\r", "")
    return out


def check(a):
    R, Q = a.run, a.disks
    res = {"cases": {}}

    def chk(case, what, ok, detail=""):
        res["cases"].setdefault(case, []).append({"check": what, "ok": bool(ok), "detail": str(detail)[:400]})

    def load(case):
        d = f"{R}/{case}"
        if not os.path.exists(f"{d}/result.json"):
            return None, "", {}
        r = json.load(open(f"{d}/result.json"))
        t = open(f"{d}/serial.log", "rb").read().decode("utf-8", "replace")
        sec = sections(t)
        os.makedirs(f"{d}/sections", exist_ok=True)
        for k, v in sec.items():
            open(f"{d}/sections/{k.lower()}.txt", "w").write(v)
        return r, t, sec

    def shots_of(c):  # Android's screenshots (screens/), else QEMU's (shot-*.png)
        d = f"{R}/{c}/screens/shots"
        if os.path.isdir(d):
            return sorted("shot-" + f for f in os.listdir(d))
        return sorted(f for f in os.listdir(f"{R}/{c}") if f.startswith("shot-")) if os.path.isdir(f"{R}/{c}") else []
    r, t, sec = load("dryrun")
    if r:
        chk("dryrun", "every expect step matched", r["steps_done"] == r["steps"], f"{r['steps_done']}/{r['steps']} ({r['reason']})")
        chk("dryrun", "SELinux enforcing", "Enforcing" in sec.get("PROPS", ""), sec.get("PROPS", "")[-200:])
        chk("dryrun", "the wizard started by itself after boot", "org.openbook.installer" in sec.get("WIZARD-AUTOSTART", ""),
            sec.get("WIZARD-AUTOSTART", "")[:200])
        chk("dryrun", "openbook_installd runs in its own domain", "u:r:openbook_installd:s0" in sec.get("LABELS", ""),
            sec.get("LABELS", "")[-300:])
        chk("dryrun", "whole-disk nodes carry openbook_disk_block_device",
            sec.get("LABELS", "").count("openbook_disk_block_device") >= 2)
        try:
            plan = json.loads(sec.get("CLI-PLAN", "").strip().splitlines()[0])
        except (ValueError, IndexError):
            plan = {}
        chk("dryrun", "CLI dry run: a plan for the NVMe disk", plan.get("plan_sha256") and plan.get("target", {}).get("bus") == "nvme",
            sec.get("CLI-PLAN", "")[:300])
        chk("dryrun", "the app's dry run went through the daemon", "(dry run, read-only)" in sec.get("INSTALLD-LOG", ""))
        chk("dryrun", "screens captured: welcome, hardware, choose, disk, plan",
            all(any(s.startswith(f"shot-{p}") for s in shots_of("dryrun")) for p in ("1-welcome", "2-hardware", "3-choose", "4-disk", "4-plan")),
            shots_of("dryrun"))
        nv = f"{Q}/dryrun-nvme.img"
        if os.path.exists(nv):
            st = os.stat(nv)
            chk("dryrun", "the NVMe disk has no allocated block after the dry run (nothing written)", st.st_blocks == 0,
                f"{st.st_blocks} blocks")
        avc = [l for l in sec.get("AVC", "").splitlines() if "denied" in l and re.search(r"openbook|org\.openbook", l)]
        chk("dryrun", "no SELinux denial for the app or the daemon", not avc, "\n".join(avc[:5]))
    r, t, sec = load("install")
    if r:
        chk("install", "every expect step matched", r["steps_done"] == r["steps"], f"{r['steps_done']}/{r['steps']} ({r['reason']})")
        chk("install", "screens captured: confirm, typed, install, done",
            all(any(s.startswith(f"shot-{p}") for s in shots_of("install")) for p in ("5-confirm", "5-confirm-typed", "6-install", "7-done")),
            shots_of("install"))
        log = sec.get("INSTALLD-LOG", "")
        chk("install", "the daemon ran the install and it verified", re.search(r"verified \d+ partitions and files", log)
            and "ended: ok" in log, log[-300:])
        avc = [l for l in sec.get("AVC", "").splitlines() if "denied" in l and re.search(r"openbook|org\.openbook", l)]
        chk("install", "no SELinux denial for the app or the daemon (enforcing)", not avc, "\n".join(avc[:5]))
        chk("install", "the run ended with the guest's reboot (Restart now)", r["reason"].startswith("QEMU exited"), r["reason"])
    def nvjson(text):
        """The first `openbook-install nvram` JSON object in a section."""
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("{") and '"nvram"' in line:
                try:
                    return json.loads(line)["nvram"]
                except ValueError:
                    pass
        return {}

    def ob_entry(nv):
        return next((e for e in nv.get("entries", []) if e.get("description") == "OpenBook"), None)

    def hashes(text):
        return dict((os.path.basename(m.group(2)).split("-")[0], m.group(1))
                    for m in re.finditer(r"^([0-9a-f]{64})\s+(\S+)", text, re.M))

    installed_entry = None
    if r:
        nv = nvjson(sec.get("NVRAM-AFTER", ""))
        e = ob_entry(nv)
        installed_entry = e and e["num"]
        chk("install", "firmware entry: one \"OpenBook\" Boot#### -> HD(1, GPT)/\\EFI\\OpenBook\\systemd-bootx64.efi, first in BootOrder",
            e and e.get("partition") == 1 and e.get("path") == "\\EFI\\OpenBook\\systemd-bootx64.efi" and
            nv.get("boot_order", [None])[0] == e["num"], {"entry": e, "boot_order": nv.get("boot_order")})
        chk("install", "efivarfs mounted by init with its own label (openbook_efivarfs)",
            "openbook_efivarfs" in sec.get("LABELS", "") and "efivarfs /sys/firmware/efi/efivars" in sec.get("LABELS", ""),
            sec.get("LABELS", "")[-300:])
    r, t, sec = load("nvram-boot")
    if r:
        nv = nvjson(sec.get("NVRAM-BOOT", ""))
        e = ob_entry(nv)
        s = sec.get("NVRAM-BOOT", "")
        chk("nvram-boot", "every expect step matched", r["steps_done"] == r["steps"], f"{r['steps_done']}/{r['steps']} ({r['reason']})")
        lst = open(f"{R}/nvram-boot/esp-EFI-listing.txt").read() if os.path.exists(f"{R}/nvram-boot/esp-EFI-listing.txt") else ""
        chk("nvram-boot", "the copy has no fallback path: EFI/BOOT/BOOTX64.EFI deleted",
            lst and "::/EFI/BOOT/BOOTX64.EFI" not in lst.upper(), lst.strip()[:200])
        chk("nvram-boot", "the firmware kept the install's BootOrder (OpenBook first; no bootindex hints)",
            installed_entry and nv.get("boot_order", [None])[0] == installed_entry, nv.get("boot_order"))
        chk("nvram-boot", "OVMF started the installed system through OpenBook's entry (BootCurrent = the entry the install made)",
            e and nv.get("boot_current") == e["num"] == installed_entry, {"boot_current": nv.get("boot_current"),
                                                                           "entry": e and e["num"], "installed": installed_entry})
        links = re.findall(r" (\S+) -> (/dev/block/\S+)", s)
        chk("nvram-boot", "Android booted from the NVMe disk (by-name links on nvme0n1, installed=whole)",
            "BOOTDONE=1" in t and links and all("nvme0n1" in x for _, x in links) and "\nwhole" in s, len(links))
    r, t, sec = load("alongside")
    if r:
        before, after = (nvjson(sec.get(k, "")) for k in ("NVRAM-BEFORE", "NVRAM-AFTER"))
        hb, ha = hashes(sec.get("NVRAM-BEFORE", "")), hashes(sec.get("NVRAM-AFTER", ""))
        e = ob_entry(after)
        win = next((x for x in before.get("entries", []) if x.get("description") == "Windows Boot Manager"), {})
        chk("alongside", "every expect step matched", r["steps_done"] == r["steps"], f"{r['steps_done']}/{r['steps']} ({r['reason']})")
        chk("alongside", "before: Windows Boot Manager (Boot0007) first in BootOrder", before.get("boot_order", [None])[0] == "0007"
            and win.get("num") == "0007", before.get("boot_order"))
        chk("alongside", "the install verified (daemon, enforcing)", re.search(r"verified \d+ partitions and files", sec.get("INSTALLD-LOG", ""))
            and "Enforcing" in sec.get("PROPS", ""))
        chk("alongside", "one new \"OpenBook\" entry -> HD(1, GPT, the Windows ESP)/\\EFI\\OpenBook\\systemd-bootx64.efi",
            e and e.get("partition") == 1 and e.get("partuuid") == win.get("partuuid") and
            e.get("path") == "\\EFI\\OpenBook\\systemd-bootx64.efi" and
            len(after.get("entries", [])) == len(before.get("entries", [])) + 1, e)
        chk("alongside", "Windows Boot Manager byte-identical; BootOrder = the old order plus OpenBook at the end "
            "(no consent; owner decision 2026-10-17)",
            hb.get("Boot0007") and hb.get("Boot0007") == ha.get("Boot0007") and e and
            after.get("boot_order") == before.get("boot_order", []) + [e["num"]],
            {"before": before.get("boot_order"), "after": after.get("boot_order"), "Boot0007": [hb.get("Boot0007"), ha.get("Boot0007")]})
        chk("alongside", "Confirm and Done say OpenBook is added to the boot menu and Windows stays the default",
            r["steps_done"] == r["steps"] and all(any(x.startswith(f"shot-{p}") for x in shots_of("alongside"))
                                                  for p in ("a5-confirm", "a7-done")), shots_of("alongside"))
        chk("alongside", "no SELinux denial for the app or the daemon", not [l for l in sec.get("AVC", "").splitlines()
                                                                          if "denied" in l and re.search(r"openbook|org\.openbook", l)])
        alongside_entry, alongside_order = e and e["num"], after.get("boot_order")
    else:
        alongside_entry, alongside_order = None, None
    r, t, sec = load("alongside-default")
    if r:
        nv, nxt = nvjson(sec.get("NVRAM-BOOT", "")), nvjson(sec.get("NVRAM-NEXT", ""))
        s = sec.get("NVRAM-BOOT", "")
        chk("alongside-default", "every expect step matched", r["steps_done"] == r["steps"], f"{r['steps_done']}/{r['steps']} ({r['reason']})")
        m = re.search(r"windows-standin started: BootCurrent=(\w+) BootOrder=([0-9A-F,]+)", t)
        order = m.group(2).split(",") if m else []
        chk("alongside-default", "the install's NVRAM, no hints: the firmware starts Windows Boot Manager by default "
            "(the stand-in reports BootCurrent=0007; OpenBook last in BootOrder)",
            m and m.group(1) == "0007" and order[:1] == ["0007"] and alongside_entry and order[-1:] == [alongside_entry],
            m and m.group(0))
        i = t.find("Please select boot device")  # the menu's items come before its footer
        menu = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", t[i:t.find("ESC to exit", i)]) if i >= 0 else ""
        chk("alongside-default", "the firmware's boot menu lists OpenBook (it is in BootOrder)",
            "OpenBook" in menu and "Windows Boot Manager" in menu and
            all(any(x.startswith(f"shot-{p}") for x in shots_of("alongside-default")) for p in ("fw-menu", "fw-menu-openbook")),
            re.findall(r"OpenBook|Windows Boot Manager", menu)[:4])
        chk("alongside-default", "picked in the boot menu, the firmware started OpenBook's entry (BootCurrent = the new entry)",
            alongside_entry and nv.get("boot_current") == alongside_entry and not nv.get("boot_next"),
            {"boot_current": nv.get("boot_current"), "boot_next": nv.get("boot_next"), "entry": alongside_entry})
        chk("alongside-default", "Windows still first, OpenBook still last in BootOrder",
            nv.get("boot_order", [None])[0] == "0007" and alongside_entry and nv.get("boot_order", [])[-1:] == [alongside_entry],
            nv.get("boot_order"))
        links = re.findall(r" (\S+) -> (/dev/block/\S+)", s)
        chk("alongside-default", "Android booted from the Windows disk's new partitions (installed=alongside, enforcing)",
            "BOOTDONE=1" in t and links and all("nvme0n1" in x for _, x in links) and "\nalongside" in s and "Enforcing" in s,
            len(links))
        chk("alongside-default", "no SELinux denial for OpenBook's domains", not [l for l in sec.get("AVC", "").splitlines()
                                                                                if "denied" in l and re.search(r"openbook", l)])
        chk("alongside-default", "test step: BootNext points at OpenBook's entry", alongside_entry and nxt.get("boot_next") == alongside_entry,
            nxt.get("boot_next"))
    r, t, sec = load("alongside-boot")
    if r:
        nv = nvjson(sec.get("NVRAM-BOOT", ""))
        s = sec.get("NVRAM-BOOT", "")
        chk("alongside-boot", "every expect step matched", r["steps_done"] == r["steps"], f"{r['steps_done']}/{r['steps']} ({r['reason']})")
        chk("alongside-boot", "OVMF started OpenBook through its entry once (BootCurrent = the new entry, BootNext used up)",
            alongside_entry and nv.get("boot_current") == alongside_entry and not nv.get("boot_next"),
            {"boot_current": nv.get("boot_current"), "boot_next": nv.get("boot_next"), "entry": alongside_entry})
        chk("alongside-boot", "Windows stays first in BootOrder; its entry is still there",
            nv.get("boot_order", [None])[0] == "0007" and any(x.get("description") == "Windows Boot Manager" for x in nv.get("entries", [])),
            nv.get("boot_order"))
        links = re.findall(r" (\S+) -> (/dev/block/\S+)", s)
        chk("alongside-boot", "Android booted from the Windows disk's new partitions (installed=alongside)",
            "BOOTDONE=1" in t and links and all("nvme0n1" in x for _, x in links) and "\nalongside" in s, len(links))
    r, t, sec = load("installed")
    if r:
        sh = shots_of("installed")
        chk("installed", "the installed disk boots without the stick (screenshots)", len(sh) >= 5, sh)
    r, t, sec = load("console")
    if r:
        s = sec.get("INSTALLED", "")
        chk("console", "every expect step matched", r["steps_done"] == r["steps"], f"{r['steps_done']}/{r['steps']} ({r['reason']})")
        chk("console", "boot_completed from the NVMe disk", "BOOTDONE=1" in t)
        links = re.findall(r" (\S+) -> (/dev/block/\S+)", s)
        chk("console", "every by-name link points at the NVMe disk", links and all("nvme0n1" in x for _, x in links),
            ", ".join(sorted({os.path.basename(x) for _, x in links}))[:200])
        chk("console", "no live flags; installed=whole; SELinux enforcing",
            "ro.boot.openbook.live" not in s and "[ro.boot.openbook.installed]: [whole]" in s and "Enforcing" in s, s[:300])
        st = sec.get("INSTALLER-STATE", "")
        lines = st.strip().splitlines()
        chk("console", "installer launcher entry off and daemon never started on the installed system",
            lines and lines[0].strip() == "0" and "daemon=[]" in st, lines[:2])
        chk("console", "first screen of the installed system is OpenBook setup",
            "org.openbook.installer/.SetupActivity" in st, st[-200:])
        aft = sec.get("AFTER-SETUP", "").strip().splitlines()
        chk("console", "after setup: provisioned, setup complete, setup off, the launcher on top",
            len(aft) >= 4 and aft[0].strip() == "1" and aft[1].strip() == "1" and aft[2].strip() == "0" and
            "launcher" in aft[3].lower(), aft)
        chk("console", "setup screens captured", all(any(x.startswith(f"shot-{p}") for x in shots_of("console"))
                                                    for p in ("8-setup-language", "8-setup-wifi", "8-setup-lock", "9-desktop")),
            shots_of("console"))
        avc = [l for l in sec.get("AVC", "").splitlines() if "denied" in l]
        res["console_avc"] = avc[:50]
        chk("console", "AVC denials on the installed system (reported, not gated)", True, f"{len(avc)} lines")
    total = sum(len(v) for v in res["cases"].values())
    passed = sum(x["ok"] for v in res["cases"].values() for x in v)
    res.update(passed=passed, total=total, image=os.path.basename(a.image))
    json.dump(res, open(f"{R}/results.json", "w"), indent=1)
    with open(f"{R}/SUMMARY.md", "w") as f:
        f.write(f"# Installer wizard in QEMU: {os.path.basename(a.image)}\n\n{passed}/{total} checks passed.\n\n"
                "| Case | Check | Result | Detail |\n|---|---|---|---|\n")
        for c, v in res["cases"].items():
            for x in v:
                f.write(f"| {c} | {x['check']} | {'PASS' if x['ok'] else 'FAIL'} | {x['detail'].replace('|', '/').replace(chr(10), ' ')[:160]} |\n")
    print(open(f"{R}/SUMMARY.md").read())
    return 0 if passed == total else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("expect")
    e.add_argument("case")
    e.add_argument("out")
    e.add_argument("--target", default="nvme-QEMU_NVMe_Ctrl_internal0")
    e.add_argument("--model", default="QEMU NVMe Ctrl")
    e.add_argument("--win", help="mkwin's JSON (the alongside case)")
    m = sub.add_parser("mkwin")
    m.add_argument("out")
    c = sub.add_parser("check")
    c.add_argument("--run", required=True)
    c.add_argument("--disks", required=True)
    c.add_argument("--image", required=True)
    a = ap.parse_args()
    if a.cmd == "expect":
        json.dump(expect(a.case, a.target, a.model, json.loads(a.win) if a.win else None), open(a.out, "w"), indent=0)
        return 0
    if a.cmd == "mkwin":
        mkwin(a.out)
        return 0
    return check(a)


if __name__ == "__main__":
    sys.exit(main())
