#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""OpenBook OTA on a Ruby A/B disk in QEMU: apply into slot B, reboot into it, and fall back.

Three phases on one evolving disk, each judged from the disk and the serial log:

  apply     Copies the A/B apply-test disk (build-ruby-ab-image.py from a
            build-ota-trust-candidate.py --apply-from-drive candidate) and boots it
            with the signed payload on a second drive. The one-shot driver runs the
            stock update_engine_client --update; update_engine writes slot B and the
            boot HAL runs bootsync `activate b`; the driver then reboots as the
            system updater would, which ends the run. A copy of the disk is kept
            right after the apply for the fallback phase.
  boot      Boots that disk again: slot B should start (systemd-boot's preferred,
            counted entry), complete boot, be marked successful (bootsync
            mark-good) and merge its Virtual A/B snapshot.
  fallback  Takes the post-apply copy, corrupts vbmeta_b (a bad update), and boots
            it repeatedly: each slot-B attempt fails in first-stage init and
            systemd-boot counts it down; with no tries left it boots slot A, which
            must complete boot with the update rolled back.

Regular image files only, no device, no network. Run in the openbook-installer container.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


r = load("run_probe", "run-probe.py")
mq = load("migration_qemu", "migration-qemu.py")
abq = load("ab_qemu", "ab-qemu.py")
STATIC_B = ("boot_b", "init_boot_b", "vendor_boot_b", "vbmeta_b")
# SnapshotManager's UpdateState (system/core/fs_mgr/libsnapshot/android/snapshot/snapshot.proto)
UPDATE_STATES = {0: "None", 1: "Initiated", 2: "Unverified", 3: "Merging", 4: "MergeNeedsReboot",
                 5: "MergeCompleted", 6: "MergeFailed", 7: "Cancelled"}


def nonzero(disk, offset, length):
    with open(disk, "rb") as f:
        f.seek(offset)
        left = length
        while left:
            b = f.read(min(left, 8 << 20))
            if not b:
                return False
            if b.strip(b"\0"):
                return True
            left -= len(b)
    return False


def snapshot_state(disk, offs, lens, work):
    """libsnapshot's /metadata/ota/state (field 1 of SnapshotUpdateStatus), read from the disk image."""
    part = work / "metadata.img"
    with open(disk, "rb") as src, open(part, "wb") as dst:
        src.seek(offs["metadata"])
        dst.write(src.read(lens["metadata"]))
    stat = subprocess.run(["debugfs", "-R", "stat /ota/state", str(part)], capture_output=True, text=True)
    out = subprocess.run(["debugfs", "-R", "cat /ota/state", str(part)], capture_output=True)
    part.unlink()
    if "not found" in stat.stderr + stat.stdout or "Size:" not in stat.stdout:
        return "absent"
    data = out.stdout
    # proto3 omits default fields: an empty message (or no field 1) is UpdateState::None.
    if not data or data[0] != 0x08:
        return "None"
    return UPDATE_STATES.get(data[1], f"unknown({data[1]})")


def booted_slot(serial):
    """The slot first-stage init maps: 'init: [libfs_mgr] Created logical partition system_a', or for a
    snapshot boot 'system_b-base' / 'init: Mapped COW device for system_b'. Only init's lines count:
    update_engine also names system_b when it unmaps a rolled-back snapshot on the old slot."""
    slots = set(re.findall(r"init: (?:\[libfs_mgr\] )?(?:Created logical partition|Mapped COW device for) "
                           r"system_([ab])\b", serial))
    return "".join(sorted(slots)) or None


def boot_completed(serial):
    return bool(re.search(r"processing action \(sys\.boot_completed=1\)", serial))


