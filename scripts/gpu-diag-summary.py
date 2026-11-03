#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarise gpu-diag.sh runs (ANAL-336, docs/gpu-diagnostics.md).

usage: gpu-diag-summary.py RUN_DIR...            run.json in each RUN_DIR, and a table of them on stdout
       gpu-diag-summary.py --json OUT RUN_DIR... also every run's summary in one file

Per run: the GPU the app's own processes reported (renderer and driver lines in its logcat), Android's routing
inputs, start-up time, frame pacing from SurfaceFlinger's per-layer present timestamps over the scored interval,
TimeStats for the same layers, CPU and GPU load, clocks, temperatures, the dGPU's runtime status, battery energy
(battery runs only), kernel GPU errors and crashes. A run is "valid" only if it finished, the sampled timestamps
cover the whole interval, and the renderer seen matches the GPU asked for. Missing data stays missing (None):
no sample is ever counted as zero frames or zero jank.

Table: one row per (label, gpu) with every run's value, the median and min-max; invalid runs are listed with why.
"""
import json
import os
import re
import statistics
import sys

PENDING = 9223372036854775807  # FenceTime::Signal::PENDING (INT64_MAX)


def read(d, name):
    try:
        with open(os.path.join(d, name), errors="replace") as f:
            return f.read()
    except OSError:
        return None


def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def kvs(line):
    return dict(re.findall(r"(\w+)=(\S+)", line))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------- sampler output
def parse_samples(text):
    """device.sh sample output -> {begin, end, abort, vsync_ns, samples: [{up_cs, layers: {name: [(d, a, r)]}}],
    loads: [{...}]}"""
    out = {"begin": None, "end": None, "abort": None, "vsync_ns": None, "samples": [], "loads": [], "malformed": []}
    if text is None:
        return out
    cur = None      # current @t sample
    layer = None    # current @L layer name inside it
    last = None     # the last @L layer, which an @Le line closes
    load = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("@"):
            layer = None
            if line.startswith("@Le "):
                # Exactly three integers, end not before start; anything else is a malformed timing (a gap).
                m = re.fullmatch(r"@Le s=(\d+) e=(\d+) rc=(\d+)", line)
                t = tuple(int(x) for x in m.groups()) if m else None
                if t is None or t[1] < t[0]:
                    out["malformed"].append(line)
                    t = None
                if cur is not None and last is not None:
                    cur.setdefault("timing", {})[last] = t
                continue
            if line.startswith("@begin"):
                b = kvs(line)
                out["begin"] = b
                out["vsync_ns"] = num(b.get("vsync_ns"))
            elif line.startswith("@end"):
                out["end"] = kvs(line)
            elif line.startswith("@abort"):
                out["abort"] = line[len("@abort "):]
            elif line.startswith("@t "):
                m = re.fullmatch(r"@t up_cs=(\d+)", line)
                if not m:                       # a sample without a valid time: its dumps are dropped
                    out["malformed"].append(line)
                    cur = None
                    continue
                cur = {"up_cs": int(m.group(1)), "layers": {}}
                out["samples"].append(cur)
                load = None
            elif line.startswith("@L ") and cur is not None:
                layer = last = line[3:]
                cur["layers"][layer] = []
                cur.setdefault("vsync", {})[layer] = None
                cur.setdefault("bad", {})[layer] = 0
            elif line.startswith("@load"):
                m = re.fullmatch(r"@load up_cs=(\d+)", line)
                if not m:
                    out["malformed"].append(line)
                    load = None
                    continue
                load = {"up_cs": int(m.group(1)), "pidstat": [], "freq": {}, "nvidia": {}, "hwmon": {}, "bat": {}}
                out["loads"].append(load)
            continue
        if layer is not None and cur is not None:
            # dumpsys SurfaceFlinger --latency: the pacesetter's vsync period, then one row per frame, then a blank line
            parts = line.split("\t")
            if len(parts) == 3:
                try:
                    cur["layers"][layer].append(tuple(int(x) for x in parts))
                except ValueError:
                    cur["bad"][layer] += 1
            elif line.strip().isdigit() and cur["vsync"][layer] is None and not cur["layers"][layer]:
                cur["vsync"][layer] = int(line)
            elif line.strip():
                cur["bad"][layer] += 1
            continue
        if load is None:
            continue
        w = line.split()
        if not w:
            continue
        if w[0] == "cpu":
            load["cpu"] = [int(x) for x in w[1:]]
        elif w[0] == "pidstat" and len(w) > 2:
            # pidstat NAME PID (COMM) STATE ...: utime and stime are /proc/PID/stat's fields 14 and 15
            m = re.match(r"(\d+) \((.*)\) (.*)", line.split(" ", 2)[2])
            if m:
                f = m.group(3).split()
                if len(f) > 12:
                    load["pidstat"].append((int(m.group(1)), w[1], int(f[11]) + int(f[12])))
        elif w[0] == "freq" and len(w) == 3:
            load["freq"][w[1]] = num(w[2])
        elif w[0] == "amdgpu" and len(w) > 1 and w[1] != "na":
            k = kvs(line)
            load["amdgpu"] = {"busy": num(k.get("busy")), "mem_busy": num(k.get("mem_busy")),
                              "sclk": k.get("sclk"), "mclk": k.get("mclk")}
        elif w[0] == "amdgpu_hwmon":
            k = kvs(line)
            load["amdgpu_hwmon"] = {"temp_mC": num(k.get("temp_mC")), "power_uW": num(k.get("power_uW"))}
        elif w[0] == "nvidia" and len(w) > 2:
            load["nvidia"][w[1]] = kvs(line).get("runtime_status")
        elif w[0] == "hwmon" and len(w) > 2:
            load["hwmon"][w[1]] = num(kvs(line).get("temp1_mC"))
        elif w[0] == "bat" and len(w) > 2:
            load["bat"][w[1]] = {k: num(v) if k != "status" else v for k, v in kvs(line).items()}
    return out


# On Android 17, dumpsys SurfaceFlinger --latency LAYER reads FrameTimeline (Layer::getFrameStats ->
# FrameTimeline::generateFrameStats): the layer's frames among the last 64 display frames (kDefaultMaxDisplayFrames)
# whose present fence has signalled. SurfaceFlinger composes at most one display frame per vsync, so a dump reaches
# back at least WINDOW vsyncs. Each dump is timed (@Le: start s, end e, centiseconds), so two dumps' snapshots are
# at most (e2 - s1 + 1) cs apart; that must stay under WINDOW - SLACK vsyncs (SLACK: frames still pending at either
# snapshot, and rounding).
WINDOW = 64
SLACK = 4


def row_key(d, a, r):
    """A frame's identity across samples: its desired-present time, else its ready or present time."""
    for v in (d, r, a):
        if 0 < v < PENDING:
            return v
    return None


