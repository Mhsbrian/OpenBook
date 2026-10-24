#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Add ANAL-238's dGPU diagnostics to a Ruby candidate's vendor partition.

Three vendor files change, each from its reviewed original (BASE_PINS) to this repository's version:
  /bin/openbook-pc-setup              device/anybook/common/pc/bin/openbook-pc-setup.sh: logs to logd too; the
                                      dgpu-report and dgpu-ctl subcommands
  /etc/init/hw/init.openbook.rc       device/anybook/common/pc/init.openbook.rc: the dgpu-report service (at boot
                                      completion and on debug.openbook.dgpu_report) and dgpu-ctl (debug.openbook.dgpu_pm)
  /etc/selinux/vendor_sepolicy.cil    the base file plus r_dir_file(openbook_pc_setup, sysfs_suspend_stats), written
                                      as the base's own expansion of the same rule for hal_power_stats_default
Every other vendor inode, xattr and file keeps its bytes (build-input-candidate.rebuild_erofs proves it), and
the other logical images are used as they are. vbmeta, super and the boot entries are assembled by the same
path as every OpenBook candidate (build-input-candidate.assemble).

Fail-closed checks:
  - each base file is the reviewed original;
  - the base's precompiled policy does not match the platform policy hash, so init compiles the split policy at
    boot and the vendor rule takes effect (a matching hash would load the stale precompiled policy instead);
  - the new policy compiles with secilc, neverallows included, against the candidate's own platform, system_ext
    and product policies; the base policy compiles too, and only the new one grants openbook_pc_setup the
    suspend_stats reads (sepolicy-analyze).
--vm-check also adds a disposable system service reporting the diagnostics to the serial console (DGR_* lines);
such a candidate is marked not deployable.
--check-policy-only runs the policy checks on the base and writes OUT/policy-check.json; no candidate.

usage: build-dgpu-diag-candidate.py --base STAGED_CANDIDATE --base-sha256 SHA --tools AOSP_HOST_BIN
                                    --inventory erofs-inventory --key AVB_KEY --out DIR [--vm-check | --check-policy-only]
Container only (inst-docker.sh); regular image files.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


b = load("builder", "build-input-candidate.py")
guard = load("guard", "build-ota-guard-candidate.py")
p = b.p

SETUP = "/bin/openbook-pc-setup"
RC = "/etc/init/hw/init.openbook.rc"
CIL = "/etc/selinux/vendor_sepolicy.cil"
# The vendor of RB-20261021-01 .. RB-20261023-03 (unchanged since RB01): the files this change replaces.
BASE_PINS = {
    SETUP: "0e70d4a55c27388c0fb22de69151895633db17d6db49fd90404b73a2c890b31d",
    RC: "9836f8d3d3218663730f348eccf86436a905f7b1ad9da6a2b70288b0a19fe73f",
    CIL: "321e4491be38226c102ecb554517887753f8f37770237abdb129197e84035673",
}
SOURCES = {
    SETUP: REPO / "device/anybook/common/pc/bin/openbook-pc-setup.sh",
    RC: REPO / "device/anybook/common/pc/init.openbook.rc",
}
RULE_TEMPLATE_DOMAIN = "hal_power_stats_default"
DOMAIN = "openbook_pc_setup"
STATS_TYPE = "sysfs_suspend_stats"
SCOPE = ("dGPU diagnostics (ANAL-238): openbook-pc-setup logs to logd; a root-domain dgpu-report at boot completion "
         "and on debug.openbook.dgpu_report; a volatile dgpu-ctl on|auto hold from debug.openbook.dgpu_pm; "
         "read access to /sys/power/suspend_stats for openbook_pc_setup. No firmware setting (dgpu_disable, "
         "gpu_mux_mode) is written")
# sepolicy-analyze probes: (rule, allowed in the base?, allowed in the candidate?)
PROBES = [
    (f"{DOMAIN} {STATS_TYPE}:dir search", False, True),
    (f"{DOMAIN} {STATS_TYPE}:file read", False, True),
    (f"{DOMAIN} {STATS_TYPE}:lnk_file read", False, True),
    (f"{RULE_TEMPLATE_DOMAIN} {STATS_TYPE}:file read", True, True),
    (f"{DOMAIN} sysfs:file write", True, True),
    (f"{DOMAIN} tmpfs:chr_file write", False, False),
    ("vendor_init debug_prop:file read", True, True),
    ("vendor_init boot_status_prop:file read", True, True),
    ("shell debug_prop:property_service set", True, True),
]

