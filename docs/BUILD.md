# Build and reproduce

How to build OpenBook from source: the host, the containers, the AOSP tree, the products, the kernel, Mesa, the G14
images, and the tests for each area. Each section names the topic doc that explains the why. Turning a built image
into a release is in [`RELEASE.md`](RELEASE.md).

## Host

- **No host sudo.** The build host runs Arch Linux; every tool its base system doesn't provide runs in a Docker
  container. You need Docker, your user in the `docker` group, and `/dev/kvm` accessible.
- **CPU and RAM:** plan for 32+ threads and 64 GB of RAM, plus swap. A full AOSP build peaks at about 41 GiB of RAM
  plus 18.5 GiB of swap on a 61 GB host; Soong analysis alone takes 38–43 GiB. So only one AOSP build runs at a time
  ([lane lock](#the-lane-lock)).
- **File system:** snapshots of build outputs are reflink copies. On btrfs they cost no space; elsewhere they are
  plain copies.
- **Disk** (compressed `du` on btrfs zstd:3):

  | What | Size |
  |---|---|
  | AOSP source mirror and build tree | 102 GB + 128 GB |
  | AOSP `out/` | 137 GB, 165 GB with `dist` |
  | ccache | up to 100 GB (about 10 GB after one full build) |
  | Kernel sources and Bazel cache | 53 GB + 9 GB, plus 0.6 GB per dist |
  | Googlebook OS reference images and the emulator SDK (optional) | about 60 GB |
  | Digitalis AOSP 16 tree (optional, for the emulator bridge) | 115 GB |

  A full AOSP mirror plus one build is about 600 GB. Sizing details: [`aosp-build.md`](aosp-build.md),
  [`kernel.md`](kernel.md).

## Layout (outside the repo; images are never committed)

```
~/anybook/
  repo/                 this repository
  aosp/mirror, aosp/src AOSP source mirror and build tree (docs/aosp-build.md)
  ccache/               AOSP ccache
  kernel/               kernel tree, dists, G14 packaging, firmware (docs/kernel.md)
  mesa/                 Mesa sources, builds and artifacts (docs/mesa.md)
  installer/out/        product and live images
  ota/                  A/B update packages
  release/out/          release folders (docs/RELEASE.md)
  logs/                 build and test logs, per area
  dl/                   downloads (recovery zips, SDK zips): proprietary, local only
  work/<codename>/      unpacked Googlebook OS images (gbos-unpack.sh output)
  android-sdk/, avd/    emulator SDK and AVDs (m0-emulator.sh)
  evidence/openbook/    results that test scripts write ($OPENBOOK_EVIDENCE); never committed
```

Scripts call this the data dir; most also read `OPENBOOK_HOME` or `ANYBOOK_HOME`.

## Containers

```bash
docker build -t anybook-inspect -f tools/Dockerfile.inspect tools/         # android-tools, erofs-utils, binutils, elfx86exts
docker build -t anybook-qemu    -f tools/Dockerfile.qemu    tools/         # qemu 11.x + OVMF
docker build -t openbook-installer -f tools/Dockerfile.installer tools/   # qemu + OVMF, GRUB, systemd-boot/ukify, mtools, gptfdisk, make (test modules)
docker build -t anybook-aosp -f tools/Dockerfile.aosp --build-arg UID=$(id -u) --build-arg GID=$(id -g) tools/
docker build -t anybook-mesa-android -f tools/Dockerfile.mesa-android tools/   # NDK r30 LTS, meson 1.12.1
docker build -t anybook-cuttlefish -f tools/Dockerfile.cuttlefish tools/       # pinned Cuttlefish image + Mesa Vulkan
```

The kernel image (`tools/Dockerfile.kernel`, Ubuntu 24.04) is built on first use by `scripts/kernel-docker.sh`.
Plain Cuttlefish boots use `cuttlefish-orchestration:1.56.0`, pinned by digest in `scripts/cf-boot.sh`.

## AOSP source tree

```bash
scripts/aosp-docker.sh bash -c 'ccache -M 100G && ccache --set-config=compiler_check=content'   # ~/anybook/ccache
scripts/aosp-docker.sh -d anybook-aosp-sync /repo/scripts/aosp-sync.sh all && docker wait anybook-aosp-sync   # ~47 min first time; rerun resumes
scripts/aosp-docker.sh /repo/scripts/aosp-verify.sh aosp_cf_x86_64_pc-cp2a-userdebug   # lunch + m nothing
```

- `~/anybook/aosp/mirror` is a full-history mirror of the 975 source projects. `~/anybook/aosp/src` is the
  `android-latest-release` tree; it borrows source objects from the mirror, and the 112 prebuilt projects are
  shallow. Don't delete the mirror while the tree exists.
- **The pin:** `manifests/aosp/manifest-pinned.xml.gz` records every project's revision. `scripts/aosp-patches.sh`,
  which `aosp-build.sh` runs before every build, applies OpenBook's patch series (`aosp/patches/<project>/`) on top of
  each project's pinned revision, and imports the Digitalis fork into `frameworks/libs/binary_translation` from its
  `IMPORT` file. It is idempotent; `--export PROJECT` writes edited commits back. Moving the pin:
  `manifests/README.md`.
- **`IMPORT` commits are fetched on the host.** The build container has no GitHub credentials, so `aosp-docker.sh`
  runs `aosp-patches.sh --fetch` on the host before it starts `aosp-build.sh` or `aosp-patches.sh`, under the lane
  lock. It fetches only the commits the tree lacks (a private fork such as OpenBook Launcher needs `gh auth login` on
  the host), so it is a no-op without network once they are there. Test: `tests/aosp-patches-import-test.sh`.
- **Use `cp2a`, not `trunk_staging`.** `cp2a` builds Android 17 (`REL`); `trunk_staging` on this branch reports
  `PLATFORM_VERSION=Baklava`.
- Why the tree is split this way, the container and the sandbox options: [`aosp-build.md`](aosp-build.md).

### The lane lock

The AOSP tree and `out/` are shared by every branch that builds, so builds run under the lane lock
`~/anybook/aosp/.lane.lock`.
- `aosp-docker.sh` takes it for `aosp-build.sh`, `aosp-sync.sh` and `aosp-patches.sh` (any command with `ANYBOOK_LANE=1`). It waits for
  whoever holds it and keeps it until the container exits, `-d` included.
- A caller that already holds it with `flock <lock> …` is recognised; one holding it through an inherited fd sets
  `ANYBOOK_LANE_LOCK_HELD=1`. Started any other way, `aosp-build.sh` refuses.
- `installer-image.sh` holds the lock while it snapshots `PRODUCT_OUT`; `g14-stage-kernel.sh` refuses while a build
  runs.
- `ANYBOOK_LANE_UNLOCKED=1` is for a tree of your own. Test: `scripts/aosp-lane-test.sh`.
- **Before a build that follows another branch's,** give the tree's device directory the current time:
  `find ~/anybook/aosp/src/device/anybook -exec touch {} +`. Otherwise outputs another branch copied from its own
  version of a file can look up to date.
- To build and snapshot in one hold, so no other build changes `PRODUCT_OUT` in between, wrap both in
  `flock ~/anybook/aosp/.lane.lock bash -c '…'` (examples below).

## Build targets

| Lunch target | What | `PRODUCT_OUT` | Doc |
|---|---|---|---|
| `aosp_cf_x86_64_pc-cp2a-userdebug` | Google's PC Cuttlefish product: the plain AOSP baseline (M1b) | `vsoc_x86_64_only` | [`aosp-build.md`](aosp-build.md) |
| `anybook_cf_x86_64_pc-cp2a-userdebug` | The OpenBook desktop product, for Cuttlefish | `anybook_vsoc_x86_64` | [`aosp-desktop.md`](aosp-desktop.md) |
| `anybook_g14_x86_64-cp2a-userdebug` | The OpenBook G14 product, for bare metal | `anybook_g14` | [`g14-product.md`](g14-product.md) |

Both OpenBook products need the staged Mesa prebuilts ([Mesa](#mesa)); without them `graphics-amd.mk` stops the
build with a message naming the scripts. The G14 product also needs the staged kernel ([The G14 product](#the-g14-product)).

### The AOSP baseline in Cuttlefish (M1b)

```bash
AOSP_JOBS=32 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh aosp_cf_x86_64_pc-cp2a-userdebug
docker wait anybook-aosp-build          # ~2 h 10 min cold on a shared host; re-running resumes
scripts/cf-boot.sh                      # Cuttlefish container: launch, wait for boot_completed, capture, tear down (~45 s)
```

- Cuttlefish runs in `cuttlefish-orchestration:1.56.0` (pinned by digest) with `--cap-add NET_ADMIN`,
  `seccomp=unconfined`, and `/dev/kvm`, `/dev/net/tun`, `/dev/vhost-net` and `/dev/vhost-vsock`.
- Images are staged as reflink copies in `~/anybook/aosp/cf/product`; `out/` is never modified.
- `scripts/cf-boot.sh up|wait|capture|down` runs the steps one at a time; logs go to `~/anybook/logs/aosp/cf-<ts>/`.

### The OpenBook desktop product in Cuttlefish (M2)

```bash
AOSP_JOBS=32 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug
docker wait anybook-aosp-build          # 13–25 min incremental on top of the baseline
CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_DEVICE=anybook_vsoc_x86_64 scripts/cf-boot.sh   # Radeon iGPU; CF_GPU=nvidia also works
```

- `scripts/desktop-capture.sh` captures screenshots and windowing/SurfaceFlinger dumps; `scripts/desktop-ref-emulator.sh`
  runs the same capture on Google's desktop emulator image; `scripts/desktop-compare.py` diffs the two;
  `scripts/cf-gfx-bench.sh` compares GPU modes. See [`aosp-desktop.md`](aosp-desktop.md).

### A private Cuttlefish copy for checks

The Quire and UI checks run on a snapshot of the product, so the shared `out/` can move on. Build and snapshot in one
lane-lock hold, then boot the snapshot under its own name and ports:

```bash
flock ~/anybook/aosp/.lane.lock bash -c 'AOSP_JOBS=24 scripts/aosp-docker.sh /repo/scripts/aosp-build.sh \
    anybook_cf_x86_64_pc-cp2a-userdebug droid [EXTRA_MODULES] &&
  S=~/anybook/aosp/cf/NAME-out O=~/anybook/aosp/src/out P=anybook_vsoc_x86_64 &&
  mkdir -p $S/target/product/$P $S/host/linux-x86 &&
  find $O/target/product/$P -maxdepth 1 -type f -exec cp --reflink=auto -t $S/target/product/$P {} + &&
  cp --reflink=auto $O/host/linux-x86/cvd-host_package.tar.gz $S/host/linux-x86/'
export CF_OUT=~/anybook/aosp/cf/NAME-out CF_STAGE=~/anybook/aosp/cf/NAME CF_NAME=anybook-cf-NAME \
  CF_DEVICE=anybook_vsoc_x86_64 CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle \
  CF_ADB_PORT=<adb port> CF_WEBRTC_PORT=<webrtc port> CF_ARGS=--vhost_user_vsock=true
scripts/cf-boot.sh up && scripts/cf-boot.sh wait && adb connect 127.0.0.1:<adb port>
scripts/ui/desktop-defaults.sh 127.0.0.1:<adb port> OUT/defaults     # first, before any app opens
# ... the checks ...
scripts/cf-boot.sh down
```

A second VM on the same host needs `CF_ARGS=--vhost_user_vsock=true`: vsock ports are host-wide. Test APKs built as
`EXTRA_MODULES` (for example `QuireSecureProbe`) land under `$O/target/product/$P`; copy them out in the same hold.

## Kernel

Google's GKI rebuilt from the exact Googlebook sources, OpenBook's vendor modules, and the G14 packaging. Everything
runs in `tools/Dockerfile.kernel` through `scripts/kernel-docker.sh`. Details, checks and the reasons:
[`kernel.md`](kernel.md).

```bash
scripts/kernel-sync.sh            # exact Googlebook kernel sources (manifests/kernel/gbos-16302624.xml) -> ~/anybook/kernel/src
scripts/kernel-build.sh           # the plain GKI: tools/bazel run --config=stamp //common:kernel_x86_64_dist -> ~/anybook/kernel/dist/<target>
```

Plan for 53 GB of sources, 9 GB of Bazel cache and about 6 min per build on 32 threads.

**AMD vendor modules** (ANAL-171), on the same tree:

```bash
scripts/kernel-amd-apply.sh       # kernel/patches -> common and build/kernel, kernel/devices/anybook -> //devices/anybook
KERNEL_TARGET=//devices/anybook:anybook_amd_x86_64_dist scripts/kernel-build.sh anybook-amd-gbos-16302624
```

**The kernel in Cuttlefish** (ANAL-172): the OpenBook kernel with the AOSP baseline's userspace (`~/anybook/aosp/src/out`,
read only).

```bash
KERNEL_TARGET=//common-modules/virtual-device:virtual_device_x86_64_dist scripts/kernel-build.sh anybook-vdev-gbos-16302624   # 6 min, once
scripts/kernel-cf-boot.sh          # OpenBook module set; `board` for the control. About 1.5 min per boot
```

- Its own container (`anybook-cf-kernel`), ports (adb 16572, WebRTC 11472) and vsock CID 172, so it can run next to
  `scripts/cf-boot.sh`.
- Disk: 4.1 GB of reflinks for the snapshot, plus 3.3 GB per staged boot, in `~/anybook/kernel/cf/`.

**G14 bare-metal packaging** (ANAL-198): needs the synced tree and, for the boot check, a Cuttlefish `PRODUCT_OUT` to
borrow the userspace from (default: the snapshot `kernel-cf-boot.sh` takes, read only).

```bash
scripts/kernel-g14-package.sh     # apply, Kleaf images, list/signing checks, firmware, QEMU first-stage check
```

- Resumable: finished steps are skipped while their inputs are unchanged; `--from STEP` reruns from STEP.
  `--evidence DIR` also copies the reports (no images, no firmware) to DIR, outside the checkout.
- Outputs in `~/anybook/kernel/g14/<label>/` (default label `anybook-g14-gbos-16302624`): `images/`
  (`vendor_boot.img`, `vendor_dlkm.img`, `system_dlkm.img`, `bzImage`, `vm/`), `firmware/` (`/vendor/firmware` tree
  and `firmware.mk`), `qemu/` and `results.json`.
- The firmware step needs a linux-firmware git clone at `~/anybook/kernel/firmware/linux-firmware`
  ([`kernel.md`](kernel.md), "Firmware subset").
- Disk: about 0.6 GB per dist, 50 MB of staged firmware and 9 GB of sparse QEMU disks. The QEMU runs use 6 GiB of RAM
  each, one at a time.
- NVIDIA's GSP firmware for the G14 image is a separate step: [`nvidia-open.md`](nvidia-open.md), "Build it".

## Mesa

radeonsi and RADV for Android x86_64, built out of tree with the NDK, then staged into the AOSP tree as vendor
prebuilts. Details and the reasons: [`mesa.md`](mesa.md), [`graphics-amd.md`](graphics-amd.md).

```bash
scripts/mesa-android-build.sh fetch deps setup build install verify -- upstream   # what the image needs; resumable
scripts/graphics-amd-stage-mesa.sh              # Mesa prebuilts -> ~/anybook/aosp/src/vendor/anybook/mesa (never committed)
scripts/mesa-android-build.sh                   # all steps (+ isa), both trees: upstream and Android-Generic, for comparison
scripts/mesa-android-smoke.sh                   # load test on the AOSP Desktop emulator (own AVD, port 5590)
```

- Defaults: `LIBELF=shared`, `ANDROID_STRICT=false` (RADV reports Vulkan 1.4, and `graphics-amd-stage-mesa.sh` writes
  `mesa.mk` so the image declares the same version). `fetch` applies `mesa/patches/upstream/`.
- A strict (Vulkan 1.1) build for comparison or fallback, in its own directories:
  `MESA_VARIANT=-strict ANDROID_STRICT=true scripts/mesa-android-build.sh fetch setup build install verify -- upstream`,
  staged with `scripts/graphics-amd-stage-mesa.sh upstream-strict`.
- Artifacts go to `~/anybook/mesa/out/<tree>/vendor/` and logs to `~/anybook/logs/mesa/`.
- Rerun the stage script after every Mesa rebuild, before the OS build.

### NVK, the NVIDIA driver for apps

The G14 product carries OpenBook NVK: NVK on NVIDIA's open kernel driver, in the system package `org.openbook.nvk`
([`nvk-openbook.md`](nvk-openbook.md)). Build and stage it before the OS build. The product stops without it, and
`OPENBOOK_NVK=false` builds an image without NVIDIA app support.

```bash
scripts/nvk-provenance-check.sh                                    # the provenance gate: 0 hits, the clean-room files unchanged
scripts/mesa-android-build.sh fetch deps clc rm setup build install verify -- nvk-rm-clean   # ~5 min with ccache
scripts/nvk-stage.sh                                               # the tested bytes only -> <AOSP>/vendor/anybook/nvk
scripts/graphics/nvk-package-hosttest.sh                           # after the OS build: the image's package on this host's NVIDIA GPU
```

## The G14 product

```bash
G14_NVIDIA_FIRMWARE=<dir>|none scripts/g14-stage-kernel.sh [<dist>]   # the packaged kernel -> <AOSP>/vendor/anybook/g14-kernel
touch ~/anybook/aosp/src/vendor/anybook/g14-kernel/*                    # older images keep older mtimes; the incremental build would keep the old copies
scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug && docker wait anybook-aosp-build
scripts/g14-image.sh --xz                                     # the product as a USB GPT disk image in ~/anybook/installer/out/
scripts/g14-qemu.sh <img> <run> && scripts/g14-qemu.sh --again <run>   # two boots in QEMU/OVMF from USB
scripts/g14-qemu.sh <img> <run> $PWD/scripts/installer/expect-g14-nvidia.json   # the NVIDIA check (absolute path)
scripts/graphics/graphics-app-qemu.sh <img> <run>             # OpenBook Graphics and OpenBook NVK: packages, screens, the switch, loading
```

- `g14-stage-kernel.sh` checks every image against the dist's `images.json`, so a `bzImage` and a `system_dlkm` from
  different builds can't be staged together. A dist whose `vendor_dlkm` carries `nvidia.ko` needs
  `G14_NVIDIA_FIRMWARE`: a firmware directory, or `none` for an image without NVIDIA's firmware (the public build;
  [`nvidia-open.md`](nvidia-open.md)).
- `g14-image.sh` is image files only; it never touches a disk.
- `scripts/installer/expect-g14-*.json` are the `g14-qemu.sh` check sets: media, MediaPlayer, SoundPool, audio-net,
  NVIDIA, graphics modes, adb auth, reboot. Pass them as absolute paths.
- The product's partitions, packages and vendor layer: [`g14-product.md`](g14-product.md).

### The live USB image

The image people download and write to a stick: the G14 product plus the installer, from
`out/target/product/anybook_g14`.

```bash
scripts/installer-image.sh --menu-timeout 10 [--label <label>] [--no-xz]       # -> ~/anybook/installer/out/
scripts/installer/live-qemu.sh ~/anybook/installer/out/<label>.img <run>        # QEMU/OVMF: grow, persist, reset, logs, decoy NVMe
scripts/graphics/refresh-qemu.sh ~/anybook/installer/out/<label>.img <run>      # refresh rate: render cap, render rate while scrolling
```

- `installer-image.sh` snapshots `PRODUCT_OUT` under the lane lock, builds `openbook-live-init` and runs its host
  test, then assembles the image. Same inputs, label and `--epoch` give the same image, byte for byte.
  `--product-out DIR` takes a snapshot instead of `PRODUCT_OUT`.
- The wizard (`OpenBookInstaller`), the engine (`openbook-install`) and its daemon are part of the G14 product
  (`device/anybook/common/installer/`), so the product build includes them.
- **Writing a stick:** `scripts/installer/write-stick.sh` with `OPENBOOK_WRITE_CONFIRM=/dev/disk/by-id/usb-…`. It
  writes a physical device, so it needs the owner's confirmation of that exact device. Details:
  [`installer.md`](installer.md) §11.
- The integrated owner stick (installer plus the check add-ons, from a clean `main` checkout) and its full test set:
  `installer.md` §13.9. Keep a reflink copy of the image before the add-ons go on: the add-on QEMU tests apply their
  add-on to it.
- The user guide and the release checklist: [`INSTALL.md`](INSTALL.md).

### An A/B update package

For an installed laptop, updated over adb:

```bash
BUILD_NUMBER=<date>.<x> scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug \
    droid target-files-package otatools-package && docker wait anybook-aosp-build
scripts/ota/make-ota.sh openbook-ota-<date>-<x> [--tree DESC]   # -> ~/anybook/ota/out/<label>.{zip,json,bootsync}
```

- Each update build needs its own `BUILD_NUMBER`: it is in the fingerprint, and `g14-adb.sh ota` refuses the running
  build's.
- A full package replaces every partition, so build it from what is installed plus the change (an integration
  branch), not from an older `main`. `--tree` records what it was built from.
- Target files and OTA tools are kept under `~/anybook/ota/builds/`.
- Applying it, the rehearsal and the rollback: [`adb-debug.md`](adb-debug.md) §7. Each update writes the laptop's disk,
  so it needs the owner's go for that device.

### A release image

`scripts/release/make-release.sh` packages a live image that is already built and tested; it does not build the OS.
The steps that make the image:

```bash
G14_NVIDIA_FIRMWARE=<firmware dir>|none scripts/g14-stage-kernel.sh <dist>
scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug && docker wait anybook-aosp-build
scripts/installer-image.sh --label <label> --no-xz             # the live USB image people download
scripts/installer/live-qemu.sh ~/anybook/installer/out/<label>.img <run>        # all live cases in QEMU
scripts/release/make-sources.sh --version <V> --image ~/anybook/installer/out/<label>.img   # GPL/LGPL source, ~300 MB
```

Run `make-sources.sh` before the next AOSP build: it reads that build's NOTICE files. Packaging, signing, the gates
and the publish steps: [`RELEASE.md`](RELEASE.md). The NVIDIA side: [`nvidia-open.md`](nvidia-open.md).

### Debugging the installed G14 over adb

```bash
scripts/g14-adb.sh find && scripts/g14-adb.sh connect     # mDNS finds "OpenBook on ..."; or OPENBOOK_G14_ADDR=<ip>
scripts/g14-adb.sh capture [--hwtest] [--bugreport] [--redact OUT] [DEST]   # the "save logs" set, ~35 s
scripts/g14-adb.sh logcat -b all                           # follow; resumes after a dropped link
scripts/g14-adb.sh persist-logs on                         # keep logcat across boots (product default)
```

The G14 has no USB device mode, so adb is network-only, and it currently needs no authorization
([`adb-debug.md`](adb-debug.md) §5).

## Tests to run

Test once, at the level that decides something (`CONTRIBUTING.md`, [`../tests/README.md`](../tests/README.md)):

- **Fast host tests:** `tests/run.sh` (no hardware, images or containers; CI runs it on every pull request).
- **Component and VM tests:** the harnesses below, for the area a change touches. Results go on the issue and into
  `$OPENBOOK_EVIDENCE`, never into Git.

### Installer and boot chain

```bash
device/anybook/common/installer/app/tools/compile-check.sh        # the wizard's Kotlin, with the in-tree kotlinc (no Soong)
scripts/installer/engine-test.sh <live.img> <run>                 # engine host tests on image files, ~3 min
scripts/installer/wizard-qemu.sh <live.img> <run>                 # dryrun, install, installed, console in QEMU
scripts/installer/e2e-qemu.sh <live.img> <run> all                # or the cases in groups, each call under 10 min
python3 scripts/installer/e2e-qemu.py avc OUT <logcat.gz and sections/avc.txt files>   # SELinux denials, grouped
```

- `engine-test.sh` builds the engine with gcc in the installer container and runs it on a fixture sysfs with image
  files. It covers refusals, a whole-disk install and an install alongside a Windows-like disk, checked with `sgdisk`,
  `fsck.fat`, mtools and `lpdump`.
- `wizard-qemu.sh` drives the app with `uiautomator` and `input` over the serial console. It installs to a blank
  64 GiB virtual NVMe disk and boots that disk alone; Android's screenshots go to the stick's ESP (`openbook/shots/`).
  Extra cases for firmware boot entries: `nvram-boot` (after `install`), then `alongside`, `alongside-default` and
  `alongside-boot` in that order (`installer.md` §12.11). The Windows-like disk's boot manager is a small EFI app
  (`scripts/installer/efi-standin.c`) built with AOSP's prebuilt clang and lld (`OPENBOOK_EFI_CLANG` to override).
  Results go to `~/anybook/logs/installer/<run>/` (`results.json`, `SUMMARY.md`). Details: `installer.md` §12.
- `e2e-qemu.sh` covers alongside a Windows-like disk, a small disk, power cuts at every install step with restarts,
  the installed disk with and without the stick, and a reinstall. It builds its own test EFI apps
  (`scripts/installer/e2e/obtest-efi.c`). Image files only, about 25 minutes.

The boot-chain prototype (GRUB, systemd-boot, UKI, GBL; `installer.md` §2 and §9):

```bash
scripts/installer/snapshot-inputs.sh <input-label>               # reflink snapshot of PRODUCT_OUT + kernel dist (read-only use)
scripts/installer/proto-matrix.sh <input-label> <run-label>      # USB stick + decoy NVMe, image files only, QEMU/KVM + OVMF
scripts/installer/render-design.sh                               # installer design PNGs from docs/installer-design/index.html
```

The GBL variants need `gbl_x86_64_dev.efi` from ci.android.com (`installer.md` §9).

### Add-ons: microG

The framework patches (`aosp/patches/frameworks/base/0002`–`0004`) are in every build. `openbook-addons` and its
catalogue (`device/anybook/common/addons/`) are part of the PC products. The APKs are microG's own release files,
fetched and checked here, never committed.

```bash
scripts/microg/fetch.sh                        # microG's APKs -> ~/anybook/dl/microg/<version>/ (sha256, size, OpenPGP, signing cert, package)
scripts/microg/make-addon.sh                   # -> ~/anybook/installer/out/openbook-microg-<version>-addon/
scripts/microg/add-to-image.sh IMG ADDON_DIR   # put it on a live IMAGE FILE (--remove IMG takes it off); then write-stick.sh as usual
scripts/microg/addons-test.sh <run>                                    # openbook-addons host tests (image files, a fake cmd)
scripts/microg/engine-addon-test.sh LIVE.img ADDON_DIR <run>           # the installer's add-on path, and a no-add-on plan against main's engine
scripts/microg/addon-qemu.sh IMG MAIN_IMG ADDON_DIR <run> all          # the G14 image in QEMU: plain, main, add-on, second boot, install, installed
scripts/microg/build-test-apks.sh                                      # signature/location checker and the negative-test APK (throwaway keys)
ADB="adb -s <serial>" scripts/microg/gms-apps.sh <label> <outdir>      # Play-services apps on a device, with or without microG
```

- Cuttlefish tests use the VM's own Wi-Fi: `cmd wifi set-wifi-enabled enabled; cmd wifi connect-network VirtWifi open`.
- On Cuttlefish (no OpenBook ESP), run an NDK build of `openbook-addons` as root with
  `--catalog catalog --state state --from-dir src run`.
- Before anything leaves the VM, `scripts/microg/redact.sh` removes FCM, MCS and check-in tokens and device IDs from
  the logs.
- Details: [`gapps.md`](gapps.md) §6 and `installer.md` §14.

### Audio, Wi-Fi and Bluetooth

```bash
# In one lane-lock hold: build with the test modules, then snapshot PRODUCT_OUT
flock ~/anybook/aosp/.lane.lock bash -c 'AOSP_JOBS=24 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh \
  anybook_g14_x86_64-cp2a-userdebug droid openbook_hals_test openbook_audio_logic_test validatekeymaps \
  out/soong/.intermediates/external/wpa_supplicant_8/hostapd/hostapd/android_vendor_x86_64_silvermont_cfi/hostapd \
  && docker wait anybook-aosp-build && scripts/audio-net-qemu.sh snapshot NAME'
scripts/g14-image.sh --label openbook-g14-NAME --product-out ~/anybook/audio-net/product/NAME
scripts/audio-net-qemu.sh payload                      # hwsim + hostapd + DHCP test disk for the guest
scripts/audio-net-qemu.sh run ~/anybook/installer/out/openbook-g14-NAME.img RUN   # HDA card + Wi-Fi AP in QEMU
scripts/installer-image.sh --product-out ~/anybook/audio-net/product/NAME --label openbook-live-<date>-<name> --menu-timeout 10
```

`aosp-build.sh` applies the `aosp/patches/hardware/interfaces` patches (the audio HAL's card and pacing properties).
Details: [`g14-audio-net.md`](g14-audio-net.md).

### Power and input

```bash
scripts/power/make-power-check.sh <name>               # add-on for a live stick, ~1 min (needs openbook-installer with make)
scripts/power/power-check-qemu.sh <name> vm            # QEMU: LPS0 fixture, s2idle, 14 steps
scripts/power/power-check-qemu.sh <name> real          # QEMU: the entry as shipped
scripts/power/collect-qemu.sh RUN <live.img>                            # save-logs facts inside Android 17
scripts/power/touchpad/touchpad-qemu.sh RUN <live.img>                  # the G14 touchpad on uhid: repeat frames, clock errors
TP_MODE=palm scripts/power/touchpad/touchpad-qemu.sh RUN <live.img>     # ... with palm lift-offs (or sticky: a 150 ms pause)
scripts/power/touchpad/touchpad-logs-qemu.sh RUN <live.img>             # the save-logs boot's touchpad capture (TOUCHPADEV)
scripts/power/touchpad/build-replay.sh <AOSP>/external/libchrome-gestures OUT   # offline gestures-library replay on the host
```

- Pass the live image explicitly: the QEMU scripts' default images are old labels.
- `build-replay.sh` builds an isolated host copy of the bundled gestures library and an offline event replay; it
  does not use the AOSP lane or touch the laptop ([`touchpad-behavior.md`](touchpad-behavior.md)).
- Owner steps (Linux comparison on the laptop, the add-on on the stick) and how to read the results:
  [`power-input.md`](power-input.md).

### Graphics

AMD drivers on this host's GPU, from the image:

```bash
scripts/amd-android-hwtest.sh                   # the image's RADV/radeonsi/minigbm on this host's AMD GPU
scripts/minigbm-amdgpu-host-test.sh             # minigbm amdgpu backend, Linux build, same GPU
```

Conformance: dEQP and ANGLE end2end on the G14 (ANAL-177):

```bash
# test modules for the G14 product (~8 min incremental)
AOSP_JOBS=24 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug \
  deqp-binary com.drawelements.deqp AngleEnd2EndTestsHelper && docker wait anybook-aosp-build
scripts/graphics/build-deqp-runner.sh                                   # Mesa's deqp-runner 0.23.2, static musl
scripts/graphics/mkcaselists.py ~/anybook/aosp/src/external/deqp/android/cts/main ~/anybook/gfx-cts/caselists/v1 \
  --angle-expectations ~/anybook/aosp/src/external/angle/android/cts/angle_end2end_tests_expectations.txt
scripts/graphics/pre-check.sh ~/anybook/gfx-cts/caselists/v1            # the lists on this host's AMD GPU (~4 min)
scripts/graphics/gfx-report.py ~/anybook/logs/gfx-cts/precheck-<ts> --mesa-ci ~/anybook/mesa/src/upstream/src/amd/ci \
  --radv-gpu raphael --radeonsi-gpu mendocino
scripts/graphics/make-gfx-check.sh <name>                               # add-on for a live stick (~30 s)
scripts/graphics/gfx-qemu.sh <name> quick1 <live.img>                   # QEMU: the add-on end to end, 40 cases per list
```

Owner steps (add the check to the stick, run it, read the results): `graphics-amd.md`, "dEQP and CTS on the G14".

Headless video-buffer check (ANAL-210): `scripts/graphics/ahb-import-check.c` tests RGB, YV12 and flexible YUV420
imports through the installed EGL driver, including colour readback. It opens no window and does not launch Photos.
Build it with the NDK (API 37):

```sh
x86_64-linux-android37-clang -O2 -Wall -Wextra -Werror \
  scripts/graphics/ahb-import-check.c -landroid -lEGL -lGLESv2 -o ahb-import-check
adb -s <device> push ahb-import-check /data/local/tmp/
adb -s <device> shell /data/local/tmp/ahb-import-check 384 640
```

Exit 0 means all three imports and pixel comparisons passed; 1 means a failed case; 2 means a setup or argument
failure. Optional dimensions must be even, 4–4096. The YV12 fix is Mesa patch `0005`, which
`mesa-android-build.sh fetch` applies; rebuild and stage Mesa before building the OS image.

### ARM compatibility

The harness and the libndk_translation baseline (ANAL-180), on the AOSP Desktop emulator:

```bash
scripts/compat/build-probes.sh         # NDK r30 toolchain (sha1-verified) + probe APKs + CoreMark, in the anybook-ndk container
scripts/compat/fetch-corpus.sh         # F-Droid corpus, sha256-pinned in scripts/compat/corpus/fdroid.tsv
scripts/compat/run-matrix.sh --fresh   # emulator on port 5580: install, launch, wait 15 s, check, screenshot, CSV
scripts/compat/run-bench.sh            # CoreMark arm64 (translated) vs x86_64 (native)
```

`scripts/compat/emulator.sh` boots the M0 AVD with guest Vulkan (`-feature Vulkan`, `hw.gltransport=virtio-gpu`).
Results default to `$OPENBOOK_EVIDENCE/<date>-compat/`. Details: [`compat-harness.md`](compat-harness.md).

Digitalis, the built-in bridge (ANAL-200). The bridge is part of both products: `aosp-patches.sh` imports the fork and
applies its patches and the ART patch in `aosp/patches/art/`.

```bash
scripts/aosp-docker.sh /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug droid berberis_arm64_host_tests
scripts/aosp-docker.sh bash -c 'cd /aosp/src/out/host/linux-x86/nativetest64/berberis_arm64_host_tests && ./berberis_arm64_host_tests --gtest_brief=1'
COMPAT_TARGET=cf scripts/compat/run-matrix.sh -o <dir>        # our Cuttlefish build (scripts/compat/cf.sh up|down|status)
COMPAT_TARGET=cf scripts/compat/run-bench.sh -o <dir>
scripts/compat/digitalis/fp-estimate.sh build && scripts/compat/digitalis/fp-estimate.sh reference
COMPAT_TARGET=cf scripts/compat/digitalis/fp-estimate.sh device -o <dir>   # FRECPE/FRSQRTE vs QEMU, every tier
python3 -I scripts/compat/digitalis/audit-shipped.py out/target/product/<device> <dir>   # what ships, licenses
```

- Adding the bridge to an existing `out/` took about 12 min at `-j28`, with a memory peak of 57.7 GB.
- On a device or the live image, `su 0 openbook-hwtest bridge` checks it ([`digitalis.md`](digitalis.md),
  "On the G14").

Digitalis on the emulator AVD (ANAL-181), from its own AOSP 16 tree:

```bash
scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/sync.sh       # AOSP 16 + Digitalis -> ~/anybook/digitalis/aosp16 (115 GB, ~53 min)
DIGITALIS_JOBS=16 scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/build.sh modules   # 70 bridge modules (44 min) -> ~/anybook/digitalis/bundle
scripts/compat/digitalis/install.sh [-o <dir>]                                  # overlay onto AVD anybook-digitalis (port 5580)
COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system scripts/compat/run-matrix.sh -o <dir> --keep-emulator
scripts/compat/digitalis/bundle.sh && scripts/compat/digitalis/install.sh ~/anybook/digitalis/bundle-a17   # the A17 bridge on the AVD
```

- The tree borrows source objects from the shared AOSP mirror, mounted read-only. It has its own ccache in
  `~/anybook/digitalis/ccache`.
- `install.sh` wipes and reinstalls every time, because a data wipe drops the overlay. The libndk_translation AVD
  `anybook-desktop` is never modified.

### Document fonts

Metric-compatible stand-ins for Windows fonts (ANAL-208). The fonts are committed
(`device/anybook/common/desktop/fonts/documents/`; its `README.md` has sources and sha256).

```bash
# After changing DOCS in scripts/ui/fonts-customization.py, regenerate both configs:
scripts/ui/fonts-customization.py > device/anybook/common/desktop/fonts/fonts_customization.xml   # framework
scripts/ui/fonts-legacy-patch.sh          # aosp/patches/frameworks/base: /system/etc/fonts.xml, for WebView
# Check on a Cuttlefish device, then compare with the fonts' own metrics:
scripts/ui/doc-fonts-check.sh SERIAL OUT                  # WebView: report.json, screen.png, cmd font dump
scripts/ui/doc-fonts-typeface.sh SERIAL OUT/typeface.tsv  # the framework: Typeface + Paint
scripts/ui/doc-fonts-metrics.py --fonttools ~/anybook/aosp/src/external/fonttools/Lib --afm AFMDIR \
  --font arimo=.../Arimo-VF.ttf ... --report LABEL=OUT/report.json --typeface LABEL=OUT/typeface.tsv
```

`aosp-build.sh` applies the `frameworks/base` patch (legacy `fonts.xml` only; the framework reads
`font_fallback.xml`). Details: [`googlebook-ui.md`](googlebook-ui.md) §2.1.1.

### Quire

The agent layer's platform hooks (ANAL-216). Quire is in both products through `desktop.mk`
(`device/anybook/common/quire/quire.mk`). Besides its module it needs frameworks/base patches `0005`–`0007` and
Launcher3 `0002` (`aosp-build.sh` applies them), four aconfig flags in `release/openbook/cp2a/`, and the build flag
`RELEASE_PACKAGE_COMPUTER_CONTROL` (`release/flag_values/cp2a/`). Why: [`quire.md`](quire.md) §2.5.

```bash
device/anybook/common/quire/tools/compile-check.sh   # Quire and its test helper, with the in-tree kotlinc (no Soong)
device/anybook/common/quire/tools/unit-test.sh       # host tests for the parts with no Android types (SessionRoutes, IntakePolicy)
python3 device/anybook/common/quire/tools/policy-test.py   # tool-confirmation regressions; QUIRE_POLICY_SOURCE=<older tools dir> for a negative control
# On a private Cuttlefish copy built with QuireSecureProbe (above):
scripts/quire/q2-cf-check.py SERIAL OUT --probe QuireSecureProbe.apk   # invocation, computer control, refusals, health; fresh /data
```

- `q2-cf-check.py` drives Quire through its root-only `LabActivity` alias, so it needs a userdebug build and
  `adb root`.
- `policy-test.py` uses the AOSP JDK and Kotlin compiler with host boundary fakes; no device, model or network.

Quire's note (ANAL-219):

```bash
# Iterate without the AOSP lane: build the APK outside Soong (platform test key) and install it over the image's.
device/anybook/common/quire/tools/build-apk.sh                       # -> /tmp/quire-dev-apk/OpenBookQuire.apk
adb -s SERIAL install -r -d /tmp/quire-dev-apk/OpenBookQuire.apk
# Every design state in light and dark next to the design renders, keyboard, labels, Remove animations, frames, health.
# The checks start scripts/quire/q5-acp-agent.py (scripted ACP agents) on this host and `adb reverse` to them.
scripts/quire/q5-cf-check.py SERIAL OUT --design <renders>     # <renders>/png/ from scripts/quire/render-design.sh
scripts/quire/q5-cf-check.py SERIAL OUT --only states --themes dark --states control,stopped   # a subset
scripts/quire/q5-cf-check.py SERIAL OUT --desk none ...          # nothing behind the note (Settings and Files hide it)
# Safety regressions: protected windows, the consent dialog at 1920x1080 and 1280x800, two agents with colliding
# session IDs, the payload an agent receives. Needs the image's QuireSecureProbe.apk.
scripts/quire/q5-safety-check.py SERIAL OUT --probe QuireSecureProbe.apk
# Icons: cut Material Symbols to the note's set (fonts/README.md)
device/anybook/common/quire/tools/subset-icons.py MaterialSymbolsRounded.ttf \
  device/anybook/common/quire/app/res/font/quire_symbols.ttf device/anybook/common/quire/app/src/dev/openbook/quire/note/Icons.kt
```

- The halo and the pointer for contextual search are frameworks/base `0008` (SystemUI), which `aosp-build.sh` applies
  with the others.
- The note's lab commands (`note/LabReceiver.kt`) work on debuggable builds only, from root or the system.

The Linux environment and `quired serve` (Q4, ANAL-218):

```bash
(cd quire/quired && go test -race ./...)                       # quired, serve included
quire/linux-env/build-deb.sh OUT [amd64|arm64]                  # quired_<version>_<arch>.deb
# The Debian guest, with AOSP's builder from the pinned tree (privileged Docker, ~3 min warm, ~10 GB):
scripts/quire/linux-env-image.sh OUT [--test-agent opencode]   # OUT/images.tar.gz, image-info.txt, kernel_config
scripts/quire/linux-env-qemu.sh OUT/images.tar.gz RUN [--prompt opencode "Reply with exactly: QUIRE OK"]
# On a private Cuttlefish copy, booted with CF_ARGS="--vhost_user_vsock=true --data_policy=always_create --blank_data_image_mb=16384":
scripts/quire/q4-cf-check.py SERIAL RUN --image OUT/images.tar.gz        # facts, off, install, guest, prompt, refuse
# No KVM: the same boot with CF_ARGS+=" --extra_kernel_cmdline=initcall_blacklist=svm_init", then
scripts/quire/q4-cf-check.py SERIAL RUN --image OUT/images.tar.gz --only nokvm,health
# An installed system over adb (on Cuttlefish add Q4_WIFI=VirtWifi):
scripts/quire/linux-env-adb.sh -s SERIAL preflight
scripts/quire/linux-env-adb.sh -s SERIAL check OUT/images.tar.gz RUN
# On the device itself: adb push or the stick, then as root
sh q4-device-check.sh /sdcard/linux/images.tar.gz /data/local/tmp/q4 [PROMPT]
```

Quire setup (ANAL-393, `docs/quire-setup.md`):

```bash
device/anybook/common/quire/tools/unit-test.sh                          # SetupModel with the other host tests
device/anybook/common/linux-env/tests/image-archive-test.sh TREE       # patch 0003's install classes (TREE: patched Virtualization)
scripts/quire/linux-env-qemu.sh OUT/images.tar.gz RUN --setup          # the admin worker and an install, real services
scripts/quire/setup-walk.py SERIAL RUN --image OUT/images.tar.gz       # the wizard in Cuttlefish, every page
scripts/quire/linux-env-sources.py OUT BUNDLE --fetch                  # a release's source bundle for the guest image
scripts/quire/linux-env-sources.py --check OUT BUNDLE                  # make-release.sh --linux-env runs this
```

- `scripts/aosp-build.sh` builds the `quired` package that Quire core carries (`/system_ext/etc/quire/quired.deb`) from
  `quire/` before Soong runs, into the gitignored `device/anybook/common/quire/prebuilt/`.
- The image a build installs is named by `device/anybook/common/linux-env/linux-env.json`; the release fills its URL
  and SHA-256. With no URL, the wizard says the build has no image yet.

- AVF comes from `device/anybook/common/linux-env/linux-env.mk` (both products, through `desktop.mk`); the Terminal
  app's agent bridge is `aosp/patches/packages/modules/Virtualization/0001` (`aosp-build.sh` applies it).
- The image builder runs as root in a privileged container and uses loop devices. A desktop automounter (udiskie, for
  example) mounts them on the host; the script unmounts the build's own while it runs
  (`tests/quire/unmount-build-loops-test.sh` tests that selection).
- Why each piece: `quire.md` §4.1, §5.4; pairing a second computer is a design under review
  ([`quire-pairing.md`](quire-pairing.md)).

## Reference: Googlebook OS and the AOSP Desktop emulator (M0)

Tools for studying Google's own images. They download Google's files to `~/anybook/dl/` for local analysis only;
nothing from them is committed or redistributed.

**The AOSP Desktop emulator baseline:**

```bash
scripts/m0-emulator.sh            # downloads (sha1-verified) emulator + "AOSP Desktop (Preview)" 37.0 x86_64, boots headless, captures
```

The output goes to `~/anybook/evidence/m0-emulator/` (or the directory given): `boot-result.txt`, `props.txt`, two
screenshots, logcat and dmesg. The ARM harness and the Mesa smoke test reuse this AVD.

**The Googlebook OS image, then static analysis:**

```bash
scripts/fetch-gbos-recovery.sh ruby                  # downloads + md5-verifies against Google's manifest
docker run --rm -u $(id -u):$(id -g) -v $HOME/anybook:/a anybook-inspect \
  /a/repo/scripts/gbos-unpack.sh /a/dl/gbos-ruby/android-desktop_signed_recovery_image.bin /a/work/gbos-ruby
docker run --rm -u $(id -u):$(id -g) -v $HOME/anybook:/a anybook-inspect \
  python3 /a/repo/scripts/isa-scan.py /a/logs/isa-scan-ruby.json \
  /a/work/gbos-ruby/fs /a/work/gbos-ruby/ramdisks
```

`isa-scan.py` lists instructions from extensions Zen 4 lacks: AVX-VNNI, AVX-IFMA, AVX-VNNI-INT8/16, AMX, CMPCCXADD,
APX and others. For each one it notes whether Zen 5 adds it. The APX regex also matches register names, so check any
APX hit by hand.

**Google's kernel and init on this CPU:**

```bash
docker run --rm -u $(id -u):$(id -g) --device /dev/kvm -v $HOME/anybook:/a anybook-qemu \
  /a/repo/scripts/gbos-qemu-boot.sh /a/work/gbos-ruby /a/dl/gbos-ruby/android-desktop_signed_recovery_image.bin \
  /a/logs/gbos-boot/zen4-kvm.log kvm 150
```

- It loads the stock `boot_a` kernel.
- The initrd is the vendor PLATFORM ramdisk, then the vendor DLKM ramdisk, then the generic ramdisk, followed by a
  bootconfig trailer (`androidboot.*`, slot `_a`, orange state).
- The recovery image is attached as an NVMe disk at PCI `00:04.0` with `snapshot=on`, so the image is never modified.
- Use `tcg` instead of `kvm` to run on QEMU's emulated `max` CPU.
