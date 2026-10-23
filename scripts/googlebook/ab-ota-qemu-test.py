#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""ab-ota-qemu.py's slot judgement, on serial lines from real runs (2026-10-23 test update rehearsal)."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("abq", Path(__file__).with_name("ab-ota-qemu.py"))
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


class BootedSlot(unittest.TestCase):
    def test_slot_a(self):
        self.assertEqual(q.booted_slot("[ 3.1][ T1] init: [libfs_mgr] Created logical partition system_a on device /dev/block/dm-0\n"), "a")

    def test_snapshot_boot_of_slot_b(self):
        log = ("[ 3.1][ T1] init: [libfs_mgr] Created logical partition system_b-base on device /dev/block/dm-0\n"
               "[ 3.2][ T1] init: Mapped COW device for system_b at /dev/block/dm-1\n")
        self.assertEqual(q.booted_slot(log), "b")

    def test_rollback_cleanup_on_slot_a_is_not_a_slot_b_boot(self):
        log = ("[ 3.1][ T1] init: [libfs_mgr] Created logical partition system_a on device /dev/block/dm-0\n"
               "[40.0][T550] I/update_engine(  550): [INFO:snapshot.cpp(2909)] Successfully unmapped snapshot system_b\n"
               "[40.1][T550] I/update_engine(  550): [INFO:snapshot.cpp(1073)] Cow device system_b-cow not found, skipping discard\n")
        self.assertEqual(q.booted_slot(log), "a")

    def test_nothing_mapped(self):
        self.assertIsNone(q.booted_slot("[ 1.0][ T1] Linux version 6.18\n"))


if __name__ == "__main__":
    unittest.main()
