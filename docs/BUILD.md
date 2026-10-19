# Build and reproduce

## Local Ruby/OpenBook integration probe (ANAL-228, 2026-10-19)

`docs/googlebook-bringup.md` documents `scripts/googlebook/compat-audit.py` and
`hybrid-probe.py`. They use an existing G14 product/kernel build and retained
Ruby extraction, audit VINTF/APEX/kernel/policy, then assemble a disposable VM
image. The installer container mounts sources read-only and passes only KVM.
Outputs contain local recovery-derived material and are not release artifacts.
The measured probe reaches zygote but fails on AVX-VNNI instructions on the
7950X host; read the evidence before interpreting a successful script exit.

## Googlebook image-base groundwork (ANAL-228, 2026-10-19)

See `docs/googlebook-image-base.md` for the pinned GBRUNCH review and remaining
boot/integration gates. No Google recovery is needed for these checks:

```sh
python3 scripts/installer/recovery-preflight-test.py -v
OUT=/tmp/ob228-app device/anybook/common/installer/app/tools/compile-check.sh
scripts/installer/engine-host-build.sh "$HOME/anybook/installer/build/ob228/openbook-install"
scripts/installer/inst-docker.sh python3 "$PWD/scripts/installer/image-base-test.py" \
  --engine "$HOME/anybook/installer/build/ob228/openbook-install" \
  --image /path/to/existing-openbook-live.img \
  --run "$HOME/anybook/installer/work/ob228-new-run"
```

The run directory must be new. The test copies the live image and uses a sparse
file target. `image-base-qemu.py` similarly takes `--image`, a newly built
`--apk` and a new `--run` directory under `installer/qemu/`, and checks the actual
chooser in QEMU with the existing image's daemon. It never installs to the target.
The host fixture suite tests the changed daemon separately.

For a recovery you have permission to use, run
`python3 scripts/installer/recovery-preflight.py --raw /path/to/recovery.bin`
(or `--zip`). Redirect stdout to a **different** report file if desired. Exit 0
means byte identity matched, not installation approval. It opens only a regular
file read-only and does not download, mount, extract or execute recovery content.
The source is about 19.1 GB raw; streaming hashing uses bounded memory. A future
local assembly needs space for both the retained recovery and separate output,
kernel/AOSP artifacts and scratch storage; this phase does not size or build it.

## G14 touchpad diagnostic replay (ANAL-226, 2026-10-19)

`scripts/power/touchpad/build-replay.sh` builds an isolated host copy of the
bundled gestures library and an offline event replay; it does not use the AOSP
build lane or write the laptop. Commands, dependencies and limitations are in
`docs/touchpad-behavior.md`. Eight synthetic control checks pass. Physical
reproduction and a libinput runtime comparison remain required before an image
change; no touchpad update image has been built.

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

- The AOSP tree and `out/` are shared between lanes, so builds run under the lane lock `~/anybook/aosp/.lane.lock`. `aosp-docker.sh` takes it for `aosp-build.sh` and `aosp-sync.sh` (any command with `ANYBOOK_LANE=1`): it waits for whoever holds it and keeps it until the container exits, `-d` included. A caller that already holds it with `flock <lock> …` is recognised; one holding it through an inherited fd sets `ANYBOOK_LANE_LOCK_HELD=1`. Started any other way, `aosp-build.sh` refuses. `installer-image.sh` holds the lock while it snapshots `PRODUCT_OUT`. `ANYBOOK_LANE_UNLOCKED=1` for a tree of your own. Test: `scripts/aosp-lane-test.sh`.
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

## ARM compat: Digitalis as our built-in bridge on Android 17 (ANAL-200)

The bridge is part of both products. `scripts/aosp-patches.sh` (which `aosp-build.sh` runs) imports the fork into `frameworks/libs/binary_translation` from `aosp/patches/frameworks/libs/binary_translation/IMPORT` and applies our patches, plus the ART patch in `aosp/patches/art/`.

```bash
scripts/aosp-docker.sh /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug droid berberis_arm64_host_tests
scripts/aosp-docker.sh bash -c 'cd /aosp/src/out/host/linux-x86/nativetest64/berberis_arm64_host_tests && ./berberis_arm64_host_tests --gtest_brief=1'
COMPAT_TARGET=cf scripts/compat/run-matrix.sh -o <dir>        # our Cuttlefish build (scripts/compat/cf.sh up|down|status)
COMPAT_TARGET=cf scripts/compat/run-bench.sh -o <dir>
scripts/compat/digitalis/fp-estimate.sh build && scripts/compat/digitalis/fp-estimate.sh reference
COMPAT_TARGET=cf scripts/compat/digitalis/fp-estimate.sh device -o <dir>   # FRECPE/FRSQRTE vs QEMU, every tier
python3 -I scripts/compat/digitalis/audit-shipped.py out/target/product/<device> <dir>   # what ships, licenses
scripts/compat/digitalis/bundle.sh && scripts/compat/digitalis/install.sh ~/anybook/digitalis/bundle-a17   # A17 bridge on the emulator AVD
```

