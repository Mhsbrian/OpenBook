#!/usr/bin/env python3
"""Check that vendor modules match the kernel they ship with: vermagic, symbol CRCs and KMI symbol use.

usage: kernel-modules-check.py DIST VENDOR_MODULES_LIST [--report OUT.md] [--tsv OUT.tsv]

  DIST                 dist dir of the mixed build (scripts/kernel-build.sh): bzImage, vmlinux.symvers,
                       abi_symbollist, linux_banner.txt, the GKI modules and the vendor modules
  VENDOR_MODULES_LIST  file with one vendor module file name per line (e.g. amdgpu.ko); every other
                       .ko in DIST is treated as a GKI module

For every vendor module:
  vermagic  must start with the kernel release from linux_banner.txt, followed by the GKI's flags
  CRCs      each symbol in __versions (`modprobe --dump-modversions`) that vmlinux exports must carry
            the CRC from vmlinux.symvers; a mismatch means the module was built against other headers
  imports   each undefined symbol must be exported by vmlinux, a GKI module or another vendor module
  KMI       vendor modules are unsigned, so under MODULE_SIG_PROTECT they may only import symbols on
            the KMI list (abi_symbollist) from vmlinux and GKI modules
Needs modinfo/modprobe (kmod) and nm (binutils). Exit status 1 on any failure.
"""
import argparse
import collections
import os
import re
import subprocess
import sys


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def exports(ko):
    out = set()
    for line in run("nm", ko).splitlines():
        p = line.split()
        if len(p) >= 2 and p[-1].startswith("__ksymtab_"):
            out.add(p[-1][len("__ksymtab_"):])
    return out


def undefined(ko):
    return {l.split()[-1] for l in run("nm", "-u", ko).splitlines() if l.strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dist")
    ap.add_argument("vendor_list")
    ap.add_argument("--report")
    ap.add_argument("--tsv")
    a = ap.parse_args()
    d = a.dist
    release = open(os.path.join(d, "linux_banner.txt")).read().split("Linux version ", 1)[1].split()[0]
    symvers = {}
    for line in open(os.path.join(d, "vmlinux.symvers")):
        crc, sym = line.split()[:2]
        symvers[sym] = int(crc, 16)
    kmi = {l.strip() for l in open(os.path.join(d, "abi_symbollist")) if l.startswith("  ")}
    vendor = [l.strip() for l in open(a.vendor_list) if l.strip() and not l.startswith("#")]
    allko = sorted(f for f in os.listdir(d) if f.endswith(".ko"))
    gki = [f for f in allko if f not in set(vendor)]
    gki_exp = {s: f for f in gki for s in exports(os.path.join(d, f))}
    ven_exp = {s: f for f in vendor for s in exports(os.path.join(d, f))}

    flags = None
    fails = collections.defaultdict(list)
    rows = []
    for f in vendor:
        ko = os.path.join(d, f)
        if not os.path.exists(ko):
            fails[f].append("missing from dist")
            continue
        mi = {}
        for line in run("modinfo", ko).splitlines():
            k, _, v = line.partition(":")
            mi.setdefault(k.strip(), v.strip())
        vm = mi.get("vermagic", "")
        rel, _, fl = vm.partition(" ")
        flags = flags or fl
        if rel != release:
            fails[f].append(f"vermagic release {rel!r} != kernel {release!r}")
        if fl != flags:
            fails[f].append(f"vermagic flags {fl!r} differ from {flags!r}")
        crc_bad = []
        for line in run("modprobe", "--dump-modversions", ko).splitlines():
            crc, sym = line.split()[:2]
            if sym in symvers and int(crc, 16) != symvers[sym]:
                crc_bad.append(sym)
        if crc_bad:
            fails[f].append(f"{len(crc_bad)} CRC mismatches vs vmlinux.symvers, e.g. {crc_bad[:3]}")
        und = undefined(ko)
        from_vmlinux = {s for s in und if s in symvers}
        from_gki = {s for s in und if s not in symvers and s in gki_exp}
        from_vendor = {s for s in und if s not in symvers and s not in gki_exp and s in ven_exp}
        unresolved = sorted(und - from_vmlinux - from_gki - from_vendor)
        unlisted = sorted(s for s in from_vmlinux | from_gki if s not in kmi)
        if unresolved:
            fails[f].append(f"{len(unresolved)} unresolved symbols, e.g. {unresolved[:4]}")
        if unlisted:
            fails[f].append(f"{len(unlisted)} imports not on the KMI list, e.g. {unlisted[:4]}")
        rows.append(dict(module=f, vermagic=vm, license=mi.get("license", ""), intree=mi.get("intree", ""),
                         depends=mi.get("depends", ""), vmlinux=len(from_vmlinux), gki=len(from_gki),
                         vendor=len(from_vendor), firmware=len(run("modinfo", "-F", "firmware", ko).split()),
                         status="FAIL" if fails[f] else "ok"))

    out = [f"# Vendor module check: {os.path.basename(os.path.normpath(d))}", "",
           f"Kernel release `{release}`; {len(vendor)} vendor modules, {len(gki)} GKI modules in the dist; "
           f"{len(symvers)} vmlinux exports; {len(kmi)} KMI-listed symbols.", "",
           f"vermagic expected: `{release} {flags or '?'}`", "",
           f"Result: {sum(r['status'] == 'ok' for r in rows)} ok, {len([f for f in vendor if fails[f]])} failing.", ""]
    for f in vendor:
        for msg in fails[f]:
            out.append(f"- FAIL `{f}`: {msg}")
    out += ["", "| module | license | intree | imports vmlinux / GKI mod / vendor mod | MODULE_FIRMWARE | status |",
            "|---|---|---|---|---|---|"]
    out += [f"| {r['module']} | {r['license']} | {r['intree']} | {r['vmlinux']} / {r['gki']} / {r['vendor']} | "
            f"{r['firmware']} | {r['status']} |" for r in rows]
    text = "\n".join(out) + "\n"
    if a.report:
        open(a.report, "w").write(text)
    if a.tsv:
        with open(a.tsv, "w") as o:
            keys = list(rows[0]) if rows else []
            o.write("\t".join(keys) + "\n")
            for r in rows:
                o.write("\t".join(str(r[k]) for k in keys) + "\n")
    print("\n".join(out[:8 + sum(len(v) for v in fails.values())]))
    return 1 if any(fails.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
