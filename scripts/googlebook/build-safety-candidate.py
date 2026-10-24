#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Neutralise the Google security chip firmware tools in a Ruby candidate's system (ANAL-251).

Through the same exact-inventory reassembler as every OpenBook candidate (build-input-candidate.py),
these Google files are replaced by OpenBook's (device/anybook/common/safety/):
  /system/etc/init/gscutil.rc            no gscutil perform-os-startup at boot (it stages Google security
                                         chip firmware and sends it commands through /dev/tpm0, the PC's
                                         firmware TPM); the /metadata/gscutil directory is still made
  /system/etc/init/gscutil-executor.rc   no IGscutilExecutor service (how Google's postinstall installs
                                         security chip firmware)
Only those two files change, and only in size. rebase-google-build.py and the on-laptop adapter carry
them onto later Google builds as changed paths: if Google changes either file, they stop (fail closed).

Fail-closed checks:
  - each replacement matches its pin in firmware-safety.json, and each Google file being replaced is
    the reviewed original (its google_sha256): a different file means Google changed it, so review first;
  - the finished candidate's system, system_ext, product and vendor (APEX init scripts included) pass
    check-firmware-safety.py: no unreviewed firmware/TPM/EC trigger and no forbidden tool.
--vm-check adds a disposable service reporting the security services to the serial console (FWS_*
lines); such a candidate is marked not deployable.

usage: build-safety-candidate.py --base STAGED_CANDIDATE --base-sha256 SHA --tools AOSP_HOST_BIN
                                 --inventory erofs-inventory --key AVB_KEY --out DIR [--vm-check]
Container only (inst-docker.sh); regular image files.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


b = load("builder", "build-input-candidate.py")
check = load("safety", "check-firmware-safety.py")

SCOPE = ("Google security chip (GSC) firmware tools neutralised: no gscutil perform-os-startup at boot and no "
         "IGscutilExecutor service; gscd, check_tpm_clear and udsattestation keep running (standard TPM 2.0 "
         "commands; Trusty's secure storage uses gscd)")
