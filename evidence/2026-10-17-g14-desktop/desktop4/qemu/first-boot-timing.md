# First boot of a freshly written stick: desktop3 vs desktop4 (QEMU/OVMF)

Both runs used the same QEMU case, `live-qemu.sh IMG RUN logs`: a fresh 16 GiB copy of the image, the VM-only "console + save logs" entry, and the first boot, so `/data` is formatted. They ran back to back on an idle host (2026-10-17 ~03:15Z, after ANAL-179's build had finished). Values come from the helper's `dmesg.txt`, `collect-final.txt` (`ro.boottime.*`), `logcat-final.txt` (`boot_progress_*`) and `summary.json`.

| | desktop3 (compressed APEXes) | desktop4 (`PRODUCT_COMPRESSED_APEX := false`) |
|---|---|---|
| `apexd: Decompressing` lines | 28 | **0** |
| init: wait for `apexd.status=activated` | 14,737 ms | **43 ms** |
| SurfaceFlinger started | 19.9 s | **5.4 s** |
| zygote (`boot_progress_start`) | 20.3 s | 5.9 s |
| `boot_progress_enable_screen` | 24.9 s | 10.9 s |
| `sys.boot_completed` | 27.9 s | **17.8 s** |
| logs-case checks | 8/10 | 8/10 (the same two VM-only misses: no power-off after shutdown, no screencap on the VM display) |

The stages from zygote on take the same time in both (enable_screen − start: 4.6 s vs 5.0 s). The whole difference is the decompression before SurfaceFlinger.

On the G14 the stick is slower than the host's NVMe: the same decompression (20 APEXes) took 34 s and init waited 40.7 s, with SurfaceFlinger at 55.4 s (`../../g14-desktop3/`). **Expected on the G14 (H)**: SurfaceFlinger and the boot animation about 35–40 s earlier on a fresh stick. To be confirmed by the owner's first boot of desktop4.

An earlier full-matrix run (`SUMMARY.md` here, 37/39) ran while ANAL-179's AOSP build loaded the host (15-minute load average 42). Every boot stage was about twice as slow there (`boot_completed` 39.5 s), so its timings are not used.
