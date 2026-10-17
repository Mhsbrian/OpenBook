#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the OpenBook live USB image (ANAL-190, docs/installer.md section 11) from a snapshot of a real OpenBook
product's PRODUCT_OUT: the approved format (docs/installer.md section 1.2, 3.1), a raw GPT disk image with
systemd-boot, slot A only, and blank metadata/userdata that Android formats on first boot. Nothing in the Android
images is rebuilt or re-signed.

Runs in the openbook-installer container (scripts/installer/inst-docker.sh; scripts/installer-image.sh wraps it).
Reads the snapshot (boot.img, init_boot.img, vendor_boot.img, vbmeta.img, super.img) and AOSP's host tools
(unpack_bootimg, avbtool, simg2img, lpdump, lpmake, fsck.erofs); writes only below --work and --out.

Disk (PARTUUIDs derived from --label):
  EFI 256 MiB  misc 4  boot_a  init_boot_a  vendor_boot_a  vbmeta_a (sized to their images)  metadata 64
  super        the product's dynamic partitions re-packed with lpmake into content + --super-margin-mib (the
               product's super is sized for OTAs; a live stick never takes one). Partition contents, names, groups
               and the virtual A/B flag are kept, and every partition is checked by sha256 against the original.
  userdata     --userdata-mib, blank. openbook-live-init grows it to fill the stick on the first boot.
ESP (FAT32 "OPENBOOK", systemd-boot at the removable-media path, Boot Loader Spec type #1 entries):
  openbook/a/{kernel, vendor_ramdisk.img, ramdisk.img, live.img, bootconfig*.img}
      live.img is a cpio with /openbook-live-init (scripts/installer/live-init.c), started as rdinit=.
  Entries: "OpenBook" (default), "OpenBook - save logs to this USB stick", "OpenBook - safe graphics" and
      "OpenBook - safe graphics, save logs", "OpenBook - start fresh", "OpenBook - serial console (virtual
      machines)". Bootconfig per entry = vendor_boot's static values + the loader's runtime values (slot _a, orange
      AVB state, vbmeta digest/size, boot_part_uuid = this disk's ESP, serialno) + androidboot.openbook.live=1
      (+ live_reset=1, or logs=1 and selinux=permissive, or hardware.egl=mesa).
  LICENSES/: the firmware licence files taken from the vendor image itself, systemd-boot's and the kernel's licence
      texts and a README naming each component, its licence and where its source is.
  openbook/README.txt, openbook/MANIFEST.json (image identity and partition hashes), openbook/logs/.
  openbook/install/super-metadata.img and MANIFEST.json's "install" section (ANAL-191): what the installer
      (openbook-install, device/anybook/common/installer) needs to put this system on a disk: the installed
      layout, super's metadata for the installed size with every logical partition's offset in both supers, the
      loader files and their hashes, and the bootconfig without the live-only values.
--vm-bundle DIR also writes the extra entries the QEMU tests use (console + start fresh, console + save logs).
Deterministic: the same inputs, --label and --epoch give the same image, byte for byte.

usage: mklive.py --inputs DIR --live-init FILE --work DIR --out IMG [--label L] [--userdata-mib N]
                 [--super-margin-mib N] [--menu-timeout T] [--epoch S] [--vm-bundle DIR]
                 [--firmware-manifest TSV] [--install-super-mib N] [--install-min-gb N]
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
SDBOOT = "/usr/lib/systemd/boot/efi/systemd-bootx64.efi"
SPDX = "/usr/share/licenses/spdx"
VM_OPTIONS = "console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on"


