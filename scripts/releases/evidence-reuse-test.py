#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "reuse", Path(__file__).with_name("evidence-reuse.py")
)
reuse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reuse)

BASE, APK, POLICY, OTHER = ("a" * 64), ("b" * 64), ("c" * 64), ("d" * 64)


def plan(**changes):
    return {
        "release": "RB-TEST", "track": "ruby-g14", "targets": ["laptop-update"],
        "image_inputs": {"base": BASE, "apk": APK, "policy": POLICY}, **changes,
    }


def check(**changes):
    return {
        "id": "fresh-boot", "kind": "fresh-boot-vm", "scope": "image", "passed": True,
        "summary": "16/16", "evidence": "evidence/vm/judge.json",
        "inputs": {"base": BASE, "apk": APK, "policy": POLICY}, **changes,
    }


def unit(**changes):
    return check(**{"id": "unit", "kind": "unit", "scope": "component", "summary": "19/19",
                    "inputs": {"apk": APK}, **changes})


def handoff(*checks, **changes):
    return {
        "schema": "anybook-handoff/1", "source_issue": "ANAL-1", "commit": "e" * 40,
        "track": "ruby-g14", "checks": list(checks), **changes,
    }


def decisions(report):
    return {c["id"]: c["decision"] for c in report["source_checks"]}


def steps(report):
    return {s["id"]: s["decision"] for s in report["release_steps"]}


class ReuseTest(unittest.TestCase):
    def test_matching_inputs_are_cited_and_release_steps_still_run(self):
        report = reuse.make_report(plan(), [handoff(check(), unit())])
        self.assertEqual(decisions(report), {"fresh-boot": "reuse", "unit": "reuse"})
        self.assertEqual(set(steps(report).values()), {"run"})
        self.assertEqual(report["summary"]["run"],
                         ["candidate", "control", "update-rehearsal", "fallback", "after-update"])
        self.assertEqual(report["summary"]["cite"], ["fresh-boot", "unit"])

    def test_stick_fresh_boot_is_cited_only_from_a_matching_image(self):
        stick = plan(targets=["laptop-update", "stick"])
        self.assertEqual(steps(reuse.make_report(stick, [handoff(check())]))["fresh-boot"],
                         "cite-source")
        other = check(inputs={"base": BASE, "apk": OTHER, "policy": POLICY})
        report = reuse.make_report(stick, [handoff(other)])
        self.assertEqual(decisions(report), {"fresh-boot": "rerun"})
        self.assertEqual(steps(report)["fresh-boot"], "run")

    def test_an_image_check_does_not_cover_a_release_with_more_changes(self):
        bigger = plan(targets=["stick"], image_inputs={
            "base": BASE, "apk": APK, "policy": POLICY, "vendor": OTHER})
        report = reuse.make_report(bigger, [handoff(check(), unit())])
        self.assertEqual(decisions(report), {"fresh-boot": "rerun", "unit": "reuse"})
        self.assertIn("the release also changes vendor", report["source_checks"][0]["reasons"][0])

    def test_laptop_only_release_does_not_rerun_a_stale_fresh_boot(self):
        stale = check(inputs={"base": OTHER, "apk": APK, "policy": POLICY})
        report = reuse.make_report(plan(), [handoff(stale)])
        self.assertEqual(decisions(report), {"fresh-boot": "not-required"})
        self.assertNotIn("fresh-boot", report["summary"]["run"])

    def test_changed_failed_or_unpinned_component_checks_rerun(self):
        for changed, reason in (
            (unit(inputs={"apk": OTHER}), "apk differs"),
            (unit(passed=False), "did not pass"),
            (unit(inputs={"apk": APK, "engine": OTHER}), "engine is not pinned"),
            (unit(evidence=""), "names no evidence"),
        ):
            with self.subTest(reason=reason):
                report = reuse.make_report(plan(), [handoff(changed)])
                self.assertEqual(decisions(report), {"unit": "rerun"})
                self.assertTrue(any(reason in r for r in report["source_checks"][0]["reasons"]))

    def test_other_track_and_unrelated_checks(self):
        report = reuse.make_report(plan(), [handoff(unit(), track="aosp")])
        self.assertEqual(decisions(report), {"unit": "rerun"})
        report = reuse.make_report(plan(), [handoff(unit(inputs={"kernel": OTHER}))])
        self.assertEqual(decisions(report), {"unit": "not-applicable"})

    def test_missing_evidence_file_reruns_when_a_checkout_is_given(self):
        with tempfile.TemporaryDirectory() as repo:
            report = reuse.make_report(plan(), [handoff(unit())], Path(repo))
            self.assertEqual(decisions(report), {"unit": "rerun"})
            (Path(repo) / "evidence/vm").mkdir(parents=True)
            (Path(repo) / "evidence/vm/judge.json").write_text("{}")
            report = reuse.make_report(plan(), [handoff(unit())], Path(repo))
            self.assertEqual(decisions(report), {"unit": "reuse"})

    def test_malformed_input_fails(self):
        for bad_plan, bad_handoff in (
            (plan(targets=["phone"]), handoff(unit())),
            (plan(targets=[]), handoff(unit())),
            (plan(image_inputs={"apk": "B" * 64}), handoff(unit())),
            (plan(), handoff(unit(), schema="other")),
            (plan(), handoff(unit(), commit="abc")),
            (plan(), handoff()),
            (plan(), handoff(unit(), unit())),
            (plan(), handoff(unit(scope="whole"))),
            (plan(), handoff(unit(kind="cts"))),
            (plan(), handoff(unit(passed="yes"))),
            (plan(), handoff(unit(inputs={}))),
        ):
            with self.subTest(plan=bad_plan, handoff=bad_handoff), self.assertRaises(ValueError):
                reuse.make_report(bad_plan, [bad_handoff])

    def test_command_line_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "plan.json").write_text(json.dumps(plan()))
            (tmp / "handoff.json").write_text(json.dumps(handoff(unit())))
            command = [sys.executable, "-I", str(Path(__file__).with_name("evidence-reuse.py")),
                       "--plan", str(tmp / "plan.json"), str(tmp / "handoff.json"),
                       "--output", str(tmp / "out.json")]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("reuse          ANAL-1 unit 19/19", first.stdout)
            self.assertEqual(json.loads((tmp / "out.json").read_text())["summary"]["cite"], ["unit"])
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 1)
            self.assertIn("failed", second.stderr)


if __name__ == "__main__":
    unittest.main()
