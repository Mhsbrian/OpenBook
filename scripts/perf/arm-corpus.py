#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The ARM-translation corpus on an OpenBook device over adb (ANAL-380, docs/arm-performance.md). Run it through
scripts/perf/arm-corpus.sh, which holds the G14 lock and connects; this file does the work.

  list                      the corpus (scripts/perf/arm-corpus.tsv)
  fetch                     host only: download every pinned F-Droid APK into ~/anybook/perf/arm-corpus and check
                            its sha256, its signer's certificate and that it carries the ABIs its row says; check that
                            locally built rows exist and carry both ABIs
  install OUT ID --abi ABI  install corpus app ID with its native code forced to ABI (arm64-v8a: translated; x86_64:
                            native), then check the installed package's primaryCpuAbi and version. Only test packages:
                            a package that is already installed and that this tool didn't install is refused, never
                            replaced. 'fat' rows install the same APK for both ABIs; per-ABI rows install that ABI's
                            build of the same version (-d, since their version codes differ)
  remove OUT [ID...]        uninstall what this tool installed on this device (default: all of it), each removal
                            confirmed; anything unconfirmed stays in the journal and fails the run
  exe OUT                   CoreMark and simd-bench as arm64 executables (translated, through binfmt_misc) and x86_64
                            executables (native), each pinned to one CPU of every core type the device has, rounds
                            interleaved with the ABI order alternating. Results are checked: CoreMark's own validation,
                            simd-bench's checksums against its scalar reference and across the two ABIs

  bench OUT ID [--runs 3]   a corpus app's own unattended benchmark (task "bench": today the TPS demo built by
                            scripts/perf/workloads/build-tps-demo.sh), process-cold each run. The log is cleared and
                            the app launched (both must succeed); only the lines of the process that launch started
                            count (logcat's pid and the pid the benchmark prints must both be it). The gate is checked every --poll
                            seconds. At the end, and on input, a timeout, an adb failure or a signal, the app is
                            force-stopped and its stop confirmed; until then the journal marks it running, and any
                            later command stops it first. The engine's reported architecture must match the
                            installed ABI (arm64 translated, x86_64 native)

Starts and CPU attribution of installed corpus apps come from scripts/perf/app-perf.sh, frames from
scripts/gpu-diag.sh. SuperTuxKart's built-in performance test can only be started by tapping its menu; it isn't run
unattended until injected taps can be told apart from an owner's input.

Every device command except remove checks first that the laptop is idle (the gate app-perf and gpu-diag use) and
stops at the next check after any input (exit 3); exe checks it every --poll seconds while a benchmark runs and stops
that benchmark's processes on input, an adb failure, a timeout or a signal. remove runs whenever asked, so test
packages never stay behind. Package writes need a confirmed answer from the package manager: when adb or pm doesn't
answer, nothing is installed, replaced or removed, and the journal keeps its entries.
OUT must not exist; each run writes run.json and its raw outputs there.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("app_perf", os.path.join(HERE, "app-perf.py"))
AP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(AP)

R = AP.R
A = os.path.expanduser(os.environ.get("OPENBOOK_HOME", os.environ.get("ANYBOOK_HOME", "~/anybook")))
TSV = os.path.join(HERE, "arm-corpus.tsv")
STORE = os.path.join(A, "perf", "arm-corpus")
D = "/data/local/tmp/openbook-arm-corpus"
INVALID, FAILED = AP.INVALID, AP.FAILED
Fail, Invalid = AP.Fail, AP.Invalid
ABIS = ("arm64-v8a", "x86_64")
FDROID = ["https://f-droid.org/repo", "https://f-droid.org/archive"]
MIRRORS = os.environ.get("FDROID_MIRRORS", "https://plug-mirror.rcac.purdue.edu/fdroid/repo "
                         "https://mirror.fcix.net/fdroid/repo").split()
BENCH = {  # executable -> (host path, how its output is read)
    "coremark": os.path.join(A, "compat", "out", "probes", "bench", "coremark-{abi}"),
    "simd": os.path.join(A, "perf", "simd-bench", "simd-bench-{abi}"),
}
EXE_ABI = {"arm64-v8a": "arm64", "x86_64": "x86_64"}
COREMARK_ARGS = "0x0 0x0 0x66 {iterations}"  # as scripts/compat/run-bench.sh: seeds 0,0,0x66 (performance run)


# ---- the corpus ----

def load_corpus(path=TSV):
    rows, header = [], None
    with open(path) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            cells = line.rstrip("\n").split("\t")
            if header is None:
                header = cells
                continue
            if len(cells) != len(header):
                raise Fail(f"{path}: {len(cells)} cells, header has {len(header)}: {line[:60]}")
            rows.append(dict(zip(header, cells)))
    return rows


def row_for(rows, rid, abi):
    """The row that installs corpus app RID with ABI: its own per-ABI row, or its 'fat' row."""
    mine = [r for r in rows if r["id"] == rid]
    if not mine:
        raise Fail(f"no corpus app {rid!r} (ids: {', '.join(sorted({r['id'] for r in rows}))})")
    for r in mine:
        if r["abi"] == abi:
            return r
    for r in mine:
        if r["abi"] == "fat":
            return r
    raise Fail(f"corpus app {rid} has no {abi} build")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def apk_abis(path):
    with zipfile.ZipFile(path) as z:
        libs = {}
        for n in z.namelist():
            m = re.fullmatch(r"lib/([^/]+)/([^/]+\.so)", n)
            if m:
                libs.setdefault(m.group(1), []).append(m.group(2))
    return {k: sorted(v) for k, v in sorted(libs.items())}


def apksigner():
    for base in (os.path.join(A, "compat", "sdk", "build-tools", "37.0.0"),
                 os.path.join(A, "toolchain", "openbook-update-sdk", "build-tools", "37.0.0")):
        p = os.path.join(base, "apksigner")
        if os.path.exists(p):
            return p
    raise Fail("no apksigner (scripts/compat/setup-toolchain.sh installs build-tools 37.0.0)")


def signer_digests(path):
    r = subprocess.run([apksigner(), "verify", "--print-certs", path], capture_output=True, text=True)
    if r.returncode:
        raise Fail(f"{os.path.basename(path)}: apksigner verify failed: {(r.stderr or r.stdout).strip()[-300:]}")
    return re.findall(r"certificate SHA-256 digest: ([0-9a-f]{64})", r.stdout)


def check_apk(row, path):
    """Problems with a fetched or built APK, as a list (empty: fine)."""
    problems = []
    if row["sha256"] != "-" and sha256_file(path) != row["sha256"]:
        problems.append("sha256 differs from the pin")
    abis = apk_abis(path)
    want = ABIS if row["abi"] == "fat" else (row["abi"],)
    for abi in want:
        if abi not in abis:
            problems.append(f"no lib/{abi}")
    if row["abi"] != "fat" and set(abis) - {row["abi"]}:
        problems.append(f"also carries {sorted(set(abis) - {row['abi']})}")
    if row["signer_sha256"] != "-":
        if row["signer_sha256"] not in signer_digests(path):
            problems.append("signer certificate differs from the pin")
    return problems


def cmd_list(rows):
    for r in rows:
        print(f"{r['id']:10} {r['abi']:10} {r['package']:28} {r['version_name']:16} {r['task']:14} {r['represents']}")
    return 0


def download(row, dest):
    tmp = dest + ".part"
    if row["source"].startswith("github:"):
        urls = [row["source"].split(":", 1)[1]]
    else:
        urls = [f"{base}/{row['file']}" for base in MIRRORS + FDROID]
    for url in urls:
        base = url.rsplit("/", 1)[0]
        try:
            with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as f:
                shutil.copyfileobj(resp, f, 1 << 20)
        except OSError as e:
            print(f"  {base}: {e}", file=sys.stderr)
            continue
        if sha256_file(tmp) == row["sha256"]:
            os.replace(tmp, dest)
            return base
        print(f"  {base}: sha256 mismatch, trying the next source", file=sys.stderr)
    if os.path.exists(tmp):
        os.remove(tmp)
    raise Fail(f"could not fetch a verified {row['file']}")


def cmd_fetch(rows):
    os.makedirs(STORE, exist_ok=True)
    report, bad = [], 0
    for r in rows:
        dest = os.path.join(STORE, r["file"])
        entry = {"id": r["id"], "abi": r["abi"], "file": r["file"]}
        if r["source"] == "fdroid" or r["source"].startswith("github:"):
            if not (os.path.exists(dest) and sha256_file(dest) == r["sha256"]):
                print(f"fetching {r['file']}")
                entry["from"] = download(r, dest)
        elif not os.path.exists(dest):
            entry["problems"] = [f"missing: build it with {r['source'].split(':', 1)[-1]}"]
            report.append(entry)
            bad += 1
            continue
        entry["sha256"] = sha256_file(dest)
        entry["problems"] = check_apk(r, dest)
        libs = sorted({l for v in apk_abis(dest).values() for l in v})
        entry["frameworks"] = AP.framework_hints(libs)
        entry["libraries"] = libs
        bad += bool(entry["problems"])
        report.append(entry)
        print(f"{'ok ' if not entry['problems'] else 'BAD'} {r['id']:10} {r['abi']:10} {r['file']}"
              f"{'  ' + '; '.join(entry['problems']) if entry['problems'] else ''}"
              f"{'  [' + ', '.join(entry['frameworks']) + ']' if entry['frameworks'] else ''}")
    with open(os.path.join(STORE, "FETCHED.json"), "w") as f:
        json.dump({"tsv_sha256": sha256_file(TSV), "at": AP.utc(), "apks": report}, f, indent=1)
    return 1 if bad else 0


# ---- installs, journalled per device so only what this tool installed is ever replaced or removed ----

class Journal:
    def __init__(self, path, device):
        self.path, self.device = path, device

    def _load(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path) as f:
            return json.load(f)

    def mine(self):
        return self._load().get(self.device, {})

    def put(self, pkg, entry):
        data = self._load()
        data.setdefault(self.device, {})[pkg] = entry
        self._write(data)

    def drop(self, pkg):
        data = self._load()
        data.get(self.device, {}).pop(pkg, None)
        if not data.get(self.device):
            data.pop(self.device, None)
        self._write(data)

    def _write(self, data):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, self.path)


