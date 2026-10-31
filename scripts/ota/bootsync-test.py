#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host tests of openbook-bootsync (ANAL-223, device/anybook/common/bootsync) on disk image files, in the
openbook-installer container. scripts/ota/bootsync-test.sh builds both binaries and runs this.

The fixture is a real whole-disk install: the install engine (host build) installs the live image onto a blank
64 GiB image file, exactly as on the G14. "update_engine" is then simulated by writing a build's boot, init_boot,
vendor_boot and vbmeta images into slot B (or A), and systemd-boot's boot counting by renaming entries with mtools.
Everything bootsync writes is read back from outside (mtools, fsck.fat), and which entry systemd-boot 262 would start
is computed here independently of bootsync (src/boot/boot.c: boot_entry_compare, config_select_default_entry).

Cases:
  installed      status on the fresh install: slot A good and in sync byte for byte with what bootsync would export
  refuse-blank   activate b with slot B blank: refused, the ESP unchanged
  refuse-corrupt one byte of vendor_boot_b changed: refused (hash descriptor), the ESP unchanged
  refuse-key     vbmeta_b signed with another key: refused; accepted with --allow-new-key
  refuse-unsigned vbmeta_b unsigned: refused
  activate       activate b: files, entry openbook-b+3.conf, loader.conf (default a, preferred b), fsck clean
  again          activate b a second time: the same ESP
  booted         systemd-boot's first try (+3 -> +2-1), then mark-good on b: openbook-b.conf, default b, A's entry gone
  rollback       B's tries used up (+0-3): A starts; mark-good on a drops the preferred line, B's entry stays (bad)
  reupdate       after the rollback, activate b again: the bad entry replaced, B preferred again
  second         from "booted" (B good), new images in slot A, activate a on b: openbook-a+3.conf, default b, preferred a
  cancel         activate b, then activate a on a: B's pending entry and the preferred line go
  disable        disable b on a after activate: entry and preferred line gone
  cut-*          activate b stopped after each write step (files, entry, loader): the ESP is consistent and starts
                 a until loader.conf is written, then b

usage: bootsync-test.py --bootsync BIN --engine BIN --image LIVE.img --run DIR [--slot-images DIR] [--alt-images DIR]
  --slot-images: boot.img, init_boot.img, vendor_boot.img, vbmeta.img of the build to "update" to (default: the
                 stick's own slot A); --alt-images: a second build for the "second" case (default: the same)
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INST = os.path.join(os.path.dirname(HERE), "installer")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ET = load("engine_test", f"{INST}/engine-test.py")
E2E = load("e2e_qemu", f"{INST}/e2e-qemu.py")
BC = load("bootconfig", f"{INST}/bootconfig.py")
MiB, GiB = 1 << 20, 1 << 30
results = {"cases": {}}
IMAGES = ("boot", "init_boot", "vendor_boot", "vbmeta")


def sh(*cmd, **kw):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)


def check(case, what, ok, detail=""):
    results["cases"].setdefault(case, []).append({"check": what, "ok": bool(ok), "detail": str(detail)[:400]})
    print(f"[{'PASS' if ok else 'FAIL'}] {case}: {what}{(' - ' + str(detail)[:300]) if detail and not ok else ''}",
          flush=True)


