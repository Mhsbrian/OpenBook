# NVIDIA's open kernel driver on OpenBook (ANAL-319)

2026-10-30. OpenBook's G14 kernel and vendor layer now carry NVIDIA's open kernel driver for the RTX 5070 Ti Laptop
GPU (GB205), the same build the Googlebook (Ruby) track has shipped since 2026-10-26. The two tracks share one
kernel and one vendor layer: `kernel/` is byte-identical to GoodBook's, and `device/` differs only in GoodBook's
Ruby-only folders (see "How the tracks share it" below).

Labels:
- **CONFIRMED**: read in source we have, or seen in our own test output.
- **HYPOTHESIS**: not yet tested.

Release impact: **AOSP**. It changes the G14 product's kernel, `vendor_dlkm` and `vendor`. The laptop runs the
Ruby image, so no OpenBook image has been written to it.

## What you get, and what you don't

| | On OpenBook | Notes |
|---|---|---|
| NVIDIA's open modules, 615.78.08 | ✅ In `vendor_dlkm`, loaded after boot in Hybrid | `nvidia.ko`, `nvidia-modeset.ko`, `nvidia-drm.ko` (Dual MIT/GPL) |
| GSP firmware | ✅ `/vendor/firmware/nvidia/615.78.08/` | 85.3 MB, unmodified, with NVIDIA's licence |
| The RTX powering off when idle | ✅ Runtime D3cold, CONFIRMED on the G14 | the GPU wakes for a client and goes back to D3cold |
| Graphics modes | 🧪 The switcher reads the mode (Hybrid) and keeps the stack on the panel's GPU | switching waits for firmware writes, which stay off; no app on OpenBook yet ([`nvidia-graphics-modes.md`](nvidia-graphics-modes.md)) |
| A GPU health line in `dgpu-report` | ✅ NVRM/Xid counts and NVIDIA's runtime-D3 status | for diagnosis over adb |
| Apps on the RTX (Vulkan, GL) | ❌ Not on OpenBook | needs NVK on NVIDIA's driver, which stays private to GoodBook (below) |
| nouveau | ⏸ In `vendor_dlkm`, blocklisted, never loaded | owner decision 2026-10-27: NVIDIA's open driver only |
| Display through the RTX (Ultimate, HDMI in Hybrid) | ❌ Not yet | ANAL-244, ANAL-249 |

**Why apps can't use the RTX here:** an Android app reaches a GPU through a Vulkan driver, and the only one that
runs on NVIDIA's kernel driver is NVK built from the `nvk-rm` tree. The owner cleared that code for one laptop and
one private repository (ANAL-298, 2026-10-26), so it is not in OpenBook. Upstream NVK runs only on nouveau, which is
off. When NVIDIA's driver binds, init still offers the OpenBook NVK package to apps (`ro.gfx.driver.0`). OpenBook
installs no such package, so Android logs `updatable driver package 'org.openbook.nvk' not installed` and an app
opted in keeps the Radeon driver. CONFIRMED in AOSP 17's `GraphicsEnvironment.java`.

## Licences, and the owner's decisions

- **The modules** are NVIDIA's open-gpu-kernel-modules, Dual MIT/GPL. CONFIRMED.
- **The GSP firmware** is NVIDIA's, from its 615.78.08 driver package, under the NVIDIA Driver License Agreement it
  ships with (`LICENSES/LICENSE.nvidia-driver-615.78.08`). Its §1.1(c) allows own use; its §1.1(d) allows
  distribution "for use with operating system kernels distributed under the terms of an OSI-approved open source
  license", provided "(i) the binary files thereof are not modified in any way (except for uncompressing of
  compressed files) and (ii) this Agreement is provided to each SOFTWARE recipient". §2.8 limits GeForce software
  to GeForce hardware the user owns. CONFIRMED in the Agreement's text.
  - 2026-10-26 (ANAL-297): the owner chose the own-use terms; OpenBook images with the firmware stayed private.
  - **2026-10-31 (ANAL-320): the owner wants NVIDIA's work in the public image.** Public OpenBook images carry the
    firmware under §1.1(d). `scripts/release/make-release.sh --nvidia-licence` checks every NVIDIA file in the
    image against its pin (unmodified), and puts the Agreement next to the image, in `SHA256SUMS` and in
    `release.json`. openbook.page links it from the download, and the image has it in `/vendor/firmware/LICENSES`.
- **NVK on NVIDIA's driver (apps on the RTX) stays out of OpenBook.** GoodBook's `nvk-rm` tree has 3 backend files
  and 13 Mesa patches that cite reverse engineering of NVIDIA's proprietary libraries, and the owner's rule for it is
  "private use, never shared; replace these parts first if anything is ever shared" (GoodBook `docs/nvidia-rm-nvk.md`
  §8, ANAL-298). Bringing apps on the RTX to OpenBook needs that replacement first: a clean rewrite of the 6 places
  in the backend core from open-gpu-kernel-modules' MIT headers, and of the 13 patches. GoodBook's estimate for the
  core: "looks small (HYPOTHESIS until done)".
