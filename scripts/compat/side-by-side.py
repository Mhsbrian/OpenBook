#!/usr/bin/env python3
"""Side-by-side Markdown tables of two run-matrix.sh runs under different native bridges (ANAL-181).

Usage: side-by-side.py <label-A> <run-dir-A> <label-B> <run-dir-B>
Prints three tables: per-APK verdicts, per-probe-test status (with the failed checks), and the probe
checks whose status differs. Values come straight from results.csv and probe-results.csv.
"""
import csv
import re
import sys


def load(d):
    res = {r["id"]: r for r in csv.DictReader(open(f"{d}/results.csv", encoding="utf-8"))}
    probes = {}
    for r in csv.DictReader(open(f"{d}/probe-results.csv", encoding="utf-8")):
        probes[(r["id"], r["test"])] = r
    return res, probes


def verdict(r):
    if r is None:
        return "—"
    v = r["verdict"]
    if r["kind"] == "probe" and r["install"] == "ok":
        v += f" {r['probe_pass']}/{r['probe_fail']}/{r['probe_skip']}"
    if v.startswith(("CRASH", "RUNS_WITH_CRASH")) and r["crash_signature"]:
        v += f": `{r['crash_signature'][:90]}`"
    if r["install"] not in ("ok",):
        v += f" `{r['install']}`"
    return v


def failed(r):
    if r is None:
        return "—"
    m = re.search(r"failed=(\S+)", r["detail"])
    return r["status"] + (f" ({m.group(1).replace(';', ', ')})" if m and r["status"] == "FAIL" else "")


def main(la, a, lb, b):
    ra, pa = load(a)
    rb, pb = load(b)
    print(f"| APK | ABI | {la} | {lb} |")
    print("|---|---|---|---|")
    for i in sorted(set(ra) | set(rb), key=lambda k: (k.startswith("probe") is False, k)):
        r = ra.get(i) or rb.get(i)
        abi = r["role"].replace("-only", "").replace("-control", " control")
        print(f"| {r['package']} {r['version']} | {abi} | {verdict(ra.get(i))} | {verdict(rb.get(i))} |")
    print()
    print(f"| Probe | Test | {la} | {lb} |")
    print("|---|---|---|---|")
    for k in sorted(set(pa) | set(pb)):
        if k[1] == "load":
            continue
        print(f"| {k[0]} | `{k[1]}` | {failed(pa.get(k))} | {failed(pb.get(k))} |")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
