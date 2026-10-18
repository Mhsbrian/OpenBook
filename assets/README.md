# OpenBook brand, README art and system assets

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

## System assets (ANAL-207)

OpenBook's own wallpapers, boot animation, sounds and pointer, in place of AOSP's stock ones. They are drawn or synthesised by `scripts/brand/` from the palette and mark above. Nothing is traced, sampled or downloaded. Licence: **CC-BY-4.0** (`LICENSE`); the generators are Apache-2.0.

| Directory | What | Installed as |
|---|---|---|
| `wallpapers/2880x1800/`, `wallpapers/1920x1080/` | Four designs, each light and dark: **Folio** (pages fanning out of the spine; the default is Folio light), **Bloom** (the spark's warm light), **Strata** (page edges in slow waves), **Tide** (teal light and a ribbon). JPEG, q92, 4:4:4 | The default: `AnyBookDesktopFrameworkOverlay` `drawable-{,sw600dp-,sw720dp-}nodpi/default_wallpaper.jpg`. The set: an "OpenBook" category in Wallpaper & style, from the partner customization package (`res/xml/wallpapers.xml`) |
| `wallpapers/thumbs/` | 480×300 thumbnails for the picker | Same package |
| `wallpapers/monet.json` | The dynamic colour Android 17 should derive from each: seeds, TonalSpot role colours (light, dark), tonal palettes. A prediction (`monet.py`); the device's values are in the evidence | — |
| `bootanimation/bootanimation.zip` | 480×480, 30 fps, on `#121318`: `part0` the pages unfold and the spark lights (1.4 s, always played), `part1` the spark breathes (2 s, loops until boot completes), `part2` the mark fades (0.4 s). Stored, not compressed. `preview/` has key frames | `/product/media/bootanimation.zip` |
| `sounds/` | **Open Pages** (ringtone, 5.9 s, loops), **Spark** (notification, 1.9 s), **First Light** (alarm, 17.2 s, grows over eight bars, loops); UI: Lock, Unlock, Trusted, Low battery, Charging started. One glass-mallet voice and one motif (D major 9 rising). Vorbis 48 kHz; ringtone, notification and alarm at −16 LUFS, UI sounds peak around −10 dBFS, like AOSP's. `sounds.json` lists length, loudness, peak and the PCM digest | `/product/media/audio/{ringtones,notifications,alarms,ui}/OpenBook_*.ogg`; `ro.config.{ringtone,notification_sound,alarm_alert}`; UI sound paths in `OpenBookSoundsSettingsProviderOverlay`. AOSP's sounds stay selectable |
| `pointer/drawable/` | 20 pointer shapes on Android 17's vector pointer icons (24 dp, AOSP's hotspots): arrow, hand, text, the resize arrows, zoom, grab… Body in the user's fill colour, outline in the stroke colour, so Settings › Accessibility › Mouse fill, stroke and size keep working. Badges (copy, help, menu, alias) in brand blue, no-drop in red. `preview/` has SVGs | `OpenBookPointerOverlay`: the vectors, plus AOSP's nine pointer colour styles, each with the same colour under the overlay's own `openbookPointerFill` / `openbookPointerStroke` attribute (`values/`; `device/anybook/common/branding/Android.bp` explains why) |

Not replaced: the wait spinner, touch spots, handwriting pointer, keyboard clicks, camera and dock sounds (AOSP's). Click sounds are off by default (ANAL-206).

**Regenerate:** `scripts/brand/render-brand-assets.sh` (all) or `… wallpapers monet bootanimation sounds pointer`. It installs pinned numpy, Pillow and materialyoucolor (`scripts/brand/requirements.txt`) into a venv in the host data dir; sounds need ffmpeg with libvorbis. **Check:** `scripts/brand/render-brand-assets.sh --check` renders into a temporary directory and compares it with what is committed. Images are compared by pixels, sounds by the synthesised PCM, everything else byte for byte.

**Review:** `scripts/brand/contact-sheet.py OUT.jpg` draws every asset on one sheet. On a device, `scripts/brand/device-checks.sh` and `scripts/brand/bootanim-capture.sh` collect the evidence. They use `scripts/brand/probe/` (BrandProbe), which renders the pointers through the framework's own `PointerIcon` code, because screencap does not draw the pointer.
