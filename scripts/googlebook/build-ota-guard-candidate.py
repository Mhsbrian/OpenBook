#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a disposable camera25 OTA guard experiment. Never deploy to hardware.

Reuses the exact-baseline EROFS/AVB reassembler. Replaces the updater, and uses
the existing updater-client path for a bounded Binder probe after boot.
The stock service still starts normally. No settings, apps or data are inputs.
"""
import argparse
import importlib.util
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("builder", HERE / "build-input-candidate.py")
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
q = b.load("quarantine", "update-quarantine.py")

TEST_SERVICE = """
# Disposable VM only: this client path contains the guard IPC test.
service openbook.ota-guard-probe /system/bin/sh -c "exec /system/bin/update_engine_client --disposable-vm"
    user shell
    group shell system log readproc
    seclabel u:r:shell:s0
    console ttyS0
    disabled
    oneshot

on property:sys.boot_completed=1
    start openbook.ota-guard-probe
"""

TEST_POLICY = """
; Disposable VM harness only. Production shell callers must remain denied.
(allow shell update_engine (binder (call transfer)))
(allow update_engine shell (binder (call transfer)))
(allow shell update_engine (fd (use)))
(allow update_engine shell (fd (use)))
"""


def test_policy(a, source):
    """Compile exact image policy inputs with neverallow checks before packaging."""
    old = b.json.loads((a.base / "manifest.json").read_text())
    roots = {}
    for name in ("vendor", "system_ext", "product"):
        image = b.p.regular(a.base / f"logical/{name}_a.img")
        if b.p.h.audit.sha(image) != old["logical_sha256"][name]:
            raise ValueError("Policy input image changed")
        roots[name] = a.out / f"policy-{name}"
        b.p.h.run(a.tools / "fsck.erofs", f"--extract={roots[name]}", image)
    se = source / "system/etc/selinux"
    vendor = roots["vendor"] / "etc/selinux"
    version = (vendor / "plat_sepolicy_vers.txt").read_text().strip()
    genfs = (vendor / "genfs_labels_version.txt").read_text().strip()
    if version != "202604" or genfs != "202604":
        raise ValueError("Unreviewed policy mapping/genfs version")
    plat = (se / "plat_sepolicy.cil").read_bytes()
    mapping = (se / f"mapping/{version}.cil").read_bytes()
    if (se / "plat_sepolicy_and_mapping.sha256").read_text().strip() != b.p.hashlib.sha256(plat + mapping).hexdigest():
        raise ValueError("Unrecognized platform policy hash contract")
    updated = plat + TEST_POLICY.encode()
    local = a.out / "probe-plat.cil"; local.write_bytes(updated)
    inputs = [local, se / f"mapping/{version}.cil",
              vendor / "plat_pub_versioned.cil", vendor / "vendor_sepolicy.cil",
              se / f"plat_sepolicy_genfs_{genfs}.cil"]
    for name in ("system_ext", "product"):
        directory = roots[name] / "etc/selinux"
        inputs += [directory / f"{name}_sepolicy.cil", directory / f"mapping/{version}.cil"]
    policy = a.out / "probe-policy.bin"
    b.p.h.run(a.tools / "secilc", "-m", "-M", "true", "-G", "-c", "33",
              "-o", policy, "-f", "/dev/null", *inputs)
    # Updating the real platform hash invalidates the vendor's cached policy.
    # Android init recompiles these same sources; no permissive or -N build gate.
    replacements = {
        "/system/etc/selinux/plat_sepolicy.cil": updated,
        "/system/etc/selinux/plat_sepolicy_and_mapping.sha256":
            (b.p.hashlib.sha256(updated + mapping).hexdigest() + "\n").encode(),
    }
    return replacements, {"scope": "shell test-client Binder/FD access only; never deploy",
                          "neverallow_checked": True, "policy_sha256": b.p.h.audit.sha(policy),
                          "rules_sha256": b.p.hashlib.sha256(TEST_POLICY.encode()).hexdigest(),
                          "runtime_recompilation_required": True}


def binary(path, expected):
    path = b.p.regular(path)
    if b.p.h.audit.sha(path) != expected:
        raise ValueError("Build artifact differs from supplied SHA-256")
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x02\x01" or data[18:20] != b"\x3e\x00":
        raise ValueError("Expected an x86_64 ELF artifact")
    if b"OpenBook: OS installation is disabled pending a qualified update path" not in data:
        raise ValueError("Artifact is missing the compiled guard policy")
    return data


def build(a):
    engine = binary(a.engine, a.engine_sha256)
    probe = binary(a.probe, a.probe_sha256)
    if engine == probe:
        raise ValueError("Engine and probe must be distinct build artifacts")

    def transform(source):
        rc = source / "system/etc/init/update_engine.rc"
        if rc.read_text() != q.STOCK_RC:
            raise ValueError("Unrecognized stock init contract")
        replacements = {
            "/system/bin/update_engine": engine,
            "/system/bin/update_engine_client": probe,
            "/system/etc/init/update_engine.rc": (q.STOCK_RC + TEST_SERVICE).encode(),
        }
        policy_files, policy_record = test_policy(a, source)
        replacements.update(policy_files)
        return replacements, {"experimental_ota_guard": {
            "deployment_eligible": False, "hardware_validated": False,
            "unattended_safe": False, "probe_replaces_update_engine_client": True,
            "engine_sha256": a.engine_sha256, "probe_sha256": a.probe_sha256,
            "test_harness_policy": policy_record,
            "files": {name: b.p.hashlib.sha256(data).hexdigest()
                      for name, data in replacements.items()},
            "scope": "normal-boot Binder installation requests; recovery and independent downloads uncontained",
        }}
    b.build_system(a, transform, "openbook-ruby-ota-guard-candidate/1")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "tools", "inventory", "key", "out", "engine", "probe"):
        p.add_argument("--" + name, type=Path, required=True)
    for name in ("engine-sha256", "probe-sha256"):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Use inst-docker.sh; disposable regular images only")
    os.umask(0o077)
    build(a)
