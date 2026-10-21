#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Local signed-review gate and immutable staging prototype; never a disk writer.

An independently trusted operator key authorizes one exact tuple and stage.
Reports are signed reviewer attestations, not automatically verified hardware
facts. No shipped Ruby profile is approved for hardware or unattended use.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

GATES = {
    "rehearsal": ("license", "provenance", "signatures", "rollback_indexes", "vintf",
                  "selinux", "kernel_modules", "firmware_graphics", "layout", "installer_pin"),
    "trial": ("encrypted_data", "boot_health", "failure_recovery", "containment", "data_rollback"),
    "promotion": ("hardware", "owner_acceptance"),
}
HOST_RESERVE_BYTES = 40 * 2**30
STAGING_OVERHEAD_BYTES = 64 * 2**20


def require(value, message):
    if not value:
        raise ValueError(message)


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink input refused")
    require(stat.S_ISREG(path.stat().st_mode), "Regular files only; no devices")
    return path


def digest(path):
    with regular(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def json_bytes(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def safe_name(name):
    require(isinstance(name, str) and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", name),
            "Flat artifact names required")
    return name


def verify_review(raw, signature, key):
    # Verify these bytes, not paths that can be swapped after verification.
    key_bytes = regular(key).read_bytes()
    sig_bytes = regular(signature).read_bytes()
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for name, data in (("review", raw), ("key", key_bytes), ("sig", sig_bytes)):
            (root / name).write_bytes(data)
        result = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(root / "key"),
                                 "-signature", str(root / "sig"), str(root / "review")],
                                capture_output=True, timeout=30)
    require(result.returncode == 0, "Untrusted review signature")
    return hashlib.sha256(key_bytes).hexdigest(), sig_bytes, key_bytes


def evaluate(original, candidate, profile_path, review_path, signature, key, stage, now=None):
    profile_raw = regular(profile_path).read_bytes()
    review_raw = regular(review_path).read_bytes()
    key_sha, sig_bytes, key_bytes = verify_review(review_raw, signature, key)
    profile, review = json_bytes(profile_raw), json_bytes(review_raw)
    require(profile.get("schema") == "openbook-ruby-update-profile/1", "Unknown profile schema")
    require(review.get("schema") == "openbook-ruby-update-review/1", "Unknown review schema")
    require(stage in GATES and review.get("stage") == stage, "Approval is for a different stage")
    require(review.get("profile_sha256") == hashlib.sha256(profile_raw).hexdigest(),
            "Unreviewed profile")
    require(profile.get("local_only") is True, "Only local artifacts are supported")
    require(profile.get("original", {}).get("kind") == "full-recovery",
            "Only full recovery staging is implemented; OTA reconstruction needs a separate adapter")
    require(profile["original"].get("url", "").startswith("https://"), "Missing original provenance URL")
    require(digest(original) == profile["original"].get("sha256"), "Unknown original input")
    expires = datetime.datetime.fromisoformat(review["expires_utc"].replace("Z", "+00:00"))
    require(expires.tzinfo is not None, "Approval expiry requires timezone")
    require((now or datetime.datetime.now(datetime.timezone.utc)) < expires, "Expired approval")
    require(isinstance(profile.get("target"), str) and profile["target"], "Missing exact target")
    require(isinstance(profile.get("build"), str) and profile["build"], "Missing build")
    artifacts = profile.get("artifacts")
    require(isinstance(artifacts, dict) and artifacts, "No artifacts")
    for name, expected in artifacts.items():
        require(digest(candidate / safe_name(name)) == expected, f"Artifact changed: {name}")
    tuple_sha = hashlib.sha256(canonical({"original": profile["original"],
                                         "artifacts": artifacts, "target": profile["target"],
                                         "build": profile["build"]})).hexdigest()
    require(review.get("tuple_sha256") == tuple_sha, "Review belongs to another build tuple")
    needed = []
    for current, gates in GATES.items():
        needed.extend(gates)
        if current == stage:
            break
    checks = review.get("checks", {})
    reports = {}
    for name in needed:
        check = checks.get(name, {})
        require(check.get("passed") is True, f"Gate not passed: {name}")
        filename = safe_name(check.get("report"))
        require(digest(candidate / filename) == check.get("sha256"), f"Evidence changed: {name}")
        require(check.get("tuple_sha256") == tuple_sha, f"Evidence tuple mismatch: {name}")
        reports[filename] = check["sha256"]
    if stage != "rehearsal":
        require(profile.get("hardware_eligible") is True, "Research-only profile cannot reach hardware")
    decision = {"schema": "openbook-ruby-update-decision/1", "stage": stage,
                "tuple_sha256": tuple_sha, "review_sha256": hashlib.sha256(review_raw).hexdigest(),
                "trusted_key_sha256": key_sha, "gates": needed, "accepted_for_stage": True,
                "physical_device_written": False, "automatic_install_authorized": False}
    return decision, profile, reports, profile_raw, review_raw, sig_bytes, key_bytes


