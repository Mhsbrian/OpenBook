#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Update the system on an OpenBook live USB stick in place, keeping its user data (ANAL-331).

A live stick keeps the owner's data in `metadata` (the encryption metadata) and `userdata` (grown to fill the stick
on its first boot). Writing a new image over the whole stick would erase both. This writes only the system:
  partitions  boot_a, init_boot_a, vendor_boot_a, vbmeta_a and super, from IMG, each only where it differs
  ESP         file by file (mtools): every file of IMG's ESP that is missing or different on the stick, except the
              stick's own runtime files (loader/random-seed, openbook/logs/); nothing on the ESP is deleted
Never written: the GPT, misc, metadata and userdata.

IMG must be built for this stick: scripts/installer-image.sh --uuid-label <the label the stick was built with>
--super-mib <the stick's super size>, so every partition the update writes has the stick's start, size and
PARTUUID, and the bootconfig names the stick's own ESP (androidboot.boot_part_uuid). The update is refused unless
the stick's GPT matches IMG's for every partition (userdata: start and PARTUUID; it is larger on the stick).

Android's keys stay usable: the software KeyMint binds key blobs to the verified boot key and state, which an
image signed with the same key keeps, not to vbmeta's digest; IMG's security patch must not be older (checked by
the caller's plan). Rehearse on a byte copy of the stick first (docs/installer.md, "Updating a live stick").

usage: stick-update.py --image IMG --target TARGET [--from SUMS.json] [--write] [--report OUT.json]
  TARGET   the stick's whole-disk device, or a byte copy of it (an image file)
  --from   {partition: sha256} the stick must hold now (e.g. its last read-back): a stick that changed since the plan
           is refused
  --write  write and read back; without it, only the checks and the plan
Runs where it can read (and with --write, write) TARGET: for a device, the openbook-installer container with the
device passed in. Exit 0 done (or nothing to do), 1 refused or failed, 2 usage.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import uuid

SYSTEM = ("super", "boot_a", "init_boot_a", "vendor_boot_a", "vbmeta_a")   # written in this order; the ESP last
KEEP = ("metadata", "userdata", "misc")
ESP_RUNTIME = ("loader/random-seed", "openbook/logs/")
CHUNK = 4 << 20


def gpt(path):
    """[(name, first_lba, sectors, partuuid)] from the primary GPT of PATH (512-byte sectors)."""
    with open(path, "rb") as f:
        f.seek(512)
        hdr = f.read(92)
        if hdr[:8] != b"EFI PART":
            sys.exit(f"{path}: no GPT")
        start, n, size = struct.unpack("<QII", hdr[72:88])
        f.seek(start * 512)
        ents = f.read(n * size)
    out = []
    for i in range(n):
        e = ents[i * size:(i + 1) * size]
        if e[:16] == b"\0" * 16:
            continue
        first, last = struct.unpack("<QQ", e[32:48])
        out.append((e[56:128].decode("utf-16le").rstrip("\0"), first, last - first + 1,
                    str(uuid.UUID(bytes_le=e[16:32]))))
    return out


def digest(path, first, sectors):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        f.seek(first * 512)
        left = sectors * 512
        while left:
            b = f.read(min(left, CHUNK))
            if not b:
                sys.exit(f"{path}: short read")
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def copy_part(src, dst, first, sectors):
    with open(src, "rb") as s, open(dst, "r+b") as d:
        s.seek(first * 512)
        d.seek(first * 512)
        left = sectors * 512
        while left:
            b = s.read(min(left, CHUNK))
            d.write(b)
            left -= len(b)
        d.flush()
        os.fsync(d.fileno())


def esp_files(path, first, into):
    """Extract the FAT ESP at sector FIRST of PATH into INTO; {relative path: sha256}."""
    subprocess.run(["mcopy", "-s", "-n", "-m", "-i", f"{path}@@{first * 512}", "::/", into], check=True,
                   stdout=subprocess.DEVNULL)
    out = {}
    for root, _, names in os.walk(into):
        for n in names:
            p = os.path.join(root, n)
            out[os.path.relpath(p, into)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--from", dest="from_sums")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--report")
    a = ap.parse_args()
    report = {"schema": "openbook-stick-update/1", "image": os.path.basename(a.image), "target": a.target,
              "write": a.write, "refused": None}

    def refuse(why):
        report["refused"] = why
        if a.report:
            open(a.report, "w").write(json.dumps(report, indent=2) + "\n")
        print(f"refused: {why}")
        sys.exit(1)

    img, tgt = gpt(a.image), gpt(a.target)
    ti = {p[0]: p for p in tgt}
    for name, first, sectors, puuid in img:
        t = ti.get(name)
        if t is None:
            refuse(f"the stick has no {name} partition")
        if name == "userdata":
            ok = (t[1], t[3]) == (first, puuid) and t[2] >= sectors
        else:
            ok = t[1:] == (first, sectors, puuid)
        if not ok:
            refuse(f"{name}: the stick has start {t[1]}, {t[2]} sectors, {t[3]}; the image {first}, {sectors}, "
                   f"{puuid} (build the image with --uuid-label and --super-mib for this stick)")
    if [p[0] for p in tgt] != [p[0] for p in img]:
        refuse("the stick's partitions are not the image's, in the image's order")
    ip = {p[0]: p for p in img}

    now = {name: digest(a.target, ip[name][1], ip[name][2]) for name in SYSTEM}
    want = {name: digest(a.image, ip[name][1], ip[name][2]) for name in SYSTEM}
    report["before"] = now
    report["image_partitions"] = want
    if a.from_sums:
        expected = json.load(open(a.from_sums))
        for name, sha in expected.items():
            if now.get(name) != sha:
                refuse(f"{name} is not what the plan read back ({now.get(name, '?')[:12]}, expected {sha[:12]})")
    keep_before = {name: digest(a.target, ti[name][1], ti[name][2]) for name in ("metadata", "misc")}

    work = tempfile.mkdtemp(prefix="stick-update-")
    try:
        new_esp = esp_files(a.image, ip["EFI"][1], f"{work}/new")
        old_esp = esp_files(a.target, ip["EFI"][1], f"{work}/old")
        esp_plan = sorted(p for p, sha in new_esp.items()
                          if not p.startswith(ESP_RUNTIME) and old_esp.get(p) != sha)
        part_plan = [n for n in SYSTEM if now[n] != want[n]]
        report["plan"] = {"partitions": part_plan, "esp_files": esp_plan,
                          "kept": list(KEEP) + ["GPT", "ESP runtime files: " + ", ".join(ESP_RUNTIME)]}
        print("partitions to write: " + (", ".join(part_plan) or "none"))
        print("ESP files to write:  " + (", ".join(esp_plan) or "none"))
        if not a.write:
            print("plan only (no --write): nothing written")
            return 0
        for name in part_plan:
            copy_part(a.image, a.target, ip[name][1], ip[name][2])
            print(f"wrote {name}")
        for rel in esp_plan:
            parent = os.path.dirname(rel)
            if parent:
                subprocess.run(["mmd", "-D", "s", "-i", f"{a.target}@@{ip['EFI'][1] * 512}", "::/" + parent],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["mcopy", "-o", "-m", "-i", f"{a.target}@@{ip['EFI'][1] * 512}",
                            f"{work}/new/{rel}", "::/" + rel], check=True)
            print(f"wrote ESP {rel}")
        subprocess.run(["sync"])
        # read back: every system partition is the image's, the ESP has every planned file, metadata and misc
        # are untouched
        after = {name: digest(a.target, ip[name][1], ip[name][2]) for name in SYSTEM}
        shutil.rmtree(f"{work}/old")
        back = esp_files(a.target, ip["EFI"][1], f"{work}/old")
        keep_after = {name: digest(a.target, ti[name][1], ti[name][2]) for name in ("metadata", "misc")}
        report["after"] = after
        bad = [n for n in SYSTEM if after[n] != want[n]] + \
              [f"ESP {p}" for p in esp_plan if back.get(p) != new_esp[p]] + \
              [n for n in keep_after if keep_after[n] != keep_before[n]]
        report["readback_ok"] = not bad
        if bad:
            print("READ-BACK FAILED: " + ", ".join(bad))
            return 1
        print("read back: the system partitions and ESP files are the image's; metadata and misc unchanged")
        return 0
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if a.report:
            open(a.report, "w").write(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())
