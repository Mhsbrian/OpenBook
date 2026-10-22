#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Rehearse the USB's laptop update/restore entries on synthetic disks in QEMU.

Container only; no networking, physical disk or owner data. Phases run as
separate bounded invocations sharing one new run directory:
  prepare  installs a synthetic configured camera25 USB onto a synthetic NVMe
  ui       boots the USB's actual update or restore entry and types like a human
  android  boots the synthetic NVMe with the run's persistent software TPM
The serial driver types the same disk choice and exact confirmation a person
would; the shipped tool has no unattended-write switch.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import time

HERE = Path(__file__).resolve().parent


def load(name, filename):
    s = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(s)
    s.loader.exec_module(value)
    return value


mq = load("migration_qemu", "migration-qemu.py")
lu = load("laptop_update", "laptop-update.py")
m, r = mq.m, mq.r
SERIAL = "LAPTOPUPDATETEST"


def fixture_pin(image, build):
    """Synthetic-fixture pin with the same fields as migration-package.py pin."""
    fd = os.open(image, os.O_RDONLY)
    try:
        gpt = m.read_gpt(fd)
        work = image.parent / f"{build}-pin-esp"
        work.mkdir()
        esp, tree = lu.extract_esp(fd, gpt["rows"][0], work, "fixture")
        entries = {mode: m.parse_initrd((tree / f"ruby/initrd-{mode}.img").read_bytes())[1] for mode in m.MODES}
        names = ["ruby/kernel", "EFI/BOOT/BOOTX64.EFI"] + [f"ruby/initrd-{mode}.img" for mode in m.MODES]
        names += [str(p.relative_to(tree)) for p in (tree / "loader/entries").glob("*.conf")]
        pin = dict(schema="openbook-ruby-migration-source/1", build=build,
                   dmi_product_prefix="ROG Zephyrus G14 GA403WR", image_bytes=gpt["used_bytes"],
                   gpt=[{k: row[k] for k in ("name", "first_lba", "last_lba", "partuuid")} for row in gpt["rows"]],
                   entries=entries, kernel_sha256=mq.sha(tree / "ruby/kernel"),
                   payload_readback={row["name"]: m.digest(fd, *m.extent(row))
                                     for row in gpt["rows"] if row["name"] in m.STATIC},
                   efi_sha256={n: mq.sha(tree / n) for n in names})
        m.check_source(fd, pin)
        return pin
    finally:
        os.close(fd)


def partition_hashes(image):
    fd = os.open(image, os.O_RDONLY)
    try:
        gpt = m.read_gpt(fd)
        return {row["name"]: m.digest(fd, *m.extent(row)) for row in gpt["rows"]}, gpt
    finally:
        os.close(fd)


def usb_fingerprint(usb, work):
    """USB partitions plus ESP files, except the seed systemd-boot refreshes at every boot."""
    hashes, gpt = partition_hashes(usb)
    fd = os.open(usb, os.O_RDONLY)
    try:
        work.mkdir()
        _, tree = lu.extract_esp(fd, gpt["rows"][0], work, "usb")
    finally:
        os.close(fd)
    del hashes["EFI"]
    return dict(partitions=hashes, gpt=gpt["rows"], esp=lu.files(tree, {"loader/random-seed"}))


def usb_record(usb, pin):
    fd = os.open(usb, os.O_RDONLY)
    try:
        gpt = m.read_gpt(fd)
        base, layout = lu.rollback_layout(pin, {row["name"]: row for row in gpt["rows"]}, m.capacity(fd))
        return lu.read_header(fd, base)
    finally:
        os.close(fd)


def bootconfig(image):
    fd = os.open(image, os.O_RDONLY)
    try:
        gpt = m.read_gpt(fd)
        work = Path(os.environ.get("TMPDIR", "/tmp")) / f"bootcfg-{os.getpid()}-{time.monotonic_ns()}"
        work.mkdir()
        _, tree = lu.extract_esp(fd, gpt["rows"][0], work, "check")
        return {mode: m.parse_initrd((tree / f"ruby/initrd-{mode}.img").read_bytes())[1] for mode in m.MODES}
    finally:
        os.close(fd)


