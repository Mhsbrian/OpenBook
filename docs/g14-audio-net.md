# G14 audio, Wi-Fi and Bluetooth (ANAL-179)

Status as of 2026-10-17. Goal: speakers, microphone, headphone jack, Wi-Fi and Bluetooth on the ASUS ROG Zephyrus G14 (GA403WR) under OpenBook. Evidence is in `evidence/2026-10-17-g14-audio-net/`, starting with `SUMMARY.md`. Labels: **C** = confirmed (we ran it), **H** = hypothesis. **The owner ran two sessions on the G14 on 2026-10-17** (§10): Wi-Fi to the internet, Bluetooth pairing with A2DP, the codec and its amplifiers, and the speaker-to-mic loopback through ALSA all work there. The Android audio path needed a HAL fix (§5). This issue's checks for the next stick (ANAL-192's) are in §10.4.

## 1. Result

| | |
|---|---|
| Wi-Fi | AOSP's wpa_supplicant and the framework's own nl80211 code, **no vendor HAL** (none is public) and no wificond (Android 17 has none). In QEMU over `mac80211_hwsim`: scan, WPA2-PSK connect in about 1 s, DHCP through Android's IpClient, gateway ping 0% loss, **iperf3 661–770 Mbit/s up, 577–715 down** (runs e–i) (C, VM) |
| Regulatory database | signed `regulatory.db` loads at boot (cfg80211 reports no error; `wifi_regulatory` yes) after two SELinux fixes (C, VM). Before: missing on the G14 (live-001) |
| Bluetooth | AOSP's AIDL HAL over the HCI user channel; starts, and finds no controller in a VM, as expected (C). On the G14, it pairs and connects A2DP (§10) |
| Audio | `openbook-audio-setup` finds the codec card and unmutes it (the codec comes up at 0/off); a 1 kHz tone reaches the codec **directly through ALSA** (2.0 s at −18.1 dBFS RMS, exactly the −15 dBFS peak played) and **through AudioFlinger** (AAudio → HAL). Before patch 0002, 1.65 s of the 2 s tone arrived, with phase breaks in about 24 of its 50 ms windows. **With the patch: 2.05 s and 2 glitched windows, and capture is no longer padded** (runs l–n, §5, §9) (C, VM). Capture opens through both paths (the VM codec records silence) |
| Found and fixed on the way | the audio HAL could not write its own stream queues, so **no app could play or record** (memfd SELinux type); cfg80211's regulatory keyring was unsearchable; HDA mixers come up muted; firmware loads from `/vendor/firmware` were denied under enforcing (ANAL-176's fix, taken over) |
| Tests | `openbook-hwtest` in the save-logs entry, verdicts in `live-report.py`; `openbook_audio_logic_test` 8/8, `openbook_hals_test` 15/15 on the host |
| Stick image | `openbook-live-20261017-audionet3` (this branch + ANAL-176's desktop4 + `main`, branch `anal-179/stick-integration` `7953651`): ANAL-190's QEMU matrix **39/39**; its save-logs case ran `openbook-hwtest` and `live-report.py` gave the new verdicts (`evidence/.../live-audionet3/`) |
| On the G14 (2026-10-17, two sessions, §10) | **Wi-Fi:** MT7925 on 5 GHz (160 MHz, −37 dBm), DHCP, gateway ping 0 % loss, internet validated (C). **Bluetooth:** paired, A2DP with LDAC 96 kHz (C); under enforcing the Bluetooth app aborted when A2DP started (a denial PR #52 fixes). **Audio:** card 2 `ALC285 Analog` set up, both CS35L56 amplifiers tuned, loopback through ALSA heard cleanly (C); through Android heard but broken (24 of 30 slices), now fixed by the codec-paced HAL (§5, QEMU). **Not tested:** iperf3 (no server configured), the headphone jack (nothing plugged in) |

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
- **PNO** (scans with the screen off): the framework scans a disconnected, screen-off device only through PNO. Without a vendor HAL that means nl80211's scheduled scan (`Nl80211Native.startPnoScan`), which `config_wifi_background_scan_support` turns on. Without it, the G14 logged "PNO is not available" five times and then did not scan until the screen came on (§10.2).
  - The MT7925 driver registers a scheduled scan (`mt792x_core.c`: `max_sched_scan_reqs = 1`). Whether its firmware runs one is `wifi_pno` on the next stick (H). If it fails, the framework retries and gives up, as before.
  - It only helps while the system is awake. With no WoWLAN configured, cfg80211 stops scheduled scans and disconnects at every suspend (`net/wireless/sysfs.c`: `wiphy_suspend` → `cfg80211_leave_all`), and the framework reconnects after resume (H: not yet seen on the G14 while connected).
- **Firmware: AOSP's MT7925 files** (linux-firmware `b981cd37`/`c8949c63`, build `20260414`), not ANAL-198's newer ones (`20260813`, linux-firmware `3c11e660`/`50e034a2`, 2026-08-25). Reasons: they are the ones that loaded on the G14 in live-001 (WM and BT build times in its dmesg), and AOSP's `linux_firmware_mt7925*` modules own those paths. MediaTek's commit messages name no fixes. Switch if the G14 shows a firmware fault (H: none seen so far).
- **What no vendor HAL costs:** no link-layer statistics (Wi-Fi scoring falls back to RSSI), no STA+AP concurrency, no MAC randomization, no firmware logs or packet fates in bug reports.

## 4. Bluetooth

AOSP's AIDL HAL `android.hardware.bluetooth-service.default`: it finds the controller through the kernel's management channel, unblocks it with rfkill and opens `hci0` as an HCI user channel, so `btusb` + `btmtk` keep owning the firmware download. OpenBook adds `/dev/rfkill` for it (ueventd, SELinux type `openbook_rfkill_device`), `bluetooth_le.xml`, a laptop class of device (computer/laptop; networking, capturing, object transfer, audio) and the profiles a laptop uses: A2DP source, AVRCP target, HID host, GATT, battery, OPP, PAN user. **No HFP gateway** yet: it needs the HAL's SCO audio path, untested. The audio HAL already declares the Bluetooth audio provider, so A2DP uses the software encoder. On the G14, A2DP negotiated LDAC at 96 kHz/32-bit, and AudioFlinger opened the A2DP output (C, §10). Nobody has yet confirmed hearing it on the headphones.

In QEMU there is no controller: the HAL starts, logs "waiting for hci interface 0", and the stack stays in `BLE_TURNING_ON` (C). The G14 results are in §10.

## 5. Audio

**The card.** `openbook-audio-setup boot` (`audio/`, at `post-fs`, before the HAL) reads `/proc/asound/pcm` and picks the first PCM an HDA codec driver calls "… Analog", else the first playback PCM that is not HDMI/DP. It publishes `vendor.audio.primary.card`/`.device`; **OpenBook's AOSP patch** (`aosp/patches/hardware/interfaces/0001-…`) makes the example HAL's primary module read them instead of its fixed card 0, and card `-1` selects the HAL's stub driver (a VM without sound). Unset, the HAL behaves as before, so other branches' images built in the shared tree are unaffected.

**The mixer.** Android has no alsactl or UCM, and an HDA codec comes up muted: in QEMU the virtual master was `0`/off before the setup ran (C). The setup turns on Master, Speaker, Bass Speaker, Headphone and Capture switches and sets Master, Speaker, Headphone, PCM and Capture volumes to 0 dB from each control's TLV (the maximum when a control has none). Volume stays in AudioFlinger. The CS35L56 amplifiers keep their tuning's own gain, and the codec switches between speakers and headphones itself (auto-mute).

**The policy** (`audio/primary_audio_policy_configuration.xml`): 48 kHz stereo 16-bit in and out, because the G14's speaker DAC (node `0x02`) takes nothing else and the HAL opens ALSA without resampling. Speaker and built-in mic are attached; wired headphones, headset and headset mic are connectable, and `config_useDevInputEventForAudioJack` lets the HDA jack switches drive them.

**The HAL's clock (AOSP patch `0002-…`, from the G14).** The example HAL paces synchronous streams to the wall clock and drops a buffer whenever a stream falls behind. That is an emulator workaround (b/302587331). Its MonoPipe is one buffer deep (4096 frames, 85 ms): output that does not fit is dropped, and input that has not arrived yet is padded with silence. On the G14 a 3.5 s AAudio capture got 4096 frames of silence 7 times, and the Android loopback lost most of its tone, while the same loopback straight on ALSA was clean (§10.2). With `vendor.audio.primary.pacing=false`, which `openbook-audio-setup` sets whenever it finds a sound card, the stream is clocked by the device instead:
- no wall-clock pacing;
- a pipe two buffers deep;
- a writer that waits for room (MonoPipe's blocking write);
- a reader that waits up to two buffers' worth for its data.

Unset (another branch's image, or a VM without sound), nothing changes. Turning off only the pacing had killed the output (run g), because the writer then overran a non-blocking pipe. That is why the patch changes the pipe too.

**SELinux, found in QEMU (C):** the HAL's stream message queues are memfds, which on this kernel carry their creator's tmpfs type; denied writing its own queues, the HAL failed every stream open, AudioPolicy had no output and every AudioTrack got `NO_INIT`. `hal_audio_default` now gets its own tmpfs type, which audioserver may map. These are the "audio HAL writing a tmpfs memfd" denials ANAL-199 listed as harmless: they were, while nothing played.

## 6. Tests

| Tool | What it does |
|---|---|
| `openbook-hwtest [wifi\|bt\|audio]` (`/system_ext/bin`, userdebug) | Wi-Fi: driver, regulatory domain and database, enable, scan (counts per band), connection (frequency, signal, bit rates), DHCP, gateway ping, Android's internet validation, iperf3 both ways to a configured server. Bluetooth: HAL, enable, profiles, number of bonded devices. Audio: cards, PCMs, mixer, policy, the ports and jacks (`audio-routes`), and two speaker-to-mic loopbacks; the Android one names the Speaker and Built-In Mic ports, and counts what the HAL padded, dropped or skipped meanwhile. Wi-Fi also starts and stops one scheduled scan (`wifi-pno`). One `HWTEST {json}` line per result; SSIDs, device names and MAC addresses are masked |
| `openbook-audio-setup test` | loopback on ALSA directly: plays 2 s of 1 kHz at −15 dBFS while recording the built-in mic, and measures the tone (Goertzel) against the half second before it |
| `openbook-audio-test` | the same through Android (AAudio → AudioFlinger → HAL), i.e. what apps get |
| live stick, "save logs" entries | `openbook-live-init` runs `openbook-hwtest` in its final capture (`hwtest-final.txt`, `hwtest_rc` in `summary.json`), with settings from `openbook/hwtest.conf` on the stick's ESP (`iperf3_server=…`; letters, digits and `.:_-` only; never credentials) |
| `live-report.py` | turns the `HWTEST` lines into verdicts: `wifi_regulatory`, `wifi_scan`, `wifi_pno`, `wifi_connected`, `wifi_dhcp`, `wifi_gateway_ping`, `wifi_internet`, `wifi_iperf3`, `bt_enabled`, `bt_paired`, `audio_card`, `audio_loopback_alsa`, `audio_loopback_android`, `audio_android_clean` (heard, and the HAL padded, dropped and skipped nothing meanwhile), `audio_routes` (Speaker and Built-In Mic ports, jack input devices, wired or A2DP output connected, the HAL's pacing) |
| `openbook-hwtest bridge` (ANAL-200) | the arm64 native bridge: its configuration, then `/system/bin/arm64/openbook_bridge_check` through the translator. Verdicts `bridge_config`, `bridge_exec`, `bridge_id_registers`, `bridge_fp_estimates`, `bridge_int_simd`; `all` runs it first (`docs/digitalis.md`) |
| `scripts/audio-net-qemu.sh` | the QEMU rig (§8): an HDA card recorded to a WAV file, and two `mac80211_hwsim` radios with an access point on one |

The tone counts as heard when 1 kHz comes back at least 20 dB above its level before the tone and carries at least a fifth of the energy, averaged over 50 ms slices; slices under 90% are counted as glitches (`glitched_slices`), which is how dropped buffers show (`openbook_audio_logic_test`, 8 host tests, C).

## 7. On the G14: owner checklist

> **After the owner's sessions (2026-10-17):** the next stick is ANAL-192's integrated image from `main`. This issue's checks for it, and what each one needs, are in §10.4; the results of these steps are in §10.
>
> **Superseded image (2026-10-17):** write **`openbook-live-20261017-combined`** instead (`evidence/2026-10-17-g14-combined/`). It contains this image's contents plus ANAL-178's and ANAL-200's work, and it passes the same tests in QEMU. The steps below are unchanged; use that file name in the `write-stick.sh` command.

The stick image is **`openbook-live-20261017-audionet3`**: this branch merged with ANAL-176's `anal-176/g14-stability` (desktop4, `a81c25e`) and `main` (`9515e22`), so it carries the desktop fixes too. It is on the build host in `~/anybook/installer/out/` (sha256 in its `.sha256` file).

1. **Optional, for the throughput test:** on a PC on the same Wi-Fi network, run `iperf3 -s` (Arch: `sudo pacman -S iperf3`) and note its address (`ip -4 addr`). Have a Bluetooth device ready to pair: headphones or a speaker is best, a mouse or a phone also counts.
2. **Write the stick** (erases it; reports already on it are copied to the PC first). From any OpenBook checkout on the build host:
   ```bash
   OPENBOOK_WRITE_CONFIRM=/dev/disk/by-id/usb-SanDisk_Ultra_<serial>-0:0 \
     scripts/installer/write-stick.sh ~/anybook/installer/out/openbook-live-20261017-audionet3.img \
     /dev/disk/by-id/usb-SanDisk_Ultra_<serial>-0:0
   ```
   Done when it prints `stick powered off: safe to unplug`.
3. **Optional: tell the stick where the iperf3 server is.** Plug it back in; its `OPENBOOK` partition mounts. Then:
   ```bash
   printf 'iperf3_server=192.168.1.20\n' > /run/media/$USER/OPENBOOK/openbook/hwtest.conf && sync   # your PC's address
   ```
   Eject it. Only the address goes there, never a Wi-Fi password.
4. **Boot "OpenBook"** (Esc → USB stick → Enter). On the desktop:
   - Settings → Network & internet → Internet: turn Wi-Fi on, pick your network, enter its password. Hoped for: "Connected". The network stays saved on the stick.
   - Settings → Connected devices → Pair new device: pair the Bluetooth device. With headphones, play a sound (next point) through them too.
   - Speakers: Settings → Sound & vibration → Default notification sound (or Default alarm sound): choosing a sound plays it. Then plug wired headphones in and play one again: it should move to the headphones.
   - Note or photograph anything odd. Hold the power button to turn off.
5. **Boot "OpenBook - save logs to this USB stick"** (↓ once, Enter). After the boot it runs the checks by itself: **two 2-second beeps from the speakers** (the microphone test: keep the room quiet and the lid open), a Wi-Fi scan and measurements, Bluetooth status. Then it shuts down, about 5 minutes in all. If the screen stays black, wait 15 minutes before holding the power button.
6. Plug the stick into the build host and reply "stick attached". The agent runs, read-only:
   ```bash
   scripts/installer/read-stick-logs.sh /dev/disk/by-id/usb-SanDisk_Ultra_<serial>-0:0
   python3 scripts/installer/live-report.py <data dir>/installer/g14/stick-<UTC>/live-NNN --expect g14
   ```

**What counts** (the issue's acceptance, as `report.md` verdicts): `wifi_connected`, `wifi_dhcp` and `wifi_iperf3` (Mbit/s both ways) for Wi-Fi; `bt_paired` for Bluetooth; `audio_loopback_alsa` and `audio_loopback_android` (the beep heard by the built-in mic) for playback and capture; plus what you heard in step 4. The raw facts are in `hwtest-final.txt`.

**Unattended (device agent, ANAL-193/194):** the same entry with `androidboot.openbook.logs_after=reboot` (`docs/installer.md` §11.7) and `openbook/hwtest.conf` on the ESP. Wi-Fi and Bluetooth need one interactive connect and pairing first; both stay on the stick's `/data`. `report.json` has the verdicts.

## 8. QEMU rig

`scripts/audio-net-qemu.sh payload` builds a test disk for the guest: `mac80211_hwsim` with the cfg80211 and mac80211 it was built with (the virtual-device Kleaf dist; `modversions-check.py` shows all their CRCs match our vmlinux, while our own mac80211 differs in `ieee80211_alloc_hw_nm`), AOSP's `hostapd` (built, not installed: `BOARD_HOSTAPD_DRIVER`), `openbook-test-dhcpd` (a 100-line DHCP server, static, NDK), a shim that lets hostapd skip its AIDL registration, and the access point scripts. `run IMG RUN` boots the image with QEMU's HDA controller and duplex codec (output recorded to `audio-out.wav`) and the test disk on USB. In the guest (`guest-test.sh`), as root: the audio checks, then the radio swap (the image's own Wi-Fi drivers unloaded, hwsim with two radios loaded, the second moved into a network namespace with hostapd, the DHCP server and an iperf3 server), a framework restart so it resolves nl80211 again, connect to `openbook-test` (WPA2-PSK) through `cmd wifi`, and `openbook-hwtest wifi` against that iperf3 server. QEMU's codec records silence and there is no Bluetooth controller, so "heard" is false and Bluetooth stays off by design.

| Run | Image | What it showed |
|---|---|---|
| a | `anal179-a` | invalid: half of the device tree was another branch's (stale copied outputs in the shared tree); SurfaceFlinger found no EGL. Led to the device-tree touch before each build (BUILD.md) and ANAL-176's content sync |
| b | `anal179-b` | boot in 21 s. Codec found, mixer set; **every AudioTrack failed** (`NO_INIT`): the HAL's message-queue memfds; regulatory keyring denied; QEMU-only nl80211 family renumbering after the radio swap (`qemu-b/findings.md`) |
| c | `anal179-c` | audio through AudioFlinger works (AAudio both ways; 1.65 s of the tone, ~24 glitched windows, media volume at its default); regulatory database loads at boot; Wi-Fi scan finds the AP, but the test AP never answered (hostapd stuck in its AIDL registration) |
| d | `anal179-c` | same, with hostapd's own log: blocked on `/dev/vndbinder` |
| e | `anal179-c` | **Wi-Fi end to end**: connect in 1 s, DHCP `192.168.77.10/24`, ping 0.13 ms, iperf3 661/715 Mbit/s |
| f | `anal179-stick-a` (integration) | the same on the integration build: iperf3 742/644 Mbit/s; the AAudio tone at media volume 10/15: −34 dBFS, 1.65 s, 23 glitched windows |
| g | `anal179-stick-b` | a patch turning off the HAL's wall-clock pacing made the AAudio tone disappear entirely: the HAL writes into a non-blocking pipe, and the pacing is what keeps it real time. Reverted |
| h | `anal179-stick-c` | the final configuration on the integration build: iperf3 770/712 Mbit/s; the AAudio tone as in f |
| i | `anal179-stick-d` | the same plus the slice metrics in the loopback tests (the stick's build): iperf3 733/650 Mbit/s; the codec gets the ALSA tone whole (0 glitched windows) and 1.65 s of the AAudio tone (24 of 33 windows glitched) |
| j, k | `anal179-g14r-b` (G14 fixes: patch 0002, PNO, hwtest) | the AAudio tone at the codec: **2.05 s, 2 glitched windows**; with the silent card (k), the HAL padded the capture 0 times. `audio-routes` wrongly saw wired and A2DP outputs (fixed for l). The PNO check never reached the scanner: the test network had failed validation and was out of PNO |
| l, m | `anal179-g14r-c` | the same, plus the loopback a second time with AOSP's pacing in the same boot. Tone 2.05 s / 2 windows, against 1.70 s / 22 with AOSP pacing (l). Capture padding 0, against 7 insertions plus 1 skip with AOSP pacing (m, silent card): the G14's numbers. iperf3 681/732 and 697/706 Mbit/s |
| n | `anal179-g14r-c`, payload with the PNO step reconnecting with validation off | the framework's hardware-PNO path reached `Nl80211Native.startPnoScan`, which hwsim refuses; 5 attempts, then the framework gave up. The audio A/B repeated (2.05 s / 2 against 1.65 s / 23) |

Per-run table: `evidence/2026-10-17-g14-audio-net/qemu-summary/runs.md`.

Evidence: `evidence/2026-10-17-g14-audio-net/qemu-*` (results, the guest's sections, `hwtest.json`, `audio-out-tones.json`, serial log, logcat and dmesg). The live image's own QEMU matrix (`scripts/installer/live-qemu.sh`, ANAL-190's six cases) is in `.../live-audionet3/` (39/39); its save-logs case shows the helper running `openbook-hwtest` and `live-report.py` giving the new verdicts.

## 9. Open items

- **Still to show on the G14** (§10.4): iperf3 throughput; Android playback and capture without gaps on the patched HAL; Bluetooth audio and app audio under enforcing (PR #52's rules); the headphone jack switching; `wifi_pno`. Shown already (§10): MT7925 scan, connect, DHCP and internet; `btmtk` with the HCI user channel and A2DP; the CS35L56 amplifiers; the built-in mics through ALSA.
- **Audio through the HAL dropped and padded buffers**, in the VM (runs c–i: 1.65 s of a 2 s tone, about 24 of its 50 ms windows glitched) and on the G14 (§10.2). Patch 0002 makes the codec's clock pace the stream (§5). In QEMU, the AAudio tone and AOSP's pacing ran in the same boot (runs l–n). With the patch, the tone reaches the codec whole: 2.05 s, 2 glitched windows, against 1.65–1.70 s and 22–23 with AOSP's pacing. Capture is no longer padded: 0 insertions, against 7 plus 1 skipped transfer, which are the G14's numbers. On the G14: `audio_android_clean`, on the next stick.
- **Headphone jack:** WiredAccessoryManager warns "Both input event and extcon are used for audio jack" (H: harmless, since there is no extcon jack on this kernel). Not plugged yet.
- **Wi-Fi at suspend:** with no WoWLAN, every s2idle disconnects Wi-Fi, and the framework reconnects after resume (§3, H). A wake-on-WLAN setup would need a vendor HAL or our own nl80211 call.
- **Wi-Fi country:** without telephony and without `ro.boot.wificountrycode`, the framework sets the world domain (`00`); cfg80211 then follows the access point's country element once connected. An installer question (ANAL-191) could pass the country in bootconfig.
- **No HFP gateway** (headset microphones in calls), no LE Audio, no Wi-Fi Direct or hotspot: each needs work and a test of its own.
- **HDMI/DP audio** (the Radeon's card) is not routed; external displays are USB-C only while the dGPU is off.
- **The AOSP tree is shared:** the audio HAL patch stays applied for other branches' builds. Unset, its properties keep AOSP's behaviour, so their images are unaffected.
- **`wifi_hal_prop`:** system_server is denied reading `wifi.interface` once per Wi-Fi start (AOSP policy); it falls back to `wlan0`, which is right here.

## 10. On the G14: the owner's two sessions (2026-10-17)

The two sticks were read from their host copies, read-only. The redacted evidence is in `evidence/2026-10-17-g14-audio-net/g14-anal178c/` and `g14-anal176s/`:
- `report.md`/`report.json`: `live-report.py --expect g14 --redact`, using PR #52's version (before #52, `main`'s crashed on the touchpad verdict);
- `hwtest-final.txt`;
- `digest.txt`: the Wi-Fi, Bluetooth, audio, jack and denial lines of dmesg and logcat, for the save-logs boot and the boots before it;
- `tombstones.txt`.

ANAL-176's analysis of the same sessions (desktop, enforcing boot, all denials) is in `evidence/2026-10-17-g14-desktop/` (PR #52). Neither session booted the power check or the graphics check.

| Session | Stick | Boots | What the owner did |
|---|---|---|---|
| 1, 12:15Z | `openbook-live-20261017-anal178c` (`main`) | default entry (enforcing), then "save logs" (permissive, runs `openbook-hwtest`) | joined Wi-Fi |
| 2, 13:40Z | `openbook-live-20261017-anal176s` (`main` + PR #52 as of then) | the same two | joined Wi-Fi, paired a Bluetooth audio device (LDAC), used the browser |

### 10.1 Verdicts (`live-report.py --expect g14`, save-logs boots)

| Verdict | Session 1 | Session 2 | Notes |
|---|---|---|---|
| `wifi_regulatory` | yes (`mt7925e`, country `00`) | yes (country `US`) | `00` at boot, `US` from the access point's country element once associated |
| `wifi_enabled`, `wifi_scan` | yes: 91 networks (12 / 79 / 0 on 2.4 / 5 / 6 GHz) | yes: 82 (17 / 64 / 1) | |
| `wifi_connected` | **NO**, wrongly | yes | 5320 MHz (channel 64, DFS), 160 MHz HE, −37/−38 dBm, link rate 1201 up / 1922 down Mbit/s. Session 1 was connected: hwtest reused the status it read when it turned Wi-Fi on (fixed, §10.3) |
| `wifi_dhcp`, `wifi_gateway_ping`, `wifi_internet` | yes; ping 0 % loss, 16.0 ms | yes; 0 %, 7.8 ms | Android's validation: the HTTP and HTTPS probes returned 204 |
| `wifi_iperf3` | unknown | unknown | no iperf3 server was configured (`hwtest.conf`) |
| `bt_enabled` | yes (HAL running) | yes | |
| `bt_paired` | NO (0 bonded) | yes (1) | the owner paired only in session 2 |
| `audio_card` | yes: card 2, `ALC285 Analog` | yes | |
| `audio_loopback_alsa` | **yes**: tone −32.0 dBFS over a −72.5 noise bin, 0 of 33 slices glitched | **yes**: −33.6 over −75.5, 2 of 33 | speaker → built-in mic, straight on ALSA |
| `audio_loopback_android` | yes, **but 24 of 30 slices glitched** (tone −49.8 dBFS) | **NO**: the tone went to the Bluetooth device | through AAudio → AudioFlinger → HAL; see Audio below |

### 10.2 What the logs show (C unless marked)

**Wi-Fi.**
- `mt7925e` loads AOSP's firmware (WM and BT build `20260414`), and the signed regulatory database loads at boot.
- Session 1's default boot joined the owner's WPA2-PSK network and passed validation.
- The country is `00` until association. It becomes `US` from the access point (`CTRL-EVENT-REGDOM-CHANGE init=COUNTRY_IE`), and the DFS channel works.
- The errors logged are the ones expected without a vendor HAL ("mWifiHal is null", no link-layer statistics), plus "Wiphy index not recorded for band" (47 in the earlier boots). That last one is the 6 and 60 GHz band lookups (H: harmless).
- **Screen off.** In session 1's save-logs boot the screen went off at 12:20:40, while Wi-Fi was disconnected. The framework asked for PNO five times ("PNO is not available") and gave up. The laptop was then in s2idle from 41 to 61 s.
- The network was joined at 12:21:37, 2 s after it first showed up as a saved network. At the first scan after the screen came on (12:21:16), there was no saved candidate, although the access point was at −38 dBm. Why it was missing then is not known.
- Session 2's save-logs boot came up already connected.

**Bluetooth.**
- `btmtk` set up `hci0` in 0.29 s. The second setup at 18 s is the HAL opening it (H: the timing matches).
- In session 2, SSP pairing ran from 13:43:28 to bonded at 13:43:32.5. A2DP connected at 13:43:33.9, with LDAC at 96 kHz/32-bit.
- **Under enforcing, A2DP's session start failed** (`StartSession: BluetoothAudioHal failure ... FAILED_TRANSACTION`), 4 ms after `bluetooth → hal_audio_default_tmpfs:file { read write }` was denied. com.android.bluetooth aborted at 13:43:34 and at 13:44:05 (`tombstones.txt`).
- The permissive save-logs boot reconnected A2DP with LDAC, with no abort. PR #52 adds the rule (not yet run on the G14).
- The controller logs "Enhanced Setup Synchronous Connection command is advertised, but not supported". That concerns SCO (HFP), which OpenBook does not offer yet.

**Audio.**
- **Setup.** `openbook-pc-setup` unbinds the dGPU's HDMI audio function (`64:00.1`). `openbook-audio-setup` picks card 2, device 0, and sets Master switch 0 → 1, Capture switch 0 → 1 and Master volume 0 → 87.
- **Amplifiers.** Both CS35L56 amplifiers load the `10431024-spkid1` tuning (DSP firmware 3.11.16) at boot, and again after the s2idle resume at 62 s.
- **Direct ALSA loopback.** It heard the tone in both sessions, about 40 dB over the noise bin.
- **Through Android, session 1.** The tone was heard in only 6 of its 30 slices. The HAL logged "inserting 4096 frames of silence" 7 times and skipped one transfer.
  - Session 2's capture got the same 7 insertions in 3.5 s.
  - This is the pattern QEMU showed: the HAL's wall-clock pacing and its one-buffer pipe (§9). Patch 0002 fixes it (§5, §10.3).
- **Through Android, session 2.** The tone went to the paired A2DP device: AudioFlinger opened `AUDIO_DEVICE_OUT_BLUETOOTH_A2DP` at 96 kHz, so the built-in mic heard nothing. The test now names the Speaker and Built-In Mic ports.
- **App audio under enforcing.** In session 2, apps got no AudioTrack ("Could not get control block") after `untrusted_app_29 → audioserver_tmpfs:file { write }` was denied. PR #52 fixes it (MLS; not yet run on the G14).

**Headphone jack: not tested.**
- The codec's `HD-Audio Generic Headphone` jack device exists (`card2/input23`), and WiredAccessoryManager reads it.
- Every `ACTION_HEADSET_PLUG` reports "plugged in: false": nothing was plugged in during the sessions.
- WiredAccessoryManager warns "Both input event and extcon are used for audio jack" (H: harmless, since there is no extcon jack on this kernel).

**Denials in the enforcing default boots** that touch audio, Wi-Fi or Bluetooth. None are in ANAL-179's own domains (supplicant, the HALs, `openbook-audio-setup`).

| Denial | Session 1 | Session 2 | Effect | Status |
|---|---|---|---|---|
| `bluetooth → hal_audio_default_tmpfs:file { read write }` | 0 | 2 | A2DP start fails; Bluetooth aborts | fixed in PR #52 |
| `untrusted_app_29 → audioserver_tmpfs:file { write }` | 0 | 2 | no sound from apps that run with MLS categories (the browser) | fixed in PR #52 |
| `system_server → wifi_hal_prop:file { read }` | 1 | 2 | reads `wifi.interface`, falls back to `wlan0` | AOSP's policy; harmless |
| `platform_app → bluetooth_lea_prop` / `bluetooth_finder_prop` | 9 | 30 | SystemUI reads Bluetooth flags | AOSP's own |
| `keystore → hal_gatekeeper_service { find }` | 1 | 1 | — | AOSP's own |

### 10.3 Changes made from these results

| Change | Why | Shown |
|---|---|---|
| **Audio HAL paced by the codec**: AOSP patch `hardware/interfaces/0002-…`, turned on by `openbook-audio-setup` (`vendor.audio.primary.pacing=false`) when it finds a sound card (§5) | session 1's broken Android loopback; 7 silence insertions in each session's 3.5 s capture | QEMU, one boot with each mode (runs l–n): the tone at the codec lasts 2.05 s with 2 glitched windows, against 1.65–1.70 s and 22–23 with AOSP's pacing. Capture padding is 0, against 7 insertions plus 1 skipped transfer, as on the G14 (C, VM). G14: next stick |
| **Android loopback on explicit ports**: `openbook-audio-test --out-device/--in-device` with the Speaker and Built-In Mic port IDs from the audio policy; while it runs, hwtest counts the HAL's silence insertions, dropped writes and skipped transfers | session 2's tone went to the Bluetooth device | QEMU: `out_device` 2 and `in_device` 5 are the Speaker and Built-In Mic ports; `audio-routes` yes, wired and A2DP false (C, VM). Run j wrongly had them true: the parser read the module's declared devices, now fixed |
| hwtest reads the Wi-Fi connection at its own step, and no longer prints addresses | session 1's wrong `wifi_connected` | QEMU runs j–n: `wifi_connected` yes, with DHCP, gateway ping, and iperf3 681–755 up / 702–732 down Mbit/s (C, VM) |
| **PNO through the driver's scheduled scan** (`config_wifi_background_scan_support`), and a `wifi-pno` hwtest step that starts and stops one through the framework's nl80211 code | session 1's "PNO is not available" with the screen off | QEMU run n: with the screen off and the access point gone, the framework now takes the hardware-PNO path down to `Nl80211Native.startPnoScan`. hwsim has no scheduled scan, so the call fails, and the framework retries 5 times as before; `wifi-pno` is no (C, VM). The MT7925: next stick (H) |
| New verdicts: `audio_android_clean` (heard, with no padding, drops or skips), `audio_routes`, `wifi_pno` | | `live-report.py` |

### 10.4 For ANAL-192's integrated stick: this issue's G14 checks

PR #52 is merged, and ANAL-192 builds one integrated image from `main`. That image needs this PR merged too, for patch 0002, the hwtest changes and the PNO setting. The checks below go on that stick's checklist.

| Check | What it needs from the owner | Verdict / evidence that counts |
|---|---|---|
| Android playback and capture without gaps | quiet room, lid open, during "save logs" | `audio_loopback_android` yes and **`audio_android_clean` yes** (`hal_input_pads`, `hal_output_drops` and `hal_skipped_transfers` all 0), with `out_device`/`in_device` set to the Speaker and Built-In Mic ports |
| Wi-Fi throughput | `iperf3 -s` on a PC on the same network, and its address in `openbook/hwtest.conf` (`iperf3_server=…`) | `wifi_iperf3` with Mbit/s both ways |
| Wi-Fi connection at its own step | none | `wifi_connected` yes in the same run as `wifi_dhcp` |
| PNO on the MT7925 | none | `wifi_pno` yes (`driver_offers` true). A no here means the driver rejects scheduled scans, and the setting changes nothing |
| Bluetooth audio under enforcing | in the **default** entry: connect the paired headphones and play a sound | no `com.android.bluetooth` tombstone, and no `bluetooth hal_audio_default_tmpfs` denial (PR #52's rules) |
| App audio under enforcing | in the default entry: play a video in the browser | sound, with no `untrusted_app_29 audioserver_tmpfs` denial (PR #52's rules) |
| Headphone jack | in the default entry: plug in wired headphones while sound plays, then unplug | the sound moves to the headphones and back; logcat `ACTION_HEADSET_PLUG ... plugged in: true`; `audio_routes` `wired_connected` if they are still plugged in at "save logs" |
| Speakers by ear | in the default entry: Settings → Sound → a ringtone | both speakers (the CS35L56 pair) audible |

The Bluetooth device can stay paired. The loopback no longer follows the default route, and `audio_routes` reports `a2dp_connected`.

## 11. Sources (accessed 2026-10-16/17)

- AOSP 17 (`android17-release`, tree in `~/anybook/aosp/src`): `frameworks/opt/net/wifi/libwifi_hal/Android.bp` (`desktop` → `libwifi-hal-desktop`), `packages/modules/Wifi/service/.../WifiNative.java` and `WifiInjector.java` (no-HAL mode, wificond migration), `build/release/flag_values/cp2a/RELEASE_DISABLE_WIFICOND.textproto`, `external/wpa_supplicant_8` (`board_config_wpa_supplicant.mk`, `driver_nl80211.c`), `external/wireless-regdb`, `hardware/interfaces/audio/aidl/default` (`primary/StreamPrimary.cpp`, `alsa/Mixer.cpp`, `XsdcConversion.cpp`), `hardware/interfaces/bluetooth/aidl/default` (`BluetoothHci.cpp`, `net_bluetooth_mgmt.cpp`), `device/google/cuttlefish` (Wi-Fi and Bluetooth configuration), `device/generic/goldfish/wifi`, `system/sepolicy`.
- android.googlesource.com project list (2026-10-16): no `device/google/desktop`.
- linux-firmware history of `mediatek/mt7925` (gitlab.com/kernel-firmware/linux-firmware, API, 2026-10-17).
- Kernel (OpenBook android17-6.18 tree): `net/wireless/reg.c`, `net/wireless/certs/wens.hex`, `sound/hda/codecs/side-codecs/cs35l56_hda.c`, `sound/hda/codecs/realtek/alc269.c` (GA403U quirk), and, for §3 and §10: `net/wireless/sysfs.c` (`wiphy_suspend`), `drivers/net/wireless/mediatek/mt76/mt792x_core.c` (scheduled scan limits), `drivers/net/wireless/virtual/mac80211_hwsim.c` (no scheduled scan).
- AOSP 17, for §3, §5 and §10: `packages/modules/Wifi/service/.../scanner/WificondScannerImpl.java` (`isHwPnoScanRequired`), `scanner/WifiScanningServiceImpl.java` ("PNO is not available"), `WifiConnectivityManager.java` (`getAllScanOptimizationNetworks`), `nl80211/Nl80211Native.java` (`startPnoScan`), `WifiShellCommand.java` (`start-nl80211-pno-scan`), `hardware/interfaces/audio/aidl/default/alsa/StreamAlsaMonoPipe.cpp` and `primary/StreamPrimary.cpp` (pacing, b/302587331).
