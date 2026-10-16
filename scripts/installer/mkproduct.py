#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a USB-ready GPT disk image from a real OpenBook product's PRODUCT_OUT (ANAL-199): the product's own boot
images, vbmeta and super, booted by systemd-boot the way docs/installer.md §2 describes. Unlike mkproto.py (the
ANAL-189 prototype on the Cuttlefish product) nothing in the Android images is rebuilt or re-signed here.

Runs in the openbook-installer container (scripts/installer/inst-docker.sh; scripts/g14-image.sh wraps it). Reads
a snapshot of PRODUCT_OUT (boot.img, init_boot.img, vendor_boot.img, vbmeta.img, super.img) and AOSP's host
tools (unpack_bootimg, avbtool, simg2img); writes only below --work and --out.

Disk (12 GiB by default; PARTUUIDs derived from --label):
  EFI 256 MiB  misc 4 MiB  boot_a/_b 64  init_boot_a/_b 8  vendor_boot_a/_b 64  vbmeta_a/_b 1  metadata 64
  super (BOARD_SUPER_PARTITION_SIZE, from the image)  userdata (the rest; blank, formatted on first boot)
ESP (systemd-boot, Boot Loader Spec type #1, menu hidden):
  openbook/<slot>/{kernel, vendor_ramdisk.img, ramdisk.img, bootconfig.img, bootconfig-console.img}
  "OpenBook" (default; boot counting, +3 tries) and "OpenBook (serial console)" per slot. The console entry adds
  console=ttyS0 and printk.devkmsg=on (no rate limit on init's log) for VMs and serial adapters.
Bootconfig per slot = vendor_boot's (static product values) + the loader's runtime values: slot, orange AVB state,
vbmeta digest/size, boot_part_uuid (this disk's ESP), serialno. No force_normal_boot: the product has no recovery
ramdisk.

usage: mkproduct.py --inputs DIR --work DIR --out IMG [--label L] [--size-gib N] [--console-density DPI]
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.abspath(__file__))
proto = SourceFileLoader("mkproto", f"{HERE}/mkproto.py").load_module()
bc = SourceFileLoader("bootconfig", f"{HERE}/bootconfig.py").load_module()
MiB = proto.MiB


def layout_for(super_bytes):
    return [
        ("EFI", 256, "ef00"),
        ("misc", 4, "8300"),
        ("boot_a", 64, "8300"), ("boot_b", 64, "8300"),
        ("init_boot_a", 8, "8300"), ("init_boot_b", 8, "8300"),
        ("vendor_boot_a", 64, "8300"), ("vendor_boot_b", 64, "8300"),
        ("vbmeta_a", 1, "8300"), ("vbmeta_b", 1, "8300"),
        ("metadata", 64, "8300"),
        ("super", super_bytes // MiB, "8300"),
        ("userdata", None, "8300"),
    ]


def unpack(img, out):
    """unpack_bootimg into out/, and its mkbootimg arguments as a list."""
    proto.run([proto.tool("unpack_bootimg"), "--boot_img", img, "--out", out], stdout=subprocess.DEVNULL)
    return shlex.split(proto.out([proto.tool("unpack_bootimg"), "--boot_img", img, "--out", out,
                                  "--format=mkbootimg"]))


def arg(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True, help="snapshot of PRODUCT_OUT (scripts/g14-image.sh)")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="openbook-g14")
    ap.add_argument("--size-gib", type=int, default=12)
    ap.add_argument("--console-density", type=int, default=160,
                    help="androidboot.lcd_density of the serial-console entry (VMs run at 1920x1200)")
    ap.add_argument("--serialno", default="OPENBOOKG14USB01")
    a = ap.parse_args()
    if os.path.exists(a.out) and not os.path.isfile(a.out):
        sys.exit(f"refusing {a.out}: not a regular file")
    P, w = a.inputs, a.work
    shutil.rmtree(w, ignore_errors=True)
    os.makedirs(f"{w}/img")

    # ---- boot images, as a boot image v4 loader sees them
    unpack(f"{P}/boot.img", f"{w}/unpack/boot")
    unpack(f"{P}/init_boot.img", f"{w}/unpack/init_boot")
    vargs = unpack(f"{P}/vendor_boot.img", f"{w}/unpack/vendor_boot")
    vendor_cmdline = arg(vargs, "--vendor_cmdline", "")
    vendor_bc = bc.parse_text(open(f"{w}/unpack/vendor_boot/bootconfig").read())
    # All vendor ramdisk fragments in table order (the product's own ramdisk, then ANAL-198's "dlkm" fragment).
    frags = [x for x in vargs if re.search(r"vendor_ramdisk\d+$", x)]
    if not frags:
        sys.exit("vendor_boot has no ramdisk")
    vendor_ramdisk = f"{w}/vendor_ramdisk.img"
    with open(vendor_ramdisk, "wb") as o:
        for fr in frags:
            data = open(fr, "rb").read()
            pad = -len(data) % 4  # each lz4 stream padded like proto.copy_padded, so unlz4 sees a clean end
            o.write(data + b"\0" * (pad + 4 if pad else 0))
    kernel = f"{w}/unpack/boot/kernel"

    # ---- vbmeta: one top-level struct, no chained partitions in this product
    info = proto.avb_info(f"{P}/vbmeta.img")
    if "Chain Partition descriptor" in info:
        sys.exit("vbmeta has chained partitions; this script expects one top-level vbmeta (BoardConfig.mk)")
    digest = proto.out([proto.tool("avbtool"), "calculate_vbmeta_digest", "--image", f"{P}/vbmeta.img",
                        "--hash_algorithm", "sha256"]).strip()
    vb_struct = proto.vbmeta_from_image(f"{P}/vbmeta.img")
    if hashlib.sha256(vb_struct).hexdigest() != digest:
        sys.exit("vbmeta digest cross-check failed")

    # ---- super, raw
    super_raw = f"{w}/img/super.img"
    with open(f"{P}/super.img", "rb") as f:
        sparse = f.read(4) == b"\x3a\xff\x26\xed"
    if sparse:
        proto.run([proto.tool("simg2img"), f"{P}/super.img", super_raw])
    else:
        shutil.copy(f"{P}/super.img", super_raw)
    super_bytes = os.path.getsize(super_raw)

    # ---- disk layout
    size = a.size_gib << 30
    parts = proto.layout(size, a.label, scale=layout_for(super_bytes))
    esp_uuid = next(p["uuid"] for p in parts if p["name"] == "EFI")

    # ---- ESP
    e = f"{w}/esp"
    os.makedirs(f"{e}/EFI/BOOT")
    os.makedirs(f"{e}/loader/entries")
    shutil.copy("/usr/lib/systemd/boot/efi/systemd-bootx64.efi", f"{e}/EFI/BOOT/BOOTX64.EFI")
    open(f"{e}/loader/loader.conf", "w").write("timeout menu-hidden\ndefault openbook-a*\nconsole-mode keep\n"
                                               "editor no\n")
    bootconfigs = {}
    for slot in "ab":
        sd = f"{e}/openbook/{slot}"
        os.makedirs(sd)
        shutil.copy(kernel, f"{sd}/kernel")
        shutil.copy(vendor_ramdisk, f"{sd}/vendor_ramdisk.img")
        proto.copy_padded(f"{w}/unpack/init_boot/ramdisk", f"{sd}/ramdisk.img")
        p = dict(vendor_bc)
        p.update({
            "androidboot.slot_suffix": f"_{slot}",
            "androidboot.verifiedbootstate": "orange",
            "androidboot.vbmeta.device_state": "unlocked",
            "androidboot.vbmeta.avb_version": "1.3",
            "androidboot.vbmeta.hash_alg": "sha256",
            "androidboot.vbmeta.size": str(len(vb_struct)),
            "androidboot.vbmeta.digest": digest,
            "androidboot.vbmeta.invalidate_on_error": "yes",
            "androidboot.veritymode": "enforcing",
            "androidboot.boot_part_uuid": esp_uuid,
            "androidboot.serialno": a.serialno,
            "androidboot.openbook.loader": "sdboot",
        })
        with open(f"{sd}/bootconfig.img", "wb") as f:
            f.write(bc.blob(p))
        # /dev/console follows the last console= (ttyS0); androidboot.console=ttyS0 would make init open
        # /dev/ttyS0 itself, which its policy forbids.
        pc = dict(p, **{"androidboot.lcd_density": str(a.console_density)})
        with open(f"{sd}/bootconfig-console.img", "wb") as f:
            f.write(bc.blob(pc))
        bootconfigs[slot] = p
        common = (f"sort-key openbook\nlinux /openbook/{slot}/kernel\ninitrd /openbook/{slot}/vendor_ramdisk.img\n"
                  f"initrd /openbook/{slot}/ramdisk.img\n")
        # "+3": systemd-boot boot counting; it renames the file on every try (A/B tries remaining).
        open(f"{e}/loader/entries/openbook-{slot}+3.conf", "w").write(
            f"title OpenBook\nversion 17 · slot {slot.upper()}\n{common}"
            f"initrd /openbook/{slot}/bootconfig.img\noptions {vendor_cmdline}\n")
        open(f"{e}/loader/entries/openbook-{slot}-console.conf", "w").write(
            f"title OpenBook (serial console)\nversion 17 · slot {slot.upper()}\n{common}"
            f"initrd /openbook/{slot}/bootconfig-console.img\n"
            f"options {vendor_cmdline} console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on\n")
    esp_img = f"{w}/esp.fat"
    proto.make_fat(e, esp_img, 256)

    # ---- assemble
    tmp = a.out + ".partial"
    proto.make_gpt(tmp, size, parts, proto.partuuid(a.label, "disk"))
    byname = {p["name"]: p for p in parts}
    copies = [(esp_img, "EFI"), (super_raw, "super")] + [
        (f"{P}/{n}.img", f"{n}_{slot}") for slot in "ab" for n in ("boot", "init_boot", "vendor_boot", "vbmeta")]
    verified = {}
    for src, name in copies:
        proto.copy_into(tmp, src, byname[name])
        verified[name] = proto.verify_copy(tmp, src, byname[name])
    os.replace(tmp, a.out)

    fp = ""
    for f in os.listdir(P):
        if f.startswith("build_fingerprint") or f == "fingerprint.txt":
            fp = open(f"{P}/{f}").read().strip()
    meta = {
        "image": a.out, "size": size, "label": a.label, "loader": "systemd-boot",
        "fingerprint": fp, "vendor_cmdline": vendor_cmdline, "vendor_bootconfig": vendor_bc,
        "vendor_ramdisk_fragments": [os.path.basename(x) for x in frags],
        "vbmeta_digest": digest, "vbmeta_size": len(vb_struct), "super_bytes": super_bytes,
        "bootconfig_a": bootconfigs["a"], "partitions": parts, "verified_sha256": verified,
        "esp_files": sorted(os.path.relpath(os.path.join(r, f), e) for r, _, fs in os.walk(e) for f in fs),
    }
    json.dump(meta, open(a.out + ".json", "w"), indent=1)
    proto.run(["sgdisk", "--print", a.out])
    print(a.out)


if __name__ == "__main__":
    main()
