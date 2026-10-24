#!/usr/bin/env python3
"""Read-only Multica issue census. This does not qualify or approve a release."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

PROJECT = "b2998471-cf89-4a67-a2e5-d605ae0049ac"
HUB = "01a15aa2-77a9-76a2-9f34-db99940b0f68"
COORDINATOR = "517b88d9-124d-43e9-a8ca-bb617437e116"
FIELDS = (
    "id,identifier,title,status,parent_issue_id,revision,last_activity_at,updated_at"
)


def multica(*args):
    result = subprocess.run(
        ["multica", *args, "--output", "json"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def list_all_issues(call):
    """Read through an empty page, including with legacy/inaccurate totals."""
    issues = []
    seen = set()
    while True:
        page = call(
            "issue", "list", "--project", PROJECT, "--limit", "100",
            "--offset", str(len(issues)), "--sort", "created_at",
            "--direction", "asc", "--fields", FIELDS,
        )
        if not isinstance(page, dict) or not isinstance(page.get("issues"), list):
            raise ValueError("Malformed issue page; census is incomplete")
        rows = page["issues"]
        if not rows:
            if page.get("has_more"):
                raise ValueError("Empty page with has_more; census is incomplete")
            return issues
        for row in rows:
            if not isinstance(row, dict) or not all(
                row.get(key) is not None
                for key in ("id", "identifier", "title", "status", "revision")
            ):
                raise ValueError("Incomplete issue record; census is incomplete")
            if row["id"] in seen:
                raise ValueError("Repeated issue; project moved during pagination")
            seen.add(row["id"])
            issues.append(row)


def watch_usable(rule, now):
    if (
        rule.get("enabled") is not True
        or rule.get("agent_id") != COORDINATOR
        or rule.get("last_error")
        or rule.get("paused_reason")
        or rule.get("timed_out_at")
        or (rule.get("mode") == "once" and rule.get("fire_count", 0) > 0)
    ):
        return False
    expiry = rule.get("expires_at")
    if not expiry:
        return False
    try:
        return datetime.fromisoformat(expiry.replace("Z", "+00:00")) > now
    except (ValueError, TypeError):
        return False


def make_report(issues, rules, previous, now):
    if not isinstance(rules, list):
        raise ValueError("Malformed wakeup list")
    if previous is not None and (
        previous.get("schema_version") != 1
        or previous.get("project_id") != PROJECT
        or not isinstance(previous.get("issues"), list)
    ):
        raise ValueError("Previous census has a different schema/project")
    old = {row["id"]: row for row in previous["issues"]} if previous else {}
    result = []
    for issue in issues:
        row = dict(issue)
        row["role"] = (
            "hub" if row["id"] == HUB
            else "release_record" if row.get("parent_issue_id") == HUB
            else "work_item"
        )
        matches = [
            rule for rule in rules
            if rule.get("condition", {}).get("type") == "other_issue"
            and rule["condition"].get("issue_id") == row["id"]
            and rule["condition"].get("state") == "in_review"
        ]
        row["usable_ready_watch_ids"] = [
            rule["id"] for rule in matches if watch_usable(rule, now)
        ]
        row["watch_attention"] = (
            "duplicate" if len(row["usable_ready_watch_ids"]) > 1
            else "none" if row["usable_ready_watch_ids"]
            else "not_armed"
        )
        prior = old.get(row["id"])
        row["change"] = (
            "initial" if previous is None else "new" if prior is None
            else "changed" if any(
                row.get(key) != prior.get(key) for key in issue
            ) else "unchanged"
        )
        result.append(row)
    work = [row for row in result if row["role"] == "work_item"]
    return {
        "schema_version": 1,
        "project_id": PROJECT,
        "hub_id": HUB,
        "observed_at": now.isoformat(),
        "scope": "Issue index and watch health only; no release eligibility or approval.",
        "limitations": [
            "Not an atomic snapshot; rerun before freezing/building.",
            "Unwatched does not mean image-affecting, ready or excluded.",
            "Read relevant threads and verify linked PR heads separately; commits "
            "can change without an issue-index change.",
            "New direct children of the hub must be verified as release records.",
        ],
        "summary": {
            "issues": len(result),
            "work_items": len(work),
            "work_item_statuses": dict(Counter(row["status"] for row in work)),
            "work_items_with_usable_watch": sum(
                bool(row["usable_ready_watch_ids"]) for row in work
            ),
            "changes": dict(Counter(row["change"] for row in work)),
        },
        "missing_since_previous": sorted(set(old) - {row["id"] for row in result}),
        "issues": result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New JSON file")
    parser.add_argument("--previous", type=Path, help="Prior census for index changes")
    args = parser.parse_args()
    try:
        previous = (
            json.loads(args.previous.read_text(encoding="utf-8"))
            if args.previous else None
        )
        issues = list_all_issues(multica)
        rules = multica("issue", "wakeup", "list", HUB)
        report = make_report(issues, rules, previous, datetime.now(timezone.utc))
        # Never truncate an earlier audit, even if collection failed part-way.
        with args.output.open("x", encoding="utf-8") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write("\n")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Intake census failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
