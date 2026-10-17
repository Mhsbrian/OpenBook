#!/usr/bin/env python3
"""Targeted desktop checks for the ANAL-204 flag groups (docs/googlebook-flags.md), on a booted OpenBook device.
Run it after scripts/desktop-capture.sh, which leaves Settings and Files open as desktop windows.

  scripts/ui/flag-checks.py SERIAL OUTDIR [--triage device/anybook/common/desktop/release/googlebook-triage.tsv]
Env: ADB (default ~/anybook/android-sdk/platform-tools/adb); ANDROID_ADB_SERVER_PORT for a private adb server.

Input goes through a virtual USB mouse made with the device's `uinput -` tool, so WM Shell, Launcher and SystemUI
see real mouse hovers, clicks and drags. The cursor is steered in a loop: move, read where the last mouse event
landed from `dumpsys input`, correct. Pointer acceleration doesn't matter that way.

Writes to OUTDIR: checks.log, results.tsv (check, result, detail), flag-state.tsv (each flag the triage enables:
group, state on the device), NN-*.png screenshots, and dumps (crash/ANR/denial summaries, SurfaceFlinger, WM Shell).
A check reports PASS, FAIL or INFO (observed, nothing to compare); a missing UI element is reported, not fatal.
"""
import argparse
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path


class Dev:
    def __init__(self, serial, out):
        self.adb = os.environ.get("ADB", str(Path.home() / "anybook/android-sdk/platform-tools/adb"))
        self.s, self.o, self.n = serial, Path(out), 0
        self.o.mkdir(parents=True, exist_ok=True)
        self.results = []

    def run(self, *args, timeout=120, text=True):
        return subprocess.run([self.adb, "-s", self.s, *args], capture_output=True, text=text, timeout=timeout)

    def sh(self, cmd, timeout=120):
        return self.run("shell", cmd, timeout=timeout).stdout.replace("\r", "")

    def log(self, msg):
        line = f"=== {time.strftime('%H:%M:%S')} {msg}"
        print(line, flush=True)
        with open(self.o / "checks.log", "a") as f:
            f.write(line + "\n")

    def shot(self, name):
        self.n += 1
        p = self.o / f"{self.n:02d}-{name}.png"
        p.write_bytes(self.run("exec-out", "screencap", "-p", text=False).stdout)
        return p.name

    def save(self, name, cmd):
        (self.o / name).write_text(self.sh(cmd))
        return self.o / name

    def result(self, check, ok, detail):
        r = "INFO" if ok is None else ("PASS" if ok else "FAIL")
        self.results.append((check, r, detail))
        self.log(f"{r} {check}: {detail}")

    def key(self, *codes):
        self.sh("input keycombination " + " ".join(codes) if len(codes) > 1 else f"input keyevent {codes[0]}")


