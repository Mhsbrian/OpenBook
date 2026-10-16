#!/usr/bin/env python3
"""Boot the G14 kernel images under QEMU/KVM with Android's own first-stage init, from a GPT disk attached as
USB mass storage and as NVMe, and check first-stage mount and the vendor_dlkm module load (ANAL-198).

usage: kernel-g14-qemu.py --dist DIST --product PRODUCT_OUT --tools DIR --key PEM --fstab FILE --work W --out OUT
                          [--runs NAME,...] [--force] [--timeout S]

  --dist     G14 dist (scripts/kernel-g14-package.sh): bzImage, boot.img, system_dlkm.flatten.erofs.img,
             {bm,vm}/vendor_boot.img and {bm,vm}/vendor_dlkm.img, all from one Kleaf build
  --product  an existing Cuttlefish PRODUCT_OUT, read only: init_boot.img (Android's generic ramdisk with
             first-stage init) and the system, system_ext, product, vendor, odm and odm_dlkm images. Nothing in
             the AOSP tree is built or written.
  --tools    Kleaf's host tools (prebuilts/kernel-build-tools/linux_musl-x86/bin): unpack_bootimg, avbtool,
             lpmake, mke2fs
  --key      an AVB test key (external/avb/test/data/testkey_rsa4096.pem) for the test vbmeta
  --fstab    the first-stage test fstab (kernel/devices/anybook/g14/test/fstab.qemu)
  --work     scratch space, about 9 GB of sparse disk images; reused across reruns
  --out      evidence: per run NAME.serial.log, NAME.json, NAME.md, plus results.json and summary.md

What plays the bootloader: QEMU loads our bzImage directly and gets an initrd made the way a boot image v4
bootloader assembles one: the vendor ramdisk fragments of our vendor_boot.img, then a small test fragment with
the fstab, then the generic ramdisk from init_boot.img, then bootconfig (vendor_boot's, plus the androidboot.*
values a bootloader adds: slot, verified-boot state, vbmeta digest and the boot device). The kernel command
line is the GKI built-in one plus vendor_boot's plus a serial console.

The disk is GPT, laid out like Googlebook's: misc, boot_a (our boot.img), init_boot_a, vendor_boot_a (ours),
vbmeta_a, metadata (ext4), super and userdata. super holds the product's logical partitions plus our
vendor_dlkm and system_dlkm. One vbmeta, signed with the test key, carries every hashtree descriptor, so
first-stage init sets up dm-verity for all of them. A second copy of the disk gets new partition GUIDs, so two
disks with the same partition names can be attached at once.

Runs (default: all):
  usb       bare-metal images; disk on usb-storage (bulk-only) behind qemu-xhci behind a PCIe root port;
            androidboot.boot_devices names the xHCI's root port, as on the GA403WR (00:08.x)
  uas       the same disk on usb-uas
  nvme      bare-metal images; disk on NVMe behind a PCIe root port; boot_devices names that root port
  both-uuid both disks attached, NVMe and USB, identical partition names; androidboot.boot_part_uuid names
            boot_a on the USB disk, so first-stage init must take every partition from the USB disk (strict mode)
  vm        VM images (vm/vendor_boot.img, vm/vendor_dlkm.img) on NVMe: asus-nb-wmi blocklisted, so dlkm_loader
            completes and sets vendor.dlkm.modules.ready

Evidence comes from the serial console: the kernel log, and a root shell (the userdebug console service, then
su) that lists /dev/block/by-name, mounts, dm devices and /proc/modules once Cuttlefish's dlkm_loader has
finished. SELinux stays enforcing. A run passes when the logical partitions are mounted with dm-verity from the expected
disk, every by-name link points at that disk, every module in vendor_dlkm's modules.load is live (bare metal:
except asus-nb-wmi, whose init returns -ENODEV without the ASUS WMI GUID) and the log has no unknown-symbol,
CRC, signature or format error. Runs in the anybook-qemu image (scripts/kernel-g14-qemu.sh).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
import uuid
import zlib

MiB = 1 << 20
SECTOR = 512
LINUX_DATA = "0fc63daf-8483-4772-8e79-3d69d8477de4"
VBMETA_TYPE = "88434509-d9d1-487d-b82c-15ef964cbd4b"  # what ruby's vbmeta_a uses
LOGICAL = ["system", "system_ext", "product", "vendor", "odm", "odm_dlkm", "vendor_dlkm", "system_dlkm"]
FSTAB_SUFFIX = "cf.f2fs.hctr2"
USB_RP, NVME_RP = "08.0", "02.0"  # PCIe root ports, devfn as in pci0000:00/0000:00:XX.X

# The Cuttlefish userspace reads these from bootconfig (taken from ANAL-172's crosvm boot, cmdline-bootconfig.txt);
# the device-specific ones (vsock ports, CIDs, Wi-Fi) are left out because nothing here provides them.
CF_BOOTCONFIG = {
    "androidboot.hardware": "cutf_cvm",
    "androidboot.hardware.hwcomposer": "ranchu",
    "androidboot.hardware.hwcomposer.display_finder_mode": "drm",
    "androidboot.hardware.gralloc": "minigbm",
    "androidboot.hardware.vulkan": "pastel",
    "androidboot.hardware.egl": "angle",
    "androidboot.vendor.apex.com.android.hardware.keymint": "com.android.hardware.keymint.rust_nonsecure",
    "androidboot.vendor.apex.com.android.hardware.secure_element": "com.android.hardware.secure_element",
    "androidboot.vendor.apex.com.google.emulated.camera.provider.hal": "com.google.emulated.camera.provider.hal",
    "androidboot.vendor.apex.com.android.hardware.gatekeeper": "com.android.hardware.gatekeeper.nonsecure",
    "androidboot.vendor.apex.com.android.hardware.weaver": "none",
    "androidboot.vendor.apex.com.android.hardware.strongbox": "none",
    "androidboot.vendor.apex.com.android.hardware.graphics.composer": "com.android.hardware.graphics.composer.ranchu",
    "androidboot.hw_timeout_multiplier": "3",
    "androidboot.lcd_density": "160",
    "androidboot.setupwizard_mode": "DISABLED",
    "androidboot.serialno": "ANYBOOKQEMU01",
}

RUNS = {
    "usb": dict(variant="bm", disks=[("usb-storage", "a")], select="boot_devices", expect="sda"),
    "uas": dict(variant="bm", disks=[("usb-uas", "a")], select="boot_devices", expect="sda"),
    "nvme": dict(variant="bm", disks=[("nvme", "a")], select="boot_devices", expect="nvme0n1"),
    "both-uuid": dict(variant="bm", disks=[("nvme", "a"), ("usb-storage", "b")], select="boot_part_uuid",
                      expect="sda", uuid_disk="b"),
    "vm": dict(variant="vm", disks=[("nvme", "a")], select="boot_devices", expect="nvme0n1"),
}
# Expected module load failures per variant: (module, errno text)
EXPECTED_FAIL = {"bm": {"asus_nb_wmi": "No such device"}, "vm": {}}

ERRORS = [
    ("unknown_symbol", re.compile(r"Unknown symbol|Unknown rela relocation")),
    ("crc", re.compile(r"disagrees about version of symbol|no symbol version for")),
    ("signature", re.compile(r"module verification failed|Loading of unsigned module|unavailable key|"
                             r"PKCS#7 signature not signed|Key was rejected|Lockdown: .*unsigned module")),
    ("format", re.compile(r"Invalid module format|exec format error|module has bad taint")),
    ("protected", re.compile(r"\(err -13\)|protected symbol")),
]


def sh(*cmd, **kw):
    return subprocess.run([str(c) for c in cmd], check=True, capture_output=True, text=True, **kw).stdout


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def stamp_ok(target, inputs):
    """True when target exists and was made from inputs with these hashes (resumable steps)."""
    st = target + ".inputs"
    want = "\n".join(f"{sha256(i) if os.path.isfile(i) else i}  {i}" for i in inputs)
    return os.path.exists(target) and os.path.exists(st) and open(st).read() == want, (st, want)


def stamp_write(info):
    open(info[0], "w").write(info[1])


def round_up(n, a):
    return (n + a - 1) // a * a


# ---------- images ----------

def unpack(tools, img, out):
    if os.path.exists(out):
        shutil.rmtree(out)
    info = sh(f"{tools}/unpack_bootimg", "--boot_img", img, "--out", out, "--format", "info")
    return info


def newc(entries):
    """cpio newc archive; entries: (path, mode, data or None for dirs). Owner root, mtime 0."""
    out = bytearray()
    for ino, (path, mode, data) in enumerate(entries + [("TRAILER!!!", 0, b"")], 1):
        name = path.encode() + b"\0"
        data = data or b""
        hdr = "070701" + "".join(f"{v:08x}" for v in (ino, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(name), 0))
        out += hdr.encode() + name
        out += b"\0" * (-len(out) % 4) + data
        out += b"\0" * (-len(out) % 4)
    return bytes(out)


def bootconfig_trailer(text, preceding_len):
    data = text.encode() + b"\0"
    pad = -(preceding_len + len(data) + 8 + 12) % 4
    data += b"\0" * pad
    return data + struct.pack("<II", len(data), sum(data) & 0xFFFFFFFF) + b"#BOOTCONFIG\n"


class Gpt:
    def __init__(self, parts, seed):
        """parts: list of (name, size_bytes, type_guid, payload_path or None)."""
        self.seed = seed
        lba = 2048
        self.parts = []
        for name, size, tguid, payload in parts:
            size = round_up(size, MiB)
            self.parts.append(dict(name=name, first=lba, last=lba + size // SECTOR - 1, type=tguid,
                                   uuid=str(uuid.uuid5(uuid.NAMESPACE_URL, f"anybook-g14-qemu/{seed}/{name}")),
                                   payload=payload))
            lba += size // SECTOR
        self.total = (lba + 2048) * SECTOR
        self.disk_guid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"anybook-g14-qemu/{seed}/disk"))

    def headers(self):
        nsect = self.total // SECTOR
        entries = bytearray(128 * 128)
        for i, p in enumerate(self.parts):
            name = p["name"].encode("utf-16-le").ljust(72, b"\0")
            entries[i * 128:(i + 1) * 128] = (uuid.UUID(p["type"]).bytes_le + uuid.UUID(p["uuid"]).bytes_le +
                                              struct.pack("<QQQ", p["first"], p["last"], 0) + name)
        ecrc = zlib.crc32(entries)

        def hdr(cur, alt, entries_lba):
            h = struct.pack("<8sIIIIQQQQ16sQIII", b"EFI PART", 0x10000, 92, 0, 0, cur, alt, 34, nsect - 34,
                            uuid.UUID(self.disk_guid).bytes_le, entries_lba, 128, 128, ecrc)
            h = h[:16] + struct.pack("<I", zlib.crc32(h)) + h[20:]
            return h.ljust(SECTOR, b"\0")

        mbr = bytearray(SECTOR)
        mbr[446:462] = struct.pack("<BBBBBBBBII", 0, 0, 2, 0, 0xEE, 0xFF, 0xFF, 0xFF, 1, min(nsect - 1, 0xFFFFFFFF))
        mbr[510:512] = b"\x55\xaa"
        primary = bytes(mbr) + hdr(1, nsect - 1, 2) + bytes(entries)
        backup = bytes(entries) + hdr(nsect - 1, 1, nsect - 33)
        return primary, backup

    def write(self, path, payloads=True):
        primary, backup = self.headers()
        with open(path, "r+b" if os.path.exists(path) and not payloads else "wb") as f:
            f.truncate(self.total)
            f.seek(0)
            f.write(primary)
            f.seek(self.total - len(backup))
            f.write(backup)
            if payloads:
                for p in self.parts:
                    if p["payload"]:
                        f.seek(p["first"] * SECTOR)
                        with open(p["payload"], "rb") as src:
                            for b in iter(lambda: src.read(4 * MiB), b""):
                                if b.count(0) == len(b):
                                    f.seek(len(b), 1)  # keep the image sparse
                                else:
                                    f.write(b)

    def table(self):
        return [dict(name=p["name"], first_lba=p["first"], last_lba=p["last"], partuuid=p["uuid"]) for p in self.parts]


def prepare(a, variant, log):
    w = os.path.join(a.work, variant)
    os.makedirs(w, exist_ok=True)
    common = os.path.join(a.work, "common")
    os.makedirs(common, exist_ok=True)
    d, p = a.dist, a.product

    # vendor_boot (ours) and the generic ramdisk (product's init_boot)
    vb = os.path.join(d, variant, "vendor_boot.img")
    info = unpack(a.tools, vb, os.path.join(w, "vendor_boot"))
    vcmd = re.search(r"vendor command line args: (.*)", info).group(1).strip()
    frags = sorted(f for f in os.listdir(os.path.join(w, "vendor_boot")) if f.startswith("vendor_ramdisk"))
    names = re.findall(r"name: (\S*)", info)
    vbootconfig = open(os.path.join(w, "vendor_boot", "bootconfig")).read()
    ib = os.path.join(p, "init_boot.img")
    unpack(a.tools, ib, os.path.join(common, "init_boot"))
    fstab = newc([("first_stage_ramdisk", 0o40755, None),
                  (f"first_stage_ramdisk/fstab.{FSTAB_SUFFIX}", 0o100644, open(a.fstab, "rb").read())])
    # lz4 legacy like the other ramdisks: the kernel only takes an uncompressed cpio at a 4-byte aligned offset,
    # and a compressed predecessor can end anywhere
    open(os.path.join(common, "fstab.cpio.lz4"), "wb").write(
        subprocess.run(["lz4", "-l", "-9", "-c"], input=fstab, capture_output=True, check=True).stdout)

    # vbmeta over every logical partition
    imgs = {n: os.path.join(p, f"{n}.img") for n in LOGICAL}
    imgs["vendor_dlkm"] = os.path.join(d, variant, "vendor_dlkm.img")
    imgs["system_dlkm"] = os.path.join(d, "system_dlkm.flatten.erofs.img")
    vbmeta = os.path.join(w, "vbmeta.img")
    ok, st = stamp_ok(vbmeta, [a.key] + [imgs[n] for n in LOGICAL])
    if not ok:
        args = [f"{a.tools}/avbtool", "make_vbmeta_image", "--algorithm", "SHA256_RSA4096", "--key", a.key,
                "--padding_size", "4096", "--output", vbmeta]
        for n in LOGICAL:
            args += ["--include_descriptors_from_image", imgs[n]]
        sh(*args)
        stamp_write(st)
    digest = sh(f"{a.tools}/avbtool", "calculate_vbmeta_digest", "--image", vbmeta, "--hash_algorithm", "sha256").strip()
    # androidboot.vbmeta.size is the vbmeta struct (header + authentication + auxiliary blocks), not the padded file
    blocks = re.findall(r"(?:Header|Authentication|Auxiliary) Block:\s+(\d+) bytes",
                        sh(f"{a.tools}/avbtool", "info_image", "--image", vbmeta))
    vbmeta_size = sum(int(b) for b in blocks)

    # super
    super_img = os.path.join(w, "super.img")
    sizes = {n: round_up(os.path.getsize(imgs[n]), 4096) for n in LOGICAL}
    super_size = round_up(sum(sizes.values()) + 64 * MiB, 64 * MiB)
    ok, st = stamp_ok(super_img, [imgs[n] for n in LOGICAL] + [str(super_size)])
    if not ok:
        args = [f"{a.tools}/lpmake", "--metadata-size", "65536", "--super-name", "super", "--metadata-slots", "2",
                "--device", f"super:{super_size}", "--group", f"anybook_dynamic_partitions_a:{super_size - 4 * MiB}",
                "--output", super_img]
        for n in LOGICAL:
            args += ["--partition", f"{n}_a:readonly:{sizes[n]}:anybook_dynamic_partitions_a",
                     "--image", f"{n}_a={imgs[n]}"]
        log(f"lpmake super ({super_size // MiB} MiB)")
        sh(*args)
        stamp_write(st)

    metadata = os.path.join(common, "metadata.img")
    if not os.path.exists(metadata):
        with open(metadata, "wb") as f:
            f.truncate(16 * MiB)
        sh(f"{a.tools}/mke2fs", "-q", "-t", "ext4", "-b", "4096", "-L", "metadata", metadata)

    layout = [("misc", MiB, LINUX_DATA, None),
              ("boot_a", 64 * MiB, LINUX_DATA, os.path.join(d, "boot.img")),
              ("init_boot_a", 8 * MiB, LINUX_DATA, ib),
              ("vendor_boot_a", 32 * MiB, LINUX_DATA, vb),
              ("vbmeta_a", MiB, VBMETA_TYPE, vbmeta),
              ("metadata", 16 * MiB, LINUX_DATA, metadata),
              ("super", super_size, LINUX_DATA, super_img),
              ("userdata", 2048 * MiB, LINUX_DATA, None)]
    disks = {}
    for seed in ("a", "b"):
        g = Gpt(layout, f"{variant}-{seed}")
        path = os.path.join(w, f"disk-{seed}.img")
        ok, st = stamp_ok(path, [x[3] or x[0] for x in layout] + [seed])
        if not ok:
            if seed == "a":
                log(f"writing {path} ({g.total // MiB} MiB, sparse)")
                g.write(path)
            else:  # same payloads, new GUIDs: a reflink copy plus fresh GPT headers
                subprocess.run(["cp", "--reflink=auto", disks["a"]["path"], path], check=True)
                g.write(path, payloads=False)
            stamp_write(st)
        disks[seed] = dict(path=path, gpt=g.table(), disk_guid=g.disk_guid)
    return dict(variant=variant, vendor_cmdline=vcmd, vendor_bootconfig=vbootconfig,
                fragments=[os.path.join(w, "vendor_boot", f) for f in frags], fragment_names=names,
                generic_ramdisk=os.path.join(common, "init_boot", "ramdisk"),
                fstab_cpio=os.path.join(common, "fstab.cpio.lz4"), vbmeta=vbmeta, vbmeta_digest=digest,
                vbmeta_size=vbmeta_size, super_size=super_size, disks=disks,
                inputs={k: sha256(v) for k, v in dict(vendor_boot=vb, init_boot=ib, boot=os.path.join(d, "boot.img"),
                                                       bzImage=os.path.join(d, "bzImage"), **imgs).items()})


# ---------- run ----------

class Console:
    def __init__(self, sock_path, log_path):
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.log = open(log_path, "wb")
        for _ in range(100):
            try:
                self.s = socket.socket(socket.AF_UNIX)
                self.s.connect(sock_path)
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise SystemExit(f"cannot connect to {sock_path}")
        self.t = threading.Thread(target=self._read, daemon=True)
        self.t.start()

    def _read(self):
        while True:
            try:
                b = self.s.recv(65536)
            except OSError:
                break
            if not b:
                break
            with self.lock:
                self.buf += b
            self.log.write(b)
            self.log.flush()

    def text(self, start=0):
        with self.lock:
            return self.buf[start:].decode("utf-8", "replace")

    def size(self):
        with self.lock:
            return len(self.buf)

    def send(self, s):
        self.s.sendall(s.encode())

    def wait(self, pattern, timeout, start=0):
        rx = re.compile(pattern)
        end = time.time() + timeout
        while time.time() < end:
            m = rx.search(self.text(start))
            if m:
                return m
            if not self.t.is_alive():
                return None
            time.sleep(0.2)
        return None

    def run(self, name, cmd, timeout=60):
        start = self.size()
        self.send(f"echo @@BEGIN_{name}@@; {cmd}; echo @@END_{name}@@ rc=$?\n")
        # the typed command, if echoed, has "@@BEGIN_x@@;" and "rc=$?", so only the real output matches
        m = self.wait(rf"(?s)@@BEGIN_{name}@@\r?\n(.*?)\r?\n@@END_{name}@@ rc=(\d+)", timeout, start)
        if not m:
            return None
        # drop kernel messages that reached the console while the command ran
        return "\n".join(l for l in m.group(1).replace("\r", "").split("\n") if not re.match(r"\[\s*\d+\.\d+\]", l))


def run_one(a, name, spec, prep, log):
    out = os.path.join(a.out, name)
    res_path = f"{out}.json"
    if os.path.exists(res_path) and not a.force:
        log(f"{name}: result exists, skipping (--force reruns)")
        return json.load(open(res_path))
    sock = os.path.join(a.work, f"{name}.sock")
    if os.path.exists(sock):
        os.unlink(sock)

    # bootconfig, as a bootloader would append it
    bc = {**CF_BOOTCONFIG,
          "androidboot.slot_suffix": "_a", "androidboot.force_normal_boot": "1",
          "androidboot.fstab_suffix": FSTAB_SUFFIX, "androidboot.verifiedbootstate": "orange",
          "androidboot.vbmeta.device_state": "unlocked", "androidboot.vbmeta.avb_version": "1.2",
          "androidboot.vbmeta.hash_alg": "sha256", "androidboot.vbmeta.size": str(prep["vbmeta_size"]),
          "androidboot.vbmeta.digest": prep["vbmeta_digest"], "androidboot.veritymode": "enforcing",
          "androidboot.console": "ttyS0"}
    qdev, drives = [], []
    expect_prefix = None
    for i, (kind, seed) in enumerate(spec["disks"]):
        disk = prep["disks"][seed]["path"]
        # snapshot=on: the guest's writes (metadata, the userdata format) go to a throwaway overlay, so every
        # run starts from the same disk
        drives += ["-drive", f"if=none,id=d{i},file={disk},format=raw,cache=unsafe,aio=threads,snapshot=on"]
        if kind == "nvme":
            qdev += ["-device", f"pcie-root-port,id=rp{i},bus=pcie.0,addr=0x{NVME_RP.split('.')[0]},chassis={i + 1}",
                     "-device", f"nvme,serial=ANYBOOK{seed.upper()}NVME,drive=d{i},bus=rp{i}"]
            prefix = f"pci0000:00/0000:00:{NVME_RP}"
        else:
            qdev += ["-device", f"pcie-root-port,id=rp{i},bus=pcie.0,addr=0x{USB_RP.split('.')[0]},chassis={i + 1}",
                     "-device", f"qemu-xhci,id=xhci{i},bus=rp{i}"]
            if kind == "usb-uas":
                qdev += ["-device", f"usb-uas,id=uas{i},bus=xhci{i}.0",
                         "-device", f"scsi-hd,bus=uas{i}.0,scsi-id=0,lun=0,drive=d{i}"]
            else:
                qdev += ["-device", f"usb-storage,bus=xhci{i}.0,drive=d{i},removable=on"]
            prefix = f"pci0000:00/0000:00:{USB_RP}"
        if i == 0 or seed == spec.get("uuid_disk"):
            expect_prefix = prefix
    if spec["select"] == "boot_devices":
        bc["androidboot.boot_devices"] = expect_prefix
    else:
        bc["androidboot.boot_part_uuid"] = next(
            p["partuuid"] for p in prep["disks"][spec["uuid_disk"]]["gpt"] if p["name"] == "boot_a")
    text = prep["vendor_bootconfig"] + "".join(f'{k} = "{v}"\n' for k, v in bc.items())

    initrd = os.path.join(a.work, f"{name}.initrd")
    with open(initrd, "wb") as f:
        for frag in prep["fragments"]:
            f.write(open(frag, "rb").read())
        f.write(open(prep["fstab_cpio"], "rb").read())
        f.write(open(prep["generic_ramdisk"], "rb").read())
        f.write(bootconfig_trailer(text, f.tell()))
    # The GKI builds the 8250 driver with no runtime UARTs; Cuttlefish passes 8250.nr_uarts=1 for the same reason
    cmdline = (prep["vendor_cmdline"] + " 8250.nr_uarts=1 console=ttyS0,115200 earlycon=uart8250,io,0x3f8,115200 "
               "printk.devkmsg=on panic=-1")
    qemu = ["qemu-system-x86_64", "-enable-kvm", "-machine", "q35,kernel-irqchip=split", "-cpu", "host",
            "-smp", "4", "-m", "6144"] + (["-device", "amd-iommu,intremap=on"] if a.iommu else []) + [
            "-kernel", os.path.join(a.dist, "bzImage"), "-initrd", initrd, "-append", cmdline,
            "-display", "none", "-vga", "none", "-nic", "none", "-no-reboot",
            "-chardev", f"socket,id=ser0,path={sock},server=on,wait=on", "-serial", "chardev:ser0",
            "-monitor", "none"] + drives + qdev
    log(f"{name}: {' '.join(qemu)}")
    t0 = time.time()
    proc = subprocess.Popen(qemu, stdout=open(f"{out}.qemu.log", "wb"), stderr=subprocess.STDOUT)
    con = Console(sock, f"{out}.serial.log")
    captures, timeline = {}, {}
    try:
        if con.wait(r"init: Switching root to", 60):
            timeline["first_stage_switch_root_s"] = round(time.time() - t0, 1)
        # the console service starts at "on init"; poke it until the prompt answers
        prompt = None
        end = time.time() + a.timeout
        while time.time() < end and proc.poll() is None:
            con.send("\n")
            prompt = con.wait(r"console:/ [#$] ", 3, max(0, con.size() - 4096))
            if prompt:
                break
        if not prompt:
            raise RuntimeError("no console prompt")
        timeline["console_s"] = round(time.time() - t0, 1)
        # a root shell (userdebug su), quiet: the kernel log up to here is already on the serial line, which runs
        # at 115200 baud, so later kernel messages are kept off the console instead of interleaving with output
        con.send("su\n")
        if not con.wait(r"console:/ # ", 15, max(0, con.size() - 256)):
            raise RuntimeError("su gave no root prompt")
        con.send("set +o emacs; stty -echo; dmesg -n 1\n")
        time.sleep(1)
        # wait for Cuttlefish's dlkm_loader (oneshot, started at early-init) to finish
        state = ""
        while time.time() < end:
            state = (con.run("svc", "getprop init.svc.vendor.dlkm_loader") or "").strip()
            if state in ("stopped", "restarting") or (state == "" and time.time() - t0 > 120):
                break
            time.sleep(2)
        timeline["dlkm_loader_done_s"] = round(time.time() - t0, 1)
        timeline["dlkm_loader_state"] = state
        time.sleep(5)  # let late module probes and logs settle
        for key, cmd in [
            ("uname", "uname -r"),
            ("cmdline", "cat /proc/cmdline"),
            ("bootconfig", "cat /proc/bootconfig"),
            ("props", "getprop | grep -E 'ro\\.boot\\.(boot_devices|boot_part_uuid|slot_suffix|verifiedbootstate|"
                      "fstab_suffix|vbmeta\\.(digest|device_state))|vendor\\.dlkm|init\\.svc\\.vendor\\.dlkm|"
                      "ro(\\.vendor)?\\.build\\.fingerprint|sys\\.boot_completed|ro\\.boot\\.hardware\\]'"),
            ("by_name", "ls -l /dev/block/by-name/"),
            ("block_dirs", "ls -l /dev/block/pci /dev/block/nvme /dev/block/scsi /dev/block/platform 2>&1"),
            ("sys_block", "for b in /sys/class/block/sd? /sys/class/block/nvme?n?; do [ -e $b ] && "
                          "echo $b $(readlink -f $b); done"),
            ("mounts", "grep -E ' /(system|system_ext|product|vendor|odm|vendor_dlkm|odm_dlkm|system_dlkm|"
                       "metadata|data) ' /proc/mounts"),
            ("dm", "dmctl list devices"),
            ("modules", "cat /proc/modules"),
            ("vendor_lib_modules", "ls -l /vendor/lib/modules /system/lib/modules | head -3; "
                                   "ls /vendor_dlkm/lib/modules/*.ko | wc -l; ls /system_dlkm/lib/modules/*.ko | wc -l"),
            ("tainted", "cat /proc/sys/kernel/tainted"),
        ]:
            captures[key] = con.run(key, cmd, timeout=60)
        con.send("reboot -p\n")
        proc.wait(timeout=60)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        captures["error"] = str(e)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    timeline["total_s"] = round(time.time() - t0, 1)
    res = analyse(a, name, spec, prep, captures, con.text(), timeline, bc, cmdline, qemu)
    json.dump(res, open(res_path, "w"), indent=1)
    open(f"{out}.md", "w").write(report(res))
    for k in ("by_name", "block_dirs", "mounts", "modules", "dm", "props", "bootconfig", "sys_block"):
        if captures.get(k) is not None:
            open(f"{out}.{k}.txt", "w").write(captures[k] + "\n")
    # readable excerpts of the kernel log: how the disk appeared and what first-stage init did with it, and
    # what dlkm_loader loaded
    klines = [l for l in con.text().replace("\r", "").split("\n") if re.match(r"\[\s*\d+\.\d+\]\[\s*[TC]\d+\]", l)]
    disk = re.compile(r"usb \d-\d|scsi|sd \d|\[sd[a-z]\]| sd[a-z]: |nvme|Command line:|Load bootconfig")
    fs_lines, inside = [], False
    for l in klines:
        if "init first stage started" in l:
            inside = True
        if inside or disk.search(l):
            fs_lines.append(l)
        if "init second stage started" in l:
            break
    open(f"{out}.first-stage.txt", "w").write("\n".join(fs_lines) + "\n")
    open(f"{out}.dlkm.txt", "w").write("\n".join(l for l in klines if "dlkm_loader" in l) + "\n")
    os.unlink(initrd)
    log(f"{name}: {'PASS' if res['pass'] else 'FAIL'} ({timeline['total_s']} s)")
    return res


def canon(m):
    return m.removesuffix(".ko").replace("-", "_")


def analyse(a, name, spec, prep, cap, serial, timeline, bc, cmdline, qemu):
    v = spec["variant"]
    # kernel console lines only ("[time][caller]"): the shell echoes what the harness types
    klog = "\n".join(l for l in serial.replace("\r", "").split("\n") if re.match(r"\[\s*\d+\.\d+\]\[\s*[TC]\d+\]", l))
    fs = {
        "switch_root": bool(re.search(r"init: Switching root to '/first_stage_ramdisk'", klog)),
        "logical_created": re.findall(r"\[libfs_mgr\] Created logical partition (\S+) on device", klog),
        "mounted": re.findall(r"__mount\(source=\S+,target=(/\S*),type=(\w+)\)=0", klog),
        "mount_failed": re.findall(r"__mount\(source=\S+,target=(/\S*),type=(\w+)\)=-1", klog),
        "avb_status": re.findall(r"\[libfs_avb\] Returning avb_handle with status: (\w+)", klog),
        "verity_tables": len(re.findall(r"\[libfs_avb\] Built verity table", klog)),
        "boot_device_from_uuid": re.findall(r"Boot device (\S+) found via partition UUID", klog),
        "first_stage_errors": [l for l in klog.splitlines()
                               if re.search(r"init: .*(Failed to mount|failed to find|Failed to create|"
                                            r"Failed to load kernel modules|Failed to setup verity)", l)],
    }
    fs["logical_mounted"] = sorted({t.lstrip("/") for t, _ in fs["mounted"]} & set(LOGICAL))

    by_name = {}
    for line in (cap.get("by_name") or "").splitlines():
        m = re.search(r"(\S+) -> (\S+)$", line)
        if m:
            by_name[m.group(1)] = os.path.basename(m.group(2))
    expect = spec["expect"]
    wrong = {k: t for k, t in by_name.items() if not t.startswith(expect)}
    needed = ["super", "vbmeta_a", "metadata", "boot_a", "init_boot_a", "vendor_boot_a", "misc", "userdata"]

    live = {l.split()[0]: l for l in (cap.get("modules") or "").splitlines() if l.strip()}
    load_list = [l.strip() for l in open(os.path.join(a.dist, v, "vendor_dlkm.modules.load")) if l.strip()]
    first_stage = [l.strip() for l in open(os.path.join(a.dist, v, "modules.load")) if l.strip()]
    expected_fail = EXPECTED_FAIL[v]
    missing = [m for m in first_stage + load_list if canon(m) not in live and canon(m) not in expected_fail]
    unexpected_live = [m for m in expected_fail if m in live]
    errors = {k: [l for l in klog.splitlines() if rx.search(l)] for k, rx in ERRORS}
    # libmodprobe's own report of what failed and why
    insmod_fail = re.findall(r"Failed to insmod '([^']+)'[^\n]*?: (.+)", klog)
    fail_ok = [(f, why) for f, why in insmod_fail if canon(os.path.basename(f)) in expected_fail
               and expected_fail[canon(os.path.basename(f))] in why]
    fail_bad = [(f, why) for f, why in insmod_fail if (f, why) not in fail_ok]
    loader = re.findall(r"module load count is (\d+)", klog)
    from_system_dlkm = sorted(set(re.findall(r"Loaded kernel module /system/lib/modules/(\S+)", klog)))
    signing_cert = re.findall(r"Loaded X\.509 cert '([^']+)'", klog)
    gki_live = sorted(m for m in ("bluetooth", "rfkill", "btbcm", "libarc4") if m in live)
    tainted = (cap.get("tainted") or "").strip()

    checks = {
        "switch_root": fs["switch_root"],
        "all_logical_mounted": fs["logical_mounted"] == sorted(LOGICAL),
        "avb_ok": bool(fs["avb_status"]) and all(s == "Success" for s in fs["avb_status"]),
        "dm_verity_for_all": fs["verity_tables"] >= len(LOGICAL),
        "by_name_complete": all(n in by_name for n in needed),
        "by_name_on_expected_disk": bool(by_name) and not wrong,
        "vendor_dlkm_all_live": not missing,
        "expected_failures_only": not fail_bad and not unexpected_live,
        "no_symbol_crc_signature_errors": not any(errors.values()),
        "gki_deps_from_system_dlkm_live": gki_live == ["bluetooth", "btbcm", "libarc4", "rfkill"],
    }
    if spec["select"] == "boot_part_uuid":
        checks["boot_device_found_by_uuid"] = bool(fs["boot_device_from_uuid"])
    if v == "vm":
        checks["dlkm_ready"] = "[vendor.dlkm.modules.ready]: [true]" in (cap.get("props") or "")
    return {
        "run": name, "variant": v, "disks": spec["disks"], "select": spec["select"], "expected_disk": expect,
        "pass": all(checks.values()), "checks": checks, "timeline": timeline, "error": cap.get("error"),
        "first_stage": fs, "by_name": by_name, "by_name_wrong_disk": wrong,
        "modules": dict(live=len(live), vendor_dlkm_listed=len(load_list), first_stage_listed=len(first_stage),
                        missing=missing, expected_failures=fail_ok, unexpected_failures=fail_bad,
                        dlkm_loader_count=loader, gki_deps_live=gki_live, loaded_from_system_dlkm=from_system_dlkm,
                        kernel_signing_cert=signing_cert, tainted=tainted),
        "errors": {k: l[:20] for k, l in errors.items()}, "bootconfig": bc, "cmdline": cmdline, "qemu": qemu,
        "gpt": {s: prep["disks"][s]["gpt"] for _, s in spec["disks"]}, "inputs": prep["inputs"],
    }


def report(r):
    lines = [f"# QEMU run `{r['run']}`: {'PASS' if r['pass'] else 'FAIL'}", "",
             f"- variant `{r['variant']}`, disks {', '.join(f'{k} ({s})' for k, s in r['disks'])}, "
             f"boot device by `{r['select']}`, expected disk `{r['expected_disk']}`",
             f"- timeline: {json.dumps(r['timeline'])}", ""]
    lines += ["| check | result |", "|---|---|"] + [f"| {k} | {'ok' if v else 'FAIL'} |" for k, v in r["checks"].items()]
    fs, m = r["first_stage"], r["modules"]
    lines += ["", f"- logical partitions mounted: {', '.join(fs['logical_mounted'])}",
              f"- AVB: {', '.join(fs['avb_status'])}; dm-verity tables built: {fs['verity_tables']}",
              f"- boot device from UUID: {fs['boot_device_from_uuid'] or '-'}",
              f"- by-name: " + ", ".join(f"{k} -> {v}" for k, v in sorted(r['by_name'].items())),
              f"- modules live: {m['live']}; vendor_dlkm modules.load: {m['vendor_dlkm_listed']}; first stage: "
              f"{m['first_stage_listed']}; missing: {m['missing'] or 'none'}",
              f"- expected failures: {m['expected_failures'] or 'none'}; unexpected: {m['unexpected_failures'] or 'none'}",
              f"- dlkm_loader load count: {m['dlkm_loader_count'] or '-'}; GKI deps live: {m['gki_deps_live']}; "
              f"tainted: {m['tainted']}",
              f"- loaded by dlkm_loader from /system/lib/modules (system_dlkm): {m['loaded_from_system_dlkm']}",
              f"- kernel trusts: {m['kernel_signing_cert']}",
              f"- error lines: " + (", ".join(f"{k} {len(v)}" for k, v in r["errors"].items())),
              ]
    if r.get("error"):
        lines.append(f"- harness error: {r['error']}")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ("dist", "product", "tools", "key", "fstab", "work", "out"):
        ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--runs", default=",".join(RUNS))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--timeout", type=int, default=240)
    # Off by default: with QEMU's amd-iommu, an xHCI or NVMe controller behind a PCIe root port never completes a
    # command (no USB device enumerates, no xHCI error either), while the same devices work without it.
    ap.add_argument("--iommu", action=argparse.BooleanOptionalAction, default=False,
                    help="emulate the AMD IOMMU (QEMU amd-iommu,intremap=on)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.work, exist_ok=True)

    def log(s):
        print(f"### {time.strftime('%H:%M:%S')} {s}", flush=True)

    names = a.runs.split(",")
    preps = {}
    results = []
    for n in names:
        spec = RUNS[n]
        if spec["variant"] not in preps:
            log(f"prepare {spec['variant']}")
            preps[spec["variant"]] = prepare(a, spec["variant"], log)
        results.append(run_one(a, n, spec, preps[spec["variant"]], log))
    summary = {"pass": all(r["pass"] for r in results), "runs": {r["run"]: {
        "pass": r["pass"], "checks": r["checks"], "timeline": r["timeline"]} for r in results}}
    json.dump(summary, open(os.path.join(a.out, "results.json"), "w"), indent=1)
    md = ["# ANAL-198 QEMU first-stage check", "", "| run | variant | disks | boot device by | result |",
          "|---|---|---|---|---|"]
    md += [f"| {r['run']} | {r['variant']} | {', '.join(k for k, _ in r['disks'])} | {r['select']} | "
           f"{'PASS' if r['pass'] else 'FAIL'} |" for r in results]
    open(os.path.join(a.out, "summary.md"), "w").write("\n".join(md) + "\n")
    log("overall " + ("PASS" if summary["pass"] else "FAIL"))
    sys.exit(0 if summary["pass"] else 1)


if __name__ == "__main__":
    main()
