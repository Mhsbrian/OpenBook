# ANAL-216 (Quire Q2): platform hooks, Quire core as a privileged system app (2026-10-18)

The write-up is `docs/quire.md` §2.2–2.6 and §8.

**What changed** (all in both products, through `device/anybook/common/desktop/desktop.mk`):
- `device/anybook/common/quire/`: Quire core, `dev.openbook.quire` (Kotlin, platform-signed, system_ext priv-app): the
  assistant (`VoiceInteractionService`, session, recognition stub), the contextual search activity, and computer control
  (`ComputerControl`, `MirrorView`, `ControlActivity` with a root-only `LabActivity` alias for scripted checks). Also the
  framework RRO (`config_defaultAssistant`, `config_defaultContextualSearchPackageName`), the privapp and
  default-permission files, the contextual search feature, and the factory computer-control allowlists. Test helper
  `QuireSecureProbe` (never in an image).
- Flags (`device/anybook/common/desktop/release/openbook/cp2a/`): `computer_control_access`,
  `computer_control_support_v5`, `enable_contextual_cursor_desktop_entrypoints`. Build flag
  `RELEASE_PACKAGE_COMPUTER_CONTROL=true` (`release/flag_values/cp2a/`).
- AOSP patches: frameworks/base `0005` (allowlist fallback), `0006` (SystemUI: shake without a headless system user),
  `0007` (`ComputerControlSession`'s accessibility proxy); Launcher3 `0002` (`ACCESS_CONTEXTUAL_SEARCH`).

## Builds

| Build | Repo | Result | Log (host) |
|---|---|---|---|
| `anybook_cf_x86_64_pc-cp2a-userdebug`, first image | `af9a7b8` | OK, 14:15–14:47 UTC (31 min, peak RSS 41.6 GB) | `~/anybook/logs/aosp/build-20261018T141558Z.log` |
| `anybook_cf_x86_64_pc-cp2a-userdebug`, second image | `d0afeed` (plus uncommitted docs) | OK, 15:25–15:54 UTC | `~/anybook/logs/aosp/build-20261018T152522Z.log` |

Both ran under the lane lock (`scripts/aosp-docker.sh`, `AOSP_JOBS=24`), with the Cuttlefish images, the host package
and the two APKs snapshotted (reflinks) inside the lock. Both were booted on the AMD lane: `CF_GPU=amd`,
`gfxstream_guest_angle`, 1920×1080. Boot completed 30 s and 26 s after `cvd create`.

## Results, second image (`cf/`)

**`scripts/quire/q2-cf-check.py`: 63 PASS, 0 FAIL, 1 INFO** (`cf/q2/results.tsv`; per section `results-*.tsv`).

| Acceptance | Check | Result | Files |
|---|---|---|---|
| — | Facts: Quire in `/system_ext/priv-app`, privileged; `ACCESS_COMPUTER_CONTROL`, `ACCESS_CONTEXTUAL_SEARCH`, `POST_NOTIFICATIONS` granted; assistant role holder; both overlay values; the feature; six flags `enabled`; DeviceConfig `computer_control` empty; system_server logged `Using factory value` for both allowlists | 20 PASS, 1 INFO (Quire is also the voice recognition service) | `checks.log`, `quire-package.txt`, `aflags.txt`, `allowlist-boot-log.txt`, `computercontrol-factory.txt` |
| 1 | **The pointer shake** (a virtual USB mouse made with `uinput`, 8 strokes of 15 counts, 50 ms apart) | Note opened on the first shake: `trigger=system_action entrypoint=9(SYSTEM_ACTION)` | `invoke-shake*` |
| 1 | **Meta+Space** (`input keycombination`) | `trigger=assistant_shortcut entrypoint=11(KEYBOARD_SHORTCUT)` | `invoke-meta_space*` |
| 1 | **The assist key** (`KEYCODE_ASSIST`) | `trigger=assist_key entrypoint=11(KEYBOARD_SHORTCUT)` | `invoke-assist_key*` |
| 1 | For all three: visible packages, secure window, screenshot | `visible=[dev.openbook.quire.secureprobe, com.android.settings, com.android.settings, com.android.launcher3]`, `flagSecureFound=true`, a 1920×1080 screenshot saved with **0** pixels of the probe's magenta; the probe's window is black in it, its caption bar is not | `invoke-*-screenshot.png`, `invoke-*.json`, `invoke-*-note.png` |
| 2 | Request a session for Settings | `cc: pending`, then the platform's dialog "Allow **Quire** to use screen automation?" (Always allow / Only this time / Don't allow); "Only this time" | `control-consent.png`, `control-consent.xml` |
| 2 | Settings on the session display | Session created (1920×1080, active), Dark theme page launched; `dumpsys activity`: display #7 | `control-activities-session.txt`, `control-display.txt` (`virtual:dev.openbook.quire,...`) |
| 2 | Quire's mirror shows it | `cc: mirror created`; Quire's window shows the session display | `control-mirror.png`, `control-mirror-after.png` |
| 2 | The session's notification | "Quire is using Settings", `flags=ONGOING_EVENT\|NO_CLEAR\|NO_DISMISS\|COMPUTER_CONTROL` | `control-notification.txt` |
| 2 | A tap through the session changes a toggle | Quire found "Use dark theme" in the session's accessibility windows, tapped its row at (1309, 189): `cmd uimode night` no → **yes** | `control-log.txt`, `control-session-before.png`, `control-session-after.png` |
| 2 | `handOverApplications()` | `cc: hand over: done`, `closed reason=4(SESSION_EMPTY)`, Settings on display #0 | `control-activities-after.txt`, `control-handed-over.png` |
| 3 | Consent denied | "Don't allow" → `creation failed: error=3(PERMISSION_DENIED)` | `refuse-consent.png`, `refuse-log.txt` |
| 3 | Lock screen | PIN set, screen locked (`showing=true`), request → `creation failed: error=2(DEVICE_LOCKED)` | `refuse-locked.png`, `refuse-locked-keyguard.txt` |
| 3 | `FLAG_SECURE` window | Probe allowlisted through DeviceConfig for this check only; consent; session → `lifecycle: blocked reason=1(SECURE_CONTENT) package=dev.openbook.quire.secureprobe`; a tap was refused by the platform (`Computer control interaction blocked since session is not active: tap`); mirror black; closed. Then the device's own allowlist restored, and the probe refused again | `refuse-secure-mirror.png`, `refuse-secure-server-log.txt` |
| 3 | An app outside the allowlist | `IllegalArgumentException: Invalid target package for ComputerControl: com.android.calendar` | `refuse-log.txt` |
| 4 | Desktop defaults (`scripts/ui/desktop-defaults.sh`, fresh boot) | **16/16 PASS**, as on `main` | `cf/defaults/` |
| 4 | Desktop capture (`scripts/desktop-capture.sh`) | Files and Settings open as freeform windows in the Desk, as before | `cf/desktop/` |
| 4 | Health over the whole session | SystemUI and Quire each started once, at boot; no `am_crash`, `am_anr` or `am_native_crash` since boot; no tombstones or ANR traces; the kernel log has the three denials Cuttlefish always has (bootanim/gpu_service, init/tracefs, gceservice/zygote_config_prop) and **no new one** | `health-whole-session.txt`, `selinux-denials.txt` |

