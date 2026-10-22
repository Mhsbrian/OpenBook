#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Unit checks for plan-ruby-ab.py."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("ab", Path(__file__).with_name("plan-ruby-ab.py"))
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)

SECTOR = ab.SECTOR


def manifest():
    sizes = {"EFI": 268435456, "misc": 4194304, "boot_a": 67108864, "init_boot_a": 8388608,
             "vendor_boot_a": 67108864, "vbmeta_a": 1048576, "metadata": 67108864,
             "super": 3690987520, "userdata": 8589934592}
    gpt, lba = [], 34
    for name, size in sizes.items():
        n = size // SECTOR
        gpt.append(dict(name=name, first_lba=lba, last_lba=lba + n - 1))
        lba += n
    return dict(image_sha256="cand", gpt=gpt, logical_sha256={k: k for k in
                ("system", "system_ext", "product", "vendor", "vendor_dlkm", "system_dlkm")})


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.m = manifest()
        self.layout = ab.plan(self.m, 1000204886016)  # a 1 TB SSD

    def test_two_slots_and_blank_b(self):
        rows = {r["name"]: r for r in self.layout["partitions"]}
        for base in ("boot", "init_boot", "vendor_boot", "vbmeta"):
            self.assertEqual(rows[f"{base}_a"]["length"], rows[f"{base}_b"]["length"])
            self.assertEqual(rows[f"{base}_a"]["source"], "candidate")
            self.assertEqual(rows[f"{base}_b"]["source"], "blank")
        self.assertEqual(rows["super"]["length"], 12 * ab.GiB)

    def test_userdata_takes_the_rest_and_grows(self):
        rows = {r["name"]: r for r in self.layout["partitions"]}
        self.assertEqual(self.layout["partitions"][-1]["name"], "userdata")
        self.assertGreater(rows["userdata"]["length"], 900 * ab.GiB)  # was ~8 GiB single-slot

    def test_validate_accepts_and_is_contiguous(self):
        self.assertTrue(ab.validate(self.layout))

    def test_disk_too_small_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Disk too small"):
            ab.plan(self.m, 20 * ab.GiB)

    def test_missing_slotted_partition_is_refused(self):
        m = manifest()
        m["gpt"] = [r for r in m["gpt"] if r["name"] != "boot_a"]
        with self.assertRaisesRegex(ValueError, "missing boot_a"):
            ab.plan(m, 1000204886016)

    def test_super_must_fit_candidate_content(self):
        m = manifest()
        big = next(r for r in m["gpt"] if r["name"] == "super")
        big["last_lba"] = big["first_lba"] + (13 * ab.GiB) // SECTOR - 1
        with self.assertRaisesRegex(ValueError, "super is smaller"):
            ab.plan(m, 1000204886016)

    def test_validate_rejects_a_gap(self):
        bad = ab.plan(self.m, 1000204886016)
        bad["partitions"][5]["offset"] += ab.MiB
        with self.assertRaisesRegex(ValueError, "gap or overlap"):
            ab.validate(bad)


if __name__ == "__main__":
    unittest.main()