def mib(n):
    return -(-n // MiB)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(16 * MiB), b""):
            h.update(b)
    return h.hexdigest()


def unpack(img, out):
    """unpack_bootimg into out/, and its mkbootimg arguments as a list."""
    proto.run([proto.tool("unpack_bootimg"), "--boot_img", img, "--out", out], stdout=subprocess.DEVNULL)
    return shlex.split(proto.out([proto.tool("unpack_bootimg"), "--boot_img", img, "--out", out,
                                  "--format=mkbootimg"]))


def arg(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


# ---------------------------------------------------------------- super
def lp_layout(super_raw):
    """lpdump of a raw super image: header facts, groups, and each partition's linear extents on 'super'."""
    meta = json.loads(proto.out([proto.tool("lpdump"), "--json", super_raw]))
    text = proto.out([proto.tool("lpdump"), super_raw])
    slot0 = text.split("Slot 1:")[0]
    slot0 = slot0.split("Partition table:")[1].split("Super partition layout:")[0]
    parts, cur = {}, None
    for line in slot0.splitlines():
        m = re.match(r"\s+Name: (\S+)", line)
        if m:
            cur = parts.setdefault(m.group(1), {"extents": [], "attrs": "none", "group": None})
            continue
        if cur is None:
            continue
        m = re.match(r"\s+Group: (\S+)", line)
        if m:
            cur["group"] = m.group(1)
        m = re.match(r"\s+Attributes: (.*)", line)
        if m:
            cur["attrs"] = "readonly" if "readonly" in m.group(1) else "none"
        m = re.match(r"\s+(\d+) \.\. (\d+) linear (\S+) (\d+)", line)
        if m:
            a, b, dev, phys = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))
            if dev != "super":
                sys.exit(f"extent on block device {dev}: only a single 'super' device is handled")
            cur["extents"].append((a, b - a + 1, phys))
        elif re.match(r"\s+\d+ \.\. \d+ ", line):
            sys.exit(f"unsupported extent type: {line.strip()}")
    sizes = {p["name"]: int(p.get("size", 0)) for p in meta["partitions"]}
    for name, p in parts.items():
        p["size"] = sizes.get(name, 0)
        if sum(n for _, n, _ in p["extents"]) * 512 != p["size"]:
            sys.exit(f"{name}: extents do not add up to its size")
    hdr = {
        "metadata_size": int(re.search(r"Metadata max size: (\d+)", text).group(1)),
        "metadata_slots": int(re.search(r"Metadata slot count: (\d+)", text).group(1)),
        "virtual_ab": "virtual_ab_device" in re.search(r"Header flags: (.*)", text).group(1),
        "block_size": int(meta["block_devices"][0]["block_size"]),
        "alignment": int(meta["block_devices"][0]["alignment"]),
        "device_size": int(meta["block_devices"][0]["size"]),
    }
    groups = [(g["name"], int(g.get("maximum_size", 0))) for g in meta["groups"] if g["name"] != "default"]
    return hdr, groups, parts


def extract_partitions(super_raw, parts, out):
    os.makedirs(out, exist_ok=True)
    files = {}
    with open(super_raw, "rb") as src:
        for name, p in parts.items():
            if not p["size"]:
                continue
            path = f"{out}/{name}.img"
            with open(path, "wb") as dst:
                for _, n, phys in p["extents"]:
                    src.seek(phys * 512)
                    left = n * 512
                    while left:
                        b = src.read(min(left, 16 * MiB))
                        dst.write(b)
                        left -= len(b)
            files[name] = path
    return files


