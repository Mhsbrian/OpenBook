#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""build-input-candidate.py: added files (experiments and reviewed production records) and their metadata."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("builder", Path(__file__).with_name("build-input-candidate.py"))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

EXEC = "u:object_r:openbook_updater_exec:s0"


def inode(path, mode, nlink=1, size=0):
    return f"I {path.encode().hex()} {mode} 0 0 {nlink} {size} 1230768000 0"


class AddedFiles(unittest.TestCase):
    def test_plain_bytes_are_a_0644_system_file(self):
        self.assertEqual(b.added_file(b"x"), (b"x", 0o644, b.ADDED_CONTEXT))
        self.assertIsNone(b.added_file(None))

    def test_executable_with_its_own_label(self):
        self.assertEqual(b.added_file((b"#!/system/bin/sh\n", 0o755, EXEC)), (b"#!/system/bin/sh\n", 0o755, EXEC))

    def test_unsafe_modes_and_labels_are_refused(self):
        for value in ((b"x", 0o4755, EXEC), (b"x", 0o777, EXEC), (b"x", 0o755, "u:r:openbook_updater:s0"),
                      (b"x", 0o755, "openbook_updater_exec"), ("text", 0o644, EXEC)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                b.added_file(value)


class Review(unittest.TestCase):
    ADDS = {"/system/bin/openbook-updater": (b"script", 0o755, EXEC), "/system/etc/init/openbook-updater.rc": b"rc"}

    def record(self, **override):
        listed = {"/system/bin/openbook-updater": hashlib.sha256(b"script").hexdigest(),
                  "/system/etc/init/openbook-updater.rc": hashlib.sha256(b"rc").hexdigest()}
        listed.update(override)
        return {"openbook_updater": dict(deployment_eligible=True, added_files=listed)}

    def test_no_additions_need_no_review(self):
        b.check_additions({}, {})

    def test_disposable_experiment(self):
        b.check_additions({"/system/etc/test": b"x"}, {"experimental_x": dict(deployment_eligible=False)})

    def test_production_record_listing_every_file(self):
        b.check_additions(self.ADDS, self.record())

    def test_unreviewed_additions_are_refused(self):
        cases = {"no record": {},
                 "wrong hash": self.record(**{"/system/etc/init/openbook-updater.rc": "0" * 64}),
                 "unlisted file": {"openbook_updater": dict(deployment_eligible=True, added_files={
                     "/system/bin/openbook-updater": hashlib.sha256(b"script").hexdigest()})},
                 "not deployment eligible": {"openbook_updater": dict(self.record()["openbook_updater"],
                                                                      deployment_eligible=False)}}
        for label, annotations in cases.items():
            with self.subTest(label), self.assertRaises(ValueError):
                b.check_additions(self.ADDS, annotations)

    def test_directories_are_listed_as_dir(self):
        b.check_additions({"/system/etc/openbook": None},
                          {"r": dict(deployment_eligible=True, added_files={"/system/etc/openbook": "dir"})})


class Metadata(unittest.TestCase):
    def test_rows_carry_mode_size_and_label(self):
        rows = [inode("/system/bin", 0o40755, nlink=2), inode("/system/etc", 0o40755, nlink=2)]
        out = b.addition_metadata(rows, {"/system/bin/openbook-updater": (b"script", 0o755, EXEC),
                                         "/system/etc/openbook": None})
        self.assertIn(inode("/system/bin/openbook-updater", 0o100755, size=6), out)
        self.assertIn(f"X {'/system/bin/openbook-updater'.encode().hex()} {b'security.selinux'.hex()} {EXEC.encode().hex()}", out)
        self.assertIn(inode("/system/etc", 0o40755, nlink=3), out)          # new subdirectory counted
        self.assertIn(inode("/system/etc/openbook", 0o40755, nlink=2), out)

    def test_parent_must_exist(self):
        with self.assertRaises(ValueError):
            b.addition_metadata([inode("/system", 0o40755, nlink=2)], {"/system/missing/file": b"x"})


if __name__ == "__main__":
    unittest.main()
