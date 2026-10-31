# OpenBook 0.1.0-preview.1: the public build, its source and its release folder (ANAL-320, 2026-10-31)

> **Superseded the same day.** The owner wants NVIDIA's work in the public image, so `0.1.0-preview.1` is now built
> with NVIDIA's driver and firmware ([`../SUMMARY.md`](../SUMMARY.md)). This build, without the firmware, is kept as the record of
> `G14_NVIDIA_FIRMWARE=none`, of the live-stick fix and of the first source bundle.

The first image built to be published: the G14 product without NVIDIA's GSP firmware, a fix that makes the live
USB stick boot at all, the GPL/LGPL source bundle, and the release folder with its gates. **Nothing is published.**
The folder is unsigned and not owner-approved, so `release.json` says `"public": false`.

## The image

`openbook-live-20261031-anal320pub.img`: 3,106,930,688 bytes, sha256 `a150c202…02b3`. Product
`anybook_g14_x86_64-cp2a-userdebug` (fingerprint `…:userdebug/test-keys`), kernel `6.18.21-android17-5-g2461ae8277e6`
(the 2026-10-26 `anal297` dist, the same kernel the G14 has run since then), staged with `G14_NVIDIA_FIRMWARE=none`
(`image/kernel-staging-provenance.txt`). Built from this branch at `be4ac675` plus the then-uncommitted changes in
this commit (`build.json` says `dirty: true`).

| Check | Result | File |
|---|---|---|
| No NVIDIA firmware in `/vendor/firmware` | the folder has no `nvidia` directory; `LICENSES` has no NVIDIA licence (`dump.erofs` on `vendor.img`, sha256 `58d414ca…`, the same as `vendor_a` inside the live image) | `image/vendor-firmware-ls.txt`, `image/vendor-firmware-licenses-ls.txt` |
| NVIDIA's modules still ship | `nvidia.ko`, `nvidia-modeset.ko`, `nvidia-drm.ko` in `vendor_dlkm` (Dual MIT/GPL; their source is in the kernel tarball), blocklisted and never loaded without firmware | `image/kernel-staging-provenance.txt` |
| Standard G14 QEMU check (installed disk) | **58/58**, boot completed; the image's own `openbook-pc-setup-test` 0 failures, including the four no-firmware cases; 0 SELinux denials | `qemu-g14/` |
| Live USB stick in QEMU, before the fix | **fails**: Android restarts at the end of every boot, `reboot: Restarting system with command 'Checkpoint commit failed'` | `qemu-live-before-fix/` |
| Live USB stick in QEMU, after the fix | **32/32**: first boot (grows to 16 GiB, boot completed at 11.6 s), second boot (data kept), start fresh, save logs | `qemu-live/` |
| `make-release.sh` firmware check | public build: no match; 2026-10-30 NVIDIA image: matches (see `docs/RELEASE.md` §2) | |

### The live stick's boot loop (found and fixed here)

Android commits vold's checkpoint when a boot completes, through the boot control HAL's `markBootSuccessful`
(`ActivityManagerService`: "About to commit checkpoint", and a failure reboots with "Checkpoint commit failed").
OpenBook's HAL first runs `openbook-bootsync mark-good`, which looks for the running slot's loader entry,
`openbook-a.conf`. A live stick has no such entry. Its entries are the stick's own (`openbook-live.conf` and the
rest, from `mklive.py`), so mark-good failed with `no_current_entry` on every boot of every live image since the
HAL arrived (ANAL-223). Updates reached the G14 over Wi-Fi in the meantime, so no stick was built in that time. The
fix: on a live boot (`ro.boot.openbook.live=1`), `markBootSuccessful` marks misc only and leaves the stick's ESP
alone. After it, logcat shows `cp_commitChanges called` followed by `live USB stick: boot marked successful in misc`
(`qemu-live/logcat-excerpt.txt`).

## The RTX without firmware

Not measured on this build. QEMU has no NVIDIA GPU, and the G14 didn't answer adb on 2026-10-31 (it runs the
Googlebook image). The design is the one measured on the G14 on 2026-10-16, with an older build: no driver bound,
`dgpu-pm` lets the root port power the slot off, and both functions read `D3cold`/`suspended`
(`evidence/2026-10-16-installer/g14-live/SUMMARY.md`). To measure it on this build, boot this image's "save logs"
entry on the G14. `read-stick-logs.sh` then reports the `dgpu_off` verdict.

## The source

`sources/SOURCES.md` lists what is in each tarball and why. Totals: kernel 168,653,008 bytes, userspace 108,585,296,
systemd-boot 19,049,404.

- **Kernel:** the Kleaf workspace that built the shipped kernel (`kernel/nvidia-open-anal297/ws`, common at
  `2461ae8277e6`, clean): Google's `3938c8d97142` plus 5 OpenBook commits, Kleaf `5877a401` plus 1 OpenBook commit
  (the GKI symbol-list exception), `devices/anybook` (OpenBook's modules, nouveau, NVIDIA's open modules), the
  pinned manifest, and the patch series.
- **Userspace:** 14 AOSP projects whose binaries carry a GPL or LGPL text, found by
  `scripts/release/notice-scan.py` in the image's own NOTICE files: angle, bpftool, dnsmasq, e2fsprogs, exfatprogs,
  f2fs-tools, fec, gptfdisk, hyphenation-patterns, iproute2, iptables, libcap, libexif, libnl. Also Mesa's libelf
  (elfutils `219c3a3`, LGPL-3.0+) and Mesa 26.2.5 with OpenBook's 4 patches, as built. The Kotlin apps and Dialer
  carry licence collections whose GPL/LGPL entries are not in the binaries. They are listed with the reason and need
  no source here (checked by hand; the reasons are in `notice-scan.py`).
- **systemd-boot 262-1:** upstream's v262 source and Arch's packaging at `262-1`, downloaded 2026-10-31.

## The release folder

`<data dir>/release/out/0.1.0-preview.1/` (not in the repository; 945 MB):

| | |
|---|---|
| Image | `openbook-0.1.0-preview.1-x86_64-live.img.xz`, 944,840,824 bytes, xz -9 in 15 blocks |
| Torrent | hybrid v1 + v2, 902 pieces of 1 MiB, info hash v1 `a3f1c69c71050d70136bc284b450f7c06c7f4204`, web seed `https://github.com/Mhsbrian/OpenBook/releases/download/v0.1.0-preview.1/…` |
| Gates | pass: `no_nvidia_firmware`, `firmware_licences`, `source_offer`. Blocking: `release_keys`, `user_build`, `checksums_signed`, `owner_approved`. Nothing waived |
| Download test | `swarm-test.sh` 9/9: the whole image from the web seed alone (through a 302) and from the seeder alone, both matching the sha256 |

`release-0.1.0-preview.1/` holds `release.json`, `SHA256SUMS` and the logs.