def launch(a, disk, out, seconds, payload=None):
    """One boot of DISK; returns when the guest reboots/powers off (-no-reboot) or SECONDS pass."""
    out.mkdir(mode=0o700, parents=True)
    vars_file = out / "vars.fd"
    vars_file.write_bytes(Path("/usr/share/edk2/x64/OVMF_VARS.4m.fd").read_bytes())
    cmd = [str(a.qemu), "-machine", "q35", "-accel", a.accel, "-cpu", "host" if a.accel == "kvm" else "max",
           "-smp", "4", "-m", "8192", "-display", "none", "-nic", "none", "-monitor", "none", "-no-reboot",
           "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd",
           "-drive", f"if=pflash,format=raw,file={vars_file}",
           "-drive", f"file={disk},format=raw,if=none,id=target",
           "-device", "nvme,drive=target,serial=RUBYABTEST,addr=0x4,bootindex=1"]
    if payload:
        cmd += ["-drive", f"file={payload},format=raw,if=none,id=payload,snapshot=on",
                "-device", "nvme,drive=payload,serial=OTAPAYLOAD,addr=0x5"]  # nvme0 or nvme1: probe order
    cmd += ["-device", "virtio-vga", "-serial", f"file:{out}/serial.log",
            "-qmp", "unix:qmp.sock,server=on,wait=off",
            "-chardev", "socket,id=chrtpm,path=tpm.sock", "-tpmdev", "emulator,id=tpm0,chardev=chrtpm",
            "-device", "tpm-crb,tpmdev=tpm0"]
    (out / "command.json").write_text(json.dumps(cmd, indent=2) + "\n")
    start = time.monotonic()
    # The software TPM holds Android's keys: carry it across boots of the same disk.
    tpm_from = a.tpm_state if a.tpm_state.exists() else None
    with r.tpm_backend(out, True, tpm_from), (out / "qemu.log").open("wb") as log:
        proc = subprocess.Popen(cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT)
        try:
            timed_out, events = mq.observe(proc, out / "qmp.sock", seconds, out)
        finally:
            mq.stop(proc)
    shutil.rmtree(a.tpm_state, ignore_errors=True)
    shutil.copytree(out / "tpm-state", a.tpm_state)
    serial = (out / "serial.log").read_text(errors="replace")
    return dict(elapsed_s=round(time.monotonic() - start, 1), timed_out=timed_out,
                qmp_events=[e.get("event") for e in events], serial=serial)


def bootsync_status(a, disk, current):
    st = subprocess.run([str(a.bootsync), "--disk", str(disk), "--current", current, "--json", "status"],
                        capture_output=True, text=True)
    return json.loads(st.stdout) if st.stdout.strip() else {}


def region_equals(disk, offset, image):
    """The partition at OFFSET starts with exactly IMAGE's bytes."""
    data = Path(image).read_bytes()
    with open(disk, "rb") as f:
        f.seek(offset)
        return f.read(len(data)) == data