def install_super(w, hdr, groups, parts, live_parts, check, size_mib):
    """super's metadata for an installed disk (docs/installer.md 3.2): the same partitions, groups (at their
    original maximum sizes), attributes and virtual A/B flag as the product's super, for a size_mib partition.
    lpmake allocates the logical partitions in the same order and alignment as for the live super, so every
    partition sits at the same offset in both; the installer copies the live super's extents and then writes this
    metadata region (the reserved area, both geometries and every metadata slot, up to the first logical sector)."""
    size = size_mib * MiB
    img = f"{w}/super.install-meta.img"
    cmd = [proto.tool("lpmake"), "--device-size", size, "--metadata-size", hdr["metadata_size"],
           "--metadata-slots", hdr["metadata_slots"], "--super-name", "super", "--alignment", hdr["alignment"],
           "--block-size", hdr["block_size"], "--force-full-image", "--output", img]
    if hdr["virtual_ab"]:
        cmd.append("--virtual-ab")
    for g, maxsize in groups:
        cmd += ["--group", f"{g}:{maxsize}"]
    for name, p in parts.items():
        cmd += ["--partition", f"{name}:{p['attrs']}:{p['size']}:{p['group']}"]
    proto.run(cmd, stdout=subprocess.DEVNULL)
    ihdr, igroups, iparts = lp_layout(img)
    if [g for g, _ in igroups] != [g for g, _ in groups] or ihdr["virtual_ab"] != hdr["virtual_ab"]:
        sys.exit("install super: groups or flags differ")
    extents, first = [], None
    for name, p in parts.items():
        q, lp = iparts.get(name), live_parts.get(name)
        if not q or (q["size"], q["attrs"], q["group"]) != (p["size"], p["attrs"], p["group"]):
            sys.exit(f"install super: {name} differs")
        if not p["size"]:
            continue
        if len(q["extents"]) != 1 or len(lp["extents"]) != 1:
            sys.exit(f"install super: {name} is not one linear extent")
        src, dst = lp["extents"][0][2] * 512, q["extents"][0][2] * 512
        extents.append({"name": name, "src": src, "dst": dst, "bytes": p["size"], "sha256": check[name]["sha256"]})
        first = dst if first is None else min(first, dst)
    with open(img, "rb") as f:
        meta = f.read(first)
    os.remove(img)
    path = f"{w}/super-metadata.img"
    open(path, "wb").write(meta)
    return path, {"metadata_file": "openbook/install/super-metadata.img", "metadata_bytes": len(meta),
                  "metadata_sha256": hashlib.sha256(meta).hexdigest(), "device_bytes": size,
                  "virtual_ab": hdr["virtual_ab"], "extents": extents}


