# Live USB image: build and QEMU/OVMF evidence (ANAL-190, 2026-10-16)

Design and details: `docs/installer.md` §11. **Nothing here ran on the G14.** That needs the owner's stick confirmation (§11.6).

## Image `openbook-live-20261016a`

| | |
|---|---|
| Built by | `scripts/installer-image.sh --label openbook-live-20261016a --menu-timeout 10` at repo commit `6ce38d0` (clean), epoch 1792181279 |
| Inputs | ANAL-199's `anybook_g14_x86_64-cp2a-userdebug` `PRODUCT_OUT`, snapshotted 2026-10-16 22:14:52 UTC (its iter6 build); kernel `6.18.21-android17-5-g44a90255c95f`. Hashes: `build/inputs-provenance.txt` |
| Image | 2,882,535,424 bytes, sha256 `b50b6dfc60fc29dfd30b7e8c301822e848a518f671a233816176f5106f2db07c` |
| `.img.xz` | 904,520,596 bytes, sha256 `7f18d9b2298fc46cdbb3722aba1a7958697099ca011a772aca4ca6a0e0c0f213` |
| Build time | 41 s (`build/openbook-live-20261016a.build.json`) |
| Reproducible | four builds of this label from the same snapshot (with and without a clean commit) gave the same `.img` and `.img.xz` hashes |
| Licences | 137 firmware files in `/vendor/firmware`, 0 without a licence file; 5 licence files copied to `LICENSES/firmware/` on the stick (`build/openbook-live-20261016a.img.json`) |
| `super` | the product's 8 GiB `super` re-packed to 1.23 GiB; all 7 non-empty logical partitions byte-identical to the originals |

`build/live-init-test.txt`: `openbook-live-init` host test, 9/9 (grow, second run, repair, exact size, wrong ESP, userdata not last, short stick, bad CRC, reset).
`build/write-stick-dry-run.txt`: the dry run against the owner's attached stick (serial redacted). The image hash was checked, the stick identified, and nothing written.

## QEMU/OVMF matrix (`qemu/SUMMARY.md`, `qemu/results.json`): 38 of 39 checks pass

- **first** (16 GiB stick + decoy NVMe): grow 1 → 14.3 GiB; GPT valid; `/metadata` and `/data` formatted on the stick; by-name links only on the stick; decoy unchanged; marker written. **FAIL:** `sys.boot_completed` not set after 600 s. That is the product (below).
- **second:** nothing to grow; the marker persisted.
- **reset:** metadata and userdata zeroed and formatted again; the marker gone.
- **exact:** nothing to grow; `/data` at 1 GiB.
- **logs:** `qemu/logs/live-001/` is what the stick saved (redacted): dmesg, logcat, system facts, `screen-*.png`, `summary.json`, `report.md`. Android then powered off by itself.
- **default:** the image's own menu (`qemu/default/shot-4.png`) and default entry; the grow happened.

Screens: `qemu/default/shot-4.png` (boot menu); `qemu/logs/live-001/screen-final.png` (the boot animation, from SurfaceFlinger). `qemu/first/shot-after-boot.png` and `qemu/default/shot-15…360.png` show QEMU's virtio-vga reporting "Display output is not active".

## Why no desktop (product, ANAL-199; passed on there)

- `system_server` is killed by its watchdog in a loop in `AudioService` → `AudioSystem.setLowRamDevice`. `audioserver` waits for `android.hardware.audio.core.IModule/default`, which the example audio HAL never registers: `AHAL_Config: getEngineConfig: No audio configuration files found`, and `/vendor/etc` has no `audio_policy_configuration.xml`.
- In the VM, SurfaceFlinger needs `execmem` for SwiftShader under enforcing SELinux (ANAL-199 is on it), and the virtio-vga scanout stays inactive. Both are VM-only.
- No Wi-Fi HAL or `wpa_supplicant`, and no `regulatory.db`, in the product yet.
