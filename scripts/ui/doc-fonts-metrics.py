#!/usr/bin/env python3
"""Metric checks for the document fonts (ANAL-208). Prints Markdown.

1. Per glyph, against an independent reference: Adobe's Core 14 AFM widths. Arial was drawn to Helvetica's widths,
   Times New Roman to Times Roman's and Courier New to Courier's, so Arimo, Tinos and Cousine should match
   Helvetica, Times-Roman and Courier on every printable ASCII character, within AFM rounding (0.5/1000 em).
   Georgia and Comic Sans MS have no public metrics; for Gelasio and Comic Relief only their upstreams' claims stand.
2. The widths of the test page's two strings (doc-fonts-test.html) in each candidate font at 100 px, regular and bold: the
   plain sum of advance widths, as the page measures it (kerning and ligatures off). Variable fonts are instanced at
   the weight with fontTools.
3. With --report: each family name the page measured, the widths it got, and the candidate fonts whose widths match
   both strings' (|difference| < 0.05 px), i.e. which font the browser really used for that name. Fonts with the
   same advances (Cousine and Droid Sans Mono are both 0.6 em monospace) all match.
4. With --typeface: the same for the framework, from doc-fonts-typeface.sh (Typeface.create + Paint.measureText).
   Paint returns whole pixels, so a match there is within 1 px on both strings.

usage: doc-fonts-metrics.py --fonttools LIB --afm DIR --font NAME=PATH[,BOLDPATH] ... [--report LABEL=JSON ...]
                            [--typeface LABEL=TSV ...]
  NAME=PATH: a candidate (e.g. arimo=.../Arimo-VF.ttf, roboto=.../Roboto-Regular.ttf); a single variable font is
  instanced at wght 700 for bold, a static family takes a second, bold file.
"""
import argparse
import hashlib
import json
import sys

TEXTS = ["The quick brown fox jumps over the lazy dog 0123456789", "WAVE Ivy, fjord; mmm iii (42%) & @#?!"]
SIZE = 100.0
# Stand-in -> (AFM regular, AFM bold), for the per-glyph check.
REFERENCE = {"arimo": ("Helvetica", "Helvetica-Bold"), "tinos": ("Times-Roman", "Times-Bold"),
             "cousine": ("Courier", "Courier-Bold"), "roboto": ("Helvetica", "Helvetica-Bold"),
             "noto-serif": ("Times-Roman", "Times-Bold")}


def load_afm(path, agl):
    widths = {}
    for line in open(path, encoding="latin-1"):
        if line.startswith("C "):
            f = dict(p.strip().split(" ", 1) for p in line.split(";") if " " in p.strip())
            u = agl.toUnicode(f["N"])
            if len(u) == 1:
                widths[ord(u)] = float(f["WX"])
    return widths


def instance(TTFont, instancer, path, weight):
    f = TTFont(path)
    if "fvar" in f:
        axes = {a.axisTag: a.defaultValue for a in f["fvar"].axes}
        axes["wght"] = weight
        f = instancer.instantiateVariableFont(f, axes)
    return f


def advances(font):
    cmap, hmtx, upm = font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm
    return {c: hmtx[g][0] * 1000.0 / upm for c, g in cmap.items()}, upm


