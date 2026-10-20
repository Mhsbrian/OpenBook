#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Failure guards for preserving a configured research USB; no devices needed."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("update", Path(__file__).with_name("preserve-update.py"))
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
spec = importlib.util.spec_from_file_location("apply_update", Path(__file__).with_name("apply-preserved-update.py"))
applier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(applier)


class PreserveGuards(unittest.TestCase):
    def test_apply_plan_cannot_target_userdata_or_omit_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); backup, gpt = self.disk(root)
            prepared = root / "prepared"; prepared.mkdir()
            image = prepared / "ruby-live.img"; image.write_bytes(backup.read_bytes())
            plan = dict(schema="openbook-ruby-preserving-update/1", complete=True,
                        backup_sha256=u.h.audit.sha(backup), image_sha256=u.h.audit.sha(image),
                        writes=[dict(name=r['name'], offset=u.extent(r)[0], length=u.extent(r)[1],
                                     sha256=u.digest_range(image, *u.extent(r)))
                                for r in gpt.table() if r['name'] in u.WRITABLE],
                        protected=[dict(offset=a, length=b, sha256=u.digest_range(backup, a, b))
                                   for a, b in u.protected_ranges(gpt.table(), gpt.total)])
            (prepared / "update.json").write_text(json.dumps(plan))
            applier.validate_plan(prepared, backup)
            bad = copy.deepcopy(plan); bad["writes"][0]["name"] = "userdata"
            (prepared / "update.json").write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "Only"):
                applier.validate_plan(prepared, backup)
            bad = copy.deepcopy(plan); bad["writes"][0]["offset"] = 0
            (prepared / "update.json").write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "outside"):
                applier.validate_plan(prepared, backup)
            bad = copy.deepcopy(plan); bad["protected"].pop()
            (prepared / "update.json").write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "coverage"):
                applier.validate_plan(prepared, backup)

    def test_apply_ranges_preserve_surrounding_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / "source"; target = root / "target"
            source.write_bytes(bytes(range(256)) * 32)
            original = b"P" * 8192; target.write_bytes(original)
            rows = [dict(name=name, offset=offset, length=512)
                    for name, offset in (("EFI", 512), ("vbmeta_a", 3072), ("super", 4096))]
            applier.write_ranges(source, target, rows)
            expected = bytearray(original)
            for row in rows:
                a, b = row["offset"], row["offset"] + row["length"]
                expected[a:b] = source.read_bytes()[a:b]
            self.assertEqual(target.read_bytes(), expected)

    def test_physical_apply_rejects_unnamed_or_regular_device(self):
        for path in ("/dev/sda", "/dev/nvme0n1", "/tmp/test", "/dev/disk/by-id/usb-fake-part1"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                applier.device_info(Path(path))

    def disk(self, root):
        gpt = u.h.gpt.Gpt([(n, 1 << 20, u.h.gpt.LINUX_DATA, None)
                          for n in ("EFI", *u.live.NAMES)], "synthetic-preservation-test")
        path = root / "disk.img"
        gpt.write(str(path))
        return path, gpt

    def test_devices_and_symlinks_refused(self):
        with self.assertRaisesRegex(ValueError, "regular"):
            u.regular(Path("/dev/null"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); src = root / "source"; src.write_bytes(b"keep")
            link = root / "link"; link.symlink_to(src)
            with self.assertRaisesRegex(ValueError, "regular"):
                u.regular(link)

    def test_both_gpt_copies_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, gpt = self.disk(Path(tmp))
            self.assertEqual(u.read_gpt(path), gpt.table())
            for offset in (512 + 56, path.stat().st_size - 512 + 56, 1024 + 100,
                           path.stat().st_size - 33 * 512 + 100):
                gpt.write(str(path))
                with path.open("r+b") as f:
                    f.seek(offset); f.write(b"BROKEN")
                with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, "CRC"):
                    u.read_gpt(path)

    def test_gpt_cannot_be_relocated_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = self.disk(Path(tmp))
            with path.open("ab") as f:
                f.write(bytes(512))
            with self.assertRaisesRegex(ValueError, "location"):
                u.read_gpt(path)

    def test_truncated_range_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data"; path.write_bytes(b"abc")
            with self.assertRaisesRegex(ValueError, "Truncated"):
                u.digest_range(path, 1, 3)

    def test_every_byte_outside_three_allowed_partitions_is_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, gpt = self.disk(Path(tmp))
            spans = list(u.protected_ranges(gpt.table(), gpt.total))
            writable = [u.extent(row) for row in gpt.table() if row["name"] in u.WRITABLE]
            cursor = 0
            for start, length in sorted(spans + writable):
                self.assertEqual(start, cursor)
                cursor += length
            self.assertEqual(cursor, gpt.total)
            for row in gpt.table():
                if row["name"] not in u.WRITABLE:
                    start, length = u.extent(row)
                    self.assertTrue(any(a <= start and start + length <= a + b for a, b in spans))

    def manifest(self):
        params = {"androidboot.boot_part_uuid": "old", "androidboot.vbmeta.digest": "old",
                  "androidboot.selinux": "enforcing", "androidboot.veritymode": "enforcing",
                  "androidboot.serialno": "identity"}
        return dict(gpt=[], kernel_sha256="kernel", vendor_cmdline="cmd",
                    logical_sha256=dict(system="framework", vendor="vendor", system_dlkm="modules"),
                    payload_readback={n: n for n in u.BOOT},
                    entries={mode: dict(params) for mode in ("live", "logs", "safe-logs", "serial", "serial-logs")})

    def test_framework_identity_and_enforcement_changes_refused(self):
        old = self.manifest()
        for section, key, value in (("logical_sha256", "system", "new"),
                                    ("logical_sha256", "system_dlkm", "new"),
                                    ("payload_readback", "boot_a", "new"),
                                    ("live", "androidboot.serialno", "new"),
                                    ("logs", "androidboot.selinux", "permissive")):
            new = copy.deepcopy(old)
            target = new["entries"][section] if section in new["entries"] else new[section]
            target[key] = value
            with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                u.compatible(old, new)
        new = copy.deepcopy(old); new["logical_sha256"]["vendor"] = "new"
        for entry in new["entries"].values():
            entry["androidboot.vbmeta.digest"] = "new"
            entry["androidboot.boot_part_uuid"] = "new"
        u.compatible(old, new)

    def test_bootconfig_rebind_retains_ramdisk(self):
        body = b"not-a-real-ramdisk" * 100
        data = body + u.h.gpt.bootconfig_trailer("androidboot.boot_part_uuid = original\n", len(body))
        retained, conf = u.split_initrd(data)
        self.assertEqual(retained, body)
        self.assertEqual(conf["androidboot.boot_part_uuid"], "original")
        conf["androidboot.boot_part_uuid"] = "preserved"
        rebuilt = body + u.h.gpt.bootconfig_trailer(u.h.bc.render(conf).decode(), len(body))
        self.assertEqual(u.split_initrd(rebuilt), (body, conf))
        with self.assertRaises(ValueError):
            u.split_initrd(data[:-20] + struct.pack("<I", 0xffffffff) + data[-16:])
        with self.assertRaises(ValueError):
            u.split_initrd(data[:-21] + b"X" + data[-20:])


if __name__ == "__main__":
    unittest.main()
