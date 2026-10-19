# The owner's `anal192d` session: touchpad, Battery Saver, power (ANAL-178, 2026-10-18)

The stick is `openbook-live-20261018-anal192d` (`main` `81578c1` + #83), with the EventHub patch in its product. The session ran from about 11:00 to 12:15 UTC:
- a 59-minute default boot, whose persisted logcat is in `live-001/prior/`;
- "save logs" (`live-001`);
- the ARM apps check (`live-002`).

ANAL-192 made the read-only host copy (`<data dir>/installer/g14/stick-20261018T123221Z`). ANAL-178 read a local copy of it. Analysis: `docs/power-input.md` §7.7.

| File | What |
|---|---|
| `live-001-report.{md,json}`, `live-002-report.{md,json}` | `live-report.py --expect g14` from this branch (redacted) |
| `clock-errors.txt` | The 71 "Clock changed backwards" of the persisted logcat, with the gaps between them |
| `battery-level.txt` | Android's battery level and status over the default boot |
| `facts.json` | Battery, supply, suspend, power, EPP, sensors and backlight from both captures |
| `qemu/` | Frames without `MSC_TIMESTAMP` in QEMU before and after `0002`, the converter unit tests, and the early touchpad capture in a save-logs boot (`SUMMARY.md` there) |

## Results
| Check | Result |
|---|---|
| Touchpad clock errors, default boot | **71 per hour** (70 in 59 min), against 6,700–19,600 per hour in the default boots of `anal178c`, `anal176s` and `anal176t` before the EventHub patch |
| What is left | Sparse, often in pairs 8 ms apart after taps and clicks. hid-multitouch's palm lift-off frames reproduce it in QEMU (4 errors for 4 strokes); fixed by `0002` (no error at a lift-off) |
| Touchpad raw capture (`TOUCHPADEV`) | Empty: it ran after openbook-hwtest, not when the owner used the touchpad. `live-init` now records it from boot completion (`qemu/tpearly-*`) |
| Battery Saver | Not turned on: no dialog, no `battery_saver_mode`, no `balance_power`. The laptop ran on battery throughout (`plugged 0`) |
| Battery | 42 % → 20 % in 51 min of use, about 15.5 W. The save-logs boot drew 12.3 W; the ARM check charged at 12.2 W |
| Health HAL | GOOD. State of health 88.7 % → 87.8 % between the two boots, as the firmware recalibrated the full charge (4.063 → 4.023 Ah); the charge counter stays within 4 % of `charge_now` |
| EPP | `performance`/`balance_performance` 61 times each (app launches). The screen never went off; no suspend |
| S0i3 | No new data: neither the power check nor the Linux run was done |
