#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble the OpenBook ARM-apps check (ANAL-200) as an add-on for an OpenBook live USB stick's ESP.

The stick's own Android runs it: a new boot entry boots the stick's kernel, ramdisks and "save logs" bootconfig with
androidboot.openbook.addon=bridge. Once Android has booted, the stick's openbook-live-init unpacks
openbook/bridge/payload into the stick's /data, runs the payload's run.sh (scripts/compat/digitalis/stick/run.sh) as
root, saves the results next to the boot's other logs (openbook/logs/live-NNN/addon-bridge*) and powers off. Nothing
on the stick is replaced, and the laptop's own disks are never touched. Files, all new on the stick:

  openbook/bridge/payload        gzip tar: run.sh, VERSION.json, MANIFEST.sha256, apk/anybook-probe-{arm64,x86_64}.apk,
                                 bench/coremark-{arm64,x86_64}, LICENSES/
  openbook/bridge/README-bridge-check.txt
  loader/entries/openbook-bridge.conf   written by add-to-image.sh from the image's own "save logs" entry

usage: mkaddon.py --payload DIR --out DIR --name NAME
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import tarfile

README = """OpenBook ARM apps check (ANAL-200), added to this live stick
============================================================
One extra menu entry, after the normal OpenBook ones: "OpenBook ARM apps check". It boots OpenBook from this stick
as the "save logs" entry does (SELinux permissive), waits until the desktop is up, then checks how ARM-only Android
apps run on this laptop's own CPU through OpenBook's translator (Digitalis): its self-check, a test app built for
ARM and the same app built for x86 (the control), and the CoreMark CPU benchmark in both. It takes about 10 minutes;
test windows open now and then. Leave the laptop alone, plugged in, with the lid open. When it is done it saves
everything to openbook/logs/live-NNN/ on THIS stick and powers off.

Nothing is written to the laptop's own disk. The tests run from the stick's own storage; the two test apps are
uninstalled and the keep-screen-on setting is put back afterwards.

Then plug the stick into the build host and copy the logs off (scripts/installer/read-stick-logs.sh), and run
scripts/compat/digitalis/stick/bridge-report.py on the live-NNN folder.
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
    for k in ("payload", "out", "name"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    out, pl = a.out, a.payload
    for need in ("run.sh", "VERSION.json", "apk/anybook-probe-arm64.apk", "apk/anybook-probe-x86_64.apk",
                 "bench/coremark-arm64", "bench/coremark-x86_64"):
        if not os.path.exists(os.path.join(pl, need)):
            raise SystemExit(f"payload: {need} missing")
    # MANIFEST.sha256 inside the payload: openbook-live-init checks the unpacked copy against it on the device.
    with open(f"{pl}/MANIFEST.sha256", "w") as m:
        for f in files_under(pl):
            if f != "MANIFEST.sha256":
                m.write(f"{sha256(os.path.join(pl, f))}  {f}\n")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(f"{out}/openbook/bridge")
    # Deterministic tar: sorted, root-owned, fixed times; executables 0755, the rest 0644.
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH", "1792195200"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as t:
        for d in sorted({os.path.dirname(f) for f in files_under(pl)} - {""}):
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
    gz = gzip.compress(raw, 9, mtime=0)
    open(f"{out}/openbook/bridge/payload", "wb").write(gz)
    open(f"{out}/openbook/bridge/README-bridge-check.txt", "w").write(README)
    # The applier refuses images without these: only an OpenBook live image with a "save logs" entry gets the add-on.
    open(f"{out}/EXPECT", "w").write("loader/entries/openbook-live.conf\nloader/entries/openbook-logs.conf\n"
                                     "openbook/a/bootconfig-logs.img\nopenbook/a/live.img\n")
    files = files_under(f"{out}/openbook")
    with open(f"{out}/MANIFEST.sha256", "w") as m:
        for f in files:
            m.write(f"{sha256(os.path.join(out, 'openbook', f))}  openbook/{f}\n")
    meta = {
        "schema": "openbook-bridge-check-addon/1", "name": a.name,
        "payload": {"bytes": len(gz), "tar_bytes": len(raw), "sha256": sha256(f"{out}/openbook/bridge/payload"),
                    "files": len(files_under(pl))},
        "esp_files": [f"openbook/{f}" for f in files],
        "esp_bytes": sum(os.path.getsize(os.path.join(out, "openbook", f)) for f in files),
        "version": json.load(open(f"{pl}/VERSION.json")),
    }
    json.dump(meta, open(f"{out}.json", "w"), indent=1)
    print(json.dumps({k: meta[k] for k in ("name", "payload", "esp_bytes")}, indent=1))


if __name__ == "__main__":
    main()
