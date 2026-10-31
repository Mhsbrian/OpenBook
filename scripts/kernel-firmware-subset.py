#!/usr/bin/env python3
"""Pick the linux-firmware files a set of kernel modules needs, stage them, and record each file's licence.

usage: kernel-firmware-subset.py --fw LINUX_FIRMWARE_GIT --modules DIR --rules RULES
                                 [--out STAGE_DIR] [--list OUT.tsv] [--report OUT.md]

  --fw       a linux-firmware git clone (a --no-checkout clone is enough; files are read from HEAD)
  --modules  directory searched for *.ko; `modinfo -F firmware` gives what each module may request
  --rules    kernel/firmware/<profile>.rules:
               module <name> <regex>   keep the MODULE_FIRMWARE names of module <name> that match <regex>
               extra <driver> <regex>  also keep linux-firmware files matching <regex> that the driver
                                       loads by a runtime-built name (no MODULE_FIRMWARE entry)
  --out      copy the selected files (and the licence files they cite) here, with linux-firmware's layout

Licences come from linux-firmware's WHENCE: the block that lists a file gives its Driver and Licence lines.
Names that are a WHENCE "Link:" are resolved to their target and staged as a symlink; so are names under a linked
directory (nvidia/gb205 -> gb202), however many links deep.
"""
import argparse
import collections
import glob
import hashlib
import os
import re
import subprocess
import sys


def git(fw, *args, binary=False):
    return subprocess.run(["git", "-C", fw, *args], check=True, capture_output=True, text=not binary).stdout


def parse_whence(text):
    """file -> (driver, licence, link_target or None).

    Within a WHENCE block, a Licence line applies to the File/Link lines above it (back to the previous
    Licence line); files after the last Licence line of a block take that last licence."""
    info = {}
    for block in re.split(r"^-{10,}\s*$", text, flags=re.M):
        drivers = re.findall(r"^Driver:\s*(.+)$", block, re.M)
        driver = drivers[0].strip() if drivers else "?"
        pending, licence = [], "?"
        for line in block.splitlines():
            m = re.match(r"^(?:Raw)?File:\s*\"?([^\"]+?)\"?\s*$", line)
            if m:
                pending.append((m[1], None))
                continue
            m = re.match(r"^Link:\s*(\S+)\s*->\s*(\S+)\s*$", line)
            if m:
                pending.append((m[1], os.path.normpath(os.path.join(os.path.dirname(m[1]), m[2]))))
                continue
            m = re.match(r"^Licen[cs]e:\s*(.+)$", line)
            if m:
                licence = m[1].strip()
                for f, target in pending:
                    info[f] = (driver, licence, target)
                pending = []
        for f, target in pending:
            info[f] = (driver, licence, target)
    return info


def resolve(f, whence, tree):
    """(file in the tree that name f ends up at, WHENCE entry that first describes f), following file links and
    directory links (a Link: whose name is a directory prefix of f); (None, None) when f leads nowhere."""
    entry, seen = None, set()
    while f not in tree:
        if f in seen:
            return None, None
        seen.add(f)
        if f in whence and whence[f][2]:
            entry = entry or whence[f]
            f = whence[f][2]
            continue
        parts = f.split("/")
        for i in range(len(parts) - 1, 0, -1):
            d = "/".join(parts[:i])
            if d in whence and whence[d][2]:
                entry = entry or whence[d]
                f = "/".join([whence[d][2]] + parts[i:])
                break
        else:
            return None, None
    return f, entry or whence.get(f)


