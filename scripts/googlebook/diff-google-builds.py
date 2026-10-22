#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""What did Google change between two Ruby builds, and what does it mean for the OpenBook patch layers?

Compares two staged stock trees (stage-stock-source.py): every partition by
SHA-256, then, inside the framework partitions OpenBook keeps from Google
(system, system_ext, product), every file. It then checks the file each
OpenBook patch layer is anchored to:

  trackpad correction   /system/lib64/libinputflinger.so (8-byte patch pinned to the whole-file hash)
  OTA certificate swap  /system/etc/security/otacerts.zip (pinned to the stock archive)
  Digitalis bridge      /system/build.prop native-bridge properties, /system/lib64/arm64
  owner OTA policy      /system/etc/selinux/plat_sepolicy.cil and mapping/<version>.cil
  vendor compatibility  framework compatibility matrices the fixed OpenBook vendor must satisfy

Private inputs; the report holds hashes, sizes and paths only.

usage: diff-google-builds.py --old STOCK_DIR --new STOCK_DIR --tools AOSP_HOST_BIN --work DIR --out report.json
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

FRAMEWORK = ("system", "system_ext", "product")
ANCHORS = {
    "trackpad correction": ["system/lib64/libinputflinger.so"],
    "OTA certificate swap": ["system/etc/security/otacerts.zip"],
    "Digitalis bridge": ["system/build.prop"],
    "owner OTA policy": ["system/etc/selinux/plat_sepolicy.cil", "system/etc/selinux/plat_sepolicy_vers.txt"],
}
PROPS = ("ro.dalvik.vm.native.bridge", "ro.dalvik.vm.isa.arm64", "ro.enable.native.bridge.exec64",
         "ro.build.version.incremental", "ro.build.id", "ro.build.version.security_patch", "ro.build.fingerprint")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tree(root):
    """{relative path: sha256 or 'symlink:target'} for every regular file and symlink."""
    out = {}
    for dirpath, dirs, files in os.walk(root):
        for name in files + [d for d in dirs if os.path.islink(os.path.join(dirpath, d))]:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            out[rel] = "symlink:" + os.readlink(full) if os.path.islink(full) else sha(full)
    return out


def props(path):
    if not path.is_file():
        return {}
    kv = dict(l.split("=", 1) for l in path.read_text(errors="replace").splitlines() if "=" in l and not l.startswith("#"))
    return {k: kv.get(k) for k in PROPS}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("old", "new", "tools", "work", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    old_rec = json.loads((a.old / "stock.json").read_text())
    new_rec = json.loads((a.new / "stock.json").read_text())
    parts = {}
    for name in sorted(set(old_rec["partitions"]) | set(new_rec["partitions"])):
        o, n = old_rec["partitions"].get(name), new_rec["partitions"].get(name)
        parts[name] = dict(changed=(o or {}).get("sha256") != (n or {}).get("sha256"),
                           old_bytes=(o or {}).get("bytes"), new_bytes=(n or {}).get("bytes"))
    a.work.mkdir(parents=True, exist_ok=True)
    trees, files = {}, {}
    env = dict(os.environ, LD_LIBRARY_PATH=str(a.tools.parent / "lib64"))
    for build, root in (("old", a.old), ("new", a.new)):
        trees[build] = {}
        for part in FRAMEWORK:
            dst = a.work / build / part
            shutil.rmtree(dst, ignore_errors=True)
            dst.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run([str(a.tools / "fsck.erofs"), f"--extract={dst}", str(root / f"{part}.img")],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
            # system's image holds the root (system/...); the others hold their partition's contents.
            trees[build][part] = tree(dst)
    for part in FRAMEWORK:
        o, n = trees["old"][part], trees["new"][part]
        files[part] = dict(added=sorted(set(n) - set(o)), removed=sorted(set(o) - set(n)),
                           changed=sorted(k for k in set(o) & set(n) if o[k] != n[k]), total_new=len(n))
    sysroot = {b: a.work / b / "system" for b in ("old", "new")}
    anchors = {}
    for layer, paths in ANCHORS.items():
        rows = []
        for rel in paths:
            o, n = trees["old"]["system"].get(rel), trees["new"]["system"].get(rel)
            rows.append(dict(path="/" + rel, present_old=o is not None, present_new=n is not None,
                             changed=o != n))
        anchors[layer] = dict(files=rows, needs_rework=any(r["changed"] for r in rows))
    arm64 = {b: sorted(k for k in trees[b]["system"] if k.startswith("system/lib64/arm64/")) for b in ("old", "new")}
    anchors["Digitalis bridge"]["arm64_dir_files"] = dict(old=len(arm64["old"]), new=len(arm64["new"]),
                                                          changed=sum(1 for k in set(arm64["old"]) & set(arm64["new"])
                                                                      if trees["old"]["system"][k] != trees["new"]["system"][k]))
    bp = {b: props(sysroot[b] / "system" / "build.prop") for b in ("old", "new")}
    vintf = sorted(k for part in FRAMEWORK for k in files[part]["changed"] + files[part]["added"]
                   if re.search(r"etc/vintf/.*compatibility_matrix", k))
    mapping = sorted(k for k in trees["new"]["system"] if re.match(r"system/etc/selinux/mapping/\d+\.cil$", k))
    report = dict(schema="openbook-google-build-diff/1", old_build=old_rec["build"], new_build=new_rec["build"],
                  partitions=parts, framework_files={k: dict(added=len(v["added"]), removed=len(v["removed"]),
                                                             changed=len(v["changed"]), total=v["total_new"])
                                                     for k, v in files.items()},
                  build_props=bp, anchors=anchors, compatibility_matrices_changed=vintf,
                  selinux_mappings_new=mapping, changed_paths={k: v["changed"][:400] for k, v in files.items()},
                  added_paths={k: v["added"][:200] for k, v in files.items()},
                  removed_paths={k: v["removed"][:200] for k, v in files.items()})
    a.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(old=report["old_build"], new=report["new_build"],
                          changed_partitions=[k for k, v in parts.items() if v["changed"]],
                          framework_files=report["framework_files"],
                          anchors={k: v["needs_rework"] for k, v in anchors.items()},
                          compatibility_matrices_changed=vintf, selinux_mappings=mapping,
                          build=bp["new"].get("ro.build.id"), security_patch=(bp["old"].get("ro.build.version.security_patch"),
                                                                                 bp["new"].get("ro.build.version.security_patch"))),
                     indent=1))


if __name__ == "__main__":
    main()
