#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Quire on an installed OpenBook (ANAL-225): Q2, Q5 and Q4 together, the way the person meets them. Runs against the
G14 over adb, or the OTA rehearsal VM (scripts/ota/ota-qemu.py) before it.

usage: g14-quire-check.py SERIAL OUTDIR [--only SECTION,...] [--prompt TEXT] [--expect TEXT]

Sections, in order:
  facts    Quire is the assistant and a privileged system app; AVF and KVM (ro.boot.hypervisor.vm.supported); the
           Terminal app and its agent bridge; the Linux environment's state as Quire core sees it.
  invoke   On the desktop (Home: a surface that lets the note show): a pointer shake (a virtual USB mouse made with
           `uinput`) and Meta+Space each open the note, which must be on screen (the window titled "Quire",
           isOnScreen) and beside the pointer (its frame within reach of the pointer's position from dumpsys input).
           Esc closes it. Then with Settings in front, Meta+Space: the note is made but hidden, because Settings hides
           other apps' overlays. That is the reviewed behaviour (docs/quire.md §8 item 10), reported, not failed.
  agent    On the desktop, Meta+Space; the note lists the agents quired reports in the Linux environment; the person's
           steps: "Connect <agent>" (skipped when one is connected already), PROMPT typed with `input text`, Enter; the
           answer streams into the note and must contain EXPECT. Needs the Linux environment running
           (scripts/quire/linux-env-adb.sh check). Nothing is sent another way: if typing doesn't reach the note, the
           section fails there.
  control  The computer-control demo on Settings: the platform's consent dialog, "Only this time", the live mirror,
           taps on Display and Dark theme through the session (it opens the page and changes nothing), then Stop.
  health   Since this run started: crashes and ANRs of Quire, SystemUI and the Terminal app; tombstones; SELinux
           denials naming Quire, the Terminal app, crosvm or virtualization.

The screen must be unlocked: the check wakes it but never unlocks it (on the G14 that is the owner's PIN). Locked, the
screen-driving sections are skipped and reported as failed for that reason.
Changes nothing the person set: no app is installed, no setting is changed, the demo only opens pages. Home brings the
desktop forward, so open windows go to the taskbar, where they stay. Screen-driving: run it only while nobody uses the
device. Commands that are not a person's (the control demo's plan, the check's
markers) go through Quire's lab receiver, which only root reaches on a debuggable build, so adbd is made root and put
back to unroot at the end if it was not root before.
Writes OUTDIR/results.tsv (check, PASS/FAIL/INFO, detail), OUTDIR/checks.log, screenshots and UI dumps.
Env: ADB (default ~/anybook/android-sdk/platform-tools/adb); ANDROID_ADB_SERVER_PORT for a private server.
"""
import argparse
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("q2check", HERE / "q2-cf-check.py")
q2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(q2)

QUIRE = "dev.openbook.quire"
SETTINGS = "com.android.settings"
TERMINAL = "com.android.virtualization.terminal"
NOTE_LAB = f"{QUIRE}/.note.LabReceiver"
CONTROL_LAB = f"{QUIRE}/.control.LabActivity"
# The demo opens Display, then Dark theme, and taps nothing that changes a setting.
TAPS = [["Display", "Tapping Display", "Opened Display"],
        ["Dark theme", "Tapping Dark theme", "Opened Dark theme"]]
POINTER_RE = r"note: shown task (\d+) phase=(\w+) anchor=(\w+)"
# The note's window title (note/NoteWindow.kt); the tray and the consent card have their own.
NOTE_TITLE = "Quire"
# How far the note's frame may be from the pointer and still be "beside" it, in pixels (it opens next to the pointer,
# flipped or shifted to stay on screen).
NEAR_PX = 400


class Dev(q2.Dev):
    def note(self, verb, **extras):
        args = []
        for k, v in extras.items():
            if isinstance(v, float):
                args += ["--ef", k, str(v)]
            else:
                args += ["--es", k, f"'{v}'"]
        return self.sh(f"am broadcast -n {NOTE_LAB} -a dev.openbook.quire.lab.{verb} " + " ".join(args))

    def since(self, tag):
        text = self.quire_log()
        return text[text.rfind(tag):] if tag in text else ""

    def texts(self, xml):
        try:
            root = q2.ET.fromstring(xml)
        except q2.ET.ParseError:
            return []
        return [n.get("text") or n.get("content-desc") or "" for n in root.iter("node")
                if n.get("package") == QUIRE]

    def tap_text(self, text, timeout=10, prefix=False):
        end = time.time() + timeout
        while time.time() < end:
            try:
                root = q2.ET.fromstring(self.ui())
            except q2.ET.ParseError:
                time.sleep(0.5)
                continue
            for n in root.iter("node"):
                t = n.get("text") or ""
                if t == text or (prefix and t.startswith(text)):
                    self.tap_node(n)
                    return t
            time.sleep(0.5)
        return None

    def unlocked(self):
        """Wakes the screen; returns (unlocked, detail): the user's storage unlocked and no keyguard showing."""
        self.sh("input keyevent KEYCODE_WAKEUP")
        time.sleep(1)
        user = self.sh("am get-started-user-state 0").strip()
        m = re.search(r"(?i)keyguardShowing[=:]\s*(true|false)", self.sh("dumpsys activity activities | grep -i keyguard"))
        keyguard = m.group(1).lower() if m else "unknown"
        return "RUNNING_UNLOCKED" in user and keyguard == "false", f"user={user} keyguardShowing={keyguard}"

    def pointer(self):
        """The mouse pointer's position in display pixels, from dumpsys input's pointer controller, or None."""
        dump = self.sh("dumpsys input")
        self.write("dumpsys-input-pointer.txt", "\n".join(l for l in dump.splitlines()
                                                         if re.search(r"(?i)pointer|position|cursor", l))[:20000])
        for rx in (r"Pointer\(id=\d+, MOUSE\) at \((-?[\d.]+), (-?[\d.]+)\)",  # input dispatcher (Android 17)
                   r"(?i)cursor position[:=]\s*\(?\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)",
                   r"(?i)\bposition[:=]\s*\(?\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)",
                   r"(?i)pointerX[:=]\s*(-?[\d.]+)\W+pointerY[:=]\s*(-?[\d.]+)"):
            m = re.search(rx, dump)
            if m:
                return float(m.group(1)), float(m.group(2))
        return None

    def note_card(self, xml):
        """The note card's bounds on screen: the union of Quire's labelled nodes in a UI dump (the window itself may
        span the display while the note unfolds), or None."""
        try:
            root = q2.ET.fromstring(xml)
        except q2.ET.ParseError:
            return None
        boxes = [list(map(int, re.findall(r"-?\d+", n.get("bounds")))) for n in root.iter("node")
                 if n.get("package") == QUIRE and (n.get("text") or n.get("content-desc"))]
        if not boxes:
            return None
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))

    def note_window(self):
        """The note's window from dumpsys window: (frame, on screen), or None when there is none."""
        dump = self.sh("dumpsys window windows")
        self.write("dumpsys-window-last.txt", dump)
        for block in dump.split("Window #")[1:]:
            if not re.match(r"\d+ Window\{\w+ u\d+ " + re.escape(NOTE_TITLE) + r"\}:", block):
                continue
            m = re.search(r"Frames:.*? frame=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", block)
            return (tuple(map(int, m.groups())) if m else None), "isOnScreen=true" in block
        return None


