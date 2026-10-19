#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The microG add-on on the G14 product in QEMU/KVM + OVMF (ANAL-210), image files only: expect scripts for
scripts/installer/qemu-run.py (a root shell on the serial console, as scripts/installer/wizard-qemu.py) and the checks.

Cases (addon-qemu.sh runs them):
  plain        this branch's live image, no add-on, SELinux enforcing: openbook-addons only logs that there is none,
               no microG package, no denial for an OpenBook domain; the package list (compared with "main")
  main         the comparison image built from main, the same commands: the package list
  addon        the same image with the add-on (add-to-image.sh): openbook-addons installs the three APKs after
               boot_completed; versions, granted permissions, app-op, battery exemption, the signatures apps see,
               microG's self-check (UI dump and screenshot), the kernel-log lines, no denial
  addon-2      the same stick booted again: nothing reinstalled; microG is now the network and fused location provider
  addon-logs   the same stick's "save logs" entry: the stick's helper captures what openbook-addons did, microG's
               packages and the location providers (its ADDONS section), and writes them to the stick
  install      the add-on stick and a blank NVMe disk: `openbook-install addons`, a whole-disk plan with
               --addon microg, the unattended install (as e2e-qemu.py's), then power-off
  installed    the installed disk alone (serial console copy): its first start installs microG from its own EFI
               partition; no denial

usage: addon-qemu.py expect CASE OUT.json
       addon-qemu.py check --run DIR
"""
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_s = importlib.util.spec_from_file_location("wizard_qemu", os.path.join(HERE, "../installer/wizard-qemu.py"))
W = importlib.util.module_from_spec(_s)
_s.loader.exec_module(W)
PROMPT = W.PROMPT
TARGET = "nvme-QEMU_NVMe_Ctrl_internal0"
PKGS = ("com.google.android.gms", "com.android.vending", "com.google.android.gsf")


def section(name, cmd, timeout=180):
    # The end marker must start a line (the shell echoes the typed command, which contains it too).
    return [{"send": f"echo ==={name}-BEGIN===; {cmd}; echo ==={name}-END===\n"},
            {"wait": f"\n==={name}-END===", "timeout": timeout}, {"wait": PROMPT, "timeout": 30}]


def poweroff():
    return [{"send": "sync; reboot -p\n"},
            {"wait": r"reboot: Power down|ACPI: PM: Preparing to enter system sleep state S5|Power down", "timeout": 120}]


def boot(snapdev=None):
    s = W.steps_common_boot() + W.helpers()
    if snapdev:  # screenshots go to this FAT partition (the helpers' default is the stick's)
        s += W.send(f"export SNAPDEV={snapdev}", 30)
    s += section("PROPS", "getprop | grep -E 'ro.boot.(openbook|selinux|boot_part_uuid)|ro.build.fingerprint'; getenforce")
    # openbook-addons starts at boot_completed; wait until init reports it stopped (it is a oneshot).
    s += section("ADDONS-WAIT", "i=0; while [ \"$(getprop init.svc.openbook_addons)\" != stopped ] && [ $i -lt 240 ]; do sleep 2; i=$((i+2)); done; "
                                "echo svc=[$(getprop init.svc.openbook_addons)] after=${i}s", 300)
    s += section("ADDONS", "cat /data/misc/openbook_addons/addons.log; echo; echo LAST-RUN; cat /data/misc/openbook_addons/last-run.json; "
                           "echo; echo STATE; cat /data/misc/openbook_addons/microg.json 2>&1; echo; ls -lZ /data/misc/openbook_addons")
    s += section("KMSG", "dmesg | grep -E 'openbook_addons|openbook-addons' | grep -v 'avc: ' | tail -n 30")
    s += section("PKGS", "pm list packages | sort")
    return s


def wizard_disk(addon):
    """The wizard (it starts by itself on a live stick) up to its disk screen, where the first eligible disk is
    preselected. With the add-on on the stick, its switch must be there and off; ticked, "View the plan" lists the
    add-on check. Without it, there is no switch."""
    s = W.wait_ui("Choose your language", 180) + W.tap("Continue", 4)
    s += W.wait_ui("STEP 2 OF 7", 120) + W.tap("Continue", 4)
    s += W.wait_ui("STEP 3 OF 7", 60) + W.tap("Install OpenBook", 2) + W.tap("Continue", 4)
    s += W.wait_ui("Choose your image base", 60) + W.tap("Continue", 4)
    s += W.wait_ui("STEP 4 OF 7", 90) + [{"pause": 5}]
    s += section("WIZARD-DISK", "ui; cat /data/local/tmp/ui.xml; echo", 60)
    s += W.shot("wizard-disk")
    if addon:
        s += W.tap("Google services compatibility (microG)", 3)
        s += section("WIZARD-SWITCH", "ui; cat /data/local/tmp/ui.xml; echo", 60)
        s += W.tap("View the plan", 12)
        s += section("WIZARD-PLAN", "ui; cat /data/local/tmp/ui.xml; echo", 60)
        s += W.shot("wizard-plan-addon")
    s += [{"send": "input keyevent 111\n"}, {"wait": PROMPT, "timeout": 30}, {"pause": 2}]
    return s


def tail():
    return section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120) + poweroff()


def microg_checks():
    s = section("MICROG", "pm list packages --show-versioncode | grep -E 'com.google.android.gms$|com.google.android.gms |com.android.vending |com.google.android.gsf '; "
                          "for p in com.google.android.gms com.android.vending com.google.android.gsf; do echo PKG $p; "
                          "dumpsys package $p | grep -E 'codePath=|versionCode=|installerPackageName=|pkgFlags='; done; "
                          "echo GRANTED; dumpsys package com.google.android.gms | grep -E 'granted=true' | sed 's/^ *//' | sort -u; "
                          "echo APPOPS; appops get com.google.android.gms SYSTEM_ALERT_WINDOW; "
                          "echo DEVICEIDLE; cmd deviceidle whitelist | grep -E 'com.google.android.gms'; "
                          "echo LAUNCHER; pm query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER "
                          "| grep -E 'com.google.android.gms/|com.android.vending/|com.google.android.gsf/'", 120)
    # microG's self-check, as the user opens it: the UI tree (labels and checkboxes) and a screenshot.
    s += W.send("am start -W -n 'com.google.android.gms/org.microg.gms.ui.SelfCheckFragment$AsActivity' >/dev/null; sleep 10", 60)
    s += section("SELFCHECK-UI", "ui; cat /data/local/tmp/ui.xml; echo", 60)
    s += W.shot("selfcheck")
    s += W.send("input swipe 900 1000 900 200 400; sleep 2", 30)  # the rest of the list
    s += section("SELFCHECK-UI2", "ui; cat /data/local/tmp/ui.xml; echo", 60)
    s += W.shot("selfcheck-2")
    s += W.send("input keyevent 111; am force-stop com.google.android.gms", 30)
    return s


def expect(case):
    if case == "plain":
        return boot() + wizard_disk(False) + tail()
    if case == "main":
        return boot() + tail()
    if case == "addon":
        return boot() + microg_checks() + tail()
    if case == "addon-2":
        s = boot()
        s += section("LOCATION", "dumpsys location | grep -A9 -E '^ *(network|fused) provider:' | grep -E 'provider:|identity=|target service='")
        return s + tail()
    if case == "addon-logs":  # no shell: the helper does everything and powers off
        return [{"wait": "openbook-live: live boot: boot_part_uuid=", "timeout": 120},
                {"wait": r"openbook-live: logs: saving to openbook/logs/live-\d+", "timeout": 60},
                {"wait": "openbook-live: logs: (no second stage|Android second stage seen)", "timeout": 300},
                {"wait": "openbook-live: logs: done: ", "timeout": 1200}]
    if case == "install":
        s = boot() + wizard_disk(True)
        s += section("ADDON-LIST", "openbook-install addons", 120)
        s += section("PLAN", f"openbook-install plan --target /dev/disk/by-id/{TARGET} --layout whole --locale en-US --keyboard us "
                             f"--addon microg --out /data/local/tmp/plan.json >/dev/null; echo PLAN-RC=$?; "
                             f"grep -o '\"request\":{{[^}}]*}}' /data/local/tmp/plan.json; grep -o '\"op\":\"check_addon\",\"text\":\"[^\"]*\"' /data/local/tmp/plan.json", 120)
        s += section("APPLY", f"OPENBOOK_INSTALL_ERASE=/dev/disk/by-id/{TARGET} openbook-install apply --plan /data/local/tmp/plan.json "
                              f"--confirm-disk /dev/disk/by-id/{TARGET}; echo APPLY-RC=$?", 900)
        return s + tail()
    if case == "installed":
        return boot("/dev/block/nvme0n1p1") + microg_checks() + tail()
    sys.exit(f"unknown case {case}")


# ------------------------------------------------------------------------------------------- checks
def sections(serial):
    out = {}
    for m in re.finditer(r"\n===(\S+?)-BEGIN===\r?\n(.*?)\n===\1-END===", serial, re.S):
        out[m.group(1)] = m.group(2).replace("\r", "")
    return out


def selfcheck(xml):
    items, last = [], None
    for m in re.finditer(r"<node [^>]*>", xml):
        n = m.group(0)
        t = (re.search(r' text="([^"]*)"', n) or [None, ""])[1]
        cls = (re.search(r' class="([^"]*)"', n) or [None, ""])[1]
        if cls.endswith("CheckBox"):
            if last:
                items.append((last, (re.search(r' checked="(\w+)"', n) or [None, ""])[1] == "true"))
                last = None
        elif t.endswith(":"):
            last = t
    return items


def switch_state(xml_text, label="Google services compatibility (microG)"):
    """The checked state of the checkable node (Compose's toggleable row) whose subtree shows LABEL: True/False, or
    None when no such node is on the screen."""
    import xml.etree.ElementTree as ET
    a, b = xml_text.find("<?xml"), xml_text.rfind("</hierarchy>")
    if a < 0 or b < 0:
        return None
    try:
        root = ET.fromstring(xml_text[a:b + len("</hierarchy>")])
    except ET.ParseError:
        return None
    for n in root.iter("node"):
        if n.get("checkable") == "true" and any((d.get("text") or "").startswith(label) for d in n.iter("node")):
            return n.get("checked") == "true"
    return None


def avc_ours(text):
    return [l for l in text.splitlines() if re.search(r"avc: +denied", l) and re.search(r"openbook", l)]


def check(run):
    res = []

    def chk(case, what, ok, detail=""):
        res.append({"case": case, "check": what, "ok": bool(ok), "detail": "" if ok else str(detail)[:400]})
        print(("PASS " if ok else "FAIL ") + f"{case}: {what}" + ("" if ok else f"  [{str(detail)[:200]}]"))

    def load(case):
        d = f"{run}/{case}"
        if not os.path.exists(f"{d}/result.json"):
            return None, {}
        r = json.load(open(f"{d}/result.json"))
        serial = open(f"{d}/serial.log", errors="replace").read()
        chk(case, "every expect step matched", r.get("steps_done") == r.get("steps"),
            f"{r.get('steps_done')}/{r.get('steps')} ({r.get('reason')})")
        return r, sections(serial)

    pk = {}
    import glob
    r, _ = load("addon-logs")
    if r is not None:
        caps = sorted(glob.glob(f"{run}/addon-logs/stick-logs/logs/live-*/collect-*.txt"))
        text = open(caps[-1], errors="replace").read() if caps else ""
        m = re.search(r"===ADDONS===\n(.*?)\n===", text, re.S)
        sec = m.group(1) if m else ""
        chk("addon-logs", "the helper's capture has the ADDONS section", m, caps[-1:] or "no capture")
        chk("addon-logs", "... with openbook-addons' state and microG's three packages",
            '"result":"installed"' in sec and all(re.search(rf"package:{re.escape(p)} versionCode:", sec) for p in PKGS), sec[-400:])
        chk("addon-logs", "... and microG as the network provider, coordinates redacted",
            re.search(r"network provider:\s*\n(\s*last location=.*\n)?\s*identity=\d+/com.google.android.gms", sec)
            and not re.search(r"Location\[\w+ -?\d+\.\d+,", sec), sec[-400:])
    for case in ("plain", "main", "addon", "addon-2", "install", "installed"):
        r, sec = load(case)
        if r is None:
            continue
        chk(case, "SELinux enforcing", "Enforcing" in sec.get("PROPS", ""), sec.get("PROPS", "")[-200:])
        ours = avc_ours(sec.get("AVC", ""))
        chk(case, "no denial for an OpenBook domain", not ours, ours[:3])
        pk[case] = sorted(l.strip() for l in sec.get("PKGS", "").splitlines() if l.startswith("package:"))
        log = sec.get("ADDONS", "")
        if case == "main":
            continue
        if case == "plain":
            chk(case, "openbook-addons ran and found no add-on", "microg: not on the boot disk" in log and
                '"result":"absent"' in log, log[-300:])
            wd = sec.get("WIZARD-DISK", "")
            chk(case, "the wizard's disk screen has no add-on switch",
                "<hierarchy" in wd and "Google services compatibility" not in wd, wd[-300:])
            chk(case, "no microG package", not any(f"package:{p}" in pk[case] for p in PKGS), pk[case])
        if case in ("addon", "installed"):
            chk(case, "openbook-addons installed the add-on", '"result":"installed"' in log and "microg 0.3.17.252432: done" in log,
                log[-400:])
            m = sec.get("MICROG", "")
            chk(case, "the three packages at the pinned versions",
                all(re.search(rf"package:{re.escape(p)} versionCode:{v}\b", m) for p, v in
                    zip(PKGS, (252432034, 84022634, 8))), m[:400])
            chk(case, "installed in /data as normal apps", m.count("codePath=/data/app/") == 3, m[:600])
            for perm in ("ACCESS_FINE_LOCATION", "ACCESS_BACKGROUND_LOCATION", "POST_NOTIFICATIONS", "RECEIVE_SMS",
                         "INTERACT_ACROSS_USERS"):
                chk(case, f"GmsCore holds {perm}", re.search(rf"android.permission.{perm}: granted=true", m), "")
            chk(case, "SYSTEM_ALERT_WINDOW allowed", re.search(r"SYSTEM_ALERT_WINDOW: allow", m), m[-300:])
            chk(case, "battery-optimisation exemption", "com.google.android.gms" in m.split("DEVICEIDLE")[-1].split("LAUNCHER")[0], m[-200:])
            launch = m.split("LAUNCHER")[-1]
            chk(case, "microG Services has a launcher entry", "com.google.android.gms/" in launch, launch[-300:])
            res[-1]["detail"] = launch.strip().replace("\n", "; ")[:300]
            items = list(dict(selfcheck(sec.get("SELFCHECK-UI", "")) + selfcheck(sec.get("SELFCHECK-UI2", ""))).items())
            chk(case, f"microG self-check: all green ({sum(ok for _, ok in items)}/{len(items)})",
                items and all(ok for _, ok in items), [t for t, ok in items if not ok] or "no items")
            chk(case, "init started openbook_addons after boot_completed", "starting service 'openbook_addons'" in sec.get("KMSG", ""),
                sec.get("KMSG", "")[-200:])
        if case == "addon-2":
            chk(case, "second boot: nothing reinstalled (already installed)", '"result":"already_installed"' in log, log[-300:])
            loc = sec.get("LOCATION", "")
            chk(case, "microG is the network location provider (installed in /data)",
                re.search(r"network provider:\s*\n\s*identity=\d+/com.google.android.gms", loc), loc)
            chk(case, "microG is the fused location provider", re.search(r"fused provider:\s*\n\s*identity=\d+/com.google.android.gms", loc), loc)
        if case == "install":
            wd = sec.get("WIZARD-DISK", "")
            chk(case, "the wizard's disk screen shows the microG switch, off", switch_state(wd) is False, switch_state(wd))
            sw = sec.get("WIZARD-SWITCH", "")
            chk(case, "tapping it turns it on", switch_state(sw) is True, switch_state(sw))
            # uiautomator writes the operation's inner quotes unescaped, so look for the text, not the attribute.
            wp = sec.get("WIZARD-PLAN", "")
            chk(case, "\"View the plan\" then lists the add-on check",
                re.search(r"2\. Check the add-on .Google services compatibility \(microG\). 0\.3\.17\.252432", wp), wp[-300:])
            a = sec.get("ADDON-LIST", "")
            chk(case, "the stick carries the add-on (openbook-install addons)", '"on_stick":true' in a, a[-300:])
            p = sec.get("PLAN", "")
            chk(case, "the plan names the add-on and checks it", "PLAN-RC=0" in p and '"addons":["microg"]' in p and "check_addon" in p, p[-300:])
            ap = sec.get("APPLY", "")
            j = [json.loads(l) for l in ap.splitlines() if l.startswith("{") and '"openbook-install-report/1"' in l]
            chk(case, "install ok and verified", "APPLY-RC=0" in ap and j and j[-1].get("ok") and j[-1].get("verified"), ap[-400:])
    if "plain" in pk and "main" in pk:
        a, b = set(pk["plain"]), set(pk["main"])
        chk("plain", "the same packages as the image from main", a == b, {"only here": sorted(a - b), "only main": sorted(b - a)})
    if "addon" in pk and "plain" in pk:
        extra = sorted(set(pk["addon"]) - set(pk["plain"]))
        chk("addon", "exactly microG's three packages more than without the add-on",
            extra == sorted(f"package:{p}" for p in PKGS), extra)
    ok = sum(r["ok"] for r in res)
    json.dump({"schema": "openbook-addon-qemu/1", "passed": ok, "total": len(res), "checks": res},
              open(f"{run}/results.json", "w"), indent=1)
    with open(f"{run}/SUMMARY.md", "w") as f:
        f.write(f"# microG add-on in QEMU (ANAL-210): {ok}/{len(res)}\n\n| Case | Check | Result |\n|---|---|---|\n")
        for r in res:
            f.write(f"| {r['case']} | {r['check']} | {'pass' if r['ok'] else 'FAIL: ' + r['detail'][:150]} |\n")
    print(f"{ok}/{len(res)} passed")
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "expect":
        json.dump(expect(sys.argv[2]), open(sys.argv[3], "w"), indent=1)
    elif len(sys.argv) == 4 and sys.argv[1] == "check" and sys.argv[2] == "--run":
        sys.exit(check(sys.argv[3]))
    else:
        sys.exit(__doc__)