def phase_apply(a, offs, lens):
    disk = a.out / "disk.img"
    if a.reevaluate:  # judge an earlier run again from its disk and logs; no boot
        run = json.loads((a.out / "run.json").read_text())
        serial = (a.out / "run" / "serial.log").read_text(errors="replace")
        before = json.loads((a.out / "before.json").read_text())
    else:
        a.out.mkdir(mode=0o700)
        subprocess.run(["cp", "--reflink=auto", str(a.image_dir / "disk.img"), str(disk)], check=True)
        before = {n: nonzero(disk, offs[n], lens[n]) for n in STATIC_B}
        (a.out / "before.json").write_text(json.dumps(before) + "\n")
        run = launch(a, disk, a.out / "run", a.seconds, payload=a.payload)
        serial = run.pop("serial")
        (a.out / "run.json").write_text(json.dumps(run, indent=2) + "\n")
        # Keep the post-apply state (disk + TPM) for the fallback phase.
        subprocess.run(["cp", "--reflink=auto", str(disk), str(a.out / "disk-after-apply.img")], check=True)
        shutil.copytree(a.tpm_state, a.out / "tpm-after-apply")
    # update_engine logs to a file in encrypted /data and the driver's console stream can drop lines,
    # so success is judged from what update_engine leaves on disk, not from console text.
    on_device = (re.search(r"OTAAPPLY payload=([0-9a-f]{64})", serial) or [None, None])[1]
    bs = bootsync_status(a, disk, "a")
    state = snapshot_state(disk, offs, lens, a.out)
    b = bs.get("slots", {}).get("b", {})
    static_match = {n: region_equals(disk, offs[f"{n}_b"], a.target_dir / f"{n}.img")
                    for n in ("boot", "init_boot", "vendor_boot", "vbmeta")} if a.target_dir else None
    checks = {
        "driver_ran": "OTAAPPLY idle" in serial,
        "payload_on_device_matches": on_device == a.payload_sha256 if a.payload_sha256 else bool(on_device),
        # FinishedSnapshotWrites() sets Unverified only after every write and verification succeeded.
        "update_engine_finished_writes": state == "Unverified",
        # update_engine calls setActiveBootSlot only once the update succeeded (end of postinstall).
        "update_engine_set_active_slot_b": bool(re.search(r"bootsync activate _b: .*loader\.conf: default "
                                                          r"openbook-a\.conf, preferred openbook-b\.conf", serial)),
        "slot_b_static_partitions_equal_target": all(static_match.values()) if static_match else
                                                  all(nonzero(disk, offs[n], lens[n]) for n in STATIC_B),
        "slot_b_static_were_blank": not any(before.values()),
        "bootsync_next_boot_b": bs.get("next_boot_slot") == "b",
        "slot_b_entry_counted": b.get("entry_state") in ("pending", "trying"),
        "slot_b_images_verified_by_bootsync": b.get("images_ok") is True,
        "slot_b_esp_files_in_sync": b.get("esp_files") == "in_sync",
        "orderly_reboot": bool(re.search(r"Received sys\.powerctl='reboot,' from pid: \d+ \(system_server\)",
                                         serial)) and not run["timed_out"],
    }
    return dict(phase="apply", run=run, payload_sha256_on_device=on_device, snapshot_state=state,
                slot_b_static_before=before, slot_b_static_equal_target=static_match, bootsync=bs,
                activate_log=re.findall(r"bootsync activate _b: [^\n]*", serial), checks=checks)


def phase_boot(a, offs, lens):
    disk = a.disk
    if a.reevaluate:  # judge an earlier run again from its disk and logs; no boot
        run = json.loads((a.out / "result.json").read_text())["run"]
        serial = (a.out / "serial.log").read_text(errors="replace")
    else:
        run = launch(a, disk, a.out, a.seconds)
        serial = run.pop("serial")
    slot = booted_slot(serial)
    bcl = abq.boot_control(disk, offs["misc"])
    bs = bootsync_status(a, disk, "b")
    state = snapshot_state(disk, offs, lens, a.out)
    checks = {
        "booted_slot_b": slot == "b",
        "boot_completed": boot_completed(serial),
        "slot_b_marked_successful": bcl["slots"][1]["successful"],
        "bootsync_b_entry_good": bs.get("slots", {}).get("b", {}).get("entry_state") == "good",
        "bootsync_next_boot_b": bs.get("next_boot_slot") == "b",
        # After the merge libsnapshot clears its update files and the state goes back to None.
        "snapshot_merged": state in ("MergeCompleted", "None") and bool(re.search(r"Merge completed", serial)),
        "no_avb_error": "Failed to verify vbmeta digest" not in serial,
    }
    return dict(phase="boot", run=run, booted_slot=slot, boot_control=bcl, bootsync=bs, snapshot_state=state,
                merge_log=sorted(set(re.findall(r"[^\n]{0,60}[Mm]erge[^\n]{0,60}", serial)))[:12],
                runtime_findings=r.runtime_findings(serial), checks=checks)


