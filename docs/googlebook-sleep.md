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

## Packaged release candidate (RB-20261021-01, proposed)

`scripts/googlebook/build-module-candidate.py` adds one module to `vendor_dlkm`.
It adds the file as `root:root 0644 vendor_file`, appends it to `modules.load`
and adds a `modules.dep` entry, proving that every other inode, xattr and file is
unchanged. It then re-signs AVB with the local key and updates the bootconfig
digest. Ruby's `vendor.openbook.dlkm` service loads it at boot.

USB packaging is chained and then composed against the original backup:

1. `preserve-update.py --allow-logical vendor_dlkm`: the system stage, explicitly
   reviewed and marked incomplete until the installer is re-pinned;
2. `migration-package.py pin` and `add --replace-installer-sha256`: an installer
   pinned to the new system, with a laptop record RB01 → RB01 + guard;
3. `stick-entries.py`: the sleep-diagnostics entry;
4. `compose-usb-plan.py`: checks the chain, protected bytes and installer pin, and
   emits one plan accepted by `apply-preserved-update.py`.

Results are in `evidence/2026-10-21-ruby-sleep-fix/release-candidate.json`:
- The Ruby VM boots the candidate with the module loaded.
- The synthetic laptop takes camera25 → RB01 → RB01 + guard, boots with the module
  loaded and encryption keys unchanged, and restores to RB01 byte for byte.
- The real stick plan passes the read-only physical preflight.

## S0i3 and the dGPU (ANAL-238)

Evidence: `evidence/2026-10-22-ruby-dgpu-power/`. Labels as in `STATUS.md`.

**S0i3 is never reached** (CONFIRMED). The PowerStats HAL reports `total_hw_sleep` as the SoC's S0i3 residency, and
batterystats records it after resumes. Across 7 boots (2026-10-20 to 2026-10-22, before and after the lid guard) it
is 0 ms in every record, over 130 suspends. `scripts/googlebook/sleep-history.py <bugreport.zip>` extracts this
without root, together with wake reasons and battery-only spans.

**What sleep costs today** (CONFIRMED). Overnight on battery, with the screen off and 98.6 % of the time suspended,
the laptop drew 4.5 W on average (631 minutes, 63 spans of 10 minutes, 2.9–5.9 W each).

**The dGPU is not shown to be the blocker.** The earlier wording "S0i3 still blocked by the driverless dGPU" was an
expectation carried over, not a measurement:
- On the AOSP image the same G14 missed S0i3 with the dGPU's bridge in D3cold, and again with every LPI constraint
  met (`power-input.md` §1, runs 4–7).
- On Ruby the dGPU hook (`vendor.openbook.dgpu-pm`) runs at early-init. Its HDMI-audio unbind is CONFIRMED:
  `snd_hda_intel` binds `64:00.1` at boot, and holds only the AMD functions afterwards.
- D3cold is a HYPOTHESIS until a root capture, because a user build's shell cannot read PCI power state.

The cause of the S0i3 miss is UNKNOWN. The AOSP track's leading HYPOTHESIS is MPM or the USB4 routers
(`power-input.md`).

**Why the hook's own report was never seen.** init's `stdio_to_kmsg` opens `/dev/kmsg_debug`. Ruby's user second
stage never relabels that node, so it stays `tmpfs`, and every write by a vendor domain is denied (four denials per
boot from `openbook_pc_setup`). The same applies to every `stdio_to_kmsg` vendor service on Ruby.

**Wake sources in the RB-20261021-01 lid test.** 5 of 7 dark resumes were `9 acpi:38 PCIe PME`. IRQ 38 is the PME and
hotplug vector of `00:03.1`, the dGPU's root port (`/proc/interrupts`). Whether the dGPU itself raises them is a
HYPOTHESIS.

### Root-domain report and D0 hold (vendor change, not yet in a release)

- `openbook-pc-setup` logs every line to logd as well, through vendor toybox's `log`.
- `dgpu-report` runs at `sys.boot_completed=1`, and again whenever `debug.openbook.dgpu_report` changes. It logs, as
  root:
  - each NVIDIA function's driver, `power_state`, `runtime_status`, `control` and runtime-PM times;
  - the root port and its ACPI power resources (`PG00:<resource_in_use>`);
  - `dgpu_disable` and `gpu_mux_mode` (read only);
  - `/sys/power/suspend_stats`;
  - a verdict: `d3cold`, `d3hot`, `d0-no-driver`, `d0-driver` or `absent`.

  It never reads PCI config space.
- `debug.openbook.dgpu_pm=on|auto` (`dgpu-ctl`) holds every NVIDIA function in D0, or lets it suspend again. The hold
  is volatile: a reboot returns to `dgpu-pm`'s default. It refuses while a driver drives the GPU.
- Policy: one added rule, `r_dir_file(openbook_pc_setup, sysfs_suspend_stats)`. Everything else is already allowed
  by the laptop's compiled policy (`policy-check.txt`). The `debug.` triggers are allowed too: vendor_init may read
  `debug_prop`, and shell may set it.

Use from the host:

```sh
python3 -I scripts/googlebook/dgpu-power-adb.py --serial <adb serial> report
# on battery, lid open, nobody using it; 3 x 10 min: auto (D3cold), on (D0), auto
python3 -I scripts/googlebook/dgpu-power-adb.py --serial <adb serial> battery --minutes 10 --out dgpu-battery.json
```

The battery run flags any state in which the screen went off, someone used the laptop or the charger was connected.
Such a comparison is not valid. The run always ends with `auto`.

The boot-time report is a convenience. On a busy boot, logcat's ring can drop its lines within minutes (the QEMU
check lost them about 150 s after boot), so `report` always asks for a fresh one.

### Release path on the two-slot system

The change touches only `vendor`. A release adds it with `scripts/googlebook/build-dgpu-diag-candidate.py`, on the
release's own parent candidate (RB-20261023-03 or later), through the shared exact-inventory reassembler and AVB
assembly.

- **Three vendor files change:**
  - `/bin/openbook-pc-setup` and `/etc/init/hw/init.openbook.rc`, from this repository;
  - `/etc/selinux/vendor_sepolicy.cil`, which gains three statements. They are the base's own expansion of the same
    rule for `hal_power_stats_default`, re-targeted to `openbook_pc_setup`.

  Every other vendor inode keeps its bytes and labels. The vendor keeps its own file time, through the new
  `timestamp` argument of `build-input-candidate.rebuild_erofs`; its default, 1230768000, is unchanged for
  Google's partitions.
- **It fails closed:**
  - unless each replaced file is the reviewed original;
  - if the vendor's precompiled policy matches the platform hash. RB-20261023-03's do not match (`318c33bb…` against
    `344a39b0…`), so init compiles the split policy at boot and the new rule takes effect;
  - unless both policies compile with neverallows, and only the new one grants the `suspend_stats` reads.
- **On-laptop updates (ANAL-229's adapter)** keep OpenBook's vendor and recompile the policy from it. Once a release
  carries the change, later on-laptop updates carry it forward.

`scripts/googlebook/dgpu-vm.sh` boots the VM-check variant on the real Ruby image in QEMU, and `dgpu-vm-judge.py`
compares the result with a fresh boot of the same release without the change. Results are in
`evidence/2026-10-24-ruby-dgpu-diag/`.
