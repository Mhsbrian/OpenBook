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

## ARM-compat harness and libndk_translation baseline (ANAL-180)

```bash
scripts/compat/build-probes.sh         # NDK r30 toolchain (sha1-verified) + probe APKs + CoreMark, in the anybook-ndk container
scripts/compat/fetch-corpus.sh         # F-Droid corpus, sha256-pinned in scripts/compat/corpus/fdroid.tsv
scripts/compat/run-matrix.sh --fresh   # emulator on port 5580: install, launch, wait 15 s, check, screenshot, CSV
scripts/compat/run-bench.sh            # CoreMark arm64 (translated) vs x86_64 (native)
```

`scripts/compat/emulator.sh` boots the M0 AVD with guest Vulkan: it passes `-feature Vulkan` and sets `hw.gltransport=virtio-gpu`. Details are in `docs/compat-harness.md`.

