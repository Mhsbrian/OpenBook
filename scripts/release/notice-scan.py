#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Which binaries in an OpenBook image carry a GPL or LGPL licence text, and which source projects they come from.
Reads the image's own NOTICE files (<PRODUCT_OUT>/{system,system_ext,product,vendor}/etc/NOTICE.xml.gz) and
module-info.json, and maps every flagged file to the repo project it is built from. For scripts/release/make-sources.sh.

A flagged file needs its source published unless every GPL/LGPL text it carries comes from one of EXEMPT below: a
licence collection whose GPL/LGPL entry is for something not in the binary. Each exemption says why and was checked
by hand (ANAL-320, 2026-10-31). A new GPL binary in a later build is therefore included, not missed.

usage: notice-scan.py PRODUCT_OUT AOSP_SRC [--json FILE]
NOTICE.xml.gz is not well-formed XML (licence texts carry raw control characters), so it is read with patterns.
"""
import argparse
import gzip
import json
import os
import re
import sys

PARTS = ("system", "system_ext", "product", "vendor")
# lib attribute of the NOTICE entry -> why its GPL/LGPL text needs no source here
EXEMPT = {
    "kotlinc": "Kotlin's notice collects the licences of the Kotlin distribution; its GPL-2.0 text follows MPL-1.1's "
               "Exhibit A, for components under \"MPL-1.1 or GPL-2.0\" (used under the MPL). The apps are Apache-2.0",
    "prebuilts/tools": "the notice is prebuilts/tools' whole licence collection (416 KB); its LGPL entries are build "
                       "tools there such as JNA 3.4.0, and the app's dex has no JNA classes (checked 2026-10-31)",
}
# Source published by make-sources.sh in its own folder, not as an AOSP project
SEPARATE = {"vendor/anybook/mesa": "Mesa's libelf (elfutils, LGPL-3.0+): mesa-build/ in the userspace tarball"}
# OpenBook's own apps: their source is the OpenBook repository itself (Apache-2.0)
OWN = ("device/anybook/",)

FILE_RE = re.compile(r'<file-name contentId="([0-9a-f]+)" lib="([^"]*)">([^<]*)</file-name>')
TEXT_RE = re.compile(r'<file-content contentId="([0-9a-f]+)"><!\[CDATA\[(.*?)\]\]></file-content>', re.S)


def scan(pout):
    files = {}
    for part in PARTS:
        p = f"{pout}/{part}/etc/NOTICE.xml.gz"
        if not os.path.exists(p):
            continue
        d = gzip.open(p).read().decode("utf-8", "replace")
        kinds = {}
        for cid, text in TEXT_RE.findall(d):
            k = set()
            if re.search(r"GNU (LESSER|LIBRARY) GENERAL PUBLIC LICENSE", text):
                k.add("LGPL")
            if re.search(r"GNU GENERAL PUBLIC LICENSE", text):
                k.add("GPL")
            if k:
                kinds[cid] = k
        for cid, lib, path in FILE_RE.findall(d):
            if cid in kinds:
                for k in kinds[cid]:
                    files.setdefault(path, set()).add((k, lib))
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("product_out")
    ap.add_argument("aosp_src")
    ap.add_argument("--json")
    a = ap.parse_args()
    files = scan(a.product_out)
    mi = json.load(open(f"{a.product_out}/module-info.json"))
    marker = "/target/product/" + os.path.basename(os.path.normpath(a.product_out)) + "/"
    srcdirs = {}
    for v in mi.values():
        for i in v.get("installed", []):
            if marker in i:
                srcdirs.setdefault("/" + i.split(marker, 1)[1], set()).update(v.get("path", []))
    projects = [l.strip() for l in open(f"{a.aosp_src}/.repo/project.list")]

    def project(path):
        best = None
        for q in projects:
            if (path == q or path.startswith(q + "/")) and (best is None or len(q) > len(best)):
                best = q
        return best

    inc, exc, sep, own = {}, {}, {}, {}
    for f, ks in sorted(files.items()):
        dirs = srcdirs.get(f) or {"?"}
        needs = {(k, lib) for k, lib in ks if lib not in EXEMPT}
        kinds = "/".join(sorted({k for k, _ in ks}))
        for d in dirs:
            pr = project(d) or d
            if any(d.startswith(s) for s in SEPARATE):
                sep.setdefault(next(s for s in SEPARATE if d.startswith(s)), []).append(f)
            elif d.startswith(OWN):
                own.setdefault(d, []).append(f)
            elif needs:
                e = inc.setdefault(pr, {"project": pr, "kinds": set(), "files": []})
                e["kinds"].update(k for k, _ in needs)
                e["files"].append(f)
            else:
                libs = sorted({lib for _, lib in ks})
                e = exc.setdefault(pr, {"project": pr, "files": [], "why": "; ".join(EXEMPT[l] for l in libs)})
                e["files"].append(f)
    if any(p.startswith("?") or not os.path.isdir(f"{a.aosp_src}/{p}") for p in inc):
        missing = [p for p in inc if p.startswith("?") or not os.path.isdir(f"{a.aosp_src}/{p}")]
        sys.exit(f"notice-scan: flagged files with no source project in the tree: {missing}")
    out = {
        "included": [dict(v, kinds="/".join(sorted(v["kinds"]))) for _, v in sorted(inc.items())],
        "source_projects": sorted(inc),
        "not_included": [v for _, v in sorted(exc.items())] +
                        [{"project": p, "files": fs, "why": SEPARATE[p]} for p, fs in sorted(sep.items())] +
                        [{"project": p, "files": fs, "why": "OpenBook's own app (Apache-2.0); its GPL text is "
                          "Kotlin's, as above. Source: the OpenBook repository"} for p, fs in sorted(own.items())],
    }
    for v in out["included"]:
        print(f"source   {v['project']:40} {v['kinds']:8} {len(v['files']):3} files, e.g. {v['files'][0]}")
    for v in out["not_included"]:
        print(f"no-src   {v['project']:40} {'':8} {len(v['files']):3} files: {v['why'][:70]}")
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
