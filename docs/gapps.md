# Google apps on OpenBook: an optional, user-installed "GApps" (ANAL-201)

As of 2026-10-17. Labels: **C** = confirmed (we read it from a primary source, or from an image ourselves), **R** = reported (press or third party), **U** = unverified, **HYPOTHESIS** = not yet tested. Why Googlebook looks the way it does is covered in [`googlebook-ui.md`](googlebook-ui.md). Evidence is in `evidence/2026-10-17-gbos-ui/`.

## Summary

- **OpenBook images can never contain Google apps.**
  - GMS is licensed to device makers only (MADA/EMADA). The GSI+GMS images and the Android SDK system images allow testing and app development, and forbid redistribution.
  - Any Google apps on OpenBook have to come from the user. The alternative is microG, which is open source.
- **Google apps don't make the desktop look like Googlebook.**
  - Google's own Google APIs Desktop image has the same GMS as Googlebook and still shows AOSP's launcher, SystemUI and Settings.
  - The Googlebook look comes from platform components (Pixel Launcher, a platform-signed SystemUI and Settings, fonts, overlays and flags). No GApps package contains those.
- **Options, best first:**
  1. **microG as an optional add-on.** Apache-2.0, x86_64, so OpenBook can ship it. It needs a small framework patch that LineageOS already carries on Android 17.
  2. **A GApps package the user brings.** Today the only current Android 17 x86_64 package we found is LiteGapps `x86_64/37`. **Built (ANAL-211, §5):** an advanced installer step that checks the package and puts its apps into a rebuilt, dm-verity-protected `product` partition.
  3. **Not viable:**
     - arm64 GApps such as MindTheGapps, NikGApps and BiTGApps. MindTheGapps dropped x86 after Android 13.
     - GMS copied out of the Googlebook or SDK images (their licences).
     - Transplanting Googlebook's UI apps (platform key).
- **What users should expect with real GApps:**
  - "Device is not Play Protect certified" until they register their GSF ID with Google.
  - No `MEETS_DEVICE_INTEGRITY` or `MEETS_STRONG_INTEGRITY`. Probably no `MEETS_BASIC_INTEGRITY` either with software KeyMint (HYPOTHESIS).
  - So Google Wallet tap to pay, Netflix from Play and many banking apps won't work. **We don't bypass Play Integrity.**

## 1. What Google's desktop builds actually carry (C)

**The two images** (read offline, `inventory/googlebook-ruby-gms-apex.txt`, `inventory/*-packages.tsv`):
- Both the Googlebook ruby image and the Google APIs Desktop 37.1 image ship **GmsCore 26.22.43 inside an APEX**, `com.google.android.gmssystem.prodvic.apex` on `/product`:
  - `PrebuiltGmsCoreVic.apk` (x86_64 + x86, targetSdk 37);
  - a privileged-permission allowlist with 139 permissions;
  - a preinstall config;
  - `/product/etc/sysconfig/allowed_apex_com.google.android.gmssystem.xml` permits the APEX.
- The rest of the core:
  - `GoogleServicesFramework` (system_ext priv-app);
  - Play Store 52.4.41 (product priv-app, x86_64);
  - setup wizard;
  - partner setup;
  - ConfigUpdater;
  - GmsCore's dynamite modules;
  - `privapp-permissions-google*.xml`, `default-permissions-google.xml`, `google-hiddenapi-package-whitelist.xml`, `sysconfig/google.xml` and `preferred-apps/google*.xml`.
- **Signing:**
  - GMS, GSF, Play Store, Chrome and setup are signed with Google's own keys. That's why GApps packages work on other ROMs.
  - Googlebook's SystemUI and Settings are signed with the platform key (`inventory/googlebook-ruby-signers.txt`).
- **Size of the Google set:** Googlebook adds about 70 more Google packages on top of that core: desktop apps, AI services and Workspace stubs. The Google APIs Desktop image adds a dozen (Chrome, Gmail, Maps, Photos, YouTube, Gboard, the Google app).

