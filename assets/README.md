# OpenBook brand and README art

| File | Use |
|---|---|
| `brand/openbook-mark.svg` | The mark: two pages opening from a spine, and a spark. Vector, works on light and dark backgrounds. |
| `brand/openbook-icon-512.png` | App/launcher icon (512×512, transparent corners). |
| `readme/hero-{light,dark}.jpg` | README banner. GitHub picks the variant with `<picture>` and `prefers-color-scheme`. |
| `readme/showcase-{light,dark}.jpg` | Installer design showcase (design renders, sample data). |
| `readme/desktop-{light,dark}.jpg` | A **real** screenshot of our Android 17 desktop build (2026-10-16, Cuttlefish on a Radeon 610M), framed. |
| `readme/social-preview.jpg` | 1280×640 repository card. Upload it under GitHub **Settings → General → Social preview**. |
| `readme/icons/*.png` | Feature icons (Material Symbols Rounded, Apache-2.0) in the brand gradient. |

**Palette** (Material 3, from `docs/installer-design/`): primary `#4355B9`, pages `#7E8CFF → #4355B9` and `#D08BFF → #7A4CE0`, spark `#FFB38A → #FF7A9C`, ink `#1B1B21`, dark surface `#121318`.
**Type:** Roboto Flex (OFL-1.1).

**Regenerate:** `scripts/brand/render-readme-assets.sh` renders everything from `src/readme-art.html` with headless Chromium and ImageMagick. Fonts are fetched at render time into the host data dir and are never committed.

**Honesty rule:** label design renders as designs. Only screenshots captured from our builds may be presented as "running".
