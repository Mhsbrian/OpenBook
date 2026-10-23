# OpenBook Update, the on-laptop updater app (ANAL-229, phase 2, 2026-10-23)

The owner asked for a visible, themed updater app with notifications. It must ask for the owner's
approval before installing, and confirm before restarting. It must not be a hidden background service.
This is that app, built, reviewed and tested. It is not on the laptop yet: that needs the owner's
approval, through the release hub.

Design: `docs/googlebook-on-device-updater.md`. Build: `docs/BUILD.md`.

## What was tested

The APK is the clean, reproducible release build of commit `367090f`:
- `OpenBookUpdate.apk`, signed SHA-256 `f3308832e914314ce73b0e141142101033280bf18d4bbd8c08e6d241732953c5`;
- pinned in `device/anybook/common/updater/app-pins.json`;
- provenance in `build.json`, signature check in `apksigner-verify.txt`.

The emulator and the Ruby VM ran these exact bytes.

| Evidence | Result |
|---|---|
| Engine, host (`openbook-updater-test.py`) | 32/32 on the host's shell, and 32/32 on Android's own mksh R59, one-true-awk and toybox (`engine-test-env.sh`) |
| App unit tests (JVM) | 19/19. Lint clean on debug and release; no compiler warnings |
| Build | `build.sh --reproducible-check`: two clean builds are byte-identical. Gradle runs in bubblewrap with the system read-only and the key directory empty. The toolchain is pinned |
| Emulator: Google's Android Desktop, API 37.1 (`emulator/`) | Engine on the emulator's own tools: 9/9 (`engine-device-test.txt`). Instrumented tests: 8/8 (`instrumentation-summary.txt`) |
| Emulator: system app | The release APK as a privileged system app: REBOOT granted, battery-exempt, started at boot for the owner (user 10), first check ran (`system-*.txt`, `logcat-system-boot.txt`, screenshots) |
| Screens (`screenshots/`) | 54 PNGs: every state, light and dark, rendered on the emulator |
| Ruby VM (`vm/`) | **16/16** (`judge.json`): Google's Ruby 16658739 with OpenBook's layer (RB-20261023-02 base) and this app, fresh userdata, two slots (boot checks 9/9, `boot.json`). Privileged app for the owner only (user 0 without it); REBOOT and notifications granted; battery-exempt; runs as `u:r:openbook_update_app`; binds update_engine; boot work scheduled and the A/B slot read (`_a`); the engine's first check ran from the app's domain (exit 3: the VM has no network); the shell's refresh received; **0 denials for the app**; no app crash (`report.txt`). The image does not enforce privileged allow-lists (`ro.control_privapp_permissions` unset). QEMU's display stays dark (OpenBook's vendor drives AMD displays), so the screens are the emulator's |
| Production path (`candidate-production-check.json`) | The deployable candidate builds on RB-20261023-02. It has REBOOT as its only privileged permission, 31 app-domain statements derived from Google's policy, and no experimental parts. Not a release |
| Rebase (`rebase-same-build.json`) | The candidate, rebased from Google 16658739 onto the same build, gives a byte-identical `system`. The rebase carries the app, the policy, the app context and the signer exactly |

### What the emulator does not show

- **No OpenBook SELinux domain or update_engine.** The emulator's own policy has neither, so there the
  app runs as Google's `priv_app`. The Ruby VM shows the app's domain.
- **Notifications without a first boot.** After a restart with existing data (as an OpenBook update brings
  the app), the default permission grant does not apply. The app asks once when opened, and shows
  "Notifications are off" until allowed (`system-desktop-notifications-off.png`).

## Review

Three independent reviews in round 1 covered the app, the system integration and security, and the
engine. Round 2 checked the fixes. Every valid finding is fixed and tested, or recorded below as accepted.

**Engine:**
- Release kinds were read from the build ID's first letter, which is the year's release train, not the
  Android version (AOSP's own release configs show this). They now come from the train.
- A stop during the checksum could not interrupt it.
- A stop between the rename and the marker discarded a verified download.
- The listing parser allowed control characters to forge a row.
- Refused listings were reported as checksum failures.
- A check wiped "downloaded" and paused progress from view.

**App:**
- Guests and other users could run the updater and restart the laptop. Now only admin users run it.
- Any app could open the restart confirmation, and it reopened by itself. It now comes only through a
  non-exported alias, and is consumed.
- "Went back" could be claimed after an update was withdrawn. It is now claimed only after a restart the
  owner confirmed.
- "Waiting for Wi-Fi" was shown for every reason a download waits.
- A notification that could not be shown was marked as shown.
- The update_engine binding never recovered.
- An owner's pause was forgotten.
- A process was spawned on the main thread.
- A failure in background work could crash the app.

**System integration:**
- The app's SELinux domain lacked the shared-memory rules every app domain gets (seen in the VM as a
  `memfd:jit-cache` denial). The statements Google's app domains share are now derived from the image's
  policy, and the rebase derives them again from each new policy.
- `uses-permission-sdk-23` slipped past the permission check, and this image does not enforce the
  privileged-permission allow-list (`ro.control_privapp_permissions` is unset). The builder now reads the
  manifest and gates every signature permission.
- The APK signature was not verified by Android's own tool. `apksigner verify` now runs.
- The rebase's signer re-insertion was weaker than the builder's.
- No deployable candidate could be built, because the pin lacked provenance.
- A Gradle plugin could read or alter the signing toolchain.

**Accepted for phase 2, documented in the design doc:**
- Binder access to update_engine cannot be narrowed to status calls.
- The network-facing engine shares the app's domain. Its input is TLS from dl.google.com, read by a fixed
  awk parser.
- A second admin user would run their own copy.
- The release-train rule rests on Google's production build IDs seen so far. An unrecognized ID is held,
  never downloaded.

## Not tested here (before the laptop)

**The OpenBook-update path in QEMU.** That means booting the current release, applying this candidate as
a two-slot update with existing data, and booting it. Then check:
- the boot-time start for the owner, without opening the app;
- the app's domain, with no denials;
- the update_engine binding;
- the idle copy in the headless user;
- the "Notifications are off" banner.

This is part of the release build and rehearsal after the owner approves a release plan. It is not done
yet.

## Storage

- Disposable VM runs, the production-check candidate and the rebase test were removed after their records
  were taken. Each removal is recorded in the work directory's `cleanup-manifest.txt`.
- Kept: the toolchain (`~/anybook/toolchain`, about 2 GB), the signed builds, and the logs.
