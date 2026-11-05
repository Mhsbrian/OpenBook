#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Per-app performance of an OpenBook device over adb (ANAL-378, docs/app-performance.md). Run it through
scripts/perf/app-perf.sh, which holds the G14 lock and connects; this file does the work and the parsing.

  state OUT              the device: build, slot, kernel, power source, platform profile, amd-pstate and the EPP of
                         every policy, core ranking, temperatures, memory, ART and native-bridge properties
  inventory OUT [PKG..]  per app (default: every third-party app): version, installer, the ABI it was installed with
                         and the ABIs its installed APKs carry, so whether its native code runs translated; a framework
                         hint from its library names; ART's compiler filter and reason for each of its dex files
  start OUT PKG          process-cold and warm launch times, every sample kept with its spread, and the EPP and top
                         frequency seen while each launch ran
  cpu OUT PKG            where the app's CPU time goes from a process-cold launch on: translated ARM code, the
                         translator (compiling, interpreting, its runtime), Java (ART), the app's x86_64 code, graphics,
                         the kernel, the rest of the system, unknown. --translator adds Digitalis's own profile: its
                         counters (berberis.stats) and the translated samples by tier and by library offset
                         (berberis.profiling's perf map)
  dexopt OUT PKG         compile one package with a chosen filter (pm compile), its state recorded before and after
  table DIR...           a Markdown table from these runs
  restore                put back a power setting that a killed run left changed (its journal)
Frames come from scripts/gpu-diag.sh run (SurfaceFlinger's per-layer present times), not from this tool.

Every command except table checks first that the laptop is idle (the gpu-diag gate: no input for --idle-min minutes,
display awake, no keyguard, no audio) and that the app isn't running, so an owner's session is never touched; input at
any later point stops the run (exit 3). OUT must not exist; each run writes run.json and its raw outputs there.
"""
import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time

R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = "/data/local/tmp/openbook-app-perf"
SEP = "#|#"  # simpleperf's CSV separator here: C++ symbols contain commas
INVALID, FAILED, RESTORE_FAILED = 3, 1, 4


class Invalid(Exception):
    """The run can't count: the laptop isn't idle, someone used it, or the app was already running."""


class Fail(Exception):
    pass


# ------------------------------------------------------------------------------------- parsers (tests/perf/)
def kv_tokens(line):
    """'a=1 b=x y' -> {'a': '1', 'b': 'x'}"""
    return dict(t.split("=", 1) for t in line.split() if "=" in t)


def num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def stats(values):
    """Median, min, max and spread of the numbers among values (None is a sample with no time)."""
    v = sorted(x for x in values if isinstance(x, (int, float)))
    if not v:
        return {"n": 0, "missing": len(values)}
    return {"n": len(v), "missing": len(values) - len(v), "median": statistics.median(v), "min": v[0],
            "max": v[-1], "spread": v[-1] - v[0]}


def parse_am_start(text):
    """am start -W output -> status, LaunchState, TotalTime and WaitTime (ms), activity, warnings."""
    r = {"status": None, "launch_state": None, "total_ms": None, "wait_ms": None, "activity": None,
         "warnings": [], "error": None}
    for line in text.splitlines():
        s = line.strip()
        k, _, v = s.partition(": ")
        if k == "Status":
            r["status"] = v
        elif k == "LaunchState":
            r["launch_state"] = v
        elif k == "TotalTime":
            r["total_ms"] = num(v)
        elif k == "WaitTime":
            r["wait_ms"] = num(v)
        elif k == "Activity":
            r["activity"] = v
        elif s.startswith("Warning:"):
            r["warnings"].append(s)
        elif s.startswith(("Error", "Exception", "java.lang.")):
            r["error"] = s
    r["ok"] = r["status"] == "ok" and r["total_ms"] is not None and r["error"] is None
    return r


def parse_epp_counts(v):
    """'16:performance,8:balance_power' -> {'performance': 16, 'balance_power': 8}; 'na' -> {}"""
    out = {}
    for part in (v or "").split(","):
        n, _, name = part.partition(":")
        if name and n.isdigit():
            out[name] = int(n)
    return out


def parse_launch(text):
    """device.sh launch output -> the am start result, the sampler's samples, what EPP values and top frequency
    were seen while it ran."""
    am, samples, t0, t1, rc = [], [], None, None, None
    for line in text.splitlines():
        if line.startswith("@s "):
            p, kv = line.split(), kv_tokens(line)
            samples.append({"t_cs": num(p[1]) if len(p) > 1 else None, "epp": parse_epp_counts(kv.get("epp")),
                            "maxfreq_khz": num(kv.get("maxfreq_khz"))})
        elif line.startswith("@t0 "):
            t0 = num(line.split()[1])
        elif line.startswith("@t1 "):
            t1, rc = num(line.split()[1]), num(kv_tokens(line).get("rc"))
        else:
            am.append(line)
    freqs = [s["maxfreq_khz"] for s in samples if s["maxfreq_khz"]]
    return {"am": parse_am_start("\n".join(am)), "t0_cs": t0, "t1_cs": t1, "rc": rc, "samples": samples,
            "epp_seen": sorted({k for s in samples for k in s["epp"]}),
            "maxfreq_khz": max(freqs) if freqs else None}


def parse_dumpsys_package(text, pkg):
    """The 'Package [PKG]' block of dumpsys package PKG (the first; an updated system app has a second, hidden one)."""
    r, on = {}, False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("Package ["):
            if on:
                break
            on = s.startswith(f"Package [{pkg}]")
            continue
        if not on:
            continue
        if line and not line[0].isspace():
            break
        k, eq, v = s.partition("=")
        if not eq:
            continue
        if k == "versionCode":
            r["versionCode"] = num(kv_tokens(s).get("versionCode"))
            r["targetSdk"] = num(kv_tokens(s).get("targetSdk"))
        elif k in ("versionName", "primaryCpuAbi", "secondaryCpuAbi", "cpuAbiOverride", "codePath",
                   "extractNativeLibs", "installerPackageName", "initiatingPackageName", "timeStamp",
                   "lastUpdateTime", "loadingProgress", "splits", "pageSizeCompat") and k not in r:
            r[k] = None if v == "null" else v
    return r


def parse_apk_listing(text):
    """device.sh apk output -> {abis: {abi: [library names]}, dex: number of dex files}"""
    abis, dex = {}, 0
    for line in text.splitlines():
        name = line.strip()
        m = re.fullmatch(r"lib/([^/]+)/([^/]+\.so)", name)
        if m:
            abis.setdefault(m.group(1), set()).add(m.group(2))
        elif re.fullmatch(r"classes\d*\.dex", name):
            dex += 1
    return {"abis": {k: sorted(v) for k, v in sorted(abis.items())}, "dex": dex}


# Library names that point to the framework an app is built with. A hint, never proof: an app may carry a
# framework's library without running its UI on it.
FRAMEWORKS = [
    ("Flutter", ["libflutter.so"]),
    ("Unity", ["libunity.so", "libil2cpp.so"]),
    ("Unreal", ["libUE4.so", "libUnreal.so"]),
    ("React Native", ["libreactnativejni.so", "libhermes.so", "libhermes_executor.so", "libjsc.so"]),
    (".NET", ["libmonosgen-2.0.so", "libmonodroid.so"]),
    ("Godot", ["libgodot_android.so"]),
    ("Cocos2d-x", ["libcocos2dcpp.so", "libcocos2djs.so", "libcocos.so"]),
    ("Qt", ["libQt5Core*.so", "libQt6Core*.so"]),
    ("Chromium", ["libchrome.so", "libmonochrome.so", "libmonochrome_64.so"]),
    ("Gecko", ["libxul.so"]),
]


def framework_hints(libs):
    return [name for name, pats in FRAMEWORKS if any(fnmatch.fnmatchcase(l, p) for l in libs for p in pats)]


def native_code(primary_abi, abis):
    """How the app's own native code runs. Its Java and Kotlin always run as x86_64 through ART: an arm64 app's dex
    is compiled for x86_64 (ro.dalvik.vm.isa.arm64=x86_64), so only its .so libraries go through the bridge."""
    if primary_abi in (None, "", "null"):
        return "none" if not abis else "unknown"
    if primary_abi == "x86_64":
        return "x86_64"
    if primary_abi.startswith("arm"):
        return f"translated ({primary_abi})"
    return f"unknown ({primary_abi})"


def parse_art_dump(text):
    """pm art dump PKG -> the primary dex files' status per ISA: [{path, isa, status, reason, primary_abi}]"""
    files, path = [], None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("path: "):
            path = s[6:]
        elif s == "known secondary dex files:":
            path = None
        else:
            m = re.match(r"(\S+): \[status=([^\]]*)\] \[reason=([^\]]*)\](.*)", s)
            if m and path:
                files.append({"path": path, "isa": m.group(1), "status": m.group(2), "reason": m.group(3),
                              "primary_abi": "[primary-abi]" in m.group(4)})
    return files


def dexopt_summary(files):
    """'speed-profile/install' for the primary-ABI status of base.apk (others, if different, after it)."""
    seen = []
    for f in files:
        if f["primary_abi"]:
            v = f"{f['status']}/{f['reason']}"
            if v not in seen:
                seen.append(v)
    return ", ".join(seen) if seen else "na"


def parse_simpleperf_csv(text):
    """simpleperf report --csv --csv-separator SEP -> (header facts, rows as dicts keyed by the column names)."""
    head, rows, cols = {}, [], None
    for line in text.splitlines():
        if cols is None:
            if SEP in line:
                cols = line.split(SEP)
            else:
                k, _, v = line.partition(": ")
                if v:
                    head[k.strip()] = v.strip()
            continue
        f = line.split(SEP)
        if len(f) == len(cols):
            rows.append(dict(zip(cols, f)))
    return head, rows


def parse_maps(text):
    """device.sh maps output -> {pid: [(start, end, perms, name)]}"""
    out, pid = {}, None
    for line in text.splitlines():
        if line.startswith("@pid "):
            pid = line.split()[1]
            out.setdefault(pid, [])
            continue
        p = line.split(None, 5)
        if pid is None or len(p) < 5 or "-" not in p[0]:
            continue
        try:
            a, b = (int(x, 16) for x in p[0].split("-"))
        except ValueError:
            continue
        out[pid].append((a, b, p[1], p[5].strip() if len(p) > 5 else ""))
    return out


def region_of(maps, addr):
    """The mapping holding addr. With several snapshots of one process, the latest one that holds it wins."""
    for a, b, _, name in reversed(maps or []):
        if a <= addr < b:
            return name
    return None


# Where a sample's time goes. Samples simpleperf can't place (dso "unknown", symbol "unknown[+ADDR]") are looked up
# in the process's maps: Digitalis (Berberis) runs translated code from a memfd named "exec" that it maps over
# libberberis_exec_region.so's reserved range, and simpleperf doesn't attribute that memfd.
CATEGORIES = ["translated", "translator-helpers", "translator-interpret", "translator-compile", "translator-runtime",
              "bridge-proxies", "java", "app-native", "graphics", "system-native", "kernel", "unknown"]
GROUPS = {
    "arm_code": ["translated", "translator-helpers", "translator-interpret"],
    "translation_overhead": ["translator-compile"],
    "bridge_runtime": ["translator-runtime", "bridge-proxies"],
}
GRAPHICS = re.compile(r"^(vulkan\.|libvulkan|libEGL|libGLES|libgallium|libdrm|libhwui|libgui\.|libui\.|libskia|"
                      r"libvk_swiftshader|libnvk|.*angle.*|.*_dri\.so|libsurfaceflinger|librenderengine)", re.I)


def translator_part(sym):
    if "Interpret" in sym:
        return "translator-interpret"
    if "intrinsics::" in sym:
        return "translator-helpers"
    if re.search(r"ExecuteGuest|RunGeneratedCode|berberis_entry|GuestCall|Syscall|Signal|TranslationCache|"
                 r"GetHostCode|RunGuest|Trampoline", sym):
        return "translator-runtime"
    if re.search(r"Translat|Optimi[sz]|MachineIR|MachineCode|MachineInsn|Assembler|Decoder|SemanticsPlayer|VReg|"
                 r"RegAlloc|FoldInsns|CodePool|Memfd|x86_64::", sym):
        return "translator-compile"
    return "translator-runtime"


def categorize(dso, sym="", region=None):
    if dso == "unknown":
        if not region:
            return "unknown"
        if "memfd:exec" in region or "libberberis_exec_region" in region:
            return "translated"
        if "jit-cache" in region or "dalvik-jit" in region:
            return "java"
        if "swiftshader" in region.lower():
            return "graphics"
        if region.startswith("/") and not region.startswith("/memfd:"):
            return categorize(region, sym)
        return "unknown"
    base = dso.rsplit("/", 1)[-1]
    if dso.startswith("[kernel") or base.endswith(".ko"):
        return "kernel"
    if "memfd:exec" in dso or base.startswith("libberberis_exec_region"):
        return "translated"
    if base.startswith("libberberis_proxy_"):
        return "bridge-proxies"
    if base.startswith(("libberberis", "libndk_translation")):
        return translator_part(sym)
    if (base.startswith("libart") or base.endswith((".oat", ".odex", ".vdex", ".art")) or "JIT" in dso
            or "dalvik-jit" in dso or "jit-cache" in dso):
        return "java"
    if dso.startswith(("/data/app/", "/data/data/", "/data/user/")):
        return "app-native"
    if GRAPHICS.match(base) or "swiftshader" in dso.lower():
        return "graphics"
    if dso.startswith(("/system/", "/system_ext/", "/apex/", "/vendor/", "/odm/", "/product/", "[vdso]")):
        return "system-native"
    return "unknown"


def cpu_attribution(rows, maps):
    """simpleperf rows (Pid, Shared Object, Symbol, EventCount) -> event count and share per category and group,
    and the biggest contributors of the translator and of unknown."""
    tot = {c: 0 for c in CATEGORIES}
    top = {}
    for r in rows:
        n = num(r.get("EventCount")) or 0
        dso, sym = r.get("Shared Object", ""), r.get("Symbol", "")
        region = None
        m = re.fullmatch(r"unknown\[\+([0-9a-fA-F]+)\]", sym)
        if dso == "unknown" and m:
            region = region_of(maps.get(r.get("Pid", "")), int(m.group(1), 16))
        c = categorize(dso, sym, region)
        tot[c] += n
        if c.startswith("translator") or c == "unknown":
            key = (c, region or dso, sym if c != "unknown" else "")
            top[key] = top.get(key, 0) + n
    total = sum(tot.values())
    share = {c: (tot[c] / total if total else None) for c in CATEGORIES}
    groups = {g: (sum(tot[c] for c in cs) / total if total else None) for g, cs in GROUPS.items()}
    biggest = sorted(top.items(), key=lambda kv: -kv[1])[:20]
    return {"event_total": total, "events": tot, "share": share, "groups": groups,
            "top_translator_and_unknown": [{"category": k[0], "where": k[1], "symbol": k[2], "events": v,
                                            "share": v / total if total else None} for k, v in biggest]}


# Digitalis's translator profile (ANAL-383). With `berberis.stats` set, the translator keeps its counters in one
# self-describing block and logs the block's address when the process starts; root reads it from /proc/PID/mem (layout
# OBSTAT2: magic, count, names size, enabled, owner pid, baseline valid, the counters, the baseline, then their names).
# `berberis.profiling` writes a perf map per process naming each translated region's host code range, tier, guest
# address and size, and, for code in a mapped file only, its offset in the file
# ("<last 16 chars of the path>_<tier>_0x<guest>+<size>[@0x<offset>]").
STATS_BLOCK = re.compile(r"berberis\.stats: on; block at 0x([0-9a-fA-F]+) \(layout OBSTAT2")
STATS_HEADER = 48  # bytes: magic, count, names size, enabled, owner pid, baseline valid
PERF_MAP_SYM = re.compile(r"^(?P<lib>.*?)(?P<tier>lite_range|lite|heavy)_0x(?P<guest>[0-9a-fA-F]+)\+(?P<gsize>\d+)"
                          r"(?:@0x(?P<off>[0-9a-fA-F]+))?$")


def parse_stats_addresses(text):
    """logcat lines (-v brief or threadtime) -> {pid: block address} from the line each process logs at start."""
    out = {}
    for line in text.splitlines():
        m = STATS_BLOCK.search(line)
        if not m:
            continue
        pm = re.match(r"^\w/berberis\(\s*(\d+)\)", line) or re.match(r"^\S+ \S+\s+(\d+)\s+\d+ \w berberis", line)
        if pm:
            out[pm.group(1)] = int(m.group(1), 16)
    return out


# Where the block lives: a static of the translator library, in its writable data (.data, then the anonymous .bss
# after it). A process only logs the block's address at its start, and Digitalis logs a debug line every 100
# translations, so on a device the 256 KiB main log has usually rotated that line out by the end of a recording
# (ANAL-384, 2026-11-04: Chromium's three lines were gone within 20 s). A forked process (an app zygote's child)
# logs none at all. So the block is looked for in the process's own memory too.
BLOCK_LIB = "libberberis_arm64.so"
BLOCK_SCAN_MAX = 1 << 20  # bytes of that library's writable mappings read per process, at most


def block_scan_ranges(maps_text, lib=BLOCK_LIB):
    """/proc/PID/maps -> [(start, end)] of LIB's writable mappings and the anonymous .bss right after them."""
    out, after_lib = [], False
    for line in maps_text.splitlines():
        f = line.split()
        if len(f) < 5 or "-" not in f[0]:
            after_lib = False
            continue
        try:
            lo, hi = (int(x, 16) for x in f[0].split("-", 1))
        except ValueError:
            after_lib = False
            continue
        path = " ".join(f[5:])
        is_lib = path == lib or path.endswith("/" + lib)
        if "w" in f[1] and (is_lib or (after_lib and path in ("", "[anon:.bss]"))):
            out.append((lo, hi))
        after_lib = is_lib or (after_lib and path in ("", "[anon:.bss]"))
    return out


def find_stats_block(data, base):
    """The address of the first 8-byte-aligned OBSTAT2 header with a plausible size in DATA (read from BASE), or
    None."""
    i = data.find(b"OBSTAT2\0")
    while i != -1:
        if (base + i) % 8 == 0 and len(data) - i >= STATS_HEADER:
            try:
                parse_stats_header(data[i:i + STATS_HEADER].hex())
                return base + i
            except ValueError:
                pass
        i = data.find(b"OBSTAT2\0", i + 1)
    return None


def parse_stats_header(hexdump):
    """xxd -p of the block's first 48 bytes -> {count, names_size, enabled, owner_pid, baseline_valid}. ValueError if
    it isn't an OBSTAT2 block (wrong address, or an image without the patch)."""
    b = bytes.fromhex("".join(hexdump.split()))
    if len(b) < STATS_HEADER or b[:8] != b"OBSTAT2\0":
        raise ValueError("no OBSTAT2 block at that address")
    w = [int.from_bytes(b[i:i + 8], "little") for i in range(8, STATS_HEADER, 8)]
    h = dict(zip(("count", "names_size", "enabled", "owner_pid", "baseline_valid"), w))
    if not 0 < h["count"] <= 256 or not 0 < h["names_size"] <= 4096:
        raise ValueError(f"implausible block header (count {h['count']}, names {h['names_size']})")
    return h


def stats_body_size(h):
    return 2 * h["count"] * 8 + h["names_size"]


def parse_stats_body(hexdump, h):
    """xxd -p of the counters, baseline and names -> ({name: value}, {name: baseline value})."""
    b = bytes.fromhex("".join(hexdump.split()))
    count, size = h["count"], stats_body_size(h)
    if len(b) < size:
        raise ValueError(f"block cut short ({len(b)} of {size} bytes)")
    names = b[2 * count * 8:size].split(b"\0", 1)[0].decode("ascii", "replace").split(" ")
    if len(names) != count:
        raise ValueError(f"{len(names)} names for {count} counters")
    word = lambda i: int.from_bytes(b[i * 8:i * 8 + 8], "little")
    return ({n: word(i) for i, n in enumerate(names)}, {n: word(count + i) for i, n in enumerate(names)})


def stats_origin(pid, h, counters, baseline):
    """Whose counts these are. A process that started the translator owns them from its start; a fork() child owns
    them from its fork, with what it inherited as the baseline; a raw-clone child (a guest's fork) still shows its
    parent as owner, and its totals include the parent's counts up to the fork."""
    owner = str(h["owner_pid"])
    if owner == str(pid) and not h["baseline_valid"]:
        return {"counts_from": "process start"}
    if owner == str(pid):
        return {"counts_from": "fork from its parent; since_fork = counters - baseline",
                "since_fork": {k: counters[k] - baseline.get(k, 0) for k in counters}}
    return {"counts_from": f"inherited from pid {owner} with no baseline: the totals include that process's counts "
                           "up to the fork (a raw clone runs no fork handler)"}


def parse_translator_stats(text):
    """logcat lines -> {pid: {"t_ms": ms since the translator started, counter: value, ...}}, the latest
    'openbook-stats v1' line per pid (a program's last line, logged when it ends: exit(), a return from main or
    _exit(), patch 7; patch 6 logged it only on _exit()). Lines that aren't a whole record are skipped."""
    out = {}
    for line in text.splitlines():
        i = line.find("openbook-stats v1 ")
        if i < 0:
            continue
        kv = {}
        for tok in line[i + len("openbook-stats v1 "):].split():
            k, eq, v = tok.partition("=")
            if not eq or not v.isdigit():
                kv = None
                break
            kv[k] = int(v)
        if not kv or "pid" not in kv or "t_ms" not in kv:
            continue
        pid = str(kv.pop("pid"))
        if pid not in out or kv["t_ms"] >= out[pid]["t_ms"]:
            out[pid] = kv
    return out


def parse_perf_map(text):
    """A Digitalis perf map -> [(start, end, tier, lib_tail, guest, guest_size, offset or None)] in file order (a
    later line for the same host range is newer). Lines it doesn't name as a translated region are skipped."""
    out = []
    for line in text.splitlines():
        p = line.split(None, 2)
        if len(p) != 3:
            continue
        m = PERF_MAP_SYM.match(p[2].strip())
        try:
            start, size = int(p[0], 16), int(p[1], 16)
        except ValueError:
            continue
        if not m or size <= 0:
            continue
        lib = m.group("lib")
        lib = lib[:-1] if lib.endswith("_") else lib
        off = m.group("off")
        out.append((start, start + size, m.group("tier"), lib, int(m.group("guest"), 16), int(m.group("gsize")),
                    int(off, 16) if off is not None else None))
    return out


def perf_map_lookup(entries, addr):
    """The newest perf-map entry whose host range holds addr, or None. Entries come sorted by start with their
    file position (see tier_attribution)."""
    best = None
    lo, hi = 0, len(entries)
    while lo < hi:  # first entry starting after addr
        mid = (lo + hi) // 2
        if entries[mid][0] <= addr:
            lo = mid + 1
        else:
            hi = mid
    for e in reversed(entries[max(0, lo - 64):lo]):  # regions don't overlap much; look back a little
        if e[0] <= addr < e[1] and (best is None or e[-1] > best[-1]):
            best = e
    return best


def file_backed(path):
    """A mapping with a stable identity: a file, not anonymous memory, a memfd or a deleted file."""
    return bool(path) and path.startswith("/") and not path.startswith(("/memfd:", "/dev/")) \
        and not path.endswith("(deleted)")


def tier_attribution(rows, maps, perf_maps):
    """Translated samples by tier and by region. rows: simpleperf rows; maps: parse_maps output; perf_maps:
    {pid: parse_perf_map output}. A translated sample whose host address no perf-map entry covers (the map was
    missing, cut short, or the code isn't a region: trampolines, the exec region's stubs) is 'unattributed'.
    A region of a mapped file is named by the library's full path (from the maps) and its offset, which stay the same
    between launches. Anything else (anonymous memory such as a guest JIT's, a memfd, an unknown address) is named by
    its guest address and size: distinct regions stay distinct, and the name is marked not comparable across
    launches."""
    index = {pid: sorted((e + (n,) for n, e in enumerate(ents)), key=lambda e: e[0])
             for pid, ents in perf_maps.items()}
    by_tier = {t: 0 for t in ("lite", "heavy", "unattributed")}
    regions = {}
    total = 0
    for r in rows:
        n = num(r.get("EventCount")) or 0
        dso, sym, pid = r.get("Shared Object", ""), r.get("Symbol", ""), r.get("Pid", "")
        m = re.fullmatch(r"unknown\[\+([0-9a-fA-F]+)\]", sym)
        if dso != "unknown" or not m:
            continue
        addr = int(m.group(1), 16)
        if categorize(dso, sym, region_of(maps.get(pid), addr)) != "translated":
            continue
        total += n
        e = perf_map_lookup(index.get(pid, []), addr)
        if not e:
            by_tier["unattributed"] += n
            continue
        _, _, tier, lib_tail, guest, gsize, off, _ = e
        tier_key = "heavy" if tier == "heavy" else "lite"
        by_tier[tier_key] += n
        lib = region_of(maps.get(pid), guest)
        stable = off is not None and file_backed(lib)
        if stable:
            where = f"{lib}@0x{off:x}"
        else:  # process-local: keyed by pid too, since another process's address means something else
            where = f"{lib or lib_tail or 'unmapped'} pid {pid} guest 0x{guest:x}+{gsize}"
        key = (where, tier)
        reg = regions.setdefault(key, {"region": where, "tier": tier, "guest_bytes": gsize, "events": 0,
                                       "comparable_across_launches": stable})
        reg["events"] += n
    share = {t: (v / total if total else None) for t, v in by_tier.items()}
    top = sorted(regions.values(), key=lambda x: -x["events"])[:30]
    for x in top:
        x["share_of_translated"] = x["events"] / total if total else None
    return {"translated_events": total, "events_by_tier": by_tier, "share_by_tier": share, "top_regions": top,
            "regions_with_samples": len(regions)}


def parse_power(text):
    """device.sh power output -> {top: {...}, policies: [...], cpus: [...]}"""
    top, policies, cpus = {}, [], []
    for line in text.splitlines():
        if line.startswith("policy "):
            policies.append({"policy": line.split()[1], **kv_tokens(line)})
        elif line.startswith("cpu "):
            cpus.append({"cpu": line.split()[1], **kv_tokens(line)})
        else:
            top.update(kv_tokens(line))
    epp = {}
    for p in policies:
        epp[p.get("epp", "na")] = epp.get(p.get("epp", "na"), 0) + 1
    tiers = {}
    for c in cpus:
        tiers.setdefault(c.get("max_khz", "na"), []).append(c["cpu"])
    return {**top, "policies": policies, "cpus": cpus, "epp_counts": epp, "cpus_by_max_khz": tiers}


# ------------------------------------------------------------------------------------- the device
class Device:
    def __init__(self, serial, adb):
        self.serial, self.adb = serial, adb
        self.rooted = False
        self.busy = None  # set when something the run started on the device couldn't be stopped: its files stay
        self.notes = {}   # what the run did on the device, kept in run.json even when the run fails

    def run(self, *args, timeout=120, check=True):
        try:
            r = subprocess.run([self.adb, "-s", self.serial, *args], capture_output=True, text=True,
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            raise Fail(f"adb {' '.join(args)[:100]}: no answer in {timeout} s")
        if check and r.returncode:
            raise Fail(f"adb {' '.join(args)[:100]}: exit {r.returncode}: {(r.stderr or r.stdout).strip()[-400:]}")
        return r

    def sh(self, cmd, timeout=120, check=True):
        r = self.run("shell", cmd, timeout=timeout, check=False)
        out = r.stdout.replace("\r", "")
        if check and r.returncode:
            raise Fail(f"device: {cmd[:100]}: exit {r.returncode}: {(out + r.stderr).strip()[-400:]}")
        return out, r.returncode

    def reconnect(self):
        for _ in range(15):
            time.sleep(2)
            if ":" in self.serial:
                subprocess.run([self.adb, "connect", self.serial], capture_output=True, timeout=20)
            r = subprocess.run([self.adb, "-s", self.serial, "get-state"], capture_output=True, text=True,
                               timeout=20)
            if r.stdout.strip() == "device":
                return
        raise Fail(f"{self.serial}: adb didn't come back")

    def uid(self):
        return self.sh("id -u", check=False)[0].strip()

    def root(self):
        if self.uid() == "0":
            return
        self.run("root", check=False)
        self.reconnect()
        if self.uid() != "0":
            raise Fail("adbd can't run as root here (a user build?)")
        self.rooted = True

    def unroot(self):
        if self.rooted:
            self.run("unroot", check=False)
            self.reconnect()
            self.rooted = False

    def helper(self, args, timeout=120, check=True):
        return self.sh(f"sh {D}/device.sh {args}", timeout=timeout, check=check)


def q(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


def setup(dev):
    dev.sh(f"mkdir -p {D}")
    dev.run("push", f"{R}/scripts/perf/device.sh", f"{D}/device.sh")
    dev.run("push", f"{R}/scripts/gpu-diag/device.sh", f"{D}/gpu-diag-device.sh")


def cleanup(dev):
    """Remove the run's files and give up root, unless something the run started still runs (dev.busy), or a
    recorder is found writing into the directory, or that can't be checked."""
    if dev.busy:
        return f"skipped: {dev.busy}; {D} kept and adbd left as it is"
    pids = find_recorders(dev)
    if pids is None:
        dev.busy = "can't check for a recorder before removing its directory (adb failed)"
    elif pids:
        dev.busy = f"simpleperf (pid {', '.join(pids)}) is recording into {D}"
    if dev.busy:
        dev.notes.setdefault("recorder", dev.busy)
        return f"skipped: {dev.busy}; {D} kept and adbd left as it is"
    dev.sh(f"rm -rf {D}", check=False)
    dev.unroot()
    return "ok"


def idle_facts(dev):
    out, _ = dev.sh(f"sh {D}/gpu-diag-device.sh idle", check=False)
    kv = {}
    for line in out.splitlines():
        kv.update(kv_tokens(line))
    return kv


def running(dev, pkg):
    return dev.helper(f"pids {q(pkg)}", check=False)[0].strip()


class Gate:
    """gpu-diag's idle gate and its activity token: the run starts only on an idle, awake, unlocked laptop with the app
    not running, and stops at the next check after any input."""

    def __init__(self, dev, idle_min, pkg=None):
        self.dev = dev
        kv = idle_facts(dev)
        reasons = []
        idle = num(kv.get("idle_ms"))
        if idle_min > 0 and (idle is None or idle < idle_min * 60000):
            reasons.append(f"last input {'unknown' if idle is None else f'{idle / 60000:.1f} min'} ago, "
                           f"not {idle_min} min")
        if kv.get("wakefulness") != "Awake":
            reasons.append(f"display {kv.get('wakefulness') or 'unknown'}")
        if kv.get("keyguard_showing") != "false":
            reasons.append(f"keyguard showing={kv.get('keyguard_showing') or 'unknown'}")
        if kv.get("audio_started") != "0":
            reasons.append(f"audio playing ({kv.get('audio_started') or 'unknown'})")
        if pkg and running(dev, pkg):
            reasons.append(f"{pkg} is running (an owner's session is never touched)")
        if reasons:
            raise Invalid("not idle: " + "; ".join(reasons))
        self.token, self.facts = kv.get("user_activity_uptime_ms"), kv

    def check(self, where):
        now = idle_facts(self.dev).get("user_activity_uptime_ms")
        if now != self.token:
            raise Invalid(f"input on the laptop {where} (activity {now}, gate {self.token}); stopped")


EPP_READ = ("for f in /sys/devices/system/cpu/cpufreq/policy*/energy_performance_preference; do "
            "[ -e \"$f\" ] || continue; v=$(cat \"$f\") || { echo \"@err $f\"; continue; }; echo \"@v $v\"; done; "
            "echo @end")


def parse_epp_read(text):
    """EPP_READ's output -> '16:performance,8:balance_power' (sorted by value), or 'na' on a device without EPP.
    A file that can't be read, or output cut short, is an error, never a value."""
    lines = text.splitlines()
    if "@end" not in lines:
        raise Fail(f"reading the EPP: no complete answer ({' '.join(text.split())[-120:]!r})")
    errs = [l[5:] for l in lines if l.startswith("@err ")]
    if errs:
        raise Fail(f"reading the EPP: can't read {', '.join(errs[:3])}")
    counts = {}
    for l in lines:
        if l.startswith("@v "):
            counts[l[3:].strip()] = counts.get(l[3:].strip(), 0) + 1
    return ",".join(f"{counts[k]}:{k}" for k in sorted(counts)) if counts else "na"


def device_identity(dev):
    """A hash of what names this laptop and its installed system: the Android serial number and the boot partition's
    UUID, and the owner's Android ID. Not the network address, which DHCP may give to another device. The raw values
    never leave the device; the hash goes into the power journal only."""
    out, rc = dev.sh("echo \"s=$(getprop ro.serialno)\"; echo \"b=$(getprop ro.boot.boot_part_uuid)\"; "
                     "echo \"a=$(settings get secure android_id)\"; echo @end", check=False)
    kv = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
    vals = [kv.get(k, "").strip() for k in ("s", "b", "a")]
    vals = ["" if v in ("null", "unknown", "0") else v for v in vals]
    if rc or "@end" not in out or sum(1 for v in vals if v) < 2:
        raise Fail("can't identify the device well enough to journal a power change (serial number, boot "
                   "partition UUID, Android ID: need two of three)")
    return hashlib.sha256("|".join(vals).encode()).hexdigest()[:32]


# Power settings, one per run, journalled on the host before the change and put back afterwards (on failure and on
# a signal too), verified by a read-back. Everything here works without the device helper, so `restore` works from a
# fresh invocation after a run has removed its files.
class Power:
    PROFILE = "/sys/firmware/acpi/platform_profile"

    def __init__(self, dev, journal):
        self.dev, self.journal, self.saved = dev, journal, None

    def epp(self):
        out, rc = self.dev.sh(EPP_READ, check=False)
        if rc:
            raise Fail(f"reading the EPP: exit {rc}")
        return parse_epp_read(out)

    def read(self, kind):
        if kind == "platform-profile":
            out, rc = self.dev.sh(f"cat {self.PROFILE}", check=False)
            return out.strip() if rc == 0 else None
        return None  # fixed-performance: Android has no getter

    def write(self, kind, value):
        if kind == "platform-profile":
            self.dev.root()
            self.dev.sh(f"echo {q(value)} > {self.PROFILE}")
            got = self.read(kind)
            if got != value:
                raise Fail(f"platform_profile reads {got!r} after writing {value!r}")
        else:
            out, rc = self.dev.sh(f"cmd power set-fixed-performance-mode-enabled {value} 2>&1", check=False)
            if rc or "Failed" in out:
                raise Fail(f"fixed performance mode {value}: {' '.join(out.split())[-200:]}")

    def apply(self, kind, value):
        ident = device_identity(self.dev)
        if kind == "fixed-performance":
            # Off is what it is before a run (nothing in OpenBook turns it on; Android has no getter), so writing
            # off first changes nothing, and fails when the power HAL can't do the mode (no EPP: a VM).
            self.write(kind, "false")
        if kind == "platform-profile":
            if self.read(kind) is None:
                raise Fail(f"no {self.PROFILE} on this device")
            choices = self.dev.sh(f"cat {self.PROFILE}_choices", check=False)[0].split()
            if value not in choices:
                raise Fail(f"platform profile {value!r} is not one of {choices}")
        before = {"kind": kind, "value": self.read(kind) if kind == "platform-profile" else "false",
                  "epp": self.epp(), "device": ident, "time": utc()}
        with open(self.journal, "w") as f:
            json.dump(before, f)
        self.saved = before
        self.write(kind, value if kind == "platform-profile" else "true")
        return {"before": {k: v for k, v in before.items() if k != "device"}, "set": value,
                "epp_after_set": self.epp(), "read_back": self.read(kind)}

    def restore(self):
        """Put the journalled value back on the device it came from, read it back, then drop the journal. Any
        failure raises Fail and keeps the journal."""
        if not self.saved:
            return None
        kind, value = self.saved.get("kind"), self.saved.get("value")
        if kind not in ("platform-profile", "fixed-performance") or value is None:
            raise Fail(f"the journal {self.journal} isn't one this tool wrote: {self.saved}")
        if not self.saved.get("device"):
            raise Fail("the journal names no device, so it can't be matched to this one")
        here = device_identity(self.dev)
        if here != self.saved["device"]:
            raise Fail("the connected device isn't the one the journal was written for; nothing written")
        self.write(kind, value)
        res = {"kind": kind, "restored": value, "read_back": self.read(kind), "epp": self.epp(),
               "epp_before": self.saved["epp"]}
        if kind == "platform-profile" and res["read_back"] != value:
            raise Fail(f"platform_profile reads {res['read_back']!r} after the restore, {value!r} before the run")
        # With the app gone and the screen on, the HAL is back on its base preference: what it was before the run.
        if kind == "fixed-performance" and res["epp"] != self.saved["epp"]:
            time.sleep(2)
            res["epp"] = self.epp()
            if res["epp"] != self.saved["epp"]:
                raise Fail(f"EPP is {res['epp']} after the restore, {self.saved['epp']} before the run")
        os.remove(self.journal)
        self.saved = None
        return res


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def newdir(path):
    if os.path.exists(path):
        raise Fail(f"{path} exists; each run gets a new directory")
    os.makedirs(path)
    return path


def save(out, name, text):
    with open(os.path.join(out, name), "w") as f:
        f.write(text)


def tool_rev():
    def git(*a):
        r = subprocess.run(["git", "-C", R, *a], capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else "na"
    return {"commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain", "--", "scripts/perf", "scripts/gpu-diag/device.sh"))}


def identity(dev):
    out, _ = dev.sh("getprop ro.build.fingerprint; getprop ro.build.version.incremental; "
                    "getprop ro.boot.openbook.installed; getprop ro.boot.slot_suffix; uname -r", check=False)
    k = (out.splitlines() + [""] * 5)[:5]
    return {"fingerprint": k[0], "build": k[1], "installed": k[2] or "no (live)", "slot": k[3], "kernel": k[4]}


def app_facts(dev, pkg):
    out, _ = dev.sh(f"dumpsys package {q(pkg)}", check=False)
    return parse_dumpsys_package(out, pkg)


def component(dev, pkg, given):
    if given:
        return given
    out, _ = dev.sh(f"cmd package resolve-activity --brief -c android.intent.category.LAUNCHER {q(pkg)}",
                    check=False)
    last = out.strip().splitlines()[-1] if out.strip() else ""
    if "/" not in last:
        raise Fail(f"{pkg}: no launcher activity; give --component")
    return last


# ------------------------------------------------------------------------------------- commands
def cmd_state(dev, a, out):
    gate = Gate(dev, a.idle_min)
    res = {"identity": identity(dev), "gate": gate.facts}
    p, _ = dev.helper("power", check=False)
    save(out, "power.txt", p)
    res["power"] = parse_power(p)
    c, _ = dev.sh(f"sh {D}/gpu-diag-device.sh conditions", check=False)
    save(out, "conditions.txt", c)
    res["conditions"] = c.splitlines()
    props, _ = dev.sh("getprop", check=False)
    keep = re.compile(r"^\[(ro\.dalvik\.vm\.|dalvik\.vm\.|pm\.dexopt\.|ro\.berberis\.|ro\.product\.cpu\.abi|"
                      r"ro\.enable\.native\.bridge|ro\.boot\.openbook|.*openbook\.gfx|persist\.vendor\.openbook|"
                      r"ro\.hardware\.(vulkan|egl)|ro\.hwui\.|debug\.hwui\.|ro\.surface_flinger\.)")
    sel = [l for l in props.splitlines() if keep.match(l)]
    save(out, "props.txt", "\n".join(sel) + "\n")
    res["props"] = dict(re.match(r"\[(.*?)\]: \[(.*)\]", l).groups() for l in sel if re.match(r"\[(.*?)\]: \[(.*)\]", l))
    mem, _ = dev.sh("grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo", check=False)
    res["memory"] = {l.split(":")[0]: l.split(":")[1].strip() for l in mem.splitlines() if ":" in l}
    gate.check("while reading the state")
    return res


def cmd_inventory(dev, a, out):
    gate = Gate(dev, a.idle_min)
    pkgs = a.packages or sorted(l.split(":", 1)[1] for l in dev.sh("pm list packages -3")[0].split()
                                if l.startswith("package:"))
    apps, raw = [], []
    for pkg in pkgs:
        facts = app_facts(dev, pkg)
        paths = [l.split(":", 1)[1] for l in dev.sh(f"pm path {q(pkg)}", check=False)[0].split()
                 if l.startswith("package:")]
        abis, dex, libs = {}, 0, set()
        for apk in paths:
            listing = parse_apk_listing(dev.helper(f"apk {q(apk)}", check=False)[0])
            dex += listing["dex"]
            for abi, names in listing["abis"].items():
                abis.setdefault(abi, set()).update(names)
                libs.update(names)
        art, _ = dev.sh(f"pm art dump {q(pkg)}", check=False)
        raw.append(f"=== {pkg}\n{art}")
        files = parse_art_dump(art)
        primary = facts.get("primaryCpuAbi")
        apps.append({
            "package": pkg, "version": facts.get("versionName"), "versionCode": facts.get("versionCode"),
            "installer": facts.get("installerPackageName") or facts.get("initiatingPackageName"),
            "lastUpdateTime": facts.get("lastUpdateTime"), "splits": len(paths),
            "primaryCpuAbi": primary, "native_code": native_code(primary, abis),
            "installed_abis": sorted(abis), "installed_set_has_x86_64": "x86_64" in abis,
            "native_libs": len(libs), "framework_hint": framework_hints(libs) or (["unknown"] if libs else []),
            "dex_files": dex, "dexopt": dexopt_summary(files), "dexopt_files": files,
        })
        gate.check(f"during the inventory ({pkg})")
    save(out, "art-dump.txt", "\n".join(raw))
    return {"apps": apps}


def launch_once(dev, gate, comp, mode, a):
    gate.check(f"before a {mode} start")
    extra = " ".join(q(x) for x in a.extra)
    text, _ = dev.helper(f"launch {q(comp)} {mode} {a.period} {extra}", timeout=a.timeout, check=False)
    r = parse_launch(text)
    r["raw"] = text
    return r


def cmd_start(dev, a, out, power):
    pkg = a.package
    gate = Gate(dev, a.idle_min, pkg)
    comp = component(dev, pkg, a.component)
    res = {"package": pkg, "component": comp, "app": app_facts(dev, pkg), "identity": identity(dev),
           "label": a.label, "power_before": parse_power(dev.helper("power", check=False)[0]),
           "definitions": {"cold": "am start -W -S: the app's processes are force-stopped first; the page cache "
                                   "and ART's compiled code stay (a process-cold start, not a boot-cold one)",
                           "warm": "am start -W --activity-clear-task after going home: the process is kept, its "
                                   "activity is created again"},
           "runs": {"cold": [], "warm": []}}
    pc = PcacheProp(dev, pkg, a.pcache) if a.pcache else None
    try:
        if pc:
            dev.root()
            pc.set()
        if a.fixed_performance:
            res["power_change"] = power.apply("fixed-performance", "true")
        elif a.platform_profile:
            res["power_change"] = power.apply("platform-profile", a.platform_profile)
        for i in range(a.runs):
            r = launch_once(dev, gate, comp, "cold", a)
            res["runs"]["cold"].append(r)
            print(f"  cold {i + 1}/{a.runs}: {r['am']['total_ms']} ms ({r['am']['launch_state']}), "
                  f"EPP seen {','.join(r['epp_seen']) or 'na'}", flush=True)
            time.sleep(a.settle)
        for i in range(a.warm_runs):
            gate.check("before going home")
            dev.helper("home", check=False)
            time.sleep(a.settle)
            r = launch_once(dev, gate, comp, "warm", a)
            res["runs"]["warm"].append(r)
            print(f"  warm {i + 1}/{a.warm_runs}: {r['am']['total_ms']} ms ({r['am']['launch_state']})", flush=True)
            time.sleep(a.settle)
        gate.check("at the end")
    finally:
        try_sh(dev, f"am force-stop {q(pkg)}")  # it wasn't running before the run; never raises, so finish() runs
        if pc:
            res["pcache"] = pc.finish()
        try:
            res["power_restore"] = power.restore()
        except Fail as e:  # main() tries once more and keeps the journal if that fails too
            res["power_restore"] = f"failed: {e}"
    for mode, runs in res["runs"].items():
        save(out, f"{mode}.txt", "\n\n".join(r.pop("raw") for r in runs))
        res[mode] = {"total_ms": stats([r["am"]["total_ms"] for r in runs]),
                     "launch_states": sorted({str(r["am"]["launch_state"]) for r in runs}),
                     "failed": sum(1 for r in runs if not r["am"]["ok"]),
                     "epp_seen": sorted({e for r in runs for e in r["epp_seen"]})}
    return res


RECORDER_DATA = f"{D}/perf.data"


def try_sh(dev, cmd, timeout=60):
    """dev.sh that never raises: (out, rc), with rc None when adb failed or timed out. The recorder paths treat
    that as 'no answer', never as an answer."""
    try:
        return dev.sh(cmd, timeout=timeout, check=False)
    except Fail as e:
        return str(e), None


def find_recorders(dev):
    """Pids of any simpleperf recording into this tool's data file (this run's or an earlier run's), or None when
    that can't be established (adb failed or timed out, the answer was cut short). The probing shell skips itself:
    its own command line holds the pattern."""
    out, rc = try_sh(dev, "for p in /proc/[0-9]*; do [ \"${p#/proc/}\" = $$ ] && continue; "
                          "case \"$(tr '\\0' ' ' < $p/cmdline 2>/dev/null)\" in "
                          f"*simpleperf*record*{RECORDER_DATA}*) echo \"@pid ${{p#/proc/}}\" ;; esac; done; echo @end")
    if rc != 0 or "@end" not in out.splitlines():
        return None
    return [l.split()[1] for l in out.splitlines() if l.startswith("@pid ")]


class Recorder:
    """The system-wide simpleperf of one cpu run, started in the background by root on the device and known by its
    exact pid. Its state is "running", "gone" or "unknown": gone only when the device answered that the pid no longer
    exists or is no longer this recorder; a failed, timed-out or cut-short answer is unknown, never gone.

    The device is marked busy before the start command is sent and stays busy until the recorder is confirmed gone
    (or confirmed never started), so no clean-up removes its files or unroots while it may run. resolve() ends it:
    stop() for a known pid (SIGINT, which makes simpleperf finish its file, then TERM, then KILL), or, when the start
    wasn't confirmed, a search for it first."""

    def __init__(self, dev, data, log):
        self.dev, self.data, self.log, self.pid = dev, data, log, None
        self.owns_busy = False

    def _hold(self, why):
        self.dev.busy, self.owns_busy = why, True

    def _release(self):
        if self.owns_busy:
            self.dev.busy, self.owns_busy = None, False

    def start(self, event, freq, seconds):
        others = find_recorders(self.dev)
        if others is None:
            raise Fail("can't check for an earlier recorder (adb failed); not starting one")
        if others:
            self.dev.busy = f"an earlier run's simpleperf (pid {', '.join(others)}) is still recording into {D}"
            raise Fail(f"{self.dev.busy}; stop it (as root: kill -INT {others[0]}) before another cpu run")
        self._hold("a recorder was being started and isn't confirmed yet")
        out, rc = try_sh(self.dev, f"rm -f {self.data} {self.log}; "
                                   f"simpleperf record -a -e {q(event)} -f {int(freq)} --duration {int(seconds)} "
                                   f"-o {self.data} > {self.log} 2>&1 < /dev/null & echo \"@pid $!\"")
        pid = next((l.split()[1] for l in out.splitlines() if l.startswith("@pid ")), None) if rc == 0 else None
        if not pid or not pid.isdigit():
            how = self.resolve()  # the answer was lost: the recorder may have started anyway
            raise Fail(f"simpleperf's start wasn't confirmed ({' '.join(out.split())[-160:]!r}); {how}")
        self.pid = pid
        self._hold(f"simpleperf pid {pid}: recording")
        st = self.state()
        if st == "gone":
            self._release()
            raise Fail(f"simpleperf (pid {pid}) exited at once: {try_sh(self.dev, f'cat {self.log}')[0][-300:]}")
        if st == "unknown":
            raise Fail(f"simpleperf (pid {pid}) started but its state can't be read (adb failed)")

    def state(self, tries=3):
        """'running', 'gone' or 'unknown' (after `tries` failed probes, a second apart)."""
        if not self.pid:
            return "unknown" if self.owns_busy else "gone"
        probe = (f"if [ -e /proc/{self.pid} ]; then echo \"@cmd $(tr '\\0' ' ' < /proc/{self.pid}/cmdline "
                 f"2>/dev/null)\"; else echo @gone; fi; echo @end")
        for i in range(tries):
            out, rc = try_sh(self.dev, probe)
            lines = out.splitlines()
            if rc == 0 and "@end" in lines:
                if "@gone" in lines:
                    return "gone"
                cmd = next((l[5:] for l in lines if l.startswith("@cmd ")), None)
                if cmd is not None:
                    # Empty (a zombie) or another program (the pid was reused): this recorder has ended.
                    return "running" if "simpleperf" in cmd and self.data in cmd else "gone"
            if i + 1 < tries:
                time.sleep(1)
        return "unknown"

    def alive(self):
        return self.state() != "gone"

    def wait(self, seconds, poll):
        """Wait up to `seconds` for the recording to end on its own (confirmed gone); poll() runs every second
        meanwhile (the gate). An unknown state keeps waiting until the deadline."""
        t0 = time.time()
        while self.state() != "gone":
            if time.time() - t0 > seconds:
                raise Fail(f"simpleperf (pid {self.pid}) not confirmed finished after {seconds} s")
            poll()
            time.sleep(1)
        self._release()

    def resolve(self):
        """End whatever this recorder may have left running and say how. With a known pid: stop(). Without one
        (the start's answer was lost): look for it; adopt and stop it if found, release the device if it's
        confirmed absent, keep it busy if that can't be checked."""
        if self.pid:
            return self.stop()
        if not self.owns_busy:
            return "not started"
        found = find_recorders(self.dev)
        if found is None:
            why = "a recorder may have started, but the device can't be checked (adb failed)"
            self._hold(why)
            self.dev.notes["recorder"] = why
            return why
        if not found:
            self._release()
            return "none is running (confirmed)"
        self.pid = found[0]
        self._hold(f"simpleperf pid {self.pid}: adopted")
        return f"adopted pid {self.pid}: {self.stop()}"

    def stop(self):
        """End the recorder and confirm it's gone. Returns what it took. Raises Fail, with the device kept busy,
        while it still runs or its state can't be read; a later stop() that confirms it gone releases that."""
        st = self.state()
        if st == "gone":
            self._release()
            return "already ended"
        if st == "running":
            for sig, grace in (("INT", 10), ("TERM", 5), ("KILL", 5)):
                try_sh(self.dev, f"kill -{sig} {self.pid}")
                t0 = time.time()
                while time.time() - t0 < grace:
                    st = self.state()
                    if st == "gone":
                        self._release()
                        return f"stopped with SIG{sig}"
                    time.sleep(0.5)
        what = ("still running after INT, TERM and KILL" if st == "running"
                else "its state can't be read (adb failed), so it may still be running")
        self._hold(f"simpleperf pid {self.pid}: {what}")
        self.dev.notes["recorder"] = f"pid {self.pid}: {what}"
        raise Fail(f"simpleperf (pid {self.pid}): {what}; its files and root were left in place")


class TranslatorProps:
    """berberis.stats and berberis.profiling for one cpu --translator run. Digitalis reads them when the app's
    process starts, so they're set (as root) before the process-cold launch and put back to what they were after.
    The perf maps the app wrote into its data directory are removed after they're read. Both properties are
    volatile: a run killed before restore() leaves them set only until the next reboot (dev.notes says so)."""

    NAMES = ("berberis.stats", "berberis.profiling")

    def __init__(self, dev, pkg):
        self.dev, self.pkg, self.old, self.perf_maps, self.map_pids = dev, pkg, None, {}, set()

    def set(self):
        old = {}
        for n in self.NAMES:
            out, rc = try_sh(self.dev, f"getprop {n}")
            if rc != 0:
                raise Fail(f"can't read {n} before setting it")
            old[n] = out.strip()
        self.old = old
        self.dev.notes["translator_props"] = f"set for this run; were {old}"
        for n, v in (("berberis.stats", "1"), ("berberis.profiling", self.pkg)):
            self.dev.sh(f"setprop {n} {q(v)}")
            if self.dev.sh(f"getprop {n}", check=False)[0].strip() != v:
                raise Fail(f"setprop {n} didn't take")

    def perf_map(self, pid):
        return f"/data/data/{self.pkg}/perf-{pid}.map"

    def read_block(self, pid, addr):
        """The block of a running process, read from its memory: (header, counters, baseline); ValueError if it
        can't be read or isn't an OBSTAT2 block."""
        mem = f"/proc/{pid}/mem"
        head, rc = try_sh(self.dev, f"xxd -s {addr} -l {STATS_HEADER} -p {mem}")
        if rc != 0:
            raise ValueError(f"can't read {mem}: {' '.join(head.split())[-160:]}")
        h = parse_stats_header(head)
        body, rc = try_sh(self.dev, f"xxd -s {addr + STATS_HEADER} -l {stats_body_size(h)} -p {mem}")
        if rc != 0:
            raise ValueError(f"can't read {mem}: {' '.join(body.split())[-160:]}")
        counters, baseline = parse_stats_body(body, h)
        return h, counters, baseline

    def scan_block(self, pid):
        """The block's address in a running process, found in the translator library's writable data (see
        BLOCK_LIB); None when it isn't there or the memory can't be read."""
        maps, rc = try_sh(self.dev, f"cat /proc/{pid}/maps", timeout=60)
        if rc != 0:
            return None
        left = BLOCK_SCAN_MAX
        for lo, hi in block_scan_ranges(maps):
            n = min(hi - lo, left)
            if n <= 0:
                break
            left -= n
            text, rc = try_sh(self.dev, f"xxd -s {lo} -l {n} -p /proc/{pid}/mem", timeout=120)
            if rc != 0:
                continue
            try:
                data = bytes.fromhex("".join(text.split()))
            except ValueError:
                continue
            addr = find_stats_block(data, lo)
            if addr is not None:
                return addr
        return None

    def parent_of(self, pid):
        out, rc = try_sh(self.dev, f"cat /proc/{pid}/stat")
        if rc != 0 or ")" not in out:
            return None
        f = out.rsplit(")", 1)[1].split()
        return f[1] if len(f) > 1 and f[1].isdigit() else None

    def read_map(self, out, pid):
        text, rc = try_sh(self.dev, f"cat {q(self.perf_map(pid))}", timeout=300)
        if rc != 0:
            return None
        self.map_pids.add(pid)
        save(out, f"perf-{pid}.map", text)
        return parse_perf_map(text)

    def collect(self, out, seen):
        """Each process's counters and perf map, read at the end of the recording while the app still runs (the
        counters keep counting after it). tiers() places the samples once simpleperf has reported them."""
        log = self.dev.sh("logcat -d -b main -v brief -s berberis:I", timeout=120, check=False)[0]
        lines = [l for l in log.splitlines() if "openbook-stats" in l or "berberis.stats" in l]
        addrs = parse_stats_addresses("\n".join(lines))
        stats, raw = {}, list(lines)
        for pid in seen:
            # The address the process logged, while that line is still in the log; else the block found in the
            # translator library's data (the line rotated out, or a forked process that never logs one).
            t = time.time()
            addr, found = addrs.get(pid), "logged"
            if addr is None:
                addr, found = self.scan_block(pid), f"found in {BLOCK_LIB}'s data"
            if addr is None:
                stats[pid] = {"error": f"no block: no address logged and none in {BLOCK_LIB}'s data (an image "
                                       "without ANAL-383's patch, berberis.stats wasn't read because the process "
                                       "was already running, or its memory can't be read)",
                              "read_s": round(time.time() - t, 2)}
                continue
            try:
                h, counters, baseline = self.read_block(pid, addr)
                stats[pid] = {"read_at_utc": utc(), "address": hex(addr), "address_from": found,
                              "enabled": bool(h["enabled"]),
                              "owner_pid": h["owner_pid"], **stats_origin(pid, h, counters, baseline),
                              "counters": counters}
                raw.append(f"@pid {pid} @0x{addr:x} enabled={h['enabled']} owner={h['owner_pid']} "
                           f"baseline_valid={h['baseline_valid']} " +
                           " ".join(f"{k}={v}" for k, v in counters.items()) +
                           " baseline: " + " ".join(f"{k}={v}" for k, v in baseline.items()))
            except ValueError as e:
                stats[pid] = {"address": hex(addr), "error": str(e)}
            stats[pid]["read_s"] = round(time.time() - t, 2)
        save(out, "translator-stats.txt", "\n".join(raw) + "\n")
        # Each process writes its own map. A fork child also runs code its parent translated before the fork (an
        # app zygote's preload): those regions are in the parent's map, so the parent's goes in first and the
        # child's own, newer, entries win where they overlap. A process with no map of its own (an isolated
        # process can't write to the app's data directory) gets no tier profile: its samples are unattributed, and
        # coverage says why.
        own = {pid: self.read_map(out, pid) for pid in seen}
        perf_maps, coverage = {}, {}
        for pid in seen:
            ppid = self.parent_of(pid)
            parent = None
            if ppid and ppid not in own:
                own[ppid] = self.read_map(out, ppid)
            if ppid:
                parent = own.get(ppid)
            entries = (parent or []) + (own[pid] or [])
            if entries:
                perf_maps[pid] = entries
            coverage[pid] = {
                "own_map_regions": len(own[pid]) if own[pid] is not None else None,
                "parent": ppid, "parent_map_regions": len(parent) if parent is not None else None,
                "tier_profile": ("own and parent's (inherited code)" if own[pid] is not None and parent
                                 else "own map" if own[pid] is not None
                                 else "parent's map only (code it inherited)" if parent
                                 else "unavailable: no perf map (an isolated process can't write one)")}
        self.perf_maps = perf_maps
        return {"stats": stats, "perf_map_coverage": coverage}

    def tiers(self, rows, maps):
        return tier_attribution(rows, maps, self.perf_maps)

    def restore(self, seen):
        """Put both properties back and remove the perf maps; returns what happened."""
        if self.old is None:
            return "nothing set"
        done = []
        for n, v in self.old.items():
            _, rc = try_sh(self.dev, f"setprop {n} {q(v)}")
            done.append(f"{n} {'restored' if rc == 0 else 'NOT restored'}")
        for pid in set(seen) | self.map_pids:
            try_sh(self.dev, f"rm -f {q(self.perf_map(pid))}")
        left, rc = try_sh(self.dev, f"ls /data/data/{q(self.pkg)}/ | grep -c '^perf-.*\\.map$'")
        done.append("perf maps removed" if rc is not None and left.strip() == "0" else f"perf maps left: {left.strip()}")
        self.dev.notes["translator_props"] = "; ".join(done)
        return self.dev.notes["translator_props"]


# Digitalis's persistent translation cache (ANAL-381, docs/digitalis-translation-cache.md): an app's files are in
# /data/data/PKG/code_cache/berberis, named by module key: <key>.pcache, <key>.pidx, <key>.lock, and a writer's
# <file>.tmp.<pid> while it creates one.
PCACHE_FILE = re.compile(r"[bs][0-9a-f-]+\.(pcache|pidx|lock)(\.tmp\.[0-9]+)?")
PACKAGE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+")


def pcache_paths(pkg):
    """(data directory, code_cache, cache directory) of PKG for user 0; Fail if PKG isn't a package name."""
    if not PACKAGE_NAME.fullmatch(pkg or ""):
        raise Fail(f"{pkg!r} isn't a package name")
    d = f"/data/data/{pkg}"
    return d, f"{d}/code_cache", f"{d}/code_cache/berberis"


def pcache_listing_cmd(pkg):
    """One shell command listing PKG's cache: each directory's type and owner (stat doesn't follow a symbolic link),
    then every entry in the cache directory, then @end."""
    d, cc, c = pcache_paths(pkg)
    return (f"for p in {q(d)} {q(cc)} {q(c)}; do stat -c '@dir %F|%u|%n' \"$p\" 2>/dev/null || echo \"@missing $p\"; "
            f"done; c={q(c)}; if [ -d \"$c\" ] && [ ! -L \"$c\" ]; then "
            "for f in \"$c\"/* \"$c\"/.[!.]* \"$c\"/..?*; do [ -e \"$f\" ] || [ -L \"$f\" ] || continue; "
            "stat -c '@entry %F|%s|%n' \"$f\"; done; fi; echo @end")


def parse_pcache_listing(text, pkg):
    """pcache_listing_cmd's output -> {exists, files, bytes, names}. Fail unless the data directory and code_cache are
    real directories of one app uid, and the cache directory, if there is one, is that app's real directory holding
    only cache files. Nothing is ever removed on the strength of a listing this refuses."""
    d, cc, c = pcache_paths(pkg)
    lines = text.splitlines()
    if "@end" not in lines:
        raise Fail(f"listing {c}: no complete answer")
    dirs, missing, entries = {}, set(), []
    for line in lines:
        if line.startswith("@dir "):
            kind, uid, path = line[5:].split("|", 2)
            dirs[path] = (kind, uid)
        elif line.startswith("@missing "):
            missing.add(line[9:])
        elif line.startswith("@entry "):
            entries.append(line[7:].split("|", 2))
    for path in (d, cc):
        if dirs.get(path, ("missing", ""))[0] != "directory":
            raise Fail(f"{path} isn't a directory ({dirs.get(path, ('missing',))[0]})")
    uid = dirs[d][1]
    if not uid.isdigit() or int(uid) < 10000 or dirs[cc][1] != uid:
        raise Fail(f"{d} and {cc} aren't one app's (uids {uid}, {dirs[cc][1]})")
    if c in missing and c not in dirs and not entries:
        return {"exists": False, "files": 0, "bytes": 0, "names": []}
    if dirs.get(c) != ("directory", uid):
        raise Fail(f"{c} isn't the app's own directory ({dirs.get(c)})")
    names, total = [], 0
    for kind, size, path in entries:
        name = path.rsplit("/", 1)[-1]
        if (kind not in ("regular file", "regular empty file") or path != f"{c}/{name}"
                or not PCACHE_FILE.fullmatch(name) or not size.isdigit()):
            raise Fail(f"unexpected entry in {c}: {kind} {path}")
        names.append(name)
        total += int(size)
    return {"exists": True, "files": len(names), "bytes": total, "names": sorted(names)}


def pcache_facts(dev, pkg):
    out, rc = try_sh(dev, pcache_listing_cmd(pkg))
    if rc is None:
        raise Fail(f"no answer listing {pkg}'s translation cache")
    return parse_pcache_listing(out, pkg)


def pcache_clear(dev, pkg):
    """Remove PKG's translation cache: exactly the files a checked listing found, then the empty directory, then list
    again. As root, with the app not running (the caller's gate)."""
    before = pcache_facts(dev, pkg)
    if not before["exists"]:
        return {"before": before, "after": before, "removed": 0}
    _, _, c = pcache_paths(pkg)
    cmd = " && ".join([f"rm -f -- {q(c + '/' + n)}" for n in before["names"]] + [f"rmdir -- {q(c)}"])
    _, rc = try_sh(dev, cmd)
    after = pcache_facts(dev, pkg)
    if rc != 0 or after["exists"]:
        raise Fail(f"{c} wasn't removed (rc {rc}): {after}")
    return {"before": before, "after": after, "removed": before["files"]}


class PcacheProp:
    """berberis.pcache for one start or cpu run (Digitalis patch 14): MODE:PKG, so only the test package's processes use
    the cache, or "off" for a control run. Set as root before the run's first process-cold launch (each reads it when
    it starts); finish() stops the app's processes before it puts the property back, so no process of the app can
    read the run's value afterwards. Volatile: a run killed before finish() leaves it set until the next reboot, and
    only for this package."""

    NAME = "berberis.pcache"

    def __init__(self, dev, pkg, mode):
        if mode not in ("off", "on", "verify"):
            raise Fail(f"--pcache {mode!r}: off, on or verify")
        pcache_paths(pkg)
        self.dev, self.pkg, self.mode, self.old = dev, pkg, mode, None
        self.value = "off" if mode == "off" else f"{mode}:{pkg}"

    def set(self):
        out, rc = try_sh(self.dev, f"getprop {self.NAME}")
        if rc != 0:
            raise Fail(f"can't read {self.NAME} before setting it")
        self.old = out.strip()
        self.dev.notes["pcache_prop"] = f"set to {self.value!r} for this run; was {self.old!r}"
        self.dev.sh(f"setprop {self.NAME} {q(self.value)}")
        if self.dev.sh(f"getprop {self.NAME}", check=False)[0].strip() != self.value:
            raise Fail(f"setprop {self.NAME} didn't take")

    def finish(self):
        res = {"mode": self.mode, "value": self.value}
        try_sh(self.dev, f"am force-stop {q(self.pkg)}")
        if self.old is None:
            res["restore"] = "nothing set"
        else:
            _, rc = try_sh(self.dev, f"setprop {self.NAME} {q(self.old)}")
            now, rc2 = try_sh(self.dev, f"getprop {self.NAME}")
            ok = rc == 0 and rc2 == 0 and now.strip() == self.old
            res["restore"] = f"{'restored' if ok else 'NOT restored'} to {self.old!r}"
            self.dev.notes["pcache_prop"] = res["restore"]
            if not ok:
                self.dev.notes["pcache_restore_failed"] = True
        try:
            res["cache_after"] = pcache_facts(self.dev, self.pkg)
        except Fail as e:
            res["cache_after"] = {"error": str(e)}
        return res


def cmd_cpu(dev, a, out):
    pkg = a.package
    gate = Gate(dev, a.idle_min, pkg)
    comp = component(dev, pkg, a.component)
    res = {"package": pkg, "component": comp, "app": app_facts(dev, pkg), "identity": identity(dev),
           "label": a.label, "seconds": a.seconds, "event": a.event, "frequency": a.freq}
    rec = Recorder(dev, RECORDER_DATA, f"{D}/record.log")
    props = TranslatorProps(dev, pkg) if a.translator else None
    pc = PcacheProp(dev, pkg, a.pcache) if a.pcache else None
    seen = {}  # every process of the app seen during the recording: pid -> name; maps at first sight and at the end
    maps_text = []

    def watch():
        gate.check("during the recording")
        for line in running(dev, pkg).splitlines():
            pid, _, name = line.strip().partition(" ")
            if pid.isdigit() and pid not in seen:
                seen[pid] = name
                maps_text.append(dev.helper(f"maps {pid}", check=False)[0])

    try:
        dev.root()
        if props:
            props.set()
        if pc:
            pc.set()
        dur = a.seconds + 2
        rec.start(a.event, a.freq, dur)
        time.sleep(1)
        gate.check("before the launch")
        r = parse_launch(dev.helper(f"launch {q(comp)} cold {a.period} {' '.join(q(x) for x in a.extra)}",
                                    timeout=a.timeout, check=False)[0])
        res["launch"] = {k: r[k] for k in ("am", "epp_seen", "maxfreq_khz")}
        watch()
        rec.wait(dur + 30, watch)
        res["recorder"] = "ended on its own"
        if props:
            res["translator"] = props.collect(out, seen)
        gate.check("after the recording")
        alive = [l.split()[0] for l in running(dev, pkg).splitlines() if l.strip()]
        if alive:
            maps_text.append(dev.helper(f"maps {' '.join(alive)}", check=False)[0])
        if not seen:
            raise Fail(f"{pkg} had no process during the recording")
        res["pids"] = [f"{p} {n}" + ("" if p in alive else " (exited during the recording)") for p, n in seen.items()]
        maps_all = "\n".join(maps_text)
        save(out, "maps.txt", maps_all)
        save(out, "record.log", dev.sh(f"cat {rec.log}", check=False)[0])
        rep = dev.sh(f"simpleperf report -i {rec.data} --pids {','.join(seen)} --sort pid,dso,symbol --csv "
                     f"--csv-separator '{SEP}'", timeout=600, check=False)[0]
        save(out, "report-pid-dso-symbol.csv", rep)
        comm = dev.sh(f"simpleperf report -i {rec.data} --sort comm --percent-limit 1", timeout=300, check=False)[0]
        save(out, "report-system-comm.txt", comm)
        head, rows = parse_simpleperf_csv(rep)
        if not rows:
            raise Fail("simpleperf reported no samples for the app")
        res["simpleperf"] = head
        res["attribution"] = cpu_attribution(rows, parse_maps(maps_all))
        if props:
            res["translator"]["tiers"] = props.tiers(rows, parse_maps(maps_all))
    finally:
        # The recorder first: its files go only once it's gone, and only then does adbd stop being root.
        try:
            how = rec.resolve()
            dev.notes["recorder"] = f"pid {rec.pid}: {how}" if rec.pid else how
            res.setdefault("recorder", dev.notes["recorder"])
            if not dev.busy:
                dev.sh(f"rm -f {rec.data} {rec.log}", check=False)
        finally:
            try_sh(dev, f"am force-stop {q(pkg)}")
            if pc:
                res["pcache"] = pc.finish()
            if props:
                res.setdefault("translator", {})["cleanup"] = props.restore(seen)
            if not dev.busy:
                dev.unroot()
    return res


def cmd_dexopt(dev, a, out):
    pkg = a.package
    if not a.yes:
        raise Fail("dexopt changes the app's compiled code, which can't be put back exactly; add --yes")
    gate = Gate(dev, a.idle_min, pkg)
    before, _ = dev.sh(f"pm art dump {q(pkg)}", check=False)
    save(out, "art-before.txt", before)
    gate.check("before compiling")
    t0 = time.time()
    log, rc = dev.sh(f"pm compile -m {q(a.filter)} -f -v {q(pkg)}", timeout=1800, check=False)
    secs = time.time() - t0
    save(out, "compile.txt", log)
    after, _ = dev.sh(f"pm art dump {q(pkg)}", check=False)
    save(out, "art-after.txt", after)
    gate.check("after compiling")
    b, f = parse_art_dump(before), parse_art_dump(after)
    return {"package": pkg, "app": app_facts(dev, pkg), "filter": a.filter, "exit": rc, "seconds": round(secs, 1),
            "before": dexopt_summary(b), "after": dexopt_summary(f), "files_before": b, "files_after": f,
            "note": "the command succeeding proves nothing: 'after' is what ART reports"}


def pct(v):
    return "na" if v is None else f"{100 * v:.1f}%"


def condition(r):
    """The power setting a start run changed, if any: 'fixed-performance', 'platform-profile=performance' or ''."""
    ch = r.get("power_change") or {}
    kind = (ch.get("before") or {}).get("kind")
    if kind == "platform-profile":
        return f"platform-profile={ch.get('set')}"
    return kind or ""


def build_identity(app):
    """(versionCode, installed ABI) of one run's or inventory entry's own app facts: what was measured, not what is
    installed now. 'na' / 'none' when a record lacks them."""
    vc = (app or {}).get("versionCode")
    return ("na" if vc is None else str(vc)), ((app or {}).get("primaryCpuAbi") or "none")


def cmd_table(dirs):
    """One row per app build (versionCode and installed ABI), label and power setting, so an app's update, a baseline
    and a changed setting never share a row. Version and native code come from each run's own record; the inventory
    adds its framework hint and ART state only to rows of the same build. Runs that aren't 'ok' are skipped and
    named."""
    inv, rows, versions, skipped = {}, {}, {}, []
    for d in dirs:
        try:
            with open(os.path.join(d, "run.json")) as f:
                run = json.load(f)
        except (OSError, ValueError) as e:
            skipped.append(f"{d}: {e}")
            continue
        r = run.get("result")
        if run.get("outcome") != "ok" or not isinstance(r, dict):
            skipped.append(f"{d}: {run.get('outcome') or 'no outcome'}")
            continue
        cmd = run.get("command")
        try:
            if cmd == "inventory":
                for app in r["apps"]:
                    build = (app["package"], *build_identity(app))
                    inv[build] = {"framework": ", ".join(app["framework_hint"]) or "-", "dexopt": app["dexopt"]}
                    versions.setdefault(build, app.get("version"))
            elif cmd in ("start", "cpu"):
                app = r.get("app") or {}
                build = (r["package"], *build_identity(app))
                versions.setdefault(build, app.get("versionName"))
                row = rows.setdefault((*build, r.get("label") or "", condition(r) if cmd == "start" else ""), {})
                if cmd == "start":
                    for mode in ("cold", "warm"):
                        st = r[mode]["total_ms"]
                        row[mode] = (f"{st['median']:.0f} ({st['min']}–{st['max']}, n={st['n']})"
                                     if st.get("n") else "na")
                else:
                    g, sh = r["attribution"]["groups"], r["attribution"]["share"]
                    row["cpu"] = (f"ARM {pct(g['arm_code'])}, compile {pct(g['translation_overhead'])}, "
                                  f"bridge {pct(g['bridge_runtime'])}, Java {pct(sh['java'])}, "
                                  f"x86_64 app {pct(sh['app-native'])}, unknown {pct(sh['unknown'])}")
        except (KeyError, TypeError) as e:
            skipped.append(f"{d}: incomplete {cmd} record ({e!r})")
    for build in inv:  # an inventoried build with no measurement still gets its row
        if not any(k[:3] == build for k in rows):
            rows[(*build, "", "")] = {}
    head = ["App", "Version (code)", "Native code", "Label", "Power setting", "Framework hint", "ART filter/reason",
            "Cold start ms, median (range, n)", "Warm start ms", "CPU from launch (share of the app's samples)"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for key in sorted(rows):
        pkg, vc, abi, label, cond = key
        build = (pkg, vc, abi)
        cells = [pkg, f"{versions.get(build) or 'na'} ({vc})", native_code(None if abi == "none" else abi, {}),
                 label or "-", cond or "as found"]
        cells += [inv.get(build, {}).get(c, "na") for c in ("framework", "dexopt")]
        cells += [rows[key].get(c, "na") for c in ("cold", "warm", "cpu")]
        lines.append("| " + " | ".join(str(c) for c in cells) + " |")
    for s_ in skipped:
        print(f"skipped {s_}", file=sys.stderr)
    return "\n".join(lines)


# ------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial")
    ap.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    ap.add_argument("--journal", help="where a power change is journalled until it's put back")
    ap.add_argument("--idle-min", type=float, default=10.0)
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("state", "inventory", "start", "cpu", "dexopt"):
        p = sub.add_parser(name)
        p.add_argument("out")
        if name == "inventory":
            p.add_argument("packages", nargs="*")
        elif name != "state":
            p.add_argument("package")
            p.add_argument("--label", default="")
        if name in ("start", "cpu"):
            p.add_argument("--component", help="PKG/ACTIVITY to start (default: the launcher activity)")
            p.add_argument("--extra", action="append", default=[], help="one more am start argument, repeatable")
            p.add_argument("--period", type=float, default=0.1, help="EPP/frequency sampling while am start runs")
            p.add_argument("--timeout", type=int, default=120, help="seconds for one am start")
            p.add_argument("--pcache", choices=("off", "on", "verify"),
                           help="Digitalis's translation cache for this run's processes: berberis.pcache=MODE:PACKAGE "
                                "(off sets 'off'), put back after the app is stopped (an image with patch 14; root)")
        if name == "start":
            p.add_argument("--runs", type=int, default=5, help="process-cold starts")
            p.add_argument("--warm-runs", type=int, default=5)
            p.add_argument("--settle", type=float, default=3.0, help="seconds between starts")
            g = p.add_mutually_exclusive_group()
            g.add_argument("--fixed-performance", action="store_true",
                           help="Android's fixed performance mode for this run (the power HAL: EPP performance)")
            g.add_argument("--platform-profile", help="the ACPI platform profile for this run (root)")
        if name == "cpu":
            p.add_argument("--seconds", type=int, default=20, help="recorded after the launch begins")
            p.add_argument("--event", default="cpu-clock")
            p.add_argument("--freq", type=int, default=1000)
            p.add_argument("--translator", action="store_true",
                           help="Digitalis's profile too: its counters and the translated samples by tier and region "
                                "(sets berberis.stats and berberis.profiling for the run; an image with ANAL-383)")
        if name == "dexopt":
            p.add_argument("--filter", required=True, help="speed-profile, speed, verify, ...")
            p.add_argument("--yes", action="store_true")
    p = sub.add_parser("table")
    p.add_argument("dirs", nargs="+")
    sub.add_parser("restore")
    a = ap.parse_args()

    if a.command == "table":
        print(cmd_table(a.dirs))
        return 0
    if not a.serial or not a.journal:
        ap.error("--serial and --journal are required (app-perf.sh gives them)")
    dev = Device(a.serial, a.adb)
    power = Power(dev, a.journal)
    if a.command == "restore":
        if not os.path.exists(a.journal):
            print("nothing to restore")
            return 0
        try:
            with open(a.journal) as f:
                power.saved = json.load(f)
            print(json.dumps(power.restore()))
        except (Fail, ValueError) as e:
            print(f"app-perf restore: {e}; the journal stays ({a.journal})", file=sys.stderr)
            return RESTORE_FAILED
        finally:
            try:
                dev.unroot()
            except Fail as e:
                print(f"app-perf restore: unroot: {e}", file=sys.stderr)
        return 0
    if os.path.exists(a.journal):
        with open(a.journal) as f:
            kept = f.read().strip()
        print(f"app-perf: an earlier run's power change wasn't put back ({kept}); run 'app-perf.sh restore' first",
              file=sys.stderr)
        return RESTORE_FAILED

    def on_signal(sig, _):
        # One signal stops the run; any later one is ignored so it can't cut the clean-up short (g14-lock.sh sends
        # KILL after its grace period if the clean-up hangs).
        for s2 in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(s2, signal.SIG_IGN)
        raise KeyboardInterrupt(f"signal {sig}")
    for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(s, on_signal)

    out = newdir(a.out)
    run = {"command": a.command, "args": {k: v for k, v in vars(a).items() if k not in ("adb",)},
           "tool": tool_rev(), "start": utc(), "serial_kind": "network" if ":" in a.serial else "local"}
    run["args"].pop("serial", None)
    status = 0
    try:
        setup(dev)
        if a.command == "state":
            run["result"] = cmd_state(dev, a, out)
        elif a.command == "inventory":
            run["result"] = cmd_inventory(dev, a, out)
        elif a.command == "start":
            run["result"] = cmd_start(dev, a, out, power)
        elif a.command == "cpu":
            run["result"] = cmd_cpu(dev, a, out)
        elif a.command == "dexopt":
            run["result"] = cmd_dexopt(dev, a, out)
        run["outcome"] = "ok"
    except Invalid as e:
        run["outcome"], status = f"invalid: {e}", INVALID
    except (Fail, KeyboardInterrupt) as e:
        run["outcome"], status = f"failed: {e}", FAILED
    finally:
        if power.saved:  # an exception before cmd_start's own restore
            try:
                run["power_restore"] = power.restore()
            except Exception as e:  # noqa: BLE001 - the journal stays for 'restore'
                run["power_restore"], status = f"FAILED, journal kept: {e}", RESTORE_FAILED
        try:
            run["cleanup"] = cleanup(dev)
            if dev.busy:
                status = FAILED if status == 0 else status
        except Fail as e:
            run["cleanup"] = f"failed: {e}"
        if dev.notes.get("pcache_restore_failed"):
            run["pcache_restore"] = "FAILED: berberis.pcache wasn't put back (volatile: a reboot clears it)"
            status = FAILED if status == 0 else status
        if dev.notes:
            run["device"] = dev.notes
        run["end"] = utc()
        with open(os.path.join(out, "run.json"), "w") as f:
            json.dump(run, f, indent=1)
    print(f"{a.command}: {run['outcome']} -> {out}/run.json")
    return status


if __name__ == "__main__":
    sys.exit(main())
