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
| 3. Reconstruct | `openbook-adapt reconstruct`: the recovery zip read once, straight from the zip; GPT and liblp metadata parsed; `system`, `system_ext`, `product` and `vbmeta` kept; Google's vbmeta signature checked against the pinned key and each dm-verity root recomputed | **built** (phase 3; laptop 41 s) |
| 4. Adapt | `openbook-adapt adapt`: the **OpenBook layer** (OpenBook's exact delta against the Google build a release was made from) re-applied to Google's new `system` with the host rebase's carry rules, fail-closed; the **firmware-safety check** (ANAL-251's rules, below); `mkfs.erofs` with the host's flags; inventory and content checks; hash tree, footer and vbmeta (AVB test key, as today) | **built** (phase 3; laptop 32 s with the check; byte-identical to the host) |
| 5. Payload | `openbook-adapt payload`. The changed partitions are written in full as 2 MiB REPLACE operations (all-zero chunks as ZERO). The rest are identity copies: free under Virtual A/B, and update_engine verifies them against the installed release's hashes. Every dynamic partition is listed. The new build's timestamp and security patch let update_engine refuse a downgrade | **built** (phase 4). In QEMU, Ruby's own update_engine installs it into slot B, boots and merges it, finds the slot byte-identical to the release, and falls back from a broken slot |
| 6. Sign | **per-laptop OTA key**: RSA-4096 in Android Keystore (`LaptopKey`), created on the laptop and never exported. The app signs the payload's two hashes (PKCS#1 v1.5 over the DigestInfo, as update_engine verifies); the engine checks them against the key's certificate before inserting them. update_engine accepts them only once the certificate is in the running system's `otacerts.zip` (enrollment, one OpenBook update); until then the app builds and checks, but installs nothing | **built** (phase 4). The master OpenBook key stays on the build host |
| 7. Install | After the owner approves in the app, `InstallWorker` serves the payload on the loopback interface (unguessable path, byte ranges) and calls `UpdateEngine.applyPayload`. update_engine checks the signature and writes the other slot. Bootsync activates it; systemd-boot falls back after three failed boots; update_engine merges once the slot is marked good | **built** (phase 4); the install path was proven from the host on 2026-10-23 |

The fail-closed rules of the host rebase carry over unchanged. A Google change to a file OpenBook
patches stops the adaptation. The laptop keeps running and reports it; it never installs a guess.

### Firmware safety on the laptop (ANAL-251)

Googlebook images assume Google hardware. Google's init scripts start the security chip's firmware tools,
and Google's update postinstall flashes security chip, BIOS and EC firmware (`docs/ruby-firmware-safety.md`).
OpenBook neutralises them, and every OpenBook image is checked with `check-firmware-safety.py` against
`device/anybook/common/safety/firmware-safety.json`. Google's next release can bring new triggers, so the
laptop applies the same rules to every release it adapts, before anything is built:

- **What is checked.** The adapted `system`, Google's new `system_ext` and `product`, and the init scripts
  inside every APEX. EROFS is read in place, the one ext4 APEX through a small reader, compressed files
  through the laptop's `fsck.erofs`.
- **What it finds.** Each finding is one of:
  - a neutralised file that is not OpenBook's replacement;
  - an init script with a firmware/TPM/EC trigger that is unreviewed, or reviewed at a different SHA-256;
  - an unreviewed firmware tool by name;
  - a forbidden flasher.
- **Rules.** The running release's own `/system/etc/openbook/firmware-safety.json`, shipped with the
  adapter and checked against the layer byte for byte.
- **Outcome.** Any finding holds the release, with the reason, in the app. So do missing rules and content
  the check cannot read. A Google change to a reviewed file holds it too, until OpenBook reviews the change
  and ships the updated rules.
- **Scope.** It reads everything the host check reads, and also what Android's init reads beyond it:
  - every file in an `etc/init` directory, whatever its name;
  - an APEX's versioned scripts (`etc/*rc`, e.g. `netbpfload.35rc`).

  A compressed APEX holds instead of being skipped. On Google 16658739 and 16452207, RB-20261023-03 and the
  test release, it gives the host check's findings and inventory exactly.
- **Payloads.** The payload writer refuses any partition with a postinstall step, so an OpenBook payload
  runs nothing at install.

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

### How it is built (phase 2, 2026-10-23)

- **App:** `device/anybook/common/updater/app/`, Kotlin + Jetpack Compose + Material 3, package
  `org.openbook.update`. A privileged app in `/system/priv-app/OpenBookUpdate`, signed with the OpenBook app
  key (RSA-4096; private key on the build host only, `make-app-key.sh`). The release APK is
  byte-reproducible (`build.sh --reproducible-check`) and pinned by SHA-256 in `app-pins.json`.
