#!/usr/bin/env python3
"""Decide which source-issue checks a release cites and what it still runs.

A check passed in a source issue is reused when it tested the same bytes the
release ships: every input it names matches the plan's pinned hash. An image
check (a fresh boot of a whole system) is reused only when its inputs equal the
plan's image inputs exactly, so nothing else changed the image. Steps that need
the installed release or the release's own payload always run in the release.
This does not approve anything; it writes the test list a plan proposes.
"""

import argparse
import json
from pathlib import Path
import re
import sys

HANDOFF_SCHEMA = "anybook-handoff/1"
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")

# Release-only steps, per target. A step with "reusable_kind" is satisfied by a
# reused image check of that kind; the rest depend on the installed release or
# on the release's own payload, so a source issue cannot run them.
STEPS = {
    "laptop-update": [
        {"id": "candidate", "does": "Build the candidate and the signed laptop "
         "payload from the pinned inputs"},
        {"id": "control", "does": "Rebuild the installed release's images from "
         "its candidate with the same steps; they must match byte for byte"},
        {"id": "update-rehearsal", "does": "VM: update the installed release into "
         "the other slot with existing data, boot it and compare the slot bytes"},
        {"id": "fallback", "does": "VM: break the new slot; the old slot must "
         "boot by itself"},
        {"id": "after-update", "does": "VM: check every changed feature after the "
         "update, with existing data"},
    ],
    "stick": [
        {"id": "stick-image", "does": "Build the stick image and its installer pin "
         "from the candidate"},
        {"id": "fresh-boot", "does": "VM: first boot of the candidate with fresh "
         "data", "reusable_kind": "fresh-boot-vm"},
        {"id": "stick-install", "does": "VM: install from the stick image, then "
         "boot without the stick"},
    ],
}
KINDS = {"unit", "emulator", "fresh-boot-vm", "other"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_plan(plan):
    require(isinstance(plan, dict), "Plan is not a JSON object")
    for key in ("release", "track"):
        require(isinstance(plan.get(key), str) and plan[key], f"Plan lacks {key}")
    targets = plan.get("targets")
    require(isinstance(targets, list) and targets and set(targets) <= set(STEPS),
            f"Plan targets must be a non-empty subset of {sorted(STEPS)}")
    check_hashes(plan.get("image_inputs"), "Plan image_inputs")


def check_hashes(inputs, where):
    require(isinstance(inputs, dict) and inputs, f"{where} must name inputs")
    for name, value in inputs.items():
        require(isinstance(value, str) and SHA256.fullmatch(value),
                f"{where}: {name} is not a lowercase SHA-256")


def check_handoff(handoff):
    require(isinstance(handoff, dict) and handoff.get("schema") == HANDOFF_SCHEMA,
            f"Handoff schema must be {HANDOFF_SCHEMA}")
    require(isinstance(handoff.get("source_issue"), str), "Handoff lacks source_issue")
    require(isinstance(handoff.get("commit"), str)
            and COMMIT.fullmatch(handoff["commit"]), "Handoff commit is not a full SHA")
    require(isinstance(handoff.get("track"), str), "Handoff lacks track")
    checks = handoff.get("checks")
    require(isinstance(checks, list) and checks, "Handoff lists no checks")
    seen = set()
    for check in checks:
        require(isinstance(check, dict) and isinstance(check.get("id"), str),
                "Check lacks an id")
        require(check["id"] not in seen, f"Repeated check {check['id']}")
        seen.add(check["id"])
        require(check.get("kind") in KINDS, f"{check['id']}: kind must be one of {sorted(KINDS)}")
        require(check.get("scope") in ("component", "image"),
                f"{check['id']}: scope must be component or image")
        require(isinstance(check.get("passed"), bool), f"{check['id']}: passed must be true/false")
        check_hashes(check.get("inputs"), f"{check['id']} inputs")


def decide(check, track, plan_inputs, targets, repo):
    """Return (decision, reasons) for one source check."""
    inputs = check["inputs"]
    shared = set(inputs) & set(plan_inputs)
    if not shared:
        return "not-applicable", ["none of its inputs is in this release"]
    reasons = []
    if not check["passed"]:
        reasons.append("it did not pass in the source issue")
    if track != check.get("track", track):
        reasons.append("it ran on another track")
    for name in sorted(inputs):
        if name not in plan_inputs:
            reasons.append(f"{name} is not pinned in this release")
        elif inputs[name] != plan_inputs[name]:
            reasons.append(f"{name} differs: tested {inputs[name][:12]}…, "
                           f"release pins {plan_inputs[name][:12]}…")
    if check["scope"] == "image":
        for name in sorted(set(plan_inputs) - set(inputs)):
            reasons.append(f"the release also changes {name}, which this image did not have")
    evidence = check.get("evidence")
    if not isinstance(evidence, str) or not evidence:
        reasons.append("it names no evidence")
    elif repo is not None and not (repo / evidence).exists():
        reasons.append(f"its evidence {evidence} is missing")
    if reasons:
        needed = check["scope"] == "component" or any(
            step.get("reusable_kind") == check["kind"]
            for target in targets for step in STEPS[target])
        return ("rerun" if needed else "not-required"), reasons
    return "reuse", []


def make_report(plan, handoffs, repo=None):
    check_plan(plan)
    plan_inputs, targets = plan["image_inputs"], plan["targets"]
    checks = []
    for handoff in handoffs:
        check_handoff(handoff)
        for check in handoff["checks"]:
            decision, reasons = decide(
                {"track": handoff["track"], **check}, plan["track"], plan_inputs,
                targets, repo)
            checks.append({
                "source_issue": handoff["source_issue"],
                "source_commit": handoff["commit"],
                "id": check["id"], "kind": check["kind"], "scope": check["scope"],
                "summary": check.get("summary", ""), "evidence": check.get("evidence"),
                "decision": decision, "reasons": reasons,
            })
    reused_kinds = {c["kind"] for c in checks if c["decision"] == "reuse" and c["scope"] == "image"}
    steps = []
    for target in targets:
        for step in STEPS[target]:
            covered = step.get("reusable_kind") in reused_kinds
            steps.append({"target": target, **step,
                          "decision": "cite-source" if covered else "run"})
    return {
        "schema": "anybook-evidence-reuse/1",
        "release": plan["release"],
        "targets": targets,
        "scope": "Test list for a release plan; not an approval.",
        "release_steps": steps,
        "source_checks": checks,
        "summary": {
            "run": [s["id"] for s in steps if s["decision"] == "run"]
            + [c["id"] for c in checks if c["decision"] == "rerun"],
            "cite": [c["id"] for c in checks if c["decision"] == "reuse"],
            "skip": [c["id"] for c in checks if c["decision"] in ("not-required", "not-applicable")],
        },
    }


def render(report):
    lines = [f"{report['release']} ({', '.join(report['targets'])})", "", "Release steps:"]
    for step in report["release_steps"]:
        lines.append(f"  {step['decision']:<12} {step['id']}: {step['does']}")
    lines += ["", "Source checks:"]
    for check in report["source_checks"]:
        lines.append(f"  {check['decision']:<14} {check['source_issue']} {check['id']}"
                     f" {check['summary']}".rstrip())
        lines += [f"{'':17}- {reason}" for reason in check["reasons"]]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True,
                        help="Release plan JSON with release, track, targets, image_inputs")
    parser.add_argument("handoffs", type=Path, nargs="+", help=f"{HANDOFF_SCHEMA} JSON files")
    parser.add_argument("--repo", type=Path, help="Checkout to confirm evidence paths exist")
    parser.add_argument("--output", type=Path, help="New JSON report (never overwritten)")
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        handoffs = [json.loads(p.read_text(encoding="utf-8")) for p in args.handoffs]
        report = make_report(plan, handoffs, args.repo)
        if args.output:
            with args.output.open("x", encoding="utf-8") as output:
                json.dump(report, output, ensure_ascii=False, indent=2)
                output.write("\n")
    except (OSError, ValueError) as error:
        print(f"Evidence reuse check failed: {error}", file=sys.stderr)
        return 1
    print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