def repack_super(super_raw, w, margin_mib, install_mib):
    hdr, groups, parts = lp_layout(super_raw)
    files = extract_partitions(super_raw, parts, f"{w}/lp")
    align = hdr["alignment"]
    content = sum(-(-p["size"] // align) * align for p in parts.values())
    # liblp puts the first logical sector after the reserved area, geometry (2 copies) and metadata (2 x slots).
    reserved = 4096 + 2 * 4096 + 2 * hdr["metadata_slots"] * hdr["metadata_size"]
    reserved = -(-reserved // align) * align
    size = -(-(reserved + content + margin_mib * MiB) // MiB) * MiB
    cmd = [proto.tool("lpmake"), "--device-size", size, "--metadata-size", hdr["metadata_size"],
           "--metadata-slots", hdr["metadata_slots"], "--super-name", "super", "--alignment", align,
           "--block-size", hdr["block_size"], "--force-full-image", "--output", f"{w}/super.live.img"]
    if hdr["virtual_ab"]:
        cmd.append("--virtual-ab")
    for g, _ in groups:
        cmd += ["--group", f"{g}:{size - reserved}"]
    for name, p in parts.items():
        cmd += ["--partition", f"{name}:{p['attrs']}:{p['size']}:{p['group']}"]
        if name in files:
            cmd += ["--image", f"{name}={files[name]}"]
    proto.run(cmd, stdout=subprocess.DEVNULL)
    # Check: same partitions, groups and attributes, and byte-identical contents.
    hdr2, groups2, parts2 = lp_layout(f"{w}/super.live.img")
    if [g for g, _ in groups2] != [g for g, _ in groups] or hdr2["virtual_ab"] != hdr["virtual_ab"]:
        sys.exit("repacked super: groups or flags differ")
    check = {}
    files2 = extract_partitions(f"{w}/super.live.img", parts2, f"{w}/lp2")
    for name, p in parts.items():
        q = parts2.get(name)
        if not q or (q["size"], q["attrs"], q["group"]) != (p["size"], p["attrs"], p["group"]):
            sys.exit(f"repacked super: {name} differs")
        if name in files:
            a, b = sha256(files[name]), sha256(files2[name])
            if a != b:
                sys.exit(f"repacked super: {name} content differs")
            check[name] = {"size": p["size"], "sha256": a}
    shutil.rmtree(f"{w}/lp2")
    meta_path, inst = install_super(w, hdr, groups, parts, parts2, check, install_mib)
    return f"{w}/super.live.img", {"original_bytes": hdr["device_size"], "live_bytes": size, "partitions": check,
                                   "virtual_ab": hdr["virtual_ab"], "metadata_slots": hdr["metadata_slots"]}, files, \
        meta_path, inst


# ---------------------------------------------------------------- licences
def firmware_licences(vendor_img, w, manifest_tsv):
    """Extract the vendor image; list /vendor/firmware and its licence files; check each file has a licence."""
    x = f"{w}/vendor-x"
    shutil.rmtree(x, ignore_errors=True)
    proto.run([proto.tool("fsck.erofs"), f"--extract={x}", "--no-preserve", vendor_img], stdout=subprocess.DEVNULL)
    fw = f"{x}/firmware"
    files, licences = [], []
    for root, _, names in os.walk(fw):
        for n in sorted(names):
            rel = os.path.relpath(os.path.join(root, n), fw)
            if re.match(r"(LICEN[CS]E|COPYING|WHENCE)", n) or rel.startswith("LICENSES/"):
                licences.append(rel)
            else:
                files.append(rel)
    files.sort()
    licences.sort()
    known = {}
    if manifest_tsv and os.path.exists(manifest_tsv):
        for line in open(manifest_tsv):
            if line.startswith(("#", "path\t")):
                continue
            f = line.rstrip("\n").split("\t")
            if len(f) >= 6:
                known[f[0].removeprefix("vendor/firmware/")] = f[5]
    lic_names = {os.path.basename(x) for x in licences}
    unmatched, rows = [], []
    for rel in files:
        lic = known.get(rel)
        if lic is None and rel.startswith("mediatek/"):
            lic = "LICENCE.mediatek"  # AOSP's linux_firmware_mt79xx modules (external/linux-firmware)
        if lic is None and rel.startswith("regulatory.db"):
            lic = "LICENSE.wireless-regdb"  # cfg80211's database from external/wireless-regdb (wifi/wifi.mk)
        if lic is None or lic not in lic_names:
            unmatched.append(rel)
        rows.append((rel, os.path.getsize(f"{fw}/{rel}"), sha256(f"{fw}/{rel}"), lic or "?"))
    return fw, files, licences, rows, unmatched


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True, help="snapshot of PRODUCT_OUT (scripts/installer-image.sh)")
    ap.add_argument("--live-init", required=True, help="static openbook-live-init binary")
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="openbook-live")
    ap.add_argument("--userdata-mib", type=int, default=1024)
    ap.add_argument("--super-margin-mib", type=int, default=64)
    ap.add_argument("--menu-timeout", default="menu-hidden", help="loader.conf timeout: menu-hidden or seconds")
    ap.add_argument("--epoch", type=int, default=int(os.environ.get("SOURCE_DATE_EPOCH", "1767225600")))
    ap.add_argument("--serialno", default="OPENBOOKLIVE0001")
    ap.add_argument("--vm-density", type=int, default=160, help="androidboot.lcd_density of the VM entries")
    ap.add_argument("--vm-bundle", help="write the QEMU-only entries (console + reset, console + logs) here")
    ap.add_argument("--firmware-manifest", help="ANAL-198 firmware-manifest.tsv, to map firmware files to licences")
    ap.add_argument("--provenance", help="text file copied to openbook/PROVENANCE.txt")
    ap.add_argument("--install-super-mib", type=int, default=12288, help="super on an installed disk (3.2)")
    ap.add_argument("--install-min-gb", type=int, default=64, help="smallest disk (or free space) to install to")
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
    frags = [x for x in vargs if re.search(r"vendor_ramdisk\d+$", x)]
    if not frags:
        sys.exit("vendor_boot has no ramdisk")
    vendor_ramdisk = f"{w}/vendor_ramdisk.img"
    with open(vendor_ramdisk, "wb") as o:
        for fr in frags:  # every lz4 stream padded like proto.copy_padded, so unlz4 sees a clean end
            data = open(fr, "rb").read()
            pad = -len(data) % 4
            o.write(data + b"\0" * (pad + 4 if pad else 0))
    kernel = f"{w}/unpack/boot/kernel"
    release = re.search(rb"(\d+\.\d+\.\d+-android\d+-\d+-g[0-9a-f]+)", open(kernel, "rb").read())
    release = release.group(1).decode() if release else "unknown"

    # ---- vbmeta: one top-level struct, no chained partitions in this product
    if "Chain Partition descriptor" in proto.avb_info(f"{P}/vbmeta.img"):
        sys.exit("vbmeta has chained partitions; this script expects one top-level vbmeta")
    digest = proto.out([proto.tool("avbtool"), "calculate_vbmeta_digest", "--image", f"{P}/vbmeta.img",
                        "--hash_algorithm", "sha256"]).strip()
    vb_struct = proto.vbmeta_from_image(f"{P}/vbmeta.img")
    if hashlib.sha256(vb_struct).hexdigest() != digest:
        sys.exit("vbmeta digest cross-check failed")

    # ---- super: raw, then re-packed to its content
    super_raw = f"{w}/img/super.raw"
    with open(f"{P}/super.img", "rb") as f:
        sparse = f.read(4) == b"\x3a\xff\x26\xed"
    if sparse:
        proto.run([proto.tool("simg2img"), f"{P}/super.img", super_raw])
    else:
        shutil.copy(f"{P}/super.img", super_raw)
    super_live, super_info, lp_files, install_meta, install_super_info = repack_super(
        super_raw, w, a.super_margin_mib, a.install_super_mib)
    os.remove(super_raw)

    # ---- firmware licences, from the vendor image that ships
    vendor_part = next((n for n in lp_files if n.startswith("vendor_") and not n.startswith("vendor_dlkm")), None)
    if not vendor_part:
        sys.exit("no vendor partition in super")
    fw, fw_files, fw_lic, fw_rows, fw_unmatched = firmware_licences(lp_files[vendor_part], w, a.firmware_manifest)
    shutil.rmtree(f"{w}/lp")

    # ---- disk layout
    sizes = {n: max(d, mib(os.path.getsize(f"{P}/{n}.img"))) for n, d in
             (("boot", 64), ("init_boot", 8), ("vendor_boot", 64), ("vbmeta", 1))}
    scale = [("EFI", 256, "ef00"), ("misc", 4, "8300"), ("boot_a", sizes["boot"], "8300"),
             ("init_boot_a", sizes["init_boot"], "8300"), ("vendor_boot_a", sizes["vendor_boot"], "8300"),
             ("vbmeta_a", sizes["vbmeta"], "8300"), ("metadata", 64, "8300"),
             ("super", os.path.getsize(super_live) // MiB, "8300"), ("userdata", a.userdata_mib, "8300")]
    # 1 MiB for the primary GPT, the partitions (userdata last, ending on a whole MiB), 1 MiB for the backup GPT:
    # on a stick of exactly this size, openbook-live-init has nothing to grow.
    size = (2 + sum(m for _, m, _ in scale)) * MiB
    parts = proto.layout(size, a.label, scale=scale)
    esp_uuid = next(p["uuid"] for p in parts if p["name"] == "EFI")

    # ---- bootconfig: product static values + loader runtime values + live flags
    base = dict(vendor_bc)
    base.update({
        "androidboot.slot_suffix": "_a",
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
        "androidboot.openbook.live": "1",
    })
    logs = {"androidboot.openbook.logs": "1", "androidboot.selinux": "permissive"}
    reset = {"androidboot.openbook.live_reset": "1"}
    # GLES straight on Mesa radeonsi instead of ANGLE on RADV; Vulkan stays RADV. The GPU HAL selection lets a
    # bootloader-set androidboot.hardware.* win (init.anybook.graphics-amd.rc).
    safe = {"androidboot.hardware.egl": "mesa"}
    vm = {"androidboot.lcd_density": str(a.vm_density)}
    variants = {  # file stem: (bootconfig, extra kernel options, title, sort key, in the image?)
        "live": (base, "", "OpenBook", "openbook-1", True),
        "logs": ({**base, **logs}, "", "OpenBook - save logs to this USB stick", "openbook-2", True),
        "safe": ({**base, **safe}, "", "OpenBook - safe graphics (Mesa GL, no ANGLE)", "openbook-3", True),
        "safe-logs": ({**base, **safe, **logs}, "", "OpenBook - safe graphics, save logs to this USB stick",
                      "openbook-4", True),
        "reset": ({**base, **reset}, "", "OpenBook - start fresh (erase this stick's saved data)", "openbook-5", True),
        "vm": ({**base, **vm}, VM_OPTIONS, "OpenBook - serial console (virtual machines)", "openbook-6", True),
        "vm-reset": ({**base, **vm, **reset}, VM_OPTIONS, "OpenBook - VM test: start fresh", "openbook-7", False),
        "vm-logs": ({**base, **vm, **logs, "androidboot.openbook.logs_timeout": "300"}, VM_OPTIONS,
                    "OpenBook - VM test: save logs", "openbook-8", False),
    }

    # ---- ESP
    e = f"{w}/esp"
    for d in ("EFI/BOOT", "loader/entries", "openbook/a", "openbook/logs", "openbook/install", "LICENSES/firmware"):
        os.makedirs(f"{e}/{d}")
    shutil.copy(SDBOOT, f"{e}/EFI/BOOT/BOOTX64.EFI")
    open(f"{e}/loader/loader.conf", "w").write(
        f"timeout {a.menu_timeout}\ndefault openbook-live.conf\nconsole-mode keep\neditor no\n")
    sd = f"{e}/openbook/a"
    shutil.copy(kernel, f"{sd}/kernel")
    shutil.copy(vendor_ramdisk, f"{sd}/vendor_ramdisk.img")
    proto.copy_padded(f"{w}/unpack/init_boot/ramdisk", f"{sd}/ramdisk.img")
    open(f"{sd}/live.img", "wb").write(proto.newc([("openbook-live-init", 0o100755, open(a.live_init, "rb").read())]))
    vmb = a.vm_bundle
    if vmb:
        shutil.rmtree(vmb, ignore_errors=True)
        os.makedirs(f"{vmb}/loader/entries")
        os.makedirs(f"{vmb}/openbook/a")
    entries = {}
    for stem, (params, extra, title, key, in_image) in variants.items():
        root = e if in_image else vmb
        if not root:
            continue
        with open(f"{root}/openbook/a/bootconfig-{stem}.img", "wb") as f:
            f.write(bc.blob(params))
        conf = (f"title {title}\nversion 17 · live\nsort-key {key}\nlinux /openbook/a/kernel\n"
                "initrd /openbook/a/vendor_ramdisk.img\ninitrd /openbook/a/ramdisk.img\ninitrd /openbook/a/live.img\n"
                f"initrd /openbook/a/bootconfig-{stem}.img\n"
                f"options {vendor_cmdline} rdinit=/openbook-live-init{' ' + extra if extra else ''}\n")
        open(f"{root}/loader/entries/openbook-{stem}.conf", "w").write(conf)
        entries[stem] = {"title": title, "in_image": in_image, "file": f"loader/entries/openbook-{stem}.conf",
                         "bootconfig": params}

    # licences
    for rel in fw_lic:
        os.makedirs(os.path.dirname(f"{e}/LICENSES/firmware/{os.path.basename(rel)}"), exist_ok=True)
        shutil.copy(f"{fw}/{rel}", f"{e}/LICENSES/firmware/{os.path.basename(rel)}")
    with open(f"{e}/LICENSES/firmware/FILES.tsv", "w") as f:
        f.write("# /vendor/firmware in this image: path, bytes, sha256, licence file (LICENSES/firmware/)\n")
        for row in fw_rows:
            f.write("\t".join(str(x) for x in row) + "\n")
    shutil.copy(f"{SPDX}/LGPL-2.1-or-later.txt", f"{e}/LICENSES/LGPL-2.1-or-later.txt")
    shutil.copy(f"{SPDX}/GPL-2.0-only.txt", f"{e}/LICENSES/GPL-2.0-only.txt")
    shutil.copy(f"{SPDX}/Apache-2.0.txt", f"{e}/LICENSES/Apache-2.0.txt")
    sdboot_ver = proto.out(["pacman", "-Q", "systemd"]).split()[1]
    open(f"{e}/LICENSES/README.txt", "w").write(f"""OpenBook live USB stick: licences of what is on it
==================================================
EFI/BOOT/BOOTX64.EFI   systemd-boot {sdboot_ver} (Arch Linux build), LGPL-2.1-or-later (LGPL-2.1-or-later.txt).
                       Source: https://github.com/systemd/systemd (tag v{sdboot_ver.split('-')[0]}) and the Arch
                       package source (https://gitlab.archlinux.org/archlinux/packaging/packages/systemd).
openbook/a/kernel      Linux {release}: the Android android17-6.18 GKI with the OpenBook patches and
                       vendor modules (in vendor_dlkm/system_dlkm), GPL-2.0-only (GPL-2.0-only.txt).
                       Corresponding source: android.googlesource.com/kernel/common at the commit in the
                       release string, plus kernel/ in https://github.com/Mhsbrian/OpenBook (patches, config,
                       module list, build manifest).
openbook/a/*ramdisk*   Android 17 (AOSP) first-stage init and vendor ramdisk, Apache-2.0 and others; the
                       per-module notices are in the system image (Settings > About > Legal information).
openbook/a/live.img    openbook-live-init (scripts/installer/live-init.c in the OpenBook repo), Apache-2.0.
super, boot partitions Android 17 built from AOSP source by the OpenBook project. No Google Mobile Services,
                       Google apps or other proprietary Google software.
/vendor/firmware       {len(fw_files)} linux-firmware files, redistributed unmodified under the licences in
                       firmware/ (the files as shipped in the vendor image). firmware/FILES.tsv maps each file
                       to its licence.
""")
    # README and manifest
    fp = ""
    for f in sorted(os.listdir(P)):
        if f.startswith("build_fingerprint"):
            fp = open(f"{P}/{f}").read().strip()
    open(f"{e}/openbook/README.txt", "w").write(f"""OpenBook live USB stick ({a.label})
Build: {fp or 'unknown'}

Start a computer from this stick (UEFI, Secure Boot off). Hold a key while it starts to see the menu:
  OpenBook                                  the live system. Your changes are kept on this stick.
  OpenBook - save logs to this USB stick    the same, and it saves the kernel log, logcat, system facts and a
                                            screenshot to openbook/logs/live-NNN/ on this stick, then shuts down
                                            (within about 10 minutes). For bug reports.
  OpenBook - safe graphics                  draws with Mesa's OpenGL ES driver directly instead of ANGLE. Try it
                                            if the screen stays black; "safe graphics, save logs" saves logs too.
  OpenBook - start fresh                    erases what the live system saved on this stick, then starts it.
  OpenBook - serial console                 for virtual machines (the console is on the first serial port).
Nothing on the computer's own disks is changed by this stick.
Licences: LICENSES/README.txt.
""")
    if a.provenance:
        shutil.copy(a.provenance, f"{e}/openbook/PROVENANCE.txt")
    copies = [("boot_a", f"{P}/boot.img"), ("init_boot_a", f"{P}/init_boot.img"),
              ("vendor_boot_a", f"{P}/vendor_boot.img"), ("vbmeta_a", f"{P}/vbmeta.img"), ("super", super_live)]
    shutil.copy(install_meta, f"{e}/openbook/install/super-metadata.img")
    esp_files = {}
    for rel in ("EFI/BOOT/BOOTX64.EFI", "openbook/a/kernel", "openbook/a/vendor_ramdisk.img", "openbook/a/ramdisk.img"):
        esp_files[rel] = {"bytes": os.path.getsize(f"{e}/{rel}"), "sha256": sha256(f"{e}/{rel}")}
    live_only = ("androidboot.openbook.live", "androidboot.boot_part_uuid", "androidboot.serialno")
    install = {
        "schema": "openbook-install-source/1",
        "min_disk_bytes": a.install_min_gb * 1000 ** 3,
        "esp_mib": 512, "xbootldr_mib": 512,
        # docs/installer.md 3.2: A/B boot partitions; slot B stays blank until the first update (bootsync, later).
        "partitions": [{"name": "misc", "mib": 4}] +
                      [x for n in ("boot", "init_boot", "vendor_boot", "vbmeta")
                       for x in ({"name": f"{n}_a", "mib": sizes[n], "src": f"{n}_a"}, {"name": f"{n}_b", "mib": sizes[n]})] +
                      [{"name": "metadata", "mib": 64}, {"name": "super", "mib": a.install_super_mib, "src": "super"},
                       {"name": "userdata", "mib": 0}],
        "super": install_super_info,
        "esp": {"loader": "EFI/BOOT/BOOTX64.EFI", "kernel": "openbook/a/kernel",
                "initrds": ["openbook/a/vendor_ramdisk.img", "openbook/a/ramdisk.img"], "files": esp_files},
        "entry": {"title": "OpenBook", "version": "17 · slot A", "options": vendor_cmdline},
        "loader_conf": "timeout menu-hidden\nconsole-mode keep\neditor no\n",
        "bootconfig": {k: v for k, v in base.items() if k not in live_only},
    }
    manifest = {
        "schema": "openbook-live-manifest/2", "label": a.label, "fingerprint": fp, "kernel_release": release,
        "slot": "a", "vbmeta_digest": digest,
        "partitions": {n: {"bytes": os.path.getsize(s), "sha256": sha256(s)} for n, s in copies},
        "install": install,
    }
    json.dump(manifest, open(f"{e}/openbook/MANIFEST.json", "w"), indent=1, sort_keys=True)
    # Deterministic FAT: fixed volume ID and times (mkfs.fat --invariant, mcopy -m with fixed file times).
    for root, dirs, names in os.walk(e):
        for n in dirs + names:
            os.utime(os.path.join(root, n), (a.epoch, a.epoch))
    esp_img = f"{w}/esp.fat"
    proto.run(["mkfs.vfat", "--invariant", "-i", hashlib.sha256(a.label.encode()).hexdigest()[:8], "-F", "32",
               "-n", "OPENBOOK", "-C", esp_img, str(256 * 1024)], stdout=subprocess.DEVNULL)
    proto.run(["mcopy", "-s", "-m", "-i", esp_img] + [os.path.join(e, x) for x in sorted(os.listdir(e))] + ["::/"],
              env={**os.environ, "SOURCE_DATE_EPOCH": str(a.epoch)})
    if vmb:
        for root, dirs, names in os.walk(vmb):
            for n in dirs + names:
                os.utime(os.path.join(root, n), (a.epoch, a.epoch))

    # ---- assemble
    tmp = a.out + ".partial"
    proto.make_gpt(tmp, size, parts, proto.partuuid(a.label, "disk"))
    byname = {p["name"]: p for p in parts}
    verified = {}
    for name, src in [("EFI", esp_img)] + copies:
        proto.copy_into(tmp, src, byname[name])
        verified[name] = proto.verify_copy(tmp, src, byname[name])
    os.replace(tmp, a.out)

    meta = {
        "schema": "openbook-live-image/1", "image": os.path.basename(a.out), "label": a.label, "bytes": size,
        "fingerprint": fp, "kernel_release": release, "loader": f"systemd-boot {sdboot_ver}",
        "menu_timeout": a.menu_timeout, "epoch": a.epoch, "vendor_cmdline": vendor_cmdline,
        "vendor_bootconfig": vendor_bc, "vendor_ramdisk_fragments": [os.path.basename(x) for x in frags],
        "vbmeta_digest": digest, "vbmeta_size": len(vb_struct), "super": super_info, "entries": entries,
        "esp_partuuid": esp_uuid, "partitions": parts, "verified_sha256": verified,
        "firmware": {"files": len(fw_files), "licence_files": fw_lic, "without_licence": fw_unmatched},
        "esp_files": sorted(os.path.relpath(os.path.join(r, f), e) for r, _, fs in os.walk(e) for f in fs),
        "live_init_sha256": sha256(a.live_init),
    }
    json.dump(meta, open(a.out + ".json", "w"), indent=1)
    proto.run(["sgdisk", "--print", a.out])
    if fw_unmatched:
        print(f"WARNING: {len(fw_unmatched)} firmware file(s) without a known licence: {fw_unmatched[:5]}")
    print(a.out)


if __name__ == "__main__":
    main()