- Adding the bridge to an existing `out/` took 11 min 35 s at `-j28`, and the container's memory peaked at 57.7 GB.
- On a device or the live image, `su 0 openbook-hwtest bridge` checks it (`docs/digitalis.md`, "On the G14").

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
scripts/graphics/refresh-qemu.sh ~/anybook/installer/out/<label>.img <run>  # refresh rate: render cap, render rate while scrolling (ANAL-212)
```
Writing a stick: `scripts/installer/write-stick.sh` with `OPENBOOK_WRITE_CONFIRM=/dev/disk/by-id/usb-…` (owner confirmation). Details: `docs/installer.md` §11.

## M8: installer wizard and install engine (ANAL-191)

The wizard (`OpenBookInstaller`), the engine (`openbook-install`) and its daemon are part of the G14 product (`device/anybook/common/installer/`), so the product build and `scripts/installer-image.sh` above include them.

```bash
device/anybook/common/installer/app/tools/compile-check.sh        # the app's Kotlin, with the in-tree kotlinc (no Soong)
scripts/installer/engine-test.sh ~/anybook/installer/out/<label>.img <run>    # engine host tests on image files, ~3 min
scripts/installer/wizard-qemu.sh ~/anybook/installer/out/<label>.img <run>    # dryrun, install, installed, console in QEMU
```
- `engine-test.sh` builds the engine with gcc in the installer container and runs it on a fixture sysfs with image files. It covers refusals, a whole-disk install and an install alongside a Windows-like disk, checked with `sgdisk`, `fsck.fat`, mtools and `lpdump`.
- `wizard-qemu.sh` drives the app with `uiautomator` and `input` over the serial console. Extra cases for firmware boot entries: `nvram-boot` (after `install`), then `alongside`, `alongside-default` and `alongside-boot` in that order (`docs/installer.md` §12.11). The Windows-like disk's boot manager is a small EFI app (`scripts/installer/efi-standin.c`) built with AOSP's prebuilt clang and lld (`OPENBOOK_EFI_CLANG` to override). It saves Android's screenshots to the stick's ESP (`openbook/shots/`), installs to a blank 64 GiB virtual NVMe disk, and boots that disk alone.
- Results go to `~/anybook/logs/installer/<run>/` (`results.json`, `SUMMARY.md`). Details: `docs/installer.md` §12.

## M8: installer end to end and the integrated owner stick (ANAL-192)

```bash
scripts/installer/e2e-qemu.sh ~/anybook/installer/out/<label>.img <run> all     # or the cases in groups, each call under 10 min
python3 scripts/installer/e2e-qemu.py avc OUT <logcat.gz and sections/avc.txt files>   # SELinux denials, grouped
```
- `e2e-qemu.sh` covers alongside a Windows-like disk, a small disk, power cuts at every install step with restarts, the installed disk with and without the stick, and a reinstall. It builds its own test EFI apps (`scripts/installer/e2e/obtest-efi.c`) with the container's gcc and PE linker. Image files only, about 25 minutes.
- The integrated stick (installer plus the check add-ons, built from a clean `main` checkout) and its full test set are in `docs/installer.md` §13.9. Keep a reflink copy of the image before the add-ons go on: the add-on QEMU tests apply their add-on to it.
- The user guide and the release checklist draft: `docs/INSTALL.md`.

## Google services compatibility: the microG add-on (ANAL-210)

The framework patch (`aosp/patches/frameworks/base/0002`–`0004`; `0001` is B7's fonts.xml) is applied by `scripts/aosp-patches.sh` in every build. `openbook-addons` and its catalogue (`device/anybook/common/addons/`) are part of the PC products. The APKs are microG's own release files, fetched and checked here, never committed.

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
- Cuttlefish tests use the VM's own Wi-Fi for internet: `cmd wifi set-wifi-enabled enabled; cmd wifi connect-network VirtWifi open`.
- On Cuttlefish (no OpenBook ESP), `openbook-addons` runs from an NDK build with `--from-dir`. The command is in `evidence/2026-10-17-microg/SUMMARY.md`.
- Before anything leaves the VM, `scripts/microg/redact.sh` removes FCM, MCS and check-in tokens and device IDs from the logs.
- Details: `docs/gapps.md` §6 and `docs/installer.md` §14.

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

## Bare metal: debugging the installed G14 over adb (ANAL-222)

```bash
scripts/g14-adb.sh find && scripts/g14-adb.sh connect     # mDNS finds "OpenBook on ..."; or OPENBOOK_G14_ADDR=<ip>
scripts/g14-adb.sh capture [--hwtest] [--bugreport] [--redact OUT] [DEST]   # the "save logs" set, ~35 s
scripts/g14-adb.sh logcat -b all                           # follow; resumes after a dropped link
scripts/g14-adb.sh persist-logs on                         # keep logcat across boots (product default)
```
The G14 has no USB device mode, so adb is network-only, and it currently needs no authorization (`docs/adb-debug.md` §5). Details: `docs/adb-debug.md`.

## Bare metal: audio, Wi-Fi and Bluetooth on the G14 (ANAL-179)

```bash
# In one lane-lock hold (other branches build in the same tree): build, then snapshot PRODUCT_OUT
flock ~/anybook/aosp/.lane.lock bash -c 'AOSP_JOBS=24 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh \
  anybook_g14_x86_64-cp2a-userdebug droid openbook_hals_test openbook_audio_logic_test validatekeymaps \
  out/soong/.intermediates/external/wpa_supplicant_8/hostapd/hostapd/android_vendor_x86_64_silvermont_cfi/hostapd \
  && docker wait anybook-aosp-build && scripts/audio-net-qemu.sh snapshot NAME'
