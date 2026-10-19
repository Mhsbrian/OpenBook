#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Synthetic inputs only. Tests cannot make the shipping profile installable."""
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("preflight", Path(__file__).with_name("recovery-preflight.py"))
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "recovery"
        self.data = b"synthetic recovery, no Google payload"
        self.path.write_bytes(self.data)
        self.profile = dict(id="fixture", build="fixture", raw_bytes=len(self.data),
                            raw_sha256=hashlib.sha256(self.data).hexdigest(),
                            zip_sha256=hashlib.sha256(self.data).hexdigest(),
                            official_zip_md5=hashlib.md5(self.data).hexdigest(), blockers=["fixture"])

    def test_match_never_authorizes_install(self):
        self.profile["installable"] = True
        for kind in ("raw", "zip"):
            result = preflight.inspect(self.path, kind, self.profile)
            self.assertTrue(result["matched"])
            self.assertFalse(result["installable"])
        self.assertEqual(self.path.read_bytes(), self.data)

    def test_changed_content(self):
        self.path.write_bytes(b"x" * len(self.data))
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            preflight.inspect(self.path, "raw", self.profile)

    def test_wrong_size(self):
        self.path.write_bytes(b"short")
        with self.assertRaisesRegex(ValueError, "size"):
            preflight.inspect(self.path, "raw", self.profile)

    def test_zip_official_manifest_mismatch(self):
        self.profile["official_zip_md5"] = "0" * 32
        with self.assertRaisesRegex(ValueError, "MD5"):
            preflight.inspect(self.path, "zip", self.profile)

    def test_symlink(self):
        alias = self.path.with_name("link")
        alias.symlink_to(self.path)
        with self.assertRaises(OSError):
            preflight.inspect(alias, "raw", self.profile)

    def test_fifo_does_not_block(self):
        fifo = self.path.with_name("fifo")
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, "regular"):
            preflight.inspect(fifo, "raw", self.profile)

    def test_device(self):
        with self.assertRaisesRegex(ValueError, "regular"):
            preflight.inspect("/dev/null", "raw", self.profile)


if __name__ == "__main__":
    unittest.main()
