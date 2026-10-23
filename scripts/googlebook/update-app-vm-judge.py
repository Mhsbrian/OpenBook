#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Judge an update-app-vm.sh run: OpenBook Update on the real Ruby image in QEMU.

Reads WORK/vm (ab-qemu.py's result.json and serial.log with the disposable check service's OBU_* report)
and writes WORK/result.json. The VM has no network: the app's first check ends with the engine's network
exit (3), which shows the engine ran from the app's own domain.

usage: update-app-vm-judge.py WORK
"""
import json
from pathlib import Path
import re
import sys


def judge(serial, boot, screenshot):
    lines = serial.replace("\r", "").splitlines()
    obu = [l for l in lines if l.startswith("OBU_")]
    tagged = lambda tag: [l[len(tag) + 1:] for l in obu if l.startswith(tag + " ")]
    owner = (tagged("OBU_OWNER") or ["none"])[0]
    pkg = "\n".join(tagged("OBU_PKG"))
    procs = tagged("OBU_PS") + tagged("OBU_PS2")
    logs = tagged("OBU_LIVE") + tagged("OBU_LOG")
    complete = "OBU_VMCHECK begin" in obu and "OBU_VMCHECK done" in obu
    # The app's own: its domain as subject or object (the kernel shows the process as "openbook.update").
    # Other domains' denials are reported apart (all_denials), e.g. a base image's own services.
    mine = lambda l: "avc:" in l and "denied" in l and ("openbook_update_app" in l or 'comm="openbook.update"' in l)
    denials = sorted({re.sub(r"^.*?avc:", "avc:", l) for l in lines if mine(l)})
    all_denials = sorted({re.sub(r"^.*?avc:", "avc:", re.sub(r"audit\([0-9.:]+\)|pid=\d+ |ino=\d+ ", "", l.strip()))
                          for l in lines if "avc:" in l and "denied" in l})
    users = {m.group(1): m.group(2) for m in (re.match(r"\s*User (\d+): .*installed=(\w+)", l) for l in tagged("OBU_PKG")) if m}
    crashes = [l for l in logs if "Process: org.openbook.update" in l]
    checks = {
        "boot_passed": bool(boot.get("passed")),
        "report_complete": complete,
        "owner_user_present": owner != "none",
        "privileged_system_app": "codePath=/system/priv-app/OpenBookUpdate-v" in pkg and "PRIVILEGED" in pkg,
        "installed_for_owner_only": users.get(owner) == "true" and users.get("0") == "false",
        "reboot_granted": "android.permission.REBOOT: granted=true" in pkg,
        "notifications_granted_on_first_boot": "android.permission.POST_NOTIFICATIONS: granted=true" in pkg,
        "power_save_exempt": any("org.openbook.update" in l for l in tagged("OBU_IDLE")),
        "runs_in_its_own_domain": any("label=u:r:openbook_update_app:" in l for l in procs),
        "boot_work_scheduled": any("BOOT_COMPLETED: regular checks scheduled" in l for l in logs),
        "slot_known_at_boot": any(re.search(r"boot: running .* from slot _[ab]", l) for l in logs),
        "watching_update_engine": any("watching update_engine" in l for l in logs),
        "engine_check_ran_offline": any("check finished: exit 3 (NETWORK)" in l for l in logs),
        "refresh_receiver_works": any("refresh requested" in l for l in logs),
        # Only meaningful when the app ran and the report finished.
        "no_denials_for_the_app": complete and bool(procs) and not denials,
        "no_app_crash": complete and not crashes,
    }
    return dict(schema="openbook-update-app-vm/2", passed=all(checks.values()), checks=checks, owner_user=owner,
                # Informational: QEMU's virtual display stays dark (OpenBook's vendor drives AMD displays).
                screenshot_taken=screenshot,
                privapp_enforcement=(tagged("OBU_PRIVAPP_ENFORCEMENT") or [""])[0],
                package_lines=tagged("OBU_PKG"), processes=procs, app_log=logs, app_crashes=crashes,
                app_denials=denials, all_denials=all_denials, deployment_eligible=False, hardware_tested=False)


def main(work):
    vm = work / "vm"
    serial = (vm / "serial.log").read_text(errors="replace") if (vm / "serial.log").exists() else ""
    boot = json.loads((vm / "result.json").read_text()) if (vm / "result.json").exists() else {}
    shot = vm / "screen-OBU_SCREEN_READY.ppm"
    if shot.is_file():
        try:                                   # PNG for the evidence, where Pillow is available (the host)
            from PIL import Image
            Image.open(shot).save(vm / "screen-OBU_SCREEN_READY.png", optimize=True)
        except ImportError:
            pass
    result = judge(serial, boot, shot.is_file())
    result["boot_checks"] = boot.get("checks")
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(passed=result["passed"], checks=result["checks"], app_denials=result["app_denials"]), indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.exit(main(Path(sys.argv[1])))
