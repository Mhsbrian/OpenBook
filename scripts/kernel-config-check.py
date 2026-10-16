#!/usr/bin/env python3
"""Check that a mixed-build vendor .config only adds modules on top of its GKI .config.

usage: kernel-config-check.py GKI_CONFIG DEVICE_CONFIG [--report OUT.md]

Every symbol whose value differs between the two configs is put in one class:
  module      n -> m: a new module, the normal vendor-module case.
  option      n -> y, a string or a number: an option the new modules read (DRM_AMD_DC=y,
              BT_HCIBTUSB_MTK=y, ...), or a menu that only gates them (WLAN_VENDOR_MEDIATEK).
  Built-in code can still test either class with IS_ENABLED(CONFIG_X); Kconfig cannot show that. The
  vmlinux equivalence build (scripts/kernel-amd-integrity.sh) finds those cases.
  build-only  symbols Kleaf sets differently for GKI and mixed builds, or that only steer the build
              (signing, export trimming, tool versions).
  CHANGED     the GKI already sets the symbol and the device config changes it. That alters code
              vmlinux or a GKI module is built from, so it is an error.
Exit status is 1 when anything is CHANGED.
"""
import argparse
import os
import re
import sys

# Kleaf manages these differently in mixed (device) builds than in the GKI build.
BUILD_ONLY = {
    "CONFIG_MODULE_SIG_ALL": "vendor modules are not signed by the device build; Makefile-only",
    "CONFIG_MODULE_SIG_PROTECT": "enforced by vmlinux, which comes from the GKI build",
    "CONFIG_MODULE_SIG_PROTECT_LIST": "input for the GKI build's protected-module list",
    "CONFIG_TRIM_UNUSED_KSYMS": "export trimming is done by the GKI build",
    "CONFIG_UNUSED_KSYMS_WHITELIST": "export trimming is done by the GKI build",
    "CONFIG_PAHOLE_VERSION": "version of the pahole that ran Kconfig; feeds BTF generation only",
}


def load(path):
    vals = {}
    for line in open(path):
        m = re.match(r"^(CONFIG_\w+)=(.*)$", line)
        if m:
            vals[m[1]] = m[2]
            continue
        m = re.match(r"^# (CONFIG_\w+) is not set$", line)
        if m:
            vals[m[1]] = "n"
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gki")
    ap.add_argument("device")
    ap.add_argument("--report")
    a = ap.parse_args()
    g, d = load(a.gki), load(a.device)
    rows = {"module": [], "option": [], "build-only": [], "CHANGED": []}
    for sym in sorted(set(g) | set(d)):
        old, new = g.get(sym, "n"), d.get(sym, "n")
        if old == new:
            continue
        if sym in BUILD_ONLY:
            rows["build-only"].append((sym, old, new, BUILD_ONLY[sym]))
        elif old == "n" and new == "m":
            rows["module"].append((sym, old, new, ""))
        elif old == "n":
            rows["option"].append((sym, old, new, ""))
        else:
            rows["CHANGED"].append((sym, old, new, "GKI value changed"))
    out = [f"# Config check: {os.path.basename(a.device)} vs {os.path.basename(a.gki)}", "",
           "| class | count |", "|---|---|"]
    out += [f"| {k} | {len(v)} |" for k, v in rows.items()]
    summary = list(out)
    for k, v in rows.items():
        if v:
            out += ["", f"## {k}", "", "| symbol | GKI | device | note |", "|---|---|---|---|"]
            out += [f"| `{s}` | {o} | {n} | {w} |" for s, o, n, w in v]
    if a.report:
        open(a.report, "w").write("\n".join(out) + "\n")
    print("\n".join(summary if a.report else out))
    for s, o, n, _ in rows["CHANGED"]:
        print(f"ERROR: {s}: GKI {o}, device {n}", file=sys.stderr)
    return 1 if rows["CHANGED"] else 0


if __name__ == "__main__":
    sys.exit(main())
