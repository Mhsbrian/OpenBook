#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Print one of openbook-live-init's embedded shell scripts or lists, decoded from live-init.c (ANAL-222), so a
host-driven capture over adb (scripts/g14-adb.sh) runs exactly what the stick's "save logs" entry runs.

  COLLECT        collect-<phase>.txt's script ("===NAME===" sections)
  PRIOR_LIST     prior-boots.txt: size and file count of /data/misc/logd, tombstones, anr, system/dropbox
  PRIOR_BOOTS    prior-boots.tar.gz: those directories as a gzipped tar, capped at PRIOR_CAP
  SUMMARY_PROPS  the properties summary.json records, one per line

usage: live-init-script.py NAME [--source live-init.c]
"""
import argparse
import ast
import os
import re
import sys


def extract(src, name):
    defines = dict(re.findall(r"^#define (\w+) (\d+)\b", src, re.M))
    m = re.search(r"^static const char (?:\*)?" + re.escape(name) + r"\[\] =\s*(.*?);\n", src, re.M | re.S)
    if not m:
        sys.exit(f"{name}: not found in live-init.c")
    body = "\n".join(l for l in m.group(1).splitlines() if not l.strip().startswith("//"))
    parts = []
    # String literals ("..."), STR(MACRO) stringification, and in a char* list, NULL (the end marker).
    for tok in re.finditer(r'"(?:[^"\\]|\\.)*"|STR\((\w+)\)|NULL', body):
        if tok.group(0) == "NULL":
            continue
        if tok.group(1):
            parts.append(defines[tok.group(1)])
        else:
            parts.append(ast.literal_eval(tok.group(0)))
    is_list = m.group(0).startswith("static const char *")
    return "\n".join(parts) + "\n" if is_list else "".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", choices=("COLLECT", "PRIOR_LIST", "PRIOR_BOOTS", "SUMMARY_PROPS"))
    ap.add_argument("--source", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "live-init.c"))
    a = ap.parse_args()
    out = extract(open(a.source).read(), a.name)
    sys.stdout.write(out if out.endswith("\n") else out + "\n")


if __name__ == "__main__":
    main()
