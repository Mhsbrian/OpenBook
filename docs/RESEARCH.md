# Research: Googlebook OS and prior art (2026-10-15)

Labels: **C** = confirmed (a primary source, or we checked it ourselves), **R** = reported (press or third-party), **U** = unknown or unverified.

## Googlebook OS facts

| Fact | Label | Source |
|---|---|---|
| Announced 2026-05-12 as "a new category of laptops" on the Android stack plus ChromeOS desktop foundations. OEMs: Acer, ASUS, Dell, HP, Lenovo | C | blog.google/products-and-platforms/platforms/android/meet-googlebook/ (2026-05-12) |
| Official name "Googlebook OS". Pre-orders 2026-09-21 from $899. Retail 2026-10-04 (US) and 2026-10-05 (CA/UK/IE/FR/DE/AU). 10 years of updates | C | blog.google/.../pre-order-googlebook/ (2026-09-21) |
| CPUs: Intel Core Ultra Series 3 (Panther Lake) and Snapdragon X Elite. No AMD | C | blog.google/.../first-look-googlebook/ (2026-09-21) |
| "Aluminium" is the internal codename | R | The Verge via daringfireball.net (2026-05-15) |
| Device codenames: moonstone (Acer), lapis (ASUS), ruby (Lenovo) are Intel and share build 16452207; mica (Dell) and quartz (HP) are Snapdragon, build 16471258 | C | `production_recovery.json` (fetched 2026-10-15) |
| Recovery images are public: `https://dl.google.com/device/recovery/<codename>-user/<build>/recovery.zip`, about 7.8 GB zipped, 17.8 GiB raw | C | We downloaded ruby and the md5 matched the manifest |
| Linux terminal is a Debian VM under pKVM, in preview, without GPU acceleration | C | android-developers.googleblog.com/2026/10/googlebook-linux-terminal-preview-vm.html |
| Chromebooks: "many newer commercial models" will be able to upgrade. Nothing has been said about ChromeOS Flex or uncertified hardware | C / U | support.google.com/chrome/a/answer/16634428 (2026-09-23) |
| Google says Intel models translate ARM apps with "a highly advanced binary translation layer", and 96.6% of the top 10k apps work | R | heise.de (2026-10-07) |

## What we confirmed in the ruby image (CL3B.260622.271.R1)

- **Partition layout:** hybrid GPT. ChromeOS `KERN-A/B` and `ROOT-B`, `EFI-SYSTEM`, Android A/B `boot`/`init_boot`/`vendor_boot`/`vbmeta`/`pvmfw`, `desktop_security_*`, and a 12 GiB virtual-A/B `super`. The `super` partition holds system, vendor, product, system_ext, system_dlkm and vendor_dlkm, all EROFS with LZ4 compression.
- **Kernel:** `6.18.21-android17-5-g3938c8d97142-ab16302624`, built with clang 22.0.1, with PGO, BOLT and LTO. The config is saved in `evidence/2026-10-15-m0/gbos-kernel-config.txt`.
- **Hardware properties:**
  - `ro.hardware=android-desktop`, `ro.hardware.type=CLAMSHELL`
  - `ro.hardware.egl=angle`, `ro.hardware.vulkan=intel`, `ro.hardware.gralloc=minigbm`
  - `ro.hardware.keystore=trusty`
- **ARM translation:** `ro.dalvik.vm.native.bridge=libhoudini.so`, and `ro.berberis.is_2nd_native_bridge=true` makes libndk_translation the second bridge. So Intel Houdini is primary and ndk_translation secondary. AOSP `shared/desktop/common_x86.mk` has the same default, `houdini_primary_ndk_translation_secondary`.
- **ART target:** `dalvik.vm.isa.x86_64.variant=pantherlake`.
- **Vendor stack is Intel-only:** `xe.ko`, SOF Intel, `iwlwifi`/`iwlmld`, IPU7 camera (`camera.libipu7_hal_fatcat.so`), OpenVINO and the Intel NPU (`libze_intel_npu.so`), and `vulkan.intel.so`.
- **Kernel command line** includes `kvm-intel.pkvm=1 fred=on ia32_emulation=false vsyscall=none binder.impl=rust`.

### UI and Google apps in the ruby image (ANAL-201, 2026-10-17)

Details are in `docs/googlebook-ui.md` and `docs/gapps.md`; evidence in `evidence/2026-10-17-gbos-ui/`.

