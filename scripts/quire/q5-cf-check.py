#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Quire Q5 checks (ANAL-219) on a booted userdebug OpenBook device, normally Cuttlefish.

usage: q5-cf-check.py SERIAL OUTDIR [--design DIR] [--only SECTION,...] [--themes light,dark]

Records every state of the note in docs/quire-design.md §3.2 in light and dark, each next to its Q3 render, and checks
what can be checked from the outside. Sections, in order:
  states     Every screen id in the design's gallery: drive it, take a screenshot and a UI dump, check its log line.
             The note's content comes from ACP over the wire: scripts/quire/q5-acp-agent.py runs here on the host
             (started by this script) and Quire reaches it through `adb reverse`. Computer control is the platform's
             real session on Settings. With --design (Q3's docs/quire-design/), writes side-by-side/<id>[-dark].jpg.
  keyboard   §6.1/§6.2: focus lands on the field, then on the consent card; Tab order through the card, reject first;
             Enter answers; Esc at consent stops and answers "cancelled"; Esc mid-run stops; Meta+Space hides a
             running task and brings it back; Esc closes an idle note.
  a11y       §6.3: every focusable or clickable node in the note's UI dumps has a label; the note is a pane titled
             Quire; consent, results and errors are live regions.
  motion     §5.3: with Remove animations the note appears and folds in one frame.
  frames     dumpsys gfxinfo for Quire over open, stream, consent and fold (Cuttlefish only: the G14 is the
             acceptance device).
  video      Screen recordings of three flows (the shake and the halo through a turn and the fold; consent by
             keyboard; the mirror with pause and take-over), with contact sheets.
  contrast   §8: the note's colour pairs on the device's palette (light and dark) and on all eight wallpapers'
             predicted palettes (scripts/quire/q5-contrast.py, with the brand venv's python).
  health     Crash buffer, ANRs, SystemUI restarts, SELinux denials against Cuttlefish's known three.

Commands go to Quire through its root-only lab receiver (note/LabReceiver.kt), so the device must be rooted.
Env: ADB (default ~/anybook/android-sdk/platform-tools/adb); set ANDROID_ADB_SERVER_PORT for a private server.
Writes OUTDIR/results.tsv (check, PASS/FAIL/INFO, detail), OUTDIR/checks.log, OUTDIR/<theme>/<id>.png and .xml,
OUTDIR/agent-*.log (the ACP traffic the scripted agents saw).
"""
import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

QUIRE = "dev.openbook.quire"
LAB = QUIRE + "/.note.LabReceiver"
SETTINGS = "com.android.settings"
HERE = Path(__file__).resolve().parent
PTR = (1010, 470)          # the design's pointer, over the Settings window
KNOWN_DENIALS = [
    "scontext=u:r:bootanim:s0 tcontext=u:object_r:gpu_service:s0",
    "scontext=u:r:init:s0 tcontext=u:object_r:debugfs_bootreceiver_tracing:s0",
    "scontext=u:r:gceservice:s0",
]
TAPS = [["Display", "Tapping Display", "Opened Display"],
        ["Dark theme", "Tapping Dark theme", "Opened Dark theme"],
        ["Use Dark theme", "Turning on Dark theme", "Turned on Dark theme"]]


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

    def result(self, check, ok, detail):
        r = "INFO" if ok is None else ("PASS" if ok else "FAIL")
        self.results.append((check, r, detail))
        self.log(f"{r} {check}: {detail}")
        return ok

    def screencap(self, path):
        path = self.o / path
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            subprocess.run([self.adb, "-s", self.s, "exec-out", "screencap", "-p"], stdout=f, timeout=60)
        return path

    def ui(self, path=None):
        # A dump fails while the note streams (no idle state); never read the previous run's file instead.
        self.sh("rm -f /data/local/tmp/q5-ui.xml; uiautomator dump /data/local/tmp/q5-ui.xml >/dev/null 2>&1")
        xml = self.sh("cat /data/local/tmp/q5-ui.xml")
        if path:
            (self.o / path).parent.mkdir(parents=True, exist_ok=True)
            (self.o / path).write_text(xml)
        return xml

    def mark(self, label):
        tag = f"q5-check {label} {time.time():.3f}"
        self.sh(f"log -t Quire -p i '{tag}'")
        return tag

    def since(self, tag):
        # Cut on the device: only the lines after the marker cross adb.
        return self.sh(f"logcat -d -v time -s Quire:I | sed -n '/{tag}/,$p'")

    def wait_log(self, pattern, tag, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            m = re.search(pattern, self.since(tag))
            if m:
                return m
            time.sleep(0.4)
        return None

    def lab(self, act, **extras):
        args = []
        for k, v in extras.items():
            if isinstance(v, bool):
                args += ["--ez", k, str(v).lower()]
            elif isinstance(v, float):
                args += ["--ef", k, str(v)]
            else:
                args += ["--es", k, "'" + str(v).replace("'", "'\\''") + "'"]
        return self.sh(f"am broadcast -n {LAB} -a dev.openbook.quire.lab.{act} " + " ".join(args))

    def key(self, *codes):
        for c in codes:
            self.sh(f"input keyevent {c}")
            time.sleep(0.25)

    def nodes(self, xml):
        try:
            return list(ET.fromstring(xml).iter("node"))
        except ET.ParseError:
            return []

    def node(self, xml, text=None, desc=None):
        for n in self.nodes(xml):
            if text is not None and n.get("text") == text:
                return n
            if desc is not None and n.get("content-desc") == desc:
                return n
        return None

    def tap_node(self, n):
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", n.get("bounds")))
        self.sh(f"input tap {(x1 + x2) // 2} {(y1 + y2) // 2}")

    def tap_text(self, text, timeout=8, desc=False):
        end = time.time() + timeout
        while time.time() < end:
            n = self.node(self.ui(), **({"desc": text} if desc else {"text": text}))
            if n is not None:
                self.tap_node(n)
                return True
            time.sleep(0.5)
        return False

    def focused(self):
        """The focused node in Quire's windows: its label and class. A dump can fail while the note's footer ticks
        (no idle state), so it is tried a few times."""
        for _ in range(4):
            nodes = self.nodes(self.ui())
            for n in nodes:
                if n.get("focused") == "true" and n.get("package") == QUIRE:
                    return (n.get("content-desc") or n.get("text") or "").strip(), n.get("class")
            if nodes:
                break
            time.sleep(0.5)
        return None, None


class Mouse:
    """A virtual relative USB mouse (`uinput -`), as in q2-cf-check.py: the pointer shake."""
    NAME = "OpenBook Q5 Test Mouse"

    def __init__(self, d):
        self.d = d
        self.p = subprocess.Popen([d.adb, "-s", d.s, "shell", "uinput", "-"], stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        self.send({"id": 1, "command": "register", "name": self.NAME, "vid": 0x18d1, "pid": 0xb219, "bus": "usb",
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

    def shake(self, amplitude=15, strokes=8, interval=0.05):
        for i in range(strokes):
            self.move(amplitude if i % 2 == 0 else -amplitude, 0)
            time.sleep(interval)

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


class Agents:
    """The scripted ACP agents on this host: Claude Code (7070), Cursor that needs sign-in (7071)."""

    def __init__(self, d):
        self.d = d
        self.procs = {}
        for port, extra in ((7070, []), (7071, ["--name", "cursor-agent", "--title", "Cursor", "--auth"])):
            log = d.o / f"agent-{port}.log"
            self.procs[port] = subprocess.Popen([sys.executable, "-I", str(HERE / "q5-acp-agent.py"), "--port",
                                                 str(port), "--log", str(log), *extra])
            d.run("reverse", f"tcp:{port}", f"tcp:{port}")
        time.sleep(1)

    def release(self, port=7070):
        os.kill(self.procs[port].pid, signal.SIGUSR1)

    def stop(self):
        for p in self.procs.values():
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


def endpoints(d, claude_connected=True):
    d.lab("ENDPOINT", id="claude", name="Claude Code", where="on this laptop", address="tcp:127.0.0.1:7070",
          cwd="/home/brian", local=True, connected=claude_connected)
    d.lab("ENDPOINT", id="cursor", name="Cursor", where="on this laptop", address="tcp:127.0.0.1:7071",
          cwd="/home/brian", local=True, connected=True)
    # A paired computer that isn't there: nothing listens on 7099.
    d.lab("ENDPOINT", id="codex", name="Codex", where="on Brian’s desk", address="tcp:127.0.0.1:7099",
          cwd="/home/brian", local=False, connected=True)
    d.lab("PICK", id="claude")


def clean(d):
    """No note, no tray, no session: Esc twice, close what's left."""
    for _ in range(3):
        d.lab("ESC")
        time.sleep(0.3)
    d.lab("CLOSE")
    d.sh("input keyevent KEYCODE_ESCAPE")
    time.sleep(0.8)


def desk(d, which):
    # One window of each, as in the renders: a fresh start closes the previous one.
    if which == "settings":
        d.sh(f"am force-stop {SETTINGS}; am start -W -a android.settings.DISPLAY_SETTINGS >/dev/null")
    elif which == "files":
        d.sh("am force-stop com.android.documentsui; "
             "am start -W -n com.android.documentsui/.files.FilesActivity >/dev/null")
    time.sleep(1.2)


def quire_texts(d, xml):
    """Every text and label in Quire's windows in a UI dump (texts may start with an icon glyph)."""
    out = []
    for n in d.nodes(xml):
        if n.get("package") == QUIRE:
            out += [t for t in (n.get("text"), n.get("content-desc")) if t]
    return out


def has_text(d, xml, needle):
    return any(needle in t for t in quire_texts(d, xml))


def save_through_picker(d, button_label, expect_name):
    """Taps a Save button in the note, then SAVE in DocumentsUI's picker; returns the saved file's first line."""
    d.sh("rm -f /sdcard/Download/*")
    if not d.tap_text(button_label, desc=True):
        return None, "no button"
    time.sleep(2.0)
    if not (d.tap_text("SAVE") or d.tap_text("Save")):
        return None, "no picker"
    time.sleep(2.0)
    listing = d.sh("ls /sdcard/Download/").strip()
    first = d.sh(f"head -n 1 '/sdcard/Download/{expect_name}'").strip()
    return first, listing


def openat(d, intake="window", name="Settings", at=PTR, text=None, trigger="lab"):
    extras = {"trigger": trigger, "intake": intake, "name": name}
    if at:
        extras.update(x=float(at[0]), y=float(at[1]))
    if text:
        extras["text"] = text
    d.lab("OPEN", **extras)
    time.sleep(0.9)


# ------------------------------------------------------------------------------------------------ the states
def states(d, agents, theme, design, only=None):
    d.log(f"== states ({theme})")
    sfx = "" if theme == "light" else "-dark"
    d.sh(f"cmd uimode night {'yes' if theme == 'dark' else 'no'}")
    time.sleep(2)

    def cap(sid, check=None, ok=True, detail="", dump=True):
        png = d.screencap(f"{theme}/{sid}.png")
        if dump:
            d.ui(f"{theme}/{sid}.xml")
        d.result(f"{theme}: {sid}" + (f" ({check})" if check else ""), ok, detail)
        if design:
            side_by_side(d, png, Path(design) / "png" / f"{sid}{sfx}.png", d.o / "side-by-side" / f"{sid}{sfx}.jpg")

    def run(sid, fn):
        clean(d)
        tag = d.mark(f"{theme} {sid}")
        try:
            fn(tag)
        except Exception as e:  # keep going: one broken state must not hide the others
            d.result(f"{theme}: {sid}", False, f"{type(e).__name__}: {e}")

    def idle(tag):
        desk(d, "settings")
        cap("idle", ok=None, detail="the desktop with no note; the taskbar's Quire button is Launcher3's (not built)")

    def invoke_key(tag):
        desk(d, "settings")
        # The pointer moves first: within 10 s, SystemUI passes its position and the note opens beside it (§2).
        mouse = Mouse(d)
        try:
            mouse.move(-300, -200)
            time.sleep(0.4)
            mouse.move(60, 40)
            time.sleep(0.4)
        finally:
            mouse.close()
        d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")
        m = d.wait_log(r"note: invocation anchor=(\S+).*intake=(\w+)", tag)
        time.sleep(1.0)
        cap("invoke-key", "Meta+Space, the real path", bool(m) and m.group(1) == "pointer",
            m.group(0) if m else "no invocation logged")

    def invoke_shake(tag):
        desk(d, "settings")
        mouse = Mouse(d)
        try:
            mouse.move(-400, -300)
            time.sleep(0.5)
            m = None
            for attempt in range(3):
                mouse.shake()
                m = d.wait_log(r"note: invocation anchor=(\S+).*intake=(\w+)", tag, timeout=6)
                if m:
                    break
                time.sleep(3.5)
            time.sleep(1.0)
            cap("invoke-shake", "the pointer shake, the real path", bool(m) and m.group(1) == "pointer",
                m.group(0) if m else "no invocation")
        finally:
            mouse.close()

    def invoke_secure(tag):
        desk(d, "settings")
        openat(d, intake="secure")
        cap("invoke-secure", ok=bool(d.wait_log(r"note: shown task", tag)))

    def invoke_taskbar(tag):
        desk(d, "files")
        openat(d, intake="none", at=None, trigger="taskbar")
        cap("invoke-taskbar", ok=bool(d.wait_log(r"anchor=Taskbar", tag)))

    def invoke_voice(tag):
        desk(d, "settings")
        openat(d)
        d.lab("LISTEN", final="Make my screen easier to read ", partial="at night")
        time.sleep(0.8)
        cap("invoke-voice", ok=None, detail="the listening card from the lab; speech to text and the mic indicator are Q7")

    def invoke_selection(tag):
        desk(d, "files")
        text = "The conference runs Tuesday to Thursday at the Centro de Congressos."
        d.sh("am start -a android.intent.action.PROCESS_TEXT -t text/plain --es android.intent.extra.PROCESS_TEXT "
             f"'{text}' -n {QUIRE}/.invocation.ProcessTextActivity")
        m = d.wait_log(r"note: ask on a selection \((\d+) chars\)", tag)
        time.sleep(1.0)
        cap("invoke-selection", "ACTION_PROCESS_TEXT", bool(m), m.group(0) if m else "not received")

    def compose(tag):
        desk(d, "settings")
        openat(d)
        d.sh("input text 'Make%smy%sscreen%seasier%sto%sread%sat%sni'")
        time.sleep(0.6)
        cap("compose", ok=bool(d.wait_log(r"note: shown task \d+ phase=COMPOSE", tag)))

    def picker(tag):
        desk(d, "settings")
        openat(d)
        d.sh("input text 'Make%smy%sscreen%seasier%sto%sread%sat%snight'")
        d.lab("PICKER")
        time.sleep(0.8)
        cap("agent-picker", ok=None, detail="claude (connected), cursor (needs sign-in once tried), codex (paired)")
        d.lab("ESC")

    def streaming(tag):
        desk(d, "settings")
        openat(d)
        d.lab("SEND", text="What does Adaptive brightness do here?")
        time.sleep(3.2)
        cap("streaming", "agent_thought_chunk, agent_message_chunk", bool(d.wait_log(r"prompt \(\d+ blocks\)", tag)))
        agents.release()
        d.wait_log(r"ended stopReason=end_turn", tag, timeout=15)

    def steps_and_done(tag):
        desk(d, "settings")
        openat(d)
        d.lab("SEND", text="Turn on Battery saver and lower the brightness")
        time.sleep(2.8)
        cap("steps", "tool_call, tool_call_update", True)
        agents.release()
        m = d.wait_log(r"ended stopReason=end_turn", tag, timeout=15)
        time.sleep(0.8)
        foot = [t for t in quire_texts(d, d.ui()) if re.fullmatch(r"Done · \d+ s", t)]
        cap("done", "stopReason end_turn; the footer says Done and the time", bool(m) and bool(foot),
            f"footer {foot[0] if foot else 'missing'}; Undo appears only for broker changes (Q6)")

    def plan(tag):
        desk(d, "settings")
        openat(d)
        d.lab("SEND", text="Set this laptop up for my talk tomorrow")
        time.sleep(2.4)
        cap("plan", "plan entries", True)
        agents.release()
        d.wait_log(r"ended stopReason", tag, timeout=15)

    def consent(tag):
        desk(d, "settings")
        openat(d)
        d.lab("BROKER", title="Change 2 settings", meta="Settings tool",
              rows=json.dumps([["Battery saver", "Settings · Battery", "Off", "On"],
                               ["Brightness level", "Settings · Display", "80%", "40%"]]),
              why="You can undo this from the note or from the Quire button.",
              prompt="Turn on Battery saver and lower the brightness",
              steps=json.dumps([["Reading Display settings", "read"], ["Reading Battery settings", "read"]]))
        time.sleep(1.0)
        cap("consent", "the broker's card, Quire's options", None, "raised from the lab: Q6's broker raises it for "
            "real; the agent-own consent is consent-command")
        if d.tap_text("Allow"):
            time.sleep(1.0)
            cap("settings-help", "the change list after Allow", None,
                "rows from the lab; applying and undoing the settings is Q6's change log")

    def consent_command(tag):
        desk(d, "files")
        openat(d, intake="selection", name="Notes", at=(700, 520),
               text="Things to pack: the HDMI adapter, the second laptop charger, walking shoes")
        d.lab("SEND", text="Turn this into a checklist file in my Documents")
        m = d.wait_log(r"permission for (\S+) options=\[(.*?)\]", tag)
        time.sleep(0.8)
        cap("consent-command", "session/request_permission with a diff", bool(m),
            m.group(0) if m else "no permission request")
        if m:
            d.tap_text("Allow")
            r = d.wait_log(r"answered (\w+)", tag)
            d.result(f"{theme}: consent-command answered", bool(r) and r.group(1) == "allow",
                     r.group(0) if r else "no answer logged")

    def control(tag):
        d.sh(f"am force-stop {SETTINGS}")
        d.sh("cmd uimode night " + ("yes" if theme == "dark" else "no"))
        desk(d, "files")
        # A slow aim (the pointer rests 8 s on each control) leaves time for the screenshots.
        d.lab("CONTROL", prompt="In Settings, turn on Dark theme", app="Settings", launch=SETTINGS,
              taps=json.dumps(TAPS), x=1400.0, y=300.0, aimMs="8000")
        m = d.wait_log(r"cc: pending", tag)
        time.sleep(1.5)
        cap("consent-system", "onSessionPending, the platform's dialog", bool(m), "the note waits beside the "
            "platform's dialog, without focus or touch")
        if not d.tap_text("Only this time"):
            d.result(f"{theme}: consent-system dialog", False, "no 'Only this time' button")
            return
        c = d.wait_log(r"cc: created: display (\d+x\d+)", tag)
        t1 = d.wait_log(r"cc: tap: (\d+),(\d+)", tag, timeout=15)
        aim = d.wait_log(r'note: control aiming at "Dark theme" bounds=(\S+)', tag, timeout=15)
        time.sleep(0.8)   # the 2x zoom settles (spring.expand)
        cap("mirror", "InteractiveMirror, 2x zoom, agent pointer", bool(c and t1 and aim),
            (c.group(0) if c else "no session") + (f"; first tap {t1.group(1)},{t1.group(2)}" if t1 else "")
            + (f"; aiming at Dark theme {aim.group(1)}" if aim else ""), dump=False)
        d.lab("MIRROR", action="pause")
        b = d.wait_log(r"cc: lifecycle: blocked reason=3\(CALLER_INITIATED\)", tag)
        time.sleep(1.2)
        cap("mirror-paused", "notifyBlocked()", bool(b), b.group(0) if b else "not blocked")
        held = not re.search(r'cc: tap: 1309', d.since(tag))
        d.result(f"{theme}: mirror-paused holds the agent's input", held, "no tap on the paused control" if held
                 else "a tap went through while paused")
        d.lab("MIRROR", action="takeover")
        h = d.wait_log(r"cc: lifecycle: closed reason=4\(SESSION_EMPTY\)", tag)
        time.sleep(1.2)
        chip = None
        for n in d.nodes(d.ui()):
            if n.get("package") == QUIRE and (n.get("content-desc") or "").startswith("Agent:"):
                chip = list(map(int, re.findall(r"\d+", n.get("bounds"))))
        left = chip is not None and chip[2] < 1400
        cap("mirror-takeover", "handOverApplications(); the note keeps the side it flipped to", bool(h) and left,
            (h.group(0) if h else "not handed over") + f"; agent chip {chip} (the hotspot is at x=1400)")
        d.sh(f"am force-stop {SETTINGS}")

    def stopped(tag):
        desk(d, "settings")
        openat(d)
        d.lab("SEND", text="Check my battery settings, and stop me when you like")
        time.sleep(2.4)
        d.sh("input keyevent KEYCODE_ESCAPE")
        m = d.wait_log(r"ended stopReason=cancelled", tag)
        time.sleep(0.8)
        texts = " ".join(quire_texts(d, d.ui()))
        tail = texts.split("Stopped after")[-1]
        honest = "Running the brightness script was interrupted and may be partly applied." in tail and \
            "Reading Display settings was interrupted" not in tail
        cap("stopped", "Esc: session/cancel; only the interrupted command may be partly applied", bool(m) and honest,
            (m.group(0) if m else "not stopped") + ("" if honest else "; copy: " + tail[-300:]))

    def error(tag):
        desk(d, "settings")
        openat(d)
        d.lab("SEND", text="Turn on Battery saver, but break while doing it")
        m = d.wait_log(r"acp: claude closed", tag, timeout=10)
        time.sleep(1.0)
        texts = " ".join(quire_texts(d, d.ui()))
        honest = "Nothing was changed." in texts and "may be partly applied" not in texts and \
            "Reading Battery settings was interrupted." in texts
        cap("error", "the agent's connection drops mid-turn; an interrupted read changed nothing", bool(m) and honest,
            (m.group(0) if m else "no drop logged") + ("" if honest else "; copy: " + texts[-300:]))

    def signin(tag):
        desk(d, "settings")
        openat(d)
        d.lab("PICK", id="cursor")
        time.sleep(0.5)
        d.lab("SEND", text="Make my screen easier to read at night")
        time.sleep(2.2)
        cap("signin", "session/new -32000, authMethods", True)
        d.lab("PICK", id="claude")

    def offline(tag):
        desk(d, "settings")
        openat(d)
        d.lab("PICK", id="codex")
        time.sleep(0.5)
        d.lab("SEND", text="Make my screen easier to read at night")
        m = d.wait_log(r"cannot reach tcp:127.0.0.1:7099", tag, timeout=8)
        time.sleep(0.8)
        cap("offline", "a paired computer unreachable", bool(m), m.group(0) if m else "not logged")
        d.lab("PICK", id="claude")

    def background(tag):
        desk(d, "files")
        openat(d, at=None, intake="none", trigger="taskbar")
        d.lab("SEND", text="Rename the photos in Lisbon by date, and stop me when you like")
        time.sleep(1.5)
        d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")   # Meta+Space hides a running task
        h = d.wait_log(r"note: hid task (\d+) running=true", tag)
        time.sleep(1.0)
        openat(d, intake="selection", name="Notes", at=(700, 520), text="Things to pack: the HDMI adapter")
        d.lab("SEND", text="Turn this into a checklist file in my Documents")
        d.wait_log(r"permission for", tag)
        d.lab("HIDE")
        time.sleep(1.0)
        d.lab("TRAY")
        time.sleep(1.0)
        cap("background", "hidden tasks and the tray", bool(h), "the tray is Quire's; the taskbar ring and badge "
            "are Launcher3's (not built)")
        d.sh("input keyevent KEYCODE_ESCAPE")
        for _ in range(2):
            d.lab("REOPEN")
            time.sleep(0.8)
            d.sh("input keyevent KEYCODE_ESCAPE")
            time.sleep(0.8)

    def long_output(tag):
        desk(d, "files")
        openat(d, name="Notes · Trip planning", at=(700, 300))
        d.lab("SEND", text="Summarise this document and suggest next steps")
        time.sleep(4.5)
        d.key("KEYCODE_PAGE_UP")              # the person scrolls up while text still arrives
        time.sleep(0.8)
        # The UI can't be dumped while text streams (no idle state), so the note's own log says what it shows.
        pill = d.wait_log(r"note: jump to latest shown", tag, timeout=3)
        save = d.wait_log(r"note: save as a file offered \(width (\d+) dp\)", tag, timeout=3)
        cap("long-output", "wide, 60 % cap, scrolled up: Jump to latest and Save as a file", bool(pill and save),
            f"jump pill {'shown' if pill else 'missing'}; {save.group(0) if save else 'save missing'}", dump=False)
        d.sh("input keycombination KEYCODE_CTRL_LEFT KEYCODE_MOVE_END")
        time.sleep(0.8)
        gone = bool(d.wait_log(r"note: jump to latest hidden", tag, timeout=3))
        d.result(f"{theme}: long-output Ctrl+End jumps to the latest", gone, "pill gone" if gone else "pill still shown")
        agents.release()
        d.wait_log(r"ended stopReason", tag, timeout=15)
        first, listing = save_through_picker(d, "Save as a file", "Quire answer.md")
        ok = first is not None and first.startswith("**Summary of the trip notes**")
        d.result(f"{theme}: long-output Save as a file (Storage Access Framework)", ok,
                 f"Download/: {listing}; first line: {first}")

    def code(tag):
        desk(d, "files")
        openat(d, name="Files · Lisbon", at=(700, 300))
        d.lab("SEND", text="Write a script that renames these photos by the date they were taken")
        m = d.wait_log(r"ended stopReason=end_turn", tag, timeout=15)
        time.sleep(0.6)
        cap("code", "fenced code in message chunks, Save as file under the block", bool(m) and
            has_text(d, d.ui(), "Save as file"))
        first, listing = save_through_picker(d, "Save as file", "script.sh")
        ok = first is not None and first.startswith("# Rename photos")
        d.result(f"{theme}: code Save as file (Storage Access Framework)", ok, f"Download/: {listing}; first line: {first}")

    def images(tag):
        desk(d, "files")
        d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")    # a real screenshot for the intake
        d.wait_log(r"note: shown task", tag)
        clean(d)
        openat(d, intake="region", name="Region · Notes", at=(726, 548))
        d.lab("SEND", text="What's the schedule here, as a table?")
        m = d.wait_log(r"ended stopReason=end_turn", tag, timeout=15)
        time.sleep(0.6)
        cap("images", "an image ContentBlock over ACP", bool(m), "the agent sends the region it was given back")

    def no_agent(tag):
        desk(d, "settings")
        d.lab("ENDPOINT_REMOVE", id="cursor")
        d.lab("ENDPOINT_REMOVE", id="codex")
        d.lab("ENDPOINT", id="claude", name="Claude Code", where="on this laptop", address="tcp:127.0.0.1:7070",
              cwd="/home/brian", local=True, connected=False)
        openat(d)
        cap("no-agent", "nothing connected until the person chooses", True)
        clean(d)
        endpoints(d)

    for sid, fn in [("idle", idle), ("invoke-key", invoke_key), ("invoke-shake", invoke_shake),
                    ("invoke-secure", invoke_secure), ("invoke-taskbar", invoke_taskbar),
                    ("invoke-voice", invoke_voice), ("invoke-selection", invoke_selection), ("compose", compose),
                    ("agent-picker", picker), ("streaming", streaming), ("steps", steps_and_done), ("plan", plan),
                    ("consent", consent), ("consent-command", consent_command), ("control", control),
                    ("stopped", stopped), ("error", error), ("signin", signin), ("background", background),
                    ("long-output", long_output), ("code", code), ("images", images), ("no-agent", no_agent),
                    ("offline", offline)]:
        if only is None or sid in only:
            run(sid, fn)
    clean(d)


def side_by_side(d, capture, render, out):
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    a = Image.open(capture).convert("RGB")
    b = Image.open(render).convert("RGB") if render.exists() else Image.new("RGB", a.size, (128, 128, 128))
    b = b.resize(a.size)
    w, h = a.size
    canvas = Image.new("RGB", (w * 2 + 24, h + 56), (24, 24, 28))
    canvas.paste(a, (0, 56))
    canvas.paste(b, (w + 24, 56))
    dr = ImageDraw.Draw(canvas)
    dr.text((16, 18), f"Built: Cuttlefish, {capture.parent.name} ({capture.stem})", fill=(235, 235, 240))
    dr.text((w + 40, 18), f"Q3 render: {render.name}" if render.exists() else "no render", fill=(235, 235, 240))
    canvas.resize((canvas.width // 2, canvas.height // 2)).save(out, quality=85)


# ------------------------------------------------------------------------------------------------ keyboard
def keyboard(d, agents):
    d.log("== keyboard")
    d.sh("cmd uimode night no")
    clean(d)
    desk(d, "settings")
    tag = d.mark("keyboard")
    openat(d)
    d.key("KEYCODE_SHIFT_LEFT")      # a key press leaves touch mode, as a keyboard user is
    label, cls = d.focused()
    d.result("keyboard: focus on open", cls == "android.widget.EditText", f"{label!r} {cls}")
    d.sh("input text 'Turn%sthis%sinto%sa%schecklist%sfile%sin%smy%sDocuments'")
    d.key("KEYCODE_ENTER")
    m = d.wait_log(r"permission for", tag)
    time.sleep(1.0)
    label, cls = d.focused()
    d.result("keyboard: focus on the consent card when it arrives", bool(m) and "asks" in (label or ""),
             f"{label!r} {cls}")
    order = []
    for _ in range(3):
        before = d.focused()[0]
        d.key("KEYCODE_TAB")
        label = before
        for _ in range(6):     # the dump can lag the key by a frame or two
            label = d.focused()[0]
            if label != before:
                break
            time.sleep(0.3)
        order.append(label)
    d.result("keyboard: Tab order on the card, reject first", order[:3] == ["Don’t allow", "Allow for this session",
                                                                           "Allow"], f"{order}")
    d.screencap("keyboard/consent-tab-allow.png")
    d.key("KEYCODE_SHIFT_LEFT")
    d.sh("input keycombination KEYCODE_SHIFT_LEFT KEYCODE_TAB")
    d.sh("input keycombination KEYCODE_SHIFT_LEFT KEYCODE_TAB")
    time.sleep(0.4)
    d.result("keyboard: Shift+Tab back to the reject option", d.focused()[0] == "Don’t allow", d.focused()[0])
    d.screencap("keyboard/consent-tab-deny.png")
    d.key("KEYCODE_ENTER")
    a = d.wait_log(r"answered (\w+)", tag)
    d.result("keyboard: Enter answers with the focused option", bool(a) and a.group(1) == "deny",
             a.group(0) if a else "no answer")
    d.wait_log(r"ended stopReason", tag)
    time.sleep(0.6)
    d.screencap("keyboard/denied.png")
    d.key("KEYCODE_ESCAPE")
    c = d.wait_log(r"note: closed task", tag)
    d.result("keyboard: Esc closes a finished note", bool(c), c.group(0) if c else "not closed")

    # Esc at consent stops the run and answers the request "cancelled" (§3.3 rule 4).
    tag = d.mark("keyboard esc-consent")
    openat(d)
    d.key("KEYCODE_SHIFT_LEFT")
    d.sh("input text 'Turn%sthis%sinto%sa%schecklist%sfile%sin%smy%sDocuments'")
    d.key("KEYCODE_ENTER")
    d.wait_log(r"permission for", tag)
    time.sleep(0.6)
    d.key("KEYCODE_ESCAPE")
    a = d.wait_log(r"answered (\w+)", tag)
    s = d.wait_log(r"ended stopReason=(\w+)", tag)
    d.result("keyboard: Esc at consent answers cancelled and stops", bool(a) and a.group(1) == "cancelled" and
             bool(s) and s.group(1) == "cancelled", f"{a.group(0) if a else '-'}; {s.group(0) if s else '-'}")
    time.sleep(0.6)
    d.screencap("keyboard/esc-at-consent.png")
    d.key("KEYCODE_ESCAPE")

    # Esc mid-run stops; it never hides (§6.1).
    tag = d.mark("keyboard esc-run")
    openat(d)
    d.key("KEYCODE_SHIFT_LEFT")
    d.sh("input text 'stop%sme%swhen%syou%slike'")
    d.key("KEYCODE_ENTER")
    time.sleep(2.0)
    d.key("KEYCODE_ESCAPE")
    s = d.wait_log(r"ended stopReason=(\w+)", tag)
    hid = re.search(r"note: hid task", d.since(tag))
    d.result("keyboard: Esc mid-run stops and doesn't hide", bool(s) and s.group(1) == "cancelled" and not hid,
             s.group(0) if s else "not stopped")
    d.key("KEYCODE_ESCAPE")

    # Meta+Space hides a running task and brings it back where it was (§6.1).
    tag = d.mark("keyboard hide")
    openat(d)
    d.key("KEYCODE_SHIFT_LEFT")
    d.sh("input text 'stop%sme%swhen%syou%slike'")
    d.key("KEYCODE_ENTER")
    time.sleep(1.5)
    d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")
    h = d.wait_log(r"note: hid task (\d+) running=true", tag)
    time.sleep(1.0)
    d.screencap("keyboard/hidden.png")
    d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")
    r = d.wait_log(r"note: reopened task (\d+) running=true", tag)
    time.sleep(1.0)
    d.screencap("keyboard/reopened.png")
    d.result("keyboard: Meta+Space hides a running task and brings it back", bool(h and r) and
             h.group(1) == r.group(1), f"{h.group(0) if h else '-'}; {r.group(0) if r else '-'}")
    d.key("KEYCODE_ESCAPE")
    d.key("KEYCODE_ESCAPE")
    clean(d)


# ------------------------------------------------------------------------------------------------ a11y
def a11y(d):
    d.log("== a11y")
    missing, checked, panes, live = [], 0, 0, 0
    for xml_path in sorted((d.o / "light").glob("*.xml")):
        for n in d.nodes(xml_path.read_text()):
            if n.get("package") != QUIRE:
                continue
            if n.get("pane-title") == "Quire" or "Quire" in (n.get("pane-title") or ""):
                panes += 1
            if (n.get("clickable") == "true" or n.get("focusable") == "true") and n.get("enabled") == "true":
                checked += 1
                label = (n.get("content-desc") or n.get("text") or n.get("hint") or "").strip()
                if not label and n.get("class") != "android.widget.EditText":
                    missing.append(f"{xml_path.stem}: {n.get('class')} {n.get('bounds')}")
    d.result("a11y: every focusable or clickable control in the note has a label", not missing,
             f"{checked} controls in {len(list((d.o / 'light').glob('*.xml')))} dumps"
             + (f"; unlabelled: {missing[:8]}" if missing else ""))
    d.result("a11y: TalkBack itself", None, "TalkBack is not in AOSP; the labels, roles and live regions are checked "
             "from the dumps; the TalkBack walkthrough is for the G14 with TalkBack installed")


# ------------------------------------------------------------------------------------------------ motion
def motion(d):
    d.log("== motion")
    d.sh("cmd uimode night no")
    clean(d)
    old = d.sh("settings get global animator_duration_scale").strip()
    d.sh("settings put global animator_duration_scale 0")
    time.sleep(1.0)
    tag = d.mark("motion")
    openat(d)
    u = d.wait_log(r"note: unfold animated=(\w+)", tag)
    d.screencap("motion/remove-animations-open.png")
    d.lab("ESC")
    f = d.wait_log(r"note: fold into=\S+ animated=(\w+)", tag)
    d.result("motion: Remove animations cuts the unfold and the fold", bool(u and f) and u.group(1) == "false" and
             f.group(1) == "false", f"{u.group(0) if u else '-'}; {f.group(0) if f else '-'}")
    d.sh(f"settings put global animator_duration_scale {old if old not in ('', 'null') else 1}")
    time.sleep(1.0)
    tag = d.mark("motion on")
    openat(d)
    u = d.wait_log(r"note: unfold animated=(\w+)", tag)
    d.result("motion: with animations on the note unfolds with spring.unfold", bool(u) and u.group(1) == "true",
             u.group(0) if u else "-")
    clean(d)


# ------------------------------------------------------------------------------------------------ frames
def frames(d, agents):
    d.log("== frames")
    d.sh("cmd uimode night no")
    clean(d)
    desk(d, "settings")
    d.sh(f"dumpsys gfxinfo {QUIRE} reset >/dev/null")
    tag = d.mark("frames")
    for _ in range(3):
        openat(d)
        d.lab("SEND", text="What does Adaptive brightness do here?")
        time.sleep(2.0)
        agents.release()
        d.wait_log(r"ended stopReason", tag, timeout=15)
        d.lab("ESC")
        time.sleep(0.8)
        openat(d)
        d.lab("SEND", text="Turn this into a checklist file in my Documents")
        d.wait_log(r"permission for", tag)
        time.sleep(0.5)
        d.tap_text("Allow")
        d.wait_log(r"ended stopReason", tag)
        d.lab("ESC")
        time.sleep(0.8)
        tag = d.mark("frames again")
    out = d.sh(f"dumpsys gfxinfo {QUIRE}")
    (d.o / "gfxinfo.txt").write_text(out)
    tot = re.search(r"Total frames rendered: (\d+)", out)
    jank = re.search(r"Janky frames: (\d+) \(([\d.]+)%\)", out)
    p90 = re.search(r"90th percentile: (\d+)ms", out)
    p99 = re.search(r"99th percentile: (\d+)ms", out)
    d.result("frames: Quire's frames over open, stream, consent and fold (Cuttlefish)", None,
             f"total {tot.group(1) if tot else '?'}, janky {jank.group(1) + ' (' + jank.group(2) + '%)' if jank else '?'}"
             f", p90 {p90.group(1) if p90 else '?'} ms, p99 {p99.group(1) if p99 else '?'} ms; the acceptance "
             "measurement is the G14's")


# ------------------------------------------------------------------------------------------------ video
class Recording:
    """`screenrecord` on the device for one flow; pulled into OUTDIR/video/NAME.mp4."""

    def __init__(self, d, name, seconds=20):
        self.d, self.name = d, name
        # On shared storage: MediaProvider scans the file, and it may not look in /data/local/tmp.
        self.remote = f"/sdcard/Movies/q5-{name}.mp4"
        d.sh(f"rm -f {self.remote}")
        self.p = subprocess.Popen([d.adb, "-s", d.s, "shell", "screenrecord", "--time-limit", str(seconds),
                                   "--bit-rate", "8000000", self.remote], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        time.sleep(1.0)

    def stop(self):
        self.d.sh("pkill -INT screenrecord")
        try:
            self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill()
        time.sleep(1.0)
        out = self.d.o / "video" / f"{self.name}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        self.d.run("pull", self.remote, str(out))
        return out


def video(d, agents):
    """Videos of the flows (acceptance 1): the shake and the halo, a turn and the fold; consent; the mirror."""
    d.log("== video")
    d.sh("cmd uimode night no")
    clean(d)
    desk(d, "settings")
    rec = Recording(d, "invoke-stream-fold", 24)
    mouse = Mouse(d)
    try:
        tag = d.mark("video shake")
        mouse.move(-300, -200)
        time.sleep(0.6)
        m = None
        for _ in range(3):
            mouse.shake()
            m = d.wait_log(r"note: invocation anchor=(\S+)", tag, timeout=5)
            if m:
                break
            time.sleep(3.5)
        time.sleep(1.2)
        d.sh("input text 'What%sdoes%sAdaptive%sbrightness%sdo%shere?'")
        d.key("KEYCODE_ENTER")
        time.sleep(3.0)
        agents.release()
        d.wait_log(r"ended stopReason", tag, timeout=15)
        time.sleep(1.0)
        d.key("KEYCODE_ESCAPE")
        time.sleep(1.5)
    finally:
        mouse.close()
    out = rec.stop()
    d.result("video: shake, halo, note at the pointer, a turn, fold", bool(m) and "pointer" in (m.group(1) if m else ""),
             f"{out.name}; {m.group(0) if m else 'no invocation'}")
    frames_of(d, out, "invoke-stream-fold")

    clean(d)
    desk(d, "files")
    rec = Recording(d, "consent", 16)
    tag = d.mark("video consent")
    openat(d, intake="selection", name="Notes", at=(700, 520), text="Things to pack: the HDMI adapter, walking shoes")
    d.sh("input text 'Turn%sthis%sinto%sa%schecklist%sfile%sin%smy%sDocuments'")
    d.key("KEYCODE_ENTER")
    d.wait_log(r"permission for", tag)
    time.sleep(1.5)
    d.key("KEYCODE_TAB", "KEYCODE_TAB", "KEYCODE_TAB")
    time.sleep(0.8)
    d.key("KEYCODE_ENTER")
    a = d.wait_log(r"answered (\w+)", tag)
    d.wait_log(r"ended stopReason", tag)
    time.sleep(1.5)
    d.key("KEYCODE_ESCAPE")
    time.sleep(1.2)
    out = rec.stop()
    d.result("video: consent by keyboard, Allow", bool(a) and a.group(1) == "allow", f"{out.name}; {a.group(0) if a else '-'}")

    clean(d)
    d.sh(f"am force-stop {SETTINGS}")
    desk(d, "files")
    rec = Recording(d, "mirror", 40)
    tag = d.mark("video mirror")
    d.lab("CONTROL", prompt="In Settings, turn on Dark theme", app="Settings", launch=SETTINGS,
          taps=json.dumps(TAPS), x=1400.0, y=300.0, aimMs="1500")
    d.wait_log(r"cc: pending", tag)
    time.sleep(1.5)
    d.tap_text("Only this time")
    t = d.wait_log(r'note: control aiming at "Use Dark theme"', tag, timeout=25)
    time.sleep(0.5)
    d.lab("MIRROR", action="pause")
    time.sleep(2.5)
    d.lab("MIRROR", action="takeover")
    h = d.wait_log(r"cc: lifecycle: closed reason=4", tag)
    time.sleep(2.0)
    out = rec.stop()
    d.sh("cmd uimode night no")
    d.result("video: platform consent, the mirror zooming on each control, pause, take over", bool(t and h),
             f"{out.name}")
    frames_of(d, out, "mirror")
    d.sh(f"am force-stop {SETTINGS}")


def frames_of(d, video_path, name):
    """A contact sheet of the video, one frame every 0.5 s, for the evidence."""
    sheet = d.o / "video" / f"{name}-sheet.jpg"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video_path), "-vf",
                    "fps=2,scale=480:-1,tile=6x6", "-frames:v", "1", "-q:v", "4", str(sheet)])


# ------------------------------------------------------------------------------------------------ contrast
def contrast(d):
    """§8: the note's pairs on the device's own palette, and on every wallpaper's predicted palette."""
    d.log("== contrast")
    pal = {}
    for theme in ("light", "dark"):
        d.sh(f"cmd uimode night {'yes' if theme == 'dark' else 'no'}")
        time.sleep(2)
        tag = d.mark(f"palette {theme}")
        d.lab("PALETTE")
        m = d.wait_log(r"note: palette (\w+) (\{.*\})", tag)
        if m:
            pal[m.group(1)] = json.loads(m.group(2))
    d.sh("cmd uimode night no")
    (d.o / "device-palette.json").write_text(json.dumps(pal, indent=1))
    py = Path.home() / "anybook/tools-local/brand-venv/bin/python"
    if not py.exists() or len(pal) < 2:
        d.result("contrast: the note's pairs on every wallpaper and on the device", None,
                 f"skipped: palette {sorted(pal)}, brand venv {'present' if py.exists() else 'missing'}")
        return
    r = subprocess.run([str(py), "-I", str(HERE / "q5-contrast.py"), "--md", "--device",
                        str(d.o / "device-palette.json")], capture_output=True, text=True)
    (d.o / "contrast.md").write_text(r.stdout)
    dev = [l for l in r.stdout.splitlines() if l.startswith("device")]
    d.result("contrast: 16 pairs on 8 wallpapers x 2 themes and on the device's palette", r.returncode == 0,
             "; ".join(dev) or r.stderr.strip())


# ------------------------------------------------------------------------------------------------ health
def health(d):
    d.log("== health")
    crash = d.sh("logcat -d -b crash")
    quire_crash = [l for l in crash.splitlines() if QUIRE in l and "FATAL" in l or "Process: dev.openbook.quire" in l]
    d.result("health: no Quire crash", not quire_crash, quire_crash[:3] if quire_crash else "crash buffer clean of Quire")
    (d.o / "crash-buffer.txt").write_text(crash)
    events = d.sh("logcat -d -b events -s am_crash am_anr am_proc_start")
    anr = [l for l in events.splitlines() if "am_anr" in l]
    sysui = [l for l in events.splitlines() if "am_proc_start" in l and "com.android.systemui" in l]
    d.result("health: no ANR", not anr, anr[:3] if anr else "none")
    d.result("health: SystemUI did not restart", len(sysui) == 0, f"{len(sysui)} SystemUI starts since the log began")
    # The kernel's ring buffer can have rotated since boot; logcat keeps the audit lines too.
    denials = [l for l in (d.sh("dmesg") + d.sh("logcat -d -b all")).splitlines() if "avc:" in l and "denied" in l]
    quire = [l for l in denials if "platform_app" in l or "dev.openbook.quire" in l]
    d.result("health: no SELinux denial for Quire (platform_app)", not quire, quire[:3] if quire else "none")
    new = [l for l in denials if not any(k in l for k in KNOWN_DENIALS)]
    (d.o / "selinux-denials.txt").write_text("\n".join(denials))
    d.result("health: no new SELinux denials", not new, f"{len(denials)} denials, new: {new[:3]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("serial")
    ap.add_argument("out")
    ap.add_argument("--design", help="Q3's docs/quire-design/ (png/ renders) for side-by-side images")
    ap.add_argument("--only", default="states,keyboard,a11y,motion,frames,video,contrast,health")
    ap.add_argument("--themes", default="light,dark")
    ap.add_argument("--states", help="only these state recipes (comma-separated), e.g. control,stopped")
    args = ap.parse_args()
    d = Dev(args.serial, args.out)
    d.run("root")
    time.sleep(2)
    d.run("wait-for-device")
    d.sh("settings put system screen_off_timeout 1800000")
    d.run("logcat", "-G", "16M")
    agents = Agents(d)
    sections = args.only.split(",")
    try:
        endpoints(d)
        if "states" in sections:
            for theme in args.themes.split(","):
                states(d, agents, theme, args.design, args.states.split(",") if args.states else None)
        if "keyboard" in sections:
            keyboard(d, agents)
        if "a11y" in sections:
            a11y(d)
        if "motion" in sections:
            motion(d)
        if "frames" in sections:
            frames(d, agents)
        if "video" in sections:
            video(d, agents)
        if "contrast" in sections:
            contrast(d)
        if "health" in sections:
            health(d)
    finally:
        agents.stop()
        d.sh("cmd uimode night no")
        # Sections can run as separate invocations into one OUTDIR; results accumulate.
        new = not (d.o / "results.tsv").exists()
        with open(d.o / "results.tsv", "a") as f:
            if new:
                f.write("check\tresult\tdetail\n")
            for c, r, det in d.results:
                f.write(f"{c}\t{r}\t{det}\n")
        n = {k: sum(1 for _, r, _ in d.results if r == k) for k in ("PASS", "FAIL", "INFO")}
        d.log(f"== {n['PASS']} PASS, {n['FAIL']} FAIL, {n['INFO']} INFO")


if __name__ == "__main__":
    main()
