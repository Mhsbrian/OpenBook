#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host tests of the install engine's bring-your-own GApps step (ANAL-211: device/anybook/common/installer/engine
gapps.c, product.c, erofs.c, avb.c, lp.c), on image files, with the fixtures of scripts/installer/engine-test.py: a
live image is the stick, sparse files are the targets. Only the synthetic packages of scripts/gapps/make-synthetic.py
are used; no Google software.

  check          gapps-check on every package: the three encodings of the reference package are accepted, their
                 staged files match the sources, and the manifest records each app's package, version and signer as
                 apksigner prints it; every negative package is refused with the expected rule
  same-install   without the step, installs are byte-identical to main's: a plan from this engine has no package key,
                 operation or file; main's engine accepts it (its own re-computation gives the same plan sha256); and
                 the disks main's and this engine install from that plan are identical (every partition's content;
                 the EFI partition's files except the install logs)
  plan-gapps     a plan with --gapps: the package and product sections, the check_gapps, product and vbmeta
                 operations, the uncertified warning, the bootconfig marked after_product; the target only read
  apply-gapps    the whole-disk install verifies; then, from outside the engine:
                 super (lpdump): product_a moved to one new extent, every other partition where it was;
                 product (avbtool): footer and hashtree descriptor, no FEC; avbtool verify_image recomputes its
                 hashtree; avbtool add_hashtree_footer over the same image and salt gives the same root digest and tree;
                 EROFS (fsck.erofs --extract): every file of the stick's product unchanged, every package file and
                 the install manifest present and identical; every new inode root-owned, 0644/0755, labeled
                 u:object_r:system_file:s0 (read from the image's xattrs);
                 vbmeta_a: unsigned, product's descriptor = the footer's, every other descriptor as on the stick,
                 avbtool calculate_vbmeta_digest = the bootconfig's androidboot.vbmeta.digest, size likewise;
                 every other logical partition byte-identical to the stick's
  scale          a package with a 256 MiB app: check, install and avbtool verify_image, with timings
  refuse-*       an unknown package sha256 (no_gapps), a package that adds a file the image has (gapps_clash), an
                 unconfirmed step (gapps_not_confirmed), and a staged file changed after the plan (apply fails in
                 check_source; the target is untouched)

usage: engine-gapps-test.py --engine BIN --main BIN --image LIVE.img --packages DIR --apks DIR --run DIR
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
spec = importlib.util.spec_from_file_location("enginetest", os.path.join(HERE, "../installer/engine-test.py"))
et = importlib.util.module_from_spec(spec)
spec.loader.exec_module(et)
sh, sha_file, check, Engine, make_root, results = et.sh, et.sha_file, et.check, et.Engine, et.make_root, et.results
GiB, MiB, HOST = et.GiB, et.MiB, et.HOST_TOOLS
SDK_ENV = {"OPENBOOK_PROP_ro_build_version_sdk": "37"}
REF = "openbook-synthetic-gapps-x86_64-37"


def blank(path, gib):
    if os.path.exists(path):
        os.remove(path)
    with open(path, "wb") as f:
        f.truncate(gib * GiB)
    return path


def content_digest(path, start=0, length=None):
    """sha256 over (offset, bytes) of every non-zero 64 KiB chunk in [start, start+length): holes and written zeros
    compare equal, as e2e-qemu.py's partition digests."""
    size = os.path.getsize(path)
    end = size if length is None else min(size, start + length)
    h = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY)
    try:
        pos = start
        while pos < end:
            try:
                pos = os.lseek(fd, pos, os.SEEK_DATA)
            except OSError:
                break
            if pos >= end:
                break
            hole = min(os.lseek(fd, pos, os.SEEK_HOLE), end)
            p = pos - (pos - start) % 65536
            while p < hole:
                os.lseek(fd, p, os.SEEK_SET)
                b = os.read(fd, min(65536, end - p))
                if b.strip(b"\0"):
                    h.update(struct.pack("<Q", p - start) + b)
                p += 65536
            pos = hole
    finally:
        os.close(fd)
    return h.hexdigest()


def extract(img, off, n, dest):
    with open(img, "rb") as s, open(dest, "wb") as d:
        s.seek(off)
        left = n
        while left:
            b = s.read(min(left, 16 * MiB))
            if not b:
                break
            d.write(b)
            left -= len(b)