def valid_frames(records):
    """--latency rows -> {key: (desired, actual, ready)} for frames whose present fence signalled."""
    fr = {}
    for d, a, r in records:
        if 0 < a < PENDING:
            fr[row_key(d, a, r)] = (d, a, r)
    return fr


def layer_frames(parsed):
    """Per layer: every presented frame seen across samples, and continuity gaps: a dump with no timing, a failed or
    unparsable dump, or two consecutive dumps of the layer whose snapshots may be WINDOW - SLACK vsyncs apart or
    more."""
    frames, gaps, prev = {}, {}, {}
    for s in parsed["samples"]:
        for name, recs in s["layers"].items():
            frames.setdefault(name, {}).update(valid_frames(recs))
            t = s.get("timing", {}).get(name)
            vs = s.get("vsync", {}).get(name)
            bad = (t is None or None in t or t[2] != 0 or not vs or s.get("bad", {}).get(name))
            if bad:
                gaps[name] = gaps.get(name, 0) + 1
                prev.pop(name, None)
                continue
            if name in prev:
                s1, vs1 = prev[name]
                span_ms = (t[1] - s1 + 1) * 10
                if span_ms >= (WINDOW - SLACK) * min(vs, vs1) / 1e6:
                    gaps[name] = gaps.get(name, 0) + 1
            prev[name] = (t[0], vs)
    return frames, gaps