class Mouse:
    """A virtual relative mouse (`uinput -` on the device), steered against the last event's coordinates."""
    NAME = "AnyBook B3 Test Mouse"

    def __init__(self, dev):
        self.d = dev
        self.p = subprocess.Popen([dev.adb, "-s", dev.s, "shell", "uinput", "-"], stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        self.send({"id": 1, "command": "register", "name": self.NAME, "vid": 0x18d1, "pid": 0xb3b3, "bus": "usb",
                   "configuration": [{"type": "UI_SET_EVBIT", "data": ["EV_KEY", "EV_REL"]},
                                     {"type": "UI_SET_KEYBIT", "data": ["BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE"]},
                                     {"type": "UI_SET_RELBIT", "data": ["REL_X", "REL_Y", "REL_WHEEL"]},
                                     {"type": "UI_SET_PROPBIT", "data": ["INPUT_PROP_POINTER"]}]})
        for _ in range(30):
            time.sleep(1)
            if self.NAME in dev.sh("dumpsys input | grep -F '" + self.NAME + "'"):
                break
        time.sleep(1)
        self.send({"id": 1, "command": "updateTimeBase"})
        self.buttons = set()

    def send(self, obj):
        import json
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()

    def ev(self, *events):
        self.send({"id": 1, "command": "inject", "events": list(events) + ["EV_SYN", "SYN_REPORT", 0]})

    def pos(self):
        """Coordinates of the newest event from this mouse in InputDispatcher's recent queue, or None."""
        dump = self.d.sh("dumpsys input")
        dev_id = None
        m = re.search(r"Device (\d+): " + re.escape(self.NAME), dump)
        if m:
            dev_id = m.group(1)
        last = None
        for line in dump.splitlines():
            if "MotionEvent" in line and "source=MOUSE" in line and (dev_id is None or f"deviceId={dev_id}," in line):
                c = re.search(r"\(([-\d.]+), ([-\d.]+)\)", line)
                if c:
                    last = (float(c.group(1)), float(c.group(2)))
        return last

    def nudge(self, dx, dy):
        while dx or dy:
            sx, sy = max(-60, min(60, dx)), max(-60, min(60, dy))
            self.ev("EV_REL", "REL_X", sx, "EV_REL", "REL_Y", sy)
            dx, dy = dx - sx, dy - sy
            time.sleep(0.02)

    def move_to(self, x, y, tol=3):
        x, y = int(x), int(y)
        for _ in range(12):
            self.nudge(1, 0)  # make sure there is a recent event to read
            time.sleep(0.15)
            p = self.pos()
            if p is None:
                self.nudge(-3000, -3000)
                continue
            ex, ey = x - p[0], y - p[1]
            if abs(ex) <= tol and abs(ey) <= tol:
                return p
            # Relative counts map to pixels with gain >= 1; undershoot and iterate.
            self.nudge(int(ex * 0.7) or (1 if ex > 0 else -1), int(ey * 0.7) or (1 if ey > 0 else -1))
            time.sleep(0.15)
        return self.pos()

    def button(self, b, down):
        self.ev("EV_KEY", b, 1 if down else 0)
        time.sleep(0.08)

    def click(self, x, y, b="BTN_LEFT", double=False):
        self.move_to(x, y)
        for _ in range(2 if double else 1):
            self.button(b, True)
            self.button(b, False)

    def drag(self, x0, y0, x1, y1, hold=None):
        """Press at (x0, y0), move to (x1, y1) in steps, release. hold(): called before release."""
        self.move_to(x0, y0)
        self.button("BTN_LEFT", True)
        time.sleep(0.3)
        p = self.pos() or (x0, y0)
        for i in range(1, 9):
            t = self.pos() or p
            self.nudge(int((x0 + (x1 - x0) * i / 8) - t[0]), int((y0 + (y1 - y0) * i / 8) - t[1]))
            time.sleep(0.1)
        r = hold() if hold else None
        self.button("BTN_LEFT", False)
        time.sleep(0.8)
        return r

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(10)
        except Exception:
            self.p.kill()


# ---------------------------------------------------------------- device state helpers
RECT = re.compile(r"Rect\((-?\d+), (-?\d+) - (-?\d+), (-?\d+)\)")


def tasks(d):
    """Visible freeform/fullscreen app tasks: [{id, pkg, bounds, mode, visible}] from `dumpsys activity activities`."""
    out, cur = [], None
    for line in d.sh("dumpsys activity activities").splitlines():
        m = re.match(r"\s+\* Task\{\w+ #(\d+) type=standard (?:A|I)=[\d:]*([\w.]+)", line)
        if m:
            cur = {"id": int(m.group(1)), "pkg": m.group(2), "bounds": None, "mode": None, "visible": None}
            out.append(cur)
            continue
        if cur is None:
            continue
        if cur["bounds"] is None and "mBounds=" in line:
            r = RECT.search(line.split("mBounds=", 1)[1])
            if r:
                cur["bounds"] = tuple(map(int, r.groups()))
        m = re.search(r"mWindowingMode=(\w+)", line)
        if m and cur["mode"] is None:
            cur["mode"] = m.group(1)
        m = re.search(r"\bisVisible=(\w+)|\bvisible=(true|false)", line)
        if m and cur["visible"] is None:
            cur["visible"] = (m.group(1) or m.group(2)) == "true"
    return out


def task_for(d, pkg):
    for t in tasks(d):
        if t["pkg"].startswith(pkg):
            return t
    return None


def ui_nodes(d, name="ui.xml"):
    """All nodes of `uiautomator dump --windows` (every window on every display)."""
    d.sh("uiautomator dump --windows /data/local/tmp/b3-ui.xml >/dev/null 2>&1")
    xml = d.sh("cat /data/local/tmp/b3-ui.xml")
    (d.o / name).write_text(xml)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    nodes = []
    for n in root.iter("node"):
        b = re.match(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", n.get("bounds", ""))
        if b:
            nodes.append(dict(n.attrib, rect=tuple(map(int, b.groups()))))
    return nodes


def find(nodes, **kw):
    for n in nodes:
        if all(re.search(v, n.get(k, "") or "", re.I) for k, v in kw.items()):
            return n
    return None


def center(r):
    return ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)


def pointer_type(d):
    m = re.findall(r"resolvedPointerType: (-?\d+)", d.sh("dumpsys input"))
    return m[-1] if m else "?"


# ---------------------------------------------------------------- checks
def check_flags(d, triage):
    aflags = d.sh("aflags list 2>&1")
    (d.o / "aflags.txt").write_text(aflags)
    state = {}
    for line in aflags.splitlines():
        t = line.split()
        if len(t) >= 2 and t[1] in ("enabled", "disabled"):
            state[t[0]] = t[1]
    rows = ["flag\tgroup\tstate"]
    by_group = {}
    for line in Path(triage).read_text().splitlines()[1:]:
        r = line.split("\t")
        if r[5] != "enable":
            continue
        st = state.get(r[0], "absent (compiled out: disabled)")
        rows.append(f"{r[0]}\t{r[6]}\t{st}")
        by_group.setdefault(r[6], []).append(st == "enabled")
    (d.o / "flag-state.tsv").write_text("\n".join(rows) + "\n")
    d.result("flag state", None, "; ".join(f"group {g}: {sum(v)}/{len(v)} enabled" for g, v in sorted(by_group.items())))


def check_windows(d, m):
    t = task_for(d, "com.android.documentsui") or task_for(d, "com.android.settings")
    if not t or not t["bounds"]:
        d.result("windows", False, "no app task with bounds (did desktop-capture.sh run?)")
        return
    d.result("windows: start", None, f"task #{t['id']} {t['pkg']} mode={t['mode']} bounds={t['bounds']}")
    d.save("activities-start.txt", "dumpsys activity activities")
    l, top, r, b = t["bounds"]
    # Focus the window first: click its caption.
    m.click(l + (r - l) // 3, top + 18)
    time.sleep(1)
    d.shot("window-focused")
    # Move: drag the caption.
    m.drag(l + (r - l) // 3, top + 18, l + (r - l) // 3 - 160, top + 18 + 90)
    t2 = task_for(d, t["pkg"])
    moved = t2 and t2["bounds"] and (t2["bounds"][0] - l, t2["bounds"][1] - top)
    d.result("move (caption drag)", bool(moved and abs(moved[0] + 160) < 30 and abs(moved[1] - 90) < 30),
             f"bounds {t['bounds']} -> {t2 and t2['bounds']}")
    d.shot("window-moved")
    # Resize: drag the bottom-right corner outwards.
    l, top, r, b = t2["bounds"]
    m.drag(r - 2, b - 2, r + 140, b + 100)
    t3 = task_for(d, t["pkg"])
    grown = t3 and t3["bounds"] and ((t3["bounds"][2] - t3["bounds"][0]) - (r - l), (t3["bounds"][3] - t3["bounds"][1]) - (b - top))
    d.result("resize (corner drag)", bool(grown and grown[0] > 60 and grown[1] > 40), f"bounds {t2['bounds']} -> {t3 and t3['bounds']}")
    d.shot("window-resized")
    # Resize below the minimum size: the no-resize cursor shows while the drag violates the size limits.
    l, top, r, b = t3["bounds"]
    seen = m.drag(r - 2, b - 2, l + 60, top + 60, hold=lambda: (time.sleep(0.4), pointer_type(d), d.shot("resize-too-small"))[1:])
    d.result("no-resize cursor (drag below minimum size)", None, f"resolvedPointerType while dragging: {seen[0]}")
    t4 = task_for(d, t["pkg"])
    # Maximize and restore with Meta+= (KEY_GESTURE_TYPE_TOGGLE_MAXIMIZE_FREEFORM_WINDOW).
    d.key("KEYCODE_META_LEFT", "KEYCODE_EQUALS")
    time.sleep(1.5)
    t5 = task_for(d, t["pkg"])
    d.shot("window-maximized")
    wide = t5 and t5["bounds"] and (t5["bounds"][2] - t5["bounds"][0]) >= 1800
    d.result("maximize (Meta+=)", bool(wide), f"bounds {t4 and t4['bounds']} -> {t5 and t5['bounds']}")
    d.key("KEYCODE_META_LEFT", "KEYCODE_EQUALS")
    time.sleep(1.5)
    t6 = task_for(d, t["pkg"])
    d.result("restore (Meta+= again)", bool(t6 and t6["bounds"] and (t6["bounds"][2] - t6["bounds"][0]) < 1800),
             f"bounds -> {t6 and t6['bounds']}")
    # Maximize button hover: opens the maximize/layout menu.
    nodes = ui_nodes(d, "ui-windows.xml")
    mx = find(nodes, **{"resource-id": "maximize_window|maximize_button"})
    if mx:
        m.move_to(*center(mx["rect"]))
        time.sleep(2.5)
        d.shot("maximize-button-hover")
        menu = find(ui_nodes(d, "ui-maximize-menu.xml"), **{"resource-id": "maximize_menu|windowing_pill|layout_menu|snap"})
        d.result("maximize menu on hover", None, f"menu node: {menu and menu.get('resource-id')}")
        m.move_to(960, 540)
        d.key("KEYCODE_ESCAPE")
    else:
        d.result("maximize menu on hover", None, "maximize button not found in the UI dump")
    # Minimize with Meta+- and bring it back from the taskbar.
    d.key("KEYCODE_META_LEFT", "KEYCODE_MINUS")
    time.sleep(1.5)
    d.shot("window-minimized")
    t7 = task_for(d, t["pkg"])
    d.result("minimize (Meta+-)", t7 is not None and t7["visible"] is False, f"task visible={t7 and t7['visible']}")
    d.save("wmshell-after-minimize.txt", "dumpsys activity service SystemUIService WMShell")
    nodes = ui_nodes(d, "ui-taskbar.xml")
    label = "Files" if "documentsui" in t["pkg"] else "Settings"
    icon = find(nodes, **{"content-desc": f"^{label}", "package": "launcher3"}) or find(nodes, **{"content-desc": f"^{label}"})
    if icon:
        m.click(*center(icon["rect"]))
        time.sleep(1.5)
        t8 = task_for(d, t["pkg"])
        d.shot("taskbar-click-restores")
        d.result("taskbar click restores the minimized window", bool(t8 and t8["visible"]), f"icon {icon['rect']}, task visible={t8 and t8['visible']}")
        # Right-click: long-press menu.
        m.click(*center(icon["rect"]), b="BTN_RIGHT")
        time.sleep(1.5)
        d.shot("taskbar-right-click-menu")
        d.result("taskbar icon menu (right click)", None, "screenshot")
        d.key("KEYCODE_ESCAPE")
        time.sleep(0.5)
    else:
        d.result("taskbar click restores the minimized window", False, f"no taskbar icon labelled {label}")


def check_cascade(d):
    """Open two more windows; with stepped cascading each new one is offset from the last."""
    before = {t["id"] for t in tasks(d)}
    for act in ("com.android.calendar/.AllInOneActivity", "com.android.deskclock/.DeskClock"):
        d.sh(f"am start -W -n {act} >/dev/null 2>&1")
        time.sleep(2)
    new = [t for t in tasks(d) if t["id"] not in before]
    d.shot("cascade")
    d.result("new window placement (cascade)", None, "; ".join(f"#{t['id']} {t['pkg']} {t['mode']} {t['bounds']}" for t in new))


def check_shade(d, m):
    d.sh("cmd statusbar expand-notifications")
    time.sleep(2)
    d.shot("shade")
    d.sh("cmd statusbar expand-settings")
    time.sleep(2)
    d.shot("quick-settings")
    nodes = ui_nodes(d, "ui-qs.xml")
    tile = find(nodes, **{"package": "systemui", "content-desc": "Internet|Wi.?Fi|Bluetooth"}) or \
        find(nodes, **{"package": "systemui", "text": "Internet|Bluetooth"})
    if tile:
        m.move_to(*center(tile["rect"]))
        time.sleep(2.5)
        d.shot("qs-tile-hover")
        tip = [n for n in ui_nodes(d, "ui-qs-hover.xml") if n.get("class", "").endswith("Popup") or "tooltip" in (n.get("resource-id", "") + n.get("text", "")).lower()]
        d.result("QS tile hover (tooltip)", None, f"tile {tile.get('content-desc') or tile.get('text')} {tile['rect']}; tooltip-like nodes: {len(tip)}")
    else:
        d.result("QS tile hover (tooltip)", None, "no Internet/Bluetooth tile in the UI dump")
    d.sh("cmd statusbar collapse")
    time.sleep(1)


def check_hun(d, m):
    """A DeskClock timer posts a heads-up notification. Hover it and see whether it outlives the decay."""
    d.sh("am start -a android.intent.action.SET_TIMER --ei android.intent.extra.alarm.LENGTH 3 "
         "--ez android.intent.extra.alarm.SKIP_UI true >/dev/null 2>&1")
    deadline, hun = time.time() + 20, None
    while time.time() < deadline and not hun:
        time.sleep(1)
        nodes = ui_nodes(d, "ui-hun.xml")
        hun = find(nodes, **{"package": "systemui", "resource-id": "expandableNotificationRow|notification_headsup|headsup"}) or \
            find(nodes, **{"package": "systemui", "text": "Timer|Time's up"})
    d.shot("heads-up")
    if not hun:
        d.result("heads-up notification hover", None, "no heads-up notification seen")
        return
    m.move_to(*center(hun["rect"]))
    time.sleep(12)
    still = find(ui_nodes(d, "ui-hun-after-hover.xml"), **{"package": "systemui", "text": "Timer|Time's up"})
    d.shot("heads-up-after-12s-hover")
    d.result("heads-up stays while hovered (12 s)", None, f"hun {hun['rect']}; still shown: {bool(still)}")
    m.move_to(960, 700)
    d.sh("am start -a android.intent.action.DISMISS_TIMER >/dev/null 2>&1")
    d.sh("cmd statusbar collapse")


def check_blur(d):
    d.sh("input keyevent --longpress KEYCODE_POWER")
    time.sleep(2)
    d.shot("power-menu")
    sf = d.sh("dumpsys SurfaceFlinger")
    (d.o / "sf-power-menu.txt").write_text(sf)
    blur = len(re.findall(r"(?:backgroundBlurRadius|blurRadius)=([1-9]\d*)", sf))
    d.result("power menu blur", None, f"layers with a blur radius: {blur}")
    d.key("KEYCODE_BACK")
    time.sleep(1)
    d.key("KEYCODE_VOLUME_UP")
    time.sleep(1)
    d.shot("volume-dialog")
    sf = d.sh("dumpsys SurfaceFlinger")
    blur = len(re.findall(r"(?:backgroundBlurRadius|blurRadius)=([1-9]\d*)", sf))
    d.result("volume dialog blur", None, f"layers with a blur radius: {blur}")
    d.key("KEYCODE_VOLUME_DOWN")
    time.sleep(3)


def check_shadows(d):
    sf = d.sh("dumpsys SurfaceFlinger")
    (d.o / "sf-windows.txt").write_text(sf)
    box = len(re.findall(r"[Bb]ox[Ss]hadow", sf))
    rad = len(re.findall(r"shadowRadius=([1-9][\d.]*)", sf))
    d.result("window shadows (SurfaceFlinger)", None, f"'boxShadow' mentions: {box}, layers with shadowRadius>0: {rad}")


def check_health(d):
    crash = d.sh("logcat -d -b crash")
    (d.o / "logcat-crash.txt").write_text(crash)
    events = d.sh("logcat -d -b events | grep -E 'am_crash|am_anr|am_native_crash|am_proc_died.*systemui'")
    (d.o / "events-crash-anr.txt").write_text(events)
    anr = d.sh("ls -l /data/anr 2>&1")
    tomb = d.sh("ls -l /data/tombstones 2>&1")
    (d.o / "anr-tombstones.txt").write_text(f"/data/anr:\n{anr}\n/data/tombstones:\n{tomb}\n")
    denials = d.sh("logcat -d -b all | grep 'avc:  denied' | sed -E 's/.*avc:  denied/avc: denied/; s/ pid=[0-9]+//; s/ ino=[0-9]+//' | sort | uniq -c | sort -rn")
    (d.o / "selinux-denials.txt").write_text(denials)
    fatal = re.findall(r"FATAL EXCEPTION|Process: [\w.:]+|signal \d+ \(SIG\w+\)", crash)
    n_anr = len(re.findall(r"am_anr", events))
    d.result("crash buffer", not crash.strip(), f"{len(crash.splitlines())} lines; {', '.join(sorted(set(fatal))[:6])}")
    d.result("ANRs", n_anr == 0, f"am_anr events: {n_anr}")
    d.result("SELinux denials", None, f"{len(denials.splitlines())} distinct")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("serial")
    ap.add_argument("out")
    ap.add_argument("--triage", default=str(Path(__file__).resolve().parents[2] /
                                           "device/anybook/common/desktop/release/googlebook-triage.tsv"))
    ap.add_argument("--skip", default="", help="comma-separated: windows,cascade,shade,hun,blur")
    a = ap.parse_args()
    d = Dev(a.serial, a.out)
    skip = set(a.skip.split(","))
    d.log(d.sh("getprop ro.build.fingerprint").strip())
    d.sh("settings put system pointer_location 0; input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard")
    check_flags(d, a.triage)
    m = Mouse(d)
    try:
        check_shadows(d)
        if "windows" not in skip:
            check_windows(d, m)
        if "cascade" not in skip:
            check_cascade(d)
        if "shade" not in skip:
            check_shade(d, m)
        if "hun" not in skip:
            check_hun(d, m)
        if "blur" not in skip:
            check_blur(d)
    finally:
        m.close()
    d.save("wmshell.txt", "dumpsys activity service SystemUIService WMShell")
    check_health(d)
    (d.o / "results.tsv").write_text("check\tresult\tdetail\n" + "".join(f"{c}\t{r}\t{x}\n" for c, r, x in d.results))


if __name__ == "__main__":
    main()
