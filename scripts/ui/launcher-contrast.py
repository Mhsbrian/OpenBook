#!/usr/bin/env python3
"""Check WCAG contrast for every colour pair the launcher design draws, in every state, in both themes (ANAL-364).

Reads the tokens from docs/launcher-design/index.html so docs/launcher-design.md §6.4 can't drift from the prototype.

Each pair names its whole stack, back to front: the taskbar (`--bar-a`) or a panel, menu or chip (`--glass-a`) is
translucent, the field is paper on the glass, and a state layer (hover, front, top hit, pressed) is `onSurface` at a
given alpha on top. The stack is composited over black and over white and the lower ratio counts. That bounds every
real backdrop: the blur averages what is behind and never makes it darker than black or lighter than white
(scripts/quire/contrast-check.py's method).

Targets: 4.5:1 for text, 3:1 for marks, icons and focus rings that carry meaning (WCAG 2.2, 1.4.3 and 1.4.11).
A two-colour focus ring that sits over arbitrary content (Overview's tiles) is checked as WCAG technique C40: its two
colours must be at least 9:1 apart, which leaves one of them at 3:1 or more against any colour behind it.

Decorative marks (the taskbar's divider, menu dividers, non-front window thumbnails) are listed with no target.

usage: launcher-contrast.py [--md] [--html PATH]      exit 1 if any pair misses its target
"""
import pathlib, re, sys

HTML = pathlib.Path(__file__).resolve().parents[2] / 'docs/launcher-design/index.html'
if '--html' in sys.argv: HTML = pathlib.Path(sys.argv[sys.argv.index('--html') + 1])
css = HTML.read_text()

def block(selector):
    m = re.search(re.escape(selector) + r'\s*\{(.*?)\n\}', css, re.S)
    return dict(re.findall(r'--([\w-]+):\s*([^;]+);', m.group(1)))

ROOT = block(':root')
T = {'light': block(':root, [data-theme="light"]'), 'dark': block('[data-theme="dark"]')}

def rgb(c, tk):
    c = c.strip()
    while c.startswith('var(--'): c = tk[c[6:-1]].strip()
    if c.startswith('#'): return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
    return tuple(float(v) for v in c.split(','))     # "251, 248, 254"

def over(fg, a, bg): return tuple(f * a + b * (1 - a) for f, b in zip(fg, bg))

def lum(c):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

def stack(layers, tk, back):
    """Composite a stack, back to front, over a backdrop colour."""
    c = back
    for l in layers:
        if l == 'bar': c = over(rgb(tk['tint'], tk), float(ROOT['bar-a']), c)
        elif l == 'glass': c = over(rgb(tk['tint'], tk), float(ROOT['glass-a']), c)
        elif l == 'field':   # --field is rgba(r, g, b, a): paper on the glass
            r, g, b, a = (float(v) for v in re.match(r'rgba\(([^)]*)\)', tk['field']).group(1).split(','))
            c = over((r, g, b), a, c)
        elif isinstance(l, float): c = over(rgb(tk['state'], tk), l, c)          # a state layer, onSurface at alpha
        else: c = rgb(tk[l], tk)                                                  # an opaque role
    return c

