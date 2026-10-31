#!/usr/bin/env python3
"""Print the boolean aconfig flags in an image's new-style flag storage, offline.

Each partition has etc/aconfig/{package.map,flag.map,flag.val}. Read-write and
read-only flags live there; fixed read-only flags that are enabled are also in
etc/aconfig_flags.pb (use `aconfig dump-cache` for those). Format: AOSP 17
build/make/tools/aconfig/aconfig_storage_file (versions 1 to 3).

  scripts/aconfig-storage-dump.py ~/anybook/work/gbos-ruby/fs/system_a/system/etc/aconfig ...
Output: <package>.<flag> ENABLED|DISABLED <type> <container>
"""
import os
import struct
import sys

TYPES = {0: "READ_WRITE", 1: "READ_ONLY", 2: "FIXED_READ_ONLY", 3: "RW_INT", 4: "RO_INT", 5: "FIXED_RO_INT"}


class R:
    def __init__(self, b, pos=0):
        self.b, self.p = b, pos

    def u8(self):
        v = self.b[self.p]; self.p += 1; return v

    def u16(self):
        v = struct.unpack_from("<H", self.b, self.p)[0]; self.p += 2; return v

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.p)[0]; self.p += 4; return v

    def u64(self):
        v = struct.unpack_from("<Q", self.b, self.p)[0]; self.p += 8; return v

    def s(self):
        n = self.u32(); v = self.b[self.p:self.p + n].decode(); self.p += n; return v


def header(r):
    return dict(version=r.u32(), container=r.s(), file_type=r.u8(), file_size=r.u32(),
                count=r.u32(), off1=r.u32(), off2=r.u32())


def packages(path):
    b = open(path, "rb").read(); r = R(b); h = header(r)
    r.p = h["off2"]; out = {}
    for _ in range(h["count"]):
        name = r.s(); pid = r.u32()
        if h["version"] >= 2:
            r.u64()
        if h["version"] >= 3:
            r.u8()
        start = r.u32(); r.u32()
        out[pid] = (name, start)
    return h, out


def flags(path):
    b = open(path, "rb").read(); r = R(b); h = header(r)
    r.p = h["off2"]; out = []
    for _ in range(h["count"]):
        pid = r.u32(); name = r.s(); ftype = r.u16(); idx = r.u16(); r.u32()
        out.append((pid, name, ftype, idx))
    return out


def values(path):
    b = open(path, "rb").read(); r = R(b)
    version = r.u32(); r.s(); r.u8(); r.u32(); n = r.u32(); off = r.u32()
    return b[off:off + n]


def main():
    for d in sys.argv[1:]:
        h, pk = packages(os.path.join(d, "package.map"))
        vals = values(os.path.join(d, "flag.val"))
        for pid, name, ftype, idx in flags(os.path.join(d, "flag.map")):
            if ftype not in (0, 1, 2):
                continue
            pkg, start = pk[pid]
            v = vals[start + idx]
            print("%s.%s %s %s %s" % (pkg, name, "ENABLED" if v else "DISABLED", TYPES[ftype], h["container"]))


if __name__ == "__main__":
    main()
