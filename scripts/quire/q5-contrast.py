#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Contrast of the Quire note's colour pairs on every OpenBook wallpaper, light and dark (ANAL-219).

usage: q5-contrast.py [--device FILE] [--md]      exit 1 if any pair misses its target

docs/quire-design.md §8 asks the build to run Q3's contrast check against the device's palette for all eight
wallpapers. The note takes every colour from the system's roles (note/../ui/Palette.kt), so this computes each
wallpaper's TonalSpot scheme the way scripts/brand/monet.py does (materialyoucolor, Material spec 2025; its seeds
from assets/wallpapers/monet.json) and scores the pairs the note draws. A translucent background (the note, 92 %)
is composited over black and over white and the lower ratio counts, as in Q3's contrast-check.py.
--device FILE takes the palette a running device reported (q5-cf-check.py's "contrast" section writes it) and checks
the same pairs on those exact values, and how far the prediction for the current wallpaper is from them.
Run it with the brand venv's python (~/anybook/tools-local/brand-venv/bin/python, scripts/brand/requirements.txt).
"""
import json
import sys
from pathlib import Path

from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
from materialyoucolor.hct import Hct
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot

R = Path(__file__).resolve().parents[2]
ROLES = ["primary", "onPrimary", "primaryContainer", "onPrimaryContainer", "secondaryContainer",
         "onSecondaryContainer", "tertiary", "tertiaryContainer", "onTertiaryContainer", "error", "surface",
         "surfaceContainer", "surfaceContainerHigh", "surfaceContainerHighest", "surfaceContainerLowest", "onSurface",
         "onSurfaceVariant", "inverseSurface", "inverseOnSurface", "outlineVariant"]
NOTE_ALPHA = 0.92
SUCCESS = {False: ("#2F6B45", "#BDEBCB", "#0B3B20"), True: ("#9BD5A8", "#1E4A2F", "#BDEBCB")}


def scheme(seed, dark):
    s = SchemeTonalSpot(Hct.from_int(seed), dark, 0.0, spec_version="2025")
    mdc = MaterialDynamicColors(spec="2025")
    out = {}
    for r in ROLES:
        snake = "".join("_" + ch.lower() if ch.isupper() else ch for ch in r)
        dc = getattr(mdc, snake, None) or getattr(mdc, r, None)
        out[r] = "#%06X" % (dc.get_argb(s) & 0xFFFFFF)
    return out


def rgb(h):
    h = h.lstrip("#")[-6:]
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def lum(c):
    ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]


def ratio(a, b):
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def over(fg, a, bg):
    return tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3))


def pairs(roles, dark):
    """The note's pairs as Palette.kt and the views draw them: (label, fg, bg, bg alpha, target)."""
    note = roles["surfaceContainer"] if dark else roles["surface"]
    card = roles["surfaceContainerHigh"] if dark else roles["surfaceContainerLowest"]
    field = roles["surfaceContainerHighest"] if dark else roles["surfaceContainer"]
    success, success_c, on_success_c = SUCCESS[dark]
    return [
        ("Answer text on the note", roles["onSurface"], note, NOTE_ALPHA, 4.5),
        ("Secondary text on the note", roles["onSurfaceVariant"], note, NOTE_ALPHA, 4.5),
        ("Secondary text on a card", roles["onSurfaceVariant"], card, 1, 4.5),
        ("Secondary text on a change row or field", roles["onSurfaceVariant"], field, 1, 4.5),
        ("Filled button", roles["onPrimary"], roles["primary"], 1, 4.5),
        ("Tonal button, intake chip", roles["onSecondaryContainer"], roles["secondaryContainer"], 1, 4.5),
        ("Text button", roles["primary"], note, NOTE_ALPHA, 4.5),
        ("New value pill", roles["onPrimaryContainer"], roles["primaryContainer"], 1, 4.5),
        ("Automation chip", roles["onTertiaryContainer"], roles["tertiaryContainer"], 1, 4.5),
        ("Jump pill, code block, paused pill", roles["inverseOnSurface"], roles["inverseSurface"], 1, 4.5),
        ("Stop (danger text)", roles["error"], note, NOTE_ALPHA, 4.5),
        ("Plan's done number", on_success_c, success_c, 1, 4.5),
        ("Done check (non-text)", success, note, NOTE_ALPHA, 3.0),
        ("Focus ring (non-text)", roles["primary"], note, NOTE_ALPHA, 3.0),
        ("Pending-step ring (non-text)", roles["onSurfaceVariant"], note, NOTE_ALPHA, 3.0),
        ("Field outline on focus (non-text)", roles["primary"], field, 1, 3.0),
    ]


def score(roles, dark):
    rows = []
    for label, fg, bg, a, target in pairs(roles, dark):
        f, b = rgb(fg), rgb(bg)
        r = ratio(f, b) if a >= 1 else min(ratio(f, over(b, a, (0, 0, 0))), ratio(f, over(b, a, (1, 1, 1))))
        rows.append((label, r, target))
    return rows


def main():
    md = "--md" in sys.argv
    device = None
    if "--device" in sys.argv:
        device = json.loads(Path(sys.argv[sys.argv.index("--device") + 1]).read_text())
    monet = json.loads((R / "assets/wallpapers/monet.json").read_text())
    ok = True
    table = []
    for wp, v in monet.items():
        seed = int(v["seeds"][0].lstrip("#"), 16) | 0xFF000000
        for dark in (False, True):
            rows = score(scheme(seed, dark), dark)
            worst = min(rows, key=lambda x: x[1] / x[2])
            fails = [f"{l} {r:.1f}:1" for l, r, t in rows if r < t]
            ok &= not fails
            table.append((wp.replace(".jpg", ""), "dark" if dark else "light", worst, fails))
    if md:
        print("| Wallpaper | Theme | Closest pair to its target | Failing pairs |")
        print("|---|---|---|---|")
        for wp, th, (l, r, t), fails in table:
            print(f"| {wp} | {th} | {l}: {r:.2f}:1 (target {t:.1f}) | {', '.join(fails) or 'none'} |")
    else:
        for wp, th, (l, r, t), fails in table:
            print(f"{wp:<26} {th:<5} closest: {l} {r:.2f}:1 (target {t}) fails: {fails or 'none'}")
    if device:
        print()
        for theme, roles in device.items():
            dark = theme == "dark"
            rows = score(roles, dark)
            fails = [f"{l} {r:.1f}:1" for l, r, t in rows if r < t]
            ok &= not fails
            worst = min(rows, key=lambda x: x[1] / x[2])
            print(f"device {theme}: {len(rows)} pairs, closest {worst[0]} {worst[1]:.2f}:1 (target {worst[2]}), "
                  f"fails: {fails or 'none'}")
            # Which wallpaper's prediction the device's palette is, and how far off (largest channel difference).
            best = None
            for wp, v in monet.items():
                pred = scheme(int(v["seeds"][0].lstrip("#"), 16) | 0xFF000000, dark)
                diff = max(abs(a - b) * 255 for r in ROLES for a, b in zip(rgb(pred[r]), rgb(roles[r])))
                if best is None or diff < best[1]:
                    best = (wp, diff)
            print(f"device {theme}: closest prediction {best[0]}, largest channel difference {best[1]:.0f} of 255")
    print("ALL PASS" if ok else "SOME FAIL", file=sys.stderr)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
