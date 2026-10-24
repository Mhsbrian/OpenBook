#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""S0i3 comparison on a laptop's own Linux (ANAL-178). Run it ON the laptop, as root, from a terminal:

    sudo python3 scripts/power/linux-s2idle.py

It records whether this Linux reaches the SoC's deepest sleep (S0i3) over suspend-to-idle, and what changes when
two drivers OpenBook's kernel does not have are taken away for one cycle each. OpenBook's own kernel never reaches
S0i3 on the GA403WR (evidence/2026-10-16-g14-hwcheck, runs 2-7); this is the other half of that comparison.

Phases (each cycle: suspend-to-idle for --seconds, woken by the RTC; the screen goes dark and comes back):
  baseline  --cycles cycles as the system is
  no-pmf    amdxdna and amd_pmf unloaded, one cycle, then loaded again
  no-ccp    also amdtee, kvm_amd and ccp (the PSP driver) unloaded, one cycle, then loaded again
  amd-s2idle  only with --amd-s2idle: AMD's own `amd-s2idle test` (package amd-debug-tools), two cycles
If the kernel's headers are installed (linux-*-headers), the test-only module openbook_s0i3_snapshot
(scripts/installer/kmod/) is built for this kernel and loaded for the run: at each S0i3 attempt it logs every PCI
function not in D3. It is unloaded at the end; an unsigned module marks the kernel tainted until the next reboot
(--no-snapshot skips it). Modules that cannot be unloaded (in use) make that phase "skipped"; everything unloaded is
loaded again on exit, also after an error or Ctrl-C. Nothing persists: no file outside the output folder, no
firmware or boot setting, no package changes.

Output: ./openbook-linux-s2idle-<UTC time>/ with summary.json (schema openbook-linux-s2idle/1), report.md,
facts.txt and the kernel log of each cycle, all redacted (MAC addresses, UUIDs, serial numbers, IP addresses,
the host name), and the same as a .tar.gz to attach to the issue.

usage: linux-s2idle.py [--cycles N] [--seconds S] [--phases LIST] [--no-snapshot] [--amd-s2idle] [--out DIR]
                       [--yes] [--dry-run]
  --phases   comma-separated subset of baseline,no-pmf,no-ccp (default all three)
  --yes      don't ask before the first suspend (unattended runs, e.g. the device agent)
  --dry-run  collect the facts and plan the phases; no suspend, no module changes (root not needed)
"""
import argparse
import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
KMOD_SRC = os.path.join(HERE, "..", "installer", "kmod", "openbook_s0i3_snapshot.c")
DBG = "/sys/kernel/debug/amd_pmc"
UNLOAD = {"no-pmf": ["amdxdna", "amd_pmf"], "no-ccp": ["amdxdna", "amd_pmf", "amdtee", "kvm_amd", "ccp"]}

HOST = socket.gethostname()
MAC = re.compile(r"\b([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")
UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
SERIAL = re.compile(r"((?:Serial|serial|SERIAL)[ _-]?(?:[Nn]umber|NUMBER|No)?\s*[:=]\s*)\S.*")
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6 = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){3,7}[0-9a-fA-F]{1,4}\b")


def redact(text):
    text = MAC.sub("XX:XX:XX:XX:XX:XX", text)
    text = UUID.sub("<uuid>", text)
    text = SERIAL.sub(lambda m: m.group(1) + "<redacted>", text)
    text = IPV4.sub("<ip>", text)
    text = IPV6.sub("<ip6>", text)
    if HOST and len(HOST) > 2:
        text = text.replace(HOST, "<host>")
    return text


def read(path, default=None):
    try:
        with open(path, errors="replace") as f:
            return f.read().strip()
    except OSError:
        return default


def write(path, value):
    with open(path, "w") as f:
        f.write(value)


def run(cmd, timeout=120):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)


def num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ parsers (shared with the OpenBook probe's JSON)

def parse_smu(text):
    """/sys/kernel/debug/amd_pmc/smu_fw_info: the SMU's verdict and the per-IP 'condition not met' times."""
    out = {"last_s0i3": None, "hint_count": None, "time_to_s0i3_us": None, "time_in_s0i3_us": None, "not_met_us": {}}
    active = False
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("Hint Count:"):
            out["hint_count"] = num(line.split(":", 1)[1].strip())
        elif line.startswith("Last S0i3 Status:"):
            out["last_s0i3"] = line.split(":", 1)[1].strip()
        elif line.startswith("Time (in us) to S0i3:"):
            out["time_to_s0i3_us"] = num(line.split(":", 1)[1].strip())
        elif line.startswith("Time (in us) in S0i3:"):
            out["time_in_s0i3_us"] = num(line.split(":", 1)[1].strip())
        elif "Active time" in line:
            active = True
        elif active and ":" in line:
            k, v = (x.strip() for x in line.split(":", 1))
            if num(v):
                out["not_met_us"][k] = num(v)
    return out


