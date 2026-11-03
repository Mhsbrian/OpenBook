# OpenBook track plan

Goal: the Googlebook experience on x86_64 laptops Google does not ship it on. AMD Ryzen comes first, then other Intel
parts and NVIDIA graphics.

This is the roadmap and the technical approach behind it. Where things stand today is in [`STATUS.md`](STATUS.md);
day-to-day progress and decisions are on the issues. The research behind the approach, with sources, is in
[`RESEARCH.md`](RESEARCH.md).

As of 2026-11-02. Facts are labelled **CONFIRMED** (we checked a primary source or ran a test ourselves), **REPORTED**
(press or third-party claims), or **HYPOTHESIS** (not yet tested).

## 1. Where things stand

- **Googlebook OS ships and its images are public.** It was announced 2026-05-12 and reached retail 2026-10-04/05. It
  runs on Intel Core Ultra Series 3 (Panther Lake) and Snapdragon X Elite. No AMD device has been announced. Google
  publishes per-device recovery images at `dl.google.com/dl/edgedl/device/recovery/production_recovery.json`.
  **CONFIRMED** (2026-10-15).
- **The OS source is not public.** The products need `device/google/desktop` and `vendor/google/...`, and both return
  404. **CONFIRMED** (2026-10-15). What is public:
  - AOSP `android17-release`, including the Cuttlefish `aosp_cf_x86_64_pc` and `aosp_cf_x86_64_desktop` products. The
    `desktop` product depends on the private trees above.
  - The desktop GKI kernel branches.
  - Google's **AOSP Desktop (Preview)** emulator image, Android 17.
- **x86_64 already works.** The job is AMD platform enablement plus getting Google's hardware assumptions out of the
  way. It is not an ISA port. We verified this ourselves (2026-10-15):
  - The AOSP Desktop image boots to a freeform desktop on a Ryzen 9 7950X under KVM in 16 s.
  - Google's stock Googlebook kernel and init run on the same Zen 4 CPU under KVM. Boot gets through first-stage mount
    and about 30 second-stage services with **zero illegal-instruction traps**. It then stalls on the hardware security
    stack (blocker 1).
- **OpenBook today:** a `userdebug` developer preview for the ASUS ROG Zephyrus G14 (2025, GA403WR, Ryzen AI 9 HX 370,
  Radeon 890M, RTX 5070 Ti Laptop). The latest release and what works are in `STATUS.md`.

## 2. Two tracks

| | **Track A: OpenBook (open source)** | **Track B: Googlebook OS on AMD** |
|---|---|---|
| Base | Public AOSP `android-latest-release` (Android 17), with desktop windowing as in the AOSP Desktop image | Google's official recovery image, which **each user downloads themselves** (the Brunch model) |
| What we ship | A full, redistributable image | Only scripts and open-source replacement parts, applied locally to the user's own download |
| Parity with Googlebook | Partial: AOSP desktop UI, no Google apps, no Houdini | High: real Googlebook launcher, Chrome and system apps |
| ARM apps | The open Digitalis bridge, built from source | Google's own libhoudini and libndk_translation, already in the image |
| Legal risk | Low | Needs the owner's decision (§6) |
| Main blockers | Building and maintaining a full AOSP desktop product | Trusty/pKVM security stack, GSC TPM, Intel-only kernel and vendor stack |

- **This repository is Track A.** Track B lives in the sibling GoodBook repository (ANAL-260, 2026-10-24; the project
  split, ANAL-320, 2026-11-01).
- **Both tracks run on one AMD enablement layer:** the kernel and its vendor modules, Mesa radeonsi/RADV, minigbm,
  the composer and the HALs, the installer and A/B updates. Why: Track B shows what parity looks like fastest, and
  Track A is what we can legally publish as images, so every AMD component must be open source and serve both. The
  shared code has the same paths in both repositories; M0 makes it one copy.

## 3. Ranked blockers

The blockers found in research (2026-10-15), in rank order, with how each is handled. Code and other docs cite them by
number.

1. **Hardware-backed security (Track B, blocks boot).**
   - KeyMint, Gatekeeper and Weaver run in a Trusty security VM: `trusty.security_vm.enabled`,
     `desktop_trusty_signed.elf`.
   - That VM needs pKVM. The stock kernel has `CONFIG_PKVM_INTEL=y` and no AMD equivalent.
   - The OS also expects a Google Security Chip on `/dev/tpm0`, used by gscd, pinweaver and gscutil.
   - Observed: `keystore2` never registers, `vold` waits on it, and zygote never starts.
   - Fix: install AOSP's software KeyMint/Gatekeeper/Weaver HALs and disable the GSC services in a local vendor
     overlay.
   - Consequence: no hardware attestation. Play Integrity will fail, and **we will not work around that**.
