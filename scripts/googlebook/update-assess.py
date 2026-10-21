#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Read-only readiness contract for a future Ruby update UI; never installs.

Known bytes are not authenticated upstream code. A signed review is a reviewer
attestation, not execution of the attested tests. Revalidate before staging.
The CLI assumes private, trusted local paths, just like update-stage.py.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

spec = importlib.util.spec_from_file_location("update_stage", Path(__file__).with_name("update-stage.py"))
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)


def assess(original, profile_path, candidate=None, review=None, signature=None,
           trusted_key=None, stage="rehearsal", stage_parent=None, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    s.require(stage in s.GATES, "Unknown stage")
    s.require(now.tzinfo is not None, "Assessment time needs a timezone")
    gates = []
    for name, checks in s.GATES.items():
        gates.extend(checks)
        if name == stage:
            break
    result = {
        "schema": "openbook-ruby-update-assessment/1", "stage": stage,
        "assessed_at_utc": now.isoformat(), "state": "blocked",
        "source_identity": "not_checked", "review": "not_verified",
        "required_checks": gates, "verified_attestations": [], "blockers": [],
        "can_stage_now": False, "must_revalidate_before_staging": True,
        "upstream_authentication": "not_established_by_this_assessment",
        "adaptation_executed": False, "physical_install_available": False,
        "automatic_install_authorized": False, "physical_device_written": False,
        "host_reserve_bytes": s.HOST_RESERVE_BYTES,
    }

    def blocked(code, message, state="blocked"):
        result["state"] = state
        result["blockers"].append({"code": code, "message": message})
        return result

    try:
        p = s.regular(profile_path)
        s.require(p.stat().st_size <= 1024 * 1024, "Profile exceeds 1 MiB limit")
        raw = p.read_bytes()
        profile = s.json_bytes(raw)
        s.require(isinstance(profile, dict), "Profile must be an object")
        s.require(profile.get("schema") == "openbook-ruby-update-profile/1", "Unknown profile schema")
        s.require(profile.get("local_only") is True, "Local-only profile required")
        for field in ("build", "target"):
            s.require(isinstance(profile.get(field), str) and profile[field], "Missing " + field)
        source = profile.get("original")
        s.require(isinstance(source, dict), "Missing original identity")
        s.require(source.get("kind") == "full-recovery",
                  "OTA reconstruction adapter is not implemented; full recovery only")
        s.require(isinstance(source.get("sha256"), str) and
                  re.fullmatch(r"[0-9a-f]{64}", source["sha256"]), "Invalid original digest")
        result.update(profile_sha256=hashlib.sha256(raw).hexdigest(),
                      build=profile["build"], target=profile["target"])
        if original is None:
            return blocked("source_missing", "Provide the exact local source file.", "awaiting_source")
        source_path = s.regular(original)
        before = source_path.stat()
        actual = s.digest(source_path)
        after = source_path.stat()
        s.require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                  (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                  "Source changed during assessment")
        result.update(source_sha256=actual, source_bytes=after.st_size)
        if actual != source["sha256"]:
            result["source_identity"] = "mismatch"
            return blocked("unknown_input", "Source bytes do not match this profile.", "unknown_input")
        result["source_identity"] = "matches_local_profile"
        inputs = {"candidate": candidate, "review": review, "signature": signature, "trusted_key": trusted_key}
        missing = [name for name, value in inputs.items() if value is None]
        if missing:
            result["missing_inputs"] = missing
            return blocked("review_inputs_missing", "Signed review and complete candidate inputs are required.",
                           "awaiting_review")
        decision, contract, reports, checked_profile, review_raw, sig_bytes, key_bytes = s.evaluate(
            original, candidate, profile_path, review, signature, trusted_key, stage, now=now)
        s.require(checked_profile == raw, "Profile changed during assessment")
        result["review"] = "signature_and_tuple_verified"
        result["verified_attestations"] = decision["gates"]
        result["review_sha256"] = decision["review_sha256"]
        result["tuple_sha256"] = decision["tuple_sha256"]
        result["trusted_key_sha256"] = decision["trusted_key_sha256"]
        result["staging_additional_bytes"] = s.staging_bytes(
            original, candidate, contract, reports,
            sum(map(len, (checked_profile, review_raw, sig_bytes, key_bytes))))
        if stage_parent is None:
            return blocked("storage_not_checked", "Select an existing staging parent for the space check.")
        parent = Path(stage_parent).absolute()
        s.require(not any(p.is_symlink() for p in (parent, *parent.parents)), "Symlink staging parent refused")
        s.require(parent.is_dir(), "Staging parent must be an existing directory")
        free = shutil.disk_usage(parent).free
        result["host_free_bytes"] = free
        if free < result["staging_additional_bytes"] + s.HOST_RESERVE_BYTES:
            return blocked("insufficient_space", "Staging would threaten the 40 GiB host reserve.")
        result.update(state="ready_for_local_staging", can_stage_now=True)
        return result
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        # These errors contain validation context, not raw diagnostics or keys.
        return blocked("validation_failed", str(error))
    except OSError:
        return blocked("input_unavailable", "A required input could not be read; inspect it locally.")
    except subprocess.SubprocessError:
        return blocked("verifier_failed", "The local signature verifier did not complete.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    for name in ("original", "candidate", "review", "signature", "trusted-key", "stage-parent"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--stage", choices=s.GATES, default="rehearsal")
    args = parser.parse_args()
    result = assess(args.original, args.profile, args.candidate, args.review,
                    args.signature, args.trusted_key, args.stage, args.stage_parent)
    print(json.dumps(result, indent=2))
    return 0 if result["can_stage_now"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
