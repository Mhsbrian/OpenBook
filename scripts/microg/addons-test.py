#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Host tests for openbook-addons (device/anybook/common/addons/addons.c, ANAL-210), on image files.

Each case builds a GPT disk image whose EFI partition carries (or not) openbook/addons/microg/, a catalogue that
pins the test's files, and runs the host build against it with fake-cmd.py standing in for /system/bin/cmd.
The "APKs" are random bytes; only openbook-addons' own logic is under test here (the real APKs and PackageManager
are tested in Cuttlefish and QEMU). Cases:

  absent         no add-on on the EFI partition: result absent, exit 0, no cmd call, no state written
  no-uuid        no boot_part_uuid: the same
  install        three packages installed with the catalogue's flags, the exact pinned bytes streamed, grants,
                 app-ops and the battery exemption applied, state "installed"; the image is unchanged (read-only)
  again          a second run: already installed, no cmd call
  uninstalled    the user uninstalled one app: the next run leaves it uninstalled
  kept           the same or a newer version installed already: kept, not reinstalled; its grants still applied
  upgrade        an earlier version of the add-on was installed: older packages upgraded, one the user removed stays
                 removed, no permission granted again
  tampered       one byte changed in one file: the whole add-on refused, nothing installed, exit 1
  missing        one file missing: refused
  commit-fails   PackageManager refuses a commit: failed, exit 1, and the next run tries again
  grant-fails    one permission cannot be granted: installed, the failure reported
  bad-catalogue  a catalogue file name with a path: refused before reading anything
  from-dir       --from-dir DIR instead of the EFI partition
  status         `status` (dry run): would_install, no cmd call that changes anything

usage: addons-test.py --addons BIN --run DIR
"""
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = []


def sh(*cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def check(case, what, ok, detail=""):
    RESULTS.append({"case": case, "check": what, "ok": bool(ok), "detail": "" if ok else str(detail)[:600]})
    print(("PASS " if ok else "FAIL ") + f"{case}: {what}" + ("" if ok else f"  [{str(detail)[:300]}]"))


def sha(b):
    return hashlib.sha256(b).hexdigest()


def sha_file(p):
    with open(p, "rb") as f:
        return sha(f.read())


FILES = [  # file, package, versionCode, size, grant, appops, power, bypass
    ("com.google.android.gms-252432034.apk", "com.google.android.gms", 252432034, 3 << 20,
     ["android.permission.ACCESS_FINE_LOCATION", "android.permission.INTERACT_ACROSS_USERS"], ["SYSTEM_ALERT_WINDOW"],
     True, False),
    ("com.android.vending-84022634.apk", "com.android.vending", 84022634, 200 << 10,
     ["android.permission.POST_NOTIFICATIONS"], [], False, False),
    ("com.google.android.gsf-8.apk", "com.google.android.gsf", 8, 21872, [], [], False, True),
]


def make_fixture(run):
    """Random 'APKs', their catalogue, and fake-cmd's map from sha256 to package."""
    os.makedirs(f"{run}/apks", exist_ok=True)
    cat = {"schema": "openbook-addon/1", "name": "microg", "title": "test", "version": "0.3.17.252432", "files": []}
    apks = {}
    for i, (f, pkg, vc, size, grant, appops, power, bypass) in enumerate(FILES):
        data = hashlib.sha256(f.encode()).digest() * (size // 32) + bytes(size % 32)
        with open(f"{run}/apks/{f}", "wb") as o:
            o.write(data)
        e = {"file": f, "package": pkg, "version_code": vc, "sha256": sha(data), "grant": grant, "appops": appops,
             "power_allowlist": power}
        if bypass:
            e["bypass_low_target_sdk"] = True
        cat["files"].append(e)
        apks[sha(data)] = {"package": pkg, "version_code": vc}
    return cat, apks


def make_disk(path, files_dir=None, esp_files=None):
    """A 96 MiB GPT disk: EFI (64 MiB, FAT32 'OPENBOOK') and an empty 'super'. Returns the ESP's PARTUUID."""
    if os.path.exists(path):
        os.remove(path)
    with open(path, "wb") as f:
        f.truncate(96 << 20)
    r = sh("sgdisk", "-n", "1:2048:+64M", "-t", "1:ef00", "-c", "1:EFI", "-n", "2:0:0", "-c", "2:super", path)
    assert r.returncode == 0, r.stderr
    esp = path + ".esp"
    if os.path.exists(esp):
        os.remove(esp)
    r = sh("mkfs.fat", "-F", "32", "-n", "OPENBOOK", "-C", esp, str(64 * 1024))
    assert r.returncode == 0, r.stderr
    sh("mmd", "-i", esp, "::/openbook")
    sh("mcopy", "-i", esp, "/dev/null", "::/openbook/MANIFEST.json")
    if esp_files is not None:
        sh("mmd", "-i", esp, "::/openbook/addons")
        sh("mmd", "-i", esp, "::/openbook/addons/microg")
        for f in esp_files:
            r = sh("mcopy", "-i", esp, f"{files_dir}/{f}", f"::/openbook/addons/microg/{f}")
            assert r.returncode == 0, r.stderr
    r = sh("dd", f"if={esp}", f"of={path}", "bs=1M", "seek=1", "conv=notrunc")
    assert r.returncode == 0, r.stderr
    os.remove(esp)
    return re.search(r"unique GUID: (\S+)", sh("sgdisk", "-i", "1", path).stdout).group(1).lower()


class Env:
    def __init__(self, run, name, binary, cat):
        self.d = f"{run}/{name}"
        shutil.rmtree(self.d, ignore_errors=True)
        for sub in ("catalog", "state", "pm"):
            os.makedirs(f"{self.d}/{sub}")
        with open(f"{self.d}/catalog/microg.json", "w") as f:
            json.dump(cat, f, indent=1)
        self.binary = binary

    def pm(self, apks, installed=None, fail=None):
        with open(f"{self.d}/pm/apks.json", "w") as f:
            json.dump(apks, f)
        if installed is not None:
            with open(f"{self.d}/pm/state.json", "w") as f:
                json.dump({"installed": installed, "sessions": {}, "grants": [], "appops": [], "deviceidle": [],
                           "next": 100}, f)
        if fail is not None:
            with open(f"{self.d}/pm/fail.json", "w") as f:
                json.dump(fail, f)
        elif os.path.exists(f"{self.d}/pm/fail.json"):
            os.remove(f"{self.d}/pm/fail.json")

    def run(self, *args, verb="run"):
        if os.path.exists(f"{self.d}/pm/calls.jsonl"):
            os.remove(f"{self.d}/pm/calls.jsonl")
        cmd = [self.binary, "--catalog", f"{self.d}/catalog", "--state", f"{self.d}/state",
               "--cmd", f"{HERE}/fake-cmd.py", *args, verb]
        p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "FAKE_PM": f"{self.d}/pm"})
        with open(f"{self.d}/{verb}-{len(os.listdir(self.d))}.log", "w") as f:
            f.write(" ".join(cmd) + "\n" + p.stderr + "\n" + p.stdout)
        try:
            out = json.loads(p.stdout)
        except json.JSONDecodeError:
            out = {}
        calls = []
        if os.path.exists(f"{self.d}/pm/calls.jsonl"):
            calls = [json.loads(l) for l in open(f"{self.d}/pm/calls.jsonl")]
        return p.returncode, out, calls, p.stderr

    def pmstate(self):
        return json.load(open(f"{self.d}/pm/state.json"))

    def state(self):
        p = f"{self.d}/state/microg.json"
        return json.load(open(p)) if os.path.exists(p) else None