def pacing(parsed):
    """Frame pacing of the scored interval: frames presented after the first sample's newest frame, up to the last
    sample's newest frame, on the layer with the most such frames."""
    frames, gaps = layer_frames(parsed)
    samples = [s for s in parsed["samples"] if s["layers"]]
    res = {"layers": {}, "primary": None, "vsync_ns": parsed["vsync_ns"]}
    if not samples:
        return res
    # The scored interval as the sampler saw it: its first to its last sample (device clock).
    phase_s = (parsed["samples"][-1]["up_cs"] - parsed["samples"][0]["up_cs"]) / 100.0
    for name, fr in frames.items():
        first = next((s for s in samples if valid_frames(s["layers"].get(name, []))), None)
        last = next((s for s in reversed(samples) if valid_frames(s["layers"].get(name, []))), None)
        if first is None:
            continue
        b0 = max(a for _, a, _ in valid_frames(first["layers"][name]).values())
        b1 = max(a for _, a, _ in valid_frames(last["layers"][name]).values())
        pres = sorted(a for _, a, _ in fr.values() if b0 <= a <= b1)
        lat = [(a - r) / 1e6 for _, a, r in fr.values() if b0 < a <= b1 and 0 < r < PENDING]
        n = len(pres) - 1
        dur = (b1 - b0) / 1e9
        iv = [(y - x) / 1e6 for x, y in zip(pres, pres[1:])]
        info = {"frames": n if n > 0 else 0, "seconds": round(dur, 3), "coverage_gaps": gaps.get(name, 0),
                "interval_s": round(phase_s, 2), "covered": round(dur / phase_s, 3) if phase_s > 0 else None,
                "first_sample_up_cs": first["up_cs"], "last_sample_up_cs": last["up_cs"]}
        if n > 0 and dur > 0:
            vs = (parsed["vsync_ns"] or 0) / 1e6
            med = statistics.median(iv)
            info.update({
                "fps": round(n / dur, 2),
                "frame_ms": {k: round(pct(iv, p), 3) for k, p in
                             (("p50", 50), ("p90", 90), ("p95", 95), ("p99", 99), ("max", 100))},
                "refresh_hz": round(1000 / vs, 2) if vs else None,
                "missed_vsync": sum(1 for x in iv if vs and x > 1.5 * vs) if vs else None,
                "over_cadence": sum(1 for x in iv if x > 1.5 * med),
                "cadence_vsyncs": round(med / vs, 2) if vs else None,
                "ready_to_present_ms": {"p50": round(pct(lat, 50), 3), "p99": round(pct(lat, 99), 3)} if lat else None,
            })
        res["layers"][name] = info
    if res["layers"]:
        res["primary"] = max(res["layers"], key=lambda k: res["layers"][k]["frames"])
    return res


def first_frame(parsed):
    """Seconds from the warm-up sampler's start to the first sample in which an app layer had presented frames."""
    b = parsed["begin"]
    if not b:
        return None
    if not str(b.get("up_cs", "")).isdigit():
        return None
    t0 = int(b["up_cs"])
    for s in parsed["samples"]:
        if any(valid_frames(r) for r in s["layers"].values()):
            return round((s["up_cs"] - t0) / 100.0, 2)
    return None


def hitches(parsed, ms=100.0):
    pres = sorted(a for fr in layer_frames(parsed)[0].values() for _, a, _ in fr.values())
    return sum(1 for x, y in zip(pres, pres[1:]) if (y - x) / 1e6 > ms)


def loads(parsed, procs_pkg):
    L = [x for x in parsed["loads"] if "cpu" in x]
    out = {}
    if len(L) >= 2:
        a, b = L[0], L[-1]
        tot = sum(b["cpu"]) - sum(a["cpu"])
        idle = (b["cpu"][3] + b["cpu"][4]) - (a["cpu"][3] + a["cpu"][4])
        secs = (b["up_cs"] - a["up_cs"]) / 100.0
        out["cpu_busy_pct"] = round(100.0 * (tot - idle) / tot, 1) if tot > 0 else None
        ncpu = max(len(x["freq"]) for x in L) or 1
        groups = {}
        first = {pid: (comm, t) for pid, comm, t in a["pidstat"]}
        for pid, comm, t in b["pidstat"]:
            if pid in first:
                g = "app" if comm == procs_pkg or comm.startswith(procs_pkg + ":") else comm
                groups[g] = groups.get(g, 0) + (t - first[pid][1])
        # clock ticks (USER_HZ 100) per second = percent of one CPU
        out["cpu_pct_of_one_core"] = {g: round(v / secs, 1) for g, v in groups.items()} if secs > 0 else None
        out["cpus"] = ncpu
    fq = [statistics.median([v for v in x["freq"].values() if v]) / 1000 for x in L if any(x["freq"].values())]
    out["cpu_mhz_median"] = round(statistics.median(fq)) if fq else None
    gb = [x["amdgpu"]["busy"] for x in L if x.get("amdgpu") and x["amdgpu"]["busy"] is not None]
    out["amdgpu_busy_pct"] = {"median": statistics.median(gb), "max": max(gb)} if gb else None
    sc = [x["amdgpu"]["sclk"] for x in L if x.get("amdgpu") and x["amdgpu"]["sclk"] not in (None, "na", "")]
    out["amdgpu_sclk_median"] = statistics.median_low(sc) if sc else None
    gt = [x["amdgpu_hwmon"]["temp_mC"] / 1000 for x in L if x.get("amdgpu_hwmon") and x["amdgpu_hwmon"]["temp_mC"]]
    out["amdgpu_temp_c_max"] = max(gt) if gt else None
    gp = [x["amdgpu_hwmon"]["power_uW"] / 1e6 for x in L if x.get("amdgpu_hwmon") and x["amdgpu_hwmon"]["power_uW"]]
    out["amdgpu_power_w_median"] = round(statistics.median(gp), 2) if gp else None
    hw = {}
    for x in L:
        for k, v in x["hwmon"].items():
            if v is not None:
                hw[k] = max(hw.get(k, -1e9), v / 1000)
    out["hwmon_temp_c_max"] = hw or None
    nv = {}
    for x in L:
        for bdf, st in x["nvidia"].items():
            nv.setdefault(bdf, {}).setdefault(st, 0)
            nv[bdf][st] += 1
    out["nvidia_runtime_status"] = nv or None
    # Battery energy: integrate power_now (µW) over the samples, when the shell user could read it.
    e, prev = 0.0, None
    for x in L:
        for bat, v in x["bat"].items():
            p = v.get("power_uW")
            if p is None and v.get("current_uA") is not None and v.get("voltage_uV") is not None:
                p = v["current_uA"] * v["voltage_uV"] / 1e6
            if p is not None and prev is not None:
                e += (p / 1e6) * (x["up_cs"] - prev) / 100.0
            if p is not None:
                prev = x["up_cs"]
    out["battery_energy_j_sampled"] = round(e, 1) if prev is not None and e > 0 else None
    return out


