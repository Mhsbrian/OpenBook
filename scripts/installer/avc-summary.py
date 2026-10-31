#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""SELinux denials of an OpenBook live boot, from what the "save logs" entry wrote (openbook/logs/live-NNN/).

The save-logs entries boot permissive, and their log helper runs in the kernel domain, so the raw counts
(live-report.py's avc_denials) are mostly the helper. This separates:
  helper      scontext kernel from the helper's own processes (openbook-live-init and the shell tools it runs, or
              service lookups by uid 0): expected, never in a normal boot. In a capture over adb (summary.json
              "source": "adb"), scontext shell, su and adbd: the adb session's own commands
  kernel      scontext kernel from anything else (modprobe, kworkers: firmware loads). These are real: the enforcing
              entries block them too (ANAL-176: amdgpu's firmware_load)
  induced     tcontext kernel, or vfat: Android services answering the helper (dumpsys, screencap, getprop), or
              writing into the helper's files on the stick's ESP, which only the helper mounts
  android     everything else: what the enforcing entries would block
The "dmesg_lines" figure is the number of android and kernel denial lines in the kernel log. ANAL-176 first
counted only android ones (live-001: 66) and so missed amdgpu's firmware_load, which is what kept every enforcing
G14 boot black. "tuples" are the distinct (source, target, class) triples in the kernel log and logcat together.

  avc-summary.py LIVE_DIR [--json OUT] [--md OUT]
"""
import argparse, collections, gzip, json, os, re, sys

AVC = re.compile(r"avc:\s+denied\s+\{ ([^}]*) \} for .*?scontext=u:r:([\w.]+):s0\S* tcontext=u:(?:object_r|r):([\w.]+):s0\S* "
                 r"tclass=(\w+)")


def lines(path):
    for p in (path, path + ".gz"):
        if os.path.exists(p):
            op = gzip.open if p.endswith(".gz") else open
            with op(p, "rt", errors="replace") as f:
                yield from f
            return


# Processes of the log helper (comm is cut to 15 characters).
HELPER_COMMS = {"openbook-live-i", "sh", "toolbox", "toybox", "getprop", "logcat", "dumpsys", "screencap", "cat", "ls",
                "df", "ps", "date", "grep", "head", "ip", "cmd", "service", "pm", "readlink", "tar", "gzip", "tail"}


def classify(scon, tcon, tclass="", comm=None, adb=False):
    # A capture over adb (scripts/g14-adb.sh, summary.json "source": "adb"): the helper is the adb session itself.
    if adb and scon in ("shell", "su", "adbd"):
        return "helper"
    if scon == "kernel":
        # Service lookups and binder calls by uid 0 carry no comm: the helper's dumpsys/cmd.
        if comm is None or comm in HELPER_COMMS or tclass in ("service_manager", "binder"):
            return "helper"
        return "kernel"
    if tcon in ("kernel", "vfat"):
        return "induced"
    return "android"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("live_dir")
    ap.add_argument("--json")
    ap.add_argument("--md")
    a = ap.parse_args()
    d = a.live_dir
    try:
        adb = json.load(open(os.path.join(d, "summary.json"))).get("source") == "adb"
    except (OSError, ValueError):
        adb = False
    counts = {"dmesg": collections.Counter(), "logcat": collections.Counter()}
    tuples = collections.defaultdict(lambda: {"perms": set(), "paths": set(), "sources": set()})
    for src, files in (("dmesg", ["dmesg.txt"]), ("logcat", ["logcat-early.txt", "logcat-final.txt"])):
        for fn in files:
            for line in lines(os.path.join(d, fn)):
                m = AVC.search(line)
                if not m:
                    continue
                perms, scon, tcon, tclass = m.groups()
                cm = re.search(r' comm="([^"]*)"', line)
                kind = classify(scon, tcon, tclass, cm.group(1) if cm else None, adb)
                counts[src][kind] += 1
                if kind not in ("android", "kernel"):
                    continue
                t = tuples[(scon, tcon, tclass)]
                t["perms"].update(perms.split())
                t["sources"].add(src)
                p = re.search(r' (?:path|name)="([^"]*)"', line)
                if p and len(t["paths"]) < 3:
                    t["paths"].add(p.group(1))
    rows = sorted(({"scontext": s, "tcontext": t, "tclass": c, "perms": sorted(v["perms"]), "paths": sorted(v["paths"]),
                    "in": sorted(v["sources"])} for (s, t, c), v in tuples.items()),
                  key=lambda r: (r["scontext"], r["tcontext"], r["tclass"]))
    out = {"schema": "openbook-avc-summary/1", "dir": os.path.basename(os.path.normpath(d)),
           "dmesg": dict(counts["dmesg"]), "logcat": dict(counts["logcat"]),
           "dmesg_lines": counts["dmesg"]["android"] + counts["dmesg"]["kernel"], "tuples": len(rows),
           "tuples_without_flags_health_check": sum(r["scontext"] != "flags_health_check" for r in rows),
           "denials": rows}
    md = [f"# SELinux denials: {out['dir']}", "",
          f"- Denial lines in the kernel log that the enforcing entries would hit (helper and helper-induced excluded): "
          f"**{out['dmesg_lines']}**",
          f"- Distinct (source, target, class) in kernel log + logcat: **{out['tuples']}** "
          f"({out['tuples_without_flags_health_check']} without flags_health_check, which only runs after repeated "
          "system_server crashes)",
          f"- Raw lines: kernel log {dict(counts['dmesg'])}, logcat {dict(counts['logcat'])}", "",
          "| source | target | class | permissions | example |", "|---|---|---|---|---|"]
    for r in rows:
        if r["scontext"] == "flags_health_check":
            continue
        md.append(f"| {r['scontext']} | {r['tcontext']} | {r['tclass']} | {' '.join(r['perms'])} | "
                  f"{(r['paths'] or [''])[0]} |")
    text = "\n".join(md) + "\n"
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
    if a.md:
        open(a.md, "w").write(text)
    if not (a.json or a.md):
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