- **UI apps (C).** Googlebook replaces the platform UI with Google builds:
  - the Pixel Launcher (`NexusLauncherRelease`);
  - Google's SystemUI (`SystemUITitan`) and Settings (`SettingsGoogle`), both signed with the platform key;
  - Wallpaper & style;
  - seven SystemUI clock plugins;
  - 61 product overlays.

  The Google APIs Desktop SDK image (37.1, `CLE3.260929.004`) has the same GMS but AOSP's Launcher3, SystemUI and Settings.
- **GMS packaging (C).** GmsCore 26.22.43 (x86_64) ships inside the APEX `com.google.android.gmssystem` on `/product`, next to GSF, Play Store 52.4.41 and the setup wizard.
- **Fonts (C).** Headlines use `google-sans` and body text `google-sans-text`. The 30 Material 3 `variable-*` families map to Google Sans Flex. AOSP 17's SystemUI, Launcher3 and SettingsLib ask for those family names but AOSP doesn't define them. **Google Sans (v14, added 2026-09-11) and Google Sans Flex (v5, 2026-10-09) are SIL OFL 1.1 in `github.com/google/fonts`.** The clock fonts are proprietary.
- **Flags (C).** 728 flags are on in Googlebook and off in our G14 build. 510 of them are not declared in AOSP 17, so Googlebook runs code newer than `android17-release`.
- **Blur (C).** Googlebook sets `ro.surface_flinger.supports_background_blur=1`.

## Public source

- **AOSP releases:** source drops twice a year (Q2 and Q4). Use `android-latest-release`. The latest tag is `android-17.0.0_r1` (2026-06), and aosp-main has been frozen since 2025-03-27. (C, source.android.com)
- **Cuttlefish products** in `device/google/cuttlefish` on `android17-release` (C):
  - `aosp_cf_x86_64_desktop` needs `device/google/desktop/...`, `vendor/google/products/cuttlefish/desktop` and `vendor/unbundled_google/...`. All of them return 404.
  - `aosp_cf_x86_64_pc` uses AOSP paths only.
- **CI builds:** the public CI branch is `aosp-android-latest-release`. Build 16373615 publishes `aosp_cf_x86_64_only_phone-userdebug`. No desktop or pc artifacts are published. (C)
- **Desktop GKI branches** in `kernel/common`: `android-mainline-desktop` (active, 2026-10-13), `android16-6.12-desktop`, `android15-6.6-desktop`. They contain only the generic x86 `gki_defconfig`. (C)
- **Placeholder repos:** `platform/system/desktop/{ec,ap,security,intel-pmt,fingerprint,...}` and `platform/external/cros_*` exist but are empty. `trusty/device/desktop` has real content. (C)
- **Emulator images** in the SDK repo `sys-img/android-desktop/sys-img2-4.xml` (C):
  - `system-images;android-37.0;android-desktop;x86_64`: "AOSP Desktop (Preview)", SDK preview license, translates arm64.
  - `system-images;android-37.1;android-desktop;x86_64`: "Google APIs Desktop (Preview)".

## Prior art

| Project | Approach | License | Latest (verified) | AMD | Reuse |
|---|---|---|---|---|---|
| GBRUNCH (danbyumagic/gbrunch) | Builds ruby Googlebook from the recovery image locally; GRUB; compat vendor layer; software KeyMint/Gatekeeper | MIT | v0.3-preview, 2026-10-10 | Blocked: 131 missing amdgpu symbols, no amdgpu minigbm, Intel-only Vulkan | **Highest** for Track B |
| gbos-vm (skylartaylor) | Dell ARM64 image under QEMU on Apple Silicon; vendor rebuilt from Cuttlefish parts; Mesa 26.2.4 with patched virglrenderer | MIT | created 2026-10-07 | n/a | VM graphics plumbing |
| skylartaylor x86 KVM gist | lapis image under KVM; reports init crashing on "older CPUs" and "probably Zen 5 only" | — | 2026-10-07 | **Our Zen 4 test disagrees for early boot** | CPU-feature lead |
| Brunch (sebanc) | ChromeOS recovery image plus a custom kernel; the user supplies the image | GPL-3.0 | r154, 2026-10-10 | Good on Ryzen iGPUs | Boot and licensing model. Googlebook support: none |
| Android-Generic / Bliss OS | AOSP-x86; Bliss 18 is Android 15; Zenith kernel 6.18; Mesa 26.0; minigbm gbm_mesa; drm_hwcomposer | Apache-2.0 / GPL | Public ISOs paused; Mesa branch updated 2026-09-30 | Historically good | **Very high** for the AMD graphics stack |
| Waydroid | Android in LXC on a Linux host | GPL-3.0 | 1.6.3, 2026-05-28 | Verified on a Radeon 780M with Android 13 | ARM compat bench |
| Cuttlefish | Google virtual device; podcvd container image `cuttlefish-orchestration:1.56.0` | Apache-2.0 | host tools 1.57.0, 2026-08-29 | n/a | Track A VM target |
| FydeOS / openFyde | Chromium OS fork; openFyde has `amd64_apu` overlays | proprietary / BSD-3 | v23.0, 2026-08-20 / r144 | Yes | Medium |
| ChromeOS Flex | Proprietary ChromeOS for PCs | proprietary | tracks ChromeOS | Good | Low: no announced Googlebook path |
| Intel Celadon | Intel AOSP reference | Apache-2.0 | Discontinued 2026-01-27 | Intel only | HWC and device-tree patterns |
| Android-x86, PrimeOS, Phoenix OS | Old AOSP-x86 | mixed | 2020–2022 / dead | Old | Historical only |
| DangerousAndroid/AluminiumOS | Leaked ARM64 GSI | — | 2026-07-01 | — | **Avoid** (leak) |

