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
  - **Background blur.** The G14 product doesn't enable it; Googlebook does.
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
- **OpenBook:**
  - The Cuttlefish product inherits blur from `device/google/cuttlefish/shared/device.mk`. The prototype screenshots show the blurred Quick Settings panel.
  - **The G14 product doesn't set the property, so OpenBook on the laptop has no blur at all** (`inventory/openbook-g14-ui-props.txt`).
- **Next:** set it in `device/anybook/g14`, then measure frame times on the 890M with the scroll benchmark and `dumpsys gfxinfo`.

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
- **Sounds:** Googlebook uses Google's set (`Soft_Mallets.ogg`, `Oxygen.ogg`, `product/media/audio/{ui,notifications,ringtones,alarms}`). We use AOSP's (`OnTheHunt.ogg`, `Alarm_Classic.ogg`). The 9to5Google review called Googlebook's default click sounds "very annoying". Googlebook's own `SettingsProviderDesktopOverlay` already sets `def_sound_effects_enabled=false` (C). OpenBook now does the same (§2.6).
- **Boot animation:** Googlebook ships `system/media/bootanimation.zip`; we have none.
- **Setup:** Googlebook runs Google's setup wizard (`setupwizard.theme=glif_expressive`); we run AOSP Provision.

### 2.6 Desktop clutter (C for OpenBook, R for Googlebook)

- **OpenBook before ANAL-206 (C):** the default desktop showed AOSP's legacy `QuickSearchBox` widget, a dark "Google" bar across the bottom (`fonts-prototype/before-settings.png`). It is Launcher3's hotseat search box, and Google's AOSP Desktop emulator image shows the same bar. The taskbar held Launcher3's tablet defaults: Calendar, Gallery, WebView Shell, Camera.
- **Googlebook (R):** reviewers describe its launcher as the Pixel Launcher's search, opened from the G key (9to5Google review, 2026-10-12).
- **Googlebook (C, from its overlays):** touch sounds off by default (`SettingsProviderDesktopOverlay`), the screenshot shutter sound only when forced (`com.android.systemui.screenshot_remove_nonforced_sound`), and new apps not added to the desktop (`NexusLauncherOverlayDesktop`: `pref_add_icon_to_home_default=false`).
- **OpenBook since ANAL-206 (C, Cuttlefish and the G14 product in QEMU; `evidence/2026-10-17-clean-desktop/`):**
  - no search box: a Launcher3 RRO empties the hotseat's search slot, and `QuickSearchBox` is no longer installed;
  - taskbar pins from a partner customization package: Files, Settings, the browser, Calendar, Gallery, and Camera where a camera exists;
  - touch sounds, the on-screen keyboard's keypress sound and the non-forced screenshot sound are off.

  The mechanisms, what depended on `QuickSearchBox`, and what was left alone are in [`aosp-desktop.md`](aosp-desktop.md#the-default-desktop-no-search-box-taskbar-pins-quiet-sounds-anal-206).
- **Still different:** AOSP 17's Launcher3 adds every newly installed app to the desktop, and the setting's default can't be changed without a Launcher3 patch. The screenshot still flashes; no setting exists for it.

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

## 4. Beautification backlog (alpha → beta)

The owner approved every item on 2026-10-17. Each one is a sub-issue of ANAL-201, and all are being worked in parallel.

| # | Issue | Item | Size | Needs |
|---|---|---|---|---|
| B1 | ANAL-202 | **Fonts in the product.** `PRODUCT_COPY_FILES` for the three OFL fonts and `OFL.txt`, the generated `fonts_customization.xml`, and the four values in `AnyBookDesktopFrameworkOverlay`. Then the desktop capture in Cuttlefish and the G14 checklist | small | — (approved) |
| B2 | ANAL-203 | **Blur on the G14.** `ro.surface_flinger.supports_background_blur=1`; check frame times on the 890M | small | — |
| B3 | ANAL-204 | **Flag set v2.** Evaluate the 128 UI flags AOSP 17 declares, in groups. Start with box shadows, blur on more surfaces, resizing (`perfect_edge`, no-resize cursor, fluid resizing) and taskbar clicks. `scripts/desktop-flags.py` already writes the value set | medium | — |
| B4 | ANAL-205 | **Shape and wallpaper values:** circular icon mask, round icons, wallpaper dim 0, wallpaper colour thresholds | small | — |
| B5 | ANAL-206 | **A clean default desktop:** remove the QuickSearchBox widget and the app, set taskbar pins (Files, Settings, browser), quiet sounds. **Done in ANAL-206** (§2.6); the owner can change the pin list in review | small | Pins proposed in the PR; the owner reviews |
| B6 | ANAL-207 | **Brand assets:** wallpapers (our own or CC0/CC-BY, not bulk Unsplash), a sound set with click sounds off by default, a boot animation, a pointer theme. Based on the brand mark in `assets/brand/` | medium | Owner reviews the visuals in the PR |
| B7 | ANAL-208 | **Document fonts:** the 42 OFL metric-compatible fonts, for web and Office fidelity | small | — |
| B8 | ANAL-209 | **Setup:** a first-run flow in our style, after the installer | medium | Coordinate with ANAL-191 (installer) |

## Owner decisions (2026-10-17)

1. **Fonts:** approved. We ship Google Sans and Google Sans Flex (OFL) under the internal family names `google-sans*`, never in OpenBook branding.
2. **Backlog:** all of B1–B8 approved and opened as ANAL-202 to ANAL-209.

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