# ------------------------------------------------------------------------------------------- other files
def timestats(text, pkg):
    if not text:
        return None
    res = []
    for blk in text.split("\ndisplayRefreshRate = ")[1:]:
        if f"packageName = {pkg}" not in blk and pkg not in (re.search(r"layerName = (.*)", blk) or [""])[0]:
            continue
        g = lambda k: (re.search(rf"^{k} = (.*)$", blk, re.M) or [None, None])[1]
        res.append({"layer": g("layerName"), "totalFrames": num(g("totalFrames")),
                    "droppedFrames": num(g("droppedFrames")), "averageFPS": num(g("averageFPS")),
                    "renderRate": g("renderRate"), "displayRefreshRate": blk.split("\n", 1)[0]})
    return res


def am_start(text):
    if not text:
        return None
    g = lambda k: (re.search(rf"^{k}: (\S+)", text, re.M) or [None, None])[1]
    return {"status": g("Status"), "launch_state": g("LaunchState"), "total_ms": num(g("TotalTime")),
            "wait_ms": num(g("WaitTime"))}


# What identifies the GPU an app renders on: its GL renderer string or Vulkan device name. Driver selection and
# loading (GraphicsEnvironment's choice, the driver package's search path, libEGL/vulkan loader lines) say which
# driver Android picked, not what the app rendered on: they are kept, and never count as verification.
RENDERER_ID = re.compile(r"(ANGLE \([^\n]*\)|GL_RENDERER\W+[^\n]+|\((?:NVK|RADV) [A-Z0-9_]+\)|"
                         r"(?:NVIDIA GeForce|GeForce RTX|AMD Radeon|Radeon \d+M|SwiftShader|llvmpipe)[^\n,)]*)")
SELECTION_TAGS = {"GraphicsEnvironment", "libEGL", "vulkan", "GpuStats", "GraphicsEnv", "ANGLE-Selection"}
SELECTION = re.compile(r"(Updatable driver package search path[^\n]*|updatable (?:production|prerelease) driver[^\n]*|"
                       r"org\.openbook\.nvk[^\n]*|[Aa]ngle[^\n]*(?:driver|choice|select)[^\n]*)")
# Failures in the app's own processes, and rendering errors it logs (a shader that didn't compile or is missing,
# a GL/Vulkan error). Either invalidates a run: a timing from a broken render isn't a speed.
APP_ERR = re.compile(r"FATAL EXCEPTION|Fatal signal|DEVICE_LOST|VK_ERROR_OUT_OF_DEVICE_MEMORY|GL_OUT_OF_MEMORY|"
                     r"[Cc]ontext lost|CONTEXT_LOST|GPU hang")
RENDER_ERR = re.compile(r"shader is missing|shader.*(compil|link)\w* (error|fail)|(compile|link) (error|fail)|"
                        r"GL_INVALID_(OPERATION|VALUE|ENUM|FRAMEBUFFER_OPERATION)|VK_ERROR_\w+|fallback to solid", re.I)
LINE = re.compile(r"^\S+ \S+\s+(?:\S+\s+)?(\d+)\s+\d+ ([VDIWEFA]) ([^:]*?)\s*: (.*)$")


