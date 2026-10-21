#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Laptop update/restore integrity and failure tests on synthetic regular files only."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("laptop", Path(__file__).with_name("laptop-update.py"))
lu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lu)
m = lu.m


def sha(path, length=None):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        left = length if length is not None else os.path.getsize(path)
        while left:
            data = f.read(min(left, 4 * m.MIB))
            h.update(data)
            left -= len(data)
    return h.hexdigest()


class Disk:
    """Small Ruby-shaped USB: GPT, filled partitions and an ESP with bootconfig initrds."""

    def __init__(self, root, label, vbmeta_digest, fill):
        self.path = root / f"{label}.img"
        with self.path.open("wb") as f:
            f.truncate(32 * m.MIB)
        args = ["sgdisk", "--clear"]
        for i, name in enumerate(m.NAMES, 1):
            args += [f"--new={i}:0:+{'16M' if i == 1 else '1M'}", f"--change-name={i}:{name}",
                     f"--typecode={i}:{'ef00' if i == 1 else '8300'}"]
        m.run(*args, self.path)
        fd = os.open(self.path, os.O_RDWR)
        try:
            self.gpt = m.read_gpt(fd)
            for i, row in enumerate(self.gpt["rows"][1:]):
                start, length = m.extent(row)
                m.write_at(fd, start, bytes([fill.get(row["name"], i + 33)]) * length)
        finally:
            os.close(fd)
        tree = root / f"{label}-tree"
        for name in ("EFI/BOOT", "ruby", "loader/entries", "openbook/logs"):
            (tree / name).mkdir(parents=True, exist_ok=True)
        (tree / "EFI/BOOT/BOOTX64.EFI").write_bytes(b"synthetic EFI")
        (tree / "ruby/kernel").write_bytes(b"synthetic kernel")
        (tree / "openbook/logs/old.txt").write_text("keep old logs")
        (tree / "loader/loader.conf").write_text("default openbook-a.conf\n")
        self.entries = {}
        for mode in m.MODES:
            params = {"androidboot.boot_part_uuid": self.gpt["rows"][0]["partuuid"],
                      "androidboot.serialno": "KEEP-ENCRYPTION-IDENTITY",
                      "androidboot.selinux": "enforcing", "androidboot.veritymode": "enforcing",
                      "androidboot.vbmeta.digest": vbmeta_digest, "androidboot.vbmeta.size": "4032"}
            body = b"synthetic ramdisk " + mode.encode()
            (tree / f"ruby/initrd-{mode}.img").write_bytes(body + m.bootconfig(params, len(body)))
            self.entries[mode] = params
        (tree / "ruby/RESEARCH.json").write_text("{}")
        esp = root / f"{label}-esp.img"
        with esp.open("wb") as f:
            f.truncate(16 * m.MIB)
        m.run("mkfs.fat", esp)
        for path in tree.iterdir():
            m.run("mcopy", "-s", "-i", esp, path, "::/")
        fd = os.open(self.path, os.O_RDWR)
        try:
            m.write_at(fd, m.extent(self.gpt["rows"][0])[0], esp.read_bytes())
            self.pin = dict(schema="openbook-ruby-migration-source/1", build=label,
                            dmi_product_prefix="ROG Zephyrus G14 GA403WR",
                            gpt=[{k: r[k] for k in ("name", "first_lba", "last_lba", "partuuid")}
                                 for r in self.gpt["rows"]],
                            image_bytes=32 * m.MIB, entries=self.entries,
                            kernel_sha256=hashlib.sha256(b"synthetic kernel").hexdigest(),
                            payload_readback={r["name"]: m.digest(fd, *m.extent(r))
                                              for r in self.gpt["rows"] if r["name"] in m.STATIC},
                            efi_sha256={str(p.relative_to(tree)): hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in (tree / "ruby").iterdir() if p.name != "RESEARCH.json"})
        finally:
            os.close(fd)


class LaptopUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old = Disk(self.root, "camera25", "a" * 64, {})
        self.new = Disk(self.root, "rb01", "b" * 64, {"super": 0x51, "vbmeta_a": 0x52})
        self.laptop = self.install(self.old, "laptop")
        self.laptop_sha = sha(self.laptop)
        with self.new.path.open("r+b") as f:
            f.truncate(3 * lu.GIB)  # sparse room for the rollback area after the 32 MiB system
        self.usb_system_sha = sha(self.new.path, self.new.pin["image_bytes"])
        self.spec = dict(schema="openbook-ruby-laptop-update/1",
                         previous=dict(build="camera25",
                                       payload_readback=dict(self.old.pin["payload_readback"]),
                                       entries={k: lu.portable(v) for k, v in self.old.entries.items()},
                                       kernel_sha256=self.old.pin["kernel_sha256"]),
                         new=dict(build="rb01", payload_readback=self.new.pin["payload_readback"],
                                  entries={k: lu.portable(v) for k, v in self.new.entries.items()}),
                         changed_logical=["system"], data_compatible_rollback=True)
        # Boot partitions are unchanged between the two systems in the real pair.
        self.align_boot()

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, disk, label):
        work = self.root / f"{label}-work"
        work.mkdir()
        target = self.root / f"{label}.img"
        src = os.open(disk.path, os.O_RDONLY)
        dst = os.open(target, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.ftruncate(dst, 64 * m.MIB)
            m.migrate(src, dst, disk.pin, work)
            gpt = m.read_gpt(dst)
            start, length = m.extent(next(r for r in gpt["rows"] if r["name"] == "userdata"))
            m.write_at(dst, start, b"OWNER DATA MUST SURVIVE" * 100)
        finally:
            os.close(src)
            os.close(dst)
        return target

    def align_boot(self):
        """Make the new USB's boot partitions match the installed laptop's, as in RB01."""
        src = os.open(self.old.path, os.O_RDONLY)
        dst = os.open(self.new.path, os.O_RDWR)
        try:
            for name in lu.BOOT:
                row = next(r for r in self.old.gpt["rows"] if r["name"] == name)
                m.write_at(dst, m.extent(row)[0], m.read_at(src, *m.extent(row)))
                self.new.pin["payload_readback"][name] = m.digest(dst, *m.extent(row))
                self.spec["previous"]["payload_readback"][name] = self.new.pin["payload_readback"][name]
        finally:
            os.close(src)
            os.close(dst)
        self.spec["new"]["payload_readback"] = dict(self.new.pin["payload_readback"])
        self.usb_system_sha = sha(self.new.path, self.new.pin["image_bytes"])

    def run_op(self, operation, laptop=None, spec=None, usb=None, label=None):
        out = self.root / (label or f"{operation}-{len(list(self.root.glob(operation + '-*')))}")
        usb_fd = os.open(usb or self.new.path, os.O_RDWR)
        lap = os.open(laptop or self.laptop, os.O_RDWR)
        try:
            if operation == "update":
                out.mkdir()
                plan = lu.plan_update(usb_fd, lap, self.new.pin, spec or self.spec, out)
                return plan if plan["state"] == "current" else lu.apply_update(usb_fd, lap, plan, self.new.pin)
            plan = lu.plan_restore(usb_fd, lap, self.new.pin)
            return plan if plan["state"] == "current" else lu.apply_restore(usb_fd, lap, plan, self.new.pin)
        finally:
            os.close(usb_fd)
            os.close(lap)

    def rows(self, path):
        fd = os.open(path, os.O_RDONLY)
        try:
            return {r["name"]: r for r in m.read_gpt(fd)["rows"]}
        finally:
            os.close(fd)

    def range_sha(self, path, row):
        fd = os.open(path, os.O_RDONLY)
        try:
            return m.digest(fd, *m.extent(row))
        finally:
            os.close(fd)

    def esp_tree(self, path, label):
        rows = self.rows(path)
        esp = self.root / f"{label}.esp"
        start, length = m.extent(rows["EFI"])
        with open(path, "rb") as f, esp.open("wb") as out:
            f.seek(start)
            out.write(f.read(length))
        tree = self.root / f"{label}-esp-tree"
        tree.mkdir()
        m.run("mcopy", "-s", "-i", esp, "::*", tree)
        return tree

    def test_update_then_restore_is_byte_exact_and_keeps_data(self):
        before_rows = self.rows(self.laptop)
        keep = {n: self.range_sha(self.laptop, before_rows[n])
                for n in ("misc", *lu.BOOT, "metadata", "userdata")}
        result = self.run_op("update")
        self.assertEqual(result["state"], "updated")
        rows = self.rows(self.laptop)
        self.assertEqual(rows, before_rows)
        for name in ("super", "vbmeta_a"):
            self.assertEqual(self.range_sha(self.laptop, rows[name]), self.new.pin["payload_readback"][name])
        for name, digest in keep.items():
            self.assertEqual(self.range_sha(self.laptop, rows[name]), digest, name)
        tree = self.esp_tree(self.laptop, "updated")
        for mode in m.MODES:
            _, params = m.parse_initrd((tree / f"ruby/initrd-{mode}.img").read_bytes())
            self.assertEqual(params["androidboot.vbmeta.digest"], "b" * 64)
            self.assertEqual(params["androidboot.boot_part_uuid"], rows["EFI"]["partuuid"])
            self.assertEqual(params["androidboot.openbook.ruby_installed"], "1")
            self.assertEqual(params["androidboot.serialno"], "KEEP-ENCRYPTION-IDENTITY")
        record = json.loads((tree / "ruby/RESEARCH.json").read_text())
        self.assertEqual(record["payload_readback"], self.new.pin["payload_readback"])
        self.assertEqual(record["system_update"]["previous_build"], "camera25")
        self.assertEqual((tree / "openbook/logs/old.txt").read_text(), "keep old logs")
        self.assertEqual(sha(self.new.path, self.new.pin["image_bytes"]), self.usb_system_sha)
        self.assertEqual(self.run_op("update")["state"], "current")
        restored = self.run_op("restore")
        self.assertEqual(restored["state"], "restored")
        self.assertEqual(sha(self.laptop), self.laptop_sha)
        self.assertEqual(self.run_op("restore")["state"], "current")
        self.assertEqual(sha(self.new.path, self.new.pin["image_bytes"]), self.usb_system_sha)

    def test_update_after_restore_and_newer_data_is_allowed(self):
        self.run_op("update")
        rows = self.rows(self.laptop)
        with open(self.laptop, "r+b") as f:  # the newer system used the data partition
            f.seek(m.extent(rows["userdata"])[0] + 4096)
            f.write(b"written by the newer system")
        self.run_op("restore")
        self.assertEqual(self.run_op("update")["state"], "updated")

    def test_refuses_laptop_bytes_that_differ_from_record(self):
        rows = self.rows(self.laptop)
        with open(self.laptop, "r+b") as f:
            f.seek(m.extent(rows["super"])[0])
            f.write(b"unexpected")
        with self.assertRaisesRegex(ValueError, "differ from its record"):
            self.run_op("update")

    def test_refuses_unreviewed_previous_system(self):
        spec = copy.deepcopy(self.spec)
        spec["previous"]["payload_readback"]["super"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "reviewed previous system"):
            self.run_op("update", spec=spec)

    def test_refuses_boot_security_drift(self):
        spec = copy.deepcopy(self.spec)
        for mode in m.MODES:
            spec["previous"]["entries"][mode]["androidboot.selinux"] = "permissive"
        with self.assertRaisesRegex(ValueError, "Boot identity/security"):
            self.run_op("update", spec=spec)

    def test_refuses_spec_for_another_usb_system(self):
        spec = copy.deepcopy(self.spec)
        spec["new"]["build"] = "other"
        with self.assertRaisesRegex(ValueError, "does not match this USB"):
            self.run_op("update", spec=spec)

    def test_refuses_boot_partition_change(self):
        spec = copy.deepcopy(self.spec)
        spec["previous"]["payload_readback"]["boot_a"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Unsupported boot partition change"):
            self.run_op("update", spec=spec)

    def test_interrupted_write_requires_restore_then_restores_exactly(self):
        original = lu.copy_range

        def failing(src, src_offset, dst, dst_offset, length, label):
            if label == "super":
                m.write_at(dst, dst_offset, b"\xff" * (length // 2))
                raise OSError("simulated power loss")
            return original(src, src_offset, dst, dst_offset, length, label)

        with patch.object(lu, "copy_range", failing), self.assertRaisesRegex(OSError, "power loss"):
            self.run_op("update")
        self.assertNotEqual(sha(self.laptop), self.laptop_sha)
        with self.assertRaisesRegex(ValueError, "differ from its record"):
            self.run_op("update")
        self.assertEqual(self.run_op("restore")["state"], "restored")
        self.assertEqual(sha(self.laptop), self.laptop_sha)
        self.assertEqual(self.run_op("update")["state"], "updated")

    def test_unfinished_operation_blocks_a_new_update(self):
        self.run_op("update")
        self.run_op("restore")
        usb = os.open(self.new.path, os.O_RDWR)
        try:
            base, _ = lu.rollback_layout(self.new.pin, self.rows(self.laptop), m.capacity(usb))
            record = lu.read_header(usb, base)
            lu.write_header(usb, base, dict(record, state="writing"))
        finally:
            os.close(usb)
        with self.assertRaisesRegex(ValueError, "use Restore first"):
            self.run_op("update")
        self.assertEqual(sha(self.laptop), self.laptop_sha)
        self.assertEqual(self.run_op("restore")["state"], "restored")  # closes the record, no laptop writes
        self.assertEqual(sha(self.laptop), self.laptop_sha)
        self.assertEqual(self.run_op("update")["state"], "updated")

    def test_damaged_rollback_copy_is_refused(self):
        self.run_op("update")
        usb = os.open(self.new.path, os.O_RDWR)
        try:
            base, layout = lu.rollback_layout(self.new.pin, self.rows(self.laptop), m.capacity(usb))
            m.write_at(usb, layout["super"][0], b"corrupt")
        finally:
            os.close(usb)
        updated = sha(self.laptop)
        with self.assertRaisesRegex(ValueError, "Rollback copy damaged: super"):
            self.run_op("restore")
        self.assertEqual(sha(self.laptop), updated)

    def test_restore_refuses_a_different_laptop(self):
        self.run_op("update")
        other = self.install(self.old, "other-laptop")
        before = sha(other)
        with self.assertRaisesRegex(ValueError, "different laptop disk"):
            self.run_op("restore", laptop=other)
        self.assertEqual(sha(other), before)

    def test_small_usb_is_refused_before_any_write(self):
        small = self.root / "small.img"
        with self.new.path.open("rb") as f, small.open("wb") as out:
            out.write(f.read(self.new.pin["image_bytes"]))
        with self.assertRaisesRegex(ValueError, "too small"):
            self.run_op("update", usb=small)
        self.assertEqual(sha(self.laptop), self.laptop_sha)

    def test_header_falls_back_to_previous_slot(self):
        self.run_op("update")
        usb = os.open(self.new.path, os.O_RDWR)
        try:
            base, _ = lu.rollback_layout(self.new.pin, self.rows(self.laptop), m.capacity(usb))
            latest = lu.read_header(usb, base)
            m.write_at(usb, base + lu.HEADER_SLOTS[latest["seq"] % 2] + 100, b"torn")
            fallback = lu.read_header(usb, base)
        finally:
            os.close(usb)
        self.assertEqual(fallback["seq"], latest["seq"] - 1)
        self.assertEqual(fallback["state"], "writing")

    def test_guard_detects_stray_write(self):
        original = lu.copy_range

        def stray(src, src_offset, dst, dst_offset, length, label):
            got = original(src, src_offset, dst, dst_offset, length, label)
            if label == "EFI":
                rows = self.rows(self.laptop)
                m.write_at(dst, m.extent(rows["metadata"])[0], b"stray")
            return got

        with patch.object(lu, "copy_range", stray), self.assertRaisesRegex(ValueError, "Protected laptop bytes"):
            self.run_op("update")
        self.assertEqual(self.run_op("restore")["state"], "restored")

    def test_usb_partitions_are_never_written(self):
        self.run_op("update")
        self.run_op("restore")
        self.assertEqual(sha(self.new.path, self.new.pin["image_bytes"]), self.usb_system_sha)

    def test_image_test_rejects_block_devices(self):
        class Args:
            usb = Path("/dev/null")
            laptop = self.laptop
            out = self.root / "refused"
            operation = "update"
        with self.assertRaisesRegex(ValueError, "refuses devices"):
            lu.image_test(Args, self.new.pin, self.spec)


if __name__ == "__main__":
    unittest.main()