def package_section(dump):
    """Only the 'Packages:' section of a dumpsys package dump: this package's own facts and permissions. The other
    sections can name other installed apps (Queries: lists which apps can see this one), and the dump is evidence that
    may be attached to an issue, so an owner's app names stay out of it (ANAL-384)."""
    out, keep = [], False
    for line in dump.splitlines():
        if line and not line[0].isspace() and line.rstrip().endswith(":"):
            keep = line.rstrip() == "Packages:"
        if keep:
            out.append(line)
    return "\n".join(out) + ("\n" if out else "")


def ungranted_runtime_permissions(text):
    """dumpsys package's 'runtime permissions:' lines with granted=false and not yet user-fixed."""
    out, on = [], False
    for line in text.splitlines():
        st = line.strip()
        if st == "runtime permissions:":
            on = True
            continue
        if on:
            m = re.match(r"([\w.]+): granted=(true|false)(?:, flags=\[(.*)\])?", st)
            if not m:
                on = False
                continue
            if m.group(2) == "false" and "USER_FIXED" not in (m.group(3) or ""):
                out.append(m.group(1))
    return out


PRESENT, ABSENT, UNKNOWN = "present", "absent", "unknown"


def package_state(dev, pkg):
    """present or absent from a package-manager answer that ran to completion; unknown when adb failed or timed
    out, pm failed or the answer was cut short. Every write needs a confirmed answer."""
    out, rc = AP.try_sh(dev, f"pm list packages {AP.q(pkg)}; echo \"@rc $?\"; echo @end", timeout=60)
    lines = out.splitlines() if rc is not None else []
    if rc != 0 or "@end" not in lines or "@rc 0" not in lines:
        return UNKNOWN
    return PRESENT if f"package:{pkg}" in lines else ABSENT


def installed_apk_sha256(dev, pkg):
    """sha256 of the package's installed base APK (Android keeps an installed APK byte for byte), or None when it
    can't be read."""
    out, rc = AP.try_sh(dev, f"p=$(pm path {AP.q(pkg)} | sed -n 's/^package://p' | head -1); "
                             "[ -n \"$p\" ] && sha256sum \"$p\"; echo @end", timeout=180)
    if rc != 0 or "@end" not in out.splitlines():
        return None
    m = re.match(r"([0-9a-f]{64})\s", out.strip())
    return m.group(1) if m else None


