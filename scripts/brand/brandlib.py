# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for the OpenBook brand asset generators (scripts/brand/*.py).

Everything is deterministic: no clock, no unseeded randomness, numpy and Pillow pinned in requirements.txt.
Colours are blended in linear light and written as sRGB.
"""
import hashlib
import json
import os

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ASSETS = os.path.join(REPO, "assets")

# The brand palette (assets/README.md).
PRIMARY = "#4355B9"
PAGE_L = ("#7E8CFF", "#4355B9")
PAGE_R = ("#D08BFF", "#7A4CE0")
SPARK = ("#FFB38A", "#FF7A9C")
INK = "#1B1B21"
SURFACE_DARK = "#121318"


def hex_rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)], dtype=np.float32)


def to_lin(c):
    c = np.asarray(c, dtype=np.float32)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def to_srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float32), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055).astype(np.float32)


def lin(h):
    """A #RRGGBB colour in linear light."""
    return to_lin(hex_rgb(h))


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def mix(a, b, t):
    """Blend colour/array a to b by t (t broadcasts over the last axis)."""
    t = np.asarray(t, dtype=np.float32)
    if t.ndim and t.shape[-1] != 1:
        t = t[..., None]
    return a + (b - a) * t


def over(dst, color, alpha):
    """Composite a colour (or an HxWx3 image) over dst with coverage alpha (HxW)."""
    a = np.asarray(alpha, dtype=np.float32)[..., None]
    return dst * (1.0 - a) + color * a


def box_blur(img, r):
    """Box blur of radius r (pixels) along both axes, via cumulative sums. img: HxW or HxWxC."""
    if r < 1:
        return img
    out = img
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (r + 1, r)
        p = np.pad(out, pad, mode="edge")
        c = np.cumsum(p, axis=axis, dtype=np.float64)
        n = out.shape[axis]
        hi = np.take(c, np.arange(2 * r + 1, 2 * r + 1 + n), axis=axis)
        lo = np.take(c, np.arange(0, n), axis=axis)
        out = ((hi - lo) / (2 * r + 1)).astype(np.float32)
    return out


def gauss_blur(img, sigma):
    """Approximate Gaussian blur: three box blurs."""
    if sigma <= 0.5:
        return img
    r = max(1, int(round(np.sqrt(12.0 * sigma * sigma / 3.0 + 1.0) / 2.0)))
    for _ in range(3):
        img = box_blur(img, r)
    return img


def rng(name):
    """A numpy Generator seeded from a name, so each asset has its own stable noise."""
    seed = int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "little")
    return np.random.Generator(np.random.PCG64(seed))


def dither_to_u8(rgb_lin, name, grain=0.0):
    """Linear RGB float -> sRGB uint8 with triangular dither (no banding in the gradients) and optional grain."""
    s = to_srgb(rgb_lin)
    g = rng(name + ":dither")
    h, w = s.shape[:2]
    noise = (g.random((h, w, 1), dtype=np.float32) - g.random((h, w, 1), dtype=np.float32))
    if grain:
        noise = noise + g.standard_normal((h, w, 1), dtype=np.float32) * grain
    out = np.clip(np.floor(s * 255.0 + 0.5 + noise), 0, 255).astype(np.uint8)
    return out


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def pixel_digest(path):
    """sha256 of an image's decoded RGB(A) pixels: stable across encoder builds, unlike the file bytes."""
    from PIL import Image
    with Image.open(path) as im:
        im.load()
        return hashlib.sha256(im.tobytes()).hexdigest()
