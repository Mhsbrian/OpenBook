# ANAL-179 evidence: audio, Wi-Fi and Bluetooth for the G14 product (2026-10-17)

The QEMU runs ran on the build host (Ryzen 9 7950X) under KVM. **`g14-anal178c/` and `g14-anal176s/` are the owner's two G14 sessions of 2026-10-17**, read from the host copies of the sticks, read-only, and redacted. Design, results and the next stick's checks: `docs/g14-audio-net.md` (§10 for the G14).

## What is here

| Path | What |
|---|---|
| `g14-anal178c/`, `g14-anal176s/` | the G14 sessions on sticks `anal178c` (`main`) and `anal176s` (`main` + PR #52 then): `report.md`/`.json` (`live-report.py --expect g14 --redact`, using PR #52's version), `hwtest-final.txt`, `summary.json`, `digest.txt` (Wi-Fi, Bluetooth, audio, jack and denial lines from dmesg and logcat, for the save-logs boot and the boots before it), `tombstones.txt` (session 2's Bluetooth aborts), `stick-provenance.txt`. Masked: MAC and Bluetooth addresses, IPv4 addresses, network names and IDs, the PCI SSID |
| `qemu-l/` | the G14 fixes (`anal179-g14r-c`: patch 0002, PNO, hwtest), with the WAV backend: the AAudio tone at the codec, as built and then with AOSP's pacing in the same boot (`audio-out-tones.json`, third tone; `sections/paced.txt`), and the Wi-Fi and PNO steps |
| `qemu-m/` | the same image with the silent card: the HAL's capture padding, as built (0) and with AOSP's pacing (7 plus 1 skipped transfer) |
| `qemu-n/` | the PNO check with the test network eligible: the framework's hardware-PNO path (`sections/pno.txt`) |
| `qemu-o/`, `qemu-p/` | the same checks on this branch merged with `main` (PR #52, #55): WAV and silent card; results, sections, no serial log |
| `qemu-summary/runs.md` | one row per QEMU run (c–n), and the pacing A/B of runs l–n: codec found, what reached QEMU's codec through ALSA and through AudioFlinger, Wi-Fi scan/connect/DHCP/ping/iperf3 |
| `qemu-i/` | the stick's own build (`anal179-stick-d` = the image inside `openbook-live-20261017-audionet3`): `hwtest.json` (the guest's `HWTEST` results), `audio-out-tones.json` (what reached the codec, from QEMU's WAV), the guest's sections (`audio`, `wifi`, `bt`, `avcnew`, `hallog`, `props`), logcat, dmesg, serial log |
| `qemu-e/` | the first full Wi-Fi pass (this branch alone, image `anal179-c`): connect in 1 s, DHCP, iperf3 661/715 Mbit/s |
| `qemu-c/` | audio through AudioFlinger working after the memfd fix; regulatory database loading at boot |
| `qemu-b/findings.md` | log excerpts of what run b found: audio streams denied, regulatory keyring denied, nl80211 renumbering (QEMU only), kmsg; and run a's muted HDA mixer |
| `regdb-verify.txt` | `regulatory.db.p7s` verifies against the `wens` certificate, identical to the one built into cfg80211 |
| `firmware/` | MT7925 firmware: AOSP's copies (shipped, build 20260414, the one the G14 loaded) vs ANAL-198's (build 20260813), and linux-firmware's history for it |
| `host/` | `openbook_audio_logic_test` 8/8, `openbook_hals_test` 15/15 |
| `image/` | the stick image `openbook-live-20261017-audionet3` (sha256, build and layout records) and the QEMU test image of the same build |
| `build/` | the stick build's log and timing (integration commit `7953651`) |
| `live-audionet3/` | the stick image's QEMU matrix (ANAL-190's six cases, 39/39) and its save-logs case: `hwtest-final.txt` written by the helper, `report.md` from the integration branch's `live-report.py` (a VM has no Wi-Fi, sound card or Bluetooth controller, so those verdicts are no) |

## Results (C = we ran it, in a VM)

- **Wi-Fi** (runs e–i): scan finds the access point, WPA2-PSK connect in about 1 s, DHCP lease from the test server through Android's IpClient, gateway ping 0% loss, iperf3 661–770 Mbit/s up and 577–715 down over `mac80211_hwsim`. No vendor HAL and no wificond: logcat shows `WifiNative: Vendor Hal not supported` and the module's `Nl80211Proxy` doing the work.
- **Regulatory database:** at boot cfg80211 loads the signed `regulatory.db` without complaint (runs c–i; before the keyring rule it reported "malformed or signature is missing/invalid"). The later "malformed" line in each run is the test's own reload of cfg80211 from a root shell.
- **Audio:** `openbook-audio-setup` finds the codec (`Generic Analog`, card 0 in QEMU) and unmutes it: Master `0/off → 74/on`. The direct ALSA loopback's 2 s tone reaches the codec whole (−18.1 dBFS RMS for −15 dBFS peak, 0 glitched windows). Through AAudio → AudioFlinger → HAL, 1.65 s of the 2 s tone arrives with phase breaks in about 24 of its 50 ms windows: the HAL drops buffers in the VM. With the HAL's pacing turned off (run g) nothing arrived, so that patch was dropped. QEMU's codec records silence, so "heard" is false by design.
- **Bluetooth:** the AIDL HAL starts and waits for `hci0`; a VM has no controller, so the stack stays in `BLE_TURNING_ON`.
- **SELinux** (final runs): no denials in the new domains; what remains is AOSP's own (`bluetooth_lea_prop` from SystemUI, keystore → Gatekeeper's shared secret, one `wifi_hal_prop` read by system_server), plus the kernel's `key { search }` on the keyring of the test's own cfg80211 reload from `su`.

## On the G14 (C = the owner ran it, 2026-10-17)

- **Wi-Fi:** the MT7925 connected on 5320 MHz (160 MHz, −37/−38 dBm, link rate 1201/1922 Mbit/s), with DHCP, gateway ping 0 % loss and internet validation, in both sessions. Session 1's `wifi_connected` NO came from hwtest reusing an old status (fixed). iperf3 did not run: no server was configured.
- **Bluetooth:** `hci0` came up through `btmtk`. In session 2 a device paired and A2DP connected with LDAC at 96 kHz. Under enforcing, the Bluetooth app aborted twice when A2DP started (`tombstones.txt`), because of `bluetooth → hal_audio_default_tmpfs` (fixed in PR #52).
- **Audio:** card 2 `ALC285 Analog` was set up, and both CS35L56 amplifiers loaded their tuning. The ALSA loopback was heard in both sessions (0 and 2 of 33 slices glitched).
  - Through Android, session 1 heard the tone in only 6 of 30 slices. The HAL padded the capture with silence 7 times; patch 0002 fixes this.
  - In session 2 the tone went to the Bluetooth device. The test now names its ports.
- **Headphone jack:** not tested; nothing was plugged in.

## Not shown here

Still to show on the G14: iperf3 throughput, the patched HAL's Android loopback, Bluetooth audio and app audio under enforcing, the headphone jack, and `wifi_pno`. These are the checks for ANAL-192's integrated stick, in `docs/g14-audio-net.md` §10.4.
