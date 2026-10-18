#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""One image of every OpenBook brand asset, for the owner's visual review (ANAL-207): the wallpapers with the
dynamic colour each gives, the boot animation's key frames, the pointer set (and its accessibility styles), and the
sounds as spectrograms with their length and loudness.

Pointers come from a device when --device-pointers is given (BrandProbe's renders: the framework's own drawing of
our overlay), else from the preview SVGs (rsvg-convert). Monet swatches are monet.json's prediction; with
--device-monet (device-checks.sh's monet-device.tsv) the seed the device chose is shown next to it.
Font: Roboto Flex (OFL), fetched by scripts/brand/render-readme-assets.sh into the host data dir.

usage: contact-sheet.py OUT.jpg [--device-pointers DIR] [--device-monet TSV] [--note TEXT]
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brandlib import ASSETS  # noqa: E402
import pointers as ptr  # noqa: E402
import sounds as snd  # noqa: E402

W = 2400
M = 48
BG = (247, 246, 251)
INK = (27, 27, 33)
SUB = (96, 96, 110)
FONT = os.path.join(os.environ.get("OPENBOOK_HOME", os.path.expanduser("~/anybook")), "installer", "fonts",
                    "RobotoFlex.ttf")


def font(size, weight=400):
    f = ImageFont.truetype(FONT, size)
    try:
        f.set_variation_by_axes([weight if a["name"] == b"Weight" else a["default"] for a in f.get_variation_axes()])
    except Exception:
        pass
    return f


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Sheet:
    def __init__(self):
        self.parts = []  # (height, draw(img, y))

    def add(self, h, fn):
        self.parts.append((h, fn))

    def render(self, path):
        H = sum(h for h, _ in self.parts) + 2 * M
        img = Image.new("RGB", (W, H), BG)
        y = M
        for h, fn in self.parts:
            fn(img, y)
            y += h
        img.save(path, "JPEG", quality=90, subsampling=0, optimize=True)
        return img.size


def heading(sheet, title, sub=None):
    def draw(img, y):
        d = ImageDraw.Draw(img)
        d.text((M, y + 20), title, font=font(46, 600), fill=INK)
        if sub:
            d.text((M, y + 80), sub, font=font(26), fill=SUB)
    sheet.add(130 if sub else 96, draw)


def wallpapers(sheet, monet, device):
    names = [("folio", "Folio"), ("bloom", "Bloom"), ("strata", "Strata"), ("tide", "Tide")]
    tw, th = (W - 2 * M - 40) // 2, ((W - 2 * M - 40) // 2) * 10 // 16
    row_h = th + 190

    for key, title in names:
        def draw(img, y, key=key, title=title):
            d = ImageDraw.Draw(img)
            for i, variant in enumerate(("light", "dark")):
                x = M + i * (tw + 40)
                f = f"openbook-{key}-{variant}"
                im = Image.open(os.path.join(ASSETS, "wallpapers", "2880x1800", f + ".jpg")).convert("RGB")
                img.paste(im.resize((tw, th), Image.Resampling.LANCZOS), (x, y))
                label = f"{title} · {variant}" + ("   (default)" if (key, variant) == ("folio", "light") else "")
                d.text((x, y + th + 14), label, font=font(30, 600), fill=INK)
                mo = monet.get(f + ".jpg", {})
                sw, sy = 54, y + th + 62
                seeds = mo.get("seeds", [])[:1]
                cells = [("seed", seeds[0] if seeds else "#000000")]
                cells += [("L " + r, mo.get("light", {}).get(k, "#000000")) for r, k in
                          (("pri", "primary"), ("sec", "secondary"), ("ter", "tertiary"), ("cont", "primaryContainer"),
                           ("surf", "surfaceContainer"))]
                cells += [("D " + r, mo.get("dark", {}).get(k, "#000000")) for r, k in
                          (("pri", "primary"), ("sec", "secondary"), ("ter", "tertiary"), ("cont", "primaryContainer"),
                           ("surf", "surfaceContainer"))]
                for j, (lab, c) in enumerate(cells):
                    cx = x + j * (sw + 8)
                    d.rounded_rectangle((cx, sy, cx + sw, sy + sw), 10, fill=hexrgb(c))
                    d.text((cx, sy + sw + 6), lab, font=font(16), fill=SUB)
                dev = device.get(f)
                txt = f"predicted seed {seeds[0] if seeds else '?'}"
                if dev:
                    txt += f" · device seed {dev['seed_device']}, accent1_600 {dev['system_accent1_600']}"
                d.text((x, sy + sw + 34), txt, font=font(20), fill=SUB)
        sheet.add(row_h, draw)


def bootanimation(sheet):
    pv = os.path.join(ASSETS, "bootanimation", "preview")
    frames = sorted(f for f in os.listdir(pv) if f.endswith(".png"))
    n = len(frames)
    s = (W - 2 * M - (n - 1) * 12) // n

    def draw(img, y):
        d = ImageDraw.Draw(img)
        for i, f in enumerate(frames):
            im = Image.open(os.path.join(pv, f)).convert("RGB").resize((s, s), Image.Resampling.LANCZOS)
            x = M + i * (s + 12)
            img.paste(im, (x, y))
            d.text((x, y + s + 8), f.replace(".png", ""), font=font(18), fill=SUB)
        desc = open(os.path.join(pv, "desc.txt")).read().strip().replace("\n", "   |   ")
        d.text((M, y + s + 40), "desc.txt: " + desc, font=font(22), fill=SUB)
    sheet.add(s + 90, draw)


def render_svg(icon_name, fill, stroke, px):
    svg = ptr.svg(ptr.placed(icon_name), fill=fill, stroke=stroke)
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(svg)
    out = f.name + ".png"
    subprocess.run(["rsvg-convert", "-w", str(px), "-h", str(px), f.name, "-o", out], check=True)
    im = Image.open(out).convert("RGBA")
    os.unlink(f.name)
    os.unlink(out)
    return im


def pointers(sheet, device_dir):
    names = list(ptr.ICONS)
    px = 96
    cell = 112

    def get(name, fill, stroke):
        if device_dir:
            p = os.path.join(device_dir, f"{name}-{fill}-{stroke}.png")
            if os.path.exists(p):
                im = Image.open(p).convert("RGBA")
                return im.resize((px, px * im.height // im.width), Image.Resampling.LANCZOS)
        colours = {"black": "#000000", "green": "#1AA64A", "red": "#F55E57", "pink": "#F94AAB", "blue": "#009DC9",
                   "purple": "#AD72FF"}
        sc = {"white": "#FFFFFF", "black": "#000000", "none": None}[stroke]
        return render_svg(name, colours[fill], sc, px)

    per_row = (W - 2 * M) // cell

    def draw_set(img, y):
        d = ImageDraw.Draw(img)
        for bi, bgc in enumerate(((154, 160, 181), (255, 255, 255), (24, 25, 32))):
            yy = y + bi * (cell + 10)
            d.rounded_rectangle((M - 8, yy - 8, M + per_row * cell, yy + cell - 8), 16, fill=bgc)
            for i, n in enumerate(names[:per_row]):
                im = get(n, "black", "white")
                img.paste(im, (M + i * cell, yy), im)
        d.text((M, y + 3 * (cell + 10) + 4), "  ·  ".join(names), font=font(17), fill=SUB)
    sheet.add(3 * (cell + 10) + 44, draw_set)

    show = ["arrow", "hand", "text", "zoom_in"]
    fills = ["black", "green", "red", "pink", "blue", "purple"]
    strokes = ["white", "black", "none"]

    def draw_styles(img, y):
        d = ImageDraw.Draw(img)
        for si, s in enumerate(strokes):
            yy = y + si * (cell + 6)
            d.text((M, yy + 36), f"stroke {s}", font=font(24, 600), fill=INK)
            for fi, f in enumerate(fills):
                for ii, n in enumerate(show):
                    x = M + 200 + (fi * len(show) + ii) * (cell - 28)
                    d.rectangle((x, yy, x + cell - 32, yy + cell - 16), fill=(154, 160, 181))
                    im = get(n, f, s).resize((cell - 36, cell - 36), Image.Resampling.LANCZOS)
                    img.paste(im, (x + 2, yy + 2), im)
        for fi, f in enumerate(fills):
            d.text((M + 200 + fi * len(show) * (cell - 28), y + 3 * (cell + 6)), f"fill {f}", font=font(20),
                   fill=SUB)
    sheet.add(3 * (cell + 6) + 40, draw_styles)


def sounds(sheet):
    man = json.load(open(os.path.join(ASSETS, "sounds", "sounds.json")))
    rows = list(man.items())
    sw, sh = W - 2 * M - 640, 110

    for name, m in rows:
        def draw(img, y, name=name, m=m):
            d = ImageDraw.Draw(img)
            d.text((M, y + 10), f"{m['title']}", font=font(30, 600), fill=INK)
            d.text((M, y + 50), f"{m['file']}", font=font(18), fill=SUB)
            d.text((M, y + 74), f"{m['seconds']} s · {m['lufs']} LUFS · peak {m['true_peak_dbfs']} dBFS"
                   f"{' · loops' if m['loop'] else ''}", font=font(18), fill=SUB)
            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "s.png")
                subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i",
                                os.path.join(ASSETS, "sounds", m["file"]), "-lavfi",
                                f"showspectrumpic=s={sw}x{sh}:mode=combined:legend=0:scale=log:fscale=log:"
                                f"color=intensity", out], check=True)
                im = Image.open(out).convert("RGB").resize((sw, sh))
            img.paste(im, (M + 620, y))
        sheet.add(sh + 16, draw)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--device-pointers")
    ap.add_argument("--device-monet")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    monet = json.load(open(os.path.join(ASSETS, "wallpapers", "monet.json")))
    device = {}
    if a.device_monet:
        with open(a.device_monet) as f:
            for r in csv.DictReader(f, delimiter="\t"):
                device[r["wallpaper"]] = r
    sh = Sheet()
    heading(sh, "OpenBook system assets — contact sheet (ANAL-207)", a.note or None)
    heading(sh, "Wallpapers", "8 of our own, 2880×1800 and 1920×1080. Swatches: the dynamic colour (TonalSpot) "
            "predicted for light (L) and dark (D) themes")
    wallpapers(sh, monet, device)
    heading(sh, "Boot animation", "/product/media/bootanimation.zip, 480×480 at 30 fps on #121318: the pages unfold, "
            "the spark lights and breathes until boot completes, then the mark fades")
    bootanimation(sh)
    heading(sh, "Pointer", ("20 shapes on Android 17's vector pointer icons; " +
                            ("rendered on the device by PointerIcon from our overlay" if a.device_pointers
                             else "previews (rsvg-convert)") +
                            ". Top: default style on grey, white and dark; below: the accessibility fills and strokes"))
    pointers(sh, a.device_pointers)
    heading(sh, "Sounds", "Synthesised: one glass-mallet voice and the D major 9 motif. Spectrograms, log frequency")
    sounds(sh)
    print(a.out, sh.render(a.out))


if __name__ == "__main__":
    main()
