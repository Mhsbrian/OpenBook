# Status

## Now (2026-10-16)

**Decisions needed from the owner**
- **Repo license** for the scripts and docs. Apache-2.0 is suggested, to match AOSP.
- **Track B** (ANAL-165): whether to go past research with Google's proprietary image (`docs/PLAN.md` §6).
- **Mesa libelf licensing** (ANAL-173): libelf is LGPL-3.0+ and is statically linked into the MIT Mesa libraries. Pick an approach before redistributing any image; the recommendation is to ship libelf as a shared library (`docs/mesa.md`).
- **Hardware inventory**: received 2026-10-16 (non-root run). The laptop is a **GA403WR** (Ryzen AI 9 HX 370), not a GA403WP; see `docs/HARDWARE.md` and `evidence/2026-10-16-ga403wr-inventory/`. A `--with-root` run would add `dmesg`.

**Tracking** (Multica, children of ANAL-159). ✓ = delivered and PR merged, ▶ = running, ⏳ = starts automatically when its dependency delivers.

| Epic | Stage 1 | Stage 2 | Stage 3 |
|---|---|---|---|
| ANAL-160 Track A: AOSP 17 desktop boots in a VM | ✓ ANAL-167 build container and source mirror (PR #5) | ▶ ANAL-168 build `aosp_cf_x86_64_pc-cp2a-userdebug` and boot to adb | ⏳ ANAL-169 VM graphics and desktop windowing |
| ANAL-161 AMD GKI kernel (android17-6.18) | ✓ ANAL-170 stock GKI reproduced, 0-symbol config diff (PR #4) | ▶ ANAL-171 AMD config and modules for the G14 | ⏳ ANAL-172 QEMU boot test (needs ANAL-171 and ANAL-168) |
| ANAL-162 AMD graphics userspace | ✓ ANAL-173 Mesa radeonsi/RADV for Android (PR #3) | ⏳ ANAL-174 device-tree integration (needs ANAL-168) | ANAL-177 dEQP/CTS on the G14 |
| ANAL-164 ARM compat and native bridge | ✓ ANAL-180 harness and libndk_translation baseline (PR #6) | ▶ ANAL-181 Digitalis evaluation | — |
| ANAL-163 Bare-metal bring-up on the G14 2025 | ANAL-175 inventory (waiting on the owner) | ANAL-176 USB boot | ANAL-178 input and power, ANAL-179 audio and Wi-Fi |
| ANAL-165 Track B: Googlebook OS on AMD (parked: licensing) | ANAL-182 VM boot to `boot_completed`, ANAL-183 Zen 4 ISA spike | ANAL-184 kernel swap | ANAL-185 graphics overlay |
| ANAL-186 NVIDIA dGPU, RTX 5070 Laptop (parked) | ANAL-187 nouveau/NVK research | — | — |
| ANAL-166 Performance and parity (parked) | — | — | — |

## History

### 2026-10-15: M0 (research, dev host, baselines)

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

### 2026-10-15: Kernel, stock android17-6.18 GKI reproduced with Kleaf (ANAL-170)

**Done**
- Googlebook OS ships the unmodified public GKI: the ruby `boot_a` kernel is byte-identical to ci.android.com build 16302624 (`kernel_x86_64`, branch `common-android17-6.18-2026-06`, `common` 3938c8d97142).
- Built it locally from that build's pinned manifest (`manifests/kernel/gbos-16302624.xml`) in 5 min 37 s. The `.config` and KMI CRCs are identical. Built with the same build number, `vmlinux` differs only in the per-build module-signing certificate and build ID (1,098 bytes).
- Config diff: 0 symbols. Google adds nothing beyond `gki_defconfig`. `PKVM_INTEL` is explicit in `gki_defconfig`; `X86_FRED` is selected by `KVM_INTEL` through an upstream Kconfig `select`.
- Our kernel boots on Zen 4 under KVM to the same `keystore2` stall as the stock kernel. Google's signed GKI modules (`rust_binder`, `zsmalloc`) are rejected, so `system_dlkm` must come from our build.
- The `android17-6.18` tip (6.18.32) also builds. The shipped KMI list is unchanged there.

**Evidence:** `evidence/2026-10-15-kernel/`. Details are in `docs/kernel.md`.

**Next:** an AMD defconfig fragment and an `anybook_amd` KMI symbol list on this tree, then boot with our `system_dlkm`.

### 2026-10-15: Graphics userspace, Mesa radeonsi + RADV for Android x86_64 (ANAL-173)

**Done**
- Built upstream Mesa 26.2.5 and Android-Generic `26.0/main` (26.0.8 + 63 commits), out-of-tree with NDK r30 at API 37 (`tools/Dockerfile.mesa-android`, `scripts/mesa-android-build.sh`). radeonsi uses ACO only, so no Android LLVM is needed. libelf comes from AOSP elfutils.
- Both trees: 0 unresolved NEEDED entries or symbols against the API 37 sysroot. `vulkan.radv.so` exports only `HMI`. Baseline ISA is x86-64 with SSE4.2; wider code is only behind runtime checks.
- Load test on the Android 17 emulator: the Vulkan HAL opens and `vkCreateInstance` succeeds with 0 devices (there's no GPU in the VM). EGL loads; `eglInitialize` fails because there's no DRM device. **Nothing has run on AMD hardware yet.**
- A clean rebuild is bit-identical. Details are in `docs/mesa.md`.

**Evidence:** `evidence/2026-10-15-mesa/`

**Blocked / needs a decision:** the static libelf is LGPL-3.0-or-later inside the MIT Mesa libraries. That's fine for local builds; binary redistribution needs a decision (`docs/mesa.md`).

**Next:** minigbm with an amdgpu/gbm_mesa backend so Mesa's `cros` gralloc path works, then SP-HAL SELinux labels, then a hardware run (M4).

### 2026-10-16: M1b prep, AOSP 17 build environment (ANAL-167, Track A)

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

### 2026-10-15: ARM compat harness and libndk_translation baseline (ANAL-180)

**Done**
- `scripts/compat/`: probe APKs (arm64-only, armv7-only, x86_64 control) with 19 test groups, a pinned F-Droid corpus (16 arm64-only apps plus 7 x86_64 controls), a resumable matrix runner and a CoreMark benchmark.
- **Apps:** 13 of 16 arm64-only F-Droid apps run under libndk_translation. Tor VPN (SIGILL on `mrs ID_AA64ISAR0_EL1`) and Element X fail only under translation; AAAAXY also fails natively.
- **No arm32:** armeabi-v7a does not install (the image is 64-bit only).
- **Speed:** translated arm64 runs at 0.457× native x86_64 (CoreMark, same emulator).
- **Probe findings:** seq_cst store→load ordering is broken (about 1% of store-buffering trials), NaN rules follow x86, `CNTVCT_EL0` runs about 429× fast, and `MRS` of ID registers is not emulated.

**Evidence:** `evidence/2026-10-15-compat/` (2 runs with identical outcomes, screenshots, logs, `bench/`, `analysis/`).

**Next:** the same corpus under houdini (after M1a) and Digitalis/Berberis (after M1b); root-cause Element X.

### 2026-10-16: M1b, our AOSP 17 build boots in Cuttlefish (ANAL-168, Track A)

**Done**
- Built `aosp_cf_x86_64_pc-cp2a-userdebug` with `scripts/aosp-build.sh`: 2 h 10 min cold at `-j32` on the shared host. Peak container RAM was 41 GiB, plus 18.5 GiB of swap. `out/` is 137 GB (165 GB after `m dist`), and ccache got 25% hits even though the cache started empty.
- Booted it with `scripts/cf-boot.sh` in Google's Cuttlefish container (no sudo, no `--privileged`). `sys.boot_completed=1` came 17–29 s after `cvd create`. The display is up at 1920×1080 showing Launcher3, and `adb` captures work. The boot also works with our build's own host tools (`CF_HOST_TOOLS=build`).
- Device: Android 17, SDK 37, `CP2A.260605.016`. `feature:android.hardware.type.pc` and freeform window management are present. The kernel is Google's prebuilt android16-6.12 GKI.

**Evidence:** `evidence/2026-10-16-aosp/`. Details are in `docs/aosp-build.md` (M1b).

**Findings**
- Cuttlefish in Docker needs three things the recipe left out: `seccomp=unconfined` (Docker's default profile blocks `AF_VSOCK`), a writable host path, and a writable product path. cvd 1.57 also swaps in all of its packaged host tools, because AOSP's host package ships `debian_substitution_marker`.
- The build advertises `arm64-v8a` in its abilist but ships no native bridge. An arm64-only APK installs, then fails `dlopen` with `EM_AARCH64`.

**Next:** ANAL-169, graphics and desktop windowing on this image. In ANAL-181, a translator for the advertised `arm64-v8a`.

### 2026-10-16: Kernel, AMD config and vendor modules (ANAL-171)

**Done**
- AnyBook GKI: the shipped `android17-6.18` tree plus 3 patches (`kernel/patches/common/`). Release `6.18.21-android17-5-g44a90255c95f`.
  - Three bool built-ins: `AMD_IOMMU`, `PINCTRL_AMD`, `X86_AMD_PLATFORM_DEVICE`.
  - An `anybook_amd` KMI list with 1,887 symbols, 214 of them new. amdgpu alone needs 129 symbols the stock GKI does not export.
- Kleaf mixed build `//devices/anybook` (`kernel/devices/anybook/`) produces 138 vendor modules: amdgpu with DC, amdxdna, amd-pmc, pinctrl-amd (built in), i2c-designware/i2c-hid-acpi, HDA ALC269/CS35L56, ACP/SOF-AMD, mt7921e/mt7925e, rtw89, btusb-MTK, asus-wmi, hid-asus, virtio-gpu and more.
- linux-firmware subset list: 131 files, 52.5 MB, all redistributable, with each file's licence taken from WHENCE.

**Evidence:** `evidence/2026-10-16-kernel-amd/`
- All 138 modules have vermagic, CRCs and imports matching the kernel.
- In a QEMU/KVM load test, 137 modules load and 1 returns -ENODEV (no ASUS WMI in the VM), with 0 symbol errors. AMD-Vi interrupt remapping is on, and virtio-gpu creates `card0`.
- Every stock KMI CRC is unchanged.
- The equivalence build shows 5 harmless vmlinux differences.

**Blocked:** amd-pmf. `ccp.ko` links SEV code that calls `kernel_read`/`kernel_write`, both on GKI's deny list. Owner decision needed; see `docs/kernel.md`.

**Next:** ANAL-172 packages `vendor_dlkm`/`vendor_boot` and does a boot test; then the `android17-6.18` tip build.

**Update (same day):** the inventory showed a GA403WR with codec SSID 1043:1024. The mainline quirk for it is backported, and the card reader and NVIDIA-WMI-EC backlight modules are added (see `docs/kernel.md`).

### 2026-10-16: Kernel, AnyBook kernel boots our AOSP 17 userspace in Cuttlefish (ANAL-172)

**Done**
- `scripts/kernel-cf-boot.sh` boots the ANAL-171 kernel and its own signed `system_dlkm` under ANAL-168's `aosp_cf_x86_64_pc` images, through cvd's `--kernel_path`/`--initramfs_path`. Android is not rebuilt.
- `scripts/kernel-cf-modset.py` merges the GKI, the 138 AnyBook modules and the Cuttlefish board modules (built from `common-modules/virtual-device` on our GKI), and checks every cross-module CRC.

**Evidence:** `evidence/2026-10-16-kernel-cf/`
- `sys.boot_completed=1` 30–33 s after `cvd create` (twice), `uname -r` = `6.18.21-android17-5-g44a90255c95f`.
- 169/169 expected modules are live, including 137 of the 138 AnyBook modules, amdgpu among them. There are 0 symbol, CRC or signature errors.
- virtio-gpu drives a 1920×1080 display. dmesg and logcat are included.

**Not loaded**
- `asus-nb-wmi`: -ENODEV, because the VM has no ASUS WMI. It is blocklisted in the VM image.
- 9 Cuttlefish virtual Wi-Fi and mt76 USB modules: CRC-incompatible with AnyBook's cfg80211/mac80211/mt76, because Cuttlefish sets `NL80211_TESTMODE`. The VM therefore has no virtual Wi-Fi.
- amd-pstate does not register: crosvm's ACPI has no `_CPC`.

**Next:** VM Wi-Fi modules built against the AnyBook config; real probing on the G14 (bare-metal epic).

### 2026-10-16: ARM compat, Digitalis evaluation (ANAL-181)

**Done**
- Built Digitalis from source:
  - Translator `b6b7fc30` on AOSP `android16-qpr2-release`, manifest `3969040d`.
  - The 70 bridge modules in 44 min; the full reference image in 82 min.
- Installed it as the native bridge of the AOSP Desktop 37.0 emulator, on its own AVD, and ran the ANAL-180 corpus, probes and CoreMark. Two wiped runs gave identical outcomes.
- Ran Digitalis's own AOSP 16 image as a control. It gave the same results.
- **Apps:** 12 of 16 arm64-only apps alive, against 13 for libndk_translation. Digitalis loses Fennec to a deterministic translation SIGSEGV at `libxul.so+0x2b32da0`. Tor VPN (`MRS ID_AA64ISAR0_EL1`) and Element X fail under both bridges.
- **Probes:** Digitalis fixes seq_cst ordering, `CNTVCT` rate, `uname` and FMAX NaN. It adds an `FRECPE` failure.
- **Speed:** CoreMark 0.30× native, against 0.45× for libndk_translation the same day, so about 34% slower.
- **License audit:** Apache-2.0, built from source, no Digitalis prebuilts in the image. The sample-app repo carries a proprietary SDK binary and must stay out of Track A.
- **Recommendation: GO for Track A**, with conditions:
  - port it to Android 17 (its guest NDK is A16: 43 `libandroid` exports missing);
  - fix the Fennec crash, `MRS ID_AA64ISAR0_EL1` and `FRECPE`;
  - accept or close the speed gap.

  Details are in `docs/digitalis.md`.

**Evidence:** `evidence/2026-10-16-digitalis/` (run1, run2, a16-control, bench, bench-ndk, analysis, bundle checksums, pinned manifest).

**Blocked / needs a decision**
- The owner's OK to report the findings upstream to DigitalisX64. That is an outward-facing action.

**Next:** port Digitalis to `android17-release` and build it in the Track A tree (after ANAL-168), boot it in Cuttlefish, and re-run the matrix.
