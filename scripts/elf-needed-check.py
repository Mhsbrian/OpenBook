#!/usr/bin/env python3
"""Check Android shared libraries' NEEDED entries and undefined symbols against an NDK sysroot.

For each library: list SONAME and NEEDED, classify each NEEDED as another artifact, an NDK
library at the given API level, or build-time stub only (a platform/LLNDK library the NDK
does not ship). Then resolve every non-weak undefined symbol, preferring artifacts and the
NDK API stubs, and report symbols only a build-time stub provides (LLNDK/platform-only APIs)
or that nothing provides.

  elf-needed-check.py --nm llvm-nm --readelf llvm-readelf --sysroot <sysroot/usr/lib/<triple>/<api>>
                      [--stub <dir with build-time stub .so>] lib.so...
Exit status 1 if any NEEDED library or symbol is unresolved.
"""
import argparse, os, re, subprocess, sys


def run(*cmd):
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout


def dyn(readelf, path):
    out = run(readelf, "-d", path)
    soname = re.search(r"\(SONAME\)\s+Library soname: \[(.+?)\]", out)
    return (soname.group(1) if soname else os.path.basename(path),
            re.findall(r"\(NEEDED\)\s+Shared library: \[(.+?)\]", out))


def syms(nm, path, defined):
    out = run(nm, "-D", "--defined-only" if defined else "--undefined-only", path)
    res = set()
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        kind, name = parts[-2], parts[-1].split("@")[0]
        if not defined and kind in ("w", "v"):
            continue  # weak undefined: allowed to stay unresolved
        res.add(name)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nm", required=True)
    ap.add_argument("--readelf", required=True)
    ap.add_argument("--sysroot", required=True)
    ap.add_argument("--stub", action="append", default=[])
    ap.add_argument("libs", nargs="+")
    a = ap.parse_args()

    artifacts = {}
    for p in a.libs:
        soname, needed = dyn(a.readelf, p)
        artifacts[soname] = (p, needed)
        artifacts.setdefault(os.path.basename(p), (p, needed))

    def find(dirs, name):
        for d in dirs:
            for root, _, files in os.walk(d):
                if name in files:
                    return os.path.join(root, name)
        return None

    cache, bad = {}, 0
    print(f"# NDK sysroot: {a.sysroot}")
    for p in a.libs:
        soname, needed = dyn(a.readelf, p)
        print(f"\n== {p}\nSONAME: {soname}")
        providers = []
        for n in needed:
            if n in artifacts and artifacts[n][0] != p:
                kind, src = "artifact", artifacts[n][0]
            elif os.path.exists(os.path.join(a.sysroot, n)):
                kind, src = "ndk", os.path.join(a.sysroot, n)
            elif find(a.stub, n):
                kind, src = "stub-only (platform/LLNDK, not in NDK)", find(a.stub, n)
            else:
                kind, src = "MISSING", None
                bad += 1
            print(f"NEEDED {n:28s} {kind}")
            if src:
                providers.append((kind, n, src))
                if kind == "ndk":
                    stub = find(a.stub, n)
                    if stub:
                        providers.append(("stub-only (platform/LLNDK, not in NDK)", n, stub))
        undef = syms(a.nm, p, False)
        where = {}
        for kind, n, src in providers:
            if src not in cache:
                cache[src] = syms(a.nm, src, True)
            for s in undef & cache[src]:
                where.setdefault(s, (kind, n))
        stub_only = sorted(s for s, (k, _) in where.items() if k.startswith("stub"))
        missing = sorted(undef - set(where))
        print(f"undefined (non-weak) symbols: {len(undef)}; via ndk/artifact: "
              f"{len(undef) - len(stub_only) - len(missing)}; stub-only: {len(stub_only)}; unresolved: {len(missing)}")
        for s in stub_only:
            print(f"  stub-only {s} ({where[s][1]})")
        for s in missing:
            print(f"  UNRESOLVED {s}")
        bad += len(missing)
    print(f"\n# result: {'OK' if not bad else f'{bad} problem(s)'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
