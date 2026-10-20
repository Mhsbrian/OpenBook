#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synthetic preservation/refusal tests for the disposable OTA experiment."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

s = importlib.util.spec_from_file_location("guard", Path(__file__).with_name("build-ota-guard-candidate.py"))
g = importlib.util.module_from_spec(s); s.loader.exec_module(g)
s = importlib.util.spec_from_file_location("runner", Path(__file__).with_name("ota-guard-qemu.py"))
r = importlib.util.module_from_spec(s); s.loader.exec_module(r)


class Gates(unittest.TestCase):
    def test_probe_console_interleave_and_false_passes(self):
        text = "\n".join("PASS " + name + "[  201.634075][ T2760] kernel message"
                         for name in r.EXPECTED)
        result = r.probe_checks(text)
        self.assertEqual(len(result["ipc_checks_passed"]), 24)
        self.assertFalse(result["ipc_checks_missing"])
        self.assertFalse(result["ipc_failures"])
        for text in ("I/log: PASS ordinary bind\n", "PASS ordinary bind-extra\n",
                     "PASS ordinary bind[not a kernel timestamp]\n"):
            self.assertFalse(r.probe_checks(text)["ipc_checks_passed"])
        self.assertEqual(r.probe_checks("FAIL real cleanup accepted\n")["ipc_failures"],
                         ["real cleanup accepted"])

    def row(self, name="/system/bin/update_engine", mode=0o100755, links=1):
        return f"I {name.encode().hex()} {mode} 0 2000 {links} 42 1230768000 0"

    def test_size_only_preserves_owner_mode_time_and_xattrs(self):
        row = self.row()
        attr = f"X {'/system/bin/update_engine'.encode().hex()} 01 02"
        before = sorted([row, attr, self.row("/other")])
        expected = g.b.replacement_metadata(before, {"/system/bin/update_engine": b"replacement"})
        self.assertIn(row.replace(" 42 ", " 11 "), expected)
        self.assertIn(attr, expected)
        self.assertIn(self.row("/other"), expected)
        self.assertEqual(len(expected), len(before))

    def test_identical_size_preserves_every_metadata_byte(self):
        before = [self.row()]
        self.assertEqual(g.b.replacement_metadata(before, {"/system/bin/update_engine": bytes(42)}), before)

    def test_missing_symlink_directory_and_hardlink_refused(self):
        target = {"/system/bin/update_engine": b""}
        for row in (self.row("/other"), self.row(mode=0o120777),
                    self.row(mode=0o040755), self.row(links=2)):
            with self.subTest(row=row), self.assertRaises(ValueError):
                g.b.replacement_metadata([row], target)

    def test_unknown_hash_wrong_arch_and_missing_policy_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "binary"
            data = bytearray(128)
            data[:6] = b"\x7fELF\x02\x01"; data[18:20] = b"\x3e\x00"
            path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                g.binary(path, "0" * 64)
            with self.assertRaisesRegex(ValueError, "policy"):
                g.binary(path, g.b.p.h.audit.sha(path))
            path.write_bytes(b"not an ELF")
            with self.assertRaisesRegex(ValueError, "x86_64"):
                g.binary(path, g.b.p.h.audit.sha(path))
            path.unlink(); path.symlink_to("/dev/null")
            with self.assertRaises(ValueError): g.binary(path, "0" * 64)


if __name__ == "__main__":
    unittest.main()