def parse_cycle_log(text):
    """The kernel log of one cycle (pm_debug_messages on)."""
    m = re.findall(r"SMU idlemask s0i3: (0x[0-9a-fA-F]+)", text)
    snap = [l.split("s0i3-entry: ", 1)[1] for l in text.splitlines() if "openbook_s0i3_snapshot: s0i3-entry: " in l]
    return {
        "idlemask_entry": m[-1] if m else None,
        "not_deepest_warning": "didn't reach deepest state" in text,
        "constraints_not_met": sorted(set(re.findall(r"(\\\S+): LPI: Constraint not met", text))),
        "wake": sorted(set(re.findall(r"Resume caused by (IRQ \d+, [^\n]+)", text) +
                           re.findall(r"PM: Triggering wakeup from (IRQ \d+)", text))),
        "timekeeping_suspended_s": [float(x) for x in re.findall(r"Timekeeping suspended for ([\d.]+) seconds", text)],
        "snapshot_not_in_d3": [s for s in snap if s.startswith("0000:")],
        "snapshot_summary": next((s for s in reversed(snap) if not s.startswith("0000:")), None),
    }


def cpuidle_read():
    out = {}
    base = "/sys/devices/system/cpu"
    for cpu in sorted(os.listdir(base)):
        if not re.fullmatch(r"cpu\d+", cpu) or not os.path.isdir(f"{base}/{cpu}/cpuidle"):
            continue
        for st in sorted(os.listdir(f"{base}/{cpu}/cpuidle")):
            u = num(read(f"{base}/{cpu}/cpuidle/{st}/s2idle/usage"))
            if u is not None:
                out[(cpu, st)] = (u, num(read(f"{base}/{cpu}/cpuidle/{st}/s2idle/time")) or 0)
    return out


def cpuidle_delta(a, b):
    states = {}
    for (cpu, st), (u1, t1) in b.items():
        u0, t0 = a.get((cpu, st), (0, 0))
        s = states.setdefault(st, {"state": st, "name": read(f"/sys/devices/system/cpu/cpu0/cpuidle/{st}/name"),
                                   "latency_us": num(read(f"/sys/devices/system/cpu/cpu0/cpuidle/{st}/latency")),
                                   "entries": 0, "cpus": 0, "time_us": 0})
        s["entries"] += u1 - u0
        s["time_us"] += t1 - t0
        s["cpus"] += u1 > u0
    return [states[k] for k in sorted(states)]


# ------------------------------------------------------------------ the machine

