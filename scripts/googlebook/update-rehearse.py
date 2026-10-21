#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rehearse one pinned adaptation job on a known synthetic encrypted VM.

Two bounded offline boots, with copied software TPM state and a cold restart.
No owner data, device writer, OTA guard, rollback or release qualification.
The completed assembly job is immutable; this creates a separate linked record.
"""
import argparse
import copy
import fcntl
import importlib.util
import os
from pathlib import Path
import re
import shutil
import signal
import sys
import time

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


w = load("workflow", HERE / "update-workflow.py")
PROFILE = w.REPO / "config/image-bases/ruby-rehearsal-camera25.json"
DEPENDENCIES = (*w.SCRIPTS, "googlebook/update-workflow.py", "googlebook/run-probe.py",
                "googlebook/migration-qemu.py", "googlebook/migrate.py",
                "googlebook/apply-preserved-update.py")
OBSERVATION_SECONDS = 760
PEAK_BYTES = 64 * w.GIB


def tree_identity(path):
    w.require(path.is_dir() and not path.is_symlink(), "Regular software TPM directory required")
    files = sorted(path.iterdir())
    w.require(files and all(p.is_file() and not p.is_symlink() for p in files), "Unexpected TPM state files")
    return w.sha_value({p.name: w.sha(p) for p in files})


def policy_identity(text):
    # Only a runtime verification of this path, not a command or init-script echo.
    values = sorted(set(re.findall(
        r"init: Verified that /data/misc has the encryption policy ([0-9a-f]{32}) "
        r"v2 modes ([0-9]+/[0-9]+) flags (0x[0-9a-f]+)(?=\r?$|\n)", text, re.MULTILINE)))
    return w.sha_value(values) if len(values) == 1 else None


def validate(a):
    profile = w.read_json(PROFILE)
    w.require(profile.get("schema") == "openbook-ruby-rehearsal-profile/1" and
              profile.get("fixture_kind") == "synthetic-vm" and
              profile.get("container_image") == os.environ.get("OPENBOOK_WORKFLOW_CONTAINER_ID"),
              "Unknown rehearsal profile/container")
    expected_scripts = {"scripts/" + name for name in DEPENDENCIES}
    w.require(set(profile["scripts"]) == expected_scripts, "Incomplete rehearsal recipe pins")
    for name, digest in profile["scripts"].items():
        w.require(w.sha(w.REPO / name) == digest, f"Recipe changed: {name}")
    w.require(w.sha(a.fixture) == profile["fixture_sha256"], "Unknown synthetic fixture")
    w.require(tree_identity(a.tpm) == profile["tpm_tree_sha256"], "Wrong synthetic software TPM")
    w.require(w.sha(a.base_manifest) == profile["base_manifest_sha256"], "Wrong baseline manifest")
    w.require(w.sha(a.qemu) == profile["qemu_sha256"], "Unknown QEMU")
    job = w.read_json(a.job / "job.json")
    w.require(job.get("schema") == "openbook-ruby-update-job/1" and
              job.get("state") == "assembled_unqualified" and
              job.get("candidate_sha256") == profile["candidate_sha256"], "Wrong or incomplete assembly job")
    local_profile = w.read_json(a.job / "profile.json")
    w.require(w.sha(a.job / "profile.json") == job["profile_sha256"] ==
              w.sha(w.REPO / "config/image-bases/ruby-workflow-camera25.json"),
              "Assembly profile mismatch")
    for field, file in (("audit_report_sha256", "audit/report.json"),
                        ("assembly_result_sha256", "candidate/result.json"),
                        ("input_native_sha256", "input-native.json")):
        w.require(w.sha(a.job / file) == job[field], "Assembly evidence changed")
    w.verify_audit(w.read_json(a.job / "audit/report.json"), local_profile)
    w.require(w.verify_candidate(a.job / "candidate", local_profile) == profile["candidate_sha256"],
              "Candidate identity mismatch")
    return profile


def prepare(a):
    profile = validate(a)
    p = load("preserve", HERE / "preserve-update.py")

    def exact_transform(old, new):
        w.require(new["image_sha256"] == profile["candidate_sha256"], "Unreviewed VM transform")
        check = copy.deepcopy(new)
        check["logical_sha256"]["system"] = old["logical_sha256"]["system"]
        p.compatible(old, check)
        w.require(new["logical_sha256"]["vendor"] == old["logical_sha256"]["vendor"],
                  "Concurrent vendor change refused")

    p.prepare(a.fixture, profile["fixture_sha256"], a.base_manifest,
              a.job / "candidate", a.out / "prepared", experiment_validator=exact_transform)
    applier = load("apply", HERE / "apply-preserved-update.py")
    try:
        applier.validate_plan(a.out / "prepared", a.fixture)
    except ValueError as error:
        w.require(str(error) == "Incomplete preserving update", "Unexpected writer refusal")
    else:
        raise ValueError("Physical writer accepted the VM experiment")


def verdict(observation, text, keys_before, keys_after, profile):
    """Independent fail-closed health verdict, including later crashes."""
    text = text.replace("\r", "")
    boot_lines = re.findall(r"(?m)^(?:OPENBOOK_RUBY_BOOT_COMPLETED=1|\[sys.boot_completed\]: \[1\]|sys.boot_completed=1)$", text)
    findings = observation.get("runtime_findings", {})
    fatal = sorted(set(line.strip() for line in text.splitlines()
                       if "Fatal signal " in line or "FATAL EXCEPTION:" in line))
    checks = {
        "observation_completed": observation.get("observation_window_elapsed") is True and
                                 observation.get("elapsed_s", 0) >= OBSERVATION_SECONDS,
        "qemu_identity": observation.get("qemu_sha256") == profile["qemu_sha256"],
        "qemu_exited_cleanly": observation.get("qemu_exit") == 0,
        "source_image_unchanged": observation.get("input_unchanged") is True,
        "source_tpm_unchanged": observation.get("source_tpm_unchanged") is True,
        "software_tpm_restored": observation.get("software_tpm_restored") is True,
        "decoy_unchanged": observation.get("decoy_unchanged") is True,
        "fresh_capture_complete": observation.get("usb_capture_finished") is True and
                                  observation.get("logs_readback_exit") == 0,
        "boot_completed": bool(boot_lines) and observation.get("boot_completed_reported") is True,
        "enforcing_observed": bool(re.search(r"(?m)^Enforcing$", text)),
        "encrypted_data_mount_observed": bool(re.search(
            r"(?m)^/dev/block/dm-[0-9]+ /data f2fs (?:[^\n ]*,)?inlinecrypt(?:,| )", text)),
        "encryption_policy_retained": policy_identity(text) == profile["data_policy_sha256"],
        "four_metadata_keys_retained": len(keys_before) == 4 and keys_before == keys_after,
        "no_kernel_panic": observation.get("kernel_panic") is False and "Kernel panic" not in text,
        "no_sigill": observation.get("sigill") is False and "signal 4 (SIGILL)" not in text,
        "no_fatal_exception": not fatal,
        "no_system_server_crash": findings.get("system_server_fatal_signals") == [],
        "no_zygote_restart": findings.get("zygote_exit_events") == 0,
        "no_mmd_abort": findings.get("mmd_setup_abort_seen") is False,
        "no_camera_abort": findings.get("camera_provider_abort_seen") is False,
        "no_avb_handoff_error": not any(s in text for s in (
            "vbmeta size mismatch", "Failed to verify vbmeta digest")),
    }
    return {"checks": checks, "passed": all(checks.values()),
            "blockers": [name for name, passed in checks.items() if not passed],
            "fatal_lines": fatal, "metadata_key_files": len(keys_before),
            "data_policy_sha256": policy_identity(text),
            "owner_credentials_tested": False, "app_data_contents_verified": False,
            "rollback_tested": False, "physical_device_written": False}


def clean_scratch(out):
    # Only completed disposable copies. Evidence and the input job remain.
    paths = [out / "prepared/ruby-live.img", out / "prepared/esp.img",
             out / "prepared/esp-before", out / "prepared/esp-after",
             out / "restart-input/ruby-live.img"]
    for phase in ("boot", "restart"):
        paths += [out / phase / n for n in ("usb-test.img", "internal-decoy.img")]
    paths += list(out.glob("*-metadata.img")) + list(out.glob("*-metadata-keys"))
    for p in paths:
        w.require(not p.is_symlink() and p.resolve().is_relative_to(out.resolve()), "Unsafe cleanup path")
    record = dict(paths=[str(p) for p in paths if p.exists()], complete=False,
                  free_before_bytes=shutil.disk_usage(out).free, children_reaped=True)
    w.atomic_json(out / "cleanup.json", record)
    for p in paths:
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    record.update(complete=True, free_after_bytes=shutil.disk_usage(out).free)
    record["observed_free_delta_bytes"] = record["free_after_bytes"] - record["free_before_bytes"]
    w.atomic_json(out / "cleanup.json", record)
    return {k: v for k, v in record.items() if k != "paths"}


def execute(a):
    a.out.mkdir(mode=0o700, exist_ok=False)
    record = dict(schema="openbook-ruby-rehearsal-job/1", state="created", history=[],
                  cases={}, physical_device_written=False, release_approved=False,
                  rollback_implemented=False, hardware_tested=False,
                  peak_additional_budget_bytes=PEAK_BYTES, reserve_bytes=w.RESERVE,
                  rehearsal_sha256=w.sha(Path(__file__)))

    def state(name, **fields):
        record.update(state=name, **fields)
        record["history"].append(dict(state=name, time_unix=time.time(), free_bytes=shutil.disk_usage(a.out).free))
        w.atomic_json(a.out / "job.json", record)

    try:
        state("validating")
        w.space(a.out, PEAK_BYTES)
        profile = validate(a)
        record.update(assembly_job_sha256=w.sha(a.job / "job.json"), profile_sha256=w.sha(PROFILE),
                      candidate_sha256=profile["candidate_sha256"], fixture_sha256=profile["fixture_sha256"])
        w.atomic_json(a.out / "profile.json", profile)
        state("preparing")
        command = [sys.executable, Path(__file__), "--prepare-only"]
        for name in ("job", "fixture", "tpm", "base_manifest", "qemu", "out"):
            command += ["--" + name.replace("_", "-"), getattr(a, name)]
        w.run_command(command, a.out / "prepare.log", a.out)
        q = load("migration_qemu", HERE / "migration-qemu.py")
        keys = q.metadata_key_hashes(a.fixture, a.out, "source")
        w.require(len(keys) == 4, "Expected four synthetic metadata key files")
        # Private comparisons only. Key blobs and hashes are never public evidence.
        w.atomic_json(a.out / "private-key-comparisons.json", {"source": keys})
        staged, tpm = a.out / "prepared", a.tpm
        for phase in ("boot", "restart"):
            state(phase)
            w.space(a.out, 40 * w.GIB if phase == "boot" else 28 * w.GIB)
            command = [sys.executable, HERE / "run-probe.py", "--input", staged,
                       "--out", a.out / phase, "--qemu", a.qemu, "--accel", "tcg",
                       "--uefi-usb", "--usb-logs", "--tpm", "--tpm-state-from", tpm,
                       "--audio", "--timeout", str(OBSERVATION_SECONDS)]
            # A nonzero harness result can still carry diagnostic evidence.
            command_error = None
            try:
                w.run_command(command, a.out / (phase + ".log"), a.out,
                              timeout=OBSERVATION_SECONDS + 300)
            except ValueError as error:
                command_error = str(error)
            observation = w.read_json(a.out / phase / "result.json")
            disk = a.out / phase / "usb-test.img"
            after = q.metadata_key_hashes(disk, a.out, phase)
            text = w.regular(a.out / phase / "serial.log").read_text(errors="replace")
            outcome = verdict(observation, text, keys, after, profile)
            outcome.update(observation_sha256=w.sha(a.out / phase / "result.json"),
                           serial_sha256=w.sha(a.out / phase / "serial.log"))
            if command_error:
                outcome.update(passed=False, command_error=command_error)
                outcome["blockers"].append("harness_command_failed")
            record["cases"][phase] = outcome
            w.atomic_json(a.out / (phase + "-verdict.json"), outcome)
            private = w.read_json(a.out / "private-key-comparisons.json")
            private[phase] = after
            w.atomic_json(a.out / "private-key-comparisons.json", private)
            # Do not carry damaged or incomplete observations into another boot.
            carry_checks = ("observation_completed", "source_image_unchanged", "source_tpm_unchanged",
                            "decoy_unchanged", "four_metadata_keys_retained", "encryption_policy_retained")
            if not all(outcome["checks"][key] for key in carry_checks):
                break
            if phase == "boot":
                state("preparing_restart")
                w.space(a.out, 28 * w.GIB)
                staged = a.out / "restart-input"
                staged.mkdir()
                w.run_command(["cp", "--reflink=auto", "--sparse=always", disk, staged / "ruby-live.img"],
                              a.out / "restart-copy.log", a.out)
                manifest = w.read_json(a.out / "prepared/manifest.json")
                manifest["image_sha256"] = w.sha(staged / "ruby-live.img")
                w.require(manifest["image_sha256"] == w.sha(disk), "Restart copy mismatch")
                w.atomic_json(staged / "manifest.json", manifest)
                tpm = a.out / "boot/tpm-state"
        state("verifying")
        validate(a)
        w.require(w.sha(a.job / "job.json") == record["assembly_job_sha256"] and
                  w.sha(PROFILE) == record["profile_sha256"], "Parent job/profile changed during rehearsal")
        record["inputs_unchanged"] = True
        passed = set(record["cases"]) == {"boot", "restart"} and all(v["passed"] for v in record["cases"].values())
        state("cleaning")
        cleanup = clean_scratch(a.out)
        state("rehearsed_unqualified" if passed else "held", cleanup=cleanup,
              remaining_gates=["upstream trust/provenance", "owner app/PIN data", "long-term stability",
                               "production containment", "automatic fallback/data rollback", "hardware/release approval"])
        return 0 if passed else 2
    except BaseException as error:
        state("failed", failed_phase=record["state"], error=str(error) or type(error).__name__)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("job", "fixture", "tpm", "base-manifest", "qemu", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--prepare-only", action="store_true", help=argparse.SUPPRESS)
    a = parser.parse_args()
    w.require(Path("/.dockerenv").exists(), "Pinned offline container required")
    for name in ("job", "fixture", "tpm", "base_manifest", "qemu", "out"):
        value = w.argument_path(getattr(a, name))
        w.require(not any(c in str(value) for c in ",\n\r"), "Unsafe QEMU path")
        setattr(a, name, value)
    workspace = Path(os.environ["OPENBOOK_HOME"]).resolve(strict=True) / "installer"
    w.require(a.out.parent.is_dir() and a.out.is_relative_to(workspace / "work"), "Private output required")
    for root in (a.job, a.tpm, a.fixture.parent, a.base_manifest.parent, a.qemu.parent, w.REPO):
        w.require(not a.out.is_relative_to(root), "Output overlaps an input")
    os.umask(0o077)
    lock = workspace / ".ruby-release.lock"
    if a.prepare_only:
        # Internal child uses the parent's lock and pre-existing durable record.
        parent = w.read_json(a.out / "job.json")
        w.require(parent.get("schema") == "openbook-ruby-rehearsal-job/1" and
                  parent.get("state") == "preparing", "Preparation requires an active parent job")
        with os.fdopen(os.open(lock, os.O_RDWR | os.O_NOFOLLOW), "r+") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                prepare(a)
                return 0
            raise ValueError("Preparation requires the parent's held track lock")
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
        print(f"Rehearsal stopped: {error}", file=sys.stderr)
        raise SystemExit(2)
