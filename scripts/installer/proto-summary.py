#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Summarise a proto-matrix.sh run: for each variant, what the EFI loader handed the kernel (from the anybook-probe
lines and the console dump) and how far Android got. Writes <LOGDIR>/results.json and prints a Markdown table.

usage: proto-summary.py LOGDIR
"""
import json
import os
import re
import sys

ANSI = re.compile(rb"\x1b\[[0-9;?]*[a-zA-Z]")


def grab(pattern, text, group=1):
    m = re.search(pattern, text, re.M)
    return m.group(group) if m else None


def summarise(d):
    res = json.load(open(f"{d}/result.json")) if os.path.exists(f"{d}/result.json") else {}
    raw = open(f"{d}/serial.log", "rb").read() if os.path.exists(f"{d}/serial.log") else b""
    t = ANSI.sub(b"", raw).replace(b"\r", b"").decode("utf-8", "replace")
    bc = dict(re.findall(r'PROBE bootconfig\| (androidboot\.[\w.]+) = "?([^"\n]*)"?', t))
    cmdline = grab(r"PROBE cmdline\| (.*)", t) or ""
    out = {
        "variant": os.path.basename(d.rstrip("/")),
        "reason": res.get("reason"),
        "seconds": res.get("seconds"),
        "steps": f"{res.get('steps_done', 0)}/{res.get('steps', 0)}",
        "loader": ("GRUB" if "AnyBook GRUB:" in t else "GBL " + (grab(r"VCS info: (\S+)", t) or "")
                   if "Generic Bootloader (GBL)" in t else
                   "systemd-boot" if "loader/entries" in cmdline or "systemd-boot" in t else None),
        "kernel": grab(r"Linux version (\S+)", t),
        "probe_ran": "anybook-probe start" in t,
        "bootconfig_lines": len(re.findall(r"PROBE bootconfig\|", t)),
        "bootconfig_missing": bool(re.search(r"PROBE bootconfig: /proc/bootconfig missing", t)),
        "slot_suffix": bc.get("androidboot.slot_suffix"),
        "verifiedbootstate": bc.get("androidboot.verifiedbootstate"),
        "vbmeta_digest": bc.get("androidboot.vbmeta.digest"),
        "boot_part_uuid": bc.get("androidboot.boot_part_uuid") or grab(r"androidboot\.boot_part_uuid=(\S+)", cmdline),
        "loader_marker": bc.get("androidboot.anybook.loader") or ("gbl" if bc.get("androidboot.gbl.vcs") else None),
        "kernel_image": grab(r"BOOT_IMAGE=(\S+)", cmdline),
        "boot_device": grab(r"init: Boot device (\S+) found via partition UUID", t),
        "first_stage": "init first stage started" in t,
        "second_stage": "init second stage started" in t,
        "digest_error": "Failed to verify vbmeta digest" in t or "vbmeta digest mismatch" in t,
        "metadata_formatted": "/metadata ext4 is formattable. Format it" in t,
        "userdata_formatted": "/data f2fs is formattable. Format it" in t,
        "console_dump": "===ANYBOOK-END===\n" in t and "===ANYBOOK-BEGIN===" in t,
        "by_name": sorted(set(re.findall(r"(\w+) -> (/dev/block/\w+)", t))),
        "kernel_no_bootconfig": "'bootconfig' found on command line, but no bootconfig found" in t,
        "failure": None,
    }
    if not out["loader"] and out["loader_marker"]:
        out["loader"] = {"sdboot": "systemd-boot", "grub": "GRUB", "uki": "UKI"}.get(out["loader_marker"],
                                                                                   out["loader_marker"])
    for pat in (r"(Failed to read bootloader message from misc partition: \w+)",
                r"(Failed to create devices required for first stage mount)",
                r"(Kernel panic - not syncing: [^\n]*)",
                r"(Service \S+ has 'reboot_on_failure' option and failed)"):
        f = grab(pat, t)
        if f:
            out["failure"] = f
            break
    if os.path.exists(f"{d}/esp-entries-after.txt"):
        out["esp_entries_after"] = re.findall(r"anybook-\S+\s+conf", open(f"{d}/esp-entries-after.txt").read())
    return out


def main(logdir):
    rows = [summarise(os.path.join(logdir, n)) for n in sorted(os.listdir(logdir))
            if os.path.isdir(os.path.join(logdir, n)) and os.path.exists(os.path.join(logdir, n, "result.json"))]
    json.dump(rows, open(f"{logdir}/results.json", "w"), indent=1)
    yn = lambda v: "yes" if v else "no"
    print("| variant | loader | /proc/bootconfig | slot | AVB state | boot_part_uuid | boot device found | "
          "1st / 2nd stage | /data formatted | console dump | failure | run |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        bcs = ("missing" if r["bootconfig_missing"] else "**empty**" if r["probe_ran"] and not r["bootconfig_lines"]
               else f"{r['bootconfig_lines']} lines" if r["probe_ran"] else "-")
        dev = "USB (" + r["boot_device"].split("/")[1] + ")" if r["boot_device"] and "usb" in r["boot_device"] \
            else (r["boot_device"] or "-")
        print(f"| {r['variant']} | {r['loader'] or '-'} | {bcs} | {r['slot_suffix'] or '-'} | "
              f"{r['verifiedbootstate'] or '-'} | {(r['boot_part_uuid'] or '-')[:8]} | {dev} | "
              f"{yn(r['first_stage'])} / {yn(r['second_stage'])} | {yn(r['userdata_formatted'])} | "
              f"{yn(r['console_dump'])} | {r['failure'] or '-'} | {r['steps']} steps, {r['seconds']} s |")
    print()
    for r in rows:
        extra = []
        if r["kernel_no_bootconfig"]:
            extra.append("kernel: 'bootconfig' found on command line, but no bootconfig found")
        if r["digest_error"]:
            extra.append("libfs_avb reported a vbmeta digest mismatch")
        if r.get("esp_entries_after"):
            extra.append("ESP entries after boot: " + ", ".join(r["esp_entries_after"]))
        if r["by_name"]:
            extra.append("by-name: " + ", ".join(f"{a}->{b}" for a, b in r["by_name"]))
        if r["kernel_image"]:
            extra.append(f"BOOT_IMAGE={r['kernel_image']}")
        if extra:
            print(f"- **{r['variant']}**: " + "; ".join(extra))


if __name__ == "__main__":
    main(sys.argv[1])
