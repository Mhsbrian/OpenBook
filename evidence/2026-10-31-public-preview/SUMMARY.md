# OpenBook 0.1.0-preview.1: the public build with NVIDIA's open driver and firmware (ANAL-320, 2026-10-31)

The owner wants NVIDIA's work in the public image (comment on ANAL-320, 2026-10-31). This is the G14 product as
it runs on the laptop: NVIDIA's open driver 615.78.08, its GSP firmware, runtime D3 and the graphics-mode layer.
The firmware ships under the NVIDIA Driver License Agreement's §1.1(d): unmodified, for use with an OSI-licensed
kernel, with the Agreement given to every recipient. Apps on the RTX (NVK on NVIDIA's driver) are not in it (see
the end). **Nothing is published.** The folder is unsigned and not owner-approved, so `release.json` says
`"public": false`.

An earlier build of the same day without the firmware, `G14_NVIDIA_FIRMWARE=none`, is in
[`without-nvidia/`](without-nvidia/SUMMARY.md). It also records the live-stick fix and how it was found.

## The image

`openbook-live-20261031-anal320nv.img`: 3,180,331,008 bytes, sha256 `5cc31063…e8618`. Product
`anybook_g14_x86_64-cp2a-userdebug` (`…:userdebug/test-keys`), kernel `6.18.21-android17-5-g2461ae8277e6` (the
`anal297` dist the G14 has run since 2026-10-26), NVIDIA's firmware staged and checked against its pins
(`image/kernel-staging-provenance.txt`). Built from this branch at `bc680b08`, clean (`build.json`: `dirty: false`).

| Check | Result | File |
|---|---|---|
| NVIDIA's files in the image are NVIDIA's, unmodified | `gsp_ga10x.bin` `a20100ca…`, `ucodes_ga10x.bin` `eed53d76…` and the Agreement `c692fb14…` match `kernel/firmware/anybook-nvidia-open.tsv`. They were read both inside the booted image and from the image's own vendor partition, which `make-release.sh` extracts (`vendor.img` = the image's `vendor_a`, `592daf33…`) | `qemu-g14-nvidia/nv-firmware.txt`, `image/vendor-match.txt`, `release-0.1.0-preview.1/make-release.log` |
| Every firmware file has its licence | 141 files, none without a licence. The NVIDIA files map to the Agreement through NVIDIA's manifest (fixed here: `mklive.py` read only linux-firmware's) | `image/openbook-live-20261031-anal320nv.build.json` |
| NVIDIA check (installed disk, QEMU) | **23/23**: the modules match the kernel and are blocklisted for early boot, the firmware hashes match, the device-node rules are installed, the switcher stays in Hybrid with firmware writes off, 0 SELinux denials | `qemu-g14-nvidia/` |
| Standard G14 check (installed disk, QEMU) | **58/58**; the image's own `openbook-pc-setup-test` 0 failures; 0 SELinux denials | `qemu-g14/` |
| Live USB stick (QEMU) | **32/32**: first boot (boot completed at 14.8 s), second boot, start fresh, save logs. Logcat shows the checkpoint commit, then the HAL's live-stick branch (the fix) | `qemu-live/` |

QEMU has no NVIDIA GPU, so the driver doesn't bind there. On the G14 this kernel and vendor layer load NVIDIA's
driver after boot and hold the RTX in D3cold when idle: shown on 2026-10-26 (R5, ANAL-299) and 2026-10-28 (R7)
with the sibling image (`docs/nvidia-open.md`). This exact image has not run on the G14.

## The source

`sources/SOURCES.md`; 168,659,600 + 108,583,468 + 19,049,408 bytes. The kernel tarball holds NVIDIA's open modules
(Dual MIT/GPL) with OpenBook's patches, under `devices/anybook/nvidia_open`, along with Google's kernel and
OpenBook's commits. The rest is as in `without-nvidia/`.

## The release folder

`<data dir>/release/out/0.1.0-preview.1/` (not in the repository):

| | |
|---|---|
| Image | `openbook-0.1.0-preview.1-x86_64-live.img.xz`, 1,010,992,432 bytes, xz -9 |
| NVIDIA's Agreement | `LICENSE.nvidia-driver-615.78.08` next to the image, in `SHA256SUMS`, and in `release.json`'s `third_party` with the terms and the decision |
| Torrent | hybrid v1 + v2, 965 pieces of 1 MiB, info hash v1 `3cdb539387471bfb8e8d766ddd4051c9039fcc0d`, web seed on the GitHub Release |
| Gates | pass: `nvidia_firmware_terms`, `firmware_licences`, `source_offer`. Blocking: `release_keys`, `user_build`, `checksums_signed`, `owner_approved`. Nothing waived |
| Download test | `swarm-test.sh` **9/9**: the whole image from the web seed alone (through a 302) and from the seeder alone, both matching the sha256 |

`site/downloads-page-test-copy.png`: a TEST-ONLY copy marked public, published with openbook.page's
`publish-release.sh --from` (openbook.page PR #2). The Agreement is served as text (`text/plain`, 22,653 bytes) and
linked as "Licence: NVIDIA GSP firmware 615.78.08".

## Not in the image: apps on the RTX

GoodBook runs apps on the RTX through NVK on NVIDIA's driver, built from its `nvk-rm` tree. That tree has 3 backend
files and 13 Mesa patches that cite reverse engineering of NVIDIA's proprietary libraries, and the owner's rule
for it (GoodBook `docs/nvidia-rm-nvk.md` §8, ANAL-298) is private use, never shared, with those parts replaced
before anything is shared. So OpenBook's image has NVIDIA's driver, firmware and power management, and the desktop
and apps stay on the Radeon. The way to bring apps on the RTX here is a clean rewrite of those parts from
open-gpu-kernel-modules' MIT headers; GoodBook estimates the core as small, a hypothesis until done.
