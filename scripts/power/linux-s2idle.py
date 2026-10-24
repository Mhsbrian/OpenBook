#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""S0i3 comparison on a laptop's own Linux (ANAL-178), or a Linux live USB (ANAL-257). Run it ON the laptop, as
root, from a terminal:

    sudo python3 scripts/power/linux-s2idle.py                # the laptop's own Linux
    sudo python3 scripts/power/linux-s2idle.py --live-usb     # a live USB (docs/googlebook-s0i3.md, owner steps)

It records whether this Linux reaches the SoC's deepest sleep (S0i3) over suspend-to-idle, and what changes when
two drivers OpenBook's kernel does not have are taken away for one cycle each. OpenBook's own kernel never reaches
S0i3 on the GA403WR (evidence/2026-10-16-g14-hwcheck, runs 2-7); this is the other half of that comparison.

Phases (each cycle: suspend-to-idle for --seconds, woken by the RTC; the screen goes dark and comes back):
  baseline    --cycles cycles as the system is
  nouveau     the NVIDIA dGPU bound to nouveau with runtime PM on (power/control=auto), one cycle once it has
              runtime-suspended (or after 60 s)
  driverless  nouveau and snd_hda_intel unbound from the dGPU, then OpenBook's own dGPU hook steps
              (openbook-pc-setup dgpu-pm: power/control=auto on every dGPU function, HDA power_save 10), one cycle;
              the drivers are bound again afterwards
  ptm-off     openbook_sleep_diag reloaded with ptm_off=1: PTM off on every PCI function across the cycle
  no-pmf      amdxdna and amd_pmf unloaded, one cycle, then loaded again
  no-ccp      also amdtee, kvm_amd and ccp (the PSP driver) unloaded, one cycle, then loaded again
  eco         only with --allow-firmware-change (owner approval naming the laptop): the dGPU removed and the
              firmware's dgpu_disable set to 1 (asus-wmi), one cycle, then dgpu_disable back to 0 and a PCI rescan.
              dgpu_disable persists in firmware; the script always tries to put it back, also after an error
