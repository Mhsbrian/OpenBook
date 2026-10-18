# Desktop flag set v2: the Googlebook flags AOSP 17 declares (ANAL-204)

As of 2026-10-18. Labels: **C** = confirmed (read from source or an image, or shown on a device), **HYPOTHESIS** = not tested. Backlog item B3 of [`googlebook-ui.md`](googlebook-ui.md) §4.

The table of every flag is [`device/anybook/common/desktop/release/googlebook-triage.tsv`](../device/anybook/common/desktop/release/googlebook-triage.tsv); it is rendered at the end of this page. Evidence is in `evidence/2026-10-17-desktop-flags-v2/`.

## Summary

- **All 218 flags are triaged (C):** `googlebook-triage.tsv` gives each one its declaration, its readers in our tree, a category, a decision, a group and a reason.
- **84 are enabled**, in six groups, through the existing value set. With ANAL-169's 79 it now holds **163 flags**. 43 are deferred, 89 skipped, and 2 were dropped after testing.
- **23 of the 218 do nothing in AOSP 17 (C):** no source file in our tree reads them. That includes four of ANAL-201's headline flags: `perfect_edge`, `enable_taskbar_icon_desktop_clicks` (click to minimize), `enable_desktop_taskbar_in_fullscreen_mode` and `notification_animated_action_style_2026`. A fifth, `enable_no_resize_cursor`, is read, but nothing acts on what it reports.
- **Two flags break the desktop in AOSP 17 and were dropped (C).** The issue warned of exactly this:
  - `com.android.window.flags.enable_add_window_decoration_to_all_tasks` crashes SystemUI when a minimized window is restored from the taskbar (`IllegalStateException: Expected non-null decoration container surface` in `DefaultWindowDecoration.updateDragResizeListenerIfNeeded`).
  - `com.android.systemui.start_on_gone_scene_if_no_lockscreen` leaves the notification shade empty. OpenBook disables the lock screen by default, so with this flag SystemUI starts on the Gone scene. The keyguard section that binds the notification stack never runs, and the rows are never laid out. With a PIN set, the same image shows them.
- **What changes on screen (C, Cuttlefish on the Radeon 610M):**
  - box shadows and a 1 px border on every desktop window;
  - new windows cascade in 60 px steps;
  - the windowing pill moves into the maximize menu;
  - Quick Settings tiles get tooltips on hover;
  - the Cast tile works over Ethernet;
  - the power menu blurs what is behind it.
- **Deviation from the issue's plan:** the groups were not built one at a time. Up to five sibling builds were queued on the shared lane, so all six groups went into one image (v2) and each group got its own checks. Each failure was traced to a single flag (stack trace, code, and a runtime A/B test), and the fixes were confirmed in two more images (v3, v4).

## Where the 218 flags come from

- ANAL-201 read the aconfig storage of Googlebook's `ruby` image and of our G14 build (`evidence/2026-10-17-gbos-ui/flags/`).
  - 728 flags are on in Googlebook and off for us.
  - **218 of them are declared in our AOSP 17 tree** (`googlebook-on-openbook-off.tsv`, column `in_aosp_17`).
  - The other 510 belong to code Google hasn't published.
- In our cp2a builds a disabled read-only flag is compiled out. So these 218 can only be turned on at build time, through the value set ANAL-169 started (`docs/aosp-desktop.md` § aconfig flags).
- **Googlebook runs in headless system user mode (C):** `ro.fw.mu.headless_system_user=true` in its `system_ext/etc/build.prop`. That is why it enables the `hsu_*` flags. OpenBook boots a normal system user, so they don't apply to us.

## How each flag was triaged

