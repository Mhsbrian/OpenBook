#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""End-to-end installer matrix in QEMU/KVM + OVMF (ANAL-192), on image files only. scripts/installer/e2e-qemu.sh
runs the cases; this file writes their disks and expect scripts, inspects the disks between runs, and checks.

Disks: a Windows-like disk (GPT: an ESP whose EFI/Microsoft/Boot/bootmgfw.efi and EFI/BOOT/BOOTX64.EFI are a
stand-in boot manager that prints a marker and powers off, MSR, a 100 GiB NTFS partition, a recovery partition,
about 99 GiB free), a 32 GiB blank disk, and a second Windows-like disk for the whole-disk runs.

Cases (each is one QEMU boot; the live ones boot a 16 GiB copy of the stick, SELinux enforcing):
  live-a          stick + Windows-like disk + 32 GiB disk: `disks`; the small disk refused (plan); the wizard's disk
                  screen; an alongside plan; apply without OPENBOOK_INSTALL_ERASE (refused); the unattended
                  alongside install (--confirm-disk + OPENBOOK_INSTALL_ERASE, --events); `disks` again
  al-windows      the alongside disk alone, fresh NVRAM: the firmware's fallback path still starts "Windows"
  al-fwsetup      a helper stick adds a firmware boot option for EFI/OpenBook/systemd-bootx64.efi, as a user does in
                  the firmware setup (OpenBook adds none: no efivarfs)
  al-openbook     the alongside disk alone with that NVRAM: OpenBook starts from the option; screenshots
  al-console      a copy with one more entry on XBOOTLDR (serial console): what the installed system sees
  cut-N           stick + the whole-disk target: the unattended install, and a power cut (QEMU quit) at step N;
                  each run restarts the install on the previous run's cut disk
  fw-cut-N        a copy of the cut disk alone, fresh NVRAM: what the firmware starts from it
  install         stick + the last cut disk: the install restarted and completed
  installed       the installed disk alone, unchanged, fresh NVRAM, no stick: screenshots
  inst-stick      a copy with a serial-console entry, the stick still plugged in and the disk first in the boot
                  order: what the installed system sees; through OpenBook setup to the desktop; the stick unchanged
  reinstall       stick + the used installed disk (after setup): the live system leaves it alone, sees OpenBook on
                  it; the wizard's disk screen; a whole-disk reinstall over it
  reinstalled     a console copy of the reinstalled disk, no stick: a new system (new serial, setup again)

usage: e2e-qemu.py mkdisk windows OUT --gib N --mark EFI      a Windows-like disk image
       e2e-qemu.py expect CASE OUT.json                       CASE's expect script
       e2e-qemu.py inspect DISK OUT.json [--plan PLAN.json] [--ref REF.json]   GPT, ESP files, bootability, digests
       e2e-qemu.py plan-of CASE_DIR OUT.json                  the plan a live case printed
       e2e-qemu.py avc OUT LOG... [--base DIR]                SELinux denials in logs, grouped (OUT.json, OUT.md)
       e2e-qemu.py check --run DIR --disks DIR --image IMG    results.json + SUMMARY.md
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import struct
import subprocess
import sys
import zlib

MiB, GiB = 1 << 20, 1 << 30
HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("wizard_qemu", os.path.join(HERE, "wizard-qemu.py"))
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)
PROMPT = W.PROMPT
TARGET = "nvme-QEMU_NVMe_Ctrl_internal0"
SMALL = "nvme-QEMU_NVMe_Ctrl_internal1"
ERASE = f"OPENBOOK_INSTALL_ERASE=/dev/disk/by-id/{TARGET}"
# Where each cut-N stops the install: (the engine's --events line to wait for, seconds after it). The engine
# fsyncs at the end of every step, so a cut right after a "done" or "running" event lands just after a barrier,
# and one a few seconds into a step lands in the middle of its writes.
CUTS = {
    1: (r'"step":"check_source","state":"running"', 1),     # before anything is written: the old table stays
    2: (r'"step":"boot_images","state":"running"', 0),      # right after the old table was wiped
    3: (r'"step":"system","state":"running"', 3),           # in the middle of super
    4: (r'"step":"boot_entry","state":"running"', 0.3),     # while the ESP is formatted and written
    5: (r'"step":"verify","state":"running"', 1),           # new table written, read-back running, not activated
    6: (r'"step":"report","state":"running"', 0),           # activated and verified, the report not yet written
}
WIN_PARTS = ("EFI system partition", "Microsoft reserved partition", "Basic data partition", "Recovery")


def sh(*cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)


# ------------------------------------------------------------------------------------------- disks and digests
def digest(path, off, length):
    """sha256 over the range's non-zero 64 KiB chunks with their offsets: equal content gives an equal digest
    whether zeros are holes or written zeros. Holes are skipped with SEEK_DATA, so sparse disks hash fast."""
    h = hashlib.sha256()
    end = off + length
    with open(path, "rb") as f:
        fd = f.fileno()
        pos = off
        while pos < end:
            try:
                d = os.lseek(fd, pos, os.SEEK_DATA)
            except OSError:
                break
            if d >= end:
                break
            hole = min(os.lseek(fd, d, os.SEEK_HOLE), end)
            p = d - (d - off) % 65536
            f.seek(p)
            while p < hole:
                blk = f.read(min(4 * MiB, end - p))
                if not blk:
                    break
                for i in range(0, len(blk), 65536):
                    c = blk[i:i + 65536]
                    if c.count(0) != len(c):
                        h.update(struct.pack("<Q", p + i - off) + c)
                p += len(blk)
            pos = max(hole, p)
    return h.hexdigest()