**What a GApps install on OpenBook therefore needs:**
- the core packages as privileged system apps, with their permission and sysconfig XMLs;
- x86_64 native code;
- a `product` partition that can hold them. Ours is EROFS, checked by dm-verity on every boot even in the orange state (`docs/installer.md` §1.1, §2.1).

## 2. GApps packages today

| Project | Android 17 | x86_64 | How it installs | APKs from / stance | Source (date, label) |
|---|---|---|---|---|---|
| **LiteGapps** | SDK 37 and 36 | **Yes:** `x86_64/37/{core,lite}` (2026-09-30) | Magisk/KernelSU/APatch module, recovery, or adb sideload | MIT build tool; the APK source is not stated | sourceforge.net/projects/litegapps/files/litegapps/x86_64/37/ (2026-09-30, C) |
| **MindTheGapps** | arm64, `17.0.0-arm64` 20261006 | **No.** The last x86_64 builds are 12.1/13 (2023-10-25). "Drop x86 support (not updated since A13)", 2026-06-30 | Flashable zip, or build-time `vendor/gapps` makefiles | Pixel factory images; GmsCore "generally from APKMirror". The LICENSE disclaims ownership of the blobs | github.com/MindTheGapps/vendor_gapps, `cinnamonbun` branch (2026-10-06, C) |
| NikGApps | No public Android 17 folder (Android 16 arm64 only) | No | Recovery zip | GPL-3.0 tooling | sourceforge.net/projects/nikgapps (2026-10, C) |
| BiTGApps | Claims Android 17 | Claimed; no x86_64 Android 17 file visible | Recovery or module | Pixel OTA images (arm64) | bitgapps.io (2026-08, C claim / U x86_64) |
| Android-Generic `vendor_gapps` | Android 16 only (`dev/baklava`) | Yes, but **imported from `gsi_gms_x86_64` GSI images**, whose licence forbids distribution | Makefiles + zip | GSI+GMS | gitlab.com/android-generic/vendor_gapps (2026-09-08, C) |
| OpenGApps, FlameGApps | No (dead since 2022/2023) | Android 11 at most | — | — | github.com/opengapps (C) |

Prior art on x86:
- **Bliss OS** ships `gms` and `foss` builds and says GMS builds are "intended for individuals only". Its PC images have been paused since 2026.
- **Waydroid's** GAPPS image is LineageOS 20 (Android 13).
- **waydroid_script** installs OpenGApps (Android 11) or MindTheGapps 13 x86_64.

Nothing current in that space covers Android 17 x86_64 (C, research summary 2026-10-17).

## 3. microG

| Item | Finding | Label |
|---|---|---|
| Release | GmsCore **v0.3.17.252432, 2026-09-29** (security release). Apache-2.0. ABIs include `x86_64` | C (github.com/microg/GmsCore) |
| What works | Push (FCM), fused location and the Maps v1 API fully; Maps v2 mostly; Google sign-in partly; SafetyNet/Play Integrity at best `MEETS_BASIC`; no Wear | C (microG wiki, 2025-05) |
| Framework support | microG must present Google's signature. LineageOS commit **`198fa72864` "Allow signature spoofing for microG Companion/Services"** (on `lineage-24.0` = Android 17). It changes `ComputerEngine.java`, `AppsFilterImpl.java` and a small JNI file. Spoofing applies only if (1) the build is debuggable, (2) the package is `com.google.android.gms` or `com.android.vending`, (3) the APK is signed with **microG's release key** and (4) the requested fake signature is Google's. Companion commit `03da1783cb` lets microG's location provider live in /data | C (github.com/LineageOS/android_frameworks_base) |
| User builds | lineageos4microg removes the debuggable check with a one-line patch. CalyxOS instead uses a package allowlist plus a `FAKE_PACKAGE_SIGNATURE` permission (`android17` branch) | C |
| Apply to our tree | Not tried on `CP2A.260605` yet | U |

