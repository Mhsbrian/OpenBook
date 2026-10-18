# ANAL-216 (Quire Q2): platform hooks, Quire core as a privileged system app (2026-10-18)

The write-up is `docs/quire.md` §2.2–2.6 and §8.

**What changed** (in both products, through `device/anybook/common/desktop/desktop.mk`):
- `device/anybook/common/quire/`: Quire core, `dev.openbook.quire` (Kotlin, platform-signed, system_ext priv-app).
  - The assistant: a `VoiceInteractionService`, its session, and a recognition stub.
  - The contextual search activity.
  - Computer control: `ComputerControl`, `MirrorView`, and `ControlActivity`, with a root-only `LabActivity` alias for scripted checks.
  - Also: the framework RRO (`config_defaultAssistant`, `config_defaultContextualSearchPackageName`), the privapp and default-permission files, the contextual search feature, and the factory computer-control allowlists.
  - The test helper `QuireSecureProbe`, which is never in an image.
- Flags (`device/anybook/common/desktop/release/openbook/cp2a/`):
  - `computer_control_access`
  - `computer_control_support_v5`
  - `computer_control_per_app_consent`
  - `enable_contextual_cursor_desktop_entrypoints`
  - the build flag `RELEASE_PACKAGE_COMPUTER_CONTROL=true` (`release/flag_values/cp2a/`).
- AOSP patches:
  - frameworks/base `0005`: the allowlist fallback;
  - frameworks/base `0006`: SystemUI arms the shake without a headless system user;
  - frameworks/base `0007`: `ComputerControlSession`'s accessibility proxy;
  - Launcher3 `0002`: `ACCESS_CONTEXTUAL_SEARCH`.

## Builds

| Build | Repo | Result | Log (host, `~/anybook/logs/aosp/`) |
|---|---|---|---|
| `anybook_cf_x86_64_pc-cp2a-userdebug`, first image | `af9a7b8` | OK, 14:15–14:47 UTC (31 min, peak RSS 41.6 GB) | `build-20261018T141558Z.log` |
| `anybook_cf_x86_64_pc-cp2a-userdebug`, second image | `d0afeed` | OK, 15:25–15:54 UTC | `build-20261018T152522Z.log` |
| `anybook_cf_x86_64_pc-cp2a-userdebug`, **third image** | `d69cad3` | OK, 16:26–16:55 UTC | `build-20261018T162652Z.log` |
| `anybook_g14_x86_64-cp2a-userdebug`, compile check | `d69cad3` | see the PR | the next `build-*.log` |

All ran under the lane lock (`scripts/aosp-docker.sh`, `AOSP_JOBS=24`). The Cuttlefish images, the host package and the two APKs were snapshotted (reflinks) inside the lock. Each image was booted on the AMD lane: `CF_GPU=amd`, `gfxstream_guest_angle`, 1920×1080, `boot_completed` 26–30 s after `cvd create`.

## Results, third image (`cf/`)

**`scripts/quire/q2-cf-check.py`: 69 PASS, 0 FAIL, 1 INFO** (`cf/q2/results.tsv`, `checks.log`). It was one run on a fresh `/data`, with no manual steps; the desktop checks ran before and after it.

