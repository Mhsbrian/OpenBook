#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Judge a dgpu-vm.sh run: ANAL-238's vendor dGPU diagnostics and ANAL-257's lab on the real Ruby image in QEMU.

Reads WORK/vm (ab-qemu.py's result.json and serial.log: the kernel console with init's log, and the
disposable check service's DGR_* report) and BASELINE, the serial log of a fresh boot of the same release
without the change. Writes WORK/result.json. QEMU has no NVIDIA GPU, so every report must say state=absent.

  changed:    the boot report runs at boot completion as root and reaches logcat; a new debug.openbook.dgpu_report
              value runs it again; debug.openbook.dgpu_pm on|auto runs dgpu-ctl, which finds no NVIDIA function and
              reports; the report reads /sys/power/suspend_stats (the new policy rule); every service exits 0.
              The lab (ANAL-257): a request is refused while the switch is off; "enable" switches it on; a report
              runs as root; with openbook_sleep_diag.ko in vendor_dlkm, diag-snapshot loads it through init's
              vendor_modprobe service with the lab's parameters, the report relays its state, diag-unload unloads
              it and nothing stays loaded; "disable" switches it off and requests are refused again
  unchanged:  boot passes; openbook_pc_setup has no SELinux denial the baseline lacks (the baseline's kmsg_debug
              writes from dgpu-pm, perms and kvm remain), and vendor_modprobe none either; no system_server fatal
              signal, zygote exit or new app crash

usage: dgpu-vm-judge.py WORK BASELINE_SERIAL
"""
import json
from pathlib import Path
import re
import sys


def exits(lines, service):
    return [int(m.group(1)) for l in lines if f"'{service}'" in l
            for m in [re.search(r"exited with status (\d+)", l)] if m]


def denials(lines, domain="openbook_pc_setup"):
    """A domain's denials, normalised (no pid, inode or timestamp)."""
    out = set()
    for l in lines:
        if "avc:" in l and "denied" in l and f"scontext=u:r:{domain}:s0" in l:
            l = re.sub(r"^.*?avc:", "avc:", l)
            out.add(re.sub(r"\s+", " ", re.sub(r"audit\([0-9.:]+\)|pid=\d+ |ino=\d+ ", "", l)).strip())
    return sorted(out)


def facts(serial):
    lines = serial.replace("\r", "").splitlines()
    return dict(
        denials=denials(lines),
        modprobe_denials=denials(lines, "vendor_modprobe"),
        lab_exits=exits(lines, "vendor.openbook.lab"),
        lab_mod_exits=exits(lines, "vendor.openbook.lab-diag-snapshot") + exits(lines, "vendor.openbook.lab-diag-unload"),
        crashed_apps=sorted({m.group(1) for l in lines if "DGR_" not in l
                             for m in [re.search(r"AndroidRuntime.*Process: ([^, ]+)", l)] if m}),
        init_errors=sorted({re.sub(r"^(\[[^\]]*\])+\s*", "", l).strip() for l in lines if "init.openbook.rc" in l
                            and re.search(r"error|unexported|invalid|failed", l, re.I)}),
        report_exits=exits(lines, "vendor.openbook.dgpu-report"),
        ctl_exits=exits(lines, "vendor.openbook.dgpu-ctl"),
        lines=lines)


def section(dgr, name):
    """The report lines (logcat -v raw) captured at one step of the check script."""
    tag = f"DGR_LOG {name} "
    return [l[len(tag):] for l in dgr if l.startswith(tag)]


def run_of(lines, reason):
    """The lines of the last dgpu-report run with this reason: from its header to its state= line."""
    starts = [i for i, l in enumerate(lines) if l == f"dgpu-report ({reason})"]
    if not starts:
        return []
    out = []
    for l in lines[starts[-1]:]:
        out.append(l)
        if l.startswith("dgpu-report: state="):
            break
    return out


def report_ok(run):
    return bool(run) and run[-1] == "dgpu-report: state=absent" and \
        any(re.fullmatch(r"dgpu-report: suspend_stats success=\d+.*", l) for l in run)


def judge(serial, boot, baseline):
    now, before = facts(serial), facts(baseline)
    dgr = [l for l in now["lines"] if l.startswith("DGR_")]
    tagged = lambda tag: [l[len(tag) + 1:] for l in dgr if l.startswith(tag + " ")]
    boot_run = run_of(section(dgr, "boot"), "boot")
    report_run = run_of(section(dgr, "report"), "vm-1")
    on_lines = section(dgr, "ctl-on")
    auto_lines = section(dgr, "ctl-auto")
    findings = boot.get("runtime_findings", {})
    lab = lambda step: section(dgr, f"lab-{step}")
    lab_report = lab("report@on")
    checks = {
        "boot_passed": bool(boot.get("passed")),
        "report_complete": "DGR_VMCHECK begin" in dgr and "DGR_VMCHECK done" in dgr,
        "boot_completed": tagged("DGR_BOOT") == ["1"],
        # changed
        "boot_report_in_logcat": report_ok(boot_run),
        "suspend_stats_readable": any(l.startswith("dgpu-report: suspend_stats success=") for l in boot_run),
        "on_demand_report": report_ok(report_run),
        "ctl_on_runs": "dgpu-ctl: no NVIDIA function enumerated; nothing to do" in on_lines
                       and report_ok(run_of(on_lines, "dgpu-ctl on")),
        "ctl_auto_runs": "no NVIDIA GPU enumerated; nothing to do" in auto_lines
                         and report_ok(run_of(auto_lines, "dgpu-ctl auto")),
        "services_exit_0": len(now["report_exits"]) >= 2 and set(now["report_exits"]) == {0}
                           and len(now["ctl_exits"]) >= 2 and set(now["ctl_exits"]) == {0},
        # the lab (ANAL-257)
        "lab_refused_while_off": "lab: 'report@off' refused: the lab switch is off (setprop debug.openbook.lab enable)"
                                 in lab("report@off"),
        "lab_switched_on": any(l.startswith("lab: switched on") for l in lab("enable")),
        "lab_report_runs": "lab-report (report@on): switch=1" in lab_report
                           and report_ok(run_of(lab_report, "lab report@on")),
        "lab_module_in_vendor_dlkm": tagged("DGR_LABMOD") == ["present"],
        "lab_module_loads": "lab: diag-snapshot: openbook_sleep_diag present" in lab("diag-snapshot")
                            and any(l.startswith("lab: module openbook_sleep_diag loaded state=live")
                                    for l in lab("diag-snapshot")),
        "lab_module_parameters": "lab: openbook_sleep_diag ptm_off=N snapshot=2 usb4=Y cycles=8" in lab("report@diag"),
        "lab_module_report_relayed": any(l.startswith("lab: diag ") for l in lab("report@diag")),
        "lab_module_unloads": "lab: diag-unload: openbook_sleep_diag absent" in lab("diag-unload")
                              and not tagged("DGR_PROCMOD"),
        "lab_switched_off": "lab: switched off (persist.vendor.openbook.lab=0)" in lab("disable")
                            and "lab: 'report@disabled' refused: the lab switch is off (setprop debug.openbook.lab enable)"
                            in lab("report@disabled"),
        "lab_services_exit_as_expected": bool(now["lab_exits"]) and set(now["lab_exits"]) <= {0, 3}
                                         and len(now["lab_mod_exits"]) == 2 and set(now["lab_mod_exits"]) == {0},
        "no_new_init_script_errors": set(now["init_errors"]) <= set(before["init_errors"]),
        # unchanged
        "no_new_openbook_pc_setup_denials": set(now["denials"]) <= set(before["denials"]),
        "no_new_vendor_modprobe_denials": set(now["modprobe_denials"]) <= set(before["modprobe_denials"]),
        "no_system_server_fatal_signal": not findings.get("system_server_fatal_signals"),
        "no_zygote_exit": findings.get("zygote_exit_events", 1) == 0,
        "no_new_app_crash": set(now["crashed_apps"]) <= set(before["crashed_apps"]),
    }
    return dict(schema="openbook-dgpu-vm/1", passed=all(checks.values()), checks=checks,
                baseline=dict((k, v) for k, v in before.items() if k != "lines"),
                now=dict((k, v) for k, v in now.items() if k != "lines"),
                reports=dict(boot=boot_run, on_demand=report_run, ctl_on=on_lines, ctl_auto=auto_lines,
                             lab_report=lab_report, lab_diag=lab("report@diag")),
                services=tagged("DGR_SVC"), security_denials=tagged("DGR_AVC"), crash_lines=tagged("DGR_CRASH"),
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
