#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Ensure icing-probe decoding cannot turn missing or wrong results into a pass."""
import importlib.util
import os
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("probe", Path(__file__).with_name("icing-probe.py"))
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

OK = probe.field(1, probe.field(1, 1))


def search_result(uris, code=1):
    return probe.field(1, probe.field(1, code)) + b"".join(
        probe.field(2, probe.field(1, probe.field(2, u))) for u in uris)


def run(records):
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        for kind, body in records:
            f.write(kind.encode() + struct.pack("<i", -1 if body is None else len(body)) + (body or b""))
    try:
        return probe.decode(f.name)
    finally:
        os.unlink(f.name)


def good(override=None):
    queries = [search_result(sorted(probe.expected(q))) for q in probe.QUERIES]
    records = [("I", OK), ("S", OK)] + [("P", OK)] * probe.DOCS
    records += [("Q", q) for q in queries] + [("F", OK), ("J", OK)] + [("K", q) for q in queries]
    return override(records) if override else records


class DecodeTests(unittest.TestCase):
    def test_complete_expected_run_passes(self):
        self.assertTrue(run(good())["pass"])

    def test_missing_result_fails(self):
        self.assertFalse(run(good(lambda r: r[:-1]))["pass"])

    def test_null_result_fails(self):
        self.assertFalse(run(good(lambda r: r[:2] + [("P", None)] + r[3:]))["pass"])

    def test_wrong_matches_fail(self):
        first_query = 2 + probe.DOCS
        self.assertFalse(run(good(lambda r: r[:first_query] + [("Q", search_result(["setting/0"]))] + r[first_query + 1:]))["pass"])

    def test_failed_put_status_fails(self):
        out = run(good(lambda r: r[:2] + [("P", probe.field(1, probe.field(1, 7)))] + r[3:]))
        self.assertFalse(out["pass"])
        self.assertEqual(out["puts"]["other"], {"INTERNAL": 1})

    def test_failed_restart_fails(self):
        self.assertFalse(run(good(lambda r: [x if x[0] != "J" else ("J", probe.field(1, probe.field(1, 2))) for x in r]))["pass"])

    def test_expected_model_covers_empty_and_and_queries(self):
        self.assertEqual(probe.expected("nonexistentzz"), set())
        self.assertEqual(probe.expected("display brightness"), set())
        self.assertGreater(len(probe.expected("disp")), 0)
        self.assertEqual(probe.expected("disp"), probe.expected("display"))


if __name__ == "__main__":
    unittest.main()