def facts():
    f = {
        "kernel": os.uname().release,
        "board": read("/sys/class/dmi/id/board_name"), "product": read("/sys/class/dmi/id/product_name"),
        "bios": read("/sys/class/dmi/id/bios_version"), "bios_date": read("/sys/class/dmi/id/bios_date"),
        "cpu": next((l.split(":", 1)[1].strip() for l in (read("/proc/cpuinfo") or "").splitlines()
                     if l.startswith("model name")), None),
        "mem_sleep": read("/sys/power/mem_sleep"), "aspm_policy": read("/sys/module/pcie_aspm/parameters/policy"),
        "amd_pstate": read("/sys/devices/system/cpu/amd_pstate/status"),
        "epp": read("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference"),
        "ac_online": read("/sys/class/power_supply/ACAD/online"),
        "battery": {k: read(f"/sys/class/power_supply/BAT1/{k}") for k in ("status", "capacity")},
        "cmdline_flags": [w for w in (read("/proc/cmdline") or "").split()
                          if not re.search(r"uuid|PARTUUID|UUID|root=|cryptdevice|resume=", w, re.I)],
        "modules_of_interest": {},
        "amd_pmc": {}, "dgpu": {},
    }
    mods = {l.split()[0]: l.split()[2] for l in (read("/proc/modules") or "").splitlines()}
    for m in ("amd_pmc", "amd_pmf", "amdtee", "ccp", "kvm_amd", "amdxdna", "amd_sfh", "thunderbolt", "nvidia",
              "nvidia_drm", "asus_wmi", "asus_nb_wmi", "asus_armoury", "hid_asus", "amdgpu", "mt7925e"):
        f["modules_of_interest"][m] = {"loaded": m in mods, "users": num(mods.get(m))}
    for d in ("/sys/bus/platform/devices/AMDI000A:00", "/sys/bus/platform/devices/AMDI0007:00"):
        if os.path.isdir(d):
            f["amd_pmc"] = {k: read(f"{d}/{k}") for k in ("smu_program", "smu_fw_version")}
    for p in ("/sys/devices/platform/asus-nb-wmi/dgpu_disable", "/sys/devices/platform/asus-nb-wmi/gpu_mux_mode",
              "/sys/class/firmware-attributes/asus-armoury/attributes/dgpu_disable/current_value"):
        if os.path.exists(p):
            f["dgpu"][p.split("/")[-1] if "armoury" not in p else "armoury_dgpu_disable"] = read(p)
    pci = []
    for d in sorted(os.listdir("/sys/bus/pci/devices")):
        b = f"/sys/bus/pci/devices/{d}"
        drv = os.path.basename(os.readlink(f"{b}/driver")) if os.path.islink(f"{b}/driver") else "-"
        pci.append(f"{d} {read(f'{b}/vendor', '?')[2:]}:{read(f'{b}/device', '?')[2:]} class {read(f'{b}/class', '?')[2:]} "
                   f"driver {drv} {read(f'{b}/power_state', '-')} runtime {read(f'{b}/power/runtime_status', '-')} "
                   f"acpi {read(f'{b}/firmware_node/path', '-')}")
    f["pci"] = pci
    return f


class Modules:
    """Unload modules for one phase and always load them back (also from atexit)."""

    def __init__(self):
        self.removed = []

    def unload(self, names):
        loaded = {l.split()[0] for l in (read("/proc/modules") or "").splitlines()}
        for n in names:
            if n not in loaded:
                continue
            rc, out = run(["modprobe", "-r", n])
            if rc:
                return f"could not unload {n}: {out[-200:]}"
            self.removed.append(n)
        return None

    def restore(self):
        msgs = []
        while self.removed:
            n = self.removed.pop()
            rc, out = run(["modprobe", n])
            msgs.append(f"modprobe {n}: {'ok' if rc == 0 else out[-200:]}")
        return msgs


def kmsg(text):
    try:
        write("/dev/kmsg", f"openbook-linux-s2idle: {text}\n")
    except OSError:
        pass


def dmesg_since(marker):
    rc, out = run(["dmesg"])
    i = out.rfind(marker)
    return out[i:] if i >= 0 else out


def cycle(seconds, label):
    marker = f"openbook-linux-s2idle: cycle {label} start {time.time():.0f}"
    kmsg(marker[len("openbook-linux-s2idle: "):])
    pre = {k: num(read(f"/sys/power/suspend_stats/{k}")) for k in ("success", "fail", "total_hw_sleep")}
    ci0 = cpuidle_read()
    write("/sys/class/rtc/rtc0/wakealarm", "0")
    write("/sys/class/rtc/rtc0/wakealarm", f"+{seconds}")
    t0, err = time.time(), None
    try:
        write("/sys/power/state", "mem")
    except OSError as e:
        err = str(e)
    slept = time.time() - t0
    time.sleep(3)  # let the kernel finish logging the resume
    ci1 = cpuidle_read()
    post = {k: num(read(f"/sys/power/suspend_stats/{k}")) for k in ("success", "fail", "total_hw_sleep")}
    log = dmesg_since(marker)
    smu = parse_smu(read(f"{DBG}/smu_fw_info"))
    hw = num(read("/sys/power/suspend_stats/last_hw_sleep"))
    res = re.search(r"Residency Time: (\d+)", read(f"{DBG}/s0ix_stats", "") or "")
    c = {
        "label": label, "error": err, "wall_s": round(slept, 1),
        "suspend_success_delta": (post["success"] or 0) - (pre["success"] or 0),
        "suspend_fail_delta": (post["fail"] or 0) - (pre["fail"] or 0),
        "last_hw_sleep_us": hw,
        "total_hw_sleep_delta_us": None if post["total_hw_sleep"] is None else post["total_hw_sleep"] - (pre["total_hw_sleep"] or 0),
        "s0ix_residency_us": num(res.group(1)) if res else None,
        "smu": smu, "idlemask_after": (read(f"{DBG}/amd_pmc_idlemask", "") or "").split(":")[-1].strip() or None,
        "cpuidle": cpuidle_delta(ci0, ci1), **parse_cycle_log(log),
    }
    c["s0i3"] = bool((hw or 0) > 0 or smu["last_s0i3"] == "Success" or (c["s0ix_residency_us"] or 0) > 0)
    return c, log


