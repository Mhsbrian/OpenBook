# ANAL-204 (B3) on the G14: the owner's `anal192d` session (2026-10-18)

This is the first G14 session with the B3 flag set (PR #79). The stick image is `openbook-live-20261018-anal192d` (`main` `81578c1` + #83). Everything here was read from the host copy `~/anybook/installer/g14/stick-20261018T123221Z/` and from the image's own `super.img` on the build host. The stick itself was not touched.

The owner booted it three times:
- the default boot, 11:00–11:59Z, whose persisted logcat is in `live-001/prior/`;
- "save logs" (`live-001/`);
- "ARM apps check" (`live-002/`).

## Results

| Check | Result |
|---|---|
| The flag set in the image (C) | **84 of 84 enabled; both dropped flags are absent (compiled out).** Read offline from the image's `system`, `system_ext` and `product` aconfig storage (`scripts/aconfig-storage-dump.py`). B5's `screenshot_remove_nonforced_sound` is also enabled, as intended. See `stick-flag-state.tsv` |
| Crashes (C) | **One app crash, not B3's:** `com.android.wallpaper` at 11:05:07Z, a `NullPointerException` in `WallpaperPreviewActivity`'s `requestFullscreen` callback. It is an AOSP WallpaperPicker2 bug gated by cp2a's own `fullscreen_preview_flag` and `fullscreen_preview_flow_fix`, which are on in the pre-B3 baseline too (`evidence/2026-10-17-desktop-flags-v2/baseline/aflags.txt.gz`). B1 and B4 reported it on ANAL-192, and B4 proposed the fix (`onResult(result: Void?)`). No native crash in any boot |
| ANRs (C) | 0 in all three boots |
| SystemUI (C) | Started once per boot and never died. The crash signature B3 dropped in Cuttlefish (`Expected non-null decoration container surface`) appears 0 times |
| Error kinds that existed before B3 (C) | Close-animation CUJ timeouts (one per window close), `TransitionChain` mismatches and SystemUI's `No package ID 7f` lookups. They occur at similar rates in the three G14 sessions from 2026-10-17, which had no B3 (`health.txt`) |
| What the session exercised | 5 maximize/restore toggles, 24 window closes, 9 openings of the notification panel (3–4 notifications listed each time), and the power menu |
| What it did not exercise | One window was minimized with its caption button (11:21:45Z) and **never restored**: the restore from the taskbar, the path that crashed SystemUI on B3's v2 image, was not tried. Calendar was not opened, so the cascade step was not checked. No B3 photos have been posted yet |
| Stepped cascading | No `stepped-cascade=` decision was logged. 16 of the 21 launches carried no position from WM Shell and opened at the centred default; the other 5 kept WM Shell's position. So the session neither shows nor rules out stepping; the checklist's Calendar step will |

**Not B3's, but seen:** `TransitionChain` errors in system_server, for example at 11:32:52Z, when a browser window left the desk for fullscreen. They match the earlier sessions' rate.

## Files

- `stick-flag-state.tsv`: the 84 enabled and 2 dropped flags of the triage, with their state in the image.
- `health.txt`: per-boot counts (fatal exceptions, `am_crash`, ANR, native crashes, SystemUI starts and deaths, minimize, maximize toggles, closes), the crash line, B3's dropped-flag signature, and the comparison with the three earlier sessions.

## How

```bash
# Logs: join the persisted logcat (oldest file first) and cut it at the reboot
cd ~/anybook/installer/g14/stick-20261018T123221Z/live-001/prior/misc/logd
cat logcat.16 logcat.15 ... logcat.01 logcat > default.txt      # then up to "ShutdownThread: Logging pre-reboot"
# Flags: unsparse super.img, take system/system_ext/product, dump the aconfig storage
docker run --rm -v ~/anybook:/a:ro -v $PWD:/w anybook-inspect sh -c \
  'simg2img /a/installer/inputs/openbook-live-20261018-anal192d/super.img /w/super.raw &&
   for p in system_a system_ext_a product_a; do lpunpack -p $p /w/super.raw /w/super; fsck.erofs --extract=/w/fs/$p /w/super/$p.img; done'
scripts/aconfig-storage-dump.py fs/system_a/system/etc/aconfig fs/system_ext_a/etc/aconfig fs/product_a/etc/aconfig
```
