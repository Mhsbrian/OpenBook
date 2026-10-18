#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Quire Q2 checks (ANAL-216) on a booted userdebug OpenBook device, normally Cuttlefish.

usage: q2-cf-check.py SERIAL OUTDIR --probe QuireSecureProbe.apk [--only SECTION,...]

Sections, in order (docs/quire.md §2, acceptance in ANAL-216):
  facts       Quire installed and privileged; the assistant role, the contextual search package, the feature, the flags,
              the permissions; the computer-control allowlists system_server loaded.
  invoke      The pointer shake (a virtual USB mouse made with `uinput`), Meta+Space and the assist key each open Quire's
              note, with Settings and a FLAG_SECURE window (the probe) on screen. Each must log its trigger, entry point
              and visible packages, report the secure window, and save a screenshot with no pixel of the probe in it.
  control     A computer-control session for Settings: the platform's consent dialog, "Only this time", Settings' Dark
              theme page on the session display, Quire's mirror of it, a tap through the session that turns Dark theme
              on, then handOverApplications() moving Settings to the main display.
  refuse      Denied consent; the lock screen (a PIN, screen locked); an app outside the allowlist; a FLAG_SECURE window
              on the session display (the probe, allowlisted for the test only through DeviceConfig, then restored).
  health      Crash buffer, ANRs, tombstones, SystemUI restarts, SELinux denials against Cuttlefish's known three.

Writes OUTDIR/results.tsv (check, PASS/FAIL/INFO, detail), OUTDIR/checks.log and the artifacts it names. Commands go to
Quire through its non-exported LabActivity alias, so the device must be rooted (`adb root`, userdebug).
Env: ADB (default ~/anybook/android-sdk/platform-tools/adb); set ANDROID_ADB_SERVER_PORT for a private server.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

QUIRE = "dev.openbook.quire"
PROBE = "dev.openbook.quire.secureprobe"
SETTINGS = "com.android.settings"
DARK_THEME = "com.android.settings/.Settings$DarkThemeSettingsActivity"
LAB = QUIRE + "/.control.LabActivity"
VDM = "com.android.virtualdevicemanager"
# AOSP's test keys (build/make/target/product/security/): the probe is signed with testkey.
TESTKEY_DIGEST = "A40DA80A59D170CAA950CF15C18C454D47A39B26989D8B640ECD745BA71BF5DC"
# Cuttlefish's denials on main before Quire (evidence/2026-10-17-desktop-flags-v2/v4/selinux-denials.txt).
KNOWN_DENIALS = [
    "scontext=u:r:bootanim:s0 tcontext=u:object_r:gpu_service:s0",
    "scontext=u:r:init:s0 tcontext=u:object_r:debugfs_bootreceiver_tracing:s0",
    "scontext=u:r:gceservice:s0",
]
FLAGS = [
    "android.companion.virtualdevice.flags.computer_control_access",
    "android.companion.virtualdevice.flags.computer_control_support_v5",
    "com.android.hardware.input.enable_contextual_cursor_desktop_entrypoints",
    "com.android.hardware.input.enable_contextual_search_desktop_entrypoints",
    "android.companion.virtualdevice.flags.computer_control_managed_profiles",
    "android.companion.virtualdevice.flags.computer_control_role_assistant_requirement",
]


