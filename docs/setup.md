# OpenBook setup: the first-run flow (ANAL-209)

As of 2026-10-18. Labels: **C** = confirmed (a log, a screenshot or a test cited here), **HYPOTHESIS** = not yet shown. Evidence: `evidence/2026-10-18-setup/`.

Backlog item B8 of ANAL-201 (`docs/googlebook-ui.md` §2.5, §4).

## Summary

- **What it replaces (C).** AOSP has no setup wizard of its own. `packages/apps/Provision` is a home activity that only sets `device_provisioned` and `user_setup_complete` and disables itself. Googlebook runs Google's setup wizard (`setupwizard.theme=glif_expressive`), which is proprietary and needs a Google account.
- **What OpenBook ships now:** `OpenBookSetup` (`device/anybook/common/setup/`), nine pages in the installer's style, with no account:
  1. welcome (with **Skip setup**);
  2. language and region;
  3. keyboard layout;
  4. internet (optional);
  5. date and time;
  6. your name and a screen lock (optional);
  7. "OpenBook isn't a Google-certified device" (the orange-state notice);
  8. optional extras: microG (G1) and Google apps you provide (G2) (optional);
  9. done.
- **Both products** get it: `desktop.mk` inherits `setup/setup.mk`, and both `anybook_cf_x86_64_pc` and the PC/G14 product inherit `desktop.mk`.
- **It never gets in the way of automation.** It steps aside, without drawing anything, on:
  - live sessions (`androidboot.openbook.live=1`): the install wizard is the first screen there, as before;
  - `androidboot.openbook.setup=skip`: the flag for unattended runs on an installed system;
  - `ro.setupwizard.mode=DISABLED`: AOSP's setup-wizard switch. **Cuttlefish sets it by default** (cvd `--setupwizard_mode`, default `DISABLED`), so every existing Cuttlefish run lands on the desktop as before.

Results: see §5.

## 1. The mechanism, and why