def ownership(dev, pkg, journal, rows):
    """Whether the installed PKG is this tool's test install: True, False, or None when that can't be established.
    Being in the journal isn't enough: the installed APK must also be one this tool installs for PKG (its pinned
    sha256, or the sha256 the journal recorded when it installed a local build), so a journal left stale by an owner
    reinstalling the app never lets the tool replace or remove the owner's copy."""
    entry = journal.mine().get(pkg)
    if not entry:
        return False, "not installed by this tool"
    sha = installed_apk_sha256(dev, pkg)
    if sha is None:
        return None, "can't read the installed APK"
    allowed = set(entry.get("apk_sha256s", [])) | {r["sha256"] for r in rows if r["package"] == pkg and r["sha256"] != "-"}
    if sha in allowed:
        return True, f"installed APK {sha[:12]} is this tool's"
    return False, f"installed APK {sha[:12]} isn't one this tool installs (someone reinstalled {pkg})"


def runtime_permissions(text):
    """{permission: 'granted=..., flags=[...]'} for every line of dumpsys package's runtime permissions: recorded
    after each install, so the two ABIs' runs can be shown to share the same permission state."""
    out, on = {}, False
    for line in text.splitlines():
        st = line.strip()
        if st == "runtime permissions:":
            on = True
            continue
        if on:
            m = re.match(r"([\w.]+): (granted=.*)", st)
            if not m:
                on = False
                continue
            out[m.group(1)] = m.group(2)
    return out


def cmd_install(dev, a, out, rows, journal):
    row = row_for(rows, a.id, a.abi)
    pkg = row["package"]
    apk = os.path.join(STORE, row["file"])
    if not os.path.exists(apk):
        raise Fail(f"{apk} missing: run 'arm-corpus.sh fetch' first")
    problems = check_apk(row, apk)
    if problems:
        raise Fail(f"{row['file']}: {'; '.join(problems)}")
    sha = sha256_file(apk)
    state = package_state(dev, pkg)
    if state == UNKNOWN:
        raise Fail(f"can't tell whether {pkg} is installed (adb or pm didn't answer): nothing changed")
    if state == PRESENT:
        own, why = ownership(dev, pkg, journal, rows)
        if own is None:
            raise Fail(f"{pkg} is installed and {why}: nothing changed")
        if not own:
            raise Invalid(f"{pkg} is installed and {why}: an owner's app is never replaced")
    AP.Gate(dev, a.idle_min, pkg)  # also: the app isn't running
    before = AP.app_facts(dev, pkg) if state == PRESENT else {}
    entry = dict(journal.mine().get(pkg, {}))
    entry.update({"id": a.id, "abi": a.abi, "state": "installing", "at": AP.utc(),
                  "apk_sha256s": sorted(set(entry.get("apk_sha256s", [])) | {sha})})
    journal.put(pkg, entry)  # first, so an interrupted install can still be recognised and removed
    args = ["install", "--no-incremental", "-r", "--abi", a.abi]
    if row["abi"] != "fat":
        args.append("-d")  # the other ABI's build of the same version has a different version code
    try:
        r = dev.run(*args, apk, timeout=600, check=False)
        install_out = r.stdout + r.stderr
        ok = r.returncode == 0 and "Success" in r.stdout
    except Fail as e:  # no answer: whether it installed is checked below
        install_out, ok = str(e), False
    AP.save(out, "install.txt", install_out)
    after = package_state(dev, pkg)
    if not ok:
        if after == ABSENT:
            journal.drop(pkg)  # confirmed: nothing of this tool's is installed
        raise Fail(f"adb install failed ({install_out.strip()[-300:]}); {pkg} is now {after}"
                   f"{'; the journal keeps it' if after != ABSENT else ''}")
    if after != PRESENT or installed_apk_sha256(dev, pkg) != sha:
        raise Fail(f"after adb install, {pkg} isn't confirmed installed with the APK installed; the journal keeps it")
    entry["state"] = "installed"
    journal.put(pkg, entry)
    # A permission prompt at the first start would sit on top of the app and swallow its process-cold starts. Every
    # runtime permission the test package hasn't been granted is left denied and marked user-fixed, so it never asks;
    # the same state for both ABIs, since it survives install -r.
    dump, rc = AP.try_sh(dev, f"dumpsys package {AP.q(pkg)}", timeout=60)
    if rc != 0:
        raise Fail(f"can't read {pkg}'s permissions")
    AP.save(out, "dumpsys-package.txt", package_section(dump))
    fixed = ungranted_runtime_permissions(dump)
    for perm in fixed:
        _, rc = AP.try_sh(dev, f"pm set-permission-flags {AP.q(pkg)} {AP.q(perm)} user-set user-fixed")
        if rc != 0:
            raise Fail(f"can't mark {perm} as user-fixed for {pkg}")
    dump_after, rc = AP.try_sh(dev, f"dumpsys package {AP.q(pkg)}", timeout=60)
    flags_after = runtime_permissions(dump_after) if rc == 0 else None
    if fixed and (not flags_after or any("USER_FIXED" not in flags_after.get(p, "") for p in fixed)):
        raise Fail(f"{pkg}: the permission flags didn't read back as user-fixed: {flags_after}")
    facts = AP.parse_dumpsys_package(dump_after, pkg) if rc == 0 else {}
    got = facts.get("primaryCpuAbi")
    res = {"id": a.id, "package": pkg, "abi_requested": a.abi, "primaryCpuAbi": got,
           "versionCode": facts.get("versionCode"), "versionName": facts.get("versionName"),
           "apk": row["file"], "apk_sha256": sha, "row_abi": row["abi"],
           "native_code": AP.native_code(got, apk_abis(apk)), "before": before or None,
           "permissions_denied_fixed": fixed, "permission_flags_after": flags_after}
    if got != a.abi:
        raise Fail(f"installed with primaryCpuAbi {got}, not {a.abi}")
    if str(facts.get("versionCode")) != row["version_code"] and row["source"] == "fdroid":
        raise Fail(f"installed versionCode {facts.get('versionCode')}, pinned {row['version_code']}")
    return res