1. **Declaration (C).** `scripts/ui/flag-facts.py` reads each flag's `.aconfig` entry in our tree (`~/anybook/aosp/src`, `android17-release`, synced 2026-10-15): namespace, purpose (`PURPOSE_BUGFIX` or feature), description, bug.
2. **Readers (C).** The same script lists every non-test source file that reads the flag:
   - the Java/Kotlin accessor (`Flags.enableFoo()`);
   - a wrapper such as `DesktopExperienceFlags.ENABLE_FOO`;
   - the C++/Rust accessor.

   Registries that only list flags (`DesktopExperienceFlags.java`, SurfaceFlinger's `FlagManager`) don't count. **23 flags have no reader at all**: the code they gate is not in AOSP 17, so turning them on changes nothing.
3. **What it guards.** For every flag with readers, the reader lines were read to see what changes. Dependencies were checked too:
   - `blur_on_more_surfaces` also needs `config_enableBlurExpansion` (true by default);
   - the Compose status icons need `scene_container` and `new_status_bar_icons` (both on);
   - `bind_model_using_repository` needs `model_repository` and `simplified_launcher_model_binding` (both on);
   - DocumentsUI's Peek needs `use_material3` (on).
4. **Category:** `visual` (polish), `desktop` (desktop behaviour), `bugfix`, `platform` (system internals with no intended UI change) or `n/a` (telephony, HSUM, Wear, AI services we don't have, and so on).
5. **Decision and reason:**
   - `enable`, in one of six groups;
   - `defer`: useful, but it needs hardware, an owner decision, a config value or a test this pass can't give it;
   - `skip`: no reader, not applicable, or no effect;
   - `drop`: enabled, tested, and broke something.

| Decision | Flags | Why |
|---|---|---|
| enable | 84 | in groups 1–6 below |
| drop | 2 | broke the desktop in testing (above) |
| defer | 43 | process management (9), platform internals (7), laptop hardware for the G14 (6), graphics pipeline for the G14 (5), multi-user policy (4), wallpaper work for B4/B6 (3), and nine single items (listed after the table) |
| skip | 89 | no reader (23), telephony (13), diagnostics only (11), HSUM (8), AI and agent services (5), work profile/DPC (4), tablet hub (4), four already enabled in `release/openbook/` (ANAL-206's `screenshot_remove_nonforced_sound`; ANAL-216's `computer_control_access`, `computer_control_support_v5` and `enable_contextual_cursor_desktop_entrypoints`, for Quire), and 17 other not-applicable or no-effect flags |

The nine single deferred items are: a games list the owner approves, lid-close doze (G14), binder netlink, the enterprise policy refactor, boot-phase parallelism, ARR panels, a Settings migration, an accessibility feature, and `use_android_ui_dispatcher`. That last one was taken out while the empty shade was bisected, and is untested on its own.

## The groups

| Group | Flags | What changes | Targeted test |
|---|---|---|---|
| 1 Window shadows and resizing | `enable_freeform_box_shadows_v2`, `enable_pip_box_shadows_v2`, SurfaceFlinger `color_transform_box_shadows_and_border`, `improve_fluid_resizing_performance`, `enable_no_resize_cursor`, `filter_events_from_irrelevant_devices_in_drag_move_resize` | Box shadows behind desktop and PiP windows; the client-side fluid-resize pipeline | Move and resize a window with the mouse; resize it below its minimum while reading the pointer type; SurfaceFlinger's shadow settings |
| 2 Blur | `com.android.systemui.blur_on_more_surfaces`, `com.android.launcher3.blur_on_more_surfaces` | Blur behind the power menu and volume dialog, Launcher folders and long-press menus. On the G14 it needs B2's `ro.surface_flinger.supports_background_blur=1`; Cuttlefish already has it | Power menu and volume dialog: screenshots and the layers SurfaceFlinger blurs |
| 3 Taskbar and desktop behaviour | `enable_home_screen_peeking`, `enable_stepped_cascading`, `enable_fullscreen_window_controls`, `enable_consolidated_window_options`, `enable_recents_in_taskbar`, `desktop_minimize_last_task_bugfix`, `enable_collapse_sysui_panels_on_taskbar_click`, home-screen file copy/paste and rename, the share sheet's `desktop_ui`, DocumentsUI Peek and approved handler, `press_any_key_to_access_bouncer_2` | New windows cascade; one maximize/layout menu; recent apps in the taskbar | Maximize and restore (Meta+= and the caption button); minimize (Meta+- and the button); restore from the taskbar; the app-chip menu; hovering the maximize button; opening two more apps |
| 4 SystemUI, Launcher and Settings polish | `enable_qs_tile_tooltips`, `hun_timer_pause_on_hover`, `default_hun_expansion`, `expandable_long_press_menu`, `fallback_reveal_animation`, `inline_notification_settings_access`, `animation_library_dynamic_target_resolution`, the Compose status icons (2), `internet_dialog_delegate_legacy_deprecation`, `all_apps_surface`, the share sheet's sticky checkbox, the IME switcher (2), two Settings flags | QS tile tooltips on hover; heads-up behaviour; right-click on a notification; the new long-press menu; Compose status icons | Shade and Quick Settings; hovering a tile; hovering and right-clicking a notification; right-clicking a taskbar icon; All Apps |
| 5 Remaining applicable bugfixes | 42 `PURPOSE_BUGFIX` flags in WM, WM Shell, SystemUI, Launcher3, SurfaceFlinger, media routing, accessibility and the framework | Each fixes a race, leak, flicker or misplacement; none should be visible | Everything above, plus the crash, ANR and SELinux buffers |
| 6 Internal refactors and performance | `only_cache_low_res_task_snapshot`, `add_one_off_handler_leashes`, `status_bar_event_forwarding_modernization`, `enable_taskbar_ui_thread`, `bind_model_using_repository` | Googlebook ships them; no intended visible change | Everything above, plus the crash, ANR and SELinux buffers |

Group 6 was not in the issue's proposal. These flags are neither bugfixes nor visible changes, so they didn't fit groups 1–5. But Googlebook ships them, and they touch the taskbar, the status bar and transitions all the time. They were tested like the rest.

## How the value set is written

`scripts/desktop-flags.py` has a second mode, `--list`:

```bash
scripts/desktop-flags.py --list device/anybook/common/desktop/release/googlebook-triage.tsv [--groups 1,2,...] \
  ~/anybook/aosp/src device/anybook/common/desktop/release
```

- It takes the rows with decision `enable`, limited to `--groups` if given. It writes one `ENABLED`/`READ_ONLY` value file per flag into the same value set as ANAL-169's 79 flags (`aconfig/cp2a/<package>/`).
- Each file's first line names its source (`# From googlebook-triage.tsv group N: reason`).
  - A later `--list` run replaces only the files from that list.
  - Diff mode (`REF OURS SRC OUT`, as before) replaces only its own files (`# Declared in …`).

  So each source can be regenerated on its own. Diff mode, rerun on ANAL-169's dumps with `--extra com.android.providers.media.flags.enable_photopicker_desktop`, gives the same 79 flags as before.
- A plain list, one `<package>.<flag>` per line, works too.
- Declarations are looked up in one index of all `.aconfig` files (about 1.5 s), instead of a `grep -r` per flag.

The value set now holds **163 flags**: 79 from ANAL-169 and 84 from this triage. The G14 product inherits `desktop.mk`, so it gets them too.

## Testing

**Images.** Four builds of `anybook_cf_x86_64_pc-cp2a-userdebug` (`CP2A.260605.016`) from this branch. Each was booted in Cuttlefish on the host's Radeon 610M (`CF_GPU=amd`, `gfxstream_guest_angle`, 1920×1080 at 160 dpi), with B3's VM name and ports:

| Image | Value set | Build | Boot |
|---|---|---|---|
| baseline | ANAL-169's 79 flags (`c861cf4`) | 29 min | 26 s |
| v2 | + groups 1–6, 87 flags (`38cf5ba`) | 31 min | 23 s |
| v3 | v2 without `enable_add_window_decoration_to_all_tasks` and `use_android_ui_dispatcher`, 85 (`8ed9f5f`) | 30 min | 30 s |
| **v4** (committed) | v3 without `start_on_gone_scene_if_no_lockscreen`, 84 (`d5d5acf`) | 29 min | 26 s |

**Per image**, three steps:
1. `scripts/ui/flag-checks.py --reset`. Android 17 restores desk windows, recent tasks and remembered window bounds after a reboot, so the reset deletes them and reboots.
2. `scripts/desktop-capture.sh`, which opens Settings and Files as a user would.
3. `scripts/ui/flag-checks.py`:
   - **Input as a user gives it.** The checks register a virtual USB mouse on the device with the `uinput` tool. WM Shell, Launcher and SystemUI see real hover, click, right-click and drag events, which `input` can't produce. The cursor is steered in a loop against the coordinates of its last event in `dumpsys input`, so pointer acceleration doesn't matter.
   - **Windows:**
     - focus Files by clicking its caption;
     - move it by dragging the caption, and resize it from the corner;
     - drag the corner below the minimum size and read the pointer type while the button is held;
     - open the app-chip menu, and hover the maximize button;
     - maximize and restore, with Meta+= and with the caption button;
     - minimize with the caption button and with Meta+-, then restore from the taskbar;
     - click the focused app's taskbar icon, and right-click it.

     Bounds come from `dumpsys activity activities`, polled until a transition settles.
   - **New windows:** open Calendar and Clock, and record where they land.
   - **Shade and Quick Settings:** open both and hover a tile. Then post a notification as the `shell` user, and hover and right-click it.
   - **Blur:** open the power menu from the Quick Settings power button and the volume dialog, and name the layers SurfaceFlinger blurs behind.
   - **Health:**
     - `aflags list` against the triage: every enabled flag must read `enabled`;
     - the crash buffer, `am_anr` events, `/data/anr` and tombstones;
     - SELinux denials.

**Not testable in the VM:** a heads-up notification. The shell's notification channel has fixed default importance, and DeskClock's timer notification is default importance too. So `hun_timer_pause_on_hover` and `default_hun_expansion` are on the G14 checklist.

## Results per group

Every enabled flag reads `enabled` in `aflags list` on v2, v3 and v4 (`flag-state.tsv` in each evidence directory). On the baseline all of them are compiled out.

| Group | Result | Evidence |
|---|---|---|
| 1 Shadows and resizing | **Box shadows (C):** every desktop window layer carries `BoxShadowSettings` (two 24 px blurs: ambient at 10 % black, key at 20 % black 16 px down) and a 1 px border. The baseline has only the legacy elevation shadow.<br>Moving and resizing with the mouse pass on every image. `improve_fluid_resizing_performance`: resizing works, with no crash or ANR.<br>**`enable_no_resize_cursor` has no visible effect in AOSP 17 (C).** Dragging below the minimum size shows the same diagonal-resize pointer (type 1017) on every image, because `ResizeTaskPositioner` discards the size-violation result the flag turns on | `v4/sf-shadows.txt`, `cmp-windows.png`, `cmp-resize-below-minimum.png` |
| 2 Blur | **The power menu blurs what is behind it (C):** v2–v4 blur its dim layer (`backgroundBlurRadius=34`).<br>The volume dialog is not blurred: AOSP blurs it only when the dialog is vertical, and the desktop one is horizontal.<br>The Quick Settings shade blurs on every image; that is the platform default, not this group | `v4-power-menu.png`, `v4/results.tsv` |
| 3 Taskbar and desktop behaviour | **Stepped cascading (C):** Files opens 60 px right of and below Settings, and Calendar and Clock follow the same steps. The baseline puts Files at the right edge and Clock in the top-left corner.<br>**Consolidated window options (C):** the fullscreen/split/desktop pill moves from the app-chip menu into the maximize button's hover menu.<br>Maximize, restore, minimize and restoring from the taskbar pass on v3 and v4.<br>**`enable_add_window_decoration_to_all_tasks` dropped:** on v2, restoring a minimized window from the taskbar crashed SystemUI. With `ENABLE_ADD_WINDOW_DECORATION_TO_ALL_TASKS`, `relayout` calls `updateDragResizeListenerIfNeeded` even when the task has no decoration container surface | `cmp-cascade.png`, `cmp-maximize-menu.png`, `cmp-app-chip-menu.png`, `v2-all-groups/systemui-crash.txt` |
| 4 Polish | **QS tile tooltips (C):** hovering the Wi-Fi tile shows "Wi-Fi" on v2–v4, and nothing on the baseline.<br>**The taskbar right-click menu** (`expandable_long_press_menu`) offers Add to Taskbar, App info, New Window, Manage Windows and Close.<br>All Apps opens from the taskbar button with `all_apps_surface`.<br>**Notifications:** hovering a row in the shade shows its X, as on the baseline. Right-clicking a row closes the shade on both images, so the inline settings of `inline_notification_settings_access` were not seen in the VM (G14 item 6). The two heads-up flags can't be tested in the VM | `cmp-qs-tooltip.png`, `cmp-taskbar-menu.png`, `cmp-shade.png` |
| 5 Bugfixes | **The Cast tile no longer needs Wi-Fi (C):** on the baseline it is greyed out ("No Wi-Fi or Ethernet") on Cuttlefish's Ethernet; on v2–v4 it is available (`qs_cast_tile_skip_wifi_check`).<br>The rest have no intended visible effect, and none caused a crash, ANR or new SELinux denial | `cmp-quick-settings.png` |
| 6 Internals | No problem from the five that stay on | `v4/results.tsv` |

**The empty notification shade, found on v2 (C).**
- On v2 the shade opened as an empty box. Its rows existed but were never laid out (`0,0-0,0`). The placeholder view model had `expandFraction=1.0`, while the stack itself had `mExpansionFraction=0.0` and `mStackHeight=0.0`.
- v3, without `use_android_ui_dispatcher`, still showed it.
- The binding that feeds the stack (`SharedNotificationContainerBinder` → `NotificationScrollViewBinder`) is called only from the keyguard blueprint's `NotificationStackScrollLayoutSection`.
- OpenBook's framework overlay sets `config_disableLockscreenByDefault=true`. So `start_on_gone_scene_if_no_lockscreen` starts SystemUI on the Gone scene, and that section never binds.
- **The A/B test, on the same v3 image:** after `locksettings set-pin 1234` and a reboot (initial scene Lockscreen), the rows are laid out, with `mExpansionFraction=1.0` and `mStackHeight=380`.
- v4 drops the flag. On v4, with the lock screen disabled as shipped, the rows show (`cmp-shade.png`).

Evidence: `v3/shade-root-cause.txt`, `v2-all-groups/cmp-shade-baseline-vs-v2.png`.

**Health.**
- Crash buffer: baseline empty; v2 one SystemUI crash (the dropped decoration flag); v3 empty; v4 empty.
- No ANR on any image.
- SELinux denials: the same kinds on every image (bootanim `gpu_service`, `init` tracefs, `gceservice` `zygote_config_prop`), all present before this work. Nothing new.

## Open items and G14 checks

**G14 check items** (posted on ANAL-192 for the next stick):
1. Window shadows: a box shadow and a 1 px border around every desktop window, in light and dark theme.
2. New windows cascade in steps.
3. Hover a Quick Settings tile: a tooltip appears after about a second.
4. Hover the maximize button: one menu with Maximize, Resize and the fullscreen/split/desktop row.
5. Minimize a window and restore it from the taskbar: no SystemUI restart.
6. Open the notification shade with a few notifications. The rows show; hovering one shows its X; right-clicking one opens its settings.
7. Heads-up (not reproducible in the VM): a heads-up notification stays while hovered and opens expanded.
8. Power menu over a window: the background blurs. **This needs B2's** `ro.surface_flinger.supports_background_blur=1` on the G14 product; without it nothing blurs.
9. Health: `logcat -b crash` is empty, and there is no `am_anr`.

**Open:**
- `enable_no_resize_cursor` and the 23 flags with no reader need Google's newer code. Revisit them on the next AOSP drop; `scripts/ui/flag-facts.py` recounts the readers.
- Recheck the two dropped flags on the next AOSP drop too:
  - The decoration crash looks like incomplete code.
  - `start_on_gone_scene_if_no_lockscreen` is what we'd want for a laptop without a lock screen, once the stack binding no longer depends on the keyguard.
- `use_android_ui_dispatcher` needs a test on its own.
- The other deferred flags each have their reason in the table:
  - the laptop-hardware and graphics ones belong to the G14 tracks;
  - the wallpaper ones belong to B4/B6;
  - `launch_games_in_fullscreen_by_allowlist` needs an owner-approved games list (Googlebook ships 26 package names in `config_desktopLaunchInFullscreenPackages`).
- No benchmark was run for groups 1 and 6 (`improve_fluid_resizing_performance`, `only_cache_low_res_task_snapshot`). The VM runs at 60 Hz on a shared host, so measure on the G14.

## Reproduce

```bash
# Facts and the triage table (the decisions are hand-written in scripts/ui/flag-triage.py; the TSV is the record)
scripts/ui/flag-facts.py evidence/2026-10-17-gbos-ui/flags/googlebook-on-openbook-off.tsv ~/anybook/aosp/src > facts.tsv
scripts/ui/flag-triage.py facts.tsv > device/anybook/common/desktop/release/googlebook-triage.tsv
scripts/ui/flag-triage-md.py device/anybook/common/desktop/release/googlebook-triage.tsv
# Value set: every enabled group (what is committed), or --groups to bisect
scripts/desktop-flags.py --list device/anybook/common/desktop/release/googlebook-triage.tsv ~/anybook/aosp/src \
  device/anybook/common/desktop/release
# Build under the lane lock; snapshot the Cuttlefish product so the VM can boot after the lock is released
flock ~/anybook/aosp/.lane.lock bash -c 'scripts/aosp-docker.sh /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug &&
  S=~/anybook/aosp/cf/b3-out O=~/anybook/aosp/src/out P=anybook_vsoc_x86_64 &&
  mkdir -p $S/target/product/$P $S/host/linux-x86 &&
  find $O/target/product/$P -maxdepth 1 -type f -exec cp --reflink=auto -t $S/target/product/$P {} + &&
  cp --reflink=auto $O/host/linux-x86/cvd-host_package.tar.gz $S/host/linux-x86/'
# Boot (B3's VM name and ports), capture, check, tear down
export CF_OUT=~/anybook/aosp/cf/b3-out CF_NAME=anybook-cf-b3 CF_STAGE=~/anybook/aosp/cf/b3 CF_ADB_PORT=16533 \
  CF_WEBRTC_PORT=11533 CF_DEVICE=anybook_vsoc_x86_64 CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle ANDROID_ADB_SERVER_PORT=5133
scripts/cf-boot.sh up && scripts/cf-boot.sh wait && adb connect 127.0.0.1:16533
scripts/ui/flag-checks.py 127.0.0.1:16533 --reset          # forget restored desks and recents, reboot
scripts/desktop-capture.sh 127.0.0.1:16533 OUT/desktop
scripts/ui/flag-checks.py 127.0.0.1:16533 OUT/checks
scripts/cf-boot.sh down
```

## The triage table

218 flags: 43 defer, 2 drop, 6 enable (group 1), 2 enable (group 2), 13 enable (group 3), 16 enable (group 4), 42 enable (group 5), 5 enable (group 6), 89 skip.

### Enabled (84)

| Group | Flag | Category | Readers | Reason |
|---|---|---|---|---|
| 1 | `com.android.graphics.surfaceflinger.flags.color_transform_box_shadows_and_border` | bugfix | 1 | applies the colour transform to box shadows and borders in RenderEngine; pairs with the shadows |
| 1 | `com.android.window.flags.filter_events_from_irrelevant_devices_in_drag_move_resize` | bugfix | 1 | drag-move/resize ignores events from a second input device |
| 1 | `com.android.window.flags.enable_no_resize_cursor` | desktop | 1 | no visible effect in AOSP 17 (C): DragPositioningCallbackUtility reports the size-constraint violation, but ResizeTaskPositioner discards it and the cursor stays a resize arrow (type 1017 on both builds); harmless, kept for when the cursor code lands |
| 1 | `com.android.window.flags.improve_fluid_resizing_performance` | desktop | 19 | client-side fluid-resize pipeline (batched config changes, caption insets); Googlebook ships it |
| 1 | `com.android.window.flags.enable_freeform_box_shadows_v2` | visual | 2 | box shadows on freeform windows (WM Shell window decoration) |
| 1 | `com.android.wm.shell.enable_pip_box_shadows_v2` | visual | 5 | box shadows on picture-in-picture windows |
| 2 | `com.android.launcher3.blur_on_more_surfaces` | visual | 5 | blur behind Launcher folders and long-press menus |
| 2 | `com.android.systemui.blur_on_more_surfaces` | visual | 5 | blur behind the power menu and volume dialog (needs config_enableBlurExpansion, default true) |
| 3 | `com.android.launcher3.enable_collapse_sysui_panels_on_taskbar_click` | bugfix | 1 | a taskbar click collapses an open notification shade |
| 3 | `com.android.window.flags.desktop_minimize_last_task_bugfix` | bugfix | 1 | minimizing the last window of a desk animates and stays in desktop mode |
| 3 | `com.android.documentsui.flags.use_approved_document_handler` | desktop | 1 | Files: opens documents with an approved handler app; needs use_material3 |
| 3 | `com.android.documentsui.flags.use_peek_preview_ro` | desktop | 2 | Files: Peek preview of a file (desktop quick look); needs use_material3, which is on |
| 3 | `com.android.intentresolver.desktop_ui` | desktop | 2 | desktop layout for the share sheet (Chooser) |
| 3 | `com.android.launcher3.enable_home_screen_files_copy_paste` | desktop | 1 | copy/paste for files on the home screen (we ship show_files_on_home_screen) |
| 3 | `com.android.launcher3.enable_home_screen_files_renaming` | desktop | 1 | rename files on the home screen |
| 3 | `com.android.systemui.press_any_key_to_access_bouncer_2` | desktop | 2 | on the lock screen any key opens the bouncer (keyboard laptops) |
| 3 | `com.android.systemui.shared.enable_recents_in_taskbar` | desktop | 6 | taskbar shows recent apps instead of hotseat predictions |
| 3 | `com.android.window.flags.enable_consolidated_window_options` | desktop | 3 | one maximize/layout menu instead of the windowing pill plus menu |
| 3 | `com.android.window.flags.enable_fullscreen_window_controls` | desktop | 1 | app header with window controls on fullscreen tasks in desktop mode |
| 3 | `com.android.window.flags.enable_home_screen_peeking` | desktop | 4 | peek at the home screen behind desktop windows (action corner, WM Shell) |
| 3 | `com.android.window.flags.enable_stepped_cascading` | desktop | 2 | new windows cascade in steps instead of all opening at one spot |
| 4 | `com.android.launcher3.expandable_long_press_menu` | bugfix | 5 | Compose long-press menu with expandable sections (Launcher and taskbar) |
| 4 | `com.android.settings.flags.storage_summary_percentage_alignment` | bugfix | 2 | storage percentage formatting in Settings (RTL) |
| 4 | `com.android.systemui.enable_qs_tile_tooltips` | bugfix | 1 | tooltips on Quick Settings tiles (mouse hover) |
| 4 | `android.view.inputmethod.ime_switcher_button_in_navbar_setting` | desktop | 2 | setting to show or hide the IME switcher button |
| 4 | `com.android.systemui.hun_timer_pause_on_hover` | desktop | 1 | hovering a heads-up notification pauses its dismiss timer |
| 4 | `com.android.systemui.inline_notification_settings_access` | desktop | 1 | right-click (context click) on a notification opens its settings |
| 4 | `android.view.inputmethod.ime_switcher_menu_systemui_style_update` | visual | 2 | SystemUI-styled IME switcher menu (base of ime_switcher_menu_systemui_style_update_desktop, which we ship) |
| 4 | `com.android.intentresolver.include_link_sticky_checkbox` | visual | 1 | share sheet remembers the include-link checkbox |
| 4 | `com.android.launcher3.all_apps_surface` | visual | 6 | All Apps drawn on its own surface |
| 4 | `com.android.launcher3.fallback_reveal_animation` | visual | 1 | Launcher reveal animation when another process runs the transition |
| 4 | `com.android.settings.flags.show_footer_buttons_on_password_confirm` | visual | 1 | Clear/Confirm buttons on the Settings password confirmation screen |
| 4 | `com.android.systemui.animation_library_dynamic_target_resolution` | visual | 1 | launch/return animations pick their target dynamically |
| 4 | `com.android.systemui.default_hun_expansion` | visual | 1 | heads-up notifications open expanded |
| 4 | `com.android.systemui.internet_dialog_delegate_legacy_deprecation` | visual | 2 | Internet tile uses the details view instead of the legacy dialog (we ship qs_tile_detailed_view) |
| 4 | `com.android.systemui.status_bar_system_status_icons_in_compose` | visual | 1 | status bar system icons drawn in Compose (needs scene_container and new_status_bar_icons, both on) |
| 4 | `com.android.systemui.status_icons_in_compose_refresh` | visual | 1 | refreshed Compose status icons; pairs with status_bar_system_status_icons_in_compose |
| 5 | `android.app.metric_value_alternative_strings` | bugfix | 5 | notification metric values pick a fitting format (10,000 / 10k) |
| 5 | `android.content.res.resources_manager_cache_leak_cleanup` | bugfix | 1 | ResourcesManager frees expired resource impls (memory leak) |
| 5 | `android.service.dreams.drive_dream_state_from_occlusion` | bugfix | 2 | dream state from WM occlusion (race fix) |
| 5 | `android.view.accessibility.fix_a11y_lock_screen_jank` | bugfix | 3 | accessibility lock transition |
| 5 | `android.view.inputmethod.set_self_visibility_only_once` | bugfix | 1 | IME visibility set once |
| 5 | `com.android.graphics.surfaceflinger.flags.hwc_buffer_override_skip` | bugfix | 1 | SurfaceFlinger buffer-override check includes non-client layers |
| 5 | `com.android.launcher3.enable_drag_start_end_multi_dispatch` | bugfix | 1 | Launcher drag start/end reach every listener |
| 5 | `com.android.media.flags.make_device_selection_behaviour_respect_route_listing_preference` | bugfix | 2 | media output switcher honours RouteListingPreference |
| 5 | `com.android.media.flags.move_output_switcher_calls_to_background_thread` | bugfix | 1 | media output switcher off the main thread |
| 5 | `com.android.server.accessibility.enable_magnification_hide_settings_button_in_temporary_mode` | bugfix | 1 | magnification settings button |
| 5 | `com.android.server.accessibility.fix_full_screen_magnification_event_time_corruption` | bugfix | 1 | full-screen magnification event times |
| 5 | `com.android.server.accessibility.send_hover_exit_on_gesture_interruption` | bugfix | 1 | touch exploration hover exit |
| 5 | `com.android.systemui.async_notification_launch_ipc` | bugfix | 1 | notification clicks do their binder calls off the main thread |
| 5 | `com.android.systemui.clipboard_overlay_multiuser` | bugfix | 6 | clipboard overlay uses the current user's context |
| 5 | `com.android.systemui.enable_compose_external_display_dialog` | bugfix | 1 | Compose dialog for connecting an external display |
| 5 | `com.android.systemui.fix_predictive_back_clipping` | bugfix | 2 | predictive-back animation clipping with a pinned taskbar |
| 5 | `com.android.systemui.floating_menu_adjust_cutout_avoidance` | bugfix | 1 | accessibility floating menu placement |
| 5 | `com.android.systemui.handle_boot_completed_on_separate_thread` | bugfix | 1 | SystemUI handles LOCKED_BOOT_COMPLETED off the main thread |
| 5 | `com.android.systemui.nesteddraggable_gesture_pickup` | bugfix | 1 | shade drag gesture pickup in NestedDraggable |
| 5 | `com.android.systemui.nssl_touch_dispatch_fix` | bugfix | 1 | notification list sends whole touch streams to Compose (scene container is on) |
| 5 | `com.android.systemui.qs_cast_tile_skip_wifi_check` | bugfix | 1 | Cast tile also works on Ethernet |
| 5 | `com.android.systemui.stl_fling_animation_consume_overshoot` | bugfix | 1 | shade fling animation handles overshoot |
| 5 | `com.android.systemui.wakefulness_events_shared_flow` | bugfix | 2 | PowerInteractor wakefulness events as a SharedFlow |
| 5 | `com.android.systemui.wakefulness_for_animations` | bugfix | 3 | keyguard animations use the right wakefulness signal |
| 5 | `com.android.window.flags.add_bg_color_for_transparent_bubbles` | bugfix | 1 | bubbles get a background colour (no transparent layers) |
| 5 | `com.android.window.flags.camera_compat_ignore_requested_orientation_allowed` | bugfix | 1 | camera compat in freeform windows |
| 5 | `com.android.window.flags.camera_compat_update_treatment_on_rotation` | bugfix | 1 | camera compat treatment follows display rotation |
| 5 | `com.android.window.flags.consolidate_remove_starting_window_from_task` | bugfix | 1 | starting windows are removed once all activities draw |
| 5 | `com.android.window.flags.enable_focus_reset_on_display_removal` | bugfix | 1 | focus returns to the default display when an external one is unplugged |
| 5 | `com.android.window.flags.enable_split_dismiss_animation_v2` | bugfix | 1 | split-screen dismiss animation |
| 5 | `com.android.window.flags.fix_multi_window_task_focus_change` | bugfix | 1 | focus does not jump to a lower multi-window task |
| 5 | `com.android.window.flags.prioritize_visible_task_display_over_source` | bugfix | 1 | launch display follows the visible task |
| 5 | `com.android.window.flags.reduce_window_traversal_on_entering` | bugfix | 1 | fewer window traversals after enter animations |
| 5 | `com.android.window.flags.remove_starting_window_when_commit_invisible` | bugfix | 1 | orphaned starting windows are cleaned up |
| 5 | `com.android.window.flags.report_missed_enter_anim_on_resume` | bugfix | 2 | enter-animation-complete is delivered after a late attach |
| 5 | `com.android.window.flags.return_windowless_root_views_in_wmglobal_getwindowview` | bugfix | 1 | getWindowView finds SurfaceControlViewHost roots |
| 5 | `com.android.window.flags.show_ime_layering_target_when_adding` | bugfix | 2 | no IME flicker when a layering target is added |
| 5 | `com.android.window.flags.update_dims_when_window_shown` | bugfix | 1 | dim layers update when a window first draws |
| 5 | `com.android.window.flags.use_snapshot_fixed_rotation` | bugfix | 1 | snapshot starting windows use the snapshot's rotation |
| 5 | `com.android.wm.shell.fix_bubble_bar_stashing_with_hardware_keyboard` | bugfix | 1 | bubble bar stashes correctly with a hardware keyboard |
| 5 | `com.android.wm.shell.fix_bubble_bar_visibility_update_dropped` | bugfix | 1 | bubble bar visibility updates survive interrupted animations |
| 5 | `com.android.wm.shell.fix_bubbles_stack_visible_in_immersive` | bugfix | 1 | bubble stack hidden in immersive mode |
| 6 | `com.android.launcher3.bind_model_using_repository` | platform | 1 | Launcher model binds through repositories (model_repository and simplified binding are on) |
| 6 | `com.android.launcher3.enable_taskbar_ui_thread` | platform | 15 | taskbar runs on its own UI thread |
| 6 | `com.android.systemui.status_bar_event_forwarding_modernization` | platform | 1 | status bar touch forwarding from Compose (scene container is on) |
| 6 | `com.android.window.flags.only_cache_low_res_task_snapshot` | platform | 9 | task snapshots: only low-res cached in system_server (memory) |
| 6 | `com.android.wm.shell.add_one_off_handler_leashes` | platform | 4 | one-off transition handlers get their own leashes |

### Dropped after testing (2)

| Group | Flag | Category | Readers | Reason |
|---|---|---|---|---|
|  | `com.android.window.flags.enable_add_window_decoration_to_all_tasks` | bugfix | 5 | crashes SystemUI in AOSP 17 (C, ANAL-204 v2 build): restoring a minimized window from the taskbar calls DefaultWindowDecoration.updateDragResizeListenerIfNeeded with no decoration container surface (IllegalStateException on wmshell.main); the flag's code is incomplete in this snapshot |
|  | `com.android.systemui.start_on_gone_scene_if_no_lockscreen` | desktop | 1 | empties the notification shade in AOSP 17 (C, ANAL-204 v2 and v3 builds): OpenBook disables the lock screen by default (config_disableLockscreenByDefault), so SystemUI starts on the Gone scene, the keyguard blueprint's NotificationStackScrollLayoutSection never binds the stack, and its rows are never laid out; with a PIN set (initial scene Lockscreen) the same image shows them |

### Deferred (43)

| Group | Flag | Category | Readers | Reason |
|---|---|---|---|---|
|  | `com.android.server.deviceidle.quick_doze_on_lid_close` | desktop | 1 | lid-close Quick Doze: no lid in Cuttlefish; take with the G14 power work (docs/power-input.md) |
|  | `com.android.window.flags.launch_games_in_fullscreen_by_allowlist` | desktop | 1 | only acts on config_desktopLaunchInFullscreenPackages, empty in AOSP (Googlebook lists 26 games); needs an owner-approved list |
|  | `android.app.admin.flags.policy_transparency_refactor_enabled` | platform | 57 | enterprise policy refactor across 57 files; no DPC to exercise it |
|  | `android.hardware.usb.flags.enable_pci_tunnel_control` | platform | 2 | laptop hardware: needs the G14 (USB4, USB audio, RAPL, ambient light) |
|  | `android.hardware.usb.flags.enable_persistent_usb_device_permissions` | platform | 6 | laptop hardware: needs the G14 (USB4, USB audio, RAPL, ambient light) |
|  | `android.multiuser.dont_show_other_users_apps_to_admin` | platform | 3 | multi-user policy; revisit with multi-user support |
|  | `android.multiuser.enable_explicit_static_overlay_allowlisting` | platform | 1 | multi-user policy; revisit with multi-user support |
|  | `android.multiuser.user_filter_refactoring` | platform | 3 | multi-user policy; revisit with multi-user support |
|  | `android.os.binder_netlink_enabled` | platform | 1 | kernel-dependent (binder netlink); check the G14 and Cuttlefish kernels first |
|  | `android.os.disallow_add_guest` | platform | 6 | multi-user policy; revisit with multi-user support |
|  | `android.security.enable_service_side_credential_type_cache` | platform | 1 | platform internals with no desktop effect (credential cache, OTA snapshots, idle quotas, display data store, screen-capture filter API, USB HAL) |
|  | `android.view.accessibility.enable_captions_easy_reader` | platform | 2 | accessibility feature, not a desktop change; take with an accessibility pass |
|  | `android.view.flags.toolkit_disable_category_on_mrr` | platform | 1 | graphics pipeline change; test on the G14 (drm_hwcomposer, 890M) rather than the VM |
|  | `com.android.btaudio.hal.flags.leaudio_iso_parameter_update` | platform | 1 | laptop hardware: needs the G14 (USB4, USB audio, RAPL, ambient light) |
|  | `com.android.graphics.surfaceflinger.flags.graphite_renderengine_preview_rollout` | platform | 1 | graphics pipeline change; test on the G14 (drm_hwcomposer, 890M) rather than the VM |
|  | `com.android.graphics.surfaceflinger.flags.mirror_with_crop` | platform | 3 | graphics pipeline change; test on the G14 (drm_hwcomposer, 890M) rather than the VM |
|  | `com.android.graphics.surfaceflinger.flags.modeset_multi_display` | platform | 3 | graphics pipeline change; test on the G14 (drm_hwcomposer, 890M) rather than the VM |
|  | `com.android.graphics.surfaceflinger.flags.use_last_vsync_predict` | platform | 1 | adaptive-refresh-rate panels only (Pixel ARR) |
|  | `com.android.graphics.surfaceflinger.flags.wb_framebuffersurface2` | platform | 1 | graphics pipeline change; test on the G14 (drm_hwcomposer, 890M) rather than the VM |
|  | `com.android.hardware.input.hid_api` | platform | 4 | platform internals with no desktop effect (credential cache, OTA snapshots, idle quotas, display data store, screen-capture filter API, USB HAL) |
|  | `com.android.libsnapshot.memory_efficient_data_structures` | platform | 1 | platform internals with no desktop effect (credential cache, OTA snapshots, idle quotas, display data store, screen-capture filter API, USB HAL) |
|  | `com.android.server.am.enable_capability_controller_computation` | platform | 6 | process management (OomAdjuster / capabilities): no visible change; evaluate under memory pressure, not in a UI pass |
|  | `com.android.server.am.encapsulate_cur_oom_adj` | platform | 1 | process management (OomAdjuster / capabilities): no visible change; evaluate under memory pressure, not in a UI pass |
|  | `com.android.server.am.encapsulate_cur_proc_state` | platform | 3 | process management (OomAdjuster / capabilities): no visible change; evaluate under memory pressure, not in a UI pass |
|  | `com.android.server.am.explicit_cpu_capability_for_top_processes` | platform | 2 | process management (OomAdjuster / capabilities): no visible change; evaluate under memory pressure, not in a UI pass |
|  | `com.android.server.am.set_initial_oom_score_adj` | platform | 1 | process management (OomAdjuster / capabilities): no visible change; evaluate under memory pressure, not in a UI pass |
|  | `com.android.server.am.set_initial_oom_score_adj_for_type_added_application` | platform | 1 | process management (OomAdjuster / capabilities): no visible change; evaluate under memory pressure, not in a UI pass |
|  | `com.android.server.am.set_initial_oom_score_adj_for_type_broadcast` | platform | 1 | process management (OomAdjuster / capabilities): no visible change; evaluate under memory pressure, not in a UI pass |
|  | `com.android.server.am.set_initial_oom_score_adj_for_type_link_failed` | platform | 1 | process management (OomAdjuster / capabilities): no visible change; evaluate under memory pressure, not in a UI pass |
|  | `com.android.server.am.set_initial_oom_score_adj_for_type_on_hold` | platform | 1 | process management (OomAdjuster / capabilities): no visible change; evaluate under memory pressure, not in a UI pass |
|  | `com.android.server.deviceidle.support_allow_while_idle_quota_zero` | platform | 1 | platform internals with no desktop effect (credential cache, OTA snapshots, idle quotas, display data store, screen-capture filter API, USB HAL) |
|  | `com.android.server.display.feature.flags.refactor_persistent_data_store` | platform | 1 | platform internals with no desktop effect (credential cache, OTA snapshots, idle quotas, display data store, screen-capture filter API, USB HAL) |
|  | `com.android.server.display.feature.flags.smart_adaptive_brightness` | platform | 1 | laptop hardware: needs the G14 (USB4, USB audio, RAPL, ambient light) |
|  | `com.android.server.flags.parallelize_onbootphase` | platform | 2 | boot-time change in system_server; measure with boot timing separately |
|  | `com.android.server.power.optimization.x86_cpu_energy_attribution` | platform | 3 | laptop hardware: needs the G14 (USB4, USB audio, RAPL, ambient light) |
|  | `com.android.server.usb.flags.wait_for_alsa_scan_results_if_has_audio_interface` | platform | 1 | laptop hardware: needs the G14 (USB4, USB audio, RAPL, ambient light) |
|  | `com.android.settings.flags.catalyst_migration_26q3` | platform | 3 | Settings preference-framework migration (battery screens); no desktop change |
|  | `com.android.systemui.use_android_ui_dispatcher` | platform | 1 | untested on its own: taken out of v3 while the empty shade was bisected, which turned out to be start_on_gone_scene_if_no_lockscreen; it moves every @Main coroutine in SystemUI to Compose's AndroidUiDispatcher, so retest it alone |
|  | `com.android.window.flags.screen_capture_exclusion_flags` | platform | 1 | platform internals with no desktop effect (credential cache, OTA snapshots, idle quotas, display data store, screen-capture filter API, USB HAL) |
|  | `suspend_service.flags.enable_pm_fs_abort` | platform | 2 | platform internals with no desktop effect (credential cache, OTA snapshots, idle quotas, display data store, screen-capture filter API, USB HAL) |
|  | `android.app.optimize_default_wallpaper` | visual | 1 | only acts with config_optimizeDefaultWallpaper=true (Googlebook sets it); take with the wallpaper work (B4) |
|  | `com.android.wallpaper.refactor_wallpaper_info_flag` | visual | 1 | Wallpaper picker refactor; take with the wallpaper work (B4/B6) |
|  | `com.android.wallpaper.refactor_wallpaper_preview_screen_flag` | visual | 8 | Wallpaper picker refactor; take with the wallpaper work (B4/B6) |

### Skipped (89)

| Group | Flag | Category | Readers | Reason |
|---|---|---|---|---|
|  | `android.location.flags.use_settings_main_switch_for_scanning` | bugfix | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.graphics.libgui.flags.allocate_buffer_priority_inheritance` | bugfix | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.systemui.screenshot_remove_nonforced_sound` | bugfix | 1 | already on: ANAL-206 (B5) enables it in release/openbook/ (no screenshot shutter sound unless forced); not duplicated in this value set |
|  | `com.android.window.flags.appheader_launch_color_bugfix` | bugfix | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.window.flags.show_when_locked_desktop_bugfix` | bugfix | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.wm.shell.consolidate_split_keyboard_shortcut_controllers` | bugfix | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.launcher3.enable_taskbar_customization` | desktop | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.launcher3.enable_taskbar_icon_desktop_clicks` | desktop | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.window.flags.enable_desktop_taskbar_in_fullscreen_mode` | desktop | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.window.flags.enable_fullscreen_in_new_task_preference` | desktop | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `android.app.admin.flags.add_user_info_in_profile_off_deadline_alarm` | n/a | 1 | work profile / device-owner (DPC) only; OpenBook ships no DPC |
|  | `android.app.admin.flags.check_personal_suspension_for_all_profiles` | n/a | 1 | work profile / device-owner (DPC) only; OpenBook ships no DPC |
|  | `android.app.admin.flags.use_hardened_frp_active_check` | n/a | 1 | work profile / device-owner (DPC) only; OpenBook ships no DPC |
|  | `android.app.contextualsearch.flags.include_audio_playing_status` | n/a | 1 | AI/agent services OpenBook does not have (computer control, contextual search, attention, summaries, Magic Pointer) |
|  | `android.app.enable_automation_notification_ui` | n/a | 2 | AI/agent services OpenBook does not have (computer control, contextual search, attention, summaries, Magic Pointer) |
|  | `android.app.supervision.flags.enable_remove_device_admin_checks_for_reset_password_token` | n/a | 1 | Google supervision (Family Link) app |
|  | `android.app.supervision.flags.enable_supported_apps_retrieval_updates` | n/a | 2 | Google supervision (Family Link) app |
|  | `android.hardware.usb.flags.mtp_download_io_order_improvement` | n/a | 1 | MTP device (gadget) mode; a laptop is the USB host |
|  | `android.hardware.usb.flags.mtp_ffs_handle_close_concurrency_fix` | n/a | 1 | MTP device (gadget) mode; a laptop is the USB host |
|  | `android.location.flags.disable_hardware_ar` | n/a | 1 | legacy hardware activity recognition; no such sensor |
|  | `android.media.audio.enable_ringtone_haptics_customization` | n/a | 4 | needs a vibrator (phones) |
|  | `android.multiuser.hsu_allowlist_activities` | n/a | 5 | headless system user mode (HSUM) only: Googlebook runs in HSUM (ro.fw.mu.headless_system_user=true in its system_ext build.prop), OpenBook does not |
|  | `android.multiuser.hsu_allowlist_notifications` | n/a | 2 | headless system user mode (HSUM) only: Googlebook runs in HSUM (ro.fw.mu.headless_system_user=true in its system_ext build.prop), OpenBook does not |
|  | `android.multiuser.hsu_app_management` | n/a | 17 | headless system user mode (HSUM) only: Googlebook runs in HSUM (ro.fw.mu.headless_system_user=true in its system_ext build.prop), OpenBook does not |
|  | `android.multiuser.hsu_device_provisioner` | n/a | 1 | headless system user mode (HSUM) only: Googlebook runs in HSUM (ro.fw.mu.headless_system_user=true in its system_ext build.prop), OpenBook does not |
|  | `android.multiuser.hsu_disable_notifications` | n/a | 2 | headless system user mode (HSUM) only: Googlebook runs in HSUM (ro.fw.mu.headless_system_user=true in its system_ext build.prop), OpenBook does not |
|  | `android.os.login_add_user_enforcement` | n/a | 1 | headless system user mode (HSUM) only: Googlebook runs in HSUM (ro.fw.mu.headless_system_user=true in its system_ext build.prop), OpenBook does not |
|  | `android.service.dreams.dreams_switcher` | n/a | 8 | tablet hub / dream switcher |
|  | `android.service.dreams.dreams_switcher_edge_swipe_enabled` | n/a | 1 | tablet hub / dream switcher |
|  | `android.service.dreams.dreams_switcher_long_press_enabled` | n/a | 1 | tablet hub / dream switcher |
|  | `com.android.aconfig_new_storage.enable_bootloader_sync` | n/a | 1 | bootloader reads flags from misc; OpenBook boots through UEFI/GRUB |
|  | `com.android.input.flags.enable_attention_service_apis` | n/a | 4 | AI/agent services OpenBook does not have (computer control, contextual search, attention, summaries, Magic Pointer) |
|  | `com.android.internal.telephony.flags.downloadable_subscription_include_carrier_identifier_internal` | n/a | 4 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.internal.telephony.flags.enable_ons_cleanup` | n/a | 2 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.internal.telephony.flags.enforce_emergency_exit_multi_call` | n/a | 1 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.internal.telephony.flags.fix_sql_injection_hbpcd` | n/a | 1 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.internal.telephony.flags.ignore_incall_mmi_for_emergency` | n/a | 2 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.internal.telephony.flags.init_rcs_provisioning_monitor_async` | n/a | 1 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.internal.telephony.flags.new_satellite_icon` | n/a | 4 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.internal.telephony.flags.offload_startup_binder_calls` | n/a | 2 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.internal.telephony.flags.ons_handler_thread` | n/a | 1 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.internal.telephony.flags.satellite_data_metrics_enhancement` | n/a | 1 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.internal.telephony.flags.support_same_uri_conference_srvcc` | n/a | 2 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.launcher3.enable_cue_bar_desktop_form_factor` | n/a | 1 | AI/agent services OpenBook does not have (computer control, contextual search, attention, summaries, Magic Pointer) |
|  | `com.android.media.audio.camera_shutter_sound` | n/a | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.server.accessibility.enable_color_daltonizer_in_suw` | n/a | 2 | setup wizard / Google services UI we do not ship |
|  | `com.android.server.backup.enable_synchronous_restore_session_cleanup` | n/a | 1 | fixes flaky backup tests only |
|  | `com.android.server.connectivity.sync_airplane_mode_with_watches` | n/a | 7 | Wear / watch sync |
|  | `com.android.server.notification.favorites_incoming_call_lights` | n/a | 3 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.server.notification.notification_vibration_in_sound_uri` | n/a | 4 | needs a vibrator (phones) |
|  | `com.android.server.usb.flags.enable_camera_policy_check` | n/a | 1 | work profile / device-owner (DPC) only; OpenBook ships no DPC |
|  | `com.android.settings.flags.enable_binary_transparency_in_safety_center` | n/a | 1 | setup wizard / Google services UI we do not ship |
|  | `com.android.settings.flags.enable_satellite_toggle` | n/a | 2 | telephony / modem (OpenBook laptops have none) |
|  | `com.android.settings.flags.owl_v2_enabled` | n/a | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.systemui.floating_menu_on_headless_user` | n/a | 1 | headless system user mode (HSUM) only: Googlebook runs in HSUM (ro.fw.mu.headless_system_user=true in its system_ext build.prop), OpenBook does not |
|  | `com.android.systemui.hsu_qs_changes` | n/a | 7 | headless system user mode (HSUM) only: Googlebook runs in HSUM (ro.fw.mu.headless_system_user=true in its system_ext build.prop), OpenBook does not |
|  | `com.android.systemui.notification_summarization_allow_animation` | n/a | 1 | AI/agent services OpenBook does not have (computer control, contextual search, attention, summaries, Magic Pointer) |
|  | `com.android.systemui.upright_charging_dreams_setup` | n/a | 1 | tablet hub / dream switcher |
|  | `com.android.wallpaper.enable_effect_for_cat_smile` | n/a | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.window.flags.activity_start_interceptor_speedbumps` | n/a | 1 | digital-wellbeing distracting-app interception; no wellbeing app |
|  | `android.app.admin.flags.introduce_generic_provisioning_error` | platform | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `android.app.backup_restore_logging` | platform | 1 | diagnostics, logging or metrics only; no user-visible change |
|  | `android.companion.virtualdevice.flags.computer_control_access` | platform | 11 | already on: ANAL-216 (Quire Q2) enables it in release/openbook/ (computer control for Quire); not duplicated in this value set |
|  | `android.companion.virtualdevice.flags.computer_control_support_v5` | platform | 1 | already on: ANAL-216 (Quire Q2) enables it in release/openbook/ (computer control version 5); not duplicated in this value set |
|  | `android.hardware.usb.flags.enable_usb_dp_upstream_irq` | platform | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `android.hardware.usb.flags.enable_usbdp_utils_library` | platform | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `android.location.flags.location_auditing` | platform | 2 | diagnostics, logging or metrics only; no user-visible change |
|  | `android.multiuser.user_removal_minor_apis_2026` | platform | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `android.tracing.protolog_auto_clear_incremental_state` | platform | 1 | diagnostics, logging or metrics only; no user-visible change |
|  | `com.android.graphics.libgui.flags.wb_ring_buffer` | platform | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.hardware.input.enable_contextual_cursor_desktop_entrypoints` | platform | 5 | already on: ANAL-216 (Quire Q2) enables it in release/openbook/ (the pointer shake starts contextual search, which Quire handles); not duplicated in this value set |
|  | `com.android.hardware.input.enable_poem_input_customization` | platform | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.launcher3.enable_recents_window_proto_log` | platform | 1 | diagnostics, logging or metrics only; no user-visible change |
|  | `com.android.launcher3.enable_state_manager_proto_log` | platform | 1 | diagnostics, logging or metrics only; no user-visible change |
|  | `com.android.server.adb.flags.use_pairing_server_v2` | platform | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.server.am.enable_long_method_tracing_on_anr_timer` | platform | 2 | diagnostics, logging or metrics only; no user-visible change |
|  | `com.android.server.stats.add_webview_pin_quota_puller` | platform | 1 | diagnostics, logging or metrics only; no user-visible change |
|  | `com.android.server.ui_latency_stats.ui_latency_stats_service` | platform | 6 | diagnostics, logging or metrics only; no user-visible change |
|  | `com.android.server.utils.long_method_trace` | platform | 1 | diagnostics, logging or metrics only; no user-visible change |
|  | `com.android.window.flags.enable_input_dispatcher_long_method_tracing` | platform | 1 | diagnostics, logging or metrics only; no user-visible change |
|  | `perfetto.flags.use_unix_socket_inotify` | platform | 2 | diagnostics, logging or metrics only; no user-visible change |
|  | `com.android.launcher3.enable_compose_for_options_popup_menu_dialog` | visual | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.launcher3.enable_widgets_section_in_options_menu` | visual | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.systemui.enable_note_in_action_corner` | visual | 2 | needs a notes-role app; OpenBook ships none |
|  | `com.android.systemui.enable_note_qs_tile` | visual | 1 | needs a notes-role app; OpenBook ships none |
|  | `com.android.systemui.notification_animated_action_style_2026` | visual | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
|  | `com.android.systemui.notification_storage_alerts_channel` | visual | 1 | needs config_notificationAlertsChannel, which we do not set |
|  | `com.android.systemui.status_bar_is_connected_display_chip_controlled_by_config` | visual | 1 | no effect: config_isStatusBarConnectedDisplayChipEnabled is true by default |
|  | `com.android.window.flags.perfect_edge` | visual | 0 | no reader in AOSP 17: the code it gates is not public, so enabling it changes nothing |
