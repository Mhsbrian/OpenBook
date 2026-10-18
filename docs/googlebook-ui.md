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
  - Both OpenBook desktop products ship them since ANAL-202 (§3.1). The G14 check is still to run.
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
| 42 extra system fonts: metric-compatible document fonts (Arimo, Tinos, Cousine, Tachyonic, Velarium, Geotic, Tisane, Gaumond, Trophis, Codecs, Comedic Sans, Whendings, Archivo, Gelasio, Comic Relief …) | OFL 1.1 (`name` tables) | **Only 17 of the 42 files are public** (7 families, all in google/fonts). The other 25 name `github.com/googlefonts/<name>` projects that were not public on 2026-10-17 (§2.1.1) |

The OFL lets us ship both families unmodified with `OFL.txt`. Google's `TRADEMARKS.md` forbids using "Google" or "Google Sans" in our product name, and implying affiliation. Our use of `google-sans` as an internal font-family identifier refers to the original font. The owner approved that reading on 2026-10-17 (see Owner decisions).

**Result:** the prototype in §3, then the product (§3.1, ANAL-202).

#### 2.1.1 Document fonts (B7, ANAL-208)

Web pages and Office documents name Windows fonts. Without a font of the same widths, lines break in different places and layouts shift. AOSP 17 maps `arial`, `verdana` and `tahoma` to Roboto, `times new roman` and `georgia` to Noto Serif, and `courier new` to Cutive Mono, none of which share their widths.

**What is public (C, 2026-10-17).** Each of Googlebook's 42 document fonts names its upstream in its copyright string:
- **Public, in google/fonts** (7 families, 17 files): Arimo, Tinos, Cousine, Gelasio, Comic Relief, Archivo Black, Archivo Narrow. Their versions are the ones Googlebook ships.
- **Not public** (13 families, 25 files): Tachyonic, Velarium, Geotic, Tisane, Gaumond, Trophis, Codecs, Comedic Sans, Whendings 1–4, Arvos (and Black, Narrow). Their `github.com/googlefonts/<name>` repositories return 404, google/fonts doesn't have them, and a web search found no release. We don't copy them from Google's image.
- So **Verdana and Tahoma have no stand-in yet**. Googlebook maps them to Velarium and Tachyonic.

**Aliases, from upstream metadata only.** Each family's google/fonts description, which matches the font's own `name` table:

| Family | Windows name it takes | Upstream says |
|---|---|---|
| `arimo` | `arial` | "metrically compatible with Arial" |
| `tinos` | `times new roman` | "metrically compatible with Times New Roman" |
| `cousine` | `courier new` | "metrically compatible with Courier New" |
| `gelasio` | `georgia` | "metrics compatible with Georgia" in all four styles |
| `comic-relief` | `comic sans ms` | "metrically equivalent to … Comic Sans MS" |
| `archivo-black`, `archivo-narrow` | none | no metric claim. Googlebook maps `arial-black` and `arial-narrow` to them; we don't |

The three multi-word families also answer to their own names (`comic relief`, `archivo black`, `archivo narrow`), because WebView knows a font only by the names `fonts.xml` gives it.

**Independent check (C).** Arial was drawn to Helvetica's widths, Times New Roman to Times Roman's and Courier New to Courier's. Adobe's freely distributable Core 14 AFMs give those widths. On all 95 printable ASCII characters, Arimo, Tinos and Cousine match Helvetica, Times-Roman and Courier, regular and bold, within 0.24/1000 em, which is AFM rounding. Roboto matches 0 of 95 (`evidence/2026-10-17-doc-fonts/offline-metrics.md`). Georgia and Comic Sans MS have no public metrics, so for Gelasio and Comic Relief we have only their upstreams' word.

