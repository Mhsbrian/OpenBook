# ANAL-204: desktop flag set v2, the Googlebook flags AOSP 17 declares (2026-10-17/18)

The write-up is `docs/googlebook-flags.md`. The triage table is `device/anybook/common/desktop/release/googlebook-triage.tsv`.

**Images:** `anybook_cf_x86_64_pc-cp2a-userdebug` (`CP2A.260605.016`), Cuttlefish on the host's Radeon 610M (`gfxstream_guest_angle`), 1920×1080 at 160 dpi. Each image got `flag-checks.py --reset`, then `desktop-capture.sh`, then `flag-checks.py`.

| Image | Value set | Build | Boot to `sys.boot_completed` |
|---|---|---|---|
| `baseline/` | ANAL-169's 79 flags (`c861cf4`) | 29 min | 26 s |
| `v2-all-groups/` | + groups 1–6, 87 flags (`38cf5ba`) | 31 min | 23 s |
| `v3/` | v2 without `enable_add_window_decoration_to_all_tasks` and `use_android_ui_dispatcher`, 85 (`8ed9f5f`) | 30 min | 30 s |
| **`v4/`** (committed) | v3 without `start_on_gone_scene_if_no_lockscreen`, 84 (`d5d5acf`) | 29 min | 26 s |

## Results

| Check | baseline | v2 (87) | v3 (85) | v4 (84) |
|---|---|---|---|---|
| Triage flags enabled in `aflags list` | 0 (compiled out) | 87/87 | 85/85 | 84/84 |
| Window layers with `BoxShadowSettings` | none (legacy elevation shadow) | two 24 px shadows + 1 px border | same | same |
| Move, resize, maximize, restore (mouse, Meta+=, caption button) | pass | pass | pass | pass |
| Minimize, then restore from the taskbar | pass | **SystemUI crash** | pass | pass |
| New windows | Files at the right edge, Clock top-left | 60 px steps | 60 px steps | 60 px steps |
| Maximize-button hover menu | Maximize, Resize | + fullscreen/split/desktop row | same | same |
| Pointer while resizing below the minimum | 1017 | 1017 | 1017 | 1017 (no effect from `enable_no_resize_cursor`) |
| QS tile hover | no tooltip | "Wi-Fi" tooltip | same | same |
| Cast tile on Ethernet | disabled ("No Wi-Fi or Ethernet") | available | available | available |
| Notification shade with notifications | rows shown | **empty** (rows `0,0-0,0`) | **empty**; rows shown once a PIN is set | rows shown |
| Power menu from the QS power button | not measured (the baseline run used a long press, which opens nothing on Cuttlefish) | dim layer blurred (34) | dim layer blurred (34) | dim layer blurred (34) |
| Crash buffer / ANRs | empty / 0 | 1 SystemUI crash / 0 | empty / 0 | empty / 0 |
| SELinux denial kinds | 4 | 4 | 4 | 3 (same kinds) |

The two failures, traced:
- **The crash:** `enable_add_window_decoration_to_all_tasks` makes `DefaultWindowDecoration.relayout` call `updateDragResizeListenerIfNeeded` for a task that has no decoration container surface.
- **The empty shade:** `start_on_gone_scene_if_no_lockscreen`. OpenBook disables the lock screen by default, so SystemUI starts on Gone, and the keyguard section that binds the notification stack never runs. On the same v3 image with a PIN set, the stack reports `mExpansionFraction=1.0` and `mStackHeight=380` instead of `0.0` and `0.0` (`v3/shade-root-cause.txt`).

## Files

- `baseline/`, `v4/`: from `scripts/desktop-capture.sh` and `scripts/ui/flag-checks.py`:
  - `results.tsv` (every check) and `checks.log`;
  - `flag-state.tsv` (each enabled flag and its state) and `aflags.txt.gz`;
  - `windowing-summary.txt` and `surfaceflinger-summary.txt`;
  - the crash, ANR and SELinux files;
  - `build-boot.txt`;
  - `v4/sf-shadows.txt`.
- `v2-all-groups/`:
  - the three check runs: `results-run1.tsv` (with the crash), `results-run2-no-minimize.tsv` and `results-run3-shade-blur.tsv`;
  - `systemui-crash.txt`, `shade-rows-not-laid-out.txt` and `sf-shadows.txt`;
  - `cmp-shade-baseline-vs-v2.png`.
- `v3/`:
  - `results.tsv`, and `results-with-pin.tsv` (after `locksettings set-pin`);
  - `shade-root-cause.txt` and `notification-hover-with-pin.png`;
  - the crash and denial files.
- `cmp-*.png`: baseline | v4, at half size, or cropped at full size: `windows`, `cascade`, `app-chip-menu`, `maximize-menu`, `quick-settings`, `qs-tooltip`, `shade`, `notification-right-click`, `taskbar-menu`, `resize-below-minimum`.
- `v4-power-menu.png`: v4 only.

## Commands

`docs/googlebook-flags.md` § Reproduce.
