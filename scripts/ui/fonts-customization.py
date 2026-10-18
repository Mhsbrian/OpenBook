#!/usr/bin/env python3
"""Write an /product/etc/fonts_customization.xml that gives AOSP 17's SystemUI, Launcher3 and SettingsLib
the font families they ask for, using the OFL releases of Google Sans and Google Sans Flex.

AOSP 17 styles name `google-sans*` and `variable-<role>-<size>[-emphasized]` families (21 uses in SystemUI,
25 in Launcher3, 30 in SettingsLib) that no AOSP font config defines, so they fall back to Roboto.
Googlebook defines them in its own fonts_customization.xml (docs/googlebook-ui.md). The variable-* families
follow the Material 3 type scale: optical size = type size in sp; Expressive "emphasized" = one weight
step heavier and fully rounded (ROND 100).

Font files (github.com/google/fonts, OFL 1.1; see docs/googlebook-ui.md for the pinned commit):
  GoogleSans-VF.ttf          ofl/googlesans/GoogleSans[GRAD,opsz,wght].ttf        opsz 17..18, wght 400..700
  GoogleSans-Italic-VF.ttf   ofl/googlesans/GoogleSans-Italic[GRAD,opsz,wght].ttf
  GoogleSansFlex-VF.ttf      ofl/googlesansflex/GoogleSansFlex[ROND,opsz,slnt,wdth,wght].ttf

It also defines the metric-compatible document fonts (ANAL-208: Arimo, Tinos, Cousine, Gelasio, Comic Relief,
Archivo Black, Archivo Narrow; files and sources in device/anybook/common/desktop/fonts/documents) and points the
Windows family names their upstream metadata names at them: arial -> arimo, times new roman -> tinos, and so on.

The desktop products install the committed output, device/anybook/common/desktop/fonts/fonts_customization.xml,
to /product/etc. The build runs --check on it and fails if it differs from what this script writes, so after
editing this script, regenerate it:

  scripts/ui/fonts-customization.py > device/anybook/common/desktop/fonts/fonts_customization.xml
  scripts/ui/fonts-customization.py --check device/anybook/common/desktop/fonts/fonts_customization.xml

WebView and Chrome never read fonts_customization.xml: their Skia parses only /system/etc/fonts.xml, with font
paths relative to /system/fonts (docs/googlebook-ui.md §2.1). --legacy-fonts-xml rewrites AOSP's fonts.xml so it
declares the same families (as ../../product/fonts/<file>) and moves the aliases to them. The result is
aosp/patches/frameworks/base/0001-*.patch; after changing DOCS, regenerate the patch from

  scripts/ui/fonts-customization.py --legacy-fonts-xml <AOSP>/frameworks/base/data/fonts/fonts.xml
"""

import difflib
import re
import sys

SANS, SANS_I, FLEX = "GoogleSans-VF.ttf", "GoogleSans-Italic-VF.ttf", "GoogleSansFlex-VF.ttf"

# Material 3 type scale: role -> (size in sp, regular weight). m3.material.io/styles/typography/type-scale-tokens
SCALE = [
    ("display-large", 57, 400), ("display-medium", 45, 400), ("display-small", 36, 400),
    ("headline-large", 32, 400), ("headline-medium", 28, 400), ("headline-small", 24, 400),
    ("title-large", 22, 400), ("title-medium", 16, 500), ("title-small", 14, 500),
    ("label-large", 14, 500), ("label-medium", 12, 500), ("label-small", 11, 500),
    ("body-large", 16, 400), ("body-medium", 14, 400), ("body-small", 12, 400),
]


def vf(upright, italic=None, weights=(400, 500, 600, 700)):
    """A wght 400..700 variable font (and its italic) as one <font> per weight: (file, weight, style, axes)."""
    out = [(upright, w, "normal", {"wght": w}) for w in weights]
    if italic:
        out += [(italic, w, "italic", {"wght": w}) for w in weights]
    return out


