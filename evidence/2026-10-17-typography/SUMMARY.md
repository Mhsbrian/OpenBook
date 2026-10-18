# ANAL-202 (backlog B1): Google Sans typography in the desktop products (2026-10-17/18)

The write-up is in `docs/googlebook-ui.md` §2.1 and §3.1. The framework values are listed in `docs/aosp-desktop.md`, and the font files' provenance is in `device/anybook/common/desktop/fonts/README.md`.

**Builds** (`build/build-results.txt`; all under the AOSP lane lock):
- **Base:** `c861cf4` (ANAL-201's branch, no fonts).
- **Fonts:** `c91ca38` (this branch before it merged `main`). The build logs say `-dirty` because a doc was uncommitted; `device/anybook` was exactly `c91ca38`.
- **Products:** `anybook_cf_x86_64_pc-cp2a-userdebug` and `anybook_g14_x86_64-cp2a-userdebug`, base and fonts, so four builds. The fonts builds exited 0 for both products.
- **Merged tree:** `d5b12fa`, this branch after merging `main` (B2, B4 and B5 in). Both products built again (`m exit 0`), and the Cuttlefish image was booted once more (`merged/`).
- **Cuttlefish:** AMD Radeon 610M (`CF_GPU=amd`, `gfxstream_guest_angle`), 1920x1080 at 160 dpi, VM `anybook-cf-b1`. Each build booted from a reflink snapshot of its own images.

## Results

| Check | Base | Fonts | File |
|---|---|---|---|
| Both products build | yes | **yes** (`m exit 0`, cf and G14) | `build/build-results.txt` |
| `/product/fonts` | absent | the three OFL files; on the device their sha256 matches google/fonts `47d54ca1` | `cf/fonts/font-state.txt`, `cf/fonts/ui-state.txt` |
| `/product/etc/fonts_customization.xml` | absent | 40 families; the device's font manager (`dumpsys font`) lists all 40 as named families | same |
| `cmd overlay lookup` for `config_headlineFontFamily`, `…Medium`, `config_bodyFontFamily`, `…Medium` | empty, `sans-serif-medium`, `sans-serif`, `sans-serif-medium` | `google-sans`, `google-sans-medium`, `google-sans-text`, `google-sans-text-medium` | `cf/*/font-state.txt` |
| Settings, window captions, Quick Settings, notifications, all apps, Files | Roboto | **Google Sans** | `cf/cmp-*.png` (half size), `cf/cmp-*-crop.png` (full size) |
| Desktop (`scripts/desktop-capture.sh`) | Settings and Files as freeform windows, taskbar present | **the same**: 8 freeform activity records, taskbar present, caption layers in SurfaceFlinger | `cf/*/windowing-summary.txt`, `cf/*/taskbar.txt`, `cf/*/surfaceflinger-summary.txt`, `cf/fonts-desktop-windows.png` |
| Crash buffer | empty in all 3 runs | **empty in all 3 runs** | `cf/runs.txt`, `cf/*/logcat-crash.txt` |
| SELinux denials | 3 kinds (Cuttlefish's `gceservice`, `bootanim`, `init` debugfs). One run also had 2 `su` (adb shell) kinds | **the same 3 kinds in every run; none new** | `cf/runs.txt`, `cf/*/avc-denials.txt` |
| Boot to `sys.boot_completed` | 34–40 s | 32–40 s | `cf/runs.txt` |
| Image size | — | **product.img +9.24 MiB** (cf +9,691,136 B; G14 +9,678,848 B). super.img grows by the same. system, system_ext and vendor unchanged. The files total 13.98 MB; EROFS compresses them | `build/image-sizes.txt` |
| Notices | — | `/product/etc/NOTICE.xml.gz` (both products) maps each font to its family's OFL text, with its own copyright line, and `fonts_customization.xml` to Apache-2.0 | `build/notice-and-drift-check.txt` |
| Drift check | — | the build runs `--check` on the committed XML before installing it (sbox command recorded). The built tool exits 0 on it and 1, with a diff, when one value is changed | same |

### Settings scroll (`scripts/cf-gfx-bench.sh`, 5 rounds × 20 swipe pairs per run)

Three alternating pairs (base, fonts, base, fonts, base, fonts), because the shared host's load ranged from 49 to 239 (32 threads) while sibling builds ran:

| Run | Build | Frames | Janky | Janky % | Median p90 (ms) | Host load |
|---|---|---|---|---|---|---|
| r1 | base | 3,687 | 176 | 4.77 | 25 | 90–93 |
| r1 | fonts | 3,455 | 58 | 1.68 | 14 | 84–101 |
| r2-1 | base | 3,532 | 111 | 3.14 | 20 | 112–124 |
| r2-2 | fonts | 3,846 | 67 | 1.74 | 19 | 150–165 |
| r2-3 | base | 3,811 | 189 | 4.96 | 21 | 217–239 |
| r2-4 | fonts | 3,460 | 20 | 0.58 | 12 | 49–63 |
| **all** | **base** | 11,030 | 476 | **4.32** | **20** | |
| **all** | **fonts** | 10,761 | 145 | **1.35** | **15** | |

- **No regression.** The fonts build had fewer janky frames in every pair, including r2-2, where its host load was higher than the base run's.
- **This is not a pure text-rendering cost.** Google Sans has taller line metrics than Roboto, so Settings' rows are about a quarter taller: roughly 75 → 94 px at 160 dpi (`cf/cmp-settings.png`). The same swipe then brings fewer new rows on screen. **HYPOTHESIS:** that, not the font, explains the lower jank. Per-glyph cost wasn't isolated.
- HWUI's GPU time per frame was 1 ms (p50 and p90) in every round of both builds.

### The merged tree (`merged/`)

`d5b12fa` in Cuttlefish, on a quiet host (load 9):
- **Fonts:** the same: the fonts' sha256 on the device match upstream, all 40 families load, and the four values resolve.
- **Desktop:** two freeform windows with captions, and the taskbar. B4's circular icons and B5's taskbar without the search bar show alongside Google Sans (`merged/desktop-windows.png`).
- **Health:** crash buffer empty; the same three SELinux denial kinds as before.
- **Settings scroll, 2 rounds:** 0 janky frames, p90 5–6 ms. That is a quiet-host data point, not a comparison.
- **Size:** `product.img` is 302,100,480 B (cf) and 301,666,304 B (G14).

After this, `main` gained #79 (B3, the desktop flag set v2) and was merged again. #79 changes only `release/` aconfig files, none of B1's, and that combination was not rebuilt.

## Not covered

- **The G14.** The check is posted on ANAL-192 for the next stick's checklist.
- **Non-Latin text.** Only English UI text was looked at.

## Reproduce

```bash
# Under the lane lock: build each tree, then snapshot the CF images by reflink (top-level files of
# out/target/product/anybook_vsoc_x86_64 -> SNAP/target/product/anybook_vsoc_x86_64, and
# out/host/linux-x86/cvd-host_package.tar.gz -> SNAP/host/linux-x86/). Boot a snapshot after releasing the lane:
export CF_OUT=SNAP CF_STAGE=~/anybook/aosp/cf/b1 CF_NAME=anybook-cf-b1 CF_ADB_PORT=16531 CF_WEBRTC_PORT=11531 \
  CF_DEVICE=anybook_vsoc_x86_64 CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_LOGS=OUT/cf-boot
scripts/cf-boot.sh up && scripts/cf-boot.sh wait
export ANDROID_ADB_SERVER_PORT=5131; adb connect 127.0.0.1:16531; adb root
scripts/ui/ui-shots.sh 127.0.0.1:16531 OUT/shots
for k in config_headlineFontFamily config_headlineFontFamilyMedium config_bodyFontFamily config_bodyFontFamilyMedium; do
  adb shell cmd overlay lookup android android:string/$k; done
adb shell dumpsys font | grep -oE 'Named Family \((google-sans[a-z-]*|variable-[a-z-]*)\)' | sort -u
scripts/desktop-capture.sh 127.0.0.1:16531 OUT/desktop
BENCH_ROUNDS=5 scripts/cf-gfx-bench.sh 127.0.0.1:16531 OUT/bench LABEL
adb logcat -d -b crash; adb logcat -d -b all | grep 'avc: *denied'
scripts/cf-boot.sh down
```
