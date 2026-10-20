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
    def test_graphics_probe_abort_is_not_a_successful_start(self):
        started = "init: starting service 'openbook.camera-buffer-test'...\n"
        aborted = "init: Service 'openbook.camera-buffer-test' (pid 123) received SIGABRT\n"
        success = "init: Service 'openbook.camera-buffer-test' (pid 456) exited with status 0\n"
        self.assertEqual(observation.runtime_findings(started)["camera_buffer_test_exit_statuses"], [])
        failed = observation.runtime_findings(started + aborted)
        self.assertTrue(failed["camera_buffer_test_abort_seen"])
        self.assertEqual(failed["camera_buffer_test_exit_statuses"], [])
        passed = observation.runtime_findings(success * 2)
        self.assertFalse(passed["camera_buffer_test_abort_seen"])
        self.assertEqual(passed["camera_buffer_test_exit_statuses"], [0])

    def test_camera_fmq_probe_requires_an_exit_result(self):
        started = "init: starting service 'openbook.camera-fmq-test'...\n"
        self.assertEqual(observation.runtime_findings(started)["camera_fmq_test_exit_statuses"], [])
        failure = "init: Service 'openbook.camera-fmq-test' (pid 123) exited with status 21\n"
        success = "init: Service 'openbook.camera-fmq-test' (pid 456) exited with status 0\n"
        self.assertEqual(observation.runtime_findings(failure * 2)["camera_fmq_test_exit_statuses"], [21])
        self.assertEqual(observation.runtime_findings(success)["camera_fmq_test_exit_statuses"], [0])

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

    def test_camera_registration_does_not_imply_camera_enumeration(self):
        state = observation.runtime_findings(
            "init.svc.vendor.camera.provider-ext=running\n"
            "Service android.hardware.camera.provider.ICameraProvider/external/0: found\n"
            "Number of camera devices: 0\n")
        self.assertTrue(state["camera_provider_running_reported"])
        self.assertTrue(state["camera_provider_registered_reported"])
        self.assertEqual(state["camera_device_counts_reported"], [0])
        state = observation.runtime_findings(
            "echo init.svc.vendor.camera.provider-ext=running\n"
            "Service android.hardware.camera.provider.ICameraProvider/external/0: not found\n")
        self.assertFalse(state["camera_provider_running_reported"])
        self.assertFalse(state["camera_provider_registered_reported"])
        self.assertEqual(state["camera_device_counts_reported"], [])
        state = observation.runtime_findings(
            "Service 'vendor.camera.provider-ext' (pid 487) received SIGABRT\n"
            "avc: denied { add } name=android.hardware.camera.provider.ICameraProvider/external/0 "
            "tcontext=u:object_r:default_android_service:s0\n")
        self.assertTrue(state["camera_provider_abort_seen"])
        self.assertTrue(state["camera_provider_default_label_denial_seen"])

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
