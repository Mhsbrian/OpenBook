# Desktop windowing and VM graphics on our AOSP 17 PC build (Track A, M2)

This covers ANAL-169, as of 2026-10-16. The stage before it is ANAL-168: `aosp_cf_x86_64_pc-cp2a-userdebug` boots in Cuttlefish (`docs/aosp-build.md`, M1b).

## Result

Our own build, `anybook_cf_x86_64_pc-cp2a-userdebug` (Android 17, `CP2A.260605.016`), boots in Cuttlefish straight into the Android desktop. It shows the same window behaviour as Google's AOSP Desktop (Preview) emulator image (`sdk_gdesktop_x86_64`, `CLE1.260506.004`):

- Apps open as freeform windows inside a `Desk` root task, with caption bars (app menu, minimize, maximize, close). Two windows (Settings and Files) are shown in `evidence/2026-10-16-desktop/desktop/screen-windows.png`.
- The desktop taskbar is pinned and centred, with the all-apps button, pinned apps, running-app indicators and no navigation buttons.
- The desktop status bar shows the clock and date on the left and the notification icon on the right.
- SurfaceFlinger renders on the host's **AMD Radeon 610M** through gfxstream: `GLES: … ANGLE (AMD, Vulkan 1.4.305 (Virtio-GPU GFXStream (AMD Radeon Graphics (RADV RAPHAEL_MENDOCINO))))`.
  - With two windows open there are 11 layers: wallpaper, Home, status bar, taskbar, two tasks, two captions and three app surfaces. RenderEngine composes all of them on the GPU (`CLIENT`) and hands one buffer to the `ranchu` HWC.
  - The reference image composes the same 11 layers the same way.
  - On ANAL-168's lock screen, by contrast, the HWC composed the layers itself (`usesDeviceComposition=true`).
- `dumpsys activity activities` reports `Task{… name=Desk … mode=freeform}` holding Files and Settings, both `mode=freeform`.
  - Home (Launcher3) is visible behind the desk, as on the reference (`show_home_behind_desktop`, see flags). Before the flag value set, WM Shell's desktop wallpaper activity sat there instead.
  - The default display's settings entry is `mWindowingMode=5`.
  - WM Shell reports `Display#0 isDesktopFirst=true`; Launcher reports `isInDesktopFirstMode=true, showDesktopFirstTaskbar=true`.

