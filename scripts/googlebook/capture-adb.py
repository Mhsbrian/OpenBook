#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded, private diagnostics from an already paired Ruby live device.

No root, remount, settings changes, reboot, log clearing or disk writes on the
device. This does not pair or discover devices. Raw output is private and must
not be committed; command failures remain explicit in manifest.json. Also
inspect output for service-level denials that may accompany exit code zero.
"""
import argparse
import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time


def endpoint(value):
    try:
        host, port = value.rsplit(":", 1)
        ipaddress.IPv4Address(host)
        if not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ValueError()
    except ValueError:
        raise argparse.ArgumentTypeError("Use the paired device's explicit IPv4:connection-port")
    return value


def capture(out, name, argv, timeout=30):
    start = time.monotonic()
    with (out / f"{name}.txt").open("xb") as stdout, (out / f"{name}.stderr.txt").open("xb") as stderr:
        os.fchmod(stdout.fileno(), 0o600)
        os.fchmod(stderr.fileno(), 0o600)
        try:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=stdout,
                                    stderr=stderr, timeout=timeout, check=False)
            status, code = ("ok" if result.returncode == 0 else "failed"), result.returncode
        except subprocess.TimeoutExpired:
            status, code = "timeout", None
        except OSError as exc:
            stderr.write(str(exc).encode())
            status, code = "launch_failed", None
    return {"name": name, "status": status, "exit_code": code,
            "elapsed_s": round(time.monotonic() - start, 3),
            "files": [{"name": p.name, "bytes": p.stat().st_size,
                       "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                      for p in (out / f"{name}.txt", out / f"{name}.stderr.txt")]}


PROPERTIES = (
    "ro.build.fingerprint", "ro.vendor.build.fingerprint", "ro.product.model",
    "ro.build.type", "ro.debuggable", "ro.boot.serialno", "ro.boot.slot_suffix",
    "ro.boot.boot_part_uuid", "ro.boot.openbook.live", "ro.boot.openbook.ruby_logs",
    "ro.boot.verifiedbootstate", "ro.boot.veritymode", "sys.boot_completed",
    "init.svc.ruby-wifi-platform", "init.svc.audioserver", "init.svc.wifi_mainline_supplicant",
    "init.svc.vendor.openbook.zram", "init.svc.mmd_setup", "init.svc.mmd",
    "mmd.zram.enabled", "mmd.setup_complete",
    "init.svc.timberslide",
)


def commands():
    yield "identity", "id; getenforce; cat /proc/uptime /proc/sys/kernel/random/boot_id"
    yield "properties", "; ".join(f'echo "{p}=$(getprop {p})"' for p in PROPERTIES)
    # User builds deny some procfs reads. Keep independent operations separate
    # so a denied bootconfig/partitions read cannot suppress other evidence.
    for name, path in (("cmdline", "/proc/cmdline"), ("bootconfig", "/proc/bootconfig"),
                       ("mounts", "/proc/mounts"), ("partitions", "/proc/partitions"),
                       ("modules", "/proc/modules"), ("memory", "/proc/meminfo"),
                       ("swaps", "/proc/swaps"), ("io-pressure", "/proc/pressure/io")):
        yield name, "cat " + path
    yield "block-links", "ls -l /dev/block/by-name"
    yield "disk-space", "df -h"
    yield "logcat", "timeout 20 logcat -d -b all -v threadtime"
    yield "kernel-logcat", "timeout 20 logcat -d -b kernel -v threadtime"
    yield "dmesg", "timeout 10 dmesg"
    yield "alsa-cards", "cat /proc/asound/cards"
    yield "alsa-pcm", "cat /proc/asound/pcm"
    yield "sound-devices", "ls -l /dev/snd"
    yield "input", "timeout 15 dumpsys input"
    yield "input-capabilities", "timeout 10 getevent -lp"
    # Presence of the input device's EV_REP capability does not establish its
    # effective repeat delay or prove repeat frames occurred; capture motion too.
    yield "input-kernel-devices", "cat /proc/bus/input/devices"
    yield "current-user", "am get-current-user"
    # Preferences are per-user; a headless system user's values can disagree
    # with the signed-in desktop user. Read exact keys, never a settings dump.
    for user in ("current", "0"):
        for key in ("touchpad_tap_to_click", "touchpad_tap_dragging", "touchpad_natural_scrolling",
                    "touchpad_pointer_speed", "touchpad_right_click_zone"):
            yield f"{key}-{user}", f"settings --user {user} get system {key}"
    yield "wifi-status", "timeout 15 cmd wifi status"
    yield "overlays", "timeout 15 cmd overlay list --user 0"
    for name in ("config_wifiMainlineSupplicantEnabled", "config_wifi_connected_mac_randomization_supported",
                 "config_wifiDropConnectionWhenMacConfigurationFails"):
        yield name, f"timeout 15 cmd overlay lookup --user 0 com.google.android.wifi.resources com.google.android.wifi.resources:bool/{name}"
    for service in ("wifi", "connectivity", "audio", "media.audio_flinger", "media.audio_policy",
                    "SurfaceFlinger", "display", "window", "power", "thermalservice", "battery", "meminfo"):
        yield service, f"timeout 15 dumpsys {service}"
    yield "last-anr", "timeout 15 dumpsys activity lastanr"
    yield "system-server-crashes", "timeout 15 dumpsys dropbox --print system_server_crash"
    yield "system-server-watchdogs", "timeout 15 dumpsys dropbox --print system_server_watchdog"
    yield "processes", "ps -AZ"
    for index, service in enumerate((
            "desktop_data_migration",
            "com.android.desktop.drm_network.IDrmNetworkService/default",
            "desktop_net",
            "com.android.server.desktop.power.IDesktopSettingHealthService/default",
            "com.google.android.snapshot.ISnapshot/default",
            "com.android.desktop.video_chat.IVideoChatManager/default",
            "com.android.server.desktop.serviceability.IDesktopServiceabilityService/default")):
        # service check can return zero for 'not found'. Keep the text as
        # evidence; command success alone is not a registration pass.
        yield f"desktop-service-{index}", f"timeout 10 service check {service}"


def collect(adb, serial, server_port, out):
    base = [str(adb), "-P", str(server_port), "-s", endpoint(serial)]
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = {"schema": "openbook-ruby-adb-capture/1", "serial": serial,
              "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "complete": False, "connected": False, "commands": [],
              "scope": "Private user-build diagnostics; command completion is not hardware qualification"}

    def save():
        pending = out / "manifest.tmp"
        pending.write_text(json.dumps(report, indent=2) + "\n")
        pending.chmod(0o600)
        pending.replace(out / "manifest.json")

    state = capture(out, "adb-state", base + ["get-state"], timeout=15)
    report["commands"].append(state)
    report["connected"] = state["status"] == "ok" and (out / "adb-state.txt").read_text().strip() == "device"
    save()
    if not report["connected"]:
        return 2
    for name, command in commands():
        report["commands"].append(capture(out, name, base + ["shell", "set -e; " + command]))
        save()
    report["complete"] = True
    report["failed_sections"] = [r["name"] for r in report["commands"] if r["status"] != "ok"]
    save()
    return 1 if report["failed_sections"] else 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    data = Path(os.environ.get("OPENBOOK_HOME", str(Path.home() / "anybook")))
    p.add_argument("--adb", type=Path, default=data / "android-sdk/platform-tools/adb")
    p.add_argument("--serial", required=True, type=endpoint)
    p.add_argument("--server-port", type=int, default=5222)
    p.add_argument("--out", type=Path, required=True, help="New private directory; existing paths are refused")
    a = p.parse_args()
    if not 1 <= a.server_port <= 65535:
        p.error("Invalid local ADB server port")
    os.umask(0o077)
    code = collect(a.adb, a.serial, a.server_port, a.out)
    print(f"Capture exit {code}: {a.out / 'manifest.json'} (raw logs are private)")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
