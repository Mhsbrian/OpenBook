# The owner's `anal176t` session: lid test, power check (ANAL-178, 2026-10-17)

Stick `openbook-live-20261017-anal176t` (ANAL-176's image: `anal178c` plus PR #52 and its audio policy; the power check and graphics check on its ESP; no EventHub fix). The owner reported "all tests done" on ANAL-178. ANAL-178 copied the stick with `scripts/installer/read-stick-logs.sh` (read-only) to `<data dir>/installer/g14/stick-20261017T154112Z`. Analysis: `docs/power-input.md` §7.6 and §1.3.

| File | What |
|---|---|
| `hwcheck-001.json`, `hwcheck-001.txt`, `hwcheck-001-dmesg.txt.gz` | The "OpenBook power check: S0i3" boot: probe v7, four s2idle cycles (baseline, `psp`, `dummy`, `asus`) with the S0i3-entry PCI snapshot |
| `s0i3-report.md`, `s0i3-report.json` | `scripts/power/s0i3-report.py hwcheck-001.json`: no cycle reached S0i3 |
| `smu-not-met.txt` | amd_pmc's "Active time" slots after each cycle, with each u64 split into halves |
| `power-events.txt` | Lid, sleep, suspend and wake lines from the default boot's persisted logcat |
| `live-001-report.{md,json}` | The "save logs" boot, `live-report.py --expect g14` from PR #57 (redacted) |

## Results
| Check | Result |
|---|---|
| Lid close → sleep → wake | **Yes.** Closed at 15:01:12 (`reason=lid_switch`); s2idle (the first attempt stopped after 1.1 s by a pending `mmc0` wakeup, the second held 5 min 20 s); opened at 15:06:38 (`WAKE_REASON_LID`). amd_pmc: not deepest |
| S0i3 in the power check | **No**, in all four cycles. At entry, D0 holds only the root complex, host bridges, SMBus, LPC and data fabric (16–17 functions); the PSP is in D3 (the PSP hypothesis is out) |
| SMU "Active time" after each cycle | `USB4_0` (low half always `0x13250`, high half 0 or float-like) and `MPM` 14,765 / 2,805 / 2,268 / 3,296 µs; every other slot 0. Slot names unconfirmed: the table layout does not match the kernel's struct |
| Battery saver | Not seen in the logs (no event, no dialog, no `balance_power`) |
| Touchpad | Capture window missed; 170 clock errors (this image has no EventHub fix) |
| Health HAL | Charge counter 1,036,000 µAh vs `charge_now` 1,034,000; health GOOD |

`live-002` (the graphics check) is ANAL-177's; it is in the same host copy.