| Acceptance | Check | Result | Files (`cf/q2/`) |
|---|---|---|---|
| — | Facts | 20 PASS, 1 INFO (Quire is also the voice recognition service). Covered: Quire in `/system_ext/priv-app`, privileged; `ACCESS_COMPUTER_CONTROL`, `ACCESS_CONTEXTUAL_SEARCH` and `POST_NOTIFICATIONS` granted; the assistant role holder; both overlay values; the feature; seven flags `enabled`; DeviceConfig `computer_control` empty; system_server logged `Using factory value` for both allowlists | `quire-package.txt`, `aflags.txt`, `allowlist-boot-log.txt`, `computercontrol-factory.txt` |
| 1 | **The pointer shake** (a virtual USB mouse made with `uinput`, 8 strokes of 15 counts, 50 ms apart) | The note opened on the first shake: `trigger=system_action entrypoint=9(SYSTEM_ACTION)` | `invoke-shake*` |
| 1 | **Meta+Space** (`input keycombination`) | `trigger=assistant_shortcut entrypoint=11(KEYBOARD_SHORTCUT)` | `invoke-meta_space*` |
| 1 | **The assist key** (`KEYCODE_ASSIST`) | `trigger=assist_key entrypoint=11(KEYBOARD_SHORTCUT)` | `invoke-assist_key*` |
| 1 | For all three: visible packages, secure window, screenshot | `visible=[dev.openbook.quire.secureprobe, com.android.settings, com.android.settings, com.android.launcher3]` and `flagSecureFound=true`. A 1920×1080 screenshot was saved with **0** pixels of the probe's magenta: the probe's window is black, its caption bar is not | `invoke-*-screenshot.png`, `invoke-*.json`, `invoke-*-note.png` |
| 2 | Fresh consent | `cc: pending`, then the platform's dialog "Allow **Quire** to use screen automation with **Settings**?" (Always allow / Only this time / Don't allow); the check chose "Only this time" | `control-consent.png`, `.xml` |
| 2 | Settings on the session display | The session was created (1920×1080, active) and the Dark theme page launched. `dumpsys activity` shows it on display #2, a virtual display owned by `dev.openbook.quire` | `control-activities-session.txt`, `control-display.txt` |
| 2 | Quire's mirror shows it | `cc: mirror created`; Quire's window shows the session display | `control-mirror.png`, `control-mirror-after.png` |
| 2 | The session's notification | "Quire is using Settings", `flags=ONGOING_EVENT\|NO_CLEAR\|NO_DISMISS\|COMPUTER_CONTROL` | `control-notification.txt` |
| 2 | A tap through the session changes a toggle | Quire found "Use dark theme" in the session's accessibility windows and tapped its row at (1309, 189). `cmd uimode night` went from no to **yes** | `control-log.txt`, `control-session-before.png`, `control-session-after.png` |
| 2 | Take-over: `handOverApplications()` | `cc: hand over: done`, then `closed reason=4(SESSION_EMPTY)`; Settings is on display #0 | `control-activities-after.txt`, `control-handed-over.png` |
| 3 | Denial | "Don't allow" gave `creation failed: error=3(PERMISSION_DENIED)` | `refuse-consent.png`, `refuse-log.txt` |
| 3 | Lock screen | With a PIN set and the screen locked (`showing=true`), the request gave `creation failed: error=2(DEVICE_LOCKED)` | `refuse-locked.png`, `refuse-locked-keyguard.txt` |
| 3 | An app outside the allowlist | `IllegalArgumentException: Invalid target package for ComputerControl: com.android.calendar` | `refuse-log.txt` |
| 3 | Per-app consent: "Always allow" covers that app only | "Always allow" on "…with Settings?". The session was created, then closed. The same request then got a session with no dialog | `refuse-always-allow.png`, `refuse-log.txt` |
| 3 | A second, unapproved app | `[Settings, probe]` asked again, for the probe alone ("…with Quire secure probe?"). "Don't allow" gave `PERMISSION_DENIED` | `refuse-second-app.png` |
| 3 | `FLAG_SECURE` window on the session display | Consent was given for the probe only. The session went to `lifecycle: blocked reason=1(SECURE_CONTENT) package=dev.openbook.quire.secureprobe`. The platform refused Quire's tap (`Computer control interaction blocked since session is not active: tap`), the mirror went black, and the session closed. Then the device's own allowlist was restored, and the probe was refused again | `refuse-secure-mirror.png`, `refuse-secure-server-log.txt` |
| 4 | Desktop defaults (`scripts/ui/desktop-defaults.sh`, fresh boot) | **16/16 PASS**, as on `main` | `cf/defaults/` |
| 4 | Desktop capture (`scripts/desktop-capture.sh`) | Files and Settings open as freeform windows in the Desk, as before | `cf/desktop/` |
| 4 | Health over the whole session | SystemUI and Quire each started once, at boot. The crash buffer is empty; there is no `am_crash`, `am_anr` or `am_native_crash`, no tombstone and no ANR trace. The kernel log has only the three denials Cuttlefish always has (bootanim/gpu_service, init/tracefs, gceservice/zygote_config_prop): **no new one** | `health-whole-session.txt`, `selinux-denials.txt` |

**The tap needs the app to start fresh on the session display.** With Settings already running on the main display, the session had no accessibility windows (`cf-second-image/`, four tries). The check force-stops Settings before the request. Open item: `docs/quire.md` §8.

## The earlier images and the pre-test

Each folder has a README.
- **`cf-second-image/`**: the same checks without per-app consent (global consent). The accessibility-tree finding is here.
- **`cf-first-image/`** found three platform gaps:
  - the shake never worked (Launcher3's missing permission, and SystemUI's logout condition);
  - the consent app was missing;
  - AOSP's accessibility-proxy bug.

  It also ran the computer-control path with the app op preset.
- **`pretest-main-snapshot/`**: Quire installed by hand on `main`'s image. It found a crash on a platform refusal.

## Not done here

- **The G14:** a compile check of the G14 product only, with no boot and no stick.
- **The new unit tests** in the frameworks/base patches (VirtualDeviceServicesTests, SystemUI multivalent tests) were not run.

## Reproduce

```bash
# Build under the lane lock and snapshot (what ~/anybook/work/anal216/build-cf3-g14.sh did)
flock ~/anybook/aosp/.lane.lock bash -c 'ANYBOOK_LANE_LOCK_HELD=1 AOSP_JOBS=24 scripts/aosp-docker.sh /repo/scripts/aosp-build.sh \
    anybook_cf_x86_64_pc-cp2a-userdebug droid QuireSecureProbe &&
  S=~/anybook/aosp/cf/q2-out O=~/anybook/aosp/src/out P=anybook_vsoc_x86_64 &&
  mkdir -p $S/target/product/$P $S/host/linux-x86 $S/apk &&
  find $O/target/product/$P -maxdepth 1 -type f -exec cp --reflink=auto -t $S/target/product/$P {} + &&
  cp --reflink=auto $O/host/linux-x86/cvd-host_package.tar.gz $S/host/linux-x86/ &&
  find $O/target/product/$P -name QuireSecureProbe.apk -exec cp --reflink=auto -t $S/apk {} \;'
export CF_OUT=~/anybook/aosp/cf/q2-out CF_STAGE=~/anybook/aosp/cf/q2 CF_NAME=anybook-cf-q2 CF_DEVICE=anybook_vsoc_x86_64 \
  CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle CF_ADB_PORT=16216 CF_WEBRTC_PORT=11216 CF_ARGS=--vhost_user_vsock=true \
  ANDROID_ADB_SERVER_PORT=5216
scripts/cf-boot.sh up && scripts/cf-boot.sh wait && ~/anybook/android-sdk/platform-tools/adb connect 127.0.0.1:16216
scripts/ui/desktop-defaults.sh 127.0.0.1:16216 OUT/defaults        # first, before any app opens
scripts/quire/q2-cf-check.py 127.0.0.1:16216 OUT/q2 --probe ~/anybook/aosp/cf/q2-out/apk/QuireSecureProbe.apk   # fresh /data
scripts/desktop-capture.sh 127.0.0.1:16216 OUT/desktop
scripts/cf-boot.sh down
```