def static(prefix, weights=((400, "Regular"), (700, "Bold")), italic=True):
    out = [("%s-%s.ttf" % (prefix, n), w, "normal", {}) for w, n in weights]
    if italic:
        out += [("%s-%s.ttf" % (prefix, "Italic" if w == 400 else n + "Italic"), w, "italic", {}) for w, n in weights]
    return out


# Metric-compatible document fonts (ANAL-208): (family, fonts, aliases). Each alias is the Windows font that the
# family's upstream metadata (google/fonts DESCRIPTION.en_us.html, the font's own name table) says it is metrically
# compatible with. Archivo Black and Archivo Narrow claim no such compatibility, so they are named families only.
# The 13 other families Googlebook adds (Tachyonic, Velarium, Geotic, Tisane, Gaumond, Trophis, Codecs, Comedic Sans,
# Whendings 1-4, Arvos) are not published anywhere yet (docs/googlebook-ui.md §2.1).
DOCS = [
    ("arimo", vf("Arimo-VF.ttf", "Arimo-Italic-VF.ttf"), ["arial"]),
    ("tinos", static("Tinos"), ["times new roman"]),
    ("cousine", static("Cousine"), ["courier new"]),
    ("gelasio", vf("Gelasio-VF.ttf", "Gelasio-Italic-VF.ttf"), ["georgia"]),
    ("comic-relief", static("ComicRelief", italic=False), ["comic sans ms"]),
    ("archivo-black", [("ArchivoBlack-Regular.ttf", 400, "normal", {})], []),
    ("archivo-narrow", vf("ArchivoNarrow-VF.ttf", "ArchivoNarrow-Italic-VF.ttf"), []),
]
# Skia knows a font only by the names fonts.xml gives it, so a family whose own name has a space ("Comic Relief")
# also gets that name, as page CSS spells it.
DOCS = [(name, fonts, aliases + ([name.replace("-", " ")] if "-" in name else [])) for name, fonts, aliases in DOCS]


def font(path, weight, style="normal", **axes):
    ax = "".join('\n      <axis tag="%s" stylevalue="%s"/>' % (t, v) for t, v in axes.items())
    return '    <font weight="%d" style="%s">%s%s\n    </font>' % (weight, style, path, ax)


def family(name, fonts):
    return '  <family customizationType="new-named-family" name="%s">\n%s\n  </family>' % (name, "\n".join(fonts))


def sans(opsz, weights, italic=True):
    out = [font(SANS, w, opsz=opsz, wght=w) for w in weights]
    if italic:
        out += [font(SANS_I, w, "italic", opsz=opsz, wght=w) for w in weights]
    return out


def render():
    fams = [
        # Google Sans: headlines (opsz 18) and running text (opsz 17), as config_headlineFontFamily /
        # config_bodyFontFamily name them.
        family("google-sans", sans(18, (400, 500, 600, 700))),
        family("google-sans-medium", sans(18, (500, 700), italic=False)),
        family("google-sans-bold", sans(18, (700,), italic=False)),
        family("google-sans-text", sans(17, (400, 500, 600, 700))),
        family("google-sans-text-medium", sans(17, (500, 700), italic=False)),
        family("google-sans-text-bold", sans(17, (700,), italic=False)),
        family("google-sans-text-italic", [font(SANS_I, w, "italic", opsz=17, wght=w) for w in (400, 500, 700)]),
        # Google Sans Flex, the full weight range; italic is the slant axis.
        family("google-sans-flex", [font(FLEX, w, wght=w) for w in range(100, 1000, 100)]
               + [font(FLEX, w, "italic", wght=w, slnt=-10) for w in range(100, 1000, 100)]),
        # Googlebook's clock families are proprietary fonts; Flex is the open stand-in.
        family("google-sans-clock", [font(FLEX, w, wght=w) for w in (400, 500, 700)]),
        family("google-sans-flex-clock", [font(FLEX, w, wght=w) for w in range(100, 1000, 100)]),
    ]
    for role, size, w in SCALE:
        fams.append(family("variable-" + role, [font(FLEX, w, wght=w, wdth=100, opsz=size)]))
    for role, size, w in SCALE:
        fams.append(family("variable-%s-emphasized" % role,
                           [font(FLEX, w + 100, wght=w + 100, wdth=100, ROND=100, opsz=size)]))
    # Document fonts. A customization alias is listed before fonts.xml's own (arial -> sans-serif, ...), and
    # Typeface keeps the first alias of a name, so these win.
    for name, fonts, _ in DOCS:
        fams.append(family(name, [font(f, w, s, **ax) for f, w, s, ax in fonts]))
    fams += ['  <alias name="%s" to="%s"/>' % (a, name) for name, _, aliases in DOCS for a in aliases]
    return "\n".join([
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!-- Generated by OpenBook scripts/ui/fonts-customization.py. Fonts: Google Sans and Google Sans Flex,",
        "     SIL Open Font License 1.1 (github.com/google/fonts). \"Google Sans\" is a trademark of Google LLC.",
        "     Document fonts: Arimo, Tinos, Cousine, Gelasio, Comic Relief, Archivo Black, Archivo Narrow (OFL 1.1). -->",
        '<fonts-modification version="1">',
        "\n".join(fams),
        "</fonts-modification>",
    ]) + "\n"