def width(adv, text):
    return sum(adv[ord(c)] for c in text) * SIZE / 1000.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonttools", required=True)
    ap.add_argument("--afm", required=True)
    ap.add_argument("--font", action="append", default=[])
    ap.add_argument("--report", action="append", default=[])
    ap.add_argument("--typeface", action="append", default=[])
    a = ap.parse_args()
    sys.path.insert(0, a.fonttools)
    from fontTools import agl
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    cands = {}
    for spec in a.font:
        name, paths = spec.split("=", 1)
        paths = paths.split(",")
        reg = instance(TTFont, instancer, paths[0], 400)
        bold = instance(TTFont, instancer, paths[1] if len(paths) > 1 else paths[0], 700)
        cands[name] = {"files": paths, "400": advances(reg)[0], "700": advances(bold)[0]}

    print("## Per-glyph widths against Adobe's Core 14 AFMs\n")
    print("Printable ASCII (U+0020–U+007E, 95 characters), advance widths in 1/1000 em. AFMs: %s.\n" % a.afm)
    print("| Font | Weight | Reference | Within 0.5/1000 em | Largest difference |")
    print("|---|---|---|---|---|")
    for name, (r400, r700) in REFERENCE.items():
        if name not in cands:
            continue
        for wt, ref in (("400", r400), ("700", r700)):
            refw = load_afm("%s/%s.afm" % (a.afm, ref), agl)
            adv = cands[name][wt]
            diffs = [abs(adv[c] - refw[c]) for c in range(0x20, 0x7F) if c in adv and c in refw]
            n_ok = sum(d <= 0.5 for d in diffs)
            print("| %s | %s | %s | %d / %d | %.2f |" % (name, wt, ref, n_ok, len(diffs), max(diffs)))
    for f in sorted({"%s/%s.afm" % (a.afm, r) for pair in REFERENCE.values() for r in pair}):
        print("\n`%s` sha256 `%s`" % (f.rsplit("/", 1)[-1], hashlib.sha256(open(f, "rb").read()).hexdigest()), end="")
    print("\n")

    print("## Expected widths of the test strings at 100 px\n")
    print("The sum of advance widths (no kerning, no ligatures). String 1: `%s`. String 2: `%s`.\n" % tuple(TEXTS))
    print("| Font | Files | 400, string 1 (px) | 400, string 2 | 700, string 1 | 700, string 2 |")
    print("|---|---|---|---|---|---|")
    exp = {}
    for name, c in cands.items():
        exp[name] = {wt: [width(c[wt], t) for t in TEXTS] for wt in ("400", "700")}
        print("| %s | %s | %.3f | %.3f | %.3f | %.3f |" % (
            name, ", ".join("`%s`" % p.rsplit("/", 1)[-1] for p in c["files"]), *exp[name]["400"], *exp[name]["700"]))
    print()

    def which(ws, wt, tol=0.05):
        hits = [n for n in exp if all(abs(w - e) < tol for w, e in zip(ws, exp[n][wt]))]
        if hits:
            return ", ".join("%s (%+.3f)" % (n, ws[0] - exp[n][wt][0]) for n in hits)
        best = min(exp, key=lambda n: sum(abs(w - e) for w, e in zip(ws, exp[n][wt])))
        return "none (closest %s, %+.2f)" % (best, ws[0] - exp[best][wt][0])

    for spec in a.report:
        label, path = spec.split("=", 1)
        r = json.load(open(path))
        assert r["texts"] == TEXTS and r["size_px"] == SIZE, "the report measured different strings or a different size"
        print("## %s: what the browser used for each name\n" % label)
        print("%s, devicePixelRatio %s. A match is a width within 0.05 px of that font's sum of advances.\n"
              % (r["userAgent"], r["devicePixelRatio"]))
        print("| CSS font-family | 400, string 1 (px) | Font it matches | 700, string 1 (px) | Font it matches |")
        print("|---|---|---|---|---|")
        for x in r["results"]:
            print("| %s | %.3f | %s | %.3f | %s |" % (x["name"], x["w400"][0], which(x["w400"], "400"),
                                                     x["w700"][0], which(x["w700"], "700")))
        print()

    for spec in a.typeface:
        label, path = spec.split("=", 1)
        rows = [line.rstrip("\n").split("\t") for line in open(path) if line.strip()]
        print("## %s: what the framework used for each name\n" % label)
        print("`Typeface.create(name)` and `Paint.measureText` at 100 px, subpixel, unhinted, kerning and ligatures off. "
              "Paint returns whole pixels, so a match is within 1 px on both strings.\n")
        print("| Family | Weight | String 1 (px) | String 2 (px) | Font it matches |")
        print("|---|---|---|---|---|")
        for fam, wt, *ws in rows:
            ws = [float(w) for w in ws]
            print("| %s | %s | %.0f | %.0f | %s |" % (fam, wt, ws[0], ws[1], which(ws, wt, 1.0)))
        print()


if __name__ == "__main__":
    main()
