# G14 audio, Wi-Fi and Bluetooth (ANAL-179)

Speakers, microphone, headphone jack, Wi-Fi and Bluetooth on the ASUS ROG Zephyrus G14 (GA403WR) under OpenBook: how
each works, how it is tested, and what has been shown on the laptop. Labels: **C** = confirmed (we ran it), **H** =
hypothesis.

## 1. State (as of 2026-10-18)

| | |
|---|---|
| Wi-Fi | AOSP's wpa_supplicant and the framework's own nl80211 code, **no vendor HAL** (none is public) and no wificond (Android 17 has none). **On the G14** (C): MT7925 on 2.4 and 5 GHz (including a 160 MHz DFS channel), DHCP, internet validated; PNO (screen-off scans) through the driver's scheduled scan works. In QEMU over `mac80211_hwsim`: scan, WPA2-PSK connect in about 1 s, DHCP, iperf3 about 590–770 Mbit/s each way (C, VM). Throughput on the G14 is not measured yet |
| Regulatory database | Signed `regulatory.db` loads at boot (cfg80211 reports no error; `wifi_regulatory` yes), on the G14 too (C) |
| Bluetooth | AOSP's AIDL HAL over the HCI user channel. **On the G14** (C): pairs; A2DP connects with LDAC (96 kHz) and AAC (44.1 kHz) headsets, and streams under enforcing (shown with AAC). No HFP gateway yet |
| Audio | `openbook-audio-setup` finds the codec card and unmutes it (the codec comes up at 0/off), and the HAL is paced by the codec's clock (patch 0002, §5). **On the G14** (C): both CS35L56 amplifiers tuned, speaker-to-mic loopback clean through ALSA and through Android (`audio_android_clean`), speaker, browser and Bluetooth playback under enforcing, the unlock sound at boot. MediaPlayer sounds (notifications, ringtone previews) needed a SELinux rule that is now in the image (§5); not yet shown on the G14. The headphone jack is not tested |
| Tests | `openbook-hwtest` in the save-logs entry, verdicts in `live-report.py`; `openbook_audio_logic_test` and `openbook_hals_test` on the host; the QEMU rig (§8) |

## 2. What the G14 has

