#!/usr/bin/env python3
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
"""Compare freshly generated brand assets (FRESH) with the committed ones (assets/). Exit 1 on any difference.

Images (wallpaper JPEGs, boot animation frames) are compared by decoded pixels, allowing a difference of 2 levels
(another libjpeg build may round differently); everything else must match exactly. Sounds are compared by the PCM
digest each render records in sounds.json (the synthesis is exact), and the committed Ogg files must decode to the
recorded length, because Vorbis encoders differ between ffmpeg builds.

usage: check-brand-assets.py FRESH [ASSETS]
"""
import io
import json
import os
import subprocess
import sys
import zipfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brandlib import ASSETS  # noqa: E402

fails = []


def same_pixels(a_bytes, b_bytes, name, tol=2):
    a = np.asarray(Image.open(io.BytesIO(a_bytes)).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(io.BytesIO(b_bytes)).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        fails.append(f"{name}: size {b.shape} != {a.shape}")
        return
    d = np.abs(a - b)
    if d.max() > tol:
        fails.append(f"{name}: pixels differ (max {d.max()}, mean {d.mean():.3f})")


def walk(root, sub):
    base = os.path.join(root, sub)
    for dp, _, fs in os.walk(base):
        for f in fs:
            yield os.path.relpath(os.path.join(dp, f), root)


def compare_tree(fresh, ref, sub, exts, pixels=False):
    got = {p for p in walk(fresh, sub) if p.endswith(exts)}
    want = {p for p in walk(ref, sub) if p.endswith(exts)}
    for p in sorted(want - got):
        fails.append(f"{p}: committed but not generated")
    for p in sorted(got - want):
        fails.append(f"{p}: generated but not committed")
    for p in sorted(got & want):
        a = open(os.path.join(fresh, p), "rb").read()
        b = open(os.path.join(ref, p), "rb").read()
        if a == b:
            continue
        if pixels:
            same_pixels(a, b, p)
        else:
            fails.append(f"{p}: differs")
    return len(got & want)


def compare_bootanimation(fresh, ref):
    za = zipfile.ZipFile(os.path.join(fresh, "bootanimation", "bootanimation.zip"))
    zb = zipfile.ZipFile(os.path.join(ref, "bootanimation", "bootanimation.zip"))
    na, nb = za.namelist(), zb.namelist()
    if na != nb:
        fails.append("bootanimation.zip: different entries")
        return 0
    for n in na:
        if zb.getinfo(n).compress_type != zipfile.ZIP_STORED:
            fails.append(f"bootanimation.zip: {n} is compressed")
        a, b = za.read(n), zb.read(n)
        if a != b:
            if n.endswith(".png"):
                same_pixels(a, b, f"bootanimation.zip:{n}", tol=0)
            else:
                fails.append(f"bootanimation.zip:{n} differs")
    return len(na)


def compare_sounds(fresh, ref):
    ma = json.load(open(os.path.join(fresh, "sounds", "sounds.json")))
    mb = json.load(open(os.path.join(ref, "sounds", "sounds.json")))
    if set(ma) != set(mb):
        fails.append(f"sounds.json: {sorted(set(ma) ^ set(mb))}")
    for k in sorted(set(ma) & set(mb)):
        if ma[k]["pcm_sha256"] != mb[k]["pcm_sha256"]:
            fails.append(f"sounds/{mb[k]['file']}: the synthesis differs from the committed render")
        path = os.path.join(ref, "sounds", mb[k]["file"])
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True)
        if out.returncode or abs(float(out.stdout or 0) - mb[k]["seconds"]) > 0.03:
            fails.append(f"sounds/{mb[k]['file']}: does not decode to {mb[k]['seconds']} s ({out.stdout.strip()})")
    return len(mb)


def main():
    fresh = sys.argv[1]
    ref = sys.argv[2] if len(sys.argv) > 2 else ASSETS
    counts = {}
    if os.path.isdir(os.path.join(fresh, "wallpapers")):
        counts["wallpapers"] = compare_tree(fresh, ref, "wallpapers", (".jpg",), pixels=True)
        counts["monet"] = compare_tree(fresh, ref, "wallpapers", (".json",))
    if os.path.isdir(os.path.join(fresh, "pointer")):
        counts["pointer"] = compare_tree(fresh, ref, "pointer", (".xml", ".svg", ".txt"))
    if os.path.isdir(os.path.join(fresh, "bootanimation")):
        counts["bootanimation"] = compare_bootanimation(fresh, ref)
        counts["bootanimation preview"] = compare_tree(fresh, ref, "bootanimation/preview", (".png", ".txt"),
                                                       pixels=True)
    if os.path.isdir(os.path.join(fresh, "sounds")):
        counts["sounds"] = compare_sounds(fresh, ref)
    for k, v in counts.items():
        print(f"{k}: {v} files compared")
    for f in fails:
        print("DIFF", f)
    print("check-brand-assets: " + ("OK" if not fails else f"{len(fails)} difference(s)"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
