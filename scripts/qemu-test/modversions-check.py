#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Will a kernel module built in another Kleaf dist load into ours? Compares MODULE's __versions CRCs with what
SYMVERS (vmlinux.symvers of the target kernel) and the PROVIDER modules export (their __kcrctab). The QEMU Wi-Fi
test borrows mac80211_hwsim from the virtual-device dist (scripts/audio-net-qemu.sh). Exit 1 on any mismatch.

usage: modversions-check.py MODULE SYMVERS [PROVIDER.ko ...]"""
import struct, subprocess, sys
def kcrc(ko):
    out = {}
    data = open(ko, 'rb').read()
    # section table
    shoff, = struct.unpack_from('<Q', data, 0x28); shentsize, shnum, shstrndx = struct.unpack_from('<HHH', data, 0x3a)
    secs = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + i * shentsize) for i in range(shnum)]
    names = secs[shstrndx]; nm = lambda o: data[names[4] + o:data.index(b'\0', names[4] + o)].decode()
    byname = {nm(s[0]): (i, s) for i, s in enumerate(secs)}
    if '__kcrctab' not in byname: return out
    ki, ks = byname['__kcrctab']; sym = byname['.symtab'][1]; strt = secs[sym[6]]
    for j in range(sym[5] // 24):
        st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from('<IBBHQQ', data, sym[4] + j * 24)
        n = data[strt[4] + st_name:data.index(b'\0', strt[4] + st_name)].decode()
        if n.startswith('__crc_') and st_shndx == ki:
            out[n[6:]] = struct.unpack_from('<I', data, ks[4] + st_value)[0]
    return out
m, symvers, provs = sys.argv[1], sys.argv[2], sys.argv[3:]
have = {}
for line in open(symvers):
    c, s = line.split()[:2]; have[s] = int(c, 16)
for p in provs: have.update(kcrc(p))
need = [l.split() for l in subprocess.run(['/sbin/modprobe', '--dump-modversions', m], capture_output=True, text=True).stdout.splitlines()]
bad = [(s, c, have.get(s)) for c, s in need if have.get(s) != int(c, 16)]
print(f"{m}: {len(need)} versioned symbols, {len(bad)} mismatched or missing")
for s, c, h in bad[:20]: print(f"  {s}: wants {c}, have {h if h is None else hex(h)}")
sys.exit(1 if bad else 0)
