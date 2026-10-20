#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Migration integrity and failure tests on synthetic regular files only."""
import copy
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("migration", Path(__file__).with_name("migrate.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "source.img"
        with self.src.open("wb") as f:
            f.truncate(32 * m.MIB)
        args = ["sgdisk", "--clear"]
        for i, name in enumerate(m.NAMES, 1):
            args += [f"--new={i}:0:+{'16M' if i == 1 else '1M'}", f"--change-name={i}:{name}",
                     f"--typecode={i}:{'ef00' if i == 1 else '8300'}"]
        m.run(*args, self.src)
        fd = os.open(self.src, os.O_RDWR)
        try:
            self.gpt = m.read_gpt(fd)
            for i, row in enumerate(self.gpt["rows"][1:]):
                start, length = m.extent(row)
                m.write_at(fd, start, bytes([i + 33]) * length)
        finally:
            os.close(fd)
        tree = self.root / "tree"
        for name in ("EFI/BOOT", "ruby", "loader/entries", "openbook/logs"):
            (tree / name).mkdir(parents=True, exist_ok=True)
        (tree / "EFI/BOOT/BOOTX64.EFI").write_bytes(b"synthetic EFI")
        (tree / "ruby/kernel").write_bytes(b"synthetic kernel")
        (tree / "openbook/logs/old.txt").write_text("keep old logs")
        (tree / "loader/loader.conf").write_text("default openbook-a.conf\n")
        entries = {}
        for mode in m.MODES:
            params = {"androidboot.boot_part_uuid": self.gpt["rows"][0]["partuuid"],
                      "androidboot.serialno": "KEEP-ENCRYPTION-IDENTITY",
                      "androidboot.selinux": "enforcing", "androidboot.veritymode": "enforcing"}
            body = b"synthetic ramdisk"
            (tree / f"ruby/initrd-{mode}.img").write_bytes(body + m.bootconfig(params, len(body)))
            entries[mode] = params
        (tree / "ruby/RESEARCH.json").write_text("{}")
        (tree / "loader/entries/ruby-install.conf").write_text("installer")
        esp = self.root / "esp.img"
        with esp.open("wb") as f:
            f.truncate(16 * m.MIB)
        m.run("mkfs.fat", esp)
        for path in tree.iterdir():
            m.run("mcopy", "-s", "-i", esp, path, "::/")
        fd = os.open(self.src, os.O_RDWR)
        try:
            m.write_at(fd, m.extent(self.gpt["rows"][0])[0], esp.read_bytes())
            self.pin = dict(schema="openbook-ruby-migration-source/1", build="synthetic",
                            gpt=[{k: r[k] for k in ("name", "first_lba", "last_lba", "partuuid")}
                                 for r in self.gpt["rows"]],
                            image_bytes=self.src.stat().st_size, entries=entries,
                            kernel_sha256=hashlib.sha256(b"synthetic kernel").hexdigest(),
                            payload_readback={r["name"]: m.digest(fd, *m.extent(r))
                                              for r in self.gpt["rows"] if r["name"] in m.STATIC},
                            efi_sha256={str(p.relative_to(tree)): hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in (tree / "ruby").iterdir() if p.name != "RESEARCH.json"})
        finally:
            os.close(fd)
        self.before = hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.target = self.root / "target.img"
        with self.target.open("wb") as f:
            f.truncate(64 * m.MIB)
        self.work = self.root / "work"
        self.work.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def migrate(self, pin=None, expected=None, fresh=False):
        src = os.open(self.src, os.O_RDONLY)
        dst = os.open(self.target, os.O_RDWR)
        try:
            return m.migrate(src, dst, pin or self.pin, self.work, expected, fresh=fresh)
        finally:
            os.close(src)
            os.close(dst)

    def test_full_copy_preserves_state_and_rebinds_only_boot_identity(self):
        result = self.migrate()
        self.assertTrue(result["complete"])
        self.assertEqual(hashlib.sha256(self.src.read_bytes()).hexdigest(), self.before)
        src = os.open(self.src, os.O_RDONLY)
        dst = os.open(self.target, os.O_RDONLY)
        try:
            actual = m.read_gpt(dst)
            self.assertEqual(actual["used_bytes"], self.target.stat().st_size)
            for old, new in zip(self.gpt["rows"], actual["rows"]):
                self.assertNotEqual(old["partuuid"], new["partuuid"])
                self.assertEqual(m.extent(old), m.extent(new))
                if old["name"] != "EFI":
                    self.assertEqual(m.digest(src, *m.extent(old)), m.digest(dst, *m.extent(new)))
            for mode in m.MODES:
                original = self.root / f"tree/ruby/initrd-{mode}.img"
                changed = self.work / f"efi-after/ruby/initrd-{mode}.img"
                body, params = m.parse_initrd(changed.read_bytes())
                self.assertEqual(body, m.parse_initrd(original.read_bytes())[0])
                self.assertEqual(params["androidboot.boot_part_uuid"], actual["rows"][0]["partuuid"])
                self.assertEqual(params["androidboot.serialno"], "KEEP-ENCRYPTION-IDENTITY")
            self.assertFalse((self.work / "efi-after/loader/entries/ruby-install.conf").exists())
            self.assertEqual((self.work / "efi-after/openbook/logs/old.txt").read_text(), "keep old logs")
        finally:
            os.close(src)
            os.close(dst)
        check = subprocess.run(["sgdisk", "-v", str(self.target)], text=True, capture_output=True, check=True)
        self.assertIn("No problems found", check.stdout)

    def test_changed_system_refused_before_writes(self):
        pin = copy.deepcopy(self.pin)
        pin["payload_readback"]["super"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Source system changed"):
            self.migrate(pin)
        self.assertEqual(self.target.read_bytes(), bytes(self.target.stat().st_size))

    def test_changed_boot_file_refused_before_writes(self):
        pin = copy.deepcopy(self.pin)
        pin["efi_sha256"]["ruby/kernel"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Source boot file changed"):
            self.migrate(pin)
        self.assertEqual(self.target.read_bytes(), bytes(self.target.stat().st_size))

    def test_changed_data_since_confirmation_refused(self):
        with self.assertRaisesRegex(ValueError, "Source changed after confirmation"):
            self.migrate(expected="0" * 64)
        self.assertEqual(self.target.read_bytes(), bytes(self.target.stat().st_size))

    def test_smaller_target_refused(self):
        with self.target.open("wb") as f:
            f.truncate(24 * m.MIB)
        with self.assertRaisesRegex(ValueError, "too small"):
            self.migrate()
        self.assertEqual(self.target.read_bytes(), bytes(24 * m.MIB))

    def test_bad_backup_gpt_refused(self):
        with self.src.open("r+b") as f:
            f.seek(-512 + 56, os.SEEK_END)
            f.write(b"BROKEN")
        with self.assertRaisesRegex(ValueError, "CRC"):
            self.migrate()

    def test_interrupted_write_never_activates_gpt_or_changes_source(self):
        original = m.write_at
        data_start = m.extent(self.gpt["rows"][-1])[0]
        def interrupted(fd, offset, data):
            if data_start <= offset < data_start + m.MIB:
                raise OSError("simulated power cut")
            original(fd, offset, data)
        with patch.object(m, "write_at", interrupted), self.assertRaisesRegex(OSError, "power cut"):
            self.migrate()
        self.assertEqual(self.target.read_bytes()[:34 * 512], bytes(34 * 512))
        self.assertEqual(hashlib.sha256(self.src.read_bytes()).hexdigest(), self.before)

    def test_failed_readback_never_activates_gpt(self):
        original = m.digest
        def corrupt(fd, offset, length):
            if os.fstat(fd).st_ino == self.target.stat().st_ino:
                return "0" * 64
            return original(fd, offset, length)
        with patch.object(m, "digest", corrupt), self.assertRaisesRegex(ValueError, "Readback failed"):
            self.migrate()
        self.assertEqual(self.target.read_bytes()[:34 * 512], bytes(34 * 512))

    def test_source_target_alias_and_non_nvme_refused(self):
        source = dict(rdev=7, used_bytes=32 * m.MIB)
        target = dict(rdev=8, path="/dev/nvme0n1", bus_path="/pci/nvme", model="NVMe",
                      serial="target", size=64 * m.MIB)
        m.target_allowed(source, target)
        for change in (dict(rdev=7), dict(path="/dev/sda"), dict(bus_path="/usb/nvme"),
                       dict(serial=""), dict(size=m.MIB)):
            with self.subTest(change=change), self.assertRaises(ValueError):
                m.target_allowed(source, target | change)

    def test_corrupt_bootconfig_refused(self):
        data = b"body" + m.bootconfig({"a": "b"}, 4)
        with self.assertRaisesRegex(ValueError, "checksum"):
            m.parse_initrd(data[:-16] + bytes(4) + data[-12:])

    def test_power_guard_and_final_prewrite_recheck(self):
        with self.assertRaisesRegex(ValueError, "charger"):
            m.check_power([dict(type="Battery", capacity="20")])
        with self.assertRaisesRegex(ValueError, "charger"):
            m.check_power([dict(type="Battery")])
        m.check_power([dict(type="Battery", capacity="20"), dict(type="Mains", online="1")])
        m.check_power([dict(type="Battery", capacity="70")])
        m.check_power([dict(type="Battery", capacity="1", scope="Device")])
        m.check_power([])
        src, dst = os.open(self.src, os.O_RDONLY), os.open(self.target, os.O_RDWR)
        try:
            with self.assertRaisesRegex(ValueError, "charger"):
                m.migrate(src, dst, self.pin, self.work,
                          before_write=lambda: m.check_power([dict(type="Battery", capacity="10")]))
        finally:
            os.close(src); os.close(dst)
        self.assertEqual(self.target.read_bytes(), bytes(self.target.stat().st_size))

    def test_fresh_resets_old_state_and_uses_target_capacity(self):
        self.target.write_bytes(b"OLD SSD DATA" * (self.target.stat().st_size // 12) + b"\0" * 4)
        result = self.migrate(fresh=True)
        self.assertEqual(result["install_mode"], "fresh")
        self.assertLess(result["unallocated_bytes"], m.MIB)
        self.assertGreater(result["userdata_bytes"], 32 * m.MIB)
        src, dst = os.open(self.src, os.O_RDONLY), os.open(self.target, os.O_RDONLY)
        try:
            new = m.read_gpt(dst)
            for old, row in zip(self.gpt["rows"], new["rows"]):
                start, size = m.extent(row)
                if row["name"] in m.STATIC:
                    self.assertEqual(m.digest(src, *m.extent(old)), m.digest(dst, start, size))
                elif row["name"] in ("misc", "metadata"):
                    self.assertEqual(m.read_at(dst, start, size), bytes(size))
                elif row["name"] == "userdata":
                    self.assertEqual(m.read_at(dst, start, 4 * m.MIB), bytes(4 * m.MIB))
                    self.assertEqual(m.read_at(dst, start + size - 4 * m.MIB, 4 * m.MIB), bytes(4 * m.MIB))
            self.assertEqual(hashlib.sha256(self.src.read_bytes()).hexdigest(), self.before)
        finally:
            os.close(src); os.close(dst)
        record = json.loads((self.work / "efi-after/ruby/RESEARCH.json").read_text())
        self.assertTrue(record["userdata_format_on_first_boot"])
        self.assertEqual(record["userdata_bytes"], result["userdata_bytes"])

    def test_one_tb_layout_has_backup_gpt_at_end_and_full_data_extent(self):
        size = 1_000_000_000_000
        rows, headers = m.target_gpt(self.gpt, size, fresh=True)
        with self.target.open("wb") as f:
            f.truncate(size)
        fd = os.open(self.target, os.O_RDWR)
        try:
            for offset, data in headers:
                m.write_at(fd, offset, data)
            actual = m.read_gpt(fd)
        finally:
            os.close(fd)
        self.assertEqual(actual["used_bytes"], size)
        self.assertEqual(actual["rows"], rows)
        self.assertGreater(m.extent(rows[-1])[1], 990_000_000_000)
        self.assertLess(size - 33 * 512 - (rows[-1]["last_lba"] + 1) * 512, m.MIB)

    def test_fresh_requires_distinct_typed_confirmation(self):
        self.assertEqual(m.confirmation_phrase("EXACT-SERIAL", True), "FRESH ERASE EXACT-SERIAL")
        self.assertNotEqual(m.confirmation_phrase("EXACT-SERIAL"), m.confirmation_phrase("EXACT-SERIAL", True))

    def test_interrupted_fresh_reset_leaves_target_unpublished_and_source_unchanged(self):
        write = m.write_at
        data_start = m.extent(self.gpt["rows"][-1])[0]
        def interrupt(fd, offset, data):
            if offset == data_start:
                raise OSError("fresh reset interrupted")
            return write(fd, offset, data)
        with patch.object(m, "write_at", interrupt), self.assertRaisesRegex(OSError, "interrupted"):
            self.migrate(fresh=True)
        with self.target.open("rb") as f:
            self.assertEqual(f.read(34 * 512), bytes(34 * 512))
            f.seek(-33 * 512, os.SEEK_END)
            self.assertEqual(f.read(), bytes(33 * 512))
        self.assertEqual(hashlib.sha256(self.src.read_bytes()).hexdigest(), self.before)


if __name__ == "__main__":
    unittest.main()
