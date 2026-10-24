#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Ensure diagnostics cannot turn missing/unrelated evidence into a search pass."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("search", Path(__file__).with_name("settings-search.py"))
search = importlib.util.module_from_spec(spec)
spec.loader.exec_module(search)


def crash(package=search.PACKAGE, pid=12024):
    prefix = f"10-21 07:35:28.928 {pid:5} 12238 E AndroidRuntime: "
    return (prefix + f"Process: {package}, PID: {pid}\n" + prefix +
            'java.lang.UnsatisfiedLinkError: dlopen failed: "apk!/lib/arm64-v8a/libicing.so" '
            'is for EM_AARCH64 (183) instead of EM_X86_64 (62)\n')


class AnalyzeTests(unittest.TestCase):
    def test_historical_permission_error_does_not_fail_capture(self):
        self.assertFalse(search.command_denied(b"10-21 07:34:51.755 12024 12024 E AndroidRuntime: java.lang.SecurityException: Permission denied"))

    def test_command_denial_is_detected(self):
        self.assertTrue(search.command_denied(b"Permission Denial: cannot dump service\n"))

    def test_record_and_deduplicate_crash(self):
        result = search.analyze([crash(), crash()])
        self.assertEqual(len(result["settings_search_icing_architecture_crashes"]), 1)
        self.assertFalse(result["fix_validated"])

    def test_empty_is_inconclusive(self):
        self.assertEqual(search.analyze([""])["diagnosis"], "inconclusive")

    def test_other_app_same_library_is_not_search(self):
        self.assertEqual(search.analyze([crash("example.other")])["diagnosis"], "inconclusive")

    def test_unidentified_library_error_is_inconclusive(self):
        self.assertEqual(search.analyze([crash().splitlines()[1]])["diagnosis"], "inconclusive")

    def test_same_pid_other_time_is_not_attributed(self):
        rows = crash().splitlines()
        rows[1] = rows[1].replace("07:35:28.928", "08:00:00.000")
        self.assertEqual(search.analyze(["\n".join(rows)])["diagnosis"], "inconclusive")

    def test_bridge_failure_without_crash_is_inconclusive(self):
        result = search.analyze(["10-21 07:34:51.755 12024 12024 I houdini : [12024] Initialize library(version: test)... failed(0x00010002)."])
        self.assertEqual(result["diagnosis"], "inconclusive")
        self.assertEqual(len(result["houdini_initialization_failures_all_processes"]), 1)

    def test_successful_bridge_line_is_not_failure(self):
        result = search.analyze(["10-21 07:34:51.755 12024 12024 I houdini : [12024] Initialize library(version: test)... done."])
        self.assertEqual(result["houdini_initialization_failures_all_processes"], [])


if __name__ == "__main__":
    unittest.main()
