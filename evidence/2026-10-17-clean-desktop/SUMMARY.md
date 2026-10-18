# ANAL-206 (backlog B5): a clean default desktop (2026-10-17/18)

The write-up is `docs/aosp-desktop.md`, section "The default desktop", and `docs/googlebook-ui.md` §2.6.

**What changed** (`device/anybook/common/desktop/`, both products through `desktop.mk`):
- `AnyBookDesktopLauncherOverlay`: Launcher3's hotseat search slot (`layout/qsb_container_hotseat`) is an empty view, and the RRO `overrides` `QuickSearchBox`, so that app is not installed.
- `AnyBookDesktopPartnerCustomization`: Launcher3's partner layout. No desktop icons; taskbar pins Files, Settings, browser, Calendar, Gallery, Camera.
- `AnyBookDesktopSettingsProviderOverlay`: `def_sound_effects_enabled=false`.
- `AnyBookDesktopLatinIMEOverlay`: `config_default_sound_enabled=false` for the default, `sw600dp` and `sw768dp` configurations.
- `release/openbook/cp2a/`: `com.android.systemui.screenshot_remove_nonforced_sound` ENABLED (READ_ONLY).

## Builds

| Build | Repo | Result | Log |
|---|---|---|---|
| `anybook_cf_x86_64_pc-cp2a-userdebug`, first | `a3304ad` | OK, 23:15–23:29 UTC | `~/anybook/logs/aosp/build-20261017T231541Z.log` (host) |
| `anybook_g14_x86_64-cp2a-userdebug`, first | `a3304ad` | OK, 23:29–00:00 UTC; live image `openbook-live-20261017-anal206` | host logs |
| `anybook_cf_x86_64_pc-cp2a-userdebug`, with the LatinIME fix | `9e249c4` | OK, 01:44–02:13 UTC | host logs |
| `anybook_g14_x86_64-cp2a-userdebug`, with the LatinIME fix | `9e249c4` | OK, 02:13–02:43 UTC; live image `openbook-live-20261017-anal206b` | host logs |

Both builds ran under the lane lock (`scripts/aosp-docker.sh`, `AOSP_JOBS=24`), with the Cuttlefish images snapshotted (reflinks) inside the lock and booted from the snapshot afterwards.

## Results

