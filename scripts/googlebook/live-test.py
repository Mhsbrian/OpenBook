#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Safety boundaries for the local live packager; no recovery or device needed."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("live", Path(__file__).with_name("live-image.py"))
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)
spec = importlib.util.spec_from_file_location("observation", Path(__file__).with_name("run-probe.py"))
observation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observation)


class LiveGuards(unittest.TestCase):
    def test_duplicate_capture_does_not_double_count_zygote_exit(self):
        line = "init: Service 'zygote' (pid 123) received signal 9\n"
        result = observation.runtime_findings(line + line)
        self.assertEqual(result["zygote_exit_events"], 1)

    def test_init_trigger_is_not_boot_completion(self):
        for text in ("init: parsing action sys.boot_completed=1\n", "sys.boot_completed=0\n",
                     "echo OPENBOOK_RUBY_BOOT_COMPLETED=1\n"):
            self.assertFalse(observation.boot_completed_reported(text))
        for text in ("sys.boot_completed=1\n", "[sys.boot_completed]: [1]\r\n",
                     "OPENBOOK_RUBY_BOOT_COMPLETED=1\n"):
            self.assertTrue(observation.boot_completed_reported(text))

    def test_boot_uuid_replaces_pci_path_without_changing_input(self):
        conf = {"androidboot.boot_devices": "pci0000:00/0000:00:04.0",
                "androidboot.selinux": "enforcing", "androidboot.veritymode": "enforcing"}
        uuid = "14148ab8-fab4-44e6-b57d-1932fa8d3607"
        out = live.boot_parameters({"bootconfig": conf}, uuid)
        self.assertNotIn("androidboot.boot_devices", out)
        self.assertEqual(out["androidboot.boot_part_uuid"], uuid)
        self.assertIn("androidboot.boot_devices", conf)
        self.assertEqual(out["androidboot.openbook.live"], "1")

    def test_permissive_recipe_refused(self):
        with self.assertRaisesRegex(ValueError, "enforcing"):
            live.boot_parameters({"bootconfig": {"androidboot.selinux": "permissive"}},
                                 "14148ab8-fab4-44e6-b57d-1932fa8d3607")

    def test_truncated_extent_refused(self):
        with tempfile.TemporaryDirectory() as td:
            w = Path(td); (w / "source").write_bytes(b"abc")
            with self.assertRaisesRegex(ValueError, "Truncated"):
                live.copy_range(w / "source", w / "out", 0, 4)

    def test_existing_output_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            w = Path(td); (w / "source").write_bytes(b"abc"); (w / "out").write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                live.copy_range(w / "source", w / "out", 0, 3)
            self.assertEqual((w / "out").read_bytes(), b"keep")

    def test_readback_detects_corruption(self):
        with tempfile.TemporaryDirectory() as td:
            w = Path(td); (w / "payload").write_bytes(b"abc")
            (w / "disk").write_bytes(bytes(512) + b"abd")
            table = [{"name": "super", "first": 1, "last": 1, "payload": str(w / "payload")}]
            with self.assertRaisesRegex(ValueError, "Readback mismatch"):
                live.verify_payloads(w / "disk", table)

    def test_oversize_payload_refused(self):
        with tempfile.TemporaryDirectory() as td:
            w = Path(td); (w / "payload").write_bytes(bytes(513)); (w / "disk").write_bytes(bytes(2048))
            with self.assertRaisesRegex(ValueError, "exceeds"):
                live.verify_payloads(w / "disk", [{"name": "super", "first": 1, "last": 1, "payload": str(w / "payload")}])


if __name__ == "__main__":
    unittest.main()
