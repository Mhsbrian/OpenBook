#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Apply a verified preserving update to one explicitly confirmed USB stick.

Default is read-only preflight. --apply requires --confirm-device naming the
same whole USB by-id path. Never use on a mounted or running Android disk.
Writes only super, vbmeta_a and EFI, then independently reads the entire used
extent. The backup remains private and untouched. Not power-loss atomic.
"""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("preserve", HERE / "preserve-update.py")
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


def validate_plan(prepared, backup):
    image = u.regular(prepared / "ruby-live.img")
    backup = u.regular(backup)
    plan = json.loads(u.regular(prepared / "update.json").read_text())
    if plan.get("schema") != "openbook-ruby-preserving-update/1" or plan.get("complete") is not True:
        raise ValueError("Incomplete preserving update")
    if u.h.audit.sha(backup) != plan["backup_sha256"] or u.h.audit.sha(image) != plan["image_sha256"]:
        raise ValueError("Backup or prepared image checksum mismatch")
    table = u.read_gpt(backup)
    if u.read_gpt(image) != table or image.stat().st_size != backup.stat().st_size:
        raise ValueError("Prepared image changed disk identity/layout")
    rows = {r["name"]: r for r in table}
    if len(plan["writes"]) != 3 or {r["name"] for r in plan["writes"]} != set(u.WRITABLE):
        raise ValueError("Only EFI, super and vbmeta_a may be written")
    for write in plan["writes"]:
        offset, length = u.extent(rows[write["name"]])
        if (write["offset"], write["length"]) != (offset, length):
            raise ValueError("Write range is outside the allowed partition")
        if u.digest_range(image, offset, length) != write["sha256"]:
            raise ValueError("Write payload checksum mismatch")
    expected_ranges = list(u.protected_ranges(table, image.stat().st_size))
    if [(r["offset"], r["length"]) for r in plan["protected"]] != expected_ranges:
        raise ValueError("Incomplete protected range coverage")
    for protected in plan["protected"]:
        offset, length = protected["offset"], protected["length"]
        if u.digest_range(backup, offset, length) != protected["sha256"] or u.digest_range(image, offset, length) != protected["sha256"]:
            raise ValueError("Protected state changed")
    return image, plan


def device_info(path):
    if not str(path).startswith("/dev/disk/by-id/usb-") or "-part" in path.name:
        raise ValueError("Name the whole stick with its USB by-id path")
    target = path.resolve(strict=True)
    if not stat.S_ISBLK(target.stat().st_mode):
        raise ValueError("Target is not a block device")
    info = json.loads(subprocess.check_output([
        "lsblk", "--json", "--bytes", "--output", "NAME,TYPE,TRAN,SIZE,RO,LOG-SEC,MOUNTPOINTS", str(target)], text=True))["blockdevices"]
    if len(info) != 1:
        raise ValueError("Ambiguous disk")
    info = info[0]
    if info["type"] != "disk" or info["tran"] != "usb" or info["ro"] or info["log-sec"] != 512:
        raise ValueError("Requires a writable whole USB disk with 512-byte sectors")

    def mounted(row):
        return any(row.get("mountpoints") or []) or any(mounted(child) for child in row.get("children", []))
    if mounted(info):
        raise ValueError("Unmount every target partition before preflight/apply")
    return target, info["size"], target.stat().st_rdev


def direct_digest(device, size):
    # Read through O_DIRECT after fsync; a page-cache comparison is insufficient.
    proc = subprocess.Popen(["dd", f"if={device}", "bs=4M", f"count={size}",
                             "iflag=direct,count_bytes", "status=none"], stdout=subprocess.PIPE)
    try:
        digest = u.hashlib.sha256(); count = 0
        while data := proc.stdout.read(4 << 20):
            digest.update(data); count += len(data)
    finally:
        proc.stdout.close()
        code = proc.wait()
    if code or count != size:
        raise ValueError("Incomplete direct device read")
    return digest.hexdigest()


def write_ranges(source, target, writes):
    # System first, matching boot files last. Never imply transactional rollback.
    by_name = {r["name"]: r for r in writes}
    with source.open("rb") as src, target.open("r+b", buffering=0) as dst:
        fcntl.flock(dst.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        for name in ("super", "vbmeta_a", "EFI"):
            row = by_name[name]; left = row["length"]
            src.seek(row["offset"]); dst.seek(row["offset"])
            print(f"Writing {name}: {left} bytes", flush=True)
            while left:
                data = src.read(min(left, 4 << 20))
                if not data:
                    raise ValueError("Truncated prepared payload")
                view = memoryview(data)
                while view:
                    count = dst.write(view)
                    if not count:
                        raise OSError("Short device write")
                    view = view[count:]
                left -= len(data)
            os.fsync(dst.fileno())


def inside(apply):
    target = Path("/dev/openbook-target")
    if not Path("/.dockerenv").exists() or not stat.S_ISBLK(target.stat().st_mode):
        raise ValueError("Internal phase requires the isolated USB container")
    image, plan = validate_plan(Path("/prepared"), Path("/backup.img"))
    print("Checking current USB against the complete verified backup", flush=True)
    if direct_digest(target, image.stat().st_size) != plan["backup_sha256"]:
        raise ValueError("USB changed since backup; stop and take a new verified snapshot")
    if not apply:
        print("Read-only preflight passed; no device bytes written", flush=True)
        return
    write_ranges(image, target, plan["writes"])
    print("Direct readback of the entire used extent", flush=True)
    actual = direct_digest(target, image.stat().st_size)
    if actual != plan["image_sha256"]:
        raise ValueError("DEVICE VERIFICATION FAILED; retain backup and do not boot")
    print("VERIFIED: complete used extent matches the preserving image", flush=True)
    print(json.dumps({"schema": "openbook-ruby-usb-apply/1", "verified": True,
                      "image_bytes": image.stat().st_size, "readback_sha256": actual,
                      "written_names": ["super", "vbmeta_a", "EFI"],
                      "protected_bytes": sum(r["length"] for r in plan["protected"])}), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prepared", type=Path)
    p.add_argument("--backup", type=Path)
    p.add_argument("--device", type=Path)
    p.add_argument("--confirm-device", type=Path)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    a = p.parse_args()
    if a.inside:
        inside(a.apply)
        return
    if not all((a.prepared, a.backup, a.device)):
        p.error("--prepared, --backup and --device are required")
    if a.apply and a.confirm_device != a.device:
        p.error("--confirm-device must name the exact authorized USB by-id path")
    target, size, identity = device_info(a.device)
    image = u.regular(a.prepared / "ruby-live.img")
    backup = u.regular(a.backup)
    if size < image.stat().st_size:
        p.error("USB is smaller than the prepared image")
    repo = HERE.parents[1]
    if any("," in str(path) for path in (repo, a.prepared, backup)):
        p.error("Mount paths cannot contain commas")
    # Recheck mounts and device number immediately before passing this one disk.
    if device_info(a.device) != (target, size, identity):
        p.error("Device identity changed")
    cmd = ["docker", "run", "--rm", "--network", "none", "--device",
           f"{target}:/dev/openbook-target:{'rw' if a.apply else 'r'}",
           "--mount", f"type=bind,src={repo},dst=/repo,readonly",
           "--mount", f"type=bind,src={a.prepared.resolve()},dst=/prepared,readonly",
           "--mount", f"type=bind,src={backup},dst=/backup.img,readonly",
           "openbook-installer", "python3", "/repo/scripts/googlebook/apply-preserved-update.py", "--inside"]
    if a.apply:
        cmd.append("--apply")
    subprocess.run(cmd, check=True)
    if a.apply:
        subprocess.run(["udisksctl", "power-off", "-b", str(target)], check=True)
        print("Verified and powered off; safe to unplug.")


if __name__ == "__main__":
    main()
