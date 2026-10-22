#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Instrument a synthetic bridge experiment for a bounded VM run, never release.

Retains enforcing policy. Replaces only the existing vendor serial diagnostic
script and rebuilds its verified filesystem. Embeds the open-source JNI probes
in that script. Does not touch a physical device or configured owner data.
Without --logical, unchanged logical images are copied out of the candidate.
"""
import argparse
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

spec = importlib.util.spec_from_file_location("candidate", Path(__file__).with_name("build-bridge-candidate.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
p = c.p


def build(a):
    src = a.candidate / "ruby-live.img"
    old = json.loads((a.candidate / "manifest.json").read_text())
    if p.h.audit.sha(p.regular(src)) != old["image_sha256"]:
        raise ValueError("Candidate hash differs")
    if not old.get("bridge_correction") or old.get("installable"):
        raise ValueError("Requires a synthetic, non-installable bridge experiment")
    w = a.out
    w.mkdir(mode=0o700, parents=True, exist_ok=False)
    c.space(w, 6 << 30)
    free_before = shutil.disk_usage(w).free
    copied = []
    if a.logical:
        logical = {n: a.logical / f"{n}_a.img" for n in old["logical_sha256"]}
    else:
        candidate_layout = c.disk_layout(src, p.read_gpt(src), w)
        logical = {}
        for n in old["logical_sha256"]:
            if n == "system": continue
            logical[n] = w / f"input-{n}.img"
            offset, layout = candidate_layout
            c.copy_logical(src, logical[n], offset, layout[n + "_a"])
            copied.append(logical[n])
    vendor = logical["vendor"]
    if p.h.audit.sha(p.regular(vendor)) != old["logical_sha256"]["vendor"]:
        raise ValueError("Vendor differs")
    before = c.inventory(a.inventory, vendor)
    root = w / "vendor-root"
    p.h.run(a.tools / "fsck.erofs", f"--extract={root}", vendor)
    contents = c.contents(root)
    target = "/etc/ruby-probe.sh"
    file = root / target.lstrip("/")
    original = file.read_bytes()
    script = Path(__file__).with_name("bridge-vm-guest.sh").read_text()
    setup = []
    apk_hashes = {}
    for abi in ("x86_64", "arm64"):
        apk = a.probes / f"anybook-probe-{abi}.apk"
        apk_hashes[abi] = p.h.audit.sha(p.regular(apk))
        setup.append(f"base64 -d >{abi}.apk <<'APK_{abi}'\n" +
                     base64.encodebytes(apk.read_bytes()).decode() + f"APK_{abi}\n")
    script = script.replace("# APK_SETUP: the host embeds only the repository's open-source test APKs here.", "\n".join(setup)).encode()
    file.chmod(file.stat().st_mode | 0o200)
    file.write_bytes(script)
    rebuilt, extracted = c.rebuild_one_file(a.tools, a.inventory, vendor, root, before, contents,
                                            target, original, script, "vendor", w, "/vendor")
    c.remove_extracted(extracted)
    images = {n: logical.get(n) for n in old["logical_sha256"]}
    images.update(system=a.candidate / "system.img", vendor=rebuilt)
    for n, file in images.items():
        if n != "vendor" and p.h.audit.sha(p.regular(file)) != old["logical_sha256"][n]:
            raise ValueError(f"Logical input differs: {n}")
    vbmeta = w / "vbmeta.img"
    cmd = [a.tools / "avbtool", "make_vbmeta_image", "--algorithm", "SHA256_RSA4096", "--key", a.key,
           "--padding_size", "4096", "--output", vbmeta]
    for file in images.values(): cmd += ["--include_descriptors_from_image", file]
    p.h.run(*cmd)
    chain = w / "avb"
    chain.mkdir()
    shutil.copyfile(vbmeta, chain / "vbmeta.img")
    for name, file in images.items(): (chain / f"{name}.img").symlink_to(file.resolve())
    p.h.run(a.tools / "avbtool", "verify_image", "--image", chain / "vbmeta.img", "--key", a.key)
    digest = subprocess.check_output([str(a.tools / "avbtool"), "calculate_vbmeta_digest", "--image", str(vbmeta)], text=True).strip()
    info = subprocess.check_output([str(a.tools / "avbtool"), "info_image", "--image", str(vbmeta)], text=True)
    vbsize = sum(map(int, re.findall(r"(?:Header|Authentication|Auxiliary) Block:\s+(\d+) bytes", info)))
    table = p.read_gpt(src)
    rows = {r["name"]: r for r in table}
    offset, size = p.extent(rows["super"])
    # lpdump needs metadata, not payloads. Keep a sparse metadata-only scratch.
    meta = w / "super-metadata.img"
    p.live.copy_range(src, meta, offset, 1 << 20)
    with meta.open("r+b") as f: f.truncate(size)
    _, _, layout = p.live.lp.lp_layout(str(meta))
    extents = layout["vendor_a"]["extents"]
    if layout["vendor_a"]["size"] != rebuilt.stat().st_size:
        raise ValueError("Vendor size changed")
    disk = w / "ruby-live.img"
    p.h.run("cp", "--reflink=always", src, disk)
    with disk.open("r+b") as out, rebuilt.open("rb") as inp:
        for logical, sectors, physical in extents:
            out.seek(offset + physical * 512)
            inp.seek(logical * 512)
            data = inp.read(sectors * 512)
            if len(data) != sectors * 512: raise ValueError("Short vendor extent")
            out.write(data)
        start, length = p.extent(rows["vbmeta_a"])
        out.seek(start)
        out.write(vbmeta.read_bytes())
        out.write(bytes(length - vbmeta.stat().st_size))
        out.flush(); os.fsync(out.fileno())
    esp = f"{disk}@@{p.extent(rows['EFI'])[0]}"
    updated = copy.deepcopy(old)
    for mode, params in updated["entries"].items():
        local = w / f"initrd-{mode}.img"
        p.h.run("mcopy", "-i", esp, f"::/ruby/initrd-{mode}.img", local)
        body, actual = p.split_initrd(local.read_bytes())
        if actual != old["entries"][mode]: raise ValueError("Boot parameters differ")
        params["androidboot.vbmeta.digest"] = digest
        params["androidboot.vbmeta.size"] = str(vbsize)
        local.write_bytes(body + p.h.gpt.bootconfig_trailer(p.h.bc.render(params).decode(), len(body)))
        p.h.run("mcopy", "-o", "-i", esp, local, f"::/ruby/initrd-{mode}.img")
    updated["logical_sha256"]["vendor"] = p.h.audit.sha(rebuilt)
    updated["vm_instrumentation"] = {"not_for_release": True, "source": old["image_sha256"],
        "changed_file": "/vendor" + target, "guest_script_sha256": c.hashlib.sha256(script).hexdigest(),
        "probe_apk_sha256": apk_hashes, "policy_unchanged": True}
    embedded = w / "RESEARCH.json"
    embedded.write_text(json.dumps({k:v for k,v in updated.items() if k not in ("image_sha256", "payload_readback")}, indent=2) + "\n")
    p.h.run("mcopy", "-o", "-i", esp, embedded, "::/ruby/RESEARCH.json")
    for name in ("super", "vbmeta_a", "EFI"):
        updated["payload_readback"][name] = p.digest_range(disk, *p.extent(rows[name]))
    for name, expected in updated["logical_sha256"].items():
        if c.hash_logical(disk, offset, layout[name + "_a"]) != expected:
            raise ValueError(f"Logical readback failed: {name}")
    for start, length in p.protected_ranges(table, src.stat().st_size):
        if p.digest_range(disk,start,length) != p.digest_range(src,start,length): raise ValueError("Protected data differs")
    updated["image_sha256"] = p.h.audit.sha(disk)
    if p.h.audit.sha(src) != old["image_sha256"]: raise ValueError("Source changed")
    (w / "manifest.json").write_text(json.dumps(updated, indent=2) + "\n")
    meta.unlink()
    for file in copied: file.unlink()
    (w / "cleanup.json").write_text(json.dumps({"removed": [str(root),str(extracted),str(meta),*map(str, copied)],
        "free_before": free_before, "free_after": shutil.disk_usage(w).free}, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "tools", "inventory", "key", "probes", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--logical", type=Path, help="Directory of unchanged *_a.img inputs; default: copy from the candidate")
    args = parser.parse_args()
    if not Path("/.dockerenv").exists(): parser.error("Use the local installer tools container")
    os.umask(0o077)
    build(args)
