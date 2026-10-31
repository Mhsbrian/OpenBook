#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Predict the dynamic colour (Monet) theme Android 17 derives from each wallpaper.

The steps follow AOSP 17:
  1. android.app.WallpaperColors.fromBitmap: scale to at most 112x112 pixels of area without filtering, quantize
     with CelebiQuantizer (Wu, then weighted k-means) to at most 128 colours, keep each colour's population.
  2. com.android.systemui.monet.ColorScheme.getSeedColors (frameworks/libs/systemui/monet): hue populations,
     the 15-degree hue window, the chroma >= 5 and > 1 % filter, score = 0.3/0.1 * (chroma - 48) + 70 * share,
     then seeds at least 90..15 degrees apart.
  3. ThemeOverlayController's default style, TONAL_SPOT, for light and dark.
Quantizer, HCT and schemes come from materialyoucolor (MIT), a port of Material Color Utilities. AOSP 17 asks for
spec 2026, which the port does not have; it uses spec 2025, so the role colours are a prediction. The device's own
values (dumpsys) are the ground truth: docs/googlebook-ui.md §4 compares the two.

usage: monet.py [--out FILE] IMAGE...   (prints JSON; --out also writes it)
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from materialyoucolor.dynamiccolor.material_dynamic_colors import MaterialDynamicColors
from materialyoucolor.hct import Hct
from materialyoucolor.quantize import QuantizeCelebi
from materialyoucolor.scheme.scheme_tonal_spot import SchemeTonalSpot

MAX_AREA = 112 * 112
MIN_CHROMA = 5
ACCENT1_CHROMA = 48
GOOGLE_BLUE = 0xFF1B6EF3
ROLES = ["primary", "onPrimary", "primaryContainer", "secondary", "secondaryContainer", "tertiary",
         "tertiaryContainer", "surface", "surfaceContainer", "onSurface", "outline"]
TONES = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99, 100]


def hexc(argb):
    return "#%06X" % (argb & 0xFFFFFF)


def wallpaper_colors(path):
    """{argb: population}, as WallpaperColors.fromBitmap computes it."""
    im = Image.open(path).convert("RGB")
    w, h = im.size
    if w * h > MAX_AREA:
        scale = math.sqrt(MAX_AREA / (w * h))
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        im = im.resize((nw, nh), Image.Resampling.NEAREST)  # Bitmap.createScaledBitmap(..., filter=false)
    w, h = im.size
    rgb = np.asarray(im, dtype=np.uint32).reshape(-1, 3)
    pixels = np.concatenate([rgb, np.full((len(rgb), 1), 255, np.uint32)], axis=1).tolist()
    n = max(5, min(128, (w * h) // 16))
    q = QuantizeCelebi(pixels, n)
    return {int(k) | 0xFF000000: int(v) for k, v in q.items()}


def seed_colors(pop, filt=True):
    total = float(sum(pop.values()))
    hct = {c: Hct.from_int(c) for c in pop}
    share = {c: v / total for c, v in pop.items()}
    hue_pop = [0.0] * 360
    for c, p in share.items():
        hh = hct[c]
        if filt and hh.chroma <= MIN_CHROMA:
            continue
        hue_pop[int(round(hh.hue)) % 360] += p
    hue_share = {}
    for c in pop:
        hue = int(round(hct[c].hue))
        hue_share[c] = sum(hue_pop[i % 360] for i in range(hue - 15, hue + 16))

    def score(c):
        ch = hct[c].chroma
        cs = 0.1 * (ch - ACCENT1_CHROMA) if ch < ACCENT1_CHROMA else 0.3 * (ch - ACCENT1_CHROMA)
        return cs + 0.7 * 100.0 * hue_share[c]

    cand = [c for c in pop if not filt or (hct[c].chroma >= MIN_CHROMA and hue_share[c] > 0.01)]
    cand.sort(key=score, reverse=True)
    seeds = []
    for dist in range(90, 14, -1):
        seeds = []
        for c in cand:
            if any(min(abs(hct[c].hue - hct[s].hue), 360 - abs(hct[c].hue - hct[s].hue)) < dist for s in seeds):
                continue
            seeds.append(c)
            if len(seeds) >= 4:
                break
        if seeds:
            break
    return seeds or [GOOGLE_BLUE], hct


def scheme(seed, dark):
    s = SchemeTonalSpot(Hct.from_int(seed), dark, 0.0, spec_version="2025")
    mdc = MaterialDynamicColors(spec="2025")
    roles = {}
    for r in ROLES:
        snake = "".join("_" + ch.lower() if ch.isupper() else ch for ch in r)
        dc = getattr(mdc, snake, None) or getattr(mdc, r, None)
        if dc is not None:
            roles[r] = hexc(dc.get_argb(s))
    palettes = {}
    for name, pal in (("accent1", s.primary_palette), ("accent2", s.secondary_palette),
                      ("accent3", s.tertiary_palette), ("neutral1", s.neutral_palette)):
        palettes[name] = {str(t): hexc(pal.tone(t)) for t in TONES}
    return roles, palettes


def analyse(path):
    pop = wallpaper_colors(path)
    seeds, hct = seed_colors(pop)
    seed = seeds[0]
    h = Hct.from_int(seed)
    out = {"seeds": [hexc(s) for s in seeds],
           "seed_hct": [round(h.hue, 1), round(h.chroma, 1), round(h.tone, 1)],
           "clusters": len(pop)}
    for name, dark in (("light", False), ("dark", True)):
        roles, pals = scheme(seed, dark)
        out[name] = roles
        if not dark:
            out["palettes"] = pals
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = {os.path.basename(p): analyse(p) for p in a.images}
    txt = json.dumps(res, indent=2, sort_keys=True) + "\n"
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w") as f:
            f.write(txt)
    sys.stdout.write(txt)


if __name__ == "__main__":
    main()
