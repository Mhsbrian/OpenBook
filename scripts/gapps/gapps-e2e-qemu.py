#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The bring-your-own GApps step end to end in QEMU/KVM + OVMF (ANAL-211), on the installer's harness
(scripts/installer/e2e-qemu.py: its stick, Windows-like disk, expect sections and disk inspection; qemu-run.py).
Only the synthetic packages of scripts/gapps/make-synthetic.py are used; no Google software.

Cases (the live ones boot the 16 GiB stick copy, SELinux enforcing, with a USB drive "GAPPSUSB" holding the packages):
  g-cut-N      gapps-check of a package that touches the framework (refused) and of the reference package, plan
               --gapps, the unattended whole-disk install over the Windows-like disk, and a power cut at the N-th
               point of the package step (CUTS below); each run restarts on the previous run's cut disk
  g-ui         the wizard: disk screen, the advanced switch, the package page, the system file picker on the USB drive,
               the check, the confirmation, the Confirm screen with the package, the install, Done
  g-cli        the same install, unattended (instead of g-ui)
  g-installed  a console copy of the installed disk alone: enforcing; product mounted through dm-verity with the
               report's root digest and vbmeta digest; every product file readable; the synthetic apps installed from
               /product, privileged where in priv-app/, with the package's privileged permission (allowlisted), its
               default-granted runtime permissions, its power-save exemption and feature; OpenBook setup's
               registration page with the (fake) GSF Android ID; Settings > About's entry
  g-verity     a copy of the installed disk with one byte flipped in a package file inside the rebuilt product:
               reading that file trips dm-verity (the new hashtree covers the new data)

usage: gapps-e2e-qemu.py expect CASE OUT.json
       gapps-e2e-qemu.py report-of CASE_DIR OUT.json                         the install report a case printed
       gapps-e2e-qemu.py corrupt DISK REPORT.json PATH OUT.json              flip a byte of PATH in the rebuilt product
       gapps-e2e-qemu.py check --run DIR --disks DIR --packages DIR