def addon(out):
    return (out.get("addons") or [{}])[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--addons", required=True)
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    run = a.run
    os.makedirs(run, exist_ok=True)
    cat, apks = make_fixture(run)
    names = [f[0] for f in FILES]
    writing = lambda calls: [c for c in calls if c["args"][:2] != ["package", "list"]]

    # absent
    e = Env(run, "absent", a.addons, cat)
    e.pm(apks)
    uuid = make_disk(f"{e.d}/disk.img")
    rc, out, calls, err = e.run("--disk", f"{e.d}/disk.img", "--boot-part-uuid", uuid)
    check("absent", "exit 0", rc == 0, err)
    check("absent", "result absent", addon(out).get("result") == "absent", out)
    check("absent", "the EFI partition was found", out.get("source") == f"{e.d}/disk.img", out)
    check("absent", "no cmd call", calls == [], calls)
    check("absent", "no state written", e.state() is None)

    # no-uuid
    rc, out, calls, err = e.run("--disk", f"{e.d}/disk.img")
    check("no-uuid", "exit 0, result absent, no cmd call",
          rc == 0 and addon(out).get("result") == "absent" and calls == [], (rc, out, calls))

    # install
    e = Env(run, "install", a.addons, cat)
    e.pm(apks, installed={})
    disk = f"{e.d}/disk.img"
    uuid = make_disk(disk, f"{run}/apks", names)
    before = sha_file(disk)
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    st = e.pmstate()
    check("install", "exit 0", rc == 0, err)
    check("install", "result installed", addon(out).get("result") == "installed", out)
    check("install", "all three packages installed at the pinned versions",
          st["installed"] == {f[1]: f[2] for f in FILES}, st["installed"])
    streamed = [c.get("stdin_sha256") for c in calls if c["args"][:2] == ["package", "install-write"]]
    check("install", "the exact pinned bytes were streamed, in catalogue order",
          streamed == [x["sha256"] for x in cat["files"]], streamed)
    flags = {c["installed"]: c["flags"] for c in calls if "installed" in c}
    check("install", "--bypass-low-target-sdk-block only for the package that asks for it",
          "--bypass-low-target-sdk-block" in flags.get("com.google.android.gsf", [])
          and not any("--bypass-low-target-sdk-block" in v for k, v in flags.items() if k != "com.google.android.gsf"),
          flags)
    want_grants = [[f[1], p] for f in FILES for p in f[4]]
    check("install", "the catalogue's permissions granted", st["grants"] == want_grants, st["grants"])
    check("install", "app-ops set", st["appops"] == [["com.google.android.gms", "SYSTEM_ALERT_WINDOW", "allow"]],
          st["appops"])
    check("install", "battery-optimisation exemption for GmsCore only", st["deviceidle"] == ["+com.google.android.gms"],
          st["deviceidle"])
    s = e.state()
    check("install", "state: installed, this version", s and s["result"] == "installed" and s["version"] == cat["version"], s)
    check("install", "the disk image is unchanged (read-only)", sha_file(disk) == before)
    check("install", "a log was written", os.path.getsize(f"{e.d}/state/addons.log") > 0)

    # again
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    check("again", "exit 0, already installed, no cmd call",
          rc == 0 and addon(out).get("result") == "already_installed" and calls == [], (rc, addon(out), calls))

    # uninstalled
    st = e.pmstate()
    del st["installed"]["com.android.vending"]
    json.dump(st, open(f"{e.d}/pm/state.json", "w"))
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    check("uninstalled", "an app the user uninstalled stays uninstalled",
          rc == 0 and calls == [] and "com.android.vending" not in e.pmstate()["installed"], (rc, calls))

    # kept: GmsCore newer, Companion the same, GsfProxy missing
    e = Env(run, "kept", a.addons, cat)
    e.pm(apks, installed={"com.google.android.gms": 252432099, "com.android.vending": 84022634})
    disk = f"{e.d}/disk.img"
    uuid = make_disk(disk, f"{run}/apks", names)
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    st = e.pmstate()
    acts = {p["package"]: p.get("action") for p in addon(out).get("packages", [])}
    check("kept", "exit 0, installed", rc == 0 and addon(out).get("result") == "installed", (rc, addon(out)))
    check("kept", "newer and equal versions kept, the missing one installed",
          acts == {"com.google.android.gms": "kept", "com.android.vending": "kept", "com.google.android.gsf": "installed"}
          and st["installed"]["com.google.android.gms"] == 252432099, (acts, st["installed"]))
    check("kept", "grants still applied to kept packages", ["com.google.android.gms", FILES[0][4][0]] in st["grants"],
          st["grants"])

    # upgrade: the state says 0.3.16 was installed; GmsCore is older, Companion was removed, the proxy is current
    e = Env(run, "upgrade", a.addons, cat)
    e.pm(apks, installed={"com.google.android.gms": 252432030, "com.google.android.gsf": 8})
    os.makedirs(f"{e.d}/state", exist_ok=True)
    json.dump({"schema": "openbook-addon-state/1", "name": "microg", "version": "0.3.16.252432", "result": "installed"},
              open(f"{e.d}/state/microg.json", "w"))
    disk = f"{e.d}/disk.img"
    uuid = make_disk(disk, f"{run}/apks", names)
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    st = e.pmstate()
    acts = {p["package"]: p.get("action") for p in addon(out).get("packages", [])}
    check("upgrade", "exit 0, installed, state at the new version",
          rc == 0 and addon(out).get("result") == "installed" and (e.state() or {}).get("version") == cat["version"], (rc, addon(out)))
    check("upgrade", "the older package upgraded, the removed one left out, the current one kept",
          acts == {"com.google.android.gms": "installed", "com.android.vending": "removed_by_user",
                   "com.google.android.gsf": "kept"} and "com.android.vending" not in st["installed"]
          and st["installed"]["com.google.android.gms"] == 252432034, (acts, st["installed"]))
    check("upgrade", "no permission, app-op or exemption applied again", not st["grants"] and not st["appops"] and
          not st["deviceidle"], (st["grants"], st["appops"], st["deviceidle"]))

    # tampered
    e = Env(run, "tampered", a.addons, cat)
    e.pm(apks, installed={})
    bad = f"{e.d}/apks"
    shutil.copytree(f"{run}/apks", bad)
    with open(f"{bad}/{names[1]}", "r+b") as f:
        f.seek(1000)
        b = f.read(1)
        f.seek(1000)
        f.write(bytes([b[0] ^ 1]))
    disk = f"{e.d}/disk.img"
    uuid = make_disk(disk, bad, names)
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    check("tampered", "exit 1, refused", rc == 1 and addon(out).get("result") == "refused", (rc, addon(out)))
    check("tampered", "nothing installed, no write call at all", writing(calls) == [] and e.pmstate()["installed"] == {},
          calls)
    check("tampered", "the reason names the file", names[1] in (addon(out).get("why") or ""), addon(out))
    check("tampered", "state: refused", (e.state() or {}).get("result") == "refused", e.state())

    # missing
    e = Env(run, "missing", a.addons, cat)
    e.pm(apks, installed={})
    disk = f"{e.d}/disk.img"
    uuid = make_disk(disk, f"{run}/apks", names[:2])
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    check("missing", "exit 1, refused, nothing installed",
          rc == 1 and addon(out).get("result") == "refused" and writing(calls) == [], (rc, addon(out), calls))

    # commit-fails, then a retry
    e = Env(run, "commit-fails", a.addons, cat)
    e.pm(apks, installed={}, fail={"commit": "com.android.vending"})
    disk = f"{e.d}/disk.img"
    uuid = make_disk(disk, f"{run}/apks", names)
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    check("commit-fails", "exit 1, failed", rc == 1 and addon(out).get("result") == "failed", (rc, addon(out)))
    check("commit-fails", "stops at the failing package", "com.google.android.gsf" not in e.pmstate()["installed"],
          e.pmstate()["installed"])
    e.pm(apks)
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    check("commit-fails", "the next run tries again and completes",
          rc == 0 and addon(out).get("result") == "installed" and len(e.pmstate()["installed"]) == 3, (rc, addon(out)))

    # grant-fails
    e = Env(run, "grant-fails", a.addons, cat)
    e.pm(apks, installed={}, fail={"grant": "android.permission.INTERACT_ACROSS_USERS"})
    disk = f"{e.d}/disk.img"
    uuid = make_disk(disk, f"{run}/apks", names)
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    g = [x for p in addon(out).get("packages", []) for x in p.get("grant", [])]
    check("grant-fails", "installed; the failed grant is reported",
          rc == 0 and addon(out).get("result") == "installed"
          and any(x["permission"].endswith("INTERACT_ACROSS_USERS") and not x["ok"] for x in g), (rc, g))

    # bad-catalogue
    bc = copy.deepcopy(cat)
    bc["files"][0]["file"] = "../../etc/passwd.apk"
    e = Env(run, "bad-catalogue", a.addons, bc)
    e.pm(apks, installed={})
    disk = f"{e.d}/disk.img"
    uuid = make_disk(disk, f"{run}/apks", names)
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid)
    check("bad-catalogue", "exit 1, bad_catalog, no cmd call",
          rc == 1 and addon(out).get("result") == "bad_catalog" and calls == [], (rc, addon(out), calls))

    # from-dir
    e = Env(run, "from-dir", a.addons, cat)
    e.pm(apks, installed={})
    os.makedirs(f"{e.d}/src")
    shutil.copytree(f"{run}/apks", f"{e.d}/src/microg")
    rc, out, calls, err = e.run("--from-dir", f"{e.d}/src")
    check("from-dir", "exit 0, installed from the directory",
          rc == 0 and addon(out).get("result") == "installed" and len(e.pmstate()["installed"]) == 3, (rc, addon(out)))

    # status
    e = Env(run, "status", a.addons, cat)
    e.pm(apks, installed={})
    disk = f"{e.d}/disk.img"
    uuid = make_disk(disk, f"{run}/apks", names)
    rc, out, calls, err = e.run("--disk", disk, "--boot-part-uuid", uuid, verb="status")
    check("status", "would_install, nothing written, no state",
          rc == 0 and addon(out).get("result") == "would_install" and writing(calls) == [] and e.state() is None,
          (rc, addon(out), calls))

    ok = sum(r["ok"] for r in RESULTS)
    with open(f"{run}/results.json", "w") as f:
        json.dump({"schema": "openbook-addons-test/1", "passed": ok, "total": len(RESULTS), "checks": RESULTS}, f,
                  indent=1)
    with open(f"{run}/SUMMARY.md", "w") as f:
        f.write(f"# openbook-addons host tests: {ok}/{len(RESULTS)}\n\n| Case | Check | Result |\n|---|---|---|\n")
        for r in RESULTS:
            f.write(f"| {r['case']} | {r['check']} | {'pass' if r['ok'] else 'FAIL: ' + r['detail'][:120]} |\n")
    print(f"{ok}/{len(RESULTS)} passed")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