scripts/g14-image.sh --label openbook-g14-NAME --product-out ~/anybook/audio-net/product/NAME
scripts/audio-net-qemu.sh payload                      # hwsim + hostapd + DHCP test disk for the guest
scripts/audio-net-qemu.sh run ~/anybook/installer/out/openbook-g14-NAME.img RUN   # HDA card + Wi-Fi AP in QEMU
scripts/installer-image.sh --product-out ~/anybook/audio-net/product/NAME --label openbook-live-<date>-<name> --menu-timeout 10
```
- `aosp-build.sh` applies both `aosp/patches/hardware/interfaces` patches (the audio HAL's card and pacing properties).
- Before a build that follows another branch's, give the tree's `device/anybook` the current time (`find ~/anybook/aosp/src/device/anybook -exec touch {} +`): outputs another branch copied from its own version of a file can otherwise look up to date.
- Details: `docs/g14-audio-net.md`.

## Power and input: the power check and laptop config (ANAL-178)
```bash
docker build -t openbook-installer:anal178 -f tools/Dockerfile.installer tools   # needs make for the test modules
export OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178
scripts/power/make-power-check.sh openbook-powercheck-anal178-a        # add-on for a live stick, ~1 min
scripts/power/power-check-qemu.sh openbook-powercheck-anal178-a vm     # QEMU: LPS0 fixture, s2idle, 14 steps
scripts/power/power-check-qemu.sh openbook-powercheck-anal178-a real   # QEMU: the entry as shipped
scripts/power/collect-qemu.sh a                                        # save-logs facts inside Android 17
scripts/power/touchpad/touchpad-qemu.sh RUN [LIVE_IMAGE]               # the G14 touchpad on uhid: repeat frames, clock errors
TP_MODE=palm scripts/power/touchpad/touchpad-qemu.sh RUN [LIVE_IMAGE]  # ... with palm lift-offs (or sticky: a 150 ms pause)
scripts/power/touchpad/touchpad-logs-qemu.sh RUN [LIVE_IMAGE]          # the save-logs boot's touchpad capture (TOUCHPADEV)
```
Owner steps (Linux comparison on the laptop, the add-on on the stick) and how to read the results: `docs/power-input.md`.


## Graphics conformance: dEQP and ANGLE end2end on the G14 (ANAL-177)
```bash
# test modules for the G14 product (AOSP lane, ~8 min incremental)
AOSP_JOBS=24 scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug \
  deqp-binary com.drawelements.deqp AngleEnd2EndTestsHelper && docker wait anybook-aosp-build
