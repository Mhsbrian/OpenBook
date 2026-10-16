# Status

## 2026-10-15: M0 (research, dev host, baselines)

**Done**
- Researched Googlebook OS and prior art. Findings are in `docs/RESEARCH.md`, and the two-track plan with ranked blockers is in `docs/PLAN.md`.
- Downloaded Google's official recovery image for ruby (Lenovo Googlebook 15, Intel), build `16452207_CL3B.260622.271.R1`. The zip md5 `0567fe2ed0dd1c1753b383a6b3dbfe81` matches Google's manifest. The image is stored locally and never committed.
- Unpacked it without root: GPT, `super`, EROFS partitions, boot/init_boot/vendor_boot, ramdisks, and the kernel config.
- ISA scan: of 2,675 x86-64 ELF files, 79 contain instructions Zen 4 doesn't implement. 65 of those use AVX-VNNI, including `init`, `linker64`, `surfaceflinger` and `libhwui`.
- **Execution test:** booted Google's stock kernel and ramdisks in QEMU/KVM with `-cpu host` on a Ryzen 9 7950X (Zen 4):
  - First-stage mount works: dm-linear `super`, dm-verity using Google's hashtree, AVB in orange state.
  - Second-stage init starts about 30 services.
  - **0 SIGILL or invalid-opcode traps.**
  - Boot stalls at `keystore2` because KeyMint lives in the Trusty pKVM security VM and there is no GSC TPM. Zygote and the UI never start.
- Booted Google's AOSP Desktop (Preview) Android 17 emulator image headless under KVM:
  - `boot_completed` after 16 s.
  - The desktop taskbar is up and Settings and Files open in freeform windows.
  - `feature:android.hardware.type.pc` is present, and the native bridge is libndk_translation with `arm64-v8a` listed.

**Evidence** (in `evidence/2026-10-15-m0/`)
- `m0-emulator/screen-desktop.png`, `m0-emulator/screen-windows.png`, `props.txt`, `boot-result.txt`, `logcat.txt.gz`, `dmesg.txt.gz`
- `gbos-boot-zen4-kvm.log`: full serial log of the Googlebook kernel and init on Zen 4
- `isa-scan-ruby.json`: per-binary counts of instructions Zen 4 doesn't implement
- `gbos-kernel-config.txt`: the stock Googlebook GKI config

**Blocked / needs a decision**
- Target hardware: **ASUS ROG Zephyrus G14 (2025) GA403WP**, Ryzen AI 9 HX 370 (Zen 5, confirmed by the owner 2026-10-16) + RTX 5070. Component IDs still need `scripts/hw-inventory.sh` output from the laptop (ANAL-175). See `docs/HARDWARE.md`.
- ~~Merge PR #1.~~ Merged 2026-10-16.
- ~~Which repo receives this work.~~ Resolved: https://github.com/Mhsbrian/AnyBook (public, created 2026-10-15).
- License for the scripts and docs. Apache-2.0 is suggested, to match AOSP. Not chosen yet.
- Track B licensing: whether to proceed past research with Google's proprietary image (`docs/PLAN.md` §6).

**Next**
- M1a: software KeyMint/Gatekeeper/Weaver vendor overlay (GBRUNCH method), then boot Googlebook OS in QEMU/KVM to `boot_completed`.
- M1b: mirror and sync `android17-release`, then build `aosp_cf_x86_64_pc` and boot it in the Cuttlefish container.

## 2026-10-15: Graphics userspace, Mesa radeonsi + RADV for Android x86_64 (ANAL-173)