- **The kernel's GKI exception** (ANAL-297; with NVIDIA's driver in the public image, it ships too): Google's GKI denylist forbids
  `filp_open`, `kernel_read` and `kernel_write` on partner symbol lists. NVIDIA's runtime D3 and its saving of video
  memory across suspend need exactly those, so `kernel/patches/build-kernel/0001` takes an explicit exception for
  the AnyBook list. The alternative, NVIDIA's own Android build mode, loses both features.

## Images without the firmware (ANAL-320)

Since 2026-10-31 public images carry the firmware (above). An image can still be built without it, for anyone who
wants to publish OpenBook without NVIDIA's Agreement. It ships the same kernel and modules, which are Dual MIT/GPL
and redistributable with their source, and leaves the driver unloaded:

- **Staging:** `G14_NVIDIA_FIRMWARE=none scripts/g14-stage-kernel.sh <dist>` stages the kernel without the firmware
  and says so in `PROVENANCE.txt`. Without `none`, the staging still refuses `nvidia.ko` with no firmware.
- **No load:** `openbook-pc-setup dgpu-driver boot` looks for `/vendor/firmware/nvidia/*/gsp_*.bin` first. With none
  there, it logs why and returns, without touching the crash guard, so an image that has the firmware behaves as
  before. `openbook_pc_setup` may list that folder and stat its files, and nothing more.
- **The RTX powers off as before the driver existed:** at early init `dgpu-pm` finds the GPU unbound, unbinds
  `snd_hda_intel` from its HDMI-audio function and sets `power/control=auto` on every function, so the root port can
  take the slot to D3cold.
- **The check:** `scripts/release/make-release.sh` refuses an image whose raw bytes hold a firmware file's directory
  entry or NVIDIA's licence file. It ignores the firmware paths inside `nvidia.ko`, which every image with the
  modules has.

What has been shown, and what hasn't:

| | Result | Evidence |
|---|---|---|
| The firmware is not in the public build | `/vendor/firmware` has no `nvidia` folder and `LICENSES` has no NVIDIA licence (`dump.erofs` on the vendor image inside the live image, same sha256) | `evidence/2026-10-31-public-preview/` |
| The public build boots | standard G14 QEMU check 58/58; the image's own `openbook-pc-setup-test` 0 failures, with the no-firmware cases | same |
| The unbound RTX reaches D3cold on the G14 | **2026-10-16, older build, same `dgpu-pm` hook:** both functions `D3cold`/`suspended` with no driver bound | `evidence/2026-10-16-installer/g14-live/SUMMARY.md` |
| The same on this build's kernel | **not measured yet.** QEMU has no NVIDIA GPU, and the laptop's adb was off on 2026-10-31. Next: the stick's "save logs" entry on the G14 records it | |

## The kernel side

All of it lives in `kernel/`, identical in both repositories.

- **Version pin:** `kernel/patches/nvidia-open/PIN`, 615.78.08, built by Kleaf as external vendor modules of the G14
  kernel `6.18.21-android17-5-g2461ae8277e6` (`kernel/devices/anybook/nvidia_open/`).
- **Seven patches to NVIDIA's tree** (`kernel/patches/nvidia-open/0001`–`0007`):
  - leave out the Tegra SoC code and NUMA onlining of coherent GPU memory on x86_64;
  - import Google's VFS symbol namespace;
  - create the device nodes through the driver core;
  - build the OS-independent cores with the kernel's retpoline and return-thunk flags;
  - two Kbuild fixes for an out-of-tree build.
- **61 KMI symbols** (`kernel/patches/common/0005`): 53 new exports for vendor modules, and 8 that GKI modules already
  get but that are protected from unsigned ones. No existing export or CRC changed. CONFIRMED.
- **Hardening:** as NVIDIA ships them, the cores would load with no retpolines, return thunks or kCFI type hashes,
  and with `PANIC_ON_OOPS=y` a checked call into them panics. Here they are built with the kernel's flags, and with
  kCFI type hashes but no checks inside the cores, because NVIDIA's NVOC dispatch calls methods through generic
  pointer types. CONFIRMED in QEMU.
- **nouveau** and its 33 symbols (`kernel/patches/common/0004`, `kernel/devices/anybook/nvidia/`) stay in the kernel,
  so both tracks build the same kernel. Its module is blocklisted and nothing loads it.

## The vendor side

- **Loading.** `vendor_dlkm` blocklists all three modules, so nothing NVIDIA's loads in early boot. Once the system
  is up in Hybrid, `openbook-pc-setup dgpu-driver boot` loads `nvidia-drm`, which pulls in the other two, and waits
  for the GPU to bind.
  - **Crash guard:** `persist.vendor.openbook.dgpu_driver` reads `loading` while a load runs. A boot that finds
    `loading` (the last load never finished), or a load that fails, leaves `failed`, and no later boot tries again.
  - **Switch:** `setprop debug.openbook.dgpu_driver off` turns the boot load off, and `on` turns it back on (and
    clears `failed`). The choice is kept across reboots.
  - **Never with nouveau.** The lab helper's `nvidia-load` is refused while nouveau is loaded, and the other way round.