VM_CHECK_RC = b"""# Disposable VM test only (ANAL-238): report the vendor dGPU diagnostics to the serial console. Never deploy.
service openbook_dgpu_vmcheck /system/bin/sh /system/etc/openbook-dgpu-vmcheck.sh
    user shell
    group shell log readproc
    seclabel u:r:shell:s0
    console ttyS0
    disabled
    oneshot

# The boot-time report, read from logcat 10 s after boot completion, before a busy boot rotates it out.
service openbook_dgpu_logwatch /system/bin/sh /system/etc/openbook-dgpu-vmcheck.sh boot
    user shell
    group shell log
    seclabel u:r:shell:s0
    disabled
    oneshot

on property:sys.boot_completed=1
    start openbook_dgpu_logwatch

# After the base image's own console service (openbook.ruby.probe) has ended: its exit takes the shared
# console from services started before it.
on property:sys.boot_completed=1 && property:init.svc.openbook.ruby.probe=stopped
    start openbook_dgpu_vmcheck
"""
VM_CHECK_SH = b"""#!/system/bin/sh
# Disposable VM test only (ANAL-238): the vendor dgpu-report and dgpu-ctl services, as DGR_* lines. Never deploy.
BOOT=/data/local/tmp/openbook-dgpu-boot.txt
if [ "$1" = boot ]; then
    sleep 10
    logcat -d -v raw -s openbook-pc-setup:I > $BOOT
    exit 0
fi
sleep 60
echo "DGR_VMCHECK begin"
echo "DGR_BOOT $(getprop sys.boot_completed)"
lines() { logcat -d -v raw -s openbook-pc-setup:I | sed "s/^/DGR_LOG $1 /"; }
sed "s/^/DGR_LOG boot /" $BOOT
setprop debug.openbook.dgpu_report vm-1
sleep 15
lines report
setprop debug.openbook.dgpu_pm on
sleep 25
lines ctl-on
setprop debug.openbook.dgpu_pm auto
sleep 25
lines ctl-auto
for s in dgpu-pm dgpu-report dgpu-ctl; do echo "DGR_SVC $s $(getprop init.svc.vendor.openbook.$s)"; done
logcat -d -b all | grep 'avc:' | grep 'denied' | grep -E 'openbook_pc_setup|openbook-pc-set' | sed 's/^/DGR_AVC /'
logcat -d -b crash | grep -E 'Fatal signal|FATAL EXCEPTION|Process: |>>> ' | sed 's/^/DGR_CRASH /'
rm -f $BOOT
echo "DGR_VMCHECK done"
"""


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rule_lines(cil_text):
    """The base's own expansion of r_dir_file(hal_power_stats_default, sysfs_suspend_stats), re-targeted to
    openbook_pc_setup: one (allow ...) statement each for dir, file and lnk_file."""
    prefix = f"(allow {RULE_TEMPLATE_DOMAIN} {STATS_TYPE}_"
    found = [l for l in cil_text.splitlines() if l.startswith(prefix)]
    classes = sorted(l.split(" (", 1)[1].split(" ", 1)[0] for l in found)
    if classes != ["dir", "file", "lnk_file"]:
        raise ValueError(f"Expected the template rule for dir, file and lnk_file; found {classes}")
    if any(l.startswith(f"(allow {DOMAIN} {STATS_TYPE}_") for l in cil_text.splitlines()):
        raise ValueError(f"The base already grants {DOMAIN} {STATS_TYPE}")
    return [l.replace(f"(allow {RULE_TEMPLATE_DOMAIN} ", f"(allow {DOMAIN} ", 1) for l in found]


def new_cil(base):
    """The base vendor_sepolicy.cil with the three statements appended (CIL is order-independent)."""
    text = base.decode()
    if not text.endswith("\n"):
        raise ValueError("vendor_sepolicy.cil does not end with a newline")
    added = rule_lines(text)
    return (text + "".join(l + "\n" for l in added)).encode(), added


def replacements_for(vendor_root):
    """{image path: new bytes} for the three vendor files, each checked against its reviewed original."""
    out = {}
    for path, pin in BASE_PINS.items():
        local = vendor_root / path.lstrip("/")
        if not local.is_file() or local.is_symlink():
            raise ValueError(f"{path} is not a regular file in the base vendor")
        current = sha(local.read_bytes())
        if current != pin:
            raise ValueError(f"{path} ({current[:12]}) is not the reviewed original ({pin[:12]}): review the base first")
    for path, src in SOURCES.items():
        out[path] = src.read_bytes()
    out[CIL], _ = new_cil((vendor_root / CIL.lstrip("/")).read_bytes())
    for path, data in out.items():
        if sha(data) == BASE_PINS[path]:
            raise ValueError(f"{path}: the new bytes equal the base's")
    return out


def extract(a, image, out):
    p.h.run(a.tools / "fsck.erofs", f"--extract={out}", image)
    return out


