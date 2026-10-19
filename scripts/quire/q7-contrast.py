#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Contrast of the glass note's colour pairs on every OpenBook wallpaper, light and dark (ANAL-227).

usage: q7-contrast.py [--alpha A] [--device FILE] [--md]      exit 1 if any pair misses its target

The glass note (docs/quire-design.md §4) takes every colour from the system's roles, so this computes each wallpaper's
TonalSpot scheme the way scripts/brand/monet.py does (materialyoucolor, Material spec 2025; its seeds from
assets/wallpapers/monet.json) and scores the pairs the note draws, through the whole stack: a sheet of paper over the
glass over the backdrop, composited over black and over white, the lower ratio counting. Soft ink is derived, not fixed:
onSurface blended 85 % over the note's own colour. This is scripts/quire/q5-contrast.py's method with the glass tokens;
when the build takes the glass, q5-contrast.py's pairs and NOTE_ALPHA follow this file.
--alpha A tries another glass alpha (the one knob; §4.1). --device FILE takes the palette a running device reported
(q5-cf-check.py's "contrast" section) and checks the same pairs on those exact values.
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
         "onSecondaryContainer", "tertiary", "tertiaryContainer", "onTertiaryContainer", "error", "errorContainer",
         "onErrorContainer", "surface", "surfaceContainer", "surfaceContainerHigh", "surfaceContainerHighest",
         "surfaceContainerLowest", "onSurface", "onSurfaceVariant", "inverseSurface", "inverseOnSurface", "outlineVariant"]
GLASS_ALPHA = 0.80          # §4.1: the note's own colour over the blur
PAPER = {False: ("surfaceContainerLowest", 0.72), True: ("surfaceContainerHigh", 0.80)}     # §4.2 paper
FIELD = {False: ("surfaceContainerLowest", 0.80), True: ("surfaceContainerHighest", 0.85)}  # the field, change rows
SOFT_INK = 0.85             # §4.3: onSurface blended over the note's colour
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


def worst(fg, stack):
    """stack: [(colour, alpha), ...] top first. The lower ratio over black and over white."""
    out = None
    for bd in ((0, 0, 0), (1, 1, 1)):
        c = bd
        for col, a in reversed(stack):
            c = over(col, a, c)
        r = ratio(fg, c)
        out = r if out is None else min(out, r)
    return out


def pairs(roles, dark, alpha):
    """The glass note's pairs as the prototype draws them: (label, fg, stack, target)."""
    note = rgb(roles["surfaceContainer"] if dark else roles["surface"])
    glass = (note, alpha)
    paper = (rgb(roles[PAPER[dark][0]]), PAPER[dark][1])
    field = (rgb(roles[FIELD[dark][0]]), FIELD[dark][1])
    ink = rgb(roles["onSurface"])
    soft = over(ink, SOFT_INK, note)
    primary = rgb(roles["primary"])
    success, success_c, on_success_c = (rgb(x) for x in SUCCESS[dark])
    return [
        ("Ink on the glass (answer text, text buttons)", ink, [glass], 4.5),
        ("Soft ink on the glass (quiet line, pending steps)", soft, [glass], 4.5),
        ("Soft ink on paper", soft, [paper, glass], 4.5),
        ("Soft ink in the field", soft, [field, glass], 4.5),
        ("Ink on paper (undo pill)", ink, [paper, glass], 4.5),
        ("Filled button", rgb(roles["onPrimary"]), [(primary, 1)], 4.5),
        ("Tonal button, picker selection", rgb(roles["onSecondaryContainer"]), [(rgb(roles["secondaryContainer"]), 1)], 4.5),
        ("Stop pill, Delete", rgb(roles["onErrorContainer"]), [(rgb(roles["errorContainer"]), 1)], 4.5),
        ("New value pill", rgb(roles["onPrimaryContainer"]), [(rgb(roles["primaryContainer"]), 1)], 4.5),
        ("Automation chip", rgb(roles["onTertiaryContainer"]), [(rgb(roles["tertiaryContainer"]), 1)], 4.5),
        ("Jump pill, halo label, paused pill", rgb(roles["inverseOnSurface"]), [(rgb(roles["inverseSurface"]), 1)], 4.5),
        ("Plan's done number", on_success_c, [(success_c, 1)], 4.5),
        ("Done tick (non-text)", success, [glass], 3.0),
        ("Focus ring on the glass (non-text)", primary, [glass], 3.0),
        ("Focus ring on paper (non-text)", primary, [paper, glass], 3.0),
        ("Pending ring, soft ink (non-text)", soft, [glass], 3.0),
        ("Field outline on focus (non-text)", primary, [field, glass], 3.0),
        ("Running mark, the ink dot (non-text)", primary, [glass], 3.0),
    ]


def score(roles, dark, alpha):
    return [(label, worst(fg, stack), target) for label, fg, stack, target in pairs(roles, dark, alpha)]


def main():
    md = "--md" in sys.argv
    alpha = float(sys.argv[sys.argv.index("--alpha") + 1]) if "--alpha" in sys.argv else GLASS_ALPHA
    device = None
    if "--device" in sys.argv:
        device = json.loads(Path(sys.argv[sys.argv.index("--device") + 1]).read_text())
    monet = json.loads((R / "assets/wallpapers/monet.json").read_text())
    ok = True
    table = []
    for wp, v in monet.items():
        seed = int(v["seeds"][0].lstrip("#"), 16) | 0xFF000000
        for dark in (False, True):
            rows = score(scheme(seed, dark), dark, alpha)
            closest = min(rows, key=lambda x: x[1] / x[2])
            fails = [f"{l} {r:.1f}:1" for l, r, t in rows if r < t]
            ok &= not fails
            table.append((wp.replace(".jpg", ""), "dark" if dark else "light", closest, fails))
    if md:
        print(f"Glass alpha {alpha:.2f}; every pair at its worst backdrop (black and white behind the stack).\n")
        print("| Wallpaper | Theme | Closest pair to its target | Failing pairs |")
        print("|---|---|---|---|")
        for wp, th, (l, r, t), fails in table:
            print(f"| {wp} | {th} | {l}: {r:.2f}:1 (target {t:.1f}) | {', '.join(fails) or 'none'} |")
    else:
        print(f"glass alpha {alpha:.2f}")
        for wp, th, (l, r, t), fails in table:
            print(f"{wp:<26} {th:<5} closest: {l} {r:.2f}:1 (target {t}) fails: {fails or 'none'}")
    if device:
        print()
        for theme, roles in device.items():
            dark = theme == "dark"
            rows = score(roles, dark, alpha)
            fails = [f"{l} {r:.1f}:1" for l, r, t in rows if r < t]
            ok &= not fails
            closest = min(rows, key=lambda x: x[1] / x[2])
            print(f"device {theme}: {len(rows)} pairs, closest {closest[0]} {closest[1]:.2f}:1 (target {closest[2]}), "
                  f"fails: {fails or 'none'}")
    print("ALL PASS" if ok else "SOME FAIL", file=sys.stderr)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