class Erofs:
    """Just enough EROFS to read inodes, directories and xattrs (external/erofs-utils/include/erofs_fs.h)."""

    def __init__(self, path):
        self.f = open(path, "rb")
        sb = self.read(1024, 128)
        assert struct.unpack_from("<I", sb)[0] == 0xE0F5E1E2
        self.root = struct.unpack_from("<H", sb, 14)[0]
        self.blocks, self.meta, self.xattr = struct.unpack_from("<III", sb, 36)

    def read(self, off, n):
        self.f.seek(off)
        return self.f.read(n)

    def inode(self, nid):
        pos = self.meta * 4096 + nid * 32
        b = self.read(pos, 64 + 256)
        fmt, xic, mode = struct.unpack_from("<HHH", b)
        ext = fmt & 1
        if ext:
            size, raw, ino, uid, gid = struct.unpack_from("<QIIII", b, 8)
            nlink = struct.unpack_from("<I", b, 44)[0]
        else:
            nlink, size, _, raw, ino, uid, gid = struct.unpack_from("<HIIIIHH", b, 6)
        isz = 64 if ext else 32
        xs = 12 + 4 * (xic - 1) if xic else 0
        return {"pos": pos, "layout": (fmt >> 1) & 7, "mode": mode, "size": size, "raw": raw, "uid": uid, "gid": gid,
                "nlink": nlink, "isize": isz, "xsize": xs, "ibody": b[isz:isz + xs]}

    def xattrs(self, ino):
        out, body = {}, ino["ibody"]
        if not body:
            return out
        shared = body[4]
        prefixes = {1: "user.", 4: "trusted.", 6: "security."}

        def entry(buf, at):
            nl, idx, vs = struct.unpack_from("<BBH", buf, at)
            name = prefixes.get(idx, f"[{idx}].") + buf[at + 4:at + 4 + nl].decode()
            return name, buf[at + 4 + nl:at + 4 + nl + vs], (4 + nl + vs + 3) // 4 * 4
        for k in range(shared):
            sid = struct.unpack_from("<I", body, 12 + 4 * k)[0]
            buf = self.read(self.xattr * 4096 + sid * 4, 4 + 255 + 65536)
            n, v, _ = entry(buf, 0)
            out[n] = v
        at = 12 + 4 * shared
        while at + 4 <= len(body):
            n, v, step = entry(body, at)
            out[n] = v
            at += step
        return out

    def dir_data(self, ino):
        if ino["layout"] == 0:
            return self.read(ino["raw"] * 4096, ino["size"])
        full = ino["size"] // 4096 * 4096
        return self.read(ino["raw"] * 4096, full) + self.read(ino["pos"] + ino["isize"] + ino["xsize"],
                                                              ino["size"] - full)

    def entries(self, ino):
        d, out = self.dir_data(ino), []
        for b in range(0, len(d), 4096):
            blk = d[b:b + 4096]
            first = struct.unpack_from("<H", blk, 8)[0]
            n = first // 12
            for j in range(n):
                nid, no, ft = struct.unpack_from("<QHB", blk, 12 * j)
                ne = struct.unpack_from("<H", blk, 12 * (j + 1) + 8)[0] if j + 1 < n else len(blk)
                out.append((blk[no:ne].rstrip(b"\0").decode(), nid, ft))
        return out

    def lookup(self, path):
        nid = self.root
        for comp in [c for c in path.split("/") if c]:
            ents = {n: x for n, x, _ in self.entries(self.inode(nid))}
            if comp not in ents:
                return None
            nid = ents[comp]
        return nid


def avb_info(img):
    r = sh(f"{HOST}/avbtool", "info_image", "--image", img)
    return r.stdout + r.stderr


def ht_block(info, part):
    """The hashtree descriptor of partition part from avbtool info_image's text."""
    for m in re.finditer(r"Hashtree descriptor:\n((?:      .*\n)+)", info):
        f = dict(re.findall(r"^\s+([A-Za-z ]+?):\s+(.*)$", m.group(1), re.M))
        if f.get("Partition Name") == part:
            return f
    return {}


def walk(d):
    out = {}
    for root, _, files in os.walk(d):
        for n in files:
            p = os.path.join(root, n)
            out[os.path.relpath(p, d)] = "link:" + os.readlink(p) if os.path.islink(p) else sha_file(p)
    return out


