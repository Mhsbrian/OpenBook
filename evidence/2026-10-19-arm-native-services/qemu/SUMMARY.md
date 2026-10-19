# OTA rehearsal in QEMU (armfix1)

36/36 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| ab | g14-adb.sh ota: slot b written over adb, verified | PASS |  |
| ab | the boot HAL moved the ESP entry (no bootstrap) | PASS |  |
| ab | progress shown while update_engine writes | PASS |  |
| ab | after the reboot systemd-boot starts slot b | PASS |  |
| ab | after the update: the PIN unlocks the user's storage | PASS |  |
| ab | after the update: slot b runs the package's build (vbmeta digest, build date) | PASS |  |
| ab | after the update: /data intact: the setting, the 4 MiB file, the app, the serial number, provisioned | PASS |  |
| ab | after the update: no setup screen after the update (OpenBookSetup steps aside on a provisioned system) | PASS |  |
| ab | after the update: SELinux enforcing; the OpenBook boot HAL runs | PASS |  |
| ab | the virtual A/B merge completes | PASS |  |
| ab | ESP: slot b's entry is good and the default; slot a's entry is gone | PASS |  |
| ab | boot HAL (misc): current and active slot b, marked successful | PASS |  |
| ab | no SELinux denial for openbook-bootsync, the boot HAL or the ESP (enforcing); the others are listed in avc.txt, not gated | PASS |  |
| rollback | the broken package (its kernel cannot start: rdinit missing) installs on slot b and verifies like any other | PASS |  |
| rollback | slot b fails to start three times (kernel panic, reboot), then systemd-boot starts slot a by itself | PASS |  |
| rollback | slot a is the build it ran before, /data intact (PIN, setting, file, app) | PASS |  |
| rollback | update_engine is idle again on slot a (the failed update is cancelled) | PASS |  |
| rollback | the boot HAL followed the loader: misc names slot a active, slot b unbootable; the ESP starts a next | PASS |  |
| rollback | then the good package from slot a: written to slot b and verified (the bad entry replaced) | PASS |  |
| rollback | slot b boots the good build | PASS |  |
| rollback | after the second attempt: the PIN unlocks the user's storage | PASS |  |
| rollback | after the second attempt: slot b runs the package's build (vbmeta digest, build date) | PASS |  |
| rollback | after the second attempt: /data intact: the setting, the 4 MiB file, the app, the serial number, provisioned | PASS |  |
| rollback | after the second attempt: no setup screen after the update (OpenBookSetup steps aside on a provisioned system) | PASS |  |
| rollback | after the second attempt: SELinux enforcing; the OpenBook boot HAL runs | PASS |  |
| rollback | the merge completes | PASS |  |
| cut | power cut while update_engine writes slot b | PASS |  |
| cut | after the cut slot a boots, the build it ran before, /data intact | PASS |  |
| cut | the update re-run completes and verifies | PASS |  |
| cut | slot b boots | PASS |  |
| cut | after the re-run: the PIN unlocks the user's storage | PASS |  |
| cut | after the re-run: slot b runs the package's build (vbmeta digest, build date) | PASS |  |
| cut | after the re-run: /data intact: the setting, the 4 MiB file, the app, the serial number, provisioned | PASS |  |
| cut | after the re-run: no setup screen after the update (OpenBookSetup steps aside on a provisioned system) | PASS |  |
| cut | after the re-run: SELinux enforcing; the OpenBook boot HAL runs | PASS |  |
| cut | the merge completes | PASS |  |
