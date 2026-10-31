#!/usr/bin/env python3
"""Compare two GKI dists symbol by symbol: did a config change alter vmlinux or the GKI modules?

usage: kernel-equiv-compare.py DIST_A DIST_B

vmlinux: every symbol's size from `nm -S`. Lists symbols present in only one build and symbols whose size
differs. Addresses are ignored, since one inserted function shifts everything after it.
GKI modules (the names in DIST_A/system_dlkm.modules.load): compared after dropping the module signature,
.note.gnu.build-id and .BTF. Module BTF is split BTF on top of vmlinux's, so its type IDs move whenever
vmlinux gains a type; that is not a code change. For modules that still differ, the differing sections
are listed. Also reports whether vmlinux.symvers (export CRCs) and abi_symbollist are identical.
Needs nm, objcopy, readelf.
"""
import collections
import hashlib
import os
import subprocess
import sys
import tempfile


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def nm_sizes(vmlinux):
    d = collections.defaultdict(list)
    for line in subprocess.run(["nm", "-S", vmlinux], capture_output=True, text=True, check=True).stdout.splitlines():
        f = line.split()
        if len(f) == 4:
            d[f[3]].append(int(f[1], 16))
    return {k: sorted(v) for k, v in d.items()}


def sections(ko):
    return [l.split("]", 1)[1].split()[0] for l in subprocess.run(["readelf", "-SW", ko], capture_output=True,
            text=True).stdout.splitlines() if "] ." in l]


def dump(ko, sec, out):
    if os.path.exists(out):
        os.remove(out)
    subprocess.run(["objcopy", "--dump-section", f"{sec}={out}", ko, out + ".x"], capture_output=True)
    if os.path.exists(out + ".x"):
        os.remove(out + ".x")
    return open(out, "rb").read() if os.path.exists(out) else None


def main(a, b):
    w = print
    w(f"A: {a}\nB: {b}\n")
    for f in ["vmlinux.symvers", "abi_symbollist", "modules.builtin", "system_dlkm.modules.load"]:
        pa, pb = os.path.join(a, f), os.path.join(b, f)
        if os.path.exists(pa) and os.path.exists(pb):
            w(f"{'IDENTICAL' if sha(pa) == sha(pb) else 'DIFFERENT'}  {f}")

    sa, sb = nm_sizes(os.path.join(a, "vmlinux")), nm_sizes(os.path.join(b, "vmlinux"))
    only_a, only_b = sorted(set(sa) - set(sb)), sorted(set(sb) - set(sa))
    resized = [(k, sa[k], sb[k]) for k in sorted(set(sa) & set(sb)) if sa[k] != sb[k]]
    w(f"\n## vmlinux symbols (nm -S): A {len(sa)}, B {len(sb)}")
    w(f"only in A: {len(only_a)} {only_a}")
    w(f"only in B: {len(only_b)} {only_b}")
    w(f"same name, different size: {len(resized)}")
    for k, x, y in resized:
        w(f"  {k}: {x} -> {y}")

    names = [os.path.basename(l.strip()) for l in open(os.path.join(a, "system_dlkm.modules.load")) if l.strip()]
    same, differ, missing = 0, [], []
    with tempfile.TemporaryDirectory() as t:
        for m in names:
            ka, kb = os.path.join(a, m), os.path.join(b, m)
            if not (os.path.exists(ka) and os.path.exists(kb)):
                missing.append(m)
                continue
            strip = ["-R", ".note.gnu.build-id", "-R", ".BTF", "-R", ".BTF.base"]
            subprocess.run(["objcopy", *strip, ka, f"{t}/a.ko"], check=True)
            subprocess.run(["objcopy", *strip, kb, f"{t}/b.ko"], check=True)
            if open(f"{t}/a.ko", "rb").read() == open(f"{t}/b.ko", "rb").read():
                same += 1
                continue
            secs = [s for s in sections(f"{t}/a.ko") if dump(f"{t}/a.ko", s, f"{t}/sa") != dump(f"{t}/b.ko", s, f"{t}/sb")]
            differ.append((m, secs))
    w(f"\n## GKI modules ({len(names)} in system_dlkm.modules.load; signature, build ID and .BTF dropped)")
    w(f"identical: {same}, different: {len(differ)}, missing: {len(missing)} {missing}")
    for m, secs in differ:
        w(f"  {m}: {', '.join(secs) or 'ELF headers only'}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