def build_snapshot(work):
    kdir = f"/usr/lib/modules/{os.uname().release}/build"
    if not os.path.isdir(kdir):
        return None, f"no kernel headers in {kdir} (install linux-*-headers for this kernel to get the PCI snapshot)"
    if not shutil.which("make"):
        return None, "make is not installed"
    src = f"{work}/kmod"
    os.makedirs(src, exist_ok=True)
    shutil.copy(KMOD_SRC, src)
    write(f"{src}/Kbuild", "obj-m += openbook_s0i3_snapshot.o\n")
    rc, out = run(["make", "-s", "-C", kdir, f"M={src}", "modules"], timeout=600)
    ko = f"{src}/openbook_s0i3_snapshot.ko"
    return (ko, None) if rc == 0 and os.path.exists(ko) else (None, f"build failed: {out[-400:]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycles", type=int, default=2)
    ap.add_argument("--seconds", type=int, default=20)
    ap.add_argument("--phases", default="baseline,no-pmf,no-ccp")
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--amd-s2idle", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    phases = [p for p in a.phases.split(",") if p]
    bad = [p for p in phases if p not in ("baseline", "no-pmf", "no-ccp")]
    if bad:
        ap.error(f"unknown phase(s): {bad}")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = os.path.abspath(a.out or f"openbook-linux-s2idle-{stamp}")
    os.makedirs(out, exist_ok=True)
    summary = {"schema": "openbook-linux-s2idle/1", "started": stamp, "dry_run": a.dry_run,
               "args": {"cycles": a.cycles, "seconds": a.seconds, "phases": phases}, "phases": [], "notes": []}
    f = facts()
    summary["facts"] = {k: v for k, v in f.items() if k != "pci"}
    open(f"{out}/facts.txt", "w").write(redact(json.dumps(summary["facts"], indent=1) + "\n\nPCI functions:\n" +
                                               "\n".join(f["pci"]) + "\n"))
    if "[s2idle]" not in (f["mem_sleep"] or ""):
        summary["notes"].append(f"mem_sleep is {f['mem_sleep']!r}, not s2idle: the cycles test whatever 'mem' is")
    if not a.dry_run:
        if os.geteuid() != 0:
            sys.exit("run as root (sudo), or use --dry-run")
        if not a.yes:
            print(f"This suspends the laptop {a.cycles + len([p for p in phases if p != 'baseline'])} time(s) for "
                  f"{a.seconds} s each (screen off, then back). Save your work first.")
            if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
                sys.exit("cancelled")
    mods = Modules()
    snap_loaded = False
    try:
        if not a.dry_run:
            if not os.path.isdir(DBG):
                run(["mount", "-t", "debugfs", "none", "/sys/kernel/debug"])
            pm_debug = read("/sys/power/pm_debug_messages")
            write("/sys/power/pm_debug_messages", "1")
        if not a.no_snapshot:
            ko, why = build_snapshot(out) if not a.dry_run else (None, "dry run")
            summary["snapshot"] = {"built": bool(ko), "note": why}
            if ko and not a.dry_run:
                rc, msg = run(["insmod", ko])
                snap_loaded = rc == 0
                summary["snapshot"]["loaded"] = snap_loaded
                if rc:
                    summary["snapshot"]["note"] = msg[-300:]
        for ph in phases:
            entry = {"phase": ph, "unloaded": [], "cycles": [], "skipped": None}
            if a.dry_run:
                entry["skipped"] = f"dry run: would {'unload ' + ', '.join(UNLOAD[ph]) + ' and ' if ph in UNLOAD else ''}suspend"
                summary["phases"].append(entry)
                continue
            if ph in UNLOAD:
                why = mods.unload(UNLOAD[ph])
                entry["unloaded"] = list(mods.removed)
                if why:
                    entry["skipped"] = why
            if not entry["skipped"]:
                for i in range(a.cycles if ph == "baseline" else 1):
                    c, log = cycle(a.seconds, f"{ph}-{i}")
                    entry["cycles"].append(c)
                    open(f"{out}/dmesg-{ph}-{i}.txt", "w").write(redact(log))
                    print(f"{ph} cycle {i}: S0i3 {'REACHED' if c['s0i3'] else 'NOT reached'} "
                          f"(last_hw_sleep {c['last_hw_sleep_us']} us, SMU {c['smu']['last_s0i3']}, "
                          f"idle mask at entry {c['idlemask_entry']})", flush=True)
                    time.sleep(5)
            entry["reloaded"] = mods.restore()
            summary["phases"].append(entry)
        if a.amd_s2idle and not a.dry_run:
            if shutil.which("amd-s2idle"):
                rc, msg = run(["amd-s2idle", "test", "--count", "2", "--duration", str(a.seconds), "--wait", "5",
                               "--format", "md", "--report-file", f"{out}/amd-s2idle.md"], timeout=600)
                summary["amd_s2idle"] = {"rc": rc, "tail": redact(msg[-600:])}
                if os.path.exists(f"{out}/amd-s2idle.md"):
                    open(f"{out}/amd-s2idle.md", "w").write(redact(read(f"{out}/amd-s2idle.md")))
            else:
                summary["amd_s2idle"] = {"rc": None, "tail": "amd-s2idle not installed (pacman -S amd-debug-tools)"}
    finally:
        if mods.removed:
            summary["notes"].append(f"restored on exit: {mods.restore()}")
        if snap_loaded:
            run(["rmmod", "openbook_s0i3_snapshot"])
        if not a.dry_run:
            try:
                write("/sys/power/pm_debug_messages", pm_debug or "0")
            except (OSError, NameError):
                pass
        reached = {p["phase"]: [c["s0i3"] for c in p["cycles"]] for p in summary["phases"]}
        summary["verdict"] = {"s0i3_by_phase": reached,
                              "kernel_tainted": num(read("/proc/sys/kernel/tainted"))}
        json.dump(json.loads(redact(json.dumps(summary))), open(f"{out}/summary.json", "w"), indent=1)
        lines = [f"# S0i3 on this Linux: {f['product']} ({f['board']}), BIOS {f['bios']}, kernel {f['kernel']}", "",
                 "| Phase | Unloaded | Cycle | S0i3 | last_hw_sleep (us) | SMU | idle mask at entry | not in D3 at entry |",
                 "|---|---|---|---|---|---|---|---|"]
        for p in summary["phases"]:
            if p["skipped"]:
                lines.append(f"| {p['phase']} | {' '.join(p['unloaded']) or '-'} | - | skipped: {p['skipped'][:80]} | | | | |")
            for i, c in enumerate(p["cycles"]):
                lines.append(f"| {p['phase']} | {' '.join(p['unloaded']) or '-'} | {i} | {'yes' if c['s0i3'] else 'NO'} | "
                             f"{c['last_hw_sleep_us']} | {c['smu']['last_s0i3']} | {c['idlemask_entry']} | "
                             f"{c['snapshot_summary'] or '-'} |")
        lines += ["", "Notes: " + ("; ".join(summary["notes"]) or "none")]
        open(f"{out}/report.md", "w").write(redact("\n".join(lines) + "\n"))
        with tarfile.open(f"{out}.tar.gz", "w:gz") as t:
            t.add(out, arcname=os.path.basename(out))
        print("\n".join(lines))
        print(f"\nresults: {out}/ and {out}.tar.gz (attach the .tar.gz to the issue)")


if __name__ == "__main__":
    main()