H, F, T10, P = .08, .06, .10, .12     # hover, front tile, top hit, pressed (index.html: .tb-app, .cell, .row)
TEXT, MARK = 4.5, 3.0
# (area, pair, foreground, stack, target)   target None = decorative
PAIRS = [
    # §2 taskbar. Each state line lies on the bar 1 dp under its 48 dp target, so no state layer is ever under it (§2.3)
    ('taskbar', 'Running line and dot', 'on-surface-variant', ['bar'], MARK),
    ('taskbar', 'Front line and dot', 'primary', ['bar'], MARK),
    ('taskbar', 'Minimized hollow line', 'on-surface-variant', ['bar'], MARK),
    ('taskbar', 'Focus ring (targets and the pill)', 'primary', ['bar'], MARK),
    ('taskbar', 'Pill glyph', 'on-secondary-container', ['secondary-container'], MARK),
    ('taskbar', 'Pill glyph, hovered', 'on-secondary-container', ['secondary-container', H], MARK),
    ('taskbar', 'Pill glyph, open', 'on-primary', ['primary'], MARK),
    ('taskbar', 'Pill glyph, open and hovered', 'on-primary', ['primary', H], MARK),
    ('taskbar', 'Pill\'s edge on the bar (the glyph identifies it)', 'secondary-container', ['bar'], None),
    ('taskbar', 'Divider', 'outline-variant', ['bar'], None),
    ('taskbar', 'Tooltip', 'inverse-on-surface', ['inverse-surface'], TEXT),
    # §3 All Apps
    ('All Apps', 'App label', 'ink', ['glass'], TEXT),
    ('All Apps', 'App label, hovered', 'ink', ['glass', H], TEXT),
    ('All Apps', 'App label, top hit', 'ink', ['glass', T10], TEXT),
    ('All Apps', 'Cell focus ring', 'primary', ['glass'], MARK),
    ('All Apps', 'Cell focus ring, top hit', 'primary', ['glass', T10], MARK),
    ('All Apps', 'Placeholder', 'ink-soft', ['glass', 'field'], TEXT),
    ('All Apps', 'Search text and matches', 'ink', ['glass', 'field'], TEXT),
    ('All Apps', 'Search and clear icons', 'on-surface-variant', ['glass', 'field'], MARK),
    ('All Apps', 'Caret', 'primary', ['glass', 'field'], MARK),
    ('All Apps', 'Field focus ring, inside', 'primary', ['glass', 'field'], MARK),
    ('All Apps', 'Field focus ring, outside', 'primary', ['glass'], MARK),
    ('All Apps', 'Scroll bar', 'on-surface-variant', ['glass'], MARK),
    ('All Apps', 'No results', 'ink-soft', ['glass'], TEXT),
    # §4 menus
    ('menus', 'Label', 'ink', ['glass'], TEXT),
    ('menus', 'Label, hovered', 'ink', ['glass', H], TEXT),
    ('menus', 'Header (app name)', 'ink', ['glass'], TEXT),
    ('menus', 'Shortcut hint', 'ink-soft', ['glass'], TEXT),
    ('menus', 'Shortcut hint, hovered (turns to ink)', 'ink', ['glass', H], TEXT),
    ('menus', 'Icon', 'on-surface-variant', ['glass'], MARK),
    ('menus', 'Icon, hovered', 'on-surface-variant', ['glass', H], MARK),
    ('menus', 'Front window outline', 'primary', ['glass'], MARK),
    ('menus', 'Front window outline, hovered', 'primary', ['glass', H], MARK),
    ('menus', 'Row focus ring', 'primary', ['glass'], MARK),
    ('menus', 'Other windows\' outlines', 'outline-variant', ['glass'], None),
    ('menus', 'Divider', 'outline-variant', ['glass'], None),
    # §5 Overview: labels and Clear all sit on glass chips
    ('Overview', 'Tile label', 'ink', ['glass'], TEXT),
    ('Overview', 'Desk\'s apps (soft ink)', 'ink-soft', ['glass'], TEXT),
    ('Overview', 'Desk glyph', 'on-surface-variant', ['glass'], MARK),
    ('Overview', 'Clear all', 'ink', ['glass'], TEXT),
]
# two-colour rings over arbitrary content: (area, pair, colour a, colour b), checked as C40 (>= 9:1 between them)
C40 = [('Overview', 'Tile focus ring (two colours)', 'on-primary-container', 'surface-lowest')]

rows, fail = [], False
for theme in T:
    tk = {**T['light'], **T[theme]}
    for area, name, fg, layers, target in PAIRS:
        worst = min(ratio(rgb(tk[fg], tk), stack(layers, tk, back)) for back in ((0, 0, 0), (255, 255, 255)))
        ok = target is None or worst >= target
        fail |= not ok
        on = ' + '.join(f'{int(l * 100)} %' if isinstance(l, float) else f'`{l}`' if l not in ('bar', 'glass', 'field') else l
                        for l in layers)
        rows.append((theme, area, name, f'`{fg}`', on, worst, target, ok))
    for area, name, a, b in C40:
        r = ratio(rgb(tk[a], tk), rgb(tk[b], tk))
        ok = r >= 9.0
        fail |= not ok
        rows.append((theme, area, name, f'`{a}`', f'`{b}` (C40)', r, 9.0, ok))

if '--md' in sys.argv:
    print('| Theme | Area | Pair | Foreground | On (back to front) | Worst | Target | |')
    print('|---|---|---|---|---|---|---|---|')
    for th, ar, n, fg, on, r, t, ok in rows:
        print(f'| {th} | {ar} | {n} | {fg} | {on} | {r:.2f}:1 | {f"{t:g}:1" if t else "decorative"} | {"pass" if ok else "**FAIL**"} |')
else:
    for th, ar, n, fg, on, r, t, ok in rows:
        print(f'{th:5} {"PASS" if ok else "FAIL"} {r:5.2f}:1 (target {f"{t:g}" if t else "-"}) {ar}: {n}: {fg} on {on}')
    print(f'{sum(1 for r in rows if r[6])} checked pairs, {sum(1 for r in rows if r[6] and not r[7])} failing; '
          f'{sum(1 for r in rows if not r[6])} decorative', file=sys.stderr)
sys.exit(1 if fail else 0)
