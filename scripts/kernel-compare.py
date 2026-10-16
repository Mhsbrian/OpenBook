#!/usr/bin/env python3
"""Measure how close a local Kleaf GKI build is to a reference build (ci.android.com and/or a shipped image).

usage: kernel-compare.py OUR_DIST REF_DIR [SHIPPED_KERNEL]  > report.txt
  OUR_DIST        ~/anybook/kernel/dist/<label> from kernel-build.sh
  REF_DIR         ~/anybook/kernel/ci/<bid> from kernel-fetch-ci.sh
  SHIPPED_KERNEL  optional bzImage unpacked from a device image (gbos-unpack.sh: work/<codename>/boot_a/kernel)

Checks: byte identity of the text artifacts, System.map layout, then decompresses both bzImages
(scripts/kernel-info.py, needs lz4/zstd/xz/gzip) and attributes every differing vmlinux byte to an
ELF section and the nearest System.map symbol. Needs readelf (binutils).
"""
import bisect, collections, hashlib, os, subprocess, sys, tempfile

ARTIFACTS = ["kernel_x86_64_dot_config", "vmlinux.symvers", "System.map", "modules.builtin",
             "abi_symbollist", "system_dlkm.modules.load"]
HERE = os.path.dirname(os.path.abspath(__file__))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def vmlinux_of(bz, out):
    subprocess.run([sys.executable, os.path.join(HERE, "kernel-info.py"), bz, out], check=True, capture_output=True)
    return os.path.join(out, "vmlinux")


def sections(elf):
    secs = []
    for line in subprocess.run(["readelf", "-SW", elf], capture_output=True, text=True).stdout.splitlines():
        p = line.replace("[ ", "[").split()
        if len(p) > 6 and p[0].startswith("[") and p[0] != "[Nr]":
            try:
                secs.append((p[1], int(p[3], 16), int(p[4], 16), int(p[5], 16)))
            except ValueError:
                pass
    return secs


def main(ours, ref, shipped=None):
    w = print
    w(f"ours: {ours}\nref:  {ref}\n")
    for f in ARTIFACTS:
        a, b = os.path.join(ours, f), os.path.join(ref, f)
        if os.path.exists(a) and os.path.exists(b):
            w(f"{'IDENTICAL' if sha(a) == sha(b) else 'DIFFERENT'}  {f}")
    sm = lambda p: [(int(l.split()[0], 16), l.split()[2]) for l in open(p)]
    a, b = sm(os.path.join(ours, "System.map")), sm(os.path.join(ref, "System.map"))
    moved = [(x, y) for x, y in zip(a, b) if x != y]
    w(f"\nSystem.map: {len(a)} vs {len(b)} symbols, same name set: {sorted(n for _, n in a) == sorted(n for _, n in b)}, "
      f"entries at a different address: {len(moved)}" + (f" (first: {moved[0][1][1]})" if moved else ""))

    bz_o, bz_r = os.path.join(ours, "bzImage"), os.path.join(ref, "bzImage")
    w(f"\nbzImage sha256 ours {sha(bz_o)}\nbzImage sha256 ref  {sha(bz_r)}")
    if shipped:
        w(f"bzImage sha256 shipped {sha(shipped)} -> {'IDENTICAL to ref' if sha(shipped) == sha(bz_r) else 'differs from ref'}")
    with tempfile.TemporaryDirectory() as t:
        vo, vr = vmlinux_of(bz_o, os.path.join(t, "o")), vmlinux_of(bz_r, os.path.join(t, "r"))
        do, dr = open(vo, "rb").read(), open(vr, "rb").read()
        w(f"vmlinux (decompressed from bzImage): {len(do)} vs {len(dr)} bytes")
        if len(do) != len(dr):
            w("sizes differ: layout changed, byte attribution skipped"); return
        diff = [i for k in range(0, len(do), 1 << 16) if do[k:k + (1 << 16)] != dr[k:k + (1 << 16)]
                for i in range(k, min(k + (1 << 16), len(do))) if do[i] != dr[i]]
        w(f"differing bytes: {len(diff)} ({100.0 * len(diff) / len(do):.5f}%)")
        secs, syms = sections(vo), sorted(b)
        addrs = [x for x, _ in syms]
        c = collections.Counter()
        for off in diff:
            for name, va, fo, size in secs:
                if fo <= off < fo + size:
                    i = bisect.bisect_right(addrs, va + off - fo) - 1 if va else -1
                    c[(name, syms[i][1] if i >= 0 else "-")] += 1
                    break
            else:
                c[("(outside sections)", "-")] += 1
        top = c.most_common()
        for (name, sym), n in top[:15]:
            w(f"  {n:8d} bytes in {name} near symbol {sym}")
        if len(top) > 15:
            w(f"  ... {sum(n for _, n in top[15:])} more bytes near {len(top) - 15} other symbols")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(*sys.argv[1:4])
