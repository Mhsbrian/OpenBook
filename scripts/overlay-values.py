#!/usr/bin/env python3
"""Flatten `aapt2 dump resources` output (as written by gbos-inventory.py into overlays/)
into one line per value:  <overlay> <type>/<name> [<config>] = <value>

  scripts/overlay-values.py ~/anybook/gbos-ui/ruby/overlays/*.txt > overlay-values.txt
"""
import os
import re
import sys

RES = re.compile(r"^\s+resource 0x[0-9a-f]+ (\S+)")
VAL = re.compile(r"^\s+\(([^)]*)\) (.*)$")


def flatten(path):
    name = os.path.basename(path)[:-4]
    out, res, cfg, buf = [], None, None, None

    def flush():
        if res and buf is not None:
            out.append("%s %s [%s] = %s" % (name, res, cfg, " ".join(buf)))

    for line in open(path, errors="replace"):
        line = line.rstrip("\n")
        m = RES.match(line)
        if m:
            flush()
            res, cfg, buf = m.group(1), None, None
            continue
        m = VAL.match(line)
        if m and res:
            flush()
            cfg, buf = m.group(1), [m.group(2).strip()]
            continue
        if buf is not None and line.startswith("        "):
            buf.append(line.strip())
    flush()
    return out


for p in sys.argv[1:]:
    for l in flatten(p):
        print(l)
