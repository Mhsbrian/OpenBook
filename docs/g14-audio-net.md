# G14 audio, Wi-Fi and Bluetooth (ANAL-179)

Status as of 2026-10-17. Goal: speakers, microphone, headphone jack, Wi-Fi and Bluetooth on the ASUS ROG Zephyrus G14 (GA403WR) under OpenBook. Evidence is in `evidence/2026-10-17-g14-audio-net/`, starting with `SUMMARY.md`. Labels: **C** = confirmed (we ran it), **H** = hypothesis. **Nothing here has run on the G14 yet**: the device gate applies, and the owner checklist is in §7.

## 1. Result

@@RESULT@@

## 2. What the G14 has (from its inventory and the first live boot)

| Part | Linux side on the G14 (live-001, `evidence/2026-10-16-installer/g14-live/`) | Android side before ANAL-179 |
|---|---|---|
| MediaTek MT7925 Wi-Fi 7, `14c3:7925` | `mt7925e` binds, firmware `20260414` loads, `wlan0` exists; `regulatory.db` missing | no Wi-Fi service at all (`cmd: Can't find service: wifi`) |
| MT7925 Bluetooth 5.4, USB `0489:e11e` | `btusb` + `btmtk`, `hci0` set up in 1.7 s | no Bluetooth HAL; the Bluetooth app aborted in a loop |
| Realtek ALC285 (SSID `1043:1024`) + 2× Cirrus CS35L56 on I2C | the GA403U quirk applies, both amplifiers load the `10431024-spkid1` tuning; one PCM, `ALC285 Analog`, on **card 2** (card 0 is the dGPU's HDMI audio, card 1 the Radeon HDMI/DP) | AOSP's example audio HAL on card 0, which is HDMI or missing |
| Internal mics | two digital mics on the HDA codec (pins `0x12`, `0x13`); ACP 7.0's DMIC path registers no PCM | — |
| Headphone jack | pin `0x21`, with the headset mic on `0x19` (reported broken upstream, R) | — |

The ALC285's card number is not stable: with the dGPU off (`dgpu_disable=1`, the bring-up default) the NVIDIA HDMI function is not enumerated, and the codec becomes card 1 (the inventory's `aplay -l`).

## 3. Wi-Fi

**Design.** AOSP's `wpa_supplicant` (AIDL) over standard nl80211, and no vendor Wi-Fi HAL (`device/anybook/common/pc/wifi/`).
- **No vendor HAL.** AOSP's `libwifi_hal` has a `desktop` WLAN device, but its implementation (`libwifi-hal-desktop`) is not in AOSP (checked 2026-10-16: `device/google/desktop`, which `external/wireless-regdb` names in its visibility, is not on android.googlesource.com). goldfish's `libwifi-hal-emu` reports fixed versions and 2.4 GHz channels only. The framework supports running without a vendor HAL (`WifiNative`: "Vendor Hal not supported, ignoring createStaIface"), and the QEMU runs show it doing so (C).
- **No wificond either.** Android 17's `cp2a` release sets `RELEASE_DISABLE_WIFICOND`, so the Wi-Fi module talks nl80211 itself (`Nl80211Proxy` in system_server) (C, QEMU logcat).
- **DRIVER commands** (`wifi/driver_cmd_openbook.c`, `BOARD_WPA_SUPPLICANT_PRIVATE_LIB`): with no vendor HAL, the framework's country code reaches the kernel only as the supplicant's `DRIVER COUNTRY xx`, which this sends as `NL80211_CMD_REQ_SET_REG`. The rest follows Cuttlefish's hook (START/STOP/MACADDR; vendor-only commands succeed as no-ops).
- **Regulatory database:** `regulatory.db` and `.p7s` from AOSP's `external/wireless-regdb` (2025-10-07, ISC) in `/vendor/firmware`, with its licence. The `.p7s` verifies against the `wens` certificate, which is byte-identical to the one built into our cfg80211 (`regdb-verify.txt`, C). Two SELinux rules were needed before the kernel would use it (C, QEMU): `firmware_load` on `/vendor/firmware` (ANAL-176 found the same denial for amdgpu; cherry-picked as-is), and `kernel → vendor_modprobe : key { search }`, because cfg80211's regulatory keyring takes the label of the modprobe that loads it.
- **Framework settings** (`wifi/overlay`): 5 and 6 GHz on; station, P2P and AP MAC randomization off, since setting a MAC address goes through the vendor HAL.
- **Firmware: AOSP's MT7925 files** (linux-firmware `b981cd37`/`c8949c63`, build `20260414`), not ANAL-198's newer ones (`20260813`, linux-firmware `3c11e660`/`50e034a2`, 2026-08-25). Reasons: they are the ones that loaded on the G14 in live-001 (WM and BT build times in its dmesg), and AOSP's `linux_firmware_mt7925*` modules own those paths. MediaTek's commit messages name no fixes. Switch if the G14 shows a firmware fault (H: none seen so far).
- **What no vendor HAL costs:** no link-layer statistics (Wi-Fi scoring falls back to RSSI), no STA+AP concurrency, no MAC randomization, no firmware logs or packet fates in bug reports.

