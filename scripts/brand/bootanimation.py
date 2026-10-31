#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""OpenBook's boot animation, from the brand mark (assets/brand/openbook-mark.svg): the two pages unfold from the
spine and the spark lights up (part0, played in full), the spark breathes while Android boots (part1, looped until
boot completes), and the mark fades out (part2, played in full). Format: frameworks/base/cmds/bootanimation/
FORMAT.md. Frames are 480 x 480 on the brand's dark surface; bootanimation centres them and fills the rest of the
screen with the same colour.

Output: assets/bootanimation/bootanimation.zip (stored, not compressed, as bootanimation needs) and
assets/bootanimation/preview/*.png (key frames for the contact sheet).

usage: bootanimation.py [--out DIR]
"""
import argparse
import io
import math
import os
import re
import sys
import zipfile

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brandlib import ASSETS, SURFACE_DARK, gauss_blur, hex_rgb  # noqa: E402

SIZE = 480
FPS = 30
SS = 4              # supersampling for the polygon edges
MARK_PX = 250       # the mark's 48-unit box, on screen
MARK = os.path.join(ASSETS, "brand", "openbook-mark.svg")
PARTS = [("c", 1, 0, "part0", 42), ("p", 0, 0, "part1", 60), ("c", 1, 0, "part2", 12)]


def mark_paths():
    """The mark's three paths and gradients, read from the SVG so the animation follows the brand file."""
    svg = open(MARK).read()
    grads = {}
    for m in re.finditer(r'<linearGradient id="(\w+)" x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)">'
                         r'<stop offset="0" stop-color="(#\w+)"/><stop offset="1" stop-color="(#\w+)"/>', svg):
        grads[m.group(1)] = ([float(m.group(i)) for i in range(2, 6)], hex_rgb(m.group(6)), hex_rgb(m.group(7)))
    paths = []
    for m in re.finditer(r'<path d="([^"]+)" fill="url\(#(\w+)\)"/>', svg):
        paths.append((flatten(m.group(1)), grads[m.group(2)]))
    assert len(paths) == 3, "openbook-mark.svg: expected two pages and a spark"
    return paths


def flatten(d, steps=24):
    """Absolute M/L/C/Z path data -> polygon points."""
    toks = re.findall(r"[MLCZ]|-?[\d.]+", d)
    pts, i, cmd, cur = [], 0, None, (0.0, 0.0)
    while i < len(toks):
        if toks[i] in "MLCZ":
            cmd = toks[i]
            i += 1
            if cmd == "Z":
                continue
        if cmd in ("M", "L"):
            cur = (float(toks[i]), float(toks[i + 1]))
            pts.append(cur)
            i += 2
        elif cmd == "C":
            c = [float(t) for t in toks[i:i + 6]]
            p0, p1, p2, p3 = cur, (c[0], c[1]), (c[2], c[3]), (c[4], c[5])
            for k in range(1, steps + 1):
                t = k / steps
                mt = 1 - t
                pts.append((mt ** 3 * p0[0] + 3 * mt * mt * t * p1[0] + 3 * mt * t * t * p2[0] + t ** 3 * p3[0],
                            mt ** 3 * p0[1] + 3 * mt * mt * t * p1[1] + 3 * mt * t * t * p2[1] + t ** 3 * p3[1]))
            cur = p3
            i += 6
    return np.array(pts, dtype=np.float64)


def ease_out_cubic(t):
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


def ease_out_back(t, s=1.9):
    t = min(max(t, 0.0), 1.0) - 1
    return 1 + t * t * ((s + 1) * t + s)


def phase(t, a, b):
    return min(max((t - a) / (b - a), 0.0), 1.0)


def coverage(poly_px):
    """Anti-aliased coverage of a polygon given in output pixels."""
    im = Image.new("L", (SIZE * SS, SIZE * SS), 0)
    ImageDraw.Draw(im).polygon([(x * SS, y * SS) for x, y in poly_px], fill=255)
    im = im.resize((SIZE, SIZE), Image.Resampling.BOX)
    return np.asarray(im, dtype=np.float32) / 255.0


def gradient(poly_px, grad):
    """SVG objectBoundingBox linear gradient, interpolated in sRGB as SVG does."""
    (x1, y1, x2, y2), c0, c1 = grad
    lo, hi = poly_px.min(axis=0), np.maximum(poly_px.max(axis=0), poly_px.min(axis=0) + 1e-3)
    ys, xs = np.mgrid[0:SIZE, 0:SIZE].astype(np.float32) + 0.5
    u, v = (xs - lo[0]) / (hi[0] - lo[0]), (ys - lo[1]) / (hi[1] - lo[1])
    dx, dy = x2 - x1, y2 - y1
    t = np.clip(((u - x1) * dx + (v - y1) * dy) / (dx * dx + dy * dy), 0, 1)[..., None]
    return c0 + (c1 - c0) * t


class Painter:
    def __init__(self):
        self.paths = mark_paths()
        self.bg = hex_rgb(SURFACE_DARK)

    def to_px(self, pts, scale=1.0, cy_shift=0.0):
        s = MARK_PX / 48.0 * scale
        return np.stack([SIZE / 2 + (pts[:, 0] - 24) * s, SIZE / 2 + (pts[:, 1] - 24 + cy_shift) * s], axis=1)

    def frame(self, open_=1.0, rise=0.0, alpha=1.0, spark=1.0, spark_rot=0.0, glow=0.35, scale=1.0, sheen=None):
        img = np.broadcast_to(self.bg, (SIZE, SIZE, 3)).copy()
        (left, gl), (right, gr), (spk, gs) = self.paths
        # pages: scaled out from the spine (x = 24) and lifted a little while they open
        pages = []
        for pts, g in ((left, gl), (right, gr)):
            p = pts.copy()
            p[:, 0] = 24 + (p[:, 0] - 24) * max(open_, 0.02)
            p[:, 1] = 40 - (40 - p[:, 1]) * (0.82 + 0.18 * open_)
            pages.append((self.to_px(p, scale, rise), g))
        for poly, g in pages:
            col = gradient(poly, g)
            cov = coverage(poly) * alpha
            if sheen is not None:  # a soft band of light travelling across the pages
                xs = np.arange(SIZE, dtype=np.float32)[None, :, None]
                band = np.exp(-((xs - sheen) / 38.0) ** 2) * 0.22
                col = col + (1 - col) * band
            img = img * (1 - cov[..., None]) + col * cov[..., None]
        # spark: grows from the centre of its own box, turns, and glows
        if spark > 0:
            c = spk.mean(axis=0)
            a = math.radians(spark_rot)
            q = spk - c
            q = np.stack([q[:, 0] * math.cos(a) - q[:, 1] * math.sin(a),
                          q[:, 0] * math.sin(a) + q[:, 1] * math.cos(a)], axis=1) * spark + c
            poly = self.to_px(q, scale, rise)
            cov = coverage(poly) * alpha
            halo = gauss_blur(cov, 14.0) * glow * 2.2
            halo_col = hex_rgb("#FF9A92")
            img = img + (halo_col - img) * np.clip(halo, 0, 1)[..., None] * 0.9
            col = gradient(poly, gs)
            img = img * (1 - cov[..., None]) + col * cov[..., None]
        return np.clip(np.round(img * 255), 0, 255).astype(np.uint8)


def frames():
    p = Painter()
    out = {}
    n0 = PARTS[0][4]
    out["part0"] = []
    for i in range(n0):
        t = i / (n0 - 1)
        o = ease_out_cubic(phase(t, 0.05, 0.70))
        sp = ease_out_back(phase(t, 0.50, 0.95))
        out["part0"].append(p.frame(open_=o, rise=3.0 * (1 - o), alpha=ease_out_cubic(phase(t, 0.0, 0.35)),
                                    spark=sp, spark_rot=45 * (1 - phase(t, 0.5, 0.95)),
                                    glow=0.35 + 0.45 * math.sin(math.pi * phase(t, 0.55, 1.0))))
    n1 = PARTS[1][4]
    out["part1"] = []
    for i in range(n1):
        t = i / n1  # loops: frame n1 would equal frame 0
        breathe = math.sin(2 * math.pi * t)
        out["part1"].append(p.frame(spark=1.0 + 0.05 * breathe, glow=0.35 + 0.18 * breathe,
                                    sheen=-120 + (SIZE + 240) * t))
    n2 = PARTS[2][4]
    out["part2"] = []
    for i in range(n2):
        t = (i + 1) / n2
        out["part2"].append(p.frame(alpha=1 - ease_out_cubic(t), scale=1 + 0.04 * t, glow=0.35 * (1 - t)))
    return out


def png_bytes(arr):
    b = io.BytesIO()
    Image.fromarray(arr, "RGB").save(b, "PNG", optimize=True)
    return b.getvalue()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(ASSETS, "bootanimation"))
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "preview"), exist_ok=True)
    fr = frames()
    bg = SURFACE_DARK
    desc = f"{SIZE} {SIZE} {FPS}\n" + "".join(f"{t} {c} {p} {d} {bg}\n" for t, c, p, d, _ in PARTS)
    zpath = os.path.join(a.out, "bootanimation.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
        def add(name, data):
            zi = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, data)
        add("desc.txt", desc)
        for _, _, _, part, n in PARTS:
            for i, arr in enumerate(fr[part]):
                add(f"{part}/{i:03d}.png", png_bytes(arr))
    # key frames for the contact sheet
    keys = [("part0", i) for i in (0, 8, 14, 20, 26, 32, 41)] + [("part1", 15), ("part1", 45), ("part2", 6)]
    for part, i in keys:
        Image.fromarray(fr[part][i], "RGB").save(os.path.join(a.out, "preview", f"{part}-{i:03d}.png"))
    with open(os.path.join(a.out, "preview", "desc.txt"), "w") as f:
        f.write(desc)
    print(zpath, os.path.getsize(zpath), "bytes,", sum(p[4] for p in PARTS), "frames")


if __name__ == "__main__":
    main()
