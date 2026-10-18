# ANAL-205 (backlog B4): circular icons, round icons, no wallpaper dim, Googlebook's wallpaper colour thresholds (2026-10-17)

The write-up is in `docs/googlebook-ui.md` §2.4. The values are listed in `docs/aosp-desktop.md` (framework RRO table and product properties).

**Builds:** `anybook_cf_x86_64_pc-cp2a-userdebug`, before and after, plus `anybook_g14_x86_64-cp2a-userdebug` after, all three in one hold of the lane lock (`build/build-results.txt`).
- **Before** is base `c861cf4`.
- **After** is `fdd811f`. Its build log says `fdd811f-dirty` because a doc was uncommitted at the time; `device/anybook` was exactly `fdd811f`. After a rebase onto #71's newer docs commit, it is `bab6a3a`, with the same `device/` tree.
- **Cuttlefish:** the AMD Radeon 610M (`CF_GPU=amd`, `gfxstream_guest_angle`), 1920x1080 at 160 dpi, VM `anybook-cf-b4`. Each build was booted from a reflink snapshot of its own images.

## Results

| Check | Before (AOSP values) | After (B4) | File |
|---|---|---|---|
| `cmd overlay lookup` `config_icon_mask` | rounded square, 8-unit corners | `M50,0 A50,50 0 1,1 50,100 A50,50 0 1,1 50,0 Z` | `*/shape-state.txt` |
| `config_useRoundIcon` / `config_wallpaperDimAmount` | false / 0.05 | true / 0.0 | same |
| `persist.wallpapercolors.threshold` / `max_dark_area` | unset (code defaults 70 / 5) | 55 / 12 | same |
| In the images (aapt2 on the overlay APK, `/product/etc/build.prop`) | — | the CF and G14 products both carry all five | `build/*/` |
| All apps, taskbar | rounded squares | circles | `compare-all-apps.png`, `compare-taskbar.png`, `*/all-apps.png` |
| Settings homepage and Settings → Apps → All apps | rounded squares | circles. Legacy (non-adaptive) icons such as Calendar and Contacts are unmasked in both | `compare-settings.png`, `*/settings-apps.png` |
| Flat grey wallpaper 180 / 206 as shown on screen (`scripts/ui/wallpaper-dim-check.sh`) | 171 / 195 (×0.95: AOSP's 5 % default dim) | 180 / 206 (no dim) | `*/wallpaper-dim.txt`, `*/screen-grey-180-quarter.png` |
| `WallpaperColors.fromBitmap()` dark-text hint on the device (`scripts/ui/wallpaper-hints.sh`) | grey L 0.62: no; white with 8 % dark pixels: no | both: **yes**. White with 15 % dark pixels: no in both; white: yes in both; black: dark theme in both | `*/wallpaper-hints.txt` |
| Launcher3 shape options (the picker's data) | Circle marked selected, but the launcher drew the rounded square | Circle marked selected, and drawn | `*/shape-state.txt` |
| Picker UI (Wallpaper & style → Icons → Shape) | — | five shapes, Circle selected | `after/picker-shape.png` |
| User picks Square (Launcher3 `grid_control` provider, as the picker does) | the taskbar follows | the taskbar follows (square), and Circle returns when the pick is cleared | `compare-taskbar.png`, `*/pick-square.txt` |
| Taskbar all-apps panel after a pick | keeps the system mask (pixel diff 0) | keeps the system mask, also after a Launcher restart | not caused by B4 (AOSP Launcher3); see `docs/googlebook-ui.md` §2.4 |
| Crashes | none from the checks* | crash buffer empty after every step; 0 `FATAL EXCEPTION` or `ANR` in `logcat -b all` | `after/crash-buffer-final.txt`, `*/logcat-all.txt.gz` |

\* `before/shape-state.txt` and `before/pick-square.txt` show a `DeadSystemException` at 01:01:22. It came from the first version of the dim check, which restarts the framework with `stop`/`start`, and it happened before those captures. The script has cleared the crash buffer after `stop` since then, and its later runs, in both builds, logged nothing.

## Not covered

- **The G14.** The checks are posted for ANAL-192's stick checklist.
- **The lock screen.** It is off by default on our desktop.
- **A real photo wallpaper.** The stock wallpaper is dark, so it has the dark-theme hint and was never dimmed. The grey test images isolate the dim instead.

## Reproduce

```bash
# Under the lane lock: build, then snapshot the CF images by reflink (top-level files of
# out/target/product/anybook_vsoc_x86_64 -> SNAP/target/product/anybook_vsoc_x86_64, and
# out/host/linux-x86/cvd-host_package.tar.gz -> SNAP/host/linux-x86/). Boot a snapshot after releasing the lane:
export CF_OUT=SNAP CF_STAGE=~/anybook/aosp/cf/b4 CF_NAME=anybook-cf-b4 CF_ADB_PORT=16534 \
  CF_WEBRTC_PORT=11534 CF_DEVICE=anybook_vsoc_x86_64 CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_ARGS=--vsock_guest_cid=134
scripts/cf-boot.sh up
export ANDROID_ADB_SERVER_PORT=5134; adb connect 127.0.0.1:16534
SHAPE_PICK=square scripts/ui/shape-shots.sh 127.0.0.1:16534 OUT
scripts/ui/wallpaper-hints.sh 127.0.0.1:16534 OUT/wallpaper-hints.txt
scripts/ui/wallpaper-dim-check.sh 127.0.0.1:16534 OUT/dim 180 206     # restarts the framework twice
scripts/cf-boot.sh down
```