def gpt_read(path):
    """Both GPT copies: {"primary": {...} | None, "backup": ..., "mbr": "protective" | "none" | "other"}."""
    size = os.path.getsize(path)
    sectors = size // 512
    out = {"sectors": sectors}
    with open(path, "rb") as f:
        mbr = f.read(512)
        out["mbr"] = "none" if mbr.count(0) == 512 else \
            "protective" if mbr[510:512] == b"\x55\xaa" and mbr[446 + 4] == 0xEE else "other"

        def hdr(lba):
            f.seek(lba * 512)
            h = f.read(92)
            if h[:8] != b"EFI PART":
                return None
            crc = struct.unpack_from("<I", h, 16)[0]
            if zlib.crc32(h[:16] + b"\0\0\0\0" + h[20:92]) & 0xFFFFFFFF != crc:
                return {"valid": False, "why": "header crc"}
            my, alt, first, last = struct.unpack_from("<QQQQ", h, 24)
            guid = h[56:72]
            elba, n, esz, ecrc = struct.unpack_from("<QIII", h, 72)
            f.seek(elba * 512)
            ents = f.read(n * esz)
            if zlib.crc32(ents) & 0xFFFFFFFF != ecrc:
                return {"valid": False, "why": "entries crc", "alt": alt}
            parts = []
            for i in range(n):
                e = ents[i * esz:(i + 1) * esz]
                if e[:16].count(0) == 16:
                    continue
                fl, ll = struct.unpack_from("<QQ", e, 32)
                parts.append({"index": i + 1, "type": guid_str(e[:16]), "uuid": guid_str(e[16:32]), "first": fl,
                              "last": ll, "name": e[56:128].decode("utf-16-le").rstrip("\0")})
            return {"valid": True, "my": my, "alt": alt, "disk_guid": guid_str(guid), "parts": parts}

        p = hdr(1)
        out["primary"] = p
        alt = p.get("alt") if p and p.get("alt") else sectors - 1
        out["backup"] = hdr(alt) or (hdr(sectors - 1) if alt != sectors - 1 else None)
    return out


def guid_str(b):
    a, b2, c = struct.unpack_from("<IHH", b, 0)
    return f"{a:08X}-{b2:04X}-{c:04X}-{b[8:10].hex().upper()}-{b[10:16].hex().upper()}"


def table_of(g):
    """The table a reader would use: the primary if valid, else a valid backup (as firmware and Linux do)."""
    for k in ("primary", "backup"):
        if g.get(k) and g[k].get("valid"):
            return g[k], k
    return None, None


def fat_files(path, off):
    r = sh("mdir", "-/", "-b", "-i", f"{path}@@{off}", "::/")
    return sorted(x[3:] if x.startswith("::/") else x for x in r.stdout.split() if not x.endswith("/")) \
        if r.returncode == 0 else None


def fat_sha(path, off, name, tmp):
    if os.path.exists(tmp):
        os.remove(tmp)
    r = sh("mcopy", "-n", "-o", "-i", f"{path}@@{off}", f"::/{name}", tmp)
    if r.returncode or not os.path.exists(tmp):
        return None
    h = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
    os.remove(tmp)
    return h


def fsck_fat(path, off, length, tmp):
    with open(path, "rb") as f, open(tmp, "wb") as o:
        f.seek(off)
        left = length
        while left:
            b = f.read(min(left, 16 * MiB))
            if not b:
                break
            o.write(b)
            left -= len(b)
    r = sh("fsck.fat", "-n", tmp)
    os.remove(tmp)
    return {"rc": r.returncode, "out": (r.stdout + r.stderr).strip().splitlines()[-3:]}


def inspect(a):
    """One disk image, read only: its GPT (both copies), every FAT partition's files, what the firmware could start
    (EFI/BOOT/BOOTX64.EFI, an OpenBook loader entry), the files of --plan against their hashes, and a digest of every
    partition of --ref (a reference inspection: are they still there, byte for byte?)."""
    g = gpt_read(a.disk)
    t, which = table_of(g)
    res = {"disk": os.path.basename(a.disk), "mbr": g["mbr"], "primary_valid": bool(g["primary"] and g["primary"].get("valid")),
           "backup_valid": bool(g["backup"] and g["backup"].get("valid")), "table_from": which,
           "disk_guid": t["disk_guid"] if t else None, "partitions": [], "fat": {}}
    tmp = a.out + ".tmp"
    for p in (t["parts"] if t else []):
        off, ln = p["first"] * 512, (p["last"] - p["first"] + 1) * 512
        with open(a.disk, "rb") as f:
            f.seek(off)
            head = f.read(MiB)
        q = dict(p, bytes=ln, digest=digest(a.disk, off, min(ln, 64 * GiB)), head_blank=head.count(0) == len(head))
        res["partitions"].append(q)
        files = fat_files(a.disk, off)
        if files is not None:
            res["fat"][p["name"]] = {"files": files, "fsck": fsck_fat(a.disk, off, ln, tmp) if ln <= GiB else None,
                                     "sha256": {x: fat_sha(a.disk, off, x, tmp) for x in files
                                                if x.lower().endswith((".efi", ".conf")) or "bootmgfw" in x.lower()}}
    lower = {n: [x.lower() for x in v["files"]] for n, v in res["fat"].items()}
    res["fallback"] = [n for n, v in lower.items() if "efi/boot/bootx64.efi" in v]
    res["openbook_entry"] = [n for n, v in lower.items() if any(x.startswith("loader/entries/openbook") for x in v)]
    if a.plan and os.path.exists(a.plan):
        plan = json.load(open(a.plan))
        boot = next((p for p in plan.get("partitions", []) if p["name"] in ("EFI", "xbootldr")), None)
        ok, bad = [], []
        if boot and t:
            tp = next((p for p in t["parts"] if p["uuid"].upper() == boot["partuuid"].upper()), None)
            for f in plan.get("files", []):
                if f.get("shared"):
                    continue
                got = fat_sha(a.disk, tp["first"] * 512, f["path"], tmp) if tp else None
                (ok if got == f["sha256"] else bad).append(f["path"])
        res["plan_files_ok"], res["plan_files_bad"] = len(ok), bad
        res["plan_table"] = bool(t and boot and any(p["uuid"].upper() == boot["partuuid"].upper() for p in t["parts"]))
    if a.ref and os.path.exists(a.ref):
        ref = json.load(open(a.ref))
        cur = {p["uuid"]: p for p in res["partitions"]}
        res["ref_partitions"] = {p["name"]: ("unchanged" if cur.get(p["uuid"], {}).get("digest") == p["digest"] else
                                             "changed" if p["uuid"] in cur else "gone") for p in ref["partitions"]}
        # Without a table, are the old partitions' bytes still there (the wipe only clears the table)?
        res["ref_bytes"] = {p["name"]: digest(a.disk, p["first"] * 512, min(p["bytes"], 64 * GiB)) == p["digest"]
                            for p in ref["partitions"]} if not t or which != "primary" or \
            res["disk_guid"] != ref["disk_guid"] else None
    # The state, for the S9 rule: the old table, no table, or the new one; bootable only when complete.
    if not t:
        res["state"] = "blank"
    elif a.ref and os.path.exists(a.ref) and res["disk_guid"] == json.load(open(a.ref))["disk_guid"]:
        res["state"] = "old-table"
    elif res.get("plan_table"):
        res["state"] = "new-complete" if res["openbook_entry"] and not res.get("plan_files_bad") else \
            "new-not-activated" if not res["openbook_entry"] and not res["fallback"] else "new-inconsistent"
    else:
        res["state"] = "other-table"
    json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("state", "mbr", "primary_valid", "backup_valid", "fallback", "openbook_entry")}))
    return 0


