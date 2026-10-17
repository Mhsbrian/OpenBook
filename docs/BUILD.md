# Build and reproduce

Everything here runs without host sudo. The tools that Arch's base system doesn't provide run in Docker containers. You need `/dev/kvm` accessible and your user in the `docker` group.

## Layout (outside the repo; images are never committed)

```
~/anybook/
  repo/                 this repository
  dl/                   downloads (recovery zips, SDK zips) — proprietary, local only
  work/<codename>/      unpacked images (gbos-unpack.sh output)
  android-sdk/, avd/    emulator SDK + AVD (m0-emulator.sh)
  evidence/             raw logs before curation into repo/evidence/
```

Disk use for M0 is about 60 GB: 27 GB of downloads, 27 GB unpacked, 6 GB SDK. A full AOSP mirror plus a build adds about 600 GB. Plan for 32+ threads and 64 GB of RAM.

## Toolbox containers

```bash
docker build -t anybook-inspect -f tools/Dockerfile.inspect tools/   # android-tools, erofs-utils, binutils, elfx86exts
docker build -t anybook-qemu    -f tools/Dockerfile.qemu    tools/   # qemu 11.x + OVMF
docker build -t openbook-installer -f tools/Dockerfile.installer tools/  # qemu + OVMF, GRUB, systemd-boot/ukify, mtools, gptfdisk
```

## M0-A: AOSP Desktop emulator baseline

```bash
scripts/m0-emulator.sh            # downloads (sha1-verified) emulator + "AOSP Desktop (Preview)" 37.0 x86_64, boots headless, captures evidence
```

The output goes to `~/anybook/evidence/m0-emulator/`: `boot-result.txt`, `props.txt`, two screenshots, logcat and dmesg.

## M0-B: Googlebook OS image, then static analysis

```bash
scripts/fetch-gbos-recovery.sh ruby                  # downloads + md5-verifies against Google's manifest
docker run --rm -u $(id -u):$(id -g) -v $HOME/anybook:/a anybook-inspect \
  /a/repo/scripts/gbos-unpack.sh /a/dl/gbos-ruby/android-desktop_signed_recovery_image.bin /a/work/gbos-ruby
docker run --rm -u $(id -u):$(id -g) -v $HOME/anybook:/a anybook-inspect \
  python3 /a/repo/scripts/isa-scan.py /a/evidence/isa-scan-ruby.json \
  /a/work/gbos-ruby/fs /a/work/gbos-ruby/ramdisks
```

`isa-scan.py` lists instructions from extensions Zen 4 lacks: AVX-VNNI, AVX-IFMA, AVX-VNNI-INT8/16, AMX, CMPCCXADD, APX and others. For each one it notes whether Zen 5 adds it. Note that the APX regex also matches register names, so check any APX hit by hand.

## M0-C: run Google's kernel and init on this CPU

```bash
docker run --rm -u $(id -u):$(id -g) --device /dev/kvm -v $HOME/anybook:/a anybook-qemu \
  /a/repo/scripts/gbos-qemu-boot.sh /a/work/gbos-ruby /a/dl/gbos-ruby/android-desktop_signed_recovery_image.bin \
  /a/evidence/gbos-boot/zen4-kvm.log kvm 150
```

The script works like this:
- It loads the stock `boot_a` kernel.
- The initrd is the vendor PLATFORM ramdisk, then the vendor DLKM ramdisk, then the generic ramdisk, followed by a bootconfig trailer (`androidboot.*`, slot `_a`, orange state).
- The recovery image is attached as an NVMe disk at PCI `00:04.0` with `snapshot=on`, so the image is never modified.
- Use `tcg` instead of `kvm` to run on QEMU's emulated `max` CPU.

## ARM-compat harness and libndk_translation baseline (ANAL-180)

