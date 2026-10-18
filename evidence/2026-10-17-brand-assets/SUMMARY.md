# ANAL-207 (B6): OpenBook's own wallpapers, boot animation, sounds and pointer

Run 2026-10-18 (UTC) on the shared host (Ryzen 9 7950X).
- **Builds:** `anybook_cf_x86_64_pc-cp2a-userdebug` (`droid`) and `anybook_g14_x86_64-cp2a-userdebug` (`productimage`, the partition B6 changes), in one hold of the lane lock, from `ea262d8` (`build/build-results.txt`).
- **VM:** `anybook-cf-b6`, Cuttlefish on the Radeon 610M (`CF_GPU=amd`, `gfxstream_guest_angle`), 1920×1080 at 160 dpi, booted from a reflink snapshot of that build.
- **G14:** not tested here. The checks are posted for ANAL-192's next stick.

All assets are ours: drawn or synthesised by `scripts/brand/` from the brand palette and mark (`assets/README.md`, licence CC-BY-4.0 in `assets/LICENSE`). **`contact-sheet.jpg` shows every asset for review.**

## Results

| Check | Result | Files |
|---|---|---|
| Generators reproduce `assets/` from a clean checkout | `render-brand-assets.sh --check` in a fresh clone: **OK**, every wallpaper, the Monet file, 41 pointer files, 115 boot-animation entries, 11 previews and 8 sounds | `check/render-check.log` |
| Installed in **both products** | CF and G14: `/product/media/bootanimation.zip`, 8 `OpenBook_*.ogg` in `/product/media/audio/*`, `ro.config.{ringtone,notification_sound,alarm_alert}` in `product/etc/build.prop` (AOSP's optional values dropped by the build), `OpenBookPointerOverlay`, `OpenBookSoundsSettingsProviderOverlay`, `default_wallpaper` (nodpi, sw600dp, sw720dp) in `AnyBookDesktopFrameworkOverlay`, 8 wallpapers + 8 thumbnails + `xml/wallpapers.xml` in `AnyBookDesktopPartnerCustomization` | `build/cf/`, `build/g14/` |
| **Boot animation** during boot | Played from `/product/media/bootanimation.zip`: 12.1 s, 28 screencaps; logcat shows part1 looping, then part2 | `boot/boot-frames.jpg`, `boot/boot-frame-crop.png`, `boot/boot-screenrecord.mp4`, `boot/bootanimation-logcat.txt` |
| Boot animation replayed on the desktop | `start bootanim`, then `service.bootanim.exit=1`: all three parts, the pages unfolding, the spark breathing, the fade | `boot/replay.mp4`, `boot/replay-frames.jpg` |
| **Default wallpaper** | `cmd overlay lookup` resolves `android:drawable/default_wallpaper` to our `default_wallpaper.jpg`. A fresh `/data` shows Folio light, in the light and the dark theme | `desktop/desktop-light.png`, `desktop/desktop-dark.png`, `overlays.txt` |
| **Wallpaper set in Wallpaper & style** | Home page carousel "1 of 9 … 4 of 9"; More wallpapers → Collections lists **OpenBook** (and On-device wallpapers); OpenBook shows Folio, Bloom, Strata, Tide, each light and dark | `picker/picker-home.png`, `picker/picker-collections.png`, `picker/picker-openbook.png` |
| **Dynamic colour (Monet)** from each wallpaper | Each of the 8 gives its own seed on the device (SystemUI `mMainWallpaperColor`), with TonalSpot (`mThemeStyle=1`). Families: indigo (Folio light), violet (Folio dark, Strata), rose (Bloom), blue (Tide dark), teal (Tide light). The device's primary colour matches `monet.py`'s prediction within 3 RGB units for 7 of 8, light and dark; Bloom light is 7 off (`#894D5D` against `#874D64`). Secondary, tertiary and container roles are within 14. Seed hues agree within 0–7.4° | `desktop/monet-device.tsv`, `desktop/monet-compare.tsv`, `desktop/wallpaper-*.jpg`, `../../assets/wallpapers/monet.json` |
| **Pointer theme**, rendered by the framework | `BrandProbe pointers` runs `PointerIcon.getLoadedSystemIcon` with the theme `PointerIconCache` builds, for 21 types × 6 fills × 3 strokes = 378 icons. Our 20 shapes in every style; AOSP's wait spinner unchanged and still coloured | `pointer/pointers-device.png`, `pointer/renders/`, `pointer/pointers.tsv` |
| Pointer on screen | A virtual USB mouse (`uinput`): `dumpsys input` shows a `MouseCursorController` with `resolvedPointerType: 1000` (arrow) and `resourcesLoaded: true`. In this build `skipScreenshot` is false, so screencap does show the pointer: our arrow with Android's drop shadow | `pointer/dumpsys-input-pointer.txt`, `pointer/pointer-on-screen-crop.png`, `pointer/screen-with-mouse.jpg` |
| **Sounds** | `settings`: ringtone → "Open Pages", notification → "Spark", alarm → "First Light" (MediaProvider URIs). Lock, unlock, trusted, low-battery and charging paths → `/product/media/audio/ui/OpenBook_*.ogg`. MediaProvider indexed all 8 with their durations (5931, 1937, 17198 ms …). `sound_effects_enabled=0` (ANAL-206) | `sounds/sounds.txt` |
| All scripted checks | 8 PASS, 0 FAIL | `device-checks.log` |

## The pointer overlay: a first attempt that failed (`pretest/`)

Before the build, the overlays were side-loaded onto a VM from a base snapshot (`b7-base`).

- **First attempt.** We compiled `OpenBookPointerOverlay` as resource package `android`, so its XML could name the private attributes `pointerIconVectorFill` / `pointerIconVectorStroke`. aapt2 forbids `?android:attr/<private>` from any other package.
  - It linked, idmap2 mapped all 20 vectors, and the overlay was enabled.
  - **Android ignored it.** The framework still returned AOSP's path data (`pretest/resinfo-package-android-overlay.txt`, `pointers-package-android-overlay.png`).
  - Why: aapt2 forces package `android` to ID 0x01. Overlays load as dynamic packages, and `DynamicRefTable` treats 0x01 IDs as the framework's own, so the overlay's entries are looked up in framework-res and never found.
- **What we ship.** The overlay also replaces AOSP's nine `PointerIconVectorStyleFill*` / `Stroke*` styles. aapt2 accepts private attributes as style item names (`*android:…`).
  - Each style keeps AOSP's items, and adds the same colour under the overlay's own `openbookPointerFill` / `openbookPointerStroke`, which our vectors use.
  - On the VM the framework returned our path data and drew our shapes in every style (`pretest/pointers-style-overlay.png`). The real build confirmed it (above).
- `scripts/brand/pointers.py --check-aosp` keeps those nine colours and the 20 hotspots equal to AOSP's: 9/9 and 20/20.

## Not covered

- **The G14.** Not tested here; the checks are on ANAL-192's checklist. The product image only shows the files are installed, which is not the same as seeing them work on the laptop.
- **Listening.** The sounds were checked by loudness (EBU R128), spectrograms and decoding (MediaProvider durations), not by ear. The owner should listen; the files are in `assets/sounds/`.
- **Settings UI.** We didn't capture the Mouse pointer colour picker. It reads the private attributes, which our styles keep.
- **The lock screen and dock sounds.** The lock screen is off by default on our desktop, and dock sounds stay AOSP's and off.
- **What isn't replaced:** the wait spinner, touch spots, handwriting pointer, keyboard clicks and camera sounds (AOSP's).

