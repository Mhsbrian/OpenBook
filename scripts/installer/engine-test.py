#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host tests of openbook-install, the install engine (ANAL-191; device/anybook/common/installer/engine): the
engine runs against a fixture root (--root) whose sysfs describes a USB stick and an NVMe disk, and whose
/dev/block nodes are image files. The stick is a copy of a live image built by scripts/installer-image.sh (with
the install data of MANIFEST.json); targets are sparse files. Nothing here touches a real disk.

Cases:
  disks        the inventory: the stick is the boot disk and refused; a blank NVMe may take a whole-disk install
  plan         the dry run: every operation listed; the target's bytes are unchanged (sha256 before and after)
  refuse-*     apply without OPENBOOK_INSTALL_ERASE, with the wrong disk, on the stick, on a mounted disk, on a disk
               that is too small, after the disk changed since the plan, and from a stick with a corrupted super
               (S10): refused, and the target is unchanged
  whole        a whole-disk install; then the GPT (sgdisk -v), the ESP (fsck.fat, mtools: every file against the
               plan), super's metadata (lpdump: the 7 logical partitions at the expected offsets) and every copied
               partition (sha256) are checked from outside the engine
  alongside    a Windows-like disk (ESP with EFI/Microsoft/Boot/bootmgfw.efi and EFI/BOOT/BOOTX64.EFI, MSR, an NTFS
               partition, 70 GiB free): our partitions go into the free space; the existing partitions' bytes are
               unchanged except the ESP, which gains only EFI/OpenBook/systemd-bootx64.efi (S7)
Writes RUN/results.json and RUN/SUMMARY.md, and keeps each command's stdout/stderr in RUN/<case>/.

usage: engine-test.py --engine BIN --image LIVE.img --run DIR
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

GiB = 1024 ** 3
MiB = 1024 ** 2
HOST_TOOLS = os.path.expanduser(os.environ.get("OPENBOOK_HOME", os.environ.get("ANYBOOK_HOME", "~/anybook"))) + \
    "/aosp/src/out/host/linux-x86/bin"
results = {"cases": {}}


def sh(*cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)


def sha_file(path, length=None, offset=0):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        f.seek(offset)
        left = length if length is not None else os.path.getsize(path) - offset
        while left > 0:
            b = f.read(min(left, 16 * MiB))
            if not b:
                break
            h.update(b)
            left -= len(b)
    return h.hexdigest()


def check(case, what, ok, detail=""):
    results["cases"].setdefault(case, []).append({"check": what, "ok": bool(ok), "detail": str(detail)[:300]})
    print(f"[{'PASS' if ok else 'FAIL'}] {case}: {what} {('- ' + str(detail)[:200]) if detail and not ok else ''}")


