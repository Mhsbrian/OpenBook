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
