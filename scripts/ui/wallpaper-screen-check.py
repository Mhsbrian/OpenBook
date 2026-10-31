#!/usr/bin/env python3
# Copyright (C) 2026 The AnyBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Was the wallpaper dimmed on a device's screen? (ANAL-205)

Compares a screenshot (e.g. the live stick's screen-final.png) with the wallpaper's source image, mapped the way
SurfaceFlinger draws it: the wallpaper layer's toDisplayTransform from `dumpsys SurfaceFlinger` (scale and offset;
on the G14 desktop `scale 1.1006, tx -145, ty -91`). A ratio near 1.00 means no dim; WallpaperService's AOSP
default dim (config_wallpaperDimAmount 0.05) gives 0.95.

It also prints the dark hints android.app.WallpaperColors would give the source image, under AOSP's thresholds
(70 / 5) and Googlebook's (55 / 12, persist.wallpapercolors.*): the default dim only applies to a wallpaper with
neither the dark-text nor the dark-theme hint, so a "no dim" result proves nothing for one that has a hint.
The hints follow WallpaperColors.calculateDarkHints() (scaled to an area of at most 112x112, relative luminance,
dark pixel = contrast with black at most 5.5); the bitmap scaling differs slightly, so values right at a
threshold are approximate.

usage: wallpaper-screen-check.py SOURCE [SCREENSHOT --scale K --offset TX,TY] [--skip X0,Y0,X1,Y1 ...]
  --skip  screen rectangles to leave out (status bar, taskbar, widgets, windows); default: top 100 px, bottom 110 px
"""
import argparse
import math
import statistics

from PIL import Image


def lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(p):
    return 0.2126 * lin(p[0]) + 0.7152 * lin(p[1]) + 0.0722 * lin(p[2])


def hints(src):
    w, h = src.size
    s = min(1.0, math.sqrt(112 * 112 / (w * h)))
    small = src.resize((max(1, round(w * s)), max(1, round(h * s))), Image.BILINEAR)
    lums = [luminance(p) for p in small.getdata()]
    mean = sum(lums) / len(lums)
    dark = sum(1 for v in lums if (v + 0.05) / 0.05 <= 5.5) / len(lums)
    print(f"source: mean luminance {mean:.3f}, dark pixels {100 * dark:.1f} %")
    for name, threshold, max_dark in (("AOSP 70 / 5", 0.70, 0.05), ("Googlebook 55 / 12", 0.55, 0.12)):
        h = [n for n, on in (("dark_text", mean > threshold and dark <= max_dark), ("dark_theme", mean < 0.3)) if on]
        print(f"  {name}: hints {h or 'none'} -> {'dimmed by default' if not h else 'never dimmed by default'}")


def compare(src, shot, k, tx, ty, skips):
    exp = src.transform(shot.size, Image.AFFINE, (1 / k, 0, -tx / k, 0, 1 / k, -ty / k), resample=Image.BICUBIC)
    sp, ep = shot.load(), exp.load()
    w, h = shot.size
    diffs, ratios = [], []
    for y in range(0, h, 8):
        for x in range(0, w, 8):
            if any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in skips):
                continue
            s, e = sum(sp[x, y][:3]), sum(ep[x, y][:3])
            diffs.append(abs(s - e) / 3)
            if e > 150:
                ratios.append(s / e)
    ratios.sort()
    print(f"screen vs source: {len(diffs)} samples, mean |difference| {statistics.mean(diffs):.2f} levels per channel")
    print(f"  brightness ratio screen/source: median {statistics.median(ratios):.4f}, "
          f"p10 {ratios[len(ratios) // 10]:.4f}, p90 {ratios[9 * len(ratios) // 10]:.4f} "
          f"(1.00: no dim; 0.95: AOSP's 5 % default dim)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source")
    ap.add_argument("screenshot", nargs="?")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--offset", default="0,0")
    ap.add_argument("--skip", action="append", default=[])
    a = ap.parse_args()
    src = Image.open(a.source).convert("RGB")
    hints(src)
    if a.screenshot:
        shot = Image.open(a.screenshot).convert("RGB")
        tx, ty = (float(v) for v in a.offset.split(","))
        w, h = shot.size
        skips = [tuple(int(v) for v in s.split(",")) for s in a.skip] or [(0, 0, w, 100), (0, h - 110, w, h)]
        compare(src, shot, a.scale, tx, ty, skips)


if __name__ == "__main__":
    main()
