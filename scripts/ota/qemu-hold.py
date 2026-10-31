#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Boots a copy of a saved disk state of an ota-qemu.py run and keeps it running for hands-on debugging over adb,
until OUT/stop exists (ANAL-225). Prints the adb serial (on the rehearsal's private adb server, port 5223).

usage: qemu-hold.py --run RUN --from STATE [--minutes N]
"""
import argparse
import importlib.util
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("otaqemu", os.path.join(HERE, "ota-qemu.py"))
oq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(oq)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--from", dest="from_state", required=True)
    ap.add_argument("--minutes", type=int, default=60)
    a = ap.parse_args()
    q, out = oq.case_dir(a.run, f"hold-from-{a.from_state}")
    disk, vars_file = f"{q}/hold.img", f"{q}/hold.vars"
    oq.reflink(f"{q}/{a.from_state}.img", disk)
    shutil.copy(f"{q}/{a.from_state}.vars", vars_file)
    port = oq.free_port()
    vm = oq.VM(out, disk, vars_file, port, f"ota-{a.run}-hold")
    vm.start()
    try:
        slot = oq.boot(vm)
        adb = oq.Adb(port, out)
        adb.connect()
        unlocked, _ = oq.unlock(adb)
        adb.sh("svc power stayon true")
        oq.log(f"hold: slot {slot}, unlocked={unlocked}, adb 127.0.0.1:{port} (ANDROID_ADB_SERVER_PORT={oq.ADB_PORT}); "
               f"touch {out}/stop to end")
        end = time.time() + a.minutes * 60
        while time.time() < end and not os.path.exists(f"{out}/stop") and vm.running():
            time.sleep(2)
    finally:
        vm.stop()
        if os.path.exists(disk):
            os.remove(disk)
    return 0


if __name__ == "__main__":
    sys.exit(main())