With --amd-s2idle, AMD's own `amd-s2idle test` (package amd-debug-tools) runs one more cycle at the end of every
phase, in that phase's state.
If the kernel's headers are installed (linux-*-headers), the test-only module openbook_sleep_diag
(kernel/devices/anybook/sleep_diag/, the same source as the Googlebook image's sleep diagnostics) is built for this
kernel and loaded for the run with snapshot=1 usb4=1: at each S0i3 attempt it logs every PCI function not in D3 with
its link and PTM state, and the USB4 routers' runtime PM. It is unloaded at the end; an unsigned module marks the
kernel tainted until the next reboot (--no-snapshot skips it, and the ptm-off phase with it). Modules that cannot be
unloaded (in use) make that phase "skipped"; everything unloaded or unbound is loaded or bound again on exit, also
after an error or Ctrl-C. Nothing persists apart from eco's firmware setting, which is restored: no file outside the
output folder, no boot setting, no package changes.

--live-usb is the ANAL-257 run: phases baseline,nouveau,driverless,ptm-off,no-pmf,no-ccp and --amd-s2idle. It
refuses to run while any partition of an internal NVMe disk is mounted (the laptop's disks stay untouched: nothing
is installed, mounted or written there).

Output: ./openbook-linux-s2idle-<UTC time>/ with summary.json (schema openbook-linux-s2idle/1), report.md,
facts.txt and the kernel log of each cycle, all redacted (MAC addresses, UUIDs, serial numbers, IP addresses,
the host name), and the same as a .tar.gz to attach to the issue.

usage: linux-s2idle.py [--live-usb] [--cycles N] [--seconds S] [--phases LIST] [--no-snapshot] [--amd-s2idle]
                       [--allow-firmware-change] [--out DIR] [--yes] [--dry-run]
  --phases   comma-separated, in order, from baseline,nouveau,driverless,ptm-off,no-pmf,no-ccp,eco
             (default baseline,no-pmf,no-ccp)
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
KMOD_DIR = os.path.join(HERE, "..", "..", "kernel", "devices", "anybook", "sleep_diag")
KMOD = "openbook_sleep_diag"
KMOD_ARGS = ["snapshot=1", "usb4=1", "cycles=99"]
DBG = "/sys/kernel/debug/amd_pmc"
SYS = os.environ.get("OPENBOOK_SYSFS_ROOT", "") + "/sys"   # tests point this at a fake tree
UNLOAD = {"no-pmf": ["amdxdna", "amd_pmf"], "no-ccp": ["amdxdna", "amd_pmf", "amdtee", "kvm_amd", "ccp"]}
PHASES = ("baseline", "nouveau", "driverless", "ptm-off", "no-pmf", "no-ccp", "eco")
LIVE_USB_PHASES = "baseline,nouveau,driverless,ptm-off,no-pmf,no-ccp"

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
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
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
    # openbook_sleep_diag ("s0i3-entry N: ...") and the older openbook_s0i3_snapshot ("s0i3-entry: ...")
    snap = [re.split(r"s0i3-entry ?\d*: ?", l.split("openbook_", 1)[1], maxsplit=1)[1] for l in text.splitlines()
            if re.search(r"openbook_(sleep_diag|s0i3_snapshot): s0i3-entry( \d+)?: ", l)]
    ptm = [l.split("openbook_sleep_diag: ", 1)[1] for l in text.splitlines()
           if re.search(r"openbook_sleep_diag: (suspend|resume) \d+: PTM", l)]
    usb4 = [l.split("openbook_sleep_diag: ", 1)[1] for l in text.splitlines()
            if re.search(r"openbook_sleep_diag: (suspend|s0i3-entry): usb4 ", l)]
    return {
        "idlemask_entry": m[-1] if m else None,
        "not_deepest_warning": "didn't reach deepest state" in text,
        "constraints_not_met": sorted(set(re.findall(r"(\\\S+): LPI: Constraint not met", text))),
        "wake": sorted(set(re.findall(r"Resume caused by (IRQ \d+, [^\n]+)", text) +
                           re.findall(r"PM: Triggering wakeup from (IRQ \d+)", text))),
        "timekeeping_suspended_s": [float(x) for x in re.findall(r"Timekeeping suspended for ([\d.]+) seconds", text)],
        "snapshot_not_in_d3": [s for s in snap if s.startswith("0000:")],
        "snapshot_summary": next((s for s in reversed(snap) if not s.startswith("0000:") and "PCI functions" in s),
                                 None),
        "ptm": ptm,
        "usb4": usb4,
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


def build_diag(work):
    kdir = f"/usr/lib/modules/{os.uname().release}/build"
    if not os.path.isdir(kdir):
        return None, f"no kernel headers in {kdir} (install linux-*-headers for this kernel to get the PCI snapshot)"
    if not shutil.which("make"):
        return None, "make is not installed"
    src = f"{work}/kmod"
    os.makedirs(src, exist_ok=True)
    for f in ("openbook_sleep_diag.c", "ptm_plan.h"):
        shutil.copy(os.path.join(KMOD_DIR, f), src)
    write(f"{src}/Kbuild", f"obj-m += {KMOD}.o\n")
    rc, out = run(["make", "-s", "-C", kdir, f"M={src}", "modules"], timeout=600)
    ko = f"{src}/{KMOD}.ko"
    return (ko, None) if rc == 0 and os.path.exists(ko) else (None, f"build failed: {out[-400:]}")


def load_diag(ko, extra=()):
    """(Re)load openbook_sleep_diag; its parameters are read-only once loaded."""
    run(["rmmod", KMOD])
    rc, msg = run(["insmod", ko, *KMOD_ARGS, *extra])
    return rc == 0, msg[-300:]


# ------------------------------------------------------------------ the laptop's disks stay untouched (ANAL-257)

def on_nvme(name, depth=0):
    """A block device that is an NVMe disk or partition, or sits on one (dm-crypt, LVM, md)."""
    if name.startswith("nvme"):
        return True
    slaves = f"{SYS}/class/block/{name}/slaves"
    return depth < 4 and os.path.isdir(slaves) and any(on_nvme(x, depth + 1) for x in os.listdir(slaves))


def nvme_in_use(mounts=None, swaps=None):
    """Mounted filesystems and active swap on an NVMe disk: [(device, where)]."""
    out = []
    for text, kind in ((mounts if mounts is not None else read("/proc/mounts") or "", "mount"),
                       (swaps if swaps is not None else read("/proc/swaps") or "", "swap")):
        for line in text.splitlines():
            w = line.split()
            if len(w) < 2 or not w[0].startswith("/dev/"):
                continue
            name = os.path.basename(os.path.realpath(w[0]) if mounts is None else w[0])
            if on_nvme(name):
                out.append((w[0], w[1] if kind == "mount" else "swap"))
    return out


# ------------------------------------------------------------------ the NVIDIA dGPU (ANAL-257)

def pci_dir(bdf):
    return f"{SYS}/bus/pci/devices/{bdf}"


def driver_of(bdf):
    link = f"{pci_dir(bdf)}/driver"
    return os.path.basename(os.readlink(link)) if os.path.islink(link) else None


def find_dgpu():
    """NVIDIA functions: display (class 03xx), the others (HDMI audio), and the bridge (root port) above them."""
    base = f"{SYS}/bus/pci/devices"
    g = {"display": [], "other": [], "bridge": None}
    for d in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if read(f"{base}/{d}/vendor") != "0x10de":
            continue
        g["display" if (read(f"{base}/{d}/class") or "").startswith("0x03") else "other"].append(d)
        up = os.path.basename(os.path.dirname(os.path.realpath(f"{base}/{d}")))
        if g["bridge"] is None and re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]", up):
            g["bridge"] = up
    return g


def dgpu_state(g):
    def one(bdf):
        d = pci_dir(bdf)
        return {"bdf": bdf, "driver": driver_of(bdf), "power_state": read(f"{d}/power_state"),
                "runtime_status": read(f"{d}/power/runtime_status"), "control": read(f"{d}/power/control")}
    return {"functions": [one(b) for b in g["display"] + g["other"]],
            "bridge": one(g["bridge"]) if g["bridge"] else None}


def wait_dgpu_asleep(g, timeout=60):
    """Until the bridge above the dGPU (or, without one, its display function) has runtime-suspended."""
    target = g["bridge"] or (g["display"] or [None])[0]
    t0 = time.time()
    while target:
        if read(f"{pci_dir(target)}/power/runtime_status") == "suspended":
            return True, round(time.time() - t0, 1)
        if time.time() - t0 >= timeout:
            break
        time.sleep(1)
    return False, round(time.time() - t0, 1)


class Binds:
    """Driver binds/unbinds and sysfs writes for one phase, undone in reverse order (also from finally)."""

    def __init__(self):
        self.undo = []

    def unbind(self, bdf):
        drv = driver_of(bdf)
        if drv:
            write(f"{SYS}/bus/pci/drivers/{drv}/unbind", bdf)
            self.undo.append(("bind", drv, bdf))
        return drv

    def bind(self, drv, bdf):
        write(f"{SYS}/bus/pci/drivers/{drv}/bind", bdf)
        self.undo.append(("unbind", drv, bdf))

    def set(self, path, value):
        old = read(path)
        if old is not None and old != value:
            write(path, value)
            self.undo.append(("set", path, old))

    def restore(self):
        msgs = []
        while self.undo:
            op, a, b = self.undo.pop()
            try:
                write(f"{SYS}/bus/pci/drivers/{a}/{op}" if op != "set" else a, b)
                msgs.append(f"{op} {a} {b}: ok")
            except OSError as e:
                msgs.append(f"{op} {a} {b}: {e}")
        return msgs


def busy_driver(g):
    """A display driver other than nouveau owns the dGPU: this script never unbinds or replaces it."""
    for bdf in g["display"]:
        drv = driver_of(bdf)
        if drv and drv != "nouveau":
            return f"{bdf} is driven by {drv}; these phases need nouveau or no driver (boot without the NVIDIA driver)"
    return None


def prep_nouveau(g, binds):
    if not g["display"]:
        return "no NVIDIA display function on the PCI bus (dgpu_disable=1, or no dGPU)"
    why = busy_driver(g)
    if why:
        return why
    if not all(driver_of(b) for b in g["display"]):
        run(["modprobe", "nouveau"])
    for bdf in g["display"]:
        if not driver_of(bdf):
            try:
                binds.bind("nouveau", bdf)
            except OSError as e:
                return f"could not bind nouveau to {bdf}: {e}"
        if driver_of(bdf) != "nouveau":
            return f"nouveau did not take {bdf}"
    for bdf in g["display"] + g["other"] + ([g["bridge"]] if g["bridge"] else []):
        binds.set(f"{pci_dir(bdf)}/power/control", "auto")
    return None


def prep_driverless(g, binds):
    """Unbind the dGPU's drivers, then what openbook-pc-setup dgpu-pm does on the Googlebook image."""
    if not g["display"]:
        return "no NVIDIA display function on the PCI bus (dgpu_disable=1, or no dGPU)"
    why = busy_driver(g)
    if why:
        return why
    try:
        for bdf in g["other"]:
            if driver_of(bdf) == "snd_hda_intel":
                binds.unbind(bdf)
        for bdf in g["display"]:
            binds.unbind(bdf)
        for bdf in g["display"] + g["other"]:
            binds.set(f"{pci_dir(bdf)}/power/control", "auto")
        if read(f"{SYS}/module/snd_hda_intel/parameters/power_save") == "0":
            binds.set(f"{SYS}/module/snd_hda_intel/parameters/power_save", "10")
    except OSError as e:
        return f"could not prepare: {e}"
    return None


ECO = ("/class/firmware-attributes/asus-armoury/attributes/dgpu_disable/current_value",
       "/devices/platform/asus-nb-wmi/dgpu_disable")
MUX = ("/class/firmware-attributes/asus-armoury/attributes/gpu_mux_mode/current_value",
       "/devices/platform/asus-nb-wmi/gpu_mux_mode")


def prep_eco(g, binds, state):
    """Eco mode as supergfxctl does it: drivers off, dGPU functions removed, firmware dgpu_disable=1."""
    path = next((SYS + p for p in ECO if os.path.exists(SYS + p)), None)
    mux = next((read(SYS + p) for p in MUX if os.path.exists(SYS + p)), None)
    if not path:
        return "no dgpu_disable control (asus-wmi or asus-armoury not loaded)"
    if read(path) != "0":
        return f"dgpu_disable is {read(path)!r}, not 0: not touching it"
    if mux not in (None, "1"):
        return f"gpu_mux_mode is {mux!r}, not 1 (Optimus): not touching the dGPU"
    why = busy_driver(g)
    if why:
        return why
    try:
        for bdf in g["other"] + g["display"]:
            binds.unbind(bdf)
        for bdf in g["other"] + g["display"]:
            write(f"{pci_dir(bdf)}/remove", "1")
        binds.undo.clear()          # the functions are gone; the rescan in restore_eco brings them back
        state["removed"] = True
        state["path"] = path
        state["set"] = True         # set before the write: restore_eco always tries to put 0 back
        write(path, "1")
    except OSError as e:
        return f"could not switch to Eco: {e}"
    return None


def restore_eco(state):
    msgs = []
    if state.get("set"):
        try:
            write(state["path"], "0")
            state["set"] = False
            msgs.append("dgpu_disable 0: ok")
        except OSError as e:
            msgs.append(f"dgpu_disable 0 FAILED ({e}): set it back before anything else: echo 0 > {state['path']}")
    if state.pop("removed", False):
        time.sleep(2)
        try:
            write(f"{SYS}/bus/pci/rescan", "1")
            msgs.append("PCI rescan: ok")
        except OSError as e:
            msgs.append(f"PCI rescan: {e}")
    return msgs


def amd_s2idle(out, ph, seconds):
    """AMD's own tool, one cycle in this phase's state. --force: it still runs (and reports) when a prerequisite
    it checks is what this phase took away."""
    if not shutil.which("amd-s2idle"):
        return {"rc": None, "tail": "amd-s2idle not installed (package amd-debug-tools)"}
    rep_file = f"{out}/amd-s2idle-{ph}.md"
    rc, msg = run(["amd-s2idle", "test", "--count", "1", "--duration", str(seconds), "--wait", "5", "--force",
                   "--format", "md", "--report-file", rep_file], timeout=900)
    if os.path.exists(rep_file):
        open(rep_file, "w").write(redact(read(rep_file)))
    return {"rc": rc, "report": os.path.basename(rep_file) if os.path.exists(rep_file) else None,
            "tail": redact(msg[-600:])}


PLAN = {"baseline": "suspend as the system is", "nouveau": "bind nouveau to the dGPU (runtime PM on) and suspend",
        "driverless": "unbind nouveau and snd_hda_intel from the dGPU, apply dgpu-pm, suspend, bind them again",
        "ptm-off": "reload openbook_sleep_diag with ptm_off=1 and suspend",
        "no-pmf": "unload " + ", ".join(UNLOAD["no-pmf"]) + " and suspend",
        "no-ccp": "unload " + ", ".join(UNLOAD["no-ccp"]) + " and suspend",
        "eco": "remove the dGPU, set dgpu_disable=1, suspend, set dgpu_disable=0 and rescan"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live-usb", action="store_true")
    ap.add_argument("--cycles", type=int, default=2)
    ap.add_argument("--seconds", type=int, default=20)
    ap.add_argument("--phases")
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--amd-s2idle", action="store_true")
    ap.add_argument("--allow-firmware-change", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    a.amd_s2idle = a.amd_s2idle or a.live_usb
    phases = [p for p in (a.phases or (LIVE_USB_PHASES if a.live_usb else "baseline,no-pmf,no-ccp")).split(",") if p]
    bad = [p for p in phases if p not in PHASES]
    if bad:
        ap.error(f"unknown phase(s): {bad}")
    if "eco" in phases and not a.allow_firmware_change:
        ap.error("eco changes a firmware setting (dgpu_disable): it needs the owner's approval naming this laptop, "
                 "then --allow-firmware-change")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = os.path.abspath(a.out or f"openbook-linux-s2idle-{stamp}")
    os.makedirs(out, exist_ok=True)
    summary = {"schema": "openbook-linux-s2idle/1", "started": stamp, "dry_run": a.dry_run, "live_usb": a.live_usb,
               "args": {"cycles": a.cycles, "seconds": a.seconds, "phases": phases, "amd_s2idle": a.amd_s2idle},
               "phases": [], "notes": []}
    f = facts()
    f["dgpu_pci"] = dgpu_state(find_dgpu())
    f["nvme_in_use"] = [list(x) for x in nvme_in_use()]
    summary["facts"] = {k: v for k, v in f.items() if k != "pci"}
    open(f"{out}/facts.txt", "w").write(redact(json.dumps(summary["facts"], indent=1) + "\n\nPCI functions:\n" +
                                               "\n".join(f["pci"]) + "\n"))
    if "[s2idle]" not in (f["mem_sleep"] or ""):
        summary["notes"].append(f"mem_sleep is {f['mem_sleep']!r}, not s2idle: the cycles test whatever 'mem' is")
    if a.live_usb and f["nvme_in_use"]:
        msg = (f"an internal NVMe disk is in use ({', '.join(d + ' on ' + w for d, w in f['nvme_in_use'])}): "
               "unmount it (and swapoff) first; the live-USB run never touches the laptop's disks")
        if not a.dry_run:
            sys.exit(msg)
        summary["notes"].append("dry run: " + msg)
    if not a.dry_run:
        if os.geteuid() != 0:
            sys.exit("run as root (sudo), or use --dry-run")
        if not a.yes:
            n = a.cycles + sum(1 for p in phases if p != "baseline") + (len(phases) if a.amd_s2idle else 0)
            print(f"This suspends the laptop about {n} time(s) for {a.seconds} s each (screen off, then back). "
                  "Save your work first.")
            if "eco" in phases:
                print("The eco phase sets the firmware's dgpu_disable to 1 and back to 0 afterwards.")
            if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
                sys.exit("cancelled")
    mods = Modules()
    diag_ko = None
    try:
        if not a.dry_run:
            if not os.path.isdir(DBG):
                run(["mount", "-t", "debugfs", "none", "/sys/kernel/debug"])
            pm_debug = read("/sys/power/pm_debug_messages")
            write("/sys/power/pm_debug_messages", "1")
        if not a.no_snapshot:
            ko, why = build_diag(out) if not a.dry_run else (None, "dry run")
            summary["snapshot"] = {"module": KMOD, "built": bool(ko), "note": why}
            if ko and not a.dry_run:
                ok, msg = load_diag(ko)
                summary["snapshot"]["loaded"] = ok
                if ok:
                    diag_ko = ko
                    rc, klog = run(["dmesg"])
                    open(f"{out}/sleep-diag-load.txt", "w").write(
                        redact("\n".join(l for l in klog.splitlines() if f"{KMOD}:" in l) + "\n"))
                else:
                    summary["snapshot"]["note"] = msg
        for ph in phases:
            entry = {"phase": ph, "unloaded": [], "cycles": [], "skipped": None}
            if a.dry_run:
                entry["skipped"] = f"dry run: would {PLAN[ph]}"
                summary["phases"].append(entry)
                continue
            binds, eco = Binds(), {}
            try:
                g = find_dgpu()
                if ph in UNLOAD:
                    why = mods.unload(UNLOAD[ph])
                    entry["unloaded"] = list(mods.removed)
                    entry["skipped"] = why
                elif ph == "nouveau":
                    entry["skipped"] = prep_nouveau(g, binds)
                elif ph == "driverless":
                    entry["skipped"] = prep_driverless(g, binds)
                elif ph == "ptm-off":
                    ok, msg = load_diag(diag_ko, ["ptm_off=1"]) if diag_ko else (False, "needs openbook_sleep_diag "
                                                                                       "(kernel headers, not --no-snapshot)")
                    entry["skipped"] = None if ok else msg
                elif ph == "eco":
                    entry["skipped"] = prep_eco(g, binds, eco)
                if not entry["skipped"] and ph in ("nouveau", "driverless"):
                    reached, after = wait_dgpu_asleep(find_dgpu())
                    entry["dgpu_runtime_suspended"] = {"reached": reached, "after_s": after}
                entry["dgpu"] = dgpu_state(find_dgpu())
                if not entry["skipped"]:
                    for i in range(a.cycles if ph == "baseline" else 1):
                        c, log = cycle(a.seconds, f"{ph}-{i}")
                        entry["cycles"].append(c)
                        open(f"{out}/dmesg-{ph}-{i}.txt", "w").write(redact(log))
                        print(f"{ph} cycle {i}: S0i3 {'REACHED' if c['s0i3'] else 'NOT reached'} "
                              f"(last_hw_sleep {c['last_hw_sleep_us']} us, SMU {c['smu']['last_s0i3']}, "
                              f"idle mask at entry {c['idlemask_entry']})", flush=True)
                        time.sleep(5)
                    if a.amd_s2idle:
                        entry["amd_s2idle"] = amd_s2idle(out, ph, a.seconds)
            finally:
                entry["restored"] = restore_eco(eco) + mods.restore() + binds.restore()
                if ph == "ptm-off" and diag_ko:
                    entry["restored"].append(f"{KMOD} without ptm_off: {'ok' if load_diag(diag_ko)[0] else 'failed'}")
                summary["phases"].append(entry)
    finally:
        if mods.removed:
            summary["notes"].append(f"restored on exit: {mods.restore()}")
        if diag_ko:
            run(["rmmod", KMOD])
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
                 "| Phase | Changed | Cycle | S0i3 | last_hw_sleep (us) | SMU | idle mask at entry | not in D3 at entry |",
                 "|---|---|---|---|---|---|---|---|"]
        for p in summary["phases"]:
            changed = " ".join(p["unloaded"]) or ("-" if p["phase"] in ("baseline",) else p["phase"])
            if p["skipped"]:
                lines.append(f"| {p['phase']} | {changed} | - | skipped: {p['skipped'][:80]} | | | | |")
            for i, c in enumerate(p["cycles"]):
                lines.append(f"| {p['phase']} | {changed} | {i} | {'yes' if c['s0i3'] else 'NO'} | "
                             f"{c['last_hw_sleep_us']} | {c['smu']['last_s0i3']} | {c['idlemask_entry']} | "
                             f"{c['snapshot_summary'] or '-'} |")
            if p.get("amd_s2idle"):
                lines.append(f"| {p['phase']} | amd-s2idle | - | see {p['amd_s2idle'].get('report') or 'tail'} | | | | |")
        lines += ["", "Notes: " + ("; ".join(summary["notes"]) or "none")]
        open(f"{out}/report.md", "w").write(redact("\n".join(lines) + "\n"))
        with tarfile.open(f"{out}.tar.gz", "w:gz") as t:
            t.add(out, arcname=os.path.basename(out))
        print("\n".join(lines))
        print(f"\nresults: {out}/ and {out}.tar.gz (attach the .tar.gz to the issue)")


if __name__ == "__main__":
    main()
