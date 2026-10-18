# Why Googlebook looks cleaner than AOSP, and what OpenBook can match (ANAL-201)

As of 2026-10-17. Labels: **C** = confirmed (we read it from the image, ran it, or read a primary source), **R** = reported (press or third party), **HYPOTHESIS** = not yet tested.

Google apps and how to install them are covered in [`gapps.md`](gapps.md). Evidence is in `evidence/2026-10-17-gbos-ui/`.

## Summary

- **The look does not come from GApps (C).** We compared three images:
  - Google's **AOSP Desktop** emulator image (37.0): AOSP's UI and no Google apps.
  - Google's **Google APIs Desktop** emulator image (37.1, `CLE3.260929.004`): the same GMS APEX, Play Store and GSF that Googlebook has. It still uses AOSP's Launcher3 (`Quickstep`), AOSP SystemUI, AOSP Settings and AOSP Wallpapers.
  - The **Googlebook** recovery image (ruby, `CL3B.260622.271.R1`).

  Installing Google apps leaves the AOSP look in place.
- **Googlebook replaces the platform UI with Google's own builds (C):**
  - Pixel Launcher (`NexusLauncherRelease`, package `com.google.android.apps.nexuslauncher`).
  - Google's SystemUI (`SystemUITitan`, package `com.android.systemui`).
  - Settings (`SettingsGoogle`).
  - Wallpaper & style (`WallpaperPickerGoogleRelease`).
  - Seven SystemUI clock plugins.

  It also adds 61 product overlays, the Google Sans fonts and 728 more enabled feature flags.
  - **SystemUI and Settings are signed with the device's platform key (C).** They can't run on our framework, and copying them would mean redistributing Google's code.
  - **510 of those 728 flags are not declared anywhere in public AOSP 17 (C).** Googlebook runs internal code newer than `android17-release`.
- **The largest gap we can close with open source is typography (C).**
  - AOSP 17's SystemUI, Launcher3 and SettingsLib ask for font families that AOSP never defines, so they fall back to Roboto:
    - `google-sans*`;
    - the 30 Material 3 Expressive `variable-*` families.
  - Googlebook defines all 40 families on top of Google Sans and Google Sans Flex.
  - **Both fonts are SIL OFL 1.1 in `github.com/google/fonts`.**
  - In a VM, our prototype puts them on the OpenBook desktop without rebuilding the image (§3).
- **Other gaps we can close:**
  - **Background blur.** Googlebook enables it. The G14 product does now too (ANAL-203, §2.3); the laptop check is still to run.
  - **Window shadows, cursor fixes and other polish.** These sit behind flags AOSP 17 already declares.
  - **Circular icons** and **0 % wallpaper dim**.
  - **A tidy default desktop.** Today it carries AOSP's old search widget.
  - **Our own wallpapers, sounds, boot animation and pointer set.**
- **Out of reach (proprietary or tied to Google services):** Magic Pointer (gPointer), Gemini, AI and cinematic wallpapers, At a Glance content, the Google Sans Clock faces and the Glowbar.

## What we examined

| Image | Build | How we read it |
|---|---|---|
| Googlebook OS, Lenovo `ruby` recovery image | `CL3B.260622.271.R1` (16452207, Android 17, SDK 37.1) | Downloaded 2026-10-15 for M0 (`docs/RESEARCH.md`) and unpacked with `scripts/gbos-unpack.sh`. Never committed |
| Google APIs Desktop (Preview), `system-images;android-37.1;android-desktop;x86_64` | `desktop_generic-userdebug 17 CLE3.260929.004 16489338` | `x86_64-37.1_r01.zip`, sha1 `7d2d46be…` (matches the SDK manifest). Android SDK License: local use only |
| OpenBook | `anybook_g14` and `anybook_cf_x86_64_pc` from `main` (2026-10-17) | `out/target/product/*` |

Tools (all in this PR):
- `scripts/gbos-inventory.py`: every APK's package, version, ABIs and signer; overlay targets; fonts; build props.
- `scripts/overlay-values.py`: flattens overlay resource values.
- `scripts/aconfig-storage-dump.py`: reads Android 17's binary flag storage offline.