## 4. Play Protect certification and Play Integrity

- **Certification.** Google says only Play Protect certified devices may include Google apps. Its help page lists a modified OS and an unlocked bootloader as reasons a device is uncertified (support.google.com/googleplay/answer/7165974, C).
  - Custom builds register their **GSF Android ID** at `google.com/android/uncertified` (Waydroid documents the same steps, C).
  - The ID changes after a reset or reinstall.
- **Play Integrity verdicts** (developer.android.com/google/play/integrity/verdicts, updated 2026-10-06, C):
  - Since May 2025, on Android 13 and later, `MEETS_DEVICE_INTEGRITY` needs hardware-backed proof of a locked bootloader running a certified OS.
  - `MEETS_BASIC_INTEGRITY` "requires only that the attestation root of trust is provided by Google".
  - OpenBook runs unlocked (orange) with software KeyMint, so expect no DEVICE or STRONG verdict. **HYPOTHESIS:** without Google-rooted attestation, no BASIC either.
- **Apps that refuse:**
  - Google Wallet tap to pay (support.google.com/wallet/answer/12200245, C).
  - Netflix from Play (help.netflix.com/node/57688, C).
  - Many banking and government apps (grapheneos.org attestation guide, C).
- **Same image, other hardware.** GBRUNCH and gbos-vm run Google's own Googlebook image, and users report Play downloads working (gbos-vm issue #15, 2026-10-12, R). That is the Track B route, not OpenBook's.
- **We will not spoof fingerprints, attestation or verdicts.**

## 5. Recommendation and proposed design

### G1: "Google services compatibility (microG)", optional (shippable)

1. **Framework patch.** Add LineageOS `198fa72864` (and `03da1783cb`) as patches under `aosp/patches/frameworks/base/` (Apache-2.0), with the debuggable check dropped for our user builds.
   - The trust anchor stays narrow: two package names and microG's release certificate.
   - The trade-off: any APK signed with microG's key could claim Google's signature for those two packages.
2. **Ship microG's signed GmsCore and Companion as an installer add-on**, off by default. The installer and live stick already have add-ons (`docs/installer.md` §13.1).
3. **F-Droid as the open store.** Third-party Play clients (Aurora Store) are the user's choice. We don't bundle them, because they access Play outside Google's terms.
4. **Tests:** the microG self-check passes; FCM push in a test app; location through the network provider; the top-50 compatibility apps (`docs/COMPAT-MATRIX.md`) with and without microG.

### G2: "Install a Google apps package you provide" (optional, user-supplied)

**Built (ANAL-211, 2026-10-18; `docs/installer.md` §14).** Tested with synthetic packages only: OpenBook's own dummy APKs and XMLs in LiteGapps' layout (`scripts/gapps/`). No Google package was downloaded or used.
- **The wizard.** The disk screen has an off-by-default switch, "Install a Google apps package you provide (advanced)". Its page:
  - picks a file with the system file picker, from this stick's storage or a USB drive. OpenBook never downloads, mirrors or names a download link;
  - checks the file and lists every app with its package, version, privileged or not, native code, and its signer's name and SHA-256, or every refused path with its reason;
  - asks the user to confirm a warning: not Play Protect certified, the GSF ID to register, no Play Integrity device verdict (Wallet, Netflix, banking apps), the read-only `product` partition, and no workaround.
