#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Quire Q4 checks (ANAL-218) on a booted userdebug OpenBook device, normally Cuttlefish on the AMD lane.

usage: q4-cf-check.py SERIAL OUTDIR --image images.tar.gz [--only SECTION,...] [--prompt TEXT]

Sections, in order (docs/quire.md §4, acceptance in ANAL-218):
  facts     AVF is in the image: the virtualization feature, crosvm and virtmgr in the APEX, the hypervisor properties,
            /dev/kvm, KVM in the kernel log; the Terminal app installed and off by default; its agent bridge exported
            behind ACCESS_AGENT_BRIDGE, which Quire holds.
  off       With the Terminal app off, Quire says so and names the fallback (a paired computer, none paired).
  install   The person's steps: turn the Terminal app on, then Install from the image at /sdcard/linux/images.tar.gz
            (debuggable builds; scripts/quire/linux-env-image.sh). The VM then starts by itself.
  guest     Quire core reaches quired in the guest through the bridge and lists the agents installed there. Records the
            guest's boot time (its console) and how long from VM start until quired answered.
  terminal  `quired agents` typed into the Terminal app itself, with a screenshot.
  prompt    A prompt from Quire core to the first ready agent (opencode in the test image), answered over vsock.
            --approve none: the agent may not change anything.
  refuse    An app without ACCESS_AGENT_BRIDGE is refused; ports other than quired's are not offered; a stopped VM is
            reported as stopped, with the fallback.
  nokvm     For a device booted without KVM: /dev/kvm absent, and Quire says the Linux environment can't run and names
            the fallback instead of failing silently.
  health    Crash buffer, ANRs, SELinux denials (new ones listed).

