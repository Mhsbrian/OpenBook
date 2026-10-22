#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit checks for build-ruby-ab-super.py's geometry parser (the full build runs on real supers)."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("abs_", Path(__file__).with_name("build-ruby-ab-super.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# A trimmed real lpdump of the pristine Googlebook Ruby super.
GBOS = """Metadata version: 10.2
Metadata size: 1256 bytes
Metadata max size: 65536 bytes
Metadata slot count: 3
Header flags: virtual_ab_device
Partition table:
------------------------
  Name: system_a
  Group: google_dynamic_partitions_a
  Attributes: readonly
  Name: system_b
  Group: google_dynamic_partitions_b
  Attributes: readonly
Block device table:
------------------------
  Partition name: super
  First sector: 2048
  Size: 12884901888 bytes
  Flags: none
Group table:
------------------------
  Name: default
  Maximum size: 0 bytes
  Name: google_dynamic_partitions_a
  Maximum size: 12880707584 bytes
  Flags: none
  Name: google_dynamic_partitions_b
  Maximum size: 12880707584 bytes
  Flags: none
"""

SINGLE_SLOT = """Metadata max size: 65536 bytes
Metadata slot count: 2
Header flags: none
  Name: system_a
  Group: ruby_probe_a
  Attributes: readonly
Block device table:
  Partition name: super
  First sector: 2048
  Size: 3690987520 bytes
Group table:
  Name: ruby_probe_a
  Maximum size: 3686793216 bytes
"""


class Geometry(unittest.TestCase):
    def parse(self, text):
        with mock.patch.object(m.subprocess, "check_output", return_value=text):
            return m.read_geometry(Path("lpdump"), Path("ref"))

    def test_reads_googlebook_ab_geometry(self):
        g = self.parse(GBOS)
        self.assertEqual(g["super_size"], 12884901888)
        self.assertEqual(g["metadata_slots"], 3)
        self.assertEqual(g["metadata_size"], 65536)
        self.assertTrue(g["virtual_ab"])
        self.assertEqual(g["group"], "google_dynamic_partitions")
        self.assertEqual(g["group_max"], 12880707584)

    def test_single_slot_super_has_no_ab_group(self):
        # ruby_probe_a has no _b sibling, so the single-slot base is not a valid A/B reference.
        with self.assertRaisesRegex(ValueError, "one A/B group base"):
            self.parse(SINGLE_SLOT)

    def test_super_size_regex_spans_first_sector_line(self):
        g = self.parse(GBOS)
        self.assertEqual(g["super_size"], 12884901888)  # not the group max or a sector count


if __name__ == "__main__":
    unittest.main()
