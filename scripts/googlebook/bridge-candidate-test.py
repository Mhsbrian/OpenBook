#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("builder", Path(__file__).with_name("build-bridge-candidate.py"))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.props = b"# Ruby properties\n" + b.OLD + b"ro.berberis.is_2nd_native_bridge=true\nother=value\n"

    def test_selects_shipped_translator_and_keeps_guest_layout(self):
        result = b.patch(self.props)
        self.assertIn(b.NEW, result)
        self.assertIn(b"ro.berberis.is_2nd_native_bridge=true\nother=value\n", result)
        self.assertEqual(result.replace(b.NEW, b.OLD), self.props)

    def test_duplicate_selection_rejected(self):
        with self.assertRaises(ValueError): b.patch(self.props + b.OLD)

    def test_generated_override_comment_is_preserved(self):
        comment = b"# Removed because overridden by " + b.OLD
        self.assertEqual(b.patch(comment + self.props), comment + b.patch(self.props))

    def test_different_duplicate_selection_rejected(self):
        with self.assertRaises(ValueError): b.patch(self.props + b.NEW)

    def test_applied_input_rejected(self):
        with self.assertRaises(ValueError): b.patch(b.patch(self.props))

    def test_guest_layout_flag_must_remain_enabled(self):
        with self.assertRaises(ValueError): b.patch(self.props.replace(b"=true", b"=false"))

    def test_only_expected_inode_size_changes(self):
        target = b.TARGET.encode().hex()
        rows = [f"I {target} 33188 0 0 1 100 1230768000 0", "I 2f6f74686572 33188 0 0 1 100 1230768000 0", f"X {target} 7365637572697479 00"]
        expected = [rows[0].replace(" 100 ", " 109 "), *rows[1:]]
        self.assertEqual(b.metadata_expected(rows, 9), sorted(expected))

    def test_mountpoint_label_changes_only_exact_directory(self):
        old = "u:object_r:system_lib_file:s0"
        new = "u:object_r:system_file:s0"
        def row(path):
            return f"X {path.encode().hex()} {b'security.selinux'.hex()} {old.encode().hex()}"
        rows = [row(b.MOUNTPOINT), row(b.MOUNTPOINT + "/libc.so")]
        result = b.relabel_metadata(rows, b.MOUNTPOINT, old, new)
        self.assertIn(rows[1], result)
        self.assertIn(rows[0].removesuffix(old.encode().hex()) + new.encode().hex(), result)
        with self.assertRaises(ValueError): b.relabel_metadata(result, b.MOUNTPOINT, old, new)

    def test_context_override_is_directory_only_and_not_duplicated(self):
        original = b"/system/lib(64)?(/.*)? u:object_r:system_lib_file:s0\n"
        result = b.patch_contexts(original)
        self.assertTrue(result.startswith(original))
        self.assertIn(b"/system/lib64/arm64 -d u:object_r:system_file:s0\n", result)
        with self.assertRaises(ValueError): b.patch_contexts(result)


if __name__ == "__main__":
    unittest.main()