- **What it accepts** (`engine/gapps.c`). LiteGapps' layout, read from its MIT build scripts (`github.com/litegapps/litegapps` `764224e3`, 2026-10-03, C): a zip with `module.prop` (`litegapps_arch`, `litegapps_sdk`) and `files/files.tar.br`, `.xz` or `.tar`, whose tar holds `<arch>/<sdk>/system/product/…`.
  - Only below `x86_64/37/system/product/`: `priv-app/` and `app/` APKs, with their `lib/x86_64/` libraries; `etc/permissions`, `etc/sysconfig` and `etc/default-permissions` XMLs.
  - Refused, path by path: the framework (`framework/`, `overlay/`, APEX), init (`etc/init/`, `bin/`), SELinux, native libraries outside an app, other partitions, other ABIs and SDKs, links, unsafe names.
  - In the XMLs, refused element by element: shared libraries, split permissions, permissions assigned to system UIDs or mapped to Linux groups, and anything not on the allowlist.
  - APKs must be signed and must not claim `android.uid.*`. Their native code must include x86_64: ARM-only apps would run translated, and this image has no 32-bit ABI. Other ABIs in a multi-ABI APK are listed but never loaded.
  - It records each APK's package, version, SDK levels, ABIs and signing certificate in the install manifest (`openbook-gapps/1`). The new system keeps that manifest as `/product/etc/openbook/gapps-manifest.json`.
- **What it changes on the disk** (`engine/product.c`, `erofs.c`, `avb.c`, `lp.c`).
  - The new `product` is the stick's EROFS image plus the package's files. Its blocks are kept byte for byte; the new files, directories and inodes are appended, so compressed files are never re-encoded. New files carry the same SELinux label as their directory (`system_file`).
  - A new dm-verity hashtree (the stick's salt, no FEC) and AVB footer are written. `product_a` moves to a new extent in `super`.
  - `vbmeta_a` gets the new descriptor, **unsigned**. The bootconfig's `androidboot.vbmeta.digest` and `.size` follow it.
  - This is the orange state OpenBook already boots in: first-stage init allows the verification error and still sets up dm-verity from the new descriptor.
  - Without the step, installs are byte-identical to `main`'s.
- **After the install.** OpenBook setup's last step, and **Settings › About › Google apps registration**, show the GSF Android ID (from GSF's `gservices` provider) and the steps for `google.com/android/uncertified`.
- **Found while building it (C).** OpenBook images don't set `ro.control_privapp_permissions`, so Android doesn't enforce the privileged-permission allowlist: a package's priv-apps get every privileged permission they request, allowlisted or not. The plan warns about it (`privapp_allowlist_not_enforced`). Whether OpenBook should set `enforce` is a separate decision; it would also apply to OpenBook's own priv-apps.

**Why not a Magisk-style overlay:**
- OpenBook has no root-manager layer.
- Read-write overlays on system partitions exist only with verity off (`adb remount`). We don't want that on users' machines.

### Not recommended

- Copying GMS out of the Googlebook image or the SDK desktop images, even locally inside the installer. Both licences forbid copying.
- arm64 GApps under the native bridge. GMS's native code would run translated; it is slow and fragile, and unnecessary when x86_64 exists.

## Owner decisions (2026-10-17)

1. **G1 (microG):** approved. The patch and the add-on are ANAL-210.
2. **G2 (bring your own GApps):** approved. It is ANAL-211, worked in parallel with G1, behind an "advanced" step that the user must confirm. Its tests use a synthetic package only.
3. **Track B (Google's whole image, `docs/PLAN.md` §6)** is unchanged by this. It remains the only way to get the real Googlebook launcher and apps, and it stays parked until you decide.

## Sources

The research tables carry URLs and dates. Primary sources:
- github.com/MindTheGapps/vendor_gapps
- sourceforge.net/projects/litegapps
- github.com/microg/GmsCore (releases, wiki)
- github.com/LineageOS/android_frameworks_base commit `198fa72864`
- developer.android.com/google/play/integrity/verdicts
- android-developers.googleblog.com/2024/12 (Play Integrity changes)
- support.google.com/googleplay/answer/7165974
- android.com/gms
- android-developers.googleblog.com/2009/09/note-on-google-apps-for-android.html
- developer.android.com/topic/generic-system-image/releases (GSI+GMS licence)
- the Android SDK repository XML (`sys-img2-4.xml`)
- docs.blissos.org/legal/licensing
- github.com/casualsnek/waydroid_script
- github.com/danbyumagic/gbrunch, github.com/skylartaylor/gbos-vm
