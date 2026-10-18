#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""OpenBook's default wallpapers: four designs, each in a light and a dark variant, drawn procedurally from the
brand palette (assets/README.md). Output: assets/wallpapers/<W>x<H>/openbook-<design>-<variant>.jpg.

Scene coordinates are in picture heights: y runs 0 (top) to 1 (bottom) and x is centred, so a 16:10 picture spans
x = -0.8..0.8 and a 16:9 one x = -0.89..0.89. Every design keeps its focus near the centre, which is what the
wallpaper picker keeps when it crops for another aspect ratio. Shapes are curves y = f(x) with analytic
anti-aliasing, shadows and rims; colours are mixed in linear light and dithered to 8 bits.

usage: wallpapers.py [--out DIR] [--size WxH ...] [--only NAME ...] [--preview]
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brandlib import ASSETS, dither_to_u8, lin, mix, over, smoothstep  # noqa: E402

SIZES = [(2880, 1800), (1920, 1080)]


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = 1.0 / h  # one pixel in scene units
        xs = (np.arange(w, dtype=np.float32) + 0.5 - w / 2.0) / h
        ys = (np.arange(h, dtype=np.float32) + 0.5) / h
        self.x1, self.y1 = xs, ys
        self.X, self.Y = np.meshgrid(xs, ys)

    def edge(self, curve):
        """Signed distance (scene units) below the curve y = curve(x): > 0 under it, < 0 above it."""
        c = curve(self.x1).astype(np.float32)
        dc = np.gradient(c, self.x1)
        return (self.Y - c[None, :]) / np.sqrt(1.0 + dc * dc)[None, :]

    def cover(self, d, soft=1.0):
        """Anti-aliased coverage of d > 0, over about one pixel (soft widens it)."""
        k = self.px * soft
        return smoothstep(-k, k, d)


def vgrad(cv, top, bottom, ease=1.0):
    t = np.clip(cv.Y, 0, 1) ** ease
    return mix(lin(top), lin(bottom), t[..., None])


def radial(cv, cx, cy, r, inner, outer, power=1.0):
    d = np.sqrt((cv.X - cx) ** 2 + (cv.Y - cy) ** 2) / r
    t = np.clip(d, 0, 1) ** power
    return mix(lin(inner), lin(outer), t[..., None]), d


def glow(cv, cx, cy, sx, sy=None):
    sy = sy or sx
    return np.exp(-(((cv.X - cx) / sx) ** 2 + ((cv.Y - cy) / sy) ** 2))


