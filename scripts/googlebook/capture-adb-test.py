#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Device-independent failure and privacy checks for live ADB collection."""
import argparse
import importlib.util
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("capture", Path(__file__).with_name("capture-adb.py"))
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class CaptureGuards(unittest.TestCase):
    def test_explicit_endpoint_required(self):
        self.assertEqual(capture.endpoint("192.0.2.1:42747"), "192.0.2.1:42747")
        for value in ("192.0.2.1", "-e", "host:5555", "192.0.2.1:0", "192.0.2.1:65536", "192.0.2.1:5555;id"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                capture.endpoint(value)

    def test_existing_capture_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out / "keep").write_text("prior evidence")
            with self.assertRaises(FileExistsError):
                capture.collect("/does/not/exist", "192.0.2.1:5555", 5222, out)
            self.assertEqual((out / "keep").read_text(), "prior evidence")

    def test_failed_command_retains_private_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = capture.capture(out, "denied", [sys.executable, "-c",
                "import sys; print('partial'); print('Permission denied',file=sys.stderr); sys.exit(1)"])
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertIn("Permission denied", (out / "denied.stderr.txt").read_text())
            for p in out.iterdir():
                self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)

    def test_hung_client_is_reaped_and_partial_output_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            result = capture.capture(out, "hung", [sys.executable, "-u", "-c",
                "import time; print('started'); time.sleep(30)"], timeout=0.25)
            self.assertEqual(result["status"], "timeout")
            self.assertLess(result["elapsed_s"], 5)
            self.assertEqual((out / "hung.txt").read_text(), "started\n")

    def test_unconnected_device_stops_before_shell_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "capture"; adb = root / "fake-adb"
            adb.write_text("#!/bin/sh\n[ \"$5\" = get-state ] || exit 99\necho unauthorized >&2\nexit 1\n")
            adb.chmod(0o700)
            self.assertEqual(capture.collect(adb, "192.0.2.1:5555", 5222, out), 2)
            report = json.loads((out / "manifest.json").read_text())
            self.assertFalse(report["connected"])
            self.assertFalse(report["complete"])
            self.assertEqual(len(report["commands"]), 1)
            self.assertEqual(report["commands"][0]["exit_code"], 1)
            self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((out / "manifest.json").stat().st_mode), 0o600)

    def test_partial_capture_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root / "capture"; adb = root / "fake-adb"
            adb.write_text('''#!/bin/sh
[ "$1" = -P ] && [ "$2" = 5222 ] && [ "$3" = -s ] && [ "$4" = 192.0.2.1:5555 ] || exit 99
if [ "$5" = get-state ]; then echo device; exit 0; fi
[ "$5" = shell ] || exit 99
if [ "$6" = "set -e; timeout 10 dmesg" ]; then echo 'Permission denied' >&2; exit 1; fi
echo captured
''')
            adb.chmod(0o700)
            self.assertEqual(capture.collect(adb, "192.0.2.1:5555", 5222, out), 1)
            report = json.loads((out / "manifest.json").read_text())
            self.assertTrue(report["connected"])
            self.assertTrue(report["complete"])
            self.assertEqual(report["failed_sections"], ["dmesg"])
            self.assertEqual(len(report["commands"]), len(list(capture.commands())) + 1)
            self.assertFalse((out / "manifest.tmp").exists())


if __name__ == "__main__":
    unittest.main()
