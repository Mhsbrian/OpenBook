# ANAL-209 (B8): OpenBook's first-run setup (2026-10-18)

The write-up is `docs/setup.md`. Everything here comes from this branch's builds (userdebug, AOSP test keys).
- **Final runs:** `cuttlefish/`, `qemu/` and `contact-sheet.png`. They come from `24b7787`: the branch merged with `main` at `f49ccd8`, which includes B1, B3, B6, B7, G1 (#80), G2 (#85) and the `anal192d` stick (#86). The PR adds only docs and evidence on top.
- **`earlier/`:** the results of earlier trees, including the runs that found the bugs in "Found and fixed".

Tools: `scripts/setup/setup-walk.sh` (Cuttlefish), the installer's `scripts/installer/live-qemu.sh` and `wizard-qemu.sh` (QEMU/OVMF, G14 product image).

## Builds (all passed)

| Tree | Products |
|---|---|
| `ceec8ed` (before merging `main`) | `anybook_cf_x86_64_pc` and `anybook_g14_x86_64` (one lane hold, 08:38–09:37 UTC) |
| `11a652b` (merged) | `anybook_cf_x86_64_pc` (10:05–10:38) |
| `bbfef6b` (merged + fix) | `anybook_g14_x86_64` and live image `openbook-live-20261018-anal209m` (10:39–11:10), `anybook_cf_x86_64_pc` (11:10–11:39) |
| **`24b7787`** (merged again, with G2, #86, #87) | **`anybook_cf_x86_64_pc` (12:09–12:38), `anybook_g14_x86_64` and live image `openbook-live-20261018-anal209n` (12:38–13:10)** |

In both products: `/system_ext/priv-app/OpenBookSetup/OpenBookSetup.apk` and `privapp-permissions-openbook-setup.xml`, and no Provision (`installed-files-system_ext.txt`).

## Cuttlefish, final (`24b7787`; Radeon 610M, `gfxstream_guest_angle`, 1920×1080 at 160 dpi; each a fresh `cvd create`)

| Run | cvd flags | Checks |
|---|---|---|
| `walk`: every page | `--setupwizard_mode=REQUIRED` | **15/15** |
| `skip`: "Skip setup" | `--setupwizard_mode=REQUIRED` | **8/8** |
| `flag`: the automated-run flag | `--setupwizard_mode=REQUIRED --extra_bootconfig_args=androidboot.openbook.setup=skip` | **7/7** |
| `default`: Cuttlefish's default | none (`ro.setupwizard.mode=DISABLED`) | **7/7** |

Every run checks:
- `device_provisioned=1` and `user_setup_complete=1`;
- setup gone from the home list, Provision not installed, the launcher on top;
- **no `am_crash`/`am_anr` of setup**.

What each run adds:
- **`walk`:**
  - One screenshot per page (`cuttlefish/walk/1-welcome.png` … `9-done.png`, `10-desktop.png`, `4b-wifi-settings.png`), and `contact-sheet.png`.
  - Choices: English, region United Kingdom, layout English (UK); the Wi-Fi settings opened and left; Europe/London (the region's only zone, preselected); the 24-hour clock written; the name "OpenBook Tester"; the PIN 2468.
  - Results: `persist.sys.locale=en-GB`, `persist.sys.timezone=Europe/London`, `time_12_24=24`.
  - `cmd user list`: `UserInfo{0:OpenBook Tester…}`; `cmd lock_settings verify --old 2468`: verified.
  - `input-manager-state.xml`: `keyboard_layout_english_uk` for the VM's keyboard under LatinIME's subtype.
  - `setup-wizard-package.txt` (`dumpsys package`): `Setup Wizard: org.openbook.setup`.
- **`skip`:** the language is unchanged.
- **`flag`, `default`:** setup never started. It logged `step aside: androidboot.openbook.setup=skip` (`flag`) or `step aside: ro.setupwizard.mode=DISABLED` (`default`).

## QEMU, final (G14 product image `openbook-live-20261018-anal209n`, `24b7787`, sha256 in `qemu/*.sha256`)

| Run | Result | Files |
|---|---|---|
| Installer live checks (`live-qemu.sh`) | **40/40** | `qemu/live-results.json`, `live-SUMMARY.md`; `live-default-shot-120.png`: the install wizard opens by itself (QEMU's display swaps red and blue, `docs/installer.md` §12.7) |
| The live stick's first boot (case `first`) | Setup steps aside once (`live session`); the system starts Settings' `FallbackHome` itself; **0 `am_crash`** | `qemu/live-first-boot-setup.txt` |
| Installer wizard (`wizard-qemu.sh`: dryrun, install, installed, console) | **27/27.** The dryrun (the stick's first boot) opens the wizard by itself. On the installed disk, OpenBook setup is the first screen; the driver walks the nine pages, skipping the optional ones; afterwards provisioned, complete, setup off, the launcher on top | `qemu/wizard-results.json`, `wizard-SUMMARY.md`, `qemu/installed-setup/` (half size, 2880×1800 at density 240) |
| G2's end to end with a synthetic package (`scripts/gapps/gapps-e2e-qemu.sh`: prep, g-cli, g-installed, check) | **g-cli 10/10, g-installed 18/18.** On the installed system, setup has 10 pages. Page 9, "Register this computer with Google", shows the stand-in GSF's ID `3141592653589793238` (hex `2b992ddfa23249d6`) and the steps for `google.com/android/uncertified`. Settings › About's entry still opens the installer's registration page. The other G2 cases (power cuts, the wizard's file picker, verity) don't touch setup and were not rerun | `qemu/gapps/` (`results.json`, `SUMMARY.md`, `setup-register-ui.txt`, `g-setup-register.png`) |
| SELinux on the installed disk | No denial from setup. Reported (not gated): MediaProvider scanning the test's `/data/local/tmp` files, SystemUI's `bluetooth_lea_prop` read, keystore → Gatekeeper's `ISharedSecret` (all known before) | `qemu/console-avc.txt` |

Earlier trees, for comparison (`earlier/`): `ceec8ed` Cuttlefish 14/14, 7/7, 6/6, 6/6 (no crash check yet), QEMU live 40/40, the wizard's dryrun failing; `bbfef6b` Cuttlefish 15/15, 8/8, 7/7, 7/7, QEMU live 40/40, wizard 27/27.

## Found and fixed

1. **Setup crashed when it stepped aside while the user was still locked** (fixed in `d9942d4`).
   - **Where:** the first boot of a fresh live stick, and Cuttlefish's default boot.
   - **What:** it started home explicitly. Before the user is unlocked, home resolves to Settings' `FallbackHome`, which needs `DEVICE_POWER`: `SecurityException`, `am_crash`.
   - **Effect:** in the wizard's dryrun the install wizard never appeared (`earlier/qemu-ceec8ed/dryrun-before-fix.txt`, `wizard-results-ceec8ed.json`). On Cuttlefish it crashed once at boot (`earlier/11a652b/default-before-fix/`, 6/7).
   - **Fix:** start home only once the user is unlocked, and never let it throw; finishing is enough, as for Provision.
   - **Why the first runs missed it:** the `earlier/ceec8ed/flag` and `default` runs passed 6/6 because the system went home anyway and `setup-walk.sh` didn't look for crashes. It does now.
2. **The time zone list was locked** on devices that can't detect a zone. Android keeps the setting on (`cmd time_zone_detector dump`: NOT_SUPPORTED). The page follows the capability now (`ceec8ed`).
3. **State lost on a relaunch.** The framework restarts the activity once, 0.9 s after the first start, before any input (an asset change). The state is in a ViewModel now (`ceec8ed`).
4. **Colemak and Dvorak were suggested** for English (US). No longer (`ceec8ed`).
5. **The Done page used the standard-time name** ("Greenwich Mean Time" in summer). It now says "London · United Kingdom Time (UTC+1)" (`11a652b`).

## Not covered

- **The G14.** The checklist is on ANAL-192.
- **The internet page's online state:** these Cuttlefish VMs had no network (`Active default network: none`).
- **The GSF registration note (G2):** no image has GSF.
- **Host load:** sibling builds ran during most runs. One early Cuttlefish boot (`earlier/ceec8ed/default`) started with 11 GiB available, under the 16 GiB rule. It booted normally.
