#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a private Ruby ARM bridge configuration experiment. Regular images only.

Requires the read-only erofs-inventory helper built against the AOSP host tools.
Rebuilds EROFS with original ownership/labels, then compares EVERY inode/xattr
and file. Unknown extended attributes or hardlinks fail closed.
No userdata from an installed laptop is an input. Never flash this whole image
over a configured device. Release packaging and a reviewed preserving updater
are separate steps. OPENBOOK_RELEASE_TOOLS names the pinned PR #123 checkout.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import struct

HERE = Path(os.environ["OPENBOOK_RELEASE_TOOLS"]).resolve() / "scripts/googlebook"
TOOLS_COMMIT = "ca0335c2ae06062cc6b45560b3b57a3b304e6c01"
LOCK = json.loads(Path(__file__).with_name("bridge-tooling-lock.json").read_text())
if LOCK["commit"] != TOOLS_COMMIT:
    raise ValueError("Tooling lock revision differs")
for name, expected_sha in LOCK["files"].items():
    if hashlib.sha256((HERE.parents[1] / name).read_bytes()).hexdigest() != expected_sha:
        raise ValueError(f"Pinned release helper changed: {name}")


def load(name, file):
    s = importlib.util.spec_from_file_location(name, HERE / file)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


p = load("preserve", "preserve-update.py")
BASE_SHA = "554fb78970f94d985c8be86f4b07c42c5f64ea9823eac33816a993a5d88dffe6"
TARGET = "/system/build.prop"
OLD = b"ro.dalvik.vm.native.bridge=libhoudini.so\n"
NEW = b"ro.dalvik.vm.native.bridge=libndk_translation.so\n"
CONTEXTS = "/system/etc/selinux/plat_file_contexts"
MOUNTPOINT = "/system/lib64/arm64"
RESERVE = 40 << 30


def space(out, additional):
    free = shutil.disk_usage(out).free
    if free < RESERVE + additional:
        raise ValueError(f"Space reserve: need {additional} additional bytes, have {free} above {RESERVE} reserve")


def remove_extracted(path):
    # fsck.erofs may preserve read-only directory modes. This is a newly created
    # extraction owned by this invocation; never follow a directory symlink.
    for directory in [path, *path.rglob("*")]:
        if directory.is_dir() and not directory.is_symlink():
            directory.chmod(directory.stat().st_mode | 0o700)
    shutil.rmtree(path)


def patch(data):
    lines = data.splitlines(keepends=True)
    active = [line for line in lines if line.startswith(b"ro.dalvik.vm.native.bridge=")]
    if active != [OLD]:
        raise ValueError("Expected exactly one active Houdini selection")
    if data.count(b"ro.berberis.is_2nd_native_bridge=true\n") != 1:
        raise ValueError("Retain Ruby's secondary-layout flag so its init bind-mount selects the matching guest libraries")
    return b"".join(NEW if line == OLD else line for line in lines)


def metadata_expected(rows, size_delta, target=TARGET):
    encoded = target.encode().hex()
    expected = []
    for row in rows:
        fields = row.split(" ")
        if fields[:2] == ["I", encoded]:
            fields[6] = str(int(fields[6]) + size_delta)
            row = " ".join(fields)
        expected.append(row)
    return sorted(expected)



def inventory(tool, image):
    rows = subprocess.check_output([str(tool), str(image)], text=True).splitlines()
    # Ordering of shared xattrs and directory entries is immaterial.
    return sorted(rows)


def contents(root):
    result = {}
    for path in root.rglob("*"):
        name = "/" + str(path.relative_to(root))
        if path.is_symlink():
            result[name] = ["symlink", os.readlink(path)]
        elif path.is_file():
            result[name] = ["file", p.h.audit.sha(path)]
    return result


