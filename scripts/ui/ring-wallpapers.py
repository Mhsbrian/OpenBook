#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""ANAL-372: Overview's two-colour focus ring (design §5.2, WCAG technique C40) over OpenBook's eight wallpapers.

usage: scripts/ui/ring-wallpapers.py . OUT_DIR   (OUT_DIR: the design store, $OPENBOOK_EVIDENCE/design/launcher-design/)

For each wallpaper and each theme, the backdrop the ring sits on is built as Overview builds it: the wallpaper at
1920x1200 (the VM's 240 dpi screen), blurred (SurfaceFlinger's 51 px background blur, approximated by a Gaussian of
sigma 25.5) or sharp (blur off: battery saver, thermal, Developer options), under `surface` at 18 % (light) or 30 %
(dark). The ring's colours are the wallpaper's own roles from assets/wallpapers/monet.json: surfaceContainerLowest
(white / black) and onPrimaryContainer (accent1 tone 30 light, tone 90 dark; the prototype's Folio values). A model,
not a proof: the backdrop is sampled at 480x300 (every 4th pixel), and at each sample the better of the two colours
gives the contrast, not the colour actually drawn at a band's position. The lowest over the samples is
reported, with the share of pixels under 3:1 and under 4.5:1. Writes ring-wallpapers.json and one crop per case.
"""
import json, os, sys
from PIL import Image, ImageFilter, ImageDraw

R, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
monet = json.load(open(f"{R}/assets/wallpapers/monet.json"))


def rgb(h): return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lum(p): return 0.2126 * lin(p[0]) + 0.7152 * lin(p[1]) + 0.0722 * lin(p[2])


def cr(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


res = {}
for name in sorted(monet):
    src = Image.open(f"{R}/assets/wallpapers/2880x1800/{name}").convert("RGB").resize((1920, 1200), Image.LANCZOS)
    pal = monet[name]["palettes"]["accent1"]
    for theme in ("light", "dark"):
        sch = monet[name][theme]
        surface = rgb(sch["surface"])
        alpha = 0.18 if theme == "light" else 0.30
        lowest = (255, 255, 255) if theme == "light" else (0, 0, 0)
        opc = rgb(pal["30"] if theme == "light" else pal["90"])
        for mode in ("blurred", "sharp"):
            bg = src.filter(ImageFilter.GaussianBlur(25.5)) if mode == "blurred" else src
            tint = Image.new("RGB", bg.size, surface)
            bg = Image.blend(bg, tint, alpha)
            small = bg.resize((480, 300))  # every 4th pixel
            worst, under3, under45, n = 99.0, 0, 0, 0
            worst_at = None
            for y in range(small.height):
                for x in range(small.width):
                    p = small.getpixel((x, y))
                    c = max(cr(lowest, p), cr(opc, p))
                    n += 1
                    if c < 3: under3 += 1
                    if c < 4.5: under45 += 1
                    if c < worst: worst, worst_at = c, (x * 4, y * 4)
            key = f"{name} {theme} {mode}"
            res[key] = {"min": round(worst, 2), "at": worst_at, "under_3": under3 / n, "under_4_5": round(under45 / n, 4),
                        "colours": {"surfaceContainerLowest": "#%02X%02X%02X" % lowest,
                                    "onPrimaryContainer": "#%02X%02X%02X" % opc, "surface": sch["surface"]},
                        "ring_colours_apart": round(cr(lowest, opc), 2)}
            # A crop: the ring drawn around a 480x300 tile at the worst place, for eyes.
            if mode == "blurred":
                x, y = worst_at
                x0, y0 = max(0, min(1920 - 520, x - 260)), max(0, min(1200 - 340, y - 170))
                img = bg.copy()
                d = ImageDraw.Draw(img)
                box = [x0 + 20, y0 + 20, x0 + 500, y0 + 320]
                d.rounded_rectangle(box, 20, fill=src.crop(tuple(box)).resize((480, 300)).getpixel((0, 0)))
                for i, col in enumerate((lowest, opc, lowest)):
                    o = 3 * i + 1.5
                    d.rounded_rectangle([box[0] - o, box[1] - o, box[2] + o, box[3] + o], 20 + o, outline=col, width=3)
                img.crop((x0, y0, x0 + 520, y0 + 340)).save(f"{OUT}/ring-{name[:-4]}-{theme}.png")
    print(name, {k.split(" ", 1)[1]: v["min"] for k, v in res.items() if k.startswith(name)}, flush=True)
json.dump(res, open(f"{OUT}/ring-wallpapers.json", "w"), indent=1)
print("lowest:", min(v["min"] for v in res.values()))
