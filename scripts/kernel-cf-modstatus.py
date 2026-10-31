#!/usr/bin/env python3
"""Which modules loaded in a kernel-cf-boot.sh run, and why the others did not.

usage: kernel-cf-modstatus.py LOGDIR      (prints Markdown; kernel-cf-boot.sh writes it to LOGDIR/modload-status.md)

Inputs from LOGDIR: modset.tsv (kernel-cf-modset.py), proc-modules.txt (guest /proc/modules after boot),
kernel.log (full guest console from the host side), dmesg.txt and probe-blocklisted.txt (the hand-loaded
VM-blocklisted modules). Every module that the module set lists for
first-stage init (vendor_ramdisk) or for dlkm_loader (vendor_dlkm, not blocklisted) is expected to be live.
For each one that is not, the log lines that name it are quoted: libmodprobe's "Failed to insmod" lines from
init and dlkm_loader, and the kernel's own module loader errors.
"""
import collections
import os
import re
import sys

KERNEL_ERR = re.compile(r"disagrees about version|Unknown symbol|module verification failed|loading module failed|"
                        r"Invalid module|module is from|version magic|probe .* failed|failed with error")


def norm(name):
    return name.removesuffix(".ko").replace("-", "_")


def main():
    d = sys.argv[1]
    rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(d, "modset.tsv"))][1:]
    live = set()
    p = os.path.join(d, "proc-modules.txt")
    if os.path.exists(p):
        live = {l.split()[0] for l in open(p) if l.strip() and not l.startswith("error")}
    logs = []
    for f in ("kernel.log", "dmesg.txt"):
        p = os.path.join(d, f)
        if os.path.exists(p):
            logs += open(p, errors="replace").read().splitlines()
    seen, lines = set(), []
    for l in logs:
        k = re.sub(r"^\[[ \d.]+\]\s*", "", l)
        if k not in seen:
            seen.add(k)
            lines.append(l.strip())

    def why(name):
        n, base = norm(name), name.removesuffix(".ko")
        hits = [l for l in lines if (f"/{name}'" in l and "insmod" in l)
                or (KERNEL_ERR.search(l) and re.search(rf"\b({re.escape(base)}|{re.escape(n)})\b", l))]
        return hits[:4]

    expected = [r for r in rows if r[3] in ("vendor_ramdisk", "vendor_dlkm") and r[4] == "listed"]
    by = collections.Counter()
    fails = []
    for name, origin, path, stage, load, _ in expected:
        ok = norm(name) in live
        by[(origin, stage, ok)] += 1
        if not ok:
            fails.append((name, origin, stage, why(name)))
    gki_live = sorted(norm(r[0]) for r in rows if r[1] == "gki" and norm(r[0]) in live)
    blocked = [(r[0], norm(r[0]) in live) for r in rows if r[4] == "blocklisted"]
    excluded = [r for r in rows if r[3] == "excluded"]
    summary = [l for l in lines if re.search(r"Loaded \d+ kernel modules|module load count is|dlkm loader|"
                                             r"modules from vendor dlkm", l)]

    out = [f"# Module load status: {os.path.basename(os.path.normpath(d))}", ""]
    if not live:
        out += ["**No /proc/modules from the guest** (adb never answered); only log lines below.", ""]
    out += [f"{len(live)} modules live after boot. Of {len(expected)} modules that first-stage init or "
            f"dlkm_loader should load, **{len(expected) - len(fails)} are live and {len(fails)} are not**.", "",
            "| source | stage | expected | live |", "|---|---|---|---|"]
    for origin in ("gki", "board", "anybook"):
        for stage in ("vendor_ramdisk", "vendor_dlkm"):
            e = by[(origin, stage, True)] + by[(origin, stage, False)]
            if e:
                out.append(f"| {origin} | {stage} | {e} | {by[(origin, stage, True)]} |")
    out += ["", f"GKI modules from system_dlkm loaded as dependencies or on demand: {len(gki_live)} "
            f"({', '.join(gki_live)}).", "",
            "Blocklisted, so not loaded by dlkm_loader: " +
            ", ".join(f"{n} ({'live: loaded explicitly' if l else 'not live'})" for n, l in blocked) + ".", ""]
    if summary:
        out += ["Loader summary lines:", "", "```"] + summary[:12] + ["```", ""]
    out += ["## Not live", ""]
    if not fails:
        out.append("None.")
    for name, origin, stage, hits in fails:
        out.append(f"- `{name}` ({origin}, {stage})")
        out += [f"  - `{h[:300]}`" for h in hits] or ["  - no log line names it"]
    p = os.path.join(d, "probe-blocklisted.txt")
    if os.path.exists(p) and os.path.getsize(p):
        out += ["", "## Blocklisted for this VM, then loaded by hand after boot", "", "```"] + \
               open(p, errors="replace").read().rstrip("\n").splitlines() + ["```"]
    if excluded:
        out += ["", "## Left out of the image by kernel-cf-modset.py", "",
                "| module | source | reason |", "|---|---|---|"] + [f"| {r[0]} | {r[1]} | {r[5]} |" for r in excluded]
    print("\n".join(out))


if __name__ == "__main__":
    main()
