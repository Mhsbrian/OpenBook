# OpenBook track plan

Goal: the Googlebook experience on x86_64 hardware Google does not ship. AMD Ryzen comes first, then other Intel parts, and NVIDIA later.

Status as of 2026-10-15. Facts are labelled **CONFIRMED** (we checked a primary source or ran a test ourselves), **REPORTED** (press or third-party claims), or **HYPOTHESIS** (not yet tested). See `docs/RESEARCH.md` for sources and `docs/STATUS.md` for evidence.

## 1. Where things stand

- **Googlebook OS ships and its images are public.** It was announced 2026-05-12 and reached retail 2026-10-04/05. It runs on Intel Core Ultra Series 3 (Panther Lake) and Snapdragon X Elite. No AMD device has been announced. Google publishes per-device recovery images at `dl.google.com/dl/edgedl/device/recovery/production_recovery.json`. **CONFIRMED.**
- **The OS source is not public.** The products need `device/google/desktop` and `vendor/google/...`, and both return 404. **CONFIRMED.** What is public:
  - AOSP `android17-release`, including the Cuttlefish `aosp_cf_x86_64_pc` and `aosp_cf_x86_64_desktop` products. The `desktop` product depends on the private trees above.
  - The desktop GKI kernel branches.
  - Google's **AOSP Desktop (Preview)** emulator image, Android 17.
- **x86_64 already works.** The job is AMD platform enablement plus getting Google's hardware assumptions out of the way. It is not an ISA port. We verified this ourselves:
  - The AOSP Desktop image boots to a freeform desktop on a Ryzen 9 7950X under KVM in 16 s.
  - Google's stock Googlebook kernel and init run on the same Zen 4 CPU under KVM. Boot gets through first-stage mount and about 30 second-stage services with **zero illegal-instruction traps**. It then stalls on the hardware security stack.

## 2. Two tracks

| | **Track A: OpenBook (open source)** | **Track B: Googlebook OS on AMD** |
|---|---|---|
| Base | Public AOSP `android-latest-release` (Android 17), with desktop windowing as in the AOSP Desktop image | Google's official recovery image, which **each user downloads themselves** (the Brunch model) |
| What we ship | A full, redistributable image | Only scripts and open-source replacement parts, applied locally to the user's own download |
| Parity with Googlebook | Partial: AOSP desktop UI, no Google apps, no Houdini | High: real Googlebook launcher, Chrome and system apps |
| ARM apps | No open arm64 translator yet. Berberis is riscv64-only; Digitalis needs evaluation; libndk_translation only if the user installs it | Google's own libhoudini and libndk_translation, already in the image |
| Legal risk | Low | **Needs a decision from the owner** (see §6) |
| Main blockers | Building and maintaining a full AOSP desktop product | Trusty/pKVM security stack, GSC TPM, Intel-only kernel and vendor stack |

**Recommendation:** run both tracks on one shared AMD enablement layer: kernel config, Mesa radeonsi/RADV, minigbm, drm_hwcomposer and HALs. Track B gets us to "Googlebook on Ryzen" fastest and shows what parity looks like. Track A is what we can legally publish as images. Every AMD component we build must be open source, so it serves both tracks.

## 3. Ranked blockers

1. **Hardware-backed security (Track B, blocks boot).**
   - KeyMint, Gatekeeper and Weaver run in a Trusty security VM: `trusty.security_vm.enabled`, `desktop_trusty_signed.elf`.
   - That VM needs pKVM. The stock kernel has `CONFIG_PKVM_INTEL=y` and no AMD equivalent.
   - The OS also expects a Google Security Chip on `/dev/tpm0`, used by gscd, pinweaver and gscutil.
   - Observed: `keystore2` never registers, `vold` waits on it, and zygote never starts.
   - Fix: install AOSP's software KeyMint/Gatekeeper/Weaver HALs and disable the GSC services in a local vendor overlay.
   - Consequence: no hardware attestation. Play Integrity will fail, and **we will not work around that**.