def app_logcat(text, pkg):
    """Lines from PKG's processes (pids from ActivityManager's 'Start proc PID:PKG', child processes such as a
    browser's GPU process included): renderer identification, and separately driver selection/loading."""
    if not text:
        return None
    pids = set(re.findall(rf"Start proc (\d+):{re.escape(pkg)}[/:]", text))
    lines, renderer, selection = [], [], []
    for ln in text.splitlines():
        m = LINE.match(ln)
        if not m or m.group(1) not in pids:
            continue
        lines.append(ln)
        tag, msg = m.group(3), m.group(4)
        if tag in SELECTION_TAGS:
            for x in SELECTION.findall(msg) or [msg]:
                if x not in selection:
                    selection.append(x.strip())
            continue
        for x in RENDERER_ID.findall(msg):
            if x.strip() not in renderer:
                renderer.append(x.strip())
        for x in SELECTION.findall(msg):
            if x.strip() not in selection:
                selection.append(x.strip())
    blob = "\n".join(renderer)
    nv = bool(re.search(r"NVK|NVIDIA|GeForce", blob))
    amd = bool(re.search(r"RADV|AMD|Radeon", blob))
    seen = "mixed" if nv and amd else "nvidia" if nv else "radeon" if amd else "other" if renderer else None
    bad = [ln for ln in lines if APP_ERR.search(ln)]
    render = [ln for ln in lines if RENDER_ERR.search(ln)]
    p = re.escape(pkg)
    crash = [ln for ln in text.splitlines()
             if re.search(rf"ANR in {p}\b|Process {p}(:\S+)? \(pid \d+\) has died|>>> {p}\b|"
                          rf"am_(anr|crash)\W.*\b{p}\b", ln)]
    return {"pids": sorted(pids), "lines": len(lines), "renderer_facts": renderer[:20],
            "selection_facts": selection[:20], "gpu_seen": seen, "errors": bad[:20], "render_errors": render[:20],
            "crash_lines": crash[:20]}


KERNEL_ERR = re.compile(r"NVRM *: *Xid|NVRM *: .*(error|failed)|fallen off the bus|GSP.*(error|timeout|fail)|"
                        r"amdgpu.*(ring .*timeout|GPU reset|gpu reset|fault)|nouveau.*(fault|timeout)", re.I)


def kernel_errors(text):
    if text is None:
        return None
    return [ln for ln in text.splitlines() if KERNEL_ERR.search(ln)][:50]


def dgpu(text):
    if not text:
        return None
    h = re.search(r"dgpu-report: health (.*)", text)
    return kvs(h.group(1)) if h else {"unavailable": text.strip().splitlines()[-1] if text.strip() else "empty"}


