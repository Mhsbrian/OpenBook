# microG as an optional add-on: evidence (ANAL-210, 2026-10-17)

Design, the security trade-off and limits: `docs/gapps.md` §6. Installer side: `docs/installer.md` §14. Play-services apps: `docs/COMPAT-MATRIX.md`. Everything ran in Cuttlefish, QEMU or on the host; **nothing ran on the G14**.

## Builds
| What | Result | Files |
|---|---|---|
| Patch provenance | Our `0001` and `0002` have the same `git patch-id` as LineageOS `198fa72864` and `03da1783cb`. Both are ancestors of `lineage-24.0`, and authors and dates are kept | `build/patch-provenance.txt` |
| `anybook_cf_x86_64_pc-cp2a-userdebug` (branch `a7ceb27`) | `frameworks/base: base 94b4c163b7df + 3 patches`; built in 5 min 10 s | `build/cf-build.txt` |
| `anybook_g14_x86_64-cp2a-userdebug` (branch `be86eec`) and live image `openbook-live-anal210-g1a` | `frameworks/base: base 94b4c163b7df + 3 patches`, `openbook-addons` and the catalogue in `system_ext`, SELinux policy builds (neverallow checks pass); 5 min 31 s; image sha256 `a049ed23…` | `build/g14-build.txt`, `build/openbook-live-anal210-g1a.*` |
| microG's APKs (`scripts/microg/fetch.sh`) | 3/3 files match the catalogue: sha256, size, signing certificate `9bd06727…` (one signer), package and versionCode. microG's OpenPGP signature is good for GmsCore and Companion | `fetch/VERIFIED.txt` |

