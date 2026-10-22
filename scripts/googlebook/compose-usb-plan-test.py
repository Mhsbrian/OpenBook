#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage-chain refusals of compose-usb-plan.py (the full chain is exercised on real images)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("compose", Path(__file__).with_name("compose-usb-plan.py"))
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def stages():
    system = dict(schema="openbook-ruby-preserving-update/1", complete=False, requires_installer_rebind=True,
                  reviewed_logical=["vendor_dlkm"], backup_sha256="backup", image_sha256="a", protected=[])
    installer = dict(operation="Replace", complete=True, backup_sha256="a", image_sha256="b")
    entries = dict(operation="AddBootEntries", complete=True, backup_sha256="b", image_sha256="c")
    return [system, installer, entries]


class ComposeTests(unittest.TestCase):
    def run_with(self, plans):
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "backup.img"
            backup.write_bytes(b"x")
            dirs = [Path(tmp) / f"s{i}" for i in range(len(plans))]
            with patch.object(c, "plan", side_effect=plans), patch.object(c.u.h.audit, "sha", return_value="backup"):
                return c.compose(backup, "backup", dirs, Path(tmp) / "pin.json", Path(tmp) / "out")

    def test_requires_reviewed_incomplete_system_stage_first(self):
        p = stages(); p[0]["complete"] = True
        with self.assertRaisesRegex(ValueError, "reviewed, incomplete system stage"):
            self.run_with(p)
        p = stages(); del p[0]["requires_installer_rebind"]
        with self.assertRaisesRegex(ValueError, "reviewed, incomplete system stage"):
            self.run_with(p)

    def test_system_stage_must_come_from_this_backup(self):
        p = stages(); p[0]["backup_sha256"] = "other"
        with self.assertRaisesRegex(ValueError, "not built from this backup"):
            self.run_with(p)

    def test_second_stage_must_replace_installer(self):
        p = stages(); p[1]["operation"] = "Add"
        with self.assertRaisesRegex(ValueError, "replace the installer"):
            self.run_with(p)
        with self.assertRaisesRegex(ValueError, "system stage and an installer stage"):
            self.run_with(stages()[:1])

    def test_chain_must_be_continuous_and_extras_only_add_entries(self):
        p = stages(); p[2]["backup_sha256"] = "a"
        with self.assertRaisesRegex(ValueError, "chain broken"):
            self.run_with(p)
        p = stages(); p[2]["operation"] = "Replace"
        with self.assertRaisesRegex(ValueError, "only add boot entries"):
            self.run_with(p)


if __name__ == "__main__":
    unittest.main()