## 4. Bluetooth

AOSP's AIDL HAL `android.hardware.bluetooth-service.default`: it finds the controller through the kernel's management channel, unblocks it with rfkill and opens `hci0` as an HCI user channel, so `btusb` + `btmtk` keep owning the firmware download. OpenBook adds `/dev/rfkill` for it (ueventd, SELinux type `openbook_rfkill_device`), `bluetooth_le.xml`, a laptop class of device (computer/laptop; networking, capturing, object transfer, audio) and the profiles a laptop uses: A2DP source, AVRCP target, HID host, GATT, battery, OPP, PAN user. **No HFP gateway** yet: it needs the HAL's SCO audio path, untested. The audio HAL already declares the Bluetooth audio provider, so A2DP uses the software encoder (H until a headset plays).

In QEMU there is no controller: the HAL starts, logs "waiting for hci interface 0", and the stack stays in `BLE_TURNING_ON` (C). Pairing is a G14 test.

## 5. Audio

**The card.** `openbook-audio-setup boot` (`audio/`, at `post-fs`, before the HAL) reads `/proc/asound/pcm` and picks the first PCM an HDA codec driver calls "… Analog", else the first playback PCM that is not HDMI/DP. It publishes `vendor.audio.primary.card`/`.device`; **OpenBook's AOSP patch** (`aosp/patches/hardware/interfaces/0001-…`) makes the example HAL's primary module read them instead of its fixed card 0, and card `-1` selects the HAL's stub driver (a VM without sound). Unset, the HAL behaves as before, so other branches' images built in the shared tree are unaffected.

**The mixer.** Android has no alsactl or UCM, and an HDA codec comes up muted: in QEMU the virtual master was `0`/off before the setup ran (C). The setup turns on Master, Speaker, Bass Speaker, Headphone and Capture switches and sets Master, Speaker, Headphone, PCM and Capture volumes to 0 dB from each control's TLV (the maximum when a control has none). Volume stays in AudioFlinger. The CS35L56 amplifiers keep their tuning's own gain, and the codec switches between speakers and headphones itself (auto-mute).

**The policy** (`audio/primary_audio_policy_configuration.xml`): 48 kHz stereo 16-bit in and out, because the G14's speaker DAC (node `0x02`) takes nothing else and the HAL opens ALSA without resampling. Speaker and built-in mic are attached; wired headphones, headset and headset mic are connectable, and `config_useDevInputEventForAudioJack` lets the HDA jack switches drive them.

**SELinux, found in QEMU (C):** the HAL's stream message queues are memfds, which on this kernel carry their creator's tmpfs type; denied writing its own queues, the HAL failed every stream open, AudioPolicy had no output and every AudioTrack got `NO_INIT`. `hal_audio_default` now gets its own tmpfs type, which audioserver may map. These are the "audio HAL writing a tmpfs memfd" denials ANAL-199 listed as harmless: they were, while nothing played.

## 6. Tests