def licence_files(licence):
    return sorted({f.rstrip(".") for f in re.findall(r"\b(LICEN[CS]E[\w.\-]*|GPL-[23])", licence)})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fw", required=True)
    ap.add_argument("--modules", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--out")
    ap.add_argument("--list")
    ap.add_argument("--report")
    a = ap.parse_args()

    head = git(a.fw, "log", "-1", "--format=%H %cs").strip()
    tree = set(git(a.fw, "ls-tree", "-r", "--name-only", "HEAD").split("\n")) - {""}
    whence = parse_whence(git(a.fw, "show", "HEAD:WHENCE"))

    declared = {}
    for ko in sorted(glob.glob(os.path.join(a.modules, "**", "*.ko"), recursive=True)):
        name = os.path.basename(ko)[:-3].replace("-", "_")
        fws = subprocess.run(["modinfo", "-F", "firmware", ko], capture_output=True, text=True).stdout.split()
        declared[name] = fws

    want = collections.OrderedDict()  # firmware name -> requested-by
    rules = []
    for line in open(a.rules):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        kind, who, rx = line.split(None, 2)
        rules.append((kind, who, re.compile(rx)))
        if kind == "module":
            mod = who.replace("-", "_")
            if mod not in declared:
                sys.exit(f"rules name module {who}, which is not under {a.modules}")
            for f in declared[mod]:
                if rx and re.fullmatch(rx, f):
                    want.setdefault(f, who)
        elif kind == "extra":
            for f in sorted(tree | {k for k, v in whence.items() if v[2]}):
                if re.fullmatch(rx, f):
                    want.setdefault(f, who)

    rows, missing, lic_needed, missing_lic = [], [], set(), []
    for f, who in want.items():
        src, entry = resolve(f, whence, tree)
        if src is None:
            missing.append((f, who))
            continue
        driver, licence, _ = entry or ("?", "?", None)
        link = src if src != f else None
        blob = git(a.fw, "show", f"HEAD:{src}", binary=True)
        rows.append(dict(file=f, link=link or "", size=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
                         driver=driver, licence=licence, by=who))
        lic_needed.update(licence_files(licence))
        if a.out:
            dst = os.path.join(a.out, src)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").write(blob)
            if link:
                lnk = os.path.join(a.out, f)
                os.makedirs(os.path.dirname(lnk), exist_ok=True)
                if os.path.lexists(lnk):
                    os.remove(lnk)
                os.symlink(os.path.relpath(dst, os.path.dirname(lnk)), lnk)
    if a.out:
        for l in sorted(lic_needed):
            for src in (l, f"LICENSES/{l}"):  # newer linux-firmware keeps them under LICENSES/
                if src in tree:
                    os.makedirs(os.path.dirname(os.path.join(a.out, src)) or a.out, exist_ok=True)
                    open(os.path.join(a.out, src), "wb").write(git(a.fw, "show", f"HEAD:{src}", binary=True))
                    break
            else:
                missing_lic.append(l)
        open(os.path.join(a.out, "WHENCE"), "w").write(git(a.fw, "show", "HEAD:WHENCE"))

    if a.list:
        with open(a.list, "w") as o:
            o.write(f"# linux-firmware {head}\n# file\tlink_target\tsize\tsha256\trequested_by\tdriver\tlicence\n")
            for r in rows:
                o.write("\t".join(str(r[k]) for k in ("file", "link", "size", "sha256", "by", "driver", "licence")) + "\n")
            for f, who in missing:
                o.write(f"{f}\tMISSING\t\t\t{who}\t\t\n")

    by_lic = collections.Counter()
    size_lic = collections.Counter()
    for r in rows:
        by_lic[r["licence"]] += 1
        size_lic[r["licence"]] += r["size"]
    rep = [f"# Firmware subset ({os.path.basename(a.rules)})", "",
           f"linux-firmware `{head}`: {len(rows)} files, {sum(r['size'] for r in rows) / 1e6:.1f} MB; "
           f"{len(missing)} requested names not in linux-firmware.", "",
           "| licence (from WHENCE) | files | MB |", "|---|---|---|"]
    rep += [f"| {l} | {n} | {size_lic[l] / 1e6:.2f} |" for l, n in by_lic.most_common()]
    rep += ["", "| requested by | files |", "|---|---|"]
    rep += [f"| {w} | {n} |" for w, n in collections.Counter(r["by"] for r in rows).most_common()]
    rep += ["", "Licence files staged: " + ", ".join(f"`{l}`" for l in sorted(lic_needed) if l not in missing_lic)]
    if missing_lic:
        rep += ["", "Licence files cited in WHENCE but not found: " + ", ".join(missing_lic)]
    if missing:
        rep += ["", "Requested but not in linux-firmware:", ""] + [f"- `{f}` ({w})" for f, w in missing]
    if a.report:
        open(a.report, "w").write("\n".join(rep) + "\n")
    print("\n".join(rep))


if __name__ == "__main__":
    main()
