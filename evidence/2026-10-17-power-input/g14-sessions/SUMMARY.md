# Power and input from the owner's G14 sessions (ANAL-178, 2026-10-17)

Read from ANAL-176's read-only host copies of the two sessions, never from the stick:
- `anal178c`: `g14/stick-20261017T122351Z`, image `openbook-live-20261017-anal178c`; a default (enforcing) boot, then "save logs";
- `anal176s`: `g14/stick-20261017T135624Z`, `anal178c` plus PR #52; a default boot, then "save logs".

The power-check and graphics-check entries were not booted, so there is no `hwcheck-*` and no S0i3 bisect. Analysis: `docs/power-input.md` §7.

| File | What |
|---|---|
| `anal178c/report.{md,json}`, `anal176s/report.{md,json}` | `scripts/installer/live-report.py --expect g14` from this branch: the earlier verdicts plus `health_hal`, `lid_events`, `epp_modes`, `touchpad_clock_warnings`, and `repeat_frames` in `touchpad_clock` |
| `*/power-events.txt` | Sleep, wake, suspend, lid and shutdown lines of both boots, from the persisted logcat in `prior-boots.tar.gz` |
| `*/dmesg-suspend.txt` | The save-logs boot's suspend lines (alarmtimer `-EBUSY`, the 20 s s2idle, wake IRQs, amd_pmc) |
| `facts.json` | Battery (`BAT`, `dumpsys battery`), EPP, power, thermal HAL, sensors, LEDs, backlight, and the touchpad's `/proc/bus/input/devices` entry and clock numbers, both sessions |
| `touchpad/*-touchpadev-excerpt.txt` | The touchpad's raw events around the first `BTN_TOOL_FINGER REPEAT` frame |
| `touchpad/elan-04f3-3315-layout.json` | Field layout of the touchpad's input report (ID 84), decoded from its descriptor (`scripts/power/touchpad/elan-04f3-3315.rdesc.hex`); 8 input usages on the vendor page `0xFF01` |
| `qemu/` | `scripts/power/touchpad/touchpad-qemu.sh` before and after the EventHub patch: 173 → 0 repeat frames, 172 → 0 "Clock changed backwards" |

## Results
| Check | `anal178c` | `anal176s` |
|---|---|---|
| Touchpad repeat frames in the 20 s capture / frames | 105 / 2,130 | 32 / 1,662 |
| "Clock changed backwards" in the save-logs boot | 180 | 162 |
| `health_hal`: charge counter vs `charge_now` (µAh), state of health, Android health | 1,437,000 vs 1,430,000; 88.7 %; GOOD | 1,230,000 vs 1,206,000; 88.7 %; GOOD |
| `epp_modes`: EPP values the power HAL set (count) | balance_performance 24, performance 21, power 3 | balance_performance 28, performance 28 |
| `s0i3`: Android suspends in the save-logs boot | 1 s2idle of 20 s, 3 refused (`alarmtimer`), not deepest | none |
| `lid_events` | not used | not used |
| `lid_and_power_config`, `key_layouts`, `kbd_backlight` | yes | yes |
| Power menu | Restart → `reboot,userrequested` | Power off → `shutdown,userrequested` |

Redaction: `live-report.py`'s `redact()` (MAC addresses, serial numbers, SSIDs), plus IPv4 addresses in the event excerpts. The full redacted logs of the `anal178c` session are in ANAL-176's `evidence/2026-10-17-g14-desktop/g14-anal178c/` (PR #52).
