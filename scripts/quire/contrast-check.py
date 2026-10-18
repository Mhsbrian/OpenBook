#!/usr/bin/env python3
"""Check WCAG contrast for the colour pairs the Quire note uses, in both themes (ANAL-215).

Reads the tokens from docs/quire-design/index.html so the table in docs/quire-design.md §4 cannot drift from the
prototype. Translucent surfaces (the note's background) are checked at their worst backdrop: dark text over the note
composited on black, light text over the note composited on white.

usage: contrast-check.py [--md]      exit 1 if any pair misses its target
"""
import re, sys

HTML = __import__('pathlib').Path(__file__).resolve().parents[2] / 'docs/quire-design/index.html'
css = HTML.read_text()

def block(selector):
    m = re.search(re.escape(selector) + r'\s*\{(.*?)\n\}', css, re.S)
    return dict(re.findall(r'--([\w-]+):\s*([^;]+);', m.group(1)))

T = {'light': block(':root, [data-theme="light"]'), 'dark': block('[data-theme="dark"]')}

def rgb(c):
    c = c.strip()
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
# (label, foreground token, background token, target ratio, note)
PAIRS = [
    ('Answer text on the note', 'on-surface', 'note-bg', 4.5, 'worst backdrop'),
    ('Secondary text on the note', 'on-surface-variant', 'note-bg', 4.5, 'worst backdrop'),
    ('Secondary text on a card', 'on-surface-variant', 'surface-container', 4.5, ''),
    ('Secondary text on a card (dark uses surface-high)', 'on-surface-variant', 'surface-high', 4.5, ''),
    ('Filled button: Allow', 'on-primary', 'primary', 4.5, ''),
    ('Tonal button: Allow for this task', 'on-secondary-container', 'secondary-container', 4.5, ''),
    ('Text button: Don’t allow', 'primary', 'note-bg', 4.5, 'worst backdrop'),
    ('New value pill', 'on-primary-container', 'primary-container', 4.5, ''),
    ('Mic indicator', 'on-success-container', 'success-container', 4.5, ''),
    ('Automation chip (Using Settings)', 'on-tertiary-container', 'tertiary-container', 4.5, ''),
    ('Halo label, Jump pill', 'inverse-on-surface', 'inverse-surface', 4.5, ''),
    ('Danger text: Stop', 'error', 'note-bg', 4.5, 'worst backdrop'),
    ('Intake chip', 'on-secondary-container', 'secondary-container', 4.5, ''),
    ('Done check (icon, non-text)', 'success', 'note-bg', 3.0, 'worst backdrop'),
    ('Focus ring (non-text)', 'primary', 'note-bg', 3.0, 'worst backdrop'),
    ('Pending-step outline (non-text)', 'on-surface-variant', 'note-bg', 3.0, 'worst backdrop'),
    ('Field outline on focus (non-text)', 'primary', 'surface-container', 3.0, ''),
]

def resolve(theme, fg_t, bg_t):
    tk = T[theme]; fg = rgb(tk[fg_t]); bg = rgb(tk[bg_t])
    if bg[3] < 1:  # translucent: worst case backdrop for this text colour
        bg = over(bg, BLACK if lum(fg) < 0.5 else WHITE)
    return fg, bg

rows, ok = [], True
for label, fg_t, bg_t, target, note in PAIRS:
    cells = [label]
    for theme in ('light', 'dark'):
        fg, bg = resolve(theme, fg_t, bg_t); r = ratio(fg, bg); passed = r >= target; ok &= passed
        cells.append(f'{r:.1f}:1 {"pass" if passed else "FAIL"}')
    cells.append(f'{target:.1f}:1' + (f' ({note})' if note else ''))
    rows.append(cells)

if '--md' in sys.argv:
    print('| Pair (foreground on background) | Light | Dark | Target |'); print('|---|---|---|---|')
    for r in rows: print('| ' + ' | '.join(r) + ' |')
else:
    for r in rows: print(f'{r[0]:<48} light {r[1]:<14} dark {r[2]:<14} target {r[3]}')
print(('ALL PASS' if ok else 'SOME FAIL'), file=sys.stderr)
sys.exit(0 if ok else 1)