We captured both images with the same script and diffed them (`scripts/desktop-compare.py`; result in `evidence/2026-10-16-desktop/compare-ref-vs-ours.md`). After our changes:
- 0 desktop-related aconfig flags differ.
- 0 `persist.wm.*`, characteristics or large-screen props differ.
- Every remaining difference is listed in [Differences from the Google desktop image](#differences-from-the-google-desktop-image) below.

## What turns desktop mode on in AOSP 17

**CONFIRMED** by reading the AOSP source at manifest `ad156f32` (`android17-release`), and checked on the device:

1. **`FEATURE_PC` no longer makes the display freeform.**
   - `DisplayWindowSettings.java` (`services/core/java/com/android/server/wm`) only forces freeform for PCs when `disable_display_force_freeform_on_pc` is off.
   - cp2a turns that flag on (`build/release/aconfig/cp2a/com.android.window.flags/`).
   - That is why ANAL-168's build had `android.hardware.type.pc` and `freeform_window_management` but still opened apps fullscreen.
2. **WM Shell gates desktop mode on two framework configs.**
   - `DesktopStateImpl.kt` (`libs/WindowManager/Shell/shared/.../desktopmode/`) needs `config_isDesktopModeSupported` for the device and `config_canInternalDisplayHostDesktops` for an internal display.
   - The aconfig gate `enable_desktop_windowing_mode` is already on in cp2a.
   - All three configs default to `false` (`core/res/res/values/config.xml:7757-7776`).
3. **Desktop-first, i.e. booting into the desktop.**
   - The root TaskDisplayArea has to be `WINDOWING_MODE_FREEFORM`. WM sets it from `display_settings.xml` (`/product/etc` is read first, then `/vendor/etc`).
   - WM Shell's `DesktopDisplayModeController.kt` then overrides it at runtime. It picks freeform only if one of these holds:
     - `persist.wm.debug.force_desktop_first_on_default_display_for_testing=true`
     - an extended external display is connected
     - **a touchpad and a physical keyboard** are attached
     - the device reports a laptop lid state
   - Otherwise it switches the display back to fullscreen.
   - We tested two cases in the VM with the force property off (`evidence/2026-10-16-desktop/touchpad/`):
     - **Keyboard only:** `targetWindowingModeForDefaultDisplay=1`, and Settings opens fullscreen. The `display_settings.xml` value alone gets overridden.
     - **`--touchpad=width=1280,height=800` plus the virtio keyboard:** `targetWindowingModeForDefaultDisplay=5` and `hasAnyTouchpadDevice=true`. Apps launched from Home open in a freeform `Desk`.
   - So a real laptop gets desktop-first without the "for testing" property. The VM uses the property, as Google's emulator image does.
4. **Launch placement.**
   - `DesktopModeLaunchParamsModifier.java:457-487` (`enable_desktop_first_top_fullscreen_bugfix`): on a desktop-first display, a new task stays fullscreen if no desk is active and Home is not visible. The log line is `desktop-first-but-fullscreen-visible`.
   - Example: an `am start` issued while the keyguard was still dismissing opened fullscreen, and so did the next app after it.
   - `scripts/desktop-capture.sh` waits for Home before it launches anything.
5. **Taskbar.**
   - Launcher3's `TaskbarFeatureEvaluator.kt` pins the taskbar when the display is in desktop mode, or when it is a desktop-first freeform display (`SystemWindowManagerProxy.showDesktopTaskbarForFreeformDisplay`).
   - Navigation buttons follow `config_navBarInteractionMode`. Gestural (2) removes them, as on the reference image.

## The OpenBook desktop configuration

Everything is in a device tree inside this repo. `scripts/aosp-build.sh` copies it into the AOSP tree on every build: `rsync --delete` to `device/anybook`, because Soong's nsjail sandbox only sees `/aosp/src`.

```
device/anybook/
  AndroidProducts.mk                       lunch anybook_cf_x86_64_pc-cp2a-userdebug
  common/desktop/                          reusable by any OpenBook product (VM or bare metal)
    desktop.mk                             characteristics, large_screen_common, the two RROs, release config map
    Android.bp                             AnyBookDesktopFrameworkOverlay, AnyBookDesktopSystemUIOverlay (/product)
    overlays/framework/res/values/config.xml
    overlays/systemui/res/values/config.xml
    release/                               aconfig value set "aconfig_value_set-anybook_desktop-cp2a" (163 flags: 79 here, 84 from ANAL-204)
  cuttlefish/
    anybook_cf_x86_64_pc.mk                aosp_cf_x86_64_pc + desktop.mk + the VM-only pieces below
    display_settings.xml                   port:0 windowingMode=5 ignoreOrientationRequest=true (-> /product/etc)
```

A bare-metal product (ANAL-176 onward) inherits `device/anybook/common/desktop/desktop.mk`. It shouldn't take the VM-only force property or the port-0 display settings.

### Every overlay value and property

**Reference** means Google's emulator image, read offline from its partitions (`evidence/2026-10-16-desktop/reference-image/`).

**Framework RRO** (`dev.anybook.overlay.desktop.framework`, target `android`, static, /product)

| Config | Value | Reference | Why |
|---|---|---|---|
| `config_isDesktopModeSupported` | true | true (vendor RRO) | WM Shell device gate |
| `config_canInternalDisplayHostDesktops` | true | true | internal display may host desks |
| `config_enterDesktopByDefaultOnFreeformDisplay` | true | true | taskbar/launch default; the bugfix flag forces the same in cp2a |
| `config_showHomeBehindDesktop` | true | true | read only when `show_home_behind_desktop` is on (it is now; see flags) |
| `config_showNavigationBar` | true | true | |
| `config_navBarInteractionMode` | 2 (gestural) | 2 | no nav buttons in the taskbar |
| `config_showGesturalNavigationHints` | true | true | |
| `config_allowPresentationOnInternalDisplay` | true | true | |
| `config_globalActionsList` | emergency, lock, power, restart, logout, screenshot, bugreport | same | power menu |
| `config_supportsCamToggle`, `config_supportsMicToggle` | true | true | privacy toggles |
| `config_lockPatternVisibleDefault` | false | false | |
| `config_lockPinEnhancedPrivacyDefault` | true | true | |
| `config_magnification_keep_zoom_level_when_context_changed`, `config_magnification_magnify_keyboard_default` | true | true | |

These reference values were left out:
- **Look and feel:** `config_useRoundIcon=true`, `config_icon_mask` (circle), `config_buttonTextAllCaps=false`.
- **Emulator-specific:** `config_defaultNightMode=1` and `config_minimumScreenOffTimeout=2147483647`.
- **Same as the AOSP default already:** the corner radii and `config_secondaryHomePackage`.

**SystemUI RRO** (`dev.anybook.overlay.desktop.systemui`, target `com.android.systemui`; WM Shell resources are part of SystemUI)

- **Set to true, as on the reference:**
  - `config_useDesktopStatusBar`, `config_notificationShadeOnTopEnd`, `config_statusBarTapToExpandShade`
  - `config_enableDesktopAudioTileDetailsView`, `config_enableHideNotificationsShadeOnAllAppsKey`, `config_enableInputRouting`
  - `config_enableSignOutButtonOnKeyguardStatusBar`, `config_improveLargeScreenInteractionOnLockscreen`, `config_isDesktopForFalsingPurposes`
  - `config_largeScreenPrivacyIndicator`, `config_testDesktopScreenSize`
  - `config_letterboxIsReachabilityEducationEnabled`, `config_letterboxIsRestartDialogEnabled`
- **Set to false:** `config_useBrightnessMirrorInOverlay`, `config_removeStatusBarInputLayer`.
- **Other:** `lock_icon_padding=24px`.
- **Left out:**
  - `config_disableSplitShade`: not in AOSP SystemUI.
  - `hsu_allow_list_qs_tiles`: headless system user mode (HSUM) only. Neither image uses HSUM.

**Product properties and packages**

| Setting | Where | Reference |
|---|---|---|
| `PRODUCT_CHARACTERISTICS := desktop` (`ro.build.characteristics=desktop`) | desktop.mk | same. Selects `product="desktop"` strings; Soong also generates the four `*__desktop__auto_generated_characteristics_rro.apk` the reference has |
| `large_screen_common.mk`: `persist.wm.extensions.enabled=true`, `persist.wm.extensions.activity_embedding_guard_with_android_15=false`, `persist.settings.large_screen_opt.enabled=true` | desktop.mk | same three props |
| `persist.wm.debug.force_desktop_first_on_default_display_for_testing=true` | cuttlefish product only | same |
| `/product/etc/display_settings.xml`: `port:0 windowingMode=5 ignoreOrientationRequest=true` | cuttlefish product only | `/vendor/etc/display_settings.xml`: `local:<id> windowingMode=5 ignoreOrientationRequest=true` |

### aconfig flags

All the desktop windowing flags are already on in cp2a. They include `enable_desktop_windowing_mode`, `enable_display_windowing_mode_switching`, `enable_desktop_first_*`, `enable_desktop_taskbar_on_freeform_displays` and `enable_multiple_desktops_*`.

Google's desktop build turns on more flags than cp2a does. These are UI flags, not windowing flags. **79 flags** are enabled on the reference, disabled in cp2a and declared in our tree:

| Package | Flags | Examples |
|---|---|---|
| `com.android.systemui` | 28 | `status_bar_for_desktop` (date in the status bar), `desktop_sizing`, `desktop_effects_qs_tile`, `scene_container`, `notification_add_x_on_hover_to_dismiss` |
| `com.android.documentsui.flags` | 12 | `desktop_ux_phase_2_ro`, `desktop_file_handling_ro`, `single_click_to_select` |
| `com.android.launcher3` | 10 | `enable_scalability_for_desktop_experience`, `enable_taskbar_drag_and_drop`, `enable_mouse_interaction_changes`, `enable_cursor_driven_workflows` |
| `android.multiuser` | 5 | `create_initial_user`, `user_switching_dialog_signout_message` |
| `com.android.settings.flags` | 5 | `show_top_level_device_category` |
| `com.android.window.flags` | 4 | `show_home_behind_desktop`, `enable_overflow_button_for_taskbar_pinned_items` |
| `com.android.graphics.surfaceflinger.flags` | 4 | `connected_display_hdr_v2` |
| others | 11 | `com.android.server.usb.flags.enable_usb4`, IME large-screen switcher, `enable_photopicker_desktop` (MediaProvider) |

**How they get in.**
- `scripts/desktop-flags.py` diffs `aflags list` between the two images. It writes one `ENABLED`/`READ_ONLY` value file per flag into `device/anybook/common/desktop/release/aconfig/cp2a/`, matching the reference's `read-only`.
- `desktop.mk` adds the release config map through `PRODUCT_RELEASE_CONFIG_MAPS`. lunch then lists `aconfig_value_set-anybook_desktop-cp2a` last in `RELEASE_ACONFIG_VALUE_SETS`, so its values win.
- The map lives at `device/anybook/common/desktop/release/` on purpose. `build/make/core/release_config.mk` auto-loads maps from `device/*/release/` and `device/*/*/release/` for **every** product, and other runs build `aosp_cf_x86_64_pc` from the same tree.
- In a cp2a build, a flag that is read-only and disabled doesn't appear in `aflags list` at all; it is compiled out. That's why most of them show as "—" in the pre-flags diff (`evidence/2026-10-16-desktop/desktop-before-flags/compare-ref-vs-ours.md`).

**Effect we checked.**
- The desktop status bar gained the date and the notification icon, matching the reference (compare `desktop-before-flags/screen-windows.png` with `desktop/screen-windows.png`).
- Home now sits behind the desk instead of WM Shell's desktop wallpaper activity, as on the reference.
- Windowing and the taskbar were the same before and after.

**Risk (HYPOTHESIS).** Google ships these 79 flags on Android 17. We have no regression tests for them, beyond the boot, the desktop capture and the benchmark below.

#### Flag set v2: the Googlebook flags (ANAL-204)

Googlebook enables 218 more flags that our tree declares. ANAL-204 triaged all of them and enabled **84**, in six groups, in the same value set. Details are in [`googlebook-flags.md`](googlebook-flags.md); the record is `device/anybook/common/desktop/release/googlebook-triage.tsv`.

- `scripts/desktop-flags.py --list <triage.tsv> [--groups ...]` writes them. Each value file's first line names its source, so `--list` and the diff mode above each regenerate only their own files.
- **Two flags break AOSP 17's desktop and stay off (C):**
  - `enable_add_window_decoration_to_all_tasks`: SystemUI crashes when a minimized window is restored from the taskbar.
  - `start_on_gone_scene_if_no_lockscreen`: the notification shade is empty. Our framework overlay disables the lock screen, so SystemUI would start on the Gone scene, and the keyguard section that binds the notification stack never runs.
- **23 do nothing:** nothing in our tree reads them, e.g. `perfect_edge` and `enable_taskbar_icon_desktop_clicks`.
- **Visible on the desktop (C, Cuttlefish):** box shadows and a 1 px border on windows, stepped cascading, the windowing pill inside the maximize menu, QS tile tooltips, power-menu blur, and a Cast tile that works over Ethernet.
- Evidence: `evidence/2026-10-17-desktop-flags-v2/`. The G14 checks are on ANAL-192.

## Cuttlefish GPU modes on this host

**Host:** Ryzen 9 7950X with a Radeon 610M iGPU (`/dev/dri/renderD129`, Mesa 26.2.4 on the host) and an RTX 4090 (`renderD128`, NVIDIA 615.78.08). No root.
- Both render nodes and `/dev/nvidia*` are mode 0666, so they can be passed to Docker without sudo.

**Container.**
- `tools/Dockerfile.cuttlefish` (image `anybook-cuttlefish`) is the pinned `cuttlefish-orchestration:1.56.0` image plus `mesa-vulkan-drivers`, `vulkan-tools`, `libegl-dev` and `libgles-dev` (Debian 13, Mesa 25.0.7).
- The base image has Mesa's GL drivers. It has no Vulkan ICD and no unversioned `libGLESv2.so`, which gfxstream and `graphics_detector` dlopen.

**How a GPU gets in** (`scripts/cf-boot.sh`).
- `CF_GPU=amd` passes the AMD render node and sets `EGL_PLATFORM=surfaceless`. Mesa's default platform needs X11 or Wayland; with it, `graphics_detector` reports "Failed to initialize display".
- `CF_GPU=nvidia` passes `/dev/nvidia{0,ctl,-modeset,-uvm}` and the render node. It bind-mounts the host's NVIDIA userspace read-only: `libnvidia-*.so.<ver>`, `libEGL_nvidia`, `libGLX_nvidia` (the Vulkan ICD), `libGLESv2/v1_nvidia`, plus the glvnd and Vulkan ICD JSONs.
- `CF_GPU_MODE` is passed to `--gpu_mode`. The default stays `guest_swiftshader` with no host GPU, so other runs see no change.

**Results.** Boot matrix on ANAL-168's `aosp_cf_x86_64_pc` images, 2026-10-16 (`evidence/2026-10-16-desktop/gpu/`). The benchmark ran on the final `anybook_cf_x86_64_pc` build (`evidence/2026-10-16-desktop/bench/`). Each benchmark round is 40 scripted swipes over the Settings list, read from `dumpsys gfxinfo`. Two rounds per mode, on a shared host.

| `CF_GPU` | `--gpu_mode` | Boot | Renderer reported by SurfaceFlinger | Janky frames | Frame time p50 / p90 / p99 |
|---|---|---|---|---|---|
| none | `guest_swiftshader` (old default) | yes, 17 s | ANGLE → SwiftShader Vulkan **in the guest** (CPU) | 10.1% / 31.5% | 5–7 / 32–61 / 65–89 ms |
| none | `gfxstream_guest_angle_host_swiftshader` | yes, 19 s | ANGLE → gfxstream → SwiftShader on the host (CPU) | 0.7% / 0.3% | 8 / 13 / 14–23 ms |
| **amd** | **`gfxstream_guest_angle`** | **yes, 17 s** | **ANGLE → gfxstream Vulkan → RADV, Radeon 610M** | **0% / 0%** | **5 / 5 / 5 ms** |
| amd | `gfxstream` | yes, 19 s | gfxstream GLES translator → radeonsi GLES 3.2, Radeon 610M | 0% / 0% | 5 / 5 / 7 ms |
| nvidia | `gfxstream_guest_angle` | yes, 24 s | ANGLE → gfxstream Vulkan → RTX 4090 | 0.15% / 0.14% | 5 / 5 / 5–6 ms |
| nvidia | `gfxstream` | yes, 19 s | gfxstream GLES translator → NVIDIA GL | 0.14% / 0% | 5 / 5 / 5 ms |
| amd, nvidia, none | `drm_virgl` | **no**: crosvm dies before the guest kernel starts | — | — | — |

**Choice: `CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle`.**
- It is hardware-accelerated on AMD, which is what the project targets. Mesa RADV does the host-side rendering.
- It uses the same guest stack the Cuttlefish desktop path uses: ANGLE on Vulkan, SkiaVk HWUI, minigbm, ranchu HWC.
- It had no janky frames.
- The RTX 4090 works just as well, but it is shared with other workloads on this host.
- The software modes still work without a GPU. `gfxstream_guest_angle_host_swiftshader` is the better of the two: 0.3–0.7% janky against 10–31%.

**Notes.**
- At startup, `assemble_cvd` warns that the host "does not have a non-software implementation Vulkan driver" for RADV, because `graphics_detector` reports the 610M as `TYPE_OTHER`. The warning is wrong: the SurfaceFlinger renderer string shows RADV.
- **Why `drm_virgl` fails (CONFIRMED for AOSP's crosvm).** A minimal crosvm with only `--gpu=backend=virglrenderer,…` crashes even with no host GPU, while the same command with gfxstream context types starts (`gpu/crosvm-virgl-minimal.txt`).
  - Debian `cuttlefish-base` 1.57.0 crosvm: SIGSEGV.
  - AOSP's prebuilt crosvm (from our `cvd-host_package`): SIGABRT with `Failed to create virtio gpu worker thread: invalid rutabaga build parameters`.
  - With `CF_HOST_TOOLS=build` the main crosvm core-dumps (`si_code: 3`). That launcher does not fail fast, so `cvd create` waits until its timeout.
  - So neither crosvm build can run virglrenderer. The likely reason (**HYPOTHESIS**) is that both were built without the virglrenderer rutabaga backend. Not pursued: gfxstream covers the need.
- The benchmark numbers are indicative. The swipes are injected, HWUI measures the Settings process only, the display is 60 Hz, and the host load average was 2–7 during the runs.

## Commands

Since ANAL-174 the product builds for device `anybook_vsoc_x86_64` (`docs/graphics-amd.md`), so `scripts/cf-boot.sh` needs `CF_DEVICE=anybook_vsoc_x86_64` for it.

```bash
docker build -t anybook-cuttlefish -f tools/Dockerfile.cuttlefish tools/          # 17 s
# Build the desktop product: it copies device/anybook into the tree. Incremental on top of ANAL-168's out/.
AOSP_JOBS=32 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug
docker wait anybook-aosp-build
# Boot on the AMD iGPU, keep it up, capture desktop evidence, tear down.
export CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_LOGS=$HOME/anybook/logs/desktop/run1
scripts/cf-boot.sh up && scripts/cf-boot.sh wait
export ANDROID_ADB_SERVER_PORT=5047        # private adb server; other runs share the default one
~/anybook/android-sdk/platform-tools/adb connect 127.0.0.1:16520
scripts/desktop-capture.sh 127.0.0.1:16520 $CF_LOGS/desktop
scripts/cf-gfx-bench.sh 127.0.0.1:16520 $HOME/anybook/logs/desktop/bench amd-gfxstream_guest_angle
scripts/cf-boot.sh down
# Reference: Google's desktop emulator image in its own AVD (ports 5600/5601, adb server 5047), same capture.
scripts/desktop-ref-emulator.sh $HOME/anybook/logs/desktop/ref-emulator
python3 scripts/desktop-compare.py $HOME/anybook/logs/desktop/ref-emulator $CF_LOGS/desktop > compare.md
# Regenerate the flag value set after a new reference image or AOSP release:
python3 scripts/desktop-flags.py REF/aflags.txt OURS/aflags.txt ~/anybook/aosp/src device/anybook/common/desktop/release \
  --extra com.android.providers.media.flags.enable_photopicker_desktop
```

### Build measurements (2026-10-16, incremental on top of ANAL-168's `out/`)

| Build | Wall clock | Actions | Peak (container cgroup, 15 s samples) | Notes |
|---|---|---|---|---|
| `anybook_cf_x86_64_pc`, overlays and props | 12 min 38 s (analysis about 1.5 min) | 8,263 | 48 GiB RAM + **52 GiB swap**; host `MemAvailable` reached 0.0 GiB at 15:33–15:37 UTC | `PRODUCT_CHARACTERISTICS` changed, so every app's resources were relinked |
| plus the 79 flags | 24 min 50 s | 9,918 | 48.7 GiB RAM + 16.6 GiB swap; `MemAvailable` min 1.9 GiB | framework, SystemUI, Launcher3 and DocumentsUI rebuilt |

Both builds finished without errors. The host kernel log (`journalctl -k`) shows no OOM kills from 15:25 to 16:20 UTC.
- **HYPOTHESIS:** use `AOSP_JOBS=24` for builds that touch many apps, given the swap peak of the first build.
- The second build's post-build stats (ccache and sizes) are missing: `aosp-build.sh` was edited while that build was running. Bash reads scripts as it goes, so the reporting tail failed to parse.

## Evidence (`evidence/2026-10-16-desktop/`)

- `desktop/`: the final build on the AMD iGPU (`gfxstream_guest_angle`).
  - Screenshots: `screen-desktop.png` (empty desktop and taskbar) and `screen-windows.png` (two freeform windows and the taskbar).
  - Summaries: `windowing-summary.txt` (tasks and `mWindowingMode=freeform`), `surfaceflinger-summary.txt` (renderer and HWC layers).
  - Full dumps: `activities.txt.gz`, `surfaceflinger.txt.gz`, `wmshell.txt.gz` (DesktopDisplayModeController, desks), `launcher.txt.gz` (taskbar state), `window-displays.txt.gz`.
  - Device state: `getprop.txt`, `features.txt`, `overlays.txt`, `aflags.txt.gz`, `settings-global.txt`, `input-devices.txt`.
  - Boot: `cf-boot.log`, `props-summary.txt`, `logcat.txt.gz`, `dmesg.txt.gz`.
- `reference/`: the same capture of Google's desktop emulator image. `reference-image/`: its overlay values and props, read offline. No image files are committed.
- `compare-ref-vs-ours.md` (final) and `desktop-before-flags/`: the first desktop build, before the flag value set.
- `touchpad/`: desktop-first without the force property. Case `a` is keyboard only (fullscreen); case `b` is touchpad plus keyboard (freeform).
- `gpu/`: the boot matrix. Per mode: `cf-boot.log`, props, SurfaceFlinger renderer and dump, and launcher graphics lines. Also `graphics_detector-*.txt`, `crosvm-virgl-minimal.txt` and the `drm_virgl` crash logs.
- `bench/`: `gfx-bench.csv`, raw `gfxinfo-*.txt.gz` and the per-mode boot logs.
- `build/`: build logs, GNU time and memory samples for both builds.

## Differences from the Google desktop image

Both images were captured with the same script at 1920×1080, 160 dpi. Windowing, taskbar, status bar and window captions match. Everything below differs.

| Area | Reference (`sdk_gdesktop_x86_64`, emulator) | Ours (`anybook_cf_x86_64_pc`, Cuttlefish) | Status |
|---|---|---|---|
| aconfig | 11 `com.google.wear.*` flags enabled | absent: not in AOSP | Google-only |
| aconfig, mainline modules | 9 flags enabled: Bluetooth ×5, ART `hiddenapi_platform_enforcement`, RKPD `enable_feedback_loop`, MediaProvider ×2 | disabled | not desktop-related; these follow the module trains |
| aconfig | — | 5 newer flags on: `notification_shade_blur`, `notification_background_tint_optimization`, `idempotent_wct_resolution`, `fix_bubble_insets_when_invisible`, `ensure_uij_notification` | our tree is a month newer (`CP2A.260605` vs `CLE1.260506`) |
| Framework RRO | round icons, circle icon mask, no all-caps buttons, `defaultNightMode=1`, `minimumScreenOffTimeout=MAX` | AOSP defaults | look and feel, emulator-only; left out on purpose |
| SystemUI RRO | `config_disableSplitShade`, `hsu_allow_list_qs_tiles` | — | not in AOSP / HSUM only |
| Graphics | goldfish GL pipe (`ro.hardware.egl=emulation`, `gltransport=pipe`), gralloc `ranchu`, `debug.hwui.renderer=skiagl`, GLES 3.0 | ANGLE on gfxstream Vulkan (`virtio-gpu-asg`), minigbm, HWC `ranchu`, `skiavk`, GLES 3.1 | different virtual platforms |
| ARM apps | `ro.dalvik.vm.native.bridge=libndk_translation.so` (prebuilt, not in AOSP) | `0`. The abilist still lists `arm64-v8a` | ANAL-181 |
| Hardware features | touchscreen (multitouch), fingerprint, accelerometer, compass, `faketouch`, MIDI | Ethernet, USB host/accessory, camera autofocus, `device_id_attestation` | VM device models |
| Wi-Fi | `wifi_on=1`; Wi-Fi icon in the status bar | `wifi_on=0` | Cuttlefish Wi-Fi not turned on; not investigated |
| Kernel | 6.12.58 android16-6.12 (emulator `kernel-ranchu`) | 6.12.74 android16-6.12 (Cuttlefish prebuilt GKI) | ANAL-171/172 bring android17-6.18 |
| Display identity | `display_settings.xml` keyed by unique id `local:4619827259835644672` | keyed by `port:0` | same effect: freeform, ignoring orientation requests |
| Name | "Android Desktop" | "AnyBook Cuttlefish x86_64 desktop" (`PRODUCT_MODEL`; still the old name, see the README) | ours |

## Open items

- **Bare metal.** Inherit `common/desktop/desktop.mk` and leave out the force property: the touchpad-plus-keyboard path gave a freeform desktop in the VM. The internal panel's `display_settings.xml` will need its own port or id.
- **The 79 flags** need more testing than the boot, desktop capture and scroll benchmark done here.
- **Wi-Fi** is off in our VM, as noted in the differences table.
- **ANAL-174** (AMD graphics in the device tree) can build on `anybook_cf_x86_64_pc`.
  - `out/target/product/vsoc_x86_64_only` now holds this product's images. Building `aosp_cf_x86_64_pc` again re-installs and rebuilds the flag- and characteristics-dependent modules. **Estimate:** 25–40 min, based on the two builds above.
  - That rebuild is not harmful. The release map is not auto-loaded, so `aosp_cf_x86_64_pc` keeps the stock cp2a flags.
