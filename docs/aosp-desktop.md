# Desktop windowing and VM graphics on our AOSP 17 PC build (Track A, M2)

This is the desktop configuration every OpenBook product inherits (`device/anybook/common/desktop`): what makes AOSP 17 boot into the Android desktop, every overlay value and flag we set and why, and the Cuttlefish GPU modes used to test it in a VM. It started under ANAL-169 (2026-10-16). Building AOSP itself is in `docs/aosp-build.md`; the Googlebook look on top is in `docs/googlebook-ui.md`.

## What it looks like

`anybook_cf_x86_64_pc-cp2a-userdebug` (Android 17, `CP2A.260605.016`) boots in Cuttlefish straight into the Android desktop, with the same window behaviour as Google's AOSP Desktop (Preview) emulator image (`sdk_gdesktop_x86_64`, `CLE1.260506.004`), called **the reference** below:

- Apps open as freeform windows inside a `Desk` root task, with caption bars (app menu, minimize, maximize, close). `dumpsys activity activities` shows `Task{… name=Desk … mode=freeform}` holding the apps, each `mode=freeform`.
- The taskbar is pinned and centred, with the all-apps button, pinned apps, running-app indicators and no navigation buttons.
- The desktop status bar shows the clock and date on the left and the notification icon on the right.
- Home (Launcher3) is visible behind the desk, as on the reference (`show_home_behind_desktop`, see [aconfig flags](#aconfig-flags)).
- The default display's settings entry is `mWindowingMode=5`. WM Shell reports `Display#0 isDesktopFirst=true`; Launcher reports `isInDesktopFirstMode=true, showDesktopFirstTaskbar=true`.
- With `CF_GPU=amd`, SurfaceFlinger renders on the host's AMD iGPU through gfxstream. On the build host's Radeon 610M: `GLES: … ANGLE (AMD, Vulkan 1.4.305 (Virtio-GPU GFXStream (AMD Radeon Graphics (RADV RAPHAEL_MENDOCINO))))`. With two windows open there are 11 layers (wallpaper, Home, status bar, taskbar, two tasks, two captions, three app surfaces). RenderEngine composes all of them on the GPU (`CLIENT`) and hands one buffer to the `ranchu` HWC, as the reference does.

`scripts/desktop-capture.sh` captures the same state from both images and `scripts/desktop-compare.py` diffs them. As of 2026-10-16, no desktop-related aconfig flag, `persist.wm.*` property, characteristics or large-screen property differs. Every remaining difference is in [Differences from the Google desktop image](#differences-from-the-google-desktop-image).

## What turns desktop mode on in AOSP 17

**CONFIRMED** by reading the AOSP source at manifest `ad156f32` (`android17-release`), and checked on the device:

1. **`FEATURE_PC` no longer makes the display freeform.**
   - `DisplayWindowSettings.java` (`services/core/java/com/android/server/wm`) only forces freeform for PCs when `disable_display_force_freeform_on_pc` is off.
   - cp2a turns that flag on (`build/release/aconfig/cp2a/com.android.window.flags/`).
   - So a build with `android.hardware.type.pc` and `freeform_window_management` still opens apps fullscreen.
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
   - Otherwise it switches the display back to fullscreen. Checked in the VM with the force property off:
     - **Keyboard only:** `targetWindowingModeForDefaultDisplay=1`, and Settings opens fullscreen. The `display_settings.xml` value alone gets overridden.
     - **`--touchpad=width=1280,height=800` plus the virtio keyboard:** `targetWindowingModeForDefaultDisplay=5` and `hasAnyTouchpadDevice=true`. Apps launched from Home open in a freeform `Desk`.
   - So a real laptop gets desktop-first without the "for testing" property, as long as its keyboard and touchpad count as internal devices. The VM uses the property, as Google's emulator image does.
4. **Launch placement.**
   - `DesktopModeLaunchParamsModifier.java:457-487` (`enable_desktop_first_top_fullscreen_bugfix`): on a desktop-first display, a new task stays fullscreen if no desk is active and Home is not visible. The log line is `desktop-first-but-fullscreen-visible`.
   - Gotcha: an `am start` issued while the keyguard is still dismissing opens fullscreen, and so does the next app after it. `scripts/desktop-capture.sh` waits for Home before it launches anything.
5. **Taskbar.**
   - Launcher3's `TaskbarFeatureEvaluator.kt` pins the taskbar when the display is in desktop mode, or when it is a desktop-first freeform display (`SystemWindowManagerProxy.showDesktopTaskbarForFreeformDisplay`).
   - Navigation buttons follow `config_navBarInteractionMode`. Gestural (2) removes them, as on the reference image.

## The OpenBook desktop configuration

Everything is in a device tree inside this repo. `scripts/aosp-build.sh` copies it into the AOSP tree on every build: `rsync --delete` to `device/anybook`, because Soong's nsjail sandbox only sees `/aosp/src`.

```
device/anybook/
  AndroidProducts.mk                       lunch anybook_cf_x86_64_pc-cp2a-userdebug (and the PC products)
  common/desktop/                          reusable by any OpenBook product (VM or bare metal)
    desktop.mk                             characteristics, large_screen_common, the RROs, release config map
    Android.bp                             AnyBookDesktop{Framework,SettingsProvider,SystemUI,Launcher,LatinIME}Overlay,
                                           AnyBookDesktopPartnerCustomization (all /product)
    overlays/framework/res/values/config.xml
    overlays/systemui/res/values/config.xml
    overlays/settingsprovider/             first-boot settings: screen off after 10 min, no touch sounds
    overlays/launcher/                     Launcher3: no search box in the hotseat (ANAL-206)
    overlays/latinime/                     on-screen keyboard: no keypress sound (ANAL-206)
    partner/                               Launcher3 partner customization: first home screen, taskbar pins (ANAL-206)
    fonts/                                 Google Sans and Google Sans Flex (OFL) -> /product/fonts; the generated
                                           fonts_customization.xml (40 families) -> /product/etc (ANAL-202)
    release/                               aconfig value set "aconfig_value_set-anybook_desktop-cp2a" (163 flags: 79 from
                                           the reference image, 84 from ANAL-204) and OpenBook's own picks,
                                           release/openbook/ (5 flags: the screenshot sound, ANAL-206; four for
                                           Quire, ANAL-216, docs/quire.md)
  cuttlefish/
    anybook_cf_x86_64_pc.mk                aosp_cf_x86_64_pc + desktop.mk + the VM-only pieces below
    display_settings.xml                   port:0 windowingMode=5 ignoreOrientationRequest=true (-> /product/etc)
```

Bare-metal products inherit `device/anybook/common/desktop/desktop.mk` but not the VM-only force property or the port-0 display settings. On the G14 (`docs/g14-product.md`), the input configuration files mark the built-in keyboard and touchpad as internal, and that is what makes WM Shell put the panel into desktop mode.

### Every overlay value and property

**Reference** means Google's emulator image, read offline from its partitions.

**Framework RRO** (`dev.anybook.overlay.desktop.framework`, target `android`, static, /product)

| Config | Value | Reference | Why |
|---|---|---|---|
| `config_isDesktopModeSupported` | true | true (vendor RRO) | WM Shell device gate |
| `config_canInternalDisplayHostDesktops` | true | true | internal display may host desks |
| `config_enterDesktopByDefaultOnFreeformDisplay` | true | true | taskbar/launch default; the bugfix flag forces the same in cp2a |
| `config_showHomeBehindDesktop` | true | true | read only when `show_home_behind_desktop` is on (it is; see flags) |
| `config_showNavigationBar` | true | true | |
| `config_navBarInteractionMode` | 2 (gestural) | 2 | no nav buttons in the taskbar |
| `config_showGesturalNavigationHints` | true | true | |
| `config_allowPresentationOnInternalDisplay` | true | true | |
| `config_globalActionsList` | emergency, lock, power, restart, logout, screenshot, bugreport | same | power menu |
| `config_supportsCamToggle`, `config_supportsMicToggle` | true | true | privacy toggles |
| `config_lockPatternVisibleDefault` | false | false | |
| `config_lockPinEnhancedPrivacyDefault` | true | true | |
| `config_magnification_keep_zoom_level_when_context_changed`, `config_magnification_magnify_keyboard_default` | true | true | |
| `config_icon_mask` | circle, our own path (`M50,0 A50,50 0 1,1 50,100 A50,50 0 1,1 50,0 Z`) | circle (a cubic-Bézier path); Googlebook the same | Googlebook's icon shape (ANAL-205, [`googlebook-ui.md`](googlebook-ui.md) §2.4). A shape the user picks in Wallpaper & style still wins in Launcher3 |
| `config_useRoundIcon` | true | true; Googlebook the same | PackageManager hands out `android:roundIcon` where an app has one (ANAL-205) |
| `config_wallpaperDimAmount` | 0 | AOSP default 0.05; Googlebook 0 | no 5 % default dim on wallpapers that support neither dark text nor a dark theme (ANAL-205) |
| `config_headlineFontFamily`, `config_headlineFontFamilyMedium` | `google-sans`, `google-sans-medium` | not set (AOSP defaults: empty, `@string/font_family_button_material`); Googlebook the same as ours | headlines in Google Sans, as on Googlebook (ANAL-202, [`googlebook-ui.md`](googlebook-ui.md) §2.1). The families are defined in `fonts/fonts_customization.xml` |
| `config_bodyFontFamily`, `config_bodyFontFamilyMedium` | `google-sans-text`, `google-sans-text-medium` | not set (AOSP defaults: `sans-serif`, `sans-serif-medium`); Googlebook the same as ours | running text in Google Sans Text (ANAL-202) |
| `config_defaultRefreshRate`, `config_defaultPeakRefreshRate` | 0, 1000 | not set (AOSP defaults: 60, 0); Googlebook 0, 1000 | no 60 frames-a-second render cap: each panel draws up to its own top rate, and SurfaceFlinger still lowers it for content (ANAL-212, [`graphics-amd.md`](graphics-amd.md) "Refresh rate") |

These reference values are left out:
- **Look and feel:** `config_buttonTextAllCaps=false`.
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
| `persist.wallpapercolors.threshold=55`, `persist.wallpapercolors.max_dark_area=12` (ANAL-205) | desktop.mk | unset (AOSP defaults 70 and 5); Googlebook sets 55 and 12 in `/product/etc/build.prop` |
| `openbook_fonts_customization.xml` and the three fonts it requires: `/product/fonts/GoogleSans-VF.ttf`, `GoogleSans-Italic-VF.ttf`, `GoogleSansFlex-VF.ttf` and `/product/etc/fonts_customization.xml` (ANAL-202) | desktop.mk | none; Googlebook ships Google Sans, Google Sans Flex and a 40-family `fonts_customization.xml` in `/product` |
| `persist.wm.debug.force_desktop_first_on_default_display_for_testing=true` | cuttlefish product only | same |
| `/product/etc/display_settings.xml`: `port:0 windowingMode=5 ignoreOrientationRequest=true` | cuttlefish product only | `/vendor/etc/display_settings.xml`: `local:<id> windowingMode=5 ignoreOrientationRequest=true` |

### The default desktop: no search box, taskbar pins, quiet sounds (ANAL-206)

AOSP's Launcher3 puts a search box in the hotseat, above the taskbar. It hosts the search engine's widget: on a stock build AOSP's `QuickSearchBox`, a dark "Google" bar (Google's AOSP Desktop emulator image shows the same bar). Googlebook has no search box on its desktop. Its search opens from the launcher (`docs/googlebook-ui.md` §2.6).

**What we change and why it works this way** (read in the AOSP 17 tree, `android17-release`):

| Change | Where | Mechanism |
|---|---|---|
| **No search box.** The hotseat's search slot is an empty view | `AnyBookDesktopLauncherOverlay` (`dev.anybook.overlay.desktop.launcher`, target `com.android.launcher3`): `layout/qsb_container_hotseat` | Launcher3 always creates this view (`qsb/QsbWidgetFactory.kt`), and there is no config to hide it. Without a search app it shows a "Search" button that opens a blank browser page (`OseWidgetView.getErrorView`). An empty view is what Launcher3 uses itself where it wants none (`NoOpQsbFactory`); it is only ever referenced, never looked up by id. An RRO needs no Launcher3 patch |
| **No `QuickSearchBox` app** | the same RRO: `overrides: ["QuickSearchBox"]` | `handheld_product.mk` adds it, and inherited `PRODUCT_PACKAGES` can't be filtered out; a module that overrides it keeps it from being installed, in Soong-only (Cuttlefish) and Make (G14) builds alike |
| **Taskbar pins** Files, Settings, browser, Calendar, Gallery, Camera; no desktop icons | `AnyBookDesktopPartnerCustomization` (`dev.anybook.desktop.partner`): `res/xml/partner_default_layout.xml` | Launcher3 builds a new home screen from, in order: a layout set through `launcher3.layout.provider`, a Play auto-install package, **a system app with a receiver for `com.android.launcher3.action.PARTNER_CUSTOMIZATION`**, then its own `default_workspace_6x5.xml` (`model/LayoutParserFactory.kt`, `ModelDbController.loadDefaultFavoritesIfNecessary`). On a desktop the taskbar shows the hotseat. The partner layout doesn't depend on which grid Launcher3 picks |
| **Launcher3 in its desktop form factor** | the same RRO: `bool/desktop_form_factor` and `bool/reduce_workspace_blur_usage`, both true (ANAL-352) | Googlebook's launcher overlay (`NexusLauncherOverlayDesktop`) sets both. In AOSP 17 they gate code behind flags our value set already enables: `enable_mouse_interaction_changes` and `enable_cursor_driven_workflows` (`Utilities.shouldEnable*`: a persistent page indicator, no long-press menu from a mouse), no taskbar education tooltips, desktop taskbar stashing with the dual shade, and `reduce_workspace_blur_usage` (All Apps and the widget picker leave the desktop sharp instead of blurring and zooming it). Contextual search from Launcher3 stays on because `enable_contextual_search_desktop_entrypoints` is enabled |
| **No touch sounds** | `AnyBookDesktopSettingsProviderOverlay`: `def_sound_effects_enabled=false` | The value Googlebook's `SettingsProviderDesktopOverlay` sets. Applied when `/data` is created |
| **No keypress sound** in the on-screen keyboard | `AnyBookDesktopLatinIMEOverlay`: `config_default_sound_enabled=false` | AOSP LatinIME turns it on for screens of 600 dp and up (`values-sw600dp`, `values-sw768dp`), i.e. every desktop. It plays through `AudioManager.playSoundEffect(type, volume)`, which ignores the Touch sounds setting |
| **No screenshot shutter sound** unless a region requires it | `release/openbook/cp2a/`: `com.android.systemui.screenshot_remove_nonforced_sound` (ENABLED, READ_ONLY) | Googlebook enables this flag; the reference emulator image doesn't, so `scripts/desktop-flags.py` would never add it. It lives in a second, hand-kept value set because the script rewrites `release/aconfig/` |
| **Drag a pinned app off the taskbar** to unpin it, with Undo | `release/openbook/cp2a/`: `com.android.launcher3.enable_taskbar_drag_to_remove` (ENABLED, READ_ONLY); OpenBook Launcher's quickstep input fix | AOSP 17 has the code (`TaskbarViewDragDropController.UnpinDropTarget`): dropping a pin in the band just above the taskbar shows "Remove", then "App removed from Taskbar" with Undo. The delete is written when the snackbar closes, so a reboot within its 6 s brings the pin back. Off in AOSP's release config and on the reference image. On the home screen a mouse drag up off the taskbar could be taken as swipe-up-to-home, which left the drag stuck; the fork now routes a mouse there as it does over apps (ANAL-359) |
| **New apps stay off the desktop** ("Add app icons to home screen" starts off) | the same RRO: `bool/pref_add_icon_to_home_default=false`; OpenBook Launcher reads it (ANAL-361) | Googlebook's launcher overlay sets the same value. AOSP 17 hard-codes the default to on (`DefaultsValueProvider.addIconToHome`); the fork reads it from this resource, true unless an overlay says otherwise, in `BaseDefaultsValueProvider` and as the Settings switch's `defaultValue`, so opening Home settings shows and stores the same default. It gates both ways an install reaches the desktop: the session-commit broadcast (`SessionCommitReceiver`) and the promise icon (`InstallSessionHelper.tryQueuePromiseAppIcon`). A value already stored wins: an install where Home settings was opened before this change keeps "on" until the person turns it off. An app's own pin request ("Add to home screen") is unaffected |
| **Two-line app names** in All Apps | the same RRO: `bool/pref_enable_two_line_toggle_default=true`; OpenBook Launcher reads it (ANAL-362) | AOSP 17 has the code behind the stored preference `pref_enable_two_line_toggle`, whose default it hard-codes to false, with no setting to change it. Its gate flag `enable_twoline_toggle` is already on; `enable_twoline_allapps` has no reader. A name breaks between words after what fits the first line. The fork fixes two things (`TwoLineLabels`): a name longer than two lines keeps both, the second ending in "…" (AOSP fell back to one line), and All Apps cells that already fit two lines keep their height (AOSP grew every cell by a line), so the desktop grid's rows don't change. As in AOSP: English only, and a first word wider than the cell stays on one line ending in "…". Desktop icons keep one line |
| **Type to search** on the desktop | OpenBook Launcher's `TypeToSearch` (ANAL-363); no value | With the home screen focused and nothing open over it (no window, or all minimized), a key that types a character opens All Apps with that character in its search field, and the next keys follow. AOSP 17 does this only once All Apps is open (`AppsSearchContainerLayout.preDispatchKeyEvent`); on the home screen the key went to `Activity`'s default key handling and nothing happened. With `all_apps_surface` (enabled in `release/aconfig/cp2a/`) the desktop's All Apps is the taskbar's, in its own window, and with `enable_taskbar_ui_thread` on the taskbar's thread: the fork queues the keys and has the taskbar open it ready for typing, as its search shortcut does, so keys typed before that window has focus aren't lost. The home screen's bounce hint doesn't block it. Ctrl, Alt and Meta shortcuts, dead keys, a folder or menu that is open, and apps that have focus keep their keys. Enter in the search field opens the first result in the All Apps panel (ANAL-370); AOSP 17's search never marks one, so in AOSP's sheet (the transient taskbar, other displays) Enter still opens nothing |
| **Glass taskbar** with our apps pill and one line of state per app | OpenBook Launcher's `OpenBookTaskbar`, `TaskbarGlass` and `res/values/openbook_tokens.xml` (ANAL-369); no value | The design is `launcher-design.md` §2. The bar keeps AOSP's 56 dp, so insets and app frames don't change; it becomes glass: the platform's 34 dp blur on the taskbar window's own region (`BackgroundBlurDrawable`) under the surface colour at 80 %, or a 96 % tint while blur is off. 48 dp targets 4 dp apart, the row 2 dp above centre; a 56 × 40 dp apps pill with our glyph, `primary` while All Apps is open. Under each app, on the bar: running, in front (the task WM Shell reports focused), several windows (a dot), minimized (hollow); AOSP 17's `RunningAppState` has neither in front nor a window count, and its bounce is off. Hover layer, press scale (tracked from touch events: the taskbar's cursor-driven gestures never set a view pressed), a 2 dp focus ring and a restyled tooltip after 500 ms. Tab on the empty desktop puts keyboard focus on the pill (AOSP's taskbar can't be reached by keyboard); Tab and the arrows walk it, Esc or a window coming to the front gives focus back. AOSP's one divider sits after the pill, or between pinned and unpinned running apps when there are any. The transient taskbar keeps AOSP's look |
| **All Apps as a centred glass panel** | OpenBook Launcher's `AllAppsPanel`, `AllAppsPanelCells` and `res/values/openbook_tokens.xml` (ANAL-370); no value | The design is `launcher-design.md` §3. All Apps from the taskbar (the pill, Meta, or typing on the desktop) is a 720 dp panel centred 12 dp above the taskbar with 28 dp corners, in place of AOSP's full-width sheet with its handle and scrim. Its height fits the apps, at most 640 dp, and stays put while searching. Glass: the platform's 34 dp blur on the panel's own bounds (`BackgroundBlurDrawable`), so the desktop stays sharp, or a 96 % tint while blur is off. A 48 dp field with focus from the start; a 6-column grid of 112 × 104 dp cells with two-line 13/16 labels; hover and pressed layers; a 2 dp ring for keyboard focus. The first app a search finds is the top hit and Enter opens it (AOSP 17's search never marked one, so Enter did nothing); ↓ or Tab goes into the grid, ↑ or Shift+Tab back; Esc clears the text, keeping the field focused, then closes. Opens on a spring, closes in 150 ms. The transient taskbar and other displays keep AOSP's sheet |
| **One glass menu** | OpenBook Launcher's `OpenBookMenu`, `OpenBookMenuContent`, `TaskbarMenu`, `GlassDrawable` and `res/values/openbook_tokens.xml` (ANAL-371); no value | The design is `launcher-design.md` §4. Right-clicking the desktop, a taskbar icon or an All Apps icon opens one glass menu, in place of AOSP's popup with its arrow: 16 dp corners, 36 dp rows, 20 dp icons, labels at 14/20, hints at 12/16 and dividers. Desktop menus open at the pointer and flip at the screen's edges; a taskbar icon's is centred over it, 8 dp above the bar. The desktop's lists Wallpaper & style and Widgets, then Display settings (ours) and Home settings. A taskbar icon's lists the app's name and windows (a click brings one to the front), New Window with "Middle-click", Remove from Taskbar, App info and "Close *n* windows". Shift+F10 or the menu key opens the focused item's menu with its first row focused; arrows move, Enter activates, Esc closes. A taskbar folder's menu gets the same glass and rows. A menu with more rows than the screen has room for scrolls; opened by touch, its rows are 48 dp. Opens on `spring.panel`, closes in 100 ms (ANAL-373) |
| **Overview for desks** | OpenBook Launcher's `OverviewDesks` and `res/values/openbook_tokens.xml` (ANAL-372); the image grants `READ_WALLPAPER_INTERNAL` (`device/anybook/common/desktop/privapp-permissions-launcher3-overview.xml`) | The design is `launcher-design.md` §5. Overview's backdrop is the wallpaper blurred at 34 dp under a light tint (`surface` at 18 % light, 30 % dark), instead of AOSP's scrim and wallpaper zoom; All Apps keeps its own rule. A desk's tile draws the wallpaper behind its windows and has the display's shape (16:10 on the G14); app tiles keep their window's shape. Tiles have 20 dp (desk) or 16 dp (app) corners, a lit outline and a soft shadow; hovering lifts a tile 4 dp, and keyboard focus draws a two-colour ring (WCAG technique C40: at least 3:1 against any solid colour; over OpenBook's eight wallpapers a sampled model gives at least 3.05:1). Each tile's label is a glass chip above it; a desk's lists its apps. Clear all is a glass chip centred above the taskbar. With a live wallpaper, desk tiles keep AOSP's flat colour |
| **One motion system** | OpenBook Launcher's `OpenBookMotion` (ANAL-373); no value | The design is `launcher-design.md` §7. Three springs and three durations, the same as Quire's: `spring.panel` 500/0.90, `spring.settle` 700/0.90, `spring.tick` 1400/0.70, `duration.fade` 120 ms, `duration.hover` 100/150 ms, `duration.exit` 150 ms (menus 100 ms). Geometry moves on springs, opacity and colour on durations, and Remove animations makes every one a cut. The taskbar, All Apps, the menus, a taskbar folder's menu (AOSP's 200/233 ms popup), the tooltip and Overview's hover lift use them, and so does the launcher's own All Apps state on a desk (AOSP's 500/100 ms). A window's own open, minimize and restore are WM Shell's and keep AOSP's motion |

**Pins in detail** (`partner/res/xml/partner_default_layout.xml`):
- **Files:** DocumentsUI's launcher entry has `APP_FILES` but no `DEFAULT` category, so a `<resolve>` by category alone misses it; the component `com.android.documentsui/.LauncherActivity` is the fallback.
- **Browser:** whatever handles `APP_BROWSER` or `http` when Launcher3 creates its database. With no browser in the image, on a fresh `/data` that is AOSP's WebView Shell ("WebView Browser Tester").
- **Camera:** Camera2's `SetActivitiesCameraReceiver` disables its launcher entry at every boot when the device has no `android.hardware.camera{,.front,.external}` feature, and Launcher3 drops pins for disabled components. So the pin only stays where a camera exists.
- The layout is read once, when Launcher3 creates its database (new `/data` or cleared Launcher data). Existing installs keep their pins.

**What depends on `QuickSearchBox`** (checked before removing it):
- **Global search** (`android.search.action.GLOBAL_SEARCH`): `SearchManager.startGlobalSearch` logs "No global search activity found" and returns. `DefaultPermissionGrantPolicy` skips the grant.
- **Launcher3's search box fallback:** covered by the empty view above.
- **Settings search** goes to SettingsIntelligence (`com.android.settings.action.SETTINGS_SEARCH`), not to `QuickSearchBox`.
- **The search key** (`KEYCODE_SEARCH`) starts `config_searchKeyTargetActivity` or `ACTION_WEB_SEARCH`; with no handler `PhoneWindowManager` logs "Not launching app" and carries on.
- The All Apps search in Launcher3 is its own and stays.
- Only two sysconfig allowlists in `build/make` name the package.

**Left as they are:**
- **Lock and unlock sounds** (`lockscreen_sounds_enabled`). Googlebook keeps them on, and SystemUI's unlock sound at boot is the G14 checklist's SoundPool probe (`docs/g14-audio-net.md`).
- **Charging, power and dock sounds:** the AOSP defaults, as on Googlebook.
- **The screenshot flash.** No setting exists: `ScreenshotController` always flashes for a full-screen capture. Only a SystemUI patch could remove it.

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
- The map lives at `device/anybook/common/desktop/release/` on purpose. `build/make/core/release_config.mk` auto-loads maps from `device/*/release/` and `device/*/*/release/` for **every** product, and `aosp_cf_x86_64_pc` is still built from the same tree. Because this map is not auto-loaded, `aosp_cf_x86_64_pc` keeps the stock cp2a flags.
- In a cp2a build, a flag that is read-only and disabled doesn't appear in `aflags list` at all; it is compiled out. So a diff taken before the value set shows most of them as "—".

**What they change (checked in Cuttlefish).** The desktop status bar gains the date and the notification icon, and Home sits behind the desk instead of WM Shell's desktop wallpaper activity, both as on the reference. Windowing and the taskbar are the same with and without them.

**Risk (HYPOTHESIS).** Google ships these 79 flags on Android 17. We have no regression tests for them beyond the boot, the desktop capture and the scroll benchmark.

#### Flag set v2: the Googlebook flags (ANAL-204)

Googlebook enables 218 more flags that our tree declares. ANAL-204 triaged all of them and enabled **84**, in six groups, in the same value set. Details are in [`googlebook-flags.md`](googlebook-flags.md); the record is `device/anybook/common/desktop/release/googlebook-triage.tsv`.

- `scripts/desktop-flags.py --list <triage.tsv> [--groups ...]` writes them. Each value file's first line names its source, so `--list` and the diff mode above each regenerate only their own files.
- **Two flags break AOSP 17's desktop and stay off (C):**
  - `enable_add_window_decoration_to_all_tasks`: SystemUI crashes when a minimized window is restored from the taskbar.
  - `start_on_gone_scene_if_no_lockscreen`: the notification shade is empty. Our framework overlay disables the lock screen, so SystemUI would start on the Gone scene, and the keyguard section that binds the notification stack never runs.
- **23 do nothing:** nothing in our tree reads them, e.g. `perfect_edge` and `enable_taskbar_icon_desktop_clicks`.
- **Visible on the desktop (C, Cuttlefish):** box shadows and a 1 px border on windows, stepped cascading, the windowing pill inside the maximize menu, QS tile tooltips, power-menu blur, and a Cast tile that works over Ethernet.
- The G14 checks are on ANAL-192.

## Cuttlefish GPU modes

**Build host** (as of 2026-10-16): Ryzen 9 7950X with a Radeon 610M iGPU (`/dev/dri/renderD129`, Mesa 26.2.4 on the host) and an RTX 4090 (`renderD128`, NVIDIA 615.78.08). No root. Both render nodes and `/dev/nvidia*` are mode 0666, so they can be passed to Docker without sudo.

**Container.**
- `tools/Dockerfile.cuttlefish` (image `anybook-cuttlefish`) is the pinned `cuttlefish-orchestration:1.56.0` image plus `mesa-vulkan-drivers`, `vulkan-tools`, `libegl-dev` and `libgles-dev` (Debian 13, Mesa 25.0.7).
- The base image has Mesa's GL drivers. It has no Vulkan ICD and no unversioned `libGLESv2.so`, which gfxstream and `graphics_detector` dlopen.

**How a GPU gets in** (`scripts/cf-boot.sh`).
- `CF_GPU=amd` passes the AMD render node and sets `EGL_PLATFORM=surfaceless`. Mesa's default platform needs X11 or Wayland; without it, `graphics_detector` reports "Failed to initialize display".
- `CF_GPU=nvidia` passes `/dev/nvidia{0,ctl,-modeset,-uvm}` and the render node. It bind-mounts the host's NVIDIA userspace read-only: `libnvidia-*.so.<ver>`, `libEGL_nvidia`, `libGLX_nvidia` (the Vulkan ICD), `libGLESv2/v1_nvidia`, plus the glvnd and Vulkan ICD JSONs.
- `CF_GPU_MODE` is passed to `--gpu_mode`. The default stays `guest_swiftshader` with no host GPU.

**Modes compared** (2026-10-16). Boot on `aosp_cf_x86_64_pc`; frame times from `scripts/cf-gfx-bench.sh` (40 scripted swipes over the Settings list, read from `dumpsys gfxinfo`, two rounds) on `anybook_cf_x86_64_pc`. Indicative only: the swipes are injected, HWUI measures the Settings process only, the display is 60 Hz, and the host was shared (load average 2–7).

| `CF_GPU` | `--gpu_mode` | Boot | Renderer reported by SurfaceFlinger | Janky frames | Frame time p50 / p90 / p99 |
|---|---|---|---|---|---|
| none | `guest_swiftshader` (default) | yes, 17 s | ANGLE → SwiftShader Vulkan **in the guest** (CPU) | 10.1% / 31.5% | 5–7 / 32–61 / 65–89 ms |
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
- Without a GPU, `gfxstream_guest_angle_host_swiftshader` is the better software mode: 0.3–0.7% janky against 10–31%.

**Notes.**
- At startup, `assemble_cvd` warns that the host "does not have a non-software implementation Vulkan driver" for RADV, because `graphics_detector` reports the 610M as `TYPE_OTHER`. The warning is wrong: the SurfaceFlinger renderer string shows RADV.
- **Why `drm_virgl` fails (CONFIRMED for AOSP's crosvm).** A minimal crosvm with only `--gpu=backend=virglrenderer,…` crashes even with no host GPU, while the same command with gfxstream context types starts.
  - Debian `cuttlefish-base` 1.57.0 crosvm: SIGSEGV.
  - AOSP's prebuilt crosvm (from our `cvd-host_package`): SIGABRT with `Failed to create virtio gpu worker thread: invalid rutabaga build parameters`.
  - With `CF_HOST_TOOLS=build` the main crosvm core-dumps (`si_code: 3`). That launcher does not fail fast, so `cvd create` waits until its timeout.
  - The likely reason (**HYPOTHESIS**) is that both were built without the virglrenderer rutabaga backend. Not pursued: gfxstream covers the need.

## Commands

The product builds for device `anybook_vsoc_x86_64` (since ANAL-174, `docs/graphics-amd.md`), so `scripts/cf-boot.sh` needs `CF_DEVICE=anybook_vsoc_x86_64` for it.

```bash
docker build -t anybook-cuttlefish -f tools/Dockerfile.cuttlefish tools/          # 17 s
# Build the desktop product: it copies device/anybook into the tree.
AOSP_JOBS=32 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug
docker wait anybook-aosp-build
# Boot on the AMD iGPU, capture the desktop state, run the scroll benchmark, tear down.
export CF_DEVICE=anybook_vsoc_x86_64 CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_LOGS=$HOME/anybook/logs/desktop/run1
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

**Build cost** (2026-10-16, incremental builds, container cgroup peaks):
- Changing `PRODUCT_CHARACTERISTICS` relinks every app's resources: 12 min 38 s, 8,263 actions, 48 GiB RAM plus 52 GiB swap, with host `MemAvailable` at 0.0 GiB for a few minutes. No OOM kills.
- Adding the 79 flags rebuilds framework, SystemUI, Launcher3 and DocumentsUI: 24 min 50 s, 9,918 actions, 48.7 GiB RAM plus 16.6 GiB swap.
- **HYPOTHESIS:** use `AOSP_JOBS=24` for builds that touch many apps, given that swap peak.
- Gotcha: don't edit `scripts/aosp-build.sh` while a build runs. Bash reads a script as it goes, so the reporting tail fails to parse and the post-build stats are lost.

## Differences from the Google desktop image

Both images captured with the same script at 1920×1080, 160 dpi (as of 2026-10-16). Windowing, taskbar, status bar and window captions match. Everything below differs.

| Area | Reference (`sdk_gdesktop_x86_64`, emulator) | Ours (`anybook_cf_x86_64_pc`, Cuttlefish) | Status |
|---|---|---|---|
| aconfig | 11 `com.google.wear.*` flags enabled | absent: not in AOSP | Google-only |
| aconfig, mainline modules | 9 flags enabled: Bluetooth ×5, ART `hiddenapi_platform_enforcement`, RKPD `enable_feedback_loop`, MediaProvider ×2 | disabled | not desktop-related; these follow the module trains |
| aconfig | — | 5 newer flags on: `notification_shade_blur`, `notification_background_tint_optimization`, `idempotent_wct_resolution`, `fix_bubble_insets_when_invisible`, `ensure_uij_notification` | our tree is a month newer (`CP2A.260605` vs `CLE1.260506`) |
| aconfig | the reference's flags only | plus the 84 Googlebook flags and OpenBook's own picks | ours, after Googlebook (ANAL-204, ANAL-206, ANAL-216) |
| Framework RRO | no all-caps buttons, `defaultNightMode=1`, `minimumScreenOffTimeout=MAX` | AOSP defaults | look and feel, emulator-only; left out on purpose |
| SystemUI RRO | `config_disableSplitShade`, `hsu_allow_list_qs_tiles` | — | not in AOSP / HSUM only |
| Graphics | goldfish GL pipe (`ro.hardware.egl=emulation`, `gltransport=pipe`), gralloc `ranchu`, `debug.hwui.renderer=skiagl`, GLES 3.0 | ANGLE on gfxstream Vulkan (`virtio-gpu-asg`), minigbm, HWC `ranchu`, `skiavk`, GLES 3.1 | different virtual platforms |
| ARM apps | `ro.dalvik.vm.native.bridge=libndk_translation.so` (prebuilt, not in AOSP) | `libberberis_arm64.so`, Digitalis built from source (ANAL-200, `docs/digitalis.md`) | open-source bridge |
| Hardware features | touchscreen (multitouch), fingerprint, accelerometer, compass, `faketouch`, MIDI | Ethernet, USB host/accessory, camera autofocus, `device_id_attestation` | VM device models |
| Wi-Fi | `wifi_on=1`; Wi-Fi icon in the status bar | `wifi_on=0` | Cuttlefish Wi-Fi not turned on; not investigated |
| Kernel | 6.12.58 android16-6.12 (emulator `kernel-ranchu`) | 6.12.74 android16-6.12 (Cuttlefish prebuilt GKI) | the android17-6.18 kernel is in `docs/kernel.md` |
| Display identity | `display_settings.xml` keyed by unique id `local:4619827259835644672` | keyed by `port:0` | same effect: freeform, ignoring orientation requests |
| Home and sounds | `QuickSearchBox` "Google" bar above the taskbar; taskbar pins from Launcher3's `default_workspace_6x5.xml`; touch sounds on | no search box and no `QuickSearchBox`; partner-layout pins (Files, Settings, browser, Calendar, Gallery, Camera); touch, keypress and non-forced screenshot sounds off | ours, after Googlebook (ANAL-206) |
| Name | "Android Desktop" | "AnyBook Cuttlefish x86_64 desktop" (`PRODUCT_MODEL`, the project's old name) | ours |

## Known limits

- **The 79 reference flags** have no regression tests beyond the boot, the desktop capture and the scroll benchmark.
- **Wi-Fi** is off in the Cuttlefish product, as noted in the differences table.
- **"Add new apps to Home screen"** stays on until a Launcher3 patch changes AOSP's hard-coded default.
- **`drm_virgl`** doesn't run with either crosvm build; use a gfxstream mode.
