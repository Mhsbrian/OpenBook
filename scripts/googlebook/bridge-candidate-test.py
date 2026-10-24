#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import unittest
import tempfile

spec = importlib.util.spec_from_file_location("builder", Path(__file__).with_name("build-bridge-candidate.py"))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
spec = importlib.util.spec_from_file_location("digitalis", Path(__file__).with_name("digitalis-overlay.py"))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


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

    def test_logical_readback_orders_non_adjacent_physical_extents(self):
        with tempfile.TemporaryDirectory() as directory:
            disk = Path(directory) / "disk.img"
            disk.write_bytes(b"a" * 512 + b"b" * 512 + b"c" * 512)
            part = {"extents": [(0, 1, 2), (1, 1, 0)], "size": 1024}
            self.assertEqual(b.hash_logical(disk, 0, part), b.hashlib.sha256(b"c" * 512 + b"a" * 512).hexdigest())

    def test_logical_readback_rejects_gaps(self):
        with tempfile.TemporaryDirectory() as directory:
            disk = Path(directory) / "disk.img"; disk.write_bytes(bytes(1024))
            with self.assertRaises(ValueError):
                b.hash_logical(disk, 0, {"extents": [(1, 1, 0)], "size": 512})

    def test_logical_readback_rejects_truncation(self):
        with tempfile.TemporaryDirectory() as directory:
            disk = Path(directory) / "disk.img"; disk.write_bytes(bytes(511))
            with self.assertRaises(ValueError):
                b.hash_logical(disk, 0, {"extents": [(0, 1, 0)], "size": 512})

    def test_digitalis_selects_matching_guest_layout(self):
        source = self.props + b"ro.berberis.version=16.0.0\n"
        result = d.properties(source)
        self.assertIn(d.NEW_BRIDGE, result)
        self.assertIn(b"ro.berberis.is_2nd_native_bridge=false\n", result)
        self.assertNotIn(b"ro.berberis.version=", result)
        self.assertTrue(result.endswith(b"ro.berberis.flags=disable-ir-check\n"))
        self.assertIn(b"other=value\n", result)

    def test_digitalis_rejects_ambiguous_bridge_selection(self):
        with self.assertRaises(ValueError): d.properties(self.props + b.OLD)

    def test_digitalis_rejects_unreviewed_runtime_flags(self):
        with self.assertRaises(ValueError): d.properties(self.props + b"ro.berberis.flags=unknown\n")

    def test_digitalis_rejects_wrong_bundle_before_filesystem_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "SHA256SUMS").write_text("0" * 64 + "  system/lib64/foreign.so\n")
            with self.assertRaises(ValueError): d.bundle_files(bundle)


if __name__ == "__main__":
    unittest.main()