class Dev:
    def __init__(self, serial, out):
        self.s = serial
        self.o = Path(out)
        self.o.mkdir(parents=True, exist_ok=True)
        self.adb = os.environ.get("ADB", str(Path.home() / "anybook/android-sdk/platform-tools/adb"))
        self.results = []
        self.logf = open(self.o / "checks.log", "a")

    def log(self, msg):
        line = f"{time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        self.logf.write(line + "\n")
        self.logf.flush()

    def run(self, *args, timeout=120):
        return subprocess.run([self.adb, "-s", self.s, *args], capture_output=True, text=True, timeout=timeout)

    def sh(self, cmd, timeout=120):
        return self.run("shell", cmd, timeout=timeout).stdout.replace("\r", "")

    def write(self, name, text):
        (self.o / name).write_text(text)

    def result(self, check, ok, detail):
        r = "INFO" if ok is None else ("PASS" if ok else "FAIL")
        self.results.append((check, r, detail))
        self.log(f"{r} {check}: {detail}")
        return ok

    def screencap(self, name):
        with open(self.o / name, "wb") as f:
            subprocess.run([self.adb, "-s", self.s, "exec-out", "screencap", "-p"], stdout=f, timeout=60)
        return self.o / name

    def quire_log(self):
        return self.sh("logcat -d -v time -s Quire:I")

    def wait_log(self, pattern, timeout=20, since=None):
        """First Quire log line matching pattern (after the marker line `since`, if given)."""
        end = time.time() + timeout
        while time.time() < end:
            text = self.quire_log()
            if since is not None:
                text = text[text.rfind(since):] if since in text else ""
            m = re.search(pattern, text)
            if m:
                return m
            time.sleep(0.5)
        return None

    def mark(self, label):
        """Writes a marker into the log, so waits only see lines after it."""
        tag = f"q2-check {label} {time.time():.3f}"
        self.sh(f"log -t Quire -p i '{tag}'")
        return tag

    def lab(self, action, **extras):
        args = []
        for k, v in extras.items():
            if isinstance(v, bool):
                args += ["--ez", k, str(v).lower()]
            elif isinstance(v, int):
                args += ["--el" if k.endswith("Ms") else "--ei", k, str(v)]
            else:
                args += ["--es", k, f"'{v}'"]
        return self.sh(f"am start -n {LAB} -a dev.openbook.quire.lab.{action} " + " ".join(args))

    def ui(self):
        self.sh("uiautomator dump /data/local/tmp/q2-ui.xml >/dev/null 2>&1")
        return self.sh("cat /data/local/tmp/q2-ui.xml")

    def find_node(self, xml, resource_id=None, text=None):
        try:
            root = ET.fromstring(xml)
        except ET.ParseError:
            return None
        for n in root.iter("node"):
            if resource_id and n.get("resource-id") == resource_id:
                return n
            if text and n.get("text") == text:
                return n
        return None

    def tap_node(self, node):
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", node.get("bounds")))
        self.sh(f"input tap {(x1 + x2) // 2} {(y1 + y2) // 2}")

    def wait_node(self, resource_id, timeout=15):
        end = time.time() + timeout
        while time.time() < end:
            xml = self.ui()
            n = self.find_node(xml, resource_id=resource_id)
            if n is not None:
                return n, xml
            time.sleep(1)
        return None, None


