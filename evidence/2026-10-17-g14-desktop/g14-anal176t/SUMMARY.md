# G14 boots of `openbook-live-20261017-anal176t` (ANAL-176, 2026-10-17 14:57–15:41Z)

`anal176t` is `anal176s` plus the two audio policy lines from PR #52 (`../anal176t/`, sha256 `8ba0eff5…`). The owner ran:
- the default entry (enforcing, 14:57:45–15:06:52Z, with the lid test);
- "save logs" (`live-001`);
- the power check;
- the graphics check (`live-002`).

ANAL-178 copied the stick read-only to `<data dir>/installer/g14/stick-20261017T154112Z/`. This directory has redacted extracts only:
- Bluetooth addresses and the headset's name are removed;
- the full logcats stay on the host.

## Default entry, enforcing (from the persisted logcat in `live-001/prior-boots.tar.gz`)

| | Result | Source |
|---|---|---|
| Desktop | 29.1 s (`sf_stop_bootanim: 29087`) on the freshly written stick | `boot1-default-enforcing/timeline.txt` |
| Storage notice, lock screen | `Not managing disk 8:0`; the lock screen was dismissed at boot, with no sleep | `timeline.txt` |
| Frames | **0** pin failures and 0 failed presentations; 12 refused test commits, during bring-up only | counts in `timeline.txt` |
| **Bluetooth audio** | Bonded 14:59:02.9, **A2DP Connected 14:59:03.8**; the audio HAL registered the A2DP session (`A2DP_SOFTWARE_ENCODING_DATAPATH`); AudioFlinger opened two `BLUETOOTH_A2DP` outputs; the headset became the active A2DP device. **0 fatal signals, 0 `FAILED_TRANSACTION`, 0 tombstones** (`anal176s`: 2 Bluetooth aborts). The link closed at 15:00:53 without a stream having started (`co_started:0`) | `timeline.txt` |
| Playback | Ringtone previews (RingtonePicker opened 5 times): **15 × `NuPlayerDecoder: Failed to create audio/vorbis decoder`** in `mediaserver`, 1 ms after the source started. Nothing played, so nothing reached Bluetooth. Only the `__ApexCodecs__` Codec2 service was listed; `Could not open DMA-BUF heap named: system` appears 294 times | `timeline.txt` |
| App audio | No browser or other SDK 28+ app played sound: 0 `Could not get control block`, 0 `audioserver_tmpfs` denials. The fix is not exercised | counts |
| Denials | 43 lines, 4 kinds, all known: `keystore` → Gatekeeper, `platform_app` → Bluetooth properties (2), `system_server` → `wifi_hal_prop`. The `bluetooth` and `untrusted_app` audio denials are gone | `boot1-default-enforcing/avc.md` |
| End | Clean shutdown after 9 minutes | `timeline.txt` |

## Other boots

- **Save logs** (`live-001`): `boot_completed` 28.2 s, live-report verdicts in `live-001/report.md`; the archive of earlier boots rc 0, 1.6 MB.
- **Graphics check** (`live-002`, permissive; ANAL-177's run, read there):
  - At 166 s a dEQP case hung the GPU: `ring gfx_0.0.0 timeout`, then a MODE2 reset, `VRAM is lost`.
  - SystemUI (`EGL_CONTEXT_LOST`) and SurfaceFlinger (`Failed to create a valid texture`) aborted at 15:27:00. Zygote restarted at 15:27:05 and SystemUI was back at 15:27:07: the whole UI restarted and recovered.

## Not shown by the logs (for ANAL-192's checklist)

- Audible sound over Bluetooth.
- Browser video with sound.
- Ringtone and notification sounds. These need the decoder failure fixed first: the missing system DMA-BUF heap is suspected (H), and it is reproducible in QEMU, whose log has the same heap errors.
