# Live image `openbook-live-20261017a` (ANAL-190, rebuilt on ANAL-199's G14 live-boot fixes, PR #38)

Built by `scripts/installer-image.sh --label openbook-live-20261017a --menu-timeout 10` at commit `2e3a56f`. The input is ANAL-199's `anybook_g14` output of 2026-10-16 19:59 EDT, with the PR #38 fixes:
- `debug.angle.feature_overrides_disabled=supportsSwapchainMaintenance1` (verified in the build's props), which keeps ANGLE off the deferred swapchain path that crashed RADV on the G14;
- SELinux labels for the denials seen on the laptop;
- the N-KEY keyboard LED.

Hashes are in `build/inputs-provenance.txt`.

| | |
|---|---|
| Image | 2,882,535,424 bytes, sha256 `8dfba134b8b7f03c731d296c8222c7270bdbf63600e85990d191ca56f1709358` |
| `.img.xz` | 904,514,052 bytes, sha256 `82673de048122731d631803e53eaeae71faf33257ea5a75c64eb3f6bef4e005c` |
| Build | 42 s; `openbook-live-init` host test 9/9 |

**QEMU/OVMF: 37 of 39 checks pass** (`qemu/SUMMARY.md`), the same as image `b`: `sys.boot_completed=1` at 23 s from the USB stick, and grow, persistence, start fresh, exact size, decoy NVMe and the default entry pass. The two failures are the known VM-side ones: the kernel power-off hangs after Android's clean shutdown (product), and `screencap` times out in the VM.

The RADV fix can only be checked on the G14, because QEMU has no AMD GPU.

**Correction (2026-10-17):** the "Android shut down by itself" failure was the machine autosuspending between the release of the helper's wake lock and its shutdown request, not a kernel power-off hang. The helper now keeps the lock through the shutdown request, and the VM powers off (`../live-helper/`).
