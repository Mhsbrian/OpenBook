# ANAL-179 evidence: audio, Wi-Fi and Bluetooth for the G14 product (2026-10-17)

Everything here ran on the build host (Ryzen 9 7950X) in QEMU/KVM; **nothing ran on the G14 yet**. Design and owner steps: `docs/g14-audio-net.md`.

## What is here

| Path | What |
|---|---|
| `qemu-summary/runs.md` | one row per QEMU run (c–i): codec found, what reached QEMU's codec through ALSA and through AudioFlinger, Wi-Fi scan/connect/DHCP/ping/iperf3 |
| `qemu-i/` | the stick's own build (`anal179-stick-d` = the image inside `openbook-live-20261017-audionet3`): `hwtest.json` (the guest's `HWTEST` results), `audio-out-tones.json` (what reached the codec, from QEMU's WAV), the guest's sections (`audio`, `wifi`, `bt`, `avcnew`, `hallog`, `props`), logcat, dmesg, serial log |
| `qemu-e/` | the first full Wi-Fi pass (this branch alone, image `anal179-c`): connect in 1 s, DHCP, iperf3 661/715 Mbit/s |
| `qemu-c/` | audio through AudioFlinger working after the memfd fix; regulatory database loading at boot |
| `qemu-b/findings.md` | log excerpts of what run b found: audio streams denied, regulatory keyring denied, nl80211 renumbering (QEMU only), kmsg; and run a's muted HDA mixer |
| `regdb-verify.txt` | `regulatory.db.p7s` verifies against the `wens` certificate, identical to the one built into cfg80211 |
| `firmware/` | MT7925 firmware: AOSP's copies (shipped, build 20260414, the one the G14 loaded) vs ANAL-198's (build 20260813), and linux-firmware's history for it |
| `host/` | `openbook_audio_logic_test` 8/8, `openbook_hals_test` 15/15 |
| `image/` | the stick image `openbook-live-20261017-audionet3` (sha256, build and layout records) and the QEMU test image of the same build |
| `build/` | the stick build's log and timing (integration commit `7953651`) |
| `live-audionet3/` | the live image's QEMU matrix (ANAL-190's six cases) and the save-logs case's `report.md`/`hwtest-final.txt` |

## Results (C = we ran it, in a VM)

- **Wi-Fi** (runs e–i): scan finds the access point, WPA2-PSK connect in about 1 s, DHCP lease from the test server through Android's IpClient, gateway ping 0% loss, iperf3 661–770 Mbit/s up and 577–715 down over `mac80211_hwsim`. No vendor HAL and no wificond: logcat shows `WifiNative: Vendor Hal not supported` and the module's `Nl80211Proxy` doing the work.
- **Regulatory database:** at boot cfg80211 loads the signed `regulatory.db` without complaint (runs c–i; before the keyring rule it reported "malformed or signature is missing/invalid"). The later "malformed" line in each run is the test's own reload of cfg80211 from a root shell.
- **Audio:** `openbook-audio-setup` finds the codec (`Generic Analog`, card 0 in QEMU) and unmutes it: Master `0/off → 74/on`. The direct ALSA loopback's 2 s tone reaches the codec whole (−18.1 dBFS RMS for −15 dBFS peak, 0 glitched windows). Through AAudio → AudioFlinger → HAL, 1.65 s of the 2 s tone arrives with phase breaks in about 24 of its 50 ms windows: the HAL drops buffers in the VM. With the HAL's pacing turned off (run g) nothing arrived, so that patch was dropped. QEMU's codec records silence, so "heard" is false by design.
- **Bluetooth:** the AIDL HAL starts and waits for `hci0`; a VM has no controller, so the stack stays in `BLE_TURNING_ON`.
- **SELinux** (final runs): no denials in the new domains; what remains is AOSP's own (`bluetooth_lea_prop` from SystemUI, keystore → Gatekeeper's shared secret, one `wifi_hal_prop` read by system_server), plus the kernel's `key { search }` on the keyring of the test's own cfg80211 reload from `su`.

## Not shown here

The MT7925 hardware, `btmtk` over the HCI user channel, the ALC285 with its CS35L56 amplifiers, the internal mics, the headphone jack: all on the G14, with the owner checklist in `docs/g14-audio-net.md` §7.
