#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build or read a Linux bootconfig blob (Documentation/admin-guide/bootconfig.rst), the way an Android
bootloader appends it to the initrd:

    [key=value lines][\\0 padding to 4 bytes][le32 size][le32 checksum]["#BOOTCONFIG\\n"]

The kernel only finds it at the very end of the (concatenated) initrd, and only with "bootconfig" on the cmdline
(GKI has CONFIG_BOOT_CONFIG=y, CONFIG_BOOT_CONFIG_FORCE off).

usage: bootconfig.py make OUT [--base FILE ...] [KEY=VALUE ...]   later keys override earlier ones (and --base)
       bootconfig.py show FILE                                     print the blob at the end of FILE, or fail
"""
import struct
import sys

MAGIC = b"#BOOTCONFIG\n"


def parse_text(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"')
    return out


def render(params):
    lines = []
    for k, v in params.items():
        needs_quote = any(c in v for c in ' \t;#,{}="\'') or v == ""
        lines.append(f'{k} = "{v}"' if needs_quote else f"{k} = {v}")
    return ("\n".join(lines) + "\n").encode()


def blob(params):
    data = render(params) + b"\0"
    data += b"\0" * (-len(data) % 4)
    return data + struct.pack("<II", len(data), sum(data) & 0xFFFFFFFF) + MAGIC


def read_trailer(buf):
    if not buf.endswith(MAGIC):
        raise ValueError("no #BOOTCONFIG trailer at the end")
    size, csum = struct.unpack_from("<II", buf, len(buf) - len(MAGIC) - 8)
    data = buf[len(buf) - len(MAGIC) - 8 - size: len(buf) - len(MAGIC) - 8]
    if sum(data) & 0xFFFFFFFF != csum:
        raise ValueError("bootconfig checksum mismatch")
    return data.rstrip(b"\0").decode()


def main(argv):
    if len(argv) >= 2 and argv[0] == "make":
        out, rest = argv[1], argv[2:]
        params = {}
        while rest:
            a = rest.pop(0)
            if a == "--base":
                with open(rest.pop(0)) as f:
                    params.update(parse_text(f.read()))
            else:
                k, _, v = a.partition("=")
                params[k] = v
        with open(out, "wb") as f:
            f.write(blob(params))
        return 0
    if len(argv) == 2 and argv[0] == "show":
        with open(argv[1], "rb") as f:
            print(read_trailer(f.read()), end="")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