def prepare(a):
    m.require(Path("/.dockerenv").exists(), "Run inside inst-docker.sh; never pass a physical device")
    a.out.mkdir(mode=0o700)
    w = a.out.resolve()
    source = w / "camera25-usb.img"
    m.run("cp", "--reflink=auto", a.camera25_usb, source)
    pin = fixture_pin(source, "camera25-synthetic")
    laptop = w / "laptop.img"
    src = os.open(source, os.O_RDONLY)
    dst = os.open(laptop, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.ftruncate(dst, a.laptop_bytes)
        work = w / "install-work"
        work.mkdir()
        m.migrate(src, dst, pin, work)
    finally:
        os.close(src)
        os.close(dst)
    source.unlink()
    # Fixture only: keep serial evidence on the installed default entry.
    mq.menu_default(laptop, "ruby-serial-logs.conf", w, installed_alias=True)
    usb = w / "usb.img"
    m.run("cp", "--reflink=auto", a.usb_package / "ruby-live.img", usb)
    with usb.open("r+b") as f:
        f.truncate(a.usb_bytes)
    usb_pin = json.loads((a.installer / "source.json").read_text())
    m.require(json.loads((a.installer / "laptop-update.json").read_text())["new"]["build"] == usb_pin["build"],
              "Installer record mismatch")
    hashes, gpt = partition_hashes(laptop)
    state = dict(schema="openbook-ruby-laptop-update-rehearsal/1", laptop_bytes=a.laptop_bytes,
                 usb_bytes=a.usb_bytes, usb_pin=usb_pin, original=hashes,
                 original_bootconfig=bootconfig(laptop), original_keys=mq.metadata_key_hashes(laptop, w, "original"),
                 tpm_state_from=str(a.tpm_state_from), android_qemu=a.android_qemu,
                 installer=str(a.installer), usb_package=str(a.usb_package), phases=[])
    (w / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps({"prepared": True, "partitions": len(hashes)}))


def common_args(vars_file, graphics="virtio-vga"):
    return ["-machine", "q35", "-smp", "4", "-m", "8192", "-display", "none", "-nic", "none",
            "-monitor", "none", "-no-reboot",
            "-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/edk2/x64/OVMF_CODE.4m.fd",
            "-drive", f"if=pflash,format=raw,file={vars_file}", "-device", graphics,
            "-device", "qemu-xhci,id=xhci", "-device", "usb-kbd,bus=xhci.0"]


def ui(a):
    w = a.run.resolve()
    state = json.loads((w / "state.json").read_text())
    pin = state["usb_pin"]
    phase = w / f"ui-{a.mode}-{len(state['phases'])}"
    phase.mkdir(mode=0o700)
    laptop, usb = w / "laptop.img", w / "usb.img"
    mq.menu_default(usb, f"ruby-{a.mode}-serial.conf", phase)
    before, gpt = partition_hashes(laptop)
    usb_system = usb_fingerprint(usb, phase / "usb-before")
    decoy = phase / "decoy.img"
    with decoy.open("xb") as f:
        f.write(b"DO NOT MODIFY OTHER DISKS\n")
        f.truncate(32 << 20)
    decoy_sha = mq.sha(decoy)
    vars_file = phase / "vars.fd"
    vars_file.write_bytes(Path("/usr/share/edk2/x64/OVMF_VARS.4m.fd").read_bytes())
    cmd = ["qemu-system-x86_64", "-accel", "kvm", "-cpu", "host", *common_args(vars_file),
           "-drive", f"file={usb},format=raw,if=none,id=usb",
           "-device", "usb-storage,drive=usb,bootindex=1",
           "-drive", f"file={laptop},format=raw,if=none,id=target",
           "-device", f"nvme,drive=target,serial={SERIAL},bootindex=2",
           "-drive", f"file={decoy},format=raw,if=none,id=decoy", "-device", "nvme,drive=decoy,serial=KEEPDECOY",
           "-smbios", "type=1,product=ROG Zephyrus G14 GA403WR_VM_TEST",
           "-qmp", "unix:qmp.sock,server=on,wait=off",
           "-chardev", "socket,id=serial,path=serial.sock,server=on,wait=off", "-serial", "chardev:serial"]
    (phase / "command.json").write_text(json.dumps(cmd, indent=2) + "\n")
    phrase = f"{a.mode.upper()} {SERIAL}"
    answer = {"cancel": b"\n", "wrong": b"WRONG SERIAL\n"}.get(a.answer, (phrase + "\n").encode())
    text, sent = "", set()
    start = time.monotonic()
    with (phase / "qemu.log").open("wb") as log, (phase / "serial.log").open("wb") as serial_log:
        proc = subprocess.Popen(cmd, cwd=phase, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + a.timeout
            while not (phase / "serial.sock").exists():
                m.require(proc.poll() is None and time.monotonic() < deadline, "QEMU did not start")
                time.sleep(0.1)
            with socket.socket(socket.AF_UNIX) as sock:
                sock.settimeout(0.5)
                sock.connect(str(phase / "serial.sock"))
                while proc.poll() is None and time.monotonic() < deadline:
                    try:
                        data = sock.recv(65536)
                    except socket.timeout:
                        continue
                    if not data:
                        break
                    serial_log.write(data)
                    serial_log.flush()
                    text += data.decode(errors="replace")
                    if "Laptop disk number, or Enter to cancel:" in text and "disk" not in sent:
                        sock.sendall(b"1\n")
                        sent.add("disk")
                    if f"Type exactly '{phrase}'" in text and "confirm" not in sent:
                        sock.sendall(answer)
                        sent.add("confirm")
                    if "Press Enter to power off." in text and "poweroff" not in sent:
                        sock.sendall(b"\n")
                        sent.add("poweroff")
                proc.wait(timeout=20)
        finally:
            mq.stop(proc)
    after, gpt_after = partition_hashes(laptop)
    usb_unchanged = usb_fingerprint(usb, phase / "usb-after") == usb_system
    record = usb_record(usb, pin)
    result = dict(mode=a.mode, answer=a.answer, elapsed_s=round(time.monotonic() - start, 1),
                  qemu_exit_code=proc.returncode, stopped="STOPPED:" in text, sent=sorted(sent),
                  usb_partitions_unchanged=usb_unchanged, decoy_unchanged=mq.sha(decoy) == decoy_sha,
                  gpt_unchanged=gpt_after["rows"] == gpt["rows"] and gpt_after["disk_guid"] == gpt["disk_guid"],
                  data_partitions_unchanged=all(after[n] == before[n] for n in
                                                ("misc", "boot_a", "init_boot_a", "vendor_boot_a", "metadata", "userdata")),
                  changed=sorted(n for n in after if after[n] != before[n]),
                  rollback_state=record and record["state"])
    if a.answer == "noop":  # repeated operation: must report nothing to do, before any prompt
        result["passed"] = (proc.returncode == 0 and "Nothing to do:" in text and "confirm" not in sent
                            and after == before and usb_unchanged and result["decoy_unchanged"])
    elif a.answer != "confirm":
        result["passed"] = (proc.returncode == 0 and "Cancelled. No disks written." in text
                            and after == before and usb_unchanged and result["decoy_unchanged"])
    elif a.mode == "update":
        boot = bootconfig(laptop)
        result.update(verified_message="UPDATE VERIFIED." in text,
                      new_system=all(after[n] == pin["payload_readback"][n] for n in ("super", "vbmeta_a")),
                      new_bootconfig=all(boot[k]["androidboot.vbmeta.digest"] == pin["entries"][k]["androidboot.vbmeta.digest"]
                                         and boot[k]["androidboot.boot_part_uuid"] == gpt["rows"][0]["partuuid"]
                                         for k in m.MODES))
        result["passed"] = all(result[k] for k in ("verified_message", "new_system", "new_bootconfig",
                               "usb_partitions_unchanged", "decoy_unchanged", "gpt_unchanged",
                               "data_partitions_unchanged")) and result["rollback_state"] == "updated" \
            and result["changed"] == ["EFI", "super", "vbmeta_a"] and not result["stopped"]
    else:
        result.update(verified_message="RESTORE VERIFIED." in text,
                      original_system_restored=all(after[n] == state["original"][n] for n in ("EFI", "super", "vbmeta_a")),
                      original_bootconfig=bootconfig(laptop) == state["original_bootconfig"])
        result["passed"] = all(result[k] for k in ("verified_message", "original_system_restored",
                               "original_bootconfig", "usb_partitions_unchanged", "decoy_unchanged",
                               "gpt_unchanged")) and result["rollback_state"] == "restored" and not result["stopped"]
    (phase / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    state["phases"].append(dict(phase=phase.name, passed=result["passed"]))
    (w / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    m.require(result["passed"], f"{a.mode} phase failed; inspect {phase / 'serial.log'}")


def verity_roots(image, avbtool, work):
    """Hashtree root digests in the disk's current vbmeta_a (avbtool from the AOSP host tools)."""
    fd = os.open(image, os.O_RDONLY)
    try:
        row = next(r for r in m.read_gpt(fd)["rows"] if r["name"] == "vbmeta_a")
        blob = work / "vbmeta_a.img"
        blob.write_bytes(m.read_at(fd, *m.extent(row)))
    finally:
        os.close(fd)
    info = subprocess.run([avbtool, "info_image", "--image", blob], capture_output=True, text=True, check=True).stdout
    roots, name = {}, None
    for line in info.splitlines():
        if "Partition Name:" in line:
            name = line.split(":", 1)[1].strip()
        elif "Root Digest:" in line:
            roots[name] = line.split(":", 1)[1].strip()
    m.require("system" in roots, "No system hashtree descriptor")
    return roots


def evaluate(phase, laptop, state, avbtool, label, completed, exit_code, events, elapsed):
    """Evidence from bytes and the guest's own verity/storage lines, not firmware output."""
    serial = (phase / "serial.log").read_text(errors="replace")
    roots = verity_roots(laptop, avbtool, phase)
    tables = [line for line in serial.splitlines() if "Built verity table" in line]
    keys = mq.metadata_key_hashes(laptop, phase, f"keys-{time.monotonic_ns()}")
    links = ("metadata -> /dev/block/nvme0n1p7", "super -> /dev/block/nvme0n1p8", "userdata -> /dev/block/nvme0n1p9")
    result = dict(label=label, elapsed_s=elapsed, observation_completed=completed, qemu_exit_code=exit_code,
                  qmp_events=events, boot_completed=r.boot_completed_reported(serial),
                  booted_bootconfig=bootconfig(laptop)["serial-logs"],
                  vbmeta_roots=roots,
                  verity_roots_observed={n: any(d in t for t in tables) for n, d in roots.items()},
                  target_storage_observed=all(text in serial for text in links)
                  and " /data f2fs " in serial,
                  metadata_keys_unchanged=keys == state["original_keys"], metadata_key_files=len(keys),
                  runtime_findings=r.runtime_findings(serial), hardware_tested=False, owner_data=False)
    result["system_verity_root_observed"] = result["verity_roots_observed"]["system"]
    result["passed"] = all(result[k] for k in ("observation_completed", "boot_completed",
                                               "system_verity_root_observed", "target_storage_observed",
                                               "metadata_keys_unchanged"))
    return result


def android(a):
    w = a.run.resolve()
    state = json.loads((w / "state.json").read_text())
    phase = w / f"android-{a.label}"
    phase.mkdir(mode=0o700)
    laptop = w / "laptop.img"
    previous = [p for p in state["phases"] if p["phase"].startswith("android-")]
    tpm_from = Path(w / previous[-1]["phase"] / "tpm-state") if previous else Path(state["tpm_state_from"])
    vars_file = phase / "vars.fd"
    vars_file.write_bytes(Path("/usr/share/edk2/x64/OVMF_VARS.4m.fd").read_bytes())
    cmd = [state["android_qemu"], "-accel", "tcg", "-cpu", "max", *common_args(vars_file),
           "-drive", f"file={laptop},format=raw,if=none,id=target",
           "-device", f"nvme,drive=target,serial={SERIAL},bootindex=1",
           "-serial", f"file:{phase}/serial.log", "-qmp", "unix:android-qmp.sock,server=on,wait=off",
           "-chardev", "socket,id=chrtpm,path=tpm.sock", "-tpmdev", "emulator,id=tpm0,chardev=chrtpm",
           "-device", "tpm-crb,tpmdev=tpm0",
           "-audiodev", "none,id=audio0", "-device", "intel-hda", "-device", "hda-duplex,audiodev=audio0"]
    (phase / "command.json").write_text(json.dumps(cmd, indent=2) + "\n")
    boot = bootconfig(laptop)["serial-logs"]
    start = time.monotonic()
    with r.tpm_backend(phase, True, tpm_from), (phase / "qemu.log").open("wb") as log:
        proc = subprocess.Popen(cmd, cwd=phase, stdout=log, stderr=subprocess.STDOUT)
        try:
            completed, events = mq.observe(proc, phase / "android-qmp.sock", a.seconds, phase)
        finally:
            mq.stop(proc)
    result = evaluate(phase, laptop, state, a.avbtool, a.label, completed, proc.returncode,
                      [e.get("event") for e in events], round(time.monotonic() - start, 1))
    m.require(result["booted_bootconfig"] == boot, "Boot entries changed during observation")
    (phase / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    state["phases"].append(dict(phase=phase.name, passed=result["passed"]))
    (w / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "runtime_findings"}, indent=2))
    m.require(result["passed"], f"Android phase failed; inspect {phase / 'serial.log'}")


def reevaluate(a):
    w = a.run.resolve()
    state = json.loads((w / "state.json").read_text())
    phase = w / f"android-{a.label}"
    first = json.loads((phase / "result.json").read_text())
    m.require(state["phases"][-1]["phase"] == phase.name, "Only the latest phase can be re-evaluated")
    (phase / "initial-result.json").write_text(json.dumps(first, indent=2) + "\n")
    result = evaluate(phase, w / "laptop.img", state, a.avbtool, a.label, first["observation_completed"],
                      first["qemu_exit_code"], first["qmp_events"], first["elapsed_s"])
    result["reevaluated_same_capture"] = True
    (phase / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    state["phases"][-1]["passed"] = result["passed"]
    (w / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "runtime_findings"}, indent=2))
    m.require(result["passed"], "Re-evaluated Android phase failed")


def swap_usb(a):
    """Attach a newer USB and make the laptop's current system the restore baseline."""
    w = a.run.resolve()
    state = json.loads((w / "state.json").read_text())
    laptop, usb = w / "laptop.img", w / "usb.img"
    m.require(state["phases"] and state["phases"][-1]["passed"], "Previous phase must pass first")
    usb.unlink()
    m.run("cp", "--reflink=auto", a.usb_package / "ruby-live.img", usb)
    with usb.open("r+b") as f:
        f.truncate(state["usb_bytes"])
    state["usb_pin"] = json.loads((a.installer / "source.json").read_text())
    hashes, _ = partition_hashes(laptop)
    state["original"], state["original_bootconfig"] = hashes, bootconfig(laptop)
    state["installer"], state["usb_package"] = str(a.installer), str(a.usb_package)
    state["phases"].append(dict(phase=f"swap-usb-{len(state['phases'])}", passed=True,
                                usb=str(a.usb_package), new_restore_baseline=True))
    (w / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps({"swapped": str(a.usb_package), "build": state["usb_pin"]["build"]}))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="phase", required=True)
    q = sub.add_parser("prepare")
    for name in ("camera25-usb", "tpm-state-from", "usb-package", "installer", "out"):
        q.add_argument("--" + name, type=Path, required=True)
    q.add_argument("--android-qemu", required=True)
    q.add_argument("--laptop-bytes", type=int, default=64 << 30)
    q.add_argument("--usb-bytes", type=int, default=24 << 30)
    q = sub.add_parser("ui")
    q.add_argument("--run", type=Path, required=True)
    q.add_argument("--mode", choices=("update", "restore"), required=True)
    q.add_argument("--answer", choices=("confirm", "wrong", "cancel", "noop"), default="confirm")
    q.add_argument("--timeout", type=int, default=540)
    q = sub.add_parser("android")
    q.add_argument("--run", type=Path, required=True)
    q.add_argument("--label", required=True)
    q.add_argument("--seconds", type=int, default=480)
    avb = Path(os.environ.get("OPENBOOK_HOME", str(Path.home() / "anybook"))) / "aosp/src/out/host/linux-x86/bin/avbtool"
    q.add_argument("--avbtool", default=str(avb))
    q = sub.add_parser("swap-usb", help="Attach a newer USB package; current laptop system becomes the restore baseline")
    q.add_argument("--run", type=Path, required=True)
    q.add_argument("--usb-package", type=Path, required=True)
    q.add_argument("--installer", type=Path, required=True)
    q = sub.add_parser("reevaluate", help="Recompute the latest Android phase from its saved capture")
    q.add_argument("--run", type=Path, required=True)
    q.add_argument("--label", required=True)
    q.add_argument("--avbtool", default=str(avb))
    a = p.parse_args()
    m.require(Path("/.dockerenv").exists(), "Run inside inst-docker.sh; never pass a physical device")
    os.umask(0o077)
    {"prepare": prepare, "ui": ui, "android": android, "reevaluate": reevaluate, "swap-usb": swap_usb}[a.phase](a)


if __name__ == "__main__":
    main()