# Since ANAL-177 the default build is non-strict (Vulkan 1.4) and graphics-amd-stage-mesa.sh writes mesa.mk, so the
# image declares the version its RADV reports. A strict (1.1) build for comparison or fallback, in its own dirs:
MESA_VARIANT=-strict ANDROID_STRICT=true scripts/mesa-android-build.sh fetch setup build install verify -- upstream
# (the first G14 run's second RADV was MESA_VARIANT=-nonstrict ANDROID_STRICT=false, when the default was strict)
scripts/graphics/build-deqp-runner.sh                                   # Mesa's deqp-runner 0.23.2, static musl
scripts/graphics/mkcaselists.py ~/anybook/aosp/src/external/deqp/android/cts/main ~/anybook/gfx-cts/caselists/v1 \
  --angle-expectations ~/anybook/aosp/src/external/angle/android/cts/angle_end2end_tests_expectations.txt
scripts/graphics/pre-check.sh ~/anybook/gfx-cts/caselists/v1            # the lists on this host's AMD GPU (~4 min)
scripts/graphics/gfx-report.py ~/anybook/logs/gfx-cts/precheck-<ts> --mesa-ci ~/anybook/mesa/src/upstream/src/amd/ci \
  --radv-gpu raphael --radeonsi-gpu mendocino
scripts/graphics/make-gfx-check.sh openbook-gfxcheck-20261017           # add-on for a live stick (~30 s)
scripts/graphics/gfx-qemu.sh openbook-gfxcheck-20261017 quick1          # QEMU: the add-on end to end, 40 cases per list
```
Owner steps (add the check to the stick, run it, read the results): `docs/graphics-amd.md`, "dEQP and CTS on the G14".

## Document fonts: metric-compatible stand-ins for Windows fonts (ANAL-208)
```bash
# The fonts are committed (device/anybook/common/desktop/fonts/documents/, README.md has sources and sha256).
# After changing DOCS in scripts/ui/fonts-customization.py, regenerate both configs:
scripts/ui/fonts-customization.py > device/anybook/common/desktop/fonts/fonts_customization.xml   # framework
scripts/ui/fonts-legacy-patch.sh          # aosp/patches/frameworks/base: /system/etc/fonts.xml, for WebView
# Check in Cuttlefish (B7's ports), then compare with the fonts' own metrics:
scripts/ui/doc-fonts-check.sh 127.0.0.1:16537 OUT          # WebView: report.json, screen.png, cmd font dump
scripts/ui/doc-fonts-typeface.sh 127.0.0.1:16537 OUT/typeface.tsv   # the framework: Typeface + Paint
scripts/ui/doc-fonts-metrics.py --fonttools ~/anybook/aosp/src/external/fonttools/Lib --afm AFMDIR \
  --font arimo=.../Arimo-VF.ttf ... --report LABEL=OUT/report.json --typeface LABEL=OUT/typeface.tsv
```
- `aosp-build.sh` applies the `frameworks/base` patch (legacy `fonts.xml` only; the framework reads `font_fallback.xml`).
- Details: `docs/googlebook-ui.md` §2.1.1; evidence `evidence/2026-10-17-doc-fonts/`.

## Quire core: the agent layer's platform hooks (ANAL-216)
```bash
device/anybook/common/quire/tools/compile-check.sh   # Quire and its test helper, with the in-tree kotlinc (no Soong)
# Build the Cuttlefish product plus the test helper under the lane lock, snapshot it, boot it on the AMD lane:
#   evidence/2026-10-18-quire-q2/SUMMARY.md, "Reproduce"
scripts/quire/q2-cf-check.py SERIAL OUT --probe QuireSecureProbe.apk   # invocation, computer control, refusals, health
```
- Quire is in both products through `desktop.mk` (`device/anybook/common/quire/quire.mk`).
- It needs, besides its module: frameworks/base patches `0005`–`0007` and Launcher3 `0002` (`aosp-build.sh` applies them),
  four aconfig flags in `release/openbook/cp2a/`, and the build flag `RELEASE_PACKAGE_COMPUTER_CONTROL`
  (`release/flag_values/cp2a/`). Why: `docs/quire.md` §2.5.
- `q2-cf-check.py` drives Quire through its root-only `LabActivity` alias, so it needs a userdebug build and `adb root`.

### Quire's surface, the note (ANAL-219)
```bash
# Iterate on Quire without the AOSP lane: build the APK outside Soong (platform test key) and install it over the image's.
device/anybook/common/quire/tools/build-apk.sh                       # -> /tmp/quire-dev-apk/OpenBookQuire.apk
adb -s SERIAL install -r -d /tmp/quire-dev-apk/OpenBookQuire.apk
# The checks: every design state in light and dark next to Q3's renders, keyboard, labels, Remove animations, frames,
# health. They start scripts/quire/q5-acp-agent.py (scripted ACP agents) on this host and `adb reverse` to them.
scripts/quire/q5-cf-check.py SERIAL OUT --design PATH/TO/docs/quire-design     # PR #98's renders
scripts/quire/q5-cf-check.py SERIAL OUT --only states --themes dark --states control,stopped   # a subset
scripts/quire/q5-cf-check.py SERIAL OUT --desk none ...          # nothing behind the note (Settings and Files hide it)
# The safety regressions (ANAL-219, the Checker's three findings): protected windows, the consent dialog at 1920x1080 and
# 1280x800, two agents with colliding session IDs, the payload an agent receives. Needs the image's QuireSecureProbe.apk.
scripts/quire/q5-safety-check.py SERIAL OUT --probe QuireSecureProbe.apk
# Host tests for the parts with no Android types (SessionRoutes, IntakePolicy): the tree's kotlinc and JDK, no device.
device/anybook/common/quire/tools/unit-test.sh
# Icons: cut Material Symbols to the note's set (fonts/README.md)
device/anybook/common/quire/tools/subset-icons.py MaterialSymbolsRounded.ttf \
  device/anybook/common/quire/app/res/font/quire_symbols.ttf device/anybook/common/quire/app/src/dev/openbook/quire/note/Icons.kt
