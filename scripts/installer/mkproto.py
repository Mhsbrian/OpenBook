#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build an OpenBook boot-chain prototype disk image (ANAL-189): a GPT image with an ESP holding one EFI loader,
A/B Android boot partitions, super, misc, metadata and an empty userdata, as a USB stick would carry it.

Runs inside the openbook-installer container (scripts/installer/inst-docker.sh). Inputs are read-only: a snapshot of
an AOSP PRODUCT_OUT plus a kernel bzImage (scripts/installer/snapshot-inputs.sh), the AOSP host tools (avbtool,
mkbootimg, unpack_bootimg, simg2img) and the AOSP AVB test key. Nothing is written outside --work.

Steps
  android  boot.img = our bzImage (mkbootimg v4), AVB hash footer signed with the AOSP test key (boot is a chained
           partition). vendor_boot = the product's vendor ramdisk without its 6.12 modules, plus an empty module
           dir for our kernel release and the probe; console and rdinit=/openbook-probe on the vendor cmdline; the
           product's static androidboot.* in the vendor bootconfig. vbmeta re-made with the product's chain layout;
           its digest and size are computed the way libavb reports them.
  esp      per loader: grub (standalone GRUB, grubenv slot, PARTUUID probed at run time), sdboot (systemd-boot with
           Boot Loader Spec type #1 entries, one initrd line per ramdisk, bootconfig last), uki (ukify UKI booted
           straight from firmware), gbl (Google's GBL EFI app, which reads the Android partitions itself). Loaders
           that take files from the ESP get a per-slot bootconfig blob: vendor bootconfig + runtime facts (slot,
           AVB state, vbmeta digest, boot_part_uuid).
  disk     GPT with deterministic PARTUUIDs; partitions copied in sparsely and verified by sha256.

usage: mkproto.py --inputs DIR --work DIR --loader {grub,sdboot,uki,gbl} [--slot a|b] [--bad-digest] [--halt]
                  [--gbl-efi FILE] [--vendor-boot-part-uuid] [--size-gib N] [--label L] [--out IMG]
       mkproto.py --decoy OUT.img     a small GPT with the same partition names and nothing in them (an "internal
                                      disk" that must NOT be picked); random PARTUUIDs
"""
import argparse
import hashlib
import json
import os
import shlex
import shutil
import struct
import subprocess
import sys
import uuid

# Host data dir, shared with the AOSP and kernel lanes (still ~/anybook until the repo-wide rename).
A = os.environ.get("OPENBOOK_HOME", os.environ.get("ANYBOOK_HOME", os.path.expanduser("~/anybook")))
HOST = f"{A}/aosp/src/out/host/linux-x86/bin"
TESTKEY = f"{A}/aosp/src/external/avb/test/data/testkey_rsa4096.pem"
HERE = os.path.dirname(os.path.abspath(__file__))
MiB = 1 << 20

# Prototype layout. Sizes follow the Cuttlefish pc product (boot/vendor_boot 64 MiB, init_boot 8 MiB, super 8 GiB).
LAYOUT = [  # name, MiB (None = rest of disk), GPT type code (sgdisk)
    ("EFI", 256, "ef00"),
    ("misc", 1, "8300"),
    ("boot_a", 64, "8300"), ("boot_b", 64, "8300"),
    ("init_boot_a", 8, "8300"), ("init_boot_b", 8, "8300"),
    ("vendor_boot_a", 64, "8300"), ("vendor_boot_b", 64, "8300"),
    ("vbmeta_a", 1, "8300"), ("vbmeta_b", 1, "8300"),
    ("vbmeta_system_a", 1, "8300"), ("vbmeta_system_b", 1, "8300"),
    ("vbmeta_system_dlkm_a", 1, "8300"), ("vbmeta_system_dlkm_b", 1, "8300"),
    ("vbmeta_vendor_dlkm_a", 1, "8300"), ("vbmeta_vendor_dlkm_b", 1, "8300"),
    ("metadata", 64, "8300"),
    ("super", 8192, "8300"),
    ("userdata", None, "8300"),
]
# The prototype boots the Cuttlefish pc product in plain QEMU, without crosvm's host-side services. cvd normally
# picks one of each duplicate vendor APEX through bootconfig (assemble_cvd/bootconfig_args.cpp); pick the in-guest
# software ones. A real OpenBook product has one APEX per HAL and needs none of this.
CF_PRODUCT_PARAMS = {
    "androidboot.vendor.apex.com.android.hardware.keymint": "com.android.hardware.keymint.rust_nonsecure",
    "androidboot.vendor.apex.com.android.hardware.gatekeeper": "com.android.hardware.gatekeeper.nonsecure",
    "androidboot.vendor.apex.com.android.hardware.secure_element": "com.android.hardware.secure_element",
    "androidboot.vendor.apex.com.android.hardware.strongbox": "none",
    "androidboot.vendor.apex.com.android.hardware.graphics.composer": "com.android.hardware.graphics.composer.ranchu",
    "androidboot.vendor.apex.com.google.emulated.camera.provider.hal": "com.google.emulated.camera.provider.hal",
    "androidboot.wifi_impl": "virt_wifi",
    "androidboot.hypervisor.vm.supported": "0",
    "androidboot.hypervisor.protected_vm.supported": "0",
    "androidboot.fstab_suffix": "cf.f2fs.hctr2",
    "androidboot.console": "ttyS0",
    "androidboot.serialconsole": "1",
}
NS = uuid.UUID("5b0f9a52-2d1e-4b7e-9a3c-6f70656e626b")  # namespace for deterministic PARTUUIDs


def run(cmd, **kw):
    print("+", " ".join(shlex.quote(str(c)) for c in cmd), flush=True)
    return subprocess.run([str(c) for c in cmd], check=True, **kw)


def out(cmd):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True).stdout


def tool(name):
    return f"{HOST}/{name}"


# ---------------------------------------------------------------- cpio (newc) writer, no root needed
def newc_entries(blob):
    """Split a newc archive into (name, raw entry bytes) pairs, trailer excluded."""
    out, i = [], 0
    while i + 110 <= len(blob):
        if blob[i:i + 6] != b"070701":
            raise ValueError(f"bad cpio magic at {i}")
        f = [int(blob[i + 6 + 8 * k: i + 14 + 8 * k], 16) for k in range(13)]
        filesize, namesize = f[6], f[11]
        name = blob[i + 110: i + 110 + namesize - 1].decode()
        end = i + 110 + namesize
        end += -end % 4
        end += filesize
        end += -end % 4
        if name == "TRAILER!!!":
            break
        out.append((name, blob[i:end]))
        i = end
    return out


def tree_entries(root, prefix):
    """newc entries for a directory tree, placed under prefix (no leading slash). Parents of prefix included."""
    out, parts = [], prefix.split("/")
    for i in range(1, len(parts) + 1):
        out.append(("/".join(parts[:i]), 0o40755, None))
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        rel = os.path.relpath(dirpath, root)
        base = prefix if rel == "." else f"{prefix}/{rel}"
        if rel != ".":
            out.append((base, 0o40755, None))
        for f in sorted(filenames):
            full = os.path.join(dirpath, f)
            if os.path.islink(full):
                out.append((f"{base}/{f}", 0o120777, os.readlink(full).encode()))
            else:
                mode = 0o100755 if os.access(full, os.X_OK) else 0o100644
                out.append((f"{base}/{f}", mode, open(full, "rb").read()))
    return out


def newc(entries, ino=0x7F000000, trailer=True):
    """entries: list of (path, mode, data or None). Directories have data None."""
    buf = bytearray()
    for path, mode, data in entries + ([("TRAILER!!!", 0, b"")] if trailer else []):
        data = data or b""
        name = path.encode() + b"\0"
        nlink = 2 if (mode & 0o170000) == 0o040000 else 1
        hdr = "070701" + "".join(f"{v:08x}" for v in (
            ino, mode, 0, 0, nlink, 0, len(data), 0, 0, 0, 0, len(name), 0))
        buf += hdr.encode() + name
        buf += b"\0" * (-len(buf) % 4)
        buf += data
        buf += b"\0" * (-len(buf) % 4)
        ino += 1
    return bytes(buf)


# ---------------------------------------------------------------- AVB helpers
def vbmeta_struct_size(blob, off=0):
    if blob[off:off + 4] != b"AVB0":
        raise ValueError("not a vbmeta struct")
    auth, aux = struct.unpack_from(">QQ", blob, off + 12)
    return 256 + auth + aux


def vbmeta_from_image(path):
    """Return the vbmeta struct bytes of a vbmeta image or of a partition image with an AVB footer."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] == b"AVB0":
        return data[:vbmeta_struct_size(data)]
    footer = data[-64:]
    if footer[:4] != b"AVBf":
        raise ValueError(f"{path}: no vbmeta and no AVB footer")
    vb_off, vb_size = struct.unpack_from(">QQ", footer, 20)  # AvbFooter: magic, major, minor, orig size, offset, size
    return data[vb_off:vb_off + vb_size]


def avb_info(path):
    return out([tool("avbtool"), "info_image", "--image", path])


# ---------------------------------------------------------------- android stage
def build_android(inp, w, args):
    d = f"{w}/android"
    stamp = f"{d}/.done"
    if os.path.exists(stamp):
        return json.load(open(f"{d}/params.json"))
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(f"{d}/img")
    P = f"{inp}/product"
    for n in ("init_boot", "vbmeta_system", "vbmeta_system_dlkm", "vbmeta_vendor_dlkm"):
        shutil.copy(f"{P}/{n}.img", f"{d}/img/{n}.img")

    # Unpack the product's boot images.
    for n in ("boot", "init_boot", "vendor_boot"):
        run([tool("unpack_bootimg"), "--boot_img", f"{P}/{n}.img", "--out", f"{d}/unpack/{n}"], stdout=subprocess.DEVNULL)
    vargs = shlex.split(out([tool("unpack_bootimg"), "--boot_img", f"{P}/vendor_boot.img", "--out",
                             f"{d}/unpack/vendor_boot", "--format=mkbootimg"]))
    release = open(f"{inp}/kernel/linux_banner.txt").read().split()[2]

    # Vendor ramdisk: the product's, minus its kernel modules (built for the product's 6.12 kernel; first-stage
    # init loads /lib/modules/modules.load whenever the release-specific dir loads nothing, and a vermagic error
    # there is fatal), plus an empty module dir for our release and the probe. A real image puts our own
    # first-stage modules here instead.
    raw = subprocess.run(["lz4", "-d", "-c", f"{d}/unpack/vendor_boot/vendor_ramdisk00"], capture_output=True,
                         check=True).stdout
    kept, dropped = [], []
    for name, entry in newc_entries(raw):
        (dropped if name.startswith("lib/modules/") else kept).append((name, entry))
    md = f"lib/modules/{release}"
    extra = [(md, 0o40755, None)] + [(f"{md}/{f}", 0o100644, b"") for f in
                                      ("modules.load", "modules.dep", "modules.alias", "modules.softdep",
                                       "modules.options")] + \
            [("openbook-probe", 0o100755, open(args.probe, "rb").read())]
    cpio = b"".join(e for _, e in kept) + newc(extra)
    open(f"{d}/vendor_ramdisk.dropped.txt", "w").write("".join(n + "\n" for n, _ in dropped))
    # lz4 legacy like the product's ramdisks. Between two lz4 streams the kernel's unlz4 expects the next magic
    # number right away (lib/decompress_unlz4.c); see copy_padded() for loaders that pad.
    vr = f"{d}/vendor_ramdisk.img"
    open(vr, "wb").write(subprocess.run(["lz4", "-l", "-12", "-c"], input=cpio, capture_output=True,
                                        check=True).stdout)

    # Re-make vendor_boot. Static product config lives here, so every loader (GBL included, which takes its
    # cmdline only from the boot images) gets it: console and the probe on the vendor cmdline, and the product's
    # androidboot.* in the vendor bootconfig section. Loaders add only runtime facts (slot, AVB, boot disk).
    from importlib.machinery import SourceFileLoader
    bc = SourceFileLoader("bootconfig", f"{HERE}/bootconfig.py").load_module()
    i = vargs.index("--vendor_cmdline")
    vendor_cmdline = vargs[i + 1] + " console=ttyS0,115200 loglevel=7 rdinit=/openbook-probe"
    vargs[i + 1] = vendor_cmdline
    vbc = bc.parse_text(open(f"{d}/unpack/vendor_boot/bootconfig").read())
    vbc.update(CF_PRODUCT_PARAMS)
    if args.vendor_boot_part_uuid:  # workaround for loaders that pass no boot disk (GBL as of 2026-10-16)
        vbc["androidboot.boot_part_uuid"] = partuuid(args.label, "EFI")
    vbc_text = bc.render(vbc).decode()
    open(f"{d}/vendor_bootconfig.txt", "w").write(vbc_text)
    vargs[vargs.index("--vendor_bootconfig") + 1] = f"{d}/vendor_bootconfig.txt"
    vargs = [vr if a.endswith("vendor_ramdisk00") else a for a in vargs]
    run([tool("mkbootimg")] + vargs + ["--vendor_boot", f"{d}/img/vendor_boot.img"])
    run([tool("avbtool"), "add_hash_footer", "--image", f"{d}/img/vendor_boot.img", "--partition_name",
         "vendor_boot", "--partition_size", 64 * MiB])

    # boot.img: our kernel, signed with the test key like the product's chained boot partition.
    info = avb_info(f"{P}/boot.img")
    rb = next(l.split()[-1] for l in info.splitlines() if l.strip().startswith("Rollback Index:"))
    run([tool("mkbootimg"), "--header_version", 4, "--kernel", f"{inp}/kernel/bzImage", "--os_version", "17.0.0",
         "--os_patch_level", "2026-06", "--output", f"{d}/img/boot.img"])
    run([tool("avbtool"), "add_hash_footer", "--image", f"{d}/img/boot.img", "--partition_name", "boot",
         "--partition_size", 64 * MiB, "--algorithm", "SHA256_RSA4096", "--key", TESTKEY, "--rollback_index", rb,
         "--prop", "com.android.build.boot.os_version:17"])

    # vbmeta: same chain descriptors and props as the product's, new vendor_boot hash descriptor.
    pub = f"{d}/testkey.avbpubkey"
    run([tool("avbtool"), "extract_public_key", "--key", TESTKEY, "--output", pub])
    info = avb_info(f"{P}/vbmeta.img")
    lines = info.splitlines()
    vb_rb = next(l.split()[-1] for l in lines if l.startswith("Rollback Index:"))
    chains, props = [], []
    for j, l in enumerate(lines):
        if "Chain Partition descriptor:" in l:
            name = lines[j + 1].split()[-1]
            loc = lines[j + 2].split()[-1]
            chains += ["--chain_partition", f"{name}:{loc}:{pub}"]
        if l.strip().startswith("Prop:"):
            k, _, v = l.strip()[5:].partition(" -> ")
            props += ["--prop", f"{k.strip()}:{v.strip().strip(chr(39))}"]
    run([tool("avbtool"), "make_vbmeta_image", "--output", f"{d}/img/vbmeta.img", "--algorithm", "SHA256_RSA4096",
         "--key", TESTKEY, "--rollback_index", vb_rb, "--padding_size", 4096] + chains + props +
        sum((["--include_descriptors_from_image", f] for f in
             (f"{d}/img/vendor_boot.img", f"{P}/odm.img", f"{P}/odm_dlkm.img", f"{P}/vendor.img")), []))

    # Digest the way libavb does: top-level vbmeta, then each chained partition's vbmeta, in descriptor order.
    digest = out([tool("avbtool"), "calculate_vbmeta_digest", "--image", f"{d}/img/vbmeta.img",
                  "--hash_algorithm", "sha256"]).strip()
    order = ["vbmeta"] + [c.split(":")[0] for c in chains[1::2]]
    structs = [vbmeta_from_image(f"{d}/img/{n}.img") for n in order]
    if hashlib.sha256(b"".join(structs)).hexdigest() != digest:
        sys.exit("vbmeta digest cross-check failed")
    size = sum(len(s) for s in structs)

    run([tool("simg2img"), f"{P}/super.img", f"{d}/img/super.img"])

    params = {
        "kernel_release": release,
        "vendor_cmdline": vendor_cmdline,
        "vendor_bootconfig": vbc_text,
        "vbmeta_digest": digest,
        "vbmeta_size": size,
        "vbmeta_order": order,
        "files": {n: hashlib.sha256(open(f"{d}/img/{n}.img", "rb").read()).hexdigest()
                  for n in ("boot", "init_boot", "vendor_boot", "vbmeta", "vbmeta_system", "vbmeta_system_dlkm",
                            "vbmeta_vendor_dlkm")},
    }
    shutil.copy(f"{inp}/kernel/bzImage", f"{d}/kernel")
    shutil.copy(f"{d}/unpack/init_boot/ramdisk", f"{d}/ramdisk.img")
    json.dump(params, open(f"{d}/params.json", "w"), indent=1)
    open(stamp, "w").close()
    return params


# ---------------------------------------------------------------- GPT helpers
def partuuid(label, name):
    return str(uuid.uuid5(NS, f"{label}/{name}"))


def layout(size_bytes, label, rand=False, scale=None):
    parts, lba = [], 2048
    total_lba = size_bytes // 512
    for name, mib, typ in (scale or LAYOUT):
        n = (total_lba - 2048 - 34 - lba) if mib is None else mib * MiB // 512
        n -= n % 2048 if mib is None else 0
        parts.append({"name": name, "start": lba, "sectors": n, "type": typ,
                      "uuid": str(uuid.uuid4()) if rand else partuuid(label, name)})
        lba += n
    return parts


def make_gpt(img, size_bytes, parts, disk_guid):
    with open(img, "wb") as f:
        f.truncate(size_bytes)
    cmd = ["sgdisk", "--clear", "--disk-guid", disk_guid]
    for i, p in enumerate(parts, 1):
        cmd += ["-n", f"{i}:{p['start']}:{p['start'] + p['sectors'] - 1}", "-t", f"{i}:{p['type']}",
                "-c", f"{i}:{p['name']}", "-u", f"{i}:{p['uuid']}"]
    run(cmd + [img], stdout=subprocess.DEVNULL)


def copy_into(img, src, part):
    """Copy src into the partition, skipping holes so the image stays sparse."""
    size = os.path.getsize(src)
    if size > part["sectors"] * 512:
        sys.exit(f"{src} ({size}) does not fit {part['name']}")
    base = part["start"] * 512
    src_fd, dst_fd = os.open(src, os.O_RDONLY), os.open(img, os.O_WRONLY)
    try:
        pos = 0
        while pos < size:
            try:
                pos = os.lseek(src_fd, pos, os.SEEK_DATA)
            except OSError:  # ENXIO: only a hole is left
                break
            end = os.lseek(src_fd, pos, os.SEEK_HOLE)
            while pos < end:  # pread/pwrite only: no file offsets shared with the SEEK_DATA/SEEK_HOLE probes
                chunk = os.pread(src_fd, min(end - pos, 16 * MiB), pos)
                os.pwrite(dst_fd, chunk, base + pos)
                pos += len(chunk)
    finally:
        os.close(src_fd)
        os.close(dst_fd)


def sha256_region(path, off, n):
    m = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY)
    try:
        done = 0
        while done < n:
            b = os.pread(fd, min(n - done, 64 * MiB), off + done)
            if not b:
                break
            m.update(b)
            done += len(b)
    finally:
        os.close(fd)
    return m.hexdigest()


def verify_copy(img, src, part):
    n = os.path.getsize(src)
    a, b = sha256_region(src, 0, n), sha256_region(img, part["start"] * 512, n)
    if a != b:
        sys.exit(f"verify failed: {src} vs {part['name']}")
    return a


# ---------------------------------------------------------------- ESP builders
def bootconfig_params(params, loader, slot, parts, bad_digest, static_part_uuid):
    from importlib.machinery import SourceFileLoader
    bc = SourceFileLoader("bootconfig", f"{HERE}/bootconfig.py").load_module()
    p = bc.parse_text(params["vendor_bootconfig"])  # what an Android loader takes from vendor_boot
    digest = params["vbmeta_digest"]
    if bad_digest:
        digest = "0" * 64
    p.update({
        "androidboot.slot_suffix": f"_{slot}",
        "androidboot.force_normal_boot": "1",
        "androidboot.verifiedbootstate": "orange",
        "androidboot.vbmeta.device_state": "unlocked",
        "androidboot.vbmeta.avb_version": "1.3",
        "androidboot.vbmeta.hash_alg": "sha256",
        "androidboot.vbmeta.size": str(params["vbmeta_size"]),
        "androidboot.vbmeta.digest": digest,
        "androidboot.vbmeta.invalidate_on_error": "yes",
        "androidboot.veritymode": "enforcing",
        "androidboot.serialno": "OPENBOOKPROTO01",
        "androidboot.openbook.loader": loader,
    })
    if static_part_uuid:
        p["androidboot.boot_part_uuid"] = next(x["uuid"] for x in parts if x["name"] == "EFI")
    return bc, p


def copy_padded(src, dst):
    """Copy an lz4 ramdisk for a loader that starts every initrd on a 4-byte boundary (GRUB's grub_initrd_init).
    1-3 zero bytes between two lz4 streams make the kernel's unlz4 read a bogus chunk length, so pad to a multiple
    of 4 with at least 4 zero bytes (a zero chunk length ends the stream cleanly; initramfs skips the rest)."""
    data = open(src, "rb").read()
    pad = -len(data) % 4
    open(dst, "wb").write(data + b"\0" * (pad + 4 if pad else 0))


def kernel_cmdline(params, halt):
    return params["vendor_cmdline"] + (" openbook.probe=halt" if halt else "")


def esp_files(w, params, loader, parts, args):
    """Populate {w}/esp-<loader>/ and return it."""
    e = f"{w}/esp-{loader}"
    shutil.rmtree(e, ignore_errors=True)
    os.makedirs(f"{e}/EFI/BOOT")
    d = f"{w}/android"
    cmd = kernel_cmdline(params, args.halt)
    if loader in ("grub", "sdboot", "uki"):
        for slot in "ab":
            sd = f"{e}/openbook/{slot}"
            os.makedirs(sd)
            shutil.copy(f"{d}/kernel", f"{sd}/kernel")
            copy_padded(f"{d}/vendor_ramdisk.img", f"{sd}/vendor_ramdisk.img")
            copy_padded(f"{d}/ramdisk.img", f"{sd}/ramdisk.img")
            # GRUB passes boot_part_uuid on the cmdline (probed at run time); the others bake it in.
            bc, p = bootconfig_params(params, loader, slot, parts, args.bad_digest, loader != "grub")
            with open(f"{sd}/bootconfig.img", "wb") as f:
                f.write(bc.blob(p))
    if loader == "grub":
        emb = f"{w}/grub-embedded.cfg"
        open(emb, "w").write(
            "# Find the partition GRUB was loaded from, then read its config from there (never \"search\":\n"
            "# a second disk with OpenBook on it would match too).\n"
            "regexp --set=1:espdev '^(\\([^)]*\\))' \"$cmdpath\"\n"
            "set root=$espdev\n"
            "configfile ($root)/openbook/grub.cfg\n")
        open(f"{e}/openbook/grub.cfg", "w").write(f"""\
# OpenBook prototype GRUB config (ANAL-189). Slot comes from grubenv; androidboot.boot_part_uuid is the PARTUUID of
# this ESP, probed at boot. Static androidboot.* params are in the per-slot bootconfig file (last initrd).
set timeout=3
set default=0
set slot=a
load_env --file ($root)/openbook/grubenv slot
probe --set=esp_partuuid --part-uuid ($root)
echo "OpenBook GRUB: root=$root slot=$slot esp_partuuid=$esp_partuuid"
menuentry "OpenBook (slot $slot)" {{
    echo "loading kernel, vendor ramdisk, generic ramdisk, bootconfig from ($root)/openbook/$slot"
    linux ($root)/openbook/$slot/kernel {cmd} androidboot.boot_part_uuid=$esp_partuuid
    initrd ($root)/openbook/$slot/vendor_ramdisk.img ($root)/openbook/$slot/ramdisk.img ($root)/openbook/$slot/bootconfig.img
}}
""")
        run(["grub-editenv", f"{e}/openbook/grubenv", "create"])
        run(["grub-editenv", f"{e}/openbook/grubenv", "set", f"slot={args.slot}"])
        run(["grub-mkstandalone", "-O", "x86_64-efi", "-o", f"{e}/EFI/BOOT/BOOTX64.EFI",
             "--modules=part_gpt fat", "--locales=", "--fonts=", "--themes=",
             "--install-modules=linux normal part_gpt fat probe regexp loadenv configfile echo test efi_gop "
             "all_video sleep reboot halt",
             f"boot/grub/grub.cfg={emb}"])
    elif loader == "sdboot" and args.hwcheck:
        # USB test stick for a real laptop: "OpenBook hardware check" (default) loads our modules and firmware from
        # an extra initrd, writes a report to this stick's ESP and powers off (probe-init.c, report mode);
        # "OpenBook preview" is the Android boot the VM tests use (console on the serial port, no display).
        shutil.copy("/usr/lib/systemd/boot/efi/systemd-bootx64.efi", f"{e}/EFI/BOOT/BOOTX64.EFI")
        os.makedirs(f"{e}/loader/entries")
        os.makedirs(f"{e}/openbook/check")
        os.makedirs(f"{e}/openbook/logs")
        cpio = newc(tree_entries(args.check_modules, f"openbook-check/modules/{params['kernel_release']}") +
                    tree_entries(args.check_firmware, "lib/firmware"))
        lz = subprocess.run(["lz4", "-l", "-9", "-c"], input=cpio, capture_output=True, check=True).stdout
        open(f"{w}/hwcheck.img", "wb").write(lz)
        copy_padded(f"{w}/hwcheck.img", f"{e}/openbook/check/hwcheck.img")
        open(f"{e}/loader/loader.conf", "w").write(
            "timeout 8\ndefault openbook-1-hwcheck.conf\nconsole-mode keep\neditor no\n")
        common = (f"linux /openbook/a/kernel\ninitrd /openbook/a/vendor_ramdisk.img\n"
                  f"initrd /openbook/a/ramdisk.img\n")
        open(f"{e}/loader/entries/openbook-1-hwcheck.conf", "w").write(
            f"title OpenBook hardware check\nsort-key openbook-1\n{common}"
            f"initrd /openbook/check/hwcheck.img\ninitrd /openbook/a/bootconfig.img\n"
            f"options {cmd} openbook.probe=report\n")
        open(f"{e}/loader/entries/openbook-2-vm.conf", "w").write(
            f"title OpenBook preview (virtual machines only)\nsort-key openbook-2\n{common}"
            f"initrd /openbook/a/bootconfig.img\noptions {cmd}\n")
        open(f"{e}/openbook/README.txt", "w").write(
            "OpenBook test stick (ANAL-189). Boot it with Secure Boot off.\n"
            "- 'OpenBook hardware check' (default): records what the laptop's hardware looks like to the OpenBook\n"
            "  kernel, loads its drivers, writes openbook/logs/hwcheck-NNN.txt (+ -dmesg.txt) on THIS stick and\n"
            "  powers off. It never writes to the laptop's own disks.\n"
            "- 'OpenBook preview (virtual machines only)': Android 17 with the console on the serial port.\n"
            "  On a laptop it shows nothing (no graphics in this preview).\n")
    elif loader == "sdboot":
        shutil.copy("/usr/lib/systemd/boot/efi/systemd-bootx64.efi", f"{e}/EFI/BOOT/BOOTX64.EFI")
        os.makedirs(f"{e}/loader/entries")
        # Product UX: no menu unless a key is held at power-on ("menu-hidden"), so the firmware logo stays on
        # screen until Android's boot animation; "--menu" shows it for 3 s (used for the menu screenshot).
        timeout = "3" if args.menu else "menu-hidden"
        open(f"{e}/loader/loader.conf", "w").write(
            f"timeout {timeout}\ndefault openbook-{args.slot}*\nconsole-mode keep\neditor no\n")
        for slot in "ab":
            # "+3" = boot counting: systemd-boot renames the file on every try (A/B "tries remaining").
            open(f"{e}/loader/entries/openbook-{slot}+3.conf", "w").write(
                f"title OpenBook\nsort-key openbook\nversion 17 \u00b7 slot {slot.upper()}\n"
                f"linux /openbook/{slot}/kernel\ninitrd /openbook/{slot}/vendor_ramdisk.img\n"
                f"initrd /openbook/{slot}/ramdisk.img\ninitrd /openbook/{slot}/bootconfig.img\noptions {cmd}\n")
    elif loader == "uki":
        slot = args.slot
        sd = f"{e}/openbook/{slot}"
        combined = f"{w}/uki-initrd-{slot}.img"
        with open(combined, "wb") as o:
            for n in ("vendor_ramdisk.img", "ramdisk.img", "bootconfig.img"):
                o.write(open(f"{sd}/{n}", "rb").read())
        run(["ukify", "build", "--linux", f"{d}/kernel", "--initrd", combined, "--cmdline", cmd,
             "--uname", params["kernel_release"], "--os-release", "NAME=OpenBook\nID=openbook\n",
             "--output", f"{e}/EFI/BOOT/BOOTX64.EFI"])
        shutil.rmtree(f"{e}/openbook")
    elif loader == "gbl":
        shutil.copy(args.gbl_efi, f"{e}/EFI/BOOT/BOOTX64.EFI")
    return e


def make_fat(src, img, mib):
    if os.path.exists(img):
        os.remove(img)
    run(["mkfs.vfat", "-F", "32", "-n", "OPENBOOK", "-C", img, str(mib * 1024)], stdout=subprocess.DEVNULL)
    items = [os.path.join(src, x) for x in os.listdir(src)]
    run(["mcopy", "-s", "-i", img] + items + ["::/"])


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs")
    ap.add_argument("--work")
    ap.add_argument("--loader", choices=["grub", "sdboot", "uki", "gbl"])
    ap.add_argument("--slot", default="a", choices=["a", "b"])
    ap.add_argument("--bad-digest", action="store_true")
    ap.add_argument("--halt", action="store_true", help="probe only: power off before Android's init")
    ap.add_argument("--menu", action="store_true", help="sdboot: show the boot menu for 3 s instead of hiding it")
    ap.add_argument("--hwcheck", action="store_true",
                    help="sdboot: test stick for a real laptop (hardware-check entry + VM preview entry)")
    ap.add_argument("--check-modules", default=f"{A}/kernel/cf/modset-anybook/root/lib/modules/"
                    "6.18.21-android17-5-g44a90255c95f",
                    help="module tree (modules.dep, modules.load) for the hardware check; ANAL-172's module set")
    ap.add_argument("--check-firmware", default=f"{A}/kernel/firmware/anybook-amd",
                    help="linux-firmware subset (ANAL-171) for the hardware check, uncompressed")
    ap.add_argument("--vendor-boot-part-uuid", action="store_true",
                    help="bake androidboot.boot_part_uuid (this image's ESP) into vendor_boot's bootconfig")
    ap.add_argument("--gbl-efi", default=f"{A}/installer/dl/gbl-16633196/gbl_x86_64_dev.efi")
    ap.add_argument("--probe", default=f"{A}/installer/build/openbook-probe")
    ap.add_argument("--size-gib", type=int, default=12)
    ap.add_argument("--label", default="openbook-proto")
    ap.add_argument("--out")
    ap.add_argument("--decoy")
    args = ap.parse_args()
    if args.hwcheck and args.loader != "sdboot":
        sys.exit("--hwcheck needs --loader sdboot")
    for target in (args.out, args.decoy):  # image files only: never a block device
        if target and os.path.exists(target) and not os.path.isfile(target):
            sys.exit(f"refusing {target}: not a regular file")

    if args.decoy:
        small = [(n, (1 if m and m <= 64 else (64 if m else None)), t) for n, m, t in LAYOUT]
        parts = layout(512 * MiB, "decoy", rand=True, scale=small)
        make_gpt(args.decoy, 512 * MiB, parts, str(uuid.uuid4()))
        json.dump(parts, open(args.decoy + ".layout.json", "w"), indent=1)
        print(args.decoy)
        return

    w = args.work
    os.makedirs(w, exist_ok=True)
    params = build_android(args.inputs, w, args)
    size = args.size_gib << 30
    parts = layout(size, args.label)
    e = esp_files(w, params, args.loader, parts, args)
    esp_img = f"{w}/esp-{args.loader}.fat"
    make_fat(e, esp_img, 256)
    img = args.out or f"{w}/{args.loader}.img"
    make_gpt(img, size, parts, partuuid(args.label, "disk"))
    byname = {p["name"]: p for p in parts}
    d = f"{w}/android/img"
    copies = [(esp_img, "EFI"), (f"{d}/super.img", "super")] + [
        (f"{d}/{n}.img", f"{n}_{slot}") for slot in "ab" for n in
        ("boot", "init_boot", "vendor_boot", "vbmeta", "vbmeta_system", "vbmeta_system_dlkm", "vbmeta_vendor_dlkm")]
    verified = {}
    for src, name in copies:
        copy_into(img, src, byname[name])
        verified[name] = verify_copy(img, src, byname[name])
    meta = {"loader": args.loader, "slot": args.slot, "bad_digest": args.bad_digest, "halt": args.halt,
            "image": img, "size": size, "partitions": parts, "android": params, "verified_sha256": verified,
            "esp_files": sorted(os.path.relpath(os.path.join(r, f), e) for r, _, fs in os.walk(e) for f in fs)}
    if args.loader == "gbl":
        meta["gbl_efi_sha256"] = hashlib.sha256(open(args.gbl_efi, "rb").read()).hexdigest()
    json.dump(meta, open(img + ".json", "w"), indent=1)
    run(["sgdisk", "--print", img])
    print(img)


if __name__ == "__main__":
    main()
