#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Quire Q5 safety checks (ANAL-219): the regressions for the Checker's three findings on PR #110 (2026-10-18), on a
booted userdebug OpenBook device, normally Cuttlefish.

usage: q5-safety-check.py SERIAL OUTDIR [--only overlay,consent,owner,agents,intake] [--probe APK]

Sections:
  overlay  1. The note and the tray hide under a window that hides overlays (the probe's ProtectedActivity calls
              Window.setHideOverlayWindows(true), as a bank would), and a tap where the card would be reaches that
              window; they show again when it goes.
           2. With the probe hiding nothing, the note's window is the card and its shadow, not the display, and a click
              beside the card reaches the app below without being blocked as an untrusted touch.
  consent  At 1920x1080, and at 1280x800 with the note where there is little room beside the dialog, with Settings (which
           hides overlays) on screen: Quire asks from its waiting activity; while the platform's dialog is up no Quire
           window on screen is above it, the waiting activity is beneath it, and the note is not on screen. "Only this
           time" creates the session, so the platform found Quire on screen without any exemption. While the session
           runs the note (mirror, Pause, Stop) is on screen though Settings hides overlays on both displays; Stop on the
           screen ends it and the note is an ordinary overlay again. "Don't allow" is refused and leaves nothing.
  owner    The exemption belongs to the session's own task (the Checker's recheck, 2026-10-19): with a paused Settings
           session and the protected probe on screen, the session's task keeps its mirror and Stop in view; a new note
           opened by the shake path, while that task runs hidden, is an ordinary overlay and hides under the probe;
           reopening the session's task brings the mirror back; another switch away is ordinary again; after Stop the
           task's own note is ordinary and hides under the probe.
  agents   Two ACP agents that both name their session "session-1" (Agent A, Agent B): each permission request reaches
           only its own agent's task and is shown under that agent's name; Esc on A's card answers A "cancelled" and
           sends session/cancel to A only; Allow on B's card answers B only; with a new task on A (session-1 again),
           closing A's connection fails only that task, and B's run goes on and finishes.
  intake   What an agent that accepts images receives with the prompt (scripts/quire/q5-acp-agent.py's role, played
           here by a small agent that records the prompt): real Meta+Space with a still pointer, and over the desktop;
           the real shake and Meta+Space over the probe's window while Files is on top elsewhere (the window under the
           pointer, named after it, its pixels compared with the screen); made-up calls through the lab (INVOKE) for
           what SystemUI never sends (empty, inverted, off-screen or stale bounds, the pointer outside them, no package,
           a package not on screen, the desktop), and one valid made-up call whose pixels say where they came from.

