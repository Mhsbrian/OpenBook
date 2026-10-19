#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package a local Ruby/OpenBook probe as a UEFI live research image.

Input: hybrid-probe.py --variant bm --prepare-only. Output is a NEW directory
of regular files. No device writes, disk installer manifest, data expansion,
reset menu or firmware-variable writes. This does not declare desktop readiness.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("hybrid", HERE / "hybrid-probe.py")
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
proto = h.module("proto", HERE.parent / "installer/mkproto.py")
lp = h.module("live", HERE.parent / "installer/mklive.py")
NAMES = ("misc", "boot_a", "init_boot_a", "vendor_boot_a", "vbmeta_a", "metadata", "super", "userdata")


def copy_range(src, dst, offset, length):
    with src.open("rb") as inp, dst.open("xb") as out:
        inp.seek(offset)
        while length:
            data = inp.read(min(length, 4 * h.MiB))
            if not data:
                raise ValueError("Truncated source image")
            out.write(data)
            length -= len(data)


def verify_payloads(disk, table):
    results = {}
    with disk.open("rb") as f:
        for part in table:
            if not part["payload"]:
                continue
            src = Path(part["payload"])
            left = src.stat().st_size
            if left > (part["last"] - part["first"] + 1) * 512:
                raise ValueError("Payload exceeds its partition")
            f.seek(part["first"] * 512)
            digest = hashlib.sha256()
            while left:
                data = f.read(min(left, 4 * h.MiB))
                if not data:
                    raise ValueError("Truncated assembled image")
                digest.update(data)
                left -= len(data)
            actual = digest.hexdigest()
            if actual != h.audit.sha(src):
                raise ValueError(f"Readback mismatch: {part['name']}")
            results[part["name"]] = actual
    return results


