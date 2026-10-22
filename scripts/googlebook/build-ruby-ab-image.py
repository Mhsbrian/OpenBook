#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble a Ruby A/B whole-disk image: slot A from a reviewed candidate, slot B blank.

Composes the pieces built and checked separately:
  plan-ruby-ab.py          the two-slot GPT layout
  build-ruby-ab-super.py   the 24 GiB Virtual A/B super (slot A filled, slot B empty)
and adds what remains:
  vbmeta_a  rebuilt to cover the boot chain like Googlebook's (boot, init_boot,
            vendor_boot hash descriptors plus the six super hashtree descriptors),
            signed with --key, so openbook-bootsync can verify a slot unchanged;
  ESP       systemd-boot plus slot A in openbook-bootsync's layout:
            openbook/a/{kernel, vendor_ramdisk.img, ramdisk.img, bootconfig.img}
            and loader/entries/openbook-a.conf. Files are extracted exactly as
            bootsync.c's slot_load() does, and the bootconfig holds vendor_boot's
            static keys plus the runtime keys, so bootsync's own `status` can
            judge slot A in_sync byte-for-byte.
Slot B, misc, metadata and userdata stay blank (sparse zeros); Android formats
metadata and userdata on first boot and update_engine fills slot B.

Regular files only: writes a private disk image, never a device. Run in the
openbook-installer container (sgdisk, mkfs.fat, mtools, systemd-boot).
"""
import argparse
import importlib.util
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SDBOOT = "/usr/lib/systemd/boot/efi/systemd-bootx64.efi"
EFI_TYPE = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
LINUX_TYPE = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
VM_OPTIONS = "console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on"
# Runtime keys a loader sets (values from the candidate's own entry, minus live-only ones).
RUNTIME_KEYS = ("androidboot.slot_suffix", "androidboot.force_normal_boot", "androidboot.verifiedbootstate",
                "androidboot.vbmeta.device_state", "androidboot.veritymode", "androidboot.vbmeta.avb_version",
                "androidboot.vbmeta.hash_alg", "androidboot.vbmeta.digest", "androidboot.vbmeta.size",
                "androidboot.serialno", "androidboot.selinux", "androidboot.boot_part_uuid")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


planner = load("plan_ab", HERE / "plan-ruby-ab.py")
bc = load("bootconfig", HERE.parent / "installer" / "bootconfig.py")


def run(*cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def rd32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def align_up(v, a):
    return (v + a - 1) // a * a


def padded(data):
    """bootsync.c padded(): pad to 4 bytes, adding pad+4 zero bytes when unaligned."""
    pad = (4 - len(data) % 4) % 4
    return data + (b"\0" * (pad + 4) if pad else b"")


def extract_boot(boot, init_boot, vendor_boot):
    """kernel, generic ramdisk and vendor ramdisk exactly as bootsync.c slot_load() reads them."""
    if boot[:8] != b"ANDROID!" or rd32(boot, 40) < 3:
        raise ValueError("boot_a: not a boot image v3/v4")
    kernel = boot[4096:4096 + rd32(boot, 8)]
    if init_boot[:8] != b"ANDROID!" or rd32(init_boot, 40) < 3:
        raise ValueError("init_boot_a: not a boot image v3/v4")
    rd_off = 4096 + align_up(rd32(init_boot, 8), 4096)
    ramdisk = padded(init_boot[rd_off:rd_off + rd32(init_boot, 12)])
    v = vendor_boot
    if v[:8] != b"VNDRBOOT" or rd32(v, 8) != 4:
        raise ValueError("vendor_boot_a: not a vendor boot image v4")
    page, vrs, hs, dtb = rd32(v, 12), rd32(v, 24), rd32(v, 2096), rd32(v, 2100)
    ts, ne, es, bcs = rd32(v, 2112), rd32(v, 2116), rd32(v, 2120), rd32(v, 2124)
    vro = align_up(hs, page)
    dto = vro + align_up(vrs, page)
    tbo = dto + align_up(dtb, page)
    bco = tbo + align_up(ts, page)
    sec, tab = v[vro:vro + vrs], v[tbo:tbo + ts]
    vram = b"".join(padded(sec[rd32(tab, i * es + 4):rd32(tab, i * es + 4) + rd32(tab, i * es)])
                    for i in range(ne)) if ne else padded(sec)
    vcmdline = v[28:28 + 2048].split(b"\0")[0].decode()
    vbc = bc.parse_text(v[bco:bco + bcs].split(b"\0")[0].decode())
    if not kernel or not ramdisk or not vram:
        raise ValueError("empty kernel or ramdisk")
    return kernel, ramdisk, vram, vcmdline, vbc


def gpt_partuuid(disk, index):
    out = subprocess.check_output(["sgdisk", "-i", str(index), str(disk)], text=True)
    for line in out.splitlines():
        if line.startswith("Partition unique GUID:"):
            return line.split(":", 1)[1].strip().lower()
    raise ValueError("no PARTUUID")


def build(a):
    manifest = json.loads((a.candidate / "manifest.json").read_text())
    layout = planner.plan(manifest, a.disk_bytes)
    planner.validate(layout)
    rows = {r["name"]: (r["first_lba"], r["last_lba"]) for r in manifest["gpt"]}
    w = a.out
    w.mkdir(mode=0o700, parents=True, exist_ok=False)

    # Slot A boot images straight from the candidate disk.
    src = {}
    with open(a.candidate / "ruby-live.img", "rb") as f:
        for name in ("boot_a", "init_boot_a", "vendor_boot_a"):
            first, last = rows[name]
            f.seek(first * 512)
            src[name] = f.read((last - first + 1) * 512)
            (w / f"{name}.img").write_bytes(src[name])

    # vbmeta_a: the candidate's six super hashtree descriptors plus the boot chain's hash descriptors.
    vbmeta = w / "vbmeta_a.img"
    run(a.tools / "avbtool", "make_vbmeta_image", "--algorithm", "SHA256_RSA4096", "--key", a.key,
        "--padding_size", "4096", "--output", vbmeta,
        "--include_descriptors_from_image", a.candidate / "vbmeta.img",
        "--include_descriptors_from_image", w / "boot_a.img",
        "--include_descriptors_from_image", w / "init_boot_a.img",
        "--include_descriptors_from_image", w / "vendor_boot_a.img")
    vb = vbmeta.read_bytes()
    vbmeta_size = 256 + sum(struct.unpack_from(">QQ", vb, 12))
    digest = subprocess.check_output([str(a.tools / "avbtool"), "calculate_vbmeta_digest",
                                      "--image", str(vbmeta)], text=True).strip()

    # Disk and GPT first: the ESP's PARTUUID goes into the bootconfig.
    disk = w / "disk.img"
    with open(disk, "wb") as f:
        f.truncate(a.disk_bytes)
    run("sgdisk", "--clear", "-U", "R", disk, stdout=subprocess.DEVNULL)
    for i, r in enumerate(layout["partitions"], 1):
        start, end = r["offset"] // 512, (r["offset"] + r["length"]) // 512 - 1
        run("sgdisk", "-n", f"{i}:{start}:{end}", "-t", f"{i}:{EFI_TYPE if r['name'] == 'EFI' else LINUX_TYPE}",
            "-c", f"{i}:{r['name']}", disk, stdout=subprocess.DEVNULL)
    index = {r["name"]: i for i, r in enumerate(layout["partitions"], 1)}
    efi_uuid = gpt_partuuid(disk, index["EFI"])

    # Slot A ESP files, as bootsync exports them.
    kernel, ramdisk, vram, vcmdline, vbc = extract_boot(src["boot_a"], src["init_boot_a"], src["vendor_boot_a"])
    live = dict(manifest["entries"]["live"])
    params = dict(vbc)                                  # vendor_boot's static keys first
    for k in RUNTIME_KEYS:
        if k in live:
            params[k] = live[k]
    params.update({"androidboot.slot_suffix": "_a", "androidboot.vbmeta.size": str(vbmeta_size),
                   "androidboot.vbmeta.digest": digest, "androidboot.boot_part_uuid": efi_uuid})
    options = vcmdline + (f" {VM_OPTIONS}" if a.vm else "")
    esp_tree = w / "esp"
    slot = esp_tree / "openbook" / "a"
    slot.mkdir(parents=True)
    (slot / "kernel").write_bytes(kernel)
    (slot / "vendor_ramdisk.img").write_bytes(vram)
    (slot / "ramdisk.img").write_bytes(ramdisk)
    (slot / "bootconfig.img").write_bytes(bc.blob(params))
    (esp_tree / "loader" / "entries").mkdir(parents=True)
    (esp_tree / "loader" / "entries" / "openbook-a.conf").write_text(
        "title Googlebook (OpenBook)\nversion slot A\nsort-key openbook-1\nlinux /openbook/a/kernel\n"
        "initrd /openbook/a/vendor_ramdisk.img\ninitrd /openbook/a/ramdisk.img\n"
        f"initrd /openbook/a/bootconfig.img\noptions {options}\n")
    (esp_tree / "loader" / "loader.conf").write_text(
        f"timeout {1 if a.vm else 3}\ndefault openbook-a.conf\neditor no\nconsole-mode keep\n")
    (esp_tree / "EFI" / "BOOT").mkdir(parents=True)
    shutil.copy(SDBOOT, esp_tree / "EFI" / "BOOT" / "BOOTX64.EFI")

    efi_row = next(r for r in layout["partitions"] if r["name"] == "EFI")
    esp = w / "esp.img"
    with open(esp, "wb") as f:
        f.truncate(efi_row["length"])
    run("mkfs.fat", "-F", "32", "-n", "OPENBOOK", esp, stdout=subprocess.DEVNULL)
    for d in sorted(p for p in esp_tree.rglob("*") if p.is_dir()):
        run("mmd", "-i", esp, "::/" + str(d.relative_to(esp_tree)))
    for p in sorted(p for p in esp_tree.rglob("*") if p.is_file()):
        run("mcopy", "-i", esp, p, "::/" + str(p.relative_to(esp_tree)))
    run("fsck.fat", "-n", esp, stdout=subprocess.DEVNULL)

    # super's LP metadata names its device size: the image must be exactly the planned partition.
    super_row = next(r for r in layout["partitions"] if r["name"] == "super")
    if a.super_img.stat().st_size != super_row["length"]:
        raise ValueError(f"super image is {a.super_img.stat().st_size} bytes, the layout's super is "
                         f"{super_row['length']} (build it with build-ruby-ab-super.py --super-bytes)")
    # Payloads into the disk at their GPT offsets.
    offs = {r["name"]: r["offset"] for r in layout["partitions"]}
    for name, path in (("EFI", esp), ("boot_a", w / "boot_a.img"), ("init_boot_a", w / "init_boot_a.img"),
                       ("vendor_boot_a", w / "vendor_boot_a.img"), ("vbmeta_a", vbmeta),
                       ("super", a.super_img)):
        run("dd", f"if={path}", f"of={disk}", "bs=4M", "conv=notrunc,sparse", "oflag=seek_bytes",
            f"seek={offs[name]}", "status=none")

    result = dict(schema="openbook-ruby-ab-image/1", disk_bytes=a.disk_bytes, vm_entry=a.vm,
                  source_image_sha256=manifest["image_sha256"], efi_partuuid=efi_uuid,
                  vbmeta_a=dict(size=vbmeta_size, digest=digest,
                                covers=["boot", "init_boot", "vendor_boot", "system", "system_ext", "product",
                                        "vendor", "vendor_dlkm", "system_dlkm"]),
                  bootconfig=params, options=options, layout=layout["partitions"])
    (w / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(disk=str(disk), efi_partuuid=efi_uuid, vbmeta_digest=digest, vbmeta_size=vbmeta_size)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "super-img", "tools", "key", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--disk-bytes", type=int, required=True)
    p.add_argument("--vm", action="store_true", help="add the serial console to the entry (QEMU tests)")
    a = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Run in the openbook-installer container (scripts/installer/inst-docker.sh)")
    os.umask(0o077)
    build(a)