def settings_on_screen(d):
    d.sh(f"am start -W -a android.settings.SETTINGS")
    time.sleep(2)


def desktop(d):
    d.sh("input keyevent KEYCODE_HOME")
    time.sleep(1.5)


def close_note(d):
    d.sh("input keyevent KEYCODE_ESCAPE")
    time.sleep(1.5)
    w = d.note_window()
    if w is not None and w[1]:
        d.note("CLOSE")
        time.sleep(1)


def beside(ptr, frame):
    """Whether the frame is within NEAR_PX of the pointer, and the distance; None when either is unknown."""
    if not ptr or not frame:
        return None, None
    dx = max(frame[0] - ptr[0], 0, ptr[0] - frame[2])
    dy = max(frame[1] - ptr[1], 0, ptr[1] - frame[3])
    dist = (dx * dx + dy * dy) ** 0.5
    return dist <= NEAR_PX, dist


def facts(d):
    d.log("== facts")
    pkg = d.sh(f"dumpsys package {QUIRE} | grep -E 'versionName|codePath|privateFlags|pkgFlags' | head -6")
    d.write("quire-package.txt", pkg)
    d.result("Quire installed as a privileged system app", "PRIVILEGED" in pkg and "/system_ext/priv-app" in pkg,
             " ".join(pkg.split())[:200])
    role = d.sh("cmd role get-role-holders android.app.role.ASSISTANT").strip()
    d.result("Quire holds the assistant role", role == QUIRE, role or "none")
    feat = d.sh("pm list features | grep -c virtualization_framework").strip()
    hyp = d.sh("getprop ro.boot.hypervisor.vm.supported").strip()
    kvm = d.sh("getprop vendor.openbook.kvm").strip()
    d.result("AVF in the image and KVM on (ro.boot.hypervisor.vm.supported)", feat == "1" and hyp == "1",
             f"feature={feat} vm.supported={hyp} vendor.openbook.kvm={kvm}")
    term = d.sh(f"pm list packages -s {TERMINAL}; pm dump {TERMINAL} | grep -m3 -E 'enabled=|agentbridge'")
    d.result("the Terminal app and its agent bridge", TERMINAL in term and "agentbridge" in term,
             " ".join(term.split())[:200])
    tag = d.mark("facts")
    d.sh(f"am start -n {CONTROL_LAB} -a dev.openbook.quire.lab.AGENTS_STATUS >/dev/null 2>&1")
    m = d.wait_log(r"agents: status (.*)", 20, since=tag)
    d.result("the Linux environment as Quire core sees it", None, m.group(1) if m else "no status logged")


