#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Split a qemu-run.py serial log into the sections an expect script printed between "===NAME-BEGIN===" and
"===NAME-END===" lines. Sections holding base64 (LOGCAT, DMESG: `| gzip | base64`) are decoded to NAME.txt.gz.

usage: serial-extract.py SERIAL_LOG OUT_DIR
"""
import base64
import binascii
import gzip
import os
import re
import sys


def main(log, out):
    os.makedirs(out, exist_ok=True)
    text = open(log, "rb").read().decode("utf-8", "replace").replace("\r", "")
    lines = text.split("\n")
    found = {}
    i = 0
    while i < len(lines):
        m = re.fullmatch(r"===([A-Z0-9-]+)-BEGIN===", lines[i].strip())
        if not m:
            i += 1
            continue
        name, body = m.group(1), []
        i += 1
        while i < len(lines) and lines[i].strip() != f"==={name}-END===":
            body.append(lines[i])
            i += 1
        found.setdefault(name, []).append(body)
        i += 1
    for name, bodies in found.items():
        for n, body in enumerate(bodies):
            stem = name if n == 0 else f"{name}-{n + 1}"
            # Kernel messages printed at high priority (sysrq dumps, panics) can land inside a base64 stream.
            joined = "".join(re.sub(r"\[\s*\d+\.\d+\]\[\s*[TC]\d+\].*$", "", l).strip() for l in body)
            if name in ("LOGCAT", "DMESG") and joined and re.fullmatch(r"[A-Za-z0-9+/=]+", joined):
                try:
                    raw = base64.b64decode(joined)
                    gzip.decompress(raw)  # integrity check
                    open(f"{out}/{stem.lower()}.txt.gz", "wb").write(raw)
                    continue
                except (binascii.Error, OSError, EOFError) as e:
                    print(f"{stem}: not valid base64+gzip ({e}); keeping text", file=sys.stderr)
            open(f"{out}/{stem.lower()}.txt", "w").write("\n".join(body).rstrip() + "\n")
    print(" ".join(sorted(found)))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
