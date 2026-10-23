# The on-laptop OpenBook updater (ANAL-229)

The goal: **the laptop itself** notices Google's new Googlebook release, downloads it, adapts it to
the G14 and installs it. No workstation and no assistant are involved. The host pipeline proved every
stage first:
- notice: `watch-google-ruby.py`;
- reconstruct: `reconstruct-google-release.py`;
- adapt: `rebase-google-build.py`;
- sign and install: `build-ruby-ab-ota.py`, `g14-ota.sh`.

This document maps those stages onto what the laptop can run, and gives the order of the work.

## What the laptop can do today

Read-only probe of the G14, 2026-10-23 (RB-20261023-02 = Google 16658739 patched for the G14,
running from slot B, user build, SDK 37, x86_64):

| Need | On the laptop | Note |
|---|---|---|
| Fetch over HTTPS | `curl` 8.16 (BoringSSL); `https://dl.google.com/…/production_recovery.json` → HTTP 200 | network reachable |
| Checksums | `md5sum`, `sha256sum` (toybox) | Google's listing gives the zip's MD5 |
| Text, JSON | `awk` (one-true-awk 20251225), `sed`, `grep`, `sort`, `cut`, `tr` | no `jq`, no Python |
| Shell | mksh R59 | **arithmetic is 32-bit**: byte counts must be done in awk |
| Locking | toybox `flock` (descriptor form only) | mksh closes `exec 9>` descriptors on exec; see the updater's re-exec |
| Archives | `unzip`, `tar`, `gzip` | |
| EROFS | **`mkfs.erofs`, `fsck.erofs`** | the core of the adapt stage is already there |
| Dynamic partitions | `lpdump` | no `lpunpack`/`lpmake`; LP extents + `dd` suffice to read a super |
| Verified boot | no `avbtool` | hash tree, footer and vbmeta signing must be built |
| Payloads | no `delta_generator` | must be built or replaced |
| RSA | no `openssl` | signing must be built (or use Android Keystore) |
| Installing | `update_engine` services `android.os.UpdateEngineService`, `…StableService`; `update_engine_client` | a privileged caller is needed (see below) |
| Storage | `/data` 928 GB, 905 GB free | a release zip is 7.8 GB; the image inside 19 GB |

## Stages on the laptop

| Stage | Component | Status |
|---|---|---|
| 1. Notice | `openbook-updater check`: Google's listing → newest STABLE build for `ro.product.device` → compare with `ro.build.version.incremental` | **built** (phase 1) |
| 2. Download | `openbook-updater download`: HTTPS only (redirects too), resume, free-space check with a reserve, Google's MD5, prune older downloads | **built** (phase 1) |
| 3. Reconstruct | `unzip` the recovery image; GPT + LP metadata (`lpdump`) → `dd` each partition; check against the release | to build (phase 3) |
| 4. Adapt | apply the **OpenBook layer** to Google's new `system`: OpenBook's exact delta against the Google build it was made for, shipped on the laptop as data. Then `fsck.erofs --extract`, apply, `build.prop` three-way merge, `mkfs.erofs` with the expected fs_config/file_contexts, inventory check, hash tree and footer, vbmeta | to build (phase 3): an Android build of `erofs-inventory`; a native hash tree, footer and vbmeta signer (AVB test key, as today) |
| 5. Payload | an update_engine payload from the installed slot to the adapted release | to build (phase 4): `delta_generator` for Android x86_64, or a minimal full-payload writer |
| 6. Sign | **per-laptop OTA key**, generated on the laptop, never exported. Its certificate is enrolled in that laptop's `otacerts.zip` by the adapt stage, so every system it builds trusts it. The first enrollment arrives as one ordinary OpenBook update | to build (phase 4): native RSA signer or Android Keystore. The master OpenBook key stays on the build host |
| 7. Install | `update_engine` applies the local payload into the other slot. Bootsync activates it, systemd-boot falls back after three failed boots, and update_engine merges once the slot is marked good | proven from the host (2026-10-23); the on-laptop caller is phase 2/4 |

The fail-closed rules of the host rebase carry over unchanged. A Google change to a file OpenBook
patches stops the adaptation. The laptop keeps running and reports it; it never installs a guess.

## OpenBook Update: the app the owner sees and approves

The updater is not a background process the owner never sees. It is a system app, **OpenBook Update**,
with notifications and an explicit approval before anything is installed (owner's requirement,
2026-10-23):

1. **Up to date:** the Googlebook build, its security patch, when it last checked; *Check now*.
2. **Update found** (notification): Google's build and security month. The download runs on unmetered
   Wi-Fi only, automatically if the owner allowed that, otherwise after a tap.