class Mouse:
    """A virtual relative USB mouse made with the device's `uinput -` tool (as in scripts/ui/flag-checks.py)."""
    NAME = "OpenBook Q2 Test Mouse"

    def __init__(self, d):
        self.d = d
        self.p = subprocess.Popen([d.adb, "-s", d.s, "shell", "uinput", "-"], stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        self.send({"id": 1, "command": "register", "name": self.NAME, "vid": 0x18d1, "pid": 0xb216, "bus": "usb",
                   "configuration": [{"type": "UI_SET_EVBIT", "data": ["EV_KEY", "EV_REL"]},
                                     {"type": "UI_SET_KEYBIT", "data": ["BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE"]},
                                     {"type": "UI_SET_RELBIT", "data": ["REL_X", "REL_Y", "REL_WHEEL"]},
                                     {"type": "UI_SET_PROPBIT", "data": ["INPUT_PROP_POINTER"]}]})
        for _ in range(30):
            time.sleep(1)
            if self.NAME in d.sh("dumpsys input | grep -F '" + self.NAME + "'"):
                break
        time.sleep(1)
        self.send({"id": 1, "command": "updateTimeBase"})

    def send(self, obj):
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()

    def move(self, dx, dy):
        self.send({"id": 1, "command": "inject",
                   "events": ["EV_REL", "REL_X", dx, "EV_REL", "REL_Y", dy, "EV_SYN", "SYN_REPORT", 0]})

    def shake(self, amplitude=12, strokes=10, interval=0.035):
        """Side to side inside SystemUI's 100 dp box, 10 direction changes in about 350 ms (it needs 3 in 500 ms)."""
        for i in range(strokes):
            self.move(amplitude if i % 2 == 0 else -amplitude, 0)
            time.sleep(interval)

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def magenta_pixels(png):
    """Pixels of the probe's colour (255, 0, 255) in a screenshot; 0 means the secure window was left out."""
    from PIL import Image
    img = Image.open(png).convert("RGB")
    n = 0
    for r, g, b in img.getdata():
        if r > 230 and g < 40 and b > 230:
            n += 1
    return n, img.size


def window_bounds(d, package):
    dump = d.sh("dumpsys window windows")
    for block in dump.split("Window #"):
        if package in block.split("\n", 1)[0] and "mViewVisibility=0x0" in block:
            m = re.search(r" frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]", block)
            secure = re.search(r"\bfl=[^\n]*\bSECURE\b", block) is not None
            if m:
                return tuple(map(int, m.groups())), secure
    return None, None


# --------------------------------------------------------------------------------------------------------------------
def facts(d):
    d.log("== facts")
    d.write("build.txt", d.sh("getprop ro.build.fingerprint") + d.sh("getprop ro.build.version.incremental"))
    path = d.sh(f"pm path {QUIRE}").strip()
    d.result("Quire installed in system_ext priv-app", "/system_ext/priv-app/" in path, path)
    pkg = d.sh(f"dumpsys package {QUIRE}")
    d.write("quire-package.txt", pkg)
    for perm in ["android.permission.ACCESS_COMPUTER_CONTROL", "android.permission.ACCESS_CONTEXTUAL_SEARCH",
                 "android.permission.POST_NOTIFICATIONS"]:
        ok = re.search(re.escape(perm) + r": granted=true", pkg) is not None
        d.result(f"permission {perm.split('.')[-1]}", ok, "granted" if ok else "not granted")
    d.result("privileged flag", "PRIVILEGED" in pkg, "pkgFlags/privateFlags include PRIVILEGED" if "PRIVILEGED" in pkg
             else "not privileged")
    holders = d.sh("cmd role get-role-holders android.app.role.ASSISTANT").strip()
    d.result("assistant role holder", holders == QUIRE, holders or "(none)")
    vis = d.sh("settings get secure voice_interaction_service").strip()
    d.result("voice interaction service", vis.startswith(QUIRE + "/"), vis)
    rec = d.sh("settings get secure voice_recognition_service").strip()
    d.result("voice recognition service", None, rec)
    cs = d.sh("dumpsys contextual_search")
    d.write("contextual-search.txt", cs)
    feature = "com.google.android.feature.CONTEXTUAL_SEARCH" in d.sh("pm list features")
    d.result("contextual search feature", feature, "declared" if feature else "missing")
    overlay = d.sh("cmd overlay list android | grep -i quire").strip()
    d.result("framework overlay enabled", overlay.startswith("[x]"), overlay or "(not listed)")
    csp = d.sh("cmd overlay lookup android android:string/config_defaultContextualSearchPackageName").strip()
    d.result("config_defaultContextualSearchPackageName", csp == QUIRE, csp)
    da = d.sh("cmd overlay lookup android android:string/config_defaultAssistant").strip()
    d.result("config_defaultAssistant", da == QUIRE, da)
    aflags = d.sh("aflags list")
    d.write("aflags.txt", aflags)
    for flag in FLAGS:
        line = next((l for l in aflags.splitlines() if l.split() and l.split()[0] == flag), "")
        d.result(f"flag {flag.split('.')[-1]}", " enabled " in f" {line} ", " ".join(line.split()[1:4]) or "missing")
    files = d.sh("for f in /system_ext/etc/computercontrol/*; do echo \"# $f\"; cat $f; done")
    d.write("computercontrol-factory.txt", files)
    persisted = d.sh("ls -l /data/system/computercontrol/ 2>&1; cat /data/system/computercontrol/*allowlist* 2>&1")
    d.write("computercontrol-persisted.txt", persisted)
    dc = d.sh("device_config list computer_control")
    d.result("DeviceConfig computer_control (expected empty)", dc.strip() == "", dc.strip() or "(empty)")
    boot = d.sh("logcat -d -b all | grep ComputerControlAllowlistController")
    d.write("allowlist-boot-log.txt", boot)
    factory = re.findall(r"Using factory value .* for key (\w+)", boot)
    d.result("allowlists from the factory files", "allowed_session_owner_apps" in factory and
             "allowed_automatable_apps" in factory, ", ".join(factory) or
             "no 'Using factory value' line in the log buffer (rotated?)")
    d.write("virtualdevice.txt", d.sh("dumpsys virtualdevice"))


# --------------------------------------------------------------------------------------------------------------------
def stage_screen(d):
    """Settings and the probe's FLAG_SECURE window side by side on the desktop."""
    d.sh(f"am start -W -a android.settings.SETTINGS")
    time.sleep(2)
    d.sh(f"am start -W -n {PROBE}/.SecureActivity")
    time.sleep(3)


def close_note(d):
    d.sh("input keyevent KEYCODE_BACK")
    time.sleep(1.5)


def invoke(d):
    d.log("== invoke")
    mouse = Mouse(d)
    cases = [
        ("shake", "system_action", "SYSTEM_ACTION", lambda: mouse.shake()),
        ("meta_space", "assistant_shortcut", "KEYBOARD_SHORTCUT",
         lambda: d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")),
        ("assist_key", "assist_key", "KEYBOARD_SHORTCUT", lambda: d.sh("input keyevent KEYCODE_ASSIST")),
    ]
    saved = []
    for name, trigger, entrypoint, act in cases:
        # Settings and the probe on screen for every case: the note is a fullscreen task, which may leave the desk.
        stage_screen(d)
        bounds, secure = window_bounds(d, PROBE)
        d.result(f"{name}: probe window visible and FLAG_SECURE", bounds is not None and secure,
                 f"frame={bounds} secure={secure}")
        d.screencap(f"invoke-{name}-staged.png")
        # Park the pointer over Settings first: the shake must happen over an app, as a person would do it.
        for _ in range(3):
            mouse.move(-15, -10)
            time.sleep(0.05)
        time.sleep(3.5)  # SystemUI's shake cooldown is 3 s
        tag = d.mark(name)
        act()
        m = d.wait_log(r"invocation: trigger=(\S+) entrypoint=(-?\d+)\((\w+)\) visible=(\[.*?\]|withheld) "
                       r"flagSecureFound=(\S+) screenshot=(\S+)", 20, since=tag)
        if not m:
            d.result(f"{name}: Quire's note opened", False, "no invocation logged in 20 s")
            d.write(f"invoke-{name}-log.txt", d.quire_log())
            continue
        got_trigger, ep, ep_name, visible, secure_found, shot = m.groups()
        d.result(f"{name}: Quire's note opened", got_trigger == trigger and ep_name == entrypoint,
                 f"trigger={got_trigger} entrypoint={ep}({ep_name})")
        d.result(f"{name}: visible packages", SETTINGS in visible and PROBE in visible, visible)
        d.result(f"{name}: secure window reported", secure_found == "true", f"flagSecureFound={secure_found}")
        s = d.wait_log(r"invocation: saved (\S+\.json)", 15, since=tag)
        time.sleep(1)
        d.screencap(f"invoke-{name}-note.png")
        if s:
            remote = s.group(1)
            local = d.o / f"invoke-{name}.json"
            d.run("pull", remote, str(local))
            d.run("pull", remote[:-5] + ".png", str(d.o / f"invoke-{name}-screenshot.png"))
            png = d.o / f"invoke-{name}-screenshot.png"
            if png.exists():
                n, size = magenta_pixels(png)
                d.result(f"{name}: screenshot saved, secure window left out", n == 0 and shot != "none",
                         f"{size[0]}x{size[1]}, {n} probe-coloured pixels")
                saved.append(png)
            else:
                d.result(f"{name}: screenshot saved, secure window left out", False, f"no PNG next to {remote}")
        else:
            d.result(f"{name}: screenshot saved, secure window left out", False, "no 'invocation: saved' line")
        d.write(f"invoke-{name}-log.txt", d.quire_log()[-6000:])
        close_note(d)
    mouse.close()
    d.sh(f"am force-stop {PROBE}")


# --------------------------------------------------------------------------------------------------------------------
def activities(d):
    return d.sh("dumpsys activity activities")


def settings_display(d):
    """Display id of the task holding Settings' Dark theme page, from dumpsys activity."""
    dump = activities(d)
    display = None
    for line in dump.splitlines():
        m = re.match(r"\s*Display #(\d+)", line)
        if m:
            display = int(m.group(1))
        if "DarkThemeSettingsActivity" in line and ("ActivityRecord" in line or "Hist" in line):
            return display, dump
    return None, dump


def consent(d, button, shot=None):
    node, xml = d.wait_node(f"{VDM}:id/{button}", 20)
    if node is None:
        return False, "no consent dialog"
    title = d.find_node(xml, resource_id=f"{VDM}:id/title")
    if shot:
        d.screencap(shot)
        d.write(shot.replace(".png", ".xml"), xml)
    d.tap_node(node)
    return True, title.get("text") if title is not None else "?"


def night(d):
    return d.sh("cmd uimode night").strip()


def control(d):
    d.log("== control")
    d.sh("cmd uimode night no")
    time.sleep(2)
    d.result("Dark theme off before", night(d).endswith("no"), night(d))
    tag = d.mark("control")
    d.lab("REQUEST", targets=SETTINGS, launch=DARK_THEME)
    pending = d.wait_log(r"cc: pending", 15, since=tag)
    d.result("consent asked (session pending)", pending is not None, "cc: pending" if pending else "no pending")
    ok, title = consent(d, "allow_button", "control-consent.png")
    d.result("platform consent dialog, 'Only this time'", ok, title)
    created = d.wait_log(r"cc: created: display (\d+)x(\d+)", 20, since=tag)
    d.result("session created", created is not None, created.group(0) if created else "not created")
    if not created:
        d.write("control-log.txt", d.quire_log())
        return
    active = d.wait_log(r"cc: lifecycle: active", 15, since=tag)
    d.result("session active", active is not None, "lifecycle: active" if active else "never active")
    launched = d.wait_log(r"cc: launch: (\S+)", 10, since=tag)
    d.result("Dark theme page launched through the session", launched is not None,
             launched.group(1) if launched else "no launch line")
    time.sleep(3)
    disp, dump = settings_display(d)
    d.write("control-activities-session.txt", dump)
    d.result("Settings runs on the session display", disp not in (None, 0), f"display #{disp}")
    mirror = d.wait_log(r"cc: mirror (created|refused)", 10, since=tag)
    d.result("Quire's mirror", mirror is not None and mirror.group(1) == "created",
             mirror.group(0) if mirror else "no mirror line")
    time.sleep(2)
    d.screencap("control-mirror.png")
    d.write("control-display.txt", d.sh("dumpsys display | grep -E 'mDisplayId=|mName=|uniqueId=' | head -40"))
    d.write("control-notification.txt", d.sh(f"dumpsys notification --noredact | grep -A30 'pkg={QUIRE}' | head -60"))
    t2 = d.mark("screenshot-before")
    d.lab("SCREENSHOT")
    shot = d.wait_log(r"cc: screenshot: (\d+x\d+) saved (\S+)", 15, since=t2)
    if shot:
        d.run("pull", shot.group(2), str(d.o / "control-session-before.png"))
    d.result("session screenshot", shot is not None, shot.group(0) if shot else "none")
    d.lab("WINDOWS")
    time.sleep(2)
    t3 = d.mark("tap")
    d.lab("TAP", text="Use Dark theme")
    target = d.wait_log(r"cc: tap target: .*", 10, since=t3)
    tap = d.wait_log(r"cc: tap: (\d+),(\d+)", 10, since=t3)
    d.result("tap through the session", tap is not None, (target.group(0) if target else "no target") + " / " +
             (tap.group(0) if tap else "no tap"))
    after = ""
    for _ in range(10):
        time.sleep(1)
        after = night(d)
        if after.endswith("yes"):
            break
    d.result("the tap turned Dark theme on", after.endswith("yes"), after)
    t4 = d.mark("screenshot-after")
    d.lab("SCREENSHOT")
    shot2 = d.wait_log(r"cc: screenshot: (\d+x\d+) saved (\S+)", 15, since=t4)
    if shot2:
        d.run("pull", shot2.group(2), str(d.o / "control-session-after.png"))
    d.screencap("control-mirror-after.png")
    t5 = d.mark("handover")
    d.lab("HAND_OVER")
    handed = d.wait_log(r"cc: hand over: done", 10, since=t5)
    closed = d.wait_log(r"cc: lifecycle: closed reason=(\d+)\((\w+)\)", 10, since=t5)
    d.result("handOverApplications()", handed is not None, handed.group(0) if handed else "no hand over")
    d.result("session closed after hand over", closed is not None,
             closed.group(0) if closed else "not closed")
    time.sleep(3)
    disp2, dump2 = settings_display(d)
    d.write("control-activities-after.txt", dump2)
    d.result("Settings moved to the main display", disp2 == 0, f"display #{disp2}")
    d.screencap("control-handed-over.png")
    d.write("control-log.txt", d.quire_log())
    d.sh("cmd uimode night no")
    d.sh(f"am force-stop {SETTINGS}")


# --------------------------------------------------------------------------------------------------------------------
def refuse(d):
    d.log("== refuse")
    d.sh(f"am start -W -n {QUIRE}/.control.ControlActivity")
    time.sleep(2)
    # 1. Denied consent.
    tag = d.mark("deny")
    d.lab("REQUEST", targets=SETTINGS, launch=DARK_THEME)
    ok, title = consent(d, "dont_allow_button", "refuse-consent.png")
    d.result("deny: consent dialog, 'Don't allow'", ok, title)
    failed = d.wait_log(r"cc: creation failed: error=(\d+)\((\w+)\)", 15, since=tag)
    d.result("deny: session refused", failed is not None and failed.group(2) == "PERMISSION_DENIED",
             failed.group(0) if failed else "no failure logged")
    # 2. Lock screen: a PIN, the screen locked, then the request.
    d.sh("locksettings set-pin 1234")
    tag = d.mark("locked")
    d.lab("REQUEST", targets=SETTINGS, launch=DARK_THEME, delayMs=6000)
    time.sleep(1)
    d.sh("input keyevent KEYCODE_SLEEP")
    time.sleep(2)
    d.sh("input keyevent KEYCODE_WAKEUP")
    time.sleep(1)
    d.write("refuse-locked-keyguard.txt", d.sh("dumpsys window | grep -iE 'keyguard|showing' | head -20"))
    d.screencap("refuse-locked.png")
    failed = d.wait_log(r"cc: creation failed: error=(\d+)\((\w+)\)", 20, since=tag)
    d.result("lock screen: session refused", failed is not None and failed.group(2) == "DEVICE_LOCKED",
             failed.group(0) if failed else "no failure logged")
    d.sh("locksettings clear --old 1234")
    d.sh("wm dismiss-keyguard")
    d.sh("input keyevent KEYCODE_WAKEUP")
    time.sleep(2)
    d.sh(f"am start -W -n {QUIRE}/.control.ControlActivity")
    time.sleep(2)
    # 3. An app outside the allowlist.
    tag = d.mark("not-allowlisted")
    d.lab("REQUEST", targets="com.android.calendar", launch="com.android.calendar")
    refused = d.wait_log(r"cc: request refused by the platform: (.*)", 10, since=tag)
    d.result("app outside the allowlist refused", refused is not None and "Invalid target package" in refused.group(1),
             refused.group(1) if refused else "not refused")
    # 4. A FLAG_SECURE window on the session display. The probe is allowlisted through DeviceConfig for this check only.
    d.run("install", "-r", "-g", str(d.probe))
    d.sh(f"device_config put computer_control allowed_automatable_apps "
         f"'{SETTINGS}:PREINSTALLED,{PROBE}:{TESTKEY_DIGEST}'")
    time.sleep(2)
    tag = d.mark("secure")
    d.lab("REQUEST", targets=PROBE, launch=PROBE)
    ok, title = consent(d, "allow_button")
    d.result("secure: consent given", ok, title)
    created = d.wait_log(r"cc: created", 20, since=tag)
    d.result("secure: session created for the probe", created is not None, "created" if created else "not created")
    blocked = d.wait_log(r"cc: lifecycle: blocked reason=(\d+)\((\w+)\) package=(\S+)", 20, since=tag)
    d.result("secure: session blocked on the secure window", blocked is not None and blocked.group(2) ==
             "SECURE_CONTENT" and blocked.group(3) == PROBE, blocked.group(0) if blocked else "never blocked")
    time.sleep(2)
    d.screencap("refuse-secure-mirror.png")
    t2 = d.mark("secure-tap")
    d.lab("TAP", x=100, y=100)
    time.sleep(2)
    server = d.sh("logcat -d -s ComputerControlSession:W | tail -20")
    d.write("refuse-secure-server-log.txt", server)
    d.result("secure: input refused while blocked", "interaction blocked since session is not active: tap" in server,
             next((l for l in server.splitlines() if "interaction blocked" in l), "no server refusal logged"))
    d.lab("SCREENSHOT")
    time.sleep(3)
    d.lab("CLOSE")
    closed = d.wait_log(r"cc: lifecycle: closed reason=(\d+)\((\w+)\)", 10, since=t2)
    d.result("secure: session closed", closed is not None, closed.group(0) if closed else "not closed")
    d.write("refuse-log.txt", d.quire_log())
    # Restore the device's own allowlist: delete the persisted copy of the test value, then the DeviceConfig value.
    d.sh("rm -f /data/system/computercontrol/automatable_app_allowlist.txt")
    d.sh("device_config delete computer_control allowed_automatable_apps")
    time.sleep(2)
    tag = d.mark("restored")
    d.lab("REQUEST", targets=PROBE, launch=PROBE)
    refused = d.wait_log(r"cc: request refused by the platform: (.*)", 10, since=tag)
    d.result("allowlist restored (probe refused again)", refused is not None and "Invalid target package" in
             refused.group(1), refused.group(1) if refused else "not refused")
    d.sh(f"pm uninstall {PROBE}")


# --------------------------------------------------------------------------------------------------------------------
def health(d, sysui_pid):
    d.log("== health")
    crash = d.sh("logcat -d -b crash")
    d.write("logcat-crash.txt", crash)
    fatal = sorted(set(re.findall(r"Process: [\w.:]+|signal \d+ \(SIG\w+\)", crash)))
    d.result("crash buffer empty", not crash.strip(), f"{len(crash.splitlines())} lines; {', '.join(fatal[:6])}")
    events = d.sh("logcat -d -b events | grep -E 'am_crash|am_anr|am_native_crash|am_proc_died.*systemui'")
    d.write("events-crash-anr.txt", events)
    d.result("no ANR", "am_anr" not in events, f"am_anr events: {events.count('am_anr')}")
    pid = d.sh("pidof com.android.systemui").strip()
    d.result("no SystemUI restart", pid == sysui_pid and "systemui" not in events,
             f"pid at start {sysui_pid}, now {pid}")
    tomb = d.sh("ls -l /data/tombstones /data/anr 2>&1")
    d.write("anr-tombstones.txt", tomb)
    denials = d.sh("logcat -d -b all | grep 'avc:  denied' | grep -v 'service requested' | "
                   "sed -E 's/.*avc:  denied/avc: denied/; s/ pid=[0-9]+//; s/ ino=[0-9]+//' | sort | uniq -c | sort -rn")
    d.write("selinux-denials.txt", denials)
    new = [l for l in denials.splitlines() if l.strip() and not any(k in l for k in KNOWN_DENIALS)]
    d.result("no new SELinux denials", not new, f"{len(denials.splitlines())} distinct, {len(new)} new" +
             (": " + " | ".join(n.strip() for n in new[:4]) if new else ""))
    quire_denials = [l for l in denials.splitlines() if "quire" in l or "platform_app" in l]
    d.result("no denial for Quire (platform_app)", not quire_denials, f"{len(quire_denials)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("serial")
    ap.add_argument("outdir")
    ap.add_argument("--probe", required=True, type=Path)
    ap.add_argument("--only", default="facts,invoke,control,refuse,health")
    a = ap.parse_args()
    d = Dev(a.serial, a.outdir)
    d.probe = a.probe
    d.run("root")
    time.sleep(3)
    d.run("wait-for-device", timeout=60)
    for _ in range(150):
        if d.sh("getprop sys.boot_completed").strip() == "1":
            break
        time.sleep(2)
    d.sh("input keyevent KEYCODE_WAKEUP")
    d.sh("wm dismiss-keyguard")
    sysui_pid = d.sh("pidof com.android.systemui").strip()
    sections = a.only.split(",")
    if "invoke" in sections:
        d.run("install", "-r", "-g", str(a.probe))
    for name in sections:
        if name == "health":
            health(d, sysui_pid)
        else:
            globals()[name](d)
    with open(d.o / "results.tsv", "w") as f:
        f.write("check\tresult\tdetail\n")
        for c, r, det in d.results:
            f.write(f"{c}\t{r}\t{det}\n")
    fails = sum(1 for _, r, _ in d.results if r == "FAIL")
    passes = sum(1 for _, r, _ in d.results if r == "PASS")
    d.log(f"== {passes} PASS, {fails} FAIL, {len(d.results) - passes - fails} INFO")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
