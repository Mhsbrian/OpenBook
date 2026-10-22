#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Add one reviewed vendor kernel module to a Ruby image's vendor_dlkm. Regular images only.

The base is a reviewed live image directory (ruby-live.img + manifest.json) and
its unpacked logical images. vendor_dlkm is rebuilt from extracted files with
the original ownership, modes, timestamps and SELinux labels; the module is
added as root:root 0644 vendor_file, appended to modules.load and given a
dependency-free modules.dep entry. Every other inode, xattr and file is
compared. All other logical images keep their bytes. AVB metadata is signed
with the supplied local key and the bootconfig digest is updated. Never flash
the whole output over configured data; use the preserving update tools.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

HERE = Path(__file__).resolve().parent


def load(name, file):
    s = importlib.util.spec_from_file_location(name, HERE / file)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


p = load("preserve", "preserve-update.py")
MODDIR = "/lib/modules"


def inventory(tool, image):
    return sorted(subprocess.check_output([str(tool), str(image)], text=True).splitlines())


def contents(root):
    result = {}
    for path in root.rglob("*"):
        name = "/" + str(path.relative_to(root))
        if path.is_symlink():
            result[name] = ["symlink", os.readlink(path)]
        elif path.is_file():
            result[name] = ["file", p.h.audit.sha(path)]
    return result


def module_name(ko):
    name = ko.name
    if not re.fullmatch(r"[a-z0-9_]{3,40}\.ko", name):
        raise ValueError("Unexpected module file name")
    return name


def expected_metadata(before, sizes, new_rows):
    rows = []
    for line in before:
        parts = line.split(" ")
        if parts[0] == "I":
            path = bytes.fromhex(parts[1]).decode()
            if path in sizes:
                parts[6] = str(sizes[path])
                line = " ".join(parts)
        rows.append(line)
    return sorted(rows + new_rows)


def check_module(ko, vermagic):
    data = ko.read_bytes()
    if data[:4] != b"\x7fELF":
        raise ValueError("Module is not an ELF object")
    if f"vermagic={vermagic}".encode() not in data:
        raise ValueError("Module vermagic does not match the image kernel modules")
    return data