3. **Preparing**, as a live checklist:
   - downloaded from Google, checksum verified;
   - checked against the G14 adaptations (trackpad, ARM apps, update certificate, AMD drivers);
   - G14 version built;
   - verified.
   If Google changed something OpenBook patches, the app says so and stops. It never guesses.
4. **Ready to install** (high-priority notification). The review screen shows:
   - what is new (Google build, security patch);
   - what OpenBook re-applied;
   - that apps and files stay;
   - that it installs into the second system slot, and the laptop returns to the current version
     automatically if the new one does not start.
   Actions: *Install and restart* / *Install now, restart later* / *Not now*.
5. **Confirmation:** "Install update and restart? Save your work first." Nothing installs without it.
6. **After the restart** (notification): "Updated to …, all checks passed", or, after a fallback, "The new
   version didn't start, so your laptop went back to … Nothing was lost."
7. **Settings and history:** automatic download on Wi-Fi, check frequency, "always ask before
   installing" (on, and not removable for system updates), past updates with their results, details.

Look: Material You (dynamic colour from the wallpaper), the Googlebook system typography, and an
"OpenBook" mark on the update-specific screens.

### How it is built

- **App:** Kotlin + Jetpack Compose, Material 3. A privileged app in `/system/priv-app`, signed with an
  OpenBook app key (private key on the build host). It is added through the OpenBook system layer, so
  `rebase-google-build.py` carries it onto every Google build.
- **Engine:** `openbook-updater` (already built and tested) runs as the app's child process in the app's
  own SELinux domain. Phase 3/4 tools join it there. Checks are WorkManager jobs, visible in Android's
  settings like any app's.
- **Install:** the proven update_engine path. The app serves its own signed payload on `127.0.0.1`
  (update_engine is allowed to fetch HTTP and was shown to apply it on this laptop), then calls
  `update_engine_client`.
- **Restart:** only after confirmation, through Android's reboot API: the REBOOT permission, allow-listed
  for this one privileged app.
- **SELinux:** a dedicated app domain chosen by `seapp_contexts`/`mac_permissions.xml` for this package
  and its certificate, both of which we own. It gets only:
  - the network (for the engine);
  - its own app data;
  - running its shell and tools;
  - binder calls to update_engine.
- **No init service:** the earlier init-service variant (`openbook-updater.rc`) was VM-tested but will
  not ship; the app replaces it.

## Phases

1. **Notice and download** — built 2026-10-23 (`device/anybook/common/updater/`; evidence
   `evidence/2026-10-23-updater-phase1/`).
   - Host tests: 19.
   - On the laptop, 7 scenarios with `openbook-updater-device-test.sh`, from a temporary directory
     over adb (nothing installed):
     - against Google's live listing it reports up to date (16658739);
     - a synthetic newer release is downloaded and verified, and a repeat run is re-hashed;
     - an MD5 mismatch is refused and cleaned up;
     - a reserve beyond 32 bits is refused correctly;
     - a concurrent run is refused.
   - Two code reviews; every valid finding fixed and tested.
   - Not yet run: a full-size download. The laptop is on the newest build, so there is nothing real
     to fetch.
2. **The OpenBook Update app, with the engine and approval flow.**
   - Toolchain, app, its SELinux domain and privileged permissions, in the OpenBook layer.
   - Shown in the VM: screens, notifications, check and download.
   - Delivered as one two-slot update after the owner approves.
3. **Reconstruct and adapt on the laptop.**
   - Android builds of the inventory checker and an AVB signer; the OpenBook layer as on-laptop data.
   - Proven by adapting 16658739 on the laptop and comparing the result with the host's rebase
     (`75fa0196…`): content, inventory and vbmeta descriptors.
4. **Payload, per-laptop key, install.** On-laptop payload and signing; key enrollment through one host
   update; the first fully on-laptop update.
5. **End to end on Google's next release.** The laptop notices, downloads, adapts, verifies and installs
   it by itself. The owner approves the reboot.

## Safety rules for every phase

- Nothing writes a partition before verification:
  - Google's checksum;
  - the fail-closed adaptation;
  - the inventory check;
  - a signed payload, checked again by update_engine.
- Installs go only to the other slot. The running slot stays bootable, and three failed boots return
  to it.
- Reboots happen only when the owner agrees or the laptop is idle, never while it is in use.
- No Google Mobile Services, images or keys are redistributed. The laptop fetches its own release from
  Google for its own use.