def analyze(a, policy, rule):
    """True when the compiled policy allows rule ("SOURCE TARGET:CLASS PERM")."""
    r = subprocess.run([str(a.tools / "sepolicy-analyze"), str(policy), "neverallow", "-n", f"neverallow {rule};"],
                       capture_output=True, text=True)
    text = r.stdout + r.stderr
    if r.returncode == 0 and not text.strip():
        return False
    if "neverallow violated by allow" in text:
        return True
    raise ValueError(f"sepolicy-analyze failed on {rule} ({r.returncode}): {text.strip()}")


def policy_check(a, w, old, vendor_root, cil_bytes):
    """Compile the base's and the candidate's split policy as init would at boot; probe the difference."""
    roots = {}
    for name in ("system", "system_ext", "product"):
        image = p.regular(a.base / f"logical/{name}_a.img")
        if p.h.audit.sha(image) != old["logical_sha256"][name]:
            raise ValueError(f"Policy input image changed: {name}")
        roots[name] = extract(a, image, w / f"policy-{name}")
    se = roots["system"] / "system/etc/selinux"
    plat_hash = (se / "plat_sepolicy_and_mapping.sha256").read_text().strip()
    pre = (vendor_root / "etc/selinux/precompiled_sepolicy.plat_sepolicy_and_mapping.sha256").read_text().strip()
    if pre == plat_hash:
        raise ValueError("The vendor's precompiled policy matches the platform hash: init would load it and "
                         "ignore the new vendor rule. Rebuild the precompiled policy first")
    compiled, probes = {}, {}
    for label, cil in (("base", (vendor_root / CIL.lstrip("/")).read_bytes()), ("candidate", cil_bytes)):
        vdir = w / f"policy-vendor-{label}"
        (vdir / "etc/selinux").mkdir(parents=True)
        for name in ("plat_pub_versioned.cil", "plat_sepolicy_vers.txt", "genfs_labels_version.txt"):
            shutil.copyfile(vendor_root / "etc/selinux" / name, vdir / "etc/selinux" / name)
        (vdir / "etc/selinux/vendor_sepolicy.cil").write_bytes(cil)
        _version, inputs = guard.policy_inputs(se / "plat_sepolicy.cil", se, vdir,
                                               {n: roots[n] for n in ("system_ext", "product")})
        out = w / f"policy-{label}.bin"
        p.h.run(a.tools / "secilc", "-m", "-M", "true", "-G", "-c", "33", "-o", out, "-f", "/dev/null", *inputs)
        compiled[label] = p.h.audit.sha(out)
        probes[label] = {rule: analyze(a, out, rule) for rule, *_ in PROBES}
    for rule, in_base, in_candidate in PROBES:
        if probes["base"][rule] != in_base or probes["candidate"][rule] != in_candidate:
            raise ValueError(f"Policy probe {rule!r}: base {probes['base'][rule]}, candidate "
                             f"{probes['candidate'][rule]}; expected {in_base}, {in_candidate}")
    return dict(neverallow_checked=True, runtime_recompilation_required=True,
                platform_policy_hash=plat_hash, vendor_precompiled_hash=pre,
                base_policy_sha256=compiled["base"], candidate_policy_sha256=compiled["candidate"],
                probes={rule: dict(base=probes["base"][rule], candidate=probes["candidate"][rule])
                        for rule, *_ in PROBES})


def footer(a, image, partition_size, name):
    """AVB hash tree and footer, salt from the content (as build-input-candidate.hashtree_footer does for system)."""
    p.h.run(a.tools / "avbtool", "add_hashtree_footer", "--image", image, "--partition_name", name,
            "--partition_size", partition_size, "--salt", p.h.audit.sha(image), "--do_not_generate_fec",
            "--hash_algorithm", "sha256")


def uniform_mtime(rows):
    """The one mtime every inode of a partition carries (mkfs.erofs -T gives all inodes the same time)."""
    times = {" ".join(r.split(" ")[7:9]) for r in rows if r.startswith("I ")}
    if len(times) != 1:
        raise ValueError(f"Partition inodes carry {len(times)} different mtimes; expected one")
    seconds, nanos = next(iter(times)).split(" ")
    if nanos != "0":
        raise ValueError("Partition mtime has a sub-second part")
    return int(seconds)


