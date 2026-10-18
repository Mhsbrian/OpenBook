# ANAL-202 (B1): Google Sans on the G14, from the owner's `anal192d` session (2026-10-18)

**Source:** the build host's read-only copy of the stick, `~/anybook/installer/g14/stick-20261018T123221Z/`. The stick itself was not touched.
- **Image:** `openbook-live-20261018-anal192d` (`main` `81578c1` + #83). It contains B1 (#77) and B7 (#78).
- **Boots:**
  - **A:** the default "OpenBook" boot. Enforcing, 11:00–11:59Z. Its logcat was persisted to `live-001/prior/`.
  - **B:** "save logs" (`live-001/`). Permissive.
  - **C:** "ARM apps check" (`live-002/`). Permissive.
- **Display:** 2880×1800 at 240 dpi.

## Results

| Check | Result | File |
|---|---|---|
| Font loading | No warning or error from `SystemFonts`, `FontManagerService`, `FontListParser` or `FontCustomizationParser` in any of the three boots. Boot A loaded the font config and started the font service normally | `font-log-lines.txt` |
| SELinux | Boot A (enforcing): no denial names a font path or the font service. Boots B and C have one `find` on `font_service` each. That comes from the log collector listing every service (uid 0, `kernel` domain, permissive), not from font loading | `font-log-lines.txt` |
| Crash buffer | Boots B and C: empty. Boot A: **one crash, not font-related**: `com.android.wallpaper` (`WallpaperPreviewActivity` `requestFullscreen` callback, a Kotlin non-null parameter that was null) at 11:05:07. The owner had just opened a wallpaper preview from Wallpaper & style. No tombstones, no ANRs | `crash-buffer.txt` |
| Google Sans on screen | Boot C's own screenshot: the window caption ("OpenBook Installer") and the status bar ("12:14 Sun, Oct 18") are in Google Sans. They match a Google Sans reference render, not Roboto. No text is clipped in either | `caption-vs-references.png`, `status-bar.png`, `screen-live-002-half.png` |
| The installer's own text | Roboto, by design: its Compose theme uses the system `sans-serif` (`installer/app/.../ui/Theme.kt`: "Text styles from the design (Roboto …)"). B1's framework values reach the DeviceDefault text styles (37 uses in AOSP's `styles_device_defaults.xml`) and the apps that name the families (SystemUI, Launcher3, SettingsLib). An app with its own theme keeps its own font | `installer-heading-vs-references.png` |
| Settings, Quick Settings, notifications, all apps; clipped text there | **Not shown.** The only screenshots are boot B's desktop and boot C's installer, and the owner has posted no photos yet | — |

In the reference images, the first row is rendered with our `GoogleSans-VF.ttf` and the second with the image's `Roboto-Regular.ttf`. The third is the crop from the G14.

## Open

- The photo part of B1's G14 step (Settings, Quick Settings, notifications, all apps, clipped text at 240 dpi) waits for the owner's photos, or for the next stick.
- The wallpaper preview crash belongs to the wallpaper picker in desktop windowing, not to B1.
