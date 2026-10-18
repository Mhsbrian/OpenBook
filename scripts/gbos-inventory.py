#!/usr/bin/env python3
"""Inventory the apps, overlays, fonts and config XMLs of an unpacked Android image.

Works on Google's Googlebook recovery image (after scripts/gbos-unpack.sh), on an
emulator system image, or on our own out/target/product/<device>. Reads files only;
writes metadata (package names, versions, overlay values, file lists), never the
APKs or fonts themselves, so the output can be committed as evidence.

  scripts/gbos-inventory.py --aapt2 ~/anybook/aosp/src/out/host/linux-x86/bin/aapt2 \
      --part system=~/anybook/work/gbos-ruby/fs/system_a/system \
      --part system_ext=~/anybook/work/gbos-ruby/fs/system_ext_a \
      --part product=~/anybook/work/gbos-ruby/fs/product_a \
      --part vendor=~/anybook/work/gbos-ruby/fs/vendor_a \
      --out ~/anybook/gbos-ui/ruby

Produces in --out:
  packages.tsv     one row per APK: partition, kind (app/priv-app/overlay/other), path,
                   package, versionName, versionCode, targetSdk, native ABIs, MiB, label,
                   overlay target, overlay isStatic, overlay priority
  overlays/        `aapt2 dump resources` of every overlay APK (resource values only)
  fonts.tsv        font files per partition with sizes
  config-xml.txt   names of permissions/sysconfig/default-permissions XMLs per partition
  props/           every build.prop, as text
"""
import argparse
import os
import re
import shutil
import subprocess
import sys


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return p.stdout


def badging(aapt2, apk):
    out = run([aapt2, "dump", "badging", apk])
    info = {}
    m = re.search(r"package: name='([^']*)' versionCode='([^']*)' versionName='([^']*)'", out)
    if m:
        info["package"], info["versionCode"], info["versionName"] = m.groups()
    m = re.search(r"targetSdkVersion:'([^']*)'", out)
    info["targetSdk"] = m.group(1) if m else ""
    m = re.search(r"application-label:'([^']*)'", out)
    info["label"] = m.group(1) if m else ""
    m = re.search(r"native-code: (.*)", out)
    info["abis"] = m.group(1).replace("'", "") if m else ""
    return info


def overlay_info(aapt2, apk):
    out = run([aapt2, "dump", "xmltree", "--file", "AndroidManifest.xml", apk])
    info = {}
    block = out.split("E: overlay", 1)
    if len(block) < 2:
        return info
    # attributes of the <overlay> element run until the next element
    attrs = block[1].split("E: ", 1)[0]
    for key in ("targetPackage", "isStatic", "priority", "requiredSystemPropertyName",
                "requiredSystemPropertyValue", "targetName"):
        m = re.search(r"A: (?:http://schemas.android.com/apk/res/android:)?%s\([^)]*\)=(?:\(type 0x[0-9a-f]+\))?(\S+)" % key, attrs)
        if m:
            info[key] = m.group(1).strip('"')
    return info


def kind_of(rel):
    for k in ("priv-app", "app", "overlay"):
        if rel.startswith(k + "/") or ("/%s/" % k) in "/" + rel:
            return k
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aapt2", required=True)
    ap.add_argument("--part", action="append", required=True, help="name=path")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    parts = [p.split("=", 1) for p in a.part]
    os.makedirs(os.path.join(a.out, "overlays"), exist_ok=True)
    os.makedirs(os.path.join(a.out, "props"), exist_ok=True)

    rows, fonts, xmls = [], [], []
    for name, root in parts:
        root = os.path.expanduser(root)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            rel_dir = os.path.relpath(dirpath, root)
            # skip nested partition mount points inside system (product/, vendor/ ...)
            if name == "system" and rel_dir.split(os.sep)[0] in ("product", "system_ext", "vendor", "odm"):
                dirnames[:] = []
                continue
            for f in sorted(filenames):
                path = os.path.join(dirpath, f)
                rel = os.path.normpath(os.path.join(rel_dir, f))
                if os.path.islink(path):
                    continue
                if f.endswith(".apk") and not rel.startswith("apex/"):
                    info = badging(a.aapt2, path)
                    kind = kind_of(rel)
                    ov = overlay_info(a.aapt2, path) if kind == "overlay" or "overlay" in rel.lower() or "rro" in f.lower() else {}
                    if ov.get("targetPackage"):
                        kind = "overlay"
                        dump = run([a.aapt2, "dump", "resources", path])
                        with open(os.path.join(a.out, "overlays", "%s__%s.txt" % (name, f[:-4])), "w") as fh:
                            fh.write("# %s/%s target=%s\n" % (name, rel, ov.get("targetPackage")))
                            fh.write(dump)
                    rows.append([name, kind, rel, info.get("package", ""), info.get("versionName", ""),
                                 info.get("versionCode", ""), info.get("targetSdk", ""), info.get("abis", ""),
                                 "%.1f" % (os.path.getsize(path) / 2**20), info.get("label", ""),
                                 ov.get("targetPackage", ""), ov.get("isStatic", ""), ov.get("priority", "")])
                elif re.search(r"\.(ttf|otf|ttc|otc)$", f) and "fonts" in rel:
                    fonts.append([name, rel, str(os.path.getsize(path))])
                elif f.endswith(".xml") and re.match(r"etc/(permissions|sysconfig|default-permissions|preferred-apps)/", rel):
                    xmls.append("%s\t%s" % (name, rel))
                elif f == "build.prop" or f.endswith("build.prop"):
                    shutil.copyfile(path, os.path.join(a.out, "props", "%s__%s" % (name, rel.replace("/", "_"))))
                elif re.match(r"etc/(fonts|font_fallback|fonts_customization)\.xml$", rel):
                    shutil.copyfile(path, os.path.join(a.out, "props", "%s__%s" % (name, rel.replace("/", "_"))))

    hdr = ["partition", "kind", "path", "package", "versionName", "versionCode", "targetSdk", "abis",
           "MiB", "label", "overlayTarget", "isStatic", "priority"]
    with open(os.path.join(a.out, "packages.tsv"), "w") as fh:
        fh.write("\t".join(hdr) + "\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")
    with open(os.path.join(a.out, "fonts.tsv"), "w") as fh:
        fh.write("partition\tpath\tbytes\n")
        for r in fonts:
            fh.write("\t".join(r) + "\n")
    with open(os.path.join(a.out, "config-xml.txt"), "w") as fh:
        fh.write("\n".join(xmls) + "\n")
    print("%d APKs (%d overlays), %d fonts, %d config XMLs -> %s" % (
        len(rows), sum(1 for r in rows if r[1] == "overlay"), len(fonts), len(xmls), a.out))


if __name__ == "__main__":
    sys.exit(main())
