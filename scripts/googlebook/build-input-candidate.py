#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a private, exact-camera25 input correction. Regular images only.

Requires the read-only erofs-inventory helper built against the AOSP host tools.
Rebuilds EROFS with original ownership/labels, then compares EVERY inode/xattr
and file. Unknown extended attributes or hardlinks fail closed.
No userdata from an installed laptop is an input. Never flash this whole image
over a configured device: use a fresh offline snapshot and installed-update.py.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import struct

HERE = Path(__file__).resolve().parent


def load(name, file):
    s = importlib.util.spec_from_file_location(name, HERE / file)
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


p = load("preserve", "preserve-update.py")
patcher = load("inputpatch", "input-timestamp-patch.py")
CAMERA25 = "df793f2eed3a5c901659014c2ae368d8e5eeb3d504b514d46fc8c0c1959a7af4"
TARGET = "/system/lib64/libinputflinger.so"
ADDED_TIMESTAMP = 1230768000
ADDED_CONTEXT = "u:object_r:system_file:s0"


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


def replacement_metadata(before, replacements):
    """Only regular-file size may differ; preserve every other inode/xattr."""
    expected, found = [], set()
    for line in before:
        row = line.split(" ")
        if row[0] == "I":
            name = bytes.fromhex(row[1]).decode()
            if name in replacements:
                if int(row[2]) & 0o170000 != 0o100000 or int(row[5]) != 1:
                    raise ValueError("Replacement requires an existing regular file without hardlinks")
                row[6] = str(len(replacements[name]))
                found.add(name)
                line = " ".join(row)
        expected.append(line)
    if found != set(replacements):
        raise ValueError("Replacement path is absent from baseline metadata")
    return sorted(expected)


def addition_metadata(rows, additions):
    """New root-owned system_file inodes: bytes for 0644 files, None for 0755 directories."""
    rows = list(rows)
    index = {bytes.fromhex(r.split(" ")[1]).decode(): i for i, r in enumerate(rows) if r.startswith("I ")}
    for name in sorted(additions):
        parent = name.rsplit("/", 1)[0]
        if name in index or parent not in index or any(c.isspace() for c in name):
            raise ValueError("Addition must be a new path in an existing directory")
        row = rows[index[parent]].split(" ")
        if int(row[2]) & 0o170000 != 0o040000:
            raise ValueError("Addition parent is not a directory")
        if additions[name] is None:
            mode, nlink, size = 0o040755, 2, 0
            row[5] = str(int(row[5]) + 1)
            rows[index[parent]] = " ".join(row)
        else:
            mode, nlink, size = 0o100644, 1, len(additions[name])
        encoded = name.encode().hex()
        index[name] = len(rows)
        rows.append(f"I {encoded} {mode} 0 0 {nlink} {size} {ADDED_TIMESTAMP} 0")
        rows.append(f"X {encoded} {b'security.selinux'.hex()} {ADDED_CONTEXT.encode().hex()}")
    return sorted(rows)


def verify_boot_files(tree, work, entries):
    for mode, params in entries.items():
        actual = (tree / f"ruby/initrd-{mode}.img").read_bytes()
        if actual != (work / f"initrd-{mode}.img").read_bytes() or p.split_initrd(actual)[1] != params:
            raise ValueError("EFI bootconfig readback mismatch")
    if (tree / "ruby/RESEARCH.json").read_bytes() != (work / "RESEARCH.json").read_bytes():
        raise ValueError("EFI manifest readback mismatch")