- **Module options** (`kernel/devices/anybook/g14/modules.options`): `NVreg_DynamicPowerManagement=0x02`
  (fine-grained runtime D3) and `nvidia-drm modeset=1`.
- **Device nodes:** `/dev/nvidiactl`, `/dev/nvidia*` and `/dev/nvidia-modeset`, 0666 `system:graphics`, labelled
  `gpu_device` like `/dev/dri/*`. The rules are `ueventd.nvidia-open.rc`, installed as `/odm/etc/ueventd.rc`.
- **SELinux for runtime D3:** NVIDIA's probe runs in a kernel thread and opens the GPU's PCI `config` file. The dGPU's
  sysfs files are labelled `sysfs_gpu`, and the kernel and `vendor_modprobe` may read them. Without this, runtime D3
  stays off without an error. CONFIRMED on the G14 (ANAL-299).
- **Graphics stack pinned to the panel's GPU:** `anybook_gpu_probe` picks the card whose internal panel is connected,
  and minigbm and the composer use that card's render node first (`aosp/patches/external/minigbm/0002`), so a second
  render node from `nvidia-drm` cannot take over composition.
- **Graphics modes:** the `openbook-gfx-mode` vendor service (`device/anybook/common/gfx-mode/`) and its recovery
  entries in the boot menu (`openbook-bootsync`). The OpenBook Graphics app's source is in the same folder, but only
  the Ruby image installs it; adding it to OpenBook's product is a follow-up. Design and rollback rules:
  [`nvidia-graphics-modes.md`](nvidia-graphics-modes.md).

## What was shown on the G14

These results come from the Googlebook images, which run this exact kernel and these vendor files. CONFIRMED unless
labelled.

- **2026-10-26, on R5 (ANAL-299):** NVIDIA's driver loads with kCFI enforced and binds the GB205. The GPU reaches
  D3cold when idle, wakes for each Vulkan client, goes back to D3cold, and survives s2idle with the driver bound. Two
  corrections came out of it: the runtime-D3 policy above, and the `/dev/nvidia*` ueventd rule (a trailing `*` is a
  prefix match, so `/dev/nvidia[0-9]*` never matched `/dev/nvidia0`).
- **2026-10-28, R7:** the driver loads at every start in Hybrid, the RTX stays in D3cold while idle, and Android's
  `system_server` does not restart.
- **2026-10-29, R8:** the `dgpu-report` health line prints on the hardware.
- **OpenBook's own G14 image, 2026-10-30, in QEMU (no NVIDIA GPU):**
  - the product's standard check passes 58/58, with no new SELinux denial;
  - the new `scripts/installer/expect-g14-nvidia.json` passes 23/23: the modules match the kernel, are blocklisted
    and are not loaded; the firmware hashes match their pins; the device-node rules are installed; the switcher
    stays in Hybrid with firmware writes off.

  Evidence: `evidence/2026-10-30-shared-nvidia-platform/`.
- **Not shown:** S0i3 (deep sleep) with the driver bound, battery life over a day, and display through `nvidia-drm`.
- **HYPOTHESIS:** OpenBook's own system image on the laptop behaves the same, since the kernel and vendor files are
  identical. It has not been installed there.

## Build it

```bash
# 1 · The G14 kernel with NVIDIA's modules (Kleaf), packaged with its module lists and QEMU checks
scripts/kernel-g14-package.sh

# 2 · NVIDIA's GSP firmware, taken from NVIDIA's driver package (only its sha256 is trusted; nothing in it runs)
python3 scripts/kernel-nvidia-open-firmware.py --pin kernel/firmware/anybook-nvidia-open.tsv \
  --run NVIDIA-Linux-x86_64-615.78.08.run --out ~/anybook/kernel/nvidia-open-firmware

# 3 · Stage both into the AOSP tree (every image and firmware file is checked against its pin), then build
G14_NVIDIA_FIRMWARE=~/anybook/kernel/nvidia-open-firmware scripts/g14-stage-kernel.sh <dist>
scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug
```

`g14-stage-kernel.sh` refuses a kernel whose `vendor_dlkm` carries `nvidia.ko` but has no matching firmware. The
QEMU checks with a test-only `nvidia.ko` that stays loaded without a GPU are `scripts/kernel-nvidia-open-qemu-variant.sh`
and `scripts/nvidia-open-variant-check.sh`.

## How the tracks share it

- **Identical in both repositories:** `kernel/`; `device/` apart from GoodBook's Ruby-only `updater`, `safety` and
  `nvk-driver` folders and the installer's Googlebook image-base choice; and the kernel build, packaging and check
  scripts. A change to any of them is made in one repository and ported to the other with
  `git format-patch` / `git am`, and the port is recorded in both pull requests.
- **GoodBook only:** the Ruby image pipeline, OpenBook Update, the Google firmware-tool guards, and NVK on NVIDIA's
  driver with its package (`mesa/patches/nvk-rm`, `nv-rm`).
- **The 2026-10-30 port** (ANAL-319) brought OpenBook up to GoodBook `792d203`. First the pre-split work from
  OpenBook's own integration commit `d7a170fa`, then GoodBook's 26 later commits on these paths, each with a
  "Ported from GoodBook" line.
