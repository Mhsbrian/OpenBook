#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute the fixed camera25 adaptation replay, on private regular files only.

Local trusted-operator CLI, NOT a remote service or release approval. The profile
pins a retained audit tuple and an independently retained derived image; it does
not prove extraction provenance from the raw recovery or upstream authenticity.
No arbitrary commands, downloads, installation, resumed partial jobs or devices.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
GIB = 2**30
RESERVE = 40 * GIB
# Conservative full-copy budgets; do not rely on sparse files or reflinks.
BUDGETS = {"validating": 64 * GIB, "auditing": 64 * GIB,
           "assembling": 48 * GIB, "verifying": GIB}
RECIPE = "camera25-input-correction-v1"
SCRIPTS = ("googlebook/compat-audit.py", "googlebook/build-input-candidate.py",
           "googlebook/input-timestamp-patch.py", "googlebook/preserve-update.py",
           "googlebook/run-input-native.py",
           "googlebook/live-image.py", "googlebook/hybrid-probe.py",
           "kernel-g14-qemu.py", "installer/bootconfig.py",
           "installer/mkproto.py", "installer/mklive.py")
TOOL_NAMES = ("checkvintf", "secilc", "checkfc", "deapexer", "debugfs_static",
              "fsck.erofs", "mkfs.erofs", "avbtool", "lpmake")