## Google apps on custom x86_64 builds (ANAL-201, 2026-10-17)

Details and sources are in `docs/gapps.md`.

| Option | Android 17 x86_64 | License | Notes |
|---|---|---|---|
| microG GmsCore v0.3.17 (2026-09-29) | Yes | Apache-2.0 | Needs signature spoofing; LineageOS `198fa72864` is on `lineage-24.0` (C) |
| LiteGapps | `x86_64/37` (2026-09-30) | Proprietary payload | Module or recovery install; the APK source is not stated (C) |
| MindTheGapps | arm64 only | Proprietary payload | Dropped x86 after Android 13 (C) |
| GSI+GMS, SDK desktop images | — | Testing and development only, no redistribution | Not a source for OpenBook (C) |

## ARM-on-x86 native bridges

| Bridge | Guest ISA | License | Redistributable | Notes |
|---|---|---|---|---|
| libhoudini (Intel) | arm/arm64 | Proprietary | No | Primary bridge in the Googlebook Intel image |
| libndk_translation (Google) | arm/arm64 | Proprietary | No | Secondary bridge in Googlebook. Also ships in SDK x86_64 emulator images and ChromeOS AMD builds; the ChromeOS copy carries an "ARM-to-AMD DBT" license |
| Berberis (AOSP) | riscv64 | Apache-2.0 | Yes | No arm64 product upstream |
| Digitalis (DigitalisX64) | arm64 | Apache-2.0 | Yes | Built on Berberis; created 2026-04; no published pass rates. **Evaluate** |
| QEMU user mode | arm64 | GPL-2.0 | Yes | Slow fallback |
| box64 / FEX | x86 on ARM | MIT | — | Wrong direction |

## Sources

- blog.google posts listed above; android-developers.googleblog.com/2026/09/adaptive-development-scale-app-googlebook.html
- https://dl.google.com/dl/edgedl/device/recovery/production_recovery.json
- https://dl.google.com/android/repository/sys-img/android-desktop/sys-img2-4.xml
- https://source.android.com/docs/setup/reference/build-numbers ; https://source.android.com/docs/devices/cuttlefish/get-started
- https://android.googlesource.com/device/google/cuttlefish/+/refs/heads/android17-release ; https://android.googlesource.com/kernel/common/+refs ; https://android.googlesource.com/platform/frameworks/libs/binary_translation/
- https://github.com/danbyumagic/gbrunch ; https://github.com/skylartaylor/gbos-vm ; https://gist.github.com/skylartaylor/236a69b2dc66f8536508451735cd521a
- https://github.com/sebanc/brunch ; https://github.com/android-generic ; https://blissos.org/status.html ; https://github.com/waydroid/waydroid ; https://github.com/google/android-cuttlefish
- https://github.com/DigitalisX64/digitalis ; https://chromeunboxed.com/a-user-has-installed-googlebook-os-onto-a-chromebook-plus-and-it-runs-great/ (2026-10-14)
- Unverified items still open: the Zen-5-only claim beyond early boot; how Digitalis performs; ANGLE requirements for Android 17 devices; Bliss 16.9.x build dates.
