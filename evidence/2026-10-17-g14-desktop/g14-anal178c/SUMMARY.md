# G14 boots of `openbook-live-20261017-anal178c` (main at `ea3c25e`), ANAL-176, 2026-10-17

The owner wrote ANAL-178's combined stick `openbook-live-20261017-anal178c`. It was built from `main` at `ea3c25e`, which includes PR #42 (uncompressed APEXes, the Launcher3 Escape fix, persistent logs), ANAL-179's Wi-Fi/Bluetooth/audio and ANAL-200's arm64 bridge. The owner booted it twice. The stick was read back read-only at 12:23Z (`read-stick-logs.sh`). Files here are redacted:
- MACs, serials and Wi-Fi names are masked by `live-report.py --redact`.
- The screenshot's list of nearby Bluetooth devices and the laptop's Bluetooth address are covered.
- The full logcats are not included, because they name nearby Bluetooth devices. They stay on the dev host.

## Boot 1: the default entry, SELinux enforcing, first boot of the freshly written stick

| Time (UTC) | | Source |
|---|---|---|
| 12:14:55 | kernel; the live helper grows `userdata` to 56.1 GiB (blank stick) | `boot1-default-enforcing/timeline.txt`, `live-init-001.json` |
| +3 s | `enforcing=1` | `type=1404 … enforcing=1` |
| +17.1 s | boot animation (desktop3's first boot: 59.4 s). **0 APEX decompressions** (desktop3: 20) | `starting service 'bootanim'` |
| +28.0 s | `boot_progress_enable_screen`; boot animation stopped at 28.5 s; `boot_completed` about 28.6 s: **the desktop, under enforcing** | `boot_progress_*`, `sf_stop_bootanim`, keystore2 |
| 12:15:34 | screen off 10 s after the desktop appeared: the boot lock screen's display timeout (`activityTimeoutWM=10000`); woken by the touchpad 1.3 s later | PowerManagerService |
| 12:15–12:19 | about 4 minutes of use: Settings, Wi-Fi (associated, `CONNECTED`), Gallery, Search, the WebView browser, Bluetooth pairing, Calendar | `START u0` |
| 12:16:25 | **the owner tapped vold's notice for `disk:8,0`, the stick itself, and got the storage set-up wizard** (which formats the disk). Backed out; nothing was formatted | vold, `notification_clicked`, `StorageWizardInit` |
| 12:19:15–17 | power menu, clean shutdown (`ShutdownThread`) | |

Totals for the boot:
- 0 app crashes and 0 tombstones.
- **23 SELinux denials, 5 distinct, none of them graphics** (`boot1-default-enforcing/avc.md`). They are the known Gatekeeper and SystemUI Bluetooth-property ones, `isolated_app` looking up `content_capture_service`, and `system_server` reading `wifi_hal_prop`.
- **151 frames never shown**: 151 × `Failed to pin framebuffer with error -22`, each followed by drm_hwcomposer `Failed to commit the frame composition` and SurfaceFlinger `present failed`. They came in bursts of 24 to 61 frames, while dialogs (Wi-Fi password, storage notice) and the WebView opened.
- 3211 test commits refused by amdgpu's display core (`Maximum is: 4` planes per stream).

## Boot 2: "save logs" (permissive), 12:20:10Z

- `boot_completed` at **28.2 s**; Wi-Fi with a **validated** internet connection; amdgpu, ANGLE on RADV, minigbm, drm_hwcomposer.
- The touchpad, keyboard, backlight, battery and the dGPU in D3cold all came up (`live-001/report.md`).
- The arm64 bridge and audio add-on checks of the other lanes are in `live-001/hwtest-final.txt`.
- The archive of earlier boots: rc 0, 1.67 MB, not capped. `prior-boots.txt` lists 9 logcat files, 0 tombstones and 101 dropbox entries.
- The device's screenshot shows the desktop with windowed Search, Settings (Bluetooth: Pair new device) and Calendar, plus the taskbar (`live-001/screen-final-redacted.png`).
- 1296 refused test commits in this boot's kernel log; 0 pin failures in its 73 s before the capture.

## Changes made from this (branch `anal-176/live-stick-safety`)

1. **vold no longer manages the disk the running system is on** (`aosp/patches/system/vold`). The live stick matched vold's USB rule, vold could not read it, and SystemUI offered to set it up (format it). The QEMU matrix reproduces this (`disk:8,0 failed to identify` in desktop4's logs case) and now checks for it: "vold leaves the boot stick alone".
2. **No lock screen until the user sets a PIN, pattern or password** (`config_disableLockscreenByDefault`), so the first desktop no longer goes black after 10 s.
3. **drm_hwcomposer uses the primary and cursor planes only** (`ro.vendor.hwc.use_overlay_planes=false`). Hypothesis: this removes both the refused test commits and the dropped frames, because SurfaceFlinger's client target is allocated for scanout. To be confirmed on the G14.

`vold` and `AnyBookDesktopFrameworkOverlay` built (`m` exit 0; the vold binary carries the new message, and the overlay APK sets `config_disableLockscreenByDefault` to true). No image was built from this branch: ANAL-191 holds the AOSP lane, and a `droid` build would change the shared `PRODUCT_OUT` it snapshots.