# ---------------------------------------------------------------------------------------------------------------
# Folio: pages fanning out of a spine at the bottom centre, blue on the left and violet on the right, with warm
# light where they meet. The brand mark's two pages, at the scale of a desk.
# ---------------------------------------------------------------------------------------------------------------
def folio(cv, dark):
    if dark:
        img = vgrad(cv, "#0E0F17", "#191B36", 1.3)
        img = over(img, lin("#2A2F6E"), 0.55 * glow(cv, 0.0, 1.05, 0.95, 0.55))
        left = ["#171A45", "#1C2259", "#232B70", "#2C3689", "#3843A6", "#4752C2", "#5A66DD"]
        right = ["#211541", "#2A1958", "#341E70", "#40248A", "#4E2BA6", "#6034C2", "#753FDB"]
        rim, rim_a, shadow_a, tint = lin("#AEB8FF"), 0.38, 0.55, 0.10
    else:
        img = vgrad(cv, "#F7F6FF", "#E6E8FD", 1.2)
        img = over(img, lin("#FFFFFF"), 0.45 * glow(cv, 0.0, 0.18, 0.9, 0.35))
        left = ["#E4E7FF", "#D3D8FF", "#C0C7FF", "#ACB5FF", "#97A2FB", "#8390F2", "#6F7DE6"]
        right = ["#F1E6FF", "#E6D4FF", "#DABFFF", "#CDAAFD", "#BF95F8", "#AF80F0", "#9C6BE6"]
        rim, rim_a, shadow_a, tint = lin("#FFFFFF"), 0.55, 0.16, 0.30
    spine_y = 1.06
    n = len(left)
    # Back pages are taller and wider; front pages hug the spine.
    for side, cols, sgn in (("l", left, -1.0), ("r", right, 1.0)):
        for k in range(n):
            f = k / (n - 1)
            height = 0.98 - 0.70 * f
            width = 0.30 - 0.17 * f + (0.02 if side == "r" else 0.0)
            lift = 0.10 * (1 - f)

            def curve(x, height=height, width=width, lift=lift, sgn=sgn):
                t = np.maximum(sgn * x, 0.0)
                # rises steeply from the spine, then rolls over like a page under its own weight
                rise = 1.0 - np.exp(-t / width)
                roll = 1.0 + lift * np.tanh((t - 0.55) * 3.0)
                y = spine_y - height * rise * roll
                # on the other side of the spine the page drops away under the bottom edge
                return np.where(sgn * x >= 0, y, spine_y + 0.5 * (sgn * -x) / width)

            d = cv.edge(curve)
            mask = cv.cover(d)
            if sgn < 0:
                mask = mask * cv.cover(-cv.X + 0.0015, 1.5)
            else:
                mask = mask * cv.cover(cv.X + 0.0015, 1.5)
            # shadow cast on the page behind, just above this page's edge
            sh = np.exp(-np.maximum(-d, 0) / (0.035 + 0.02 * f)) * (d < 0)
            img = img * (1.0 - shadow_a * (0.55 + 0.45 * f) * sh[..., None])
            base = lin(cols[k])
            edge_col = mix(base, rim, tint)
            col = mix(edge_col, base, smoothstep(0.0, 0.22, d)[..., None])
            # pages catch the light that comes out of the spine
            col = col * (1.0 + (0.9 if dark else 0.25) * glow(cv, 0.0, 1.0, 0.55, 0.45))[..., None]
            img = over(img, col, mask)
            # a fine bright rim along the page's edge
            r = np.exp(-np.maximum(d, 0) / (2.2 * cv.px)) * mask
            img = over(img, rim, rim_a * (0.5 + 0.5 * f) * r)
    # light where the pages meet
    warm = glow(cv, 0.0, 1.02, 0.20, 0.16)
    img = over(img, lin("#FFB38A"), (0.70 if dark else 0.55) * warm)
    img = over(img, lin("#FF7A9C"), (0.35 if dark else 0.22) * glow(cv, 0.0, 0.98, 0.42, 0.26))
    return img


# ---------------------------------------------------------------------------------------------------------------
# Bloom: the spark's warm gradient as a slow bloom of light, with a few fine rings.
# ---------------------------------------------------------------------------------------------------------------
def bloom(cv, dark):
    cx, cy = 0.22, 0.40
    if dark:
        img = vgrad(cv, "#150F1A", "#1C1224", 1.0)
        layers = [("#3A1F4A", 0.95, 0.9), ("#7A2E5E", 0.62, 0.85), ("#D2577A", 0.40, 0.9),
                  ("#FF8A8A", 0.24, 0.9), ("#FFC09A", 0.12, 0.95)]
        ring_c, ring_a = lin("#FFD2C2"), 0.10
    else:
        img = vgrad(cv, "#FFF8F4", "#FCEFF3", 1.0)
        layers = [("#F7E3F1", 1.05, 0.9), ("#FBD0DC", 0.70, 0.9), ("#FFB2B9", 0.45, 0.85),
                  ("#FF9C9E", 0.27, 0.8), ("#FFC4A0", 0.13, 0.9)]
        ring_c, ring_a = lin("#FFFFFF"), 0.45
    for col, r, a in layers:
        img = over(img, lin(col), a * glow(cv, cx, cy, r, r * 0.92))
    # a cool counter-glow in the opposite corner keeps the frame from going flat
    img = over(img, lin("#7A4CE0" if dark else "#D9CCFF"), (0.30 if dark else 0.55) *
               glow(cv, -0.75, 1.05, 0.55, 0.45))
    d = np.sqrt((cv.X - cx) ** 2 + (cv.Y - cy) ** 2)
    for i, rr in enumerate((0.30, 0.47, 0.66, 0.88, 1.13)):
        band = np.exp(-((d - rr) / (1.2 * cv.px)) ** 2)
        fade = np.exp(-i * 0.35)
        img = over(img, ring_c, ring_a * fade * band)
    return img