def rebuild_files(tools, inventory_tool, image, source, before, original,
                  changes, partition, w, mountpoint="", labels=None):
    """Verify the complete diff against explicit content and label changes."""
    run = p.h.run
    labels = labels or {}
    expected_metadata = before
    for target, (old_data, new_data) in changes.items():
        expected_metadata = metadata_expected(expected_metadata, len(new_data) - len(old_data), target)
    for target, (old_label, new_label) in labels.items():
        expected_metadata = relabel_metadata(expected_metadata, target, old_label, new_label)
    fsconfig, contexts = [], []
    for row in (r.split(" ") for r in before if r.startswith("I ")):
        _, encoded, mode, uid, gid, nlink, size, seconds, nanos = row
        path = bytes.fromhex(encoded).decode()
        if any(c.isspace() for c in path):
            raise ValueError("Unsupported whitespace in fs_config path")
        if int(nlink) != 1 and int(mode) & 0o170000 != 0o040000:
            raise ValueError("Hardlinks require explicit topology preservation")
        local = source / path.lstrip("/")
        if not local.is_symlink():
            os.chmod(local, int(mode) & 0o7777)
        os.utime(local, ns=(int(seconds) * 10**9 + int(nanos),) * 2, follow_symlinks=False)
        attrs = [r.split(" ") for r in before if r.startswith(f"X {encoded} ")]
        attrs = {bytes.fromhex(r[2]): bytes.fromhex(r[3]) for r in attrs}
        if b"security.selinux" not in attrs or set(attrs) - {b"security.selinux", b"security.capability"}:
            raise ValueError("Unexpected source xattrs")
        caps = 0
        if b"security.capability" in attrs:
            blob = attrs[b"security.capability"]
            if len(blob) != 20:
                raise ValueError("Unsupported capability encoding")
            magic, low, inh_low, high, inh_high = struct.unpack("<IIIII", blob)
            if magic != 0x02000001 or inh_low or inh_high:
                raise ValueError("Unsupported capability flags")
            caps = low | high << 32
        fs_path = (mountpoint + path).lstrip('/') if path else ''
        fsconfig.append(f"{fs_path} {uid} {gid} {int(mode) & 0o7777:04o} capabilities={caps:#x}")
        context = labels[path][1] if path in labels else attrs[b"security.selinux"].rstrip(b"\0").decode()
        contexts.append(f"{re.escape(mountpoint + path) if mountpoint + path else '/'} {context}")
    (w / "fs_config").write_text("\n".join(fsconfig) + "\n")
    (w / "contexts").write_text("\n".join(contexts) + "\n")
    rebuilt = w / f"{partition}.img"
    epoch = max(int(row.split(" ")[7]) for row in before if row.startswith("I "))
    space(w, image.stat().st_size + (512 << 20))
    run(tools / "mkfs.erofs", "-zlz4hc,9", "-C65536", "-T", str(epoch), "--preserve-mtime",
        *([f"--mount-point={mountpoint.lstrip('/')}"] if mountpoint else []),
        f"--fs-config-file={w / 'fs_config'}", f"--file-contexts={w / 'contexts'}", rebuilt, source)
    after = inventory(inventory_tool, rebuilt)
    if expected_metadata != after:
        (w / "after.metadata").write_text("\n".join(after) + "\n")
        raise ValueError("EROFS metadata differs; candidate not assembled")
    # Metadata and hashes are in memory; release the reproducible extraction
    # before allocating its comparison copy, keeping the host reserve intact.
    remove_extracted(source)
    extracted = w / "rebuilt"
    run(tools / "fsck.erofs", f"--extract={extracted}", rebuilt)
    expected = dict(original)
    for target, (_, patched) in changes.items():
        expected[target] = ["file", p.hashlib.sha256(patched).hexdigest()]
    if contents(extracted) != expected:
        raise ValueError("Unexpected file/content/link changes")
    run(tools / "avbtool", "add_hashtree_footer", "--image", rebuilt,
        "--partition_name", partition, "--partition_size", image.stat().st_size,
        "--do_not_generate_fec", "--hash_algorithm", "sha256")
    return rebuilt, extracted


def rebuild_one_file(tools, inventory_tool, image, source, before, original,
                     target, original_props, patched, partition, w, mountpoint=""):
    return rebuild_files(tools, inventory_tool, image, source, before, original,
                         {target: (original_props, patched)}, partition, w, mountpoint)


def relabel_metadata(rows, target, old_label, new_label):
    encoded = target.encode().hex()
    key = b"security.selinux".hex()
    old = f"X {encoded} {key} " + old_label.encode().hex()
    new = f"X {encoded} {key} " + new_label.encode().hex()
    if rows.count(old) != 1:
        raise ValueError("Expected one original mount-point label")
    return sorted(new if row == old else row for row in rows)


def patch_contexts(data):
    if b"/system/lib64/arm64" in data:
        raise ValueError("Mount-point override already exists; inspect before replacing")
    return data + b"\n# Alternate native bridge bind-mount target; directory only.\n/system/lib64/arm64 -d u:object_r:system_file:s0\n"


def disk_layout(disk, table, w):
    offset, size = p.extent(next(row for row in table if row["name"] == "super"))
    meta = w / "super-metadata.img"
    p.live.copy_range(disk, meta, offset, 1 << 20)
    with meta.open("r+b") as file: file.truncate(size)
    _, _, layout = p.live.lp.lp_layout(str(meta))
    meta.unlink()
    return offset, layout