2. **Kernel.** The stock GKI 6.18.21-android17 has none of `DRM_AMDGPU`, `PINCTRL_AMD` (touchpad GPIO IRQs),
   `AMD_PMC` (s2idle), `AMD_IOMMU`, ACP/SOF-AMD audio, `CRYPTO_DEV_CCP`, `DRM_VIRTIO_GPU`, or MediaTek MT7921/7925
   Wi-Fi. It also has `TRIM_UNUSED_KSYMS=y`, so an out-of-tree amdgpu cannot load; GBRUNCH reports 131 missing symbols.
   - Fix: rebuild GKI `android17-6.18` with Kleaf from the sources Googlebook OS ships, and add OpenBook's vendor
     modules (AMD, NVIDIA, the laptop's platform drivers). Boot, `system_dlkm` and the vendor modules ship from the same
     build (`docs/kernel.md`).
3. **Graphics userspace.** Googlebook's image sets `ro.hardware.vulkan=intel`, `ro.hardware.egl=angle` and
   `gralloc=minigbm`, and its minigbm has no amdgpu backend. Fix:
   - Mesa for Android with radeonsi and RADV, started from Android-Generic `external_mesa` 26.0 (`docs/mesa.md`);
   - minigbm with amdgpu through Mesa's GBM;
   - drm_hwcomposer;
   - ANGLE on RADV.

   How the device tree wires them: `docs/graphics-amd.md`. On the G14 the desktop renders on ANGLE and RADV
   (`STATUS.md`).
4. **CPU ISA (Track B).**
   - Google builds for `pantherlake` (`dalvik.vm.isa.x86_64.variant=pantherlake`).
   - 65 of 2,675 ELF files contain AVX-VNNI, which Zen 4 lacks and Zen 5 has. They include `init`, `linker64`, `libz`,
     `libcrypto`, `surfaceflinger` and `libhwui`.
   - On Zen 4, early boot does not reach those code paths. Rendering and media paths are untested.
   - Mitigations: target Zen 5 (Ryzen AI 300/Max, Ryzen 9000) first; the ART variant is a property, so it can be set
     per device. For Zen 4, a kernel #UD handler that emulates VEX AVX-VNNI on Zen 4's AVX-512 VNNI unit.
     **HYPOTHESIS.**
   - The G14's HX 370 is Zen 5, so the risk applies only to a Zen 4 dev host (`docs/HARDWARE.md`). Track A images
     build for the generic `silvermont` baseline and avoid it (`docs/aosp-build.md`).
5. **Boot path on generic UEFI PCs.**
   - Googlebook uses a hybrid GPT layout: ChromeOS KERN/ROOT partitions, Android A/B, virtual A/B `super`, and AVB.
   - We need an EFI loader that hands the kernel a bootconfig, `androidboot.*` parameters and the vbmeta digest, in the
     orange (unlocked) state on the user's own machine.
   - Choice (ANAL-189): **systemd-boot** with Boot Loader Spec entries, one per slot. GRUB, systemd-boot and GBL all
     boot our kernel and AOSP 17 userspace from a GPT image in QEMU/OVMF; a UKI cannot carry Android bootconfig, and GBL
     fails when a second disk has the same partition names. GBL stays an option for later (`docs/installer.md`).
6. **ARM translation (Track A).** Neither libhoudini nor libndk_translation is redistributable. Berberis upstream only
   translates riscv64. Digitalis is Apache-2.0 and Berberis-based. OpenBook builds it from source as its native bridge
   (`docs/digitalis.md`); `docs/COMPAT-MATRIX.md` tracks which ARM-only apps run.
7. **Linux terminal and AVF.** The Googlebook terminal runs in a pKVM-protected VM, which doesn't exist on AMD.
   OpenBook uses non-protected AVF VMs over plain KVM (`docs/quire.md` §4.1).
8. **NVIDIA.** Android has no hybrid-GPU plumbing. OpenBook ships NVIDIA's open kernel driver and its GSP firmware
   (`docs/nvidia-open.md`), which bind the RTX and hold it in D3cold when idle (shown on the GoodBook image, which
   shares the kernel and vendor layer), and a graphics-mode switcher (Eco, Hybrid, Ultimate) with automatic rollback,
   shipped with firmware writes off (`docs/nvidia-graphics-modes.md`). Apps can't render on the RTX yet; that is M1. Research on nouveau and
   NVK for the RTX 50 Laptop GPU is in `docs/nvidia.md`.

## 4. Milestones

The plan of record is ANAL-334 (set 2026-11-02). Each milestone has an issue, and every new issue goes under one.
State is in `STATUS.md`.

| Milestone | Goal | Done when |
|---|---|---|
| **M0** Reset | A clean base to build on | The repository holds source and docs only, and CI enforces it; a build reproduces from a clean checkout; one copy of the code shared with GoodBook; a lighter release process |
| **M1** OpenBook 0.1.0-preview.3: NVIDIA for apps | Apps on the RTX | Apps run on the RTX with a per-app choice and an on/off switch; Eco and Hybrid switching; a speed baseline; the release is published |
| **M2** OpenBook 0.2.0 public beta | A release anyone can install and trust | A fresh public repository with clean history; release keys; a `user` build; a project license; an install or live-only stick |
| **M3** Experience parity | Closer to Googlebook in daily use | Quire voice; performance; Chrome and the Linux environment; a second laptop |

Releases follow `CONTRIBUTING.md`: SemVer with `-preview.N` for developer previews, built once from a tag. Previews are
`userdebug` builds with AOSP test keys; the public beta and later are `user` builds with OpenBook's release keys.

The earlier milestone list (M0 to M8, 2026-10-15 to 2026-10-31) is in Git history. Its results are in `STATUS.md` and
the topic docs.

## 4a. Testing on the real laptop

Testing and verification happen on real hardware, not only in VMs (epic ANAL-193).

- **The reference laptop is the G14.** It is reached from the build host over Wi-Fi with adb (`scripts/g14-adb.sh`,
  `docs/adb-debug.md`). New builds go onto it as A/B updates that keep the user's data and fall back to the old slot
  by themselves (`docs/adb-debug.md` §7). USB stick sessions are no longer part of the loop (owner, 2026-10-18).
- **Heavy builds stay on the build host** (AOSP, kernel, Mesa). The laptop runs and verifies.
- **Everything built for bare metal is scripted** and safe to run unattended, and emits durable logs and
  machine-readable results. The installer's engine runs unattended with JSON output for this (`docs/installer.md`).
  Owner-run steps remain only where hands or ears are needed (touchpad, lid, listening).
- **Test once** (`CONTRIBUTING.md`): CI on every pull request; the author's checks for what a change touches; and,
  once per release, the VM suite on the release build and a smoke test on the reference laptop. Results go on the
  issue, never into the repository.
- **Safety:** nothing writes to a physical disk, USB stick or firmware, or changes the boot configuration, without the
  owner's approval of that exact write. Over adb the same rule applies.

## 5. Reuse instead of rebuild

- **GBRUNCH** (MIT): builds Googlebook from a recovery image locally, with a vendor compat layer and software KeyMint.
  Its `AMD.md` blocker list matches what we found. Track B's starting point.
- **gbos-vm** (MIT): rebuilds the vendor partition from Cuttlefish parts and has the virgl plumbing for QEMU.
- **Android-Generic / Bliss OS** (Apache-2.0): Mesa 26.0 fork, minigbm `gbm_mesa`, drm_hwcomposer, and the
  `kernel-zenith` 6.18 AMD configs.
- **Brunch** (GPL-3.0): the licensing model (user-supplied image), initramfs and UEFI boot patterns.
- **Cuttlefish and the AOSP Desktop emulator image:** a reference desktop UI and our VM boot target.
- **Waydroid on Ryzen:** a quick bench for the ARM compat matrix.
- **Digitalis** (Apache-2.0): the open arm64 native bridge, built from source.

<a id="licensing"></a>

## 6. Licensing

- Google's recovery image is proprietary. It is downloaded locally for interoperability research, is **never committed
  or redistributed**, and is not in this repository. `.gitignore` blocks images, and CI rejects them.
- Running Googlebook OS on non-Googlebook hardware may fall outside Google's terms. Whether Track B goes past research,
  and on what terms (for example, user-supplied image only, as Brunch does), is the owner's decision.
- We do not bypass Play Integrity, DRM or license checks. AVB runs in the unlocked/orange state only on hardware the
  user owns.
- Emulator system images fall under the Android SDK (Preview) License: local use only, no redistribution.
- libhoudini and libndk_translation are proprietary. Track A does not bundle them.
- Google's apps are never bundled. The user installs their own package or uses the microG option (`docs/gapps.md`).
- NVIDIA's open kernel driver and GSP firmware ship unmodified under their licence, with the licence next to the image
  (`STATUS.md`).
- OpenBook's own project license is chosen for the public beta (M2). Licensing calls go to the owner.
