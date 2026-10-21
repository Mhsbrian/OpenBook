#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline system update of an installed Ruby laptop that keeps its data.

The physical entry points run only in the USB's dedicated offline environment.
The USB's pinned system (source.json) is the new system; laptop-update.json
names the one reviewed previous system it may replace. On the laptop only
super, vbmeta_a and EFI are written. GPT, misc, boot partitions, metadata and
userdata are never written. Before the first laptop write, the laptop's current
super/vbmeta_a/EFI are copied to a rollback area beyond the USB's partitioned
extent; `restore` writes those exact bytes back. The USB's partitions are never
written. Not power-loss atomic: an interrupted update is repaired by restore.

`spec` (host, regular files) creates laptop-update.json from reviewed manifests.
`--image-test` runs update/restore on regular files and cannot open devices.
"""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec_ = importlib.util.spec_from_file_location("migration", HERE / "migrate.py")
m = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(m)

MIB, GIB = m.MIB, 1 << 30
BOOT = ("boot_a", "init_boot_a", "vendor_boot_a")
WRITES = ("super", "vbmeta_a", "EFI")  # EFI last: boot entries switch only after both payloads verify
SAVED = ("EFI", "vbmeta_a", "super")
HEADER_SLOTS = (0, 64 * 1024)
HEADER_BYTES = 4096
HEADER_MAGIC = b"OPENBOOK-LAPTOP-ROLLBACK/1\n"
LOCAL = ("androidboot.boot_part_uuid", "androidboot.openbook.ruby_installed")
DIGEST = ("androidboot.vbmeta.digest", "androidboot.vbmeta.size")


def portable(params):
    """Boot parameters without the per-disk identity that migration rebinds."""
    return {k: v for k, v in params.items() if k not in LOCAL}


def flush(fd, start, length):
    os.fsync(fd)
    if stat.S_ISBLK(os.fstat(fd).st_mode):
        fcntl.ioctl(fd, 0x1261)  # BLKFLSBUF after fsync: the readback comes from the device
    else:
        os.posix_fadvise(fd, start, length, os.POSIX_FADV_DONTNEED)


def copy_range(src, src_offset, dst, dst_offset, length, label):
    wanted = m.digest(src, src_offset, length)
    for at in range(0, length, 4 * MIB):
        m.write_at(dst, dst_offset + at, m.read_at(src, src_offset + at, min(4 * MIB, length - at)))
    flush(dst, dst_offset, length)
    m.require(m.digest(dst, dst_offset, length) == wanted, f"Readback failed: {label}")
    return wanted


def rollback_layout(pin, rows, usb_capacity):
    """Fixed area after the USB's backup GPT; nothing partitioned is inside it."""
    base = -(-pin["image_bytes"] // GIB) * GIB + GIB
    cursor, layout = base + MIB, {}
    for name in SAVED:
        length = m.extent(rows[name])[1]
        layout[name] = (cursor, length)
        cursor += -(-length // MIB) * MIB
    m.require(base >= pin["image_bytes"] + MIB, "Rollback area overlaps the USB system")
    m.require(cursor <= usb_capacity, "This USB is too small for the laptop rollback copy")
    return base, layout


def encode_header(record):
    body = json.dumps(record, sort_keys=True).encode()
    data = HEADER_MAGIC + struct.pack("<QI", record["seq"], len(body)) + body
    data += hashlib.sha256(data).digest()
    m.require(len(data) <= HEADER_BYTES, "Rollback record too large")
    return data.ljust(HEADER_BYTES, b"\0")


def decode_header(raw):
    if not raw.startswith(HEADER_MAGIC):
        return None
    at = len(HEADER_MAGIC)
    seq, size = struct.unpack_from("<QI", raw, at)
    end = at + 12 + size
    if end + 32 > len(raw) or hashlib.sha256(raw[:end]).digest() != raw[end:end + 32]:
        return None
    record = json.loads(raw[at + 12:end])
    return record if record.get("seq") == seq else None


def read_header(fd, base):
    records = [decode_header(m.read_at(fd, base + slot, HEADER_BYTES)) for slot in HEADER_SLOTS]
    records = [r for r in records if r and r.get("schema") == "openbook-ruby-laptop-rollback/1"]
    return max(records, key=lambda r: r["seq"]) if records else None


def write_header(fd, base, record):
    """Alternate slots so an interrupted record write leaves the previous one valid."""
    current = read_header(fd, base)
    record = dict(record, seq=(current["seq"] + 1) if current else 1)
    data = encode_header(record)
    offset = base + HEADER_SLOTS[record["seq"] % 2]
    m.write_at(fd, offset, data)
    flush(fd, offset, len(data))
    m.require(read_header(fd, base) == record, "Rollback record readback failed")
    return record


def table(fd):
    gpt = m.read_gpt(fd)
    return gpt, {r["name"]: r for r in gpt["rows"]}


def target_identity(gpt):
    rows = json.dumps(gpt["rows"], sort_keys=True).encode()
    return dict(disk_guid=gpt["disk_guid"], esp_partuuid=gpt["rows"][0]["partuuid"],
                gpt_rows_sha256=hashlib.sha256(rows).hexdigest())


def extract_esp(fd, row, work, label):
    esp = work / f"{label}-esp.img"
    start, length = m.extent(row)
    with esp.open("xb") as out:
        for at in range(0, length, 4 * MIB):
            out.write(m.read_at(fd, start + at, min(4 * MIB, length - at)))
    m.run("fsck.fat", "-n", esp)
    tree = work / f"{label}-esp"
    tree.mkdir()
    m.run("mcopy", "-s", "-i", esp, "::*", tree)
    return esp, tree


def files(root, skip=()):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and str(p.relative_to(root)) not in skip}


def guard_ranges(gpt, rows, capacity):
    """Everything this tool must not change, bounded for large userdata extents."""
    spans = [(0, 34 * 512), (capacity - 33 * 512, 33 * 512)]
    for name in ("misc", *BOOT, "metadata"):
        spans.append(m.extent(rows[name]))
    start, length = m.extent(rows["userdata"])
    edge = min(length, 64 * MIB)
    spans += [(start, edge), (start + length - edge, edge)]
    for name in WRITES:  # one MiB either side of each written extent
        start, length = m.extent(rows[name])
        spans += [(start - MIB, MIB), (start + length, MIB)]
    return sorted(set(spans))


def guard_hashes(fd, spans):
    return [m.digest(fd, start, length) for start, length in spans]


def check_spec(spec, pin):
    m.require(spec.get("schema") == "openbook-ruby-laptop-update/1", "Unknown laptop update record")
    m.require(spec["new"]["build"] == pin["build"] and spec["new"]["payload_readback"] == pin["payload_readback"]
              and spec["new"]["entries"] == {k: portable(v) for k, v in pin["entries"].items()},
              "Laptop update record does not match this USB's system")
    m.require(spec.get("data_compatible_rollback") is True, "Rollback data compatibility was not reviewed")
    previous = spec["previous"]
    for name in BOOT:
        m.require(previous["payload_readback"][name] == pin["payload_readback"][name],
                  f"Unsupported boot partition change: {name}")
    m.require(previous["kernel_sha256"] == pin["kernel_sha256"], "Unsupported kernel change")
    m.require(set(previous["entries"]) == set(m.MODES) == set(pin["entries"]), "Boot entry set changed")
    for mode in m.MODES:
        before, after = previous["entries"][mode], portable(pin["entries"][mode])
        m.require({k: v for k, v in before.items() if k not in DIGEST} ==
                  {k: v for k, v in after.items() if k not in DIGEST},
                  "Boot identity/security parameters changed")
        m.require(after.get("androidboot.selinux") == "enforcing"
                  and after.get("androidboot.veritymode") == "enforcing", "Requires enforcing boot")


def plan_update(usb, laptop, pin, spec, work):
    """Read-only. Returns the exact laptop writes, or state=current when already updated."""
    check_spec(spec, pin)
    usb_gpt = m.check_source(usb, pin)
    usb_rows = {r["name"]: r for r in usb_gpt["rows"]}
    gpt, rows = table(laptop)
    for name in m.NAMES[:-1]:
        m.require(m.extent(rows[name]) == m.extent(usb_rows[name]),
                  f"Unsupported laptop layout: {name}")
    m.require(m.extent(rows["userdata"])[0] == m.extent(usb_rows["userdata"])[0], "Unsupported laptop layout")
    esp, tree = extract_esp(laptop, rows["EFI"], work, "laptop")
    record = json.loads((tree / "ruby/RESEARCH.json").read_text())
    m.require(record.get("schema") == "openbook-ruby-installed/1" and record.get("same_machine_only") is True,
              "Not an installed OpenBook Googlebook laptop")
    m.require(record.get("gpt") == gpt["rows"], "Installed disk identity mismatch")
    m.require(record["kernel_sha256"] == pin["kernel_sha256"] ==
              hashlib.sha256((tree / "ruby/kernel").read_bytes()).hexdigest(), "Installed kernel mismatch")
    current = {n: m.digest(laptop, *m.extent(rows[n])) for n in m.STATIC}
    previous = spec["previous"]
    if current == pin["payload_readback"] and record["payload_readback"] == pin["payload_readback"]:
        return dict(state="current", target=target_identity(gpt))
    m.require(record["payload_readback"] == previous["payload_readback"],
              f"This laptop does not record the reviewed previous system ({previous['build']})")
    m.require(current == previous["payload_readback"],
              "Laptop system bytes differ from its record; use Restore if an update was interrupted")
    _, usb_tree = extract_esp(usb, usb_rows["EFI"], work, "usb")
    changed = {"ruby/RESEARCH.json"}
    entries = {}
    for mode in m.MODES:
        name = f"ruby/initrd-{mode}.img"
        body, params = m.parse_initrd((tree / name).read_bytes())
        expected = dict(previous["entries"][mode])
        expected.update({"androidboot.boot_part_uuid": rows["EFI"]["partuuid"],
                         "androidboot.openbook.ruby_installed": "1"})
        m.require(params == expected and portable(record["entries"][mode]) == previous["entries"][mode]
                  and record["entries"][mode] == params, "Laptop boot identity/security drift")
        new_body, new_params = m.parse_initrd((usb_tree / name).read_bytes())
        m.require(new_body == body and new_params == pin["entries"][mode], "Unreviewed initrd change")
        for key in DIGEST:
            params[key] = new_params[key]
        m.require(portable(params) == portable(new_params), "Boot parameter merge failed")
        output = work / f"initrd-{mode}.img"
        output.write_bytes(body + m.bootconfig(params, len(body)))
        m.require(m.parse_initrd(output.read_bytes()) == (body, params), "Rebuilt bootconfig mismatch")
        m.run("mcopy", "-o", "-i", esp, output, f"::/{name}")
        entries[mode] = params
        changed.add(name)
    updated = copy.deepcopy(record)
    updated["entries"] = entries
    updated["payload_readback"] = dict(pin["payload_readback"])
    updated["source_build"] = pin["build"]
    updated["system_update"] = dict(schema="openbook-ruby-laptop-update/1", previous_build=previous["build"],
                                    data_preserved=True, rollback_on_usb=True)
    manifest = work / "RESEARCH.json"
    manifest.write_text(json.dumps(updated, indent=2) + "\n")
    m.run("mcopy", "-o", "-i", esp, manifest, "::/ruby/RESEARCH.json")
    m.run("fsck.fat", "-n", esp)
    after = work / "updated-esp"
    after.mkdir()
    m.run("mcopy", "-s", "-i", esp, "::*", after)
    m.require(files(tree, changed) == files(after, changed), "Unrelated EFI files changed")
    for mode in m.MODES:
        m.require(m.parse_initrd((after / f"ruby/initrd-{mode}.img").read_bytes())[1] == entries[mode],
                  "EFI bootconfig readback failed")
    m.require(json.loads((after / "ruby/RESEARCH.json").read_text()) == updated, "EFI manifest readback failed")
    fd = os.open(esp, os.O_RDONLY)
    try:
        esp_sha = m.digest(fd, 0, m.extent(rows["EFI"])[1])
    finally:
        os.close(fd)
    writes = []
    for name in WRITES:
        start, length = m.extent(rows[name])
        source = ("file", str(esp), 0) if name == "EFI" else ("usb", None, m.extent(usb_rows[name])[0])
        sha = esp_sha if name == "EFI" else pin["payload_readback"][name]
        writes.append(dict(name=name, offset=start, length=length, source=source, sha256=sha))
    return dict(state="update", target=target_identity(gpt), previous_build=previous["build"],
                new_build=pin["build"], before={n: current[n] for n in ("super", "vbmeta_a")},
                writes=writes, static={n: current[n] for n in BOOT})


def apply_update(usb, laptop, plan, pin, before_write=None):
    """usb is opened read-write only for the rollback area beyond its partitions."""
    usb_gpt = m.read_gpt(usb)
    m.require([{k: r[k] for k in ("name", "first_lba", "last_lba", "partuuid")} for r in usb_gpt["rows"]]
              == pin["gpt"] and usb_gpt["used_bytes"] == pin["image_bytes"], "USB changed after review")
    usb_capacity, capacity = m.capacity(usb), m.capacity(laptop)
    gpt, rows = table(laptop)
    m.require(target_identity(gpt) == plan["target"], "Laptop changed after review")
    base, layout = rollback_layout(pin, rows, usb_capacity)
    edges = (m.digest(usb, 0, MIB), m.digest(usb, pin["image_bytes"] - MIB, MIB))
    previous = read_header(usb, base)
    if previous and previous.get("target") == plan["target"] and previous["state"] in ("writing", "restoring"):
        raise ValueError("An earlier operation on this laptop did not finish; use Restore first")
    record = dict(schema="openbook-ruby-laptop-rollback/1", state="saving", target=plan["target"],
                  previous_build=plan["previous_build"], new_build=plan["new_build"],
                  layout={k: list(v) for k, v in layout.items()}, static=plan["static"], saved={})
    record = write_header(usb, base, record)
    print("Saving the laptop's current system to this USB for rollback.", flush=True)
    for name in SAVED:
        start, length = m.extent(rows[name])
        record["saved"][name] = copy_range(laptop, start, usb, layout[name][0], length, f"rollback {name}")
    for name in ("super", "vbmeta_a"):
        m.require(record["saved"][name] == plan["before"][name], "Laptop changed while saving rollback")
    record = write_header(usb, base, dict(record, state="saved"))
    if before_write:
        before_write()
    spans = guard_ranges(gpt, rows, capacity)
    guard = guard_hashes(laptop, spans)
    record = write_header(usb, base, dict(record, state="writing"))
    print("Rollback saved. Updating the laptop system; keep power connected.", flush=True)
    results = []
    for w in plan["writes"]:
        kind, path, offset = w["source"]
        src = os.open(path, os.O_RDONLY) if kind == "file" else usb
        try:
            print(f"Writing {w['name']} ({w['length'] // MIB} MiB)", flush=True)
            got = copy_range(src, offset, laptop, w["offset"], w["length"], w["name"])
            m.require(got == w["sha256"], f"Unexpected payload: {w['name']}")
        finally:
            if src != usb:
                os.close(src)
        results.append(dict(name=w["name"], sha256=got))
    m.require(guard_hashes(laptop, spans) == guard, "Protected laptop bytes changed")
    m.require(m.check_source(usb, pin)["rows"] == usb_gpt["rows"]
              and edges == (m.digest(usb, 0, MIB), m.digest(usb, pin["image_bytes"] - MIB, MIB)),
              "USB system changed")
    record = write_header(usb, base, dict(record, state="updated", written=results))
    return dict(schema="openbook-ruby-laptop-update-result/1", complete=True, state="updated",
                previous_build=plan["previous_build"], new_build=plan["new_build"], writes=results,
                rollback_saved=record["saved"], protected_unchanged=True, userdata_written=False,
                credential_unlock_verified=False, boot_verified=False)


def plan_restore(usb, laptop, pin):
    m.check_source(usb, pin)
    gpt, rows = table(laptop)
    base, layout = rollback_layout(pin, rows, m.capacity(usb))
    record = read_header(usb, base)
    m.require(record is not None and record["state"] in ("saved", "writing", "updated", "restoring", "restored"),
              "This USB holds no completed rollback copy")
    m.require(record["target"] == target_identity(gpt), "The rollback copy belongs to a different laptop disk")
    m.require({k: tuple(v) for k, v in record["layout"].items()} == layout, "Rollback layout mismatch")
    for name in BOOT:
        m.require(m.digest(laptop, *m.extent(rows[name])) == record["static"][name],
                  f"Laptop boot partition changed: {name}")
    for name in SAVED:
        m.require(m.digest(usb, *layout[name]) == record["saved"][name], f"Rollback copy damaged: {name}")
    current = {n: m.digest(laptop, *m.extent(rows[n])) for n in SAVED}
    # Matching bytes after an unfinished operation still need the record closed.
    unfinished = record["state"] in ("writing", "restoring")
    state = "current" if current == record["saved"] and not unfinished else "restore"
    return dict(state=state, target=record["target"], previous_build=record["previous_build"],
                new_build=record["new_build"], record_state=record["state"])


def apply_restore(usb, laptop, plan, pin, before_write=None):
    gpt, rows = table(laptop)
    m.require(target_identity(gpt) == plan["target"], "Laptop changed after review")
    capacity = m.capacity(laptop)
    base, layout = rollback_layout(pin, rows, m.capacity(usb))
    record = read_header(usb, base)
    m.require(record and record["target"] == plan["target"], "Rollback record changed")
    if before_write:
        before_write()
    spans = guard_ranges(gpt, rows, capacity)
    guard = guard_hashes(laptop, spans)
    record = write_header(usb, base, dict(record, state="restoring"))
    for name in WRITES:
        start, length = m.extent(rows[name])
        if m.digest(laptop, start, length) == record["saved"][name]:
            continue  # already the saved bytes, e.g. interrupted before this partition
        print(f"Restoring {name} ({length // MIB} MiB)", flush=True)
        got = copy_range(usb, layout[name][0], laptop, start, length, f"restore {name}")
        m.require(got == record["saved"][name], f"Restore payload mismatch: {name}")
    m.require(guard_hashes(laptop, spans) == guard, "Protected laptop bytes changed")
    write_header(usb, base, dict(record, state="restored"))
    return dict(schema="openbook-ruby-laptop-restore-result/1", complete=True, state="restored",
                restored_build=plan["previous_build"], replaced_build=plan["new_build"],
                userdata_written=False, boot_verified=False)


def make_spec(previous_manifest, previous_build, pin, new_manifest, allow_logical):
    """Host review step: only listed framework images and the AVB root may change."""
    s = importlib.util.spec_from_file_location("preserve", HERE / "preserve-update.py")
    u = importlib.util.module_from_spec(s)
    s.loader.exec_module(u)
    m.require(new_manifest["payload_readback"] == {**new_manifest["payload_readback"], **pin["payload_readback"]},
              "Pin does not match the new system manifest")
    m.require(new_manifest["kernel_sha256"] == pin["kernel_sha256"], "Pin does not match the new system manifest")
    check = copy.deepcopy(new_manifest)
    for name in allow_logical:
        m.require(name != "vendor", "Vendor changes require a separate compatibility review")
        check["logical_sha256"][name] = previous_manifest["logical_sha256"][name]
    u.compatible(previous_manifest, check)
    m.require(previous_manifest["logical_sha256"]["vendor"] == new_manifest["logical_sha256"]["vendor"],
              "Vendor changes require a separate compatibility review")
    changed = sorted(n for n, v in new_manifest["logical_sha256"].items()
                     if previous_manifest["logical_sha256"][n] != v)
    m.require(changed == sorted(allow_logical), f"Reviewed logical changes differ: {changed}")
    spec = dict(schema="openbook-ruby-laptop-update/1",
                previous=dict(build=previous_build,
                              payload_readback={n: previous_manifest["payload_readback"][n] for n in m.STATIC},
                              entries={k: portable(v) for k, v in previous_manifest["entries"].items()},
                              kernel_sha256=previous_manifest["kernel_sha256"]),
                new=dict(build=pin["build"], payload_readback=pin["payload_readback"],
                         entries={k: portable(v) for k, v in pin["entries"].items()}),
                changed_logical=changed, data_compatible_rollback=True,
                rollback_basis="Same kernel, vendor, boot partitions, policy inputs and userdata format; "
                               "only the listed framework images and AVB metadata differ")
    check_spec(spec, pin)
    return spec


def find_usb(pin):
    found = []
    for node in Path("/sys/class/block").iterdir():
        if (node / "partition").exists() or "/usb" not in str(node.resolve()):
            continue
        path = Path("/dev") / node.name
        try:
            state = m.device_state(path, writable=True)
            fd = os.open(path, os.O_RDONLY | os.O_EXCL)
            try:
                gpt = m.read_gpt(fd)
            finally:
                os.close(fd)
            if gpt["rows"][0]["partuuid"] == pin["gpt"][0]["partuuid"]:
                state["used_bytes"] = gpt["used_bytes"]
                found.append(state)
        except (OSError, ValueError) as exc:
            print(f"USB {path.name} is not eligible: {exc}", flush=True)
    m.require(len(found) == 1, "Exactly one unmounted, writable matching OpenBook USB is required")
    return found[0]


def interactive(pin, spec, restore=False):
    verb = "RESTORE" if restore else "UPDATE"
    print("\nOPENBOOK · " + ("Restore the laptop's previous Googlebook system" if restore else
          f"Update this laptop to {pin['build']} and keep its data") + "\n", flush=True)
    print("Only the system partitions change. Accounts, apps, files, PIN and encryption keys")
    print("are on data partitions that this tool never writes.")
    print("This writes back the system saved on this USB by the last update." if restore else
          "The laptop's current system is copied to this USB first, so it can be restored.")
    print("Connect the charger. Do not remove the USB until the result is shown.")
    print("Automatic Google OS updates are NOT qualified or blocked by this tool.\n")
    product = Path("/sys/class/dmi/id/product_name").read_text().strip()
    m.require(product.startswith(pin["dmi_product_prefix"]), "This USB is pinned to a different machine profile")
    m.power_ready()
    source = find_usb(pin)
    targets = []
    for node in sorted(Path("/sys/class/block").glob("nvme*n*")):
        try:
            state = m.device_state(Path("/dev") / node.name, writable=True)
            m.target_allowed(source, state)
            targets.append(state)
        except (OSError, ValueError):
            continue
    m.require(targets, "No eligible unmounted internal NVMe disk")
    for i, row in enumerate(targets, 1):
        print(f"{i}. {row['model']} · {row['size'] / 1e9:.1f} GB · serial {row['serial']} · {row['path']}")
    answer = input("\nLaptop disk number, or Enter to cancel: ").strip()
    if not answer:
        print("Cancelled. No disks written.")
        return
    m.require(answer.isdecimal() and 1 <= int(answer) <= len(targets), "Invalid selection")
    target = targets[int(answer) - 1]
    print("\nChecking the USB and the laptop. This can take a few minutes.", flush=True)
    expected_source = {k: v for k, v in source.items() if k != "used_bytes"}
    with tempfile.TemporaryDirectory(prefix="openbook-laptop-") as tmp:
        usb = os.open(source["path"], os.O_RDWR | os.O_EXCL)
        try:
            laptop = os.open(target["path"], os.O_RDWR | os.O_EXCL)
            try:
                m.require(os.fstat(usb).st_rdev == source["rdev"] and os.fstat(laptop).st_rdev == target["rdev"],
                          "Device changed while opening")
                plan = plan_restore(usb, laptop, pin) if restore else plan_update(usb, laptop, pin, spec, Path(tmp))
                if plan["state"] == "current":
                    print("\nNothing to do: the laptop already has " +
                          (f"the saved {plan['previous_build']} system." if restore else f"{pin['build']}."))
                    return
                phrase = f"{verb} {target['serial']}"
                print(f"\nLaptop disk: {target['model']} ({target['path']}), serial {target['serial']}")
                if restore:
                    print(f"Writes back the saved {plan['previous_build']} system over {plan['new_build']}.")
                else:
                    print(f"Replaces {plan['previous_build']} with {pin['build']}: super, vbmeta_a and EFI only.")
                print("Data partitions are not written. This is not an erase.")
                if input(f"Type exactly {phrase!r} to continue, or Enter to cancel: ").strip() != phrase:
                    print("Cancelled. No disks written.")
                    return
                # Both disks stay exclusively open from review to write; recheck through
                # the same handle (device_state's own O_EXCL open would be refused).
                size = m.capacity(laptop)
                m.require(os.fstat(laptop).st_rdev == target["rdev"] and size == target["size"]
                          and m.digest(laptop, 0, MIB) + m.digest(laptop, size - MIB, MIB) == target["edge_sha256"],
                          "Laptop disk identity or partition table changed")
                if restore:
                    result = apply_restore(usb, laptop, plan, pin, before_write=m.power_ready)
                else:
                    result = apply_update(usb, laptop, plan, pin, before_write=m.power_ready)
            finally:
                os.close(laptop)
        finally:
            os.close(usb)
    print(json.dumps({k: result[k] for k in ("state", "userdata_written", "boot_verified")}))
    if restore:
        print(f"\nRESTORE VERIFIED. The laptop has its saved {plan['previous_build']} system again.", flush=True)
        print("Power off, remove the USB and start the laptop. Check your PIN, apps and files.")
    else:
        print(f"\nUPDATE VERIFIED. The laptop now has {pin['build']}; its previous system is saved on this USB.",
              flush=True)
        print("Power off, remove the USB and start the laptop. Check your PIN, apps, files and trackpad.")
        print("If it does not start or misbehaves, boot this USB and choose 'Restore previous laptop system'.")


def image_test(args, pin, spec):
    for path in (args.usb, args.laptop):
        m.require(stat.S_ISREG(path.lstat().st_mode), "Image test refuses devices and symlinks")
    args.out.mkdir(mode=0o700)
    usb = os.open(args.usb, os.O_RDWR | os.O_NOFOLLOW)
    try:
        laptop = os.open(args.laptop, os.O_RDWR | os.O_NOFOLLOW)
        try:
            if args.operation == "restore":
                plan = plan_restore(usb, laptop, pin)
                result = plan if plan["state"] == "current" else apply_restore(usb, laptop, plan, pin)
            else:
                plan = plan_update(usb, laptop, pin, spec, args.out)
                result = plan if plan["state"] == "current" else apply_update(usb, laptop, plan, pin)
        finally:
            os.close(laptop)
    finally:
        os.close(usb)
    (args.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("state",)}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="operation", required=True)
    for name in ("update", "restore"):
        q = sub.add_parser(name)
        q.add_argument("--pin", type=Path, required=True)
        q.add_argument("--spec", type=Path, required=True)
        q.add_argument("--image-test", action="store_true", help="Regular files only")
        q.add_argument("--usb", type=Path)
        q.add_argument("--laptop", type=Path)
        q.add_argument("--out", type=Path)
    s = sub.add_parser("spec")
    for name in ("previous-manifest", "new-manifest", "pin", "out"):
        s.add_argument("--" + name, type=Path, required=True)
    s.add_argument("--previous-build", required=True)
    s.add_argument("--allow-logical", action="append", default=[])
    a = p.parse_args()
    os.umask(0o077)
    if a.operation == "spec":
        m.require(not a.out.exists(), "New spec output required")
        result = make_spec(json.loads(a.previous_manifest.read_text()), a.previous_build,
                           json.loads(a.pin.read_text()), json.loads(a.new_manifest.read_text()),
                           a.allow_logical)
        a.out.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({k: result[k] for k in ("changed_logical", "data_compatible_rollback")}))
        return
    pin, spec = json.loads(a.pin.read_text()), json.loads(a.spec.read_text())
    check_spec(spec, pin)
    if a.image_test:
        m.require(a.usb and a.laptop and a.out, "Image test requires --usb, --laptop and --out")
        image_test(a, pin, spec)
        return
    m.require(not (a.usb or a.laptop or a.out), "Physical mode is interactive only")
    m.require(os.geteuid() == 0 and Path("/run/openbook-offline-installer").is_file(),
              "Physical writes require the dedicated offline USB boot")
    interactive(pin, spec, restore=a.operation == "restore")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"STOPPED: {exc}. Keep this USB. If an update was interrupted, "
                         "boot this USB and choose 'Restore previous laptop system'.")