def phase_fallback(a, offs, lens):
    a.out.mkdir(mode=0o700)
    disk = a.out / "disk.img"
    subprocess.run(["cp", "--reflink=auto", str(a.disk), str(disk)], check=True)
    # A bad update: invert one block of vbmeta_b, so it no longer matches the digest bootsync exported.
    with open(disk, "r+b") as f:
        f.seek(offs["vbmeta_b"] + 256)
        blk = f.read(4096)
        f.seek(offs["vbmeta_b"] + 256)
        f.write(bytes(x ^ 0xFF for x in blk))
    attempts = []
    for i in range(1, a.attempts + 1):
        run = launch(a, disk, a.out / f"boot{i}", a.attempt_seconds if i < a.attempts else a.seconds)
        serial = run.pop("serial")
        attempts.append(dict(attempt=i, booted_slot=booted_slot(serial), boot_completed=boot_completed(serial),
                             avb_error="Failed to verify vbmeta digest" in serial, **run))
        if attempts[-1]["booted_slot"] == "a":
            break
    bs = bootsync_status(a, disk, "a")
    state = snapshot_state(disk, offs, lens, a.out)
    b_tries = [x for x in attempts if x["booted_slot"] != "a"]
    checks = {
        "slot_b_attempts_failed": bool(b_tries) and not any(x["boot_completed"] for x in b_tries),
        "systemd_boot_counted_down_to_a": len(b_tries) == 3,
        "fell_back_to_slot_a": attempts[-1]["booted_slot"] == "a",
        "slot_a_boot_completed": attempts[-1]["boot_completed"],
        "slot_b_entry_bad_or_gone": bs.get("slots", {}).get("b", {}).get("entry_state") in ("bad", "none"),
        "next_boot_a": bs.get("next_boot_slot") == "a",
        "update_rolled_back": state in ("Cancelled", "None", "absent"),
    }
    return dict(phase="fallback", attempts=attempts, bootsync=bs, snapshot_state=state, checks=checks)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=("apply", "boot", "fallback"), default="apply")
    for name in ("image-dir", "qemu", "bootsync", "out", "tpm-state"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--payload", type=Path, help="apply: payload drive (ext4 with payload.bin, payload_properties.txt)")
    p.add_argument("--payload-sha256", help="apply: expected sha256 of payload.bin")
    p.add_argument("--disk", type=Path, help="boot/fallback: the disk from the apply phase")
    p.add_argument("--target-dir", type=Path, help="the release's partition images, to compare slot B with")
    p.add_argument("--reevaluate", action="store_true", help="apply/boot: judge an earlier run again, no boot")
    p.add_argument("--seconds", type=int, default=1500)
    p.add_argument("--attempts", type=int, default=4, help="fallback: boots to allow (3 counted B tries + A)")
    p.add_argument("--attempt-seconds", type=int, default=600, help="fallback: limit for one failing B boot")
    p.add_argument("--accel", choices=("tcg", "kvm"), default="tcg",
                   help="kvm needs a host CPU with AVX-VNNI (Ruby's userspace uses it); "
                        "tcg needs the GFNI/VNNI-emulating QEMU build")
    a = p.parse_args()
    if not Path("/.dockerenv").exists():
        p.error("Run in the openbook-installer container")
    if a.phase == "apply" and not a.payload:
        p.error("apply needs --payload")
    if a.phase != "apply" and not a.disk:
        p.error(f"{a.phase} needs --disk")
    os.umask(0o077)
    built = json.loads((a.image_dir / "result.json").read_text())
    offs = {row["name"]: row["offset"] for row in built["layout"]}
    lens = {row["name"]: row["length"] for row in built["layout"]}
    result = dict(apply=phase_apply, boot=phase_boot, fallback=phase_fallback)[a.phase](a, offs, lens)
    result["schema"] = "openbook-ruby-ab-ota/1"
    result["passed"] = all(result["checks"].values())
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    summary = {k: result[k] for k in ("phase", "booted_slot",
                                      "snapshot_state", "checks", "passed") if k in result}
    if "attempts" in result:
        summary["attempts"] = [(x["attempt"], x["booted_slot"], x["boot_completed"]) for x in result["attempts"]]
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
