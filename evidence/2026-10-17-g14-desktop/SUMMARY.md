# G14 desktop from USB: evidence (ANAL-176, 2026-10-17)

Details and reasoning: `docs/g14-desktop.md`. Nothing here ran on the G14; the owner checklist is in that doc, §6.

| Directory | What | Result |
|---|---|---|
| `radv-crash/symbolize.txt` | live-001's tombstone frame #00 symbolized with the unstripped Mesa 26.2.5 build of the same BuildId; libvulkan's caller | `radv_BindImageMemory2`, `mem->alloc_size` with `mem` = NULL (fault addr 0x60): the deferred swapchain bind |
| `hwtest/before/` | `amd-android-hwtest.sh … swapchain` with the image's RADV (26.2.5), build host Radeon 610M | create path 4/4 pass; **deferred path 4/4 `SIGSEGV`, fault addr 0x60** (the G14's crash) |
| `hwtest/after/` | all parts with the patched Mesa (`MESA_OUT`, RADV BuildId `69152ccf…`) | vulkan, gles, gralloc pass; swapchain 8/8 pass, 0 wrong pixels RADV → radeonsi and radeonsi → RADV, at 2880×1800, 1920×1200, 1000×600, 64×64 |
| `mesa/` | `versions.txt` (pin + 4 patches, patched HEAD `f30f204df44c`), `sha256sums.txt` | |
| `aosp-build/` | the product build with the patched Mesa and SELinux (`m` exit 0), the earlier `sepolicy_test` failure it fixed, `product-check.txt` | `vulkan.radv.so` BuildId `69152ccf…` in the product |
| `selinux/live-001-avc.*` | `avc-summary.py` on the first G14 live boot | **66** Android denial lines in the kernel log; 22 distinct outside `flags_health_check` |
| `selinux/label-check.*` | `sepolicy-label-check.py` with the G14's sysfs paths against the built policy | **24 of 24** as intended |
| `image/` | `openbook-live-20261017-desktop2` build record, layout and entries | 2,882,535,424 bytes, sha256 `1e6c7315c165f6cf…`; `.img.xz` 904,524,444 bytes, sha256 `1e21d55142e9dddc…`; repo `21ec644`, clean |
| `qemu/` | live-qemu.sh, 6 cases, QEMU/OVMF from USB | **37 of 39**: `boot_completed` at 20.3 s; the 2 misses are VM-only (no power-off after shutdown, `screencap` on the VM display) |
| `qemu/logs/avc*.md` | denials on the VM path, this build vs. the first build of the branch | 41 lines / 8 distinct (was 69 / 16); no `vendor_default_prop` left |

## Not shown here (needs the G14)
- RADV and the metadata layout on gfx1150 (RDNA 3.5): the build host is RDNA2.
- The safe-graphics entries (QEMU has no AMD GPU).
- The SELinux labels on the laptop's live sysfs (checked against the built policy only).

## Incident during this run
At 00:29:42 UTC this run reused the label `openbook-live-20261017a`, already built at 00:16 UTC by another run (sha256 `8dfba134…`) and being written to the owner's stick at that moment. The stick is unaffected: `dd` had the original file open, the image builder replaces its output by rename, and the stick's read-back matched `8dfba134…` (`write-stick-20261017T002919Z.log`). This run's files under that label were removed and replaced by a note (`<data dir>/installer/out/openbook-live-20261017a.NOTE.txt`); its builds use their own labels since.