- **Engine:** `openbook-updater` ships inside the APK (pinned in `pins.json`; the build stops if it differs),
  is copied into the app's private files and runs as the app's child process in the app's own domain. Its
  output goes to a file, so a stop request (SIGTERM, then SIGKILL after 10 s) never cuts it off: it ends
  its transfer and records `stopped`, and the next run resumes the partial file.
- **Background work:** WorkManager. A daily or weekly check (network connected); a check when the app
  opens after 12 hours; the download only on unmetered networks with enough storage, as a visible
  foreground job with a progress notification. Each release is announced once.
- **Kinds of release.** The engine classifies each release from the two Android build IDs. A build ID such
  as `CL3B.260622.276.R4` starts with its release train: a year letter (C = 2026), a product letter, the
  quarter (3) and a variant. A new Android version arrives with a new train (the year letter alone does
  not tell it: Android 17 shipped under C with the second quarter), so only the train decides:

  | Kind | From the build IDs | Handling |
  |---|---|---|
  | Monthly update | same train (first three characters), same or later branch date | downloads on Wi-Fi; adapting it on the laptop comes with phase 3 |
  | Quarterly release | a later train of the same product (possibly a new Android version) | held: OpenBook checks the adaptations against it and delivers it as an OpenBook update |
  | Unrecognized | unparseable, an earlier train or date, another product | held for review |
  | Beta | listing channel other than STABLE | ignored |
  | Google Play system updates | (APEX, via Google Play) | outside this app |
  | OpenBook's own updates | (update_engine, e.g. from a computer) | shown as installing / restart to finish |

  Google's real step from 16452207 (`CL3B.260622.271.R1`) to 16658739 (`CL3B.260622.276.R4`) is a monthly
  update by this rule. A release that changes a file OpenBook adapts, or no longer fits, stops at the
  adaptation (phase 3).
- **Install and restart:** in phase 2 the app watches update_engine (status and progress) and restarts
  into an installed update only after the owner confirms, through `PowerManager.reboot` (REBOOT, its only
  privileged permission, allow-listed in `privapp-permissions-org.openbook.update.xml`). After the restart
  it reports the result from the A/B slot it came back on: updated, or "went back" after a fallback.
  From version 2.0 the app installs a release the laptop built itself (phases 3–4). On a system without the
  adapter, the checklist still shows those steps as "comes with a later OpenBook update".
- **SELinux:** in this image only Google's updater (`gmscore_app`) and system components may call
  update_engine; the ordinary privileged-app domain (`priv_app`) cannot. So the app has its own domain,
  `openbook_update_app` (`app-sepolicy.cil`), built like Google's `vmlauncher_app`: `priv_app_all` (what any
  privileged app may do) plus binder calls to update_engine. The statements Android gives every app
  domain (shared memory, userfaultfd, the per-domain neverallows) are derived from what the image's policy
  gives Google's six app domains, so they follow Google's policy; the rebase checks them against each new
  one. `plat_seapp_contexts` selects the domain only for this package signed with the OpenBook certificate
  (seinfo `openbook` in `plat_mac_permissions.xml`). The policy is compiled with the image's own inputs,
  neverallows included, and the app context is checked with `checkseapp`. Accepted for phase 2: binder
  access to update_engine cannot be narrowed to status calls, and the network-facing engine runs in the
  same domain (its input is TLS from dl.google.com, parsed by a fixed awk reader). In 2.0 the adapter also
  runs there, as the engine's child. It parses images whose integrity Google's signature proves first.
  It is a static binary from Go's standard library: it ran under Android's app seccomp filter on the
  emulator, and as adb's shell on the laptop. Its first run in this domain on the laptop comes with the
  first Google release after R1. A denial there stops it before anything is installed. A narrower domain
  of its own remains a hardening step.
- **Privileged permissions:** this image does not enforce the privileged-permission allow-list
  (`ro.control_privapp_permissions` is unset), so the builder is the gate: every signature or internal
  framework permission the APK requests (`uses-permission` and `uses-permission-sdk-23`) must be in
  `privapp-permissions-org.openbook.update.xml`, which holds REBOOT only.
- **Users:** Googlebook runs a headless system user (user 0) beside the owner's. Only an admin user (the
  owner) runs checks and downloads and may restart; a guest or other user sees who manages updates. The
  sysconfig installs the app for full users, not guests, on a first boot; an OpenBook update keeps Google's
  fingerprint, so there the app also exists for the headless user and stays idle in it.
- **Notifications:** pre-granted on a first boot (`default-permissions-org.openbook.update.xml`). Android
  applies default grants only on a first boot or a new build fingerprint, and an OpenBook update keeps
  Google's fingerprint: there, the app asks once when opened, and shows "Notifications are off" until
  allowed. A notification that could not be shown is shown at a later check (it is recorded as announced
  only once it was posted); "restart to finish" is posted again whenever update_engine still waits.