def write_sys(root, rel, value):
    p = os.path.join(root, rel.lstrip("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(f"{value}\n")


def make_root(run, name, stick_img, target_img, target_serial="internal0", mounted_target=False):
    """A fixture root: sysfs for a USB stick (sda) and an NVMe disk (nvme0n1); /dev/block links to the images."""
    root = f"{run}/roots/{name}"
    shutil.rmtree(root, ignore_errors=True)
    usb = "sys/devices/pci0000:00/0000:00:14.0/usb3/3-1"
    scsi = f"{usb}/3-1:1.0/host0/target0:0:0/0:0:0:0"
    sda = f"{scsi}/block/sda"
    write_sys(root, f"{usb}/idVendor", "46f4")
    write_sys(root, f"{usb}/serial", "1-0000:00:14.0-1")
    write_sys(root, f"{scsi}/vendor", "QEMU    ")
    write_sys(root, f"{scsi}/model", "QEMU HARDDISK   ")
    write_sys(root, f"{sda}/size", os.path.getsize(stick_img) // 512)
    write_sys(root, f"{sda}/removable", 1)
    write_sys(root, f"{sda}/ro", 0)
    write_sys(root, f"{sda}/queue/logical_block_size", 512)
    write_sys(root, f"{sda}/queue/rotational", 0)
    os.makedirs(f"{root}/{sda}/holders", exist_ok=True)
    os.symlink("../../../0:0:0:0", f"{root}/{sda}/device")
    open(f"{root}/{sda}/holders/dm-0", "w").close()  # Android's super and /data sit on the stick
    nvme = "sys/devices/pci0000:00/0000:00:04.0/nvme/nvme0"
    n0 = f"{nvme}/nvme0n1"
    write_sys(root, f"{nvme}/model", "QEMU NVMe Ctrl                          ")
    write_sys(root, f"{nvme}/serial", f"{target_serial}          ")
    write_sys(root, f"{n0}/size", os.path.getsize(target_img) // 512)
    write_sys(root, f"{n0}/removable", 0)
    write_sys(root, f"{n0}/ro", 0)
    write_sys(root, f"{n0}/wwid", "nvme.1b36-696e7465726e616c30-51454d55204e564d65204374726c-00000001")
    write_sys(root, f"{n0}/queue/logical_block_size", 512)
    write_sys(root, f"{n0}/queue/rotational", 0)
    os.makedirs(f"{root}/{n0}/holders", exist_ok=True)
    os.symlink("../../nvme0", f"{root}/{n0}/device")
    if mounted_target:
        os.makedirs(f"{root}/{n0}/nvme0n1p3/holders", exist_ok=True)
        open(f"{root}/{n0}/nvme0n1p3/holders/dm-3", "w").close()
    os.makedirs(f"{root}/sys/block", exist_ok=True)
    os.symlink(f"../../{sda}", f"{root}/sys/block/sda")
    os.symlink(f"../../{n0}", f"{root}/sys/block/nvme0n1")
    os.makedirs(f"{root}/dev/block", exist_ok=True)
    os.symlink(os.path.abspath(stick_img), f"{root}/dev/block/sda")
    os.symlink(os.path.abspath(target_img), f"{root}/dev/block/nvme0n1")
    write_sys(root, "proc/self/mounts", "/dev/block/dm-5 /data f2fs rw 0 0\n/dev/block/sda7 /metadata ext4 rw 0 0")
    write_sys(root, "proc/swaps", "Filename Type Size Used Priority")
    return root


class Engine:
    def __init__(self, binary, root, uuid, out):
        self.binary, self.root, self.uuid, self.out = binary, root, uuid, out
        os.makedirs(out, exist_ok=True)
        self.n = 0

    def run(self, *args, env=None):
        self.n += 1
        e = dict(os.environ)
        e.pop("OPENBOOK_INSTALL_ERASE", None)
        e.update(env or {})
        r = sh(self.binary, "--root", self.root, "--boot-part-uuid", self.uuid, *args, env=e)
        tag = f"{self.n:02d}-{args[0]}"
        open(f"{self.out}/{tag}.stdout.json", "w").write(r.stdout)
        open(f"{self.out}/{tag}.stderr.log", "w").write(r.stderr)
        try:
            j = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
        except ValueError:
            j = {"unparsable": r.stdout[-300:]}
        return r.returncode, j, r


def gpt_list(img):
    p = sh("sgdisk", "-p", img).stdout
    return {m.group(6): (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(5)) for m in
            re.finditer(r"^\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+ \S+)\s+(\S+)\s+(\S+)$", p, re.M)}


def esp_get(img, off, path, dest):
    return sh("mcopy", "-n", "-o", "-i", f"{img}@@{off}", f"::{path}", dest).returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    run = os.path.abspath(a.run)
    os.makedirs(run, exist_ok=True)
    meta = json.load(open(a.image + ".json"))
    uuid = meta["esp_partuuid"]
    stick = f"{run}/stick.img"
    shutil.copyfile(a.image, stick) if not os.path.exists(stick) else None
    stick_sha_parts = {p["name"]: sha_file(stick, p["sectors"] * 512, p["start"] * 512) for p in meta["partitions"]
                       if p["name"] != "EFI"}
    esp = next(p for p in meta["partitions"] if p["name"] == "EFI")
    sh("mcopy", "-n", "-o", "-i", f"{stick}@@{esp['start'] * 512}", "::/openbook/MANIFEST.json", f"{run}/MANIFEST.json")
    man = json.load(open(f"{run}/MANIFEST.json"))
    inst = man["install"]

    def blank(name, gib):
        p = f"{run}/{name}.img"
        if os.path.exists(p):
            os.remove(p)
        with open(p, "wb") as f:
            f.truncate(gib * GiB)
        return p

    # ---------------------------------------------------------------- disks, plan, refusals
    t = blank("target", 64)
    E = Engine(a.engine, make_root(run, "main", stick, t), uuid, f"{run}/plan")
    rc, j, _ = E.run("disks")
    disks = {d["name"]: d for d in j.get("disks", [])}
    check("disks", "two disks found, the stick by its USB by-id", set(disks) == {"sda", "nvme0n1"} and
          disks["sda"]["by_id"].startswith("usb-QEMU_QEMU_HARDDISK_1-0000:00:14.0-1-0:0"), list(disks))
    check("disks", "the stick is the boot disk and not a target (S1)", disks.get("sda", {}).get("boot_disk") and
          disks["sda"]["layouts"]["whole"]["why"] == "boot_disk")
    nv = disks.get("nvme0n1", {})
    check("disks", "the NVMe disk: by-id nvme-QEMU_NVMe_Ctrl_internal0", nv.get("by_id") == "nvme-QEMU_NVMe_Ctrl_internal0",
          nv.get("by_id"))
    check("disks", "blank NVMe: whole ok, alongside refused (no GPT)", nv.get("layouts", {}).get("whole", {}).get("ok")
          and nv["layouts"]["alongside"]["why"] == "no_gpt", nv.get("layouts"))
    check("disks", "install source found on the stick", j.get("source", {}).get("ok"), j.get("source"))
    rc, j, _ = E.run("hwinfo")
    check("disks", "hwinfo answers (fixture: no hardware)", j.get("ok") and j["hw"]["schema"] == "openbook-hwinfo/1")

    before = sha_file(t)
    target = "nvme-QEMU_NVMe_Ctrl_internal0"
    plan = f"{run}/plan/plan-whole.json"
    rc, j, _ = E.run("plan", "--target", f"/dev/disk/by-id/{target}", "--layout", "whole", "--locale", "en-US",
                     "--keyboard", "us", "--out", plan)
    check("plan", "plan succeeds", rc == 0 and j.get("plan_sha256"), j.get("error"))
    ops = [o["op"] for o in j.get("operations", [])]
    check("plan", "operations listed in order (check, recheck, wipe, copies, super, format, files, table, verify, "
                  "activate, nvram, report)", ops[:3] == ["check_source", "recheck", "wipe_table"] and
          ops[-3:] == ["activate", "nvram", "report"] and "super" in ops and "write_table" in ops, ops)
    names = [p["name"] for p in j.get("partitions", [])]
    check("plan", "whole-disk layout (docs/installer.md 3.2)", names == ["EFI", "misc", "boot_a", "boot_b", "init_boot_a",
          "init_boot_b", "vendor_boot_a", "vendor_boot_b", "vbmeta_a", "vbmeta_b", "metadata", "super", "userdata"], names)
    check("plan", "confirm text is the disk's model", j.get("confirm_text") == "QEMU NVMe Ctrl", j.get("confirm_text"))
    check("plan", "the target was only read (sha256 unchanged)", sha_file(t) == before)
    plan_j = j

    # refusals
    rc, j, _ = E.run("apply", "--plan", plan, "--confirm-disk", f"/dev/disk/by-id/{target}")
    check("refuse-no-env", "without OPENBOOK_INSTALL_ERASE: refused", rc != 0 and j.get("code") == "confirm_mismatch",
          j.get("code"))
    rc, j, _ = E.run("apply", "--plan", plan, "--confirm-disk", "/dev/disk/by-id/nvme-OTHER",
                     env={"OPENBOOK_INSTALL_ERASE": "/dev/disk/by-id/nvme-OTHER"})
    check("refuse-wrong-disk", "a different disk named: refused", rc != 0 and j.get("code") == "confirm_mismatch")
    check("refuse-wrong-disk", "target unchanged", sha_file(t) == before)
    rc, j, _ = E.run("plan", "--target", disks["sda"]["by_id"], "--layout", "whole")
    check("refuse-boot-disk", "planning onto the stick: refused (boot_disk)", rc != 0 and j.get("error") == "boot_disk",
          j)
    Em = Engine(a.engine, make_root(run, "mounted", stick, t, mounted_target=True), uuid, f"{run}/refuse-mounted")
    rc, j, _ = Em.run("plan", "--target", target, "--layout", "whole")
    check("refuse-mounted", "a disk with a partition in use: refused (mounted)", rc != 0 and j.get("error") == "mounted", j)
    small = blank("small", 32)
    Es = Engine(a.engine, make_root(run, "small", stick, small, target_serial="small0"), uuid, f"{run}/refuse-small")
    rc, j, _ = Es.run("plan", "--target", "nvme-QEMU_NVMe_Ctrl_small0", "--layout", "whole")
    check("refuse-small", "a 32 GiB disk: refused (too_small)", rc != 0 and j.get("error") == "too_small", j)
    # the disk changes after the plan
    changed = blank("changed", 64)
    Ec = Engine(a.engine, make_root(run, "changed", stick, changed, target_serial="chg0"), uuid, f"{run}/refuse-changed")
    pc = f"{run}/refuse-changed/plan.json"
    rc, j, _ = Ec.run("plan", "--target", "nvme-QEMU_NVMe_Ctrl_chg0", "--layout", "whole", "--out", pc)
    with open(changed, "r+b") as f:
        f.seek(512)
        f.write(b"EFI PART-not-really")
    ch_before = sha_file(changed)
    rc, j, _ = Ec.run("apply", "--plan", pc, "--confirm-disk", "/dev/disk/by-id/nvme-QEMU_NVMe_Ctrl_chg0",
                      env={"OPENBOOK_INSTALL_ERASE": "/dev/disk/by-id/nvme-QEMU_NVMe_Ctrl_chg0"})
    check("refuse-changed", "the disk changed after the plan: refused (plan_changed, S4)",
          rc != 0 and j.get("code") == "plan_changed", j.get("code"))
    check("refuse-changed", "target unchanged", sha_file(changed) == ch_before)
    # a corrupted stick (S10)
    bad = f"{run}/stick-bad.img"
    shutil.copyfile(stick, bad)
    sup = next(p for p in meta["partitions"] if p["name"] == "super")
    with open(bad, "r+b") as f:
        f.seek(sup["start"] * 512 + 300 * MiB)
        f.write(b"\xde\xad\xbe\xef")
    tb = blank("target-bad", 64)
    Eb = Engine(a.engine, make_root(run, "bad", bad, tb, target_serial="bad0"), uuid, f"{run}/refuse-bad-stick")
    pb = f"{run}/refuse-bad-stick/plan.json"
    Eb.run("plan", "--target", "nvme-QEMU_NVMe_Ctrl_bad0", "--layout", "whole", "--out", pb)
    tb_before = sha_file(tb)
    rc, j, _ = Eb.run("apply", "--plan", pb, "--confirm-disk", "/dev/disk/by-id/nvme-QEMU_NVMe_Ctrl_bad0",
                      env={"OPENBOOK_INSTALL_ERASE": "/dev/disk/by-id/nvme-QEMU_NVMe_Ctrl_bad0"})
    check("refuse-bad-stick", "a corrupted super on the stick: check_source fails (S10)",
          rc != 0 and j.get("failed_step") == "check_source", j.get("error"))
    check("refuse-bad-stick", "nothing written to the target", sha_file(tb) == tb_before)
    os.remove(bad)

    # ---------------------------------------------------------------- whole-disk install
    E.out = f"{run}/whole"
    os.makedirs(E.out, exist_ok=True)
    rc, j, r = E.run("apply", "--plan", plan, "--confirm-disk", f"/dev/disk/by-id/{target}", "--events",
                     env={"OPENBOOK_INSTALL_ERASE": f"/dev/disk/by-id/{target}"})
    check("whole", "apply succeeds and verifies", rc == 0 and j.get("ok") and j.get("verified"), j.get("error"))
    steps = j.get("steps", {})
    check("whole", "every step done", all(s["state"] == "done" for s in steps.values()), steps)
    ev = [json.loads(l) for l in r.stdout.splitlines()[:-1] if l.startswith("{\"event\"")]
    check("whole", "progress events streamed", sum(e["event"] == "progress" for e in ev) >= 5 and
          any(e["event"] == "step" for e in ev), len(ev))
    v = sh("sgdisk", "-v", t).stdout
    check("whole", "GPT valid (sgdisk -v)", "No problems found" in v, v[-200:])
    gl = gpt_list(t)
    check("whole", "13 partitions as planned", list(gl) == [p["name"] for p in plan_j["partitions"]], list(gl))
    planned = {p["name"]: p for p in plan_j["partitions"]}
    check("whole", "partition offsets as planned",
          all(gl[n][1] * 512 == planned[n]["start"] and (gl[n][2] + 1) * 512 == planned[n]["start"] + planned[n]["bytes"]
              for n in gl))
    pu = sh("sgdisk", "-i", "1", t).stdout
    check("whole", "ESP PARTUUID is the bootconfig's boot_part_uuid",
          planned["EFI"]["partuuid"].upper() in pu, re.search(r"unique GUID: (\S+)", pu))
    eoff = planned["EFI"]["start"]
    espimg = f"{run}/whole/esp.img"
    sh("dd", f"if={t}", f"of={espimg}", "bs=1M", f"skip={eoff // MiB}", f"count={planned['EFI']['bytes'] // MiB}",
       "status=none")
    fs = sh("fsck.fat", "-n", espimg)
    check("whole", "ESP passes fsck.fat", fs.returncode == 0, fs.stdout[-200:] + fs.stderr[-200:])
    ok_files = []
    for f in plan_j["files"]:
        dest = f"{run}/whole/esp/{f['path']}"
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        got = esp_get(espimg, 0, f["path"], dest) and sha_file(dest) == f["sha256"]
        ok_files.append((f["path"], got))
    check("whole", "every ESP file read by mtools matches the plan", all(x for _, x in ok_files), ok_files)
    entry = open(f"{run}/whole/esp/loader/entries/openbook-a.conf").read() if os.path.exists(
        f"{run}/whole/esp/loader/entries/openbook-a.conf") else ""
    check("whole", "loader entry: kernel, three initrds with bootconfig last, vendor cmdline",
          "linux /openbook/a/kernel" in entry and entry.find("vendor_ramdisk") < entry.find("bootconfig.img") and
          "options " in entry, entry.replace("\n", " | "))
    bcf = f"{run}/whole/esp/openbook/a/bootconfig.img"
    bc = open(bcf, "rb").read() if os.path.exists(bcf) else b""
    bctext = bc[:bc.find(b"\0")].decode() if bc else ""
    check("whole", "bootconfig: the new ESP's PARTUUID, a new serial, no live flags, locale",
          f"androidboot.boot_part_uuid = {planned['EFI']['partuuid']}" in bctext and
          "androidboot.openbook.live" not in bctext and "androidboot.openbook.locale = en-US" in bctext and
          f"androidboot.serialno = {plan_j['seeds']['serialno']}" in bctext and bc.endswith(b"#BOOTCONFIG\n"), bctext)
    bcpy = sh("python3", os.path.join(os.path.dirname(os.path.abspath(__file__)), "bootconfig.py"), "show", bcf)
    check("whole", "bootconfig trailer checks out (bootconfig.py show)", bcpy.returncode == 0, bcpy.stderr)
    # super: metadata for 12 GiB, extents
    sp = planned["super"]
    head = f"{run}/whole/super-head.img"
    sh("dd", f"if={t}", f"of={head}", "bs=1M", f"skip={sp['start'] // MiB}", "count=1", "status=none")
    os.truncate(head, sp["bytes"])
    lp = sh(f"{HOST_TOOLS}/lpdump", head)
    open(f"{run}/whole/lpdump.txt", "w").write(lp.stdout + lp.stderr)
    ext = {e["name"]: e for e in inst["super"]["extents"]}
    got_ext = {m.group(2): int(m.group(1)) for m in re.finditer(r"super: (\d+) \.\. \d+: (\S+) \(", lp.stdout)}
    check("whole", "lpdump: super metadata for 12 GiB, virtual A/B, every logical partition at its offset",
          lp.returncode == 0 and "virtual_ab_device" in lp.stdout and
          all(got_ext.get(n) == e["dst"] // 512 for n, e in ext.items()), {n: got_ext.get(n) for n in ext})
    sizes_ok = all(sha_file(t, e["bytes"], sp["start"] + e["dst"]) == e["sha256"] for e in ext.values())
    check("whole", "every logical partition's bytes match the product image (sha256)", sizes_ok)
    copies = {p["name"]: p for p in plan_j["partitions"] if p["content"] == "copy"}
    check("whole", "boot_a, init_boot_a, vendor_boot_a, vbmeta_a match the stick (sha256)",
          all(sha_file(t, p["source_bytes"], p["start"]) == p["sha256"] for p in copies.values()), list(copies))
    with open(t, "rb") as f:
        heads = {}
        for n in ("userdata", "metadata", "misc", "boot_b"):
            f.seek(planned[n]["start"])
            heads[n] = f.read(MiB).count(0) == MiB
    check("whole", "metadata, userdata, misc and slot B start blank (Android formats them on first boot)",
          all(heads.values()), heads)
    rep = [x for x in sh("mdir", "-b", "-i", espimg, "::/openbook/logs").stdout.split() if x.endswith(".json")]
    check("whole", "install report on the new ESP", bool(rep), rep)
    srep = [x for x in sh("mdir", "-b", "-i", f"{stick}@@{esp['start'] * 512}", "::/openbook/logs").stdout.split()
            if "install-" in x]
    check("whole", "install report and log on the stick (S6)", len(srep) >= 2, srep)
    stick_esp = f"{run}/whole/stick-esp.img"
    sh("dd", f"if={stick}", f"of={stick_esp}", "bs=1M", f"skip={esp['start'] * 512 // MiB}",
       f"count={esp['sectors'] * 512 // MiB}", "status=none")
    fs2 = sh("fsck.fat", "-n", stick_esp)
    check("whole", "the stick's ESP still passes fsck.fat after the report", fs2.returncode == 0, fs2.stdout[-200:])
    now = {p["name"]: sha_file(stick, p["sectors"] * 512, p["start"] * 512) for p in meta["partitions"] if p["name"] != "EFI"}
    check("whole", "the stick's other partitions are unchanged", now == stick_sha_parts)

    # ---------------------------------------------------------------- alongside a Windows-like disk
    w = blank("windows", 300)
    wes = f"{run}/alongside/win-esp.img"
    os.makedirs(f"{run}/alongside", exist_ok=True)
    if os.path.exists(wes):
        os.remove(wes)
    sh("mkfs.fat", "-F", "32", "-n", "SYSTEM", "-C", wes, str(260 * 1024))
    for d in ("::/EFI", "::/EFI/Microsoft", "::/EFI/Microsoft/Boot", "::/EFI/BOOT"):
        sh("mmd", "-i", wes, d)
    fake = f"{run}/alongside/bootmgfw.efi"
    open(fake, "wb").write(os.urandom(150000))
    sh("mcopy", "-i", wes, fake, "::/EFI/Microsoft/Boot/bootmgfw.efi")
    sh("mcopy", "-i", wes, fake, "::/EFI/BOOT/BOOTX64.EFI")
    sh("sgdisk", "-n", "1:2048:+260M", "-t", "1:ef00", "-c", "1:EFI system partition",
       "-n", "2:0:+16M", "-t", "2:0c01", "-c", "2:Microsoft reserved partition",
       "-n", "3:0:+200G", "-t", "3:0700", "-c", "3:Basic data partition",
       "-n", "4:0:+800M", "-t", "4:2700", "-c", "4:", w)
    with open(w, "r+b") as f:  # the ESP is partition 1 at sector 2048
        f.seek(2048 * 512)
        f.write(open(wes, "rb").read())
    pw = sh("sgdisk", "-p", w).stdout
    starts = [int(m.group(1)) for m in re.finditer(r"^\s+\d+\s+(\d+)\s+\d+", pw, re.M)]
    with open(w, "r+b") as f:  # an NTFS boot sector on partition 3
        f.seek(starts[2] * 512 + 3)
        f.write(b"NTFS    ")
    parts_before = {}
    for m in re.finditer(r"^\s+(\d+)\s+(\d+)\s+(\d+)", pw, re.M):
        i, s, e = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if i in (2, 3, 4):
            parts_before[i] = sha_file(w, min((e - s + 1) * 512, 64 * MiB), s * 512)
    Ea = Engine(a.engine, make_root(run, "alongside", stick, w, target_serial="win0"), uuid, f"{run}/alongside")
    rc, j, _ = Ea.run("disks")
    wd = next((d for d in j.get("disks", []) if d["name"] == "nvme0n1"), {})
    check("alongside", "Windows found on the disk, alongside possible with the free space",
          "Windows" in wd.get("os", []) and wd.get("layouts", {}).get("alongside", {}).get("ok"), wd.get("layouts"))
    pa = f"{run}/alongside/plan.json"
    rc, j, _ = Ea.run("plan", "--target", "nvme-QEMU_NVMe_Ctrl_win0", "--layout", "alongside", "--out", pa)
    check("alongside", "plan: an XBOOTLDR partition and the Android partitions in the free space",
          rc == 0 and j["partitions"][0]["name"] == "xbootldr" and
          all(p["start"] >= 2048 * 512 + (260 + 16) * MiB + 200 * GiB for p in j["partitions"]), j.get("error"))
    check("alongside", "plan keeps every existing partition and erases none", len(j.get("keeps", [])) == 4 and
          not j.get("erases"))
    plan_a = j
    rc, j, _ = Ea.run("apply", "--plan", pa, "--confirm-disk", "/dev/disk/by-id/nvme-QEMU_NVMe_Ctrl_win0",
                      env={"OPENBOOK_INSTALL_ERASE": "/dev/disk/by-id/nvme-QEMU_NVMe_Ctrl_win0"})
    check("alongside", "apply succeeds and verifies", rc == 0 and j.get("verified"), j.get("error"))
    v = sh("sgdisk", "-v", w).stdout
    check("alongside", "GPT valid (sgdisk -v)", "No problems found" in v, v[-200:])
    pw2 = sh("sgdisk", "-p", w).stdout
    after = {}
    for m in re.finditer(r"^\s+(\d+)\s+(\d+)\s+(\d+)", pw2, re.M):
        i, s, e = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if i in (2, 3, 4):
            after[i] = sha_file(w, min((e - s + 1) * 512, 64 * MiB), s * 512)
    check("alongside", "MSR, NTFS and recovery partitions unchanged (S7)", after == parts_before)
    check("alongside", "4 + 13 partitions in the table", len(re.findall(r"^\s+\d+\s+\d+\s+\d+", pw2, re.M)) == 17)
    weimg = f"{run}/alongside/win-esp-after.img"
    sh("dd", f"if={w}", f"of={weimg}", "bs=1M", "skip=1", "count=260", "status=none")
    fs = sh("fsck.fat", "-n", weimg)
    check("alongside", "the Windows ESP passes fsck.fat", fs.returncode == 0, fs.stdout[-200:])
    got = f"{run}/alongside/got.efi"
    check("alongside", "EFI/Microsoft/Boot/bootmgfw.efi and EFI/BOOT/BOOTX64.EFI untouched",
          esp_get(weimg, 0, "/EFI/Microsoft/Boot/bootmgfw.efi", got) and sha_file(got) == sha_file(fake) and
          esp_get(weimg, 0, "/EFI/BOOT/BOOTX64.EFI", got) and sha_file(got) == sha_file(fake))
    sdb = next(f for f in plan_a["files"] if f["path"] == "EFI/OpenBook/systemd-bootx64.efi")
    check("alongside", "EFI/OpenBook/systemd-bootx64.efi added to the existing ESP",
          esp_get(weimg, 0, "/EFI/OpenBook/systemd-bootx64.efi", got) and sha_file(got) == sdb["sha256"])
    xb = plan_a["partitions"][0]
    xbimg = f"{run}/alongside/xbootldr.img"
    sh("dd", f"if={w}", f"of={xbimg}", "bs=1M", f"skip={xb['start'] // MiB}", f"count={xb['bytes'] // MiB}", "status=none")
    ls = sh("mdir", "-/", "-b", "-i", xbimg, "::/").stdout
    check("alongside", "XBOOTLDR holds the entry and the boot files, no loader.conf or fallback path",
          "openbook-a.conf" in ls and "/openbook/a/kernel" in ls.replace("::", "") and "loader.conf" not in ls and
          "BOOTX64" not in ls, ls[-300:])
    pt = sh("sgdisk", "-i", str(xb["index"]), w).stdout
    check("alongside", "XBOOTLDR has its type GUID", "BC13C2FF-59E6-4262-A352-B275FD6F7172" in pt)

    total = sum(len(v) for v in results["cases"].values())
    passed = sum(x["ok"] for v in results["cases"].values() for x in v)
    results.update(passed=passed, total=total, image=os.path.basename(a.image))
    json.dump(results, open(f"{run}/results.json", "w"), indent=1)
    with open(f"{run}/SUMMARY.md", "w") as f:
        f.write(f"# openbook-install host tests ({os.path.basename(a.image)})\n\n{passed}/{total} checks passed.\n\n"
                "| Case | Check | Result | Detail |\n|---|---|---|---|\n")
        for c, v in results["cases"].items():
            for x in v:
                f.write(f"| {c} | {x['check']} | {'PASS' if x['ok'] else 'FAIL'} | "
                        f"{x['detail'].replace('|', '/')[:120] if not x['ok'] else ''} |\n")
    print(f"{passed}/{total} checks passed")
    for name in ("stick.img", "target.img", "windows.img", "small.img", "changed.img", "target-bad.img"):
        if os.path.exists(f"{run}/{name}"):
            os.remove(f"{run}/{name}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
