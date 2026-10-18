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
  1. **microG as an optional add-on.** Apache-2.0, x86_64, so OpenBook can ship it. It needs a small framework patch that LineageOS already carries on Android 17. **Built (ANAL-210, §6):** the patch is in every image; the add-on comes on the stick and the installer offers it, off by default; microG's self-check is all green in Cuttlefish.
  2. **A GApps package the user brings.** Today the only current Android 17 x86_64 package we found is LiteGapps `x86_64/37`. It needs an install path into our dm-verity-protected `product` partition (§5, a design that still has to be prototyped).
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
| Apply to our tree | **Both apply unchanged** to our `frameworks/base` pin (`94b4c163`), and both products build (ANAL-210, §6) | C |

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

**Built in ANAL-210, with one change:** microG installs as normal apps in /data, not as a privileged preinstall. See §6.

### G2: "Install a Google apps package you provide" (optional, user-supplied)

**Shape (HYPOTHESIS until prototyped):**
- The wizard offers a step after the disk choice, with a file picker on the stick or a USB drive. OpenBook never downloads, mirrors or names a download link.
- It accepts an x86_64, SDK 37 package. LiteGapps' layout is the only current candidate.
- It checks that the archive contains only the expected packages and XMLs, and that every native library is x86_64.
- **The engine rebuilds `product`.** It copies the package's priv-apps and XMLs into a new EROFS image, regenerates its hashtree with `avbtool add_hashtree_footer`, and recomputes the vbmeta digest the loader passes. In the orange state, a key mismatch is allowed; dm-verity still protects the result.
- After first boot, Settings › About shows the GSF Android ID and the registration steps.

**Why not a Magisk-style overlay:**
- OpenBook has no root-manager layer.
- Read-write overlays on system partitions exist only with verity off (`adb remount`). We don't want that on users' machines.

### Not recommended

- Copying GMS out of the Googlebook image or the SDK desktop images, even locally inside the installer. Both licences forbid copying.
- arm64 GApps under the native bridge. GMS's native code would run translated; it is slow and fragile, and unnecessary when x86_64 exists.

## 6. G1 built: the microG add-on (ANAL-210)

Status as of 2026-10-17. Evidence: `evidence/2026-10-17-microg/`, starting with `SUMMARY.md`. Everything here ran in Cuttlefish or QEMU; **nothing has run on the G14 yet** (§6.7).

### 6.1 What ships

**In every image (both products): the framework patch**, `aosp/patches/frameworks/base/`:
- `0001` LineageOS `198fa72864` "Allow signature spoofing for microG Companion/Services" and `0002` `03da1783cb` "ServiceWatcher: Allow microG location provider to be installed in /data". Both are cherry-picked from `lineage-24.0` unchanged, with their authors, dates and Apache-2.0 headers. A trailer names the source commit.
- `0003` OpenBook: drops the `isDebuggable()` condition, so user builds behave as userdebug ones. We wrote it ourselves: lineageos4microg's equivalent four-line patch is GPL-3.0.
- All three apply to our pin `94b4c163` with `scripts/aosp-patches.sh`. Both products build.

**In the PC product (the G14): `openbook-addons` and its catalogue.**
- `device/anybook/common/addons/`: a small C service and `/system_ext/etc/openbook/addons/microg.json`.
- The catalogue pins each APK by sha256 and size, and lists the permissions to grant. **The image carries no APK.**

**The add-on, outside the image and outside git.** It holds microG's own release APKs, unchanged:

| File | Package, version | Size | sha256 |
|---|---|---|---|
| `com.google.android.gms-252432034.apk` | microG Services (GmsCore) 0.3.17.252432 | 108 MB | `e5e6cba0…` |
| `com.android.vending-84022634.apk` | microG Companion 0.3.17.40226 | 4.2 MB | `9b861601…` |
| `com.google.android.gsf-8.apk` | microG Services Framework Proxy v0.1.0 | 21 KB | `86891b17…` |

`scripts/microg/fetch.sh` checks every file against the catalogue (C, `evidence/…/fetch/VERIFIED.txt`):
- sha256 and size;
- the APK signing certificate: one signer, SHA-256 `9bd06727…`. It is the same value in three places: in LineageOS's patch, on microg.org's download page, and in microG's F-Droid repo fingerprint;
- package name and versionCode;
- microG's OpenPGP signature (key `22F796D6E62E6625A0BCEFEA7F979A66F3E08422`, "microG Project Team"), for GmsCore and Companion. The proxy (2016) has no published signature. GitHub and microG's F-Droid repo serve the same bytes.