CHECKED = ("system_ext", "product", "vendor")
VM_CHECK_RC = b"""# Disposable VM test only (ANAL-251): report the security services to the serial console. Never deploy.
service openbook_safety_vmcheck /system/bin/sh /system/etc/openbook-safety-vmcheck.sh
    user shell
    group shell log readproc
    seclabel u:r:shell:s0
    console ttyS0
    disabled
    oneshot

# After the base image's own console service (openbook.ruby.probe) has ended: its exit takes the shared
# console from services started before it.
on property:sys.boot_completed=1 && property:init.svc.openbook.ruby.probe=stopped
    start openbook_safety_vmcheck
"""
VM_CHECK_SH = b"""#!/system/bin/sh
# Disposable VM test only (ANAL-251): the security services after boot, as FWS_* lines. Never deploy.
sleep 60
echo "FWS_VMCHECK begin"
echo "FWS_BOOT $(getprop sys.boot_completed)"
getprop | grep -E 'init\\.svc\\.(android\\.system\\.desktop\\.security\\.|keystore2|gatekeeperd|update_engine|vendor\\.weaver|vendor\\.authsecret|storageproxyd|trusty|vold|bert_collector)' | sed 's/^/FWS_PROP /'
for s in com.google.android.system.desktop.IGscutilExecutor/default android.system.desktop.security.gsc.IGsc/default \\
         android.hardware.weaver.IWeaver/default android.hardware.security.keymint.IKeyMintDevice/default \\
         android.hardware.gatekeeper.IGatekeeper/default; do
    echo "FWS_SERVICE $s $(service check $s | sed 's/.*: //')"
done
for p in gscutil gscd check_tpm_clear udsattestation com.google.android.system.desktop.gscutil-executor; do
    echo "FWS_PIDOF $p $(pidof $p || echo none)"
done
ls -l /dev/tpm0 /dev/tpmrm0 2>&1 | sed 's/^/FWS_DEV /'
pm list users | sed 's/^/FWS_USERS /'
logcat -d -b all | grep 'avc:' | grep 'denied' | grep -E 'gscutil|gscd|hwsec|check_tpm' | sed 's/^/FWS_AVC /'
logcat -d -b crash | grep -E 'Fatal signal|FATAL EXCEPTION|>>> ' | sed 's/^/FWS_CRASH /'
echo "FWS_VMCHECK done"
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replacements_for(source, policy, safety_dir=check.SAFETY):
    """{runtime path: OpenBook bytes} for every neutralised path, each current file being Google's reviewed
    original."""
    out = {}
    for runtime, rule in policy["neutralised"].items():
        local = source / runtime.lstrip("/")
        if not local.is_file() or local.is_symlink():
            raise ValueError(f"{runtime} is not in the base system: Google moved or removed it; review the rule")
        current = sha(local.read_bytes())
        if current == rule["sha256"]:
            raise ValueError(f"{runtime} is already OpenBook's replacement: the base is already neutralised")
        if current != rule["google_sha256"]:
            raise ValueError(f"{runtime} ({current[:12]}) is not the reviewed Google original "
                             f"({rule['google_sha256'][:12]}): Google changed it, so review it before replacing it")
        out[runtime] = check.replacement(policy, runtime, safety_dir)
    return out


def safety_check(a, old, policy):
    """check-firmware-safety.py over the candidate's rebuilt system and the base's other partitions."""
    roots = {"system": a.out / "rebuilt"}
    work = a.out / "safety-check"
    work.mkdir()
    for name in CHECKED:
        if name in old["logical_sha256"]:
            roots[name] = work / name
            check.extract(a.base / f"logical/{name}_a.img", roots[name], a.tools)
    findings, inventory = check.check_tree(policy, roots, check.apex_rc_files(roots, a.tools, work / "apex-x"))
    result = dict(schema=check.RESULT_SCHEMA, mode="candidate", passed=not findings,
                  policy_sha256=check.sha_file(check.POLICY), findings=findings, inventory=inventory)
    (a.out / "firmware-safety.json").write_text(json.dumps(result, indent=2) + "\n")
    if findings:
        # Nothing downstream may take this candidate: its manifest is set aside.
        (a.out / "manifest.json").rename(a.out / "manifest.rejected.json")
        raise ValueError("Firmware safety check failed: " + "; ".join(f"{f['kind']} {f['path']}" for f in findings))
    return result


def build(a):
    policy = check.load_policy()
    vm_check = getattr(a, "vm_check", False)
    old = json.loads(b.p.regular(a.base / "manifest.json").read_text())
    if "firmware_safety" in old:
        raise ValueError("The base candidate already carries firmware_safety")

    def transform(source):
        replacements = replacements_for(source, policy)
        record = dict(
            deployment_eligible=not vm_check, issue="ANAL-251", hardware_validated=False, scope=SCOPE,
            policy_sha256=check.sha_file(check.POLICY),
            neutralised={n: dict(google_sha256=policy["neutralised"][n]["google_sha256"], sha256=sha(d))
                         for n, d in replacements.items()},
            changed_files=sorted(replacements))
        annotations = {"firmware_safety": record}
        additions = {}
        if vm_check:
            additions = {"/system/etc/init/openbook-safety-vmcheck.rc": VM_CHECK_RC,
                         "/system/etc/openbook-safety-vmcheck.sh": VM_CHECK_SH}
            annotations["experimental_safety_vmcheck"] = dict(
                deployment_eligible=False, scope="disposable VM report of the security services to the serial console",
                added_files={n: sha(v) for n, v in additions.items()})
        return replacements, annotations, additions

    b.build_system(a, transform, "openbook-ruby-safety-candidate/1")
    result = safety_check(a, old, policy)
    print(f"Firmware safety: PASS ({len(result['inventory']['reviewed_rc'])} reviewed init scripts, "
          f"{len(result['inventory']['neutralised'])} neutralised)")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("base", "tools", "inventory", "key", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--base-sha256", required=True)
    p.add_argument("--vm-check", action="store_true", help="add the disposable serial-console report (not deployable)")
    args = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Use inst-docker.sh; regular images only")
    os.umask(0o077)
    build(args)
