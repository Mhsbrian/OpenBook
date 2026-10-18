# ANAL-207 (B6): OpenBook's brand assets on the G14, from the owner's `anal192d` session (2026-10-18)

**Source:** the build host's read-only copy of the stick's logs, `~/anybook/installer/g14/stick-20261018T123221Z/` (read by `read-stick-logs.sh` at 12:32Z). The stick itself wasn't touched.
- Stick image: `openbook-live-20261018-anal192d`, from `main` `81578c1` (which includes #81, B6) plus #83.
- Boots read:
  - **A**, the default "OpenBook" boot, 11:00:33–11:59Z, enforcing (`type=1404 … enforcing=1`). This is the first boot of the stick's `/data`, so the wallpaper and sound defaults were applied in it. From the persisted logcat in `live-001/prior/`.
  - **B**, "OpenBook - save logs" (`live-001/`), with its final screenshot.
- The owner has posted no photos or listening notes yet.

Only B6-related lines are copied here: no network names or addresses.

## Results

| Check (B6) | Result on the G14 | File |
|---|---|---|
| **Boot animation** | **Played from our zip in both boots.** Boot A: `/product/media/bootanimation.zip is loaded successfully`. `part0` (the pages unfolding) ran 11:00:51.749–53.155, 1.41 s for 42 frames, so 30 fps as designed. `part1` (the spark breathing) looped 6 times at 2.0 s each. `part2` (the fade) ran 0.40 s. On screen from 18.0 s to 30.6 s after boot started; `bootanim` exited with status 0. Boot B: the same, on screen 12.8–18.9 s | `bootanimation-lines.txt` |
| **Sound defaults** | `ro.config.ringtone=OpenBook_Pages.ogg`, `notification_sound=OpenBook_Spark.ogg`, `alarm_alert=OpenBook_FirstLight.ogg`. On boot A, at 11:01:08, the system opened exactly those three files from `/product/media/audio/` as it set the defaults (RingtoneManager's cache) | `sound-lines.txt` |
| **The unlock sound under enforcing** (ANAL-179's SoundPool probe) | At 11:01:04.35, as the keyguard went away, SystemUI (pid 3492) opened an AudioFlinger track and the HAL's output stream started. It went to standby at 11:01:08.34, AudioFlinger's delay after the last sound. 0 `appdomain_tmpfs` denials and 0 "could not create track". **The G14's pass criterion is met.** The 0.5 s length of `OpenBook_Unlock.ogg` can't be measured here: the HAL's frame count runs until standby. Only QEMU's codec capture times a sound | `sound-lines.txt` |
| **Default wallpaper** | **Not seen.** No screenshot or log of boot A's desktop before the owner changed the wallpaper, 4 minutes after boot | — |
| **The wallpaper set in Wallpaper & style** | The owner opened Wallpaper & style at 11:05:01, previewed a wallpaper, and set one at 11:05:22 (SystemUI: "Wallpaper changed"). Boot B's screenshot shows **Folio dark** at 2880×1800 under the dark theme. That wallpaper exists only in our OpenBook set, so the partner package's wallpapers work on the G14 | `wallpaper-lines.txt`, `screen-final-g14-half.jpg` |
| **Dynamic colour after the change** | SystemUI re-evaluated the theme at 11:05:22. Its Info-level "Failed to parse THEME_CUSTOMIZATION_OVERLAY_PACKAGES … No value for …theme_style" is AOSP's normal path when the setting has no style; it then uses TonalSpot. The palette itself isn't in the logs | `wallpaper-lines.txt` |
| **Wallpaper preview crash** | **Found.** At 11:05:07, 4 s after the first preview opened, `com.android.wallpaper` crashed: a `NullPointerException` in `WallpaperPreviewActivity$requestFullscreen$1.onResult`. The owner's second try, at 11:05:16, worked. This is an AOSP bug: the callback declares a non-null `Void`, but the framework reports success as `onResult(null)`. So it crashes whenever a preview in a desktop window is granted fullscreen. **Reproduced in Cuttlefish** on B6's own build: tap a wallpaper on the picker's home page, then the home preview | `picker-crash-g14.txt`, `picker-crash-cf-before.txt`, `picker-flow-cf-before.txt` |
| Pointer overlay | Installed and applied: SystemUI's overlay path list includes `/product/overlay/OpenBookPointerOverlay.apk`. What it looks like on the G14 needs the owner's photo (checklist step 4) | — |

## The fix

`aosp/patches/packages/apps/WallpaperPicker2/0001-ANYBOOK-wallpaper-preview-a-granted-fullscreen-reque.patch`: the callback takes a nullable `Void`, as the framework delivers it. One line.

**Checked in Cuttlefish** (`anybook-cf-b6`, built from `7634a50` with the patch applied as `b9f365549`; `picker-cf-after.txt`):
- **Before (B6's own build):** the first preview that was granted fullscreen killed `com.android.wallpaper` with the same NPE as on the G14.
- **After:** the same steps, then 6 more exit/enter cycles. WM Shell approved 13 fullscreen requests, and the picker crashed 0 times; the crash buffer is empty.
- **A separate oddity, not a crash:** 3 times system_server rejected a change Shell had approved ("FullscreenRequestChange not handled properly"), and the picker logged the refusal (`Error requesting fullscreen mode`). Which reply reaches the app is a race. That is why the crash didn't happen on every try, on the G14 too.

## Not covered

- **The look and the sound** (boot animation on the panel, pointer, ringtone and notification previews) need the owner's photos and ears. They stay on the next stick's checklist (ANAL-192).
- **The default wallpaper on first boot**, for the same reason: no picture of boot A's desktop.
