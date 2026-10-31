#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host tests of the install engine's add-on path (ANAL-210, device/anybook/common/installer/engine/addon.c), on
image files, with the fixtures of scripts/installer/engine-test.py: a live image is the stick, sparse files are the
targets, and the image's add-on catalogue sits in the fixture root.

  inventory      `addons`: a stick without the add-on reports it absent; one with it (add-to-image.sh) reports it
  same-plan      a plan WITHOUT add-ons from this engine has no add-on key, operation or file, and main's engine
                 (--old) accepts it for apply: its own re-computation gives the same plan sha256, byte for byte
  old-apply      ... and main's engine installs that plan and verifies it
  plan-addon     a plan with --addon microg: the request names it, a check_addon operation, the three catalogued APKs
                 as files on the new EFI partition with the image's sha256 pins
  apply-addon    that install verifies; the new EFI partition holds the three APKs with the pinned sha256 (read back
                 with mtools from outside the engine), the boot files are as in the plan, and fsck.fat passes
  refuse-*       --addon on a stick without it, or on an image without the catalogue: refused (no_addon); a stick
                 whose add-on APK is corrupted: apply refuses at check_source and the target is unchanged

usage: engine-addon-test.py --engine BIN --old BIN --image LIVE.img --addon ADDON_DIR --catalog microg.json --run DIR
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("enginetest", os.path.join(HERE, "../installer/engine-test.py"))
et = importlib.util.module_from_spec(spec)
spec.loader.exec_module(et)
sh, sha_file, check, Engine, make_root = et.sh, et.sha_file, et.check, et.Engine, et.make_root
GiB = et.GiB


def blank(path, gib):
    if os.path.exists(path):
        os.remove(path)
    with open(path, "wb") as f:
        f.truncate(gib * GiB)
    return path


def reflink(src, dst):
    if os.path.exists(dst):
        os.remove(dst)
    subprocess.run(["cp", "--reflink=auto", src, dst], check=True)


