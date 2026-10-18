# G14 `anal192d`: the default boot under enforcing, desktop and stability (ANAL-176, 2026-10-18)

The stick was `openbook-live-20261018-anal192d` (`main` `81578c1` + #83). The owner wrote it at 10:57Z and ran it from about 11:00 to 12:15Z. ANAL-192 read it at 12:32Z into the host copy `<data dir>/installer/g14/stick-20261018T123221Z/`, which is all I read; the stick was not touched.

The default "OpenBook" boot (11:00:33–11:59:04Z, enforcing) comes from the persisted logcat in `live-001/prior/` (17 files, the whole boot). The files here are extracts:
- `default-boot-timeline.txt`: curated lines, with Bluetooth addresses masked;
- `default-boot-counts.txt`;
- `default-boot-avc.md` and `.json`.

The full logcat stays on the host. Audio is ANAL-179's (`evidence/2026-10-18-g14-anal192d-audio-net/`); the refresh rate is ANAL-212's (`evidence/2026-10-18-refresh-rate/`).

| | Result |
|---|---|
| Desktop | 30.7 s (`sf_stop_bootanim: 30687`) on the freshly written stick. The stick was left alone (`Not managing disk 8:0`), the lock screen was dismissed at boot, there was no sleep, and the boot shut down cleanly after 58 min |
| Failed frames | 0 `Failed to pin framebuffer`, 0 `present failed`, 0 refused test commits after bring-up (12 during it); no GPU reset |
| Jank | 4,973 frames flagged as missed by SurfaceFlinger during UI animations (legacy `JANK_COMPOSER`). Newer classification: 4,769 `JANK_NONE`, 138 `JANK_COMPOSER`, 50 `JANK_APPLICATION`, 16 unknown. App frame time was ≤ 17 ms for 4,793 of them, 34–67 ms for 87, and over 67 ms for 7. The 60 fps cap (ANAL-212's baseline: 60 Hz for 99.7 % of screen-on time) is lifted by #88 |
| Launcher | One start (11:01:03), no death in 58 min. The taskbar overlay (All Apps, menus) closed 35 times. Esc presses are not in the log |
| Bluetooth audio | A2DP connected; 8 × `BTAudioSessionAidl … SUCCESS`; 0 Bluetooth denials, 0 tombstones (ANAL-179: streamed up to 26 min) |
| App audio | 0 `audioserver_tmpfs` denials for apps (PR #52's MLS rule); Chrome and WebView Shell played (ANAL-179) |
| Crashes | 0 native crashes, 0 tombstones, 0 ANRs. 1 Java crash: `com.android.wallpaper` `WallpaperPreviewActivity.requestFullscreen` NPE at 11:05:07, ANAL-205's (#91). Dropbox: 73 `system_app_strictmode`, 57 `system_server_strictmode`, 2 `SYSTEM_BOOT`, 1 `system_app_crash` |
| Denials | 229 lines, 9 kinds (`default-boot-avc.md`). Known: Gatekeeper, SystemUI's Bluetooth properties, `system_server` `wifi_hal_prop`, `isolated_app` `content_capture_service`. Being fixed: `mediaserver → audioserver_tmpfs` (#97). New: `openbook_installd → sysfs_batteryinfo` (`/sys/class/power_supply/*/type`, 26) and `→ openbook_vendor_fw_file` dir search (1), the installer daemon while the installer app was open (ANAL-191); `isolated_app → app_data_file setattr` on Chrome's `model-info.pb` (65), no visible effect (H) |
| Media decoding | 0 `Could not open DMA-BUF heap named: system` and 0 decoder failures (`anal176t`: 294 and 15), since ANAL-198's #64 |
