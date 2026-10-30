#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check run-vm-test.sh's serial log for openbook_sleep_diag (ANAL-257) and write a JSON verdict.

usage: check-vm-log.py SERIAL.LOG OUT.json
"""
import json
import re
import sys


def main():
    log = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    klog = [line[5:] for line in log.splitlines() if line.startswith("KLOG ")]
    k = "\n".join(klog)
    s2idle_resumed = len(re.findall(r"^== s2idle \d resumed", log, re.M))
    entries = sorted({int(n) for n in re.findall(r"s0i3-entry (\d+): \d+ PCI functions", k)})
    exits = sorted({int(n) for n in re.findall(r"s0i3-exit (\d+): the s2idle loop checked", k)})
    detail_entries = sorted({int(n) for n in re.findall(r"s0i3-entry (\d+): \S+ [0-9a-f]{4}:[0-9a-f]{4} ", k)})
    ptm_suspend = sorted({int(n) for n in re.findall(r"suspend (\d+): PTM turned off on 0 of 0", k)})
    usb4_suspend = len(re.findall(r"suspend: no USB4 host router", k))
    checks = {
        "inert_without_parameters": "inactive (no openbook_sleep_diag parameter set)" in log,
        "unloads_inert": "== unloaded\n" in log or "== unloaded\r\n" in log,
        "active_with_parameters": "active: ptm_off=1 snapshot=2 usb4=1 cycles=2" in k,
        "params_read_only_visible": all(f"PARAM {p}" in log for p in ("ptm_off=Y", "snapshot=2", "usb4=Y", "cycles=2")),
        "ptm_listed_at_load": bool(re.search(r"load: \d+ function\(s\) with a PTM capability, \d+ with PTM enabled", k)),
        "usb4_at_load_and_60s": "load: no USB4 host router" in k and "load+60s: no USB4 host router" in k,
        "lps0_hook_registered": "no LPS0 device" not in k,
        "three_s2idle_cycles_resumed": s2idle_resumed == 3,
        "summary_every_s0i3_entry": entries == [1, 2, 3] and exits == [1, 2, 3],
        "full_snapshot_first_two_entries_only": detail_entries == [1, 2],
        "root_port_and_endpoint_in_snapshot": bool(re.search(r"s0i3-entry 1: \S+ 1b36:000c root-port", k))
        and bool(re.search(r"s0i3-entry 1: \S+ 8086:10d3 endpoint", k)),
        "ptm_path_every_suspend_verbose_first_two": ptm_suspend == [1, 2],
        "usb4_report_first_two_suspends": usb4_suspend == 2,
        "s3_cycle_resumed": "== s3 resumed" in log,
        "unloads_active": "== unloaded active" in log,
        "report_holds_last_s0i3_entry": bool(re.search(r"^REPORT s0i3-entry 3 \(suspend 3\), PTM off:", log, re.M))
        and bool(re.search(r"^REPORT s0i3-entry 3: \d+ PCI functions, \d+ not in D3, 0 with PTM on", log, re.M))
        and bool(re.search(r"^REPORT   \S+ 1b36:000c D0 pcieport", log, re.M))
        and "REPORT   no USB4 host router" in log,
        "report_read_only": "== report read-only" in log,
        "no_kernel_warnings": "KBAD " not in log,
        "finished": "== done" in log,
    }
    result = {
        "schema": "openbook-sleep-diag-vm/1",
        "kernel": (re.search(r"== kernel (\S+)", log) or [None, None])[1],
        "passed": all(checks.values()),
        "checks": checks,
        "s0i3_entries_logged": entries,
        "module_log_lines": len(klog),
    }
    json.dump(result, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(result, indent=1))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
