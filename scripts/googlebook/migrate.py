#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline, same-machine migration of a pinned configured Ruby USB.

The physical entry point is an interactive RAM-only Linux environment. Never
copy mounted Android data. --image-test accepts regular files only and creates
a new disposable target; it cannot write physical disks.
"""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import tempfile
import uuid
import zlib

NAMES = ("EFI", "misc", "boot_a", "init_boot_a", "vendor_boot_a",
         "vbmeta_a", "metadata", "super", "userdata")
MODES = ("live", "logs", "safe-logs", "serial", "serial-logs")
STATIC = ("boot_a", "init_boot_a", "vendor_boot_a", "vbmeta_a", "super")
MIB = 1 << 20
MAGIC = b"#BOOTCONFIG\n"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_at(fd, start, length):
    data = os.pread(fd, length, start)
    require(len(data) == length, "Truncated device or file")
    return data


def write_at(fd, start, data):
    while data:
        n = os.pwrite(fd, data, start)
        require(n > 0, "Short write")
        start += n
        data = data[n:]


def digest(fd, start, length):
    h = hashlib.sha256()
    for offset in range(start, start + length, 4 * MIB):
        h.update(read_at(fd, offset, min(4 * MIB, start + length - offset)))
    return h.hexdigest()


def capacity(fd):
    info = os.fstat(fd)
    if stat.S_ISBLK(info.st_mode):
        return struct.unpack("<Q", fcntl.ioctl(fd, 0x80081272, bytes(8)))[0]
    require(stat.S_ISREG(info.st_mode), "Requires disk or regular image")
    return info.st_size


def read_gpt(fd):
    size = capacity(fd)
    mbr = read_at(fd, 0, 512)
    require(mbr[510:] == b"\x55\xaa" and mbr[450] == 0xee, "Missing protective MBR")
    first = read_at(fd, 512, 512)
    end = struct.unpack_from("<Q", first, 32)[0]
    require(34 < end < size // 512, "GPT exceeds device")

    def header(lba, alternate, table_lba):
        raw = read_at(fd, lba * 512, 512)
        require(raw[:8] == b"EFI PART" and struct.unpack_from("<II", raw, 8) == (0x10000, 92),
                "Unsupported GPT header")
        crc = struct.unpack_from("<I", raw, 16)[0]
        require(zlib.crc32(raw[:16] + bytes(4) + raw[20:92]) == crc, "GPT header CRC")
        require(struct.unpack_from("<QQ", raw, 24) == (lba, alternate), "GPT locations disagree")
        loc, count, width, crc = struct.unpack_from("<QIII", raw, 72)
        require((loc, count, width) == (table_lba, 128, 128), "Unsupported GPT geometry")
        table = read_at(fd, loc * 512, count * width)
        require(zlib.crc32(table) == crc, "GPT table CRC")
        return raw, table

    first, table = header(1, end, 2)
    last, other = header(end, 1, end - 32)
    require(first[40:72] == last[40:72] and table == other, "GPT copies disagree")
    usable_first, usable_last = struct.unpack_from("<QQ", first, 40)
    require(34 <= usable_first <= usable_last < end - 32, "Invalid GPT usable range")
    rows = []
    previous = usable_first - 1
    for i in range(128):
        e = table[i * 128:(i + 1) * 128]
        if e == bytes(128):
            continue
        start, stop, attrs = struct.unpack_from("<QQQ", e, 32)
        require(previous < start <= stop <= usable_last and attrs == 0, "Invalid partition range")
        previous = stop
        rows.append(dict(name=e[56:].decode("utf-16-le").rstrip("\0"),
                         first_lba=start, last_lba=stop,
                         partuuid=str(uuid.UUID(bytes_le=e[16:32])),
                         type=str(uuid.UUID(bytes_le=e[:16]))))
    require(tuple(r["name"] for r in rows) == NAMES, "Unsupported partition set/order")
    require(len({r["partuuid"] for r in rows}) == len(rows), "Duplicate partition identity")
    return dict(rows=rows, used_bytes=(end + 1) * 512, disk_guid=first[56:72].hex())


def extent(row):
    return row["first_lba"] * 512, (row["last_lba"] - row["first_lba"] + 1) * 512


def target_gpt(source, size, fresh=False):
    require(size % 512 == 0 and size >= source["used_bytes"], "Target too small or unaligned")
    rows = copy.deepcopy(source["rows"])
    for row in rows:
        row["partuuid"] = str(uuid.uuid4())
    if fresh:
        # All remaining whole MiB, leaving room for the backup GPT. No fixed
        # USB capacity carries over to a new filesystem.
        rows[-1]["last_lba"] = ((size // 512 - 33) // 2048) * 2048 - 1
    # Intentionally retain the encrypted filesystem's exact extent. Growing its
    # partition alone does not grow F2FS, and formatting would destroy the setup.
    table = bytearray(16384)
    for i, r in enumerate(rows):
        e = (uuid.UUID(r["type"]).bytes_le + uuid.UUID(r["partuuid"]).bytes_le
             + struct.pack("<QQQ", r["first_lba"], r["last_lba"], 0)
             + r["name"].encode("utf-16-le").ljust(72, b"\0"))
        table[i * 128:(i + 1) * 128] = e
    disk_guid = uuid.uuid4().bytes_le
    end = size // 512 - 1

    def header(here, other, loc):
        data = bytearray(512)
        struct.pack_into("<8sIIIIQQQQ16sQIII", data, 0, b"EFI PART", 0x10000, 92, 0, 0,
                         here, other, 2048, end - 33, disk_guid, loc, 128, 128, zlib.crc32(table))
        struct.pack_into("<I", data, 16, zlib.crc32(data[:92]))
        return bytes(data)

    mbr = bytearray(512)
    mbr[450] = 0xee
    struct.pack_into("<II", mbr, 454, 1, min(end, 0xffffffff))
    mbr[510:] = b"\x55\xaa"
    return rows, [(0, bytes(mbr) + header(1, end, 2) + table),
                  ((end - 32) * 512, bytes(table) + header(end, 1, end - 32))]


def parse_initrd(data):
    require(len(data) >= 20 and data.endswith(MAGIC), "Missing initrd bootconfig")
    size, checksum = struct.unpack_from("<II", data, len(data) - 20)
    require(0 < size <= 32768 and size <= len(data) - 20, "Bad bootconfig length")
    blob = data[-20 - size:-20]
    require(sum(blob) & 0xffffffff == checksum, "Bad bootconfig checksum")
    params = {}
    for line in blob.rstrip(b"\0").decode().splitlines():
        key, sep, value = line.partition("=")
        require(sep and key.strip() not in params, "Malformed or duplicate boot parameter")
        params[key.strip()] = value.strip().strip('"')
    return data[:-20 - size], params


def bootconfig(params, body_size):
    text = "".join(f'{k} = "{v}"\n' for k, v in params.items())
    require(not any('"' in v or "\n" in v or "\0" in v for v in params.values()), "Unsafe boot value")
    data = text.encode() + b"\0"
    data += bytes(-(body_size + len(data)) % 4)
    return data + struct.pack("<II", len(data), sum(data) & 0xffffffff) + MAGIC


def run(*args):
    subprocess.run(list(map(str, args)), check=True, stdout=subprocess.DEVNULL)


def check_source(fd, pin):
    require(pin.get("schema") == "openbook-ruby-migration-source/1", "Unrecognized migration source")
    gpt = read_gpt(fd)
    require(gpt["used_bytes"] == pin["image_bytes"], "Source geometry changed")
    compact = [{k: r[k] for k in ("name", "first_lba", "last_lba", "partuuid")} for r in gpt["rows"]]
    require(compact == pin["gpt"], "This is not the configured source USB")
    for row in gpt["rows"]:
        if row["name"] in STATIC:
            require(digest(fd, *extent(row)) == pin["payload_readback"][row["name"]],
                    f"Source system changed: {row['name']}")
    return gpt


def prepare_esp(src, gpt, rows, pin, work, fresh=False):
    esp = work / "esp.img"
    start, length = extent(gpt["rows"][0])
    with esp.open("xb") as out:
        for off in range(0, length, 4 * MIB):
            out.write(read_at(src, start + off, min(4 * MIB, length - off)))
    run("fsck.fat", "-n", esp)
    tree = work / "efi-before"
    tree.mkdir()
    run("mcopy", "-s", "-i", esp, "::*", tree)
    for name, expected in pin["efi_sha256"].items():
        require(hashlib.sha256((tree / name).read_bytes()).hexdigest() == expected,
                f"Source boot file changed: {name}")
    changed = {"ruby/RESEARCH.json", "loader/entries/ruby-install.conf",
               "loader/entries/ruby-install-serial.conf",
               "loader/entries/ruby-fresh.conf", "loader/entries/ruby-fresh-serial.conf"}
    entries = {}
    for mode in MODES:
        name = f"ruby/initrd-{mode}.img"
        original = (tree / name).read_bytes()
        body, params = parse_initrd(original)
        require(params == pin["entries"][mode], "Source bootconfig changed")
        require(params.get("androidboot.selinux") == "enforcing"
                and params.get("androidboot.veritymode") == "enforcing", "Requires enforcing source")
        params["androidboot.boot_part_uuid"] = rows[0]["partuuid"]
        # Keep serial/KeyMint/credential parameters, kernel and all initrd bytes.
        # Live mode remains for compatibility with the measured source; this
        # marker is informational and does not opt into the AOSP install writer.
        params["androidboot.openbook.ruby_installed"] = "1"
        output = work / f"initrd-{mode}.img"
        output.write_bytes(body + bootconfig(params, len(body)))
        require(parse_initrd(output.read_bytes()) == (body, params), "Rebuilt bootconfig mismatch")
        run("mcopy", "-o", "-i", esp, output, f"::/{name}")
        entries[mode] = params
        changed.add(name)
    for mode in ("ruby-install.conf", "ruby-install-serial.conf",
                 "ruby-fresh.conf", "ruby-fresh-serial.conf"):
        if (tree / "loader/entries" / mode).exists():
            run("mdel", "-i", esp, f"::/loader/entries/{mode}")
    installed = dict(schema="openbook-ruby-installed/1", image_base="googlebook-ruby",
                     automatic_updates_qualified=False, data_expansion=fresh,
                     install_mode="fresh" if fresh else "preserve-usb-data",
                     userdata_format_on_first_boot=fresh,
                     source_build=pin["build"], gpt=rows, entries=entries,
                     kernel_sha256=pin["kernel_sha256"], payload_readback=pin["payload_readback"],
                     userdata_bytes=extent(rows[-1])[1], same_machine_only=True)
    record = work / "RESEARCH.json"
    record.write_text(json.dumps(installed, indent=2) + "\n")
    run("mcopy", "-o", "-i", esp, record, "::/ruby/RESEARCH.json")
    run("fsck.fat", "-n", esp)
    after = work / "efi-after"
    after.mkdir()
    run("mcopy", "-s", "-i", esp, "::*", after)
    def files(root):
        return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in root.rglob("*") if p.is_file() and str(p.relative_to(root)) not in changed}
    require(files(tree) == files(after), "Unrelated EFI files changed")
    for mode in MODES:
        require((after / f"ruby/initrd-{mode}.img").read_bytes() == (work / f"initrd-{mode}.img").read_bytes(),
                "EFI initrd readback mismatch")
    require((after / "ruby/RESEARCH.json").read_bytes() == record.read_bytes(), "EFI manifest readback mismatch")
    return esp


def migrate(src, dst, pin, work, expected_source=None, before_write=None, fresh=False):
    """FDs are already exclusively opened and checked by the caller."""
    gpt = check_source(src, pin)
    before = digest(src, 0, gpt["used_bytes"])
    require(expected_source is None or before == expected_source, "Source changed after confirmation")
    size = capacity(dst)
    rows, headers = target_gpt(gpt, size, fresh)
    esp = prepare_esp(src, gpt, rows, pin, work, fresh)
    # Prepare and verify all boot changes before the first destructive write.
    if before_write:
        before_write()
    print("Source verified. Installing; keep power connected.", flush=True)
    write_at(dst, 0, bytes(34 * 512))
    write_at(dst, size - 33 * 512, bytes(33 * 512))
    os.fsync(dst)
    checks = []
    # No valid target GPT/boot path is activated until all payloads verify.
    for row in gpt["rows"][1:] + gpt["rows"][:1]:
        start, length = extent(row)
        if fresh and row["name"] in ("misc", "metadata", "userdata"):
            target_row = next(r for r in rows if r["name"] == row["name"])
            start, length = extent(target_row)
            # Android's formattable path recognizes a zeroed first 4096 bytes.
            # Fresh metadata means new keys; never import the USB's keys/data.
            # Clear the full small state partitions and both userdata edges.
            # This is a reset, NOT a secure erase of old media.
            spans = [(start, length)] if row["name"] != "userdata" else [
                (start, min(length, 4 * MIB)), (start + length - min(length, 4 * MIB), min(length, 4 * MIB))]
            print(f"Resetting {row['name']}; new capacity {length // MIB} MiB", flush=True)
            for offset, count in spans:
                for at in range(0, count, 4 * MIB):
                    write_at(dst, offset + at, bytes(min(4 * MIB, count - at)))
            os.fsync(dst)
            if stat.S_ISBLK(os.fstat(dst).st_mode):
                fcntl.ioctl(dst, 0x1261)
            for offset, count in spans:
                for at in range(0, count, 4 * MIB):
                    n = min(4 * MIB, count - at)
                    require(read_at(dst, offset + at, n) == bytes(n), "Fresh reset readback failed")
            checks.append(dict(name=row["name"], bytes=length, reset_ranges=spans,
                               copied_from_usb=False, formatted_on_first_boot=row["name"] != "misc"))
            continue
        payload = os.open(esp, os.O_RDONLY) if row["name"] == "EFI" else src
        offset = 0 if row["name"] == "EFI" else start
        try:
            wanted = digest(payload, offset, length)
            print(f"Copying {row['name']} ({length // MIB} MiB)", flush=True)
            for off in range(0, length, 4 * MIB):
                write_at(dst, start + off, read_at(payload, offset + off, min(4 * MIB, length - off)))
            os.fsync(dst)
            # Flush device cache and evict host page cache before independent reads.
            if stat.S_ISBLK(os.fstat(dst).st_mode):
                fcntl.ioctl(dst, 0x1261)  # BLKFLSBUF; fsync precedes invalidation
            else:
                os.posix_fadvise(dst, start, length, os.POSIX_FADV_DONTNEED)
            require(digest(dst, start, length) == wanted, f"Readback failed: {row['name']}")
            checks.append(dict(name=row["name"], bytes=length, sha256=wanted))
        finally:
            if payload != src:
                os.close(payload)
    require(digest(src, 0, gpt["used_bytes"]) == before, "Source changed during migration")
    for offset, data in reversed(headers):
        write_at(dst, offset, data)
        os.fsync(dst)
        require(read_at(dst, offset, len(data)) == data, "Target GPT readback failed")
    actual = read_gpt(dst)
    require(actual["rows"] == rows and actual["used_bytes"] == size, "Final target layout mismatch")
    result = dict(schema="openbook-ruby-migration-result/1", complete=True,
                  install_mode="fresh" if fresh else "preserve-usb-data",
                  source_sha256=before, source_unchanged=True, source_bytes=gpt["used_bytes"],
                  target_bytes=size, target_gpt=rows, partitions=checks,
                  userdata_bytes=extent(rows[-1])[1],
                  unallocated_bytes=(size // 512 - 34 - rows[-1]["last_lba"]) * 512,
                  credential_unlock_verified=False, boot_verified=False, automatic_updates_qualified=False)
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def device_state(path, writable=False):
    path = path.resolve(strict=True)
    require(stat.S_ISBLK(path.stat().st_mode), "Requires a whole block device")
    node = Path("/sys/class/block") / path.name
    require(not (node / "partition").exists(), "Select a whole disk")
    require((node / "queue/logical_block_size").read_text().strip() == "512", "Only 512-byte sectors supported")
    require(not writable or (node / "ro").read_text().strip() == "0", "Target is read-only")
    nodes = [node] + [p for p in node.iterdir() if (p / "partition").exists()]
    devs = {(p / "dev").read_text().strip() for p in nodes}
    require(not any(list((p / "holders").iterdir()) for p in nodes), "Device has active holders")
    mounts = {line.split()[2] for line in Path("/proc/self/mountinfo").read_text().splitlines()}
    require(not devs & mounts, "Device or partition is mounted")
    for line in Path("/proc/swaps").read_text().splitlines()[1:]:
        swap = Path(line.split()[0])
        if swap.exists() and stat.S_ISBLK(swap.stat().st_mode):
            rdev = swap.stat().st_rdev
            require(f"{os.major(rdev)}:{os.minor(rdev)}" not in devs, "Device contains active swap")
    def value(name):
        p = node / "device" / name
        return p.read_text().strip() if p.exists() else ""
    fd = os.open(path, os.O_RDONLY | os.O_EXCL)
    try:
        size = capacity(fd)
        return dict(path=str(path), rdev=path.stat().st_rdev, size=size, serial=value("serial"),
                    model=value("model"), bus_path=str(node.resolve()),
                    edge_sha256=digest(fd, 0, MIB) + digest(fd, size - MIB, MIB))
    finally:
        os.close(fd)


def target_allowed(source, target):
    require(source["rdev"] != target["rdev"], "Source cannot be the target")
    require(re.fullmatch(r"/dev/nvme[0-9]+n[0-9]+", target["path"]), "Only whole internal NVMe targets supported")
    require("/usb" not in target["bus_path"], "USB target refused")
    require(target["serial"] and target["model"], "Target identity is incomplete")
    require(target["size"] >= source["used_bytes"], "Target is too small")


def check_power(rows):
    online = any(r.get("type") != "Battery" and r.get("online") == "1" for r in rows)
    batteries = [r for r in rows if r.get("type") == "Battery" and r.get("scope") != "Device"]
    if batteries and not online:
        require(all(r.get("capacity", "").isdecimal() and 50 <= int(r["capacity"]) <= 100
                    for r in batteries), "Connect the charger: battery is low or unreadable")


def power_ready():
    rows = []
    for path in Path("/sys/class/power_supply").glob("*"):
        row = {}
        for name in ("type", "online", "capacity", "scope"):
            try:
                row[name] = (path / name).read_text().strip()
            except OSError:
                pass
        rows.append(row)
    check_power(rows)


def confirmation_phrase(serial, fresh=False):
    return ("FRESH ERASE " if fresh else "ERASE ") + serial


def interactive(pin, fresh=False):
    print("\nOPENBOOK · " + ("Fresh Googlebook install" if fresh else
          "Install this Googlebook USB and keep its data") + "\n", flush=True)
    print("Offline installation for the same laptop. The source USB stays unchanged.")
    print("The selected SSD is replaced completely. Back up its existing contents first.")
    print("Connect the charger before installing.")
    if fresh:
        print("FRESH START: no USB or SSD accounts, apps, files or settings are retained.")
        print("Android creates new encrypted data storage using the remaining SSD space.")
    else:
        print("Saved Android data keeps its USB filesystem size; remaining SSD space stays unallocated.")
    print("Automatic Google OS updates are NOT qualified or blocked by this installer.\n")
    product = Path("/sys/class/dmi/id/product_name").read_text().strip()
    require(product.startswith(pin["dmi_product_prefix"]), "This installer is pinned to a different machine profile")
    power_ready()
    sources = []
    for node in Path("/sys/class/block").iterdir():
        if (node / "partition").exists() or "/usb" not in str(node.resolve()):
            continue
        path = Path("/dev") / node.name
        try:
            state = device_state(path)
            fd = os.open(path, os.O_RDONLY | os.O_EXCL)
            try:
                gpt = read_gpt(fd)
            finally:
                os.close(fd)
            if gpt["rows"][0]["partuuid"] == pin["gpt"][0]["partuuid"]:
                state["used_bytes"] = gpt["used_bytes"]
                sources.append(state)
        except (OSError, ValueError) as exc:
            print(f"USB {path.name} is not eligible: {exc}", flush=True)
    require(len(sources) == 1, "Exactly one unmounted matching source USB is required")
    source = sources[0]
    targets = []
    for node in sorted(Path("/sys/class/block").glob("nvme*n*")):
        try:
            state = device_state(Path("/dev") / node.name, writable=True)
            target_allowed(source, state)
            targets.append(state)
        except (OSError, ValueError):
            continue
    require(targets, "No eligible unmounted internal NVMe disk")
    for i, row in enumerate(targets, 1):
        print(f"{i}. {row['model']} · {row['size'] / 1e9:.1f} GB · serial {row['serial']} · {row['path']}")
    answer = input("\nDisk number, or Enter to cancel: ").strip()
    if not answer:
        return
    require(answer.isdecimal() and 1 <= int(answer) <= len(targets), "Invalid selection")
    target = targets[int(answer) - 1]
    print("\nChecking the source before confirmation. This can take several minutes.", flush=True)
    src = os.open(source["path"], os.O_RDONLY | os.O_EXCL)
    try:
        gpt = check_source(src, pin)
        source_hash = digest(src, 0, gpt["used_bytes"])
    finally:
        os.close(src)
    phrase = confirmation_phrase(target["serial"], fresh)
    print(f"\nThis erases ALL existing partitions on {target['model']} ({target['path']}).")
    print(f"Serial: {target['serial']} · capacity: {target['size']} bytes")
    if fresh:
        planned, _ = target_gpt(gpt, target["size"], fresh=True)
        print(f"New Android data partition: {extent(planned[-1])[1] / 1e9:.2f} GB before filesystem overhead.")
        print("All current SSD data will be lost. Setup starts from scratch.")
    print("Your configured USB is retained. This is not a secure erase.")
    print("After verification, a new OpenBook Googlebook firmware boot entry is added.")
    if input(f"Type exactly {phrase!r} to install, or Enter to cancel: ").strip() != phrase:
        print("Cancelled. No disks written.")
        return
    expected_source = {k: v for k, v in source.items() if k != "used_bytes"}
    require(device_state(Path(source["path"])) == expected_source, "Source identity changed")
    require(device_state(Path(target["path"]), writable=True) == target, "Target identity or partition table changed")
    src = os.open(source["path"], os.O_RDONLY | os.O_EXCL)
    try:
        dst = os.open(target["path"], os.O_RDWR | os.O_EXCL)
        try:
            require(os.fstat(src).st_rdev == source["rdev"] and os.fstat(dst).st_rdev == target["rdev"],
                    "Device changed while opening")
            with tempfile.TemporaryDirectory(prefix="openbook-migrate-") as tmp:
                migrate(src, dst, pin, Path(tmp), source_hash, before_write=power_ready, fresh=fresh)
            fcntl.ioctl(dst, 0x125f)  # BLKRRPART after verified final GPT
        finally:
            os.close(dst)
    finally:
        os.close(src)
    print("\nINSTALL VERIFIED. Original USB unchanged.", flush=True)
    try:
        run("modprobe", "efivarfs")
        efivars = Path("/sys/firmware/efi/efivars")
        require(efivars.is_dir(), "UEFI variables unavailable")
        run("mount", "-t", "efivarfs", "efivarfs", efivars)
        run("efibootmgr", "--create", "--disk", target["path"], "--part", "1",
            "--label", "OpenBook Googlebook", "--loader", r"\EFI\BOOT\BOOTX64.EFI")
        print("Firmware boot entry created: OpenBook Googlebook.", flush=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Disk verified; firmware entry could not be registered: {exc}")
        print(r"Select the SSD's EFI\BOOT\BOOTX64.EFI in your firmware boot menu.")
    print("Power off, remove the USB, then boot OpenBook Googlebook from the SSD.")
    print("Complete new setup and verify Storage capacity." if fresh else
          "Verify your existing PIN, apps and files. Keep the USB until accepted.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pin", type=Path, required=True)
    p.add_argument("--image-test", type=Path, help="Disposable regular source image only")
    p.add_argument("--out", type=Path)
    p.add_argument("--target-bytes", type=int)
    p.add_argument("--fresh", action="store_true", help="Erase target setup and use remaining SSD capacity")
    a = p.parse_args()
    os.umask(0o077)
    pin = json.loads(a.pin.read_text())
    if a.image_test:
        require(a.out and a.target_bytes, "Image test requires output and target size")
        require(stat.S_ISREG(a.image_test.lstat().st_mode), "Image test refuses devices and symlinks")
        a.out.mkdir(mode=0o700)
        src = os.open(a.image_test, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            dst = os.open(a.out / "installed.img", os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                os.ftruncate(dst, a.target_bytes)
                result = migrate(src, dst, pin, a.out, fresh=a.fresh)
                print(json.dumps({k: result[k] for k in ("complete", "source_unchanged", "userdata_bytes", "boot_verified")}))
            finally:
                os.close(dst)
        finally:
            os.close(src)
    else:
        require(not a.out and not a.target_bytes, "Physical mode is interactive only")
        require(os.geteuid() == 0 and Path("/run/openbook-offline-installer").is_file(),
                "Physical writes require the dedicated offline installer boot")
        interactive(pin, fresh=a.fresh)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"STOPPED: {exc}. Keep the source USB; do not boot an incomplete target.")