| Part | Linux side on the G14 | Android side before ANAL-179 |
|---|---|---|
| MediaTek MT7925 Wi-Fi 7, `14c3:7925` | `mt7925e` binds, firmware `20260414` loads, `wlan0` exists; `regulatory.db` missing | no Wi-Fi service at all (`cmd: Can't find service: wifi`) |
| MT7925 Bluetooth 5.4, USB `0489:e11e` | `btusb` + `btmtk`, `hci0` set up in 0.3–1.7 s | no Bluetooth HAL; the Bluetooth app aborted in a loop |
| Realtek ALC285 (SSID `1043:1024`) + 2× Cirrus CS35L56 on I2C | the GA403U quirk applies, both amplifiers load the `10431024-spkid1` tuning (DSP firmware 3.11.16); one PCM, `ALC285 Analog`, on **card 2** (card 0 is the dGPU's HDMI audio, card 1 the Radeon HDMI/DP) | AOSP's example audio HAL on card 0, which is HDMI or missing |
| Internal mics | two digital mics on the HDA codec (pins `0x12`, `0x13`); ACP 7.0's DMIC path registers no PCM | — |
| Headphone jack | pin `0x21`, with the headset mic on `0x19` (reported broken upstream, R); the jack input device is `HD-Audio Generic Headphone` | — |

The ALC285's card number is not stable: with the dGPU off (`dgpu_disable=1`) the NVIDIA HDMI function is not
enumerated, and the codec becomes card 1. That is why `openbook-audio-setup` picks the card by name (§5).

## 3. Wi-Fi

**Design.** AOSP's `wpa_supplicant` (AIDL) over standard nl80211, and no vendor Wi-Fi HAL (`device/anybook/common/pc/wifi/`).
- **No vendor HAL.** AOSP's `libwifi_hal` has a `desktop` WLAN device, but its implementation (`libwifi-hal-desktop`) is not in AOSP (checked 2026-10-16: `device/google/desktop`, which `external/wireless-regdb` names in its visibility, is not on android.googlesource.com). goldfish's `libwifi-hal-emu` reports fixed versions and 2.4 GHz channels only. The framework supports running without a vendor HAL (`WifiNative`: "Vendor Hal not supported, ignoring createStaIface") (C).
- **No wificond either.** Android 17's `cp2a` release sets `RELEASE_DISABLE_WIFICOND`, so the Wi-Fi module talks nl80211 itself (`Nl80211Proxy` in system_server) (C).
- **DRIVER commands** (`wifi/driver_cmd_openbook.c`, `BOARD_WPA_SUPPLICANT_PRIVATE_LIB`): with no vendor HAL, the framework's country code reaches the kernel only as the supplicant's `DRIVER COUNTRY xx`, which this sends as `NL80211_CMD_REQ_SET_REG`. The rest follows Cuttlefish's hook (START/STOP/MACADDR; vendor-only commands succeed as no-ops).
- **Regulatory database:** `regulatory.db` and `.p7s` from AOSP's `external/wireless-regdb` (2025-10-07, ISC) in `/vendor/firmware`, with its licence. The `.p7s` verifies against the `wens` certificate, which is byte-identical to the one built into our cfg80211 (C). Two SELinux rules were needed before the kernel would use it: `firmware_load` on `/vendor/firmware`, and `kernel → vendor_modprobe : key { search }`, because cfg80211's regulatory keyring takes the label of the modprobe that loads it.
- **Country.** Without telephony and without `ro.boot.wificountrycode`, the framework sets the world domain (`00`); cfg80211 then follows the access point's country element once connected (`CTRL-EVENT-REGDOM-CHANGE init=COUNTRY_IE`), and DFS channels work (C, G14).
- **Framework settings** (`wifi/overlay`): 5 and 6 GHz on; station, P2P and AP MAC randomization off, since setting a MAC address goes through the vendor HAL.
- **PNO** (scans with the screen off): the framework scans a disconnected, screen-off device only through PNO. Without a vendor HAL that means nl80211's scheduled scan (`Nl80211Native.startPnoScan`), which `config_wifi_background_scan_support` turns on. Without it, the G14 logged "PNO is not available" and then did not scan until the screen came on.
  - The MT7925 driver registers a scheduled scan (`mt792x_core.c`: `max_sched_scan_reqs = 1`), and its firmware runs one: `wifi_pno` passes on the G14 (C). If a scheduled scan fails, the framework retries and gives up, as before.
  - It only helps while the system is awake. With no WoWLAN configured, cfg80211 stops scheduled scans and disconnects at every suspend (`net/wireless/sysfs.c`: `wiphy_suspend` → `cfg80211_leave_all`), and the framework reconnects after resume (H: not yet seen on the G14 while connected).
- **Firmware: AOSP's MT7925 files** (linux-firmware `b981cd37`/`c8949c63`, build `20260414`), not ANAL-198's newer ones (`20260813`, linux-firmware `3c11e660`/`50e034a2`, 2026-08-25). Reasons: they are the ones that loaded on the G14 in its first live boot (WM and BT build times in its dmesg), and AOSP's `linux_firmware_mt7925*` modules own those paths. MediaTek's commit messages name no fixes. Switch if the G14 shows a firmware fault (none seen so far).
- **What no vendor HAL costs:** no link-layer statistics (Wi-Fi scoring falls back to RSSI), no STA+AP concurrency, no MAC randomization, no firmware logs or packet fates in bug reports. The expected log lines are "mWifiHal is null" and missing link-layer statistics; "Wiphy index not recorded for band" comes from the 6 and 60 GHz band lookups (H: harmless).

## 4. Bluetooth

AOSP's AIDL HAL `android.hardware.bluetooth-service.default`: it finds the controller through the kernel's management channel, unblocks it with rfkill and opens `hci0` as an HCI user channel, so `btusb` + `btmtk` keep owning the firmware download. OpenBook adds `/dev/rfkill` for it (ueventd, SELinux type `openbook_rfkill_device`), `bluetooth_le.xml`, a laptop class of device (computer/laptop; networking, capturing, object transfer, audio) and the profiles a laptop uses: A2DP source, AVRCP target, HID host, GATT, battery, OPP, PAN user.

- **A2DP** uses the software encoder, through the Bluetooth audio provider the audio HAL declares. Under enforcing it needs `bluetooth → hal_audio_default_tmpfs:file { read write }`; without it A2DP's session start fails and `com.android.bluetooth` aborts. On the G14 A2DP negotiates LDAC at 96 kHz/32-bit or AAC at 44.1 kHz, and with the rule an AAC headset streams under enforcing for long stretches (26 minutes) with no underflow (C).
- **No HFP gateway** yet: it needs the HAL's SCO audio path, untested. The controller logs "Enhanced Setup Synchronous Connection command is advertised, but not supported", which concerns SCO.
- In QEMU there is no controller: the HAL starts, logs "waiting for hci interface 0", and the stack stays in `BLE_TURNING_ON` (C).

## 5. Audio

**The card.** `openbook-audio-setup boot` (`audio/`, at `post-fs`, before the HAL) reads `/proc/asound/pcm` and picks the first PCM an HDA codec driver calls "… Analog", else the first playback PCM that is not HDMI/DP. It publishes `vendor.audio.primary.card`/`.device`; **OpenBook's AOSP patch** (`aosp/patches/hardware/interfaces/0001-…`) makes the example HAL's primary module read them instead of its fixed card 0, and card `-1` selects the HAL's stub driver (a VM without sound). Unset, the HAL behaves as before, so other branches' images built in the shared tree are unaffected. On the G14, `openbook-pc-setup` unbinds the dGPU's HDMI audio function, and the setup picks card 2, device 0.

**The mixer.** Android has no alsactl or UCM, and an HDA codec comes up muted: in QEMU the virtual master was `0`/off before the setup ran (C). The setup turns on Master, Speaker, Bass Speaker, Headphone and Capture switches and sets Master, Speaker, Headphone, PCM and Capture volumes to 0 dB from each control's TLV (the maximum when a control has none). Volume stays in AudioFlinger. The CS35L56 amplifiers keep their tuning's own gain (they reload it after resume), and the codec switches between speakers and headphones itself (auto-mute).

**The policy** (`audio/primary_audio_policy_configuration.xml`): 48 kHz stereo 16-bit in and out, because the G14's speaker DAC (node `0x02`) takes nothing else and the HAL opens ALSA without resampling. Speaker and built-in mic are attached; wired headphones, headset and headset mic are connectable, and `config_useDevInputEventForAudioJack` lets the HDA jack switches drive them.

**The HAL's clock (AOSP patch `0002-…`).** The example HAL paces synchronous streams to the wall clock and drops a buffer whenever a stream falls behind. That is an emulator workaround (b/302587331). Its MonoPipe is one buffer deep (4096 frames, 85 ms): output that does not fit is dropped, and input that has not arrived yet is padded with silence. On the G14 a 3.5 s AAudio capture got 4096 frames of silence 7 times, and the Android loopback lost most of its tone, while the same loopback straight on ALSA was clean. With `vendor.audio.primary.pacing=false`, which `openbook-audio-setup` sets whenever it finds a sound card, the stream is clocked by the device instead:
- no wall-clock pacing;
- a pipe two buffers deep;
- a writer that waits for room (MonoPipe's blocking write);
- a reader that waits up to two buffers' worth for its data.

Unset (another branch's image, or a VM without sound), nothing changes. Turning off only the pacing kills the output, because the writer then overruns a non-blocking pipe; that is why the patch changes the pipe too. In QEMU the tone reaches the codec whole with the patch (2.05 s of a 2 s tone, 2 glitched 50 ms windows, against 1.65–1.70 s and 22–24 with AOSP's pacing), and capture is no longer padded (0 insertions, against 7 plus 1 skipped transfer). On the G14 the Android loopback is clean (`audio_android_clean`), and an hour of speaker and browser playback logs no HAL padding, drops or ALSA errors (C).

**SELinux: the HAL's stream queues (C).** The HAL's stream message queues are memfds, which on this kernel carry their creator's tmpfs type. Denied writing its own queues, the HAL failed every stream open, AudioPolicy had no output and every AudioTrack got `NO_INIT`. `hal_audio_default` now gets its own tmpfs type, which audioserver may map. These are the "audio HAL writing a tmpfs memfd" denials ANAL-199 listed as harmless: they were, while nothing played.

**SoundPool (C, QEMU and G14, enforcing).** SoundPool hands AudioFlinger a static AudioTrack whose samples are in a memfd the app created: SystemUI's lock and unlock sounds, and any app's SoundPool. On this kernel that memfd is an `appdomain_tmpfs` file with the app's categories (`s0:c512,c768`). Its fd transfer to `audioserver` was denied, so SystemUI got "AudioFlinger could not create track" and no sound played.
- The fix is one TE rule, `allow audioserver appdomain_tmpfs:file { getattr map read write }` (`sepolicy/system_ext/audioserver.te`). It is the tmpfs-file form of AOSP's `audioserver appdomain:memfd_file` grant, and AOSP gives `mediaserver`, `system_server` and `mediaextractor` the same rule.
- MLS needs no change: AOSP's `private/mls` exempts `appdomain_tmpfs` from its read and write constraints, and only `open` is limited by category; the fd arrives already open.
- With it, the unlock sound at boot reaches the codec in QEMU (the length of `Unlock.ogg`), and on the G14 its track is created 50 ms after `keyguardDone` and the sound is heard.

**App audio (C, G14).** Apps that run with MLS categories (the browser) got no AudioTrack ("Could not get control block") while `untrusted_app_29 → audioserver_tmpfs:file { write }` was denied. With the rule from PR #52, Chrome and WebView play to the speakers and over A2DP under enforcing.

**MediaPlayer (ANAL-198, #97).** MediaPlayer plays in `mediaserver` (NuPlayer), whose AudioSink is an AudioTrack; AudioFlinger hands it the track's control block, a memfd labelled `audioserver_tmpfs`. Notification sounds, ringtone previews and every app's MediaPlayer use this path.
- Without a rule the binder transfer fails (`BR_FAILED_REPLY ... Operation not permitted`) and "AudioTrack: createTrack_l(0): Could not get control block" is logged; the G14 showed this for SystemUI's low-battery sound.
- AOSP grants this as `mediaserver audioserver:memfd_file`, which needs `memfd_class`; AOSP 17's tmpfs-form rules cover only apps' memfds. The image has `allow mediaserver audioserver_tmpfs:file { getattr map read write }` (`sepolicy/system_ext/mediaserver.te`). Both domains are `s0`, so MLS is not involved.
- In QEMU, without the rule a notification sound and the low-battery sound fail, and with it both play. Android mutes notification sounds for the first 120 s after boot, so such a test has to wait.

## 6. Tests

| Tool | What it does |
|---|---|
| `openbook-hwtest [wifi\|bt\|audio]` (`/system_ext/bin`, userdebug) | Wi-Fi: driver, regulatory domain and database, enable, scan (counts per band), connection (frequency, signal, bit rates), DHCP, gateway ping, Android's internet validation, iperf3 both ways to a configured server. Bluetooth: HAL, enable, profiles, number of bonded devices. Audio: cards, PCMs, mixer, policy, the ports and jacks (`audio-routes`), and two speaker-to-mic loopbacks; the Android one names the Speaker and Built-In Mic ports (so a paired Bluetooth device doesn't take the tone), and counts what the HAL padded, dropped or skipped meanwhile. Wi-Fi also starts and stops one scheduled scan (`wifi-pno`) and reads the connection at its own step. One `HWTEST {json}` line per result; SSIDs, device names and addresses are masked |
| `openbook-audio-setup test` | loopback on ALSA directly: plays 2 s of 1 kHz at −15 dBFS while recording the built-in mic, and measures the tone (Goertzel) against the half second before it |
| `openbook-audio-test` | the same through Android (AAudio → AudioFlinger → HAL), i.e. what apps get; `--out-device/--in-device` take the policy's port IDs |
| live stick, "save logs" entries | `openbook-live-init` runs `openbook-hwtest` in its final capture (`hwtest-final.txt`, `hwtest_rc` in `summary.json`), with settings from `openbook/hwtest.conf` on the stick's ESP (`iperf3_server=…`; letters, digits and `.:_-` only; never credentials) |
| `live-report.py` | turns the `HWTEST` lines into verdicts: `wifi_regulatory`, `wifi_scan`, `wifi_pno`, `wifi_connected`, `wifi_dhcp`, `wifi_gateway_ping`, `wifi_internet`, `wifi_iperf3`, `bt_enabled`, `bt_paired`, `audio_card`, `audio_loopback_alsa`, `audio_loopback_android`, `audio_android_clean` (heard, and the HAL padded, dropped and skipped nothing meanwhile), `audio_routes` (Speaker and Built-In Mic ports, jack input devices, wired or A2DP output connected, the HAL's pacing) |
| `openbook-hwtest bridge` (ANAL-200) | the arm64 native bridge: its configuration, then `/system/bin/arm64/openbook_bridge_check` through the translator. Verdicts `bridge_config`, `bridge_exec`, `bridge_id_registers`, `bridge_fp_estimates`, `bridge_int_simd`; `all` runs it first (`docs/digitalis.md`) |
| `scripts/audio-net-qemu.sh` | the QEMU rig (§8): an HDA card recorded to a WAV file, and two `mac80211_hwsim` radios with an access point on one |
| `scripts/installer/expect-g14-soundpool.json` | QEMU, with `QEMU_AUDIO=1 scripts/g14-qemu.sh`: SystemUI's unlock sound at boot, then with the lock screen turned on for the test, sleep, wake and dismiss. It reports the SoundPool denials and track failures; `wav-tone.py --activity` then lists what reached the codec |

The tone counts as heard when 1 kHz comes back at least 20 dB above its level before the tone and carries at least a fifth of the energy, averaged over 50 ms slices; slices under 90% are counted as glitches (`glitched_slices`), which is how dropped buffers show (`openbook_audio_logic_test`, host tests, C).

## 7. On the G14: owner checklist

For a live stick written from a current image.

1. **Optional, for the throughput test:** on a PC on the same Wi-Fi network, run `iperf3 -s` (Arch: `sudo pacman -S iperf3`) and note its address (`ip -4 addr`). Have a Bluetooth device ready to pair: headphones or a speaker is best, a mouse or a phone also counts. Have wired headphones ready for the jack.
2. **Write the stick** (erases it; reports already on it are copied to the PC first). From any OpenBook checkout on the build host:
   ```bash
   OPENBOOK_WRITE_CONFIRM=/dev/disk/by-id/usb-<stick> \
     scripts/installer/write-stick.sh ~/anybook/installer/out/<image>.img /dev/disk/by-id/usb-<stick>
   ```
   Done when it prints `stick powered off: safe to unplug`.
3. **Optional: tell the stick where the iperf3 server is.** Plug it back in; its `OPENBOOK` partition mounts. Then:
   ```bash
   printf 'iperf3_server=192.0.2.20\n' > /run/media/$USER/OPENBOOK/openbook/hwtest.conf && sync   # your PC's address
   ```
   Eject it. Only the address goes there, never a Wi-Fi password.
4. **Boot "OpenBook"** (Esc → USB stick → Enter). On the desktop:
   - Settings → Network & internet → Internet: turn Wi-Fi on, pick your network, enter its password. Hoped for: "Connected". The network stays saved on the stick.
   - Settings → Connected devices → Pair new device: pair the Bluetooth device. With headphones, play a sound through them, turn them off and on again, and play again.
   - Speakers: Settings → Sound & vibration → Default notification sound (or a ringtone): choosing a sound plays it, from both speakers. Then plug wired headphones in while sound plays: it should move to the headphones, and back when you unplug.
   - Play a video in the browser.
   - Note or photograph anything odd. Hold the power button to turn off.
5. **Boot "OpenBook - save logs to this USB stick"** (↓ once, Enter). After the boot it runs the checks by itself: **two 2-second beeps from the speakers** (the microphone test: keep the room quiet and the lid open), a Wi-Fi scan and measurements, Bluetooth status. Then it shuts down, about 5 minutes in all. If the screen stays black, wait 15 minutes before holding the power button.
6. Plug the stick into the build host and reply "stick attached". The agent runs, read-only:
   ```bash
   scripts/installer/read-stick-logs.sh /dev/disk/by-id/usb-<stick>
   python3 scripts/installer/live-report.py <data dir>/installer/g14/stick-<UTC>/live-NNN --expect g14
   ```

**What counts:**

| Check | Verdict or log that counts |
|---|---|
| Android playback and capture without gaps | `audio_loopback_android` yes and `audio_android_clean` yes (`hal_input_pads`, `hal_output_drops` and `hal_skipped_transfers` all 0), with `out_device`/`in_device` on the Speaker and Built-In Mic ports |
| Playback and capture on ALSA | `audio_loopback_alsa` yes |
| Wi-Fi | `wifi_connected` yes in the same run as `wifi_dhcp`; `wifi_iperf3` with Mbit/s both ways when a server is configured |
| PNO | `wifi_pno` yes (`driver_offers` true) |
| Bluetooth | `bt_paired`; in the default boot, no `com.android.bluetooth` tombstone and no `bluetooth hal_audio_default_tmpfs` denial |
| App audio under enforcing | sound from the browser, and no `untrusted_app_29 audioserver_tmpfs` denial |
| UI sounds (SoundPool) | nothing to do: SystemUI plays the unlock sound at every boot. No `audioserver appdomain_tmpfs` denial and no "AudioFlinger could not create track" in the default boot's logs |
| MediaPlayer sounds | the notification sound and ringtone preview play; no "Could not get control block" |
| Headphone jack | the sound moves; logcat `ACTION_HEADSET_PLUG ... plugged in: true`; `audio_routes` `wired_connected` if they are still plugged in at "save logs" |

The Bluetooth device can stay paired: the loopback no longer follows the default route, and `audio_routes` reports `a2dp_connected`. The raw facts are in `hwtest-final.txt`.

**Unattended (device agent, ANAL-193/194):** the same entry with `androidboot.openbook.logs_after=reboot` (`docs/installer.md` §11.7) and `openbook/hwtest.conf` on the ESP. Wi-Fi and Bluetooth need one interactive connect and pairing first; both stay on the stick's `/data`. `report.json` has the verdicts.

## 8. QEMU rig

`scripts/audio-net-qemu.sh payload` builds a test disk for the guest: `mac80211_hwsim` with the cfg80211 and mac80211 it was built with (the virtual-device Kleaf dist; `modversions-check.py` shows all their CRCs match our vmlinux, while our own mac80211 differs in `ieee80211_alloc_hw_nm`), AOSP's `hostapd` (built, not installed: `BOARD_HOSTAPD_DRIVER`), `openbook-test-dhcpd` (a 100-line DHCP server, static, NDK), a shim that lets hostapd skip its AIDL registration (otherwise it blocks on `/dev/vndbinder`), and the access point scripts.

`run IMG RUN` boots the image with QEMU's HDA controller and duplex codec (output recorded to `audio-out.wav`) and the test disk on USB. In the guest (`guest-test.sh`), as root: the audio checks, then the radio swap (the image's own Wi-Fi drivers unloaded, hwsim with two radios loaded, the second moved into a network namespace with hostapd, the DHCP server and an iperf3 server), a framework restart so it resolves nl80211 again (the swap renumbers the nl80211 family, a QEMU-only effect), connect to `openbook-test` (WPA2-PSK) through `cmd wifi`, and `openbook-hwtest wifi` against that iperf3 server.

Limits: QEMU's codec records silence and there is no Bluetooth controller, so "heard" is false and Bluetooth stays off by design. hwsim has no scheduled scan, so `wifi_pno` is no in the VM; the framework's hardware-PNO path still reaches `Nl80211Native.startPnoScan`, retries 5 times and gives up. The only denials in the VM are SystemUI's `bluetooth_lea_prop` reads (AOSP's own).

Gotcha: an image built from a shared AOSP tree can pick up another branch's stale copied outputs (SurfaceFlinger then finds no EGL). `docs/BUILD.md` touches the device tree before each build for this reason.

## 9. Open items

- **Still to show on the G14:** iperf3 throughput; the headphone jack switching; the Bluetooth headset reconnecting after it was turned off and on (not seen once: nothing reconnected in 2.5 minutes); MediaPlayer sounds with the `mediaserver` rule.
- **Headphone jack:** WiredAccessoryManager warns "Both input event and extcon are used for audio jack" (H: harmless, since there is no extcon jack on this kernel).
- **Gateway ping:** on one network `wifi_gateway_ping` failed (100 % loss) while `wifi_internet` passed. H: that access point does not answer ICMP echo.
- **Wi-Fi at suspend:** with no WoWLAN, every s2idle disconnects Wi-Fi, and the framework reconnects after resume (§3). A wake-on-WLAN setup would need a vendor HAL or our own nl80211 call.
- **Wi-Fi country:** an installer question (ANAL-191) could pass the country in bootconfig instead of the world domain at boot.
- **No HFP gateway** (headset microphones in calls), no LE Audio, no Wi-Fi Direct or hotspot: each needs work and a test of its own.
- **HDMI/DP audio** (the Radeon's card) is not routed.
- **The AOSP tree is shared:** the audio HAL patch stays applied for other branches' builds. Unset, its properties keep AOSP's behaviour, so their images are unaffected.
- **`wifi_hal_prop`:** system_server is denied reading `wifi.interface` once per Wi-Fi start (AOSP policy); it falls back to `wlan0`, which is right here.

## 10. On the G14: first results (2026-10-17)

Two live-stick sessions (a default boot under enforcing, then "save logs"), read with `live-report.py --expect g14`.

- **Wi-Fi:** scans found 82–91 networks across 2.4, 5 and 6 GHz; connected on 5320 MHz (channel 64, DFS), 160 MHz HE, −37 dBm, link rate 1201 up / 1922 down Mbit/s; DHCP, gateway ping with 0 % loss, internet validated (HTTP and HTTPS probes 204).
- **Bluetooth:** `btmtk` set up `hci0` in 0.29 s; SSP pairing took 4 s and A2DP connected with LDAC at 96 kHz/32-bit.
- **Audio:** card 2 set up, both amplifiers tuned at boot and after resume; the ALSA loopback heard the tone about 40 dB over the noise bin.

What these results changed:

| Found | Change |
|---|---|
| The Android loopback heard the tone in only 6 of 30 slices; 7 silence insertions in each 3.5 s capture | The codec-paced HAL, patch 0002 (§5) |
| The Android loopback's tone went to the paired A2DP device | The loopback names the Speaker and Built-In Mic ports (§6) |
| hwtest reported `wifi_connected` no while connected: it reused the status read when it turned Wi-Fi on | hwtest reads the connection at its own step |
| "PNO is not available" with the screen off | PNO through the driver's scheduled scan (§3) and the `wifi-pno` step |
| Under enforcing, A2DP start failed and Bluetooth aborted; apps with MLS categories got no AudioTrack | The two SELinux rules of PR #52 (§4, §5) |

Other denials in the enforcing boots, all AOSP's own and harmless here: `system_server → wifi_hal_prop` (§9), `platform_app → bluetooth_lea_prop` / `bluetooth_finder_prop` (SystemUI reads Bluetooth flags), `keystore → hal_gatekeeper_service { find }`.

## 11. On the G14: Android audio and Bluetooth under enforcing (2026-10-18)

One integrated live stick: an hour-long default boot under enforcing, then "save logs". All C.

| Check | Result |
|---|---|
| Android playback and capture without gaps | **`audio_android_clean` yes**: 0 of 30 slices glitched and no HAL padding, drops or skips (`out_device` 2 / `in_device` 5). The hour of speaker and browser playback logged no HAL padding, drops or ALSA errors. Patch 0002 holds on the G14 |
| PNO on the MT7925 | **`wifi_pno` yes**: "Start PNO scan succeeded" and "PNO scan started successfully". The framework's own screen-off use is still to be seen |
| Wi-Fi | connected to a 2.4 GHz network (2437 MHz, −22 dBm, Wi-Fi 6, two streams, 286.7 Mbit/s link rate), DHCP, internet validated, no disconnect all session. `wifi_gateway_ping` no (§9) |
| Bluetooth audio under enforcing | **works**: an AAC headset paired, A2DP at 44.1 kHz streamed four times, the longest 26 minutes, with no tombstone, denial, underflow or drop |
| Bluetooth reconnect | **not seen** (§9) |
| App audio under enforcing | **works**: Chrome and WebView Shell played to the speakers and over A2DP |
| UI sounds (SoundPool) | **works**: the unlock sound's track is created at boot, and the owner heard it |
| MediaPlayer sounds | **failed** on that image (SystemUI's low-battery sound); the image now carries the `mediaserver` rule (§5) |
| Headphone jack | **not shown**: every `ACTION_HEADSET_PLUG` says "plugged in: false". The codec's jack input device is there (`audio_routes`: 1 headphone and 2 mic jacks) |

## 12. Sources (accessed 2026-10-16/18)

- AOSP 17 (`android17-release`): `frameworks/opt/net/wifi/libwifi_hal/Android.bp` (`desktop` → `libwifi-hal-desktop`), `packages/modules/Wifi/service/.../WifiNative.java` and `WifiInjector.java` (no-HAL mode, wificond migration), `build/release/flag_values/cp2a/RELEASE_DISABLE_WIFICOND.textproto`, `external/wpa_supplicant_8` (`board_config_wpa_supplicant.mk`, `driver_nl80211.c`), `external/wireless-regdb`, `hardware/interfaces/audio/aidl/default` (`primary/StreamPrimary.cpp`, `alsa/Mixer.cpp`, `XsdcConversion.cpp`), `hardware/interfaces/bluetooth/aidl/default` (`BluetoothHci.cpp`, `net_bluetooth_mgmt.cpp`), `device/google/cuttlefish` (Wi-Fi and Bluetooth configuration), `device/generic/goldfish/wifi`, `system/sepolicy`.
- android.googlesource.com project list (2026-10-16): no `device/google/desktop`.
- linux-firmware history of `mediatek/mt7925` (gitlab.com/kernel-firmware/linux-firmware, API, 2026-10-17).
- Kernel (OpenBook android17-6.18 tree): `net/wireless/reg.c`, `net/wireless/certs/wens.hex`, `sound/hda/codecs/side-codecs/cs35l56_hda.c`, `sound/hda/codecs/realtek/alc269.c` (GA403U quirk), `net/wireless/sysfs.c` (`wiphy_suspend`), `drivers/net/wireless/mediatek/mt76/mt792x_core.c` (scheduled scan limits), `drivers/net/wireless/virtual/mac80211_hwsim.c` (no scheduled scan).
- AOSP 17, for §3 and §5: `packages/modules/Wifi/service/.../scanner/WificondScannerImpl.java` (`isHwPnoScanRequired`), `scanner/WifiScanningServiceImpl.java` ("PNO is not available"), `WifiConnectivityManager.java` (`getAllScanOptimizationNetworks`), `nl80211/Nl80211Native.java` (`startPnoScan`), `WifiShellCommand.java` (`start-nl80211-pno-scan`), `hardware/interfaces/audio/aidl/default/alsa/StreamAlsaMonoPipe.cpp` and `primary/StreamPrimary.cpp` (pacing, b/302587331).