```bash
scripts/compat/build-probes.sh         # NDK r30 toolchain (sha1-verified) + probe APKs + CoreMark, in the anybook-ndk container
scripts/compat/fetch-corpus.sh         # F-Droid corpus, sha256-pinned in scripts/compat/corpus/fdroid.tsv
scripts/compat/run-matrix.sh --fresh   # emulator on port 5580: install, launch, wait 15 s, check, screenshot, CSV
scripts/compat/run-bench.sh            # CoreMark arm64 (translated) vs x86_64 (native)
```

`scripts/compat/emulator.sh` boots the M0 AVD with guest Vulkan: it passes `-feature Vulkan` and sets `hw.gltransport=virtio-gpu`. Details are in `docs/compat-harness.md`.

## M1b prep: AOSP 17 build container and source tree (Track A)

Details, the mirror decision and measurements are in `docs/aosp-build.md`; evidence is in `evidence/2026-10-15-aosp/`.

```bash
docker build -t anybook-aosp -f tools/Dockerfile.aosp --build-arg UID=$(id -u) --build-arg GID=$(id -g) tools/
scripts/aosp-docker.sh bash -c 'ccache -M 100G && ccache --set-config=compiler_check=content'   # ~/anybook/ccache
scripts/aosp-docker.sh -d anybook-aosp-sync /repo/scripts/aosp-sync.sh all && docker wait anybook-aosp-sync
scripts/aosp-docker.sh /repo/scripts/aosp-verify.sh aosp_cf_x86_64_pc-cp2a-userdebug   # lunch + m nothing
```

- `~/anybook/aosp/mirror` is a full-history mirror of the 975 source projects (102 GB).
- `~/anybook/aosp/src` is the `android-latest-release` tree (128 GB, plus `out/`). It borrows source objects from the mirror; the 112 prebuilt projects are shallow.
- The first sync took about 47 minutes on this host. Re-running resumes, or is a no-op.
- Use `cp2a`, not `trunk_staging`, for an Android 17 (`REL`) build. `trunk_staging` on this branch reports `PLATFORM_VERSION=Baklava`.
## Mesa radeonsi + RADV for Android x86_64

```bash
docker build -t anybook-mesa-android -f tools/Dockerfile.mesa-android tools/   # NDK r30 LTS, meson 1.12.1
scripts/mesa-android-build.sh            # fetch deps setup build install verify isa, trees: upstream ag; resumable
scripts/mesa-android-smoke.sh            # load test on the AOSP Desktop emulator (own AVD, port 5590)
```

Artifacts go to `~/anybook/mesa/out/<tree>/vendor/` and logs to `~/anybook/logs/mesa/`. See `docs/mesa.md`.
## Kernel: android17-6.18 GKI with Kleaf

```bash
scripts/kernel-sync.sh            # exact Googlebook kernel sources (manifests/kernel/gbos-16302624.xml) -> ~/anybook/kernel/src
scripts/kernel-build.sh           # tools/bazel run --config=stamp //common:kernel_x86_64_dist -> ~/anybook/kernel/dist/<target>
```

The scripts run in `tools/Dockerfile.kernel` (Ubuntu 24.04) through `scripts/kernel-docker.sh`. Plan for 53 GB of sources, 9 GB of Bazel cache and about 6 min per build on 32 threads. Comparison, config-diff and boot-test tools are covered in `docs/kernel.md`.

AMD vendor modules (ANAL-171), on top of the same tree:

```bash
scripts/kernel-amd-apply.sh       # kernel/patches/common -> common commits, kernel/devices/anybook -> //devices/anybook
KERNEL_TARGET=//devices/anybook:anybook_amd_x86_64_dist scripts/kernel-build.sh anybook-amd-gbos-16302624
```

The checks (config, modules, symbol list, QEMU load test, equivalence build, firmware subset) are in `docs/kernel.md`.

## M1b: build aosp_cf_x86_64_pc and boot it in Cuttlefish (ANAL-168)