**Why the proxy:**
- microG's self-check has an item "microG Services Framework installed", so the proxy is needed for an all-green result.
- It targets SDK 23, below Android 17's minimum installable target (24). Its catalogue entry is the only one with `bypass_low_target_sdk`, PackageManager's own install flag for exactly this.

### 6.2 How it reaches users: an add-on, installed as normal apps

**Decision: option (a), the add-on, not a product variant.** This is LineageOS's own model. The two patches exist so that microG works as ordinary apps in /data; making that possible is the whole point of `03da1783cb`.
- **One image.** It is identical whether someone wants microG or not. There is one image to build, sign and test.
- **Updates and removal.** microG updates come from microG's F-Droid repo (same certificate) without an OS update. Users remove it like any app.
- **The cost.** A /data app gets no privileged permissions: privapp allowlists, default-permission XMLs and sysconfig apply only to system-partition apps. `openbook-addons` grants the runtime permissions microG's self-check asks for instead. The self-check is still all green (§6.4).
- **No location overlay needed.** AOSP 17's defaults (`config_enableNetworkLocationOverlay` and `config_enableFusedLocationOverlay` both `true`) let any matching provider in, and `03da1783cb` admits microG from /data.
- `config_locationProviderPackageNames` only drives default grants to system packages, so it stays as it is.

**The flow:**
1. **The stick.** `scripts/microg/make-addon.sh` and `add-to-image.sh` put `openbook/addons/microg/` on a live image's EFI partition. They work on image files only; the owner's stick is then written with `write-stick.sh`. Without the add-on, a stick is exactly as before.
2. **Every start: `openbook-addons`.** Init starts it once, after `sys.boot_completed`. It looks for the folder on the boot partition, the one `androidboot.boot_part_uuid` names. It reads the partition through the whole-disk node at its offset and never writes it.
   - **No folder:** it logs "not on the boot disk" and stops.
   - **A folder:** it checks every APK against the image's pins. One missing or different file refuses the whole add-on.
   - Then it installs the APKs as normal apps through PackageManager: `cmd package install-create/-write/-commit`, with the bytes on a pipe.
   - It grants GmsCore coarse, fine and background location, storage read and write, accounts, notifications, phone state, SMS receive and `INTERACT_ACROSS_USERS` (a `development` permission). It also sets the `SYSTEM_ALERT_WINDOW` app-op and exempts GmsCore from battery optimisation. Companion gets notifications.
   - It records the version in `/data/misc/openbook_addons/`, so an app the user uninstalls stays uninstalled.
   - A later image that pins a newer microG only upgrades the apps still installed. It grants nothing again, so it cannot bring back an app the user removed or undo a permission the user changed.
   - Its own SELinux domain, `openbook_addons`, is modelled on AOSP's `aflags`, which also runs `cmd`.
3. **The installer.** When the stick carries the add-on, the disk screen shows a switch, **"Google services compatibility (microG)", off by default.**
   - **Ticked:** the plan gains a `check_addon` operation. The engine checks the APKs against the image's pins before writing anything, copies them to the new disk's EFI partition, and reads them back in `verify`. The installed system's first start then installs them as in step 2.
   - **Not ticked:** the plan is byte for byte what it was before add-ons existed. `main`'s engine accepts it and recomputes the same sha256.
   - Protocol: `hello` lists `addons`, `plan` takes `"addons": ["microg"]`, and the CLI has `openbook-install addons` and `plan --addon NAME` (`device/anybook/common/installer/PROTOCOL.md`).
4. **Taking it off.**
   - Uninstall the three apps in Settings › Apps; they stay off.
   - On a stick image, `add-to-image.sh --remove` deletes the folder.
   - On an installed disk the folder stays on its EFI partition. Wiping /data (a reset) installs microG again, because the state lives in /data.
5. **microG's own defaults stay microG's.** Device registration, Cloud Messaging and online location lookup stay off until the user turns them on in microG's settings. OpenBook does not change them.

### 6.3 The security trade-off

**What the patch does.** Three conditions must all hold:
- the package is exactly `com.google.android.gms` or `com.android.vending`;
- it is signed with microG's release certificate (`9bd06727…`) and nothing else;
- it asks for exactly one fake signature, Google's platform-services certificate (SHA-256 `f0fd6c5b…`).

Then PackageManager reports Google's certificate to every app that asks, through both `GET_SIGNATURES` and `GET_SIGNING_CERTIFICATES`, and lets the package be force-queryable. Nothing else is spoofed. PackageManager's own decisions still use the real certificate: updates, signature permissions and shared UIDs.