BASE_NAMES = ("ruby-live.img", "manifest.json", *(
    f"logical/{name}_a.img" for name in
    ("system", "system_ext", "product", "vendor", "vendor_dlkm", "system_dlkm")))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha_value(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def regular(path):
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink input refused")
    require(path.is_file(), "Regular file required")
    return path


def argument_path(path):
    # Reject traversal rather than letting lexical is_relative_to() accept it.
    require(".." not in path.parts, "Parent traversal refused")
    value = path.absolute()
    require(not any(p.is_symlink() for p in (value, *value.parents)), "Symlink argument refused")
    return value


def sha(path):
    with regular(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(regular(path).read_bytes(), object_pairs_hook=unique)


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def space(path, additional=0):
    free = shutil.disk_usage(path).free
    require(free >= RESERVE + additional, "Insufficient space: preserve 40 GiB host reserve")
    return free


def file_inputs(a):
    # Explicit vocabulary. Profiles contain hashes, never executable paths/commands.
    result = {"$ORIGINAL": a.original, "$INVENTORY": a.inventory, "$TEST_KEY": a.key,
              "$INPUT_PROBE": a.probe}
    result.update({"$BASE/" + n: a.base / n for n in BASE_NAMES})
    result.update({"$TOOLS/" + n: a.tools / n for n in TOOL_NAMES})
    result.update({"$REPO/scripts/" + n: REPO / "scripts" / n for n in SCRIPTS})
    return result


def audit_inventory(a):
    spec = importlib.util.spec_from_file_location("workflow_audit", HERE / "compat-audit.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    args = SimpleNamespace(ruby=a.ruby, product=a.product, tools=a.tools,
                           kernel=a.kernel, out=a.out / "audit")
    ruby = {p: a.ruby / f"fs/{p}_a" for p in audit.PARTS}
    ruby["system"] /= "system"
    ruby["odm"] = args.out / "empty"
    product = {p: a.product / p for p in audit.PARTS}
    product["odm"] = args.out / "empty"
    return audit.Audit(args).inventory((ruby, product))


def validate_inputs(a, profile):
    require(profile.get("schema") == "openbook-ruby-workflow-profile/1" and
            profile.get("recipe") == RECIPE and profile.get("local_only") is True,
            "Unknown development recipe")
    files = file_inputs(a)
    require(set(profile.get("files", {})) == set(files), "Incomplete or unknown profile input set")
    # Verify executable recipe bytes before importing the audit module.
    for name, path in files.items():
        require(sha(path) == profile["files"][name], f"Input identity changed: {name}")
    inventory = audit_inventory(a)
    require(sha_value(inventory) == profile.get("audit_inventory_sha256"),
            "Native audit tuple changed; review required")
    return inventory


def verify_audit(report, profile):
    require(report.get("schema") == "openbook-googlebook-compat-audit/1" and
            report.get("installable") is False and report.get("inputs_unchanged") is True,
            "Incomplete native audit")
    require(sha_value(report.get("input_inventory")) == profile["audit_inventory_sha256"],
            "Audit evaluated a different tuple")
    for name in ("ruby", "openbook", "hybrid-reduced"):
        case = report.get("cases", {}).get(name, {})
        require(case.get("static_checks_passed") is True, f"Native audit failed: {name}")
        for check in ("vintf", "selinux", "service_contexts"):
            result = case.get(check, {})
            require(result.get("passed") is True and result.get("exit_code") == 0,
                    f"Native audit failed: {name}/{check}")
    # The unreduced hybrid is an explicit negative control for neverallow checks.
    raw = report.get("cases", {}).get("hybrid", {}).get("selinux", {})
    require(raw.get("passed") is False and isinstance(raw.get("exit_code"), int)
            and raw["exit_code"] != 0, "Missing failed raw-hybrid policy control")


def verify_candidate(out, profile):
    result, manifest = read_json(out / "result.json"), read_json(out / "manifest.json")
    require(result.get("schema") == "openbook-ruby-input-candidate/1", "Unknown assembly result")
    for field in ("complete", "all_inode_xattrs_identical", "protected_ranges_identical", "source_unchanged"):
        require(result.get(field) is True, f"Assembly check failed: {field}")
    require(result.get("physical_device_written") is False and manifest.get("installable") is False,
            "Unexpected deployment claim")
    require(result.get("changed_files") == ["/system/lib64/libinputflinger.so"], "Unexpected changed files")
    require(result.get("source_sha256") == profile["files"]["$BASE/ruby-live.img"], "Wrong assembly source")
    actual = sha(out / "ruby-live.img")
    require(actual == result.get("image_sha256") == manifest.get("image_sha256"), "Candidate hash mismatch")
    return actual


def run_command(command, log, workspace, timeout=1800):
    """Own and reap the whole subprocess group on failure/cancellation/timeout."""
    started = time.monotonic()
    with log.open("xb") as stream:
        process = subprocess.Popen(list(map(str, command)), stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            while True:
                space(workspace)
                if time.monotonic() - started > timeout:
                    raise TimeoutError("Native phase timed out")
                try:
                    code = process.wait(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    pass
            require(code == 0, f"Native phase failed (exit {code}); see {log.name}")
        except BaseException:
            # Descendants can survive even if their parent already exited.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise


def cleanup(out, report):
    """After all child processes/checks finish, remove only this job's scratch.

    Keep the final candidate, manifests, all diagnostic logs and metadata. The
    exact private deletion list is durable before deleting anything. Extracted
    APEX files can be reconstructed from pinned inputs; they are never evidence.
    """
    paths = [out / "candidate" / n for n in
             ("source", "rebuilt", "esp-before", "esp-after", "avb",
              "system_a.img", "super.img", "esp.img", "vbmeta.img")]
    for origin, records in report["apexes"].items():
        require(origin in ("ruby", "openbook"), "Unknown APEX origin")
        for record in records:
            name = record["module"]
            require(name and all(c.isalnum() or c in "_.-" for c in name)
                    and name not in (".", ".."), "Unsafe APEX cleanup name")
            paths.append(out / "audit" / (origin + "-apex") / name)
    for path in paths:
        require(not path.is_symlink() and path.resolve().is_relative_to(out.resolve()),
                "Cleanup target escaped this job")
    before = shutil.disk_usage(out).free
    manifest = {"schema": "openbook-ruby-workflow-cleanup/1",
                "paths": [str(p) for p in paths if p.exists()], "free_before_bytes": before,
                "complete": False, "children_reaped": True}
    atomic_json(out / "cleanup.json", manifest)
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
    after = shutil.disk_usage(out).free
    manifest.update(complete=True, free_after_bytes=after, observed_free_delta_bytes=after-before)
    atomic_json(out / "cleanup.json", manifest)
    return {k: v for k, v in manifest.items() if k != "paths"}


def execute(a, runner=run_command):
    # Called with the shared track lock held. No existing/partial job is resumed.
    a.out.mkdir(mode=0o700, exist_ok=False)
    job = {"schema": "openbook-ruby-update-job/1", "recipe": RECIPE,
           "state": "created", "history": [], "physical_device_written": False,
           "installation_available": False, "release_approved": False,
           "upstream_authenticated": False, "raw_to_derived_provenance_verified": False,
           "workflow_sha256": sha(Path(__file__)), "host_reserve_bytes": RESERVE}

    def state(name, **fields):
        job.update(state=name, **fields)
        job["history"].append({"state": name, "time_unix": time.time(),
                               "free_bytes": shutil.disk_usage(a.out).free})
        atomic_json(a.out / "job.json", job)

    try:
        state("validating")
        space(a.out, BUDGETS["validating"])
        profile = read_json(a.profile)
        require(profile.get("container_image") == os.environ.get("OPENBOOK_WORKFLOW_CONTAINER_ID")
                and isinstance(profile.get("container_image"), str), "Container identity mismatch")
        job["profile_sha256"] = sha(a.profile)
        inputs = validate_inputs(a, profile)
        atomic_json(a.out / "input-inventory.json", inputs)
        atomic_json(a.out / "profile.json", profile)
        state("auditing")
        space(a.out, BUDGETS["auditing"])
        runner([sys.executable, HERE / "compat-audit.py", "--ruby", a.ruby,
                "--product", a.product, "--kernel", a.kernel, "--tools", a.tools,
                "--out", a.out / "audit"], a.out / "audit.log", a.out)
        verify_audit(read_json(a.out / "audit/report.json"), profile)
        # Do not build from files changed while the audit ran.
        validate_inputs(a, profile)
        state("assembling")
        space(a.out, BUDGETS["assembling"])
        runner([sys.executable, HERE / "build-input-candidate.py", "--base", a.base,
                "--tools", a.tools, "--inventory", a.inventory, "--key", a.key,
                "--out", a.out / "candidate"], a.out / "assembly.log", a.out)
        state("verifying")
        space(a.out, BUDGETS["verifying"])
        candidate = verify_candidate(a.out / "candidate", profile)
        runner([sys.executable, HERE / "run-input-native.py", "--probe", a.probe,
                "--ruby-system", a.ruby / "fs/system_a/system",
                "--apexes", a.out / "audit/ruby-apex", "--patched-library",
                a.out / "candidate/rebuilt/system/lib64/libinputflinger.so",
                "--output", a.out / "input-native.json"], a.out / "input-native.log", a.out)
        validate_inputs(a, profile)
        require(sha(a.profile) == job["profile_sha256"], "Profile changed during job")
        state("cleaning")
        cleaned = cleanup(a.out, read_json(a.out / "audit/report.json"))
        state("assembled_unqualified", candidate_sha256=candidate,
              cleanup=cleaned, input_native_sha256=sha(a.out / "input-native.json"),
              audit_report_sha256=sha(a.out / "audit/report.json"),
              assembly_result_sha256=sha(a.out / "candidate/result.json"),
              remaining_gates=["upstream trust and extraction provenance", "installer source pin",
                               "encrypted-data boot/stability", "containment", "recovery/data rollback",
                               "hardware trial and release approval"])
        return 0
    except BaseException as error:
        state("failed", failed_phase=job["state"], error=str(error) or type(error).__name__)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("original", "base", "ruby", "product", "kernel", "tools", "inventory", "probe", "key", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--profile", type=Path,
                        default=REPO / "config/image-bases/ruby-workflow-camera25.json")
    a = parser.parse_args()
    require(Path("/.dockerenv").exists(), "Use the pinned installer container, with regular image inputs only")
    workspace = Path(os.environ["OPENBOOK_HOME"]) / "installer"
    workspace = workspace.resolve(strict=True)
    for name, value in vars(a).items():
        setattr(a, name, argument_path(value))
    require(a.out.parent.is_dir() and a.out.is_relative_to(workspace / "work"),
            "Output must be a fresh child of the private installer/work directory")
    for source in (a.base, a.ruby, a.product, a.kernel, a.tools, REPO):
        require(source.is_dir() and not a.out.is_relative_to(source), "Output overlaps an input tree")
    os.umask(0o077)
    # Same track lock as release builds. Lock inode persists; never unlink it.
    lock = workspace / ".ruby-release.lock"
    with os.fdopen(os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600), "r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return execute(a)


if __name__ == "__main__":
    def interrupted(signum, frame):
        raise InterruptedError(f"Interrupted by signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        raise SystemExit(main())
    except (ValueError, OSError, TimeoutError, KeyboardInterrupt) as error:
        print(f"Workflow stopped: {error}", file=sys.stderr)
        raise SystemExit(2)
