#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Judge a safety-vm.sh run: the firmware safety change (ANAL-251) on the real Ruby image in QEMU.

Reads WORK/vm (ab-qemu.py's result.json and serial.log: the kernel console with init's log, and the
disposable check service's FWS_* report) and BASELINE, the serial log of a fresh boot of the same release
without the change. Writes WORK/result.json.

  changed:    Google's boot-time gscutil (security chip firmware staging) does not start and leaves no
              SELinux denial; IGscutilExecutor is not defined; the /metadata/gscutil directory step runs
  unchanged:  gscd runs and serves IGsc; check_tpm_clear and udsattestation run and end as in the baseline;
              keystore2, gatekeeperd and update_engine run, the Weaver serves and KeyMint registers (from init's
              and servicemanager's log: the shell may not look KeyMint up); boot passes with no system_server
              fatal signal or zygote exit, and no app crashes that the baseline does not show

usage: safety-vm-judge.py WORK BASELINE_SERIAL
"""
import json
from pathlib import Path
import re
import sys

GSCUTIL_BOOT = "/system/bin/gscutil --direct-gsc perform-os-startup"


def exits(lines, name):
    """Exit statuses init reported for a service or exec whose description contains name."""
    return [int(m.group(1)) for l in lines if name in l
            for m in [re.search(r"exited with status (\d+)", l)] if m]


def facts(serial):
    lines = serial.replace("\r", "").splitlines()
    return dict(
        gscutil_boot_started=any("starting service" in l and GSCUTIL_BOOT in l for l in lines),
        gscutil_denials=sorted({re.sub(r"^.*?avc:", "avc:", re.sub(r"audit\([0-9.:]+\)|ino=\d+ ", "", l))
                                for l in lines if "avc:" in l and 'comm="gscutil"' in l}),
        gscutil_rc_post_fs=any("processing action (post-fs) from (/system/etc/init/gscutil.rc" in l for l in lines),
        metadata_dir_failed=any("mkdir /metadata/gscutil" in l and "failed" in l for l in lines),
        check_tpm_clear_exits=exits(lines, "(/system/bin/check_tpm_clear)"),
        udsattestation_exits=exits(lines, "'android.system.desktop.security.udsattestation'"),
        gscd_started=any("started service 'android.system.desktop.security.gscd'" in l for l in lines),
        keymint_registered=any("sid=u:r:hal_keymint_default:s0) Found android.hardware.security.keymint.IKeyMintDevice/default"
                               in l for l in lines),
        crashed_apps=sorted({m.group(1) for l in lines if "FWS_" not in l
                             for m in [re.search(r"AndroidRuntime.*Process: ([^, ]+)", l)] if m}),
        lines=lines)


def judge(serial, boot, baseline):
    now, before = facts(serial), facts(baseline)
    fws = [l for l in now["lines"] if l.startswith("FWS_")]
    tagged = lambda tag: [l[len(tag) + 1:] for l in fws if l.startswith(tag + " ")]
    props = dict(re.findall(r"\[([^\]]+)\]: \[([^\]]*)\]", "\n".join(tagged("FWS_PROP"))))
    services = dict(l.split(" ", 1) for l in tagged("FWS_SERVICE") if " " in l)
    running = lambda name: props.get(f"init.svc.{name}") == "running"
    findings = boot.get("runtime_findings", {})
    checks = {
        "boot_passed": bool(boot.get("passed")),
        "report_complete": "FWS_VMCHECK begin" in fws and "FWS_VMCHECK done" in fws,
        "boot_completed": tagged("FWS_BOOT") == ["1"],
        # changed
        "baseline_started_gscutil_at_boot": before["gscutil_boot_started"],
        "gscutil_not_started_at_boot": not now["gscutil_boot_started"],
        "no_gscutil_denials": not now["gscutil_denials"],
        "gscutil_executor_not_defined": services.get("com.google.android.system.desktop.IGscutilExecutor/default") == "not found",
        "metadata_gscutil_step_runs": now["gscutil_rc_post_fs"] and not now["metadata_dir_failed"],
        # unchanged
        "gscd_running": now["gscd_started"] and running("android.system.desktop.security.gscd"),
        "igsc_served": services.get("android.system.desktop.security.gsc.IGsc/default") == "found",
        "check_tpm_clear_as_baseline": bool(now["check_tpm_clear_exits"]) and now["check_tpm_clear_exits"] == before["check_tpm_clear_exits"],
        "udsattestation_as_baseline": bool(now["udsattestation_exits"]) and now["udsattestation_exits"] == before["udsattestation_exits"],
        "keystore_and_gatekeeper_running": running("keystore2") and running("gatekeeperd"),
        "weaver_served": services.get("android.hardware.weaver.IWeaver/default") == "found",
        "keymint_registered": now["keymint_registered"] and before["keymint_registered"],
        "update_engine_running": running("update_engine"),
        "no_system_server_fatal_signal": not findings.get("system_server_fatal_signals"),
        "no_zygote_exit": findings.get("zygote_exit_events", 1) == 0,
        "no_new_app_crash": set(now["crashed_apps"]) <= set(before["crashed_apps"]),
    }
    return dict(schema="openbook-safety-vm/1", passed=all(checks.values()), checks=checks,
                baseline=dict((k, v) for k, v in before.items() if k != "lines"),
                now=dict((k, v) for k, v in now.items() if k != "lines"),
                properties=props, services=services, processes=tagged("FWS_PIDOF"), devices=tagged("FWS_DEV"),
                security_denials=tagged("FWS_AVC"), crash_lines=tagged("FWS_CRASH"),
                deployment_eligible=False, hardware_tested=False)


def main(work, baseline):
    vm = work / "vm"
    serial = (vm / "serial.log").read_text(errors="replace") if (vm / "serial.log").exists() else ""
    boot = json.loads((vm / "result.json").read_text()) if (vm / "result.json").exists() else {}
    result = judge(serial, boot, Path(baseline).read_text(errors="replace"))
    result["boot_checks"] = boot.get("checks")
    result["baseline_serial"] = str(baseline)
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(passed=result["passed"], checks=result["checks"]), indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(Path(sys.argv[1]), sys.argv[2]))