**Where the names have to go (C):**
- **The framework** reads `/system/etc/font_fallback.xml` plus `/product/etc/fonts_customization.xml`. AOSP 17's `FontCustomizationParser` accepts `<alias>`. `FontListParser` puts the customization's aliases ahead of the system's, and `Typeface.initSystemDefaultTypefaces` keeps the first alias of a name, so `arial → arimo` beats AOSP's `arial → sans-serif`. No framework patch is needed.
- **WebView and Chrome never read the customization file.** Chromium 145 (`skia/ext/font_utils.cc`) uses Skia's `SkFontMgr_New_Android`, which parses only `/system/etc/fonts.xml`, with font paths relative to `$ANDROID_ROOT/fonts/`. The NDK path (`UseAndroidNDKFontAPI`) is off by default, and it wouldn't map aliases anyway. The framework itself reads `font_fallback.xml`; only the zygote still reads `fonts.xml`, to preload locale fonts.
- **So OpenBook does both.** The fonts and the families go in `/product` (`device/anybook/common/desktop/fonts/documents/`, and B1's generated `fonts_customization.xml`). A small patch to the legacy `fonts.xml` (`aosp/patches/frameworks/base/0001-*`) declares the same families as `../../product/fonts/<file>`, moves the four aliases AOSP already has (`arial`, `times new roman`, `courier new`, `georgia`) and adds the others. Skia keeps the first family a name maps to, so the old aliases are removed, not overridden. `scripts/ui/fonts-customization.py --legacy-fonts-xml` writes the patched file and `scripts/ui/fonts-legacy-patch.sh` the patch.
- **The alternative, named families only** (no aliases), would make `font-family: Arimo` work but not `Arial`, which is what pages use, so it doesn't meet the goal.

**Measured in Cuttlefish** (C, the `anybook_cf_x86_64_pc` product build, `evidence/2026-10-17-doc-fonts/product-cf/`; a pushed-files prototype on `main` gave the same numbers). `scripts/ui/doc-fonts-check.sh` opens `scripts/ui/doc-fonts-test.html` in the shipped WebView 145 shell. The page measures two strings in each family at 100 px, with kerning and ligatures off, and `scripts/ui/doc-fonts-metrics.py` matches each width to the font whose advance widths give it:

| CSS `font-family` | Before (AOSP fonts) | After | After − expected |
|---|---|---|---|
| Arial | Roboto | **Arimo** | +0.008 px of 2562.7 px |
| Times New Roman | Noto Serif | **Tinos** | 0.000 px |
| Courier New | Cutive Mono | **Cousine** | +0.004 px |
| Georgia | Noto Serif | **Gelasio** | +0.012 px |
| Comic Sans MS | Roboto | **Comic Relief** | +0.012 px |
| Verdana, Tahoma | Roboto | Roboto (no stand-in) | — |
| `initial` (unstyled text), `sans-serif`, `serif` | Roboto, Roboto, Noto Serif | unchanged | — |

Bold matches the same way. Both products build, B1's 40 families still load and measure as Google Sans, and the crash buffer and SELinux denials are empty. Through the framework (`Typeface.create` and `Paint`, `scripts/ui/doc-fonts-typeface.sh`) each Windows name lands within 1 px of its stand-in on both strings; Paint returns whole pixels.

**Side effect.** A page that names only fonts the device lacks, with no generic family, now gets Arimo instead of Roboto. Blink's last resort (`FontCache::GetLastResortFallbackFont`) tries `""`, then `Sans`, then `Arial`. Text with no font set, or ending in `sans-serif`, is unchanged.

**Size:** 5,313,524 bytes of fonts in `/product/fonts`, plus 4,466 bytes in `fonts_customization.xml` and 5,309 bytes in `fonts.xml`. In the images: `product.img` +3,948,544 bytes (the partition is compressed) and `system.img` +4,096, measured on the Cuttlefish product against B1's own build (`evidence/2026-10-17-doc-fonts/build/image-sizes.md`).

**Open:**
- Verdana and Tahoma wait for Google to publish Velarium and Tachyonic (and the other 11). Any other stand-in would need the owner's approval.
- Helvetica, Times and Courier still map to Roboto, Noto Serif and Cutive Mono. Blink treats Arial↔Helvetica, Times↔Times New Roman and Courier↔Courier New as interchangeable (`alternate_font_family.h`), and the AFM check above shows the widths agree. Moving those three aliases is a small follow-up, but it goes beyond what the upstreams claim, so it needs an owner decision.
- Calibri and Cambria, Office's defaults since 2007, have open metric-compatible fonts (Carlito, Caladea). Googlebook doesn't ship them; they would be a separate item.

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
- **Done in ANAL-204 (B3), see [`googlebook-flags.md`](googlebook-flags.md):** all 218 triaged and 85 enabled. Five of the visible flags above do nothing in AOSP 17: `perfect_edge`, `enable_taskbar_icon_desktop_clicks`, `enable_desktop_taskbar_in_fullscreen_mode`, `notification_animated_action_style_2026` and `appheader_launch_color_bugfix` have no reader in our tree. `enable_no_resize_cursor` is read, but nothing acts on its result. Two flags broke the desktop and stay off.

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

**On the G14, the owner's `anal192d` session** (C, 2026-10-18; `evidence/2026-10-18-blur-g14/`; the graphics check wasn't booted):
- SurfaceFlinger started with `Threaded RenderEngine with SkiaGL Backend (Ganesh)` and `Background Blurs Enabled (Kawase dual-filtering V2 algorithm)`.
- In an hour of normal use the shade was opened 9 times, and SystemUI drew its blur each time, at radius 51 px (34 dp-equivalent at 240 dpi). This is the full-screen case, since `config_supportBlurredWallpaper` is still on.
- No amdgpu fault or reset, no SurfaceFlinger, SystemUI or Launcher restart, no ≥ 30-frame skip or ≥ 700 ms frame.
- So `blur_applied` and `no_gpu_hang` pass from the logs. **`frame_cost` is still unmeasured;** it needs the graphics check boot.