def mkdisk(a):
    """A Windows-like disk: ESP (FAT32 "SYSTEM": EFI/Microsoft/Boot/{bootmgfw.efi,BCD}, EFI/BOOT/BOOTX64.EFI), MSR,
    NTFS, recovery, the rest free. Random bytes at the start, middle and end of each partition make digests count."""
    out = a.out
    if os.path.exists(out):
        os.remove(out)
    with open(out, "wb") as f:
        f.truncate(a.gib * GiB)
    ntfs_gib = a.gib - 100 if a.gib > 200 else a.gib // 2
    r = sh("sgdisk", "-n", "1:2048:+260M", "-t", "1:ef00", "-c", "1:EFI system partition",
           "-n", "2:0:+16M", "-t", "2:0c01", "-c", "2:Microsoft reserved partition",
           "-n", f"3:0:+{ntfs_gib}G", "-t", "3:0700", "-c", "3:Basic data partition",
           "-n", "4:0:+800M", "-t", "4:2700", "-c", "4:Recovery", out)
    if r.returncode:
        sys.exit(r.stderr)
    esp = out + ".esp"
    if os.path.exists(esp):
        os.remove(esp)
    sh("mkfs.fat", "-F", "32", "-n", "SYSTEM", "-C", esp, str(260 * 1024))
    for d in ("::/EFI", "::/EFI/Microsoft", "::/EFI/Microsoft/Boot", "::/EFI/BOOT"):
        sh("mmd", "-i", esp, d)
    bcd = out + ".bcd"
    open(bcd, "wb").write(os.urandom(32768))
    for src, dst in ((a.mark, "::/EFI/Microsoft/Boot/bootmgfw.efi"), (a.mark, "::/EFI/BOOT/BOOTX64.EFI"),
                     (bcd, "::/EFI/Microsoft/Boot/BCD")):
        sh("mcopy", "-i", esp, src, dst)
    os.remove(bcd)
    g = gpt_read(out)
    parts = {p["index"]: p for p in g["primary"]["parts"]}
    with open(out, "r+b") as f:
        f.seek(parts[1]["first"] * 512)
        f.write(open(esp, "rb").read())
        for i in (2, 3, 4):
            s, e = parts[i]["first"] * 512, (parts[i]["last"] + 1) * 512
            for at in (s, (s + e) // 2 // MiB * MiB, e - MiB):
                f.seek(at)
                f.write(os.urandom(MiB))
        f.seek(parts[3]["first"] * 512 + 3)
        f.write(b"NTFS    ")
    os.remove(esp)
    print(json.dumps({"disk": out, "gib": a.gib, "partitions": [(p["index"], p["name"]) for p in parts.values()]}))
    return 0


# ------------------------------------------------------------------------------------------- expect scripts
def section(name, cmd, timeout=180):
    # As wizard-qemu.py's, but the end marker must start a line: the shell's echo of the typed command contains it
    # too, and matching that echo would leave only the prompt's 30 s for a long command such as an install.
    return [{"send": f"echo ==={name}-BEGIN===; {cmd}; echo ==={name}-END===\n"},
            {"wait": f"\n==={name}-END===", "timeout": timeout}, {"wait": PROMPT, "timeout": 30}]


def poweroff():
    # The guest powers off; QEMU exits and the run ends there.
    return [{"send": "sync; reboot -p\n"}, {"wait": r"reboot: Power down|ACPI: PM: Preparing to enter system sleep state S5|Power down", "timeout": 120}]


def wizard_to_disks(name):
    s = W.wait_ui("Choose your language", 180)
    s += W.tap("Continue", 4)
    s += W.wait_ui("STEP 2 OF 7", 120)
    s += W.tap("Continue", 4)
    s += W.wait_ui("STEP 3 OF 7", 60)
    s += W.tap("Install OpenBook", 2)
    s += W.tap("Continue", 4)
    s += W.wait_ui("Choose your image base", 60)
    s += W.tap("Continue", 4)
    s += W.wait_ui("STEP 4 OF 7", 90)
    s += [{"pause": 5}]
    s += W.shot(name)
    s += [{"send": "input keyevent 111\n"}, {"wait": PROMPT, "timeout": 30}, {"pause": 2}]
    return s


def live_common():
    s = W.steps_common_boot() + W.helpers()
    s += section("PROPS", "getprop | grep -E 'ro.boot.(openbook|selinux|boot_part_uuid|serialno)|ro.build.fingerprint'; getenforce")
    s += section("BYNAME", "ls -l /dev/block/by-name; echo MOUNTS; grep -E '/dev/block/(nvme|sd|vd)' /proc/mounts; echo SWAPS; cat /proc/swaps")
    return s


def apply_cmd(plan, env=True, events=True):
    return (f"{ERASE + ' ' if env else ''}openbook-install apply --plan {plan} --confirm-disk /dev/disk/by-id/{TARGET}"
            f"{' --events' if events else ''}; echo APPLY-RC=$?")


def expect(case):
    s = []
    if case == "live-a":
        s = live_common()
        s += section("DISKS", "openbook-install disks", 120)
        s += section("PLAN-SMALL", f"openbook-install plan --target /dev/disk/by-id/{SMALL} --layout whole; echo PLAN-RC=$?", 120)
        s += wizard_to_disks("4-disk-windows-and-small")
        s += section("PLAN", f"openbook-install plan --target /dev/disk/by-id/{TARGET} --layout alongside --locale en-US --keyboard us --out /data/local/tmp/plan-a.json", 120)
        s += section("APPLY-NOENV", apply_cmd("/data/local/tmp/plan-a.json", env=False, events=False), 120)
        s += section("APPLY", apply_cmd("/data/local/tmp/plan-a.json"), 900)
        s += section("DISKS-AFTER", "openbook-install disks", 120)
        s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
        s += poweroff()
    elif case in ("al-windows", "al-fwsetup", "al-openbook") or case.startswith("fw-cut-"):
        s = []  # firmware only: the serial log has OVMF's BdsDxe lines and the stand-ins' markers
    elif case.startswith("cut-") or case == "install":
        s = W.steps_common_boot()
        s += section("PRE-DISKS", "openbook-install disks", 120)
        s += section("PLAN", f"openbook-install plan --target /dev/disk/by-id/{TARGET} --layout whole --locale en-US --keyboard us --out /data/local/tmp/plan.json", 120)
        if case == "install":
            s += section("APPLY", apply_cmd("/data/local/tmp/plan.json"), 900)
            s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
            s += poweroff()
        else:
            ev, delay = CUTS[int(case.split("-")[1])]
            s += [{"send": apply_cmd("/data/local/tmp/plan.json") + "\n"}, {"wait": ev, "timeout": 600}]
            if delay:
                s += [{"pause": delay}]
            s += [{"monitor": "quit"}]  # the power cut: the guest's unwritten cache is lost
    elif case in ("al-console", "inst-stick", "reinstalled"):
        s = W.steps_common_boot() + W.helpers()
        s += W.send(f"export SNAPDEV=/dev/block/nvme0n1p{1 if case != 'al-console' else 5}", 30)
        s += section("INSTALLED", "getprop | grep -E 'ro.boot.(openbook|selinux|boot_part_uuid|serialno|slot_suffix|verifiedbootstate)|init.svc.openbook|sys.boot_completed'; getenforce; ls -l /dev/block/by-name; cat /proc/partitions; echo MOUNTS; grep -E '/dev/block/(nvme|sd|vd)' /proc/mounts; df -k /data /metadata")
        s += section("INSTALLER-STATE", "pm query-activities -a android.intent.action.MAIN -c android.intent.category.LAUNCHER | grep -c org.openbook.installer; echo daemon=[$(getprop init.svc.openbook_installd)]; settings get global device_provisioned; dumpsys activity activities | grep -E 'topResumedActivity' | head -n 2")
        s += section("VOLD", "logcat -d -b main,system | grep -iE 'vold|StorageManager|DiskInfo|VolumeInfo' | grep -iE 'disk|volume|8:0|public|unsupported|mount' | tail -n 40; sm list-disks; sm list-volumes all", 120)
        s += section("NOTIFICATIONS", "dumpsys notification --noredact | grep -A40 'tag=disk:' | grep -E 'tag=disk:|android.title=|android.text=' | head -n 12; echo NOTIF-END", 120)
        s += W.send("input keyevent 224; wm dismiss-keyguard", 30)
        s += W.wait_ui("Get started", 180)
        s += W.shot(f"{case}-setup-welcome")
        s += W.setup_steps(f"{case}-setup", shots=False, first_timeout=60)
        s += W.shot(f"{case}-desktop")
        s += section("AFTER-SETUP", "settings get global device_provisioned; settings get secure user_setup_complete; dumpsys activity activities | grep -E 'topResumedActivity' | head -n 1")
        s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
        s += poweroff()
    elif case == "reinstall":
        s = live_common()
        s += section("DISKS", "openbook-install disks", 120)
        s += wizard_to_disks("4-disk-installed-openbook")
        s += section("PLAN", f"openbook-install plan --target /dev/disk/by-id/{TARGET} --layout whole --locale en-US --keyboard us --out /data/local/tmp/plan-r.json", 120)
        s += section("PLAN-ALONGSIDE", f"openbook-install plan --target /dev/disk/by-id/{TARGET} --layout alongside; echo PLAN-RC=$?", 120)
        s += section("APPLY", apply_cmd("/data/local/tmp/plan-r.json"), 900)
        s += section("AVC", "logcat -d -b all | grep -E 'avc: +denied' | head -n 200", 120)
        s += poweroff()
    elif case == "installed":
        s = []
    else:
        sys.exit(f"unknown case {case}")
    return s


# ------------------------------------------------------------------------------------------- checks
def json_lines(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def png_stats(path):
    """Mean brightness and the share of non-dark pixels of a PNG written by qemu-run.py (8-bit RGB, filter 0)."""
    data = open(path, "rb").read()
    w, h = struct.unpack(">II", data[16:24])
    idat, i = b"", 8
    while i < len(data):
        n, t = struct.unpack(">I", data[i:i + 4])[0], data[i + 4:i + 8]
        if t == b"IDAT":
            idat += data[i + 8:i + 8 + n]
        i += 12 + n
    raw = zlib.decompress(idat)
    stride = 1 + 3 * w
    tot, bright, cnt = 0, 0, 0
    for y in range(0, h, 8):
        row = raw[y * stride + 1:(y + 1) * stride]
        if raw[y * stride] != 0:
            return None
        for x in range(0, 3 * w, 24):
            v = row[x] + row[x + 1] + row[x + 2]
            tot += v
            bright += v > 120
            cnt += 1
    return {"w": w, "h": h, "mean": round(tot / cnt / 3, 1), "lit": round(bright / cnt, 3)}


def check(a):
    R, Q = a.run, a.disks
    res = {"cases": {}}

    def chk(case, what, ok, detail=""):
        res["cases"].setdefault(case, []).append({"check": what, "ok": bool(ok), "detail": str(detail)[:400]})

    def load(case):
        d = f"{R}/{case}"
        if not os.path.exists(f"{d}/result.json"):
            return None, "", {}
        r = json.load(open(f"{d}/result.json"))
        t = open(f"{d}/serial.log", "rb").read().decode("utf-8", "replace")
        sec = W.sections(t)
        os.makedirs(f"{d}/sections", exist_ok=True)
        for k, v in sec.items():
            open(f"{d}/sections/{k.lower()}.txt", "w").write(v)
        return r, t, sec

    def steps(case, r):
        # A run that ends with the guest powering off may stop QEMU before its last wait is read.
        ok = r["steps_done"] == r["steps"] or (r["reason"].startswith("QEMU exited") and r["steps_done"] == r["steps"] - 1)
        chk(case, "every expect step matched", ok, f"{r['steps_done']}/{r['steps']} ({r['reason']})")

    def lit(case):
        shots = sorted((f for f in os.listdir(f"{R}/{case}") if re.match(r"shot-\d+\.png$", f)), key=lambda x: int(re.sub(r"\D", "", x)))
        st = {f: png_stats(f"{R}/{case}/{f}") for f in shots}
        return any(v and v["lit"] > 0.3 for f, v in st.items() if int(re.sub(r"\D", "", f)) >= 20), \
            {k: v["lit"] if v else None for k, v in st.items()}

    def insp(name):
        p = f"{R}/inspect/{name}.json"
        return json.load(open(p)) if os.path.exists(p) else None

    def disks_of(sec, key="DISKS"):
        j = [x for x in json_lines(sec.get(key, "")) if "disks" in x]
        return {d["by_id"]: d for d in j[0]["disks"]} if j else {}

    def report_of(sec):
        j = [x for x in json_lines(sec.get("APPLY", "")) if x.get("schema") == "openbook-install-report/1"]
        return j[-1] if j else {}

    def avc_ours(sec):
        return [l for l in sec.get("AVC", "").splitlines() if "denied" in l and re.search(r"openbook|org\.openbook", l)]

    base = insp("windows-before")
    # ---- live-a: the alongside install and the refusals
    r, t, sec = load("live-a")
    if r:
        steps("live-a", r)
        chk("live-a", "SELinux enforcing; booted from the stick (by-name on sda)", "Enforcing" in sec.get("PROPS", "") and
            re.search(r"super -> /dev/block/sda\d", sec.get("BYNAME", "")), sec.get("BYNAME", "")[:200])
        d = disks_of(sec)
        win, small = d.get(TARGET, {}), d.get(SMALL, {})
        chk("live-a", "disks: the Windows-like disk shows Windows; alongside and whole both possible",
            "Windows" in win.get("os", []) and win.get("layouts", {}).get("alongside", {}).get("ok") and
            win.get("layouts", {}).get("whole", {}).get("ok"), win.get("layouts"))
        chk("live-a", "disks: the 32 GiB disk is refused for both layouts (whole: too_small)",
            small.get("layouts", {}).get("whole", {}).get("why") == "too_small" and
            not small.get("layouts", {}).get("alongside", {}).get("ok"), small.get("layouts"))
        ps = json_lines(sec.get("PLAN-SMALL", ""))
        chk("live-a", "plan on the 32 GiB disk: refused (not_eligible: too_small)", ps and ps[0].get("code") == "not_eligible" and
            ps[0].get("error") == "too_small" and
            "PLAN-RC=1" in sec.get("PLAN-SMALL", ""), sec.get("PLAN-SMALL", "")[:200])
        chk("live-a", "the wizard's disk screen captured (screenshot)",
            os.path.exists(f"{R}/live-a/screens/shots/4-disk-windows-and-small.png") or
            os.path.exists(f"{R}/live-a/shot-4-disk-windows-and-small.png"))
        pa = json_lines(sec.get("PLAN", ""))
        pa = pa[0] if pa else {}
        chk("live-a", "alongside plan: keeps the 4 Windows partitions, erases none",
            pa.get("plan_sha256") and len(pa.get("keeps", [])) == 4 and not pa.get("erases"), pa.get("error"))
        ne = json_lines(sec.get("APPLY-NOENV", ""))
        chk("live-a", "apply without OPENBOOK_INSTALL_ERASE: refused (confirm_mismatch)",
            ne and ne[-1].get("code") == "confirm_mismatch" and "APPLY-RC=1" in sec.get("APPLY-NOENV", ""),
            sec.get("APPLY-NOENV", "")[-200:])
        rep = report_of(sec)
        evs = [x for x in json_lines(sec.get("APPLY", "")) if x.get("event")]
        chk("live-a", "unattended alongside install (--confirm-disk + OPENBOOK_INSTALL_ERASE): ok and verified",
            rep.get("ok") and rep.get("verified") and "APPLY-RC=0" in sec.get("APPLY", ""), rep.get("error"))
        chk("live-a", "machine-readable progress: step and progress events, then the report",
            sum(e["event"] == "step" for e in evs) >= 12 and any(e["event"] == "progress" for e in evs), len(evs))
        da = disks_of(sec, "DISKS-AFTER").get(TARGET, {})
        chk("live-a", "after the install: Windows and OpenBook on the disk; a second alongside refused (name_clash)",
            {"Windows", "OpenBook"} <= set(da.get("os", [])) and
            da.get("layouts", {}).get("alongside", {}).get("why") == "name_clash", (da.get("os"), da.get("layouts")))
        chk("live-a", "no SELinux denial for the engine or the app (enforcing)", not avc_ours(sec), avc_ours(sec)[:3])
        after = insp("windows-after")
        if base and after:
            ref = after.get("ref_partitions", {})
            chk("live-a", "MSR, NTFS and recovery partitions byte-identical (S7)",
                all(ref.get(n) == "unchanged" for n in WIN_PARTS[1:]), ref)
            wb, wa = base["fat"].get(WIN_PARTS[0], {}), after["fat"].get(WIN_PARTS[0], {})
            added = sorted(set(wa.get("files", [])) - set(wb.get("files", [])))
            chk("live-a", "Windows ESP: only EFI/OpenBook/systemd-bootx64.efi added; bootmgfw.efi, BCD and BOOTX64.EFI unchanged",
                added == ["EFI/OpenBook/systemd-bootx64.efi"] and set(wb.get("files", [])) <= set(wa.get("files", [])) and
                all(wa["sha256"].get(k) == v for k, v in wb.get("sha256", {}).items()), added)
            chk("live-a", "Windows ESP passes fsck.fat after the install", (wa.get("fsck") or {}).get("rc") == 0, wa.get("fsck"))
            chk("live-a", "GPT: both copies valid, 4 + 13 partitions, the Windows ones at the same place",
                after["primary_valid"] and after["backup_valid"] and len(after["partitions"]) == 17 and
                all(any(q["uuid"] == p["uuid"] and q["first"] == p["first"] and q["last"] == p["last"]
                        for q in after["partitions"]) for p in base["partitions"]), len(after["partitions"]))
            chk("live-a", "XBOOTLDR holds the OpenBook entry; no loader.conf; the fallback path is Windows'",
                after["openbook_entry"] == ["xbootldr"] and
                "loader/loader.conf" not in after["fat"].get("xbootldr", {}).get("files", []) and
                after["fallback"] == [WIN_PARTS[0]], (after["openbook_entry"], after["fallback"]))
    # ---- the alongside disk in the firmware
    r, t, sec = load("al-windows")
    if r:
        chk("al-windows", "fresh NVRAM: the firmware starts the disk's fallback path, Windows' boot manager (stand-in)",
            re.search(r"OBTEST-MARK windows-bootmgr \\EFI\\BOOT\\BOOTX64\.EFI", t), re.findall(r"BdsDxe: \w+ Boot\w+ \"[^\"]+\"", t)[:4])
    r, t, sec = load("al-fwsetup")
    if r:
        chk("al-fwsetup", "a firmware boot option for EFI/OpenBook/systemd-bootx64.efi added (as in the firmware setup)",
            re.search(r"OBTEST-ADDBOOT ok: Boot1000 \"OpenBook\" -> \\EFI\\OpenBook\\systemd-bootx64\.efi", t), t[-300:])
    r, t, sec = load("al-openbook")
    if r:
        chk("al-openbook", "the firmware starts Boot1000 \"OpenBook\" from the Windows ESP", re.search(
            r"BdsDxe: starting Boot1000 \"OpenBook\" .*HD\(1,GPT.*\\EFI\\OpenBook\\systemd-bootx64\.efi", t),
            re.findall(r"BdsDxe: \w+ Boot\w+ \"[^\"]+\"", t)[:4])
        ok, st = lit("al-openbook")
        chk("al-openbook", "OpenBook's screen comes up (a screenshot after 20 s is lit, not a black or firmware screen)", ok, st)
        chk("al-openbook", "Windows was not started instead", "OBTEST-MARK" not in t)
    r, t, sec = load("al-console")
    if r:
        s = sec.get("INSTALLED", "")
        steps("al-console", r)
        xb = next((p for p in (insp("windows-after") or {}).get("partitions", []) if p["name"] == "xbootldr"), {})
        chk("al-console", "booted alongside: installed=alongside, boot_part_uuid is XBOOTLDR, enforcing, no live flags",
            "[ro.boot.openbook.installed]: [alongside]" in s and xb and xb["uuid"].lower() in s.lower() and
            "Enforcing" in s and "ro.boot.openbook.live" not in s, s[:300])
        links = re.findall(r" (\S+) -> (/dev/block/\S+)", s)
        chk("al-console", "Android's by-name links point at the NVMe disk", links and all("nvme0n1" in x for _, x in links),
            ", ".join(sorted(n for n, _ in links))[:300])
        m = s.split("MOUNTS", 1)[1] if "MOUNTS" in s else ""
        chk("al-console", "no Windows partition mounted (p1 to p4)", not re.search(r"nvme0n1p[1-4] ", m), m[:200])
        chk("al-console", "OpenBook setup, then the desktop", "SetupActivity" in sec.get("INSTALLER-STATE", "") and
            sec.get("AFTER-SETUP", "").strip().splitlines()[:2] == ["1", "1"], sec.get("AFTER-SETUP", "")[:200])
    # ---- the cut chain
    prev = "whole-before"
    for n in sorted(CUTS):
        c = f"cut-{n}"
        r, t, sec = load(c)
        if not r:
            continue
        ev, delay = CUTS[n]
        hit = re.search(ev, t)
        chk(c, f"the install reached its cut point ({ev.split(':')[1].split(',')[0]} {ev.rsplit(':', 1)[1]} + {delay} s) and the power was cut",
            hit and r["reason"].startswith("QEMU exited") and r["steps_done"] == r["steps"], r["reason"])
        pre = disks_of(sec, "PRE-DISKS").get(TARGET, {})
        chk(c, "restart from the stick: the engine reads the previous state and offers the disk again (whole ok)",
            pre.get("layouts", {}).get("whole", {}).get("ok"), (prev, pre.get("table"), pre.get("os"), pre.get("layouts", {}).get("whole")))
        i = insp(c)
        if i:
            want = {1: {"old-table"}, 2: {"blank"}, 3: {"blank"}, 4: {"blank", "new-not-activated"},
                    5: {"new-not-activated"}, 6: {"new-complete"}}[n]
            chk(c, f"cut state is one of {sorted(want)} (S9: the old table, a blank disk, or the new one, bootable only when complete)",
                i["state"] in want, f"{i['state']} (mbr {i['mbr']}, primary {i['primary_valid']}, backup {i['backup_valid']}, entry {i['openbook_entry']}, fallback {i['fallback']})")
            if n == 1:
                chk(c, "the old table and every old partition unchanged", i.get("ref_partitions") and
                    all(v == "unchanged" for v in i["ref_partitions"].values()), i.get("ref_partitions"))
        rf, tf, _ = load(f"fw-cut-{n}")
        if rf:
            started = [x for x in re.findall(r"BdsDxe: starting (Boot\w+ \"[^\"]+\")", tf) if "NVMe" in x]
            seen = started or re.findall(r"BdsDxe: failed to load (Boot\w+ \"[^\"]+\")", tf)[:3]
            if n == 1:
                chk(f"fw-cut-{n}", "the firmware still starts the old system (Windows stand-in) from the untouched disk",
                    started and "OBTEST-MARK windows-bootmgr" in tf, seen)
            elif n == 6:
                chk(f"fw-cut-{n}", "the firmware starts the complete install (OpenBook's fallback path)",
                    started and "OBTEST-MARK" not in tf, seen)
            else:
                chk(f"fw-cut-{n}", "the firmware starts nothing from the cut disk (no table, or not activated)",
                    not started and "OBTEST-MARK" not in tf, seen)
        if i and i["state"].startswith("new"):
            e = (i["fat"].get("EFI") or {}).get("fsck") or {}
            chk(c, "the new ESP passes fsck.fat", e.get("rc") == 0, e)
        prev = c
    r, t, sec = load("install")
    if r:
        rep = report_of(sec)
        steps("install", r)
        chk("install", "restarted over the last cut disk: ok and verified", rep.get("ok") and rep.get("verified"), rep.get("error"))
        chk("install", "no SELinux denial for the engine (enforcing)", not avc_ours(sec), avc_ours(sec)[:3])
        i = insp("install")
        if i:
            chk("install", "the disk: both GPT copies valid, every planned file present and matching, bootable",
                i["state"] == "new-complete" and i["primary_valid"] and i["backup_valid"] and i["mbr"] == "protective" and
                i["fallback"] == ["EFI"], i["state"])
    r, t, sec = load("installed")
    if r:
        ok, st = lit("installed")
        chk("installed", "no stick, fresh NVRAM: the firmware starts the installed disk's fallback path",
            re.search(r"BdsDxe: starting Boot\w+ \"UEFI QEMU NVMe Ctrl internal0", t), re.findall(r"BdsDxe: \w+ Boot\w+ \"[^\"]+\"", t)[:4])
        chk("installed", "OpenBook's first screen comes up (a screenshot after 20 s is lit)", ok, st)
    for c in ("inst-stick", "reinstalled"):
        r, t, sec = load(c)
        if not r:
            continue
        s = sec.get("INSTALLED", "")
        steps(c, r)
        links = re.findall(r" (\S+) -> (/dev/block/\S+)", s)
        chk(c, "booted from the NVMe disk: by-name links there, installed=whole, enforcing, no live flags",
            links and all("nvme0n1" in x for _, x in links) and "[ro.boot.openbook.installed]: [whole]" in s and
            "Enforcing" in s and "ro.boot.openbook.live" not in s, s[:200])
        ist = sec.get("INSTALLER-STATE", "").strip().splitlines()
        chk(c, "the installer is off (no launcher entry, no daemon); OpenBook setup is the first screen",
            ist and ist[0].strip() == "0" and "daemon=[]" in sec.get("INSTALLER-STATE", "") and
            "SetupActivity" in sec.get("INSTALLER-STATE", ""), ist[:4])
        chk(c, "through setup to the desktop", sec.get("AFTER-SETUP", "").strip().splitlines()[:2] == ["1", "1"],
            sec.get("AFTER-SETUP", "")[:200])
        if c == "inst-stick":
            m = s.split("MOUNTS", 1)[1] if "MOUNTS" in s else ""
            chk(c, "the stick plugged in: no partition of it mounted by Android (vold)", not re.search(r"/dev/block/(sda|vold/public:8,)", m), m[:200])
            ss = insp("stick-after-inst-stick"), insp("stick-before-inst-stick")
            if all(ss):
                ch = {p["name"]: p["digest"] == q["digest"] for p, q in zip(ss[0]["partitions"], ss[1]["partitions"])}
                chk(c, "the stick's partitions unchanged by the installed system", all(ch.values()), ch)
            res.setdefault("notes", {})["inst-stick-vold"] = sec.get("VOLD", "")[-1500:]
            nt = sec.get("NOTIFICATIONS", "")
            res["notes"]["inst-stick-notifications"] = nt[-1500:]
            # Known issue (docs/INSTALL.md): vold cannot read the stick's table and SystemUI offers to set it up
            # (format it). PR #52 only leaves alone the disk the running system booted from. Reported, not gated.
            m = re.search(r"tag=(disk:\d+,\d+).*?android\.title=String \(([^)]*)\)", nt, re.S)
            chk(c, "known issue, reported: SystemUI's notification for the plugged-in stick (not gated)", True,
                f"{m.group(1)}: '{m.group(2).strip()}' (Tap to set up = format)" if m else "none")
        else:
            s0 = (W.sections(open(f"{R}/inst-stick/serial.log", "rb").read().decode("utf-8", "replace")).get("INSTALLED", "")
                  if os.path.exists(f"{R}/inst-stick/serial.log") else "")
            ser = lambda x: (re.findall(r"\[ro\.boot\.serialno\]: \[(\w+)\]", x) or [None])[0]
            chk(c, "a new system: a new serial number, setup again", ser(s) and ser(s0) and ser(s) != ser(s0) and
                "SetupActivity" in sec.get("INSTALLER-STATE", ""), (ser(s0), ser(s)))
    r, t, sec = load("reinstall")
    if r:
        steps("reinstall", r)
        b = sec.get("BYNAME", "")
        chk("reinstall", "the live system boots from the stick with OpenBook installed on the NVMe disk (by-name on sda, nothing of nvme mounted)",
            re.search(r"super -> /dev/block/sda\d", b) and "nvme" not in b.split("MOUNTS", 1)[-1], b[:200])
        d = disks_of(sec).get(TARGET, {})
        chk("reinstall", "disks: OpenBook found on the NVMe disk, whole possible, alongside refused (name_clash)",
            "OpenBook" in d.get("os", []) and d.get("layouts", {}).get("whole", {}).get("ok") and
            d.get("layouts", {}).get("alongside", {}).get("why") == "name_clash", (d.get("os"), d.get("layouts")))
        rep = report_of(sec)
        chk("reinstall", "whole-disk reinstall over the installed OpenBook: ok and verified", rep.get("ok") and rep.get("verified"), rep.get("error"))
        i0, i1 = insp("used"), insp("reinstall")
        if i0 and i1:
            chk("reinstall", "a new disk GUID and new partition GUIDs", i0["disk_guid"] != i1["disk_guid"] and
                not {p["uuid"] for p in i0["partitions"]} & {p["uuid"] for p in i1["partitions"]}, (i0["disk_guid"], i1["disk_guid"]))
            u0 = next((p for p in i0["partitions"] if p["name"] == "userdata"), {})
            u1 = next((p for p in i1["partitions"] if p["name"] == "userdata"), {})
            chk("reinstall", "the old system's userdata is gone (its digest changed; the new one starts blank)",
                u0 and u1 and u0["digest"] != u1["digest"] and not u0["head_blank"] and u1["head_blank"],
                (u0.get("digest", "")[:12], u1.get("digest", "")[:12], i1["state"]))
    total = sum(len(v) for v in res["cases"].values())
    passed = sum(x["ok"] for v in res["cases"].values() for x in v)
    res.update(passed=passed, total=total, image=os.path.basename(a.image))
    json.dump(res, open(f"{R}/results.json", "w"), indent=1)
    with open(f"{R}/SUMMARY.md", "w") as f:
        f.write(f"# Installer end to end in QEMU/OVMF: {os.path.basename(a.image)}\n\n{passed}/{total} checks passed.\n\n"
                "| Case | Check | Result | Detail |\n|---|---|---|---|\n")
        for c, v in res["cases"].items():
            for x in v:
                f.write(f"| {c} | {x['check']} | {'PASS' if x['ok'] else 'FAIL'} | {x['detail'].replace('|', '/').replace(chr(10), ' ')[:180]} |\n")
    print(open(f"{R}/SUMMARY.md").read())
    return 0 if passed == total else 1


def avc(a):
    """SELinux denials in logs (plain or .gz: AVC sections, logcat, dmesg), grouped by source, target, class and
    permissions, enforcing (permissive=0) and permissive apart. Writes OUT.json and OUT.md."""
    import gzip
    groups = {}
    for path in a.logs:
        op = gzip.open if path.endswith(".gz") else open
        with op(path, "rt", errors="replace") as f:
            seen = set()
            for line in f:
                if "avc:" not in line or "denied" not in line:
                    continue
                m = re.search(r"denied\s+\{([^}]*)\}.*?scontext=(\S+) tcontext=(\S+) tclass=(\S+)(?: permissive=(\d))?", line)
                if not m:
                    continue
                ev = re.search(r"audit\(([\d.:]+)\)", line)
                k = (m.group(2).split(":")[2], m.group(3).split(":")[2], m.group(4), " ".join(sorted(m.group(1).split())),
                     m.group(5) or "?")
                # logcat repeats each kernel audit record (auditd and the process's own tag): count records once
                key = (k, ev.group(1) if ev else line)
                if key in seen:
                    continue
                seen.add(key)
                g = groups.setdefault(k, {"count": 0, "logs": set()})
                g["count"] += 1
                g["logs"].add(os.path.relpath(path, a.base) if a.base else path)
    rows = sorted(groups.items(), key=lambda kv: (kv[0][4] != "0", -kv[1]["count"]))
    out = [{"source": k[0], "target": k[1], "class": k[2], "perms": k[3], "permissive": k[4], "count": v["count"],
            "logs": sorted(v["logs"])} for k, v in rows]
    json.dump({"logs": a.logs, "denials": out}, open(a.out + ".json", "w"), indent=1)
    ours = [r for r in out if re.search(r"openbook", r["source"] + r["target"])]
    with open(a.out + ".md", "w") as f:
        f.write(f"# SELinux denials in {len(a.logs)} logs\n\n{sum(r['count'] for r in out if r['permissive'] == '0')} "
                f"enforcing denial records in {sum(r['permissive'] == '0' for r in out)} groups; "
                f"{len(ours)} groups involve an openbook type.\n\n| permissive | source | target | class | perms | count | logs |\n"
                "|---|---|---|---|---|---|---|\n")
        for r in out:
            f.write(f"| {r['permissive']} | {r['source']} | {r['target']} | {r['class']} | {r['perms']} | {r['count']} | "
                    f"{', '.join(r['logs'])[:160]} |\n")
    print(open(a.out + ".md").read())
    return 0


def plan_of(a):
    """The plan a live case printed (its PLAN section), for `inspect --plan`."""
    t = open(f"{a.case_dir}/serial.log", "rb").read().decode("utf-8", "replace")
    j = [x for x in json_lines(W.sections(t).get("PLAN", "")) if x.get("plan_sha256")]
    if not j:
        print(f"no plan in {a.case_dir}", file=sys.stderr)
        return 1
    json.dump(j[0], open(a.out, "w"), indent=1)
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    av = sub.add_parser("avc")
    av.add_argument("out")
    av.add_argument("logs", nargs="+")
    av.add_argument("--base")
    po = sub.add_parser("plan-of")
    po.add_argument("case_dir")
    po.add_argument("out")
    m = sub.add_parser("mkdisk")
    m.add_argument("kind", choices=["windows"])
    m.add_argument("out")
    m.add_argument("--gib", type=int, default=200)
    m.add_argument("--mark", required=True)
    e = sub.add_parser("expect")
    e.add_argument("case")
    e.add_argument("out")
    i = sub.add_parser("inspect")
    i.add_argument("disk")
    i.add_argument("out")
    i.add_argument("--plan")
    i.add_argument("--ref")
    c = sub.add_parser("check")
    c.add_argument("--run", required=True)
    c.add_argument("--disks", required=True)
    c.add_argument("--image", required=True)
    a = ap.parse_args()
    if a.cmd == "mkdisk":
        return mkdisk(a)
    if a.cmd == "expect":
        json.dump(expect(a.case), open(a.out, "w"), indent=0)
        return 0
    if a.cmd == "inspect":
        return inspect(a)
    if a.cmd == "plan-of":
        return plan_of(a)
    if a.cmd == "avc":
        return avc(a)
    return check(a)


if __name__ == "__main__":
    sys.exit(main())
