#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The dGPU's power state and battery cost on a Ruby laptop over adb, without root (ANAL-238).

Needs the vendor's `dgpu-report` and `dgpu-ctl` services (device/anybook/common/pc/init.openbook.rc):

  report   ask the vendor for a root-domain report (setprop debug.openbook.dgpu_report <token>) and print what it
           logged: each NVIDIA function's driver, power_state and runtime-PM state, the root port and its ACPI power
           resources, asus-wmi's dgpu_disable/gpu_mux_mode and /sys/power/suspend_stats.
  battery  on battery, idle and awake: average battery power for each dGPU state in --states (default auto,on,auto:
           D3cold, D0, D3cold), sampling BAT1 current_now x voltage_now every 5 s. The hold is volatile
           (debug.openbook.dgpu_pm); the run always ends with auto, and a reboot also restores it.

Device writes: only the two debug.openbook.* properties. No root, settings, input, reboot or disk writes. A sample
in which the screen went off or someone used the laptop is flagged, and the comparison is then not valid. Output
holds only power figures and kernel/ACPI state names.
"""
import argparse
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

BAT = "/sys/class/power_supply/BAT1"
WANT = {"auto": ("d3cold",), "on": ("d0-no-driver",)}


class Adb:
    def __init__(self, adb, serial, port):
        self.base = [str(adb), "-s", serial]
        self.env = dict(os.environ, ANDROID_ADB_SERVER_PORT=str(port))

    def sh(self, cmd, timeout=30):
        r = subprocess.run(self.base + ["shell", cmd], env=self.env, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"adb shell {cmd!r} failed ({r.returncode}): {r.stderr.strip()}")
        return r.stdout


def report(adb, wait=20):
    """Trigger dgpu-report and return its parsed lines, or None if this image has no such service."""
    token = f"adb-{int(time.time())}"
    adb.sh(f"setprop debug.openbook.dgpu_report {token}")
    return read_report(adb, f"dgpu-report ({token})", wait)


def read_report(adb, marker, wait=20):
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(2)
        out = adb.sh("logcat -d -v raw -s openbook-pc-setup:I")
        lines = out.splitlines()
        starts = [i for i, s in enumerate(lines) if s.strip() == marker]
        if starts:
            block = []
            for s in lines[starts[-1]:]:
                block.append(s.strip())
                if s.startswith("dgpu-report: state="):
                    return parse(block)
    return None


def parse(block):
    out = {"lines": block, "functions": [], "bridge": None, "state": None}
    for s in block:
        if not s.startswith("dgpu-report: "):
            continue
        body = s[len("dgpu-report: "):]
        kv = dict(re.findall(r"(\w+)=(\S+)", body))
        if body.startswith("state="):
            out["state"] = kv["state"]
        elif body.startswith("bridge "):
            out["bridge"] = {"bdf": body.split()[1], **kv}
        elif re.match(r"[0-9a-f]{4}:", body):
            out["functions"].append({"bdf": body.split()[0], **kv})
        elif body.startswith("asus-nb-wmi"):
            out["asus"] = kv
        elif body.startswith("suspend_stats"):
            out["suspend_stats"] = kv
    return out


def battery_sample(adb):
    out = adb.sh(f"cat {BAT}/status {BAT}/current_now {BAT}/voltage_now; dumpsys power | grep -E "
                 "'mWakefulness=|mLastUserActivityTime\\(excludingAttention\\)='")
    lines = out.split("\n")
    status, ua, uv = lines[0].strip(), int(lines[1]), int(lines[2])
    wake = re.search(r"mWakefulness=(\w+)", out)
    act = re.search(r"mLastUserActivityTime\(excludingAttention\)=(\d+)", out)
    return {"t": round(time.time(), 1), "status": status, "mw": round(abs(ua) * uv / 1e9),
            "wakefulness": wake.group(1) if wake else None, "user_activity": int(act.group(1)) if act else None}


def battery(adb, states, minutes, settle):
    first = battery_sample(adb)
    if first["status"] not in ("Discharging", "Not charging") or "AC powered: true" in adb.sh("dumpsys battery"):
        raise SystemExit(f"on AC ({first['status']}): unplug the charger first; the run must be on battery")
    if report(adb) is None:
        raise SystemExit("no dgpu-report on this image: it needs ANAL-238's vendor change")
    runs = []
    try:
        for i, st in enumerate(states):
            adb.sh(f"setprop debug.openbook.dgpu_pm {st}")
            rep = read_report(adb, f"dgpu-report (dgpu-ctl {st})", wait=30)
            if rep is None or rep["state"] not in WANT[st]:
                raise SystemExit(f"dgpu-ctl {st}: the dGPU reports {rep and rep['state']}, expected {WANT[st]}")
            time.sleep(settle)
            samples, end = [], time.time() + minutes * 60
            while time.time() < end:
                samples.append(battery_sample(adb))
                time.sleep(5)
            mws = [s["mw"] for s in samples]
            runs.append({"order": i, "dgpu_pm": st, "reported_state": rep["state"], "samples": len(samples),
                         "mean_mw": round(statistics.mean(mws)), "median_mw": round(statistics.median(mws)),
                         "min_mw": min(mws), "max_mw": max(mws),
                         "screen_awake_throughout": all(s["wakefulness"] == "Awake" for s in samples),
                         "user_activity_during": len({s["user_activity"] for s in samples}) > 1,
                         "on_battery_throughout": all(s["status"] != "Charging" for s in samples)})
    finally:
        adb.sh("setprop debug.openbook.dgpu_pm auto")
    by = {}
    for r in runs:
        by.setdefault(r["dgpu_pm"], []).append(r["mean_mw"])
    valid = all(r["screen_awake_throughout"] and not r["user_activity_during"] and r["on_battery_throughout"]
                for r in runs)
    delta = (round(statistics.mean(by["on"]) - statistics.mean(by["auto"]))
             if "on" in by and "auto" in by else None)
    return {"runs": runs, "valid": valid, "d0_minus_d3cold_mw": delta}


def main():
    data = Path(os.environ.get("OPENBOOK_HOME", str(Path.home() / "anybook")))
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--adb", type=Path, default=data / "android-sdk/platform-tools/adb")
    p.add_argument("--serial", required=True, help="adb serial of the paired laptop")
    p.add_argument("--server-port", type=int, default=5238, help="a private adb server port (default 5238)")
    p.add_argument("--out", type=Path, help="also write the JSON here")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("report")
    b = sub.add_parser("battery")
    b.add_argument("--states", default="auto,on,auto")
    b.add_argument("--minutes", type=float, default=10.0, help="sampling time per state (default 10)")
    b.add_argument("--settle", type=int, default=60, help="seconds after each change before sampling (default 60)")
    a = p.parse_args()
    adb = Adb(a.adb, a.serial, a.server_port)
    if a.cmd == "report":
        rep = report(adb)
        if rep is None:
            raise SystemExit("no dgpu-report on this image: it needs ANAL-238's vendor change")
        out = {"schema": "openbook-dgpu-report/1", **rep}
    else:
        states = a.states.split(",")
        if any(s not in WANT for s in states) or "auto" not in states or "on" not in states:
            p.error("--states: a list of auto and on, with both")
        out = {"schema": "openbook-dgpu-battery/1", "minutes_per_state": a.minutes, "settle_s": a.settle,
               **battery(adb, states, a.minutes, a.settle)}
    text = json.dumps(out, indent=1) + "\n"
    sys.stdout.write(text)
    if a.out:
        a.out.write_text(text)


if __name__ == "__main__":
    main()