def boot_parameters(recipe, esp_uuid):
    # Parse the UUID before embedding it in bootconfig. boot_part_uuid activates
    # init's strict disk selection; hardcoded PCI paths must not remain.
    h.gpt.uuid.UUID(esp_uuid)
    params = dict(recipe["bootconfig"])
    for key in ("androidboot.boot_devices", "androidboot.console", "androidboot.serialconsole"):
        params.pop(key, None)
    params.update({"androidboot.boot_part_uuid": esp_uuid, "androidboot.openbook.live": "1",
                   "androidboot.serialno": "RUBYLIVERESEARCH"})
    if params.get("androidboot.selinux") != "enforcing" or params.get("androidboot.veritymode") != "enforcing":
        raise ValueError("The live research image requires enforcing SELinux and verity")
    return params


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probe", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--label", default="ruby-live-research")
    a = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Run through inst-docker.sh")
    if not h.re.fullmatch(r"[A-Za-z0-9._-]{1,64}", a.label):
        p.error("Use a short alphanumeric label")
    src = a.probe.resolve(strict=True)
    recipe = json.loads((src / "recipe.json").read_text())
    if recipe.get("schema") != "openbook-ruby-vm-probe/1" or recipe.get("module_variant") != "bm":
        p.error("Requires the bare-metal module variant; rebuild with --variant bm")
    disk = src / "probe.img"
    if not disk.is_file() or disk.is_symlink():
        p.error("Probe must be a regular file")
    table = recipe["gpt"]
    if tuple(row["name"] for row in table) != NAMES:
        p.error("Unexpected probe partition set/order")
    source_sha = h.audit.sha(disk)
    w = h.new_output(a.out, (src,))
    h.run("sgdisk", "-v", disk)
    parts = w / "parts"
    parts.mkdir()
    scale = [("EFI", 256 * h.MiB, "c12a7328-f81f-11d2-ba4b-00a0c93ec93b", str(w / "esp.img"))]
    for row in table:
        n = row["name"]
        start, end = row["first_lba"] * 512, (row["last_lba"] + 1) * 512
        if start < h.MiB or end > disk.stat().st_size or end <= start:
            raise ValueError("Invalid probe extent")
        payload = None
        if n not in ("misc", "metadata", "userdata"):
            payload = parts / f"{n}.img"
            copy_range(disk, payload, start, end - start)
        scale.append((n, end - start, h.gpt.VBMETA_TYPE if n == "vbmeta_a" else h.gpt.LINUX_DATA, str(payload) if payload else None))
    # Verify the full logical images before calling this a packaging of that probe.
    _, _, logical = lp.lp_layout(str(parts / "super.img"))
    extracted = lp.extract_partitions(str(parts / "super.img"), logical, str(w / "logical"))
    got = {n.removesuffix("_a"): h.audit.sha(Path(path)) for n, path in extracted.items()}
    if got != recipe["source_sha256"]:
        raise ValueError("Logical images differ from the probe recipe")
    gpt = h.gpt.Gpt(scale, a.label)
    esp_uuid = gpt.parts[0]["uuid"]
    for n in ("boot", "init_boot", "vendor_boot"):
        h.run(proto.tool("unpack_bootimg"), "--boot_img", parts / f"{n}_a.img", "--out", w / n,
              stdout=subprocess.DEVNULL)
    if h.audit.sha(w / "boot/kernel") != recipe["kernel_sha256"]:
        raise ValueError("Kernel differs from the probe recipe")
    digest = subprocess.check_output([proto.tool("avbtool"), "calculate_vbmeta_digest", "--image",
                                      str(parts / "vbmeta_a.img"), "--hash_algorithm", "sha256"], text=True).strip()
    if digest != recipe["bootconfig"]["androidboot.vbmeta.digest"]:
        raise ValueError("AVB root differs from the probe recipe")
    esp = w / "esp"
    for sub in ("EFI/BOOT", "loader/entries", "ruby"):
        (esp / sub).mkdir(parents=True)
    shutil.copyfile("/usr/lib/systemd/boot/efi/systemd-bootx64.efi", esp / "EFI/BOOT/BOOTX64.EFI")
    shutil.copyfile(w / "boot/kernel", esp / "ruby/kernel")
    # The existing boot-control HAL marks slot A good through openbook-bootsync.
    # Its slot identity comes from this filename, even for an uncounted live entry.
    (esp / "loader/loader.conf").write_text("timeout 5\ndefault openbook-a.conf\neditor no\nconsole-mode keep\n")
    params = boot_parameters(recipe, esp_uuid)
    entries = {}
    for mode in ("live", "serial"):
        conf = dict(params)
        extra = ""
        if mode == "serial":
            conf.update({"androidboot.console": "ttyS0", "androidboot.serialconsole": "1"})
            extra = " console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on"
        initrd = esp / f"ruby/initrd-{mode}.img"
        with initrd.open("xb") as f:
            for ramdisk in sorted((w / "vendor_boot").glob("vendor_ramdisk*")):
                f.write(ramdisk.read_bytes())
            f.write((w / "init_boot/ramdisk").read_bytes())
            f.write(h.gpt.bootconfig_trailer(h.bc.render(conf).decode(), f.tell()))
        entries[mode] = conf
        title = "Googlebook on OpenBook - experimental live boot" if mode == "live" else "Googlebook - VM serial diagnostics"
        filename = "openbook-a.conf" if mode == "live" else "ruby-serial.conf"
        (esp / f"loader/entries/{filename}").write_text(
            f"title {title}\nlinux /ruby/kernel\ninitrd /ruby/initrd-{mode}.img\noptions bootconfig{extra}\n")
    manifest = {"schema": "openbook-ruby-live-research/1", "installable": False,
                "desktop_validated": False, "hardware_validated": False, "module_variant": "bm",
                "input_sha256": source_sha, "logical_sha256": got, "kernel_sha256": recipe["kernel_sha256"],
                "gpt": gpt.table(), "entries": entries,
                "scope": "Local research only. No installer source or redistribution permission. Fixed-size encrypted userdata on this image only."}
    (esp / "ruby/RESEARCH.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (esp / "ruby/README.txt").write_text(
        "Experimental Ruby framework on the OpenBook G14 platform.\n"
        "No desktop or hardware qualification yet. Keep this recovery-derived image local.\n"
        "UEFI Secure Boot must already be off. No installer is provided.\n"
        "Android uses this disk's fixed-size userdata; it does not grow to fill a stick.\n")
    proto.make_fat(str(esp), str(w / "esp.img"), 256)
    output = w / "ruby-live.img"
    gpt.write(str(output))
    h.run("sgdisk", "-v", output)
    manifest["payload_readback"] = verify_payloads(output, gpt.parts)
    manifest["image_sha256"] = h.audit.sha(output)
    manifest["image_bytes"] = output.stat().st_size
    manifest["input_unchanged"] = h.audit.sha(disk) == source_sha
    if not manifest["input_unchanged"]:
        raise ValueError("Input changed during packaging")
    (w / "ruby-live.sha256").write_text(f"{manifest['image_sha256']}  ruby-live.img\n")
    (w / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({k: manifest[k] for k in ("image_sha256", "image_bytes", "input_unchanged", "installable")}, indent=2))


if __name__ == "__main__":
    main()
