#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply the pinned, source-built AOSP17 Digitalis bundle to an extracted Ruby tree.

Only used by the private experiment builder. Replaces the complete guest
library directory, adds the matching runners/proxies, and uses Ruby's existing
init file for binfmt registration. Every inode/xattr/content change is explicit.
"""
import hashlib
from pathlib import Path
import stat

BUNDLE_MANIFEST_SHA = "b1e2e2f7d5883fa650510fc5faef59824b7f1d7de02a536f38b8e78cbcf88604"
GUEST = "/system/lib64/arm64"
INIT = "/system/etc/init/berberis_arm_or_arm64.rc"
SKIP = "system/etc/init/berberis.rc"
NEW_BRIDGE = b"ro.dalvik.vm.native.bridge=libberberis_arm64.so\n"


def bundle_files(bundle):
    manifest = (bundle / "SHA256SUMS").read_bytes()
    if hashlib.sha256(manifest).hexdigest() != BUNDLE_MANIFEST_SHA:
        raise ValueError("Requires the pinned, source-built AOSP17 bundle")
    files = {}
    for line in manifest.decode().splitlines():
        digest, name = line.split(None, 1)
        name = name.strip()
        parts = Path(name).parts
        if not name.startswith("system/") or ".." in parts or name in files:
            raise ValueError("Invalid or duplicate bundle path")
        file = bundle / name
        if file.is_symlink() or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Bundle file differs: {name}")
        files[name] = file
    actual = {str(x.relative_to(bundle)) for x in (bundle / "system").rglob("*") if not x.is_dir()}
    if set(files) != actual or len(files) != 74:
        raise ValueError("Unexpected bundle inventory")
    return files


def properties(data):
    old = b"ro.dalvik.vm.native.bridge=libhoudini.so\n"
    lines = data.splitlines(keepends=True)
    if [x for x in lines if x.startswith(b"ro.dalvik.vm.native.bridge=")] != [old]:
        raise ValueError("Requires the original single Houdini selection")
    if data.count(b"ro.berberis.is_2nd_native_bridge=true\n") != 1:
        raise ValueError("Unexpected guest-layout property")
    if any(x.startswith(b"ro.berberis.flags=") for x in lines):
        raise ValueError("Unexpected pre-existing translator flags")
    return b"".join(NEW_BRIDGE if x == old else
        b"ro.berberis.is_2nd_native_bridge=false\n" if x == b"ro.berberis.is_2nd_native_bridge=true\n" else x
        for x in lines if not x.startswith(b"ro.berberis.version=")) + b"ro.berberis.flags=disable-ir-check\n"


def apply(root, rows, original, bundle, contents):
    files = bundle_files(bundle)
    inode, attrs = {}, {}
    for row in rows:
        f = row.split(" "); name = bytes.fromhex(f[1]).decode()
        if f[0] == "I": inode[name] = f
        elif f[0] == "X": attrs.setdefault(name, []).append(row)
        else: raise ValueError("Unexpected metadata row")
    original_rows = list(rows)
    removed = sorted(x for x in inode if x.startswith(GUEST + "/"))
    # This exact parent has a flat guest library directory. Reject an altered
    # tree rather than guessing how to preserve a new hierarchy/hardlinks.
    if any(stat.S_ISDIR(int(inode[x][2])) for x in removed):
        raise ValueError("Unexpected nested guest directory")
    for name in removed:
        (root / name.lstrip("/")).unlink()
        del inode[name]; attrs.pop(name, None)

    changed = set(removed)
    created = set()
    def install(name, data, *, executable=False):
        target = root / name.lstrip("/")
        parents = []
        p = Path(name).parent
        while str(p) not in inode:
            parents.append(str(p)); p = p.parent
        for directory in reversed(parents):
            (root / directory.lstrip("/")).mkdir()
            inode[directory] = ["I", directory.encode().hex(), str(stat.S_IFDIR | 0o755), "0", "0", "2", "0", "1230768000", "0"]
            attrs[directory] = [label_row(directory)]
            created.add(directory)
        if name in inode:
            if not stat.S_ISREG(int(inode[name][2])): raise ValueError(f"Refusing non-file replacement: {name}")
            target.chmod(target.stat().st_mode | 0o200)
            inode[name][6] = str(len(data))
        else:
            gid = "2000" if name.startswith("/system/bin/") else "0"
            inode[name] = ["I", name.encode().hex(), str(stat.S_IFREG | (0o755 if executable else 0o644)),
                           "0", gid, "1", str(len(data)), "1230768000", "0"]
            attrs[name] = [label_row(name)]
            created.add(name)
        target.write_bytes(data)
        changed.add(name)

    def label_row(name):
        label = "system_lib_file" if name.startswith("/system/lib64/") else "system_file"
        if name == "/system/etc/ld.config.arm64.txt": label = "system_linker_config_file"
        return f"X {name.encode().hex()} {b'security.selinux'.hex()} " + f"u:object_r:{label}:s0".encode().hex()

    for name, file in files.items():
        if name != SKIP:
            install("/" + name, file.read_bytes(), executable=name.startswith(("system/bin/", "system/lib64/")))
    prop = "/system/build.prop"
    install(prop, properties((root / prop.lstrip("/")).read_bytes()))
    install(INIT, b'''# Native executables for the selected, source-built ARM64 bridge.
on early-init
    mount binfmt_misc binfmt_misc /proc/sys/fs/binfmt_misc

on property:ro.dalvik.vm.native.bridge=libberberis_arm64.so
    copy /system/etc/binfmt_misc/arm64_exe /proc/sys/fs/binfmt_misc/register
    copy /system/etc/binfmt_misc/arm64_dyn /proc/sys/fs/binfmt_misc/register
''')
    # EROFS inventory reports directory sizes as zero. Only directory link
    # counts may change when a new child directory is added.
    for name, f in inode.items():
        if stat.S_ISDIR(int(f[2])):
            f[5] = str(2 + sum(stat.S_ISDIR(int(c[2])) and str(Path(child).parent) == (name or "/")
                               for child, c in inode.items() if child and child != name))
    expected = sorted([" ".join(f) for f in inode.values()] + [r for a in attrs.values() for r in a])
    after_contents = contents(root)
    unchanged = set(original) - changed
    if any(after_contents.get(name) != original[name] for name in unchanged):
        raise ValueError("Unrelated content changed during overlay")
    return expected, after_contents, {"bundle_manifest_sha256": BUNDLE_MANIFEST_SHA,
        "artifact_count": 74, "skipped_bundle_init": SKIP, "changed_files": sorted(changed),
        "added_paths": sorted(created), "removed_guest_paths": removed,
        "metadata_before_rows": len(original_rows), "metadata_after_rows": len(expected),
        "source_manifest": (bundle / "MANIFEST.txt").read_text()}