**Dropping `isDebuggable()`.**
- LineageOS limits spoofing to userdebug builds. Our user builds would follow the same three conditions.
- **The risk:** whoever holds microG's signing key (the microG project) can make an APK that apps treat as Google Play services. Such an APK would receive their push messages, FCM tokens, sign-in requests and SafetyNet calls. That is the trust every microG user already places in that project.
- **Scope of that risk:** if the key were stolen, every OpenBook with the patch would be exposed, with or without the add-on, but only once such an APK is installed. Today that takes either the user's own sideload or the add-on, whose exact bytes the image pins.

**The patch is in every image, even when the add-on is not used.**
- Without a microG-signed package it does nothing. We show that in Cuttlefish and in the plain QEMU boots (§6.4).
- A user who installs microG from microG's F-Droid repo gets the same behaviour as with the add-on.

**The add-on's trust anchor is the verified image.**
- The catalogue with its pins sits on `system_ext`, under dm-verity.
- The EFI partition is plain FAT, so its contents are untrusted. Anything that does not match the pins is refused before installation (host tests: tampered, missing, path in the name).

**Permissions.** The grants are what the user would otherwise grant in microG's self-check. Background location, SMS and phone state are sensitive; the user can revoke any of them.

**What OpenBook does not do:** spoof Play Integrity, SafetyNet verdicts, build fingerprints or attestation. Apps that need `MEETS_DEVICE_INTEGRITY` still refuse (§4).

### 6.4 Results

