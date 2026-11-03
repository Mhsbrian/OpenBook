# OpenBook Launcher: the desk (ANAL-364)

As of 2026-11-03. This is the design for M2 of the OpenBook Launcher roadmap (ANAL-354, the fork's `openbook/ROADMAP.md` items 8 to 12): the taskbar, All Apps, the menus, Overview for desks and one motion system. It uses the material, focus ring and springs of Quire's design (`docs/quire-design.md` §4, §5, §7), so the launcher and Quire read as one system. Googlebook is a behaviour reference only: the art, the glyph and the code are our own.

Labels: **C** = confirmed (read in our tree or measured), **HYPOTHESIS** = a design assumption the build checks (§9).

- **Prototype:** [`launcher-design/index.html`](launcher-design/index.html). `?screen=desktop|taskbar|allapps|allapps-focus|allapps-search|menu-desktop|menu-taskbar|overview|motion`, `&theme=dark`, `&wall=bloom|folio|strata|tide`, `&glass=0` (the platform's blur-off fallback). `?play=1` is clickable: the apps pill, Meta, typing on the desktop, right-click on the desktop or a taskbar icon, Tab and the arrow keys in All Apps, Esc.
- **Renders:** `scripts/ui/render-launcher-design.sh` renders every screen, light and dark, at 1920×1200 dp at 1× and at the G14's 2880×1800 (1.5×, 240 dpi), plus All Apps over all eight OpenBook wallpapers. They go to the design store (`$OPENBOOK_EVIDENCE/design/launcher-design/`), not into Git.
- **Contrast:** `scripts/ui/launcher-contrast.py` reads the tokens from the prototype and scores every pair the prototype draws, in every state (rest, hover, front, top hit, pressed, focus, open), over black and over white through the glass. All 74 checked pairs pass; 8 decorative marks are listed without a target (C, 2026-11-03, §6.4).

Every app, window and value on the screens is sample data. App icons are stand-ins drawn as OpenBook's circle icons.

## Summary

- **One material.** The taskbar, All Apps, every menu and Overview's controls are the same glass as Quire's note: the platform's background blur at 34 dp under the surface colour at 80 %, a lit top edge and a soft shadow. The desktop behind All Apps stays sharp. There is no scrim and no brand colour; every colour is a Material role from the wallpaper.
- **A quiet taskbar that tells the truth.** 48 dp targets on a 4 dp grid, our own apps pill, and one line of state under each icon: running, in front, several windows, minimized. The bar stays 56 dp, so window insets don't move.
- **All Apps is a panel, not a sheet.** A centred 720 dp glass card 12 dp above the taskbar, sized to the apps and never resized by a search. Focus starts in the field. Arrow keys walk the grid with a visible ring.
- **One menu.** Desktop, taskbar and All Apps menus share one glass menu: 36 dp rows, 16 dp corners, icons, shortcut hints.
- **Overview needs our own code.** Neither Overview flag on the roadmap changes anything on the laptop's display in AOSP 17 (C, §5). The design draws the desk's wallpaper behind its windows and blurs Overview's backdrop in our code.
- **One motion system.** Three springs and three durations, the same as Quire's. Geometry moves on springs, opacity and colour on durations. Remove animations makes every one a cut.

## 1. The idea

A laptop desktop is a desk. The wallpaper is the desk's surface. The taskbar is the edge of the desk, where the tools you use sit. Panels and menus are panes of glass laid on the desk: they show what is under them as colour and leave the rest of the desk in plain sight. Nothing moves for decoration; every motion answers something the person did.

Three rules follow:
- **Glass over a sharp desk.** Only the pane itself blurs what is under it. Opening All Apps or a menu never dims, blurs or zooms the desktop around it (`reduce_workspace_blur_usage`, OpenBook #158, C).
- **One line of state.** The taskbar says, for each app, whether it is running, in front, has several windows or is minimized, with one mark per icon and no badges.
- **Keyboard is first-class.** Every surface can be reached and left with the keyboard, and the focused thing always has the same ring.

## 2. Taskbar (roadmap #8)

### 2.1 Anatomy and geometry

```text
┌──────────────────────────────────────────── 56 dp glass bar, full width ─────────────────────────────────────────────┐
│                         ( ▣▣ )  │  ◯  ◯  ◯  ◯  ◯  ◯  ◯  │  ◯                                                         │
│                         pill   div  pinned apps            div running, not pinned                                    │
│                                       ━  ‒·  ‒  ▭        ‒                                                              │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Token | Value | AOSP 17 today (C) |
|---|---|---|
| `tb.height` | 56 dp | 56 dp (`taskbar_size` = `@*android:dimen/taskbar_frame_height`). Unchanged, so window insets don't move |
| `tb.target` | 48 dp square, `tb.radius` 14 dp | none drawn: no hover highlight, and hover scale is off for the taskbar (`BubbleTextView.java:1415`) |
| `tb.icon` | 40 dp, centred in the target | 40 dp (`TaskbarIconSpecs.defaultPersistentIconSize`), 48 dp minimum touch size |
| `tb.gap` | 4 dp between targets (pitch 52 dp) | `taskbar_icon_spacing` 12 dp (pitch 56 dp) |
| `tb.pill` | 56 × 40 dp, pill radius | `TaskbarAllAppsButtonContainer`: a round icon button tinted `all_apps_button_color` |
| `tb.divider` | 1 × 24 dp `outlineVariant` at 70 %, 8 dp each side | AOSP's divider |
| `tb.surface` | glass (§6.3): `surface` / `surfaceContainer` at 80 % over the platform's 34 dp blur, 1 dp lit top edge, a hairline above | an opaque full-width rectangle in `taskbar_background` (neutral, L* 98 light / 6 dark), `TaskbarBackgroundRenderer.drawPersistentBackground` |

The row stays centred across, and sits 2 dp above centre: 2 dp over the targets, 6 dp under them, so the state lines in §2.3 lie on the bar. Pinned apps come first, then running apps that aren't pinned, after a divider (`enable_recents_in_taskbar` is on in our build, C). AOSP draws one divider: right of the pill while no unpinned app runs, and between pinned and unpinned running apps once one does, with the pill then 4 dp from the first app (C, #8's VM run, 2026-11-03).

### 2.2 The apps pill

- 56 × 40 dp, `secondaryContainer` with an `onSecondaryContainer` glyph (6.1:1, §6.4).
- **Open:** while All Apps is open the pill is `primary` with an `onPrimary` glyph, crossfaded in 120 ms. It is the one place the taskbar shows that a panel belongs to it.
- **The glyph** is our own: four 6.5 dp rounded squares on a 20 dp grid, the lower right one turned 45°. It reads as "apps", and the turned square marks it as OpenBook's.
- Hover and press follow §2.4. It is first in the taskbar's focus order. The keyboard's All Apps shortcut opens it too (#9 records which key AOSP 17 binds).

### 2.3 Indicators: one line of state

Under each icon, 1 dp below its 48 dp target and 2 dp above the bar's bottom edge. The line lies on the bar itself, outside the target, so no hover, front or pressed layer is ever under it:

| State | Mark | Colour |
|---|---|---|
| Pinned, not running | none | |
| Running, not in front | 6 × 3 dp line | `onSurfaceVariant` (3.8:1 on the bar at its worst) |
| In front (has the focused window) | 16 × 3 dp line, and the target gets a 6 % `onSurface` tile | `primary` (3.8:1) |
| More than one window | the line plus a 3 dp dot, 3 dp to its right | the line's colour |
| Every window minimized | a hollow 8 × 3 dp line (1 dp stroke) | `onSurfaceVariant` |

The width changes on `spring.settle` (§7), colour in 120 ms.

**AOSP 17 today (C):** `BubbleTextView.RunningAppState` has three states, `NOT_RUNNING`, `RUNNING` and `MINIMIZED`. Running is a 12 × 2 dp line in `materialColorTertiary`, minimized a 6 × 2 dp line in `materialColorOutline`, and `TaskbarRunningAppStateAnimationController` springs between them. There is no "in front" state and no window count; #8 adds both. In front is the task WM Shell reports as globally focused (`FocusState`, its focus-transition listener), read once from the running task at start; click-to-minimize asks `ActivityManager` per click instead. The window count is the app's running desktop tasks, minimized ones included (C, #8, 2026-11-03).

### 2.4 Hover, press, focus and the tooltip

- **Hover:** a state layer of `onSurface` at 8 % fills the 48 dp target with 14 dp corners, in 100 ms, out 150 ms (12 % on the front tile).
- **Press:** the icon scales to 0.92 on `spring.tick`; the layer goes to 12 %.
- **Keyboard focus:** a 2 dp `primary` ring, 2 dp outside the target: Quire's ring (`docs/quire-design.md` §7.2).
- **Tooltip:** after 500 ms of hover, the app's name in a 28 dp pill of `inverseSurface` / `inverseOnSurface`, 12/16 at weight 500, 8 dp above the bar, faded in 120 ms. AOSP's `TaskbarHoverToolTipController` keeps deciding whether it shows; AOSP showed it at once, #8 waits 500 ms.
- **Press with a mouse or touch** isn't a view state in AOSP 17's taskbar: its cursor-driven gesture handling (`CustomEventsTouchHandler`) never calls `setPressed`, so #8 tracks the press from the target's touch events (C, #8).
- **Reaching the bar by keyboard:** AOSP 17's taskbar window is never focusable except while one of its menus is open. Tab on the empty desktop (nothing in the launcher's own focus order) puts focus on the pill, Shift+Tab on the last app; Tab and the arrow keys walk the targets, Enter opens one, and Esc or a window coming to the front gives focus back (C, #8).

## 3. All Apps panel (roadmap #9)

### 3.1 Geometry and material

| Token | Value |
|---|---|
| `aa.width` | 6 columns × 112 dp + 2 × 24 dp = 720 dp |
| `aa.height` | the height that fits every app (84 dp header + rows × 104 dp + 28 dp), at most 640 dp and at most the space above the taskbar less 24 dp; fixed while the panel is open, so a search never moves the field |
| `aa.position` | centred on the display, its bottom 12 dp above the taskbar |
| `aa.radius` | 28 dp: Quire's note and `config_dialogCornerRadius` (C) |
| `aa.surface` | glass (§6.3) |
| Field | 48 dp, pill radius, inset 24 dp; paper (`surfaceContainerLowest` at 80 % in light, `surfaceContainerHighest` at 85 % in dark); a 20 dp search icon; "Search apps" in soft ink; text 16/24; a 2 dp `primary` ring and caret while it has focus |

At the G14's 1920 × 1200 dp the panel is 720 × 528 dp with 24 apps and 720 × 640 dp from 30 apps on. The QEMU image's 1280 × 800 dp fits the same panel.

There is no drag handle, no scrim and no blur or zoom of the desktop.

**AOSP 17 today (C):** the taskbar's All Apps is `TaskbarAllAppsSlideInView` around `TaskbarAllAppsContainerView` in a `TYPE_APPLICATION_OVERLAY` window (`TaskbarAllAppsController.java:195`): a full-width bottom sheet with 26 dp top corners, a handle (`all_apps_bottom_sheet_background.xml`) and a scrim (`TaskbarAllAppsSlideInView.java:266`). With `reduce_workspace_blur_usage` (flag ENABLED, RRO true) its blur radius is 0 and the sheet is an opaque accent colour (`TaskbarOverlayContext.java:151`). Nothing in the tree draws a centred panel. The glass needs a blur behind the panel's own bounds (`BackgroundBlurDrawable` on the panel view), not `TaskbarOverlayController.setBackgroundBlurRadius`, which blurs everything behind the window.

**As built (C, #9's VM run, 2026-11-03):** the panel is the sheet's apps view, sized and placed in the same overlay window; the sheet keeps AOSP's window, touch routing and open/close bookkeeping, without its handle, scrim or swipe. `BackgroundBlurDrawable` as the panel's background gives SurfaceFlinger one blur region on `VRI-Taskbar Overlay`; no layer gets a window-wide blur, and no sampled desktop pixel outside the panel and its shadow changes when it opens. With blur off the region goes and the panel is the 96 % tint. A press outside the panel closes it. The panel's grid comes from its own All Apps profile on the overlay window's device profile (the launcher's, with 6 × 112 × 104 dp cells), so the desktop's grid doesn't change. External displays and the transient taskbar keep AOSP's sheet (not tested).

### 3.2 The grid

- Cells 112 × 104 dp. Icon 52 dp, 12 dp from the cell's top; label 8 dp under it, 100 dp wide, 13/16 at weight 450, at most two lines (M1 #6, `pref_enable_two_line_toggle`), ending in "…".
- Alphabetical, as AOSP. No section letters and no fast scroller: a desktop scrolls with a wheel or a touchpad. A 4 dp scroll bar in `onSurfaceVariant` (3.8:1 on the glass; it can be dragged, so it is a control) appears while scrolling or when the pointer nears the right edge, 8 dp in from it.
- Hover: `onSurface` at 8 % on the cell, 16 dp corners. Press: icon 0.96 on `spring.tick`.
- **As built (C, #9):** two 16 dp lines leave no slack in the 104 dp cell, and Android keeps the last line at the font's own height (about 0.7 dp more than the pitch). M1 #6's fit check (`TwoLineLabels`) now allows that when lines are set tighter than the font; AOSP's sheet, which sets no line height, is unchanged. AOSP's focus highlight isn't drawn in the panel; its cells draw the ring.
- **Not in #9 (follow-up):** the 4 dp scroll bar. The panel keeps AOSP's fast scroller, which only shows once the apps need more than 640 dp (31 apps or more at the G14's size).

### 3.3 Keyboard and search

- The panel opens with focus in the field (M1 #7 types into it from the desktop).
- **Typing** filters the grid in place: word-prefix matches, the matched prefix in weight 650. The **top hit** has a 10 % tile; Enter opens it. Focus stays in the field.
- **↓ or Tab** moves focus into the grid; the arrow keys walk it; Enter opens; **Esc** clears the text first, then closes. Shift+Tab or ↑ from the first row returns to the field.
- **No results:** "No apps match "xyz"", 14/20 in soft ink, centred.
- The focused cell has the 2 dp `primary` ring, inside the cell's corners.
- **AOSP 17 (C, #9):** its default search never marks a top hit (`DefaultSearchAdapterProvider` records only views it creates itself), so Enter in the taskbar's All Apps opened nothing (as M1 #7's run recorded). Esc cleared the search, but leaving a search reset the search bar, which took the field's focus. #9 adds the top hit, takes Esc before the IME (the same from the field and the grid), and keeps the field focused when the text empties. The field reports the search action twice for one Enter, so the top hit opens once.
- **Not in #9 (follow-up):** the matched prefix in weight 650.

### 3.4 Open and close

- **Open:** the panel rises from the pill: scale 0.96 → 1 from its bottom centre, 16 dp → 0 rise, opacity 0 → 1, on `spring.panel` (≈ 280 ms). The grid fades in over 120 ms after 40 ms.
- **Close:** 150 ms, emphasised accelerate: opacity → 0, scale → 0.98, 8 dp fall. Launching an app closes it the same way while the window opens.
- **As built (C, #9):** geometry on `spring.panel`, opacity on `duration.fade` (§7's rule). The spring is 1 % from rest at about 270 ms and reaches AOSP's rest threshold (0.15 %) at about 360 ms. AOSP's sheet never ran its own durations: `AbstractSlideInView` starts its playback controller's player directly, which stays at `ValueAnimator`'s default 300 ms (AOSP's 100 ms close included), so the panel sets its player to 150 ms. In the VM the open's first frame takes 250–300 ms (virtio-vga without GL: the guest renders the blur on the CPU), so its smoothness is measured on the G14 (§8).

## 4. Menus (roadmap #11)

One menu for the desktop's right-click, a taskbar icon's right-click and an All Apps icon's right-click.

| Token | Value |
|---|---|
| `mn.surface` | glass (§6.3), 16 dp radius, 6 dp padding, a lighter shadow than panels (0 12 32 at 20 % plus 0 2 6 at 8 %) |
| `mn.width` | 224 dp minimum, 320 dp maximum; labels never wrap, they end in "…" |
| `mn.row` | 36 dp tall for pointer and keyboard (48 dp when opened by touch, as AOSP), 10 dp radius, 12 dp side padding |
| `mn.icon` | 20 dp `onSurfaceVariant`, 12 dp gap |
| Label | 14/20 at weight 450 in ink |
| Shortcut hint | 12/16 in soft ink, right-aligned (e.g. "Middle-click" for New window, "Meta 3"). On a hovered row it turns to ink: soft ink over the 8 % layer is 4.2:1 |
| Divider | 1 dp `outlineVariant` at 50 %, 6 dp above and below, inset 12 dp |
| Header (taskbar) | 44 dp: the app's 24 dp icon and its name at weight 600 |
| Window rows | a 20 × 14 dp outline thumbnail and the window's title; the front window at weight 600 with a `primary` outline |
| Hover | `onSurface` at 8 % on the row |

**Placement:** desktop menus open at the pointer, down and right, flipping at the display's edges. Taskbar menus are centred above the icon, 8 dp above the bar. There is no arrow.

**AOSP 17 today (C):** the desktop's menu and a taskbar icon's menu are both the Compose popup (`PopupContainer.showComposePopup`; `src/com/android/launcher3/popup/ui/ComposePopup.kt`): 24 dp corners in `materialColorSurfaceContainer`, 52 × 216 dp rows, hover in `materialColorSurfaceVariant`, focus a 3 dp `materialColorSecondary` border (`PopupMenuItems.kt`). `OptionsPopupView`/`ArrowPopup` remain only for an icon's long-press popup. So one restyle of the Compose popup reaches both menus; the arrow popup gets the same tokens.

**Contents** stay AOSP 17's (C, `expandable_long_press_menu` on: Add to Taskbar, App info, New Window, Manage Windows, Close), restyled, with these changes:
- **Desktop:** Wallpaper and style, Widgets, a divider, Display settings, Home screen settings.
- **Taskbar:** the header, the app's windows, a divider, New window (only when the app supports several instances; M1 #4's rule), Pin or Unpin, App info, a divider, Close / Close *n* windows.
- **Keyboard:** Shift+F10 or the menu key opens the focused item's menu; ↑ ↓ move, Enter activates, Esc closes.

**Motion:** open scales 0.94 → 1 from the anchor's corner on `spring.panel` with a fade on `duration.fade`; close fades in 100 ms on `duration.exit`'s curve (§7; #11 built it as 150 ms emphasised decelerate and a 100 ms linear fade, #12 moved it onto the tokens).

**As built (C, #11's VM run, 2026-11-03):**
- **One menu, AOSP's popup underneath.** A caller hands AOSP's `PopupContainer` a spec (kind, anchor, header, windows, groups, labels, hints); the popup then draws our Compose menu (`openbook/OpenBookMenu`, `OpenBookMenuContent`) in place of `ComposePopup`, with no arrow. AOSP keeps the items, their actions, the deep shortcuts and the open/close bookkeeping. The glass is the panels' (`GlassDrawable`, now shared with All Apps) with 16 dp corners and the menu's lighter shadow: one blur region on the launcher, taskbar or overlay window. The taskbar's window has two while a menu is open, the bar's and the menu's.
- **Contents.** The desktop's are AOSP's strings in the order above: "Wallpaper & style", "Widgets" | "Display settings" (ours: `Settings.ACTION_DISPLAY_SETTINGS`), "Home settings". AOSP's "Apps list" item is left out, because the pill and Meta open All Apps. The taskbar's: the header, the app's running desktop windows with the front one marked (a click brings that window to the front; they replace Manage Windows), then New Window with "Middle-click", Remove from (or Add to) Taskbar, App info | "Close" or "Close *n* windows". Windows that share a title are numbered, "Files (1)", "Files (2)". An All Apps icon keeps AOSP's items.
- **Placement.** Anchors are in screen coordinates. A menu is never taller than its room: above the bar for a taskbar icon's menu, between the bars otherwise. Beyond that its rows scroll: with the wheel or touchpad, and a focused row scrolls into view. Eight windows at 960 × 600 dp need 514 dp and get 504. A menu waits, invisible, only while its window is smaller than the screen, for at most 1 s. Opened from the keyboard, the taskbar's window is still 175 px tall when the menu is made; it grows to the full screen for the menu, and only then is the menu placed and shown. Menus stay 8 dp clear of the status bar and the taskbar: a desk's launcher window lays out under the bar, so its drag layer's bottom inset is 0 and the window's own insets are used. AOSP ignores a long press within the workspace's edge margin, a phone rule. On a desk a mouse right-click opens the menu anywhere on the desktop (`WorkspaceTouchListener`).
- **Keyboard.** Shift+F10 or the menu key opens the focused icon's menu: an All Apps cell's under the cell, a taskbar icon's above the bar. With nothing focused it opens the desktop's menu, centred. The first row is focused. ↑ ↓, Tab and Shift+Tab move and wrap, Enter activates, and Esc closes, giving focus back to the icon. Neither key is a navigation key, so the window can still be in touch mode, where rows can't take focus; a menu opened from the keyboard leaves touch mode first. Esc over All Apps closes a menu opened there with the pointer before it closes the panel. A menu opened with the pointer holds the focus itself, so Esc closes it, and ↓, Tab or Home enter its first row (↑, Shift+Tab or End its last). The taskbar's window isn't an activity, so keys reach its Esc handling only along the focus. AOSP's popup held none in touch mode, so Esc never closed a taskbar menu opened with the mouse, and the next click on the bar only closed the menu. The focus ring sits inside the row, because rows touch.
- **AOSP's view popups** (`ArrowPopup`; on a desk, a taskbar folder's menu) get the same glass, 36 dp rows (48 dp by touch) with 20 dp icons, the state layers and no arrow, and keep AOSP's placement. `DeepShortcutView` reads any layered background as AOSP's blur layers, so the state layer is on the row's text view.
- **Measured in the VM** (1280 × 800 dp): the desktop menu is 224 × 169 dp; the Files menu with two windows is 243 × 298 dp, its bottom 8 dp above the bar and centred on the icon. Open took 173 ms and close 116 ms (#11's own timings; since #12 the open's scale is `spring.panel`, §7); with Remove animations both are cuts. The G14 measures smoothness and the blur's cost (§8).
- **Touch.** A menu opened by a finger's press has 48 dp rows. In the VM, injected touchscreen long presses gave 48 dp rows in the desktop's menu (217 dp tall) and a taskbar icon's. All Apps icons and AOSP's view popups use the same rule but weren't run by touch: a touch long press on a taskbar folder starts a drag and opens no popup. No hardware touchscreen was run, because neither the VM nor the G14 has one.
- **Not run:** external displays and the transient taskbar.

## 5. Overview for desks (roadmap #10)

### 5.1 What AOSP 17 has (C, 2026-11-03)

The roadmap named two flags. Neither changes anything on its own:

| Flag | Our build | Readers in our tree |
|---|---|---|
| `com.android.launcher3.enable_overview_desktop_tile_wallpaper_background` | DISABLED, read-only | **none.** Only its accessor in `src/com/android/launcher3/util/OverviewReleaseFlags.kt:32`. The code it gates isn't public |
| `com.android.launcher3.enable_recents_window_blur` | DISABLED, read-only | `quickstep/src/com/android/quickstep/window/RecentsWindowManager.kt:221` and `:366`. On the laptop's own display Overview runs in the launcher (`LauncherRecentsView`); `RecentsWindowManager` takes over there only with `enable_launcher_overview_in_window`, DISABLED (`OverviewComponentObserver.java:237`). It does run Overview on **external** displays (`:368`), so this flag would blur Overview on a second monitor only |

Two more facts (C):
- **Overview doesn't blur at all today.** `LauncherDepthController.shouldBlur()` returns false whenever `all_apps_surface` is on (`LauncherDepthController.kt:34`), and it is ENABLED, so Overview gets the wallpaper zoom only.
- **A desk tile's background is a flat colour:** `system_neutral2_300` (`DesktopTaskView.kt:157`).

So turning the two flags on would change nothing on the laptop's screen. Moving Overview into its own window as well would replace how Overview runs on the desktop, a larger change than this item, and neither flag is in Googlebook's enabled set either (ANAL-201's diff). #10 is therefore **our own code**: the wallpaper in `DesktopTaskView`'s background view and a blur for the Overview state only. `enable_recents_window_blur` can join it for external displays if #10's two-display VM run shows it works.

### 5.2 Design

- **Backdrop:** the wallpaper, blurred at 34 dp with `surface` at 18 % (light) or 30 % (dark) over it, instead of AOSP's scrim and zoom. The taskbar stays. This lifts `LauncherDepthController`'s `all_apps_surface` gate for the Overview state only; All Apps keeps its own rule (HYPOTHESIS that this is safe: the gate exists for All Apps' separate surface; #10 checks Overview → All Apps → Overview).
- **Desk tiles** show the desk as the person left it: the wallpaper, scaled, with the desk's windows as thumbnails in their places. 20 dp corners, a 1 dp lit outline, a soft shadow. Every tile has the display's 16:10 shape.
- **App tiles** (full-screen tasks) are the same size, 16 dp corners, edge to edge.
- **Labels** above each tile, on a 28 dp glass chip: the app's 20 dp icon or the desk glyph, and the name at 13/18 weight 500; desks add their apps in soft ink. The chip is the labels' backing: on the wallpaper alone, with only the 18 % / 30 % tint, a label can fall to 1.1:1.
- **Hover** lifts a tile by 4 dp with a deeper shadow on `spring.settle`. **Keyboard focus:** a two-colour ring on the tile's edge, 2 dp each of `surfaceContainerLowest`, `onPrimaryContainer`, `surfaceContainerLowest`. It sits over the wallpaper, so it follows WCAG technique C40: its two colours are 10.1:1 (light) and 16.4:1 (dark) apart, which guarantees that one band is at least 3:1 against any **solid** colour behind it. An image or a gradient still needs checking, and a sampled model is not that proof: over all eight OpenBook wallpapers, blurred and sharp (blur off), light and dark, the backdrop modelled at 480 × 300 samples (every 4th pixel of 1920 × 1200, the blur approximated by a Gaussian) gives the better of the two colours at least 3.05:1 at every sample (C for the model, ANAL-372, `scripts/ui/ring-wallpapers.py`). It doesn't check each full-resolution pixel or the colour actually drawn at each band's position; the VM screenshots show the ring over the default wallpaper only. A single `primary` ring there can fall to 1.2:1.
- **Clear all** is a glass chip, 40 dp, centred 40 dp above the taskbar.

### 5.3 As built (C, #10's VM run, 2026-11-03)

Our code is `OverviewDesks` in the fork, with one-line hooks; without `desktop_form_factor` every hook is a no-op.

- **Backdrop:** `LauncherDepthController` lifts its `all_apps_surface` gate for `OVERVIEW`, `OVERVIEW_MODAL_TASK` and `OVERVIEW_SPLIT_SELECT` only, with the glass blur (51 px at 240 dpi) at full depth and no wallpaper zoom; `OverviewState`'s scrim becomes the 18 % / 30 % tint. SurfaceFlinger blurs AOSP's "Overview Blur" layer at 51 px, under the live tile's windows. All Apps keeps AOSP's rule: Overview → All Apps → Esc leaves Overview as it was. Leaving Overview restores the desktop exactly (no blur, no zoom).
- **The desk's wallpaper** is decoded once at the tile's width (a set wallpaper's file, or the built-in one) and reloaded when the wallpaper changes. Reading it needs `READ_WALLPAPER_INTERNAL`, which is signature|privileged; OpenBook's image grants it (`device/anybook/common/desktop/privapp-permissions-launcher3-overview.xml`). A live wallpaper has no image, so its desk tiles keep AOSP's flat colour.
- **Desk tiles keep AOSP's layout of the windows** (§10): AOSP 17 spreads a desk's windows out in Overview, each with its title and close button, rather than at their places on the desk. The wallpaper is drawn as the display shows it, behind them.
- **16:10:** AOSP sizes a tile to the windows' area, the display above the taskbar (1.72 on the G14). A desk tile's picture continues under the taskbar's strip, so the tile has the display's shape while AOSP's transitions keep mapping the windows' area; the strip takes the pointer and clicks like the rest of the tile. **App tiles keep their window's shape:** a 16:10 app tile would have to crop or letterbox the window.
- **Labels** are AOSP's chip restyled: 28 dp glass, 12 dp above the tile, sized to the text, with AOSP's "Desktop" and the desk's apps in soft ink at 400. AOSP's chevron is gone; the chip still opens AOSP's task menu (its arrow-less header is glass too; the menu itself is AOSP's). The chip lies outside its tile's bounds, so the accessibility tree leaves it out, as AOSP marks it not important for accessibility; the tile keeps its actions.
- **Hover and focus** replace TaskView's hover and focus borders. The lift moves a live tile's windows with the tile. Remove animations makes the lift a cut.
- **Clear all:** AOSP's button scrolls with the tiles, so next to one desk it sits off screen. It stays in RecentsView's scroll, invisible and out of the focus order; the chip in the drag layer takes its alpha (without the scroll's) and its click.
- **Pre-existing, unchanged** (the base launcher does the same): after Clear all, Overview stays open on the empty desk; once Tab has focused a tile, Esc no longer leaves Overview.
- **Not built:** `enable_recents_window_blur` for Overview on an external display (no two-display run).

## 6. Tokens

### 6.1 Type

Google Sans Flex, the system's `variable-*` families (OFL 1.1, already in the image, `docs/googlebook-ui.md` §2.1, C). Sizes in sp; line height after the slash.

| Role | Size | Weight | Used for |
|---|---|---|---|
| `ob.type.field` | 16/24 | 400 | The search field |
| `ob.type.menu` | 14/20 | 450 | Menu rows; 600 for the header and the front window |
| `ob.type.label` | 13/16 | 450 | App labels in All Apps |
| `ob.type.tile` | 13/18 | 500 | Overview labels |
| `ob.type.meta` | 12/16 | 400 | Shortcut hints, the tooltip (at 500) |
| `ob.type.empty` | 14/20 | 400 | No results |

### 6.2 Spacing and shape

| Token | Value |
|---|---|
| Grid | 4 dp; spacing 4, 8, 12, 16, 24, 32 dp (Quire's scale) |
| Radii | panel 28, desk tile 20, menu 16, cell 16, app tile 16, taskbar target 14, menu row 10 dp; pills and the field are pill-shaped |
| Focus ring | 2 dp `primary`, 2 dp outside, on glass or the bar (inside the corners of All Apps cells). Over the wallpaper (Overview tiles) the two-colour ring of §5.2 |
| State layers | `onSurface`: hover 8 %, front 6 %, top hit 10 %, pressed 12 % |

### 6.3 Glass

Quire's glass (`docs/quire-design.md` §4.1) without the holographic rim, which stays Quire's own:

| Token | Light | Dark |
|---|---|---|
| Blur | the platform's background blur, 34 dp (51 px at 240 dpi) | same |
| Tint | `surface` at 80 % | `surfaceContainer` at 80 % |
| Lit edge | white at 75 %, 1 dp inside the top edge | white at 18 % |
| Outline | white at 55 %, 1 dp inside | white at 14 % |
| Shadow (panels) | 0 24 48 at 22 % `#1B1B21`, plus 0 2 6 at 8 % | 0 24 48 at 55 % black, plus 0 2 6 at 30 % |
| Taskbar | the same tint and edge, and a hairline of `outline` at 22 % above it | white at 8 % |

### 6.4 Colour and contrast

All roles are Android 17's Material 3 TonalSpot from the current wallpaper; the prototype uses the Folio values (`assets/wallpapers/monet.json`, as Quire's). The build reads them from the theme, never from constants.

Measured with `scripts/ui/launcher-contrast.py` (C, 2026-11-03). Every text and meaningful mark the prototype draws is listed with its whole stack, back to front: the bar or glass, paper for the field, and the state layer on top (hover 8 %, front 6 %, top hit 10 %, pressed 12 %). Each stack is composited over black and over white, and the lower ratio counts. Targets: 4.5:1 for text, 3:1 for marks, icons and focus rings, and 9:1 between the two colours of a C40 ring. `--md` prints the full table; the lowest results:

| Pair | Light | Dark | Target |
|---|---|---|---|
| All Apps focus ring on the top hit (`primary` on glass + 10 %) | 3.3:1 | 4.2:1 | 3:1 |
| Menu icon, hovered (`onSurfaceVariant` on glass + 8 %) | 3.4:1 | 3.3:1 | 3:1 |
| Front window's outline in a menu, hovered (`primary` on glass + 8 %) | 3.4:1 | 4.4:1 | 3:1 |
| Running and minimized lines, scroll bar, menu icons (`onSurfaceVariant` on the bar or glass) | 3.8:1 | 4.0:1 | 3:1 |
| Focus ring on glass or the bar, front line | 3.8:1 | 5.4:1 | 3:1 |
| Soft ink on glass (shortcut hints, the desk's apps, no results) | 4.8:1 | 5.4:1 | 4.5:1 |
| Overview's two-colour ring (`onPrimaryContainer` against `surfaceContainerLowest`) | 10.1:1 | 16.4:1 | 9:1 |

Decorative marks, which carry no information of their own, have no target: the taskbar's divider, menu dividers, the outlines of windows other than the front one, and the pill's edge (its glyph identifies it).

**What the check missed at first.** The first version scored only resting pairs. The Checker (2026-11-03) found eight failing cases in states it left out:
- soft-ink hints on a hovered menu row: 4.2:1 light, 4.46:1 dark;
- Overview's labels straight on the tinted wallpaper: 1.1:1 light, 1.6:1 dark;
- a single `primary` focus ring there: 1.2:1 in dark.

Listing every state then found one more: the running line overlapped its target by 1 dp, which put it at 2.98:1 on a pressed tile in dark. The fixes are the hint turning to ink on hover, the glass chips, the C40 ring, and the line moved off the target (§2.3). Earlier still, the taskbar at 78 % failed the front line at 2.99:1, so the bar uses the panels' 80 %. Alpha is the knob: below 80 % the lines fail.

## 7. One motion system (roadmap #12)

Springs are stiffness and damping ratio, mass 1 (`SpringForce`; Compose `spring()`). Durations carry opacity and colour.

**AOSP 17 today (C):** All Apps from the taskbar opens in 500 ms on `EMPHASIZED` and closes in 100 ms (`AllAppsState.getTransitionDuration`, `res/values-sw600dp/config.xml`); `ArrowPopup` opens in 200 ms and closes in 233 ms with a 0.5 → 1.02 → 1 scale; the Compose popup has its own springs (`ComposePopup.kt:528`); the running line springs (`TaskbarRunningAppStateAnimationController.kt:55`). Every one of these has its own numbers. The fork already has the tools: `SpringAnimationBuilder`, `SpringProperty`, `AnimatedFloat` (`src/com/android/launcher3/anim/`).

| Token | Value | Settles | Used for | Quire |
|---|---|---|---|---|
| `spring.panel` | 500, 0.90 | ≈ 280 ms, 0.3 % overshoot | All Apps open, Overview tiles, menu scale | new |
| `spring.settle` | 700, 0.90 | ≈ 170 ms | Indicator width, Overview hover lift, search reflow | `quire.spring.settle` |
| `spring.tick` | 1400, 0.70 | ≈ 150 ms | Press on icons and the pill | `quire.spring.tick` |
| `duration.fade` | 120 ms, standard `(0.2, 0, 0, 1)` | | Colour changes, the grid's fade-in, the tooltip | `quire.duration.fade` |
| `duration.hover` | in 100 ms, out 150 ms, standard | | State layers | new |
| `duration.exit` | 150 ms, emphasised accelerate `(0.3, 0, 0.8, 0.15)` | | Panels and menus closing; menus fade out in 100 ms | `quire.duration.unwrite`'s curve |

Rules:
- Geometry on springs, opacity and colour on durations. Leaving is faster than arriving and never overshoots.
- A spring in flight is retargeted, not restarted, so a quick reopen continues from where it is.
- **Remove animations** (`ValueAnimator.areAnimatorsEnabled()` false) makes every token a cut.
- **Out of scope here:** a window's own open, minimize and restore are WM Shell's transitions in SystemUI, not the launcher's. Matching them to these tokens is a separate OpenBook change in `frameworks/base` (§10).

**As built (C, #12's VM run, 2026-11-03):**
- **One object.** `OpenBookMotion` in the fork's `openbook/` package holds the three springs and three durations, with the values and names of Quire's `Motion` (`dev.openbook.quire.ui.Motion`). Nothing else in the launcher's OpenBook code holds a stiffness or a duration, and the resources that held them are gone. Its `Value` eases or springs one value, retargets a spring in flight with its velocity, and cuts when animations are off; it replaced two copies of the same helper (taskbar, All Apps cells). `duration.exit` has a 100 ms form for menus, the 100 ms in the table above.
- **Moved onto it:**
  - the taskbar's line of state, colours, state layers, press and pill; the tooltip's fade (`duration.fade` on the standard curve, was AOSP's default curve);
  - the All Apps panel and its cells (same values as #9);
  - the menus: the scale on `spring.panel`, the fade on `duration.fade`, the close on `duration.exit`'s curve (were 150 ms emphasised decelerate and a 100 ms linear fade);
  - a desk's view popups (AOSP's `ArrowPopup`, on a desk a taskbar folder's menu): the menus' motion, in place of AOSP's 200 ms open with a 0.5 → 1.02 → 1 scale and 233 ms close. The blur region fades with the popup;
  - the launcher's own ALL_APPS state on a desk, which opens the taskbar's panel: as long as the panel's motion, `spring.panel`'s 275 ms in and `duration.exit` out, in place of AOSP's 500 ms and 100 ms. It redraws the launcher window (the hotseat and page indicator fades) for that long;
  - Overview's hover lift (#10): `spring.settle`, as before, now through `Value`;
  - AOSP's Compose popup on a desk, which only paths outside our menus still reach (accessibility actions, private space): its expansion's opacity on `duration.fade` and size on `spring.settle`, in place of its own two springs. Not run in the VM.
- **Settling times.** By `SpringForce`'s own rest test (what a `SpringAnimation` uses): `spring.panel` 0 → 1 in 275 ms (the panel logged 276–294 ms) and 0.94 → 1 in 204 ms; `spring.settle` 6 px in 145 ms (the lift); `spring.tick` 1 → 0.92 in 162 ms. A menu's scale runs instead as an animator from `SpringAnimationBuilder`, whose stricter equilibrium test ends 0.94 → 1 at 211 ms.
- **Frame timing** (`dumpsys gfxinfo` per window, before and after each animation, main's launcher then #12's, then Remove animations). The VM renders on the CPU, so a first frame can take 300–400 ms and a span varies 30–100 ms from run to run: only large differences show. ALL_APPS opening went from 24 frames over 562 ms to 12 over 302 ms; a folder popup's close from 19 frames to 8, its first burst ending at 125 ms instead of 359 ms. Overview's lift is unchanged: 9–11 frames, the last 135–181 ms after the first, in both (three hovers each). With Remove animations every one is a cut: 1–4 frames, where 3–4 are the taskbar window resizing for a menu.
- **Not changed:** AOSP's taskbar running-line bounce stays off on a desk (#8), and Esc doesn't close a taskbar folder's view popup opened with the pointer, in main's launcher as in this one.
- **Not run:** the G14 (the release suite: smoothness at 120 Hz on the 890M, §8); the Compose popup's remaining paths; touch.

## 8. Blur cost and fallbacks

- **Areas.** The taskbar blurs 1920 × 56 dp (0.24 Mpx at 1.5×, 5 % of the panel); All Apps at most 720 × 640 dp (1.0 Mpx, 20 %); a menu about 260 × 300 dp (0.18 Mpx, 3 %); Overview's backdrop the whole screen (100 %, as the shade), plus its 28 dp labels and the Clear all chip. The shade's full-screen blur, already on the G14 with no GPU fault, is 100 % (C, `docs/googlebook-ui.md` §2.3).
- **Budgets on the G14, 120 Hz** (B2's method, `scripts/ui/blur-report.py`): with All Apps open, RenderEngine ≤ 3 ms per GPU-composed frame; with only the taskbar, ≤ 1 ms; ≤ 2 janky frames in All Apps' open; taskbar idle draws nothing. HYPOTHESIS until measured; blur cost scales with area, so these sit well under the shade's.
- **If the taskbar's blur costs too much,** the bar becomes 96 % tint with no blur. Nothing else changes.
- **Blur off** (`isCrossWindowBlurEnabled()` false: battery saver, thermal, Developer options; C, `docs/quire-design.md` §4.5) turns every glass surface into 96 % tint, same layout. `?glass=0` renders it.

## 9. Build plan

One PR in OpenBookLauncher per item, each with its VM run (the epic's recipe, ANAL-354), screenshots against these renders, a crash-buffer check, and a contrast re-run on any token change. Our code goes in `quickstep/src/com/android/launcher3/openbook/` with one-line hooks upstream. Tokens are resources in the fork (`res/values/openbook_tokens.xml`), named as here; the motion tokens are code, one `OpenBookMotion` object (§7).

| Order | Item | Where it hooks (C, read in the fork at `6b57cba6`) | VM check |
|---|---|---|---|
| 1 | #8 Taskbar | Indicator: `BubbleTextView.drawRunningAppIndicatorIfNecessary` (`:998`), `RunningAppState` (`:292`), `TaskbarRunningAppStateAnimationController.kt:103`; state source `TaskbarViewController.java:919` → `TaskbarRecentAppsController.kt:174`. Pill: `TaskbarAllAppsButtonContainer.kt:42`, `:105` (drawable). Spacing: `TaskbarView.java:239`, `TaskbarIconSpecs.kt`. Bar: `TaskbarBackgroundRenderer.drawPersistentBackground` (`:158`). Tooltip: `TaskbarHoverToolTipController.java:91` | Screenshots of every state in §2.3 with real windows; hover and focus by `input mouse` and Tab; insets unchanged (`dumpsys window` content frame) |
| 2 | #9 All Apps panel | `TaskbarAllAppsController.java:195` (`taskbar_all_apps_sheet.xml`), `TaskbarAllAppsSlideInView` (scrim `:266`, motion `:144`), `ActivityAllAppsContainerView.setInsets` (`:1179`), its fill (`:1428`) and search box background (`:816`); blur `TaskbarOverlayController.java:329`, `TaskbarOverlayContext.java:151`; focus `ItemFocusIndicatorHelper.java:103` | Open from the pill, Meta and typing; keyboard walk; search and no results; panel bounds from `uiautomator dump`; the desktop stays sharp |
| 3 | #11 Menus | `ComposePopup.kt:282` (surface), `:521` (dimens), `:528` (springs); `PopupMenuItems.kt:113` (hover, focus), `:377` (row dimens); `WorkspaceLongPressOptions.kt:54` (desktop items); `TaskbarPopupController.java:280`; `ArrowPopup.java:138` for the remaining view popup | Every menu by right-click and by keyboard; bounds; edge flipping |
| 4 | #10 Overview for desks | `DesktopTaskView.kt:157` (background view), `DesktopTaskContentView.kt:39` (clip); `LauncherDepthController.kt:34` (blur gate); `OverviewState.java:169` (scrim) and `:212` (depth) | Overview from the desktop with 1 and 3 windows; wallpaper behind the desk tile; backdrop blur; Clear all |
| 5 | #12 Motion | `AllAppsState.getTransitionDuration` (`:52`), `ArrowPopup.java:82` and `:669`, `ComposePopup.kt:528`, `TaskbarRunningAppStateAnimationController.kt:55`; the tokens as one `OpenBookMotion` object in `openbook/` | Frame timing of each animation (`dumpsys gfxinfo`); Remove animations cuts all of them |

The G14 sees it only in a numbered OpenBook release; the blur budgets in §8 are measured there.

## 10. Open points

- **All Apps blur** works on the panel's own bounds in the overlay window: one blur region, the desktop sharp, the 96 % tint with blur off (C, #9's VM run, 2026-11-03). Its cost on the 890M is measured in the release (§8).
- **Taskbar blur** works on the taskbar's own window region: `BackgroundBlurDrawable` from the taskbar window's `ViewRootImpl` gives SurfaceFlinger one blur region on `VRI-Taskbar`, a window behind the bar shows blurred, and with blur off the region goes and the bar is the 96 % tint (C, #8's VM run, 2026-11-03). Its cost on the 890M is measured in the release (§8).
- **Overview's desk tiles** show the windows at AOSP's positions over the wallpaper (C, #10, §5.3): AOSP 17 lays a desk's windows out side by side in Overview, each with its title and close button.
- **Overview's backdrop cost** on the 890M is measured in the release: it blurs the full screen, as the shade does (§8).
- **Window transitions** (open, minimize, restore) belong to WM Shell. Matching them to §7 is an OpenBook `frameworks/base` change, listed here and not in this milestone.
- **Owner references** are welcome at any point; the tokens are the knobs.
