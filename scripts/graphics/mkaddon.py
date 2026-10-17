#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble the OpenBook graphics check (ANAL-177) as an add-on for an OpenBook live USB stick's ESP.

The stick's own Android runs the check: a new boot entry boots the stick's kernel, ramdisks and "save logs" bootconfig
with one more initrd, gfx-init.img, whose /openbook-gfx-init is openbook-live-init built from this tree (the add-on
hook, androidboot.openbook.addon=gfx). Once Android has booted, it unpacks openbook/gfx/payload into the stick's
/data, runs the payload's run.sh (scripts/graphics/gfx-run.sh) as root, saves the results next to the boot's other
logs on the stick (openbook/logs/live-NNN/addon-gfx*) and powers off. Nothing on the stick is replaced, and the
laptop's own disks are never touched. Files, all new on the stick:

  openbook/gfx/payload        bzip2 tar: run.sh, VERSION.json, MANIFEST.sha256, bin/ (deqp-binary64, deqp-runner,
                              gfx-nsbind), lib/libdeqp_stdout.so, radv-nonstrict/vulkan.radv.so, data/ (dEQP's
                              archive), caselists/, apk/ (dEQP app, ANGLE end2end helper), LICENSES/
  openbook/gfx/gfx-init.img   newc cpio: /openbook-gfx-init
  openbook/gfx/README-graphics-check.txt
  loader/entries/openbook-gfx.conf   written by add-to-live-stick.sh from the stick's own "save logs" entry, so it
                                     matches whatever live image is on the stick

usage: mkaddon.py --payload DIR --live-init BIN --out DIR --name NAME
"""
import argparse
import bz2
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer"))
import mkproto as proto  # noqa: E402  newc()

README = """OpenBook graphics check (ANAL-177), added to this live stick
=============================================================
One extra menu entry, after the normal OpenBook ones: "OpenBook graphics check". It boots OpenBook from this stick
as the "save logs" entry does (SELinux permissive), waits until the desktop is up, then runs graphics conformance
tests on the laptop's own GPU drivers for about 30 minutes: dEQP (Vulkan, OpenGL ES 2/3/3.1, EGL) and ANGLE's
end2end tests, from the Android CTS. The screen shows test windows now and then; leave the laptop alone, plugged in,
with the lid open. When it is done it saves everything to openbook/logs/live-NNN/ on THIS stick and powers off.

Nothing is written to the laptop's own disk. The tests run from the stick's own storage, and the settings they
change (the GL driver for one pass, keep-screen-on) are put back afterwards; the two test apps are uninstalled.

Then plug the stick into the build host and run scripts/installer/read-stick-logs.sh, or
scripts/graphics/gfx-report.py on the live-NNN folder. Remove the add-on with
scripts/graphics/add-to-live-stick.sh --remove; the normal entries are untouched.
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def files_under(root):
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)


def main():
    ap = argparse.ArgumentParser()
    for k in ("payload", "live-init", "out", "name"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    out, pl = a.out, a.payload
    for need in ("run.sh", "VERSION.json", "bin/deqp-binary64", "bin/deqp-runner", "caselists/vk.txt"):
        if not os.path.exists(os.path.join(pl, need)):
            raise SystemExit(f"payload: {need} missing")
    # MANIFEST.sha256 inside the payload: openbook-live-init checks the unpacked copy against it on the device.
    with open(f"{pl}/MANIFEST.sha256", "w") as m:
        for f in files_under(pl):
            if f != "MANIFEST.sha256":
                m.write(f"{sha256(os.path.join(pl, f))}  {f}\n")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(f"{out}/openbook/gfx")
    # Deterministic tar: sorted, root-owned, fixed times; executables 0755, the rest 0644.
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "1792195200"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        dirs = sorted({os.path.dirname(f) for f in files_under(pl)} - {""})
        for d in sorted({p for d in dirs for p in [os.path.join(*d.split("/")[:i + 1])
                                                    for i in range(len(d.split("/")))]}):
            ti = tarfile.TarInfo(d)
            ti.type, ti.mode, ti.mtime = tarfile.DIRTYPE, 0o755, epoch
            t.addfile(ti)
        for f in files_under(pl):
            p = os.path.join(pl, f)
            ti = tarfile.TarInfo(f)
            ti.size, ti.mtime = os.path.getsize(p), epoch
            ti.mode = 0o755 if os.access(p, os.X_OK) else 0o644
            with open(p, "rb") as fh:
                t.addfile(ti, fh)
    raw = buf.getvalue()
    bz = bz2.compress(raw, 9)
    open(f"{out}/openbook/gfx/payload", "wb").write(bz)
    init = open(a.live_init, "rb").read()
    open(f"{out}/openbook/gfx/gfx-init.img", "wb").write(
        proto.newc([("openbook-gfx-init", 0o100755, init)], ino=0x7E000000))
    open(f"{out}/openbook/gfx/README-graphics-check.txt", "w").write(README)
    # The applier refuses sticks without these: only an OpenBook live stick with a "save logs" entry gets the add-on.
    open(f"{out}/EXPECT", "w").write("loader/entries/openbook-live.conf\nloader/entries/openbook-logs.conf\n"
                                     "openbook/a/bootconfig-logs.img\nopenbook/a/live.img\n")
    files = files_under(f"{out}/openbook")
    with open(f"{out}/MANIFEST.sha256", "w") as m:
        for f in files:
            m.write(f"{sha256(os.path.join(out, 'openbook', f))}  openbook/{f}\n")
    version = json.load(open(f"{pl}/VERSION.json"))
    meta = {
        "schema": "openbook-gfx-check-addon/1", "name": a.name, "payload": {
            "bytes": len(bz), "tar_bytes": len(raw), "sha256": sha256(f"{out}/openbook/gfx/payload"),
            "files": len(files_under(pl))},
        "live_init_sha256": sha256(a.live_init), "esp_files": [f"openbook/{f}" for f in files],
        "esp_bytes": sum(os.path.getsize(os.path.join(out, "openbook", f)) for f in files), "version": version,
    }
    json.dump(meta, open(f"{out}.json", "w"), indent=1)
    print(json.dumps({k: meta[k] for k in ("name", "payload", "esp_bytes")}, indent=1))


if __name__ == "__main__":
    main()
