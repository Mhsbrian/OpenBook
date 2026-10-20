#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""UI smoke test on a disposable Cuttlefish container, never a real laptop."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

p = argparse.ArgumentParser()
p.add_argument("--container", required=True)
p.add_argument("--apk", type=Path, required=True)
p.add_argument("--out", type=Path, required=True)
a = p.parse_args()
assert a.container.startswith("openbook-audio-test-")
a.out.mkdir(mode=0o700)
prefix = ["docker", "exec", "-e", "PATH=/root/cvd-host/bin:/usr/bin:/bin", a.container,
          "adb", "-s", "127.0.0.1:6520"]

def adb(*args):
    return subprocess.check_output(prefix + list(args), timeout=45).decode(errors="replace")

def click(label):
    adb("shell", "uiautomator", "dump", "/sdcard/audio-ui.xml")
    xml = adb("shell", "cat", "/sdcard/audio-ui.xml")
    (a.out / "ui.xml").write_text(xml)
    for e in ET.fromstring(xml).iter("node"):
        if e.get("text", "").replace("’", "'").lower() == label.lower():
            x1, y1, x2, y2 = map(int, re.findall(r"\d+", e.attrib["bounds"]))
            adb("shell", "input", "tap", str((x1+x2)//2), str((y1+y2)//2))
            return
    raise RuntimeError("UI control not found: " + label)

pkg = "org.openbook.diagnostics.audio"
subprocess.run(["docker", "cp", str(a.apk), a.container + ":/tmp/audio.apk"], check=True)
assert "Success" in adb("install", "-r", "/tmp/audio.apk")
adb("root"); time.sleep(2)
adb("shell", "pm", "grant", pkg, "android.permission.BLUETOOTH_CONNECT")
adb("shell", "pm", "grant", pkg, "android.permission.POST_NOTIFICATIONS")
adb("shell", "am", "start", "-W", "-n", pkg + "/.MainActivity")
time.sleep(3)
click("Start diagnostic"); time.sleep(3)
adb("shell", "input", "keyevent", "HOME"); time.sleep(11)
adb("shell", "am", "start", "-W", "-n", pkg + "/.MainActivity"); time.sleep(2)
click("Mark an audio problem"); time.sleep(1)
click("Stop diagnostic"); time.sleep(2)
raw = adb("shell", "cat", "/data/user/0/" + pkg + "/files/audio-report.jsonl")
(a.out / "report.jsonl").write_text(raw)
rows = [json.loads(line) for line in raw.splitlines()]
events = [row["event"] for row in rows]
assert all(event in events for event in ("start", "storage", "sample", "user_marked_problem", "stop")), events
assert not any("access_error" in r for r in rows), rows
assert sum(r["event"] == "sample" for r in rows) >= 3
with (a.out / "screen.png").open("wb") as f:
    subprocess.run(prefix + ["exec-out", "screencap", "-p"], stdout=f, check=True)
click("Save report"); time.sleep(3)
click("Save"); time.sleep(3)
files = adb("shell", "find", "/sdcard/Download", "-name", "OpenBook-audio-*.jsonl").splitlines()
assert files, "SAF export missing"
assert adb("shell", "cat", files[-1]) == raw, "Export did not preserve report bytes"
# Revocation must degrade to permission=false, not stop the passive collector.
adb("shell", "pm", "revoke", pkg, "android.permission.BLUETOOTH_CONNECT")
adb("shell", "am", "start", "-W", "-n", pkg + "/.MainActivity"); time.sleep(2)
click("Start diagnostic"); time.sleep(2)
click("Don't allow"); time.sleep(6)
click("Stop diagnostic"); time.sleep(2)
denied = adb("shell", "cat", "/data/user/0/" + pkg + "/files/audio-report.jsonl")
(a.out / "denied.jsonl").write_text(denied)
dr = [json.loads(line) for line in denied.splitlines()]
assert any(r.get("bluetooth_permission") is False for r in dr)
assert any(r["event"] == "stop" for r in dr)
log = adb("logcat", "-d", "-s", "AndroidRuntime:E")
(a.out / "crashes.txt").write_text(log)
assert pkg not in log, "Diagnostic app crashed"
(a.out / "result.json").write_text(json.dumps(dict(
    installed=True, foreground_capture=True, background_samples=True, marker=True,
    stop=True, saf_export_identical=True, bluetooth_denial_supported=True,
    app_crash=False, physical_bluetooth_tested=False), indent=2) + "\n")
print("Audio diagnostic UI/capture/export/permission-denial checks passed.")
