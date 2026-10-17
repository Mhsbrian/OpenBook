# G14 boots of `openbook-live-20261017-anal176s` (PR #52), ANAL-176, 2026-10-17

The owner wrote `anal176s` (`../anal176s/`: `main` plus PR #52, sha256 `e3fbd5ab…`) and booted the default entry, then "save logs". The stick was read back read-only at 13:56Z. Files here are redacted:
- MACs, serials and Wi-Fi names are masked, and the paired Bluetooth device's address is fully masked.
- The full logcats are not included, because they name the paired device.
- The save-logs screenshot is not included: it shows a third-party web page (YouTube in the WebView browser). It stays on the dev host.

## Boot 1: the default entry, SELinux enforcing, first boot of the freshly written stick (13:40:22–13:48:16Z)

| | anal178c (main) | **anal176s** | Source |
|---|---|---|---|
| Boot animation / desktop | 17.1 s / 28.6 s | 16.7 s / 29.5 s | `boot1-default-enforcing/timeline.txt` |
| vold and the stick | scanned `disk:8,0`, notice, set-up wizard opened | **`Not managing disk 8:0`**: no notice | vold |
| Lock screen at boot | shown, screen off after 10 s | **dismissed 168 ms after showing; no sleep in the whole session** | `wm_set_keyguard_shown`, PowerManagerService |
| Frames never shown (`Failed to pin framebuffer`, `present failed`) | 151 | **0** | counts in `timeline.txt` |
| Test commits refused by amdgpu DC | 3211 | **12**, all at 13:40:39 during display bring-up, before the desktop | `Test-only seamless` |
| Session | 4 min | **8 min**: Settings, Wi-Fi, Bluetooth pairing, the browser, Calendar, Messaging, widgets; clean power-off | `START u0` |
| Denials (enforcing) | 23 (5 kinds) | 77 (7 kinds), none graphics; two new ones with effects, below | `boot1-default-enforcing/avc.md` |

**Two audio problems under enforcing**, both from memfd labels on this kernel:
- **Bluetooth audio:** com.android.bluetooth aborted twice, at 13:43:33.9 and 13:44:05.9 (`tombstones-headers.txt`).
  - Sequence: an audio device paired (bonded 13:43:32.5), A2DP reached Connected (13:43:33.94), then StartSession failed with `BluetoothAudioHal failure: Status(-129, EX_TRANSACTION_FAILED)`, and Bluetooth aborted.
  - Cause: the audio HAL process (which hosts the Bluetooth audio provider) passed the A2DP data queue, a `/memfd:MessageQueue`, and `bluetooth → hal_audio_default_tmpfs:file { read write }` was denied 4 ms earlier.
  - The permissive save-logs boot reached A2DP Connected with no crash, with `{ read write }` and `{ map }` granted.
- **App audio:** the WebView browser (`untrusted_app_29`) got `createTrack_l: Could not get control block` twice (13:45:23, 13:47:10), 6 ms after `untrusted_app_29 → audioserver_tmpfs:file { write }` was denied.
  - Cause: MLS. Apps run with categories, and AudioFlinger's control blocks are `s0` files of type `audioserver_tmpfs`. AOSP 17 does not enable the `memfd_class` capability (`private/policy_capabilities`) although the kernel has it, so memfds stay `file` objects.
  - Effect: no sound from the browser under enforcing.

## Boot 2: "save logs" (permissive), 13:49:20Z

- `boot_completed` at 28.1 s, with 0 pin failures, 0 refused test commits and 0 crashes.
- Wi-Fi: connected on 5 GHz at -38 dBm, link rate 1200/1921 Mbit/s, DHCP, gateway ping 0 % loss, internet.
- Bluetooth: one bond, A2DP Connected.
- ALSA loopback on the ALC285 (card 2) passed.
- The arm64 bridge checks all passed (`live-001/report.md`, `hwtest-final.txt`).
- The archive of earlier boots: rc 0, 2.9 MB, not capped (`prior-boots.txt`).

## Changes made from this

On `anal-176/live-stick-safety` (PR #52), in `device/anybook/common/pc/sepolicy/vendor/hal_audio_net.te` (ANAL-179's audio policy):
- `allow bluetooth hal_audio_default_tmpfs:file { getattr map read write };`, the same access `audioserver` has.
- `typeattribute audioserver_tmpfs mlstrustedobject;`. AOSP marks `system_server_tmpfs` the same way, and graphics-amd marks the allocator's memfds.

`m selinux_policy` passed, including AOSP's neverallow checks. In the compiled policy, `audioserver_tmpfs` is an `mlstrustedobject`, and a neverallow probe shows the Bluetooth allow is present.

Not checked here: whether Bluetooth audio and browser sound now work on the G14. That is for the next stick.