def build(a):
    base = p.regular(a.base / "ruby-live.img")
    old = json.loads(p.regular(a.base / "manifest.json").read_text())
    if p.h.audit.sha(base) != old["image_sha256"]:
        raise ValueError("Base image hash differs from its manifest")
    images = {}
    for name, digest in old["logical_sha256"].items():
        image = p.regular(a.logical / f"{name}_a.img")
        if p.h.audit.sha(image) != digest:
            raise ValueError(f"Logical image differs from manifest: {name}")
        images[name] = image
    w = a.out
    w.mkdir(mode=0o700, parents=True, exist_ok=False)
    tools, run = a.tools, p.h.run
    source_image = images["vendor_dlkm"]
    before = inventory(a.inventory, source_image)
    (w / "before.metadata").write_text("\n".join(before) + "\n")
    source = w / "source"
    run(tools / "fsck.erofs", f"--extract={source}", source_image)
    original = contents(source)
    moddir = source / MODDIR.lstrip("/")
    ko_name = module_name(a.module)
    reference = sorted(x for x in moddir.glob("*.ko"))
    if not reference:
        raise ValueError("vendor_dlkm has no modules")
    vermagic = re.search(rb"vermagic=([^\0]+)", reference[0].read_bytes()).group(1).decode()
    ko = check_module(a.module, vermagic)
    target = f"{MODDIR}/{ko_name}"
    if target in original:
        raise ValueError("Module already present")
    load_list = (moddir / "modules.load").read_text()
    dep = (moddir / "modules.dep").read_text()
    if ko_name in load_list.split() or f"/{ko_name}:" in dep:
        raise ValueError("Module already listed")
    dep_prefix = dep.splitlines()[0].split(":")[0].rsplit("/", 1)[0]
    if not dep_prefix.startswith("/") or dep_prefix.endswith("/"):
        raise ValueError("Unrecognized modules.dep layout")
    (moddir / ko_name).write_bytes(ko)
    new_load = load_list + ("" if load_list.endswith("\n") else "\n") + ko_name + "\n"
    new_dep = dep + ("" if dep.endswith("\n") else "\n") + f"{dep_prefix}/{ko_name}:\n"
    (moddir / "modules.load").write_text(new_load)
    (moddir / "modules.dep").write_text(new_dep)
    # Copy ownership, mode, time and label from an existing module inode.
    ref_hex = f"{MODDIR}/{reference[0].name}".encode().hex()
    ref_row = next(r.split(" ") for r in before if r.startswith(f"I {ref_hex} "))
    ref_label = next(r.split(" ")[3] for r in before
                     if r.startswith(f"X {ref_hex} {b'security.selinux'.hex()} "))
    new_hex = target.encode().hex()
    new_rows = [" ".join(["I", new_hex, ref_row[2], ref_row[3], ref_row[4], "1", str(len(ko)), ref_row[7], ref_row[8]]),
                " ".join(["X", new_hex, b"security.selinux".hex(), ref_label])]
    expected = expected_metadata(before, {f"{MODDIR}/modules.load": len(new_load.encode()),
                                          f"{MODDIR}/modules.dep": len(new_dep.encode())}, new_rows)
    fsconfig, ctx = [], []
    for row in (r.split(" ") for r in expected if r.startswith("I ")):
        _, encoded, mode, uid, gid, nlink, size, seconds, nanos = row
        path = bytes.fromhex(encoded).decode()
        if any(c.isspace() for c in path):
            raise ValueError("Unsupported whitespace in path")
        if int(nlink) != 1 and int(mode) & 0o170000 != 0o040000:
            raise ValueError("Hardlinks are not supported")
        local = source / path.lstrip("/")
        if not local.is_symlink():
            os.chmod(local, int(mode) & 0o7777)
        os.utime(local, ns=(int(seconds) * 10**9 + int(nanos),) * 2, follow_symlinks=False)
        attrs = {bytes.fromhex(r.split(" ")[2]): bytes.fromhex(r.split(" ")[3])
                 for r in expected if r.startswith(f"X {encoded} ")}
        if set(attrs) != {b"security.selinux"}:
            raise ValueError("Unexpected xattrs in vendor_dlkm")
        fsconfig.append(f"{path.lstrip('/')} {uid} {gid} {int(mode) & 0o7777:04o} capabilities=0x0")
        ctx.append(f"{re.escape(path) if path else '/'} {attrs[b'security.selinux'].rstrip(bytes(1)).decode()}")
    (w / "fs_config").write_text("\n".join(fsconfig) + "\n")
    (w / "contexts").write_text("\n".join(ctx) + "\n")
    rebuilt = w / "vendor_dlkm.img"
    run(tools / "mkfs.erofs", "--preserve-mtime", f"--fs-config-file={w / 'fs_config'}",
        f"--file-contexts={w / 'contexts'}", rebuilt, source)
    after = inventory(a.inventory, rebuilt)
    if after != expected:
        (w / "after.metadata").write_text("\n".join(after) + "\n")
        raise ValueError("vendor_dlkm metadata differs from the reviewed change")
    check = w / "rebuilt"
    run(tools / "fsck.erofs", f"--extract={check}", rebuilt)
    want = dict(original)
    want[target] = ["file", p.hashlib.sha256(ko).hexdigest()]
    want[f"{MODDIR}/modules.load"] = ["file", p.hashlib.sha256(new_load.encode()).hexdigest()]
    want[f"{MODDIR}/modules.dep"] = ["file", p.hashlib.sha256(new_dep.encode()).hexdigest()]
    if contents(check) != want:
        raise ValueError("Unexpected file/content/link changes")
    size = -(-(rebuilt.stat().st_size + (1 << 20)) // 4096) * 4096
    run(tools / "avbtool", "add_hashtree_footer", "--image", rebuilt, "--partition_name", "vendor_dlkm",
        "--partition_size", size, "--do_not_generate_fec", "--hash_algorithm", "sha256")
    images["vendor_dlkm"] = rebuilt
    vbmeta = w / "vbmeta.img"
    cmd = [tools / "avbtool", "make_vbmeta_image", "--algorithm", "SHA256_RSA4096",
           "--key", a.key, "--padding_size", "4096", "--output", vbmeta]
    for src in images.values():
        cmd += ["--include_descriptors_from_image", src]
    run(*cmd)
    chain = w / "avb"
    chain.mkdir()
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
        cmd += ["--partition", f"{n}_a:readonly:{p.h.gpt.round_up(src.stat().st_size, 4096)}:ruby_probe_a",
                "--image", f"{n}_a={src}"]
    run(*cmd)
    esp = w / "esp.img"
    p.live.copy_range(base, esp, *p.extent(table[0]))
    tree = w / "esp-before"
    tree.mkdir()
    run("mcopy", "-s", "-i", esp, "::*", tree)
    updated = copy.deepcopy(old)
    updated["logical_sha256"]["vendor_dlkm"] = p.h.audit.sha(rebuilt)
    updated["vendor_module"] = dict(file=ko_name, sha256=p.hashlib.sha256(ko).hexdigest(), vermagic=vermagic,
                                    loaded_by="vendor.openbook.dlkm (modules.load)", hardware_validated=False)
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
    embedded.write_text(json.dumps({k: v for k, v in updated.items()
                                    if k not in ("image_sha256", "payload_readback")}, indent=2) + "\n")
    run("mcopy", "-o", "-i", esp, embedded, "::/ruby/RESEARCH.json")
    after_tree = w / "esp-after"
    after_tree.mkdir()
    run("mcopy", "-s", "-i", esp, "::*", after_tree)
    if ({k: v for k, v in p.tree_hashes(tree).items() if k not in changed} !=
            {k: v for k, v in p.tree_hashes(after_tree).items() if k not in changed}):
        raise ValueError("Unrelated boot files changed")
    for mode, params in updated["entries"].items():
        if p.split_initrd((after_tree / f"ruby/initrd-{mode}.img").read_bytes())[1] != params:
            raise ValueError("EFI bootconfig readback mismatch")
    run("fsck.fat", "-n", esp)
    output = w / "ruby-live.img"
    run("cp", "--reflink=auto", base, output)
    with output.open("r+b") as f:
        for name, src in (("super", super_image), ("vbmeta_a", vbmeta), ("EFI", esp)):
            start, length = p.extent(rows[name])
            if src.stat().st_size > length:
                raise ValueError("Payload exceeds partition")
            f.seek(start)
            with src.open("rb") as inp:
                shutil.copyfileobj(inp, f, 4 << 20)
            f.write(bytes(length - src.stat().st_size))
            f.flush()
            os.fsync(f.fileno())
            updated["payload_readback"][name] = p.digest_range(output, start, length)
    for start, length in p.protected_ranges(table, base.stat().st_size):
        if p.digest_range(output, start, length) != p.digest_range(base, start, length):
            raise ValueError("Protected partition/GPT changed")
    updated["image_sha256"] = p.h.audit.sha(output)
    p.verify_vbmeta_bootconfig(output, table, updated["entries"])
    if p.h.audit.sha(base) != old["image_sha256"]:
        raise ValueError("Source changed")
    (w / "manifest.json").write_text(json.dumps(updated, indent=2) + "\n")
    result = dict(schema="openbook-ruby-module-candidate/1", complete=True, source_sha256=old["image_sha256"],
                  image_sha256=updated["image_sha256"], changed_logical=["vendor_dlkm"],
                  added_file=target, edited_files=[f"{MODDIR}/modules.load", f"{MODDIR}/modules.dep"],
                  metadata_rows_before=len(before), metadata_rows_after=len(after),
                  other_inodes_identical=True, protected_ranges_identical=True, source_unchanged=True,
                  physical_device_written=False, hardware_validated=False)
    (w / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("image_sha256", "added_file")}))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "logical", "module", "tools", "inventory", "key", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if not Path("/.dockerenv").exists():
        parser.error("Use inst-docker.sh; regular images only")
    os.umask(0o077)
    build(args)
