# The G14 before and after the update (counts only)

`scripts/g14-adb.sh state`. Before: 2026-10-19 10:25Z (slot B, after the owner had used the laptop). After: 10:37Z,
two minutes after the owner's restart and PIN.

| | Before | After |
|---|---|---|
| slot, build | B, `…/eng.builde` (vbmeta `e0ec4b9c…`) | A, `…/20261019.quire2` (vbmeta `1d2d8f5e…`, the package's) |
| user, state | 1 user, RUNNING_UNLOCKED | the same user, RUNNING_UNLOCKED |
| screen lock | set | set |
| SELinux | enforcing | enforcing |
| packages | 153 | 160: the same 153 at the same versions, plus Quire, its framework overlay, the Terminal app, `com.android.compos.payload`, `com.android.microdroid.empty_payload`, `com.android.virtualdevicemanager` and its RRO |
| Settings, global | 156 | 156; only `boot_count`, `time_to_full_millis` and `global_color_palette_version` changed (boot counters) |
| Settings, secure | 113 | 116; `assistant`, `voice_interaction_service`, `voice_recognition_service` and `contextual_search_package` now name Quire; `read_screen_context_request_denied_count` 0 |
| Settings, system | 43 | 43, unchanged |
| Wi-Fi networks | 2 | 2 |
| accounts | 1 | 1 |
| shared storage | 180 files (163 the user's), 552,132 KiB | 186 files (163 the user's), 552,147 KiB; the user's file list hash identical. The 6 others are MediaProvider's own |

After the restart (`ota-status-after.log`): the boot HAL marked slot A good at 10:35:24 and removed slot B's entry, and
update_engine finished the merge at 10:35:26 (`MergeCompleted`). `binaries-on-device.txt`: Quire, the AVF APEX, the
composer, `openbook-pc-setup` and `openbook-bootsync` match the target files. SurfaceFlinger: render rate and active
mode 120 Hz. No crash, ANR or tombstone. Quire holds the assistant role, and its default notification grant applied.
`IVmTethering` is registered, `ro.boot.hypervisor.vm.supported=1`, and `kvm_amd` is loaded with nested and NPT. The
Linux environment's image is at `/sdcard/linux/images.tar.gz`, with a matching sha256 (`linux-env-push.log`). The Terminal
app is installed and off, as shipped.

`capture-after/avc.md` lists 11 denials, none from Quire or AVF:
- the snapshot boot's first-stage `kernel` ones (`ota_metadata_file`, `super_block_device`, `sysfs_ublk`);
- SystemUI (`platform_app`) reading `bluetooth_lea_prop`;
- an app probing emulator properties (`untrusted_app_34`);
- `keystore` and `system_server` at boot.

`capture-before` shows none because it was taken 16 h after its boot, by which time logcat had rotated.