**Done**
- Built upstream Mesa 26.2.5 and Android-Generic `26.0/main` (26.0.8 + 63 commits), out-of-tree with NDK r30 at API 37 (`tools/Dockerfile.mesa-android`, `scripts/mesa-android-build.sh`). radeonsi uses ACO only, so no Android LLVM is needed. libelf comes from AOSP elfutils.
- Both trees: 0 unresolved NEEDED entries or symbols against the API 37 sysroot. `vulkan.radv.so` exports only `HMI`. Baseline ISA is x86-64 with SSE4.2; wider code is only behind runtime checks.
- Load test on the Android 17 emulator: the Vulkan HAL opens and `vkCreateInstance` succeeds with 0 devices (there's no GPU in the VM). EGL loads; `eglInitialize` fails because there's no DRM device. **Nothing has run on AMD hardware yet.**
- A clean rebuild is bit-identical. Details are in `docs/mesa.md`.

**Evidence:** `evidence/2026-10-15-mesa/`

**Blocked / needs a decision:** the static libelf is LGPL-3.0-or-later inside the MIT Mesa libraries. That's fine for local builds; binary redistribution needs a decision (`docs/mesa.md`).

**Next:** minigbm with an amdgpu/gbm_mesa backend so Mesa's `cros` gralloc path works, then SP-HAL SELinux labels, then a hardware run (M4).
## 2026-10-15: Kernel, stock android17-6.18 GKI reproduced with Kleaf (ANAL-170)

**Done**
- Googlebook OS ships the unmodified public GKI: the ruby `boot_a` kernel is byte-identical to ci.android.com build 16302624 (`kernel_x86_64`, branch `common-android17-6.18-2026-06`, `common` 3938c8d97142).
- Built it locally from that build's pinned manifest (`manifests/kernel/gbos-16302624.xml`) in 5 min 37 s. The `.config` and KMI CRCs are identical. Built with the same build number, `vmlinux` differs only in the per-build module-signing certificate and build ID (1,098 bytes).
- Config diff: 0 symbols. Google adds nothing beyond `gki_defconfig`. `PKVM_INTEL` is explicit in `gki_defconfig`; `X86_FRED` is selected by `KVM_INTEL` through an upstream Kconfig `select`.
- Our kernel boots on Zen 4 under KVM to the same `keystore2` stall as the stock kernel. Google's signed GKI modules (`rust_binder`, `zsmalloc`) are rejected, so `system_dlkm` must come from our build.
- The `android17-6.18` tip (6.18.32) also builds. The shipped KMI list is unchanged there.

**Evidence:** `evidence/2026-10-15-kernel/`. Details are in `docs/kernel.md`.

**Next:** an AMD defconfig fragment and an `anybook_amd` KMI symbol list on this tree, then boot with our `system_dlkm`.
**Next** (tracked in Multica as children of ANAL-159; ▶ marks issues running now)

| Epic | Stage 1 | Later stages |
|---|---|---|
| ANAL-160 Track A: AOSP 17 desktop boots in a VM | ▶ ANAL-167 build container and source mirror | ANAL-168 build `aosp_cf_x86_64_pc` and boot to adb → ANAL-169 VM graphics and desktop windowing |
| ANAL-161 AMD GKI kernel (android17-6.18) | ▶ ANAL-170 reproduce the stock GKI build and diff the config | ANAL-171 AMD config and modules → ANAL-172 QEMU boot test |
| ANAL-162 AMD graphics userspace | ▶ ANAL-173 Mesa radeonsi/RADV Android build | ANAL-174 device-tree integration → ANAL-177 dEQP/CTS on the target |
| ANAL-164 ARM compat and native bridge | ▶ ANAL-180 harness and libndk_translation baseline | ANAL-181 Digitalis evaluation |
| ANAL-163 Bare-metal bring-up on the G14 2025 (waiting for inventory output from the laptop) | ANAL-175 inventory | ANAL-176 USB boot → ANAL-178 input and power, ANAL-179 audio and Wi-Fi |
| ANAL-165 Track B: Googlebook OS on AMD (parked: licensing decision) | ANAL-182 VM boot to `boot_completed`, ANAL-183 Zen 4 ISA spike | ANAL-184 kernel swap → ANAL-185 graphics overlay |
| ANAL-166 Performance and parity (parked) | — | — |

## 2026-10-15: ARM compat harness and libndk_translation baseline (ANAL-180)

**Done**
- `scripts/compat/`: probe APKs (arm64-only, armv7-only, x86_64 control) with 19 test groups, a pinned F-Droid corpus (16 arm64-only apps plus 7 x86_64 controls), a resumable matrix runner and a CoreMark benchmark.
- **Apps:** 13 of 16 arm64-only F-Droid apps run under libndk_translation. Tor VPN (SIGILL on `mrs ID_AA64ISAR0_EL1`) and Element X fail only under translation; AAAAXY also fails natively.
- **No arm32:** armeabi-v7a does not install (the image is 64-bit only).
- **Speed:** translated arm64 runs at 0.457× native x86_64 (CoreMark, same emulator).
- **Probe findings:** seq_cst store→load ordering is broken (about 1% of store-buffering trials), NaN rules follow x86, `CNTVCT_EL0` runs about 429× fast, and `MRS` of ID registers is not emulated.

**Evidence:** `evidence/2026-10-15-compat/` (2 runs with identical outcomes, screenshots, logs, `bench/`, `analysis/`).

**Next:** the same corpus under houdini (after M1a) and Digitalis/Berberis (after M1b); root-cause Element X.
## 2026-10-16: M1b prep, AOSP 17 build environment (ANAL-167, Track A)

**Done**
- `tools/Dockerfile.aosp`: Ubuntu 24.04, running as the host uid/gid.
- Synced `android-latest-release` (manifest `ad156f32`, `android17-release`) to `~/anybook/aosp`:
  - A full-history mirror of the 975 source projects: 102 GB, 32 min.
  - A build tree with shallow prebuilts: 128 GB, 15 min.
  - A full mirror of this manifest would be 748 GB, 87% of it prebuilt history (measured).
- ccache is set to 100 GB through `CC_WRAPPER`.
- `lunch aosp_cf_x86_64_pc-trunk_staging-userdebug` and `m nothing` succeed with the Soong nsjail sandbox enabled: 1:20 wall clock, 39 GiB peak RSS.

**Evidence:** `evidence/2026-10-15-aosp/` (sync logs, pinned manifest, `repo info`, lunch, `m nothing` logs and timings, sizes).

**Findings**
- `trunk_staging` on `android17-release` builds as `PLATFORM_VERSION=Baklava`. `cp2a` gives `PLATFORM_VERSION=17` (`REL`), so M1b should build `aosp_cf_x86_64_pc-cp2a-userdebug`.
- Upstream `external/curl` has its `android17-security-release` branch pointing at a tag object, which breaks all-heads mirrors.

**Next:** ANAL-168 full build of `aosp_cf_x86_64_pc-cp2a-userdebug`, measuring ccache hits, then boot it in Cuttlefish.
| ANAL-186 NVIDIA dGPU, RTX 5070 Laptop (parked until the AMD iGPU bring-up works) | ANAL-187 research nouveau/NVK on Android and PRIME offload | — |
