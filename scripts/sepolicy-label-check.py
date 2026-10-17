#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Check the labels a built image gives to paths, without the hardware that has them.

Resolves each path against the image's installed file_contexts files as Android's libselinux does: the files in
load order (plat, system_ext, product, vendor, odm), each already in fc_sort order, entries without regex
metacharacters moved after all regex entries, and the last full match wins (label_file.c lookup_common()). Only
entries without a file-type flag are used, and those flagged for the case's type (default: regular file).

  sepolicy-label-check.py PRODUCT_OUT CASES [--json OUT]

CASES: one case per line, "<path> <expected type> [file-type flag, e.g. -d]"; '#' starts a comment. Exit 1 if any
path gets another type. For sysfs, file_contexts only applies where ueventd restorecons a device directory (on
"add" and "bind" uevents); anything else keeps its genfs_contexts label, which this does not model.
"""
import argparse, json, os, re, sys

FILES = ["system/etc/selinux/plat_file_contexts", "system_ext/etc/selinux/system_ext_file_contexts",
         "product/etc/selinux/product_file_contexts", "vendor/etc/selinux/vendor_file_contexts",
         "odm/etc/selinux/odm_file_contexts"]
META = set(".^$?*+|[({")


def has_meta(path):
    """libselinux spec_hasMetaChars(): a backslash escapes the next character."""
    i = 0
    while i < len(path):
        if path[i] == "\\":
            i += 2
            continue
        if path[i] in META:
            return True
        i += 1
    return False


def load(product_out):
    specs = []
    for rel in FILES:
        f = os.path.join(product_out, rel)
        if not os.path.exists(f):
            continue
        for n, line in enumerate(open(f), 1):
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            path, ctx = parts[0], parts[-1]
            ftype = parts[1] if len(parts) == 3 else None
            specs.append({"regex": re.compile("^" + path + "$"), "path": path, "ftype": ftype,
                          "type": ctx.split(":")[2], "meta": has_meta(path), "src": f"{rel}:{n}"})
    # libselinux sort_specs(): regex entries keep their order, exact paths go last.
    return [s for s in specs if s["meta"]] + [s for s in specs if not s["meta"]]


def lookup(specs, path, ftype):
    for s in reversed(specs):
        if s["ftype"] not in (None, ftype):
            continue
        if s["regex"].match(path):
            return s
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("product_out")
    ap.add_argument("cases")
    ap.add_argument("--json")
    a = ap.parse_args()
    specs = load(a.product_out)
    if not specs:
        sys.exit(f"no file_contexts under {a.product_out}")
    results, bad = [], 0
    for line in open(a.cases):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        path, want = parts[0], parts[1]
        ftype = parts[2] if len(parts) > 2 else "--"
        s = lookup(specs, path, ftype)
        got = s["type"] if s else "(genfs_contexts)"
        ok = got == want
        bad += not ok
        results.append({"path": path, "want": want, "got": got, "ok": ok, "rule": s["path"] if s else None,
                        "from": s["src"] if s else None})
        print(f"{'ok  ' if ok else 'FAIL'} {got:32} {path}" + ("" if ok else f"   (want {want}; {s['src'] if s else '-'})"))
    print(f"{len(results) - bad} of {len(results)} paths labelled as expected ({len(specs)} file_contexts entries)")
    if a.json:
        json.dump({"schema": "openbook-label-check/1", "product_out": a.product_out, "results": results,
                   "failures": bad}, open(a.json, "w"), indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