2. **Kernel.** The stock GKI 6.18.21-android17 has none of:
   - `DRM_AMDGPU`
   - `PINCTRL_AMD` (needed for touchpad GPIO IRQs)
   - `AMD_PMC` (s2idle)
   - `AMD_IOMMU`
   - ACP/SOF-AMD audio
   - `CRYPTO_DEV_CCP`
   - `DRM_VIRTIO_GPU`
   - MediaTek MT7921/7925 Wi-Fi

   It also has `TRIM_UNUSED_KSYMS=y`, so an out-of-tree amdgpu cannot load. GBRUNCH reports 131 missing symbols.

   Fix: build `kernel/common android17-6.18` (and later `android-mainline-desktop`) with an AMD fragment. Replace boot, system_dlkm and vendor_dlkm together.
3. **Graphics userspace.** The image sets `ro.hardware.vulkan=intel`, `ro.hardware.egl=angle` and `gralloc=minigbm`, and its minigbm has no amdgpu backend. Fix:
   - Mesa for Android with radeonsi and RADV. Start from Android-Generic `external_mesa` 26.0.
   - minigbm with amdgpu or gbm_mesa.
   - drm_hwcomposer.
   - ANGLE running on RADV.
4. **CPU ISA (Track B, open risk).**
   - Google builds for `pantherlake` (`dalvik.vm.isa.x86_64.variant=pantherlake`).
   - 65 of 2,675 ELF files contain AVX-VNNI, which Zen 4 lacks and Zen 5 has. They include `init`, `linker64`, `libz`, `libcrypto`, `surfaceflinger` and `libhwui`.
   - On Zen 4, early boot does not reach those code paths. Rendering and media paths are untested.
   - Mitigations:
     - Prefer Zen 5 (Ryzen AI 300/Max, Ryzen 9000) as the first laptop target.
     - For Zen 4, test a kernel #UD handler that emulates VEX AVX-VNNI using the AVX-512 VNNI unit Zen 4 does have. **HYPOTHESIS.**
   - The ART variant is a property, so we can set it per device.
   - **Target (2026-10-15):** the owner's laptop is an ASUS G14 2025 with a Ryzen AI 9 HX 370, which is Zen 5 and has AVX-VNNI. If its `/proc/cpuinfo` confirms `avx_vnni`, this risk only affects the Zen 4 dev host.
5. **Boot path on generic UEFI PCs.**
   - The image uses a hybrid GPT layout: ChromeOS KERN/ROOT partitions, Android A/B, virtual A/B `super`, and AVB.
   - We need an EFI loader that hands the kernel a bootconfig, `androidboot.*` parameters and the vbmeta digest, using the orange (unlocked) state on the user's own machine. Candidates: GRUB as in GBRUNCH, or Google's GBL EFI app.
   - QEMU direct-kernel boot already gets through first-stage mount.
   - **Prototyped (ANAL-189, 2026-10-16):** GRUB, systemd-boot and GBL all boot our kernel and AOSP 17 userspace from a GPT image attached as a USB stick in QEMU/OVMF, in the orange state with `boot_part_uuid`. A UKI cannot carry Android bootconfig. GBL fails when a second disk has the same partition names. Recommendation: systemd-boot now, GBL later (`docs/installer.md`).
6. **ARM translation (Track A).** Neither libhoudini nor libndk_translation is redistributable. Berberis upstream only translates riscv64. Digitalis is Apache-2.0 and Berberis-based, but young and unmeasured. Add it to the compat matrix early.
7. **Linux terminal and AVF.** The Googlebook terminal runs in a pKVM-protected VM, which doesn't exist on AMD. The fallback is non-protected AVF VMs over plain KVM.
8. **NVIDIA (long term).** NVK/nouveau in Mesa for Android with GSP firmware. This comes after AMD. Research is done (ANAL-187, `docs/nvidia.md`):
   - The open pieces exist. nouveau has supported GB20x through GSP-RM 570.144 since 6.16, and NVK is Vulkan 1.4 conformant on Blackwell.
   - The open problems:
     - Runtime PM on r570 firmware is still being fixed upstream.
     - The only RTX 5070 Laptop report shows about 5–10% of proprietary-driver performance.
     - Android has no hybrid-GPU plumbing.
   - **No-go for M3–M8**: the dGPU stays off, with `dgpu_disable=1` as ANAL-176's default.
   - After M4: research milestones N1–N6, aiming at per-app offload through Android's updatable-driver switch.

