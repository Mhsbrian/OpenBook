#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Quire in the OTA rehearsal VM (ANAL-225), before the G14: boots a copy of a saved disk state of an ota-qemu.py run
(default after-ba: the update the laptop gets, applied over adb from the laptop's own state), runs the Linux-environment
adapter's regression on its Android runtime (device/anybook/common/quire/tools/bridge-test.sh), puts the Linux
environment's Debian image on it over adb the way the laptop gets it (scripts/quire/linux-env-adb.sh check: the
person's steps, the guest, an agent's answer to Quire core), then runs scripts/quire/g14-quire-check.py. The Debian
guest runs under nested KVM (the VM has -cpu host).

usage: quire-qemu.py --run RUN --image images.tar.gz [--from STATE] [--only SECTIONS]
Results: <data dir>/logs/installer/ota/RUN/quire-from-STATE/ (serial.log, linux-env/, quire/, the scripts' logs).
The disk copy is removed at the end; the saved state is not changed.
"""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("otaqemu", os.path.join(HERE, "ota-qemu.py"))
oq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oq)


def script(cmd, logfile, timeout):
    """A repo script against the VM through the rehearsal's private adb server; its output to logfile."""
    with open(logfile, "a") as f:
        f.write(f"$ {' '.join(cmd)}\n")
        f.flush()
        p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             env={**os.environ, "ANDROID_ADB_SERVER_PORT": oq.ADB_PORT})
        try:
            return p.wait(timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            return -1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--image", required=True, help="images.tar.gz from scripts/quire/linux-env-image.sh")
    ap.add_argument("--from", dest="from_state", default="after-ba")
    ap.add_argument("--only", default="facts,invoke,agent,control,health")
    a = ap.parse_args()
    q, out = oq.case_dir(a.run, f"quire-from-{a.from_state}")
    disk, vars_file = f"{q}/quire.img", f"{q}/quire.vars"
    oq.reflink(f"{q}/{a.from_state}.img", disk)
    shutil.copy(f"{q}/{a.from_state}.vars", vars_file)
    port = oq.free_port()
    vm = oq.VM(out, disk, vars_file, port, f"ota-{a.run}-quire")
    vm.start()
    rc = {}
    try:
        slot = oq.boot(vm)
        adb = oq.Adb(port, out)
        adb.connect()
        unlocked, how = oq.unlock(adb)
        oq.log(f"quire: slot {slot}, unlocked={unlocked} ({how})")
        serial = f"127.0.0.1:{port}"
        rc["bridge"] = script([f"{oq.R}/device/anybook/common/quire/tools/bridge-test.sh", serial, f"{out}/bridge"],
                              f"{out}/bridge-test.log", 900)
        oq.log(f"quire: bridge-test.sh exit {rc['bridge']}")
        rc["linux-env"] = script([f"{oq.R}/scripts/quire/linux-env-adb.sh", "-s", serial, "check", a.image,
                                  f"{out}/linux-env"], f"{out}/linux-env-adb.log", 2400)
        oq.log(f"quire: linux-env-adb.sh check exit {rc['linux-env']}")
        rc["quire"] = script([sys.executable, f"{oq.R}/scripts/quire/g14-quire-check.py", serial, f"{out}/quire",
                              "--only", a.only], f"{out}/g14-quire-check.log", 1800)
        oq.log(f"quire: g14-quire-check.py exit {rc['quire']}")
        adb.sh("reboot -p")
        vm.wait_exit(120)
    finally:
        vm.stop()
        if os.path.exists(disk):
            os.remove(disk)
    return 0 if rc and all(v == 0 for v in rc.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