## Reproduce

```bash
scripts/brand/render-brand-assets.sh --check          # from a clean checkout: generators == assets/
# Under the lane lock: build CF (droid) and G14 (productimage), then snapshot the CF images (as ANAL-205 does):
flock ~/anybook/aosp/.lane.lock bash -c 'scripts/aosp-docker.sh /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug && <snapshot to SNAP> &&
  scripts/aosp-docker.sh /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug productimage'
export CF_OUT=SNAP CF_STAGE=~/anybook/aosp/cf/b6 CF_NAME=anybook-cf-b6 CF_ADB_PORT=16536 CF_WEBRTC_PORT=11536 \
  CF_DEVICE=anybook_vsoc_x86_64 CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_ARGS=--vsock_guest_cid=136
export ANDROID_ADB_SERVER_PORT=5136
scripts/cf-boot.sh up & scripts/brand/bootanim-capture.sh 127.0.0.1:16536 OUT/boot    # during and after boot
scripts/brand/device-checks.sh 127.0.0.1:16536 OUT/checks                             # PASS/FAIL in device-checks.log
adb -s 127.0.0.1:16536 shell uinput /data/local/tmp/virtual-mouse.json & adb -s 127.0.0.1:16536 shell dumpsys input
scripts/brand/contact-sheet.py contact-sheet.jpg --device-pointers OUT/checks/pointers --device-monet OUT/checks/monet-device.tsv
scripts/cf-boot.sh down
```