def rebuild(a, w, old, name, replacements, additions):
    """One logical image rebuilt with exactly these replacements and additions; returns (image, details)."""
    image = p.regular(a.base / f"logical/{name}_a.img")
    if p.h.audit.sha(image) != old["logical_sha256"][name]:
        raise ValueError(f"Baseline logical image differs from manifest: {name}")
    sub = w / name
    sub.mkdir()
    before = b.inventory(a.inventory, image)
    (sub / "before.metadata").write_text("\n".join(before) + "\n")
    source = extract(a, image, sub / "source")
    original = b.contents(source)
    additions = {n: b.added_file(v) for n, v in additions.items()}
    expected_metadata = b.addition_metadata(b.replacement_metadata(before, replacements), additions)
    for path, data in replacements.items():
        if path not in original or original[path][0] != "file":
            raise ValueError(f"Replacement is not an existing regular file: {name}{path}")
        p.regular(source / path.lstrip("/")).write_bytes(data)
    for path in sorted(additions):
        local = source / path.lstrip("/")
        if additions[path] is None:
            local.mkdir()
        else:
            local.write_bytes(additions[path][0])
    expected = dict(original)
    files = {**replacements, **{n: v[0] for n, v in additions.items() if v is not None}}
    expected.update({path: ["file", sha(data)] for path, data in files.items()})
    rebuilt, after = b.rebuild_erofs(a, sub, source, expected_metadata, expected, uniform_mtime(before))
    out = w / f"{name}.img"
    rebuilt.rename(out)
    footer(a, out, image.stat().st_size, name)
    return out, dict(metadata_rows=len(before), all_inode_xattrs_identical=before == after,
                     changed_files=sorted(replacements), added_paths=sorted(additions),
                     file_and_symlink_count=len(original))


def build(a):
    vm_check = getattr(a, "vm_check", False)
    base = p.regular(a.base / "ruby-live.img")
    old = json.loads(p.regular(a.base / "manifest.json").read_text())
    if old["image_sha256"] != a.base_sha256 or p.h.audit.sha(base) != a.base_sha256:
        raise ValueError("Base image differs from its reviewed pin")
    if "dgpu_diagnostics" in old:
        raise ValueError("The base candidate already carries dgpu_diagnostics")
    w = a.out
    w.mkdir(mode=0o700, parents=True, exist_ok=False)
    vendor_root = extract(a, p.regular(a.base / "logical/vendor_a.img"), w / "base-vendor")
    replacements = replacements_for(vendor_root)
    policy = policy_check(a, w, old, vendor_root, replacements[CIL])
    _, added = new_cil((vendor_root / CIL.lstrip("/")).read_bytes())
    record = dict(
        deployment_eligible=not vm_check, issue="ANAL-238", hardware_validated=False, scope=SCOPE,
        partition="vendor",
        files={path: dict(base_sha256=BASE_PINS[path], sha256=sha(data)) for path, data in replacements.items()},
        added_policy=added, policy=policy)
    if getattr(a, "check_policy_only", False):
        (w / "policy-check.json").write_text(json.dumps(dict(
            schema="openbook-ruby-dgpu-policy-check/1", base_sha256=a.base_sha256, passed=True, **record),
            indent=2) + "\n")
        print("Policy check passed; no candidate built.")
        return
    annotations = {"dgpu_diagnostics": record}
    images = {n: a.base / f"logical/{n}_a.img" for n in old["logical_sha256"]}
    vendor, vendor_details = rebuild(a, w, old, "vendor", replacements, {})
    images["vendor"] = vendor
    details = {"vendor": vendor_details}
    if vm_check:
        additions = {"/system/etc/init/openbook-dgpu-vmcheck.rc": VM_CHECK_RC,
                     "/system/etc/openbook-dgpu-vmcheck.sh": VM_CHECK_SH}
        annotations["experimental_dgpu_vmcheck"] = dict(
            deployment_eligible=False, scope="disposable VM report of the dGPU diagnostics to the serial console",
            added_files={n: sha(v) for n, v in additions.items()})
        b.check_additions({n: b.added_file(v) for n, v in additions.items()}, annotations)
        system, system_details = rebuild(a, w, old, "system", {}, additions)
        images["system"] = system
        details["system"] = system_details
    if set(annotations) & set(old):
        raise ValueError("Annotations would override baseline fields")
    b.assemble(a, w, base, old, a.base_sha256, images, annotations, "openbook-ruby-dgpu-diag-candidate/1",
               dict(partitions=details, **annotations))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("base", "tools", "inventory", "key", "out"):
        ap.add_argument("--" + name, type=Path, required=True)
    ap.add_argument("--base-sha256", required=True)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--vm-check", action="store_true", help="add the disposable serial-console report (not deployable)")
    mode.add_argument("--check-policy-only", action="store_true", help="policy checks only; no candidate")
    args = ap.parse_args()
    if not Path("/.dockerenv").exists():
        ap.error("Use inst-docker.sh; regular images only")
    os.umask(0o077)
    build(args)
