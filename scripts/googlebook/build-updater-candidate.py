#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""VM validation build: the on-laptop updater engine as an init service (phase 2 groundwork).

Not deployable: the owner wants a visible, approving app (OpenBook Update), which replaces this init
service (docs/googlebook-on-device-updater.md). This build proves the engine, its SELinux domain and
the production path for added files on the real image, in the VM.

Through the same exact-inventory reassembler as every OpenBook candidate (build-input-candidate.py),
`system` gains:
  /system/bin/openbook-updater          0755, u:object_r:openbook_updater_exec:s0
  /system/etc/init/openbook-updater.rc  0644, system_file: starts it after boot (user nobody, group inet)
and these files change:
  plat_sepolicy.cil and its hash        + the openbook_updater domain (device/anybook/common/updater/sepolicy.cil),
                                          compiled with the image's exact policy inputs, neverallows included
  plat_file_contexts                    + the binary's and the state directory's labels
Every source must match its reviewed SHA-256 in device/anybook/common/updater/pins.json (a source
change needs its pin updated in the same reviewed commit). The added files are then listed by those
SHA-256s in the candidate's `openbook_updater` record, the production path for added files
(build-input-candidate.check_additions). As part of OpenBook's system
delta, rebase-google-build.py carries them onto later Google builds.

usage: build-updater-candidate.py --base STAGED_CANDIDATE --base-sha256 SHA --tools AOSP_HOST_BIN
                                  --inventory erofs-inventory --key AVB_KEY --out DIR
Container only (inst-docker.sh); regular image files.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "device/anybook/common/updater"
spec = importlib.util.spec_from_file_location("builder", HERE / "build-input-candidate.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
g = b.load("guard", "build-ota-guard-candidate.py")

BIN = "/system/bin/openbook-updater"
RC = "/system/etc/init/openbook-updater.rc"
FILE_CONTEXTS = "/system/etc/selinux/plat_file_contexts"
EXEC_CONTEXT = "u:object_r:openbook_updater_exec:s0"
# VM check variant: the VM has no adb or logcat, but init logs a oneshot service's exit status to the
# kernel log (the serial console). This runs the same binary, domain, user and group for one check;
# in the NIC-less VM a clean run ends with status 3 (network). Never in a deployable image.
VM_CHECK_RC = b"""# Disposable VM test only (openbook-updater): one check, so init logs its exit status. Never deploy.
service openbook_updater_vmcheck /system/bin/openbook-updater --dir /data/openbook-updater check
    user nobody
    group inet
    oneshot
    disabled

on property:sys.boot_completed=1
    start openbook_updater_vmcheck
"""
SCOPE = ("VM validation of the on-laptop updater engine (phase 2 groundwork, not deployable): openbook_updater "
         "runs its shell and tools, uses the network and its own state directory under /data; it writes no partition")


PINNED = {"script": "openbook-updater", "rc": "openbook-updater.rc", "cil": "sepolicy.cil",
          "file_contexts": "file_contexts"}


def sources(src_dir=SRC):
    """The updater's sources, each checked against its reviewed pin."""
    pins = json.loads((src_dir / "pins.json").read_text())
    if pins.get("schema") != "openbook-updater-pins/1" or set(pins["files"]) != set(PINNED.values()):
        raise ValueError("Unrecognized updater pin file")
    out = {}
    for key, name in PINNED.items():
        data = (src_dir / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != pins["files"][name]:
            raise ValueError(f"{name} differs from its reviewed pin in pins.json")
        out[key] = data
    out["cil"] = out["cil"].decode()
    out["file_contexts"] = out["file_contexts"].decode()
    return out


def updated_file_contexts(current, lines):
    """Append the updater's labels; later entries win in file_contexts. Refuses a second copy."""
    if "openbook_updater" in current:
        raise ValueError("plat_file_contexts already labels openbook_updater")
    for line in lines.splitlines():
        if len(line.split()) != 2 or not line.split()[1].startswith("u:object_r:openbook_updater"):
            raise ValueError(f"Unexpected updater file_contexts line: {line!r}")
    # A pure append (no stripping): rebase-google-build.py carries APPENDED files only as OLD + tail.
    return (current + ("" if current.endswith("\n") or not current else "\n") + lines.rstrip("\n") + "\n").encode()


def build(a):
    src = sources()
    vm_check = getattr(a, "vm_check", False)
    if not src["script"].startswith(b"#!/system/bin/sh\n"):
        raise ValueError("openbook-updater must start with #!/system/bin/sh")

    def transform(source):
        se = source / "system/etc/selinux"
        if b"openbook_updater" in (se / "plat_sepolicy.cil").read_bytes():
            raise ValueError("The base policy already has the openbook_updater domain")
        policy_files, record = g.test_policy(a, source, "", base=src["cil"], scope=SCOPE)
        replacements = dict(policy_files)
        replacements[FILE_CONTEXTS] = updated_file_contexts((se / "plat_file_contexts").read_text(), src["file_contexts"])
        additions = {BIN: (src["script"], 0o755, EXEC_CONTEXT), RC: src["rc"]}
        annotations = {"experimental_updater_service": dict(
            deployment_eligible=False, phase=2, hardware_validated=False,
            superseded_by="the OpenBook Update app (owner-visible approval)",
            service="openbook_updater: init, after boot, user nobody, group inet; logs to logcat and its directory",
            state_dir="/data/openbook-updater",
            added_files={BIN: hashlib.sha256(src["script"]).hexdigest(), RC: hashlib.sha256(src["rc"]).hexdigest()},
            policy=record, file_contexts=src["file_contexts"].splitlines())}
        if vm_check:
            additions["/system/etc/init/openbook-updater-vmcheck.rc"] = VM_CHECK_RC
            annotations["experimental_updater_service"]["vm_check_rc"] = hashlib.sha256(VM_CHECK_RC).hexdigest()
        return replacements, annotations, additions

    b.build_system(a, transform, "openbook-ruby-updater-candidate/1")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("base", "tools", "inventory", "key", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--base-sha256", required=True)
    p.add_argument("--vm-check", action="store_true", help="also run one check at boot so init logs its exit status")
    args = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Use inst-docker.sh; regular images only")
    os.umask(0o077)
    build(args)
