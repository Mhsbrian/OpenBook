#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Walk Quire setup (ANAL-393, docs/quire-setup.md §8) on a booted userdebug OpenBook device, normally Cuttlefish.

usage: setup-walk.py SERIAL OUTDIR [--image images.tar.gz] [--agent opencode] [--only SECTION,...]

The device starts with the Linux environment off and not installed, the way a person meets it. With --image, the
guest image goes to /sdcard/linux/images.tar.gz first (a debuggable build's source, docs/quire-setup.md §4.1); without
it, the device's own manifest decides (no URL: the wizard says the build has no image yet).

Sections, in order:
  welcome   The Quire app opens setup on its welcome page; every control has a label.
  linux     Get started: the Linux environment is turned on, installed with progress, started, and quired answers.
  agents    The catalog is listed; the agent is selected; What will run shows its commands; Install runs it.
  signin    The sign-in page, or its skip when the agent needs no account.
  try       A real first request to the default agent is answered.
  manage    Done opens the agents page; reopening the app opens it again; the note lists the agent as connected.
  dark      The agents page and the agents grid in the dark theme.
  keys      Esc closes a sheet, then the window.
  health    Crashes, ANRs and SELinux denials of Quire and the Terminal app.

Writes OUTDIR/results.tsv, OUTDIR/checks.log and a screenshot per page. Reuses q2-cf-check.py's device helpers.
"""
import argparse
import importlib.util
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("q2check", HERE / "q2-cf-check.py")
q2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(q2)

QUIRE = q2.QUIRE
SETUP = f"{QUIRE}/.setup.SetupActivity"
TERMINAL = "com.android.virtualization.terminal"
BRIDGE = "content://com.android.virtualization.terminal.agentbridge"


def nodes(xml):
    try:
        return list(ET.fromstring(xml).iter("node"))
    except ET.ParseError:
        return []


def find(d, text=None, desc=None, starts=None, timeout=10):
    """The topmost node whose text or content-desc matches (the last in drawing order, so a sheet's button wins over
    the one under its scrim), waiting up to timeout seconds."""
    end = time.time() + timeout
    while True:
        hit = None
        for n in nodes(d.ui()):
            t, c = n.get("text") or "", n.get("content-desc") or ""
            if ((text is not None and t == text) or (desc is not None and c == desc) or
                    (starts is not None and (c.startswith(starts) or t.startswith(starts)))):
                hit = n
        if hit is not None or time.time() > end:
            return hit
        time.sleep(1)


def tap(d, **kw):
    n = find(d, **kw)
    if n is not None:
        d.tap_node(n)
    return n is not None


def unlabeled(xml):
    """Clickable or focusable nodes of setup's window with neither text nor a description (docs/quire-design.md §8.3)."""
    out = []
    for n in nodes(xml):
        if n.get("package") != QUIRE:
            continue
        if n.get("clickable") == "true" and not (n.get("text") or n.get("content-desc")):
            out.append(n.get("class", "") + " " + n.get("bounds", ""))
    return out


def bridge(d):
    out = d.sh(f"content call --uri {BRIDGE} --method status 2>&1")
    m = re.search(r"state=(\w+)", out)
    return (m.group(1) if m else None), out.strip()


def open_setup(d):
    d.sh(f"am start -W -n {SETUP}")
    time.sleep(2)


def welcome(d):
    d.log("== welcome")
    # The person's starting point: Linux environment off, not installed, setup never finished.
    d.sh(f"pm disable-user {TERMINAL} >/dev/null 2>&1; pm clear {QUIRE} >/dev/null 2>&1")
    open_setup(d)
    d.screencap("01-welcome.png")
    xml = d.ui()
    d.write("01-welcome.xml", xml)
    d.result("setup opens on its welcome page", find(d, text="Bring your AI agents to OpenBook", timeout=5) is not None, "")
    d.result("Get started is there", find(d, desc="Get started", timeout=2) is not None
             or find(d, text="Get started", timeout=2) is not None, "")
    bad = unlabeled(xml)
    d.result("every control on the page has a label", not bad, "; ".join(bad[:5]))


def linux(d, image):
    d.log("== linux")
    d.sh("cmd wifi set-wifi-enabled enabled; sleep 3; cmd wifi connect-network VirtWifi open")
    for _ in range(20):
        if " 0% packet loss" in d.sh("ping -c1 -W2 8.8.8.8"):
            break
        time.sleep(1)
    if image:
        d.sh("mkdir -p /sdcard/linux")
        t0 = time.time()
        r = d.run("push", str(image), "/sdcard/linux/images.tar.gz", timeout=900)
        d.result("guest image at /sdcard/linux/images.tar.gz", r.returncode == 0, f"{time.time() - t0:.0f} s")
    tag = d.mark("linux")
    t0 = time.time()
    if not (tap(d, desc="Get started") or tap(d, text="Get started")):
        d.result("Get started tapped", False, "not found")
        return False
    seen, shot, state = set(), False, None
    for _ in range(1800):
        state, raw = bridge(d)
        ph = re.search(r"phase=(\w+)", raw)
        if ph:
            seen.add(ph.group(1))
            if not shot and ph.group(1) in ("download", "unpack", "verify"):
                time.sleep(1)
                d.screencap("02-linux-progress.png")
                shot = True
        if state in ("no_image",) or d.wait_log(r"setup: linux ready", 0.1, since=tag):
            break
        time.sleep(1)
    if state == "no_image":
        time.sleep(2)
        d.screencap("02-no-image.png")
        said = find(d, text="This build has no Linux environment yet", timeout=10) is not None
        d.result("no image in this build: the wizard says so, and nothing is downloaded from Google", said,
                 f"bridge no_image; {raw[-160:]}")
        return False
    m = d.wait_log(r"setup: linux ready, quired (\w+)", 60, since=tag)
    d.screencap("03-linux-ready.png")
    d.result("the Linux environment is set up from the wizard, quired answers",
             m is not None and m.group(1) == "answered",
             f"{time.time() - t0:.0f} s; bridge {state}; phases seen: {','.join(sorted(seen)) or 'none'}")
    d.result("the wizard showed install progress", shot, ",".join(sorted(seen)))
    return m is not None and m.group(1) == "answered"


def agents(d, agent):
    d.log("== agents")
    if not (tap(d, desc="Next") or tap(d, text="Next")):
        d.result("Next after Linux", False, "")
        return False
    time.sleep(2)
    d.screencap("04-agents.png")
    xml = d.ui()
    d.write("04-agents.xml", xml)
    m = d.wait_log(r"setup: catalog quired=(\S+) agents=(\d+) installed=(\S*)", 10)
    d.result("the catalog is listed", m is not None and int(m.group(2)) > 0, m.group(0) if m else "")
    card = find(d, starts=f"{agent_name(agent)},", timeout=5)
    d.result(f"{agent} has a card", card is not None, "")
    if card is None:
        return False
    already = m is not None and agent in m.group(3).split(",")
    if already:
        d.result(f"{agent} is already installed in this image", True, "skips install")
        return True
    d.tap_node(card)
    time.sleep(1)
    if tap(d, desc="What will run") or tap(d, text="What will run"):
        time.sleep(1)
        d.screencap("05-what-runs.png")
        xml = d.ui()
        d.write("05-what-runs.xml", xml)
        d.result("What will run lists the commands before Install", "curl" in xml or "npm" in xml, "")
    tag = d.mark("install")
    t0 = time.time()
    installed = tap(d, starts=f"Install {agent_name(agent)}")
    d.result("Install tapped", installed, "")
    time.sleep(3)
    d.screencap("06-installing.png")
    done = d.wait_log(rf"setup: _quire/install {agent} (done|failed): ?(.*)", 900, since=tag)
    d.screencap("07-installed.png")
    d.result(f"{agent} installed by its recipe", done is not None and done.group(1) == "done",
             f"{time.time() - t0:.0f} s; {done.group(0) if done else 'no result in 15 min'}")
    return done is not None and done.group(1) == "done"


def agent_name(agent):
    return {"opencode": "opencode", "claude": "Claude Code", "copilot": "GitHub Copilot"}.get(agent, agent)


def signin(d):
    d.log("== signin")
    tap(d, desc="Next") or tap(d, text="Next")
    time.sleep(2)
    # The page, not the header's step of the same name: its line under the title.
    if find(d, starts="Each agent signs in with its maker", timeout=3) is not None:
        d.screencap("08-signin.png")
        d.result("the sign-in page lists the agents", True, "")
        tap(d, desc="Later") or tap(d, text="Later") or tap(d, desc="Next") or tap(d, text="Next")
        time.sleep(2)
    else:
        ok = find(d, text="Say hello", timeout=5) is not None
        if ok:
            d.screencap("08-signin-skipped.png")
        d.result("an agent with no account skips sign-in", ok, "")


def try_it(d, agent):
    d.log("== try")
    tag = d.mark("hello")
    m = d.wait_log(rf"setup: hello from {agent} in (\d+) ms, stop=(\w+)|setup: hello from {agent} failed: (.*)", 240)
    time.sleep(2)
    d.screencap("09-try.png")
    xml = d.ui()
    d.write("09-try.xml", xml)
    ok = m is not None and m.group(1) is not None
    d.result(f"{agent} answered the first request", ok, m.group(0) if m else "no answer in 4 min")
    return ok


def manage(d, agent):
    d.log("== manage")
    tap(d, desc="Done") or tap(d, text="Done")
    time.sleep(2)
    d.screencap("10-manage.png")
    d.result("Done opens the agents page", find(d, text="Your agents", timeout=5) is not None, "")
    d.sh(f"am force-stop {QUIRE}")
    time.sleep(1)
    open_setup(d)
    d.result("the Quire app opens on the agents page after setup", find(d, text="Your agents", timeout=10) is not None, "")
    text = d.quire_log()
    d.result("the note lists the agent the wizard installed",
             f"linux:{agent}" in text and "found in the Linux environment" in text, "")


def dark(d):
    d.log("== dark")
    d.sh("cmd uimode night yes")
    time.sleep(2)
    d.sh(f"am force-stop {QUIRE}")
    open_setup(d)
    d.screencap("11-manage-dark.png")
    if tap(d, desc="Add agents") or tap(d, text="Add agents"):
        time.sleep(2)
        d.screencap("12-agents-dark.png")
    d.sh("cmd uimode night no")
    d.result("dark theme screens", True, "11-manage-dark.png, 12-agents-dark.png")


def keys(d):
    d.log("== keys")
    open_setup(d)
    d.sh("input keyevent KEYCODE_ESCAPE")
    time.sleep(1)
    top = d.sh("dumpsys activity activities | grep -m1 topResumedActivity")
    d.result("Esc closes the window", "SetupActivity" not in top, top.strip()[-120:])


def health(d):
    d.log("== health")
    crash = d.sh("logcat -d -b crash")
    d.result("no Quire or Terminal crash", QUIRE not in crash and TERMINAL not in crash, crash[-300:])
    anr = d.sh("logcat -d -b events | grep am_anr")
    d.result("no ANR", QUIRE not in anr and TERMINAL not in anr, anr[-200:])
    den = "\n".join(l for l in d.sh("logcat -d -b all").splitlines()
                    if "avc:  denied" in l and "adbd" not in l and re.search(r"quire|vmlauncher|virtualization", l)
                    # Known and harmless (AOSP), as in g14-quire-check.py: virtmgr inherits the Terminal installer's
                    # read descriptor of a debuggable build's /sdcard image, which AVF denies.
                    and "linux/images.tar.gz" not in l)
    d.write("denials.txt", den)
    d.result("no SELinux denial for Quire or the Terminal app", not den.strip(), den.strip()[:300])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("serial")
    ap.add_argument("out")
    ap.add_argument("--image")
    ap.add_argument("--agent", default="opencode")
    ap.add_argument("--only")
    a = ap.parse_args()
    d = q2.Dev(a.serial, Path(a.out))
    only = set(a.only.split(",")) if a.only else None
    want = lambda s: only is None or s in only
    # Cuttlefish's 256 KiB main buffer rotates Quire's lines out within minutes; the checks read them.
    d.sh("logcat -G 16M; logcat -c; logcat -b crash -c")
    # The wizard's breathing leaf and ink dots loop while they are on screen, and uiautomator dumps only an idle UI:
    # the walk runs with Remove animations on (every loop then stands still, docs/quire-design.md §5.3) and puts the
    # person's scales back at the end.
    scales = {k: d.sh(f"settings get global {k}").strip() for k in
              ("animator_duration_scale", "transition_animation_scale", "window_animation_scale")}
    for k in scales:
        d.sh(f"settings put global {k} 0")
    if want("welcome"):
        welcome(d)
    ok = True
    if want("linux"):
        ok = linux(d, a.image)
    if ok and want("agents"):
        ok = agents(d, a.agent)
    if ok and want("signin"):
        signin(d)
    if ok and want("try"):
        try_it(d, a.agent)
    if want("manage"):
        manage(d, a.agent)
    if want("dark"):
        dark(d)
    if want("keys"):
        keys(d)
    health(d)
    for k, v in scales.items():
        d.sh(f"settings delete global {k}" if v in ("", "null") else f"settings put global {k} {v}")
    d.sh("logcat -d > /data/local/tmp/setup-walk-logcat.txt")
    d.run("pull", "/data/local/tmp/setup-walk-logcat.txt", str(Path(a.out) / "logcat.txt"))


if __name__ == "__main__":
    main()