```bash
AOSP_JOBS=32 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh aosp_cf_x86_64_pc-cp2a-userdebug
docker wait anybook-aosp-build          # ~2 h 10 min cold on the shared host; re-running resumes
scripts/cf-boot.sh                      # Cuttlefish container: launch, wait for boot_completed, capture, tear down (~45 s)
```

- Plan for about 41 GiB of RAM plus swap, 137 GB for `out/` (165 GB with `dist`), and 10 GB of ccache.
- Cuttlefish runs in `cuttlefish-orchestration:1.56.0` (pinned by digest) with `--cap-add NET_ADMIN`, `seccomp=unconfined`, and `/dev/kvm`, `/dev/net/tun`, `/dev/vhost-net` and `/dev/vhost-vsock`.
- Images are staged as reflink copies in `~/anybook/aosp/cf/product`; `out/` is never modified.
- See `docs/aosp-build.md` (M1b).

## Kernel in Cuttlefish: OpenBook kernel + our AOSP 17 userspace (ANAL-172)

Needs the ANAL-171 dist and the ANAL-168 build (`~/anybook/aosp/src/out`, read only).

```bash
KERNEL_TARGET=//common-modules/virtual-device:virtual_device_x86_64_dist scripts/kernel-build.sh anybook-vdev-gbos-16302624   # 6 min, once
scripts/kernel-cf-boot.sh          # OpenBook module set; `board` for the control. About 1.5 min per boot
```

- Uses its own container (`anybook-cf-kernel`), ports (adb 16572, WebRTC 11472) and vsock CID 172, so it can run next to `scripts/cf-boot.sh`.
- Disk: 4.1 GB of reflinks for the snapshot, plus 3.3 GB per staged boot, in `~/anybook/kernel/cf/`.
- See `docs/kernel.md` (ANAL-172).

## Kernel: G14 bare-metal packaging (ANAL-198)