The evidence holds metadata, configuration values and screenshots only. No Google APK, font or image file is committed.

## 1. What Googlebook ships beyond AOSP

The ruby image has 248 APKs, 66 of them overlays. OpenBook's G14 product has 111 (19 overlays); the Google APIs Desktop image has 146 (32). The full lists are in `inventory/*-packages.tsv`.

| Group | Packages (examples) | Signed with | Can OpenBook use it? |
|---|---|---|---|
| **Platform UI replaced by Google builds** | `com.android.systemui` (SystemUITitan, 51 MB, x86_64); `com.android.settings` (SettingsGoogle); Pixel Launcher `com.google.android.apps.nexuslauncher` (version "17", i.e. built inside Google's platform tree); `com.google.android.apps.wallpaper`; `SystemUIClocks-{BigNum,Calligraphy,Growth,Inflate,Metro,NumOverlap,Weather}`; `DocumentsUIGoogle`; `AvatarPickerGoogle` | SystemUI and Settings: **the platform key** (`87b95a0a…`, same as `framework-res`). Launcher: its own key (`a86bdb05…`) | **No.** They are proprietary and built against Google's internal framework. The two platform-signed apps need signature permissions that only Google's platform key grants |
| **GMS core (what a GApps package installs)** | GmsCore 26.22.43 inside the APEX `com.google.android.gmssystem` (x86_64 + x86); `GoogleServicesFramework`; Play Store 52.4.41; Android Setup; Googlebook setup; partner setup; ConfigUpdater; Play Protect service | Google release keys (portable) | Only through a user-installed option ([`gapps.md`](gapps.md)) |
| **Googlebook desktop apps** | gPointer (Magic Pointer, 224 MB); Desktop System Intelligence (`alai`); Gemini and Gemini shell; Glowbar Disco; contextual tools; Chrome 150 + Trichrome; Text; Camera; Viewer (Backpack); Tips; Link to iOS; Recorder; AI, adaptive and cinematic wallpaper; Dreams; Task Manager | Google keys | No (proprietary, tied to Google services) |
| **Google apps also on Play** | Gmail, Docs, Sheets, Slides and Meet (TWA stubs); Drive; Photos; Keep; Calendar; Contacts; Messages; YouTube; YouTube Music; Calculator; Clock; Gboard; Speech Services; TalkBack; Voice Access | Google keys | From Play, once a user-installed GMS is present |
| **OEM and factory** | Lenovo Vantage/RMA/diagnostics stubs; factory repair, diagnostics and post-manufacturing apps; Repair Mode | Google or OEM keys | Not needed |

Signers are listed in `inventory/googlebook-ruby-signers.txt`, and the GMS APEX contents in `inventory/googlebook-ruby-gms-apex.txt`.

## 2. What makes it look cleaner, ranked

### 2.1 Typography: Google Sans everywhere (C)

**Googlebook:**
- `FrameworkDesktopOverlay` sets `config_headlineFontFamily=google-sans`, `config_headlineFontFamilyMedium=google-sans-medium`, `config_bodyFontFamily=google-sans-text` and `config_bodyFontFamilyMedium=google-sans-text-medium`. DocumentsUI uses `google-sans-flex`.
- `/product/etc/fonts_customization.xml` defines 40 named families.
- The 30 `variable-<role>-<size>[-emphasized]` families are the Material 3 type scale on Google Sans Flex:
  - the optical size equals the type size, e.g. `variable-display-large` uses `opsz=57`, `variable-body-small` uses `opsz=12`;
  - "emphasized" means one weight step heavier, plus `ROND=100` (rounded terminals).

**AOSP 17:**
- SystemUI references these families 21 times in `res/values/styles.xml`, Launcher3 25 times and SettingsLib's expressive theme 30 times.
- AOSP's font config defines none of them, so every one of those styles silently renders in Roboto. That is part of why AOSP desktop text looks generic next to Googlebook's.

**Licences.** Read from each font's `name` table and from google/fonts:

| Font | In Googlebook's image | Public release |
|---|---|---|
| Google Sans (variable: opsz 17–18, wght 400–700, GRAD) | v10.001, "not open source" | **OFL 1.1**, v14.000, `ofl/googlesans`, added 2026-09-11. Same axes |
| Google Sans Flex (opsz, wdth, wght, ROND, slnt; Googlebook's copy also has GRAD) | v4.001, **OFL 1.1** | **OFL 1.1**, v5.000, `ofl/googlesansflex` (2026-10-09). No GRAD axis |
| Google Sans Clock, Google Sans Flex Clock | proprietary | none. We substitute Google Sans Flex |
| 42 extra system fonts: metric-compatible document fonts (Arimo, Tinos, Cousine, Tachyonic, Velarium, Geotic, Tisane, Gaumond, Trophis, Codecs, Comedic Sans, Whendings, Archivo, Gelasio, Comic Relief …) | OFL 1.1 (`github.com/googlefonts/*`) | Same projects. They render web pages and Office documents with correct metrics |

The OFL lets us ship both families unmodified with `OFL.txt`. Google's `TRADEMARKS.md` forbids using "Google" or "Google Sans" in our product name, and implying affiliation. Our use of `google-sans` as an internal font-family identifier refers to the original font. **The owner should confirm that reading** (see Owner decisions).

**Result:** the prototype in §3.

### 2.2 Google's SystemUI, Launcher and newer framework code (C)

- **What Googlebook enables.** Its partitions enable 2,371 aconfig flags; our G14 build enables 2,186. In these user builds, a disabled read-only flag is compiled out, so "absent" means "off".
- **728 flags are on in Googlebook and off for us** (`flags/googlebook-on-openbook-off.tsv`):
  - **510 are not declared in AOSP 17 at all.** Among them are 117 window-manager, 70 SystemUI and 31 Launcher3 flags. They belong to code Google hasn't published.
  - **218 are declared in AOSP 17**, 128 of them in UI packages. These we could turn on with the value-set mechanism from ANAL-169 (`docs/aosp-desktop.md`), testing each one.
- **The visible ones among the 128:**
  - `com.android.window.flags.enable_freeform_box_shadows_v2` (window shadows), `com.android.wm.shell.enable_pip_box_shadows_v2`, `color_transform_box_shadows_and_border`.
  - `com.android.systemui.blur_on_more_surfaces` and `com.android.launcher3.blur_on_more_surfaces`.
  - `enable_no_resize_cursor`, `perfect_edge` and `improve_fluid_resizing_performance` (window resizing).
  - `enable_stepped_cascading`, `enable_home_screen_peeking`, `enable_fullscreen_window_controls`, `enable_consolidated_window_options`, `enable_desktop_taskbar_in_fullscreen_mode`, `desktop_minimize_last_task_bugfix`, `appheader_launch_color_bugfix`.
  - Launcher3: `enable_taskbar_icon_desktop_clicks` (click to minimize), `expandable_long_press_menu`, `fallback_reveal_animation`; `com.android.systemui.shared.enable_recents_in_taskbar`.
  - SystemUI: `enable_qs_tile_tooltips`, `hun_timer_pause_on_hover`, `notification_animated_action_style_2026`, `default_hun_expansion`.
- **Risk (HYPOTHESIS).** Some of these flags may guard code that is incomplete in the June 2026 AOSP snapshot. Turn them on in small groups, with the desktop capture and the G14 checks.

### 2.3 Blur and surface effects (C)

- **Googlebook:** `ro.surface_flinger.supports_background_blur=1`. Its framework overlay also sets `config_enableSurfaceShadow=true`, a config AOSP 17's framework doesn't have.
- **OpenBook, since ANAL-203:**
  - The G14 product sets the property too (`device/anybook/g14/anybook_g14_x86_64.mk`). Before, OpenBook on the laptop had no blur at all (`inventory/openbook-g14-ui-props.txt`).
  - The Cuttlefish product is unchanged: it inherits the property from `device/google/cuttlefish/shared/device.mk`.
  - Evidence is in `evidence/2026-10-17-blur/`.

**What AOSP 17 needs alongside the property** (C, read from the source; nothing else to set in our tree):
- **Framework configs.** `config_enableAppLaunchBlur` (Launcher3's app-launch blur) and `config_enableBlurExpansion` (blur on more surfaces, with B3's flags) default to `true` in AOSP 17. Googlebook doesn't override them, and neither do we.
- **SystemUI and Launcher3** blur only when `ActivityManager.isHighEndGfx()` holds (not low-RAM, no `ro.config.avoid_gfx_accel`) and `persist.sysui.disableBlur` is unset. All of that holds on the G14.
- **WM's `BlurController` turns blur off by itself:**
  - in battery saver;
  - at thermal status SEVERE or above;
  - in tunnel mode;
  - when `Settings.Global.disable_window_blurs` is 1 (`wm disable-blur 1`; Developer options).

  The switch reaches SystemUI and Launcher3 without a restart; in our runs it took effect before the next panel opened.
- **Flags already on in our build:** SystemUI's `notification_shade_blur` and Launcher3's `app_launch_blur`. `blur_on_more_surfaces` is B3 (ANAL-204).
- **Who draws it:** SurfaceFlinger's RenderEngine, on the GPU, with `KawaseDualFilterV2`. On the G14 that is SkiaGL on ANGLE on RADV (`graphics-amd.md`, "Background blur and the renderer properties").

**Found while measuring: Googlebook blurs less than we now do (C).** Both Googlebook's SystemUI desktop overlay and Google's 37.1 desktop emulator image set SystemUI's `config_supportBlurredWallpaper=false`. In AOSP 17 that stops `NotificationShadeDepthController` from blurring (and zooming) everything behind the shade. Without it, as on our builds, opening the small Quick Settings panel in the top-right corner blurs the whole desktop, at radius 34 px in Cuttlefish (`evidence/2026-10-17-blur/cf/screens/cmp-qs-on-off.png`). Googlebook's panels instead blur only behind themselves, which is what B3's `blur_on_more_surfaces` turns on. **Recommendation for B3:** take `config_supportBlurredWallpaper=false` together with those flags, and measure both with the same tool. Until then the G14 gets the full-screen blur, the heaviest case.

**Cost in Cuttlefish** (C; Radeon 610M, `gfxstream_guest_angle`, 1920×1080 at 60 Hz; `scripts/ui/blur-bench.sh`):
- **Method.** 20 openings and closings each of the shade and of Quick Settings, then a Settings scroll with the shade closed as a control. Six rounds alternate blur on and off (on, off, on, off, on, off), switched with `wm disable-blur`.
- **Host load.** The shared host's load went from 14 to 92 (32 threads) while siblings built, so each on round is compared with the off round next to it.

| Pair (host load) | Scenario | SystemUI janky % on / off | p90 ms on / off | SF frame time avg ms on / off | RenderEngine ms per GPU frame (on) | SF missed % on / off |
|---|---|---|---|---|---|---|
| r1/r2 (14–27, quiet) | shade | 3.6 / 4.6 | 16 / 19 | 4.2 / 3.3 | 4.0 | 0 / 0.3 |
| r1/r2 (14–27, quiet) | Quick Settings | 0.8 / 0.9 | 8 / 8 | 2.7 / 2.2 | 2.8 | 0 / 0 |
| r5/r6 (85–92, loaded) | shade | 16.9 / 8.1 | 40 / 25 | 6.3 / 4.2 | 6.1 | 1.3 / 0 |
| r5/r6 (85–92, loaded) | Quick Settings | 19.2 / 12.2 | 46 / 32 | 5.5 / 4.3 | 5.4 | 0.2 / 0 |

- **Blur is applied, and only when on.** With blur on, SurfaceFlinger blurs one layer, `VRI-NotificationShade`, at radius 34. With blur off it blurs none, and no layer stayed blurred with the panels closed.
- **On a quiet host it costs SystemUI nothing measurable.** It costs SurfaceFlinger 2.8–4.0 ms of RenderEngine time per frame. Those frames go to the GPU: about 1,100 of each set's 1,600–1,800 frames with blur on, and none with it off, because Cuttlefish's composer handles them otherwise.
- **Under heavy host load the shade with blur doubles its janky frames.** In Cuttlefish, gfxstream's renderer runs on the host's CPU threads.
- **The control (Settings scroll) shows no blur effect.**
- **No crash, restart or amdgpu fault line,** in the guest or on the host.
- The first run had one off round in which the shade stayed blurred (`cf-first-run/`). It didn't recur in a manual test or in the second run. That run checks for it before every round.

**The G14 product's image in QEMU** (C; `scripts/ui/blur-qemu.sh`; virtio-gpu, so SwiftShader, a CPU renderer):
- The build carries the property (`vendor/build.prop`). In QEMU, SystemUI reports `supportsBlursOnWindows: true`.
- After OpenBook setup is finished, Quick Settings with blur on draws `backgroundBlurRadius=34` behind it, and with blur off nothing (`evidence/2026-10-17-blur/qemu/cmp-qs-on-off.png`).
- `blur-check.sh`, typed in over the serial console, ran both rounds: blur applied, no hang or restart.
- On SwiftShader blur is expensive: RenderEngine +7.3–7.8 ms per frame, and SurfaceFlinger misses 18–22 % of the frames while a panel moves, against 1.5–2.4 % without blur.
- That doesn't apply to the G14's GPU, but it does to the image's VM fallback. If QEMU-based UI tests of the G14 image get slower or flaky, gate blur on the GPU probe. That needs the property set by init on `hal=amdgpu` instead of in `vendor/build.prop`; HYPOTHESIS, untested, and the SELinux side is to check.

**What this predicts for the G14 (HYPOTHESIS):**
- the 890M has far more GPU than the 610M, and no gfxstream layer;
- the G14 draws 2.5× the pixels, at 2880×1800;
- drm_hwcomposer already sends most frames to the GPU (overlay planes are off), so blur adds only its own passes.

Only the G14 run can say.

**G14 check** (pass/fail; `scripts/ui/blur-report.py`). The graphics check's new `blur` part runs it unattended (`graphics-amd.md`), with blur on, off, on and off:

| Verdict | Pass when |
|---|---|
| `blur_applied` | With blur on, SurfaceFlinger blurs a layer behind the open shade and Quick Settings, and SystemUI reports `supportsBlursOnWindows: true`. With blur off, no layer is blurred. No layer is blurred with the panels closed |
| `no_gpu_hang` | No new amdgpu ring time-out, reset or page-fault line, and SurfaceFlinger, SystemUI and system_server keep their PIDs |
| `frame_cost` | For the shade and Quick Settings, with blur on: SystemUI janky frames ≤ 10 % and ≤ off + 5 points (paired); SurfaceFlinger missed frames ≤ off + 2 % of frames; RenderEngine time per GPU-composed frame ≤ 6 ms on average, and its p90 ≤ 8 ms (one 120 Hz refresh is 8.3 ms) |

Plus the owner's eye: in a normal session the desktop behind Quick Settings is blurred, not just dimmed.

### 2.4 Shape, icons and wallpaper (C)

| Value | Googlebook | AOSP 17 / OpenBook |
|---|---|---|
| `config_icon_mask` | circle | rounded square (8 % radius) |
| `config_useRoundIcon` | true | false |
| `config_wallpaperDimAmount` | 0 | 0.05 |
| `config_dialogCornerRadius`, `config_bottomDialogCornerRadius`, `config_buttonCornerRadius`, `config_progressBarCornerRadius` | 28, 16, 4, 1000 dp | same |
| `persist.wallpapercolors.threshold` / `max_dark_area` | 55 / 12 | unset |
| SystemUI `config_supportBlurredWallpaper`, `config_wallpaperZoomEnabled` | false, false | AOSP defaults |
| Pixel Launcher desktop overlay | taskbar all-apps button 48 dp persistent / 57 dp transient, `reduce_workspace_blur_usage=true`, Material colour roles for the taskbar | AOSP Launcher3 defaults |

Corner radii already match. The visible differences are the icon shape and the wallpaper treatment. Googlebook ships its own wallpaper set (`DesktopWallpapers`, `DefaultWallpaperOverlayRuby`) plus AI, adaptive and cinematic wallpaper apps. Our default is AOSP's stock wallpaper.

### 2.5 Pointer, sounds, boot animation, setup (C)

- **Pointer:**
  - Googlebook replaces 10 framework pointer shapes (20 drawables, each with an icon variant) with its own vector set in `FrameworkDesktopOverlay`, and adds 4 no-resize cursors in SystemUI.
  - We can't copy that art. AOSP 17 has vector pointer icons with fill and stroke styles, which we can theme with our own design.
- **Sounds:** Googlebook uses Google's set (`Soft_Mallets.ogg`, `Oxygen.ogg`, `product/media/audio/{ui,notifications,ringtones,alarms}`). We use AOSP's (`OnTheHunt.ogg`, `Alarm_Classic.ogg`). The 9to5Google review called Googlebook's default click sounds "very annoying", so OpenBook should turn them off by default.
- **Boot animation:** Googlebook ships `system/media/bootanimation.zip`; we have none.
- **Setup:** Googlebook runs Google's setup wizard (`setupwizard.theme=glif_expressive`); we run AOSP Provision.

### 2.6 Desktop clutter (C for OpenBook, R for Googlebook)

- **OpenBook (C):** our default desktop shows AOSP's legacy `QuickSearchBox` widget, a dark "Google" bar across the bottom (`fonts-prototype/before-settings.png`).
- **Googlebook (R):** reviewers describe its launcher as the Pixel Launcher's search, opened from the G key (9to5Google review, 2026-10-12).
- **Next:** remove the widget from the default workspace, and drop `QuickSearchBox` from the product.

### 2.7 Out of reach

These are proprietary or need Google services:
- Magic Pointer (gPointer, DeepMind);
- Gemini and its shell;
- AI, adaptive and cinematic wallpaper;
- At a Glance and cue-bar content;
- Desktop System Intelligence;
- Pixel clock faces (the clock fonts are proprietary);
- the Glowbar (lid hardware).

AOSP 17 keeps the hooks (contextual-search shake gesture, the Ambient Cue UI, Smartspace and AppPrediction services), so an open service could plug in later.

## 3. Prototype: Googlebook typography on OpenBook, in a VM

**What we did** (C, 2026-10-17, `evidence/2026-10-17-gbos-ui/fonts-prototype/`):

1. Booted our desktop build (`anybook_cf_x86_64_pc`, `CP2A.260605.016`) in Cuttlefish on the Radeon 610M (`gfxstream_guest_angle`). It reached `sys.boot_completed` 17 s after `cvd create`.
2. Captured the desktop, a Settings window, Quick Settings, the notification shade and all apps (`scripts/ui/ui-shots.sh`).
3. Ran `scripts/ui/font-prototype.sh`. It pushes three files from google/fonts commit `47d54ca1` (sha256 in `font-source.txt`): `GoogleSans-VF.ttf`, `GoogleSans-Italic-VF.ttf` and `GoogleSansFlex-VF.ttf`. It also pushes:
   - our generated `fonts_customization.xml` (`scripts/ui/fonts-customization.py`: 40 families, Material 3 type scale);
   - a static RRO `dev.openbook.overlay.fonts` with the four `config_*FontFamily` values Googlebook uses.

   Then it rebooted the VM (adb remount/overlayfs, verity off; VM only).
4. Captured the same screens again.

**Result:**
- After the reboot the overlay is enabled.
- `cmd overlay lookup` resolves `config_headlineFontFamily=google-sans` and `config_bodyFontFamily=google-sans-text`, and the device reads all 40 families.
- Settings, the window caption, Quick Settings and all apps render in Google Sans / Google Sans Flex (`cmp-settings.png`, `cmp-quick-settings-crop.png`). The crash buffer was empty.
- The rest of the screen is unchanged. The wallpaper, the QSB widget and the light grey taskbar are what still separate it from Googlebook.

**Limits:**
- Prototype only: test-key RRO, a userdebug VM, files pushed at runtime.
- The product build, the G14 and a font-rendering performance check are still to do.
- Upstream Google Sans Flex has no GRAD axis, so our `variable-*` families leave it out.
- The clock families map to Google Sans Flex.

## 4. Proposed beautification backlog (alpha → beta)

| # | Item | Size | Needs |
|---|---|---|---|
| B1 | **Fonts in the product.** `PRODUCT_COPY_FILES` for the three OFL fonts and `OFL.txt`, the generated `fonts_customization.xml`, and the four values in `AnyBookDesktopFrameworkOverlay`. Then the desktop capture in Cuttlefish and the G14 checklist | small | Owner OK on the trademark reading |
| B2 | **Blur on the G14.** `ro.surface_flinger.supports_background_blur=1`; check frame times on the 890M. **Done in the product (ANAL-203); measured in Cuttlefish; G14 check on ANAL-192's stick** (§2.3) | small | — |
| B3 | **Flag set v2.** Evaluate the 128 UI flags AOSP 17 declares, in groups. Start with box shadows, blur on more surfaces, resizing (`perfect_edge`, no-resize cursor, fluid resizing) and taskbar clicks. `scripts/desktop-flags.py` already writes the value set | medium | — |
| B4 | **Shape and wallpaper values:** circular icon mask, round icons, wallpaper dim 0, wallpaper colour thresholds | small | — |
| B5 | **A clean default desktop:** remove the QuickSearchBox widget and the app, set taskbar pins (Files, Settings, browser) | small | Owner's pin list |
| B6 | **Brand assets:** wallpapers (our own or CC0/CC-BY, not bulk Unsplash), a sound set with click sounds off by default, a boot animation, a pointer theme. Based on the brand mark in `assets/brand/` | medium | Owner design input |
| B7 | **Document fonts:** the 42 OFL metric-compatible fonts, for web and Office fidelity | small | — |
| B8 | **Setup:** a first-run flow in our style, after the installer | medium | After M8 |

## Owner decisions

1. **Fonts:** ship Google Sans and Google Sans Flex (OFL) under the internal family names `google-sans*`, never in OpenBook branding. Recommendation: yes.
2. **Backlog:** which of B1–B8 to open as issues. Recommendation: B1, B2, B4 and B5 first; together they are about a day of work plus G14 checks.

## Reproduce

```bash
# Inventory: the image must be unpacked first (scripts/gbos-unpack.sh); aapt2 from our AOSP host out
A=~/anybook/aosp/src/out/host/linux-x86/bin/aapt2; R=~/anybook/work/gbos-ruby/fs
scripts/gbos-inventory.py --aapt2 $A --part system=$R/system_a/system --part system_ext=$R/system_ext_a \
  --part product=$R/product_a --part vendor=$R/vendor_a --out ~/anybook/gbos-ui/ruby
scripts/overlay-values.py ~/anybook/gbos-ui/ruby/overlays/*.txt > ~/anybook/gbos-ui/ruby/overlay-values.txt
scripts/aconfig-storage-dump.py $R/system_a/system/etc/aconfig $R/system_ext_a/etc/aconfig \
  $R/product_a/etc/aconfig $R/vendor_a/etc/aconfig > ~/anybook/gbos-ui/ruby/aconfig-storage.txt
# Font prototype in Cuttlefish
export CF_DEVICE=anybook_vsoc_x86_64 CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_NAME=anybook-cf-ui
scripts/cf-boot.sh up && scripts/cf-boot.sh wait
export ANDROID_ADB_SERVER_PORT=5051; adb connect 127.0.0.1:16520; adb root
scripts/ui/ui-shots.sh 127.0.0.1:16520 OUT/before
scripts/ui/font-prototype.sh 127.0.0.1:16520 FONTDIR WORKDIR       # reboots the VM
scripts/ui/ui-shots.sh 127.0.0.1:16520 OUT/after
scripts/cf-boot.sh down
```

## Sources

- The images and tools listed above, plus `github.com/google/fonts` (`ofl/googlesans`, `ofl/googlesansflex`, read 2026-10-17).
- [9to5Google review](https://9to5google.com/2026/10/12/googlebook-os-review/), 2026-10-12, R.
- [Googlebook Help: Home screen and theming](https://support.google.com/googlebook/answer/18100780), read 2026-10-17, C.
- [AOSP window blurs](https://source.android.com/docs/core/display/window-blurs), C.
- [Material 3 type scale](https://m3.material.io/styles/typography/type-scale-tokens), C.
