#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""License and provenance audit of the arm64 native bridge as a product image ships it (ANAL-200).

For every bridge file in PRODUCT_OUT (the translator, proxies, runners, configs and the arm64 guest world) it
records the Soong module that installs it and that module's source directory (module-info.json), whether the
source lies under prebuilts/ (a binary we did not build), the SHA-256 of the file, and the licenses the image's
own NOTICE file (system/etc/NOTICE.xml.gz) lists for it, classified by their text.

  audit-shipped.py PRODUCT_OUT OUT_DIR      -> OUT_DIR/shipped.csv, OUT_DIR/summary.md
Run with python3 -I.
"""
import collections
import csv
import gzip
import hashlib
import json
import os
import re
import sys

BRIDGE = re.compile(r"^system/(lib64/arm64/|bin/arm64/|lib64/libberberis_|bin/berberis_|etc/binfmt_misc/|"
                    r"etc/init/berberis|etc/ld\.config\.arm64\.txt|etc/cpuinfo\.arm64\.txt)")

# Ordered: the first match names the text. Composite NOTICE texts get every kind they contain.
KINDS = [
    ("GPL", re.compile(r"GNU GENERAL PUBLIC LICENSE", re.I)),
    ("LGPL", re.compile(r"GNU LESSER GENERAL PUBLIC LICENSE|GNU LIBRARY GENERAL PUBLIC", re.I)),
    ("Apache-2.0 WITH LLVM-exception", re.compile(r"LLVM Exceptions to the Apache 2\.0 License", re.I)),
    ("Apache-2.0", re.compile(r"Apache License,?\s+Version 2\.0", re.I)),
    ("BSD-style", re.compile(r"Redistribution and use in source and binary forms", re.I)),
    ("MIT-style", re.compile(r"Permission is hereby granted, free of charge", re.I)),
    ("ISC-style", re.compile(r"Permission to use, copy, modify, and(/or)? distribute this software", re.I)),
    ("zlib", re.compile(r"This software is provided 'as-is', without any express or implied", re.I)),
    ("Unicode", re.compile(r"UNICODE (LICENSE|, INC\.)", re.I)),
    ("OpenSSL/SSLeay", re.compile(r"OpenSSL License|SSLeay", re.I)),
    ("public domain", re.compile(r"public domain|The author disclaims copyright to this source code", re.I)),
    ("libpng", re.compile(r"PNG Reference Library License", re.I)),
    ("BLAS (netlib)", re.compile(r"The reference BLAS is a freely-available software package", re.I)),
]


def classify(text):
    kinds = [k for k, rx in KINDS if rx.search(text)]
    if "Apache-2.0 WITH LLVM-exception" in kinds and "Apache-2.0" in kinds:
        kinds.remove("Apache-2.0")
    if "LGPL" in kinds and "GPL" in kinds and not re.search(r"(?<!LESSER )GENERAL PUBLIC LICENSE\s+Version", text):
        kinds.remove("GPL")
    return kinds or ["other"]


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    po, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    info = json.load(open(os.path.join(po, "module-info.json")))
    by_path = {}
    for name, m in info.items():
        for inst in m.get("installed") or []:
            i = inst.find("/target/product/")
            if i >= 0:
                rel = inst[i:].split("/", 4)[4]  # strip out/target/product/<device>/
                by_path.setdefault(rel, (name, (m.get("path") or [""])[0]))
    # The NOTICE "XML" carries raw license texts that are not always well-formed XML, so read it with patterns.
    notice = gzip.open(os.path.join(po, "system/etc/NOTICE.xml.gz")).read().decode("utf-8", "replace")
    texts = {m.group(1): m.group(2) for m in re.finditer(
        r'<file-content contentId="([^"]+)">(.*?)</file-content>', notice, re.S)}
    notices = collections.defaultdict(set)
    for m in re.finditer(r'<file-name contentId="([^"]+)"[^>]*>([^<]+)</file-name>', notice):
        notices[m.group(2).lstrip("/")].add(m.group(1))
    rows = []
    for root, _, files in os.walk(os.path.join(po, "system")):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), po)
            if not BRIDGE.match(rel):
                continue
            module, src = by_path.get(rel, ("?", "?"))
            kinds = sorted({k for cid in notices.get(rel, ()) for k in classify(texts.get(cid, ""))})
            sha = hashlib.sha256(open(os.path.join(po, rel), "rb").read()).hexdigest()
            rows.append({"file": "/" + rel, "module": module, "source": src,
                         "prebuilt": "yes" if src.startswith("prebuilts/") else "no",
                         "notice_licenses": "+".join(kinds) or "NOT IN NOTICE", "sha256": sha})
    rows.sort(key=lambda r: r["file"])
    with open(os.path.join(out, "shipped.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    by_src = collections.Counter(r["source"] for r in rows)
    by_lic = collections.Counter(r["notice_licenses"] for r in rows)
    lines = [f"# Shipped bridge files in {po}", "",
             f"{len(rows)} files; prebuilt binaries: {sum(r['prebuilt'] == 'yes' for r in rows)}; "
             f"not covered by NOTICE.xml.gz: {sum(r['notice_licenses'] == 'NOT IN NOTICE' for r in rows)}", "",
             "| Source directory | Files |", "|---|---|"]
    lines += [f"| `{s}` | {n} |" for s, n in sorted(by_src.items())]
    lines += ["", "| Licenses in the image's NOTICE for the file | Files |", "|---|---|"]
    lines += [f"| {k} | {n} |" for k, n in sorted(by_lic.items())]
    open(os.path.join(out, "summary.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