| Tool | What it does |
|---|---|
| `openbook-hwtest [wifi\|bt\|audio]` (`/system_ext/bin`, userdebug) | Wi-Fi: driver, regulatory domain and database, enable, scan (counts per band), connection (frequency, signal, bit rates), DHCP, gateway ping, Android's internet validation, iperf3 both ways to a configured server. Bluetooth: HAL, enable, profiles, number of bonded devices. Audio: cards, PCMs, mixer, policy, and two speaker-to-mic loopbacks. One `HWTEST {json}` line per result; SSIDs, device names and MAC addresses are masked |
| `openbook-audio-setup test` | loopback on ALSA directly: plays 2 s of 1 kHz at −15 dBFS while recording the built-in mic, and measures the tone (Goertzel) against the half second before it |
| `openbook-audio-test` | the same through Android (AAudio → AudioFlinger → HAL), i.e. what apps get |
| live stick, "save logs" entries | `openbook-live-init` runs `openbook-hwtest` in its final capture (`hwtest-final.txt`, `hwtest_rc` in `summary.json`), with settings from `openbook/hwtest.conf` on the stick's ESP (`iperf3_server=…`; letters, digits and `.:_-` only; never credentials) |
| `live-report.py` | turns the `HWTEST` lines into verdicts: `wifi_regulatory`, `wifi_scan`, `wifi_connected`, `wifi_dhcp`, `wifi_gateway_ping`, `wifi_internet`, `wifi_iperf3`, `bt_enabled`, `bt_paired`, `audio_card`, `audio_loopback_alsa`, `audio_loopback_android` |
| `scripts/audio-net-qemu.sh` | the QEMU rig (§8): an HDA card recorded to a WAV file, and two `mac80211_hwsim` radios with an access point on one |

The tone counts as heard when 1 kHz comes back at least 20 dB above its level before the tone and carries at least a fifth of the energy (`openbook_audio_logic_test`, 7 host tests, C).

## 7. On the G14: owner checklist

@@OWNER@@

## 8. QEMU rig

`scripts/audio-net-qemu.sh payload` builds a test disk for the guest: `mac80211_hwsim` with the cfg80211 and mac80211 it was built with (the virtual-device Kleaf dist; `modversions-check.py` shows all their CRCs match our vmlinux, while our own mac80211 differs in `ieee80211_alloc_hw_nm`), AOSP's `hostapd` (built, not installed: `BOARD_HOSTAPD_DRIVER`), `openbook-test-dhcpd` (60 lines of C, static, NDK), and the access point scripts. `run IMG RUN` boots the image with QEMU's HDA controller and duplex codec (output recorded to `audio-out.wav`) and the test disk on USB. In the guest (`guest-test.sh`), as root: the audio checks, then the radio swap (the image's own Wi-Fi drivers unloaded, hwsim with two radios loaded, the second moved into a network namespace with hostapd, the DHCP server and an iperf3 server), a framework restart so it resolves nl80211 again, connect to `openbook-test` (WPA2-PSK) through `cmd wifi`, and `openbook-hwtest wifi` against that iperf3 server. QEMU's codec records silence and there is no Bluetooth controller, so "heard" is false and Bluetooth stays off by design.

@@QEMU@@

## 9. Open items

@@OPEN@@

## 10. Sources (accessed 2026-10-16/17)

- AOSP 17 (`android17-release`, tree in `~/anybook/aosp/src`): `frameworks/opt/net/wifi/libwifi_hal/Android.bp` (`desktop` → `libwifi-hal-desktop`), `packages/modules/Wifi/service/.../WifiNative.java` and `WifiInjector.java` (no-HAL mode, wificond migration), `build/release/flag_values/cp2a/RELEASE_DISABLE_WIFICOND.textproto`, `external/wpa_supplicant_8` (`board_config_wpa_supplicant.mk`, `driver_nl80211.c`), `external/wireless-regdb`, `hardware/interfaces/audio/aidl/default` (`primary/StreamPrimary.cpp`, `alsa/Mixer.cpp`, `XsdcConversion.cpp`), `hardware/interfaces/bluetooth/aidl/default` (`BluetoothHci.cpp`, `net_bluetooth_mgmt.cpp`), `device/google/cuttlefish` (Wi-Fi and Bluetooth configuration), `device/generic/goldfish/wifi`, `system/sepolicy`.
- android.googlesource.com project list (2026-10-16): no `device/google/desktop`.
- linux-firmware history of `mediatek/mt7925` (gitlab.com/kernel-firmware/linux-firmware, API, 2026-10-17).
- Kernel (OpenBook android17-6.18 tree): `net/wireless/reg.c`, `net/wireless/certs/wens.hex`, `sound/hda/codecs/side-codecs/cs35l56_hda.c`, `sound/hda/codecs/realtek/alc269.c` (GA403U quirk).