# ---------------------------------------------------------------------------------------------------------------
# Strata: page edges seen from above, stacked in slow waves from violet to blue.
# ---------------------------------------------------------------------------------------------------------------
def strata(cv, dark):
    if dark:
        img = vgrad(cv, "#120F22", "#0D0E18", 1.0)
        cols = ["#1B1438", "#22174A", "#2B1B5D", "#352071", "#402686", "#3A2E93", "#303794", "#263485"]
        rim, rim_a, shadow_a, tint = lin("#B9A6FF"), 0.30, 0.55, 0.08
    else:
        img = vgrad(cv, "#F6F1FF", "#EEE9FF", 1.0)
        cols = ["#EDE4FF", "#E2D5FF", "#D5C5FE", "#C8B5FB", "#BAA6F6", "#A9A3F4", "#99A0F1", "#8C9BEC"]
        rim, rim_a, shadow_a, tint = lin("#FFFFFF"), 0.6, 0.14, 0.25
    n = len(cols)
    for k in range(n):
        f = k / (n - 1)
        base_y = 0.18 + 0.76 * f
        amp = 0.075 * (1.0 - 0.45 * f)
        ph = 0.9 * k

        def curve(x, base_y=base_y, amp=amp, ph=ph, f=f):
            return (base_y + amp * np.sin(2.3 * x + ph) + 0.45 * amp * np.sin(4.1 * x - 1.7 * ph)
                    - 0.09 * np.exp(-((x + 0.15 - 0.3 * f) / 0.35) ** 2))

        d = cv.edge(curve)
        mask = cv.cover(d)
        sh = np.exp(-np.maximum(-d, 0) / 0.05) * (d < 0)
        img = img * (1.0 - shadow_a * sh[..., None])
        base = lin(cols[k])
        col = mix(mix(base, rim, tint), base, smoothstep(0.0, 0.16, d)[..., None])
        img = over(img, col, mask)
        r = np.exp(-np.maximum(d, 0) / (2.0 * cv.px)) * mask
        img = over(img, rim, rim_a * r)
    img = over(img, lin("#6E5BFF" if dark else "#FFB38A"), (0.16 if dark else 0.22) * glow(cv, 0.55, 0.12, 0.45, 0.30))
    return img