def dropbox_new(before, after):
    if before is None or after is None:
        return None
    rx = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (\S+) \(", re.M)
    old = set(rx.findall(before))
    return sorted({tag for ts, tag in rx.findall(after) if (ts, tag) not in old})


def routing(text, pkg):
    """Android's choice from the routing inputs (GraphicsEnvironment.chooseDriverInternal as AppDriver.kt ports it);
    eligibility (not privileged, not a never-updated built-in app) is not decided here."""
    if not text:
        return None
    st = dict(re.findall(r"^setting (\S+?)=(.*)$", text, re.M))
    pr = dict(re.findall(r"^prop \[(\S+)\]: \[(.*)\]$", text, re.M))
    L = lambda k: [] if st.get(k) in (None, "null", "") else st[k].split(",")
    offered = bool(pr.get("ro.gfx.driver.0"))
    all_apps = st.get("updatable_driver_all_apps")
    if not offered:
        why = ("radeon", "no driver package offered (ro.gfx.driver.0 unset)")
    elif all_apps == "3":
        why = ("radeon", "NVIDIA off for all apps (updatable_driver_all_apps=3)")
    elif all_apps == "1":
        why = ("nvidia", "every app (updatable_driver_all_apps=1)")
    elif pkg in L("updatable_driver_production_opt_out_apps"):
        why = ("radeon", "owner chose Radeon (opt-out list)")
    elif pkg in L("updatable_driver_prerelease_opt_in_apps"):
        why = ("radeon", "prerelease list (no prerelease driver offered)")
    elif pkg in L("updatable_driver_production_opt_in_apps"):
        why = ("nvidia", "owner chose NVIDIA (opt-in list)")
    elif L("updatable_driver_production_allowlist")[:1] == ["*"] or pkg in L("updatable_driver_production_allowlist"):
        why = ("radeon", "deny-listed") if pkg in L("updatable_driver_production_denylist") else ("nvidia", "game (allow-list)")
    else:
        why = ("radeon", "not on the allow-list")
    return {"expected": why[0], "why": why[1], "offered": pr.get("ro.gfx.driver.0") or None,
            "nvk_offer": pr.get("vendor.openbook.nvk.offer"), "dgpu_ready": pr.get("vendor.openbook.dgpu.ready"),
            "build": pr.get("ro.build.fingerprint"), "kernel": (re.search(r"^kernel (.*)$", text, re.M) or [None, None])[1]}


def surface(sf, layer):
    """The primary layer's sourceCrop (the buffer area it shows: render size unless the app scales) and displayFrame
    (its size on the display), from SurfaceFlinger's output-layer dump."""
    if not sf or not layer:
        return None
    i = sf.find(f"({layer})")
    if i < 0:
        return None
    m = re.search(r"displayFrame=\[([-\d]+) ([-\d]+) ([-\d]+) ([-\d]+)\] sourceCrop=\[([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)\]",
                  sf[i:i + 4000])
    if not m:
        return None
    l, t, r, b = (int(x) for x in m.groups()[:4])
    cl, ct, cr, cb = (float(x) for x in m.groups()[4:])
    return {"display_frame": f"{r - l}x{b - t}", "source_crop": f"{round(cr - cl)}x{round(cb - ct)}"}


def window(text):
    m = re.search(r"\bframe=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", text or "")
    return f"{int(m.group(3)) - int(m.group(1))}x{int(m.group(4)) - int(m.group(2))}" if m else None


def conditions(text):
    if not text:
        return None
    g = lambda rx: (re.search(rx, text, re.M) or [None, None])[1]
    return {"ac": g(r"^battery AC powered: (\S+)"), "level": num(g(r"^battery level: (\S+)")),
            "charge_uAh": num(g(r"^battery Charge counter: (\S+)")), "voltage_mV": num(g(r"^battery voltage: (\S+)")),
            "brightness": g(r"^brightness=(\S+)"), "epp": g(r"epp=(\S+)"), "platform_profile": g(r"^platform_profile=(\S+)"),
            "wm": g(r"^wm (.*)$"), "display": [ln[8:] for ln in text.splitlines() if ln.startswith("display ")][:4]}


def meta(text):
    m = {}
    for ln in (text or "").splitlines():
        if ln.startswith("label="):
            m["label"] = ln[6:]
        else:
            m.update(kvs(ln))
    return m


def timestats_check(ts, layer, prim, m):
    """SurfaceFlinger's own count for the scored layer, cleared before the interval and dumped after it, must agree
    with the sampled frames: at least as many, and no more than the sampled rate explains over its longer span."""
    rec = [t for t in (ts or []) if t["layer"] == layer]
    if not rec:
        return ["no TimeStats record of the scored layer to cross-check"]
    t0, t1 = num(m.get("ts_clear_up_s")), num(m.get("ts_dump_up_s"))
    if t0 is None or t1 is None or t1 <= t0:
        return ["TimeStats interval not recorded"]
    total, n, fps = rec[0]["totalFrames"] or 0, prim["frames"], prim.get("fps") or 0
    if total < n * 0.98 - 2:
        return [f"TimeStats counted {total:.0f} frames, fewer than the {n} sampled"]
    most = fps * (t1 - t0) * 1.1 + 5
    if total > most:
        return [f"TimeStats counted {total:.0f} frames in {t1 - t0:.1f} s; the sampled {fps} fps explains at most "
                f"{most:.0f}: frames may be missing"]
    return []


# The app's own frame rate, from what it logs (workloads that render past the display's refresh, which presented
# frames can't show). Only report windows that provably lie wholly inside the scored interval count; warm-up never
# does.
#   vulkanExample (OpenBook's patched Willems samples): "fps N frames F ms M" once a second, logged at the end of
#     the M ms it measured; aggregated as sum(F) / sum(M).
#   glmark2: "[scene] ...duration=D... FPS: N FrameTime: T ms" per scene. Not aggregated: D is the requested
#     length, a scene runs until it has at least D seconds and is logged after teardown, so the line proves neither
#     its start nor its real length. Its reports are kept as they are (glmark2_reports).
# This is the app loop's throughput, not GPU execution time.
EPOCH_LINE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s+\d+\s+\d+\s+[VDIWEFA]\s+(\S+?)\s*:\s*(.*)$")
VKEX_FPS = re.compile(r"\bfps (\d+) frames (\d+) ms ([\d.]+)")
GLMARK2_REPORT = re.compile(r"\[([\w-]+)\].*\bFPS: (\d+)(?: FrameTime: ([\d.]+) ms)?")


def app_throughput(text, begin, end):
    if not text or begin is None or end is None:
        return None
    windows = []   # (frames, seconds)
    for ln in text.splitlines():
        m = EPOCH_LINE.match(ln)
        if not m or m.group(2) != "vulkanExample":
            continue
        f = VKEX_FPS.search(m.group(3))
        if not f:
            continue
        t, frames, secs = float(m.group(1)), int(f.group(2)), float(f.group(3)) / 1000
        if secs > 0 and t - secs >= begin and t <= end:
            windows.append((frames, secs))
    if not windows:
        return None
    rates = [fr / s for fr, s in windows]
    total_s = sum(s for _, s in windows)
    return {"source": "vulkanExample", "fps": round(sum(fr for fr, _ in windows) / total_s, 1),
            "windows": len(windows), "seconds": round(total_s, 1),
            "min": round(min(rates), 1), "max": round(max(rates), 1)}


def glmark2_reports(text):
    """glmark2's per-scene reports as logged (epoch time, scene, FPS, frame time), unaggregated: see above."""
    out = []
    for ln in (text or "").splitlines():
        m = EPOCH_LINE.match(ln)
        if m and m.group(2) == "glmark2" and (g := GLMARK2_REPORT.search(m.group(3))):
            out.append({"logged": float(m.group(1)), "scene": g.group(1), "fps": int(g.group(2)),
                        "frame_ms": float(g.group(3)) if g.group(3) else None})
    return out or None


def summarise(d):
    m = meta(read(d, "meta.txt"))
    pkg = m.get("pkg", "")
    meas, warm = parse_samples(read(d, "measure.txt")), parse_samples(read(d, "warmup.txt"))
    p = pacing(meas)
    ts = timestats(read(d, "timestats.txt"), pkg)
    log = app_logcat(read(d, "logcat.txt"), pkg)
    rt = routing(read(d, "routing-before.txt"), pkg)
    asked = m.get("gpu")
    want = asked if asked in ("radeon", "nvidia") else (rt or {}).get("expected")
    prim = p["layers"].get(p["primary"]) if p["primary"] else None
    why = []
    for k in ("skipped", "invalid"):
        if k in m:
            why.append(f"{k}: {m[k]}")
    if meas["abort"] or warm["abort"]:
        why.append(f"aborted: {meas['abort'] or warm['abort']}")
    if not meas["end"]:
        why.append("scored interval did not finish")
    for ph, parsed in (("warm-up", warm), ("measurement", meas)):
        if parsed["malformed"]:
            why.append(f"{len(parsed['malformed'])} malformed sampler line(s) in {ph}: {parsed['malformed'][0][:80]}")
    for ph, parsed in (("warm-up", warm), ("measurement", meas)):
        for key, what in (("kerr", "kernel GPU error"), ("apperr", "app error")):
            k0, k1 = num((parsed["begin"] or {}).get(key)), num((parsed["end"] or {}).get(key))
            if k0 is not None and k1 is not None and k1 > k0:
                why.append(f"{k1 - k0:.0f} {what} line(s) during {ph}")
    for key, what in (("errors", "app error"), ("crash_lines", "crash/ANR"), ("render_errors", "rendering error")):
        hits = (log or {}).get(key) or []
        if hits:
            why.append(f"{what} logged ({len(hits)}): {hits[0][-160:]}")
    db, da = dgpu(read(d, "dgpu-before.txt")) or {}, dgpu(read(d, "dgpu-after.txt")) or {}
    if num(db.get("xid")) is not None and num(da.get("xid")) is not None and num(da["xid"]) > num(db["xid"]):
        why.append(f"{num(da['xid']) - num(db['xid']):.0f} new Xid(s) between the dGPU reports")
    if prim is None or not prim.get("frames"):
        why.append("no presented frames sampled")
    else:
        if prim["coverage_gaps"]:
            why.append(f"{prim['coverage_gaps']} sampling gap(s): frames may be missing")
        if prim.get("covered") is None or prim["covered"] < 0.9:
            why.append(f"presented frames cover {prim.get('covered')} of the scored interval (< 0.9)")
        why += timestats_check(ts, p["primary"], prim, m)
    seen = (log or {}).get("gpu_seen")
    if seen is None:
        why.append("renderer not verified: no GL renderer or Vulkan device line from the app's processes"
                   + (" (driver selection only)" if (log or {}).get("selection_facts") else ""))
    elif want and seen != want:
        why.append(f"renderer {seen}, expected {want}")
    if m.get("exit") not in (None, "0"):
        why.append(f"exit {m.get('exit')}")
    s = {
        "run": os.path.basename(os.path.normpath(d)), "label": m.get("label"), "pkg": pkg, "gpu_asked": asked,
        "gpu_expected": want, "gpu_seen": seen, "valid": not why, "invalid_because": why,
        "tool": {k: m.get(k) for k in ("tool_commit", "tool_dirty", "gpu_diag_sh", "device_sh", "choice_sh")},
        "routing": rt, "start": am_start(read(d, "am-start.txt")),
        "app_fps": app_throughput(read(d, "app-logcat.txt"), num((meas["begin"] or {}).get("epoch")),
                                  num((meas["end"] or {}).get("epoch"))),
        "glmark2_reports": glmark2_reports(read(d, "app-logcat.txt")),
        "first_frame_s_after_displayed": first_frame(warm), "warmup_hitches_over_100ms": hitches(warm),
        "pacing": p, "surface": surface(read(d, "surfaceflinger.txt"), p["primary"]),
        "window": window(read(d, "window.txt")), "timestats": ts,
        "load": loads(meas, pkg), "renderer": log,
        "kernel_gpu_errors": kernel_errors(read(d, "kernel.txt")),
        "dgpu_before": dgpu(read(d, "dgpu-before.txt")), "dgpu_after": dgpu(read(d, "dgpu-after.txt")),
        "new_dropbox_entries": dropbox_new(read(d, "dropbox-before.txt"), read(d, "dropbox-after.txt")),
        "conditions_before": conditions(read(d, "conditions-before.txt")),
        "conditions_after": conditions(read(d, "conditions-after.txt")),
        "apk": (read(d, "apk.txt") or "").split(),
    }
    cb, ca = s["conditions_before"] or {}, s["conditions_after"] or {}
    if m.get("battery") == "1" and cb.get("charge_uAh") and ca.get("charge_uAh") and cb.get("voltage_mV"):
        dq = (cb["charge_uAh"] - ca["charge_uAh"]) / 1e6 * 3600  # coulombs
        v = (cb["voltage_mV"] + (ca.get("voltage_mV") or cb["voltage_mV"])) / 2000
        s["battery_energy_j_charge_counter"] = round(dq * v, 1)
    return s


# ------------------------------------------------------------------------------------------- the table
METRICS = [
    ("presented FPS", lambda s: (s["pacing"]["layers"].get(s["pacing"]["primary"]) or {}).get("fps")),
    ("app FPS", lambda s: (s.get("app_fps") or {}).get("fps")),
    ("p99 ms", lambda s: ((s["pacing"]["layers"].get(s["pacing"]["primary"]) or {}).get("frame_ms") or {}).get("p99")),
    ("missed vsync", lambda s: (s["pacing"]["layers"].get(s["pacing"]["primary"]) or {}).get("missed_vsync")),
    ("hitches", lambda s: (s["pacing"]["layers"].get(s["pacing"]["primary"]) or {}).get("over_cadence")),
    ("start ms", lambda s: (s["start"] or {}).get("total_ms")),
    ("app CPU %", lambda s: ((s["load"] or {}).get("cpu_pct_of_one_core") or {}).get("app")),
    ("GPU busy %", lambda s: ((s["load"] or {}).get("amdgpu_busy_pct") or {}).get("median")),
]


def fmt(v):
    return "–" if v is None else (f"{v:.1f}" if isinstance(v, float) else str(v))


def table(runs):
    groups = {}
    for s in runs:
        if s["valid"]:
            groups.setdefault((s["label"] or s["pkg"], s["gpu_seen"]), []).append(s)
    out = ["| workload | GPU | runs | " + " | ".join(f"{n} (median, min–max; each)" for n, _ in METRICS) + " |",
           "|---|---|---|" + "---|" * len(METRICS)]
    for (label, gpu), rs in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        cells = []
        for _, f in METRICS:
            vals = [f(s) for s in rs]
            got = [v for v in vals if v is not None]
            if got:
                cells.append(f"{fmt(statistics.median(got))}, {fmt(min(got))}–{fmt(max(got))}; "
                             + " / ".join(fmt(v) for v in vals))
            else:
                cells.append("–")
        out.append(f"| {label} | {gpu} | {len(rs)} | " + " | ".join(cells) + " |")
    bad = [s for s in runs if not s["valid"]]
    if bad:
        out += ["", "Not scored:"] + [f"- {s['run']} ({s['label'] or s['pkg']}): {'; '.join(s['invalid_because'])}"
                                       for s in bad]
    return "\n".join(out)


def main(argv):
    j = None
    if argv[:1] == ["--json"]:
        j, argv = argv[1], argv[2:]
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    runs = []
    for d in argv:
        s = summarise(d)
        with open(os.path.join(d, "run.json"), "w") as f:
            json.dump(s, f, indent=1)
        runs.append(s)
    if j:
        with open(j, "w") as f:
            json.dump(runs, f, indent=1)
    print(table(runs))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
