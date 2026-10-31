#!/usr/bin/env python3
"""Diff two desktop-capture.sh output dirs (reference image vs our build) and print a Markdown report.

usage: desktop-compare.py REF_DIR OURS_DIR [--flags-re REGEX] > compare.md
Compares: pm list features, system properties (identity/build props are skipped), aconfig flags whose name
matches --flags-re (default: desktop/freeform/taskbar/windowing), enabled overlays, and Settings.Global.
"""
import argparse
import re
from pathlib import Path

SKIP_PROP = re.compile(
    r"(fingerprint|build\.(date|id|uuid|display|description|version\.incremental|host|user|flavor|tags)|"
    r"\.serialno|boot\.(serialno|vbmeta|avb|bootreason|boottime|.*digest)|ro\.boottime|bootreceiver|"
    r"init\.svc_debug_pid|ro\.runtime\.firstboot|persist\.sys\.boot\.reason|sys\.boot\.reason|"
    r"vold\.|net\.|dhcp\.|gsm\.|ril\.|wifi\.|bluetooth\.|ro\.kernel\.|init\.svc\.|ro\.product\.(build|.*\.name|.*\.model|.*\.device|.*\.brand|.*\.manufacturer)|"
    r"apexd\.status|dev\.bootcomplete|sys\.sysctl|selinux|ro\.debuggable|ro\.adb|service\.adb|persist\.adb|"
    r"ro\.boot\.hardware\.revision|ro\.vendor\.build|ro\.system\.build|ro\.system_ext\.build|ro\.odm\.build|"
    r"ro\.vendor_dlkm|ro\.system_dlkm|ro\.odm_dlkm|ro\.product_dlkm|ro\.bootimage|cache_key)")
FLAG_RE_DEFAULT = r"desktop|freeform|taskbar|windowing|desk_|display_content_mode|force_freeform"
# Props that bear on desktop windowing, the UI shell or graphics; shown first, before the full table.
FOCUS_PROP = re.compile(
    r"(^persist\.wm|^ro\.wm|desktop|freeform|window|large_screen|characteristics|hwui|renderengine|^debug\.sf|"
    r"surface_flinger|egl|vulkan|gralloc|hwcomposer|opengles|angle|gltransport|navigation|nav_bar|taskbar|"
    r"launcher|systemui|lcd_density|sf\.lcd|density|native\.bridge|abilist|^ro\.config\.)")


def props(d):
    out = {}
    for line in (d / "getprop.txt").read_text(errors="replace").splitlines():
        m = re.match(r"\[(.+?)\]: \[(.*)\]$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def features(d):
    return {l.strip() for l in (d / "features.txt").read_text().splitlines() if l.startswith("feature:")}


def aflags(d, flag_re):
    out = {}
    p = d / "aflags.txt"
    if not p.exists():
        return out
    for line in p.read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) >= 2 and "." in parts[0] and re.search(flag_re, parts[0]):
            out[parts[0]] = parts[1]
    return out


def overlays(d):
    enabled, target = set(), None
    for line in (d / "overlays.txt").read_text(errors="replace").splitlines():
        if line and not line.startswith((" ", "[", "-")):
            target = line.strip()
            continue
        m = re.match(r"\s*\[x\]\s+(\S+)", line) or re.match(r"\s*---\s+(\S+)", line)
        if m:
            enabled.add(f"{target}: {m.group(1)}")
    return enabled


def kv(d, name):
    out = {}
    for line in (d / name).read_text(errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    return out


def table(title, ref, ours, keyfilter=None):
    keys = sorted(set(ref) | set(ours))
    if keyfilter:
        keys = [k for k in keys if keyfilter(k)]
    rows = [(k, ref.get(k, "—"), ours.get(k, "—")) for k in keys if ref.get(k) != ours.get(k)]
    print(f"\n## {title}: {len(rows)} differences\n")
    if rows:
        print("| key | reference | ours |\n|---|---|---|")
        for k, a, b in rows:
            print(f"| `{k}` | `{a[:80]}` | `{b[:80]}` |")


def setdiff(title, ref, ours):
    print(f"\n## {title}\n")
    print(f"- Only in reference ({len(ref - ours)}): " + (", ".join(f"`{x}`" for x in sorted(ref - ours)) or "none"))
    print(f"- Only in ours ({len(ours - ref)}): " + (", ".join(f"`{x}`" for x in sorted(ours - ref)) or "none"))
    print(f"- In both: {len(ref & ours)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref", type=Path)
    ap.add_argument("ours", type=Path)
    ap.add_argument("--flags-re", default=FLAG_RE_DEFAULT)
    a = ap.parse_args()
    pr, po = props(a.ref), props(a.ours)
    print(f"# Desktop comparison\n\n- Reference: `{pr.get('ro.build.fingerprint', '?')}`\n- Ours: `{po.get('ro.build.fingerprint', '?')}`")
    setdiff("pm list features", features(a.ref), features(a.ours))
    table("System properties: desktop, window, UI shell and graphics", pr, po,
          lambda k: not SKIP_PROP.search(k) and FOCUS_PROP.search(k))
    table("System properties: all (identity, network and per-boot props skipped)", pr, po,
          lambda k: not SKIP_PROP.search(k) and not k.startswith("dev.mnt."))
    table(f"aconfig flags matching /{a.flags_re}/ (aflags list)", aflags(a.ref, a.flags_re), aflags(a.ours, a.flags_re))
    setdiff("Enabled overlays (cmd overlay list)", overlays(a.ref), overlays(a.ours))
    table("Settings.Global", kv(a.ref, "settings-global.txt"), kv(a.ours, "settings-global.txt"))


if __name__ == "__main__":
    main()
