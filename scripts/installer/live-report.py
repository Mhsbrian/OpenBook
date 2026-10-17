#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarise one live-NNN/ folder that the live stick's "save logs" entry wrote (ANAL-190; openbook-live-init):
summary.json, collect-<phase>.txt ("===NAME===" sections), logcat-<phase>.txt, dmesg.txt, screen-<phase>.png.
Writes report.json (schema openbook-live-report/1: one verdict per area, true/false/null for unknown, with the
facts behind it) and report.md into the folder, and prints report.md. The device agent and the owner checklist
use the same file (docs/installer.md section 11).

  --expect g14   verdicts for the GA403WR: amdgpu HAL, eDP panel, Wi-Fi, touchpad, keyboard, dGPU in D3cold
  --expect vm    verdicts for QEMU: virtio-gpu HAL, a connected virtual display (no Wi-Fi, touchpad or dGPU)
  --redact DIR   also copy the folder to DIR with MAC addresses, USB serial numbers and Wi-Fi network names
                 masked, for committing as evidence

usage: live-report.py DIR [--expect g14|vm] [--redact OUT_DIR]
       live-report.py --redact-file FILE      print FILE with the same masking (serial logs for evidence)
"""
import argparse
import json
import os
import re
import shutil


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


MAC = re.compile(r"\b(?!00:00:00:00:00:00|ff:ff:ff:ff:ff:ff)([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")
# Kernel ("SerialNumber: "), lsusb, /dev/disk/by-id names, and Android's UsbHostManager
# ("mfg/product/ver/serial SanDisk/Ultra/1.00/<serial>").
SERIAL = re.compile(r"(SerialNumber: |iSerial\s+\d+\s+|usb-[A-Za-z0-9_]+_|mfg/product/ver/serial [^/\s]*/[^/\s]*/[^/\s]*/)"
                    r"([A-Za-z0-9]{6,})")
SSID = re.compile(r'(\b(?:SSID|ssid)\b[\s:=]*)("[^"]*"|[^\s,}"]+)')


def redact(text):
    text = MAC.sub("xx:xx:xx:xx:xx:xx", text)
    text = SERIAL.sub(lambda m: m.group(1) + "[redacted]", text)
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
    hal = props.get("vendor.anybook.gpu.hal")
    verdict("gpu_hal", hal == ("amdgpu" if a.expect == "g14" else "virtio"), hal=hal, egl=props.get("ro.hardware.egl"),
            vulkan=props.get("ro.hardware.vulkan"), gralloc=props.get("ro.hardware.gralloc"),
            hwcomposer=props.get("ro.hardware.hwcomposer"))
    # toybox df names /data by the last mount of its device, which can be /data_mirror/...
    m = re.search(r"^\S+\s+(\d+)\s+(\d+)\s+(\d+)\s+\d+% /data(?:_mirror/\S+)?$", sec.get("DF", ""), re.M)
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
        for f in sorted(os.listdir(d)):
            src, dst = f"{d}/{f}", f"{a.redact}/{f}"
            if f.endswith((".txt", ".json", ".md")):
                open(dst, "w").write(redact(open(src, errors="replace").read()))
            else:
                shutil.copy(src, dst)


if __name__ == "__main__":
    main()