"""
import argparse
import importlib.util
import json
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


E2E = _load("e2e_qemu", os.path.join(HERE, "../installer/e2e-qemu.py"))
EGT = _load("engine_gapps_test", os.path.join(HERE, "engine-gapps-test.py"))
W, section, poweroff, apply_cmd, TARGET, PROMPT = E2E.W, E2E.section, E2E.poweroff, E2E.apply_cmd, E2E.TARGET, E2E.PROMPT
REF = "openbook-synthetic-gapps-x86_64-37"
# Where each g-cut-N stops the install (the engine's --events lines; see e2e-qemu.py's CUTS for the base install).
# The cuts install the large package (a 256 MiB app), so its check and the product build take seconds and a cut
# lands inside them; the stick's last source hash is followed by the ESP files and the staged package's check.
CUTS = {
    1: (r"source super: \d+ bytes, sha256 ok", 0.3),             # checking the staged package: nothing written
    2: (r"product: building product_a", 1.0),                     # in the middle of the new product
    3: (r"product: \d+ bytes \(image", 0),                        # product built; super's metadata not written
    4: (r"vbmeta_a: rebuilt vbmeta", 0),                          # vbmeta_a written; the GPT not yet
    5: (r'"step":"verify","state":"running"', 0.5),               # the new table written, not activated
}
EXPECTED_STATE = {1: "old-table", 2: "blank", 3: "blank", 4: "blank", 5: "new-not-activated"}
BIG = f"{REF}-big"
# SELinux denials this step could cause: the installer's daemon and its files, the wizard (org.openbook.installer),
# and the package's apps. Others (AOSP's, the test shell's, other add-ons') are listed in sections/avc.txt.
MINE = re.compile(r"openbook_installd|openbook_install_data_file|org\.openbook\.(installer|test)|com\.google\.android\.gsf")
# Any package's UI nodes (the installer's helpers only look at the installer's own).
HELPERS_ANY = r"""
bnda() { ui; tr '>' '\n' < /data/local/tmp/ui.xml | grep -F -e "text=\"$1" -e "content-desc=\"$1" | head -n 1 | sed -n 's/.*bounds="\[\([0-9]*\),\([0-9]*\)\]\[\([0-9]*\),\([0-9]*\)\]".*/\1 \2 \3 \4/p'; }
tapa() { b=$(bnda "$1"); if [ -z "$b" ]; then echo "@@NOTFOUND[$1]@@"; return 1; fi; set -- $b; input tap $(( ($1+$3)/2 )) $(( ($2+$4)/2 )); echo "@@TAPPED@@"; }
waita() { i=0; while [ $i -lt ${2:-90} ]; do b=$(bnda "$1"); if [ -n "$b" ]; then echo "@@SEEN[$1]@@"; return 0; fi; sleep 2; i=$((i+2)); done; echo "@@TIMEOUT[$1]@@"; return 1; }
"""


def helpers_any():
    out = []
    for line in HELPERS_ANY.strip().splitlines():
        out += W.send(line, 30)
    return out


def tapa(text, settle=3):
    return [{"send": f"tapa '{text}'\n"}, {"wait": r"@@TAPPED@@", "timeout": 90}, {"wait": PROMPT, "timeout": 30},
            {"pause": settle}]


def waita(text, timeout=120):
    return [{"send": f"waita '{text}' {timeout}\n"}, {"wait": r"@@SEEN\[", "timeout": timeout + 60},
            {"wait": PROMPT, "timeout": 30}]


def live():
    s = W.steps_common_boot() + W.helpers() + helpers_any()
    s += W.send("export SNAPDEV=/dev/block/by-name/EFI", 30)  # the stick's ESP (a second USB drive is attached)
    s += section("PROPS", "getprop | grep -E 'ro.boot.(openbook|selinux|boot_part_uuid)|ro.build.fingerprint|ro.control_privapp'; getenforce")
    s += section("USB", f"for i in $(seq 60); do PKG=$(ls /mnt/media_rw/*/{REF}.zip 2>/dev/null | head -n 1); "
                        "[ -n \"$PKG\" ] && break; sleep 2; done; export PKG; export NEG=$(dirname $PKG)/neg-framework.zip; "
                        f"export BIG=$(dirname $PKG)/{BIG}.zip; "
                        "echo PKG=$PKG; ls -l $(dirname $PKG); sm list-volumes all", 180)
    return s


def cli_check(pkg="$PKG"):
    s = section("GNEG", "openbook-install gapps-check --package $NEG; echo GNEG-RC=$?", 180)
    s += section("GCHECK", f"openbook-install gapps-check --package {pkg} > /data/local/tmp/gcheck.json; echo GCHECK-RC=$?; "
                           "cat /data/local/tmp/gcheck.json; echo; export SHA=$(grep -o '\"gapps_sha256\":\"[0-9a-f]*\"' "
                           "/data/local/tmp/gcheck.json | cut -d'\"' -f4); echo SHA=$SHA; "
                           "ls -lZ /data/misc/openbook_install/gapps/*/ | head -n 20", 300)
    s += section("PLAN", f"openbook-install plan --target /dev/disk/by-id/{TARGET} --layout whole --locale en-US "
                         "--keyboard us --gapps $SHA --out /data/local/tmp/plan.json", 180)
    return s


def installed():
    s = W.steps_common_boot() + W.helpers() + helpers_any()
    s += W.send("export SNAPDEV=/dev/block/nvme0n1p1", 30)
    s += section("INSTALLED", "getprop | grep -E 'ro.boot.(openbook|selinux|slot_suffix|verifiedbootstate|veritymode|"
                              "vbmeta)|partition.product|sys.boot_completed'; getenforce")
    s += section("VERITY", "for d in /dev/block/mapper/*; do n=${d##*/}; echo \"== $n\"; dmctl table $n 2>&1 | head -n 4; done; "
                           "echo MOUNT; grep -E ' /product ' /proc/mounts; ls -l /dev/block/mapper/", 120)
    s += section("READALL", "find /product -type f | wc -l; find /product -type f -exec cat {} + > /dev/null; echo READ-RC=$?; "
                            "dmesg | grep -iE 'verity|corrupt' | tail -n 5", 300)
    s += section("FILES", "ls -lRZ /product/priv-app/OpenBookTest* /product/app/OpenBookTestApp /product/etc/default-permissions "
                          "/product/etc/openbook; ls -lZ /product/etc/permissions/privapp-permissions-openbook-synthetic.xml "
                          "/product/etc/sysconfig/openbook-synthetic-sysconfig.xml")
    s += section("PACKAGES", "pm list packages -f | grep -E 'openbook.test|com.google.android.gsf'", 120)
    for pkg in ("org.openbook.test.gapps.priv", "com.google.android.gsf", "org.openbook.test.gapps.app"):
        tag = pkg.split(".")[-1].upper()
        s += section(f"PKG-{tag}", f"dumpsys package {pkg} | grep -E 'codePath=|pkgFlags=|privateFlags=|primaryCpuAbi=|"
                                   f"versionName=|WRITE_SECURE_SETTINGS|ACCESS_FINE_LOCATION|ACCESS_COARSE_LOCATION|signatures=' "
                                   f"| head -n 30", 120)
    s += section("PRIVAPP", "pm get-privapp-permissions org.openbook.test.gapps.priv; pm get-privapp-permissions com.google.android.gsf", 60)
    s += section("FEATURE", "pm list features | grep -E 'org.openbook.test'", 60)
    s += section("IDLE", "dumpsys deviceidle whitelist | grep -E 'org.openbook.test'", 60)
    s += section("GSERVICES", "content query --uri content://com.google.android.gsf.gservices 2>&1 | head -n 3", 60)
    s += W.send("input keyevent 224; wm dismiss-keyguard", 30)
    s += W.wait_ui("Language", 180)
    s += W.tap("Continue", 3)
    s += W.wait_ui("Connect to Wi-Fi", 60)
    s += W.tap("Continue", 3)
    s += W.wait_ui("Protect your laptop", 60)
    s += W.tap("Continue", 3)
    s += W.wait_ui("Register this computer with Google", 60)
    s += [{"pause": 4}]
    s += W.shot("g-setup-register")
    s += section("SETUP-UI", "ui; tr '>' '\\n' < /data/local/tmp/ui.xml | grep -oE 'text=\"[^\"]+\"' | head -n 40", 60)
    s += W.tap("Start using OpenBook", 8)
    s += W.shot("g-desktop")
    s += section("AFTER-SETUP", "settings get global device_provisioned; pm list packages -e | grep -c org.openbook.installer; "
                                "pm dump org.openbook.installer | grep -A2 GappsRegistrationActivity | head -n 6")
    s += W.send("am start -n com.android.settings/.Settings\\$MyDeviceInfoActivity", 30)
    s += [{"pause": 5}]
    s += W.shot("g-settings-about-top")
    # An injected entry without an order goes to the end of About's long list: scroll until it is on screen.
    s += W.send("for i in 1 2 3 4 5 6; do input swipe 1440 1500 1440 300 200; sleep 0.5; done", 60)
    s += section("SETTINGS-DIAG", "cmd package query-activities --components -a com.android.settings.action.EXTRA_SETTINGS | "
                                  "grep -i openbook; pm dump org.openbook.installer | grep -E -A3 'enabledComponents|disabledComponents'; "
                                  "ui; tr '>' '\\n' < /data/local/tmp/ui.xml | grep -oE 'text=\"[^\"]+\"' | tail -n 12; "
                                  "logcat -d | grep -iE 'TileUtils|GappsRegistration|DashboardFragment' | tail -n 10", 120)
    s += W.shot("g-settings-about-end")
    # After setup, uiautomator keeps dumping the finished setup window here, so the entry is tapped where About's
    # last row is on this 2880x1800 screen (the screenshot above shows it), and the page is checked by what is on top.
    s += W.send("input tap 400 1690", 30)
    s += [{"pause": 5}]
    s += section("REG-TOP", "dumpsys activity activities | grep -E 'topResumedActivity' | head -n 1", 60)
    s += W.shot("g-settings-register")
    s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
    s += poweroff()
    return s


def expect(case):
    if case.startswith("g-cut-"):
        n = int(case.split("-")[2])
        s = live() + cli_check("$BIG")
        ev, delay = CUTS[n]
        s += [{"send": apply_cmd("/data/local/tmp/plan.json") + "\n"}, {"wait": ev, "timeout": 900}]
        if delay:
            s += [{"pause": delay}]
        return s + [{"monitor": "quit"}]
    if case == "g-cli":
        s = live() + cli_check()
        s += section("APPLY", apply_cmd("/data/local/tmp/plan.json"), 1200)
        s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
        return s + poweroff()
    if case == "g-ui":
        s = live()
        s += W.wait_ui("Choose your language", 180)
        s += W.tap("Continue", 4)
        s += W.wait_ui("STEP 2 OF 7", 120)
        s += W.tap("Continue", 4)
        s += W.wait_ui("STEP 3 OF 7", 60)
        s += W.tap("Install OpenBook", 2)
        s += W.tap("Continue", 4)
        s += W.wait_ui("STEP 4 OF 7", 90)
        s += [{"pause": 4}]
        s += W.shot("g4-disk")
        s += W.tap("Install a Google apps package you provide", 2)
        s += W.shot("g4-disk-advanced-on")
        s += W.tap("Continue", 4)
        s += W.wait_ui("Add a Google apps package", 60)
        s += W.shot("g4b-package-page")
        s += W.tap("Choose a package", 8)
        s += section("PICKER-UI", "dumpsys activity activities | grep -E 'topResumedActivity|ResumedActivity' | head -n 3; "
                                  "ui; tr '>' '\\n' < /data/local/tmp/ui.xml | grep -oE '(text|content-desc|package)=\"[^\"]+\"' "
                                  "| sort | uniq -c | head -n 80", 60)
        s += W.shot("g4b-picker")
        # The USB drive's root: its volume label, or (if the roots pane is folded) after opening the roots list.
        s += W.send("waita 'GAPPSUSB' 20 || { tapa 'Show roots' || tapa 'Open navigation drawer'; sleep 3; }", 90)
        s += waita("GAPPSUSB", 60)
        s += tapa("GAPPSUSB", 5)
        s += waita(f"{REF}.zip", 60)
        s += W.shot("g4b-picker-usb")
        s += tapa(f"{REF}.zip", 6)
        s += W.wait_ui("I understand. Install this package.", 300)
        s += [{"pause": 3}]
        s += W.shot("g4b-package-checked")
        s += W.tap("I understand. Install this package.", 2)
        s += W.shot("g4b-package-confirmed")
        s += W.tap("Continue", 6)
        s += W.wait_ui("STEP 5 OF 7", 120)
        s += [{"pause": 3}]
        s += W.shot("g5-confirm")
        s += W.tap("Type", 2)
        s += W.send("input text 'QEMU%sNVMe%sCtrl'", 30)
        s += [{"pause": 3}]
        s += W.tap("Erase and install", 1)
        s += W.shot("g6-install")
        s += W.wait_ui("OpenBook is installed", 1500)
        s += [{"pause": 4}]
        s += W.shot("g7-done")
        s += section("INSTALLD-LOG", "cat /data/misc/openbook_install/installd.log | tail -n 120", 120)
        s += section("REPORT", "ls -t /data/misc/openbook_install/; mkdir -p /mnt/obesp && mount -t vfat -o ro /dev/block/by-name/EFI /mnt/obesp "
                               "&& cat $(ls -t /mnt/obesp/openbook/logs/install-*.json | head -n 1); echo; umount /mnt/obesp", 120)
        s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
        return s + poweroff()
    if case == "g-installed":
        return installed()
    if case == "g-verity":
        s = W.steps_common_boot()
        s += section("VERITY", "for d in /dev/block/mapper/*; do echo \"== ${d##*/}\"; dmctl table ${d##*/} 2>&1 | head -n 3; done; getenforce", 60)
        s += section("READ-GOOD", "cat /product/priv-app/OpenBookTestGsf/OpenBookTestGsf.apk > /dev/null; echo GOOD-RC=$?", 60)
        # Reading the corrupted file: dm-verity fails the read (and, in enforcing mode, restarts the system).
        s += W.send("dmesg -n 7", 30)  # the kernel's verity error on the serial console (the boot set it to 1)
        s += [{"send": "echo ===READ-BAD-BEGIN===; cat /product/app/OpenBookTestApp/lib/x86_64/libobgapps.so > /dev/null; "
                       "echo BAD-RC=$?; dmesg | grep -iE 'verity' | tail -n 5; echo ===READ-BAD-END===\n"},
              {"wait": r"device-mapper: verity|BAD-RC=", "timeout": 120}, {"pause": 10}]
        return s
    sys.exit(f"unknown case {case}")


def corrupt(a):
    """Flip one byte of PATH's data in the rebuilt product on DISK (a copy), found from outside: the plan's super
    partition, the report's product offset, and the file's block address read from the EROFS image."""
    rep = json.load(open(a.report))
    sup = next(p for p in rep["plan"]["partitions"] if p["name"] == "super")
    g = rep["gapps"]
    base = sup["start"] + g["super_offset"]
    tmp = a.out + ".product-head.img"
    # The EROFS image's metadata: enough to look up the path (its inodes and directories may be anywhere in it).
    EGT.extract(a.disk, base, g["product_bytes"], tmp)
    fs = EGT.Erofs(tmp)
    nid = fs.lookup(a.path)
    ino = fs.inode(nid)
    os.remove(tmp)
    off = base + ino["raw"] * 4096 + 100
    with open(a.disk, "r+b") as f:
        f.seek(off)
        b = f.read(1)
        f.seek(off)
        f.write(bytes([b[0] ^ 0x5A]))
    json.dump({"path": a.path, "nid": nid, "blkaddr": ino["raw"], "disk_offset": off, "was": b[0]}, open(a.out, "w"))
    print(json.dumps({"path": a.path, "blkaddr": ino["raw"], "disk_offset": off}))
    return 0


def report_of(a):
    """The install report a live case printed (g-cli: its APPLY section; g-ui: the stick's report, REPORT)."""
    t = open(f"{a.case_dir}/serial.log", "rb").read().decode("utf-8", "replace")
    sec = W.sections(t)
    rep = [x for k in ("APPLY", "REPORT") for x in E2E.json_lines(sec.get(k, "")) if "verified" in x]
    if not rep:
        print(f"no install report in {a.case_dir}", file=sys.stderr)
        return 1
    json.dump(rep[-1], open(a.out, "w"), indent=1)
    return 0


def check(a):
    R = a.run
    res = {"cases": {}}

    def chk(case, what, ok, detail=""):
        res["cases"].setdefault(case, []).append({"check": what, "ok": bool(ok), "detail": str(detail)[:400]})

    def load(case):
        d = f"{R}/{case}"
        if not os.path.exists(f"{d}/result.json"):
            return None, "", {}
        r = json.load(open(f"{d}/result.json"))
        t = open(f"{d}/serial.log", "rb").read().decode("utf-8", "replace")
        sec = W.sections(t)
        os.makedirs(f"{d}/sections", exist_ok=True)
        for k, v in sec.items():
            open(f"{d}/sections/{k.lower()}.txt", "w").write(v)
        return r, t, sec

    def steps(case, r, allow_last=True):
        ok = r["steps_done"] == r["steps"] or (allow_last and r["reason"].startswith("QEMU exited") and
                                                r["steps_done"] == r["steps"] - 1)
        chk(case, "every expect step matched", ok, f"{r['steps_done']}/{r['steps']} ({r['reason']})")

    def live_checks(case, sec):
        chk(case, "SELinux enforcing", "Enforcing" in sec.get("PROPS", ""), sec.get("PROPS", "")[-200:])
        chk(case, "the USB drive with the packages is mounted by vold", "PKG=/mnt/media_rw/" in sec.get("USB", ""),
            sec.get("USB", "")[-300:])

    def check_checks(case, sec):
        neg = E2E.json_lines(sec.get("GNEG", ""))
        chk(case, "gapps-check refuses the package that touches the framework",
            neg and not neg[-1].get("ok") and any(x.get("rule") == "framework" for x in neg[-1].get("refused", [])) and
            "GNEG-RC=1" in sec.get("GNEG", ""), sec.get("GNEG", "")[-300:])
        gc = [x for x in E2E.json_lines(sec.get("GCHECK", "")) if "gapps_sha256" in x]
        chk(case, "gapps-check accepts the package (on the live system, from the USB drive)",
            gc and gc[-1].get("ok") and "GCHECK-RC=0" in sec.get("GCHECK", ""), sec.get("GCHECK", "")[-300:])
        chk(case, "staged files labeled openbook_install_data_file",
            "u:object_r:openbook_install_data_file:s0" in sec.get("GCHECK", ""), sec.get("GCHECK", "")[-300:])
        pl = [x for x in E2E.json_lines(sec.get("PLAN", "")) if x.get("plan_sha256")]
        chk(case, "plan --gapps: product, vbmeta and check_gapps operations",
            pl and {"product", "vbmeta", "check_gapps"} <= {o["op"] for o in pl[0].get("operations", [])},
            [o["op"] for o in pl[0].get("operations", [])] if pl else sec.get("PLAN", "")[-300:])

    for n in sorted(CUTS):
        c = f"g-cut-{n}"
        r, t, sec = load(c)
        if not r:
            continue
        chk(c, "the expect steps up to the cut matched", r["steps_done"] >= r["steps"] - 1, f"{r['steps_done']}/{r['steps']} ({r['reason']})")
        live_checks(c, sec)
        check_checks(c, sec)
        ev = CUTS[n][0]
        chk(c, f"the cut came at its point ({ev})", re.search(ev, t), "")
        p = f"{R}/inspect/{c}.json"
        if os.path.exists(p):
            st = json.load(open(p))
            chk(c, f"the disk afterwards: {EXPECTED_STATE[n]} (S9)", st.get("state") == EXPECTED_STATE[n],
                {k: st.get(k) for k in ("state", "mbr", "primary_valid", "backup_valid", "fallback", "openbook_entry")})
            if EXPECTED_STATE[n] == "old-table":
                chk(c, "the Windows-like partitions are unchanged",
                    all(v == "unchanged" for v in (st.get("ref_partitions") or {"-": "missing"}).values()),
                    st.get("ref_partitions"))
    for c in ("g-cli", "g-ui"):
        r, t, sec = load(c)
        if not r:
            continue
        steps(c, r)
        live_checks(c, sec)
        if c == "g-cli":
            check_checks(c, sec)
            rep = [x for x in E2E.json_lines(sec.get("APPLY", "")) if "verified" in x]
        else:
            for sh in ("g4-disk-advanced-on", "g4b-package-page", "g4b-package-checked", "g5-confirm", "g7-done"):
                chk(c, f"screenshot {sh}", os.path.exists(f"{R}/{c}/screens/shots/{sh}.png") or
                    os.path.exists(f"{R}/{c}/shot-{sh}.png"))
            rep = [x for x in E2E.json_lines(sec.get("REPORT", "")) if "verified" in x]
            chk(c, "the wizard streamed the package to the daemon and the daemon checked it",
                "gapps: accepted" in sec.get("INSTALLD-LOG", ""), sec.get("INSTALLD-LOG", "")[-300:])
        if os.path.exists(f"{R}/{c}/report.json"):
            rep = [json.load(open(f"{R}/{c}/report.json"))]
        ok = rep and rep[-1].get("ok") and rep[-1].get("verified")
        chk(c, "the install with the package verified", ok, (rep[-1].get("error") if rep else "no report"))
        g = rep[-1].get("gapps", {}) if rep else {}
        chk(c, "the report has the root digest and vbmeta digest", g.get("root_digest") and g.get("vbmeta_digest"), g)
        avc = [l for l in sec.get("AVC", "").splitlines() if "avc:" in l and MINE.search(l)]
        chk(c, "no SELinux denial involves the installer's daemon, its files or the package's apps", not avc, avc[:3])
        if ok:
            json.dump(rep[-1], open(f"{R}/{c}/report.json", "w"), indent=1)
    rep = None
    for c in ("g-ui", "g-cli"):
        if os.path.exists(f"{R}/{c}/report.json"):
            rep = json.load(open(f"{R}/{c}/report.json"))
            break
    r, t, sec = load("g-installed")
    if r:
        c = "g-installed"
        steps(c, r)
        g = (rep or {}).get("gapps", {})
        props = sec.get("INSTALLED", "")
        chk(c, "SELinux enforcing, orange state, the installed system", "Enforcing" in props and
            "[ro.boot.verifiedbootstate]: [orange]" in props and "[ro.boot.openbook.installed]: [whole]" in props, props[-300:])
        chk(c, "the loader passed the rebuilt vbmeta's digest (bootconfig)",
            g.get("vbmeta_digest") and f"[ro.boot.vbmeta.digest]: [{g.get('vbmeta_digest')}]" in props, props[-300:])
        ver = sec.get("VERITY", "")
        chk(c, "product is a dm-verity device with the report's root digest", g.get("root_digest") and
            re.search(r"verity, .*" + g.get("root_digest", "-"), ver), ver[:500])
        chk(c, "/product is mounted from that device", re.search(r"/dev/block/dm-\d+ /product erofs ro", ver), ver[-300:])
        chk(c, "every product file reads back through dm-verity", "READ-RC=0" in sec.get("READALL", ""),
            sec.get("READALL", "")[-300:])
        files = sec.get("FILES", "")
        chk(c, "the package's files in /product, labeled system_file",
            "OpenBookTestPriv.apk" in files and "gapps-manifest.json" in files and
            "default-permissions-openbook-synthetic.xml" in files and files.count("u:object_r:system_file:s0") >= 10 and
            "unlabeled" not in files, files[:400])
        pk = sec.get("PACKAGES", "")
        chk(c, "the three apps installed from /product", all(x in pk for x in (
            "/product/priv-app/OpenBookTestPriv/OpenBookTestPriv.apk=org.openbook.test.gapps.priv",
            "/product/priv-app/OpenBookTestGsf/OpenBookTestGsf.apk=com.google.android.gsf",
            "/product/app/OpenBookTestApp/OpenBookTestApp.apk=org.openbook.test.gapps.app")), pk)
        pv = sec.get("PKG-PRIV", "")
        chk(c, "the privileged app is PRIVILEGED, on product, x86_64, with WRITE_SECURE_SETTINGS granted",
            "PRIVILEGED" in pv and "PRODUCT" in pv and "codePath=/product/priv-app/OpenBookTestPriv" in pv and "primaryCpuAbi=x86_64" in pv and
            re.search(r"WRITE_SECURE_SETTINGS: granted=true", pv), pv[:600])
        chk(c, "its runtime permissions are granted by default (default-permissions XML)",
            re.search(r"ACCESS_FINE_LOCATION: granted=true.*GRANTED_BY_DEFAULT", pv), pv[-400:])
        chk(c, "the stand-in GSF is a privileged app; the ordinary app is not privileged",
            "PRIVILEGED" in sec.get("PKG-GSF", "") and "PRIVILEGED" not in sec.get("PKG-APP", "") and
            "codePath=/product/app/OpenBookTestApp" in sec.get("PKG-APP", ""),
            (sec.get("PKG-GSF", "")[:200], sec.get("PKG-APP", "")[:200]))
        chk(c, "SystemConfig read the package's privapp allowlist", "android.permission.WRITE_SECURE_SETTINGS" in
            sec.get("PRIVAPP", ""), sec.get("PRIVAPP", ""))
        chk(c, "... its feature", "feature:org.openbook.test.feature.SYNTHETIC_GAPPS" in sec.get("FEATURE", ""), sec.get("FEATURE", ""))
        chk(c, "... and its sysconfig (power-save allowlist)", "org.openbook.test.gapps.priv" in sec.get("IDLE", ""), sec.get("IDLE", ""))
        chk(c, "OpenBook setup shows the GSF Android ID (the stand-in's fake one) and the registration steps",
            "3141592653589793238" in sec.get("SETUP-UI", "") and "google.com/android/uncertified" in sec.get("SETUP-UI", ""),
            sec.get("SETUP-UI", "")[:400])
        sd = sec.get("SETTINGS-DIAG", "")
        chk(c, "Settings > About's entry: the activity answers Settings' EXTRA_SETTINGS and is enabled (the package is installed)",
            "org.openbook.installer/.GappsRegistrationActivity" in sd and
            re.search(r"enabledComponents:\s*\n\s*org.openbook.installer.GappsRegistrationActivity", sd), sd[:300])
        chk(c, "tapping About's last row opens the registration page (screenshots g-settings-about-end, g-settings-register)",
            "org.openbook.installer/.GappsRegistrationActivity" in sec.get("REG-TOP", ""), sec.get("REG-TOP", ""))
        avc = [l for l in sec.get("AVC", "").splitlines() if "avc:" in l and MINE.search(l)]
        chk(c, "no SELinux denial involves the installer's daemon, its files or the package's apps", not avc, avc[:3])
    r, t, sec = load("g-verity")
    if r:
        c = "g-verity"
        chk(c, "an intact package file reads", "GOOD-RC=0" in sec.get("READ-GOOD", ""), sec.get("READ-GOOD", ""))
        m = re.search(r"device-mapper: verity: (\S+): data block (\d+) is corrupted", t)
        chk(c, "the read never completed: the system restarted (restart_on_corruption)", not re.search(r"\nBAD-RC=\d", t) and
            r["reason"].startswith("QEMU exited"), r["reason"])
        cj = json.load(open(f"{R}/g-verity/corrupted.json")) if os.path.exists(f"{R}/g-verity/corrupted.json") else {}
        chk(c, "reading the corrupted package file trips dm-verity on product, at the corrupted block",
            m and cj and int(m.group(2)) == cj.get("blkaddr"), (m.group(0) if m else t[-400:], cj))
    total = sum(len(v) for v in res["cases"].values())
    passed = sum(x["ok"] for v in res["cases"].values() for x in v)
    res["summary"] = {"passed": passed, "total": total}
    json.dump(res, open(f"{R}/results.json", "w"), indent=1)
    with open(f"{R}/SUMMARY.md", "w") as f:
        f.write(f"# gapps-e2e-qemu: {passed}/{total}\n\n")
        for case, cs in res["cases"].items():
            f.write(f"## {case}: {sum(x['ok'] for x in cs)}/{len(cs)}\n")
            for x in cs:
                f.write(f"- {'PASS' if x['ok'] else 'FAIL'} {x['check']}" + (f" ({x['detail']})" if not x["ok"] else "") + "\n")
    print(f"{passed}/{total}")
    return 0 if passed == total else 1


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("expect")
    e.add_argument("case")
    e.add_argument("out")
    co = sub.add_parser("corrupt")
    for k in ("disk", "report", "path", "out"):
        co.add_argument(k)
    ro = sub.add_parser("report-of")
    ro.add_argument("case_dir")
    ro.add_argument("out")
    c = sub.add_parser("check")
    c.add_argument("--run", required=True)
    c.add_argument("--disks", required=True)
    c.add_argument("--packages", required=True)
    a = ap.parse_args()
    if a.cmd == "expect":
        json.dump(expect(a.case), open(a.out, "w"), indent=0)
        return 0
    if a.cmd == "corrupt":
        return corrupt(a)
    if a.cmd == "report-of":
        return report_of(a)
    return check(a)


if __name__ == "__main__":
    sys.exit(main())