| Option | Verdict |
|---|---|
| Keep Provision, add our own HOME activity above it (what ANAL-191's interim setup in the installer app did) | Works, but Provision stays the system's **setup wizard package** (`PackageManager` takes the single activity with `CATEGORY_SETUP_WIZARD`), and the flow lived in the installer app, which the Cuttlefish product doesn't have |
| Fork Provision's source | Nothing to keep: Provision is 200 lines that set two settings, plus a device-owner hook we don't use |
| **A new app that overrides Provision (chosen)** | `android_app { overrides: ["Provision"] }` is AOSP's own way to replace a package. Provision is not installed, so OpenBook setup is the one `SETUP_WIZARD` activity |

How it works (`SetupActivity.kt`, `AndroidManifest.xml`):
- **A home activity at priority 5**, with the categories `HOME`, `DEFAULT` and `SETUP_WIZARD`. Provision used priority 1, the installer's interim setup 3; the launcher has none. Home resolution picks the highest priority, so setup is the first screen.
- **Direct-boot aware**, as Provision is. During the first boot's locked phase only direct-boot-aware home activities can start.
- **At the end it does what Provision did:** `Settings.Global.device_provisioned=1`, `Settings.Secure.user_setup_complete=1`, then it disables its own component and starts home, so the launcher takes over for good.
- **Steps aside at once** (same ending, no window drawn) on a live session, with `androidboot.openbook.setup=skip`, with `ro.setupwizard.mode=DISABLED`, or when both settings are already 1. The reason is logged (`OpenBookSetup: setup complete (step aside: …)`).
- **Platform-signed privileged app** on `/system_ext`, like Provision and the installer. Privileged permissions are in `privapp-permissions-openbook-setup.xml`: `CHANGE_CONFIGURATION` (language), `MANAGE_TIME_AND_ZONE_DETECTION` (time zone, automatic time), `MANAGE_USERS` (the user's name), `WRITE_SECURE_SETTINGS`. `SET_KEYBOARD_LAYOUT` and `ACCESS_KEYGUARD_SECURE_STORAGE` (the screen lock) come from the platform signature.

**The installer's interim setup is gone.** ANAL-191 had built a three-page setup into `OpenBookInstaller` (`SetupActivity`, language, Wi-Fi, lock). It moved here and grew into this flow. The installer keeps its `BootReceiver`, which still applies `androidboot.openbook.locale` once on an installed system.

## 2. The pages

All pages use the installer's design (`docs/installer-design/`): the same theme, colour roles (seed `#4A5BD4`), type scale, pill buttons, notices and brand mark. They are not copies: the installer app's `ui/Theme.kt`, `ui/Components.kt` and `ui/Art.kt` are compiled into setup through the Soong filegroup `OpenBookInstallerDesign`. The left rail is the installer's step rail with setup's nine steps. Keyboard: Tab order, Enter on the focused button, Escape is Back. Headings and the rail are labelled for screen readers.

| # | Page | What it changes | API |
|---|---|---|---|
| 1 | Welcome | — ; **Skip setup** ends setup with the current settings | — |
| 2 | Language and region | The system locale, e.g. `en-GB`. Languages: the installer's list; regions: every region ICU has for that language, its likely region first. Starts from the installer's choice (`androidboot.openbook.locale`) | `LocalePicker.updateLocale` |
| 3 | Keyboard layout | The layout of every physical keyboard, for the current input method and subtype (Android 17 keeps one layout per keyboard, user, input method and subtype, as Settings › Physical keyboard does). Suggested first: the installer's pick (`androidboot.openbook.keyboard`), the layout in use, the layouts for the chosen language and region. All 57 AOSP layouts are listed, with a field to try typing. The G14's own key maps from ANAL-178 (`Vendor_0b05_Product_19b6.kl`, `Asus_WMI_hotkeys.kl`) are untouched: a layout only maps keys to characters, so special keys keep working | `InputManager.setKeyboardLayoutForInputDevice` |
| 4 | Internet (optional) | Nothing itself; shows whether the default network has internet (Wi-Fi, Ethernet) and opens Settings' Wi-Fi page | `ConnectivityManager` callback, `Settings.ACTION_WIFI_SETTINGS` |
| 5 | Date and time | The time zone (the region's zones, or all of them, with search; a region with one zone is preselected), automatic time and automatic time zone where the device supports them, the 24-hour clock. "Set date and time by hand" opens Settings | `TimeManager` (`setManualTimeZone`, `updateTimeConfiguration`), `Settings.System.TIME_12_24` |
| 6 | About you (optional) | The user's name; a PIN or password (at least 4), or none. Coming back and changing it replaces the one set here | `UserManager.setUserName`, `LockPatternUtils.setLockCredential` |
| 7 | This device | Nothing. The orange-state notice (`docs/installer.md` §2): OpenBook isn't Google-certified; verified boot is orange (the live value of `ro.boot.verifiedbootstate`) but dm-verity still checks the system; Play Integrity apps may refuse to run; no Google apps included | — |
| 8 | Extras (optional) | Nothing. **microG (G1, ANAL-210):** installed (version, "Open microG settings") or how to get it (the installer's add-on, off by default). **Google apps you provide (G2, ANAL-211):** OpenBook never downloads them; the guide is `docs/gapps.md`. If Google Services Framework is installed, the page shows Google's uncertified-device registration note and the GSF ID (HYPOTHESIS: not tested, no image of ours has GSF) | `PackageManager` (`<queries>` for the three packages) |
| 9 | Done | A summary; **Start using OpenBook** finishes | — |

"Google" appears only where the text is about Google's products. OpenBook's own name is never combined with it.

## 3. Automated runs

| Run | What it boots | What setup does | Needs |
|---|---|---|---|
| Cuttlefish (`scripts/cf-boot.sh`, every sibling's UI capture) | the Cuttlefish product | Steps aside: cvd passes `androidboot.setupwizard_mode=DISABLED` by default, and Cuttlefish's `init.vendor.rc` copies it to `ro.setupwizard.mode` | nothing. To see setup: `CF_ARGS="--setupwizard_mode=REQUIRED"` |
| Live stick, all entries (default, save logs, add-ons, the device loop's agent entry, `live-qemu.sh`) | `androidboot.openbook.live=1` | Steps aside | nothing |
| Installed system, interactive tests (`wizard-qemu.sh console`, `e2e-qemu.sh`) | the installed disk | Shows; the drivers walk all nine pages and skip the optional ones (`wizard-qemu.py` `setup_steps`) | nothing |
| Installed system, unattended (ANAL-196's device loop on a spare drive, any scripted boot) | an entry with `androidboot.openbook.setup=skip` | Steps aside | add the flag to that entry's bootconfig, e.g. `python3 scripts/installer/bootconfig.py make <out>.img --base <esp>/openbook/a/bootconfig.img androidboot.openbook.setup=skip` |
| Cuttlefish with setup on, but skipped by flag | `CF_ARGS="--setupwizard_mode=REQUIRED --extra_bootconfig_args=androidboot.openbook.setup=skip"` | Steps aside | — |

The flag is a bootconfig value like the installer's other `androidboot.openbook.*` keys (`docs/installer.md` §2.1). It is only read; nothing writes it into a normal boot entry.

## 4. Tests

- `device/anybook/common/setup/tools/compile-check.sh`: the Kotlin sources with the installer's design files, outside Soong (the installer's checker with `APP=` and `EXTRA_SRCS=`).
- `scripts/setup/setup-walk.sh SERIAL OUT walk|skip|absent`: drives a booted device and writes `results.json`.
  - `walk`: every page, one screenshot each, choosing region United Kingdom, layout English (UK), the Wi-Fi settings and back, the 24-hour clock, a name and a PIN.
  - `skip`: "Skip setup" on the first page.
  - `absent`: setup must not appear.
  - Every mode checks `device_provisioned` and `user_setup_complete` (both 1), that setup left the home list, that Provision is not installed and that the launcher is on top. `walk` also checks the locale, time zone, clock format, user name and PIN (`cmd lock_settings verify`).

## 5. Results

To be filled in from the runs in `evidence/2026-10-18-setup/`.

## 6. Not done, and limits

- **Translations:** English only, as in the installer.
- **Wi-Fi in the page itself:** the page hands over to Settings' Wi-Fi list. An in-page network list would need location access for scan results.
- **A keyboard plugged in after setup** gets Android's automatic layout (by the input method's language), not setup's choice.
- **The G14:** not run on the laptop. The steps are on ANAL-192's next stick checklist.

## Reproduce

```bash
# Build (lane lock held across the build and the snapshot)
flock ~/anybook/aosp/.lane.lock bash -c 'AOSP_JOBS=24 scripts/aosp-docker.sh /repo/scripts/aosp-build.sh anybook_cf_x86_64_pc-cp2a-userdebug && <reflink snapshot of out/target/product/anybook_vsoc_x86_64 and cvd-host_package.tar.gz to ~/anybook/aosp/cf/b8-out>'
export CF_OUT=~/anybook/aosp/cf/b8-out CF_STAGE=~/anybook/aosp/cf/b8 CF_NAME=anybook-cf-b8 CF_DEVICE=anybook_vsoc_x86_64 \
  CF_ADB_PORT=16538 CF_WEBRTC_PORT=11538 CF_GPU=amd CF_GPU_MODE=gfxstream_guest_angle
export ANDROID_ADB_SERVER_PORT=5138
# walk: setup on
CF_ARGS="--vhost_user_vsock=true --setupwizard_mode=REQUIRED" scripts/cf-boot.sh up && adb connect 127.0.0.1:16538
scripts/setup/setup-walk.sh 127.0.0.1:16538 OUT/walk walk; scripts/cf-boot.sh down
# skip: the same, then
scripts/setup/setup-walk.sh 127.0.0.1:16538 OUT/skip skip
# the automated-run flag, with setup otherwise on
CF_ARGS="--vhost_user_vsock=true --setupwizard_mode=REQUIRED --extra_bootconfig_args=androidboot.openbook.setup=skip" scripts/cf-boot.sh up
scripts/setup/setup-walk.sh 127.0.0.1:16538 OUT/flag absent
# Cuttlefish's default (DISABLED)
CF_ARGS="--vhost_user_vsock=true" scripts/cf-boot.sh up; scripts/setup/setup-walk.sh 127.0.0.1:16538 OUT/default absent
```