# In AOSP's fonts.xml the document families go after the last named family's alias, ahead of the fallback families.
LEGACY_ANCHOR = '<alias name="source-sans-pro-semi-bold" to="source-sans-pro" weight="600"/>'


def legacy_fonts_xml(text):
    """AOSP's fonts.xml with the document families and their aliases, for the apps that parse it (Skia)."""
    for _, _, aliases in DOCS:
        for a in aliases:
            # Skia keeps the first family a name maps to, so AOSP's own alias (arial -> sans-serif) has to go.
            text, n = re.subn(r'\n *<alias name="%s" to="[^"]*" */>' % re.escape(a), "", text)
            if n > 1:
                raise SystemExit("fonts.xml has %d aliases named %r" % (n, a))
    if text.count(LEGACY_ANCHOR) != 1:
        raise SystemExit("fonts.xml: no single %s to insert after" % LEGACY_ANCHOR)
    out = ["", "",
           "    <!-- OpenBook: metric-compatible document fonts (scripts/ui/fonts-customization.py). They are in",
           "         /product/fonts; paths here are relative to /system/fonts. The framework reads the same families",
           "         and aliases from /product/etc/fonts_customization.xml; this file is for apps that parse it",
           "         (WebView and Chrome). -->"]
    for name, fonts, aliases in DOCS:
        out.append('    <family name="%s">' % name)
        for f, w, s, ax in fonts:
            if ax:
                out.append('        <font weight="%d" style="%s">../../product/fonts/%s' % (w, s, f))
                out += ['          <axis tag="%s" stylevalue="%s" />' % (t, v) for t, v in ax.items()]
                out.append("        </font>")
            else:
                out.append('        <font weight="%d" style="%s">../../product/fonts/%s</font>' % (w, s, f))
        out.append("    </family>")
        out += ['    <alias name="%s" to="%s" />' % (a, name) for a in aliases]
    return text.replace(LEGACY_ANCHOR, LEGACY_ANCHOR + "\n".join(out), 1)


def main(argv):
    if argv[1:2] == ["--legacy-fonts-xml"]:
        with open(argv[2], encoding="utf-8") as f:
            sys.stdout.write(legacy_fonts_xml(f.read()))
        return 0
    xml = render()
    if argv[1:2] != ["--check"]:
        sys.stdout.write(xml)
        return 0
    with open(argv[2], encoding="utf-8") as f:
        have = f.read()
    if have == xml:
        return 0
    sys.stderr.writelines(difflib.unified_diff(have.splitlines(True), xml.splitlines(True), argv[2], "generated"))
    sys.stderr.write("%s differs from what fonts-customization.py writes; regenerate it (see the script's docstring)\n"
                     % argv[2])
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
