#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rehearse the OTA guard using ONLY a disposable camera25 VM and its soft TPM.

Applies the candidate to a private synthetic VM clone, then runs a bounded
offline UEFI test. No physical device, owner backup or install
plan is supported. All processes finish before this command returns.
"""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
s = importlib.util.spec_from_file_location("mq", HERE / "migration-qemu.py")
q = importlib.util.module_from_spec(s); s.loader.exec_module(q)
s = importlib.util.spec_from_file_location("preserve", HERE / "preserve-update.py")
p = importlib.util.module_from_spec(s); s.loader.exec_module(p)

EXPECTED = {
    "both Binder services registered", "guard identification", "harmless descriptor available",
    "ordinary URL apply", "ordinary FD apply", "stable FD apply",
    "ordinary postinstall", "stable postinstall", "resume", "suspend", "cancel",
    "reset status", "slot activation", "slot reset", "space allocation",
    "ordinary bind", "ordinary status callback", "stable bind", "stable status callback",
    "ordinary unbind", "stable unbind", "real cleanup accepted",
    "real cleanup callback received", "real cleanup succeeded on quiescent VM",
}


def probe_checks(observed):
    # Kernel console output can follow a completed userspace line before its
    # newline arrives. Accept only exact known names and that kernel boundary.
    alternatives = "|".join(re.escape(name) for name in sorted(EXPECTED, key=len, reverse=True))
    passes = set(re.findall(r"(?m)^PASS (" + alternatives +
                            r")(?=\r?$|\[\s*\d+\.\d+\]\[)", observed))
    return {"ipc_checks_passed": sorted(passes),
            "ipc_checks_missing": sorted(EXPECTED - passes),
            "ipc_failures": re.findall(r"(?m)^FAIL (.+)$", observed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("candidate", "base-manifest", "synthetic-vm", "tpm-state-from", "qemu", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--synthetic-vm-sha256", required=True)
    parser.add_argument("--seconds", type=int, default=480, choices=range(120, 1801))
    a = parser.parse_args()
    q.m.require(Path("/.dockerenv").exists(), "Use inst-docker.sh; synthetic VM only")
    os.umask(0o077)
    source = p.regular(a.synthetic_vm)
    candidate = p.regular(a.candidate / "ruby-live.img")
    new = json.loads(p.regular(a.candidate / "manifest.json").read_text())
    guard = new.get("experimental_ota_guard", {})
    q.m.require(guard.get("deployment_eligible") is False and
                guard.get("probe_replaces_update_engine_client") is True,
                "Requires disposable guard candidate with IPC probe")
    q.m.require(p.h.audit.sha(source) == a.synthetic_vm_sha256, "Synthetic baseline hash mismatch")
    q.m.require(p.h.audit.sha(candidate) == new["image_sha256"], "Candidate hash mismatch")
    def validate_experiment(old, candidate_manifest):
        check = copy.deepcopy(candidate_manifest)
        check["logical_sha256"]["system"] = old["logical_sha256"]["system"]
        p.compatible(old, check)
        q.m.require(old["logical_sha256"]["vendor"] == check["logical_sha256"]["vendor"],
                    "Concurrent vendor change is outside the guard experiment")
    a.out.mkdir(mode=0o700)
    staged = a.out / "input"
    p.prepare(source, a.synthetic_vm_sha256, a.base_manifest, a.candidate, staged,
              experiment_validator=validate_experiment)
    disk = staged / "ruby-live.img"
    # Verify that the host's physical writer refuses the experimental plan.
    spec = importlib.util.spec_from_file_location("apply", HERE / "apply-preserved-update.py")
    applier = importlib.util.module_from_spec(spec); spec.loader.exec_module(applier)
    try:
        applier.validate_plan(staged, source)
    except ValueError as error:
        q.m.require(str(error) == "Incomplete preserving update", "Unexpected writer refusal")
    else:
        raise ValueError("Physical writer accepted an experimental clone")
    keys_before = q.metadata_key_hashes(disk, a.out, "guard-before")
    result_dir = a.out / "run"
    subprocess.run(["python3", str(HERE / "run-probe.py"), "--input", str(staged),
                    "--out", str(result_dir), "--qemu", str(a.qemu),
                    "--accel", "tcg", "--uefi-usb", "--usb-logs", "--tpm",
                    "--tpm-state-from", str(a.tpm_state_from), "--audio",
                    "--timeout", str(a.seconds)], check=True)
    keys_after = q.metadata_key_hashes(result_dir / "usb-test.img", a.out, "guard-after")
    observed = (result_dir / "serial.log").read_text(errors="replace").replace("\r", "")
    checks = probe_checks(observed)
    observation = json.loads((result_dir / "result.json").read_text())
    probe_exits = list(map(int, re.findall(
        r"Service 'openbook\.ota-guard-probe' \(pid \d+\) exited with status (\d+)", observed)))
    result = dict(schema="openbook-ruby-ota-guard-rehearsal/1",
                  boot_completed=q.r.boot_completed_reported(observed),
                  observation_completed=observation["observation_window_elapsed"],
                  elapsed_s=observation["elapsed_s"],
                  source_tpm_unchanged=observation["source_tpm_unchanged"],
                  decoy_unchanged=observation["decoy_unchanged"],
                  enforcing_reported=bool(re.search(r"(?m)^Enforcing$", observed)),
                  avb_handoff_errors=sorted(set(line for line in observed.splitlines()
                      if "vbmeta size mismatch" in line or "Failed to verify vbmeta digest" in line)),
                  **checks,
                  probe_exit_statuses=probe_exits,
                  metadata_key_files=len(keys_before), metadata_keys_identical=keys_before == keys_after,
                  source_unchanged=p.h.audit.sha(source) == a.synthetic_vm_sha256,
                  candidate_unchanged=p.h.audit.sha(candidate) ==
                      json.loads((a.candidate / "manifest.json").read_text())["image_sha256"],
                  serial_sha256=p.h.audit.sha(result_dir / "serial.log"),
                  runtime_findings=q.r.runtime_findings(observed),
                  deployment_eligible=False, hardware_tested=False, unattended_safe=False)
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    q.m.require(result["boot_completed"] and result["observation_completed"]
                and result["source_tpm_unchanged"] and result["decoy_unchanged"]
                and not result["avb_handoff_errors"]
                and result["enforcing_reported"] and probe_exits and set(probe_exits) == {0}
                and not result["ipc_checks_missing"] and not result["ipc_failures"]
                and result["metadata_keys_identical"] and len(keys_before) == 4
                and result["source_unchanged"] and result["candidate_unchanged"],
                "Guard rehearsal failed; inspect retained evidence")


if __name__ == "__main__":
    main()