def staging_bytes(original, candidate, contract, reports, metadata_bytes=0):
    """Conservative full-copy allocation; no sparse/reflink savings assumed."""
    return STAGING_OVERHEAD_BYTES + metadata_bytes + regular(original).stat().st_size + sum(
        regular(candidate / n).stat().st_size
        for n in set(contract["artifacts"]) | set(reports))


def stage_files(original, candidate, profile, review, signature, key, stage, out):
    checked = evaluate(original, candidate, profile, review, signature, key, stage)
    decision, contract, reports, profile_raw, review_raw, sig_bytes, key_bytes = checked
    out = out.absolute()
    require(not out.exists() and not out.is_symlink(), "Fresh output required")
    require(not any(p.is_symlink() for p in out.parents), "Symlink output parent refused")
    # Rename on one filesystem publishes a fully checked directory. A crash
    # before rename leaves only a private .partial directory, never an approval.
    required = staging_bytes(original, candidate, contract, reports,
                             sum(map(len, (profile_raw, review_raw, sig_bytes, key_bytes))))
    require(shutil.disk_usage(out.parent).free >= required + HOST_RESERVE_BYTES,
            "Insufficient staging disk space including 40 GiB host reserve")
    pending = Path(tempfile.mkdtemp(prefix=f".{out.name}.partial-", dir=out.parent))
    try:
        (pending / "artifacts").mkdir()
        sources = [(original, pending / "original", contract["original"]["sha256"])]
        sources.extend((candidate / n, pending / "artifacts" / n, h)
                       for n, h in (contract["artifacts"] | reports).items())
        for source, target, expected in sources:
            require(shutil.disk_usage(out.parent).free >= required + HOST_RESERVE_BYTES,
                    "Insufficient staging disk space including 40 GiB host reserve")
            source_size = regular(source).stat().st_size
            with regular(source).open("rb") as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, 4 << 20)
                dst.flush()
                os.fsync(dst.fileno())
            require(digest(target) == expected, "Input changed during copy")
            target.chmod(0o400)
            required -= source_size
        require(shutil.disk_usage(out.parent).free >= required + HOST_RESERVE_BYTES,
                "Insufficient staging disk space including 40 GiB host reserve")
        for name, data in (("profile.json", profile_raw), ("review.json", review_raw),
                           ("review.sig", sig_bytes), ("reviewer.pub", key_bytes),
                           ("decision.json", canonical(decision) + b"\n")):
            with (pending / name).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            (pending / name).chmod(0o400)
        # The included public key is an audit copy, never a trust source.
        for directory in (pending / "artifacts", pending):
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        require(not out.exists(), "Output appeared while staging")
        pending.rename(out)
        fd = os.open(out.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except BaseException:
        # Keep interrupted data for diagnosis/resume design; never publish it.
        raise
    return decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("original", "candidate", "profile", "review", "signature", "trusted-key", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--stage", choices=GATES, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = stage_files(args.original, args.candidate, args.profile, args.review,
                             args.signature, args.trusted_key, args.stage, args.out)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"REFUSED: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
