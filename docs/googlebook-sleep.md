# Ruby on the G14: lid-closed sleep that wakes itself (ANAL-235)

## What the laptop does

Measured over read-only ADB on 2026-10-21, on the RB01 system
(`evidence/2026-10-21-ruby-laptop-update/g14-sleep-check.json` and
`g14-sleep-test-2.json`):

- Closing the lid sleeps Android (`lid_switch`) and the kernel enters s2idle.
- A wake within 1–30 s (`9 acpi`, once with `7 pinctrl_amd`) is followed by a
  **Power Button `KEY_WAKEUP`**. Android treats it as a wake key and lights the
  screen inside the closed lid.
- On one resume the kernel reported the lid **open** while it stayed shut.
  Googlebook then treats the laptop as open on AC and holds
  `DesktopPowerService:ScreenOff` for 1,585,000 ms, so it never suspends again.
- The same cycle ran repeatedly on camera25, so it predates RB01.

## Why

- `drivers/acpi/button.c:acpi_button_resume()` reports `KEY_WAKEUP` from every
  ACPI power button on every resume. A VM run of the G14 kernel confirms this
  (one `KEY_WAKEUP` per resume, lid open or closed).
- The lid mode is `METHOD` (no DMI quirk), so each resume and each lid
  notification re-reads the firmware's `_LID`. The G14 DSDT's `LID0._LID` returns
  **open whenever `EC0.ECOK` is clear** (`EC0._PS3` clears it), otherwise the EC
  bit `LIDS`.
- The firmware's GPIO events (SSDT `CPMGPIO0` `_EVT`) send `Notify(PWRB, 0x80)`
  and `Notify(LID0, 0x80)` for pin 0 (power button), `Notify(PWRB, 0x80)` for the
  sensor hub on pin 0x36 when `HPDW` is set, and device-wake notifies for the
  NVIDIA GPU (pins 0x05/0x10) and both USB controllers (0x3A/0x3B). Which one
  fires on the G14 is not yet measured.

## Fix candidate: `openbook_lid_guard`

`kernel/devices/anybook/lid_guard/openbook_lid_guard.c`, a vendor module built
as `//devices/anybook:openbook_lid_guard` on the same device `kernel_build` as
our other vendor modules (all its symbols are in the vendor KMI list):

1. Drops the ACPI power button's resume `KEY_WAKEUP` while a lid reports
   closed, or if the lid was closed when the system suspended. Opening the lid
   still wakes Android through its own `SW_LID` event. A power-button press with
   the lid shut stays dark; with the lid open nothing changes.
2. After each resume, re-reads `_LID` at 1, 2.5 and 5 s. If the switch reports
   open but `_LID` now says closed, it reports closed. A real open is never held
   back.

Counters `dropped_wakeups` and `lid_corrections` are module parameters; actions
are logged with the `openbook_lid_guard:` prefix.

### VM test

`kernel/devices/anybook/lid_guard/test/run-vm-test.sh` boots the G14 bzImage in
QEMU with a busybox initramfs. It uses QEMU's ACPI power button and either a
uinput lid or `lid-transient.asl`, a test SSDT lid whose `_LID` reads open for
0.5 s after each resume. QEMU's RTC wakes S3 but not s2idle, so the VM uses S3;
both resume through the same device callbacks.

```sh
scripts/installer/inst-docker.sh env BUSYBOX=$STATIC_BUSYBOX bash \
  "$PWD/kernel/devices/anybook/lid_guard/test/run-vm-test.sh" \
  "$KERNEL_DIST/bzImage" "$MODULE_KO" "$NEW_OUT" [lid-transient.aml]
```

Results (`evidence/2026-10-21-ruby-sleep-fix/`):

| Scenario | Without module | With module | After unload |
|---|---|---|---|
| uinput lid closed / open | 1 / 1 `KEY_WAKEUP` | **0** / 1 | 1 / 1 |
| ACPI lid, false open after resume | stays open, 1 `KEY_WAKEUP` | open → **closed at 1.0 s**, 0 `KEY_WAKEUP` | stays open, 1 |

Not yet done: Ruby `vendor_dlkm` packaging, a Ruby VM boot with the module,
and the G14 trial. On the laptop a false open can still light the screen for
about a second before the correction; that is a hypothesis until measured.

## Diagnostics entry

`scripts/googlebook/stick-entries.py` adds reviewed boot entries to a Ruby USB
without changing its system (only new `loader/entries/*.conf`; parameters from
a short allowlist). `ruby-sleep-diag.conf` is the 10-minute save-logs entry plus
`pm_debug_messages acpi.debug_layer=0x4 acpi.debug_level=0x4`. These log the
wake IRQ, the active AMD GPIO pin and each firmware `Dispatching Notify on
[LID0]/[PWRB]`. A synthetic stick boots it in the VM to boot completion, with
saved logs and ACPI event debug output. The physical stick needs a fresh backup
and owner approval first.
