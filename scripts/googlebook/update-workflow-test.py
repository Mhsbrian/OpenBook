#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Failure-boundary tests for local adaptation jobs; tiny temporary fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("workflow", Path(__file__).with_name("update-workflow.py"))
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a = SimpleNamespace(**{n: self.root / n for n in
            ("original", "base", "ruby", "product", "kernel", "tools", "inventory", "probe", "key", "profile", "out")})
        self.input = self.root / "input"
        self.input.write_text("known input")
        self.profile = dict(schema="openbook-ruby-workflow-profile/1", recipe=w.RECIPE,
                            local_only=True, container_image="test-container",
                            audit_inventory_sha256=w.sha_value({"fixture": "known"}),
                            files={"$BASE/ruby-live.img": w.sha(self.input)})
        self.a.profile.write_text(json.dumps(self.profile))
        passed = dict(passed=True, exit_code=0)
        self.report = dict(schema="openbook-googlebook-compat-audit/1", installable=False,
                           inputs_unchanged=True, input_inventory={"fixture": "known"},
                           apexes={"ruby": [], "openbook": []}, cases={n: dict(
                               static_checks_passed=True, vintf=passed.copy(), selinux=passed.copy(),
                               service_contexts=passed.copy()) for n in ("ruby", "openbook", "hybrid-reduced")})
        self.report["cases"]["hybrid"] = {"selinux": dict(passed=False, exit_code=1)}
        self.phases = []
        for item in (
            patch.object(w, "file_inputs", return_value={"$BASE/ruby-live.img": self.input}),
            patch.object(w, "audit_inventory", return_value={"fixture": "known"}),
            patch.object(w.shutil, "disk_usage", return_value=SimpleNamespace(free=200*w.GIB)),
            patch.dict(os.environ, OPENBOOK_WORKFLOW_CONTAINER_ID="test-container"),
        ):
            item.start()
            self.addCleanup(item.stop)

    def runner(self, command, log, workspace):
        name = Path(command[1]).name
        self.phases.append(name)
        log.write_text("synthetic native execution fixture\n")
        if name == "compat-audit.py":
            (self.a.out / "audit").mkdir()
            (self.a.out / "audit/report.json").write_text(json.dumps(self.report))
        elif name == "build-input-candidate.py":
            out = self.a.out / "candidate"
            out.mkdir()
            (out / "ruby-live.img").write_text("candidate")
            digest = w.sha(out / "ruby-live.img")
            result = dict(schema="openbook-ruby-input-candidate/1", complete=True,
                          all_inode_xattrs_identical=True, protected_ranges_identical=True,
                          source_unchanged=True, physical_device_written=False,
                          changed_files=["/system/lib64/libinputflinger.so"],
                          source_sha256=w.sha(self.input), image_sha256=digest)
            (out / "result.json").write_text(json.dumps(result))
            (out / "manifest.json").write_text(json.dumps(dict(image_sha256=digest, installable=False)))
            (out / "source").mkdir()
            (out / "source/scratch").write_text("disposable")
        else:
            (self.a.out / "input-native.json").write_text("[]")

    def job(self):
        return json.loads((self.a.out / "job.json").read_text())

    def test_success_keeps_candidate_and_evidence_removes_only_scratch(self):
        other = self.root / "other-task"
        other.mkdir()
        (other / "keep").write_text("unrelated")
        self.assertEqual(w.execute(self.a, self.runner), 0)
        self.assertEqual(self.job()["state"], "assembled_unqualified")
        for flag in ("physical_device_written", "installation_available", "release_approved",
                     "upstream_authenticated", "raw_to_derived_provenance_verified"):
            self.assertIs(self.job()[flag], False)
        self.assertEqual(len(self.phases), 3)
        self.assertTrue((self.a.out / "candidate/ruby-live.img").is_file())
        self.assertTrue((self.a.out / "audit/report.json").is_file())
        self.assertFalse((self.a.out / "candidate/source").exists())
        self.assertTrue((other / "keep").is_file())

    def test_unknown_source_never_runs_native_code(self):
        self.input.write_text("different input")
        with self.assertRaisesRegex(ValueError, "identity changed"):
            w.execute(self.a, self.runner)
        self.assertEqual(self.phases, [])
        self.assertEqual(self.job()["failed_phase"], "validating")

    def test_missing_pin_is_not_silently_accepted(self):
        self.profile["files"] = {}
        with self.assertRaisesRegex(ValueError, "input set"):
            w.validate_inputs(self.a, self.profile)

    def test_changed_native_tuple_is_rejected(self):
        with patch.object(w, "audit_inventory", return_value={"fixture": "different"}):
            with self.assertRaisesRegex(ValueError, "tuple changed"):
                w.execute(self.a, self.runner)
        self.assertEqual(self.phases, [])

    def test_failed_native_command_prevents_assembly(self):
        def fail(*args):
            raise ValueError("native exit 2")
        with self.assertRaisesRegex(ValueError, "native exit"):
            w.execute(self.a, fail)
        self.assertEqual(self.job()["failed_phase"], "auditing")
        self.assertFalse((self.a.out / "candidate").exists())

    def test_zero_exit_with_failed_check_prevents_assembly(self):
        self.report["cases"]["hybrid-reduced"]["vintf"]["passed"] = False
        with self.assertRaisesRegex(ValueError, "vintf"):
            w.execute(self.a, self.runner)
        self.assertEqual(self.phases, ["compat-audit.py"])

    def test_missing_service_check_prevents_assembly(self):
        del self.report["cases"]["ruby"]["service_contexts"]
        with self.assertRaisesRegex(ValueError, "service_contexts"):
            w.execute(self.a, self.runner)
        self.assertEqual(len(self.phases), 1)

    def test_wrong_audit_identity_prevents_assembly(self):
        self.report["input_inventory"] = {"fixture": "wrong"}
        with self.assertRaisesRegex(ValueError, "different tuple"):
            w.execute(self.a, self.runner)
        self.assertEqual(len(self.phases), 1)

    def test_missing_negative_control_is_failure(self):
        self.report["cases"].pop("hybrid")
        with self.assertRaisesRegex(ValueError, "raw-hybrid"):
            w.execute(self.a, self.runner)

    def test_input_change_during_audit_prevents_assembly(self):
        def mutate(*args):
            self.runner(*args)
            self.input.write_text("mutated")
        with self.assertRaisesRegex(ValueError, "identity changed"):
            w.execute(self.a, mutate)
        self.assertEqual(len(self.phases), 1)

    def test_storage_lost_between_phases_prevents_assembly(self):
        def consume(*args):
            self.runner(*args)
            w.shutil.disk_usage.return_value.free = 50*w.GIB
        with self.assertRaisesRegex(ValueError, "40 GiB"):
            w.execute(self.a, consume)
        self.assertEqual(len(self.phases), 1)

    def test_insufficient_initial_budget_never_runs_native_code(self):
        w.shutil.disk_usage.return_value.free = 103*w.GIB
        with self.assertRaisesRegex(ValueError, "40 GiB"):
            w.execute(self.a, self.runner)
        self.assertEqual(self.phases, [])

    def test_candidate_tamper_fails_without_cleanup_or_promotion(self):
        def tamper(*args):
            self.runner(*args)
            path = self.a.out / "candidate/ruby-live.img"
            if path.exists():
                path.write_text("corrupt")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            w.execute(self.a, tamper)
        self.assertEqual(self.job()["failed_phase"], "verifying")
        self.assertTrue((self.a.out / "candidate/source").exists())

    def test_interruption_is_durable_failure(self):
        with self.assertRaises(KeyboardInterrupt):
            w.execute(self.a, lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
        self.assertEqual(self.job()["state"], "failed")

    def test_existing_job_cannot_be_overwritten(self):
        self.a.out.mkdir()
        (self.a.out / "job.json").write_text("previous")
        with self.assertRaises(FileExistsError):
            w.execute(self.a, self.runner)
        self.assertEqual((self.a.out / "job.json").read_text(), "previous")

    def test_symlink_and_device_inputs_refused(self):
        link = self.root / "link"
        link.symlink_to(self.input)
        for path in (link, Path("/dev/null")):
            with self.assertRaises(ValueError):
                w.sha(path)

    def test_parent_traversal_cannot_bypass_output_boundary(self):
        with self.assertRaisesRegex(ValueError, "traversal"):
            w.argument_path(self.root / "installer/work/../../outside")

    def test_container_mismatch_never_runs_native_code(self):
        with patch.dict(os.environ, OPENBOOK_WORKFLOW_CONTAINER_ID="wrong"):
            with self.assertRaisesRegex(ValueError, "Container identity"):
                w.execute(self.a, self.runner)
        self.assertEqual(self.phases, [])

    def test_profile_change_during_run_prevents_completion(self):
        def mutate(*args):
            self.runner(*args)
            if len(self.phases) == 3:
                self.a.profile.write_text(self.a.profile.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "Profile changed"):
            w.execute(self.a, mutate)
        self.assertEqual(self.job()["state"], "failed")
        self.assertFalse((self.a.out / "cleanup.json").exists())

    def test_native_probe_failure_prevents_completion(self):
        def fail(*args):
            self.runner(*args)
            if len(self.phases) == 3:
                raise ValueError("native probe failed")
        with self.assertRaisesRegex(ValueError, "native probe failed"):
            w.execute(self.a, fail)
        self.assertEqual(self.job()["failed_phase"], "verifying")

    def test_cleanup_symlink_cannot_remove_unrelated_files(self):
        out = self.a.out
        (out / "candidate").mkdir(parents=True)
        (out / "candidate/source").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "escaped"):
            w.cleanup(out, self.report)
        self.assertTrue(self.input.exists())

    def test_real_subprocess_exit_failure_is_reported(self):
        with self.assertRaisesRegex(ValueError, "exit 7"):
            w.run_command([sys.executable, "-c", "raise SystemExit(7)"], self.root / "process.log", self.root)

    def test_real_subprocess_timeout_reaps_child(self):
        pid = self.root / "pid"
        code = "import os,time,pathlib; pathlib.Path(%r).write_text(str(os.getpid())); time.sleep(60)" % str(pid)
        with self.assertRaises(TimeoutError):
            w.run_command([sys.executable, "-c", code], self.root / "process.log", self.root, timeout=0.1)
        with self.assertRaises(ProcessLookupError):
            os.kill(int(pid.read_text()), 0)


if __name__ == "__main__":
    unittest.main()