## 4. Milestones

Each milestone is small, has a verification artifact, and is checked into `evidence/`.

| # | Milestone | Track | Done when | State |
|---|---|---|---|---|
| M0 | Research, dev host, baselines | A+B | AOSP Desktop emulator boots with desktop windowing; Googlebook image downloaded, verified, unpacked and scanned; stock kernel and init executed under KVM on Zen 4 | **Done** (2026-10-15) |
| M1a | Googlebook OS to an adb shell in a VM | B | QEMU/KVM boot gets past keystore2 to `sys.boot_completed=1` using software KeyMint/Gatekeeper/Weaver and the GSC services disabled, via a local vendor overlay (GBRUNCH method) | Next |
| M1b | AOSP 17 PC build boots | A | `aosp_cf_x86_64_pc` built from `android17-release` in an Ubuntu 24.04 container; boots in the Cuttlefish container (podcvd image 1.56) | Next |
| M2 | Graphics in a VM | A+B | Custom 6.18 kernel with virtio-gpu; virgl or venus; SurfaceFlinger up, with a screenshot and `dumpsys SurfaceFlinger` | |
| M3 | AMD kernel on bare metal | A+B | android17-6.18 plus an AMD fragment, booted from USB or a spare drive on the target laptop; dmesg shows amdgpu, amd-pstate, pinctrl-amd, amd_pmc and Wi-Fi bound | Needs a confirmed target device |
| M4 | AMD graphics stack | A+B | radeonsi/RADV, minigbm and HWC running on the target; ANGLE on RADV; `dEQP`/CTS graphics subset | |
| M5 | Desktop UI, input and power | A+B | Touchpad and keyboard, s2idle suspend/resume cycles, battery, backlight, audio (ACP/SOF) | |
| M6 | Apps and ARM translation | A+B | ARM-only APK compatibility matrix (top 50 plus a stress list) under houdini, ndk_translation and Digitalis | |
| M7 | Performance and parity | A+B | Benchmarks against an Intel Googlebook baseline (needs device access); Chrome; Linux terminal fallback | |
| M8 | USB installer | A | A bootable OpenBook USB image that runs live and installs through a graphical wizard, only to a disk the user confirms by name (epic ANAL-188, owner goal 2026-10-16) | Design and QEMU boot-chain prototype delivered (ANAL-189, `docs/installer.md`); live USB image built and tested in QEMU (ANAL-190, §11), G14 boot pending |

## 4a. Device-in-the-loop: Multica on the G14 (owner directive, 2026-10-16)

**Do not drop this as we iterate.** Building, testing and verification move onto the real laptop in phases, run by a Multica runtime and a dedicated test agent on the ASUS G14 (epic ANAL-193):

| Phase | Runtime host | Purpose | Issue |
|---|---|---|---|
| 1 | G14's current Linux (Arch/Omarchy) | Runtime and "OpenBook G14 Tester" agent online; root inventory (dmesg, ACPI, EDID) | ANAL-194 (needs the owner to install the daemon) |
| 2 | G14 Linux, KVM | Our AOSP 17 image and OpenBook kernel in Cuttlefish on the real Zen 5 CPU | ANAL-195 |
| 3 | G14 Linux ⇄ OpenBook bare metal | Unattended dual-boot cycle: boot OpenBook once, run test hooks, reboot to Linux, harvest and report | ANAL-196 (after ANAL-176) |
| 4 | Installed OpenBook | Runtime on the device itself: CTS/VTS subsets, ARM compat on hardware, suspend/battery, benchmarks | ANAL-197 (after M8 / ANAL-188) |

**Quality gate.** From M3 on, a bare-metal milestone (M3, M4, M5, M8) is delivered only when it is reproduced on the G14:
- by the device agent once it exists;
- until then, by an owner-run checklist with the exact commands and logs.

