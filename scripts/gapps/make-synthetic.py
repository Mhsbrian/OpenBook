#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble ANAL-211's synthetic Google apps packages in LiteGapps' layout (docs/gapps.md section 5): a zip with
module.prop and files/files.tar.br (LiteGapps' default compression), whose tar holds x86_64/37/system/product/...
Everything in them is OpenBook's own (scripts/gapps/build-synthetic-apks.sh, testapps/etc/): no Google software. The
zip also carries the parts of a LiteGapps zip the installer ignores (META-INF update scripts, customize.sh, bin/), so
a test shows they are not installed.

Writes to OUT:
  openbook-synthetic-gapps-x86_64-37.zip       the reference package (brotli, GNU tar)
  openbook-synthetic-gapps-x86_64-37-xz.zip    the same files, xz and a pax tar
  openbook-synthetic-gapps-x86_64-37-tar.zip   the same files, an uncompressed ustar tar
  neg-<case>.zip                               one defect each; EXPECTED.json lists the rule the check must report
  SHA256SUMS
Deterministic: fixed times, owners and order.

usage: make-synthetic.py --apks DIR --etc DIR --out DIR   (runs in the openbook-installer container: xz, brotli)
"""
import argparse
import hashlib
import io
import json
import os
import subprocess
import tarfile
import zipfile

MTIME = 1767225600  # 2026-01-01
PREFIX = "x86_64/37/system/product"
MODULE_PROP = """id=litegapps
name=OpenBook synthetic test package (not Google apps)
version=v1.0-anal211
versionCode=211
author=OpenBook (ANAL-211 tests)
description=Synthetic packages for the installer's bring-your-own GApps tests. Contains no Google software.
litegapps_type=litegapps
litegapps_arch={arch}
litegapps_sdk={sdk}
"""


def tree(apks, etc):
    """The reference package's files below PREFIX: (path, bytes)."""
    rd = lambda p: open(p, "rb").read()
    return [
        ("priv-app/OpenBookTestGsf/OpenBookTestGsf.apk", rd(f"{apks}/OpenBookTestGsf.apk")),
        ("priv-app/OpenBookTestPriv/OpenBookTestPriv.apk", rd(f"{apks}/OpenBookTestPriv.apk")),
        ("app/OpenBookTestApp/OpenBookTestApp.apk", rd(f"{apks}/OpenBookTestApp.apk")),
        ("app/OpenBookTestApp/lib/x86_64/libobgapps.so", rd(f"{apks}/libobgapps-x86_64.so")),
        ("etc/permissions/privapp-permissions-openbook-synthetic.xml",
         rd(f"{etc}/privapp-permissions-openbook-synthetic.xml")),
        ("etc/sysconfig/openbook-synthetic-sysconfig.xml", rd(f"{etc}/openbook-synthetic-sysconfig.xml")),
        ("etc/default-permissions/default-permissions-openbook-synthetic.xml",
         rd(f"{etc}/default-permissions-openbook-synthetic.xml")),
    ]


def make_tar(entries, fmt=tarfile.GNU_FORMAT, links=()):
    """entries: (full path in the tar, bytes); directories are added for every parent, as `tar -cf files.tar *`."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=fmt) as t:
        dirs = set()
        for path, _ in entries:
            parts = path.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        for d in sorted(dirs):
            ti = tarfile.TarInfo(d)
            ti.type, ti.mode, ti.mtime, ti.uname, ti.gname = tarfile.DIRTYPE, 0o755, MTIME, "root", "root"
            t.addfile(ti)
        for path, data in sorted(entries):
            ti = tarfile.TarInfo(path)
            ti.size, ti.mode, ti.mtime, ti.uname, ti.gname = len(data), 0o644, MTIME, "root", "root"
            t.addfile(ti, io.BytesIO(data))
        for path, target in links:
            ti = tarfile.TarInfo(path)
            ti.type, ti.linkname, ti.mtime = tarfile.SYMTYPE, target, MTIME
            t.addfile(ti)
    return buf.getvalue()


def compress(data, kind):
    if kind == "tar":
        return data
    cmd = {"br": ["brotli", "-1", "-c"], "xz": ["xz", "-6", "-c", "-T1"]}[kind]
    return subprocess.run(cmd, input=data, capture_output=True, check=True).stdout


def write_zip(path, prop, payload_name, payload, extra=()):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        def add(name, data, method=zipfile.ZIP_DEFLATED):
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = method
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
        add("META-INF/com/google/android/update-binary", b"#!/sbin/sh\n# synthetic test package: not a real installer\n")
        add("META-INF/com/google/android/updater-script", b"#MAGISK\n")
        add("customize.sh", b"# synthetic test package: the OpenBook installer never runs this\nabort\n")
        add("bin/x86_64/README", b"LiteGapps zips carry helper binaries here; the OpenBook installer ignores them.\n")
        if prop is not None:
            add("module.prop", prop.encode())
        if payload_name:
            add(payload_name, payload)
        for name, data in extra:
            add(name, data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apks", required=True)
    ap.add_argument("--etc", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    files = tree(a.apks, a.etc)
    full = [(f"{PREFIX}/{p}", d) for p, d in files]
    prop = MODULE_PROP.format(arch="x86_64", sdk=37)
    out = {}

    def package(name, entries=None, kind="br", fmt=tarfile.GNU_FORMAT, links=(), prop_text=prop, payload_name=None,
                extra=()):
        entries = full if entries is None else entries
        tar = make_tar(entries, fmt, links)
        pn = payload_name if payload_name is not None else f"files/files.tar{'' if kind == 'tar' else '.' + kind}"
        path = f"{a.out}/{name}.zip"
        write_zip(path, prop_text, pn, compress(tar, kind) if pn else b"", extra)
        out[name] = hashlib.sha256(open(path, "rb").read()).hexdigest()
        return path

    package("openbook-synthetic-gapps-x86_64-37")
    package("openbook-synthetic-gapps-x86_64-37-xz", kind="xz", fmt=tarfile.PAX_FORMAT)
    package("openbook-synthetic-gapps-x86_64-37-tar", kind="tar", fmt=tarfile.USTAR_FORMAT)

    rd = lambda p: open(f"{a.apks}/{p}", "rb").read()
    add = lambda rel, data: full + [(f"{PREFIX}/{rel}", data)]
    swap = lambda rel, data: [(p, data if p == f"{PREFIX}/{rel}" else d) for p, d in full]
    xml = lambda root, body: f'<?xml version="1.0" encoding="utf-8"?>\n<{root}>\n{body}\n</{root}>\n'.encode()
    negs = {  # name: (entries or None, extra package() args, the rule gapps-check must report, or "plan:<code>")
        "arm-only": (add("priv-app/OpenBookTestArmOnly/OpenBookTestArmOnly.apk", rd("OpenBookTestArmOnly.apk")), {},
                     "native_abi"),
        "platform-uid": (add("priv-app/OpenBookTestPlatformUid/OpenBookTestPlatformUid.apk",
                             rd("OpenBookTestPlatformUid.apk")), {}, "platform_uid"),
        "unsigned": (swap("priv-app/OpenBookTestPriv/OpenBookTestPriv.apk", rd("OpenBookTestPriv-unsigned.apk")), {},
                     "unsigned"),
        "arm-lib-dir": (add("app/OpenBookTestApp/lib/arm64-v8a/libobgapps.so", rd("libobgapps-arm64.so")), {},
                        "native_abi"),
        "bad-elf": (swap("app/OpenBookTestApp/lib/x86_64/libobgapps.so", rd("libobgapps-arm64.so")), {}, "native_abi"),
        "framework": (add("framework/com.google.android.maps.jar", b"PK\x05\x06" + b"\0" * 18), {}, "framework"),
        "overlay": (add("overlay/OpenBookTestOverlay.apk", rd("OpenBookTestApp.apk")), {}, "framework"),
        "init": (add("etc/init/openbook-synthetic.rc", b"service x /system/bin/sh\n"), {}, "init"),
        "selinux": (add("etc/selinux/product_sepolicy.cil", b"(allow untrusted_app kernel (file (read)))\n"), {},
                    "selinux"),
        "lib64": (add("lib64/libobgapps.so", rd("libobgapps-x86_64.so")), {}, "native_lib"),
        "system-ext": (full + [("x86_64/37/system/system_ext/priv-app/OpenBookTestApp/OpenBookTestApp.apk",
                                rd("OpenBookTestApp.apk"))], {}, "outside_product"),
        "vendor": (full + [("x86_64/37/vendor/etc/openbook-synthetic.xml", b"<config/>\n")], {}, "outside_product"),
        "wrong-sdk": ([(p.replace("x86_64/37/", "x86_64/36/"), d) for p, d in full],
                      {"prop_text": MODULE_PROP.format(arch="x86_64", sdk=36)}, "wrong_sdk"),
        "wrong-sdk-tree": ([(p.replace("x86_64/37/", "x86_64/36/"), d) for p, d in full],
                           {"prop_text": "id=litegapps\nname=no target in module.prop\n"}, "wrong_sdk"),
        "wrong-arch": ([(p.replace("x86_64/37/", "arm64/37/"), d) for p, d in full],
                       {"prop_text": MODULE_PROP.format(arch="arm64", sdk=37)}, "wrong_arch"),
        "traversal": (full + [(f"{PREFIX}/../../../../../etc/openbook-escape.xml", b"<permissions/>\n")], {},
                      "unsafe_path"),
        "symlink": (full, {"links": [(f"{PREFIX}/etc/permissions/link.xml", "/system/etc/hosts")]}, "link"),
        "xml-library": (add("etc/permissions/com.google.android.maps.xml",
                            xml("permissions", '    <library name="com.google.android.maps" '
                                               'file="/product/framework/com.google.android.maps.jar" />')), {},
                        "framework"),
        "xml-assign": (add("etc/sysconfig/openbook-assign.xml",
                           xml("config", '    <assign-permission name="android.permission.INTERNET" uid="shell" />')),
                       {}, "framework"),
        "xml-group": (add("etc/permissions/openbook-group.xml",
                          xml("permissions", '    <permission name="android.permission.INTERNET">\n'
                                             '        <group gid="inet" />\n    </permission>')), {}, "framework"),
        "xml-doctype": (add("etc/permissions/openbook-doctype.xml",
                            b'<?xml version="1.0"?>\n<!DOCTYPE permissions [<!ENTITY x "y">]>\n<permissions/>\n'),
                        {}, "xml_doctype"),
        "xml-unknown": (add("etc/sysconfig/openbook-unknown.xml", xml("config", '    <hidden-feature name="x" />')),
                        {}, "xml_element"),
        "not-litegapps": (full, {"payload_name": ""}, "code:not_a_package"),
        "empty": ([], {}, "empty"),
        "clash": (add("etc/permissions/com.android.contacts.xml", xml("permissions", "")), {}, "plan:gapps_clash"),
    }
    expected = {}
    for name, (entries, kw, rule) in negs.items():
        package(f"neg-{name}", entries, **kw)
        expected[f"neg-{name}"] = rule
    # A damaged package: one byte of the compressed payload flipped (the zip's CRC-32 or the decoder catches it).
    good = open(f"{a.out}/openbook-synthetic-gapps-x86_64-37.zip", "rb").read()
    with zipfile.ZipFile(io.BytesIO(good)) as z:
        info = z.getinfo("files/files.tar.br")
    lh = good[info.header_offset:info.header_offset + 30]
    data_at = info.header_offset + 30 + int.from_bytes(lh[26:28], "little") + int.from_bytes(lh[28:30], "little")
    bad = bytearray(good)
    bad[data_at + info.compress_size // 2] ^= 0x40
    open(f"{a.out}/neg-corrupt.zip", "wb").write(bad)
    out["neg-corrupt"] = hashlib.sha256(bad).hexdigest()
    expected["neg-corrupt"] = "code:not_a_package"
    open(f"{a.out}/neg-not-a-zip.zip", "wb").write(b"this is not a zip file\n" * 10)
    out["neg-not-a-zip"] = hashlib.sha256(open(f"{a.out}/neg-not-a-zip.zip", "rb").read()).hexdigest()
    expected["neg-not-a-zip"] = "code:not_a_package"
    json.dump({"files": {p: hashlib.sha256(d).hexdigest() for p, d in files}, "expected": expected},
              open(f"{a.out}/EXPECTED.json", "w"), indent=1, sort_keys=True)
    with open(f"{a.out}/SHA256SUMS", "w") as f:
        for n in sorted(out):
            f.write(f"{out[n]}  {n}.zip\n")
    print(open(f"{a.out}/SHA256SUMS").read())


if __name__ == "__main__":
    main()
