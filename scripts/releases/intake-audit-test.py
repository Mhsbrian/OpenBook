#!/usr/bin/env python3
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "audit", Path(__file__).with_name("intake-audit.py")
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def issue(key="a", **changes):
    return {
        "id": key, "identifier": key, "title": "Example", "status": "in_review",
        "revision": 1, "parent_issue_id": None, **changes,
    }


def rule(**changes):
    return {
        "id": "watch", "agent_id": audit.COORDINATOR, "enabled": True,
        "mode": "once", "fire_count": 0, "expires_at": "2027-01-01T00:00:00Z",
        "condition": {"type": "other_issue", "issue_id": "a", "state": "in_review"},
        **changes,
    }


class CensusTest(unittest.TestCase):
    def test_pagination_does_not_trust_legacy_count(self):
        offsets = []
        pages = [
            {"issues": [issue("a")], "total": 1, "has_more": False},
            {"issues": [issue("b")], "total": 1, "has_more": False},
            {"issues": [], "has_more": False},
        ]

        def call(*args):
            offsets.append(args[args.index("--offset") + 1])
            return pages.pop(0)

        self.assertEqual(len(audit.list_all_issues(call)), 2)
        self.assertEqual(offsets, ["0", "1", "2"])

    def test_partial_or_repeated_pages_fail(self):
        for pages in (
            [{"issues": [issue()]}, {"issues": [issue()]}],
            [{"issues": [], "has_more": True}],
            [{"error": "failed to count issues"}],
            [{"issues": [{"id": "a"}]}],
        ):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                audit.list_all_issues(lambda *args: pages.pop(0))

    def test_watch_health(self):
        self.assertTrue(audit.watch_usable(rule(), NOW))
        for change in (
            {"enabled": False}, {"fire_count": 1},
            {"expires_at": "2026-01-01T00:00:00Z"},
            {"expires_at": "invalid"}, {"expires_at": None},
            {"paused_reason": "paused"}, {"last_error": "unavailable"},
            {"agent_id": "another-agent"}, {"timed_out_at": "2026-10-19"},
        ):
            with self.subTest(change=change):
                self.assertFalse(audit.watch_usable(rule(**change), NOW))

    def test_duplicate_watches_are_visible(self):
        report = audit.make_report([issue()], [rule(), rule(id="second")], None, NOW)
        self.assertEqual(report["issues"][0]["watch_attention"], "duplicate")

    def test_index_changes_and_removed_issues(self):
        previous = audit.make_report(
            [issue("a"), issue("b"), issue("c")], [], None, NOW
        )
        report = audit.make_report(
            [issue("a", last_activity_at="new comment"), issue("b"), issue("d")],
            [], previous, NOW,
        )
        self.assertEqual(
            [row["change"] for row in report["issues"]],
            ["changed", "unchanged", "new"],
        )
        self.assertEqual(report["missing_since_previous"], ["c"])

    def test_hub_and_release_are_not_work_items(self):
        report = audit.make_report(
            [issue(audit.HUB), issue("release", parent_issue_id=audit.HUB), issue()],
            [], None, NOW,
        )
        self.assertEqual(report["summary"]["work_items"], 1)

    def test_wrong_project_baseline_fails(self):
        previous = audit.make_report([], [], None, NOW)
        previous["project_id"] = "other-project"
        with self.assertRaises(ValueError):
            audit.make_report([], [], previous, NOW)


if __name__ == "__main__":
    unittest.main()
