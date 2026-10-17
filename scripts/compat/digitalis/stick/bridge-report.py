#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Report of an ARM-apps check run (ANAL-200, the bridge add-on) from a live stick's openbook/logs/live-NNN/ folder.

Reads addon-bridge.txt (run.sh's output), addon-bridge-unpack.txt and addon-bridge-out.tar (run.sh's OUT_DIR: facts,
the bridge self-check, the probe's results per ABI, CoreMark), and writes report-bridge.json and report-bridge.md
into the folder (or --out DIR). Verdicts:
  addon_ran        the payload unpacked, its checksums matched and run.sh finished
  bridge_check     all of openbook_bridge_check's results ok (arm64 exec, ID registers, FRECPE/FRSQRTE, CRC32/NEON)
  probe_x86_64     the native control finished with no failure
  probe_arm64      the arm64 probe finished as an arm64-v8a app, and failed no group beyond the two known
                   semantic differences (isa: x86 NaN rules; signals: SIGILL si_code; docs/digitalis.md)
  coremark_valid   every CoreMark run passed its CRC validation
Ratios: CoreMark translated arm64 / native x86_64, medians of the rounds, for the executables and in the app.

  bridge-report.py LIVE_DIR [--out DIR]       Run with python3 -I.
"""
import argparse
import csv
import io
import json
import os
import re
import statistics
import tarfile

KNOWN_ARM64_FAILS = {"isa", "signals"}


def out_files(d):
    """run.sh's OUT_DIR from addon-bridge-out.tar (possibly cut short by live-init's size cap)."""
    files = {}
    p = os.path.join(d, "addon-bridge-out.tar")
    if not os.path.exists(p):
        return files
    try:
        with tarfile.open(p) as t:
            for m in t:
                if m.isfile():
                    files[os.path.normpath(m.name)] = t.extractfile(m).read()
    except (tarfile.TarError, EOFError):
        pass
    return files


def text(files, name):
    return files.get(name, b"").decode("utf-8", "replace")


def probe(files, abi):
    t = text(files, f"probe-{abi}.txt")
    res = {"started": None, "done": None, "pass": [], "fail": {}, "skip": [], "summary": {}}
    for line in t.splitlines():
        if "PROBE_START " in line:
            res["started"] = line.split("PROBE_START ", 1)[1].strip()
        m = re.search(r"PROBE_RESULT (\S+) (PASS|FAIL|SKIP)\s?(.*)", line)
        if m:
            name, st, rest = m.groups()
            if st == "PASS":
                res["pass"].append(name)
            elif st == "SKIP":
                res["skip"].append(name)
            else:
                res["fail"][name] = rest[:300]
        m = re.search(r"PROBE_DONE pass=(\d+) fail=(\d+) skip=(\d+)", line)
        if m:
            res["done"] = dict(zip(("pass", "fail", "skip"), map(int, m.groups())))
        if line.startswith("PROBE_SUMMARY "):
            res["summary"] = dict(kv.split("=", 1) for kv in line.split()[1:] if "=" in kv)
    return res


def bench(files):
    rows = list(csv.DictReader(io.StringIO(text(files, "bench.csv"))))
    med, out = {}, {"rows": rows, "median_iter_per_sec": {}, "ratio": {}}
    for mode in ("exe", "apk"):
        for abi in ("x86_64", "arm64-v8a"):
            v = [float(r["iter_per_sec"]) for r in rows if r["mode"] == mode and r["abi"] == abi and r["iter_per_sec"]]
            if v:
                med[(mode, abi)] = statistics.median(v)
                out["median_iter_per_sec"][f"{mode} {abi}"] = round(med[(mode, abi)], 1)
        if (mode, "x86_64") in med and (mode, "arm64-v8a") in med:
            out["ratio"][mode] = round(med[(mode, "arm64-v8a")] / med[(mode, "x86_64")], 3)
    out["valid"] = bool(rows) and all(r["valid"] == "yes" and r["iter_per_sec"] for r in rows)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--out")
    a = ap.parse_args()
    d, out = a.dir, a.out or a.dir
    files = out_files(d)
    run_txt = open(os.path.join(d, "addon-bridge.txt"), errors="replace").read() \
        if os.path.exists(os.path.join(d, "addon-bridge.txt")) else ""
    unpack = open(os.path.join(d, "addon-bridge-unpack.txt"), errors="replace").read() \
        if os.path.exists(os.path.join(d, "addon-bridge-unpack.txt")) else ""
    summary = json.load(open(os.path.join(d, "summary.json"))) if os.path.exists(os.path.join(d, "summary.json")) else {}
    facts = dict(l.split(": ", 1) if ": " in l else l.split("=", 1) for l in text(files, "facts.txt").splitlines()
                 if ": " in l or "=" in l)
    checks = [json.loads(l) for l in text(files, "bridge-check.txt").splitlines() if l.startswith("{")]
    pr = {abi: probe(files, abi) for abi in ("x86_64", "arm64")}
    b = bench(files)
    arm = pr["arm64"]
    unexpected = sorted(set(arm["fail"]) - KNOWN_ARM64_FAILS)
    addon = summary.get("addon") if isinstance(summary.get("addon"), dict) else {}
    v = {
        "addon_ran": bool(files) and "file(s) OK" in unpack and "done:" in run_txt and addon.get("rc", 0) == 0,
        "bridge_check": len(checks) >= 4 and all(c.get("ok") for c in checks),
        "probe_x86_64": bool(pr["x86_64"]["done"]) and pr["x86_64"]["done"]["fail"] == 0,
        # The app was installed as arm64-v8a and its Java side sees that ABI (Build.CPU_ABI), so its native code ran
        # through the bridge. libberberis is mapped in every zygote child, x86_64 ones too, so maps prove nothing.
        "probe_arm64": bool(arm["done"]) and not unexpected and arm["summary"].get("primary_cpu_abi") == "arm64-v8a"
                       and "cpu_abi=arm64-v8a" in (arm["started"] or ""),
        "coremark_valid": b["valid"],
    }
    rep = {"schema": "openbook-bridge-report/1", "dir": os.path.abspath(d),
           "fingerprint": facts.get("ro.build.fingerprint"), "model": facts.get("ro.product.model"),
           "cpu": facts.get("cpu"), "cpu_flags": facts.get("cpu flags (translator-relevant)"),
           "cpufreq": facts.get("cpufreq"), "platform_profile": facts.get("platform_profile"),
           "power": facts.get("power"), "selinux": facts.get("ro.boot.selinux"),
           "addon": addon,
           "verdicts": v, "bridge_check": checks,
           "probe": {abi: {"done": p["done"], "fail": p["fail"], "skip": p["skip"], "summary": p["summary"],
                           "start": p["started"]} for abi, p in pr.items()},
           "probe_arm64_unexpected_fails": unexpected,
           "coremark": {k: b[k] for k in ("median_iter_per_sec", "ratio", "valid")}}
    os.makedirs(out, exist_ok=True)
    json.dump(rep, open(os.path.join(out, "report-bridge.json"), "w"), indent=1)
    L = [f"# ARM apps check: {rep['model']}", "",
         f"- build: `{rep['fingerprint']}`", f"- CPU: {rep['cpu']}; translator-relevant flags: {rep['cpu_flags']}",
         f"- cpufreq: {rep['cpufreq']}; platform profile: {rep['platform_profile']}; {rep['power']}", "",
         "| Verdict | Result |", "|---|---|"]
    L += [f"| {k} | {'PASS' if ok else 'FAIL'} |" for k, ok in v.items()]
    L += ["", "| Probe | Done | Failed groups |", "|---|---|---|"]
    for abi, p in pr.items():
        dn = p["done"]
        done = "{pass} pass / {fail} fail / {skip} skip".format(**dn) if dn else "not finished"
        L.append(f"| {abi} | {done} | {', '.join(sorted(p['fail'])) or '-'} |")
    L += ["", "| CoreMark | it/s (median) |", "|---|---|"]
    L += [f"| {k} | {x:,.0f} |" for k, x in b["median_iter_per_sec"].items()]
    L += [""] + [f"- **{m}: arm64 / x86_64 = {r}**" for m, r in b["ratio"].items()]
    open(os.path.join(out, "report-bridge.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    raise SystemExit(0 if all(v.values()) else 1)


if __name__ == "__main__":
    main()
