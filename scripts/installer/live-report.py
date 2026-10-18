#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarise one live-NNN/ folder that the live stick's "save logs" entry wrote (ANAL-190; openbook-live-init):
summary.json, collect-<phase>.txt ("===NAME===" sections), logcat-<phase>.txt, dmesg.txt, screen-<phase>.png.
Writes report.json (schema openbook-live-report/1: one verdict per area, true/false/null for unknown, with the
facts behind it) and report.md into the folder, and prints report.md. The device agent and the owner checklist
use the same file (docs/installer.md section 11).

  --expect g14   verdicts for the GA403WR: amdgpu HAL, eDP panel, Wi-Fi, touchpad, keyboard, dGPU in D3cold
  --expect vm    verdicts for QEMU: virtio-gpu HAL, a connected virtual display (no Wi-Fi, touchpad or dGPU)
Either way, refresh_rate (ANAL-212): the display runs its fastest mode, and DisplayManager lets SurfaceFlinger draw
that fast.
Either way, hwtest-final.txt (openbook-hwtest, ANAL-179: its "HWTEST {json}" lines) adds the Wi-Fi, Bluetooth and
audio verdicts: regulatory database, scan, connection, DHCP, internet, iperf3, Bluetooth on and paired, the
built-in sound card, the speaker-to-microphone loopback directly on ALSA and through Android (and whether the HAL
kept that clean), and the audio routes (jacks, Bluetooth audio). Since ANAL-200 it
also adds the arm64 native bridge's: its configuration, an arm64 binary running, the ID registers, FRECPE/FRSQRTE
against golden values, and CRC32/NEON. A graphics check boot (ANAL-177, addon-gfx-out.tar) adds one verdict per part
(gfx_vk, gfx_vk14, gfx_gles_angle, gfx_gles_mesa, gfx_egl, gfx_angle_end2end: it ran, passed cases, and had no crash,
time-out or amdgpu fault), from scripts/graphics/gfx-report.py, which also writes addon-gfx/gfx-report.md; and
gfx_blur (ANAL-203: blur applied, no GPU hang, frame cost within scripts/ui/blur-report.py's limits).
  --redact DIR   also copy the folder to DIR with MAC addresses, USB serial numbers and Wi-Fi network names
                 masked, for committing as evidence

usage: live-report.py DIR [--expect g14|vm] [--redact OUT_DIR]
       live-report.py --redact-file FILE      print FILE with the same masking (serial logs for evidence)
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys


def sections(path):
    out, cur = {}, None
    if not os.path.exists(path):
        return out
    for line in open(path, errors="replace"):
        m = re.fullmatch(r"===([A-Z]+)===\n?", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur:
            out[cur].append(line.rstrip("\n"))
    return {k: "\n".join(v).strip() for k, v in out.items()}


def device_blocks(text):
    """dumpsys input's "Input Reader State" devices: {name: block}, from lines like "    5: Asus Keyboard (aka ...)"."""
    out, name, cur = {}, None, []
    for line in text.splitlines():
        m = re.match(r"^\s{4}\d+: (.+?)(?: \(aka .*\))?$", line)
        if m:
            if name:
                out.setdefault(name, "\n".join(cur))
            name, cur = m.group(1), []
        elif name:
            cur.append(line)
    if name:
        out.setdefault(name, "\n".join(cur))
    return out


def read(path):
    try:
        return open(path, errors="replace").read()
    except OSError:
        return ""


def touchpad_clock(text):
    """getevent -lt of the touchpad: does MSC_TIMESTAMP keep pace with the event clock? The gestures library rebuilds
    its time base from it, and "Clock changed backwards" means that base jumped back (ANAL-178). The cause on the G14:
    the kernel's autorepeat of BTN_TOOL_FINGER (the touchpad has EV_REP), in frames without MSC_TIMESTAMP; Android
    turns kernel repeat off for touchpads with aosp/patches/frameworks/native."""
    frames, msc = [], None
    for m in re.finditer(r"\[\s*([\d.]+)\]\s+(?:\S+: )?(EV_\w+)\s+(\S+)\s+([0-9a-f]+)", text):
        t, typ, code, val = float(m.group(1)), m.group(2), m.group(3), int(m.group(4), 16)
        if typ == "EV_MSC" and code == "MSC_TIMESTAMP":
            msc = val
        elif typ == "EV_SYN" and code == "SYN_REPORT":
            frames.append((t, msc))
            msc = None
    if len(frames) < 10:
        return None
    with_msc = [(t, m) for t, m in frames if m is not None]
    back = [(b[0] - a[0]) for a, b in zip(with_msc, with_msc[1:]) if b[1] < a[1]]
    ratios = sorted((b[1] - a[1]) / 1e6 / (b[0] - a[0]) for a, b in zip(with_msc, with_msc[1:])
                    if b[1] >= a[1] and b[0] > a[0] and b[0] - a[0] < 0.5)
    med = ratios[len(ratios) // 2] if ratios else None
    gaps = sorted(b[0] - a[0] for a, b in zip(frames, frames[1:]))
    repeats = len(re.findall(r"EV_KEY\s+BTN_TOOL_\w+\s+REPEAT", text))
    return {"ok": not [g for g in back if g < 1.0] and len(with_msc) == len(frames) and med is not None
            and 0.9 < med < 1.1 and not repeats, "frames": len(frames), "frames_with_msc": len(with_msc),
            "repeat_frames": repeats,
            "msc_backward_steps": len(back), "msc_backward_within_1s": len([g for g in back if g < 1.0]),
            "median_msc_per_event_second": round(med, 3) if med else None,
            "median_frame_interval_ms": round(gaps[len(gaps) // 2] * 1000, 2) if gaps else None}


def refresh_rate(text):
    """dumpsys SurfaceFlinger's pacesetter block (ANAL-212): is the panel scanned out at its fastest mode, and may
    SurfaceFlinger draw that fast? DisplayManager's primary render range was [0, 60] with AOSP's
    config_defaultRefreshRate (the G14's 120 Hz panel drew at 60). Returns (ok, facts); ok is None without a dump."""
    act = re.search(r"activeMode=\{[^}]*resolution=(\S+), vsyncRate=([\d.]+) Hz", text)
    pol = re.search(r"primaryRanges=\{physical=\[\S+ Hz, (\S+) Hz\], render=\[\S+ Hz, (\S+) Hz\]\}", text)
    # The fastest mode at the active resolution (a VM's display lists other sizes at other rates too).
    modes = [float(x) for x in re.findall(r"^\s+\{id=\d+, hwcId=\d+, resolution=%s, vsyncRate=([\d.]+) Hz"
                                          % re.escape(act.group(1)), text, re.M)] if act else []
    if not (modes and act and pol):
        return None, {"note": "no SurfaceFlinger pacesetter dump"}
    top, active, render_max = max(modes), float(act.group(2)), float(pol.group(2))

    def secs(t):  # "0d00:01:16.029"
        m = re.fullmatch(r"(\d+)d(\d+):(\d+):([\d.]+)", t)
        return round(int(m[1]) * 86400 + int(m[2]) * 3600 + int(m[3]) * 60 + float(m[4]), 1) if m else None
    rr = re.search(r"renderRate=([\d.]+) Hz", text)
    cap = lambda x: "none" if x > 1e6 else x  # inf, or FLT_MAX before DisplayManager sent its policy
    return (abs(active - top) < 0.5 and render_max >= top - 0.5), {
        "resolution": act.group(1), "active_hz": active, "fastest_mode_hz": top,
        "primary_render_max_hz": cap(render_max),
        "primary_physical_max_hz": cap(float(pol.group(1))), "render_hz_now": float(rr.group(1)) if rr else None,
        "seconds_by_render_hz": {k: secs(t) for k, t in re.findall(r"^([\d.]+) Hz: (\S+)$", text, re.M)}}


MAC = re.compile(r"\b(?!00:00:00:00:00:00|ff:ff:ff:ff:ff:ff)([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")
# Kernel ("SerialNumber: "), lsusb, /dev/disk/by-id names, and Android's UsbHostManager
# ("mfg/product/ver/serial SanDisk/Ultra/1.00/<serial>").
SERIAL = re.compile(r"(SerialNumber: |iSerial\s+\d+\s+|usb-[A-Za-z0-9_]+_|mfg/product/ver/serial [^/\s]*/[^/\s]*/[^/\s]*/)"
                    r"([A-Za-z0-9]{6,})")
SSID = re.compile(r'(\b(?:SSID|ssid)\b[\s:=]*)("[^"]*"|[^\s,}"]+)')
# Wireless debugging's six-digit pairing code, which AdbDebuggingManager logs while the pairing dialog is open
# (ANAL-222: the installed G14's logcat).
PAIRCODE = re.compile(r"(updateUIPairCode: |[Pp]airing code[:= ]+)(\d{6})\b")


# Wi-Fi network names, learned from the logs themselves so every other spelling is masked too: the installed
# system's Wi-Fi logs also name networks bare, its own and the neighbours' it scanned ("summary=NAME",
# WifiPickerTracker's "[StandardWifiEntry][NAME]", WifiNetworkSelector's "NAME:<bssid>(5GHz)"; ANAL-222).
SSID_NAME = re.compile(r'\b(?:SSID|ssid)\b[\s:=]*"([^"]{2,32})"|Wifi is connected to "([^"]{2,32})"|'
                       r"\[\w*WifiEntry\]\[([^\]\n]{2,32})\]|(?:: | / )([^/:\n]{2,32}):[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\(")


def ssid_names(text):
    return {n for m in SSID_NAME.finditer(text) for n in m.groups() if n and n not in ("<unknown ssid>", "[redacted]")}


def redact(text, names=()):
    names = set(names) | ssid_names(text)
    text = MAC.sub("xx:xx:xx:xx:xx:xx", text)
    text = SERIAL.sub(lambda m: m.group(1) + "[redacted]", text)
    text = PAIRCODE.sub(lambda m: m.group(1) + "[redacted]", text)
    for n in sorted(names, key=len, reverse=True):
        text = re.sub(r"(?<![\w-])" + re.escape(n) + r"(?![\w-])", "[redacted]", text)
    return SSID.sub(lambda m: m.group(1) + ('"[redacted]"' if m.group(2).startswith('"') else "[redacted]"), text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--redact-file")
    ap.add_argument("--expect", choices=("g14", "vm"), default="g14")
    ap.add_argument("--redact")
    a = ap.parse_args()
    if a.redact_file:
        print(redact(open(a.redact_file, "rb").read().decode("utf-8", "replace")), end="")
        return
    if not a.dir:
        ap.error("DIR is required")
    d = a.dir
    try:
        s = json.load(open(f"{d}/summary.json"))
    except (OSError, ValueError):
        s = {}  # missing, or cut short (power lost while writing): the collect files still tell most of it
    props = s.get("props", {})
    phase = "final" if os.path.exists(f"{d}/collect-final.txt") else "early"
    sec = sections(f"{d}/collect-{phase}.txt")
    allprops = dict(re.findall(r"^\[([^\]]+)\]: \[(.*)\]$", sec.get("PROPS", ""), re.M))
    props = {**allprops, **{k: v for k, v in props.items() if v}}
    v = {}

    def verdict(name, ok, **facts):
        v[name] = {"ok": ok, **facts}

    verdict("boot_completed", s.get("boot_completed"), seconds=s.get("boot_completed_s"),
            second_stage_s=s.get("second_stage_s"))
    conns = [l.split() for l in sec.get("DRM", "").splitlines() if l.strip()]
    connected = [c for c in conns if len(c) > 1 and c[1] == "connected"]
    sf = props.get("init.svc.surfaceflinger")
    want_conn = "eDP" if a.expect == "g14" else ""
    verdict("display", bool(connected and any(want_conn in c[0] for c in connected) and sf == "running"),
            connectors=[" ".join(c) for c in conns], surfaceflinger=sf,
            screenshot=os.path.exists(f"{d}/screen-{phase}.png") and os.path.getsize(f"{d}/screen-{phase}.png") > 0)
    rr_ok, rr_facts = refresh_rate(sec.get("SF", ""))
    verdict("refresh_rate", rr_ok, **rr_facts)
    hal = props.get("vendor.anybook.gpu.hal")
    verdict("gpu_hal", hal == ("amdgpu" if a.expect == "g14" else "virtio"), hal=hal, egl=props.get("ro.hardware.egl"),
            vulkan=props.get("ro.hardware.vulkan"), gralloc=props.get("ro.hardware.gralloc"),
            hwcomposer=props.get("ro.hardware.hwcomposer"))
    # df -k /data /metadata ...: toybox prints its arguments in order but names each by the last mount of its
    # device (/data_mirror/..., /data/user/0, /mnt/pass_through/0/emulated), so /data is the first line.
    m = re.search(r"^Filesystem .*\n\S+\s+(\d+)\s+(\d+)\s+\d+\s+\d+%\s+(\S+)\s*$", sec.get("DF", ""), re.M)
    m = m if m and m.group(3) not in ("/metadata", "/", "/system", "/vendor") else None
    verdict("data_on_stick", bool(m) and "f2fs" in sec.get("MOUNTS", ""),
            data_kib=int(m.group(1)) if m else None, used_kib=int(m.group(2)) if m else None,
            byname_targets=sorted({os.path.basename(t).rstrip("0123456789")
                                   for t in re.findall(r"-> (/dev/block/\S+)", sec.get("BYNAME", ""))}))
    if a.expect == "g14":
        net = sec.get("NET", "")
        verdict("wifi", "wlan0" in net if net else None, interface="wlan0" in net,
                status=sec.get("WIFI", "").splitlines()[:3], supplicant=props.get("init.svc.wpa_supplicant"))
        inp = sec.get("INPUTDEV", "")
        names = re.findall(r'^N: Name="(.*)"', inp, re.M)
        verdict("touchpad", any(re.search(r"ELAN|[Tt]ouchpad", n) for n in names) if inp else None,
                devices=[n for n in names if re.search(r"ELAN|[Tt]ouchpad", n)])
        verdict("keyboard", any(re.search(r"[Kk]eyboard|N-KEY|AT Translated", n) for n in names) if inp else None,
                devices=[n for n in names if re.search(r"[Kk]eyboard|N-KEY|AT Translated", n)])
        dg = [l.split() for l in sec.get("PCI", "").splitlines() if " 0x10de " in f" {l} "]
        verdict("dgpu_off", all("D3cold" in l for l in dg) if dg else True,
                functions=[" ".join(l) for l in dg] or "no NVIDIA function on the bus")
        bl = re.findall(r"^(\S+) (\d+)/(\d+)$", sec.get("BACKLIGHT", ""), re.M)
        verdict("backlight", bool(bl) if "BACKLIGHT" in sec else None, devices=[f"{n} {b}/{m}" for n, b, m in bl])
        sup = [l for l in sec.get("SUPPLY", "").splitlines() if re.match(r"^\S+: \S", l) and "No such" not in l]
        verdict("battery", any(" Battery" in l for l in sup) if "SUPPLY" in sec else None, supplies=sup)
        verdict("cpu_power", "active" in sec.get("POWER", "") if "POWER" in sec else None,
                facts=[l for l in sec.get("POWER", "").splitlines() if "No such" not in l])
        # Power and input (ANAL-178). Absent sections (older sticks) give null, not false.
        dev = device_blocks(sec.get("INPUT", ""))
        tp = next((b for n, b in dev.items() if "Touchpad" in n), None)
        verdict("touchpad_gestures", bool(re.search(r"Classes:.*\bTOUCHPAD\b", tp)) if tp else None,
                classes=(re.search(r"Classes: (.*)", tp) or [None, None])[1] if tp else None)
        kl = {n: (re.search(r"KeyLayoutFile: (.*)", b) or [None, ""])[1].strip() for n, b in dev.items()}
        want = {"Asus Keyboard": "Vendor_0b05_Product_19b6.kl", "Asus WMI hotkeys": "Asus_WMI_hotkeys.kl"}
        seen = {n: kl[n] for n in want if n in kl}
        verdict("key_layouts", all(seen[n].endswith(f) for n, f in want.items() if n in seen) if seen else None,
                layouts=seen)
        verdict("lid_switch", "Lid Switch" in names if inp else None,
                power_button="Power Button" in names if inp else None)
        ps = sec.get("POWERSTATE")
        # dumpsys window names the values; OpenBookPcFrameworkOverlay sets these (device/anybook/common/pc).
        cfg = dict(re.findall(r"\b(mLidKeyboardAccessibility|getLidBehavior|mShortPressOnPowerBehavior|"
                              r"mLongPressOnPowerBehavior)=(\S+)", ps or ""))
        want_cfg = {"mLidKeyboardAccessibility": "1", "getLidBehavior": "LID_BEHAVIOR_SLEEP",
                    "mShortPressOnPowerBehavior": "6",  # LOCK_OR_SLEEP: dumpsys prints this one as a number
                    "mLongPressOnPowerBehavior": "LONG_PRESS_POWER_GLOBAL_ACTIONS"}
        verdict("lid_and_power_config", all(cfg.get(k) == x for k, x in want_cfg.items()) if cfg else None,
                config=cfg, lid=(re.search(r"mLidState=(\S+)", ps or "") or [None, None])[1])
        su = dict(re.findall(r"^(\w+)=(.*)$", sec.get("SUSPEND", ""), re.M))
        n_ok, hw_sleep = int(su.get("success") or 0), int(su.get("total_hw_sleep") or 0)
        dm = read(f"{d}/dmesg.txt")
        verdict("s0i3", (hw_sleep > 0) if "SUSPEND" in sec and n_ok else None, suspends=n_ok, fails=su.get("fail"),
                total_hw_sleep_us=hw_sleep, last_hw_sleep_us=su.get("last_hw_sleep"),
                last_failed_dev=su.get("last_failed_dev") or None, not_deepest=dm.count("didn't reach deepest state"),
                resume_causes=sorted(set(re.findall(r"Resume caused by (IRQ \d+, \S+)", dm))))
        # The health HAL (vendor.health-openbook): Android's charge counter and health against the kernel's battery.
        bat = dict(re.findall(r"^BAT\d+ (\w+)=(\S+)$", sec.get("BAT", ""), re.M))
        bs = sec.get("BATTERY", "")
        cc = re.search(r"Charge counter: (-?\d+)", bs)
        health = re.search(r"^\s*health: (\d+)", bs, re.M)
        full, design = int(bat.get("charge_full") or 0), int(bat.get("charge_full_design") or 0)
        soh = round(100 * full / design, 1) if full and design else None
        want_h = None if soh is None else 2 if soh >= 80 else 8  # BatteryHealth GOOD / FAIR (health/battery.cpp)
        now = int(bat.get("charge_now") or 0)
        cc_ok = bool(cc and now and abs(int(cc.group(1)) - now) <= max(50000, now // 10))
        verdict("health_hal", (props.get("init.svc.vendor.health-openbook") == "running" and cc_ok
                               and (want_h is None or (health and int(health.group(1)) == want_h)))
                if "BAT" in sec and bat else None,
                service=props.get("init.svc.vendor.health-openbook"), charge_counter_uah=int(cc.group(1)) if cc else None,
                charge_now_uah=now or None, state_of_health_pct=soh, android_health=int(health.group(1)) if health else None,
                cycle_count=bat.get("cycle_count"), charge_limit_pct=bat.get("charge_control_end_threshold"))
        # Lid: PowerManager names the lid as a sleep or wake reason; this boot's logcat and the earlier boots' on the
        # stick (prior/, unpacked by read-stick-logs.sh). None: the lid was not used.
        logs = read(f"{d}/logcat-{phase}.txt") + "".join(read(f) for f in sorted(glob.glob(f"{d}/prior/misc/logd/logcat*")))
        # Android 17 logs the close as "Sleeping power group (... reason=lid_switch)"; older ones "Going to sleep due to".
        close_re = r"Going to sleep due to lid_switch|Sleeping power group \([^)]*reason=lid_switch"
        open_re = r"PowerManagerService: Waking up from \w+ \([^)]*reason=WAKE_REASON_LID"
        closes, opens = len(re.findall(close_re, logs)), len(re.findall(open_re, logs))
        c, o = re.search(close_re, logs), re.search(open_re, logs)
        suspended = "PM      : suspend entry" in logs[c.end():o.start()] if c and o and o.start() > c.end() else None
        verdict("lid_events", (closes > 0 and opens > 0) if closes or opens else None, sleeps_on_close=closes,
                wakes_on_open=opens, suspended_while_closed=suspended)
        # The power HAL (vendor.power-openbook) logs every EPP it sets: screen off -> power, app launch -> performance,
        # battery saver -> balance_power, otherwise the kernel's default (balance_performance).
        epp = re.findall(r"openbook\.power: energy_performance_preference=(\w+)", logs)
        tally = {x: epp.count(x) for x in sorted(set(epp))}
        screen_off = "screen_toggled: 0" in logs  # "power" is only due once the screen went off
        verdict("epp_modes", ("performance" in tally and ("power" in tally or not screen_off)) if epp else None,
                set_counts=tally, screen_went_off=screen_off, battery_saver_seen="balance_power" in tally)
        # The gestures library's complaint itself, in this boot's logcat (touchpad_clock below is the raw events).
        warn = read(f"{d}/logcat-{phase}.txt").count("Clock changed backwards")
        verdict("touchpad_clock_warnings", warn == 0 if any("Touchpad" in n for n in names) else None, count=warn)
        leds = sec.get("LEDS", "")
        verdict("kbd_backlight", "kbd_backlight" in leds if "LEDS" in sec else None,
                leds=[l for l in leds.splitlines() if "kbd" in l])
        verdict("epp", bool(sec.get("EPP", "").strip()) if "EPP" in sec else None,
                policies=sec.get("EPP", "").splitlines())
        tc = touchpad_clock(sec.get("TOUCHPADEV", ""))
        tc = tc or {"ok": None, "note": "no touchpad events captured"}
        verdict("touchpad_clock", tc["ok"], **{k: x for k, x in tc.items() if k != "ok"})
    hw = {}
    if os.path.exists(f"{d}/hwtest-final.txt"):
        for line in open(f"{d}/hwtest-final.txt", errors="replace"):
            if line.startswith("HWTEST {"):
                try:
                    o = json.loads(line[len("HWTEST "):])
                    hw[o.get("test")] = o
                except ValueError:
                    pass
    if hw:
        def hv(name, test, field="ok", keep=()):
            o = hw.get(test)
            verdict(name, None if o is None else bool(o.get(field)), **{k: o.get(k) for k in keep if o})
        hv("wifi_regulatory", "wifi-driver", "regdb_loaded", ("driver", "country"))
        hv("wifi_enabled", "wifi-enabled", keep=("supplicant",))
        hv("wifi_scan", "wifi-scan", keep=("networks", "ghz2", "ghz5", "ghz6"))
        hv("wifi_pno", "wifi-pno", keep=("driver_offers",))
        hv("wifi_connected", "wifi-connect", keep=("freq_mhz", "signal_dbm", "tx_mbit", "rx_mbit"))
        hv("wifi_dhcp", "wifi-dhcp", keep=("prefix", "gateway"))
        hv("wifi_gateway_ping", "wifi-ping-gateway", keep=("loss_pct", "avg_ms"))
        hv("wifi_internet", "wifi-validated")
        up, down = hw.get("wifi-iperf3-up"), hw.get("wifi-iperf3-down")
        verdict("wifi_iperf3", None if not (up or down) else bool(up and up.get("ok") and down and down.get("ok")),
                up_mbit_s=up and up.get("mbit_s"), down_mbit_s=down and down.get("mbit_s"),
                seconds=(up or down or {}).get("seconds"))
        hv("bt_enabled", "bt-enabled", keep=("hal",))
        hv("bt_paired", "bt-bonded", keep=("bonded",))
        hv("audio_card", "audio-card", keep=("card", "pcm"))
        loop = ("card", "tone_bin_dbfs", "noise_bin_dbfs", "glitched_slices", "slices", "playback_error", "capture_error",
                "error")
        hv("audio_loopback_alsa", "alsa-loopback", "heard", loop)
        hv("bridge_config", "bridge-config", keep=("native_bridge", "binfmt", "guest_libs", "abilist"))
        hv("bridge_exec", "bridge-exec", keep=("uname_machine", "hwcap", "error"))
        hv("bridge_id_registers", "bridge-id-registers", keep=("sigill", "first_sigill", "midr", "isar0", "pfr0"))
        hv("bridge_fp_estimates", "bridge-fp-estimates", keep=("cases", "bad", "first_bad"))
        hv("bridge_int_simd", "bridge-int-simd", keep=("crc32", "neon_fma"))
        hv("audio_loopback_android", "aaudio-loopback", "heard",
           ("tone_bin_dbfs", "noise_bin_dbfs", "glitched_slices", "slices", "xruns", "media_volume", "out_device",
            "in_device", "hal_input_pads", "hal_output_drops", "hal_skipped_transfers", "input_error", "output_error",
            "error"))
        # Clean through Android: heard, and the HAL neither padded the capture nor dropped or skipped buffers.
        aa = hw.get("aaudio-loopback")
        verdict("audio_android_clean", None if not aa or "hal_input_pads" not in aa else bool(
                    aa.get("heard") and not aa.get("hal_input_pads") and not aa.get("hal_output_drops")
                    and not aa.get("hal_skipped_transfers")),
                glitched_slices=aa and aa.get("glitched_slices"), hal_input_pads=aa and aa.get("hal_input_pads"))
        hv("audio_routes", "audio-routes", keep=("speaker_port", "mic_port", "headphone_jacks", "mic_jacks",
                                                 "wired_connected", "a2dp_connected", "pacing"))
    if os.path.exists(f"{d}/addon-gfx-out.tar") or os.path.isdir(f"{d}/addon-gfx"):
        # The graphics check (ANAL-177): gfx-report.py unpacks the results and compares them with Mesa CI's lists
        # when the Mesa tree is on this host.
        here = os.path.dirname(os.path.abspath(__file__))
        ci = os.path.join(os.environ.get("OPENBOOK_HOME", os.environ.get("ANYBOOK_HOME", os.path.expanduser(
            "~/anybook"))), "mesa", "src", "upstream", "src", "amd", "ci")
        cmd = [sys.executable, os.path.join(here, "..", "graphics", "gfx-report.py"), d]
        if os.path.isdir(ci):
            cmd += ["--mesa-ci", ci]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, check=False)
        try:
            g = json.load(open(f"{d}/addon-gfx/gfx-report.json"))
        except (OSError, ValueError):
            g = {"parts": {}}
        ad = s.get("addon") or {}
        verdict("gfx_run", (ad.get("rc") == 0) if ad else None, rc=ad.get("rc"), seconds=ad.get("seconds"),
                out_bytes=ad.get("out_bytes"))
        for part, name in (("vk", "gfx_vk"), ("vk14", "gfx_vk14"), ("gles-angle", "gfx_gles_angle"),
                           ("gles-mesa", "gfx_gles_mesa"), ("egl", "gfx_egl"), ("angle", "gfx_angle_end2end")):
            r = g["parts"].get(part)
            if not r or not r.get("ran"):
                verdict(name, None, note=(r or {}).get("skipped") or (r or {}).get("note") or "not in this run")
                continue
            c = r.get("counts", {})
            mc = r.get("mesa_ci") or {}
            verdict(name, c.get("Pass", 0) > 0 and not c.get("Crash") and not c.get("Timeout") and
                    not r.get("amdgpu_events"), renderer=r.get("renderer"), cases=r.get("total"),
                    counts=c, seconds=r.get("seconds"), amdgpu_events=r.get("amdgpu_events"),
                    not_in_mesa_ci=len(mc.get("our_failures_not_listed", [])) if mc else None)
        b = g["parts"].get("blur")
        if not b or not b.get("ran"):
            verdict("gfx_blur", None, note=(b or {}).get("skipped") or "not in this run")
        else:
            oks = [x["ok"] for x in b["verdicts"].values()]
            verdict("gfx_blur", False if False in oks else (None if None in oks else True),
                    **{k: x["ok"] for k, x in b["verdicts"].items()}, seconds=b.get("seconds"),
                    amdgpu_events=b.get("amdgpu_events"))
    mods = sec.get("MODULES", "").splitlines()
    avc = sec.get("AVC", "").split()
    report = {
        "schema": "openbook-live-report/1", "dir": os.path.basename(os.path.normpath(d)), "expect": a.expect,
        "phase": phase, "fingerprint": props.get("ro.build.fingerprint"), "model": props.get("ro.product.model"),
        "selinux": props.get("ro.boot.selinux") or "enforcing", "verdicts": v,
        "modules_loaded": len(mods), "amdgpu_loaded": any(l.startswith("amdgpu ") for l in mods),
        "avc_denials": {"dmesg": avc[0] if avc else None, "logcat": avc[1] if len(avc) > 1 else None},
        "live_init": s.get("live_init"), "files": sorted(os.listdir(d)),
    }
    json.dump(report, open(f"{d}/report.json", "w"), indent=1)
    lines = [f"# OpenBook live boot report: {report['dir']} ({a.expect})", "",
             f"Build: `{report['fingerprint']}`; SELinux {report['selinux']}; capture: {phase}; "
             f"{len(mods)} modules (amdgpu {'loaded' if report['amdgpu_loaded'] else 'NOT loaded'}).", "",
             "| Area | Verdict | Facts |", "|---|---|---|"]
    for k, x in v.items():
        mark = {True: "yes", False: "NO", None: "unknown"}[x["ok"]]
        facts = json.dumps({f: y for f, y in x.items() if f != "ok"})[:220].replace("|", "/")
        lines.append(f"| {k} | {mark} | {facts} |")
    open(f"{d}/report.md", "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if a.redact:
        os.makedirs(a.redact, exist_ok=True)
        names = set()
        for f in sorted(os.listdir(d)):
            if f.endswith((".txt", ".json", ".md")) and os.path.isfile(f"{d}/{f}"):
                names |= ssid_names(open(f"{d}/{f}", errors="replace").read())
        for f in sorted(os.listdir(d)):
            src, dst = f"{d}/{f}", f"{a.redact}/{f}"
            # Earlier boots' logs (prior-boots.tar.gz, unpacked into prior/ by read-stick-logs.sh) are not masked
            # as a whole: pick files from them with --redact-file.
            if os.path.isdir(src) or f.endswith(".tar.gz"):
                print(f"not copied to {a.redact}: {f} (use --redact-file on single files)", file=sys.stderr)
            elif f.endswith((".txt", ".json", ".md")):
                open(dst, "w").write(redact(open(src, errors="replace").read(), names))
            else:
                shutil.copy(src, dst)


if __name__ == "__main__":
    main()