Needs the synced kernel tree (above) and, for the boot check, a Cuttlefish `PRODUCT_OUT` to borrow the userspace from (default: ANAL-172's snapshot, read only).

```bash
scripts/kernel-g14-package.sh --evidence evidence/<date>-kernel-g14   # apply, Kleaf images, list/signing checks, firmware, QEMU, collect
```

- Resumable: finished steps are skipped while their inputs are unchanged; `--from STEP` reruns from STEP.
- Outputs in `~/anybook/kernel/g14/<label>/`: `images/` (`vendor_boot.img`, `vendor_dlkm.img`, `system_dlkm.img`, `bzImage`, `vm/`), `firmware/` (`/vendor/firmware` tree and `firmware.mk`), `qemu/` and `results.json`.
- Disk: about 0.6 GB per dist, 50 MB of staged firmware and 9 GB of sparse QEMU disks. The QEMU runs use 6 GiB of RAM each, one at a time.
- See `docs/kernel.md` (ANAL-198).

## ARM compat: Digitalis native bridge (ANAL-181)

```bash
scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/sync.sh       # AOSP 16 + Digitalis -> ~/anybook/digitalis/aosp16 (115 GB, ~53 min)
DIGITALIS_JOBS=16 scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/build.sh modules   # 70 bridge modules (44 min) -> ~/anybook/digitalis/bundle
scripts/compat/digitalis/install.sh -o evidence/<date>-digitalis               # overlay onto AVD anybook-digitalis (port 5580)
COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system scripts/compat/run-matrix.sh -o <dir> --keep-emulator
```

- The tree borrows source objects from the shared AOSP mirror, which is mounted read-only. It has its own ccache in `~/anybook/digitalis/ccache`.
- `install.sh` wipes and reinstalls every time, because a data wipe drops the overlay. The libndk_translation AVD `anybook-desktop` is never modified.
- Details and results are in `docs/digitalis.md`.

## M2: OpenBook desktop product and host-GPU Cuttlefish (ANAL-169)

```bash
docker build -t anybook-cuttlefish -f tools/Dockerfile.cuttlefish tools/     # pinned Cuttlefish image + Mesa Vulkan
AOSP_JOBS=32 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug
docker wait anybook-aosp-build          # copies device/anybook into the tree; 13–25 min incremental on top of M1b
CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_DEVICE=anybook_vsoc_x86_64 scripts/cf-boot.sh   # Radeon iGPU; CF_GPU=nvidia also works
# (CF_DEVICE since ANAL-174: the product's images are in out/target/product/anybook_vsoc_x86_64)
```

- `scripts/desktop-capture.sh` captures the screenshots and windowing/SurfaceFlinger dumps.
- `scripts/desktop-ref-emulator.sh` runs the same capture on Google's desktop emulator image.
- `scripts/desktop-compare.py` diffs the two captures, and `scripts/cf-gfx-bench.sh` compares GPU modes.
- See `docs/aosp-desktop.md`.

## M8: live USB image (ANAL-190)

```bash
scripts/installer-image.sh --menu-timeout 10      # live image from out/target/product/anybook_g14 -> ~/anybook/installer/out/
scripts/installer/live-qemu.sh ~/anybook/installer/out/<label>.img <run>   # QEMU/OVMF: grow, persist, reset, logs, decoy NVMe
```
Writing a stick: `scripts/installer/write-stick.sh` with `OPENBOOK_WRITE_CONFIRM=/dev/disk/by-id/usb-…` (owner confirmation). Details: `docs/installer.md` §11.

## M8: installer boot-chain prototype (ANAL-189)

```bash
scripts/installer/snapshot-inputs.sh cf-pc-20261016        # reflink snapshot of PRODUCT_OUT + kernel dist (read-only use)
scripts/installer/proto-matrix.sh cf-pc-20261016 matrix-20261016-openbook   # GRUB, systemd-boot, UKI, GBL; USB stick + decoy NVMe
scripts/installer/render-design.sh                         # installer design PNGs from docs/installer-design/index.html
```

- Builds GPT "USB stick" images from image files (no root, no real disk) and boots them in QEMU/KVM + OVMF.
- The GBL variants need `gbl_x86_64_dev.efi` from ci.android.com (see `docs/installer.md` §9).
- Logs are in `~/anybook/logs/installer/<run>/`. The design and results are in `docs/installer.md`.

## AMD graphics in the device tree (ANAL-174)

```bash
scripts/mesa-android-build.sh fetch deps setup build install verify -- upstream   # LIBELF=shared, ANDROID_STRICT=true by default; applies mesa/patches/upstream
scripts/graphics-amd-stage-mesa.sh              # Mesa prebuilts -> ~/anybook/aosp/src/vendor/anybook/mesa (never committed)
AOSP_JOBS=24 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug
docker wait anybook-aosp-build                  # also applies aosp/patches/* (scripts/aosp-patches.sh)
scripts/amd-android-hwtest.sh                   # the image's RADV/radeonsi/minigbm on this host's AMD GPU
scripts/minigbm-amdgpu-host-test.sh             # minigbm amdgpu backend, Linux build, same GPU
```

- Without the staged Mesa, `graphics-amd.mk` stops the build with a message that names the two scripts above.
- `scripts/aosp-patches.sh` applies OpenBook's AOSP patches on top of each project's pinned revision (`evidence/2026-10-15-aosp/manifest-pinned.xml.gz`). It is idempotent, and `--export PROJECT` writes edited commits back.
- See `docs/graphics-amd.md`.

## Bare metal: the OpenBook G14 product (ANAL-199)

```bash
scripts/g14-stage-kernel.sh                                   # ANAL-198's dist -> <AOSP>/vendor/anybook/g14-kernel
scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug && docker wait anybook-aosp-build
scripts/g14-image.sh --xz                                     # USB GPT image in <data dir>/installer/out/
scripts/g14-qemu.sh <img> <run> && scripts/g14-qemu.sh --again <run>   # two boots in QEMU/OVMF from USB
```
Details: `docs/g14-product.md`.
