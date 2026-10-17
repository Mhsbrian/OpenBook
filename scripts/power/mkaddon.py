#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assemble the OpenBook power check (ANAL-178) as an add-on for an OpenBook live USB stick's ESP.

The live stick (scripts/installer-image.sh) boots Android. This adds menu entries that boot the hardware-check probe
(scripts/installer/probe-init.c, v7) with its own kernel instead, run the S0i3 investigation and power off, leaving
openbook/logs/hwcheck-NNN.{txt,json} and -dmesg.txt on the stick. Files, all new on the stick:

  openbook/check/kernel        the kernel the check's modules were built for (ANAL-171/172 build, same config as the
                               G14 product's kernel but its own module signing key)
  openbook/check/hwcheck.img   lz4 cpio: openbook-check/probe, openbook-check/modules/<release>/ (the ANAL-172 module
                               set), openbook-check/kmod/*.ko (test-only modules), lib/firmware/ (ANAL-171's subset
                               plus wireless-regdb)
  openbook/check/README-power-check.txt
  loader/entries/openbook-check-*.conf

The entries end with the stick's own /openbook/a/bootconfig-live.img, so the probe finds the stick by its
androidboot.boot_part_uuid whichever live image is on it. Nothing on the stick is replaced.

usage: mkaddon.py --kernel BZIMAGE --modules DIR --firmware DIR --kmod DIR --probe BIN --out DIR --name NAME
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "installer"))
import mkproto as proto  # noqa: E402  newc(), tree_entries()

# Same options as the hardware-check stick's entries (runs 2-7), plus a large log buffer: several sleep cycles with
# pm_debug_messages overrun the default 128 KiB.
BASE = ("printk.devkmsg=on audit=1 panic=-1 8250.nr_uarts=1 binder.impl=rust cma=0 firmware_class.path=/vendor/etc/ "
        "loop.max_part=7 bootconfig console=ttyS0,115200 loglevel=7 log_buf_len=8M "
        "rdinit=/openbook-check/probe openbook.probe=report")
SLEEP = ("openbook.probe.sleep=1 openbook.probe.dgpu=detach openbook.probe.acpi_d3cold=_SB.PCI0.GPP0.SWUS "
         "openbook.probe.s0i3_snapshot=1")
ENTRIES = {  # file stem: (title, sort key, extra options)
    "check-s0i3": ("OpenBook power check: S0i3 (about 3 min, then powers off)", "openbook-91",
                   f"{SLEEP} openbook.probe.s0i3_steps=psp,dummy,asus"),
    "check-s0i3-long": ("OpenBook power check: S0i3, 60 s cycles, all steps", "openbook-92",
                        f"{SLEEP} openbook.probe.sleep_s=60 openbook.probe.s0i3_steps=psp,dummy,asus "
                        "openbook.probe.s0i3_all=1"),
    "check-hw": ("OpenBook hardware check (no sleep test)", "openbook-93", ""),
}
README = """OpenBook power check (ANAL-178), added to this live stick
================================================================
Three extra menu entries, after the normal OpenBook ones. Each boots its own small Linux (openbook/check/kernel),
not Android, writes openbook/logs/hwcheck-NNN.txt, .json and -dmesg.txt on THIS stick and powers the laptop off.
Nothing is written to the laptop's own disk, and no firmware setting changes.

- "OpenBook power check: S0i3": powers the NVIDIA GPU and an unused PCIe port down for this boot, then sleeps up to
  four times for 20 s, woken by the clock: as-is, then with the AMD security processor (PSP) given power
  management, then also an unused AMD function, then with the ASUS keyboard and hotkey drivers loaded. It stops
  early once the laptop reaches its deepest sleep state (S0i3). The screen stays black throughout; the laptop
  powers off by itself after about 3 minutes.
- "... 60 s cycles, all steps": the same with 60 s sleeps and all steps (about 5 minutes).
- "OpenBook hardware check (no sleep test)": drivers and devices only, about 1 minute.

Run it plugged in or on battery (the report records which). Then plug the stick into the build host and run
scripts/installer/read-stick-logs.sh. The add-on can be removed by deleting openbook/check/ and
loader/entries/openbook-check-*.conf; the normal entries are untouched.
"""


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    for k in ("kernel", "modules", "firmware", "kmod", "probe", "out", "name"):
        ap.add_argument(f"--{k}", required=True)
    a = ap.parse_args()
    release = os.path.basename(os.path.normpath(a.modules))
    out = a.out
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(f"{out}/openbook/check")
    os.makedirs(f"{out}/loader/entries")

    entries = (proto.tree_entries(a.modules, f"openbook-check/modules/{release}") +
               proto.tree_entries(a.firmware, "lib/firmware") +
               proto.tree_entries(a.kmod, "openbook-check/kmod") +
               [("openbook-check/probe", 0o100755, open(a.probe, "rb").read())])
    cpio = proto.newc(entries)
    lz = subprocess.run(["lz4", "-l", "-9", "-c"], input=cpio, capture_output=True, check=True).stdout
    open(f"{out}/openbook/check/hwcheck.img", "wb").write(lz)
    shutil.copy(a.kernel, f"{out}/openbook/check/kernel")
    open(f"{out}/openbook/check/README-power-check.txt", "w").write(README)
    for stem, (title, key, extra) in ENTRIES.items():
        opts = f"{BASE} {extra}".strip()
        open(f"{out}/loader/entries/openbook-{stem}.conf", "w").write(
            f"title {title}\nsort-key {key}\nlinux /openbook/check/kernel\ninitrd /openbook/check/hwcheck.img\n"
            f"initrd /openbook/a/bootconfig-live.img\noptions {opts}\n")
    # The applier refuses sticks without this file: only an OpenBook live stick gets the add-on.
    open(f"{out}/EXPECT", "w").write("loader/entries/openbook-live.conf\nopenbook/a/bootconfig-live.img\n")
    files = sorted(os.path.relpath(os.path.join(d, f), out) for d, _, fs in os.walk(out) for f in fs
                   if os.path.join(d, f).startswith((f"{out}/openbook", f"{out}/loader")))
    with open(f"{out}/MANIFEST.sha256", "w") as m:
        for f in files:
            m.write(f"{sha256(os.path.join(out, f))}  {f}\n")
    kmods = sorted(f for f in os.listdir(a.kmod) if f.endswith(".ko"))
    meta = {
        "schema": "openbook-power-check-addon/1", "name": a.name, "kernel_release": release,
        "kernel_sha256": sha256(a.kernel), "probe_sha256": sha256(a.probe),
        "kmod": {k: sha256(os.path.join(a.kmod, k)) for k in kmods},
        "modules": sum(1 for _, _, fs in os.walk(a.modules) for f in fs if f.endswith(".ko")),
        "firmware_files": sum(len(fs) for _, _, fs in os.walk(a.firmware)),
        "hwcheck_img": {"bytes": len(lz), "cpio_bytes": len(cpio), "sha256": sha256(f"{out}/openbook/check/hwcheck.img")},
        "entries": {s: {"title": t, "options": f"{BASE} {x}".strip()} for s, (t, _, x) in ENTRIES.items()},
        "files": files, "bytes": sum(os.path.getsize(os.path.join(out, f)) for f in files),
    }
    json.dump(meta, open(f"{out}.json", "w"), indent=1)
    print(json.dumps({k: meta[k] for k in ("name", "kernel_release", "kmod", "modules", "firmware_files", "bytes")},
                     indent=1))


if __name__ == "__main__":
    main()