def cmd_remove(dev, a, rows, journal):
    """Uninstall this tool's test installs. A journal entry goes only when the package is confirmed absent; an
    installed package that isn't this tool's APK any more is left alone and the claim on it dropped. Anything that
    can't be confirmed is listed under "unresolved" (the run then fails) and stays in the journal."""
    mine = journal.mine()
    ids = set(a.ids)
    todo = [p for p, e in mine.items() if not ids or e.get("id") in ids]
    res = {"removed": [], "not_installed": [], "left_alone": [], "unresolved": [],
           "not_ours": sorted(ids - {e.get("id") for e in mine.values()})}
    for pkg in sorted(todo):
        state = package_state(dev, pkg)
        if state == UNKNOWN:
            res["unresolved"].append(f"{pkg}: can't tell whether it is installed")
            continue
        if state == ABSENT:
            journal.drop(pkg)
            res["not_installed"].append(pkg)
            continue
        own, why = ownership(dev, pkg, journal, rows)
        if own is None:
            res["unresolved"].append(f"{pkg}: {why}")
            continue
        if not own:
            journal.drop(pkg)
            res["left_alone"].append(f"{pkg}: {why}")
            continue
        try:
            r = dev.run("uninstall", pkg, timeout=180, check=False)
            said = (r.stdout + r.stderr).strip()[-200:]
        except Fail as e:
            said = str(e)
        after = package_state(dev, pkg)
        if after == ABSENT:
            journal.drop(pkg)
            res["removed"].append(pkg)
        else:
            res["unresolved"].append(f"{pkg}: uninstall not confirmed ({after}; {said}); the journal keeps it")
    return res


# ---- executables ----

def parse_coremark(text):
    ips = re.search(r"Iterations/Sec\s*:\s*([\d.]+)", text)
    secs = re.search(r"Total time \(secs\)\s*:\s*([\d.]+)", text)
    return {"iterations_per_sec": float(ips.group(1)) if ips else None,
            "seconds": float(secs.group(1)) if secs else None,
            "valid": "Correct operation validated" in text and "ERROR" not in text}


