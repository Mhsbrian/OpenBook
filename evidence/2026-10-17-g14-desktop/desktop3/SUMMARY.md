# `openbook-live-20261017-desktop3`: the fixes from the G14 boots of desktop2 (ANAL-176, 2026-10-17)

Why each change was made: `../g14-desktop2/SUMMARY.md` and `docs/g14-desktop.md` §9. Owner steps: `docs/g14-desktop.md` §6. **Not run on the G14 yet.**

| | |
|---|---|
| Image | 2,882,535,424 bytes, sha256 `ac2c17a612d2d4c52ebccfe43a20d0a759c8bc985035bc3d13b218f8cca75acf`; `.img.xz` 904,528,744 bytes, sha256 `2cd6114fed56d12268e0632064651bb8eebb743a3d57e4472f4da675988f22ae`; repo `7847a32`, clean (`image/`) |
| Product build | `m` exit 0 in 9 min 15 s, under the AOSP lane lock (`build/`). Two earlier attempts failed and are kept: `host_init_verifier` rejected `.` in an init event name, and a stale `file_contexts` was left over from ANAL-179's build (fixed in `scripts/aosp-build.sh`) |
| Policy in the image | `sepolicy-analyze` on the compiled `precompiled_sepolicy` finds `allow kernel openbook_vendor_fw_file:system firmware_load` (the black enforcing boots), plus `vendor_init` reading `vendor.anybook.gpu.*` and the two `sysfs_gpu` traversals (`policy-check.txt`). 24 of 24 G14 sysfs paths are labelled as intended |
| QEMU/OVMF matrix | **37 of 39**, `boot_completed` at 20.3 s from the USB stick. The 2 misses are the known VM-only ones (no power-off after shutdown, `screencap` on the VM display) (`qemu/SUMMARY.md`) |
| HAL choice before SurfaceFlinger | The VM path runs the new early-init event at **3.74 s**, before `early-fs` and 8.6 s before SurfaceFlinger starts. desktop2's property trigger ran at 12.62 s, after SurfaceFlinger (12.29 s) (`qemu/hal-selection-timing.md`). The G14 path (`vendor-anybook-gpu-amdgpu`) uses the same mechanism |
| Logs of earlier boots | `logcatd` is running with `persist.logd.logpersistd=logcatd`. The save-logs helper's first capture wrote `prior-boots.tar.gz` (1.9 MB, rc 0): persisted logcat, tombstones, ANR traces, dropbox (`qemu/logs/`) |
| Denials, VM path | 9 kinds, all known and none from these changes (`qemu/logs/avc.md`) |

**Cannot be shown here (needs the G14):**
- that amdgpu, and so the display, comes up under enforcing;
- the 10-minute screen timeout (a fresh `/data` gets it).