**G14 check** (pass/fail; `scripts/ui/blur-report.py`). The graphics check's new `blur` part runs it unattended (`graphics-amd.md`), with blur on, off, on and off:

| Verdict | Pass when |
|---|---|
| `blur_applied` | With blur on, SurfaceFlinger blurs a layer behind the open shade and Quick Settings, and SystemUI reports `supportsBlursOnWindows: true`. With blur off, no layer is blurred. No layer is blurred with the panels closed |
| `no_gpu_hang` | No new amdgpu ring time-out, reset or page-fault line, and SurfaceFlinger, SystemUI and system_server keep their PIDs |
| `frame_cost` | For the shade and Quick Settings, with blur on: SystemUI janky frames ≤ 10 % and ≤ off + 5 points (paired); SurfaceFlinger missed frames ≤ off + 2 % of frames; RenderEngine time per GPU-composed frame ≤ 6 ms on average, and its p90 ≤ 8 ms (one 120 Hz refresh is 8.3 ms) |

Plus the owner's eye: in a normal session the desktop behind Quick Settings is blurred, not just dimmed.

### 2.4 Shape, icons and wallpaper (C)

| Value | Googlebook | AOSP 17 | OpenBook since ANAL-205 |
|---|---|---|---|
| `config_icon_mask` | circle | rounded square (8 % radius) | **circle** (our own two-arc path) |
| `config_useRoundIcon` | true | false | **true** |
| `config_wallpaperDimAmount` | 0 | 0.05 | **0** |
| `config_dialogCornerRadius`, `config_bottomDialogCornerRadius`, `config_buttonCornerRadius`, `config_progressBarCornerRadius` | 28, 16, 4, 1000 dp | same | same |
| `persist.wallpapercolors.threshold` / `max_dark_area` | 55 / 12 | unset (code defaults 70 / 5) | **55 / 12** |
| SystemUI `config_supportBlurredWallpaper`, `config_wallpaperZoomEnabled` | false, false | AOSP defaults | AOSP defaults |
| Pixel Launcher desktop overlay | taskbar all-apps button 48 dp persistent / 57 dp transient, `reduce_workspace_blur_usage=true`, Material colour roles for the taskbar | AOSP Launcher3 defaults | AOSP Launcher3 defaults |