def build_system(a, transform, result_schema):
    """Shared exact-camera25 reassembler. Callers supply an explicit transform.

    The transform returns (replacements, annotations) or, for a disposable
    experiment only, (replacements, annotations, additions).
    """
    base = p.regular(a.base / "ruby-live.img")
    old = json.loads(p.regular(a.base / "manifest.json").read_text())
    if old["image_sha256"] != CAMERA25 or p.h.audit.sha(base) != CAMERA25:
        raise ValueError("Requires the reviewed fresh camera25 baseline")
    w = a.out
    w.mkdir(mode=0o700, parents=True, exist_ok=False)
    tools = a.tools
    run = p.h.run
    system = p.regular(a.base / "logical/system_a.img")
    if p.h.audit.sha(system) != old["logical_sha256"]["system"]:
        raise ValueError("Baseline system hash mismatch")
    before = inventory(a.inventory, system)
    (w / "before.metadata").write_text("\n".join(before) + "\n")
    source = w / "source"
    run(tools / "fsck.erofs", f"--extract={source}", system)
    original = contents(source)
    replacements, annotations, *extra = transform(source)
    additions = extra[0] if extra else {}
    if not replacements or set(annotations) & set(old):
        raise ValueError("Transform must replace files without overriding baseline fields")
    if additions and not any(k.startswith("experimental_") and v.get("deployment_eligible") is False
                             for k, v in annotations.items()):
        raise ValueError("Added files are limited to disposable experiments")
    expected_metadata = addition_metadata(replacement_metadata(before, replacements), additions)
    for name, data in replacements.items():
        if name not in original or original[name][0] != "file":
            raise ValueError("Replacement is not an existing regular file")
        p.regular(source / name.lstrip("/")).write_bytes(data)
    for name in sorted(additions):
        local = source / name.lstrip("/")
        if additions[name] is None:
            local.mkdir()
        else:
            local.write_bytes(additions[name])
    fsconfig, contexts = [], []
    for row in (r.split(" ") for r in expected_metadata if r.startswith("I ")):
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
        attrs = [r.split(" ") for r in expected_metadata if r.startswith(f"X {encoded} ")]
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
        fsconfig.append(f"{path.lstrip('/')} {uid} {gid} {int(mode) & 0o7777:04o} capabilities={caps:#x}")
        context = attrs[b"security.selinux"].rstrip(b"\0").decode()
        contexts.append(f"{re.escape(path) if path else '/'} {context}")
    (w / "fs_config").write_text("\n".join(fsconfig) + "\n")
    (w / "contexts").write_text("\n".join(contexts) + "\n")
    rebuilt = w / "system.img"
    run(tools / "mkfs.erofs", "-zlz4hc,9", "-C65536", "-T", "1230768000", "--preserve-mtime",
        f"--fs-config-file={w / 'fs_config'}", f"--file-contexts={w / 'contexts'}", rebuilt, source)
    after = inventory(a.inventory, rebuilt)
    if expected_metadata != after:
        (w / "after.metadata").write_text("\n".join(after) + "\n")
        raise ValueError("EROFS metadata differs; candidate not assembled")
    extracted = w / "rebuilt"
    run(tools / "fsck.erofs", f"--extract={extracted}", rebuilt)
    expected = dict(original)
    expected.update({name: ["file", p.hashlib.sha256(data).hexdigest()]
                     for name, data in (*replacements.items(), *additions.items()) if data is not None})
    if contents(extracted) != expected:
        raise ValueError("Unexpected file/content/link changes")
    run(tools / "avbtool", "add_hashtree_footer", "--image", rebuilt,
        "--partition_name", "system", "--partition_size", system.stat().st_size,
        "--do_not_generate_fec", "--hash_algorithm", "sha256")
    images = {n: a.base / f"logical/{n}_a.img" for n in old["logical_sha256"]}
    images["system"] = rebuilt
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
    vbmeta_size = 256 + sum(struct.unpack_from(">QQ", vbmeta.read_bytes(), 12))
    table = p.read_gpt(base)
    rows = {r["name"]: r for r in table}
    ssize = p.extent(rows["super"])[1]
    super_image = w / "super.img"
    cmd = [tools / "lpmake", "--metadata-size", "65536", "--metadata-slots", "2",
           "--super-name", "super", "--device", f"super:{ssize}",
           "--group", f"ruby_probe_a:{ssize - 4 * p.h.MiB}", "--output", super_image]
    for n, src in images.items():
        cmd += ["--partition", f"{n}_a:readonly:{p.h.gpt.round_up(src.stat().st_size,4096)}:ruby_probe_a",
                "--image", f"{n}_a={src}"]
    run(*cmd)
    esp = w / "esp.img"
    p.live.copy_range(base, esp, *p.extent(table[0]))
    tree = w / "esp-before"; tree.mkdir()
    run("mcopy", "-s", "-i", esp, "::*", tree)
    updated = copy.deepcopy(old)
    updated["logical_sha256"]["system"] = p.h.audit.sha(rebuilt)
    updated.update(annotations)
    changed = {"ruby/RESEARCH.json"}
    for mode, params in updated["entries"].items():
        name = f"ruby/initrd-{mode}.img"
        body, actual = p.split_initrd((tree / name).read_bytes())
        if actual != old["entries"][mode]:
            raise ValueError("Boot parameters differ from manifest")
        params["androidboot.vbmeta.digest"] = digest
        params["androidboot.vbmeta.size"] = str(vbmeta_size)
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
    verify_boot_files(after_tree, w, updated["entries"])
    run("fsck.fat", "-n", esp)
    output = w / "ruby-live.img"
    run("cp", "--reflink=auto", base, output)
    with output.open("r+b") as f:
        for name, src in (("super",super_image),("vbmeta_a",vbmeta),("EFI",esp)):
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
    updated["image_sha256"] = p.h.audit.sha(output)
    p.verify_vbmeta_bootconfig(output, table, updated["entries"])
    if p.h.audit.sha(base) != CAMERA25:
        raise ValueError("Source changed")
    (w / "manifest.json").write_text(json.dumps(updated, indent=2) + "\n")
    (w / "result.json").write_text(json.dumps(dict(
        schema=result_schema, complete=True,
        source_sha256=CAMERA25,image_sha256=updated["image_sha256"],
        metadata_rows=len(before),all_inode_xattrs_identical=before==after,
        only_metadata_change=("replacement file sizes" + (" and added paths" if additions else ""))
                             if before!=after else None,
        file_and_symlink_count=len(original),changed_files=sorted(replacements),
        only_changed_file=next(iter(replacements)) if len(replacements)==1 and not additions else None,
        **({"added_paths": sorted(additions)} if additions else {}),
        **annotations,
        protected_ranges_identical=True,source_unchanged=True,
        physical_device_written=False), indent=2) + "\n")
    print("Candidate complete; no configured data or physical device was written.")


def build(a):
    def transform(source):
        patched, offset = patcher.patch((source / TARGET.lstrip("/")).read_bytes())
        return {TARGET: patched}, {"input_correction": dict(
            source_sha256=patcher.SOURCE_SHA256,
            output_sha256=p.hashlib.sha256(patched).hexdigest(), offset=offset,
            bytes=8, hardware_validated=False)}
    build_system(a, transform, "openbook-ruby-input-candidate/1")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base","tools","inventory","key","out"):
        parser.add_argument("--"+name,type=Path,required=True)
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        parser.error("Use inst-docker.sh; regular images only")
    os.umask(0o077)
    build(args)