def parse_simd(text):
    header, kernels = None, {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("tool") == "simd-bench":
            header = d
        elif "kernel" in d:
            kernels[d["kernel"]] = d
    return {"header": header, "kernels": kernels,
            "valid": bool(header) and bool(kernels) and all(k.get("ok", True) for k in kernels.values())
            and bool(header.get("aes_reference_ok"))}


# exe --perf-stat: simpleperf counts these for each run (the benchmark process and its children: an arm64 run's
# binfmt_misc runner, so translator and translated code together). The G14's PMU (Zen 5 and Zen 5c) has all four
# without multiplexing. Instructions against cycles tells a change in the code executed from a change in how fast the
# same code runs (layout, fetch); front-end stalls point at fetch. Neither alone proves a cause (ANAL-384).
PERF_EVENTS = ("cpu-cycles", "instructions", "branch-misses", "stalled-cycles-frontend")


def perf_wrap(cmd_line, events=PERF_EVENTS):
    """CMD_LINE under simpleperf stat (CSV on stdout after the benchmark's own output). simpleperf exits 0 whatever
    the benchmark returns, so the benchmark's own exit status is printed as '@wrc N' and read instead. No single
    quotes: run_workload puts this inside sh -c '...'."""
    return f'simpleperf stat --csv -e {",".join(events)} -- sh -c "{cmd_line}; echo @wrc \\$?"'


def parse_perf_stat(text):
    """simpleperf stat --csv lines ('22532752,cpu-cycles,2.75,GHz,') -> {event: count}, plus ipc when both cycles
    and instructions are there. None when no counter line was printed."""
    counts = {}
    for line in text.splitlines():
        m = re.match(r"\s*(\d+),([A-Za-z0-9_.:-]+),", line)
        if m and m.group(2) in PERF_EVENTS:
            counts[m.group(2)] = int(m.group(1))
    if not counts:
        return None
    if counts.get("cpu-cycles") and "instructions" in counts:
        counts["ipc"] = round(counts["instructions"] / counts["cpu-cycles"], 4)
    return counts


def perf_complete(perf, events=PERF_EVENTS):
    """Every requested counter is in the record. simpleperf leaves out an event it couldn't count, so a partial record
    is a failed measurement, never a run with zeros."""
    return perf is not None and all(isinstance(perf.get(e), int) for e in events)


def perf_run(text, valid):
    """exe --perf-stat, one run's output -> (its counters, whether the run counts): the benchmark's own validation,
    every requested counter, and the benchmark's exit status printed under simpleperf."""
    perf = parse_perf_stat(text)
    return perf, bool(valid) and perf_complete(perf) and "@wrc " in text


def run_rc(text):
    """The benchmark's exit status: '@wrc' (under simpleperf) when printed, else the wrapper's '@rc'."""
    m = re.search(r"@wrc (\d+)", text) or re.search(r"@rc (\d+)", text)
    return int(m.group(1)) if m else None


def parse_taskset(text):
    """toybox 'taskset -p PID' -> the mask as an int ('pid 123's current affinity mask: 4')."""
    m = re.search(r"affinity mask:\s*([0-9a-fA-F]+)", text)
    return int(m.group(1), 16) if m else None


def core_classes(power_text):
    """CPUs grouped by their top frequency (cpuinfo_max_freq), fastest first: on the G14 the Zen 5 and Zen 5c cores.
    One CPU of each group is picked: the highest-numbered, away from cpu0's interrupts. Without cpufreq (a VM) every
    online CPU is in one group, "all"."""
    groups = {}
    for line in power_text.splitlines():
        if not line.startswith("cpu "):
            continue
        kv = AP.kv_tokens(line)
        cpu = re.match(r"cpu cpu(\d+)", line)
        mk = AP.num(kv.get("max_khz"))
        if not cpu or kv.get("online") == "0":
            continue
        groups.setdefault(int(mk or 0), []).append(int(cpu.group(1)))
    out = []
    for i, (mk, cpus) in enumerate(sorted(groups.items(), reverse=True)):
        name = "all" if len(groups) == 1 else ("fast" if i == 0 else f"efficient{'' if len(groups) == 2 else i}")
        out.append({"class": name, "max_khz": mk or None, "cpus": sorted(cpus), "cpu": max(cpus)})
    return out


def run_order(rounds, classes, benches):
    """Every (round, class, bench, abi) once; the ABI order alternates by round, so neither ABI always runs first."""
    plan = []
    for rnd in range(rounds):
        abis = ABIS if rnd % 2 == 0 else ABIS[::-1]
        for c in classes:
            for b in benches:
                for abi in abis:
                    plan.append((rnd + 1, c, b, abi))
    return plan


BIN, OUTD = f"{D}/bin", f"{D}/out"


def gate_check(gate, where):
    """The idle gate's check, with a device that doesn't answer reported as an adb failure, not as input."""
    try:
        gate.check(where)
    except Invalid as e:
        if "activity None" in str(e):  # no activity token read at all: nobody touched it, adb didn't answer
            raise Fail(f"{where}: the device didn't answer the idle check (adb)") from e
        raise


def find_workloads(dev):
    """Pids of every process whose command line runs one of this tool's executables (a benchmark, its binfmt_misc
    runner or its wrapper shell), or None when that can't be established. The probing shell skips itself."""
    return parse_workloads(*AP.try_sh(dev, find_workloads_cmd()))


def find_workloads_cmd():
    # $$ (this shell) is always in /proc, so a scan that saw no process at all didn't read /proc: unknown, not none.
    return ("n=0; for p in /proc/[0-9]*; do [ -d \"$p\" ] || continue; n=$((n + 1)); [ \"${p#/proc/}\" = $$ ] && continue; "
            "case \"$(tr '\\0' ' ' < $p/cmdline 2>/dev/null)\" in "
            f"*{BIN}/*) echo \"@pid ${{p#/proc/}}\" ;; esac; done; echo \"@scanned $n\"; echo @end")


def parse_workloads(out, rc):
    lines = out.splitlines() if rc is not None else []
    if rc != 0 or "@end" not in lines:
        return None
    scanned = [l for l in lines if l.startswith("@scanned ")]
    if not scanned or scanned[0].split()[1] == "0":
        return None
    return [l.split()[1] for l in lines if l.startswith("@pid ")]


def stop_workloads(dev, why, wait=5.0):
    """TERM, then KILL to this tool's benchmark processes, each pid's command line checked again in the same shell
    right before its signal, until none is confirmed left (background jobs of a non-interactive shell ignore INT, so
    it isn't tried). Returns how it ended. dev.busy stays set (the device directory is kept) unless no process is
    confirmed left."""
    for sig in ("TERM", "KILL"):
        pids = find_workloads(dev)
        if pids == []:
            dev.busy = None
            return f"stopped ({why})" if sig != "TERM" else f"none running ({why})"
        if pids:
            AP.try_sh(dev, f"for p in {' '.join(pids)}; do case \"$(tr '\\0' ' ' < /proc/$p/cmdline 2>/dev/null)\" in "
                           f"*{BIN}/*) kill -{sig} $p ;; esac; done")
        end = time.time() + wait
        while time.time() < end:
            if find_workloads(dev) == []:
                dev.busy = None
                return f"stopped with SIG{sig} ({why})"
            time.sleep(0.5)
    left = find_workloads(dev)
    if left == []:
        dev.busy = None
        return f"stopped ({why})"
    dev.busy = (f"benchmark processes {', '.join(left)} survived KILL" if left else
                "can't confirm that the benchmark processes are gone (adb didn't answer)")
    return f"unresolved: {dev.busy}"


def run_workload(dev, gate, cmd_line, mask, outfile, timeout, poll=2.0, where=""):
    """Run one benchmark in the background on the device, pinned by MASK, its output in OUTFILE, and wait for it while
    checking the gate every POLL seconds. Input, an adb failure, a timeout or a signal stops the exact processes
    (stop_workloads) before the exception goes on. Returns the output."""
    # Only nohup goes to the background, with every stream redirected, so this adb call returns at once: a backgrounded
    # list ("cd ... && nohup ... &") would keep adb's output open for the whole benchmark.
    start = (f"cd {D} || exit 1; nohup taskset {mask} sh -c 'echo \"@mask $(taskset -p $$)\"; "
             f"echo \"@t0 $(cat /proc/uptime)\"; {cmd_line}; echo \"@rc $?\"; echo \"@t1 $(cat /proc/uptime)\"' "
             f"> {outfile} 2>&1 < /dev/null & echo \"@pid $!\"")
    try:
        dev.busy = "a benchmark is starting"  # until it is confirmed gone or confirmed never started
        out, rc = AP.try_sh(dev, start, timeout=30)
        if not (rc == 0 and re.search(r"@pid \d+", out)):
            pids = find_workloads(dev)
            if pids == []:
                dev.busy = None
                raise Fail(f"{where}: the benchmark didn't start ({out.strip()[-200:]})")
            if pids is None:
                raise Fail(f"{where}: the start wasn't answered and the device can't be checked")
            # Started although the answer was lost: adopted, and waited for like any other.
        deadline = time.time() + timeout
        while True:
            gate_check(gate, where)
            text, rc = AP.try_sh(dev, f"cat {outfile}; echo @end", timeout=30)
            if rc == 0 and "@rc " in text:
                break
            if time.time() > deadline:
                raise Fail(f"{where}: no result in {timeout} s")
            time.sleep(poll)
        # Finished: the wrapper is gone within moments; confirm before anything is removed.
        end = time.time() + 10
        while time.time() < end and find_workloads(dev) != []:
            time.sleep(0.5)
        if find_workloads(dev) != []:
            raise Fail(f"{where}: the benchmark wrote its result but its processes aren't confirmed gone")
        dev.busy = None
        return text.replace("\n@end", "")
    except BaseException as e:
        dev.notes.setdefault("workload", []).append(stop_workloads(dev, f"{where}: {str(e)[:120]}"))
        raise


def cleanup_device(dev):
    """Remove this tool's device directory, unless a benchmark of it may still run (dev.busy, found, or not
    checkable): then the directory stays and the reason is recorded."""
    if dev.busy:
        return f"skipped: {dev.busy}; {D} kept"
    pids = find_workloads(dev)
    if pids is None:
        dev.busy = "can't check for benchmark processes before removing their directory (adb failed)"
    elif pids:
        dev.notes.setdefault("workload", []).append(stop_workloads(dev, "found at clean-up"))
    if dev.busy:
        return f"skipped: {dev.busy}; {D} kept"
    _, rc = AP.try_sh(dev, f"rm -rf {D}")
    return "ok" if rc == 0 else f"failed: rm -rf {D} wasn't confirmed"


def cmd_exe(dev, a, out):
    gate = AP.Gate(dev, a.idle_min)
    if find_workloads(dev) != []:
        raise Fail("an earlier run's benchmark is still running, or that can't be checked: this run's clean-up stops "
                   "it if it can; then run exe again")
    dev.sh(f"mkdir -p {BIN} {OUTD}", check=False)
    files = {}
    for b in a.bench:
        for abi in ABIS:
            src = BENCH[b].format(abi=EXE_ABI[abi])
            if not os.path.exists(src):
                raise Fail(f"{src} missing ({'scripts/compat/build-probes.sh' if b == 'coremark' else 'scripts/perf/simd-bench/build.sh'})")
            dst = f"{BIN}/{b}-{EXE_ABI[abi]}"
            dev.run("push", src, dst)
            files[f"{b}-{abi}"] = {"sha256": sha256_file(src), "device": dst}
    dev.sh(f"chmod 755 {BIN}/*", check=False)
    # What makes an arm64 executable run here: the host is x86_64, so an aarch64 ELF that runs went through the
    # bridge's binfmt_misc runner (simd-bench also prints the architecture it was built for).
    bridge, _ = dev.sh("echo \"uname_m=$(uname -m)\"; echo \"abilist=$(getprop ro.product.cpu.abilist)\"; "
                       "echo \"native_bridge=$(getprop ro.dalvik.vm.native.bridge)\"; "
                       "ls /system/bin/berberis_program_runner* /system/etc/binfmt_misc 2>&1", check=False)
    AP.save(out, "bridge.txt", bridge)
    power_before, _ = dev.helper("power", check=False)
    AP.save(out, "power-before.txt", power_before)
    classes = core_classes(power_before)
    if not classes:
        raise Fail("no CPU found in the power read-out")
    if a.cpu_class:
        classes = [c for c in classes if c["class"] in a.cpu_class]
        if not classes:
            raise Fail(f"no core class {a.cpu_class}")
    runs = []
    for rnd, c, b, abi in run_order(a.rounds, classes, a.bench):
        exe = files[f"{b}-{abi}"]["device"]
        args = COREMARK_ARGS.format(iterations=a.iterations) if b == "coremark" else f"-r {a.repeats}"
        name = f"r{rnd}-{c['class']}-{b}-{abi}.txt"
        t0 = time.time()
        cmd_line = f"{exe} {args}"
        text = run_workload(dev, gate, perf_wrap(cmd_line) if a.perf_stat else cmd_line, format(1 << c["cpu"], "x"),
                            f"{OUTD}/{name}", a.timeout, a.poll, f"round {rnd}, {b} {abi} on cpu{c['cpu']}")
        AP.save(out, name, text)
        res = parse_coremark(text) if b == "coremark" else parse_simd(text)
        if b == "simd":
            res.pop("header", None)
        if a.perf_stat:
            res["perf"], res["valid"] = perf_run(text, res["valid"])
        runs.append({"round": rnd, "class": c["class"], "cpu": c["cpu"], "bench": b, "abi": abi,
                     "mask_ok": parse_taskset(text) == 1 << c["cpu"], "rc": run_rc(text),
                     "wall_s": round(time.time() - t0, 2), "file": name, **res})
        print(f"r{rnd} {c['class']:9} cpu{c['cpu']:<2} {b:8} {abi:9} "
              f"{'valid' if run_ok(runs[-1]) else 'INVALID'} mask={'ok' if runs[-1]['mask_ok'] else 'WRONG'}", flush=True)
    gate.check("after the last run")
    power_after, _ = dev.helper("power", check=False)
    AP.save(out, "power-after.txt", power_after)
    summary = summarize_exe(runs)
    if a.perf_stat:
        summary["perf"] = summarize_perf(runs)
    return {"files": files, "classes": classes, "runs": runs, "summary": summary, "perf_events": list(PERF_EVENTS) if a.perf_stat else None,
            "valid": all(run_ok(r) for r in runs) and summary["simd_same"]}


def run_ok(r):
    return bool(r.get("valid")) and bool(r.get("mask_ok")) and r.get("rc") == 0


def summarize_exe(runs):
    """Per core class and benchmark: each ABI's median, and translated speed over native speed (1.0 = native speed;
    CoreMark: arm64 iterations/s over x86_64's; simd-bench, per kernel: x86_64 time over arm64 time). Only valid runs
    count (run_ok: the benchmark's own validation, the CPU mask, exit 0); the others are counted as excluded. Checksum
    agreement is checked over every run that printed one."""
    import statistics
    out, simd_same = {}, True
    for key in sorted({(r["class"], r["bench"]) for r in runs}):
        cls, bench = key
        every = [r for r in runs if r["class"] == cls and r["bench"] == bench]
        sel = [r for r in every if run_ok(r)]
        excluded = {abi: sum(1 for r in every if r["abi"] == abi and not run_ok(r)) for abi in ABIS}
        if bench == "coremark":
            med = {}
            for abi in ABIS:
                v = [r["iterations_per_sec"] for r in sel if r["abi"] == abi and r["iterations_per_sec"]]
                med[abi] = statistics.median(v) if v else None
            ratio = med["arm64-v8a"] / med["x86_64"] if all(med.values()) else None
            out[f"{cls}/coremark"] = {"median_ips": med, "translated_over_native": ratio,
                                      "n": {abi: sum(1 for r in sel if r["abi"] == abi) for abi in ABIS},
                                      "excluded": excluded}
        else:
            kernels = sorted({k for r in every for k in r.get("kernels", {})})
            per = {}
            for k in kernels:
                t = {abi: [r["kernels"][k]["ns_per_elem_median"] for r in sel if r["abi"] == abi
                           and k in r["kernels"] and "ns_per_elem_median" in r["kernels"][k]] for abi in ABIS}
                sums = {r["kernels"][k].get("checksum") for r in every if k in r.get("kernels", {})} - {None}
                same = len(sums) <= 1
                simd_same &= same
                med = {abi: statistics.median(v) if v else None for abi, v in t.items()}
                per[k] = {"median_ns_per_elem": med, "checksums_agree": same,
                          "translated_over_native": (med["x86_64"] / med["arm64-v8a"]) if all(med.values()) else None,
                          "skipped": sorted({r["kernels"][k].get("skipped") for r in sel if k in r["kernels"]} - {None})}
            out[f"{cls}/simd"] = {"kernels": per, "n": {abi: sum(1 for r in sel if r["abi"] == abi) for abi in ABIS},
                                  "excluded": excluded}
    return {"by_class": out, "simd_same": simd_same}


def summarize_perf(runs):
    """exe --perf-stat: per core class, benchmark and ABI, the median of each counter and of IPC over valid runs.
    The counts cover the whole run (simd-bench: every kernel together), not one kernel."""
    import statistics
    out = {}
    for key in sorted({(r["class"], r["bench"], r["abi"]) for r in runs}):
        sel = [r for r in runs if (r["class"], r["bench"], r["abi"]) == key and run_ok(r) and r.get("perf")]
        med = {}
        for ev in (*PERF_EVENTS, "ipc"):
            v = [r["perf"][ev] for r in sel if ev in r["perf"]]
            med[ev] = statistics.median(v) if v else None
        out["/".join(key)] = {"n": len(sel), "median": med}
    return out


# ---- a corpus app's own benchmark ----

BENCH_LINE = re.compile(r"OPENBOOK_BENCH (start|level loaded|result|error)\b(.*)")
ENGINE_ARCH = {"arm64-v8a": "arm64", "x86_64": "x86_64"}


def number(v):
    """An int or a float if V reads as one, else V."""
    for t in (int, float):
        try:
            return t(v)
        except ValueError:
            pass
    return v


def parse_bench(text, pid=None):
    """The OPENBOOK_BENCH lines of a log: {"start": {...}, "level loaded": {...}, "result": {...}, "error": {...}},
    key=value pairs parsed, each with "log_pid", the pid logcat recorded for it. With PID, only lines that logcat
    recorded for that process and that report pid=PID themselves count: an earlier launch's lines never do."""
    out = {}
    for line in text.splitlines():
        m = BENCH_LINE.search(line)
        if not m:
            continue
        kv = {k: number(v) for k, v in re.findall(r"(\w+)=(\([^)]*\)|\S+)", m.group(2))}
        lp = re.match(r"\s*\S+\s+\S+\s+(\d+)\s+\d+\s", line)  # logcat threadtime: date time pid tid level tag
        kv["log_pid"] = int(lp.group(1)) if lp else None
        if pid is not None and (kv["log_pid"] != pid or kv.get("pid") != pid):
            continue
        if m.group(1) == "error":
            kv["text"] = m.group(2).strip()
        out[m.group(1)] = kv
    return out


def app_pids_cmd(pkg):
    """The shell command behind app_pids. The listing must prove itself: ps's own exit status is checked, its header
    must be there and the filter must succeed, or the command fails, so a failed listing never reads as "none"."""
    return ("l=$(ps -A -o PID,NAME) || { echo \"@ps-failed $?\"; exit 1; }; "
            "printf '%s\\n' \"$l\" | awk -v p=" + AP.q(pkg) + " 'NR == 1 && $1 == \"PID\" {print \"@header\"} "
            "NR > 1 && ($2 == p || index($2, p \":\") == 1) {print \"@pid \" $1}' || exit 1; echo @end")


def parse_app_pids(out, rc):
    lines = out.splitlines() if rc is not None else []
    if rc != 0 or "@end" not in lines or "@header" not in lines:
        return None
    return [l.split()[1] for l in lines if l.startswith("@pid ")]


def app_pids(dev, pkg):
    """Pids of PKG's processes (PKG and PKG:*), or None when that can't be established."""
    return parse_app_pids(*AP.try_sh(dev, app_pids_cmd(pkg)))


def stop_app(dev, pkg, tries=5):
    """Force-stop this tool's test package and confirm that none of its processes is left: True when confirmed,
    False when it can't be (adb failed, or a process stays)."""
    for _ in range(tries):
        AP.try_sh(dev, f"am force-stop {AP.q(pkg)}")
        if app_pids(dev, pkg) == []:
            return True
        time.sleep(1)
    return False


def mark_running(journal, pkg, token):
    entry = dict(journal.mine().get(pkg, {}))
    if token:
        entry["running"] = token
    else:
        entry.pop("running", None)
    journal.put(pkg, entry)


def recover_apps(dev, journal):
    """Stop any test package an earlier run started and couldn't confirm stopped (its journal entry says "running").
    The mark goes only once the stop is confirmed; otherwise the device is busy and the run fails."""
    done = []
    for pkg, entry in journal.mine().items():
        if not entry.get("running"):
            continue
        if stop_app(dev, pkg):
            mark_running(journal, pkg, None)
            done.append(f"{pkg}: stopped and confirmed (left running by run {entry['running']})")
        else:
            dev.busy = f"{pkg} was left running by an earlier run and still isn't confirmed stopped"
            done.append(f"{pkg}: still not confirmed stopped")
    if done:
        dev.notes.setdefault("recovered", []).extend(done)
    return done


def finish_app(dev, journal, pkg, run):
    """Every exit of a run: force-stop the app and confirm it; the journal's running mark goes only then."""
    if stop_app(dev, pkg):
        mark_running(journal, pkg, None)
        run["stopped"] = "confirmed"
        return True
    run["stopped"] = "not confirmed: the journal keeps it as running for the next command to stop"
    dev.busy = f"{pkg} isn't confirmed stopped"
    dev.notes.setdefault("apps", []).append(f"{pkg}: run {run.get('run_id')} not confirmed stopped")
    return False


def cmd_bench(dev, a, out, rows, journal):
    row = next((r for r in rows if r["id"] == a.id), None)
    if not row or row["task"] != "bench":
        raise Fail(f"corpus app {a.id!r} has no unattended benchmark (task 'bench')")
    pkg = row["package"]
    state = package_state(dev, pkg)
    if state != PRESENT:
        raise Fail(f"{pkg} is {state}: install it with 'arm-corpus.sh install' first")
    own, why = ownership(dev, pkg, journal, rows)
    if not own:
        raise Invalid(f"{pkg}: {why}; only this tool's own test install is benchmarked")
    gate = AP.Gate(dev, a.idle_min, pkg)
    facts = AP.app_facts(dev, pkg)
    abi = facts.get("primaryCpuAbi")
    comp_out, rc = AP.try_sh(dev, f"cmd package resolve-activity --brief {AP.q(pkg)} | tail -n 1")
    comp = comp_out.strip() if rc == 0 else ""
    if "/" not in comp:
        raise Fail(f"can't resolve {pkg}'s launcher activity ({comp!r})")
    res = {"package": pkg, "primaryCpuAbi": abi, "versionName": facts.get("versionName"),
           "apk_sha256": installed_apk_sha256(dev, pkg), "runs": []}
    for n in range(1, a.runs + 1):
        run_id = secrets.token_hex(8)  # names this run in the journal's running mark
        run = {"run": n, "run_id": run_id}
        res["runs"].append(run)
        _, rc = AP.try_sh(dev, "logcat -c")
        if rc != 0:
            raise Fail(f"run {n}: clearing the log failed, so this launch's lines couldn't be told apart: not started")
        mark_running(journal, pkg, run_id)  # before the launch: a lost run is still recognised and stopped
        try:
            am, rc = AP.try_sh(dev, f"am start -W -S -n {AP.q(comp)}", timeout=120)
            run["am_start"] = AP.parse_am_start(am) if rc is not None else {"ok": False, "error": am}
            if not run["am_start"].get("ok"):
                raise Fail(f"run {n}: am start didn't succeed: {run['am_start'].get('error') or am.strip()[-200:]}")
            # This launch's process: am start -S stopped any earlier one, so its pid tells this launch's lines apart.
            pids = None
            for _ in range(3):  # an unanswered listing is retried; a confirmed one is final
                pids = app_pids(dev, pkg)
                if pids is not None:
                    break
                time.sleep(1)
            if pids is None or len(pids) != 1:
                raise Fail(f"run {n}: can't establish the launched process ({'no answer' if pids is None else pids})")
            run["pid"] = int(pids[0])
            deadline = time.time() + a.timeout
            while True:
                gate_check(gate, f"during run {n}")
                text, rc = AP.try_sh(dev, "logcat -d -v threadtime -s godot:I", timeout=60)
                got = parse_bench(text, run["pid"]) if rc == 0 else {}
                if "result" in got or "error" in got:
                    break
                if time.time() > deadline:
                    raise Fail(f"run {n}: no result from the launched process (pid {run['pid']}) in {a.timeout} s")
                time.sleep(a.poll)
        except BaseException:
            finish_app(dev, journal, pkg, run)
            raise
        AP.save(out, f"run{n}-log.txt", text)
        confirmed = finish_app(dev, journal, pkg, run)
        run.update({k: v for k, v in got.items()})
        arch = (got.get("result") or got.get("start") or {}).get("arch")
        run["arch_ok"] = arch == ENGINE_ARCH.get(abi)
        run["valid"] = "start" in got and "result" in got and "error" not in got and run["arch_ok"] and confirmed
        r = got.get("result") or {}
        print(f"bench run {n} ({abi}, engine {arch}, pid {run['pid']}, {(got.get('start') or {}).get('adapter', '?')}): "
              f"{r.get('fps_avg')} fps avg, p99 {r.get('p99_ms')} ms, window {r.get('window_s')} s, "
              f"{'valid' if run['valid'] else 'INVALID'}", flush=True)
        if not confirmed:
            raise Fail(f"run {n}: {pkg} isn't confirmed stopped")
        time.sleep(a.settle)
    gate.check("after the last run")
    res["valid"] = all(r["valid"] for r in res["runs"])
    return res


# ---- main ----

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial")
    ap.add_argument("--adb", default=os.environ.get("ADB", "adb"))
    ap.add_argument("--journal", help="the host file recording what this tool installed, per device")
    ap.add_argument("--idle-min", type=float, default=10.0)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    sub.add_parser("fetch")
    p = sub.add_parser("install")
    p.add_argument("out")
    p.add_argument("id")
    p.add_argument("--abi", required=True, choices=ABIS)
    p = sub.add_parser("remove")
    p.add_argument("out")
    p.add_argument("ids", nargs="*")
    p = sub.add_parser("exe")
    p.add_argument("out")
    p.add_argument("--bench", action="append", choices=sorted(BENCH), help="default: both")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--iterations", type=int, default=600000, help="CoreMark iterations, as run-bench.sh")
    p.add_argument("--repeats", type=int, default=5, help="simd-bench timed runs per kernel")
    p.add_argument("--cpu-class", action="append", help="only these core classes (fast, efficient, all)")
    p.add_argument("--timeout", type=int, default=900, help="seconds for one benchmark run")
    p.add_argument("--poll", type=float, default=2.0, help="seconds between gate checks while a benchmark runs")
    p.add_argument("--perf-stat", action="store_true",
                   help=f"count {', '.join(PERF_EVENTS)} for each run with simpleperf stat")
    p = sub.add_parser("bench")
    p.add_argument("out")
    p.add_argument("id")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--timeout", type=int, default=300, help="seconds for one run to print its result")
    p.add_argument("--poll", type=float, default=2.0, help="seconds between gate checks while it runs")
    p.add_argument("--settle", type=float, default=10.0, help="seconds between runs")
    a = ap.parse_args()
    rows = load_corpus()
    if a.command == "list":
        return cmd_list(rows)
    if a.command == "fetch":
        return cmd_fetch(rows)
    if a.command == "exe" and not a.bench:
        a.bench = sorted(BENCH)
    if not a.serial or not a.journal:
        ap.error("--serial and --journal are required (arm-corpus.sh gives them)")

    def on_signal(sig, _):
        for s2 in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            signal.signal(s2, signal.SIG_IGN)
        raise KeyboardInterrupt(f"signal {sig}")
    for s in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(s, on_signal)

    dev = AP.Device(a.serial, a.adb)
    AP.D = D  # app-perf's helpers (gate, power read-out) run from this tool's own device directory
    out = AP.newdir(a.out)
    run = {"command": a.command, "args": {k: v for k, v in vars(a).items() if k not in ("adb", "serial", "journal")},
           "tool": AP.tool_rev(), "tsv_sha256": sha256_file(TSV), "start": AP.utc(),
           "serial_kind": "network" if ":" in a.serial else "local"}
    status = 0
    try:
        AP.setup(dev)
        run["device"] = AP.identity(dev)
        journal = Journal(a.journal, AP.device_identity(dev))
        recover_apps(dev, journal)
        if dev.busy:
            raise Fail(f"recovery: {dev.busy}")
        if a.command == "install":
            run["result"] = cmd_install(dev, a, out, rows, journal)
        elif a.command == "remove":
            run["result"] = cmd_remove(dev, a, rows, journal)
            if run["result"]["unresolved"]:
                status = FAILED
        elif a.command == "bench":
            run["result"] = cmd_bench(dev, a, out, rows, journal)
            if not run["result"]["valid"]:
                status = FAILED
        elif a.command == "exe":
            run["result"] = cmd_exe(dev, a, out)
            if not run["result"]["valid"]:
                status = FAILED
        run["outcome"] = "ok" if status == 0 else (
            "failed: not every removal was confirmed" if a.command == "remove" else "failed: a run's result didn't validate")
    except Invalid as e:
        run["outcome"], status = f"invalid: {e}", INVALID
    except (Fail, KeyboardInterrupt) as e:
        run["outcome"], status = f"failed: {e}", FAILED
    finally:
        try:
            run["cleanup"] = cleanup_device(dev)
            if dev.busy and status == 0:
                status = FAILED
        except Fail as e:
            run["cleanup"] = f"failed: {e}"
        if dev.notes:
            run["device_notes"] = dev.notes
        run["end"] = AP.utc()
        with open(os.path.join(out, "run.json"), "w") as f:
            json.dump(run, f, indent=1)
    print(f"{a.command}: {run['outcome']} -> {out}/run.json")
    return status


if __name__ == "__main__":
    sys.exit(main())
