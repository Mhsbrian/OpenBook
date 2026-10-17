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
The stick boots a test entry at 2880x1800 with density 240 (the G14's panel and scaling), virtio-vga.

usage: wizard-qemu.py expect CASE OUT.json [--target BY-ID] [--model MODEL]      write CASE's expect script
       wizard-qemu.py check --run DIR --disks DIR --image IMG                    results.json + SUMMARY.md
"""
import argparse
import base64
import gzip
import json
import os
import re
import subprocess
import sys

PROMPT = r"console:/ # "
# Shell helpers typed into the root shell: tap a node by its text or content description (prefix), wait for one.
HELPERS = r"""
while read -r k n v; do [ "$k" = export ] && export "$n=$v"; done < /data/system/environ/classpath
ui() { uiautomator dump /data/local/tmp/ui.xml >/dev/null 2>&1; }
bnd() { ui; tr '>' '\n' < /data/local/tmp/ui.xml | grep -F 'package="org.openbook.installer"' | grep -F -e "text=\"$1" -e "content-desc=\"$1" | head -n 1 | sed -n 's/.*bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]".*/\1 \2 \3 \4/p'; }
tap() { b=$(bnd "$1"); if [ -z "$b" ]; then echo "@@NOTFOUND[$1]@@"; return 1; fi; set -- $b; input tap $(( ($1+$3)/2 )) $(( ($2+$4)/2 )); echo "@@TAPPED@@"; }
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


def expect(case, target, model):
    if case == "installed":
        return []  # no serial console on the installed entry: screenshots only (wizard-qemu.sh --shot)
    s = steps_common_boot()
    if case in ("dryrun", "install"):
        s += helpers()
        s += section("PROPS", "getprop | grep -E 'ro.boot.(openbook|selinux|boot_part_uuid)|init.svc.openbook|ro.build.fingerprint'; getenforce")
        s += section("LABELS", "ls -lZ /dev/block | grep -E ' (sd[a-z]+|nvme0n1)$'; ls -lZ /dev/socket/openbook_installd; ps -AZ | grep -E 'openbook|installer'")
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
        s += [{"send": "sync\n"}, {"wait": PROMPT, "timeout": 60}]
        # The guest reboots and QEMU (-no-reboot) exits: the tap's own marker is the last step.
        s += [{"send": "tap 'Restart now'\n"}, {"wait": r"@@TAPPED@@", "timeout": 90}]
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
    c = sub.add_parser("check")
    c.add_argument("--run", required=True)
    c.add_argument("--disks", required=True)
    c.add_argument("--image", required=True)
    a = ap.parse_args()
    if a.cmd == "expect":
        json.dump(expect(a.case, a.target, a.model), open(a.out, "w"), indent=0)
        return 0
    return check(a)


if __name__ == "__main__":
    sys.exit(main())
