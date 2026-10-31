#!/usr/bin/env python3
"""Check that two run-matrix.sh runs agree (ANAL-180 reproducibility check).

Compares the outcome columns of results.csv per APK and the status of every probe test, ignoring
timings, PIDs, hashes of re-signed probe APKs and other values that legitimately change between runs.
Usage: compare-runs.py <run-dir-A> <run-dir-B>   (exit 1 if any outcome differs)
"""
import csv
import sys

OUTCOME = ["install", "primary_abi", "launch", "alive", "native_bridge", "verdict", "probe_pass", "probe_fail", "probe_skip"]


def crashed(r):
    return "yes" if int(r["java_crashes"] or 0) + int(r["native_crashes"] or 0) > 0 else "no"


def load(d):
    res = {r["id"]: r for r in csv.DictReader(open(f"{d}/results.csv", encoding="utf-8"))}
    probes = {(r["id"], r["test"]): r["status"] for r in csv.DictReader(open(f"{d}/probe-results.csv", encoding="utf-8"))}
    return res, probes


def main(a, b):
    ra, pa = load(a)
    rb, pb = load(b)
    diffs = []
    for i in sorted(set(ra) | set(rb)):
        if i not in ra or i not in rb:
            diffs.append(f"{i}: only in {'A' if i in ra else 'B'}")
            continue
        for c in OUTCOME:
            if ra[i][c] != rb[i][c]:
                diffs.append(f"{i}: {c} {ra[i][c]!r} -> {rb[i][c]!r}")
        if crashed(ra[i]) != crashed(rb[i]):
            diffs.append(f"{i}: crashed {crashed(ra[i])} -> {crashed(rb[i])}")
    for k in sorted(set(pa) | set(pb)):
        if pa.get(k) != pb.get(k):
            diffs.append(f"{k[0]} / {k[1]}: {pa.get(k)} -> {pb.get(k)}")
    print(f"APKs compared: {len(set(ra) & set(rb))}, probe tests compared: {len(set(pa) & set(pb))}, "
          f"outcome columns: {', '.join(OUTCOME)}, crashed")
    print("\n".join(diffs) if diffs else "identical outcomes")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
