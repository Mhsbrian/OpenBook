#!/usr/bin/env python3
"""Targeted desktop checks for the ANAL-204 flag groups (docs/googlebook-flags.md), on a booted OpenBook device.
Run it after scripts/desktop-capture.sh, which leaves Settings and Files open as desktop windows.

  scripts/ui/flag-checks.py SERIAL OUTDIR [--triage device/anybook/common/desktop/release/googlebook-triage.tsv]
  scripts/ui/flag-checks.py SERIAL --reset      # VM only: forget saved desks and recents, reboot, wait

Android 17 restores desk windows and recent tasks after a reboot, and WM Shell remembers window bounds, so runs on
one VM build on each other. --reset (adb root) deletes /data/system_ce/0/recent_tasks and WM Shell's desktop
datastore, then reboots; run it, then scripts/desktop-capture.sh, then the checks.
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
        self.skip = set()

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
    """App tasks: [{id, pkg, bounds, mode, visible}] from `dumpsys activity activities`."""
    out, cur = [], None
    for line in d.sh("dumpsys activity activities").splitlines():
        m = re.match(r"\s+\* Task\{\w+ #(\d+) type=standard (?:A=\d+:|I=)([\w.]+)", line)
        if m and any(t["id"] == int(m.group(1)) for t in out):
            cur = None  # the hierarchy is dumped twice
        elif m:
            v, mode = re.search(r" visible=(\w+)", line), re.search(r" mode=([\w-]+)", line)
            cur = {"id": int(m.group(1)), "pkg": m.group(2), "bounds": None, "mode": mode and mode.group(1),
                   "visible": bool(v) and v.group(1) == "true"}
            out.append(cur)
        elif re.match(r"\s+\* Task\{", line):
            cur = None
        elif cur is not None and cur["bounds"] is None and line.strip().startswith("mBounds="):
            r = RECT.search(line)
            cur["bounds"] = r and tuple(map(int, r.groups()))
    return out


def task_for(d, pkg, settle=True, tid=None, until=None):
    """Task tid, or the first visible task of pkg (else the first). With settle, polled until its bounds and
    visibility hold for 0.8 s, so a transition in flight isn't read; with until(task), polled up to 6 s until
    it holds (a transition that hasn't started yet)."""
    last, t0 = None, time.time()
    while True:
        ts = [t for t in tasks(d) if (t["id"] == tid if tid else t["pkg"].startswith(pkg))]
        cur = next((t for t in ts if t["visible"]), ts[0] if ts else None)
        if until:
            if (cur and until(cur)) or time.time() - t0 > 6:
                return cur
        elif not settle or (cur and last and (cur["bounds"], cur["visible"]) == (last["bounds"], last["visible"])) \
                or time.time() - t0 > 8:
            return cur
        last = cur
        time.sleep(0.8)


def width(t):
    return t["bounds"][2] - t["bounds"][0] if t and t["bounds"] else 0


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


def focused(d):
    m = re.search(r"mCurrentFocus=Window\{\w+ u\d+ ([\w.]+)", d.sh("dumpsys window | grep mCurrentFocus"))
    return m.group(1) if m else ""


# Caption geometry at 160 dpi (px = dp): 48 px tall; buttons centred 32, 88 and 144 px from the right edge
# (close, maximize, minimize); the app chip starts at the left edge. WM Shell's caption views are not in the
# accessibility dump, so they are found by position.
CAPTION_Y, BTN_CLOSE, BTN_MAX, BTN_MIN = 24, 32, 88, 144


def focus(d, m, pkg, tid=None):
    """Click the window's caption (between the app chip and the buttons) so it comes to the front and key
    gestures go to it; a point in the body may be covered by another window."""
    for _ in range(2):
        t = task_for(d, pkg, tid=tid)
        if t and t["bounds"]:
            l, top, r, b = t["bounds"]
            m.click(max(l + 160, (l + r) // 2 - 60), top + CAPTION_Y)
            time.sleep(0.8)
        if focused(d).startswith(pkg.split(".root")[0]):
            return True
    return False


def instances(d, pkg):
    return [f"#{t['id']}{'' if t['visible'] else ' (hidden)'}" for t in tasks(d) if t["pkg"].startswith(pkg)]


def check_windows(d, m):
    pkg = "com.android.documentsui"
    t = task_for(d, pkg)
    if not t or not t["bounds"]:
        d.result("windows", False, "no Files task with bounds (did desktop-capture.sh run?)")
        return
    tid = t["id"]
    d.result("windows: start", None, f"task #{tid} {t['pkg']} mode={t['mode']} bounds={t['bounds']}")
    d.save("activities-start.txt", "dumpsys activity activities")
    l, top, r, b = t["bounds"]
    d.result("focus (click into the window)", focus(d, m, pkg, tid), f"mCurrentFocus={focused(d)}")
    d.shot("window-focused")
    # Move: drag the caption up and left, so the whole window stays on screen.
    dx, dy = (-150 if l > 200 else 150), (-80 if top > 120 else 80)
    m.drag(l + (r - l) // 3, top + CAPTION_Y, l + (r - l) // 3 + dx, top + CAPTION_Y + dy)
    t2 = task_for(d, pkg, tid=tid)
    got = t2 and t2["bounds"] and (t2["bounds"][0] - l, t2["bounds"][1] - top)
    d.result("move (caption drag)", bool(got and abs(got[0] - dx) < 30 and abs(got[1] - dy) < 30),
             f"bounds {t['bounds']} -> {t2 and t2['bounds']}")
    d.shot("window-moved")
    # Resize: drag the bottom-right corner, outwards if there is room, else inwards.
    l, top, r, b = t2["bounds"]
    gx, gy = (120 if r + 120 < 1910 else -120), (80 if b + 80 < 1010 else -80)
    m.drag(r - 3, b - 3, r - 3 + gx, b - 3 + gy)
    t3 = task_for(d, pkg, tid=tid)
    dw = t3 and t3["bounds"] and ((t3["bounds"][2] - t3["bounds"][0]) - (r - l), (t3["bounds"][3] - t3["bounds"][1]) - (b - top))
    d.result("resize (corner drag)", bool(dw and abs(dw[0] - gx) < 40 and abs(dw[1] - gy) < 40),
             f"bounds {t2['bounds']} -> {t3 and t3['bounds']}")
    d.shot("window-resized")
    # Below the minimum size: with enable_no_resize_cursor WM Shell reports the violation and shows a
    # no-resize cursor (resolvedPointerType changes while the drag is held).
    l, top, r, b = t3["bounds"]
    held = m.drag(r - 3, b - 3, l + 40, top + 40,
                  hold=lambda: (time.sleep(0.5), pointer_type(d), d.shot("resize-below-minimum"))[1])
    t4 = task_for(d, pkg, tid=tid)
    d.result("no-resize cursor (drag below minimum size)", None,
             f"resolvedPointerType while held: {held} (1000 = arrow); bounds after: {t4 and t4['bounds']}")
    # App chip (left of the caption): the handle menu with the windowing options.
    l, top, r, b = t4["bounds"]
    m.click(l + 60, top + CAPTION_Y)
    time.sleep(1.5)
    d.shot("app-handle-menu")
    d.key("KEYCODE_ESCAPE")
    time.sleep(0.8)
    # Hover the maximize button: the maximize/layout menu.
    m.move_to(r - BTN_MAX, top + CAPTION_Y)
    time.sleep(2.5)
    d.shot("maximize-button-hover")
    m.move_to((l + r) // 2, min(b - 20, top + 200))
    d.key("KEYCODE_ESCAPE")
    time.sleep(0.8)
    # Maximize and restore with Meta+= (KEY_GESTURE_TYPE_TOGGLE_MAXIMIZE_FREEFORM_WINDOW).
    focus(d, m, pkg, tid)
    d.key("KEYCODE_META_LEFT", "KEYCODE_EQUALS")
    time.sleep(1.5)
    t5 = task_for(d, pkg, tid=tid, until=lambda t: width(t) >= 1900)
    d.shot("window-maximized")
    wide = t5 and t5["bounds"] and (t5["bounds"][2] - t5["bounds"][0]) >= 1900
    d.result("maximize (Meta+=)", bool(wide), f"bounds {t4['bounds']} -> {t5 and t5['bounds']}")
    d.key("KEYCODE_META_LEFT", "KEYCODE_EQUALS")
    time.sleep(1.5)
    t6 = task_for(d, pkg, tid=tid, until=lambda t: 0 < width(t) < 1900)
    d.result("restore (Meta+= again)", bool(t6 and t6["bounds"] and (t6["bounds"][2] - t6["bounds"][0]) < 1900),
             f"bounds -> {t6 and t6['bounds']}")
    # Maximize with the caption button, then restore with a double click on the caption.
    l, top, r, b = t6["bounds"]
    m.click(r - BTN_MAX, top + CAPTION_Y)
    time.sleep(1.5)
    t7 = task_for(d, pkg, tid=tid, until=lambda t: width(t) >= 1900)
    d.result("maximize (caption button)", bool(t7 and t7["bounds"] and (t7["bounds"][2] - t7["bounds"][0]) >= 1900),
             f"bounds -> {t7 and t7['bounds']}")
    if t7 and t7["bounds"]:
        m.click((t7["bounds"][0] + t7["bounds"][2]) // 2, t7["bounds"][1] + CAPTION_Y, double=True)
        time.sleep(1.5)
    t8 = task_for(d, pkg, tid=tid, until=lambda t: 0 < width(t) < 1900)
    d.result("restore (caption double click)", None, f"bounds -> {t8 and t8['bounds']}")
    if "minimize" in d.skip:
        return
    # Minimize with the caption button; the taskbar icon brings it back.
    l, top, r, b = t8["bounds"]
    m.click(r - BTN_MIN, top + CAPTION_Y)
    time.sleep(1.5)
    d.shot("window-minimized")
    t9 = task_for(d, pkg, tid=tid, until=lambda t: t["visible"] is False)
    d.result("minimize (caption button)", bool(t9 and t9["visible"] is False), f"task visible={t9 and t9['visible']}")
    d.save("wmshell-after-minimize.txt", "dumpsys activity service SystemUIService WMShell")
    nodes = ui_nodes(d, "ui-taskbar.xml")
    icon = find(nodes, **{"content-desc": "^Files", "package": "launcher3"})
    if icon:
        m.click(*center(icon["rect"]))
        time.sleep(1.5)
        t10 = task_for(d, pkg, tid=tid, until=lambda t: t["visible"])
        d.shot("taskbar-click-restores")
        d.result("taskbar click restores the minimized window", bool(t10 and t10["visible"]),
                 f"icon {icon['rect']}, task visible={t10 and t10['visible']}")
        # Click the icon of the focused, visible window: AOSP 17 brings it to front; click-to-minimize is
        # enable_taskbar_icon_desktop_clicks, which has no reader in AOSP 17.
        m.click(*center(icon["rect"]))
        time.sleep(1.5)
        t11 = task_for(d, pkg, tid=tid)
        d.result("taskbar click on the focused window", None,
                 f"task visible={t11 and t11['visible']}; Files tasks: {', '.join(instances(d, pkg))}")
        m.click(*center(icon["rect"]), b="BTN_RIGHT")
        time.sleep(1.5)
        d.shot("taskbar-right-click-menu")
        d.result("taskbar icon menu (right click)", None, "screenshot")
        d.key("KEYCODE_ESCAPE")
        time.sleep(0.5)
    else:
        d.result("taskbar click restores the minimized window", False, "no taskbar icon labelled Files")
    # Minimize with Meta+- .
    focus(d, m, pkg, tid)
    d.key("KEYCODE_META_LEFT", "KEYCODE_MINUS")
    time.sleep(1.5)
    t12 = task_for(d, pkg, tid=tid, until=lambda t: t["visible"] is False)
    d.result("minimize (Meta+-)", bool(t12 and t12["visible"] is False),
             f"task visible={t12 and t12['visible']}; focus was {focused(d)}; Files tasks: {', '.join(instances(d, pkg))}")
    if icon:
        m.click(*center(icon["rect"]))
        time.sleep(1.5)


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


def check_notifications(d, m):
    """Hover and right-click a notification in the shade (inline_notification_settings_access opens its
    settings on a context click; notification_add_x_on_hover_to_dismiss, on since ANAL-169, shows an X)."""
    # As the shell user: with adbd running as root the post comes from uid 0 and NotificationService drops it.
    d.sh("su shell cmd notification post -t 'B3 hover test' b3hover 'A notification to hover and right-click' >/dev/null")
    d.sh("cmd statusbar expand-notifications")
    time.sleep(2)
    row = find(ui_nodes(d, "ui-shade.xml"), **{"package": "systemui", "text": "B3 hover test"})
    if not row:
        d.result("notification hover", None, "no notification row in the shade dump")
        d.shot("shade-notification")
    else:
        x, y = center(row["rect"])
        m.move_to(x + 200, y + 10)
        time.sleep(1.5)
        d.shot("notification-hover")
        d.result("notification hover", None, f"row {row['rect']}: screenshot")
        m.click(x + 200, y + 10, b="BTN_RIGHT")
        time.sleep(1.5)
        d.shot("notification-right-click")
        guts = [n for n in ui_nodes(d, "ui-notification-right-click.xml")
                if re.search(r"Turn off notifications|Settings|Default|Silent|Done", n.get("text", "")) and "systemui" in n.get("package", "")]
        d.result("notification right click (inline settings)", None, f"settings-like nodes after right click: {len(guts)}")
        d.key("KEYCODE_ESCAPE")
    d.sh("cmd statusbar collapse")
    time.sleep(1)


def sf_blur_layers(d, name):
    """Names of the layers SurfaceFlinger blurs behind (backgroundBlurRadius > 0)."""
    sf = d.sh("dumpsys SurfaceFlinger")
    (d.o / name).write_text(sf)
    layers, cur = set(), None
    for line in sf.splitlines():
        m = re.match(r"\s*Layer \[\d+\] (.+?)#\d+", line)
        if m:
            cur = m.group(1)
        r = re.search(r"backgroundBlurRadius=([1-9]\d*)", line)
        if r and cur:
            layers.add(f"{cur} ({r.group(1)})")
    return ", ".join(sorted(layers)) or "none"


def check_blur(d, m):
    """Power menu (from the Quick Settings power button) and volume dialog: blur_on_more_surfaces."""
    d.sh("cmd statusbar expand-settings")
    time.sleep(2)
    power = find(ui_nodes(d, "ui-qs-power.xml"), **{"package": "systemui", "content-desc": "^Power"})
    if power:
        m.click(*center(power["rect"]))
        time.sleep(2)
        d.shot("power-menu")
        d.result("power menu blur", None, f"blurred layers: {sf_blur_layers(d, 'sf-power-menu.txt')}")
        d.key("KEYCODE_ESCAPE")
        time.sleep(1)
    else:
        d.result("power menu blur", None, "no power button in the Quick Settings dump")
    d.sh("cmd statusbar collapse")
    time.sleep(1)
    d.key("KEYCODE_VOLUME_UP")
    time.sleep(1)
    d.shot("volume-dialog")
    d.result("volume dialog blur", None, f"blurred layers: {sf_blur_layers(d, 'sf-volume.txt')}")
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
    denials = d.sh("logcat -d -b all | grep 'avc:  denied' | grep -v 'service requested' | sed -E 's/.*avc:  denied/avc: denied/; s/ pid=[0-9]+//; s/ ino=[0-9]+//' | sort | uniq -c | sort -rn")
    (d.o / "selinux-denials.txt").write_text(denials)
    fatal = re.findall(r"FATAL EXCEPTION|Process: [\w.:]+|signal \d+ \(SIG\w+\)", crash)
    n_anr = len(re.findall(r"am_anr", events))
    d.result("crash buffer", not crash.strip(), f"{len(crash.splitlines())} lines; {', '.join(sorted(set(fatal))[:6])}")
    d.result("ANRs", n_anr == 0, f"am_anr events: {n_anr}")
    d.result("SELinux denials", None, f"{len(denials.splitlines())} distinct")


def reset(d):
    d.run("root")
    time.sleep(2)
    d.run("wait-for-device", timeout=60)
    d.sh("rm -f /data/system_ce/0/recent_tasks/* /data/user_de/0/com.android.systemui/files/datastore/desktop*")
    d.run("reboot")
    time.sleep(15)
    d.run("wait-for-device", timeout=300)
    for _ in range(100):
        if d.sh("getprop sys.boot_completed").strip() == "1":
            return True
        time.sleep(3)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("serial")
    ap.add_argument("out", nargs="?", default="")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--triage", default=str(Path(__file__).resolve().parents[2] /
                                           "device/anybook/common/desktop/release/googlebook-triage.tsv"))
    ap.add_argument("--skip", default="", help="comma-separated: windows,minimize,cascade,shade,notifications,blur")
    a = ap.parse_args()
    if a.reset:
        ok = reset(Dev(a.serial, Path.home() / ".cache/flag-checks"))
        print("reset: boot completed" if ok else "reset: no boot", flush=True)
        raise SystemExit(0 if ok else 1)
    d = Dev(a.serial, a.out)
    skip = d.skip = set(a.skip.split(","))
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
        if "notifications" not in skip:
            check_notifications(d, m)
        if "blur" not in skip:
            check_blur(d, m)
    finally:
        m.close()
    d.save("wmshell.txt", "dumpsys activity service SystemUIService WMShell")
    check_health(d)
    (d.o / "results.tsv").write_text("check\tresult\tdetail\n" + "".join(f"{c}\t{r}\t{x}\n" for c, r, x in d.results))


if __name__ == "__main__":
    main()
