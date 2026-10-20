#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("report", Path(__file__).with_name("audio-report.py"))
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class Report(unittest.TestCase):
    def rows(self):
        return [{"schema": "openbook-audio-diagnostic/1", "elapsed_ms": 0, "event": "start"},
                {"elapsed_ms": 5, "event": "sample", "bluetooth_permission": True, "mode": 0,
                 "devices": [{"type": "bluetooth_a2dp"}],
                 "available_communication_devices": [{"type": "speaker"}],
                 "profiles": [{"profile": "HFP", "connection_state": 2, "audio_connected_count": 0}],
                 "recording_metadata_visible_to_app": [
                     {"device": {"type": "built_in_mic"}, "silenced": False}]}]

    def test_connected_hfp_is_not_open_audio(self):
        s = report.summarize(self.rows())
        self.assertEqual(s["profiles"]["HFP"]["connection_states_observed"], [2])
        self.assertEqual(s["profiles"]["HFP"]["audio_connected_counts_observed"], [0])
        self.assertTrue(s["no_bluetooth_communication_route_observed"])
        self.assertEqual(s["recording_device_types_observed"], ["built_in_mic"])

    def test_transition_to_headset_is_not_missing(self):
        rows = self.rows()
        rows[-1]["available_communication_devices"].append({"type": "bluetooth_sco"})
        self.assertFalse(report.summarize(rows)["no_bluetooth_communication_route_observed"])

    def test_denied_or_error_is_not_disconnected(self):
        rows = self.rows()
        rows[-1]["bluetooth_permission"] = False
        s = report.summarize(rows)
        self.assertEqual(s["profiles"]["HFP"]["connection_states_observed"], [])
        rows[-1]["access_error"] = "SecurityException"
        self.assertIsNone(report.summarize(rows)["no_bluetooth_communication_route_observed"])

    def test_no_raw_identifiers_are_forwarded(self):
        rows = self.rows()
        rows[-1].update(device_address="SECRET", build="SECRET", utc_ms="SECRET")
        rows[-1]["devices"].append({"type": "SECRET", "id": "SECRET", "name": "SECRET"})
        self.assertNotIn("SECRET", json.dumps(report.summarize(rows)))

    def test_invalid_schema_and_time_fail(self):
        for rows in ([], [{"schema": "unknown"}], self.rows() + [{"elapsed_ms": 1}]):
            with self.assertRaises(ValueError):
                report.summarize(rows)


unittest.main(verbosity=2)