# ------------------------------------------------------------------------------------------- the disk
class Disk:
    def __init__(self, path):
        self.path = path
        t, _ = E2E.table_of(E2E.gpt_read(path))
        self.parts = {p["name"]: p for p in t["parts"]}
        self.esp = self.parts["EFI"]["first"] * 512
        self.esp_len = (self.parts["EFI"]["last"] - self.parts["EFI"]["first"] + 1) * 512

    def m(self, *args):
        return sh(*args[:1], "-i", f"{self.path}@@{self.esp}", *args[1:])

    def files(self, d="::/"):
        r = sh("mdir", "-/", "-b", "-i", f"{self.path}@@{self.esp}", d)
        return sorted(x[3:] for x in r.stdout.split() if x.startswith("::/") and not x.endswith("/"))

    def read(self, rel, tmp):
        if os.path.exists(tmp):
            os.remove(tmp)
        r = sh("mcopy", "-n", "-o", "-i", f"{self.path}@@{self.esp}", f"::/{rel}", tmp)
        if r.returncode:
            return None
        b = open(tmp, "rb").read()
        os.remove(tmp)
        return b

    def entries(self):
        return sorted(f.split("/")[-1] for f in self.files() if f.startswith("loader/entries/"))

    def rename(self, old, new):
        return sh("mren", "-i", f"{self.path}@@{self.esp}", f"::/loader/entries/{old}", f"::/loader/entries/{new}")

    def write_part(self, name, src):
        p = self.parts[name]
        size = (p["last"] - p["first"] + 1) * 512
        data = open(src, "rb").read()
        if len(data) > size:
            raise SystemExit(f"{src} ({len(data)} bytes) does not fit {name} ({size})")
        with open(self.path, "r+b") as f:  # the rest of the partition zeroed, as update_engine leaves it
            f.seek(p["first"] * 512)
            f.write(data)
            left = size - len(data)
            while left:
                n = min(left, 16 * MiB)
                f.write(b"\0" * n)
                left -= n

    def esp_digest(self):
        return E2E.digest(self.path, self.esp, self.esp_len)

    def fsck(self, tmp):
        return E2E.fsck_fat(self.path, self.esp, self.esp_len, tmp)


def put_slot(d, slot, images):
    for n in IMAGES:
        d.write_part(f"{n}_{slot}", f"{images}/{n}.img")


# ------------------------------------------------------------------------------------------- systemd-boot 262
def entry_id(name):
    """openbook-b+2-1.conf -> (openbook-b.conf, tries_left, tries_done); no counter -> left None."""
    m = re.match(r"^(.*?)(?:\+(\d+)(?:-(\d+))?)?\.conf$", name)
    base, left, done = m.group(1), m.group(2), m.group(3)
    return (base + ".conf").lower(), int(left) if left is not None else None, int(done or 0)


def verkey(s):
    return [(0, int(x), "") if x.isdigit() else (1, 0, x) for x in re.findall(r"\d+|\D", s)]


def sdboot_pick(d, tmp):
    """The entry systemd-boot 262 starts by itself (no EFI variables set): its file name, or None."""
    lc = (d.read("loader/loader.conf", tmp) or b"").decode()
    conf = {}
    for line in lc.splitlines():
        k, _, v = line.strip().partition(" ")
        if k:
            conf[k] = v.strip().lower()
    ents = []
    for f in d.entries():
        text = (d.read(f"loader/entries/{f}", tmp) or b"").decode()
        fields = dict((l.split(" ", 1) + [""])[:2] for l in text.splitlines() if l.strip())
        i, left, done = entry_id(f)
        ents.append({"file": f, "id": i, "left": left, "done": done, "sort": fields.get("sort-key"),
                     "version": fields.get("version", "")})
    import functools

    def vc(a, b):
        ka, kb = verkey(a), verkey(b)
        return (ka > kb) - (ka < kb)

    def cmp(a, b):
        ba, bb = a["left"] == 0, b["left"] == 0
        if ba != bb:
            return 1 if ba else -1
        if (a["sort"] is None) != (b["sort"] is None):
            return 1 if a["sort"] is None else -1
        if a["sort"] is not None:
            if a["sort"] != b["sort"]:
                return -1 if a["sort"] < b["sort"] else 1
            r = -vc(a["version"], b["version"])
            if r:
                return r
        r = -vc(a["id"], b["id"])
        if r:
            return r
        if a["left"] is None or b["left"] is None:
            return 0
        if a["left"] != b["left"]:
            return b["left"] - a["left"]
        return a["done"] - b["done"]

    ents.sort(key=functools.cmp_to_key(cmp))
    import fnmatch
    if conf.get("preferred"):
        for e in ents:
            if fnmatch.fnmatchcase(e["id"], conf["preferred"]) and e["left"] != 0:
                return e["file"]
    if conf.get("default"):
        for e in ents:
            if fnmatch.fnmatchcase(e["id"], conf["default"]):
                return e["file"]
    return ents[0]["file"] if ents else None


