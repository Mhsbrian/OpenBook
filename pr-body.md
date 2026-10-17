## ANAL-179: audio, Wi-Fi and Bluetooth for the G14 product (Android side)

**Status:** works in QEMU. It has **not run on the G14 yet**: that needs the owner's stick boot (device gate). Details, design and owner steps are in `docs/g14-audio-net.md`, and the evidence is in `evidence/2026-10-17-g14-audio-net/` (start with `SUMMARY.md`).

### What changed
- **Wi-Fi** (`device/anybook/common/pc/wifi/`):
  - AOSP's `wpa_supplicant` (AIDL) plus the Wi-Fi module's own nl80211 code. There is **no vendor Wi-Fi HAL**: AOSP's `desktop` HAL implementation isn't public. There is no wificond either, because Android 17 builds without it.
  - A DRIVER-command hook passes the country code to the kernel over nl80211.
  - Adds the signed `regulatory.db` with its licence, and a Wi-Fi resource overlay.
  - Keeps AOSP's MT7925 firmware: build 20260414, the one the G14 loaded in live-001.
  - Adds `iperf3` and `iw` on userdebug.
- **Bluetooth:** AOSP's AIDL HAL over the HCI user channel (`btusb` + `btmtk`), with `/dev/rfkill`, laptop profiles and a laptop class of device.
- **Audio:**
  - `openbook-audio-setup` finds the codec's ALSA card at boot (on the G14 the ALC285 is card 1 or 2) and sets its mixer, since HDA codecs come up muted.
  - **AOSP patch** `aosp/patches/hardware/interfaces/0001`: the example HAL's primary module reads `vendor.audio.primary.card/.device`, and card `-1` means the stub driver. When the properties are unset it behaves exactly as before.
  - A 48 kHz primary policy with speaker, built-in mic, and headphone/headset ports; jack events come from input devices.
- **SELinux found in QEMU:**
  - The audio HAL could not write its own stream message queues (memfds), so **no app could play or record**. It now gets its own tmpfs type, which audioserver may map.
  - The kernel could not search cfg80211's regulatory keyring (labelled by modprobe), so the signed database was rejected.
  - Smaller: kmsg for the setup tool, socket permissions for the Bluetooth HAL.
- **Tests:**
  - `openbook-hwtest` (userdebug) checks Wi-Fi scan, connect, DHCP, ping and iperf3, Bluetooth state and pairing, and runs speaker-to-mic loopbacks both on ALSA directly and through AAudio. The results come out as `HWTEST {json}` lines.
  - The live stick's save-logs helper (`live-init.c`) runs it in the final capture, reading `openbook/hwtest.conf` from the ESP (e.g. `iperf3_server=…`).
  - `live-report.py` turns the results into verdicts: `wifi_*`, `bt_*`, `audio_*`.
- **QEMU rig** (`scripts/audio-net-qemu.sh`, `scripts/qemu-test/`):
  - an HDA card whose output is recorded to a WAV file;
  - two `mac80211_hwsim` radios, with a hostapd access point, a small DHCP server and an iperf3 server in a separate network namespace;
  - `qemu-run.py`/`g14-qemu.sh` gain `--audio` and an extra USB disk.
- **Taken over from ANAL-176** (identical patches, so they merge cleanly): `firmware_load` on `/vendor/firmware`, and the content-based device-tree sync in `aosp-build.sh`.

### Evidence (QEMU/KVM on the 7950X)
- **Wi-Fi:** WPA2-PSK connect in about 1 s, DHCP through Android's IpClient, gateway ping with 0% loss, iperf3 661–770 Mbit/s up and 577–715 down (runs e–i). The signed regulatory database loads at boot.
- **Audio:**
  - The codec is found and unmuted.
  - A 2 s tone written directly to ALSA reaches the codec whole.
  - Through AAudio → AudioFlinger → HAL, 1.65 s of the tone arrives, with phase breaks: the HAL drops buffers in the VM. This is an open item, and the G14 loopback will show whether it happens on hardware too.
- **Bluetooth:** the HAL is up; a VM has no controller.
- **Host tests:** `openbook_audio_logic_test` 8/8, `openbook_hals_test` 15/15.
- **Live image:** see the comment on ANAL-179 for the stick image's QEMU matrix.

### Stick for the owner
`openbook-live-20261017-audionet3` was built from `anal-179/stick-integration` (`7953651`), which is this branch merged with ANAL-176's `anal-176/g14-stability` (desktop4) and `main`. The owner checklist is in `docs/g14-audio-net.md` §7.

### Notes
- The AOSP tree is shared, so the HAL patch stays applied for other branches' builds. Its properties are unset there, so their images behave as before.
- Open items:
  - the HAL's dropped buffers (VM);
  - the Wi-Fi country code without telephony;
  - no HFP gateway, LE Audio, Wi-Fi Direct or hotspot;
  - HDMI audio.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
