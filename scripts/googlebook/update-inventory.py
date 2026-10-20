#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read retained Ruby files and emit a small, shareable update inventory.

No downloads, devices, package changes or raw user logs. Extracted-tree hashes
identify inspected files; they do not authenticate the original Google input.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def props(root):
    result = {}
    for path in (root / "build.prop", root / "etc/build.prop"):
        if path.is_file():
            for line in path.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    if any(s in key for s in ("fingerprint", "security_patch", "ab_update",
                                              "ab_ota", "virtual_ab", "desktop_os")):
                        result[key] = value
    return result


def components(text):
    """Extract direct component attributes from aapt2's xmltree output."""
    result = []
    current = None
    for line in text.splitlines():
        element = re.match(r"(\s*)E: (\S+)", line)
        if element:
            depth, kind = len(element[1]), element[2]
            if current and depth <= current["_depth"]:
                if current.get("name", "").startswith("com.google.android.gms.update."):
                    result.append({k: v for k, v in current.items() if k != "_depth"})
                current = None
            if kind in ("service", "receiver", "provider", "activity"):
                current = {"kind": kind, "_depth": depth}
        attr = re.match(r"(\s*)A: http://schemas.android.com/apk/res/android:"
                        r"(name|enabled|exported|permission|directBootAware)\([^)]*\)=(.*)", line)
        if current and attr and len(attr[1]) == current["_depth"] + 2:
            current[attr[2]] = attr[3].split(" (Raw:")[0].strip('"')
    if current and current.get("name", "").startswith("com.google.android.gms.update."):
        result.append({k: v for k, v in current.items() if k != "_depth"})
    return result


def inventory(ruby, vendor, apex, live, aapt):
    roots = {"system": ruby / "fs/system_a/system", "system_ext": ruby / "fs/system_ext_a",
             "product": ruby / "fs/product_a", "stock_vendor": ruby / "fs/vendor_a",
             "hybrid_vendor": vendor,
             "recovery": ruby / "ramdisks/vendor_boot_a_vendor_ramdisk01/system"}
    report = {"schema": "openbook-ruby-update-inventory/1",
              "scope": "Static retained inputs; no current device or network measurement",
              "properties": {name: props(root) for name, root in roots.items()},
              "files": {}, "init_services": {}, "ota_certificates": {}}
    wanted = re.compile(r"(update_engine|update_verifier|boot-service|bootsync|fstab|"
                        r"otacerts|snapshot|snapuserd|updater-wrapper|firmware_updater)")
    for name, root in roots.items():
        for path in sorted(root.rglob("*")):
            rel = str(path.relative_to(root))
            if path.is_symlink() or not path.is_file() or not wanted.search(rel):
                continue
            if not (rel.startswith(("bin/", "etc/init/", "etc/vintf/")) or
                    "fstab" in rel or "otacerts" in rel):
                continue
            label = f"{name}/{rel}"
            report["files"][label] = sha(path)
            if rel.endswith(".rc"):
                report["init_services"][label] = [
                    line.strip() for line in path.read_text().splitlines()
                    if line.strip() and not line.lstrip().startswith("#")]
            if path.name == "otacerts.zip":
                with zipfile.ZipFile(path) as archive:
                    report["ota_certificates"][label] = {
                        member: hashlib.sha256(archive.read(member)).hexdigest()
                        for member in archive.namelist() if not member.endswith("/")}
    apks = list(apex.glob("com.google.android.gmssystem/priv-app/*/*.apk"))
    if len(apks) != 1:
        raise ValueError("Expected one retained GmsSystem APK; inspect the new packaging")
    text = subprocess.check_output([str(aapt), "dump", "xmltree", str(apks[0]),
                                    "--file", "AndroidManifest.xml"], text=True)
    report["gms"] = {"apk_sha256": sha(apks[0]), "aapt2_sha256": sha(aapt),
                     "update_components": components(text),
                     "recovery_permission_declared": '"android.permission.RECOVERY"' in text,
                     "reboot_permission_declared": '"android.permission.REBOOT"' in text}
    report["gms"]["privileged_allowlists"] = {}
    for label, directory in (("product", roots["product"] / "etc/permissions"),
                             ("gms-apex", apex / "com.google.android.gmssystem/etc/permissions")):
        for path in sorted(directory.glob("privapp*.xml")):
            grants = [p.attrib["name"] for group in ET.parse(path).iter("privapp-permissions")
                      if group.get("package") == "com.google.android.gms"
                      for p in group.findall("permission")]
            if grants:
                report["gms"]["privileged_allowlists"][f"{label}/{path.name}"] = {
                    "sha256": sha(path), "grants": grants}
    manifest = json.loads(live.read_text())
    report["hybrid"] = {"manifest_sha256": sha(live),
                        "image_sha256": manifest["image_sha256"],
                        "partition_names": [row["name"] for row in manifest["gpt"]],
                        "logical_sha256": manifest["logical_sha256"],
                        "kernel_sha256": manifest["kernel_sha256"],
                        "boot_modes": manifest["entries"]}
    report["unattended_safe"] = False
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ruby", "vendor", "apex", "live-manifest", "aapt2", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = inventory(args.ruby, args.vendor, args.apex, args.live_manifest, args.aapt2)
    with args.out.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