# ------------------------------------------------------------------------------------------- bootsync
class Sync:
    def __init__(self, binary, out):
        self.binary, self.out, self.n = binary, out, 0
        os.makedirs(out, exist_ok=True)

    def run(self, disk, cur, *args):
        self.n += 1
        r = sh(self.binary, "--json", "--disk", disk.path, "--current", cur, *args)
        tag = f"{self.n:02d}-{'-'.join(args)}-on-{cur}".replace("/", "_")
        open(f"{self.out}/{tag}.json", "w").write(r.stdout)
        open(f"{self.out}/{tag}.log", "w").write(r.stderr)
        try:
            j = json.loads(r.stdout) if r.stdout.strip() else {}
        except ValueError:
            j = {"unparsable": r.stdout[-300:]}
        return r.returncode, j


def bootconfig_of(d, slot, tmp):
    b = d.read(f"openbook/{slot}/bootconfig.img", tmp)
    return BC.parse_text(BC.read_trailer(b)) if b else {}


def vbmeta_digest(path):
    data = open(path, "rb").read()
    auth, aux = struct.unpack_from(">QQ", data, 12)
    return hashlib.sha256(data[:256 + auth + aux]).hexdigest(), 256 + auth + aux


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootsync", required=True)
    ap.add_argument("--engine", required=True)
    ap.add_argument("--image", required=True)
    ap.add_argument("--run", required=True)
    ap.add_argument("--slot-images")
    ap.add_argument("--alt-images")
    ap.add_argument("--avbtool", default=os.path.normpath(f"{ET.HOST_TOOLS}/../../../../external/avb/avbtool.py"))
    a = ap.parse_args()
    run = os.path.abspath(a.run)
    os.makedirs(run, exist_ok=True)
    tmp = f"{run}/tmp.bin"
    meta = json.load(open(a.image + ".json"))
    S = Sync(a.bootsync, f"{run}/bootsync")

    # ---------------------------------------------------------------- the fixture: a whole-disk install
    base = f"{run}/installed.img"
    stick = f"{run}/stick.img"
    if not os.path.exists(base):
        shutil.copyfile(a.image, stick)
        t = f"{run}/target.img"
        with open(t, "wb") as f:
            f.truncate(64 * GiB)
        E = ET.Engine(a.engine, ET.make_root(run, "main", stick, t), meta["esp_partuuid"], f"{run}/engine")
        target = "nvme-QEMU_NVMe_Ctrl_internal0"
        plan = f"{run}/engine/plan.json"
        rc, j, _ = E.run("plan", "--target", f"/dev/disk/by-id/{target}", "--layout", "whole", "--locale", "en-US",
                         "--keyboard", "us", "--out", plan)
        rc2, j2, _ = E.run("apply", "--plan", plan, "--confirm-disk", f"/dev/disk/by-id/{target}",
                           env={"OPENBOOK_INSTALL_ERASE": f"/dev/disk/by-id/{target}"})
        check("fixture", "the engine installs the live image onto a 64 GiB image file", rc == 0 and rc2 == 0 and
              j2.get("verified"), j2.get("error") or j.get("error"))
        if rc2:
            return 1
        os.replace(t, base)
    # the stick's own slot-A images, the default "new build"
    src = f"{run}/stick-images"
    if not os.path.isdir(src):
        os.makedirs(src)
        if not os.path.exists(stick):
            shutil.copyfile(a.image, stick)
        sd = Disk(stick)
        for n in IMAGES:
            p = sd.parts[f"{n}_a"]
            with open(stick, "rb") as f, open(f"{src}/{n}.img", "wb") as o:
                f.seek(p["first"] * 512)
                o.write(f.read((p["last"] - p["first"] + 1) * 512))
    if os.path.exists(stick):
        os.remove(stick)
    new = os.path.abspath(a.slot_images or src)
    alt = os.path.abspath(a.alt_images or new)
    new_digest, new_size = vbmeta_digest(f"{new}/vbmeta.img")

    def fresh(name):
        p = f"{run}/{name}.img"
        if os.path.exists(p):
            os.remove(p)
        r = sh("cp", "--reflink=auto", base, p)
        if r.returncode:
            raise SystemExit(r.stderr)
        return Disk(p)

    def drop(d):
        os.remove(d.path)

    def clone(src, name):
        p = f"{run}/{name}.img"
        if os.path.exists(p):
            os.remove(p)
        sh("cp", "--reflink=auto", f"{run}/{src}.img", p)
        return Disk(p)

    # ---------------------------------------------------------------- installed
    d = fresh("w")
    rc, j = S.run(d, "a", "status")
    sa, sb = j.get("slots", {}).get("a", {}), j.get("slots", {}).get("b", {})
    check("installed", "status: slot A's images verify against vbmeta_a", rc == 0 and sa.get("images_ok"), sa)
    check("installed", "status: slot A's ESP files are byte for byte what bootsync exports (kernel, both ramdisks, "
          "bootconfig)", sa.get("esp_files") == "in_sync", sa)
    check("installed", "status: slot A good, slot B blank and without an entry",
          sa.get("entry_state") == "good" and sb.get("entry_state") == "none" and not sb.get("images_ok"), sb)
    check("installed", "status: systemd-boot starts openbook-a.conf (bootsync and the independent model agree)",
          j.get("next_boot_entry") == "openbook-a.conf" == sdboot_pick(d, tmp), (j.get("next_boot_entry"), sdboot_pick(d, tmp)))
    installed_lc = d.read("loader/loader.conf", tmp)
    check("installed", "loader.conf as the installer wrote it", installed_lc and b"default openbook-a.conf" in installed_lc,
          installed_lc)

    # ---------------------------------------------------------------- refusals
    before = d.esp_digest()
    rc, j = S.run(d, "a", "activate", "b")
    check("refuse-blank", "activate b with slot B blank: refused", rc == 1 and j.get("code") == "slot_not_ready", j)
    check("refuse-blank", "the ESP is unchanged", d.esp_digest() == before)
    put_slot(d, "b", new)
    p = d.parts["vendor_boot_b"]
    with open(d.path, "r+b") as f:
        f.seek(p["first"] * 512 + 4096 + 100)
        c = f.read(1)
        f.seek(-1, 1)
        f.write(bytes([c[0] ^ 0xFF]))
    rc, j = S.run(d, "a", "activate", "b")
    check("refuse-corrupt", "one byte of vendor_boot_b changed: refused (hash descriptor)",
          rc == 1 and j.get("code") == "slot_not_ready" and "vendor_boot_b" in j.get("error", ""), j)
    check("refuse-corrupt", "the ESP is unchanged", d.esp_digest() == before)
    drop(d)
    # another key, and no signature
    keys = os.path.normpath(f"{ET.HOST_TOOLS}/../../../../external/avb/test/data")
    for case, args in (("refuse-key", ["--key", f"{keys}/testkey_rsa2048.pem", "--algorithm", "SHA256_RSA2048"]),
                       ("refuse-unsigned", [])):
        d = fresh("w")
        put_slot(d, "b", new)
        vb = f"{run}/vbmeta-{case}.img"
        r = sh("python3", a.avbtool, "make_vbmeta_image", "--output", vb, "--include_descriptors_from_image",
               f"{new}/vbmeta.img", "--padding_size", "4096", *args)
        if r.returncode:
            check(case, "avbtool made the test vbmeta", False, r.stderr[-300:])
            drop(d)
            continue
        d.write_part("vbmeta_b", vb)
        before = d.esp_digest()
        rc, j = S.run(d, "a", "activate", "b")
        want = "key_changed" if case == "refuse-key" else "unsigned"
        check(case, f"activate b: refused ({want})", rc == 1 and j.get("code") == want, j)
        check(case, "the ESP is unchanged", d.esp_digest() == before)
        if case == "refuse-key":
            rc, j = S.run(d, "a", "--allow-new-key", "activate", "b")
            check(case, "with --allow-new-key: accepted", rc == 0 and j.get("ok"), j)
        drop(d)

    # ---------------------------------------------------------------- activate
    d = fresh("act")
    put_slot(d, "b", new)
    rc, j = S.run(d, "a", "activate", "b")
    check("activate", "activate b succeeds", rc == 0 and j.get("ok"), j.get("error"))
    ents = d.entries()
    check("activate", "entries: openbook-a.conf and openbook-b+3.conf", ents == ["openbook-a.conf", "openbook-b+3.conf"], ents)
    lc = (d.read("loader/loader.conf", tmp) or b"").decode()
    check("activate", "loader.conf: default openbook-a.conf, preferred openbook-b.conf, the installer's other lines kept",
          lc == "timeout menu-hidden\nconsole-mode keep\neditor no\ndefault openbook-a.conf\npreferred openbook-b.conf\n", lc)
    bca, bcb = bootconfig_of(d, "a", tmp), bootconfig_of(d, "b", tmp)
    check("activate", "B's bootconfig: slot _b, vbmeta_b's digest and size",
          bcb.get("androidboot.slot_suffix") == "_b" and bcb.get("androidboot.vbmeta.digest") == new_digest and
          bcb.get("androidboot.vbmeta.size") == str(new_size), {k: bcb.get(k) for k in ("androidboot.slot_suffix", "androidboot.vbmeta.digest")})
    same = {k: v for k, v in bca.items() if k not in ("androidboot.slot_suffix", "androidboot.vbmeta.digest", "androidboot.vbmeta.size")}
    check("activate", "B's bootconfig keeps the install's own values (serial, boot_part_uuid, locale, installed)",
          all(bcb.get(k) == v for k, v in same.items() if not k.startswith("androidboot.hardware")) and
          bcb.get("androidboot.serialno") == bca.get("androidboot.serialno") and
          bcb.get("androidboot.boot_part_uuid") == bca.get("androidboot.boot_part_uuid"),
          {k: (v, bcb.get(k)) for k, v in same.items() if bcb.get(k) != v})
    ent = (d.read("loader/entries/openbook-b+3.conf", tmp) or b"").decode()
    enta = (d.read("loader/entries/openbook-a.conf", tmp) or b"").decode()
    check("activate", "the entry: slot B's files, bootconfig last, version 'slot B', A's options",
          "linux /openbook/b/kernel\n" in ent and ent.index("vendor_ramdisk.img") < ent.index("/ramdisk.img") <
          ent.index("bootconfig.img") and "slot B" in ent and
          re.search(r"^options .*$", ent, re.M).group(0) == re.search(r"^options .*$", enta, re.M).group(0), ent)
    k = d.read("openbook/b/kernel", tmp)
    with open(f"{new}/boot.img", "rb") as f:
        hdr = f.read(4096)
        ks = struct.unpack_from("<I", hdr, 8)[0]
        kern = f.read(ks)
    check("activate", "openbook/b/kernel is boot_b's kernel", k == kern, len(k or b""))
    fs = d.fsck(tmp)
    check("activate", "fsck.fat: clean", fs["rc"] == 0, fs)
    check("activate", "systemd-boot starts openbook-b+3.conf (bootsync and the independent model agree)",
          j.get("next_boot_entry") == "openbook-b+3.conf" == sdboot_pick(d, tmp), (j.get("next_boot_entry"), sdboot_pick(d, tmp)))
    rc, j = S.run(d, "a", "status")
    check("activate", "status: slot B in sync, pending", j.get("slots", {}).get("b", {}).get("esp_files") == "in_sync" and
          j["slots"]["b"].get("entry_state") == "pending", j.get("slots", {}).get("b"))
    act_digest = d.esp_digest()
    files_act = {f: hashlib.sha256(d.read(f, tmp) or b"").hexdigest() for f in d.files()}
    rc, j = S.run(d, "a", "activate", "b")
    files_again = {f: hashlib.sha256(d.read(f, tmp) or b"").hexdigest() for f in d.files()}
    check("again", "activate b a second time: succeeds, the same files and contents", rc == 0 and files_again == files_act,
          set(files_again.items()) ^ set(files_act.items()))
    fs = d.fsck(tmp)
    check("again", "fsck.fat: clean", fs["rc"] == 0, fs)
    sh("cp", "--reflink=auto", d.path, f"{run}/activated.img")

    # ---------------------------------------------------------------- booted: systemd-boot's try, then mark-good on b
    r = d.rename("openbook-b+3.conf", "openbook-b+2-1.conf")
    check("booted", "systemd-boot's first try renames the entry (+3 -> +2-1; mren stands in)", r.returncode == 0, r.stderr)
    rc, j = S.run(d, "b", "mark-good")
    check("booted", "mark-good on b succeeds, after_update", rc == 0 and j.get("after_update"), j.get("error"))
    ents = d.entries()
    check("booted", "entries: openbook-b.conf only (A's goes: the merge overwrites slot A)", ents == ["openbook-b.conf"], ents)
    lc = (d.read("loader/loader.conf", tmp) or b"").decode()
    check("booted", "loader.conf: default openbook-b.conf, no preferred line", "default openbook-b.conf\n" in lc and
          "preferred" not in lc, lc)
    check("booted", "systemd-boot starts openbook-b.conf", sdboot_pick(d, tmp) == "openbook-b.conf" ==
          j.get("next_boot_entry"), sdboot_pick(d, tmp))
    fs = d.fsck(tmp)
    check("booted", "fsck.fat: clean", fs["rc"] == 0, fs)
    before = d.esp_digest()
    rc, j = S.run(d, "b", "mark-good")
    check("booted", "mark-good again (every boot): nothing written", rc == 0 and not j.get("after_update") and
          d.esp_digest() == before, j)
    sh("cp", "--reflink=auto", d.path, f"{run}/booted.img")

    # ---------------------------------------------------------------- second update: B -> A
    put_slot(d, "a", alt)
    rc, j = S.run(d, "b", "activate", "a")
    check("second", "activate a on b succeeds", rc == 0 and j.get("ok"), j.get("error"))
    ents = d.entries()
    check("second", "entries: openbook-a+3.conf, openbook-b.conf", ents == ["openbook-a+3.conf", "openbook-b.conf"], ents)
    lc = (d.read("loader/loader.conf", tmp) or b"").decode()
    check("second", "loader.conf: default openbook-b.conf, preferred openbook-a.conf",
          "default openbook-b.conf\n" in lc and "preferred openbook-a.conf\n" in lc, lc)
    check("second", "systemd-boot starts openbook-a+3.conf", sdboot_pick(d, tmp) == "openbook-a+3.conf", sdboot_pick(d, tmp))
    bca = bootconfig_of(d, "a", tmp)
    check("second", "A's bootconfig: slot _a, the A build's vbmeta digest", bca.get("androidboot.slot_suffix") == "_a" and
          bca.get("androidboot.vbmeta.digest") == vbmeta_digest(f"{alt}/vbmeta.img")[0], bca.get("androidboot.vbmeta.digest"))
    d.rename("openbook-a+3.conf", "openbook-a+2-1.conf")
    rc, j = S.run(d, "a", "mark-good")
    check("second", "A boots, mark-good on a: openbook-a.conf only, default a", rc == 0 and d.entries() == ["openbook-a.conf"]
          and "default openbook-a.conf" in (d.read("loader/loader.conf", tmp) or b"").decode(), d.entries())
    fs = d.fsck(tmp)
    check("second", "fsck.fat: clean", fs["rc"] == 0, fs)
    drop(d)

    # ---------------------------------------------------------------- rollback: B's tries used up
    d = clone("activated", "rb")
    for old, newn in (("openbook-b+3.conf", "openbook-b+2-1.conf"), ("openbook-b+2-1.conf", "openbook-b+1-2.conf"),
                      ("openbook-b+1-2.conf", "openbook-b+0-3.conf")):
        d.rename(old, newn)
    check("rollback", "after three failed tries (+0-3) systemd-boot starts openbook-a.conf",
          sdboot_pick(d, tmp) == "openbook-a.conf", sdboot_pick(d, tmp))
    rc, j = S.run(d, "a", "status")
    check("rollback", "status on a: next boot a, B bad", j.get("next_boot_slot") == "a" and
          j.get("slots", {}).get("b", {}).get("entry_state") == "bad", j.get("entries"))
    rc, j = S.run(d, "a", "mark-good")
    lc = (d.read("loader/loader.conf", tmp) or b"").decode()
    check("rollback", "mark-good on a: the preferred line goes, default a, B's bad entry stays",
          rc == 0 and "preferred" not in lc and "default openbook-a.conf" in lc and
          d.entries() == ["openbook-a.conf", "openbook-b+0-3.conf"], (lc, d.entries()))
    check("rollback", "mark-good on a reports next boot a (the HAL resets misc to it)", j.get("next_boot_slot") == "a", j)
    rc, j = S.run(d, "a", "activate", "b")
    check("reupdate", "activate b again after the rollback: the bad entry replaced by openbook-b+3.conf",
          rc == 0 and d.entries() == ["openbook-a.conf", "openbook-b+3.conf"] and
          sdboot_pick(d, tmp) == "openbook-b+3.conf", d.entries())
    fs = d.fsck(tmp)
    check("reupdate", "fsck.fat: clean", fs["rc"] == 0, fs)
    drop(d)

    # ---------------------------------------------------------------- cancel and disable
    for case, cmd in (("cancel", ["activate", "a"]), ("disable", ["disable", "b"])):
        d = clone("activated", case)
        rc, j = S.run(d, "a", *cmd)
        lc = (d.read("loader/loader.conf", tmp) or b"").decode()
        check(case, f"{' '.join(cmd)} on a: B's entry and the preferred line go, A starts",
              rc == 0 and d.entries() == ["openbook-a.conf"] and "preferred" not in lc and
              sdboot_pick(d, tmp) == "openbook-a.conf", (d.entries(), lc))
        drop(d)
    d = clone("activated", "disable-cur")
    before = d.esp_digest()
    rc, j = S.run(d, "a", "disable", "a")
    check("disable", "disable a on a (the running slot): nothing changes", rc == 0 and d.esp_digest() == before, j)
    drop(d)

    # ---------------------------------------------------------------- cuts between the write steps
    for stop, want in (("files", "openbook-a.conf"), ("entry", "openbook-a.conf"), ("loader", "openbook-b+3.conf")):
        d = fresh(f"cut-{stop}")
        put_slot(d, "b", new)
        rc, j = S.run(d, "a", "--test-stop-after", stop, "activate", "b")
        fs = d.fsck(tmp)
        check(f"cut-{stop}", f"stopped after '{stop}': fsck.fat clean, systemd-boot starts {want}",
              rc == 75 and fs["rc"] == 0 and sdboot_pick(d, tmp) == want, (rc, fs, sdboot_pick(d, tmp)))
        rc, j = S.run(d, "a", "activate", "b")
        check(f"cut-{stop}", "activate b again from that state completes",
              rc == 0 and sdboot_pick(d, tmp) == "openbook-b+3.conf", j.get("error"))
        drop(d)

    for f in ("w.img", "activated.img", "booted.img", "tmp.bin"):
        if os.path.exists(f"{run}/{f}"):
            os.remove(f"{run}/{f}")
    total = sum(len(v) for v in results["cases"].values())
    passed = sum(x["ok"] for v in results["cases"].values() for x in v)
    results.update(passed=passed, total=total, image=os.path.basename(a.image), slot_images=new, alt_images=alt)
    json.dump(results, open(f"{run}/results.json", "w"), indent=1)
    with open(f"{run}/SUMMARY.md", "w") as f:
        f.write(f"# openbook-bootsync host tests ({os.path.basename(a.image)})\n\n{passed}/{total} checks passed.\n\n"
                "| Case | Check | Result | Detail |\n|---|---|---|---|\n")
        for c, v in results["cases"].items():
            for x in v:
                f.write(f"| {c} | {x['check']} | {'PASS' if x['ok'] else 'FAIL'} | "
                        f"{x['detail'].replace('|', '/')[:120] if not x['ok'] else ''} |\n")
    print(f"{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
