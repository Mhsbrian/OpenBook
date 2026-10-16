# ANAL-199 evidence: the OpenBook G14 product boots in QEMU/OVMF as a PC

Date: 2026-10-16. Details and design: `docs/g14-product.md`. Nothing here ran on the GA403WR.

| Check | Result | Where |
|---|---|---|
| Product build `anybook_g14_x86_64-cp2a-userdebug` | exit 0; first build 30:41 + 8:38 resume, peak RSS 45 GB; last incremental 0:29 | `build/` |
| Kernel staging | ANAL-198 dist `anybook-g14-gbos-16302624`, release `6.18.21-android17-5-g44a90255c95f`, 142 firmware files, sha256 checked against `images.json` | `build/kernel-staging-PROVENANCE.txt` |
| HAL host test | 15/15 pass | `tests/openbook_hals_test.txt` |
| Key layout / IDC | `validatekeymaps`: Success | `tests/validatekeymaps.txt` |
| dGPU hook fixtures | 14/14 on the host, 14/14 inside QEMU (mksh + toybox) | `tests/openbook-pc-setup-test-*.txt` |
| Disk image | `openbook-g14-CP2A.260605.016-20261016.img`: 12,884,901,888 bytes, sha256 `995c66f61c8898600de4ae279a25f6331bc045b8d1e775027c1ea96ec34f2498`; `.img.xz` 945,533,316 bytes, sha256 `04d8fe7d6922566bcff2bb2d0960378fbbbe55b7c715f37ecb41d63dea88fe06` (not committed) | `image/` |
| QEMU boot 1 (USB stick, OVMF, virtio-vga, swtpm) | first stage 3.6 s, second stage 5.2 s, `/data` 6.8 s, **`sys.boot_completed=1` at 29.9 s**; Launcher3 resumed; 58/58 steps | `qemu/boot1/` |
| QEMU boot 2 (same disk) | **`boot_completed` at 11.7 s**, no reformat, PIN from boot 1 verified, Weaver slots kept; 26/26 steps | `qemu/boot2/` |
| SELinux | enforcing; 16 denials left, none blocking | `qemu/boot1/sections/avc.txt` |
| Earlier QEMU runs | one excerpt per blocker found and fixed | `qemu/iterations/` |

`qemu/<boot>/sections/` holds what the console printed: props, `/proc/bootconfig`, by-name links, mounts, loaded modules, the GPU probe, registered HAL services, SurfaceFlinger, input devices, features, thermal/lights/battery dumps, the dGPU check, the lock-screen test, `logcat.txt.gz` and `dmesg.txt.gz`. The screenshots show the last boot-animation frame: the VM's software display path does not refresh after the boot animation (VM-only; parked).