Everything built for bare metal must therefore be scripted, unattended-safe, and emit durable logs and machine-readable results. Heavy builds (AOSP, kernel, Mesa) stay on the 7950X dev host; the laptop runs and verifies. The device agent follows the same safety rules: never flash, repartition, wipe or change the boot configuration without explicit owner confirmation that names the device or entry.

## 5. Reuse instead of rebuild

- **GBRUNCH** (MIT): builds Googlebook from a recovery image locally, with a vendor compat layer and software KeyMint. Its `AMD.md` blocker list matches what we found. This is Track B's starting point.
- **gbos-vm** (MIT): rebuilds the vendor partition from Cuttlefish parts and has the virgl plumbing for QEMU.
- **Android-Generic / Bliss OS** (Apache-2.0): Mesa 26.0 fork, minigbm `gbm_mesa`, drm_hwcomposer, and the `kernel-zenith` 6.18 AMD configs.
- **Brunch** (GPL-3.0): the licensing model (user-supplied image), initramfs and UEFI boot patterns.
- **Cuttlefish and the AOSP Desktop emulator image:** a reference desktop UI and our CI boot target.
- **Waydroid on Ryzen:** a quick bench for the ARM compat matrix.

## 6. Licensing (decision needed)

- Google's recovery image is proprietary. It is downloaded locally into `~/anybook/dl` for interoperability research, is **never committed or redistributed**, and is not in this repo. `.gitignore` blocks images.
- Running Googlebook OS on non-Googlebook hardware may fall outside Google's terms. **Before Track B goes past research, the project owner needs to decide whether it proceeds**, and on what terms (for example, user-supplied image only, as Brunch does).
- We do not bypass Play Integrity, DRM or license checks. AVB runs in the unlocked/orange state only on hardware the user owns.
- Emulator system images fall under the Android SDK (Preview) License: local use only, no redistribution.
- libhoudini and libndk_translation are proprietary. Track A will not bundle them.

## 7. Next steps (in order, updated 2026-10-16, night)

Execution is tracked as Multica epics under ANAL-159. The live map, lanes and critical path are in `docs/STATUS.md`.

**End deliverable (owner, 2026-10-16):** a bootable USB image with an interactive installer wizard (M8, ANAL-188), verified on the G14 by an on-device agent (§4a).

**Delivered and merged** (PRs #1–#14):
- Track A in a VM: our AOSP 17 PC build gives the Android desktop experience on the host GPU (ANAL-169).
- The OpenBook GKI with 138 AMD vendor modules boots our userspace (ANAL-172).
- Mesa for Android (ANAL-173).
- The ARM compat baseline and the Digitalis evaluation (ANAL-180/181).

**Now running, by lane:**
- **AOSP lane:** ANAL-174, the AMD graphics stack in the tree as a reusable makefile with VM/bare-metal HAL selection.
- **Kernel lane:** ANAL-198, bare-metal packaging: first-stage NVMe and USB boot, vendor_boot, vendor_dlkm, system_dlkm and the firmware subset, validated in QEMU.
- **Light lanes:**
  - ANAL-189: installer and boot-chain design, with a QEMU/OVMF prototype. It was promoted ahead of ANAL-176 so the loader is proven before it reaches hardware.
  - ANAL-187: NVIDIA research, including how to keep the dGPU off at first boot. Delivered: `docs/nvidia.md` and `scripts/dgpu-power-check.sh`.

**Then, handed off automatically:**
1. ANAL-199: the real G14 product (GPT, fstab, kernel packaging, base HALs). It must boot in QEMU/OVMF as a PC first.
2. ANAL-176: USB boot on the G14, with the owner at the laptop or the device loop.
3. ANAL-200: Digitalis on Android 17 as our redistributable arm64 bridge.
4. ANAL-178/179: input, power, audio and Wi-Fi.
5. The installer: ANAL-190 to ANAL-192.

**In parallel, when the owner is ready:** the device-loop runtime on the G14 (ANAL-194 → ANAL-197).

Track B (ANAL-182) waits on the owner's licensing decision.