**The tap needed Settings to start fresh.** Run 1 and 2 of the control section (`results-control-run1.tsv`,
`-run2.tsv`) found 0 accessibility windows: Settings was already running on the main display. Started fresh on the
session display it has its accessibility tree (2 windows), with or without the consent dialog (tested both ways).
Observed four times; the cause is a HYPOTHESIS (docs/quire.md §8). The check now force-stops Settings first.

Manual diagnosis on this VM between 16:00 and 16:02 ran `logcat -c`, which clears the main, system and crash buffers;
that is why the health evidence comes from the events buffer, `dmesg` and the process start times, which it does not
clear.

## First image (`cf-first-image/`) and the pre-test (`pretest-main-snapshot/`)

The first image held for Meta+Space, the assist key and (with the app op preset by hand) the whole computer-control
path, and found three gaps fixed in the second: Launcher3's missing permission and SystemUI's shake condition (the shake
never worked), the missing consent app, and AOSP's accessibility-proxy bug. A pre-test on `main`'s image with Quire
installed by hand found a crash on a platform refusal. Each folder has a README.

## Not done here

- The G14 product: a compile check was queued after these runs (see the PR); no G14 boot.
- The new unit tests in the frameworks/base patches (VirtualDeviceServicesTests, SystemUI multivalent tests) were not
  run.

## Reproduce

```bash
# Build under the lane lock and snapshot (what ~/anybook/work/anal216/build-cf.sh did)
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
scripts/quire/q2-cf-check.py 127.0.0.1:16216 OUT/q2 --probe ~/anybook/aosp/cf/q2-out/apk/QuireSecureProbe.apk
scripts/desktop-capture.sh 127.0.0.1:16216 OUT/desktop
scripts/cf-boot.sh down
```
