#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Input and output guards for the local Ruby experiment; no recovery required."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


audit = load("audit_test", "compat-audit.py")
probe = load("probe_test", "hybrid-probe.py")


class Guards(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(audit.POLICY_PROFILE.read_text())
        self.statements = "".join((r["statement"] + "\n") * r["count"] for r in self.profile["remove"])

    def test_reduction_preserves_every_unrelated_statement(self):
        other = "(neverallow alpha beta (file (write)))\n(allow gamma delta (file (read)))\n"
        self.assertEqual(audit.reduce_policy(other + self.statements, self.profile), other)

    def test_missing_grant_refuses_drift(self):
        with self.assertRaisesRegex(ValueError, "Policy drift"):
            audit.reduce_policy(self.statements.split("\n", 1)[1], self.profile)

    def test_extra_grant_refuses_drift(self):
        with self.assertRaisesRegex(ValueError, "Policy drift"):
            audit.reduce_policy(self.statements + self.profile["remove"][0]["statement"] + "\n", self.profile)

    def test_neverallow_removal_forbidden(self):
        bad = {"remove": [{"statement": "(neverallow alpha beta (file (write)))", "count": 1}]}
        with self.assertRaisesRegex(ValueError, "only remove allow"):
            audit.reduce_policy(bad["remove"][0]["statement"], bad)

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            w = Path(td); sentinel = w / "keep"; sentinel.write_text("original")
            with self.assertRaises(ValueError):
                probe.new_output(w, [])
            self.assertEqual(sentinel.read_text(), "original")

    def test_output_cannot_be_inside_source_via_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            w = Path(td); src = w / "input"; src.mkdir(); alias = w / "alias"; alias.symlink_to(src)
            with self.assertRaises(ValueError):
                probe.new_output(alias / "new", [src])
            self.assertFalse((src / "new").exists())

    def test_device_directory_refused(self):
        with self.assertRaises(ValueError):
            probe.new_output(Path("/dev/openbook-ruby-test"), [])

    def test_qemu_option_delimiter_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "delimiters"):
                probe.new_output(Path(td) / "probe,readonly=off", [])

    def test_kernel_banner_across_read_boundary(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "vmlinux"
            p.write_bytes(b"\0" * ((1 << 20) - 7) + b"Linux version 6.18.21-android17-5-example (builder)\0")
            self.assertEqual(audit.kernel_release(p), "6.18.21-android17-5-example")


if __name__ == "__main__":
    unittest.main()
