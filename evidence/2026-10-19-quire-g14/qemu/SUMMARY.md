# OTA rehearsal in QEMU (r2)

78/78 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| prep | the installed entry gets the serial console; loader.conf as the installer wrote it | PASS |  |
| prep | the installed disk boots slot a | PASS |  |
| prep | an app installed with adb install | PASS |  |
| prep | a screen-lock PIN set | PASS |  |
| prep | the base state recorded (marker, file, app, provisioned) | PASS |  |
| prep | SELinux enforcing; the image's own boot HAL (AOSP default) runs | PASS |  |
| prep | powers off | PASS |  |
| ab | g14-adb.sh ota: slot b written over adb, verified | PASS |  |
| ab | the first update's ESP step: bootsync from the package (running image has none) | PASS |  |
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
| ba | g14-adb.sh ota: slot a written over adb, verified | PASS |  |
| ba | the boot HAL moved the ESP entry (no bootstrap) | PASS |  |
| ba | progress shown while update_engine writes | PASS |  |
| ba | after the reboot systemd-boot starts slot a | PASS |  |
| ba | after the update: the PIN unlocks the user's storage | PASS |  |
| ba | after the update: slot a runs the package's build (vbmeta digest, build date) | PASS |  |
| ba | after the update: /data intact: the setting, the 4 MiB file, the app, the serial number, provisioned | PASS |  |
| ba | after the update: no setup screen after the update (OpenBookSetup steps aside on a provisioned system) | PASS |  |
| ba | after the update: SELinux enforcing; the OpenBook boot HAL runs | PASS |  |
| ba | the virtual A/B merge completes | PASS |  |
| ba | ESP: slot a's entry is good and the default; slot b's entry is gone | PASS |  |
| ba | boot HAL (misc): current and active slot a, marked successful | PASS |  |
| ba | no SELinux denial for openbook-bootsync, the boot HAL or the ESP (enforcing); the others are listed in avc.txt, not gated | PASS |  |
| rollback | the broken package (its kernel cannot start: rdinit missing) installs and verifies like any other | PASS |  |
| rollback | slot b fails to start three times (kernel panic, reboot), then systemd-boot starts slot a by itself | PASS |  |
| rollback | slot a is the old build, /data intact (PIN, setting, file, app) | PASS |  |
| rollback | update_engine is idle again on slot a (the failed update is cancelled) | PASS |  |
| rollback | then the good package from slot a: written and verified (the bad entry replaced) | PASS |  |
| rollback | slot b boots the good build | PASS |  |
| rollback | after the second attempt: the PIN unlocks the user's storage | PASS |  |
| rollback | after the second attempt: slot b runs the package's build (vbmeta digest, build date) | PASS |  |
| rollback | after the second attempt: /data intact: the setting, the 4 MiB file, the app, the serial number, provisioned | PASS |  |
| rollback | after the second attempt: no setup screen after the update (OpenBookSetup steps aside on a provisioned system) | PASS |  |
| rollback | after the second attempt: SELinux enforcing; the OpenBook boot HAL runs | PASS |  |
| rollback | the merge completes | PASS |  |
| cut | power cut while update_engine writes slot b | PASS |  |
| cut | after the cut slot a boots, the old build, /data intact | PASS |  |
| cut | the update re-run completes and verifies | PASS |  |
| cut | slot b boots | PASS |  |
| cut | after the re-run: the PIN unlocks the user's storage | PASS |  |
| cut | after the re-run: slot b runs the package's build (vbmeta digest, build date) | PASS |  |
| cut | after the re-run: /data intact: the setting, the 4 MiB file, the app, the serial number, provisioned | PASS |  |
| cut | after the re-run: no setup screen after the update (OpenBookSetup steps aside on a provisioned system) | PASS |  |
| cut | after the re-run: SELinux enforcing; the OpenBook boot HAL runs | PASS |  |
| cut | the merge completes | PASS |  |
| cut-from-after-ab | power cut while update_engine writes slot a | PASS |  |
| cut-from-after-ab | after the cut slot b boots, the build it ran before, /data intact | PASS |  |
| cut-from-after-ab | the update re-run completes and verifies | PASS |  |
| cut-from-after-ab | slot a boots | PASS |  |
| cut-from-after-ab | after the re-run: the PIN unlocks the user's storage | PASS |  |
| cut-from-after-ab | after the re-run: slot a runs the package's build (vbmeta digest, build date) | PASS |  |
| cut-from-after-ab | after the re-run: /data intact: the setting, the 4 MiB file, the app, the serial number, provisioned | PASS |  |
| cut-from-after-ab | after the re-run: no setup screen after the update (OpenBookSetup steps aside on a provisioned system) | PASS |  |
| cut-from-after-ab | after the re-run: SELinux enforcing; the OpenBook boot HAL runs | PASS |  |
| cut-from-after-ab | the merge completes | PASS |  |
| rollback-from-after-ab | the broken package (its kernel cannot start: rdinit missing) installs on slot a and verifies like any other | PASS |  |
| rollback-from-after-ab | slot a fails to start three times (kernel panic, reboot), then systemd-boot starts slot b by itself | PASS |  |
| rollback-from-after-ab | slot b is the build it ran before, /data intact (PIN, setting, file, app) | PASS |  |
| rollback-from-after-ab | update_engine is idle again on slot b (the failed update is cancelled) | PASS |  |
| rollback-from-after-ab | the boot HAL followed the loader: misc names slot b active, slot a unbootable; the ESP starts b next | PASS |  |
| rollback-from-after-ab | then the good package from slot b: written to slot a and verified (the bad entry replaced) | PASS |  |
| rollback-from-after-ab | slot a boots the good build | PASS |  |
| rollback-from-after-ab | after the second attempt: the PIN unlocks the user's storage | PASS |  |
| rollback-from-after-ab | after the second attempt: slot a runs the package's build (vbmeta digest, build date) | PASS |  |
| rollback-from-after-ab | after the second attempt: /data intact: the setting, the 4 MiB file, the app, the serial number, provisioned | PASS |  |
| rollback-from-after-ab | after the second attempt: no setup screen after the update (OpenBookSetup steps aside on a provisioned system) | PASS |  |
| rollback-from-after-ab | after the second attempt: SELinux enforcing; the OpenBook boot HAL runs | PASS |  |
| rollback-from-after-ab | the merge completes | PASS |  |
