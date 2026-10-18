# ANAL-203: background blur on the G14, from the owner's `anal192d` session (2026-10-18)

**Source:** the build host's read-only copy of the stick's logs, `~/anybook/installer/g14/stick-20261018T123221Z/` (read by `read-stick-logs.sh` at 12:32Z). The stick itself wasn't touched.
- Stick image: `openbook-live-20261018-anal192d`, from `main` `81578c1` (which includes #72) plus #83.
- Session: about 11:00–12:15Z.
- Boots read:
  - the default "OpenBook" boot, 11:00:41–11:59:40Z, from the persisted logcat and dropbox in `live-001/prior/`;
  - the "save logs" boot (`live-001/`);
  - the ARM apps check (`live-002/`).
- **The graphics check, and with it the `blur` part's frame stats, didn't run this session.**

Only blur-related lines are copied here: no network names or addresses.

## Results

| Check | Result | File |
|---|---|---|
| Property in force | `ro.surface_flinger.supports_background_blur=1`; RenderEngine `ro.hwui.use_vulkan` and `debug.renderengine.*` unset; panel 2880×1800 at 120 Hz | `props.txt` |
| SurfaceFlinger's renderer | `Threaded RenderEngine with SkiaGL Backend (Ganesh)` and `Background Blurs Enabled (Kawase dual-filtering V2 algorithm)` at 11:00:48–49Z. No "Disabling blur effects" line. This is the G14 confirmation of `docs/graphics-amd.md`'s table, which had it from a crash backtrace | `blur-log-lines.txt` |
| **Blur drawn behind the shade** | SystemUI's `BlurUtils` reports `lastAppliedBlur 51` (px). That is Cuttlefish's 34 px at 160 dpi, scaled to the G14's 240 dpi. SystemUI's blur animations (`BlurChoreographer`) ran in the same minutes as the shade openings: 11:01, 11:02, 11:15–11:17, 11:27, 11:37 and 11:59. Launcher3's own depth blur stayed 0 | `blur-log-lines.txt`, `shade-events.txt` |
| Shade use | 9 `notification_panel_revealed` and 9 `notification_panel_hidden` events. SystemUI's LatencyTracker logged `ACTION_EXPAND_PANEL` (action 0) 9 times, at 0–1 ms | `shade-events.txt` |
| **No GPU hang** | 0 amdgpu ring time-out, reset, page-fault, wedged or VRAM-lost lines in the default boot (its kernel log is in the persisted logcat), in the save-logs boot and in the ARM apps check. SurfaceFlinger started once. SystemUI (pid 3492) and Launcher3 (pid 3803) started once, at 11:01:03Z, and kept those PIDs to the end | `stability.txt` |
| Big hitches | SystemUI logged no Choreographer "Skipped frames" (≥ 30 frames) and no HWUI "Davey" (≥ 700 ms). That rules out only large stalls: it is not the `frame_cost` check | `stability.txt` |
| Crashes | One app crash, unrelated to blur: the Wallpaper picker (`com.android.wallpaper`, `WallpaperPreviewActivity` NullPointerException in its fullscreen request, 11:05:07Z). No tombstone, ANR or native crash. The dropbox otherwise holds 130 strict-mode entries | `stability.txt` |
| **Frame cost** (`dumpsys gfxinfo`, TimeStats) | **Not measured:** the graphics check wasn't booted | — |
| Owner's eye | No photos posted yet | — |

**What blur looked like on this stick:**
- With B3's `blur_on_more_surfaces` on and `config_supportBlurredWallpaper` still at AOSP's default `true`, the shade and Quick Settings blur the whole 2880×1800 desktop. That is the heaviest case (`docs/googlebook-ui.md` §2.3).
- It ran for an hour with no GPU fault, no UI restart and no large hitch.

## Against the G14 checklist (`docs/googlebook-ui.md` §2.3)

| Verdict | From this session |
|---|---|
| `blur_applied` | **Pass from the logs** (SystemUI applied radius 51 during the shade animations). Not yet confirmed by the `blur` part's layer dump or screenshots, or by the owner's eye |
| `no_gpu_hang` | **Pass for this session** (about 60 min of normal use, plus two more boots) |
| `frame_cost` | **Not measured** |

Next: the graphics check boot on `anal192e`, whose `blur` part runs first (about 7 minutes).
