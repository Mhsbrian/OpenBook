# Ruby on the G14: the dGPU's power state, its battery cost and S0i3 (ANAL-238), 2026-10-22

All captures are read-only, from the G14 running RB-20261021-01 (Ruby user system, OpenBook userdebug vendor,
kernel `6.18.21-android17-5-gfbfdd65b0fd1`). The raw bugreport and save-logs sessions stay private on the build host;
only counts, state names and hashes are here.

## Files

| File | What |
|---|---|
| `g14-readonly.json` | What a user build's adb shell can and cannot see, and the vendor policy identity |
| `boot-hook-2026-10-19.json` | The dGPU hook in two G14 Ruby save-logs sessions (same kernel and hook) |
| `sleep-history.json` | `scripts/googlebook/sleep-history.py` on the bugreport's battery history: 7 boots, 2026-10-20 16:45 to 2026-10-21 21:50 EDT |
| `policy-check.txt` | Permissions in the laptop's compiled Ruby policy (`sepolicy-analyze`), for the hook and the new report |
| `tests.txt` | Fixture tests, parser tests and `host_init_verifier` for the vendor change |

## Results

**No root capture is possible on this image.** CONFIRMED: `ro.debuggable=0` refuses `adb root`, and the shell is
denied every PCI `power_state`/`power/*` file, `/sys/power/suspend_stats` and the ACPI power resources. The kernel log
in a bugreport is a 128 KiB ring that had already lost the boot and the lid test.

**The hook runs, its unbind worked, and its report was lost.** CONFIRMED:
- `vendor.openbook.dgpu-pm` starts about 0.5 s after `snd_hda_intel` binds `64:00.1` and exits 0 in 0.3 s.
- Today neither `64:00.0` nor `64:00.1` has a driver, and `snd_hda_intel` holds only the AMD functions
  `65:00.1` and `65:00.6`. So the unbind happened.
- The hook's own `power_state=… runtime_status=…` line never reached any log. init's `stdio_to_kmsg` opens
  `/dev/kmsg_debug`, and Ruby's user second stage never relabels that node from `tmpfs`, so every write by the
  vendor domain is denied (4 denials per boot). Every other `stdio_to_kmsg` vendor service loses its output the same
  way.
- The compiled policy allows everything else the hook does (sysfs reads and writes, symlinks), and the sessions
  show no other `openbook_pc_setup` denial.

HYPOTHESIS (strong, not measured): `power/control=auto` was written too, and the dGPU reaches D3cold, as it does on
the AOSP image with the same hook (`dgpu_off: D3cold suspended`, anal178c).

**S0i3 is never reached on Ruby.** CONFIRMED: the PowerStats HAL's records in batterystats show `time=0` (total
`total_hw_sleep`, ms) in every record. That covers 130 suspends in 7 boots, before and after the lid guard.

**Battery cost of sleep without S0i3: about 4.5 W.** CONFIRMED (dGPU state as configured by the hook, not
measured):
- Overnight 2026-10-20/21, on battery, screen off and 98.6 % suspended.
- 63 spans of 10 minutes, 631 minutes in all: 4,503 mW on average (2.9–5.9 W per span).
- That is about 14 h from a full 4.0 Ah charge (≈ 63 Wh). For comparison only: a laptop in S0i3 is expected to
  draw well under 1 W asleep. That figure is a general expectation, not measured on this G14.

**Wakes during the RB-20261021-01 lid test.** CONFIRMED: 5 of the 7 dark resumes were `9 acpi:38 PCIe PME`, and IRQ 38
is the PME/hotplug vector of `00:03.1`, the dGPU's root port. Earlier boots woke on `9 acpi` alone. Whether the dGPU
itself signals these wakes is a HYPOTHESIS.

**The S0i3 attribution.** The statement that S0i3 is "blocked by the driverless dGPU" is not supported:
- On Ruby the dGPU's state is not yet measured, and its hook does run.
- On the AOSP image, the same G14 missed S0i3 with the dGPU's bridge already in D3cold, and again with every LPI
  constraint met (`docs/power-input.md`, runs 4–7).
- The cause is UNKNOWN. The AOSP track's leading HYPOTHESIS is MPM or the USB4 routers.

## Not measured, and why

- **The dGPU's real D-state on Ruby, and D0 vs D3cold on battery.** Both need a write or read as root. The vendor
  change in this PR adds both, as root-domain services that shell can trigger over adb. It is image-affecting and
  needs a Ruby release before it can run on the laptop.
- **On-battery idle with the screen on.** The laptop was on AC during this capture.

## Commands

```sh
python3 -I scripts/googlebook/sleep-history.py <bugreport.zip> --out sleep-history.json
# after the vendor change is installed:
python3 -I scripts/googlebook/dgpu-power-adb.py --serial <adb serial> report
python3 -I scripts/googlebook/dgpu-power-adb.py --serial <adb serial> battery --minutes 10   # on battery, idle
```