def main():
    ap = argparse.ArgumentParser()
    for k in ("engine", "old", "image", "addon", "catalog", "run"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    run = os.path.abspath(a.run)
    os.makedirs(run, exist_ok=True)
    meta = json.load(open(a.image + ".json"))
    uuid = meta["esp_partuuid"]
    esp_off = next(p for p in meta["partitions"] if p["name"] == "EFI")["start"] * 512
    cat = json.load(open(a.catalog))
    target = "nvme-QEMU_NVMe_Ctrl_internal0"
    erase = {"OPENBOOK_INSTALL_ERASE": f"/dev/disk/by-id/{target}"}

    plain, withaddon, bad = f"{run}/stick-plain.img", f"{run}/stick-addon.img", f"{run}/stick-bad.img"
    reflink(a.image, plain)
    reflink(a.image, withaddon)
    r = sh(os.path.join(HERE, "add-to-image.sh"), withaddon, a.addon)
    check("inventory", "add-to-image.sh puts the add-on on a copy of the live image", r.returncode == 0, r.stderr[-300:])
    reflink(withaddon, bad)
    apk0 = cat["files"][0]["file"]
    tmp = f"{run}/x.apk"
    sh("mcopy", "-n", "-o", "-i", f"{bad}@@{esp_off}", f"::/openbook/addons/microg/{apk0}", tmp)
    with open(tmp, "r+b") as f:
        f.seek(4096)
        b = f.read(1)
        f.seek(4096)
        f.write(bytes([b[0] ^ 0xFF]))
    sh("mcopy", "-o", "-i", f"{bad}@@{esp_off}", tmp, f"::/openbook/addons/microg/{apk0}")

    def root(name, stick, tgt, catalogue=True):
        rt = make_root(run, name, stick, tgt)
        if catalogue:
            os.makedirs(f"{rt}/system_ext/etc/openbook/addons", exist_ok=True)
            shutil.copyfile(a.catalog, f"{rt}/system_ext/etc/openbook/addons/microg.json")
        return rt

    # ---------------------------------------------------------------- inventory
    t0 = blank(f"{run}/t0.img", 64)
    rc, j, _ = Engine(a.engine, root("inv-plain", plain, t0), uuid, f"{run}/inventory").run("addons")
    ad = (j.get("addons") or [{}])[0]
    check("inventory", "plain stick: microg catalogued, not on the stick",
          rc == 0 and ad.get("name") == "microg" and ad.get("on_stick") is False and "does not carry" in (ad.get("why") or ""), j)
    rc, j, _ = Engine(a.engine, root("inv-addon", withaddon, t0), uuid, f"{run}/inventory").run("addons")
    ad = (j.get("addons") or [{}])[0]
    want_bytes = sum(f["bytes"] for f in cat["files"])
    check("inventory", "add-on stick: on the stick, with its title, version and size",
          ad.get("on_stick") is True and ad.get("version") == cat["version"] and ad.get("bytes") == want_bytes, ad)

    # ---------------------------------------------------------------- the same plan without add-ons
    t1 = blank(f"{run}/t1.img", 64)
    E = Engine(a.engine, root("same", withaddon, t1), uuid, f"{run}/same-plan")
    plan_a = f"{run}/same-plan/plan.json"
    rc, j, _ = E.run("plan", "--target", target, "--layout", "whole", "--locale", "en-US", "--keyboard", "us",
                     "--set-default", "--out", plan_a)
    check("same-plan", "plan without add-ons succeeds", rc == 0 and j.get("plan_sha256"), j.get("error"))
    check("same-plan", "no add-on key, operation or file in it",
          "addons" not in j.get("request", {}) and not any(o["op"] == "check_addon" for o in j.get("operations", []))
          and not any("addons" in f["path"] for f in j.get("files", [])), j.get("request"))
    O = Engine(a.old, E.root, uuid, f"{run}/old-apply")
    rc, j, _ = O.run("apply", "--plan", plan_a, "--confirm-disk", f"/dev/disk/by-id/{target}", env=erase)
    check("same-plan", "main's engine accepts it (its own re-computation has the same sha256)",
          j.get("code") != "plan_changed", j.get("error"))
    check("old-apply", "main's engine installs and verifies it", rc == 0 and j.get("ok") and j.get("verified"), j.get("error"))

    # ---------------------------------------------------------------- a plan with the add-on
    t2 = blank(f"{run}/t2.img", 64)
    E = Engine(a.engine, root("addon", withaddon, t2), uuid, f"{run}/plan-addon")
    plan_b = f"{run}/plan-addon/plan.json"
    rc, j, _ = E.run("plan", "--target", target, "--layout", "whole", "--locale", "en-US", "--keyboard", "us",
                     "--set-default", "--addon", "microg", "--out", plan_b)
    check("plan-addon", "plan with --addon microg succeeds", rc == 0 and j.get("plan_sha256"), j.get("error"))
    check("plan-addon", "the request names the add-on", j.get("request", {}).get("addons") == ["microg"], j.get("request"))
    ops = [o["op"] for o in j.get("operations", [])]
    check("plan-addon", "a check_addon operation right after check_source", ops[:2] == ["check_source", "check_addon"], ops[:4])
    files = {f["path"]: f for f in j.get("files", [])}
    want = {f"openbook/addons/microg/{f['file']}": f for f in cat["files"]}
    check("plan-addon", "the three APKs, with the image's sha256 and size, from the same path on the stick",
          all(p in files and files[p]["sha256"] == w["sha256"] and files[p]["bytes"] == w["bytes"] and
              files[p]["source"] == p and not files[p]["after_verify"] for p, w in want.items()),
          {p: files.get(p) for p in want})
    plan_b_j = j
    rc, j, _ = E.run("apply", "--plan", plan_b, "--confirm-disk", f"/dev/disk/by-id/{target}", env=erase)
    check("apply-addon", "the install verifies", rc == 0 and j.get("ok") and j.get("verified"), j.get("error"))
    pe = {p["name"]: p for p in plan_b_j["partitions"]}["EFI"]
    off = pe["start"]
    ok = True
    for p, w in want.items():
        dst = f"{run}/readback.apk"
        got = et.esp_get(t2, off, p, dst) and sha_file(dst)
        ok = ok and got == w["sha256"]
    check("apply-addon", "the new EFI partition holds the three APKs with the pinned sha256 (mtools read-back)", ok)
    espimg = f"{run}/t2-esp.img"
    sh("dd", f"if={t2}", f"of={espimg}", "bs=1M", f"skip={off // (1 << 20)}", f"count={pe['bytes'] // (1 << 20)}")
    fs = sh("fsck.fat", "-n", espimg)
    check("apply-addon", "the new EFI partition passes fsck.fat", fs.returncode == 0, fs.stdout[-200:])
    os.remove(espimg)
    for f in plan_b_j["files"]:
        if f["path"].startswith("openbook/addons/"):
            continue
        dst = f"{run}/readback.bin"
        if not (et.esp_get(t2, off, f["path"], dst) and sha_file(dst) == f["sha256"]):
            ok = False
    check("apply-addon", "every other file is as in the plan", ok)

    # ---------------------------------------------------------------- refusals
    t3 = blank(f"{run}/t3.img", 64)
    rc, j, _ = Engine(a.engine, root("no-addon", plain, t3), uuid, f"{run}/refuse").run(
        "plan", "--target", target, "--layout", "whole", "--addon", "microg")
    check("refuse-not-on-stick", "--addon on a stick without it: refused, no_addon", rc != 0 and j.get("code") == "no_addon", j)
    rc, j, _ = Engine(a.engine, root("no-catalogue", withaddon, t3, catalogue=False), uuid, f"{run}/refuse").run(
        "plan", "--target", target, "--layout", "whole", "--addon", "microg")
    check("refuse-no-catalogue", "--addon on an image without the catalogue: refused, no_addon",
          rc != 0 and j.get("code") == "no_addon", j)
    E = Engine(a.engine, root("bad", bad, t3), uuid, f"{run}/refuse-corrupt")
    plan_c = f"{run}/refuse-corrupt/plan.json"
    rc, j, _ = E.run("plan", "--target", target, "--layout", "whole", "--addon", "microg", "--out", plan_c)
    before = sha_file(t3)
    rc, j, _ = E.run("apply", "--plan", plan_c, "--confirm-disk", f"/dev/disk/by-id/{target}", env=erase)
    check("refuse-corrupt", "a corrupted add-on APK: apply refuses at check_source",
          rc != 0 and j.get("failed_step") == "check_source" and "openbook/addons/microg" in (j.get("error") or ""),
          {k: j.get(k) for k in ("failed_step", "error")})
    check("refuse-corrupt", "the target is unchanged", sha_file(t3) == before)

    for p in (t0, t1, t2, t3, plain, withaddon, bad, tmp):
        if os.path.exists(p):
            os.remove(p)
    res = [dict(case=c, **x) for c, xs in et.results["cases"].items() for x in xs]
    ok = sum(x["ok"] for x in res)
    json.dump({"schema": "openbook-engine-addon-test/1", "passed": ok, "total": len(res), "checks": res},
              open(f"{run}/results.json", "w"), indent=1)
    with open(f"{run}/SUMMARY.md", "w") as f:
        f.write(f"# Install engine, add-on path (ANAL-210): {ok}/{len(res)}\n\n| Case | Check | Result |\n|---|---|---|\n")
        for x in res:
            f.write(f"| {x['case']} | {x['check']} | {'pass' if x['ok'] else 'FAIL: ' + x['detail'][:120]} |\n")
    print(f"{ok}/{len(res)} passed")
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    sys.exit(main())