# ---------------------------------------------------------------------------------------------------------------
# Tide: a teal and blue mesh of light with one glossy ribbon through it.
# ---------------------------------------------------------------------------------------------------------------
def tide(cv, dark):
    if dark:
        img = vgrad(cv, "#07141A", "#0B1626", 1.0)
        blobs = [("#0E4C5E", -0.55, 0.25, 0.65, 0.9), ("#123E7A", 0.60, 0.80, 0.70, 0.85),
                 ("#127A79", 0.10, 0.65, 0.45, 0.7), ("#1F5FA8", -0.20, 1.05, 0.50, 0.6),
                 ("#35B3A1", 0.45, 0.20, 0.30, 0.45)]
        rib_a, rib_b, gloss, gloss_a = "#1C8C8F", "#2B63C2", lin("#BFF5EC"), 0.35
    else:
        img = vgrad(cv, "#F1FBFA", "#E8F2FB", 1.0)
        blobs = [("#A9E6DD", -0.55, 0.25, 0.65, 0.9), ("#B7CDF7", 0.60, 0.80, 0.70, 0.85),
                 ("#8CD8CD", 0.10, 0.65, 0.45, 0.75), ("#A6C1F2", -0.20, 1.05, 0.50, 0.7),
                 ("#D8F6EE", 0.45, 0.20, 0.30, 0.6)]
        rib_a, rib_b, gloss, gloss_a = "#5CC3B5", "#5C8FE0", lin("#FFFFFF"), 0.55
    for col, x, y, r, a in blobs:
        img = over(img, lin(col), a * glow(cv, x, y, r, r * 0.85))

    # two ribbons: a broad one through the middle and a thin one riding above it
    ribbons = [
        (lambda x: 0.50 + 0.19 * np.sin(1.9 * x + 0.6) - 0.06 * np.sin(3.7 * x + 1.1),
         lambda x: 0.21 + 0.08 * np.sin(2.6 * x - 0.4), 1.0),
        (lambda x: 0.36 + 0.17 * np.sin(1.9 * x + 0.25) - 0.05 * np.sin(3.3 * x + 0.4),
         lambda x: 0.035 + 0.02 * np.sin(2.2 * x + 1.0), 0.75),
    ]
    for top, thick, strength in ribbons:
        def bottom(x, top=top, thick=thick):
            return top(x) + thick(x)

        d_top = cv.edge(top)
        d_bot = cv.edge(bottom)
        mask = cv.cover(d_top) * cv.cover(-d_bot)
        shadow = np.exp(-np.maximum(d_bot, 0) / 0.06) * (d_bot > 0)
        img = img * (1.0 - strength * (0.40 if dark else 0.12) * shadow[..., None])
        t = smoothstep(-0.8, 0.8, cv.X)
        col = mix(lin(rib_a), lin(rib_b), t[..., None])
        across = np.clip(d_top / np.maximum(d_top - d_bot, 1e-3), 0, 1)
        col = mix(col, col * (0.80 if dark else 0.88), smoothstep(0.3, 1.0, across)[..., None])
        img = over(img, col, mask * (0.92 if dark else 0.85) * strength)
        sheen = np.exp(-np.maximum(d_top, 0) / 0.016) * mask
        img = over(img, gloss, gloss_a * strength * sheen)
    return img


DESIGNS = {
    "folio": (folio, "Folio", "Pages fanning out of the spine"),
    "bloom": (bloom, "Bloom", "The spark's warm light"),
    "strata": (strata, "Strata", "Page edges in slow waves"),
    "tide": (tide, "Tide", "Teal light and a ribbon"),
}
VARIANTS = ("light", "dark")
DEFAULT = ("folio", "light")


def render(name, variant, w, h):
    cv = Canvas(w, h)
    img = DESIGNS[name][0](cv, variant == "dark")
    return dither_to_u8(img, f"{name}-{variant}-{w}x{h}", grain=0.35)


def save_jpeg(arr, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(arr, "RGB").save(path, "JPEG", quality=92, subsampling=0, optimize=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ASSETS, "wallpapers"))
    ap.add_argument("--size", action="append", help="WxH (default: 2880x1800 and 1920x1080)")
    ap.add_argument("--only", action="append", help="design[-variant]")
    ap.add_argument("--preview", action="store_true", help="720x450 PNGs only, for iterating on the designs")
    a = ap.parse_args()
    sizes = [tuple(int(v) for v in s.split("x")) for s in a.size] if a.size else SIZES
    if a.preview:
        sizes = [(720, 450)]
    for name in DESIGNS:
        for variant in VARIANTS:
            key = f"{name}-{variant}"
            if a.only and name not in a.only and key not in a.only:
                continue
            for w, h in sizes:
                arr = render(name, variant, w, h)
                if a.preview:
                    p = os.path.join(a.out, f"{key}.png")
                    os.makedirs(a.out, exist_ok=True)
                    Image.fromarray(arr, "RGB").save(p)
                else:
                    p = os.path.join(a.out, f"{w}x{h}", f"openbook-{key}.jpg")
                    save_jpeg(arr, p)
                print(p, os.path.getsize(p))


if __name__ == "__main__":
    main()