- **After a restart:** "updated" when the laptop came back on the other slot. "The new version didn't start"
  only after a restart the owner confirmed in the app and a return to the same slot; otherwise (a waiting
  update withdrawn meanwhile, or an unreadable slot) nothing is claimed. OpenBook's update tooling
  (`g14-ota.sh`) tells the app when it staged an update (a receiver only the shell or system can call), so
  "Restart to finish" appears at once.
- **App updates:** each app version gets its own directory (`OpenBookUpdate-v<versionCode>`): Android caches
  parsed packages and trusts an unchanged path while the build fingerprint stays Google's.
- **Battery:** exempt from power saving like Android's own updater (`sysconfig`), so a download found in
  the background may run as a foreground job.
- **Carried forward:** `rebase-google-build.py` re-applies all of it to each new Google build: added paths;
  appended policy, file contexts and app contexts; the signer inserted again before `</policy>`; the policy
  compiled again and the app contexts checked against it. A conflict stops the rebase.

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
2. **The OpenBook Update app, with the engine and approval flow** — built 2026-10-23
   (`device/anybook/common/updater/app/`; evidence `evidence/2026-10-23-update-app/`).
   - Toolchain, app, its SELinux domain and privileged permissions, in the OpenBook layer.
   - Tested on Google's Android Desktop emulator and in the Ruby VM (see the evidence README).
   - Delivered as one two-slot update after the owner approves.
3. **Reconstruct and adapt on the laptop** — built 2026-10-24 (`device/anybook/common/updater/adapt/`;
   evidence `evidence/2026-10-24-adapt-phase3/`).
   - `openbook-adapt`: one static Go binary (standard library only, reproducible with the pinned official
     Go toolchain). It holds the EROFS inventory, AVB (hash tree, footer, vbmeta, signing), GPT/liblp
     parsing, the layer and the carry rules, each checked against the host tool it replaces.
   - On the G14, from Google's real 7.8 GB download (fetched by the engine): RB-20261023-03's `system`
     and `vbmeta` rebuilt byte for byte from Google 16658739 and its layer. A layer made on 16452207,
     adapted to 16658739, gives the host's result byte for byte.
   - Shipping: `build-update-app-candidate.py --adapter` adds three things:
     - the pinned binary;
     - AOSP's AVB test key, whose hash is pinned so no other key can ship;
     - the firmware-safety rules.

     It rejects a candidate that fails those rules, so build it on a base with ANAL-251's change. The order
     is `build-safety-candidate.py`, then `--adapter`. `embed-adapter-layer.sh` gives a release its layer
     with the same adapter, and the firmware-safety check runs inside it. A release built this way is a
     fixed point: adapting the same Google build with the layer it carries reproduces it byte for byte.
   - Firmware safety (ANAL-251, 2026-10-24; evidence `evidence/2026-10-24-adapt-firmware-safety/`). See
     "Firmware safety on the laptop" above. On the G14, a test release with ANAL-251's change and the adapter
     was adapted in 32 s, byte-identical to the host, the check passing. RB-20261023-03's own layer was held:
     it ships no rules, and under the rules Google's `gscutil` scripts would run.
4. **Payload, per-laptop key, install** — built 2026-10-24 (evidence `evidence/2026-10-24-adapt-phase4/`).
   - `openbook-adapt payload` is checked with Google's own tools. delta_generator verifies the signature.
     `ota_extractor` applies it onto RB-20261023-02 and gives all 10 target partitions byte for byte.
   - In QEMU, Ruby's update_engine installs it: apply, boot and merge, the slot byte-identical, fallback.
   - The app (OpenBook Update 2.0):
     - adapts a verified download as local background work;
     - signs with this laptop's Keystore key once enrolled;
     - shows the real checklist, with held and failed reasons;
     - installs after the owner's review and confirmation.
   - Two OpenBook updates bring it to the laptop:
     - **R1** ships the adapter, its layer and firmware-safety rules, ANAL-251's neutralised security chip
       scripts and the app. The laptop then creates its key; the shell reads the certificate with
       `am broadcast -a org.openbook.update.action.LAPTOP_KEY`.
     - **R2** adds that certificate to `otacerts.zip`.

     From R2 on, the adapter carries the certificate to every system the laptop builds.
5. **End to end on Google's next release.** The laptop notices, downloads, adapts, verifies and installs
   it by itself. The owner approves the reboot.

## Safety rules for every phase

- Nothing writes a partition before verification:
  - Google's checksum;
  - the fail-closed adaptation;
  - the firmware-safety check;
  - the inventory check;
  - a signed payload with no postinstall step, checked again by update_engine.
- Installs go only to the other slot. The running slot stays bootable, and three failed boots return
  to it.
- Reboots happen only when the owner agrees or the laptop is idle, never while it is in use.
- No Google Mobile Services, images or keys are redistributed. The laptop fetches its own release from
  Google for its own use.