Corner radii already match. Googlebook ships its own wallpaper set (`DesktopWallpapers`, `DefaultWallpaperOverlayRuby`) plus AI, adaptive and cinematic wallpaper apps. Our default is still AOSP's stock wallpaper (B6).

**Done in ANAL-205** (evidence: `evidence/2026-10-17-shape-wallpaper/`):
- **Where the values are set.**
  - The three framework values are in `AnyBookDesktopFrameworkOverlay` (`device/anybook/common/desktop/overlays/framework/res/values/config.xml`).
  - The two properties are in `desktop.mk` (`PRODUCT_PRODUCT_PROPERTIES`, so `/product/etc/build.prop`, where Googlebook has them too).
  - Both products inherit them.
  - The circle is `M50,0 A50,50 0 1,1 50,100 A50,50 0 1,1 50,0 Z`, written by us. Googlebook and Google's desktop emulator image use a cubic-Bézier circle.
- **What reads each value in AOSP 17** (`android17-release`, read 2026-10-17):
  - **`config_icon_mask`:**
    - `AdaptiveIconDrawable` reads it, so it shapes app icons drawn in Settings' app lists, SystemUI and bubbles.
    - SettingsLib's `AdaptiveIconShapeDrawable` and `AdaptiveOutlineDrawable` read it, so it shapes the Settings homepage icons as well.
    - Launcher3's `ThemeManager.parseIconState()` uses it whenever the user hasn't picked a shape.
  - **`config_useRoundIcon`:** PackageManager reads it (`ParsingPackageUtils.readConfigUseRoundIcon`) and then hands out `android:roundIcon` instead of `android:icon`.
    - Only 3 of the 96 APKs in our image declare a round icon: CredentialManager, DeviceDiagnostics and ThreadNetworkDemoApp.
    - So this mostly matters for third-party apps, which usually ship one.
  - **`config_wallpaperDimAmount`:** read only by `WallpaperService.Engine`.
    - It is a minimum dim, applied to a wallpaper whose colours carry neither the dark-text nor the dark-theme hint.
  - **`persist.wallpapercolors.threshold` / `max_dark_area`:** read once per process into static fields of `android.app.WallpaperColors` (`BRIGHT_IMAGE_MEAN_LUMINANCE`, `MAX_DARK_AREA`).
    - Together they decide `HINT_SUPPORTS_DARK_TEXT`, which picks Launcher3's DarkText theme and SystemUI's lock screen colours.
    - Their SELinux context is `default_prop`, which every `coredomain` process may read, apps included.