def main():
    ap = argparse.ArgumentParser()
    for k in ("engine", "main", "image", "packages", "apks", "run"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    run = os.path.abspath(a.run)
    os.makedirs(run, exist_ok=True)
    meta = json.load(open(a.image + ".json"))
    uuid = meta["esp_partuuid"]
    stick = f"{run}/stick.img"
    if not os.path.exists(stick):
        subprocess.run(["cp", "--reflink=auto", a.image, stick], check=True)
    esp = next(p for p in meta["partitions"] if p["name"] == "EFI")
    sh("mcopy", "-n", "-o", "-i", f"{stick}@@{esp['start'] * 512}", "::/openbook/MANIFEST.json", f"{run}/MANIFEST.json")
    man = json.load(open(f"{run}/MANIFEST.json"))
    inst = man["install"]
    expected = json.load(open(f"{a.packages}/EXPECTED.json"))
    target = "nvme-QEMU_NVMe_Ctrl_internal0"
    erase = {"OPENBOOK_INSTALL_ERASE": f"/dev/disk/by-id/{target}", **SDK_ENV}

    def engine(binary, name, tgt, serial="internal0"):
        e = Engine(binary, make_root(run, name, stick, tgt, target_serial=serial), uuid, f"{run}/{name}")
        orig = e.run
        e.run = lambda *args, env=None: orig(*args, env={**SDK_ENV, **(env or {})})
        return e

    # ---------------------------------------------------------------- check
    t0 = blank(f"{run}/target-check.img", 64)
    E = engine(a.engine, "check", t0)
    certs = open(f"{a.apks}/certs.txt").read()
    want_cert = re.search(r"OpenBookTestPriv.apk\n.*DN: (.*)\n.*SHA-256 digest: ([0-9a-f]{64})", certs)
    for variant in ("", "-xz", "-tar"):
        rc, j, _ = E.run("gapps-check", "--package", f"{a.packages}/{REF}{variant}.zip")
        g = j.get("gapps", {})
        check("check", f"{REF}{variant}.zip: accepted", rc == 0 and j.get("ok"), j.get("error"))
        files = {f["path"]: f for f in g.get("files", [])}
        check("check", f"{REF}{variant}: the 7 files, each with the source's sha256",
              {p: f["sha256"] for p, f in files.items()} == expected["files"], sorted(files))
        apps = {x["package"]: x for x in g.get("apps", [])}
        check("check", f"{REF}{variant}: three apps, privileged where in priv-app/, x86_64 code where they have code",
              set(apps) == {"com.google.android.gsf", "org.openbook.test.gapps.priv", "org.openbook.test.gapps.app"} and
              apps["org.openbook.test.gapps.priv"]["privileged"] and not apps["org.openbook.test.gapps.app"]["privileged"]
              and apps["org.openbook.test.gapps.priv"]["native"] == "x86_64", list(apps))
        p = apps.get("org.openbook.test.gapps.priv", {})
        check("check", f"{REF}{variant}: version, SDK levels and signer as aapt2 and apksigner report them",
              p.get("version_code") == 211 and p.get("version_name") == "1.0-anal211-synthetic" and
              p.get("min_sdk") == 30 and p.get("target_sdk") == 36 and want_cert and
              p.get("signer_sha256") == want_cert.group(2) and p.get("signer") == want_cert.group(1).strip() and
              p.get("signing_scheme") == "v3", {k: p.get(k) for k in ("version_code", "signer_sha256", "signer")})
        stage = f"{run}/roots/check/data/misc/openbook_install/gapps/{j.get('gapps_sha256')}"
        staged = {f["path"]: sha_file(f"{stage}/{f['stage']}") for f in g.get("files", [])}
        check("check", f"{REF}{variant}: staged files on disk match the manifest, which is staged by its sha256",
              staged == expected["files"] and os.path.exists(f"{stage}/gapps.json") and
              sha_file(f"{stage}/gapps.json") == j.get("gapps_sha256"))
    for name, rule in sorted(expected["expected"].items()):
        rc, j, _ = E.run("gapps-check", "--package", f"{a.packages}/{name}.zip")
        rules = {x["rule"] for x in j.get("refused", [])}
        if rule.startswith("plan:"):
            check("check", f"{name}: passes the check (refused later, at plan: {rule[5:]})", rc == 0 and j.get("ok"),
                  j.get("error"))
        elif rule.startswith("code:"):
            check("check", f"{name}: refused ({rule[5:]})", rc != 0 and j.get("code") == rule[5:], j.get("error"))
        else:
            check("check", f"{name}: refused ({rule})", rc != 0 and j.get("code") == "refused" and rule in rules,
                  (j.get("code"), sorted(rules), j.get("error")))
    check("check", "a refused package leaves nothing staged",
          not [d for d in os.listdir(f"{run}/roots/check/data/misc/openbook_install/gapps") if d.startswith("check-")])

    # ---------------------------------------------------------------- same-install
    t1 = blank(f"{run}/target-main.img", 64)
    t2 = blank(f"{run}/target-this.img", 64)
    Em, Et = engine(a.main, "same-main", t1), engine(a.engine, "same-this", t2)
    p0 = f"{run}/same-this/plan.json"
    rc, j, _ = Et.run("plan", "--target", target, "--layout", "whole", "--locale", "en-US", "--keyboard", "us", "--out", p0)
    plan0 = j
    check("same-install", "plan without a package succeeds", rc == 0 and j.get("plan_sha256"), j.get("error"))
    txt = open(p0).read()
    check("same-install", "the plan has no package key, operation, section or file",
          "gapps" not in txt and "product_a" not in txt and "after_product" not in txt and
          "vbmeta_rebuilt" not in txt)
    rcm, jm, _ = Em.run("apply", "--plan", p0, "--confirm-disk", f"/dev/disk/by-id/{target}", env=erase)
    check("same-install", "main's engine accepts this engine's plan (same plan sha256) and installs it",
          rcm == 0 and jm.get("ok") and jm.get("plan_sha256") == plan0.get("plan_sha256"), jm.get("error"))
    rct, jt, _ = Et.run("apply", "--plan", p0, "--confirm-disk", f"/dev/disk/by-id/{target}", env=erase)
    check("same-install", "this engine installs the same plan", rct == 0 and jt.get("ok"), jt.get("error"))
    same = []
    for p in plan0.get("partitions", []):
        if p["name"] == "EFI":
            continue
        same.append((p["name"], content_digest(t1, p["start"], p["bytes"]) == content_digest(t2, p["start"], p["bytes"])))
    check("same-install", "every partition but EFI identical (content digest)", same and all(x for _, x in same), same)
    check("same-install", "partition tables identical (first and last MiB)",
          sha_file(t1, MiB, 0) == sha_file(t2, MiB, 0) and
          sha_file(t1, MiB, os.path.getsize(t1) - MiB) == sha_file(t2, MiB, os.path.getsize(t2) - MiB))
    pe = next(p for p in plan0["partitions"] if p["name"] == "EFI")
    efis = []
    for tg, nm in ((t1, "main"), (t2, "this")):
        d = f"{run}/same-{nm}/esp"
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
        sh("mcopy", "-s", "-n", "-i", f"{tg}@@{pe['start']}", "::/", d)
        efis.append({k: v for k, v in walk(d).items() if not k.startswith("openbook/logs/")})
    check("same-install", "EFI partitions hold the same files, byte for byte (install logs aside)",
          efis[0] and efis[0] == efis[1], (len(efis[0]), len(efis[1])))

    # ---------------------------------------------------------------- plan-gapps
    t3 = blank(f"{run}/target-gapps.img", 64)
    G = engine(a.engine, "gapps", t3)
    rc, j, _ = G.run("gapps-check", "--package", f"{a.packages}/{REF}.zip")
    gsha = j.get("gapps_sha256", "")
    staged_manifest = json.dumps(j.get("gapps"), separators=(",", ":"))
    before = content_digest(t3)
    pg = f"{run}/gapps/plan.json"
    rc, j, _ = G.run("plan", "--target", target, "--layout", "whole", "--locale", "en-US", "--gapps", gsha, "--out", pg)
    planG = j
    check("plan-gapps", "plan with the package succeeds", rc == 0 and j.get("plan_sha256"), j.get("error"))
    ops = [o["op"] for o in j.get("operations", [])]
    check("plan-gapps", "operations: check_source, check_gapps, ..., super, product, ..., vbmeta",
          ops[:2] == ["check_source", "check_gapps"] and "product" in ops and "vbmeta" in ops and
          ops.index("super") < ops.index("product"), ops)
    rq = j.get("request", {})
    check("plan-gapps", "request names the package and its confirmation",
          rq.get("gapps") == gsha and rq.get("gapps_confirmed") is True, rq)
    pr = j.get("product", {})
    check("plan-gapps", "product section: product_a grows and moves; no FEC; unsigned vbmeta",
          pr.get("partition") == "product_a" and pr.get("bytes", 0) > pr.get("stick_bytes", 1) - 4 * MiB and
          pr.get("fec_roots") == 0 and pr.get("vbmeta") == "unsigned" and
          pr.get("super_offset", 0) > pr.get("super_offset_before", 0), pr)
    ga = j.get("gapps", {})
    check("plan-gapps", "gapps section: the package, 7 files, 3 apps with their signers",
          ga.get("manifest_sha256") == gsha and ga.get("files") == 7 and len(ga.get("apps", [])) == 3 and
          all(x.get("signer_sha256") for x in ga.get("apps", [])), ga.get("package"))
    check("plan-gapps", "warnings: gapps_uncertified (and the image's privapp allowlist is not enforced)",
          "gapps_uncertified" in j.get("warnings", []) and "privapp_allowlist_not_enforced" in j.get("warnings", []),
          j.get("warnings"))
    bcf = [f for f in j.get("files", []) if f["path"] == "openbook/a/bootconfig.img"]
    check("plan-gapps", "the bootconfig is written after product is built (no sha256 in the plan yet)",
          bcf and bcf[0].get("after_product") and bcf[0].get("sha256") is None, bcf)
    vb = [p for p in j.get("partitions", []) if p["name"] == "vbmeta_a"]
    check("plan-gapps", "vbmeta_a: rebuilt", vb and vb[0]["content"] == "vbmeta_rebuilt", vb)
    check("plan-gapps", "the target was only read", content_digest(t3) == before)

    # ---------------------------------------------------------------- refusals at plan and apply
    rc, j, _ = G.run("plan", "--target", target, "--layout", "whole", "--gapps", "0" * 64)
    check("refuse-unknown", "an unknown package sha256: refused (no_gapps)", rc != 0 and j.get("code") == "no_gapps",
          j.get("code"))
    Ec = engine(a.engine, "refuse-clash", blank(f"{run}/target-clash.img", 64))
    rc, j, _ = Ec.run("gapps-check", "--package", f"{a.packages}/neg-clash.zip")
    rc, j, _ = Ec.run("plan", "--target", target, "--layout", "whole", "--gapps", j.get("gapps_sha256", ""))
    check("refuse-clash", "a package that adds a file the image has: refused (gapps_clash)",
          rc != 0 and j.get("code") == "gapps_clash" and "com.android.contacts.xml" in j.get("error", ""), j.get("error"))
    pj = json.load(open(pg))
    pj["request"]["gapps_confirmed"] = False
    pu = f"{run}/gapps/plan-unconfirmed.json"
    json.dump(pj, open(pu, "w"))
    rc, j, _ = G.run("apply", "--plan", pu, "--confirm-disk", f"/dev/disk/by-id/{target}", env=erase)
    check("refuse-unconfirmed", "an unconfirmed package step: refused (gapps_not_confirmed), target unchanged",
          rc != 0 and j.get("code") == "gapps_not_confirmed" and content_digest(t3) == before, j.get("code"))
    # a staged file changed after the plan: check_source fails, nothing written
    Es = engine(a.engine, "refuse-staged", blank(f"{run}/target-staged.img", 64))
    rc, j, _ = Es.run("gapps-check", "--package", f"{a.packages}/{REF}.zip")
    s2 = j.get("gapps_sha256", "")
    ps = f"{run}/refuse-staged/plan.json"
    Es.run("plan", "--target", target, "--layout", "whole", "--gapps", s2, "--out", ps)
    sdir = f"{run}/roots/refuse-staged/data/misc/openbook_install/gapps/{s2}"
    victim = next(f for f in j["gapps"]["files"] if f["path"].endswith("OpenBookTestPriv.apk"))
    with open(f"{sdir}/{victim['stage']}", "r+b") as f:
        f.seek(100)
        f.write(b"X")
    tsb = content_digest(f"{run}/target-staged.img")
    rc, j, _ = Es.run("apply", "--plan", ps, "--confirm-disk", f"/dev/disk/by-id/{target}", env=erase)
    check("refuse-staged", "a staged file changed after the plan: apply fails in check_source",
          rc != 0 and j.get("failed_step") == "check_source" and "OpenBookTestPriv.apk" in (j.get("error") or ""),
          (j.get("failed_step"), j.get("error")))
    check("refuse-staged", "nothing written to the target", content_digest(f"{run}/target-staged.img") == tsb)

    # ---------------------------------------------------------------- apply-gapps
    G.out = f"{run}/gapps/apply"
    os.makedirs(G.out, exist_ok=True)
    rc, j, r = G.run("apply", "--plan", pg, "--confirm-disk", f"/dev/disk/by-id/{target}", "--events", env=erase)
    res = j
    check("apply-gapps", "apply with the package succeeds and verifies", rc == 0 and j.get("ok") and j.get("verified"),
          j.get("error"))
    rg = j.get("gapps", {})
    check("apply-gapps", "report: root digest, vbmeta digest, product sha256",
          rg.get("root_digest") and rg.get("vbmeta_digest") and rg.get("product_sha256"), rg)
    items = {v["what"]: v for v in j.get("verified_items", [])}
    check("apply-gapps", "verified items include the rebuilt product and vbmeta_a",
          items.get("super:product_a (with the package)", {}).get("ok") and items.get("vbmeta_a (rebuilt)", {}).get("ok"),
          sorted(items))
    planned = {p["name"]: p for p in planG["partitions"]}
    sp = planned["super"]
    w = f"{run}/gapps/out"
    os.makedirs(w, exist_ok=True)
    head = f"{w}/super-head.img"
    extract(t3, sp["start"], MiB, head)
    os.truncate(head, sp["bytes"])
    lp = sh(f"{HOST}/lpdump", head)
    open(f"{w}/lpdump.txt", "w").write(lp.stdout + lp.stderr)
    got = {m.group(3): (int(m.group(1)) * 512, int(m.group(4)) * 512) for m in
           re.finditer(r"super: (\d+) \.\. (\d+): (\S+) \((\d+) sectors\)", lp.stdout)}
    ext = {e["name"]: e for e in inst["super"]["extents"]}
    others = all(got.get(n, (None,))[0] == e["dst"] for n, e in ext.items() if n != "product_a")
    check("apply-gapps", "lpdump: product_a at its new offset and size; every other partition where it was",
          got.get("product_a") == (pr["super_offset"], pr["bytes"]) and others, {k: v for k, v in got.items()})
    pimg = f"{w}/product.img"  # avbtool verify_image looks for <partition name>.img
    extract(t3, sp["start"] + pr["super_offset"], pr["bytes"], pimg)
    info = avb_info(pimg)
    open(f"{w}/product_a.avbinfo.txt", "w").write(info)
    ht = ht_block(info, "product")
    check("apply-gapps", "product_a: AVB footer, hashtree descriptor for the new image, no FEC",
          f"Original image size:      {pr['image_bytes']} bytes" in info and
          ht.get("Image Size") == f"{pr['image_bytes']} bytes" and ht.get("FEC num roots") == "0" and
          ht.get("Root Digest") == rg.get("root_digest"), {k: ht.get(k) for k in ("Image Size", "FEC num roots", "Root Digest")})
    vi = sh(f"{HOST}/avbtool", "verify_image", "--image", pimg)
    open(f"{w}/product_a.verify.txt", "w").write(vi.stdout + vi.stderr)
    check("apply-gapps", "avbtool verify_image recomputes product's hashtree and finds it correct",
          vi.returncode == 0 and "Successfully verified sha256 hashtree" in vi.stdout + vi.stderr,
          (vi.stdout + vi.stderr)[-300:])
    # an independent hashtree: avbtool over the same EROFS bytes with the same salt
    xi = f"{w}/product-avbtool.img"
    extract(pimg, 0, pr["image_bytes"], xi)
    salt = ht.get("Salt", "")
    # (avbtool keeps more room for metadata than the engine needs; the tree and its root do not depend on it)
    ah = sh(f"{HOST}/avbtool", "add_hashtree_footer", "--image", xi, "--partition_name", "product", "--partition_size",
            str(pr["bytes"] + 4 * MiB), "--hash_algorithm", "sha256", "--salt", salt, "--do_not_generate_fec")
    hx = ht_block(avb_info(xi), "product")
    check("apply-gapps", "avbtool add_hashtree_footer over the same image and salt: same root digest and hashtree bytes",
          ah.returncode == 0 and hx.get("Root Digest") == ht.get("Root Digest") and
          sha_file(xi, pr["hashtree_bytes"], pr["image_bytes"]) == sha_file(pimg, pr["hashtree_bytes"], pr["image_bytes"]),
          (ah.stderr[-200:], hx.get("Root Digest"), ht.get("Root Digest")))
    os.remove(xi)
    # EROFS: the stick's product unchanged inside, the package's files added
    sext = ext["product_a"]
    sup_stick = next(p for p in meta["partitions"] if p["name"] == "super")
    spimg = f"{w}/stick-product_a.img"
    extract(stick, sup_stick["start"] * 512 + sext["src"], sext["bytes"], spimg)
    for img, d in ((spimg, f"{w}/x-stick"), (pimg, f"{w}/x-new")):
        shutil.rmtree(d, ignore_errors=True)
        fx = sh(f"{HOST}/fsck.erofs", f"--extract={d}", "--no-preserve", img)
        check("apply-gapps", f"fsck.erofs extracts {os.path.basename(img)} without errors", fx.returncode == 0,
              (fx.stdout + fx.stderr)[-300:])
    old, new = walk(f"{w}/x-stick"), walk(f"{w}/x-new")
    check("apply-gapps", f"every one of the stick's {len(old)} product files is unchanged in the new image",
          old and all(new.get(k) == v for k, v in old.items()), [k for k, v in old.items() if new.get(k) != v][:5])
    added = {k: v for k, v in new.items() if k not in old}
    want = dict(expected["files"])
    check("apply-gapps", "the new image adds exactly the package's 7 files and the install manifest",
          {k: v for k, v in added.items() if k != "etc/openbook/gapps-manifest.json"} == want and
          "etc/openbook/gapps-manifest.json" in added, sorted(added))
    gm = open(f"{w}/x-new/etc/openbook/gapps-manifest.json").read() if "etc/openbook/gapps-manifest.json" in added else ""
    check("apply-gapps", "/product/etc/openbook/gapps-manifest.json is the package check's manifest",
          hashlib.sha256(gm.encode()).hexdigest() == gsha)
    fs = Erofs(pimg)
    labels = {}
    for rel in list(want) + ["etc/openbook/gapps-manifest.json", "priv-app/OpenBookTestPriv", "app/OpenBookTestApp/lib",
                             "etc/default-permissions", "etc/openbook"]:
        nid = fs.lookup(rel)
        ino = fs.inode(nid) if nid is not None else {}
        x = fs.xattrs(ino) if ino else {}
        labels[rel] = (oct(ino.get("mode", 0)), ino.get("uid"), ino.get("gid"),
                       x.get("security.selinux", b"").rstrip(b"\0").decode())
    okl = all(v[1] == 0 and v[2] == 0 and v[3] == "u:object_r:system_file:s0" and
              v[0] in ("0o100644", "0o40755") for v in labels.values())
    check("apply-gapps", "new files and directories: root-owned, 0644/0755, labeled u:object_r:system_file:s0", okl,
          {k: v for k, v in labels.items() if not (v[3] == "u:object_r:system_file:s0")})
    json.dump(labels, open(f"{w}/labels.json", "w"), indent=1)
    # vbmeta_a
    vbimg = f"{w}/vbmeta_a.img"
    extract(t3, planned["vbmeta_a"]["start"], MiB, vbimg)
    vinfo = avb_info(vbimg)
    open(f"{w}/vbmeta_a.avbinfo.txt", "w").write(vinfo)
    svb = f"{w}/stick-vbmeta_a.img"
    vpart = next(p for p in meta["partitions"] if p["name"] == "vbmeta_a")
    extract(stick, vpart["start"] * 512, vpart["sectors"] * 512, svb)
    sinfo = avb_info(svb)
    vht = ht_block(vinfo, "product")
    strip = lambda t: re.sub(r"Hashtree descriptor:\n(?:      .*\n)*?      Partition Name:        product\n(?:      .*\n)*", "",
                             t.split("Descriptors:", 1)[-1])
    check("apply-gapps", "vbmeta_a: unsigned; product's descriptor is the footer's; every other descriptor as on the stick",
          "Algorithm:                NONE" in vinfo and vht.get("Root Digest") == ht.get("Root Digest") and
          vht.get("Image Size") == ht.get("Image Size") and strip(vinfo) == strip(sinfo), vht.get("Root Digest"))
    dg = sh(f"{HOST}/avbtool", "calculate_vbmeta_digest", "--image", vbimg, "--hash_algorithm", "sha256").stdout.strip()
    espimg = f"{w}/esp.img"
    extract(t3, planned["EFI"]["start"], planned["EFI"]["bytes"], espimg)
    sh("mcopy", "-n", "-o", "-i", espimg, "::/openbook/a/bootconfig.img", f"{w}/bootconfig.img")
    bc = open(f"{w}/bootconfig.img", "rb").read() if os.path.exists(f"{w}/bootconfig.img") else b""
    bct = bc[:bc.find(b"\0")].decode() if bc else ""
    vbs = re.search(r"Header Block:\s+(\d+).*\nAuthentication Block:\s+(\d+).*\nAuxiliary Block:\s+(\d+)", vinfo)
    size = sum(int(x) for x in vbs.groups()) if vbs else -1
    check("apply-gapps", "bootconfig: androidboot.vbmeta.digest = avbtool calculate_vbmeta_digest, size = the image's",
          dg and f"androidboot.vbmeta.digest = {dg}" in bct and f"androidboot.vbmeta.size = {size}" in bct and
          dg == rg.get("vbmeta_digest"), (dg, re.findall(r"androidboot\.vbmeta\.\S+ = \S+", bct)))
    keys = lambda t: sorted(re.findall(r"^(\S+) = ", t, re.M))
    base_bc = {k for k in inst["bootconfig"]} | {"androidboot.boot_part_uuid", "androidboot.serialno",
                                                 "androidboot.openbook.locale", "androidboot.openbook.installed"}
    check("apply-gapps", "bootconfig: the same keys as without the package", set(keys(bct)) == base_bc,
          set(keys(bct)) ^ base_bc)
    diff = []
    for n, e in ext.items():
        if n == "product_a":
            continue
        diff.append((n, sha_file(t3, e["bytes"], sp["start"] + e["dst"]) == e["sha256"]))
    check("apply-gapps", "every other logical partition is byte-identical to the stick's", all(x for _, x in diff), diff)
    json.dump(res, open(f"{w}/report.json", "w"), indent=1)

    # ---------------------------------------------------------------- scale: a 256 MiB app
    big = f"{a.packages}/{REF}-big.zip"
    if os.path.exists(big):
        import time
        tb = blank(f"{run}/target-big.img", 64)
        B = engine(a.engine, "big", tb)
        t0 = time.time()
        rc, j, _ = B.run("gapps-check", "--package", big)
        t_check = time.time() - t0
        bsha = j.get("gapps_sha256", "")
        bigf = next((f for f in j.get("gapps", {}).get("files", []) if f["path"].endswith("OpenBookTestBig.apk")), {})
        check("scale", f"a {os.path.getsize(big) // MiB} MiB package with a 256 MiB app: accepted ({t_check:.1f} s)",
              rc == 0 and j.get("ok") and bigf.get("sha256") == sha_file(f"{a.apks}/OpenBookTestBig.apk"), j.get("error"))
        pb = f"{run}/big/plan.json"
        rc, j, _ = B.run("plan", "--target", target, "--layout", "whole", "--gapps", bsha, "--out", pb)
        prb = j.get("product", {})
        t0 = time.time()
        rc, j, _ = B.run("apply", "--plan", pb, "--confirm-disk", f"/dev/disk/by-id/{target}", env=erase)
        t_apply = time.time() - t0
        steps_s = {k: v.get("seconds") for k, v in j.get("steps", {}).items()}
        check("scale", f"its install verifies ({t_apply:.1f} s; steps {steps_s})", rc == 0 and j.get("ok"), j.get("error"))
        spb = next(p for p in json.load(open(pb))["partitions"] if p["name"] == "super")
        bimg = f"{run}/big/product.img"
        extract(tb, spb["start"] + prb.get("super_offset", 0), prb.get("bytes", 0), bimg)
        vi = sh(f"{HOST}/avbtool", "verify_image", "--image", bimg)
        check("scale", f"avbtool verify_image: the {prb.get('bytes', 0) // MiB} MiB product's hashtree is correct",
              vi.returncode == 0 and "Successfully verified sha256 hashtree" in vi.stdout + vi.stderr, (vi.stdout + vi.stderr)[-200:])
        fsx = Erofs(bimg)
        nid = fsx.lookup("priv-app/OpenBookTestBig/OpenBookTestBig.apk")
        ino = fsx.inode(nid) if nid is not None else {}
        got = sha_file(bimg, ino.get("size", 0), ino.get("raw", 0) * 4096) if ino else ""
        check("scale", "the 256 MiB app reads back from the image byte for byte",
              got == sha_file(f"{a.apks}/OpenBookTestBig.apk"), got)
        results["scale"] = {"package_bytes": os.path.getsize(big), "check_s": round(t_check, 1), "apply_s": round(t_apply, 1),
                            "steps_s": steps_s, "product_bytes": prb.get("bytes"), "image_bytes": prb.get("image_bytes"),
                            "hashtree_bytes": prb.get("hashtree_bytes")}
        os.remove(bimg)
        os.remove(tb)

    # ---------------------------------------------------------------- summary
    total = sum(len(v) for v in results["cases"].values())
    passed = sum(c["ok"] for v in results["cases"].values() for c in v)
    results["summary"] = {"passed": passed, "total": total}
    json.dump(results, open(f"{run}/results.json", "w"), indent=1)
    with open(f"{run}/SUMMARY.md", "w") as f:
        f.write(f"# engine-gapps-test: {passed}/{total}\n\n")
        for case, cs in results["cases"].items():
            f.write(f"## {case}: {sum(c['ok'] for c in cs)}/{len(cs)}\n")
            for c in cs:
                f.write(f"- {'PASS' if c['ok'] else 'FAIL'} {c['check']}" + (f" ({c['detail']})" if not c["ok"] else "") + "\n")
    print(f"{passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
