# ANAL-179 on the owner's `anal192d` session (G14, 2026-10-18)

Stick `openbook-live-20261018-anal192d` (`main` `81578c1` + #83). I read it from the host copy `~/anybook/installer/g14/stick-20261018T123221Z/`, read-only. Everything here is redacted: MAC and Bluetooth addresses, IPv4 addresses, network names and IDs.

| File | What |
|---|---|
| `report.md`, `report.json` | `live-report.py --expect g14 --redact` (`main`'s) on the save-logs boot (`live-001`, enforcing off) |
| `hwtest-final.txt`, `summary.json` | that boot's `openbook-hwtest` output |
| `digest-default-boot.txt` | the default boot (SELinux enforcing, 11:00:41–11:59Z), from its persisted logcat: denials, the unlock sound's track, the failing low-battery sound, HAL warnings, media audio focus per app, jack, Wi-Fi, Bluetooth and A2DP |
| `stick-provenance.txt` | the stick's build record |

## Results

- **`audio_android_clean` yes.**
  - The speaker → mic loopback through AAudio was heard, with 0 of 30 slices glitched and 0 HAL padding, drops or skips. Before patch 0002, `anal178c` had 24 of 30 glitched and 7 silence insertions.
  - The default boot's hour of playback logged no HAL padding, drops or ALSA errors either.
- **`wifi_pno` yes.** The MT7925 accepted a scheduled scan through the framework's nl80211 code ("Start PNO scan succeeded").
- **Wi-Fi:** connected to a 2.4 GHz network (2437 MHz, −22 dBm, Wi-Fi 6, two streams, 286.7 Mbit/s), with DHCP, and internet validated by the HTTP and HTTPS probes. It never disconnected all session.
  - `wifi_gateway_ping` NO: 5 of 5 pings were lost. H: this access point does not answer ICMP echo.
  - iperf3: not configured.
- **Bluetooth audio under enforcing works.**
  - An AAC headset paired, and A2DP ran at 44.1 kHz. It streamed four times between 11:27:39 and 11:56:07, the longest stretch 26 minutes.
  - There was no tombstone, no Bluetooth or audio-HAL denial, and no underflow.
  - The headset dropped the link at 11:56:34 and did not reconnect before power-off.
- **App audio under enforcing works:** Chrome and WebView Shell played media, with no `audioserver_tmpfs` denial and no track failure.
- **The unlock sound at boot (SoundPool):** AudioFlinger created its track 50 ms after `keyguardDone`, with no denial. The owner confirmed hearing it (ANAL-179, 2026-10-18).
- **MediaPlayer under enforcing fails.**
  - SystemUI's low-battery sound got "Could not get control block" at 11:51:48, after `mediaserver → audioserver_tmpfs:file { read write }` was denied.
  - ANAL-198's PR #97 adds the rule.
- **Headphone jack:** no plug event (every `ACTION_HEADSET_PLUG` reports false), so it is not shown.

Other denials under enforcing are outside this issue: `isolated_app app_data_file` (130 lines), `openbook_installd`, and AOSP's own `bluetooth_lea_prop`, `wifi_hal_prop` and keystore → gatekeeper.
