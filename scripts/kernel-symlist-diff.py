#!/usr/bin/env python3
"""Measure what a device KMI symbol list adds to the stock GKI exports, overall and per vendor module.

usage: kernel-symlist-diff.py NEW_LIST STOCK_ABI_SYMBOLLIST DIST VENDOR_MODULES_LIST [--report OUT.md] [--added OUT.txt]

  NEW_LIST              e.g. common/gki/x86_64/symbols/anybook_amd
  STOCK_ABI_SYMBOLLIST  abi_symbollist of the stock GKI build (all stock lists merged)
  DIST                  dist with the vendor modules (*.ko)
  VENDOR_MODULES_LIST   one vendor module file name per line

Per module: the symbols it imports from vmlinux or GKI modules (its undefined symbols minus what other
vendor modules export), and how many of those the stock GKI does not export. That second number is what
keeps the module from loading on the stock kernel.
"""
import argparse
import os
import subprocess


def syms(path):
    return {l.strip() for l in open(path) if l.startswith("  ")}


def nm(ko, undef):
    """Undefined symbols of ko, or (undef=False) the symbols it exports."""
    cmd = ["nm", "-u", ko] if undef else ["nm", ko]
    lines = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.splitlines()
    if undef:
        return {l.split()[-1] for l in lines if l.strip()}
    return {l.split()[-1][len("__ksymtab_"):] for l in lines if l.split() and l.split()[-1].startswith("__ksymtab_")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("new")
    ap.add_argument("stock")
    ap.add_argument("dist")
    ap.add_argument("vendor_list")
    ap.add_argument("--report")
    ap.add_argument("--added")
    a = ap.parse_args()
    new, stock = syms(a.new), syms(a.stock)
    added = sorted(new - stock)
    vendor = [l.strip() for l in open(a.vendor_list) if l.strip() and not l.startswith("#")]
    kos = {m: os.path.join(a.dist, m) for m in vendor if os.path.exists(os.path.join(a.dist, m))}
    vexp = set()
    for ko in kos.values():
        vexp |= nm(ko, False)
    rows = []
    for m, ko in sorted(kos.items()):
        imp = nm(ko, True) - vexp
        miss = imp - stock
        rows.append((m, len(imp), len(miss), sorted(miss)))
    rows.sort(key=lambda r: -r[2])
    out = ["# KMI symbol list diff: anybook_amd vs the stock GKI exports", "",
           f"- `anybook_amd` lists {len(new)} symbols; {len(new & stock)} are already exported by the stock GKI, "
           f"**{len(added)} are new exports**.",
           f"- Stock GKI KMI list: {len(stock)} symbols; with `anybook_amd`: {len(stock | new)}.",
           f"- Vendor modules with at least one import the stock GKI lacks: {sum(1 for r in rows if r[2])} of {len(rows)}.",
           "", "| module | imports from vmlinux / GKI modules | not exported by stock GKI |", "|---|---|---|"]
    out += [f"| {m} | {i} | {n} |" for m, i, n, _ in rows]
    if a.report:
        open(a.report, "w").write("\n".join(out) + "\n")
    if a.added:
        open(a.added, "w").write("".join(s + "\n" for s in added))
    print("\n".join(out[:6]))
    for m, i, n, miss in rows[:5]:
        print(f"  {m}: {n} of {i} imports missing from stock")


if __name__ == "__main__":
    main()
