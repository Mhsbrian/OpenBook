| Run | Image | audio-card | ALSA tone at the codec | AAudio tone at the codec (s / dBFS / glitched 50 ms windows) | Wi-Fi scan | connect | DHCP | ping | iperf3 up/down Mbit/s |
|---|---|---|---|---|---|---|---|---|---|
| c | `anal179-c` | yes | 2.0 s, -18.1 dBFS, 0 | 1.65 / -51.8 / 24 | yes | no | no | — | —/— |
| d | `anal179-c` | yes | 2.0 s, -18.1 dBFS, 0 | 1.65 / -52.2 / 24 | no | no | no | — | —/— |
| e | `anal179-c` | yes | 2.0 s, -18.1 dBFS, 0 | 1.65 / -51.8 / 23 | yes | yes | yes | yes | 661/715 |
| f | `anal179-stick-a` | yes | 2.0 s, -18.1 dBFS, 0 | 1.65 / -34.0 / 23 | yes | yes | yes | yes | 742/644 |
| g | `anal179-stick-b` | yes | 2.0 s, -18.1 dBFS, 0 | none | yes | yes | yes | yes | 668/577 |
| h | `anal179-stick-c` | yes | 2.0 s, -18.1 dBFS, 0 | 1.65 / -34.0 / 24 | yes | yes | yes | yes | 770/712 |
| i | `anal179-stick-d` | yes | 2.0 s, -18.1 dBFS, 0 | 1.65 / -34.0 / 24 | yes | yes | yes | yes | 733/650 |
| j | `anal179-g14r-b` (patch 0002, PNO) | yes | 2.0 s, -18.1 dBFS, 0 | **2.05 / -32.7 / 2** | yes | yes | yes | yes | 746/706 |
| k | `anal179-g14r-b`, silent card (`AUDIO=none`) | yes | — (no WAV) | — (no WAV) | yes | yes | yes | yes | 705/702 |
| l | `anal179-g14r-c` (+ `audio-routes` fix) | yes | 2.0 s, -18.1 dBFS, 0 | **2.05 / -32.7 / 2**; AOSP pacing: 1.70 / -34.1 / 22 | yes | yes | yes | yes | 681/732 |
| m | `anal179-g14r-c`, silent card | yes | — (no WAV) | — (no WAV) | yes | yes | yes | yes | 697/706 |
| n | `anal179-g14r-c` (PNO check with validation off) | yes | 2.0 s, -18.1 dBFS, 0 | **2.05 / -32.7 / 2**; AOSP pacing: 1.65 / -33.9 / 23 | yes | yes | yes | yes | 755/721 |
| o | `anal179-g14r-d` (this branch merged with `main`: PR #52, #55) | yes | 2.0 s, -18.1 dBFS, 0 | **2.05 / -32.7 / 2**; AOSP pacing: 1.70 / -33.8 / 23 | yes | yes | yes | yes | 742/592 |
| p | `anal179-g14r-d`, silent card | yes | — (no WAV) | — (no WAV) | yes | yes | yes | yes | 656/711 |

## Runs j–n: the codec-paced HAL (patch 0002) against AOSP's wall-clock pacing

Runs l–p play the AAudio loopback twice (o and p on this branch merged with `main`, i.e. with PR #52's SELinux rules and vold patch) in the same boot: first as built (`vendor.audio.primary.pacing=false`, set by `openbook-audio-setup`), then with AOSP's pacing back on (the property set to true and the HAL restarted; `sections/paced.txt`). Both use the Speaker and Built-In Mic ports. The HAL counts come from the HAL's own log during each 3.5 s run.

| | Patch 0002 (as built) | AOSP pacing | G14 session 1 (AOSP pacing) |
|---|---|---|---|
| AAudio tone at the codec, WAV backend (runs l, n, o) | 2.05 s, 2 glitched 50 ms windows, each time | 1.70 s / 22, 1.65 s / 23, 1.70 s / 23 | 24 of 30 slices glitched at the mic |
| Capture: HAL silence insertions / skipped transfers, silent card (runs m, p) | **0 / 0**, 0 / 0 | 7 / 1, 7 / 0 | 7 / 1 |
| Output: HAL "dropping" warnings (runs l, m) | 0 | 0 | — |

Under AOSP pacing the output loses 0.35 s with no HAL warning: the loss shows only at the codec. H: these are ALSA underruns, as the paced writes fall behind QEMU's codec clock. `hal_output_drops` therefore counts only drops at the pipe.

With the WAV backend, QEMU's capture side has no source, and the HAL pads either way (43 insertions in runs j and l). That is why capture is measured with the silent card.

**PNO (run n).** The screen was turned off and the test access point was then taken away. The framework took the hardware-PNO path: `WifiScanningService` `addHwPnoScanRequest` → `WificondScannerImpl` → `Nl80211Native.startPnoScan`. hwsim has no scheduled scan, so it failed ("PNO scan failed with reason: -1"), was retried, and stopped after five attempts. Without `config_wifi_background_scan_support`, the G14 logged "PNO is not available" instead. In runs j–l the test network was excluded from PNO, because its validation had failed (the test AP has no internet); run n reconnects with validation off for this step. hwtest's `wifi-pno` step is no on hwsim (`driver_offers` false), as expected.