| Check | Result | Files |
|---|---|---|
| **Cuttlefish, final build** (`9e249c4`, Radeon 610M, `gfxstream_guest_angle`, fresh `/data`): `scripts/ui/desktop-defaults.sh` | **16/16 PASS.** No `QuickSearchBox`, no global search activity, no widget bound, no search view on Home; the three RROs enabled; the partner package found; pins `[documentsui, settings, webview_shell, calendar, gallery3d, camera2]` (2 camera features); `sound_effects_enabled=0`, `lockscreen_sounds_enabled=1`; LatinIME `false`; the flag `enabled`; a screenshot taken with no SystemUI `MediaPlayer`; empty crash buffer | `cf/defaults-check.txt`, `layout-log.txt`, `audio-new-players.txt`, `home-ui.xml`, `overlays.txt` |
| `scripts/desktop-capture.sh` (Settings and Files opened as a user would) | Passes: 8 freeform activity records, both apps in a `Desk` | `cf/screen-*.png`, `windowing-summary.txt`, `surfaceflinger-summary.txt`, `capture.log`, `launcher.txt.gz` |
| Before / after | Left: `main` as captured by ANAL-201 (same product, `ui-shots.sh`, 1920×1080). Right: this build. The "Google" bar is gone; the taskbar shows the new pins | `cf/cmp-desktop.png`, `cmp-settings.png`, `cmp-all-apps.png`; full size `desktop.png`, `settings.png`, `all-apps.png`, `quick-settings.png` |
| Cuttlefish, first build (`a3304ad`) | 15 of 16. **LatinIME still `true`:** an RRO value wins only where its configuration is at least as specific as the target's, and AOSP sets `true` for `sw600dp`/`sw768dp`. Fixed in `9e249c4`. (This run's script also miscounted failures and used `KEYCODE_SYSRQ`, which opens the screen capture toolbar on this desktop; both fixed.) | `cf-run1/` |
| **G14 product, final live image in QEMU** (`scripts/ui/desktop-defaults-qemu.sh`, `openbook-live-20261017-anal206b`, `9e249c4`; q35/KVM, virtio-gpu, no camera) | **All as intended:** no `QuickSearchBox`, no global search, no widget; the partner package found; pins `[documentsui, settings, webview_shell, calendar, gallery3d]`: **Camera dropped, 0 camera features** (Launcher3 loaded the layout at 02:45:23; Camera2's receiver disabled its entry at 02:45:25); `sound_effects_enabled=0`, `lockscreen_sounds_enabled=1`; LatinIME `false`; the flag enabled; 5 RROs enabled; empty crash buffer, 0 `FATAL EXCEPTION`. Without a touchpad the VM isn't desktop-first, so Launcher3 shows its hotseat, without a search box | `g14-qemu/defaults.txt`, `layout-log.txt`, `desktop.png`, `all-apps.png` |
| G14 product, first live image in QEMU (image #1, `a3304ad`) | No `QuickSearchBox`; pins `[documentsui, settings, webview_shell, calendar, gallery3d]`: **Camera dropped, 0 camera features**; touch sounds off; lock sounds on; the flag enabled; 5 RROs enabled; crash buffer empty. LatinIME `true` (before the fix). Without a touchpad the VM isn't desktop-first, so Launcher3 shows its hotseat, without a search box | `g14-qemu-run1/` |
| **Installer live checks** (`scripts/installer/live-qemu.sh`, all six cases) | **40/40**, as on `main`, on image #1. Image #2 differs from it only by the LatinIME overlay's two extra values, which no installer check touches, so the suite was not repeated. "Install OpenBook" is still in All Apps on both | `g14-live-qemu/` |

## Not changed, on purpose
- Lock and unlock sounds: on, as on Googlebook; SystemUI's unlock sound is the G14 checklist's SoundPool probe.
- The screenshot flash: no setting exists.
- "Add new apps to Home screen": AOSP 17 hard-codes it on.

## Host notes
- `run_cvd` failed with "Can't tombstone server socket" while three sibling Cuttlefish containers were running: vsock is not namespaced. `CF_ARGS=--vhost_user_vsock=true` fixed it, as the siblings already do.

## Reproduce

```bash
flock ~/anybook/aosp/.lane.lock bash -c 'AOSP_JOBS=24 scripts/aosp-docker.sh /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug && <snapshot out/target/product/anybook_vsoc_x86_64 and cvd-host_package.tar.gz to ~/anybook/aosp/cf/b5-out>'
export CF_OUT=~/anybook/aosp/cf/b5-out CF_STAGE=~/anybook/aosp/cf/b5 CF_NAME=anybook-cf-b5 CF_DEVICE=anybook_vsoc_x86_64 \
  CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_ADB_PORT=16535 CF_WEBRTC_PORT=11535 CF_ARGS=--vhost_user_vsock=true
scripts/cf-boot.sh up && scripts/cf-boot.sh wait
export ANDROID_ADB_SERVER_PORT=5135; adb connect 127.0.0.1:16535
scripts/ui/desktop-defaults.sh 127.0.0.1:16535 OUT/defaults      # first, before any app opens
scripts/ui/ui-shots.sh 127.0.0.1:16535 OUT/shots
scripts/desktop-capture.sh 127.0.0.1:16535 OUT/desktop
scripts/cf-boot.sh down
# G14 product: live image, then the checks in QEMU
OPENBOOK_LANE_LOCK_HELD=1 scripts/installer-image.sh --label openbook-live-20261017-anal206b --menu-timeout 10   # inside the lane lock
scripts/ui/desktop-defaults-qemu.sh ~/anybook/installer/out/openbook-live-20261017-anal206b.img b5-g14-b
scripts/installer/live-qemu.sh ~/anybook/installer/out/openbook-live-20261017-anal206.img b5-live-a
```