```
- The image build is unchanged (`droid`, Quire is in `desktop.mk`). The halo and the pointer for contextual search are
  frameworks/base `0008` (SystemUI), which `aosp-build.sh` applies with the others.
- The note's lab commands (`note/LabReceiver.kt`) work on debuggable builds only, from root or the system.

## Quire Q4: the Linux environment and quired serve (ANAL-218)
```bash
(cd quire/quired && go test -race ./...)                       # quired, serve included
quire/linux-env/build-deb.sh OUT [amd64|arm64]                  # quired_<version>_<arch>.deb
# The Debian guest, with AOSP's builder from the pinned tree (privileged Docker, ~3 min warm, ~10 GB):
scripts/quire/linux-env-image.sh OUT [--test-agent opencode]   # OUT/images.tar.gz, image-info.txt, kernel_config
scripts/quire/linux-env-qemu.sh OUT/images.tar.gz RUN [--prompt opencode "Reply with exactly: QUIRE OK"]
# Cuttlefish with AVF (the build and boot commands are in evidence/2026-10-18-quire-q4/SUMMARY.md, "Reproduce"):
scripts/quire/q4-cf-check.py SERIAL RUN --image OUT/images.tar.gz        # facts, off, install, guest, prompt, refuse
scripts/quire/q4-cf-check.py SERIAL RUN --image OUT/images.tar.gz --only nokvm,health   # a boot without KVM
# On the device itself (the G14 has no host): adb push or the stick, then as root
sh q4-device-check.sh /sdcard/linux/images.tar.gz /data/local/tmp/q4 [PROMPT]
```
- AVF comes from `device/anybook/common/linux-env/linux-env.mk` (both products, through `desktop.mk`); the Terminal
  app's agent bridge is `aosp/patches/packages/modules/Virtualization/0001` (`aosp-build.sh` applies it).
- The image builder runs as root in a privileged container and uses loop devices. A desktop automounter (udiskie
  here) mounts them on the host; the script unmounts the build's own while it runs.
- Why each piece: `docs/quire.md` §4.1, §5.4; pairing a second computer is a design under review
  (`docs/quire-pairing.md`).

### Quire tool confirmation regressions

```bash
python3 device/anybook/common/quire/tools/policy-test.py
```
Uses the AOSP JDK and Kotlin compiler with host boundary fakes; no device, model or network. `QUIRE_POLICY_SOURCE` can point at an older tools directory for a negative control.

## Headless video-buffer regression check (ANAL-210)

`scripts/graphics/ahb-import-check.c` tests RGB, YV12 and flexible YUV420 imports
through the installed EGL driver, including colour readback. It opens no window
and does not launch Photos. Build with the NDK (API 37):

```sh
x86_64-linux-android37-clang -O2 -Wall -Wextra -Werror \
  scripts/graphics/ahb-import-check.c -landroid -lEGL -lGLESv2 -o ahb-import-check
adb -s <device> push ahb-import-check /data/local/tmp/
adb -s <device> shell /data/local/tmp/ahb-import-check 384 640
```

Exit 0 means all three imports and pixel comparisons passed; 1 means a failed
case; 2 means setup/argument failure. Optional dimensions must be even, 4–4096.
Mesa patch 0005 is applied by `mesa-android-build.sh fetch`; rebuild and stage
Mesa before building the OS image. Evidence: `evidence/2026-10-19-photos-yv12/`.
