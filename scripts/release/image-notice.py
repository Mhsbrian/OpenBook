#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Copy a live image's own NOTICE files out, for notice-scan.py (ANAL-341).

usage: image-notice.py IMG OUT

Reads the GPT of IMG (scripts/installer-image.sh's live image), the logical partitions of its super partition
(lpdump, through scripts/installer/mklive.py's reader), and extracts {system,system_ext,product,vendor}/etc/NOTICE.xml.gz
from the slot A EROFS images with fsck.erofs into OUT/<partition>/etc/. AOSP host tools: $AOSP_HOST_BIN, else
<data dir>/aosp/src/out/host/linux-x86/bin.
"""
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def gpt_part(img, name, out):
    with open(img, "rb") as f:
        f.seek(512)
        lba, n, esz = struct.unpack_from("<QII", f.read(92), 72)
        f.seek(lba * 512)
        table = f.read(n * esz)
        for i in range(n):
            e = table[i * esz:(i + 1) * esz]
            if e[:16] == b"\0" * 16 or e[56:128].decode("utf-16le").rstrip("\0") != name:
                continue
            a, b = struct.unpack_from("<QQ", e, 32)
            f.seek(a * 512)
            left = (b - a + 1) * 512
            with open(out, "wb") as o:
                while left:
                    d = f.read(min(left, 64 << 20))
                    o.write(d)
                    left -= len(d)
            return out
    sys.exit(f"image-notice: no {name} partition in {img}")


def main():
    img, out = sys.argv[1:3]
    host = os.environ.get("AOSP_HOST_BIN")
    if host:  # mklive's reader takes its tools from <data dir>/aosp/src/out/host/linux-x86/bin
        os.environ.setdefault("OPENBOOK_HOME", os.path.abspath(os.path.join(host, "../../../../../..")))
    spec = importlib.util.spec_from_file_location("mklive", os.path.join(HERE, "..", "installer", "mklive.py"))
    mklive = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["mklive"]
    spec.loader.exec_module(mklive)
    sys.argv = argv
    fsck = os.path.join(host or mklive.proto.HOST, "fsck.erofs")
    with tempfile.TemporaryDirectory(dir=os.path.dirname(os.path.abspath(out)) or ".") as w:
        sup = gpt_part(img, "super", f"{w}/super.img")
        _, _, parts = mklive.lp_layout(sup)
        files = mklive.extract_partitions(sup, {k: v for k, v in parts.items()
                                                if k in ("system_a", "system_ext_a", "product_a", "vendor_a")}, f"{w}/lp")
        os.unlink(sup)
        found = 0
        for name, path in sorted(files.items()):
            part = name[:-2]
            d = f"{w}/fs-{part}"
            subprocess.run([fsck, f"--extract={d}", "--no-preserve", path], check=True, capture_output=True)
            os.unlink(path)
            for rel in ("etc/NOTICE.xml.gz", "system/etc/NOTICE.xml.gz"):
                if os.path.exists(f"{d}/{rel}"):
                    os.makedirs(f"{out}/{part}/etc", exist_ok=True)
                    shutil.copy(f"{d}/{rel}", f"{out}/{part}/etc/NOTICE.xml.gz")
                    found += 1
                    break
            shutil.rmtree(d)
    print(f"image-notice: {found} NOTICE files from {os.path.basename(img)}")
    sys.exit(0 if found else 1)


if __name__ == "__main__":
    main()
