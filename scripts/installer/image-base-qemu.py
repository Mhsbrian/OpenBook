#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the built chooser APK on a private copy of an existing AOSP live image.

Run through inst-docker.sh. No host disks or network are attached. The VM keeps
the image's daemon; image-base-test.py separately exercises the changed engine.
--run must be a new writable directory with a short path (QEMU uses UNIX sockets).
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("wizard", HERE / "wizard-qemu.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


def run(*args):
    subprocess.run([str(x) for x in args], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--run", required=True, type=Path)
    a = parser.parse_args()
    assert a.image.is_file() and a.apk.is_file(), "regular input files required"
    work = a.run.resolve()
    work.mkdir(parents=True, exist_ok=False)
    meta = json.loads(Path(str(a.image) + ".json").read_text())
    offset = next(p for p in meta["partitions"] if p["name"] == "EFI")["start"] * 512
    stick = work / "stick.img"
    run("cp", "--reflink=auto", "--sparse=always", a.image, stick)
    with stick.open("r+b") as stream:
        stream.truncate(16 << 30)
    target = work / "target.img"
    with target.open("xb") as stream:
        stream.truncate(64 << 30)
    target_before = target.stat()
    fat = f"{stick}@@{offset}"
    entry = work / "vm.conf"
    run("mcopy", "-i", fat, "::/loader/entries/openbook-vm.conf", entry)
    entry.write_text(re.sub(r"^sort-key .*", "sort-key openbook-9", entry.read_text(), flags=re.M))
    loader = work / "loader.conf"
    loader.write_text("timeout 0\ndefault base-test.conf\nconsole-mode keep\neditor no\n")
    run("mcopy", "-o", "-i", fat, entry, "::/loader/entries/base-test.conf")
    run("mcopy", "-o", "-i", fat, loader, "::/loader/loader.conf")
    run("mcopy", "-o", "-i", fat, a.apk, "::/openbook/base-test.apk")
    steps = w.steps_common_boot()
    # The root console has no exported ART classpath before its first svc call.
    export = "while read -r k n v; do [ \"$k\" = export ] && export \"$n=$v\"; done < /data/system/environ/classpath; "
    for step in steps:
        if step.get("send", "").startswith("svc power"):
            step["send"] = export + step["send"]
    steps += w.send("wm density 240; mkdir -p /mnt/obesp; mount -t vfat /dev/block/sda1 /mnt/obesp; "
                    "cp /mnt/obesp/openbook/base-test.apk /data/local/tmp/base-test.apk; umount /mnt/obesp; "
                    "am force-stop org.openbook.installer; pm install -r /data/local/tmp/base-test.apk", 120)
    steps += w.send("am start --windowingMode 5 -n org.openbook.installer/.MainActivity")
    steps += w.send(w.HELPERS)
    steps += w.wait_ui("Choose your language")
    steps += w.tap("Continue") + w.wait_ui("STEP 2 OF 7")
    steps += w.tap("Continue") + w.wait_ui("STEP 3 OF 7")
    steps += w.tap("Install OpenBook") + w.tap("Continue")
    steps += w.wait_ui("Choose your image base") + w.shot("base-aosp", snap=False)
    steps += w.section("BASE-AOSP-UI", "ui; cat /data/local/tmp/ui.xml")
    steps += w.tap("Googlebook OS") + w.wait_ui("Googlebook installation is not available")
    steps += w.shot("base-googlebook", snap=False)
    steps += w.section("BASE-GOOGLEBOOK-UI", "ui; cat /data/local/tmp/ui.xml")
    steps += w.tap("Continue") + w.wait_ui("Choose your image base")
    steps += w.send("cmd uimode night yes") + [{"pause": 3}]
    steps += w.shot("base-googlebook-dark", snap=False)
    steps += w.tap("OpenBook · AOSP") + w.tap("Continue") + w.wait_ui("STEP 4 OF 7")
    steps += w.tap("Back") + w.wait_ui("Choose your image base")
    steps += w.section("BASE-RETURN-UI", "ui; cat /data/local/tmp/ui.xml")
    steps += w.tap("Back") + w.wait_ui("Install OpenBook")
    steps += w.section("BASE-RUNTIME", "getenforce; logcat -d -b crash")
    expect = work / "expect.json"
    expect.write_text(json.dumps(steps, indent=2))
    run("python3", HERE / "qemu-run.py", "--usb", stick, "--nvme", target,
        "--out", work / "vm", "--expect", expect, "--timeout", 1000, "--mem", 8192, "--smp", 8,
        "--gpu", "virtio-vga,xres=2880,yres=1800", "--usb-input", "--tpm")
    serial = (work / "vm/serial.log").read_text(errors="replace")
    checks = {}
    for label, enabled in (("AOSP", "true"), ("GOOGLEBOOK", "false"), ("RETURN", "true")):
        match = re.search(rf"\n===BASE-{label}-UI-BEGIN===\s*(.*?)===BASE-{label}-UI-END===", serial, re.S)
        xml = re.search(r"<\?xml.*?</hierarchy>", match[1], re.S) if match else None
        root = ET.fromstring(xml[0]) if xml else ET.Element("missing")
        nodes = list(root.iter("node"))
        parents = {child: parent for parent in root.iter() for child in parent}
        buttons = [n for n in nodes if n.get("text") == "Continue"]
        checks[label + " Continue enabled=" + enabled] = len(buttons) == 1 and parents[buttons[0]].get("enabled") == enabled
    after = target.stat()
    checks["no target writes"] = (target_before.st_mtime_ns, target_before.st_ctime_ns, target_before.st_blocks) == (
        after.st_mtime_ns, after.st_ctime_ns, after.st_blocks)
    checks["SELinux enforcing"] = bool(re.search(r"\n===BASE-RUNTIME-BEGIN===\s*Enforcing", serial))
    checks["no app crash"] = "FATAL EXCEPTION" not in serial and "Fatal signal" not in serial
    checks["no UI timeout"] = not re.search(r"\n@@TIMEOUT\[", serial)
    (work / "checks.json").write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
