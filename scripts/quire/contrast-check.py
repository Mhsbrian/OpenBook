#!/usr/bin/env python3
"""Check WCAG contrast for the colour pairs the Quire note uses, in both themes (ANAL-215, revised for the glass note
in ANAL-227).

Reads the tokens from docs/quire-design/index.html so the table in docs/quire-design.md §7 cannot drift from the
prototype. The note is translucent glass (`--note-tint` at `--glass-a`) and the sheets on it ("paper", the field) are
translucent too, so every pair is composited through its whole stack (paper over glass over backdrop) over both black
and white, and scored at whichever gives the lower ratio. That bounds every real backdrop under the blur: the blur
averages what is behind, it never makes it darker than black or lighter than white.

usage: contrast-check.py [--md] [--html PATH]      exit 1 if any pair misses its target
       --html PATH checks another copy of the prototype (e.g. `git show <rev>:docs/quire-design/index.html`)
"""
import re, sys

HTML = __import__('pathlib').Path(__file__).resolve().parents[2] / 'docs/quire-design/index.html'
if '--html' in sys.argv: HTML = __import__('pathlib').Path(sys.argv[sys.argv.index('--html') + 1])
css = HTML.read_text()

def block(selector):
    m = re.search(re.escape(selector) + r'\s*\{(.*?)\n\}', css, re.S)
    return dict(re.findall(r'--([\w-]+):\s*([^;]+);', m.group(1)))

ROOT = block(':root')
T = {'light': block(':root, [data-theme="light"]'), 'dark': block('[data-theme="dark"]')}
GLASS_A = float(ROOT['glass-a'])

def rgb(c, tk=None):
    c = c.strip()
    if c.startswith('var(--'):  # --ink: var(--on-surface)
        return rgb(tk[c[6:-1]], tk)
    if c.startswith('#'):
        return tuple(int(c[i:i+2], 16) / 255 for i in (1, 3, 5)) + (1.0,)
    m = re.match(r'rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)', c)
    r, g, b, a = m.groups(); return (float(r) / 255, float(g) / 255, float(b) / 255, float(a) if a else 1.0)

def over(fg, bg):  # composite fg (with alpha) over opaque bg
    a = fg[3]; return tuple(fg[i] * a + bg[i] * (1 - a) for i in range(3)) + (1.0,)

def lum(c):
    def ch(v): return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])

def ratio(a, b):
    la, lb = lum(a), lum(b); hi, lo = max(la, lb), min(la, lb); return (hi + 0.05) / (lo + 0.05)

BLACK, WHITE = (0, 0, 0, 1), (1, 1, 1, 1)
# (label, foreground token, background stack (top first), target ratio)
# 'glass' is the note; 'paper' and 'field' are the sheets on it. A stack of one opaque token needs no backdrop.
PAIRS = [
    ('Ink: answer text, titles, text buttons, on the glass', 'ink', ['glass'], 4.5),
    ('Soft ink: the quiet line, step kinds, pending steps, on the glass', 'ink-soft', ['glass'], 4.5),
    ('Soft ink on paper (cards)', 'ink-soft', ['paper', 'glass'], 4.5),
    ('Soft ink in the field (placeholder) and on change rows', 'ink-soft', ['field', 'glass'], 4.5),
    ('Ink on paper (undo pill, paper button)', 'ink', ['paper', 'glass'], 4.5),
    ('Filled button: Keep it, Take over, send', 'on-primary', ['primary'], 4.5),
    ('Tonal button, agent picker selection', 'on-secondary-container', ['secondary-container'], 4.5),
    ('Stop pill, Delete', 'on-error-container', ['error-container'], 4.5),
    ('New value pill', 'on-primary-container', ['primary-container'], 4.5),
    ('Mic indicator', 'on-success-container', ['success-container'], 4.5),
    ('Automation chip (Using Settings)', 'on-tertiary-container', ['tertiary-container'], 4.5),
    ('Halo label, Jump pill, paused pill', 'inverse-on-surface', ['inverse-surface'], 4.5),
    ('Done tick (non-text) on the glass', 'success', ['glass'], 3.0),
    ('Focus ring (non-text) on the glass', 'primary', ['glass'], 3.0),
    ('Focus ring (non-text) on paper', 'primary', ['paper', 'glass'], 3.0),
    ('Pending-step ring, soft ink (non-text)', 'ink-soft', ['glass'], 3.0),
    ('Field outline on focus (non-text)', 'primary', ['field', 'glass'], 3.0),
    ('Running mark, the ink dot (non-text)', 'primary', ['glass'], 3.0),
]

def layer(theme, name):
    tk = T[theme]
    if name == 'glass':
        r, g, b = [int(v) / 255 for v in tk['note-tint'].split(',')]
        return (r, g, b, GLASS_A)
    return rgb(tk[name], tk)

def worst(theme, fg_t, stack):
    """The pair's ratio at its worst backdrop: the minimum over black and white behind the translucent stack."""
    tk = T[theme]; fg = rgb(tk[fg_t], tk)
    layers = [layer(theme, n) for n in stack]
    if all(l[3] >= 1 for l in layers):
        return ratio(fg, layers[0]), None
    best = None
    for bd, name in ((BLACK, 'black'), (WHITE, 'white')):
        c = bd
        for l in reversed(layers): c = over(l, c)
        r = ratio(fg, c)
        if best is None or r < best[0]: best = (r, name)
    return best

rows, ok = [], True
for label, fg_t, stack, target in PAIRS:
    cells = [label]
    for theme in ('light', 'dark'):
        r, backdrop = worst(theme, fg_t, stack); passed = r >= target; ok &= passed
        cells.append(f'{r:.1f}:1 {"pass" if passed else "FAIL"}' + (f' ({backdrop})' if backdrop and '--md' not in sys.argv else ''))
    cells.append(f'{target:.1f}:1' + (' (worst backdrop)' if any(layer('light', n)[3] < 1 for n in stack) else ''))
    rows.append(cells)

if '--md' in sys.argv:
    print('| Pair (foreground on background) | Light | Dark | Target |'); print('|---|---|---|---|')
    for r in rows: print('| ' + ' | '.join(r) + ' |')
else:
    print(f'glass alpha {GLASS_A}')
    for r in rows: print(f'{r[0]:<66} light {r[1]:<14} dark {r[2]:<14} target {r[3]}')
print(('ALL PASS' if ok else 'SOME FAIL'), file=sys.stderr)
sys.exit(0 if ok else 1)
