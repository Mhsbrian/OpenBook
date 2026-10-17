# G14 boots of `openbook-live-20261017-desktop3` (ANAL-176, 2026-10-17)

The owner wrote the `desktop3` image (sha256 `ac2c17a6…`) and booted the G14 twice. The stick was read back read-only at 02:36Z with `read-stick-logs.sh`, and the files here are redacted (`live-report.py --redact`). Earlier boots' archives (`prior-boots.tar.gz`, `prior/`) are not copied whole: `live-001/prior/` holds the launcher crash, the tombstone headers and a file listing.

## Timeline (UTC)

Sources: FAT times on the stick's ESP (2 s resolution), kernel uptimes, and logcat.

| Time | What | Evidence |
|---|---|---|
| 02:28:17 | **Boot 1**, not a save-logs entry (`logs=0`; the menu's default is "OpenBook"). The live helper grew `userdata` to 56.2 GiB at 2.5 s | `live-init-001.json` (written 02:28:20) |
| before 02:29:16 | Boot 1 is switched off, at most 59 s after it started, POST and the 10 s menu included. It formatted `/data` and wrote to it (boot 2's f2fs roll-forward recovery shows an unclean end), but it did not leave decompressed APEXes, so it was still in first-boot setup. SurfaceFlinger could not have started yet (55.4 s in boot 2), so its screen was black. It saved no logs | `dmesg.txt`: `f2fs_recover_fsync_data`, 20 × `apexd: Decompressing` in boot 2 |
| 02:29:16 | **Boot 2**, "save logs" (permissive). APEX decompression 16.9 to 50.3 s; init waits 40.7 s for `apexd.status=activated`; composer and SurfaceFlinger 55.4 s; boot animation 59.4 s; `boot_completed` **78.6 s** | `dmesg.txt`, `collect-final.txt` (`ro.boottime.*`), `summary.json` |
| 02:30:30 to 02:31:10 | The Bluetooth app aborts 6 times (`HidlHci: assert failed: hci_ != nullptr`: there is no Bluetooth HAL) | `prior/tombstones-headers.txt` |
| 02:31:04, 02:31:13 | Gallery opened; then the wallpaper chooser | logcat `START u0` |
| 02:31:18.8 | **Escape key → Launcher3 dies** (`NullPointerException` in `TaskbarOverlayDragLayer.tryHandleEscapeKey`); restarted 25 ms later | `prior/dropbox-launcher3-crash.txt` |
| 02:31:20 | The helper's capture (124 s): the desktop with Quick Settings open, Wi-Fi tile unavailable, taskbar not yet back | `screen-final.png` |
| about 02:31:26 | **The helper powers the laptop off** (130 s, `"after": "poweroff"`): the save-logs entry's design in this image | `summary.json`, the end of `dmesg.txt` |

## What the logs show

| | Result |
|---|---|
| The firmware fix (black enforcing boots) | **No `firmware_load` denial any more** on the G14 (desktop2 had one per boot); amdgpu initialised at 5.6 s. This boot was permissive, so it shows the rule is in the policy and matches. It does not yet show an enforcing boot reaching the desktop: boot 1 was switched off before it could |
| Denials | **14** lines in the kernel log that an enforcing boot would hit (66 for desktop1, 29 and 22 for desktop2), 7 distinct, none of them graphics: the audio HAL's memfd, Gatekeeper, `crash_dump` on the resource cache, init's bootreceiver tracing, SystemUI's `bluetooth_lea_prop` (`live-001/avc.md`) |
| GPU HALs | amdgpu, ANGLE on RADV, minigbm, drm_hwcomposer; SurfaceFlinger started once, no restart |
| Display | 1,775 kernel errors `dc_state_add_plane: can not attach plane_state! Maximum is: 4`, up to 60 per second, one per drm_hwcomposer test commit (1,539 `Test-only … ret=-22`). drm_hwcomposer asks for more planes on the panel's stream than amdgpu's display core allows (`MAX_SURFACES 4`, `dc.h`), the test fails, and SurfaceFlinger composes on the GPU instead. Nothing is lost on screen, but it costs GPU time and floods the kernel log. One real commit failed (`Failed to pin framebuffer with error -22` at 73.2 s, 14 ms after `sf_stop_bootanim`: the first frame of the hand-over to the desktop) |
| Wi-Fi | MT7925 firmware loads, but there is no `wifi` service (no Wi-Fi HAL or feature): ANAL-179 |
| Power | panel backlight, battery, the dGPU in D3cold, amd-pstate-epp: as expected |

## Changes made from this

- `PRODUCT_COMPRESSED_APEX := false` (as on Cuttlefish), so a fresh `/data` no longer spends 34 s decompressing 20 APEXes on the stick before SurfaceFlinger can start.
- Launcher3 patch: Escape only resets the All Apps search when there is an All Apps view (`aosp/patches/packages/apps/Launcher3`).
- `live-report.py --redact` skips `prior/` and `prior-boots.tar.gz` instead of failing on them.

Not changed here: the save-logs power-off (ANAL-190's branch `anal-190/live-image-b` makes that entry keep running), Bluetooth and Wi-Fi (ANAL-179), and drm_hwcomposer's plane count (open, §7 of `docs/g14-desktop.md`).