## Cuttlefish (`anybook-cf-g1`, our cf build, SELinux enforcing, 4 vCPUs, 8 GiB, internet over the VM's Wi-Fi)
| Folder | What | Result |
|---|---|---|
| `cf-baseline/` | The patched build, no microG | 151 packages, no `com.google.android.gms`; AOSP's fused provider and no network provider; no JNI or system_server error |
| `cf-negative/` | A `com.google.android.gms` (our APK, no code) whose manifest asks for Google's certificate, signed with a throwaway key; `openbook-sigcheck` reads its signatures as any app would | **PASS:** `GET_SIGNATURES` and `GET_SIGNING_CERTIFICATES` both return its own certificate (`32b8ad52…`), not Google's (`f0fd6c5b…`) |
| `cf-microg/addons-install.txt` | `openbook-addons` (this branch's `addons.c`, NDK build), as root: `--catalog catalog --state state --from-dir src run` | 3 packages installed in 5.4 s; 11 grants, the app-op and the battery exemption ok |
| `cf-microg/sigcheck-after.txt` | Signatures after the install | GmsCore and Companion report Google's certificate (SHA-1 `38918a45…`) |
| `cf-microg/selfcheck-*.png`, `selfcheck-results.txt` | microG's self-check, read from UI dumps | **18/18 green** |
| `cf-microg/addons-rerun-after-uninstall.txt` | The user uninstalls the three apps, then `openbook-addons` runs again | "already installed; nothing to do": they stay uninstalled |
| `cf-microg/microg-settings-defaults.png` | microG's settings after a fresh install | Device registration and Cloud Messaging are off: microG's defaults |
| `cf-push/checkin-mcs.txt` | microG's two switches on (its `ProvisionService`, `checkin_enabled`/`gcm_enabled`) | Check-in done (Android ID assigned); MCS connected, TLS, logged in to `mtalk.google.com:5228` |
| `cf-gms-apps/` (per app: `.tsv` row, screenshot, redacted `.log.gz`) | Home Assistant, Bitwarden, Nextcloud, Molly (official Play-services builds), each fresh, 15 s, with and without microG | With: 4/4 alive, 0 crashes, FCM tokens issued to 3. Without: 4/4 alive, Play services missing, no push |
| `cf-location/location.txt` | One `getCurrentLocation` per provider (`openbook-sigcheck`'s `.Loc`) | microG is network and fused provider (after one restart). GPS fix (the VM's simulated GNSS); fused high-accuracy fix in 300 ms; balanced and network: none (synthetic Wi-Fi, a modem present, online lookup opt-in). With microG disabled, AOSP's fused gives the GPS fix |
| `cf-microg/avc.txt` | SELinux | Enforcing; no denial involves microG or `openbook-addons` |

Logs that touched Google's servers were redacted with `scripts/microg/redact.sh` (FCM, MCS and check-in tokens, Android ID, serials) before they were saved here.

## Host tests (image files)
| Folder | Result |
|---|---|
| `host/addons-test/` | `openbook-addons` **37/37** |
| `host/engine-addon-test/` | the installer's add-on path **19/19**, with `main`'s engine accepting the new engine's no-add-on plan |
| `host/engine-regress/` | the ANAL-191 engine suite on this branch **63/63** |

## QEMU/KVM + OVMF, the G14 image (`scripts/microg/addon-qemu.sh`)
**image `openbook-live-anal210-g1a`, 7 cases, 56 of 62 checks pass.** Every functional check passes:
- **Live stick without the add-on:** it has the same 140 packages as `main`'s image, `openbook-addons` logs "not on the boot disk", and the wizard has no switch.
- **With the add-on:** the three APKs are checked and installed 7 s after `boot_completed`, with the pinned versions, in /data. Grants, the app-op and the battery exemption are applied, and only microG Services has a launcher entry. The self-check is all green.
- **Second boot:** nothing is reinstalled, and microG is the network and fused location provider.
- **"Save logs":** the capture has the add-on state, the packages and the providers, with coordinates redacted.
- **Wizard:** the switch shows on the disk screen, off; ticked, "View the plan" lists step 2 "Check the add-on …". The engine plan and the install verify.
- **Installed disk, first start:** it installs microG from its own EFI partition, and the self-check is **18/18**.
- **The 6 failures** are one denial per boot, `openbook-addons` → `/dev/kmsg_debug` (`write`). It came from the `stdio_to_kmsg` option, which `f7df42d` removes. The rebuilt image's rerun is pending the AOSP build lane.

Per case: `qemu-g1a/SUMMARY.md`, `results.json`, each case's `result.json` and `serial.log.gz`. Screenshots: `qemu-g1a/screens/` (the wizard's plan with the add-on step, the self-check on the live stick and on the installed disk). The save-logs section: `qemu-g1a/addon-logs/collect-final-ADDONS.txt`.

## Reproduce
Commands: `docs/BUILD.md` ("Google services compatibility: the microG add-on") and `docs/gapps.md` §6.6. The Cuttlefish steps, with `ADB` this VM's adb:
```bash
# the VM: our cf build, booted as in docs/BUILD.md; internet through the VM's Wi-Fi
$ADB shell 'cmd wifi set-wifi-enabled enabled; cmd wifi connect-network VirtWifi open'
# openbook-addons for Android from the NDK container (anybook-ndk), with the engine's util.c, gpt.c, fat.c
$ADB push openbook-addons device/anybook/common/addons/microg.json <add-on>/openbook/addons/microg/*.apk /data/local/tmp/g1/...
$ADB shell 'cd /data/local/tmp/g1 && ./openbook-addons --catalog catalog --state state --from-dir src run'
$ADB shell 'am start -n "com.google.android.gms/org.microg.gms.ui.SelfCheckFragment\$AsActivity"'
$ADB shell 'am start -W -n org.openbook.test.sigcheck/.Main'          # logcat -s OpenBookSigCheck
$ADB shell 'am start -n org.openbook.test.sigcheck/.Loc --ei quality 100'   # logcat -s OpenBookLocCheck
ADB="$ADB" scripts/microg/gms-apps.sh with-microg <outdir>
```
