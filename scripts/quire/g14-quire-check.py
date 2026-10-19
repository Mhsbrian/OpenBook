#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Quire on an installed OpenBook (ANAL-225): Q2, Q5 and Q4 together, the way the person meets them. Runs against the
G14 over adb, or the OTA rehearsal VM (scripts/ota/ota-qemu.py) before it.

usage: g14-quire-check.py SERIAL OUTDIR [--only SECTION,...] [--prompt TEXT] [--expect TEXT]

Sections, in order:
  facts    Quire is the assistant and a privileged system app; AVF and KVM (ro.boot.hypervisor.vm.supported); the
           Terminal app and its agent bridge; the Linux environment's state as Quire core sees it.
  invoke   With Settings on screen: a pointer shake (a virtual USB mouse made with `uinput`) and Meta+Space each open
           the note, anchored at the pointer. Esc closes it.
  agent    Meta+Space; the note lists the agents quired reports in the Linux environment; the person's steps: "Connect
           <agent>" (skipped when one is connected already), type PROMPT, Enter; the answer streams into the note and
           must contain EXPECT. Needs the Linux environment running (scripts/quire/linux-env-adb.sh check).
  control  The computer-control demo on Settings: the platform's consent dialog, "Only this time", the live mirror,
           taps on Display and Dark theme through the session (it opens the page and changes nothing), then Stop.
  health   Since this run started: crashes and ANRs of Quire, SystemUI and the Terminal app; tombstones; SELinux
           denials naming Quire, the Terminal app, crosvm or virtualization.

Changes nothing the person set: no app is installed, no setting is changed, the demo only opens pages. Screen-driving:
run it only while nobody uses the device. Commands that are not a person's (the control demo's plan, the check's
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


class Dev(q2.Dev):
    def note(self, action, **extras):
        args = []
        for k, v in extras.items():
            if isinstance(v, float):
                args += ["--ef", k, str(v)]
            else:
                args += ["--es", k, f"'{v}'"]
        return self.sh(f"am broadcast -n {NOTE_LAB} -a dev.openbook.quire.lab.{action} " + " ".join(args))

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

    def pointer(self):
        """The mouse pointer's position in display pixels, from dumpsys input (PointerController)."""
        m = re.search(r"Position:\s*\(?\s*([\d.]+),\s*([\d.]+)", self.sh("dumpsys input | grep -A12 -i 'PointerController'"))
        return (float(m.group(1)), float(m.group(2))) if m else None

    def note_frame(self):
        """The note window's frame on screen, from dumpsys window (Quire's overlay)."""
        dump = self.sh("dumpsys window windows")
        for block in dump.split("Window #")[1:]:
            if QUIRE in block.splitlines()[0]:
                m = re.search(r"mFrame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]", block) or \
                    re.search(r"frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]", block)
                if m:
                    return tuple(map(int, m.groups()))
        return None


def settings_on_screen(d):
    d.sh(f"am start -W -a android.settings.SETTINGS")
    time.sleep(2)


def close_note(d):
    d.sh("input keyevent KEYCODE_ESCAPE")
    time.sleep(1.5)
    if d.note_frame() is not None:
        d.note("CLOSE")
        time.sleep(1)


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
    cases = [("shake", "system_action", lambda: mouse.shake()),
             ("meta_space", "assistant_shortcut",
              lambda: d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE"))]
    for name, trigger, act in cases:
        settings_on_screen(d)
        for _ in range(3):  # the pointer rests over Settings, as a person's would
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
        ptr, frame = d.pointer(), d.note_frame()
        d.screencap(f"invoke-{name}.png")
        d.write(f"invoke-{name}-ui.xml", d.ui())
        d.result(f"{name}: Quire's note opened", bool(m) and m.group(1) == trigger and bool(shown),
                 (f"trigger={m.group(1)}" if m else "no invocation logged") +
                 (f"; shown task {shown.group(1)} phase={shown.group(2)}" if shown else "; note not shown"))
        near = None
        if ptr and frame:
            dx = max(frame[0] - ptr[0], 0, ptr[0] - frame[2])
            dy = max(frame[1] - ptr[1], 0, ptr[1] - frame[3])
            near = (dx * dx + dy * dy) ** 0.5 < 400
        d.result(f"{name}: the note beside the pointer", bool(shown) and shown.group(3) == "Pointer" and near is not False,
                 f"anchor={shown.group(3) if shown else '-'} pointer={ptr} note frame={frame}")
        close_note(d)
    mouse.close()
    d.sh(f"am force-stop {SETTINGS}")


def agent(d, prompt, expect):
    d.log("== agent")
    settings_on_screen(d)
    tag = d.mark("agent")
    d.sh("input keycombination KEYCODE_META_LEFT KEYCODE_SPACE")
    shown = d.wait_log(POINTER_RE, 20, since=tag)
    if not shown:
        d.result("agent: the note opened", False, "not shown in 20 s")
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
        tapped = d.tap_text("Connect ", prefix=True)
        d.result("agent: the person connects it in the note", bool(tapped), tapped or "no Connect button")
        if not tapped:
            return
        time.sleep(1.5)
    else:
        d.result("agent: an agent is connected already", None, f"the note opened in {shown.group(2)}")
    d.sh("input text '" + prompt.replace(" ", "%s").replace("'", "") + "'")
    time.sleep(0.8)
    d.sh("input keyevent KEYCODE_ENTER")
    sent = d.wait_log(rf"note: task {task} prompt \((\d+) blocks\)", 8, since=tag)
    how = "typed, Enter"
    if not sent:
        d.note("SEND", text=prompt)
        how = "lab SEND (typing did not reach the field)"
        sent = d.wait_log(rf"note: task {task} prompt \((\d+) blocks\)", 8, since=tag)
    session = d.wait_log(rf"note: task {task} session (\S+) with (\S+)", 60, since=tag)
    d.result("agent: the prompt went to the agent in the Linux environment",
             bool(sent and session) and session.group(2).startswith("linux:"),
             how + (f"; session {session.group(1)} with {session.group(2)}" if session else "; no session"))
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
    d.sh(f"am force-stop {SETTINGS}")


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