Reuses q5-cf-check.py's device helpers. Writes OUTDIR/results.tsv, checks.log, screenshots, window dumps and the ACP
payloads the agents received (OUTDIR/intake/*.json and the images they carried).
Env: ADB (default ~/anybook/android-sdk/platform-tools/adb); set ANDROID_ADB_SERVER_PORT for a private server.
"""
import argparse
import base64
import importlib.util
import io
import json
import re
import socket
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("q5cf", HERE / "q5-cf-check.py")
q5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(q5)
Dev, Mouse = q5.Dev, q5.Mouse
QUIRE, SETTINGS = q5.QUIRE, q5.SETTINGS
PROBE = "dev.openbook.quire.secureprobe"
FILES = "com.android.documentsui"
DIALOG = "RequestComputerControlAccessActivity"
WAIT = "ConsentWaitActivity"


# ------------------------------------------------------------------------------------------------ helpers

def windows(d, save=None):
    """`dumpsys window windows` as a list, top of the z-order first: name, frame, on screen, hidden as an overlay,
    system application overlay."""
    text = d.sh("dumpsys window windows")
    if save:
        (d.o / save).parent.mkdir(parents=True, exist_ok=True)
        (d.o / save).write_text(text)
    out, cur = [], None
    for line in text.splitlines():
        m = re.match(r"  Window #(\d+) Window\{\w+ u\d+ (.*)\}:", line)
        if m:
            cur = {"z": int(m.group(1)), "name": m.group(2), "frame": None, "onscreen": False, "hidden": False,
                   "system": False}
            out.append(cur)
            continue
        if not line.startswith("    "):
            cur = None
        if cur is None:
            continue
        f = re.search(r" frame=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", line)
        if f and cur["frame"] is None:
            cur["frame"] = tuple(map(int, f.groups()))
        if "isOnScreen=true" in line:
            cur["onscreen"] = True
        if "mIsForceHiddenNonSystemOverlayWindow=true" in line:
            cur["hidden"] = True
        if "pfl=" in line and "SYSTEM_APPLICATION_OVERLAY" in line:
            cur["system"] = True
    return out


def win(ws, name):
    return next((w for w in ws if w["name"] == name or w["name"].endswith(name) or
                 (name.endswith("/") and w["name"].startswith(name))), None)


def quire_windows(ws):
    return [w for w in ws if w["name"] in ("Quire", "Quire tray") or w["name"].startswith(QUIRE + "/")]


def intersects(a, b):
    return a and b and a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def safe(label):
    """A log marker the shell and sed can carry."""
    return re.sub(r"[^\w .,+()-]", "", label)


def scene(d, *stop):
    """Nothing of Quire's, and none of these apps, on screen. Their tasks are removed, not only stopped: Settings runs
    as the system uid, and a desktop restores a stopped app's task when another app starts."""
    q5.clean(d)
    for p in (SETTINGS, FILES, PROBE) + stop:
        for tid in task_ids(d, p):
            d.sh(f"am stack remove {tid}")
        d.sh(f"am force-stop {p}")
    d.sh("input keyevent KEYCODE_HOME")
    time.sleep(1.0)


def task_ids(d, pkg):
    return re.findall(r"Task\{\w+ #(\d+) type=standard (?:A=\d+:" + re.escape(pkg) + r" |I=" + re.escape(pkg) + r"/)",
                      d.sh("dumpsys activity activities | grep -F 'Task{'"))


def task_id(d, pkg):
    m = task_ids(d, pkg)
    return m[0] if m else None


def place(d, pkg, l, t, r, b):
    """Moves the app's desktop window to [l,t][r,b]."""
    tid = task_id(d, pkg)
    if tid:
        d.sh(f"am task resize {tid} {l} {t} {r} {b}")
        time.sleep(0.8)
    w = win(windows(d), pkg + "/")
    d.log(f"placed {pkg} (task {tid}) at {w and w['frame']}")
    return tid


def glide(mouse, dx, dy, step=4):
    """Moves the pointer by (dx, dy) at about 200 counts/s, below where Android's pointer acceleration starts, so the
    distance on screen is the distance asked."""
    n = max(1, int(max(abs(dx), abs(dy)) / step))
    for i in range(n):
        mouse.move(round(dx * (i + 1) / n) - round(dx * i / n), round(dy * (i + 1) / n) - round(dy * i / n))
        time.sleep(0.02)


def probe_touches(d, tag):
    return re.findall(r"QuireProtectedProbe[^:]*: touch (\d+),(\d+) flags=(0x[0-9a-f]+)",
                      d.sh(f"logcat -d -v time -s QuireProtectedProbe:I Quire:I | sed -n '/{tag}/,$p'"))


def quire_dump(d, path, tries=6):
    """A UI dump that has Quire's nodes in it: a dump fails (empty) while the note's footer ticks, so it is tried again."""
    xml = ""
    for _ in range(tries):
        xml = d.ui(path)
        if q5.quire_texts(d, xml):
            break
        time.sleep(0.7)
    return xml


def tap_quire_text(d, text, timeout=8):
    """Taps the node in Quire's windows whose text or label is [text]."""
    end = time.time() + timeout
    while time.time() < end:
        for n in d.nodes(d.ui()):
            if n.get("package") == QUIRE and text in ((n.get("text") or ""), (n.get("content-desc") or "")):
                d.tap_node(n)
                return True
        time.sleep(0.5)
    return False


class Peer:
    """A minimal ACP agent on this host, reached by Quire through `adb reverse`: answers initialize and session/new
    (always with [session]), records everything it receives, holds session/prompt until the check answers it."""

    def __init__(self, d, name, port, images=False, session="session-1", auto_end=False):
        self.d, self.name, self.port, self.images, self.session, self.auto_end = d, name, port, images, session, auto_end
        self.msgs, self.prompts, self.conn = [], [], None
        self.lock = threading.Condition()
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", port))
        self.server.listen()
        threading.Thread(target=self._accept, daemon=True).start()
        d.run("reverse", f"tcp:{port}", f"tcp:{port}")

    def _accept(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            with self.lock:
                self.conn = conn
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        try:
            for line in conn.makefile("r"):
                msg = json.loads(line)
                with self.lock:
                    self.msgs.append(msg)
                    self.lock.notify_all()
                method, rid = msg.get("method"), msg.get("id")
                if method == "initialize":
                    self.reply(rid, {"protocolVersion": 1, "agentInfo": {"name": self.name, "title": self.name},
                                     "agentCapabilities": {"promptCapabilities": {"image": self.images}}})
                elif method == "session/new":
                    self.reply(rid, {"sessionId": self.session})
                elif method == "session/prompt":
                    with self.lock:
                        self.prompts.append(msg)
                    if self.auto_end:
                        self.reply(rid, {"stopReason": "end_turn"})
        except (OSError, ValueError):
            pass

    def send(self, obj):
        with self.lock:
            c = self.conn
        c.sendall((json.dumps(dict(jsonrpc="2.0", **obj)) + "\n").encode())

    def reply(self, rid, result):
        self.send({"id": rid, "result": result})

    def update(self, session, update):
        self.send({"method": "session/update", "params": {"sessionId": session, "update": update}})

    def wait(self, pred, timeout=10.0, start=0):
        end = time.time() + timeout
        with self.lock:
            while True:
                for m in self.msgs[start:]:
                    if pred(m):
                        return m
                left = end - time.time()
                if left <= 0:
                    return None
                self.lock.wait(left)

    def count(self):
        with self.lock:
            return len(self.msgs)

    def disconnect(self):
        with self.lock:
            c, self.conn = self.conn, None
        if c:
            c.shutdown(socket.SHUT_RDWR)
            c.close()

    def stop(self):
        self.disconnect()
        self.server.close()
        self.d.run("reverse", "--remove", f"tcp:{self.port}")


# ------------------------------------------------------------------------------------------------ overlay

def overlay(d):
    d.log("== overlay")
    scene(d)
    # 1. Under a window that hides overlays.
    d.sh(f"am start -W -n {PROBE}/.ProtectedActivity >/dev/null")
    time.sleep(1.5)
    pw = win(windows(d), f"{PROBE}/{PROBE}.ProtectedActivity")
    if not pw or not pw["frame"]:
        d.result("overlay: probe window", False, "the protected probe did not show")
        return
    pl, pt, pr, pb = pw["frame"]
    at = (pl + 200, pt + 150)
    tag = d.mark("overlay protected")
    d.lab("OPEN", intake="none", x=float(at[0]), y=float(at[1]))
    shown = d.wait_log(r"note: shown task", tag)
    time.sleep(1.5)
    ws = windows(d, "overlay/protected-windows.txt")
    note = win(ws, "Quire")
    d.screencap("overlay/protected.png")
    d.result("overlay: the note under a window that hides overlays", bool(shown) and note is not None and
             note["hidden"] and not note["onscreen"],
             f"Quire window {note and note['frame']} forceHidden={note and note['hidden']} "
             f"onScreen={note and note['onscreen']} (probe {pw['frame']})")
    if note and note["frame"]:
        l, t, r, b = note["frame"]
        cx, cy = (l + r) // 2, (t + b) // 2
        inside = pl <= cx < pr and pt <= cy < pb
        d.sh(f"input tap {cx} {cy}")
        time.sleep(1.0)
        got = [x for x in probe_touches(d, tag) if abs(int(x[0]) - cx) <= 2 and abs(int(x[1]) - cy) <= 2]
        d.result("overlay: a tap where the card would be reaches the protected window", inside and bool(got),
                 f"tap {cx},{cy} -> probe touches {got}")
    q5.clean(d)
    d.lab("TRAY")
    time.sleep(1.2)
    ws = windows(d, "overlay/protected-tray-windows.txt")
    tray = win(ws, "Quire tray")
    d.result("overlay: the tray under a window that hides overlays", tray is not None and tray["hidden"] and
             not tray["onscreen"], f"Quire tray forceHidden={tray and tray['hidden']} onScreen={tray and tray['onscreen']}")
    d.lab("ESC")
    # The note comes back when the protected window goes.
    tag = d.mark("overlay back")
    d.lab("OPEN", intake="none", x=float(at[0]), y=float(at[1]))
    time.sleep(1.5)
    d.sh(f"am force-stop {PROBE}")
    time.sleep(1.5)
    note = win(windows(d), "Quire")
    d.screencap("overlay/after-probe.png")
    d.result("overlay: the note shows again once that window is gone", note is not None and note["onscreen"] and
             not note["hidden"], f"onScreen={note and note['onscreen']} forceHidden={note and note['hidden']}")
    q5.clean(d)

    # 2. The window is the card, and clicks beside it reach the app below.
    d.sh(f"am start -W -n {PROBE}/.ProtectedActivity --ez hide false >/dev/null")
    time.sleep(1.5)
    pw = win(windows(d), f"{PROBE}/{PROBE}.ProtectedActivity")
    pl, pt, pr, pb = pw["frame"]
    tag = d.mark("overlay frame")
    d.lab("OPEN", intake="none", x=float(pl + 200), y=float(pt + 150))
    time.sleep(2.0)
    ws = windows(d, "overlay/frame-windows.txt")
    note = win(ws, "Quire")
    d.screencap("overlay/frame.png")
    frame_bounds = note and note["frame"] and "[%d,%d][%d,%d]" % note["frame"]
    cards = [n for n in d.nodes(quire_dump(d, "overlay/frame.xml")) if n.get("package") == QUIRE and
             n.get("bounds") != frame_bounds]
    if not note or not note["frame"] or not cards:
        d.result("overlay: the note's window is the card", False, "no note window or no card in the UI dump")
        q5.clean(d)
        return
    xs = [list(map(int, re.findall(r"\d+", n.get("bounds")))) for n in cards]
    card = (min(b[0] for b in xs), min(b[1] for b in xs), max(b[2] for b in xs), max(b[3] for b in xs))
    l, t, r, b = note["frame"]
    margin = max(card[0] - l, card[1] - t, r - card[2], b - card[3])
    contains = l <= card[0] and t <= card[1] and r >= card[2] and b >= card[3]
    d.result("overlay: the note's window is the card and its shadow, not the display",
             note["onscreen"] and contains and 0 <= margin <= 40, f"window {note['frame']}, card {card}, "
             f"largest margin {margin} px (display 1920x1080)")
    # Beside the card, inside the probe: the old display-wide window would have taken these.
    spots = [(min(pr - 20, r + 120), min(pb - 20, t + 40)), (pl + 40, min(pb - 20, b + 120))]
    for i, (x, y) in enumerate(spots):
        if l <= x < r and t <= y < b:
            continue
        mark = d.mark(f"overlay beside {i}")
        d.sh(f"input tap {x} {y}")
        time.sleep(1.0)
        got = [g for g in probe_touches(d, mark) if abs(int(g[0]) - x) <= 2 and abs(int(g[1]) - y) <= 2]
        untrusted = "Untrusted touch due to occlusion by " + QUIRE in d.sh(f"logcat -d -v time | sed -n '/{mark}/,$p'")
        d.result(f"overlay: a click beside the card reaches the app below ({x},{y})", bool(got) and not untrusted,
                 f"probe touches {got}; untrusted-touch log {'present' if untrusted else 'absent'}")
        # A click elsewhere hides the note (§3.1): open it again for the next spot.
        d.lab("OPEN", intake="none", x=float(pl + 200), y=float(pt + 150))
        time.sleep(1.5)
    q5.clean(d)
    d.sh(f"am force-stop {PROBE}")


# ------------------------------------------------------------------------------------------------ consent

def consent(d, size=None, at=(1400.0, 300.0), deny=False):
    label = size or "1920x1080"
    d.log(f"== consent ({label})")
    if size:
        d.sh(f"wm size {size}")
        time.sleep(3)
    try:
        scene(d)
        d.sh("am start -W -a android.settings.SOUND_SETTINGS >/dev/null")   # Settings hides overlays
        time.sleep(1.5)
        tag = d.mark(f"consent {label}")
        d.lab("CONTROL", prompt="In Settings, turn on Dark theme", app="Settings", launch=SETTINGS,
              taps=json.dumps(q5.TAPS[:2]), x=at[0], y=at[1], aimMs="15000")
        m = d.wait_log(r"cc: pending: the dialog is open", tag, timeout=15)
        asked = d.wait_log(r"consent: waiting activity on screen", tag, timeout=1)
        time.sleep(1.5)
        ws = windows(d, f"consent/{label}-windows.txt")
        d.screencap(f"consent/{label}.png")
        dialogs = [w for w in ws if DIALOG in w["name"] and w["onscreen"]]
        if not m or not dialogs:
            d.result(f"consent {label}: the platform's dialog", False, "no dialog (" +
                     (m.group(0) if m else "no 'dialog is open' log") + ")")
            return
        top = min(ws.index(w) for w in dialogs)
        box = min((w["frame"] for w in dialogs), key=lambda f: (f[2] - f[0]) * (f[3] - f[1]))
        over = [w for w in quire_windows(ws) if w["onscreen"] and ws.index(w) < top and intersects(w["frame"], box)]
        wait = win(ws, f"{QUIRE}/{QUIRE}.note.{WAIT}")
        note = win(ws, "Quire")
        d.result(f"consent {label}: Quire asked from its waiting activity, with Settings hiding overlays",
                 bool(asked), asked.group(0) if asked else "no 'waiting activity on screen' before the request")
        d.result(f"consent {label}: nothing of Quire's on screen over the dialog", not over,
                 f"dialog {box}; Quire windows above it on screen: {[(w['name'], w['frame']) for w in over]}")
        d.result(f"consent {label}: the waiting activity is beneath the dialog",
                 wait is not None and ws.index(wait) > top,
                 f"waiting activity z={wait and wait['z']}, dialog z={ws[top]['z']}; note on screen="
                 f"{note and note['onscreen']}")
        if deny:
            d.tap_text("Don’t allow") or d.tap_text("Don't allow")
            f = d.wait_log(r"cc: creation failed: error=3\(PERMISSION_DENIED\) dialogShown=true", tag)
            time.sleep(1.5)
            gone = win(windows(d, f"consent/{label}-denied-windows.txt"), f"{QUIRE}/{QUIRE}.note.{WAIT}") is None
            d.screencap(f"consent/{label}-denied.png")
            d.result(f"consent {label}: Don't allow is refused and leaves no waiting activity", bool(f) and gone,
                     (f.group(0) if f else "no refusal") + f"; waiting activity gone={gone}")
            return
        if not d.tap_text("Only this time"):
            d.result(f"consent {label}: Only this time", False, "no button")
            return
        c = d.wait_log(r"cc: created: display (\d+x\d+)", tag, timeout=15)
        d.result(f"consent {label}: Only this time creates the session (Quire was on screen for the platform)",
                 bool(c), c.group(0) if c else "not created")
        s = d.wait_log(r"note: window system overlay", tag)
        aim = d.wait_log(r'note: control aiming at', tag, timeout=15)
        time.sleep(1.0)
        ws = windows(d, f"consent/{label}-session-windows.txt")
        d.screencap(f"consent/{label}-session.png")
        note = win(ws, "Quire")
        hiding = "Hiding System Alert Windows" in (d.o / f"consent/{label}-session-windows.txt").read_text()
        d.result(f"consent {label}: while the session runs, the mirror and Stop are on screen",
                 bool(s) and bool(aim) and note is not None and note["onscreen"] and note["system"],
                 f"note {note and note['frame']} onScreen={note and note['onscreen']} system={note and note['system']}"
                 f"; windows hiding overlays present={hiding}")
        gone = win(ws, f"{QUIRE}/{QUIRE}.note.{WAIT}") is None
        d.result(f"consent {label}: the waiting activity is gone once the session exists", gone, f"gone={gone}")
        # A UI dump never idles over the live mirror: the lab says where Stop is, and the check taps it there.
        mark = d.mark(f"consent {label} stop")
        d.lab("DUMP")
        st = d.wait_log(r"lab: mirror stop at (\d+),(\d+),(\d+),(\d+)", mark, timeout=5)
        stopped = bool(st)
        if st:
            x1, y1, x2, y2 = map(int, st.groups())
            d.sh(f"input tap {(x1 + x2) // 2} {(y1 + y2) // 2}")
        e = d.wait_log(r"note: control run ended stopped=true", tag, timeout=10)
        o = d.wait_log(r"note: window ordinary overlay", tag, timeout=5)
        tap = d.wait_log(r"note: mirror action STOP", mark, timeout=1)
        d.result(f"consent {label}: Stop on the screen ends the run; the note is ordinary again",
                 stopped and bool(tap) and bool(e) and bool(o),
                 (f"tapped Stop at {st.group(0).split(' at ')[1]}; " if st else "Stop not found; ") +
                 (e.group(0) if e else "not stopped") + (" · ordinary" if o else ""))
    finally:
        q5.clean(d)
        d.sh(f"am force-stop {SETTINGS}")
        if size:
            d.sh("wm size reset")
            time.sleep(3)


# ------------------------------------------------------------------------------------------------ owner

def owner(d):
    d.log("== owner (the overlay exemption belongs to the session's own task)")
    scene(d)
    tag = d.mark("owner")
    try:
        d.lab("CONTROL", prompt="In Settings, turn on Dark theme", app="Settings", launch=SETTINGS,
              taps=json.dumps(q5.TAPS[:2]), x=1400.0, y=300.0, aimMs="60000")
        if not d.wait_log(r"cc: pending: the dialog is open", tag, timeout=15) or not d.tap_text("Only this time"):
            d.result("owner: a live session", False, "no dialog or no 'Only this time'")
            return
        created = d.wait_log(r"cc: created: display", tag, timeout=15)
        d.wait_log(r'note: control aiming at', tag, timeout=15)
        d.lab("MIRROR", action="pause")
        paused = d.wait_log(r"cc: lifecycle: blocked reason=3", tag)
        mark = d.mark("owner which task")
        d.lab("DUMP")
        own = d.wait_log(r"lab: task (\d+) phase=MIRROR running=true", mark, timeout=5)
        if not created or not paused or not own:
            d.result("owner: a live, paused session", False, (created.group(0) if created else "no session") +
                     ("; paused" if paused else "; not paused") + (f"; task {own.group(1)}" if own else "; no task"))
            return
        ctl = own.group(1)
        d.sh(f"am start -W -n {PROBE}/.ProtectedActivity >/dev/null")
        time.sleep(1.5)

        def note_state(save):
            ws = windows(d, f"owner/{save}-windows.txt")
            d.screencap(f"owner/{save}.png")
            return win(ws, "Quire")

        def dump():
            mark = d.mark(f"owner dump {time.time():.0f}")
            d.lab("DUMP")
            time.sleep(0.6)
            return d.since(mark)

        n = note_state("session-task")
        d.result("owner: the session's own task keeps its mirror and Stop over a protected window",
                 n is not None and n["system"] and n["onscreen"], f"task {ctl}: system={n and n['system']} "
                 f"onScreen={n and n['onscreen']}")
        for i in (1, 2):
            mark = d.mark(f"owner away {i}")
            d.lab("OPEN", trigger="shake", intake="none", x=600.0, y=300.0)
            shown = d.wait_log(r"note: shown task (\d+)", mark)
            time.sleep(1.2)
            n = note_state(f"away-{i}")
            st = dump()
            hid = re.search(rf"lab: task {ctl} phase=MIRROR running=true hidden=true", st)
            d.result(f"owner: a new note while the session's task runs hidden is ordinary ({i})",
                     bool(shown) and shown.group(1) != ctl and bool(hid) and n is not None and not n["system"] and
                     n["hidden"] and not n["onscreen"],
                     f"shown task {shown and shown.group(1)} (session task {ctl} hidden and running: {bool(hid)}); "
                     f"system={n and n['system']} forceHidden={n and n['hidden']} onScreen={n and n['onscreen']}")
            d.lab("REOPEN", task=ctl)
            time.sleep(1.5)
            n = note_state(f"back-{i}")
            d.result(f"owner: reopening the session's task brings its mirror back ({i})",
                     n is not None and n["system"] and n["onscreen"],
                     f"system={n and n['system']} onScreen={n and n['onscreen']}")
        st = dump()
        stop = re.search(r"lab: mirror stop at (\d+),(\d+),(\d+),(\d+)", st)
        mark = d.mark("owner stop")
        if stop:
            x1, y1, x2, y2 = map(int, stop.groups())
            d.sh(f"input tap {(x1 + x2) // 2} {(y1 + y2) // 2}")
        ended = d.wait_log(rf"note: control run ended stopped=true", mark, timeout=10)
        time.sleep(1.5)
        n = note_state("after-stop")
        d.result("owner: after Stop, the task's own note is ordinary and hides under the protected window",
                 bool(stop) and bool(ended) and n is not None and not n["system"] and n["hidden"] and not n["onscreen"],
                 (ended.group(0) if ended else "not stopped") + f"; system={n and n['system']} "
                 f"forceHidden={n and n['hidden']} onScreen={n and n['onscreen']}")
    finally:
        q5.clean(d)
        d.sh(f"am force-stop {PROBE}")


# ------------------------------------------------------------------------------------------------ agents

def agents(d):
    d.log("== agents (two agents, both 'session-1')")
    scene(d)
    a, b = Peer(d, "Agent A", 17781), Peer(d, "Agent B", 17782)
    try:
        d.lab("ENDPOINT", id="peerA", name="Agent A", where="on this laptop", address="tcp:127.0.0.1:17781",
              local=True, connected=True)
        d.lab("ENDPOINT", id="peerB", name="Agent B", where="on this laptop", address="tcp:127.0.0.1:17782",
              local=True, connected=True)
        tag = d.mark("agents")
        ids = {}
        for peer, pid in ((a, "peerA"), (b, "peerB")):
            d.lab("OPEN", intake="none", x=700.0, y=300.0)
            time.sleep(0.8)
            d.lab("PICK", id=pid)
            d.lab("SEND", text=f"Hold this task open ({peer.name})")
            m = d.wait_log(rf"note: task (\d+) session session-1 with {pid}", tag)
            got = peer.wait(lambda x: x.get("method") == "session/prompt")
            ids[pid] = m.group(1) if m else None
            d.result(f"agents: {peer.name} runs a task in its session-1", bool(m and got),
                     f"task {ids[pid]}" if m else "no session")
        ta, tb = ids["peerA"], ids["peerB"]
        if not (ta and tb):
            return
        b_before = b.count()
        for peer, rid, who in ((a, 901, "A"), (b, 902, "B")):
            peer.send({"id": rid, "method": "session/request_permission", "params": {
                "sessionId": "session-1",
                "toolCall": {"toolCallId": f"{who}-only", "title": f"Run the {who} script", "kind": "execute",
                             "status": "pending", "rawInput": {"command": f"echo from {who}"}},
                "options": [{"optionId": "deny", "name": f"Deny {who}", "kind": "reject_once"},
                            {"optionId": "allow", "name": f"Allow {who}", "kind": "allow_once"}]}})
            time.sleep(0.6)
        log = d.since(tag)
        pa = re.search(rf"note: task (\d+) permission for A-only .* from peerA session session-1", log)
        pb = re.search(rf"note: task (\d+) permission for B-only .* from peerB session session-1", log)
        d.result("agents: A's request reaches A's task only", bool(pa) and pa.group(1) == ta,
                 pa.group(0) if pa else "not routed")
        d.result("agents: B's request reaches B's task only", bool(pb) and pb.group(1) == tb,
                 pb.group(0) if pb else "not routed")
        # A's card, under A's name; Esc answers A and cancels A's session only.
        d.lab("HIDE")
        time.sleep(0.8)
        d.lab("REOPEN", task=ta)
        time.sleep(1.2)
        xml = quire_dump(d, "agents/a-consent.xml")
        d.screencap("agents/a-consent.png")
        texts = q5.quire_texts(d, xml)
        d.result("agents: A's card is shown under Agent A", any("Agent A runs this" in t for t in texts) and
                 not any("Agent B" in t for t in texts), "; ".join(t for t in texts if "Agent" in t)[:200])
        a_before = a.count()
        b_before = b.count()
        d.sh("input keyevent KEYCODE_ESCAPE")
        ans = a.wait(lambda x: x.get("id") == 901 and "result" in x, start=a_before)
        cancel = a.wait(lambda x: x.get("method") == "session/cancel", start=a_before)
        time.sleep(0.8)
        b_new = [m for m in b.msgs[b_before:]]
        d.result("agents: Esc answers A 'cancelled' and cancels A's session only",
                 bool(ans) and ans["result"].get("outcome", {}).get("outcome") == "cancelled" and bool(cancel)
                 and not b_new, f"A got {ans and ans['result']} and {cancel and cancel['method']}; B got {b_new}")
        prompt_a = a.prompts[0]
        a.reply(prompt_a["id"], {"stopReason": "cancelled"})
        # B's card, under B's name; Allow answers B only.
        d.lab("REOPEN", task=tb)
        time.sleep(1.2)
        xml = quire_dump(d, "agents/b-consent.xml")
        d.screencap("agents/b-consent.png")
        texts = q5.quire_texts(d, xml)
        d.result("agents: B's card is shown under Agent B", any("Agent B runs this" in t for t in texts) and
                 not any("Agent A" in t for t in texts), "; ".join(t for t in texts if "Agent" in t)[:200])
        a_before = a.count()
        b_before = b.count()
        tapped = d.tap_text("Allow B")
        ans = b.wait(lambda x: x.get("id") == 902 and "result" in x, start=b_before)
        time.sleep(0.8)
        d.result("agents: Allow on B's card answers B only", tapped and bool(ans) and
                 ans["result"].get("outcome", {}).get("optionId") == "allow" and a.count() == a_before,
                 f"B got {ans and ans['result']}; A got {a.msgs[a_before:]}")
        # A new task on A, again 'session-1'; then A's connection drops while B runs.
        d.lab("OPEN", intake="none", x=700.0, y=300.0)
        time.sleep(0.8)
        d.lab("PICK", id="peerA")
        n = len(a.prompts)
        d.lab("SEND", text="A second task on Agent A")
        a.wait(lambda x: x.get("method") == "session/prompt" and len(a.prompts) > n)
        ta2 = re.findall(r"note: task (\d+) session session-1 with peerA", d.since(tag))[-1]
        mark = d.mark("agents disconnect")
        a.disconnect()
        closed = d.wait_log(r"acp: peerA closed.*?(\d+) session", mark)
        time.sleep(1.0)
        d.lab("DUMP")
        time.sleep(0.5)
        dump = d.since(mark)
        a2 = re.search(rf"lab: task {ta2} phase=(\w+) running=(\w+)", dump)
        bb = re.search(rf"lab: task {tb} phase=(\w+) running=(\w+)", dump)
        d.result("agents: A's disconnect fails only A's running task",
                 bool(closed) and a2 and a2.group(1) == "ERROR" and bb and bb.group(2) == "true",
                 (closed.group(0) if closed else "no close") + f"; A2 {a2 and a2.groups()}; B {bb and bb.groups()}")
        b.update("session-1", {"sessionUpdate": "agent_message_chunk",
                               "content": {"type": "text", "text": "B is still here after A left."}})
        b.reply(b.prompts[0]["id"], {"stopReason": "end_turn"})
        done = d.wait_log(rf"note: task {tb} ended stopReason=end_turn", mark)
        d.lab("REOPEN", task=tb)
        time.sleep(1.2)
        xml = quire_dump(d, "agents/b-after.xml")
        d.screencap("agents/b-after.png")
        d.result("agents: B's run goes on and finishes after A left", bool(done) and
                 q5.has_text(d, xml, "B is still here after A left."), done.group(0) if done else "not ended")
        (d.o / "agents").mkdir(exist_ok=True)
        (d.o / "agents/peer-a.json").write_text(json.dumps(a.msgs, indent=1))
        (d.o / "agents/peer-b.json").write_text(json.dumps(b.msgs, indent=1))
    finally:
        q5.clean(d)
        for _ in range(3):
            d.lab("CLOSE")
        d.lab("ENDPOINT_REMOVE", id="peerA")
        d.lab("ENDPOINT_REMOVE", id="peerB")
        a.stop()
        b.stop()


# ------------------------------------------------------------------------------------------------ intake

def jpeg_size(data):
    """(width, height) of a JPEG, from its SOF marker."""
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return None


def intake(d):
    d.log("== intake")
    peer = Peer(d, "Intake checker", 17783, images=True, session="intake-1", auto_end=True)
    out = d.o / "intake"
    out.mkdir(parents=True, exist_ok=True)
    try:
        d.lab("ENDPOINT", id="intake", name="Intake checker", where="on this laptop",
              address="tcp:127.0.0.1:17783", local=True, connected=True)

        def sent(name, tag):
            """Sends a prompt in the note just opened; returns the prompt's content blocks the agent received."""
            n = len(peer.prompts)
            d.lab("PICK", id="intake")
            d.lab("SEND", text=f"Checker: what do you see? ({name})")
            peer.wait(lambda x: x.get("method") == "session/prompt" and len(peer.prompts) > n, timeout=10)
            if len(peer.prompts) <= n:
                return None
            blocks = peer.prompts[-1]["params"]["prompt"]
            record = []
            for i, blk in enumerate(blocks):
                if blk.get("type") == "image":
                    data = base64.b64decode(blk["data"])
                    (out / f"{name}-{i}.jpg").write_bytes(data)
                    record.append({"type": "image", "mimeType": blk.get("mimeType"), "bytes": len(data),
                                   "size": jpeg_size(data), "file": f"{name}-{i}.jpg"})
                else:
                    record.append(blk)
            (out / f"{name}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False))
            d.wait_log(r"ended stopReason=end_turn", tag, timeout=8)
            return record

        def expect_nothing(name, tag, why, m, record):
            images = [r for r in (record or []) if r.get("type") == "image"]
            window_text = [r for r in (record or []) if r.get("type") == "text" and "looking at" in r.get("text", "")]
            d.result(f"intake: {name}: nothing taken in", bool(m) and m.group(1) in ("None", "Secure") and
                     why in m.group(0) and record is not None and not images and not window_text,
                     (m.group(0) if m else "no invocation logged") + f"; the agent got {len(record or [])} blocks, "
                     f"{len(images)} images, window text {bool(window_text)}")

        inv = r"note: invocation anchor=(?:pointer \S+|taskbar) bounds=(?:null|Rect\([^)]*\)) intake=(\w+) reason=\S+.*"

        # Real calls. The probe (hiding nothing) is the window; Files is on top of it, away from the pointer.
        scene(d)
        d.sh(f"am start -W -n {PROBE}/.ProtectedActivity --ez hide false >/dev/null")
        time.sleep(1.5)
        pw = win(windows(d), f"{PROBE}/{PROBE}.ProtectedActivity")["frame"]
        mouse = Mouse(d)
        try:
            # a. The pointer still for longer than 10 s: Meta+Space carries no pointer and no window.
            mouse.move(-60, -40)
            time.sleep(11.5)
            tag = d.mark("intake still")
            d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")
            m = d.wait_log(inv, tag)
            expect_nothing("Meta+Space, pointer still 11 s", tag, "anchor=taskbar", m, sent("still", tag))
            if m:
                d.result("intake: Meta+Space, pointer still 11 s: the reason", "reason=no-pointer" in m.group(0),
                         m.group(0))
            q5.clean(d)
            # b. Over the desktop (no window under the pointer) within 10 s: the probe on the right half.
            place(d, PROBE, 1000, 120, 1880, 900)
            pw = win(windows(d), f"{PROBE}/{PROBE}.ProtectedActivity")["frame"]
            mouse.move(-3000, -3000)       # the top-left corner
            time.sleep(0.3)
            glide(mouse, 200, 500)
            time.sleep(0.5)
            tag = d.mark("intake desktop")
            d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")
            m = d.wait_log(inv, tag)
            ok_reason = m and ("reason=no-bounds" in m.group(0) or "reason=desktop" in m.group(0))
            expect_nothing("Meta+Space over the desktop", tag, "reason=no-bounds" if (m and "no-bounds" in m.group(0))
                           else "reason=desktop", m, sent("desktop", tag))
            if m and not ok_reason:
                d.result("intake: over the desktop, the reason", False, m.group(0))
            q5.clean(d)
            # c. Over the probe's window (right half), with Files in front on the left half: the window under the
            # pointer, named after it, though Files is the first visible app.
            d.sh(f"am start -W -n {FILES}/.files.FilesActivity >/dev/null")
            time.sleep(1.5)
            place(d, FILES, 40, 120, 960, 900)
            ws = windows(d)
            fw = win(ws, f"{FILES}/{FILES}.files.FilesActivity")
            mouse.move(3000, -3000)        # the top-right corner
            time.sleep(0.3)
            glide(mouse, -(1919 - (pw[0] + pw[2]) // 2), (pw[1] + pw[3]) // 2 - 150)
            time.sleep(0.6)
            for name, act in (("Meta+Space over the probe", "key"), ("the shake over the probe", "shake")):
                screen = d.screencap(f"intake/{act}-screen.png")
                tag = d.mark(f"intake {act}")
                if act == "key":
                    d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")
                    m = d.wait_log(inv, tag)
                else:
                    m = None
                    for _ in range(3):
                        mouse.shake()
                        m = d.wait_log(inv, tag, timeout=6)
                        if m:
                            break
                        time.sleep(3.5)
                record = sent(act, tag)
                images = [r for r in (record or []) if r.get("type") == "image"]
                texts = [r.get("text", "") for r in (record or []) if r.get("type") == "text"]
                b = re.search(r"bounds=Rect\((-?\d+), (-?\d+) - (-?\d+), (-?\d+)\)", m.group(0)) if m else None
                crop = tuple(map(int, b.groups())) if b else None
                named = any("Quire secure probe" in t for t in texts)
                diff = compare(screen, crop, out / images[0]["file"]) if images and crop else None
                d.result(f"intake: {name}: the window under the pointer, named after it",
                         bool(m) and m.group(1) == "Window" and "source=" + PROBE in m.group(0) and crop == pw and
                         len(images) == 1 and named and diff is not None and diff < 12,
                         (m.group(0) if m else "no invocation") + f"; image {images[0]['size'] if images else None}"
                         f", named {named}, mean difference from the screen {diff if diff is None else round(diff, 1)}"
                         f"/255 (Files on top at {fw and fw['frame']})")
                q5.clean(d)
                glide(mouse, 6, 4)          # keep the pointer recent for the next call
                time.sleep(0.4)
        finally:
            mouse.close()

        # Made-up calls for what SystemUI never sends (the lab's INVOKE; the same code from Calls.handle on).
        scene(d)
        good = dict(px="800", py="400", bounds="600,300,1400,900", source=SETTINGS, age="100", visible=SETTINGS)
        cases = [
            ("no pointer", dict(good, px=None, py=None), "no-pointer"),
            ("no bounds", dict(good, bounds=None), "no-bounds"),
            ("empty bounds", dict(good, bounds="800,300,800,900"), "empty-bounds"),
            ("inverted bounds", dict(good, bounds="1400,900,600,300"), "empty-bounds"),
            ("pointer outside the bounds", dict(good, px="100", py="1000"), "pointer-outside-bounds"),
            ("bounds off the display", dict(good, bounds="2000,100,2600,600", px="2100", py="200"),
             "bounds-off-screen"),
            ("no package", dict(good, source=None), "no-source-package"),
            ("the desktop package", dict(good, source="com.android.launcher3",
                                           visible="com.android.launcher3"), "desktop"),
            ("no time", dict(good, age=None), "no-source-time"),
            ("stale bounds (4 s)", dict(good, age="4000"), "stale-bounds"),
            ("bounds from the future", dict(good, age="-500"), "stale-bounds"),
            ("a package not on screen", dict(good, visible="com.android.documentsui"), "source-not-visible"),
            ("the secure flag, no bounds", dict(good, bounds=None, secure="true"), "no-bounds"),
        ]
        for name, extras, why in cases:
            tag = d.mark(safe(f"intake lab {name}"))
            d.lab("INVOKE", **{k: v for k, v in extras.items() if v is not None})
            m = d.wait_log(inv, tag)
            expect_nothing(f"lab: {name}", tag, f"reason={why}", m, sent(re.sub(r"\W+", "-", name), tag))
            q5.clean(d)
        tag = d.mark("intake lab valid")
        d.lab("INVOKE", **good)
        m = d.wait_log(inv, tag)
        record = sent("lab-valid", tag)
        images = [r for r in (record or []) if r.get("type") == "image"]
        texts = [r.get("text", "") for r in (record or []) if r.get("type") == "text"]
        corners = pixel_corners(out / images[0]["file"]) if images else None
        # The generated screenshot's pixels say where they came from: red = x, green = y, scaled to 255.
        want = [(600 * 255 / 1919, 300 * 255 / 1079), (1399 * 255 / 1919, 899 * 255 / 1079)]
        near = corners is not None and all(abs(c[0] - w[0]) < 10 and abs(c[1] - w[1]) < 10
                                           for c, w in zip(corners, want))
        d.result("intake: lab: a valid call takes in exactly the bounds, named after the package",
                 bool(m) and m.group(1) == "Window" and "crop=800x600" in m.group(0) and len(images) == 1 and
                 images[0]["size"] == (800, 600) and near and any("Settings" in t for t in texts),
                 (m.group(0) if m else "no invocation") + f"; image {images[0]['size'] if images else None}; corners "
                 f"(red, green) {corners} against {[(round(a), round(b)) for a, b in want]}")
        q5.clean(d)
    finally:
        q5.clean(d)
        d.lab("ENDPOINT_REMOVE", id="intake")
        peer.stop()


def compare(screen_png, crop, image_jpg):
    """Mean absolute difference (0-255) between the crop of the host's screenshot and the image the agent got."""
    try:
        from PIL import Image
    except ImportError:
        return None
    s = Image.open(screen_png).convert("RGB").crop(crop)
    g = Image.open(image_jpg).convert("RGB")
    s = s.resize(g.size)
    a, b = s.tobytes(), g.tobytes()
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def pixel_corners(image_jpg):
    """(red, green) averaged over 5x5 pixels at the top-left and bottom-right corners."""
    try:
        from PIL import Image
    except ImportError:
        return None
    g = Image.open(image_jpg).convert("RGB")
    w, h = g.size

    def avg(x0, y0):
        px = [g.getpixel((x, y)) for x in range(x0, x0 + 5) for y in range(y0, y0 + 5)]
        return (round(sum(p[0] for p in px) / 25, 1), round(sum(p[1] for p in px) / 25, 1))
    return [avg(0, 0), avg(w - 5, h - 5)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("serial")
    ap.add_argument("out")
    ap.add_argument("--only", default="overlay,consent,owner,agents,intake")
    ap.add_argument("--probe", help="install this QuireSecureProbe.apk first")
    args = ap.parse_args()
    d = Dev(args.serial, args.out)
    d.log(f"q5-safety-check on {args.serial}: {d.sh('getprop ro.build.fingerprint').strip()}")
    d.log("Quire " + d.sh(f"dumpsys package {QUIRE} | grep -m1 versionCode").strip())
    if args.probe:
        d.log("probe: " + d.run("install", "-r", "-d", args.probe).stdout.strip().splitlines()[-1])
    d.run("root")
    time.sleep(2)
    d.run("connect", args.serial)
    d.sh("input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; settings put global stay_on_while_plugged_in 7")
    only = args.only.split(",")
    try:
        if "overlay" in only:
            overlay(d)
        if "consent" in only:
            consent(d)
            consent(d, size="1280x800", at=(900.0, 300.0))
            consent(d, deny=True)
        if "owner" in only:
            owner(d)
        if "agents" in only:
            agents(d)
        if "intake" in only:
            intake(d)
    finally:
        q5.clean(d)
        with open(d.o / "results.tsv", "w") as f:
            for c, r, detail in d.results:
                f.write(f"{c}\t{r}\t{detail}\n")
        n = {k: sum(1 for _, r, _ in d.results if r == k) for k in ("PASS", "FAIL", "INFO")}
        d.log(f"== {n['PASS']} PASS, {n['FAIL']} FAIL, {n['INFO']} INFO")


if __name__ == "__main__":
    main()
