# Live image `openbook-live-20261016b` (ANAL-190, rebuilt after ANAL-199 delivered, 2026-10-16)

Built by `scripts/installer-image.sh --label openbook-live-20261016b --menu-timeout 10` at commit `6100652` (clean). The input is ANAL-199's `anybook_g14` output of 19:34 (PR #35: audio policy configuration and the allocator memfd fix). Hashes are in `build/inputs-provenance.txt`.

| | |
|---|---|
| Image | 2,882,535,424 bytes, sha256 `cb5961b0f811f09dd42ea125be819d1d74da104d8f539d549abc78ba357ff35e` |
| `.img.xz` | 904,499,712 bytes, sha256 `7e911ae267870b61cb70a0f2ef80c58c2c408d6dcf41bd656d6e1578a9f86d99` |
| Build | 42 s; `openbook-live-init` host test 9/9; 137 firmware files, 0 without a licence |

## QEMU/OVMF (`qemu/SUMMARY.md`): 37 of 39 checks pass

- **Android now finishes booting from the live stick.**
  - `sys.boot_completed=1` at 23 s, `system_server` started once (no watchdog loop), Launcher3 (`QuickstepLauncher`) resumed, and the boot animation exited normally (`qemu/first/sections/state.txt`, `logcat.txt.gz`).
  - The save-logs entry saw `boot_completed` at 28 s.
- Grow, persistence, start fresh, exact size, the decoy NVMe, and the default entry pass as before.
- **FAIL: "Android shut down by itself".** Android's own shutdown is clean (`/data` and `/metadata` unmounted and synced, "Reboot ending, jumping to kernel"). Then the kernel's power-off never completes, and init's reboot monitor would force a reboot after 300 s. ANAL-199's own `g14-release` boots of the same product show the same thing, so it's the product or kernel, not the stick (the image `a` runs printed "reboot: Power down" at once).
- **FAIL: "screenshot is a PNG".** `screencap -p` timed out after 60 s in the VM with the framework up. The VM's display path is broken (virtio-vga "Display output is not active", parked by ANAL-199). On the G14, the same capture returned at once (`../g14-live/`).