def invoke(d):
    d.log("== invoke")
    mouse = q2.Mouse(d)
    # A shake as a person makes it: 25-count strokes (the detector wants 12 dp back from each turn, ANAL-225).
    cases = [("shake", "system_action", lambda: mouse.shake(amplitude=25)),
             ("meta_space", "assistant_shortcut",
              lambda: d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE"))]
    for name, trigger, act in cases:
        desktop(d)
        for _ in range(3):  # the pointer moves a little, as a person's does before shaking
            mouse.move(-15, -10)
            time.sleep(0.05)
        time.sleep(3.5)  # SystemUI's shake cooldown is 3 s
        tag = d.mark(name)
        act()
        m = d.wait_log(r"invocation: trigger=(\S+)", 8 if name == "shake" else 20, since=tag)
        for attempt in (2, 3):  # a person shakes again when nothing happens
            if m or name != "shake":
                break
            d.log(f"shake: no invocation yet, attempt {attempt}")
            time.sleep(3.5)
            act()
            m = d.wait_log(r"invocation: trigger=(\S+)", 8, since=tag)
        shown = d.wait_log(POINTER_RE, 10, since=tag)
        time.sleep(1.2)
        ptr, w = d.pointer(), d.note_window()
        on_screen = bool(w and w[1])
        d.screencap(f"invoke-{name}.png")
        xml = d.ui()
        d.write(f"invoke-{name}-ui.xml", xml)
        frame = d.note_card(xml)
        d.result(f"{name}: Quire's note opened and is on screen",
                 bool(m) and m.group(1) == trigger and bool(shown) and on_screen,
                 (f"trigger={m.group(1)}" if m else "no invocation logged") +
                 (f"; shown task {shown.group(1)} phase={shown.group(2)}" if shown else "; note not shown") +
                 f"; window '{NOTE_TITLE}' {'on screen' if on_screen else 'not on screen' if w else 'absent'}")
        near, dist = beside(ptr, frame)
        d.result(f"{name}: the note beside the pointer",
                 bool(shown) and shown.group(3) == "Pointer" and on_screen and near is True,
                 f"anchor={shown.group(3) if shown else '-'} pointer={ptr} note card={frame}" +
                 (f" distance={dist:.0f}px (limit {NEAR_PX})" if dist is not None else " (geometry unknown)"))
        close_note(d)
    mouse.close()
    # The reviewed behaviour over Settings: the note is made, and hidden while Settings is in front.
    settings_on_screen(d)
    tag = d.mark("over-settings")
    d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")
    shown = d.wait_log(POINTER_RE, 20, since=tag)
    time.sleep(1.2)
    w = d.note_window()
    hidden = "mIsForceHiddenNonSystemOverlayWindow=true" in d.sh(
        f"dumpsys window windows | grep -A400 'Window{{[0-9a-f]* u0 {NOTE_TITLE}}}' | head -400")
    d.screencap("invoke-over-settings.png")
    d.result("over Settings: the note is made and hidden (Settings hides overlays; reviewed behaviour)", None,
             (f"shown task {shown.group(1)}" if shown else "no note logged") +
             f"; on screen={bool(w and w[1])}; force-hidden={hidden}")
    close_note(d)
    d.note("CLOSE")
    d.sh(f"am force-stop {SETTINGS}")


def agent(d, prompt, expect):
    d.log("== agent")
    desktop(d)
    tag = d.mark("agent")
    d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")
    shown = d.wait_log(POINTER_RE, 20, since=tag)
    time.sleep(1)
    w = d.note_window()
    if not shown or not (w and w[1]):
        d.result("agent: the note is on screen", False, ("shown" if shown else "not shown") + f"; window {w}")
        return
    task = shown.group(1)
    found = d.wait_log(r"acp: found in the Linux environment: (.*)", 20, since=tag)
    time.sleep(1)
    d.note("DUMP")
    time.sleep(1)
    agents = re.findall(r"lab: agent (linux:\S+) \S+ connected=(\w+) state=\w+ name=(.*)", d.since(tag))
    d.result("agent: the note lists the Linux environment's agents", bool(agents),
             (f"new: {found.group(1)}; " if found else "") + ", ".join(f"{a} connected={c}" for a, c, _ in agents))
    if not agents:
        d.write("agent-log.txt", d.since(tag))
        return
    if shown.group(2) == "NO_AGENT":
        d.screencap("agent-connect.png")
        d.write("agent-connect-ui.xml", d.ui())
        tapped = d.tap_text(f"Connect {agents[0][2].strip()}")
        d.result("agent: the person connects it in the note", bool(tapped), tapped or "no Connect button")
        if not tapped:
            return
        time.sleep(1.5)
    else:
        d.result("agent: an agent is connected already", None, f"the note opened in {shown.group(2)}")
    d.sh("input text '" + prompt.replace(" ", "%s").replace("'", "") + "'")
    time.sleep(0.8)
    d.sh("input keyevent KEYCODE_ENTER")
    sent = d.wait_log(rf"note: task {task} prompt \((\d+) blocks\)", 10, since=tag)
    d.result("agent: the typed prompt was sent (input text, Enter)", bool(sent),
             f"{sent.group(1)} content blocks" if sent else "no prompt from the note in 10 s")
    if not sent:
        d.screencap("agent-not-sent.png")
        d.write("agent-log.txt", d.since(tag))
        close_note(d)
        return
    session = d.wait_log(rf"note: task {task} session (\S+) with (\S+)", 60, since=tag)
    d.result("agent: the prompt went to the agent in the Linux environment",
             bool(session) and session.group(2).startswith("linux:"),
             f"session {session.group(1)} with {session.group(2)}" if session else "no session")
    t0 = time.time()
    end = d.wait_log(rf"note: task {task} ended stopReason=(\w+)", 240, since=tag)
    secs = time.time() - t0
    time.sleep(1.5)
    xml = d.ui()
    d.write("agent-answer-ui.xml", xml)
    d.screencap("agent-answer.png")
    texts = " | ".join(t for t in d.texts(xml) if t)
    d.write("agent-note-texts.txt", texts + "\n")
    d.result("agent: an answer in the note", bool(end) and end.group(1) == "end_turn" and expect in texts,
             (f"stopReason={end.group(1)} after {secs:.1f} s" if end else "no end in 240 s") +
             f"; '{expect}' {'shown' if expect in texts else 'not shown'}")
    d.write("agent-log.txt", d.since(tag))
    close_note(d)


def control(d):
    d.log("== control")
    d.sh(f"am force-stop {SETTINGS}")
    tag = d.mark("control")
    d.note("CONTROL", prompt="Show me the Dark theme setting", app="Settings", launch=SETTINGS,
           taps=json.dumps(TAPS), x=1400.0, y=300.0, aimMs="2500")
    pending = d.wait_log(r"cc: pending", 20, since=tag)
    time.sleep(1.5)
    d.screencap("control-consent.png")
    d.result("control: the platform's consent dialog", bool(pending), pending.group(0) if pending else "no dialog")
    if not d.tap_text("Only this time"):
        d.result("control: consent given (Only this time)", False, "no 'Only this time' button")
        return
    created = d.wait_log(r"cc: created: display (\d+x\d+)", 20, since=tag)
    aim = d.wait_log(r'note: control aiming at "Dark theme"', 40, since=tag)
    time.sleep(1.0)
    d.screencap("control-mirror.png")
    done = d.wait_log(r"note: control run complete", 40, since=tag)
    d.result("control: Settings driven through the session, shown in the mirror", bool(created and aim and done),
             (created.group(0) if created else "no session") + ("; Display, then Dark theme" if aim else "") +
             ("; complete" if done else "; not complete"))
    d.note("MIRROR", action="stop")
    ended = d.wait_log(r"note: control run ended", 20, since=tag) or d.wait_log(r"cc: lifecycle: closed", 5, since=tag)
    d.result("control: Stop ends the session", bool(ended), ended.group(0) if ended else "no end logged")
    night = d.sh("cmd uimode night").strip()
    d.result("control: nothing changed (Dark theme as before)", None, night)
    d.write("control-log.txt", d.since(tag))
    close_note(d)
    d.sh(f"am force-stop {SETTINGS}")


def health(d, since):
    d.log("== health")
    crash = d.sh(f"logcat -d -b crash -t '{since}'")
    d.write("logcat-crash.txt", crash)
    ours = [l for l in crash.splitlines() if re.search(r"quire|systemui|virtualization|crosvm", l, re.I)]
    d.result("no crash of Quire, SystemUI or the Terminal app", not ours, f"{len(ours)} lines")
    events = d.sh(f"logcat -d -b events -t '{since}' | grep -E 'am_crash|am_anr|am_native_crash'")
    d.write("events-crash-anr.txt", events)
    bad = [l for l in events.splitlines() if re.search(r"quire|systemui|virtualization", l, re.I)]
    d.result("no ANR or crash event for them", not bad, f"{len(bad)} events" + (": " + bad[0][:160] if bad else ""))
    denials = d.sh(f"logcat -d -b all -t '{since}' | grep 'avc:  denied' | "
                   "sed -E 's/.*avc:  denied/avc: denied/; s/ pid=[0-9]+//; s/ ino=[0-9]+//' | sort | uniq -c | sort -rn")
    d.write("selinux-denials.txt", denials)
    ours = [l for l in denials.splitlines() if re.search(r"quire|platform_app|virtualization|crosvm|virtmgr", l)]
    d.result("no SELinux denial for Quire or the Linux environment", not ours,
             f"{len(denials.splitlines())} distinct since start, {len(ours)} ours" +
             (": " + " | ".join(o.strip() for o in ours[:3]) if ours else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("serial")
    ap.add_argument("outdir")
    ap.add_argument("--only", default="facts,invoke,agent,control,health")
    ap.add_argument("--prompt", default="Reply with exactly: QUIRE OK")
    ap.add_argument("--expect", default="QUIRE OK")
    a = ap.parse_args()
    d = Dev(a.serial, a.outdir)
    was_root = d.sh("id -u").strip() == "0"
    d.run("root")
    time.sleep(3)
    d.run("wait-for-device", timeout=60)
    since = d.sh("date '+%m-%d %H:%M:%S.000'").strip()
    try:
        for name in a.only.split(","):
            if name in ("invoke", "agent", "control"):
                ok, detail = d.unlocked()
                if not ok:
                    d.result(f"{name}: the screen is unlocked (needed to drive it)", False, detail + "; section skipped")
                    continue
            if name == "health":
                health(d, since)
            elif name == "agent":
                agent(d, a.prompt, a.expect)
            else:
                globals()[name](d)
    finally:
        with open(d.o / "results.tsv", "w") as f:
            f.write("check\tresult\tdetail\n")
            for c, r, det in d.results:
                f.write(f"{c}\t{r}\t{det}\n")
        if not was_root:
            d.run("unroot")
    fails = sum(1 for _, r, _ in d.results if r == "FAIL")
    passes = sum(1 for _, r, _ in d.results if r == "PASS")
    d.log(f"== {passes} PASS, {fails} FAIL, {len(d.results) - passes - fails} INFO")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