- **Measured in Cuttlefish**, `anybook_cf_x86_64_pc`, base `c861cf4` against B4, on the same day and with the same scripts:
  - **Resolved values:** `cmd overlay lookup` resolves the circle path, `true` and `0.0`. `getprop` shows 55 and 12.
  - **Icons:** all apps, the taskbar, the Settings homepage and Settings' app list all draw circles (`compare-*.png`).
  - **Wallpaper dim:** a flat grey wallpaper (180) showed on screen as 171 before (×0.95, AOSP's 5 % default dim) and 180 after. Grey 206 showed as 195 before and 206 after (`scripts/ui/wallpaper-dim-check.sh`).
  - **Colour hints:** `WallpaperColors.fromBitmap()` on the device now gives the dark-text hint to:
    - a grey of luminance 0.62;
    - a white image with 8 % dark pixels.

    Before, it gave neither one the hint. A white image with 15 % dark pixels gets no hint in either build (`scripts/ui/wallpaper-hints.sh`).
  - **Crashes:** the crash buffer was empty after each check.
- **The icon-shape picker (Wallpaper & style → Home screen → Icons → Shape).**
  - **How it works:**
    - It is Launcher3's `grid_control` provider, behind `com.android.launcher3.enable_launcher_icon_shapes`, which is on in cp2a. It offers Circle, Square, 4-sided cookie, 7-sided cookie and Arch.
    - The user's pick is stored in the Launcher pref `icon_shape_model`, and on the home screen it beats `config_icon_mask`.
    - With nothing picked, the picker marks the first option, Circle, as selected.
  - **What AOSP's default did:** the picker said Circle while the launcher drew the rounded square. The circle mask removes that mismatch.
  - **What we checked, through the provider as the picker uses it:**
    - Picking Square turns the taskbar's icons square, so the user's choice still wins.
    - Clearing the pick brings the circles back.
    - Settings and SystemUI keep the system mask whatever the pick, which is AOSP's design.
  - **Open (AOSP behaviour, not caused by B4).** The taskbar's all-apps panel keeps drawing the system mask after a pick, even after Launcher restarts. The baseline build behaves the same way: the pixel diff is 0 with its rounded-square mask. **HYPOTHESIS:** that panel's icons don't follow `ThemeManager`'s shape the way the taskbar's do. The cause hasn't been traced.
- **On the G14** (the owner's `anal192d` session, 2026-10-18, from the logs; photos pending; `evidence/2026-10-18-g14-anal192d-b4/`):
  - **Properties:** `getprop` shows 55 and 12.
  - **Icons:** every taskbar icon is a circle in the laptop's own screen captures.
  - **No crash** from B4.
  - **Dim:** the wallpaper on screen matches its file (B6's Folio dark) pixel for pixel, ratio 1.002. That proves nothing about the dim, though: every B6 wallpaper carries a dark-theme or dark-text hint, so neither AOSP's 0.05 nor our 0 would dim it.
  - **Folio light, the default:** it sits at a mean luminance of about 0.701, just above AOSP's 0.70 dark-text threshold. B4's 55 leaves a wide margin.
  - **Found, not caused by B4:** Wallpaper & style crashes when a full wallpaper preview is opened from a desktop window. In AOSP's `WallpaperPreviewActivity`, the `onResult(result: Void)` callback is non-null in Kotlin, but the framework passes `null` on success. The fix is `Void?` (reported on ANAL-192).
- **Not checked yet:**
  - the lock screen, which is off by default on our desktop (`config_disableLockscreenByDefault`);
  - on the G14: All Apps, Settings and the Shape picker (the owner's photos), and `cmd overlay lookup` (the live collector doesn't record overlay values).

### 2.5 Pointer, sounds, boot animation, setup (C)

- **Pointer:**
  - Googlebook replaces 10 framework pointer shapes (20 drawables, each with an icon variant) with its own vector set in `FrameworkDesktopOverlay`, and adds 4 no-resize cursors in SystemUI.
  - We can't copy that art. AOSP 17 has vector pointer icons with fill and stroke styles, which we can theme with our own design.
- **Sounds:** Googlebook uses Google's set (`Soft_Mallets.ogg`, `Oxygen.ogg`, `product/media/audio/{ui,notifications,ringtones,alarms}`). We use AOSP's (`OnTheHunt.ogg`, `Alarm_Classic.ogg`). The 9to5Google review called Googlebook's default click sounds "very annoying". Googlebook's own `SettingsProviderDesktopOverlay` already sets `def_sound_effects_enabled=false` (C). OpenBook now does the same (§2.6).
- **Boot animation:** Googlebook ships `system/media/bootanimation.zip`; we have none.
- **Setup:** Googlebook runs Google's setup wizard (`setupwizard.theme=glif_expressive`); we run AOSP Provision.

**Done in ANAL-207 (B6): OpenBook's own wallpapers, boot animation, sounds and pointer** (`assets/README.md`; evidence `evidence/2026-10-17-brand-assets/`). Everything is drawn or synthesised by `scripts/brand/` from the brand palette and mark, CC-BY-4.0. No Google art, sample or font was copied or traced; Googlebook's own assets were not opened.
- **Wallpapers:** four designs, each light and dark, at 2880×1800 and 1920×1080: Folio (pages fanning out of the spine), Bloom, Strata and Tide.
  - The default, Folio light, is `default_wallpaper` in `AnyBookDesktopFrameworkOverlay`. AOSP has `nodpi`, `sw600dp` and `sw720dp` variants and the more specific one wins, so we override all three. The G14's 1200 dp wide screen uses `sw720dp`.
  - The set of eight is an "OpenBook" collection in Wallpaper & style. WallpaperPicker2 reads `res/xml/wallpapers.xml` from the partner customization package (ANAL-206's `AnyBookDesktopPartnerCustomization`; only one such package may exist).
  - Dynamic colour: `scripts/brand/monet.py` ports `WallpaperColors.fromBitmap` and `ColorScheme.getSeedColors` and predicts each wallpaper's seed and TonalSpot palette (`assets/wallpapers/monet.json`). The device's values are in the evidence.
- **Boot animation:** `/product/media/bootanimation.zip`, 480×480 at 30 fps on the brand's dark surface `#121318`. The pages unfold and the spark lights (`part0`, always played), the spark breathes until boot completes (`part1`), then the mark fades (`part2`).
- **Sounds:** one synthesised glass-mallet voice and one motif. Ringtone "Open Pages", notification "Spark", alarm "First Light", and the lock, unlock, trusted, low-battery and charging sounds.
  - `ro.config.*` sets the defaults; `OpenBookSoundsSettingsProviderOverlay` sets the UI sound paths. AOSP's sounds stay selectable.
  - Click and keypress sounds stay off (ANAL-206).
- **Pointer:** 20 of AOSP 17's vector pointer shapes are redrawn on AOSP's grid and hotspots. Not replaced: the wait spinner, touch spots and the handwriting pointer.
  - **How the colours work.** The accessibility fill (6 colours), stroke (white, black, none) and size settings still apply.
  - **Why the overlay replaces the nine colour styles.** Android applies the user's choice as the styles `PointerIconVectorStyleFill*` / `Stroke*`, which set private framework attributes. aapt2 lets no other package's XML refer to those attributes. It does accept them as style item names (`*android:pointerIconVectorFill`). So `OpenBookPointerOverlay` also replaces the nine styles: each keeps AOSP's items and adds the same colour under the overlay's own `openbookPointerFill` / `openbookPointerStroke`, which our vectors use.
  - **A first attempt that failed (C).** We compiled the overlay as resource package `android`, so that it could name the private attributes directly. The overlay was enabled, but Android ignored its values, and the framework kept loading AOSP's path data. aapt2 forces that package to ID 0x01, and Android treats 0x01 IDs in a dynamically loaded overlay as the framework's own (`DynamicRefTable`). Evidence: `pretest/`.
- **Measured in Cuttlefish** (the B6 build, `anybook-cf-b6`, 2026-10-18; 8/8 scripted checks, C):
  - **Boot animation:** it plays from `/product/media/bootanimation.zip` during boot (12 s, 28 frames captured), and on replay all three parts show.
  - **Default wallpaper:** a fresh `/data` shows Folio light, in both themes.
  - **Picker:** Wallpaper & style lists the OpenBook collection with all eight.
  - **Dynamic colour:** each wallpaper gives its own seed. The primary colour matches `monet.py` within 3 RGB units for 7 of 8 (Bloom light: 7).
  - **Pointer:** the framework's own loader draws our 20 shapes in all 6 fills and 3 strokes. A virtual mouse shows our arrow on screen; `skipScreenshot` is false in this build, so screencap includes it.
  - **Sounds:** the ringtone, notification and alarm settings point to Open Pages, Spark and First Light. MediaProvider indexed all 8.
- **Not covered:** the G14 (ANAL-192's stick), and listening to the sounds by ear.

### 2.6 Desktop clutter (C for OpenBook, R for Googlebook)

- **OpenBook before ANAL-206 (C):** the default desktop showed AOSP's legacy `QuickSearchBox` widget, a dark "Google" bar across the bottom (`fonts-prototype/before-settings.png`). It is Launcher3's hotseat search box, and Google's AOSP Desktop emulator image shows the same bar. The taskbar held Launcher3's tablet defaults: Calendar, Gallery, WebView Shell, Camera.
- **Googlebook (R):** reviewers describe its launcher as the Pixel Launcher's search, opened from the G key (9to5Google review, 2026-10-12).
- **Googlebook (C, from its overlays and flags):** touch sounds off by default (`SettingsProviderDesktopOverlay`), the screenshot shutter sound only when forced (`com.android.systemui.screenshot_remove_nonforced_sound`), and new apps not added to the desktop (`NexusLauncherOverlayDesktop`: `pref_add_icon_to_home_default=false`).
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
- ANAL-202 did the product build and the performance check (§3.1). The G14 is still to do.
- Upstream Google Sans Flex has no GRAD axis, so our `variable-*` families leave it out.
- The clock families map to Google Sans Flex.

### 3.1 In the product (ANAL-202)

**What ships** (C; `device/anybook/common/desktop/fonts/`, installed by `desktop.mk`, so both `anybook_cf_x86_64_pc` and `anybook_g14_x86_64` get it):
- **The fonts.** The three files from google/fonts `47d54ca1`, byte for byte, as `prebuilt_font` modules in `/product/fonts`. Their sha256 are in the directory's `README.md`.
  - They are named `GoogleSans-VF.ttf`, `GoogleSans-Italic-VF.ttf` and `GoogleSansFlex-VF.ttf`, because Soong reads the `[` in upstream's names (`GoogleSans[GRAD,opsz,wght].ttf`) as a glob.
  - `OFL.txt` and `TRADEMARKS.md` sit next to them.
- **Licence metadata.** Each family has its own `license` module (`SPDX-license-identifier-OFL-1.1`), pointing to its own `OFL.txt`, since the two copyright lines differ. Both texts reach `/product/etc/NOTICE.xml.gz`.
- **The font config.** `/product/etc/fonts_customization.xml` is the committed output of `scripts/ui/fonts-customization.py` (40 families).
  - The build runs the generator with `--check` on the committed file (a `python_binary_host` and a `genrule`), and installs it only if the two match. If someone edits one without the other, the build fails.
- **Framework values.** `AnyBookDesktopFrameworkOverlay` sets the four `config_*FontFamily` values Googlebook uses (table in [`aosp-desktop.md`](aosp-desktop.md)).

**Measured in Cuttlefish** (C; `evidence/2026-10-17-typography/`; base `c861cf4` against the fonts build, both products built; Radeon 610M, `gfxstream_guest_angle`):
- **Fonts loaded.** The device's font manager lists all 40 families, and the four overlay values resolve to `google-sans`, `google-sans-medium`, `google-sans-text` and `google-sans-text-medium`.
- **What changes on screen.** Settings, window captions, Quick Settings, notifications, all apps and Files render in Google Sans.
  - Settings' rows grow by about a quarter (roughly 75 → 94 px at 160 dpi), because Google Sans has taller line metrics than Roboto.
- **Desktop unchanged.** `scripts/desktop-capture.sh` still shows freeform windows with captions and the taskbar.
- **No crashes or new denials.** The crash buffer was empty in every run, and the same three SELinux denial kinds (all Cuttlefish's own) appear with and without the fonts.
- **Size.** `product.img` grows by 9.24 MiB in both products. The files are 13.98 MB; EROFS compresses them. No other image changes.
- **Settings scroll** (`scripts/cf-gfx-bench.sh`, three alternating base/fonts pairs on a busy host):
  - janky frames 1.35 % with the fonts against 4.32 % without; median p90 15 ms against 20 ms. The fonts build was better in every pair.
  - **HYPOTHESIS:** the taller rows mean each swipe binds fewer new rows. So this shows no regression, not a faster font.

- **With B2, B4 and B5.** After merging them, both products build again. In Cuttlefish that image shows Google Sans together with the circular icons and the taskbar without the search bar, with the same health results (`merged/`).

**On the G14** (C, the owner's `anal192d` session, 2026-10-18; `evidence/2026-10-18-g14-anal192d-typography/`):
- **Logs.** No font warning or error, and no font-related SELinux denial under enforcing.
- **Crashes.** The crash buffer holds one crash, the wallpaper preview's (`com.android.wallpaper`), which is not font-related.
- **On screen.** The laptop's own screenshot shows the window caption and the status bar in Google Sans at 240 dpi, unclipped.
- **The installer.** Its own text stays in Roboto, by its design.

**Not checked yet:** the G14 photos of Settings, Quick Settings, notifications and all apps (clipped text), and non-Latin text.

## 4. Beautification backlog (alpha → beta)

The owner approved every item on 2026-10-17. Each one is a sub-issue of ANAL-201, and all are being worked in parallel.

| # | Issue | Item | Size | Needs |
|---|---|---|---|---|
| B1 | ANAL-202 | **Fonts in the product:** the three OFL fonts with `OFL.txt` (prebuilt modules with licence metadata), the generated `fonts_customization.xml`, and the four values in `AnyBookDesktopFrameworkOverlay`. Then the desktop capture in Cuttlefish and the G14 checklist. **Done in both products (ANAL-202); measured in Cuttlefish (§3.1); the G14 check is on ANAL-192's stick** | small | — (approved) |
| B2 | ANAL-203 | **Blur on the G14.** `ro.surface_flinger.supports_background_blur=1`; check frame times on the 890M. **Done in the product (ANAL-203); measured in Cuttlefish; the G14 check is on ANAL-192's stick** (§2.3) | small | — |
| B3 | ANAL-204 | **Flag set v2.** Evaluate the 128 UI flags AOSP 17 declares, in groups. Start with box shadows, blur on more surfaces, resizing (`perfect_edge`, no-resize cursor, fluid resizing) and taskbar clicks. `scripts/desktop-flags.py` already writes the value set | medium | — |
| B4 | ANAL-205 | **Shape and wallpaper values:** circular icon mask, round icons, wallpaper dim 0, wallpaper colour thresholds. **Done in Cuttlefish (§2.4); the G14 check is on ANAL-192's stick** | small | — |
| B5 | ANAL-206 | **A clean default desktop:** remove the QuickSearchBox widget and the app, set taskbar pins (Files, Settings, browser), quiet sounds. **Done in Cuttlefish and on the G14 product in QEMU (§2.6); the G14 check is on ANAL-192's stick** | small | Pins proposed in the PR; the owner reviews |
| B6 | ANAL-207 | **Brand assets:** wallpapers (our own or CC0/CC-BY, not bulk Unsplash), a sound set with click sounds off by default, a boot animation, a pointer theme. Based on the brand mark in `assets/brand/`. **Done in Cuttlefish (§2.5); the G14 check is on ANAL-192's stick** | medium | Owner reviews the visuals in the PR (contact sheet) |
| B7 | ANAL-208 | **Document fonts:** the metric-compatible fonts, for web and Office fidelity. Done for the 7 public families (17 of the 42 files; §2.1.1): Arial, Times New Roman, Courier New, Georgia and Comic Sans MS render in them, in WebView and the framework (Cuttlefish). G14 check on the next stick | small | The other 13 families wait for Google to publish them |
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