Writes OUTDIR/results.tsv, OUTDIR/checks.log and the artifacts it names. Reuses q2-cf-check.py's device helpers.
"""
import argparse
import importlib.util
import re
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("q2check", HERE / "q2-cf-check.py")
q2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(q2)

TERMINAL = "com.android.virtualization.terminal"
BRIDGE = "content://com.android.virtualization.terminal.agentbridge"
PERMISSION = "com.android.virtualization.terminal.permission.ACCESS_AGENT_BRIDGE"
QUIRE = q2.QUIRE


def bridge_status(d):
    out = d.sh(f"content call --uri {BRIDGE} --method status 2>&1")
    m = re.search(r"state=(\w+)", out)
    return (m.group(1) if m else None), out.strip()


def quire_lines(d, since):
    text = d.quire_log()
    return text[text.rfind(since):] if since in text else ""


def facts(d):
    d.log("== facts")
    feats = d.sh("pm list features")
    d.result("feature android.software.virtualization_framework", "virtualization_framework" in feats, "")
    apex = d.sh("ls /apex/com.android.virt/bin /apex/com.android.virt/priv-app 2>&1")
    d.write("virt-apex.txt", apex)
    d.result("AVF in the APEX: crosvm, virtmgr, the Terminal app",
             all(x in apex for x in ("crosvm", "virtmgr", "VmTerminalApp")), " ".join(sorted(set(re.findall(r"crosvm|virtmgr|VmTerminalApp\w*", apex)))))
    props = d.sh("getprop | grep hypervisor")
    d.write("hypervisor-props.txt", props)
    d.result("ro.boot.hypervisor.vm.supported=1", "[ro.boot.hypervisor.vm.supported]: [1]" in props,
             " ".join(l.strip() for l in props.splitlines()))
    kvm = d.sh("ls -lZ /dev/kvm 2>&1").strip()
    d.result("/dev/kvm", kvm.startswith("c"), kvm)
    # The kernel's ring buffer has usually wrapped by now; kvm_amd's parameters show it initialised (built in).
    km = d.sh("echo svm_cpus=$(grep -c -w svm /proc/cpuinfo) nested=$(cat /sys/module/kvm_amd/parameters/nested) "
              "npt=$(cat /sys/module/kvm_amd/parameters/npt) misc=$(cat /sys/devices/virtual/misc/kvm/dev) 2>&1").strip()
    d.write("kernel-kvm.txt", km)
    d.result("KVM on AMD in the guest kernel (kvm_amd, nested)", "nested=1" in km and "misc=10:" in km, km)
    path = d.sh(f"pm path {TERMINAL}").strip()
    disabled = d.sh(f"pm list packages -d {TERMINAL}").strip()
    d.result("Terminal app installed, off by default", bool(path) and TERMINAL in disabled, f"{path}; disabled={TERMINAL in disabled}")
    pkg = d.sh(f"dumpsys package {TERMINAL}")
    d.write("terminal-package.txt", pkg)
    d.result("agent bridge provider exported with its permission",
             "AgentBridgeProvider" in pkg and PERMISSION in pkg, "")
    qp = d.sh(f"dumpsys package {QUIRE} | grep -E '{PERMISSION}'")
    d.result("Quire holds ACCESS_AGENT_BRIDGE", "granted=true" in qp, qp.strip())


def off(d):
    d.log("== off")
    d.sh(f"pm disable-user --user 0 {TERMINAL}")
    tag = d.mark("off")
    d.lab("AGENTS_LIST")
    m = d.wait_log(r"agents: unavailable: (.*)", 20, since=tag)
    lines = quire_lines(d, tag)
    d.write("off-quire.txt", lines)
    ok = m is not None and "Linux environment is off" in m.group(1) and "none is paired" in m.group(1)
    d.result("Terminal off: Quire says so and names the fallback", ok, m.group(1) if m else "no unavailable line")
    st = re.search(r"agents: status (.*)", lines)
    d.result("status line names each connector", st is not None and "linux-environment=TERMINAL_OFF" in st.group(1)
             and "paired-computer=NOT_PAIRED" in st.group(1), st.group(1) if st else "")


def install(d, image):
    d.log("== install")
    # Cuttlefish's Android has internet only over the VM's synthetic Wi-Fi (as in the microG checks); the guest's
    # comes from Android through AVF's tethering. A laptop has its Wi-Fi on.
    d.sh("cmd wifi set-wifi-enabled enabled; sleep 3; cmd wifi connect-network VirtWifi open")
    for _ in range(20):
        if " 0% packet loss" in d.sh("ping -c1 -W2 8.8.8.8"):
            break
        time.sleep(1)
    d.result("Android has internet (the VM's Wi-Fi)", " 0% packet loss" in d.sh("ping -c1 -W2 8.8.8.8"), "")
    d.sh(f"pm enable {TERMINAL}")
    for p in ("android.permission.ACCESS_LOCAL_NETWORK", "android.permission.POST_NOTIFICATIONS",
              "android.permission.RECORD_AUDIO"):
        d.sh(f"pm grant {TERMINAL} {p} 2>/dev/null")
    t0 = time.time()
    d.sh("mkdir -p /sdcard/linux")
    r = d.run("push", str(image), "/sdcard/linux/images.tar.gz", timeout=600)
    d.result("image pushed to /sdcard/linux/images.tar.gz", r.returncode == 0, f"{time.time() - t0:.0f} s; {r.stdout.strip()[-80:]}")
    tag = d.mark("not-installed")
    d.lab("AGENTS_STATUS")
    m = d.wait_log(r"agents: status (.*)", 15, since=tag)
    d.result("before install, Quire reports NOT_INSTALLED", m is not None and "NOT_INSTALLED" in m.group(1),
             m.group(1) if m else "")
    t_launch = time.time()
    d.sh(f"am start -n {TERMINAL}/.LauncherActivity")
    # On a debuggable build with a local image, the Terminal app may install it by itself; otherwise it shows
    # Install, which the person taps.
    node, auto = None, None
    for _ in range(120):
        node = d.find_node(d.ui(), text="Install")
        if node is not None:
            break
        state, _ = bridge_status(d)
        if state in ("starting", "running"):
            auto = state
            break
        time.sleep(1)
    d.screencap("terminal-install.png")
    d.result("Terminal installs the local image (Install tapped, or by itself)", node is not None or auto is not None,
             "tapped Install" if node is not None else f"installed by itself, state {auto}")
    if node is None and auto is None:
        return False
    if node is not None:
        d.tap_node(node)
    t1 = t_launch
    state, raw, started = None, "", None
    for _ in range(600):
        state, raw = bridge_status(d)
        if state == "starting" and started is None:
            started = time.time()
        if state in ("running", "error"):
            break
        time.sleep(1)
    d.vm_running_at = time.time()
    d.vm_started_at = started or t1
    d.result("Linux environment installed and running", state == "running",
             f"{raw}; install+start {time.time() - t1:.0f} s" + (f", VM start->running {time.time() - started:.0f} s" if started else ""))
    d.screencap("terminal-running.png")
    return state == "running"


def guest(d):
    d.log("== guest")
    t0 = time.time()
    agents, tag = None, None
    for attempt in range(60):
        tag = d.mark(f"list-{attempt}")
        d.lab("AGENTS_LIST")
        m = d.wait_log(r"agents: (agent \w+|unavailable|error list)", 30, since=tag)
        if m and m.group(1).startswith("agent"):
            agents = quire_lines(d, tag)
            break
        time.sleep(3)
    started = getattr(d, "vm_started_at", t0)
    d.write("guest-agents-quire.txt", agents or quire_lines(d, tag))
    listed = re.findall(r"agents: agent (\w+) version=\"([^\"]*)\" supported=(\w+)", agents or "")
    conn = re.search(r"agents: connected via (\S+) in (\d+) ms; (.*)", agents or "")
    d.result("Quire core reached quired in the guest", bool(listed),
             conn.group(0) if conn else ("an open connection, reused" if listed else "never connected"))
    d.result("quired lists an agent installed in the guest", any(s == "true" for _, _, s in listed),
             ", ".join(f"{a} {v} supported={s}" for a, v, s in listed))
    d.result("VM start -> quired answering (s)", None, f"{time.time() - started:.1f}")
    console = d.sh(f"cat /data/data/{TERMINAL}/files/*.log/*console* /data/data/{TERMINAL}/files/*.log/* 2>/dev/null | head -c 2000000")
    d.write("guest-console.log", console)
    boot = re.search(r"Startup finished in .*", console)
    kern = re.search(r"Linux version (\S+)", console)
    d.result("guest boot (systemd)", None, (boot.group(0) if boot else "no Startup line in the console") +
             (f"; kernel {kern.group(1)}" if kern else ""))
    d.agents = [a for a, _, s in listed if s == "true"]
    return bool(listed)


def webview(d):
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(d.ui())
    except ET.ParseError:
        return None
    for n in root.iter("node"):
        if n.get("class") == "android.webkit.WebView" and n.get("package") == TERMINAL:
            return n
    return None


def terminal(d):
    d.log("== terminal")
    d.sh(f"am start -n {TERMINAL}/.LauncherActivity")
    node = None
    for _ in range(30):
        node = webview(d)
        if node is not None:
            break
        time.sleep(2)
    d.result("the Terminal app shows its terminal", node is not None, node.get("bounds") if node is not None else "no WebView")
    if node is None:
        d.screencap("terminal-missing.png")
        return
    d.tap_node(node)  # focus the terminal
    time.sleep(8)  # the shell prompt
    d.sh("input text 'quired%sagents'")
    d.sh("input keyevent 66")
    time.sleep(4)
    d.sh("input text 'systemd-analyze;%ssystemctl%s--no-pager%sstatus%squired%s|%shead%s-4'")
    d.sh("input keyevent 66")
    time.sleep(4)
    shot = d.screencap("terminal-quired-agents.png")
    d.result("`quired agents` typed in the Terminal app (screenshot)", None, shot.name)


def prompt(d, text):
    d.log("== prompt")
    agent = (getattr(d, "agents", None) or ["opencode"])[0]
    tag = d.mark("describe")
    d.lab("AGENTS_DESCRIBE", agent=agent)
    m = d.wait_log(r"agents: auth (\w+) (.*)", 60, since=tag)
    d.result(f"{agent}'s sign-in methods reach Quire (ACP authMethods)", m is not None, m.group(2) if m else "")
    tag = d.mark("prompt")
    t0 = time.time()
    d.lab("AGENTS_PROMPT", agent=agent, text=text, approve="none")
    m = d.wait_log(r"agents: (answer \S+ stop=(\w+) ms=(\d+) text=(.*)|error prompt: .*)", 300, since=tag)
    lines = quire_lines(d, tag)
    d.write("prompt-quire.txt", lines)
    ok = m is not None and m.group(1).startswith("answer") and m.group(2) == "end_turn" and "QUIRE OK" in (m.group(4) or "")
    d.result(f"a prompt from Quire core is answered by {agent} in the guest", ok,
             (m.group(1) if m else "no answer") + f" ({time.time() - t0:.1f} s)")
    d.screencap("quire-answer.png")


def refuse(d):
    d.log("== refuse")
    # The shell's uid: a platform-signed privileged package without the privapp grant, so the permission (not the
    # caller's signature) must be what decides. Its dumpsys shows it isn't granted.
    shell_grant = d.sh("dumpsys package com.android.shell | grep -c 'ACCESS_AGENT_BRIDGE: granted=true'").strip()
    out = d.sh(f"su 2000 content call --uri {BRIDGE} --method status 2>&1 | head -2")
    d.write("refuse-shell-uid.txt", out)
    d.result("a caller without ACCESS_AGENT_BRIDGE is refused (shell, uid 2000)",
             shell_grant == "0" and "Permission Denial" in out and PERMISSION in out, out.strip().splitlines()[-1][:220])
    out = d.sh(f"content read --uri {BRIDGE}/vsock/4000 2>&1 | head -3")
    d.result("other guest ports are not offered (4000, the guest agent)", "not offered" in out or "FileNotFound" in out,
             out.strip()[:200])
    d.sh(f"am start-foreground-service -n {TERMINAL}/.new2.core.VmService -a ACTION_STOP_VM")
    for _ in range(60):
        state, raw = bridge_status(d)
        if state in ("stopped", "error"):
            break
        time.sleep(1)
    tag = d.mark("stopped")
    d.lab("AGENTS_DISCONNECT")
    time.sleep(1)
    d.lab("AGENTS_LIST")
    m = d.wait_log(r"agents: unavailable: (.*)", 30, since=tag)
    d.write("stopped-quire.txt", quire_lines(d, tag))
    d.result("VM stopped: Quire says so and names the fallback", m is not None and "isn’t running" in m.group(1)
             and "none is paired" in m.group(1), m.group(1) if m else f"bridge state {state}")


def nokvm(d, image):
    d.log("== nokvm")
    kvm = d.sh("ls -l /dev/kvm 2>&1").strip()
    d.result("no /dev/kvm on this boot", "No such file" in kvm, kvm)
    d.sh(f"pm enable {TERMINAL}")
    d.sh(f"pm grant {TERMINAL} android.permission.ACCESS_LOCAL_NETWORK")
    d.sh("mkdir -p /sdcard/linux")
    d.run("push", str(image), "/sdcard/linux/images.tar.gz", timeout=600)
    d.sh(f"am start -n {TERMINAL}/.LauncherActivity")
    for _ in range(40):
        node = d.find_node(d.ui(), text="Install")
        if node is not None:
            d.tap_node(node)
            break
        time.sleep(1)
    state, raw = None, ""
    for _ in range(300):
        state, raw = bridge_status(d)
        if state in ("running", "error", "stopped"):
            break
        time.sleep(1)
    d.result("the Linux environment cannot start without KVM", state != "running", raw)
    d.screencap("nokvm-terminal.png")
    tag = d.mark("nokvm")
    d.lab("AGENTS_LIST")
    m = d.wait_log(r"agents: unavailable: (.*)", 30, since=tag)
    d.write("nokvm-quire.txt", quire_lines(d, tag))
    d.result("no KVM: Quire says the Linux environment can't be used and names the fallback",
             m is not None and "none is paired" in m.group(1), m.group(1) if m else "no unavailable line")
    d.lab("AGENTS_STATUS")
    time.sleep(2)
    d.sh(f"am start -n {QUIRE}/.control.ControlActivity")
    time.sleep(3)
    d.screencap("nokvm-quire.png")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("serial")
    ap.add_argument("outdir")
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--only", default="facts,off,install,guest,terminal,prompt,refuse,health")
    ap.add_argument("--prompt", default="Reply with exactly: QUIRE OK")
    a = ap.parse_args()
    d = q2.Dev(a.serial, a.outdir)
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
    running = True
    for s in sections:
        if s == "facts":
            facts(d)
        elif s == "off":
            off(d)
        elif s == "install":
            running = install(d, a.image)
        elif s == "guest" and running:
            running = guest(d)
        elif s == "terminal" and running:
            terminal(d)
        elif s == "prompt" and running:
            prompt(d, a.prompt)
        elif s == "refuse":
            refuse(d)
        elif s == "nokvm":
            nokvm(d, a.image)
        elif s == "health":
            q2.health(d, sysui_pid)
    d.sh("logcat -d -v time -b all > /data/local/tmp/q4-logcat.txt")
    d.run("pull", "/data/local/tmp/q4-logcat.txt", str(d.o / "logcat-all.txt"), timeout=120)
    with open(d.o / "results.tsv", "w") as f:
        for c, r, detail in d.results:
            f.write(f"{c}\t{r}\t{detail}\n")
    fails = [c for c, r, _ in d.results if r == "FAIL"]
    passes = sum(1 for _, r, _ in d.results if r == "PASS")
    d.log(f"== {passes} pass, {len(fails)} fail" + (": " + "; ".join(fails) if fails else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