def copy_logical(disk, image, offset, part):
    with disk.open("rb") as src, image.open("xb") as out:
        for logical, sectors, physical in part["extents"]:
            src.seek(offset + physical * 512)
            out.seek(logical * 512)
            left = sectors * 512
            while left:
                data = src.read(min(left, 4 << 20))
                if not data: raise ValueError("Truncated logical extent")
                out.write(data); left -= len(data)
    if image.stat().st_size != part["size"]: raise ValueError("Logical size differs")


def hash_logical(disk, offset, part):
    digest = hashlib.sha256()
    cursor = 0
    with disk.open("rb") as file:
        for logical, sectors, physical in part["extents"]:
            if logical * 512 != cursor:
                raise ValueError("Non-contiguous logical extent")
            file.seek(offset + physical * 512)
            left = sectors * 512
            while left:
                data = file.read(min(left, 4 << 20))
                if not data: raise ValueError("Truncated logical readback")
                digest.update(data); left -= len(data); cursor += len(data)
    if cursor != part["size"]: raise ValueError("Logical readback size differs")
    return digest.hexdigest()


def build(a):
    base = p.regular(a.base / "ruby-live.img")
    old = json.loads(p.regular(a.base / "manifest.json").read_text())
    if old["image_sha256"] != BASE_SHA or p.h.audit.sha(base) != BASE_SHA:
        raise ValueError("Requires the reviewed RB01 synthetic pre-installer baseline")
    w = a.out
    w.mkdir(mode=0o700, parents=True, exist_ok=False)
    tools = a.tools
    run = p.h.run
    space(w, 6 << 30)
    (w / "build-inputs.json").write_text(json.dumps({
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "helper_lock": LOCK, "free_before": shutil.disk_usage(w).free,
        "tool_sha256": {name: p.h.audit.sha(p.regular(tools / name))
                         for name in ("mkfs.erofs", "fsck.erofs", "avbtool", "lpdump")},
        "inventory_sha256": p.h.audit.sha(p.regular(a.inventory)),
        "source_image_sha256": BASE_SHA,
    }, indent=2) + "\n")
    table = p.read_gpt(base)
    rows = {r["name"]: r for r in table}
    super_offset, layout = disk_layout(base, table, w)
    system = w / "input-system.img"
    copy_logical(base, system, super_offset, layout["system_a"])
    if p.h.audit.sha(system) != old["logical_sha256"]["system"]:
        raise ValueError("Baseline system hash mismatch")
    before = inventory(a.inventory, system)
    (w / "before.metadata").write_text("\n".join(before) + "\n")
    source = w / "source"
    run(tools / "fsck.erofs", f"--extract={source}", system)
    original = contents(source)
    original_props = (source / TARGET.lstrip("/")).read_bytes()
    patched = patch(original_props)
    overlay_report = None
    bridge_root = source / "system"
    required = ("lib64/libndk_translation.so", "etc/init/berberis_arm_or_arm64.rc",
                "bin/ndk_translation_program_runner_binfmt_misc_arm64",
                "lib64/berberis/arm64/libc.so", "lib64/berberis/arm64/ld-android.so")
    for name in required:
        if not (bridge_root / name).is_file(): raise ValueError(f"Missing retained bridge input: {name}")
    bridge_inputs = {name: p.h.audit.sha(bridge_root / name) for name in required}
    rc = (bridge_root / "etc/init/berberis_arm_or_arm64.rc").read_text()
    if "mount none /system/lib64/berberis/arm64 /system/lib64/arm64 bind" not in rc:
        raise ValueError("Missing existing secondary-layout guest mount")
    if a.digitalis_bundle:
        spec = importlib.util.spec_from_file_location("digitalis", Path(__file__).with_name("digitalis-overlay.py"))
        overlay = importlib.util.module_from_spec(spec); spec.loader.exec_module(overlay)
        expected_metadata, expected_contents, overlay_report = overlay.apply(source, before, original, a.digitalis_bundle, contents)
        (w / "digitalis-overlay.json").write_text(json.dumps(overlay_report, indent=2) + "\n")
        patched = (source / TARGET.lstrip("/")).read_bytes()
        changes = dict.fromkeys(overlay_report["changed_files"])
        labels = {}
        rebuilt, extracted = rebuild_files(tools, a.inventory, system, source, expected_metadata,
                                            expected_contents, {}, "system", w)
        bridge_inputs = {"bundle_manifest_sha256": overlay.BUNDLE_MANIFEST_SHA,
                        "libberberis_arm64.so": p.h.audit.sha(a.digitalis_bundle / "system/lib64/libberberis_arm64.so")}
    else:
        target = source / TARGET.lstrip("/")
        target.chmod(target.stat().st_mode | 0o200)
        target.write_bytes(patched)
        context_file = source / CONTEXTS.lstrip("/")
        old_contexts = context_file.read_bytes()
        new_contexts = patch_contexts(old_contexts)
        context_file.chmod(context_file.stat().st_mode | 0o200)
        context_file.write_bytes(new_contexts)
        changes = {TARGET: (original_props, patched), CONTEXTS: (old_contexts, new_contexts)}
        labels = {MOUNTPOINT: ("u:object_r:system_lib_file:s0", "u:object_r:system_file:s0")}
        rebuilt, extracted = rebuild_files(tools, a.inventory, system, source, before, original,
                                           changes, "system", w, labels=labels)
    # All other logical inputs are unchanged camera25 artifacts. Verify them
    # against the RB01 manifest before assembling; never accept a floating tree.
    images = {n: a.logical / f"{n}_a.img" for n in old["logical_sha256"] if n != "system"}
    for name, src in images.items():
        p.regular(src)
        if p.h.audit.sha(src) != old["logical_sha256"][name]:
            raise ValueError(f"Logical input changed: {name}")
    cleanup = [source, extracted]
    (w / "cleanup-extracted.json").write_text(json.dumps([str(x) for x in cleanup], indent=2))
    for scratch in cleanup:
        if scratch.exists(): remove_extracted(scratch)
    space(w, 2 << 30)
    images["system"] = rebuilt
    images = {name: images[name] for name in old["logical_sha256"]}
    vbmeta = w / "vbmeta.img"
    cmd = [tools / "avbtool", "make_vbmeta_image", "--algorithm", "SHA256_RSA4096",
           "--key", a.key, "--padding_size", "4096", "--output", vbmeta]
    for src in images.values():
        cmd += ["--include_descriptors_from_image", src]
    run(*cmd)
    # Verify the assembled AVB chain against the supplied local signing key.
    chain = w / "avb"; chain.mkdir()
    shutil.copyfile(vbmeta, chain / "vbmeta.img")
    for n, src in images.items():
        (chain / f"{n}.img").symlink_to(src.resolve())
    run(tools / "avbtool", "verify_image", "--image", chain / "vbmeta.img", "--key", a.key)
    digest = subprocess.check_output([str(tools / "avbtool"), "calculate_vbmeta_digest",
                                     "--image", str(vbmeta)], text=True).strip()
    table = p.read_gpt(base)
    rows = {r["name"]: r for r in table}
    esp = w / "esp.img"
    p.live.copy_range(base, esp, *p.extent(table[0]))
    tree = w / "esp-before"; tree.mkdir()
    run("mcopy", "-s", "-i", esp, "::*", tree)
    updated = copy.deepcopy(old)
    updated["logical_sha256"]["system"] = p.h.audit.sha(rebuilt)
    updated["bridge_correction"] = dict(
        previous="libhoudini.so", selected="libberberis_arm64.so" if overlay_report else "libndk_translation.so",
        mountpoint_label=labels.get(MOUNTPOINT, (None, "u:object_r:system_lib_file:s0"))[1],
        file_contexts_override=None if overlay_report else CONTEXTS,
        retained_secondary_layout=not bool(overlay_report), changed_file=TARGET,
        properties_before_sha256=p.hashlib.sha256(original_props).hexdigest(),
        properties_after_sha256=p.hashlib.sha256(patched).hexdigest(),
        existing_bridge_inputs=bridge_inputs, hardware_validated=False,
        private_retained_payload=True)
    if overlay_report: updated["bridge_correction"]["digitalis_overlay"] = overlay_report
    vbinfo = subprocess.check_output([str(tools / "avbtool"), "info_image", "--image", str(vbmeta)], text=True)
    vbsize = sum(map(int, re.findall(r"(?:Header|Authentication|Auxiliary) Block:\s+(\d+) bytes", vbinfo)))
    if not vbsize: raise ValueError("Missing actual AVB size")
    changed = {"ruby/RESEARCH.json"}
    for mode, params in updated["entries"].items():
        name = f"ruby/initrd-{mode}.img"
        body, actual = p.split_initrd((tree / name).read_bytes())
        if actual != old["entries"][mode]:
            raise ValueError("Boot parameters differ from manifest")
        params["androidboot.vbmeta.digest"] = digest
        params["androidboot.vbmeta.size"] = str(vbsize)
        local = w / f"initrd-{mode}.img"
        local.write_bytes(body + p.h.gpt.bootconfig_trailer(p.h.bc.render(params).decode(), len(body)))
        run("mcopy", "-o", "-i", esp, local, f"::/{name}")
        changed.add(name)
    embedded = w / "RESEARCH.json"
    embedded.write_text(json.dumps({k:v for k,v in updated.items()
        if k not in ("image_sha256","payload_readback")}, indent=2) + "\n")
    run("mcopy", "-o", "-i", esp, embedded, "::/ruby/RESEARCH.json")
    after_tree = w / "esp-after"; after_tree.mkdir()
    run("mcopy", "-s", "-i", esp, "::*", after_tree)
    if {k:v for k,v in p.tree_hashes(tree).items() if k not in changed} != {
            k:v for k,v in p.tree_hashes(after_tree).items() if k not in changed}:
        raise ValueError("Unrelated boot files changed")
    run("fsck.fat", "-n", esp)
    output = w / "ruby-live.img"
    run("cp", "--reflink=always", base, output)
    with output.open("r+b") as f:
        with rebuilt.open("rb") as inp:
            for logical, sectors, physical in layout["system_a"]["extents"]:
                f.seek(super_offset + physical * 512)
                inp.seek(logical * 512)
                left = sectors * 512
                while left:
                    data = inp.read(min(left, 4 << 20))
                    if not data: raise ValueError("Short system image")
                    f.write(data); left -= len(data)
            f.flush(); os.fsync(f.fileno())
        updated["payload_readback"]["super"] = p.digest_range(output, *p.extent(rows["super"]))
        for name, src in (("vbmeta_a",vbmeta),("EFI",esp)):
            start, size = p.extent(rows[name])
            if src.stat().st_size > size:
                raise ValueError("Payload exceeds partition")
            f.seek(start)
            with src.open("rb") as inp: shutil.copyfileobj(inp, f, 4 << 20)
            f.write(bytes(size - src.stat().st_size))
            f.flush(); os.fsync(f.fileno())
            updated["payload_readback"][name] = p.digest_range(output,start,size)
    for start,size in p.protected_ranges(table,base.stat().st_size):
        if p.digest_range(output,start,size) != p.digest_range(base,start,size):
            raise ValueError("Protected partition/GPT changed")
    for name, expected in updated["logical_sha256"].items():
        if hash_logical(output, super_offset, layout[name + "_a"]) != expected:
            raise ValueError(f"Logical payload readback failed: {name}")
    updated["image_sha256"] = p.h.audit.sha(output)
    if p.h.audit.sha(base) != BASE_SHA:
        raise ValueError("Source changed")
    (w / "manifest.json").write_text(json.dumps(updated, indent=2) + "\n")
    (w / "result.json").write_text(json.dumps(dict(
        schema="openbook-ruby-bridge-candidate/1", complete=True,
        source_sha256=BASE_SHA,image_sha256=updated["image_sha256"],
        metadata_rows=len(before),metadata_verified_against_exact_change_allowlist=True,
        file_and_symlink_count=len(original),changed_files=sorted(changes),changed_labels=labels,
        bridge_correction=updated["bridge_correction"],
        protected_ranges_identical=True,source_unchanged=True,logical_payloads_verified=True,
        physical_device_written=False), indent=2) + "\n")
    # Only reproducible scratch from this invocation. Keep the candidate,
    # corrected system/AVB, provenance and logs for reproduction and review.
    scratch_files = [system, esp]
    scratch_dirs = [tree, after_tree]
    (w / "cleanup-final.json").write_text(json.dumps([str(x) for x in scratch_files + scratch_dirs], indent=2))
    for scratch in scratch_files: scratch.unlink()
    for scratch in scratch_dirs: shutil.rmtree(scratch)
    print("Experimental candidate complete; no physical device was written.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base","logical","tools","inventory","key","out"):
        parser.add_argument("--"+name,type=Path,required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--digitalis-bundle", type=Path, help="Pinned source-built AOSP17 alternative; experimental Ruby qualification")
    mode.add_argument("--reproduce-rejected-ndk", action="store_true",
                      help="Reproduce the rejected shipped-translator experiment; never release")
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        parser.error("Use inst-docker.sh; regular images only")
    os.umask(0o077)
    build(args)