| Check | Where | Result | Evidence (`evidence/2026-10-17-microg/`) |
|---|---|---|---|
| Patches apply, both products build | AOSP lane, our `CP2A.260605` tree | `frameworks/base: base 94b4c163 + 3 patches`; Cuttlefish product in 5 min 10 s; G14 product in 5 min 31 s, with `openbook-addons` and its SELinux domain | `build/` |
| Without microG: nothing changes | Cuttlefish | 151 packages, no `com.google.android.gms`; AOSP's fused provider, no network provider; no JNI or system_server error | `cf-baseline/` |
| **Negative test** | Cuttlefish | A `com.google.android.gms` that asks for Google's certificate but is signed with a throwaway key: **both APIs return its own certificate** (`32b8ad52…`), not Google's (`f0fd6c5b…`) | `cf-negative/negative-test.txt` |
| Install through `openbook-addons` (the image's code, `--from-dir`) | Cuttlefish, real PackageManager | 3 packages installed in 5.4 s; 11 grants, app-op and battery exemption all ok | `cf-microg/addons-install.txt` |
| Signatures apps see | Cuttlefish | GmsCore and Companion report Google's certificate (SHA-1 `38918a45…`, the value microG's self-check compares) | `cf-microg/sigcheck-after.txt` |
| **microG self-check** | Cuttlefish | **18/18 green**: signature spoofing, the three packages and their signatures, 11 permissions, battery optimisation | `cf-microg/selfcheck-*.png`, `selfcheck-results.txt` |
| An app the user uninstalled | Cuttlefish | `openbook-addons` reports "already installed", and the app stays uninstalled | `cf-microg/addons-rerun-after-uninstall.txt` |
| **Device registration and push** | Cuttlefish, internet over the VM's Wi-Fi | Check-in succeeded (Google assigned an Android ID). MCS logged in to `mtalk.google.com:5228`. **Home Assistant, Bitwarden and Nextcloud each got an FCM token from Google through microG** at first launch | `cf-push/`, `cf-gms-apps/` |
| Location | Cuttlefish | After one restart, microG (in /data) is the network and fused provider. Fixes: GPS (the VM's simulated GNSS) yes; fused, high accuracy, yes (GPS, 300 ms); fused balanced and network: none (§6.5) | `cf-location/location.txt` |
| Play-services apps | Cuttlefish | With microG: 4/4 start, 0 crashes, 3 push tokens. Without: 4/4 start, Play services missing, no push (`docs/COMPAT-MATRIX.md`) | `cf-gms-apps/` |
| SELinux | Cuttlefish (enforcing) | No denial involves microG or `openbook-addons` | `cf-microg/avc.txt` |
| `openbook-addons`, host tests | Image files, a fake `cmd` | **37/37**: absent, install, again, uninstalled, kept, upgrade, tampered, missing, commit fails, grant fails, bad catalogue, from-dir, status | `host/addons-test/` |
| Installer add-on path, host tests | Image files, a live image | **19/19**, including "a plan without add-ons is accepted by `main`'s engine". The ANAL-191 engine suite: **63/63** | `host/engine-addon-test/`, `host/engine-regress/` |
| G14 live stick, add-on path | QEMU/KVM + OVMF, enforcing | image `g1a`: the add-on installs under enforcing on the live stick and on an installed disk's first start (self-check 18/18), the wizard's switch off by default, the plain stick has the same 140 packages as `main`'s image. One denial per boot from `stdio_to_kmsg`, removed in `f7df42d` (rerun pending the build lane) | `qemu-g1a/` |

### 6.5 Limits found

- **microG's version lags.** microG reports Play services 25.24 (`252432034`). Home Assistant, Bitwarden and Nextcloud were built for 26.12 (`261200000`) and log "Google Play services out of date" for one internal API. Their FCM registration works all the same.
- **No location fix from microG in the VM** (C), for three reasons:
  - the VM's Wi-Fi access point is synthetic;
  - microG's online lookup is off until the user turns it on;
  - with a modem present (Cuttlefish emulates one), microG does not use its IP fallback (`considerIp = !hasTelephony`, GmsCore source).
- **On the G14 (HYPOTHESIS until tested):** it has neither a GPS nor a modem. Location there would come only from microG's online Wi-Fi lookup, after the user turns it on, with the IP fallback.
- **The network provider appears from the second start after the install.** Android registers a network provider at boot only if one exists then. The fused provider switches over at once.
- **Push delivery is not tested.** Check-in, the MCS connection and token issuing are proven. A message needs the app's own server; the owner can test one with a messaging app on the G14.
- **Space on the stick.** The add-on is 112 MB. A plain stick's 256 MiB EFI partition has about 220 MB free, so microG and the graphics check (86 MB) don't both fit.
- **Updates.** microG updates come from microG's F-Droid repo (`https://repo.microg.org/fdroid/repo`, same certificate). A newer add-on needs an image with newer pins.
- **F-Droid as an add-on** (allowed by ANAL-210's scope) is not built. The catalogue mechanism takes it as one more JSON file; it waits for the owner's go-ahead.

### 6.6 Reproduce

```bash
scripts/microg/fetch.sh                       # microG's APKs into <data dir>/dl/microg/<version>/, checked against the catalogue
scripts/microg/make-addon.sh                  # <data dir>/installer/out/openbook-microg-<version>-addon/
scripts/microg/add-to-image.sh IMG ADDON_DIR  # onto a live image file (--remove IMG takes it off)
scripts/microg/addons-test.sh RUN             # openbook-addons host tests
scripts/microg/engine-addon-test.sh LIVE.img ADDON_DIR RUN   # the installer's add-on path, against main's engine too
scripts/microg/build-test-apks.sh             # the signature/location checker and the negative-test APK
scripts/microg/addon-qemu.sh IMG MAIN_IMG ADDON_DIR RUN all  # the G14 image in QEMU: plain, main, add-on, install
ADB="adb -s …" scripts/microg/gms-apps.sh LABEL OUTDIR       # Play-services apps on a device, with or without microG
```

### 6.7 On the G14

The owner's checklist goes on ANAL-192's next stick. It is posted there as a comment, with the exact steps and the expected output.

## Owner decisions (2026-10-17)

1. **G1 (microG):** approved. The patch and the add-on are ANAL-210; built and tested (§6).
2. **G2 (bring your own GApps):** approved. It is ANAL-211, worked in parallel with G1, behind an "advanced" step that the user must confirm. Its tests use a synthetic package only.
3. **Track B (Google's whole image, `docs/PLAN.md` §6)** is unchanged by this. It remains the only way to get the real Googlebook launcher and apps, and it stays parked until you decide.

## Sources

The research tables carry URLs and dates. Primary sources:
- github.com/MindTheGapps/vendor_gapps
- sourceforge.net/projects/litegapps
- github.com/microg/GmsCore (releases, wiki)
- github.com/LineageOS/android_frameworks_base commits `198fa72864` and `03da1783cb` (branch `lineage-24.0`, read 2026-10-17)
- github.com/microg/GmsCore at `v0.3.17.252432` (self-check, location and push code), github.com/microg/GsfProxy `v0.1.0`, microg.org/download.html and repo.microg.org/fdroid/repo (signing certificate fingerprint), keys.openpgp.org (microG's OpenPGP key `22F796D6…`), all 2026-10-17
- github.com/lineageos4microg/docker-lineage-cicd `src/signature_spoofing_patches/` (the user-build patch, GPL-3.0; we wrote our own), 2026-10-17
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
