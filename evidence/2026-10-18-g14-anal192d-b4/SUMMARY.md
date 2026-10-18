# ANAL-205 (B4) on the G14: the owner's `anal192d` session (2026-10-18)

**What this covers:** B4's icon shape and wallpaper values on the laptop. Everything here comes from the logs; the owner's photos weren't posted yet.

**Source:** the build host's read-only copy of the stick, `~/anybook/installer/g14/stick-20261018T123221Z/`, read with `read-stick-logs.sh` at 12:32Z. Nothing from the stick is committed except the excerpts below.

**Image:** `openbook-live-20261018-anal192d`, built from `main` `81578c1` plus #83 (`docs/installer.md` §13.12). `81578c1` contains B4 (#73) unchanged. No later change sets the three framework values or the two properties anywhere else.

**Boots:** the session ran 11:00–12:15Z.
- The default "OpenBook" boot's persisted logs and dropbox are in `live-001/prior/`.
- `live-001` itself is "save logs".
- `live-002` is "ARM apps check".

## Results

| Check | Result | File |
|---|---|---|
| Wallpaper colour properties | `persist.wallpapercolors.threshold=55`, `max_dark_area=12` in both boots | `props.txt` |
| Icon shape | Every taskbar icon is a **circle** in both boots: the pins Files, Settings, WebView Browser Tester, Calendar and Gallery, plus running apps. AOSP's mask would draw rounded squares. Nobody picked a shape, so Launcher3 is drawing the framework mask | `g14-taskbar.png` (from each boot's `screen-final.png`) |
| Wallpaper on screen vs. its file | The desktop shows **Folio dark**, not the checklist's pale Folio light; probably the owner's pick in Wallpaper & style. Mapped through the wallpaper layer's transform (scale 1.1006, offset −145, −91), the screen matches `openbook-folio-dark.jpg` to 0.43 levels per channel, ratio 1.002: **not dimmed** | `wallpaper-check.txt`, `sf-wallpaper-layer.txt` |
| Does that prove the 0 dim? | **No.** Folio dark has a mean luminance of 0.09, which earns the dark-theme hint. WallpaperService never applies the default dim to such a wallpaper, under AOSP's values or B4's. All of B6's dark wallpapers have the hint, and Folio light gets the dark-text hint under both thresholds. So on the stock wallpapers the dim value can't be seen; only `cmd overlay lookup` shows it (measured in Cuttlefish, `evidence/2026-10-17-shape-wallpaper/`) | `wallpaper-check.txt` |
| Folio light, the default | Mean luminance 0.701 by our approximation of `WallpaperColors`: just above AOSP's 0.70 threshold for dark text, and clear of B4's 0.55. **HYPOTHESIS:** under AOSP's threshold the device's exact computation could drop it below 0.70. It would then get no hint, light launcher text and the 5 % dim. B4's values leave a wide margin | `wallpaper-check.txt` |
| Crashes from B4 | None: 0 `FATAL EXCEPTION` or `ANR` in the persisted logcat (11:21–12:01Z) and in both boots' final logcat. No icon-shape or mask errors; Launcher3's error-level lines are the usual boot-order ones (`Loader task completed`, `Failed to get launcher proxy`) | `crashes.txt` |
| Other crash: Wallpaper & style | **One crash**, 273 s into the default boot (11:05:07Z): `com.android.wallpaper` NPE in `WallpaperPreviewActivity$requestFullscreen$1.onResult`. Not caused by B4 (see below) | `wallpaper-picker-crash.txt` |

## The Wallpaper & style crash (AOSP bug, desktop windowing)

- **Where it happens:** `packages/apps/WallpaperPicker2/.../preview/ui/WallpaperPreviewActivity.kt:273-287`.
  - When the user opens a full wallpaper preview from a desktop window, the activity calls `requestFullscreenMode(FULLSCREEN_MODE_REQUEST_ENTER, …)`.
  - It passes a Kotlin `OutcomeReceiver<Void, Throwable>` whose `onResult(result: Void)` is non-null.
- **Why it crashes:** on success the framework calls `callback.onResult(null)` (`FullscreenRequestHandler.notifyFullscreenRequestResult`, `core/java/android/app/FullscreenRequestHandler.java:159`). Kotlin's parameter check throws.
- **What it means:** in a desktop window, every full preview whose fullscreen request succeeds crashes the app.
- **Fix:** one character, `override fun onResult(result: Void?)`. It isn't built or tested yet. Reported on ANAL-192 for routing.

## Not covered

- The All Apps panel, Settings and the Shape picker. The anal192d checklist asks for photos of them.
- `cmd overlay lookup` on the laptop. The live stick's collector doesn't record overlay values; a proposal for that is on ANAL-192.

## Reproduce

```bash
S=~/anybook/installer/g14/stick-20261018T123221Z
git show origin/main:assets/wallpapers/2880x1800/openbook-folio-dark.jpg > /tmp/folio-dark.jpg
scripts/ui/wallpaper-screen-check.py /tmp/folio-dark.jpg $S/live-001/screen-final.png --scale 1.1006 --offset=-145,-91 \
  --skip 0,0,2880,100 --skip 0,1690,2880,1800 --skip 0,0,1000,450
```
