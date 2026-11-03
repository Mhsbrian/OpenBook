# Power and input on the G14 (ANAL-178)

How OpenBook handles suspend, CPU power, battery, lid, keyboard and touchpad on the ASUS ROG Zephyrus G14 2025
(GA403WR, Ryzen AI 9 HX 370), and how each piece is tested. **C** = confirmed by a log or test on the laptop or in
QEMU; **HYPOTHESIS** = not yet shown. Measurements on the laptop are summarised in §7.

## State (as of 2026-10-18)

| Feature | State | Details |
|---|---|---|
| Suspend to idle (s2idle) | **Works, also under Android on the laptop** (C): the screen timeout or the lid leads to s2idle, and a key, touch or lid open wakes it; the display, audio and Wi-Fi come back. Autosuspend attempts are refused while an alarm is due within 2 s (`alarmtimer` `-EBUSY`), as on any Android device | §7.1, §7.3 |
| Deepest sleep (S0i3) | **Not reached by our kernel** (C, in every cycle measured: the hardware-check runs, Android's own s2idle and the power check). The laptop's own Linux 7.2 shows no failure (C, indirect). **The driverless PSP is ruled out**; the SMU points at MPM or the USB4 routers (HYPOTHESIS: the table's slot names are unconfirmed) | §1 |
| CPU power | `amd-pstate-epp` active, EPP `balance_performance` (C). **The power HAL's EPP hints work on the laptop** (C): screen off → `power`, app launch → `performance`, then back to `balance_performance`. Battery saver (→ `balance_power`) is not exercised yet | §7.4 |
| Battery | **The OpenBook health HAL works on the laptop** (C): Android's charge counter follows `charge_now`, and health is GOOD from the state of health (88.7 %, `charge_full` 4.063 Ah of 4.580 Ah design, as of 2026-10-17). Temperature stays 0: the ACPI battery has no temperature. `cycle_count` reads 0; charge limit 100 % | §3, §7.4 |
| Backlight | `amdgpu_bl0`, 0–399000 (C) | |
| Thermal | The thermal HAL runs on the laptop (C) with `acpitz-0` (`THRM`, 41–47 °C, follows the CPU), `acpitz-1` (`TZ01`, a constant 20 °C), `k10temp-Tctl` (CPU), `amdgpu-edge` (GPU) and `mt7925_phy0` (Wi-Fi). **No sensor measures the chassis**, so no skin sensor is declared | §3 |
| Touchpad | ELAN `04F3:3315`: InputReader classes it `TOUCH \| TOUCH_MT \| TOUCHPAD`, so Android 17's gestures-library mapper drives it (C). **"Clock changed backwards" fixed** (C): EventHub turns kernel key repeat off for touchpads (`aosp/patches/frameworks/native/0001`), and the converter keeps the last `MSC_TIMESTAMP` for frames without one (`0002`) | §2, §7.2 |
| Keyboard | hid-asus, our layout file, keyboard backlight as an input light (`LIGHT`) (C) | §2 |
| ASUS hotkeys (WMI) | Own layout, **in force on the laptop** (C, `dumpsys input`: `Asus WMI hotkeys` → `Asus_WMI_hotkeys.kl`, `Asus Keyboard` → `Vendor_0b05_Product_19b6.kl`). Which key sends what is not captured yet | §2 |
| Lid, power and sleep buttons | Input devices present (C). The PC overlay's lid and power-button config is in force **on the laptop** (C: `LID_BEHAVIOR_SLEEP`, short press 6 = lock or sleep, long press = power menu). **Lid close → sleep → s2idle → lid open → wake works on the laptop** (C). The power menu's Restart and Power off work (C) | §3, §7.3 |

## 1. S0i3

### 1.1 What is known
- **Our kernel.** Every s2idle cycle completes, but the SMU reports "Last S0i3 Status: Unknown/Fail" with the OS hint
  received (Hint Count 0→1) and 0 µs to and in S0i3. The amd_pmc idle mask at S0i3 entry is `0xffef9afd`. Taken away
  one by one without effect: the driverless dGPU (bridge in D3cold) and the unused `\_SB.PCI0.GPP0.SWUS` (every LPI
  constraint met). See `docs/nvidia.md` §1 for the dGPU side.
- **Linux 7.2.8 on the same laptop (C, indirect).** A root inventory boot (2026-10-16) has 4 s2idle cycles, up to
  15.4 h long, and **no** "Last suspend didn't reach deepest state" line. amd_pmc prints that line after every cycle
  that misses S0i3, in 6.18 and in 7.2.8 alike (`amd_pmc_validate_deepest()`). So this BIOS (GA403WR.309) can reach
  S0i3, and the difference is on our side.

### 1.2 Checked from the desk (no hardware), all the same on both kernels
1. **amd_pmc.** The 6.18 → 7.2.8 diff is a refactor for this CPU (root complex `1022:1507`): same SMU message register
   (`0x938`), scratch register, OS hint and IP table. 7.2 adds a suspend delay for some Lenovo models only. (C)
2. **LPS0.** The G14's `\_SB.PEP` (`AMDI000A`, SSDT "UPEP") answers the AMD UUID with functions 0–1 only (the
   constraint list) and the Microsoft UUID with mask `0x1F9`. Screen off sends EC command `0x97`, LPS0 entry does
   nothing, exit re-plugs the card reader. Our kernel makes these three calls, and 7.2.8's
   `drivers/acpi/x86/s2idle.c` makes the same ones. (C)
3. **IOMMU.** Same IVRS handling; `MSFT0201` (Pluton) is in IOMMU group 0 on both; IVRS virtualization info
   `0x00203043` has the DMA-protection bit, which is what AMD's `amd-s2idle` checks on this CPU family. (C)
4. **CPU idle.** Same `_CST` (C1 FFH, C2 I/O `0x414`, C3 I/O `0x415`, 350 µs). "Timekeeping suspended" in the measured cycles
   means every CPU went through cpuidle's s2idle path. The ACPI processor-idle change that broke S0i3 on a GA402RJ in
   6.19.4 (LKML, 2026-02-28) is reverted in our tree. (C)
5. **amd-pmf's suspend notice.** The APMF "heartbeat" amd-pmf sends at suspend only writes a POST code to port 0x80 in
   this BIOS (SSDT "OEMPMF", `APXG`). (C) amd-pmf as a whole is not ruled out: it also sets the SMU's power limits.
6. **Drivers.** The only PCI function Linux binds and we don't is **`65:00.2`, the AMD PSP (`ccp`)**. `66:00.0` (a
   dummy function) has no driver on either. Linux also loads amd-pmf, amdtee, asus-wmi and hid-asus, and drives the
   dGPU.
7. **USB4_0.** The SMU's "not met" time for USB4_0 is exactly 78 416 µs across separate boots, so it looks like a
   fixed figure rather than a live blocker (HYPOTHESIS).

### 1.3 Leading hypothesis
**The driverless PSP is ruled out on the laptop** (power check, 2026-10-17). The hypothesis was that in
`pci_pm_suspend_noirq()` a function with no driver stays in D0 and keeps its parent bridge (`00:08.1`, GPPA) in D0.
The PCI snapshot at S0i3 entry shows otherwise: the PSP, both xHCs, the USB4 router (`67:00.5`, `thunderbolt`), the
iGPU, NVMe and every other endpoint are already in D3. Only the root complex, host bridges, SMBus, LPC and
data-fabric functions (16–17 functions) stay in D0, as they do on any AMD laptop. Giving the PSP PCI power management
(step `psp`), the same for `1022:150d` (`dummy`), and loading the ASUS modules (`asus`) all missed S0i3 as well.

**What the SMU says.** After every cycle, amd_pmc's "Active time" table (`timecondition_notmet_lastcapture`) has two
non-zero slots: **`MPM`** (2.3–14.8 ms, varying from cycle to cycle) and **`USB4_0`**. In `USB4_0` the low half is
always `0x13250`, and the high half changes between 0 and float-looking values, so the firmware's table version 3
does not match the kernel's `u64` layout. Linux 7.2.8 uses the same struct. One USB4 router is present (`NHI0`, its
power resource ON around the cycles; `NHI1` off). **HYPOTHESIS:** the IP that keeps the SoC out of S0i3 is among MPM
and the USB4 routers, but the slot names are not trustworthy until the same table is read on the laptop's own Linux,
where S0i3 works.

Remaining candidates, in order:
1. the USB4 routers (`thunderbolt` binds both NHIs; Linux 7.2's USB4 power management is newer);
2. PTM (`CONFIG_PCIE_PTM` is off in GKI; Linux 7.2 enables PTM on root ports and turns it off at suspend, while ours
   leaves whatever the firmware set; the root ports are in D3 at entry, so the normal snapshot doesn't show their PTM
   state, but the "all steps" entry does);
3. amd-pmf (SMU power limits and policies);
4. firmware.

### 1.4 Tests built in this issue
- **`openbook_s0i3_snapshot`** (`scripts/installer/kmod/`, test-only): hooks the LPS0 prepare step, the moment the SoC
  may enter S0i3, and logs every PCI function not in D3 with the kernel's and the hardware's (PMCSR) state,
  `skip_bus_pm`, ASPM, L1 substates, PTM and the ACPI state. The same source builds for 7.2.
- **`openbook_pci_pm`** (test-only): a PCI driver with power management and nothing else, bound with
  `driver_override`. At suspend it lets the PCI core put the function into its sleep state, which a driverless
  function never gets.
- **Probe v7** (`scripts/installer/probe-init.c`): several sleep cycles in one boot. After the first, each step adds
  one change: `psp` (stub on `1022:17e0`), `dummy` (`1022:150d`), `asus` (load asus-wmi, asus-nb-wmi, hid-asus),
  `pm:VVVV:DDDD`, `mod:NAME`. It stops at the first cycle that reaches S0i3. Every cycle records s0ix residency,
  `last_hw_sleep`, the SMU's verdict and per-IP times, the idle mask at entry, cpuidle state use per CPU and the
  snapshot. JSON schema `openbook-hwcheck/6`.
- **Power check add-on** (`scripts/power/make-power-check.sh`): three menu entries added to the owner's **live**
  stick, next to the normal ones (its own kernel and initrd, the stick's bootconfig). `scripts/power/add-to-live-stick.sh`
  adds or removes it. It only writes new files and refuses anything that is not an OpenBook live stick.
- **QEMU** (`scripts/power/power-check-qemu.sh NAME vm|real`): `vm` boots the add-on with an LPS0 fixture SSDT and
  `mem_sleep_default=s2idle` and checks every step (snapshot, stub, `asus` step); `real` boots the entry as shipped.
  QEMU's RTC does not wake a guest from s2idle, so the VM test presses the ACPI power button instead (`qemu-run.py`'s
  `pause` and `monitor` steps). The applier refuses a hardware-check image, a bundle that would write outside its
  folders, and a non-`by-id` path.

### 1.5 Owner steps (until the device agent, ANAL-194/197)
**Power check on the OpenBook stick** (about 5 minutes):
1. Plug the stick into the build host and reply with `Add the power check to /dev/disk/by-id/usb-<stick>`. The agent
   then runs `scripts/power/add-to-live-stick.sh /dev/disk/by-id/usb-<stick> ~/anybook/installer/out/NAME-addon`,
   which writes only new files to the stick's OPENBOOK partition and verifies them. Or run that command yourself.
2. Boot the G14 from the stick, open the boot menu and pick **"OpenBook power check: S0i3"**. The screen stays black;
   the laptop powers off by itself after about 3 minutes.
3. Plug the stick into the build host: `scripts/installer/read-stick-logs.sh /dev/disk/by-id/usb-<stick>`. The
   result is `hwcheck-NNN.json`.

**Linux baseline.** The open step is the same SMU table on the laptop's own Linux, where S0i3 works, with AMD's
`amd-s2idle` (package `amd-debug-tools`).

### 1.6 Reading the results
| Result | Meaning | Fix |
|---|---|---|
| OpenBook reaches S0i3 at step `psp` | The driverless PSP was the blocker | A vendor module that gives the PSP PCI power management (the stub's logic, ~40 lines, no SEV code, so no GKI deny-list problem), or `ccp` via the amd-pmf decision (`docs/kernel.md`) |
| at step `dummy` | Same for `1022:150d` | The same module, bound to both |
| at step `asus` | asus-wmi/hid-asus loaded is what the firmware needs | Nothing to change in Android (the product loads them); fix the check's safety list |
| Never | Something else; compare the snapshots and idle masks | Next bisect steps (`mod:`/`pm:`), PTM, USB4 |

As of 2026-10-17 the `psp`, `dummy` and `asus` steps all miss S0i3.

## 2. Input

| Device (G14, our kernel) | Driver | Android | File |
|---|---|---|---|
| Asus Keyboard (USB `0b05:19b6`) | hid-asus | built-in keyboard, backlight light | `device/anybook/g14/input/Vendor_0b05_Product_19b6.{kl,idc}` |
| Asus WMI hotkeys (`0000:0000`) | asus-nb-wmi | key layout by device name | `Asus_WMI_hotkeys.kl` |
| ELAN touchpad (I2C `04F3:3315`) | i2c-hid-acpi + hid-multitouch | `TouchpadInputMapper` (gestures library) | `Vendor_04f3_Product_3315.idc` |
| ELAN "Mouse" collection | hid-multitouch | cursor device (silent in precision-touchpad mode) | — |
| Power Button, Sleep Button, Lid Switch | ACPI button | `POWER`/`WAKEUP`, `SLEEP`, `SW_LID` | Generic, overlay (§3) |
| Video Bus ×2 | ACPI video | brightness keys | Generic.kl |

- **WMI hotkeys.** AOSP's `Generic.kl` plus `KEY_PROG1..4` → `MACRO_1..4` (as on the keyboard) and
  `KEY_SELECTIVE_SCREENSHOT` → `SCREENSHOT`. Android 17 has no key code for touchpad toggle, airplane mode, Bluetooth,
  Wi-Fi or ALS toggle, so those stay unmapped. Fn+F5 (power profile) and the keyboard-backlight codes are handled
  inside asus-wmi and never reach Android as keys.
- **Touchpad.** Android 17 classes a multitouch device with `INPUT_PROP_POINTER` and no stylus tool as a touchpad and
  gives it the gestures library: tap to click, two-finger scroll and swipes, palm rejection. `touch.deviceType` only
  matters to the older mapper. Gesture tuning (`gestureProp.*`) waits for measurements; the save-logs capture records
  `getevent -lp`. Behaviour checks are in `docs/touchpad-behavior.md`.
- **"Clock changed backwards": cause and fix.**
  - **Cause.** The ELAN touchpad's report descriptor has eight input usages on the vendor page `0xFF01`. `hid-input`
    reads that page as `HID_UP_HPVENDOR2` and turns on `EV_REP` before `hid-multitouch` drops the usages, so the
    touchpad's input device can autorepeat keys (its `/proc/bus/input/devices` entry says `EV=10001b`; bit 20 is
    `EV_REP`). While a finger rests on the pad, the input core repeats the last key, `BTN_TOOL_FINGER`, every 40 ms
    (after the 250 ms repeat delay) in a frame of its own, without `MSC_TIMESTAMP`. Android's `HardwareStateConverter`
    resets the timestamp to 0 at every `SYN_REPORT`, so the gestures library's `TimestampFilterInterpreter` re-bases
    its clock on each repeat frame, and the next real frame lands ahead by the time since the finger went down.
    `LookaheadFilterInterpreter` then logs "Clock changed backwards. Flushing queue." at the next repeat.
  - **Fix 1:** `aosp/patches/frameworks/native/0001-OPENBOOK-EventHub-disable-kernel-key-repeat-on-touch.patch`.
    EventHub sends `EVIOCSREP {0, 0}` to touchpads as it already does to keyboards (Android repeats keys itself). The
    kernel and the touchpad stay as they are; Android's change covers every touchpad with this descriptor quirk.
  - **Fix 2:** `0002-…`. hid-multitouch sends two other kinds of frame without `MSC_TIMESTAMP`: a palm's separate
    lift-off (`mt_release_pending_palms`, when a lifting contact is marked confidence 0) and the sticky-fingers release
    (`mt_release_contacts`, after 100 ms without reports). `HardwareStateConverter` now keeps the last
    `MSC_TIMESTAMP` for frames that carry none. A device that restarts its clock reports 0 itself, so that still
    re-bases.
  - **Tests.** `scripts/power/touchpad/touchpad-qemu.sh` creates the touchpad on a `uhid` device from the laptop's own
    report descriptor (`elan-04f3-3315.rdesc.hex`), so GKI's built-in `hid-multitouch` binds as on the G14 and gives
    the same `EV=10001b`. It plays four 2 s one-finger strokes, a report every 4 ms; `TP_MODE` picks `plain`, `palm`
    or `sticky` strokes. It waits 3 s after creating the device, because a stroke that starts before Android opens
    the device still gets one kernel repeat. Host `inputflinger_tests` include
    `HardwareStateConverterTest.MscTimestampKeptForFramesWithoutOne`.
  - At most one error per device open can remain. HYPOTHESIS: EventHub sends `EVIOCSREP` before `EVIOCSCLOCKID`, so
    that one `EV_REP` notice carries the realtime clock.
- **To check on the laptop:** whether brightness and keyboard-backlight keys arrive twice (ACPI video, hid-asus and
  asus-wmi all advertise them), and what each Fn key sends.

## 3. Android power

**PC framework overlay** (`device/anybook/common/pc/overlays/framework`, vendor RRO `OpenBookPcFrameworkOverlay`).
Values from Google's Googlebook image for a real laptop (ruby, `FrameworkDesktopOverlay.apk`, read with aapt2):

| Setting | AOSP | OpenBook (= Googlebook unless noted) |
|---|---|---|
| `config_lidControlsSleep` | false | **true** |
| `config_lidKeyboardAccessibility` / `NavigationAccessibility` | 0 / 0 | 1 / 1 (usable while the lid is open) |
| `config_shortPressOnPowerBehavior` | 1 (sleep) | 6 (lock, or sleep) |
| `config_longPressOnPowerBehavior` | 5 (assistant) | 1 (power menu) |
| `config_dreamsEnabledByDefault` / `ActivatedOnDock` / `ActivatedOnSleep` | true / true / false | false / false / true |
| `config_defaultBatteryPercentageSetting` | false | true |
| battery saver: adjust brightness / factor / night mode | false / – / true | true / 0.3 / false |
| `config_screenBrightnessSettingMinimum` | 10 | 1 |
| `config_enableAutoPowerModes` (Doze) | false | **false** (Googlebook: true). AOSP says to enable it only with a cloud-messaging service; OpenBook has none |
| `config_autoPowerModeUseMotionSensor` | true | false |

- **Why the lid needed this (C, Android 17 source).** PhoneWindowManager acts on `Settings.Global.lid_behavior`, which
  SettingsProvider sets on first boot from `config_lidControlsSleep`. On real Googlebooks a desktop flag sets it to
  "none" instead (`ro.boot.hardware=android-desktop`). With `LID_BEHAVIOR_SLEEP`, closing the lid calls
  `goToSleep(…LID_SWITCH…)`; Android then lets the kernel suspend to idle. A stick whose `/data` predates the overlay
  keeps the old value until "start fresh".
- **Checked:** `aapt2` links the overlay against the G14 product's own `framework-res.apk`, and `idmap2` maps all 14
  values under the vendor policy with overlayable checks on. In a booted image `dumpsys window` shows them in force.
- **Save logs** (`scripts/installer/live-init.c` COLLECT) also records suspend statistics (`hw_sleep` is S0i3 time on
  AMD), Android's power and lid state with the lid and power-button behaviour in force, EPP per CPU policy, thermal
  sensors, the battery and its charge limit, LEDs, and `getevent -lp`. `live-init` starts a touchpad capture
  (`TOUCHPAD_EARLY`: 90 s, at most 30,000 lines) as soon as it sees `sys.boot_completed=1`, so the first use of the
  touchpad after the desktop appears is recorded; COLLECT's `TOUCHPADEV` returns it. `live-report.py --expect g14`
  has verdicts for `touchpad_gestures`, `key_layouts`, `lid_switch`, `lid_and_power_config`, `s0i3`,
  `kbd_backlight`, `epp`, `health_hal`, `lid_events`, `epp_modes`, `touchpad_clock` and `touchpad_clock_warnings`.
  `scripts/power/collect-qemu.sh` runs every section inside Android 17 in QEMU, on the image's own mksh and toybox.
- **Health HAL** (`device/anybook/common/pc/hals/health`, `android.hardware.health-service.openbook`). AOSP's example
  HAL reads the ACPI battery but reports health "unknown", temperature 0 and charge counter 0 (C), because AOSP's
  `BatteryMonitor` takes those from `health`, `temp`, `charge_counter` and `state_of_health`, which phone fuel gauges
  have and ACPI batteries don't. The OpenBook HAL is AOSP's (`libhealth_aidl_impl`) plus a subclass:
  - charge counter from `charge_now`;
  - state of health from `charge_full`/`charge_full_design`;
  - health GOOD at 80 % and above, FAIR below (the 80 % line is a choice, HYPOTHESIS), only where the kernel reports
    nothing;
  - `energy_*` batteries converted with `voltage_min_design`.

  Values the kernel does report are untouched; no battery temperature exists. Host tests use three battery fixtures
  (the G14's BAT1, an energy-based worn battery, a mouse and an empty bay to skip). A VM has no battery, but the
  service runs there (`init.svc.vendor.health-openbook=running`).
- **Thermal.** No skin sensor: the laptop exposes no chassis temperature (the `asus` hwmon has fans only). `TZ01`
  reads a constant 20 °C, and `THRM` follows the CPU (41–47 °C beside `k10temp` 41–47 °C). The thermal HAL reports
  CPU, GPU and Wi-Fi temperatures, and leaves SKIN undeclared rather than standing in a CPU sensor for it, which would
  trip the skin throttling levels on CPU load alone.

## 4. Commands
```bash
OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178 scripts/power/make-power-check.sh NAME     # add-on, ~1 min
OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178 scripts/power/power-check-qemu.sh NAME vm   # LPS0 fixture, s2idle
OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178 scripts/power/power-check-qemu.sh NAME real # the entry as shipped
OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178 scripts/power/collect-qemu.sh RUN           # save-logs facts in Android
scripts/power/add-to-live-stick.sh /dev/disk/by-id/usb-<stick> ~/anybook/installer/out/NAME-addon   # owner-confirmed
scripts/power/add-to-live-stick.sh --remove /dev/disk/by-id/usb-<stick>
# The product and a live image with these pieces, in one lane-lock hold (docs/BUILD.md has the full form):
flock ~/anybook/aosp/.lane.lock bash -c 'scripts/aosp-docker.sh -d anybook-aosp-build-anal178 /repo/scripts/aosp-build.sh \
  anybook_g14_x86_64-cp2a-userdebug droid openbook_hals_test validatekeymaps && docker wait anybook-aosp-build-anal178'
scripts/installer-image.sh --product-out <PRODUCT_OUT snapshot> --label openbook-live-<date>-<name> --menu-timeout 10
scripts/power/add-to-live-stick.sh --image ~/anybook/installer/out/<label>.img ~/anybook/installer/out/NAME-addon  # then redo .sha256/.xz
```
The installer image needs `make` for the test modules: `docker build -t openbook-installer:anal178 -f
tools/Dockerfile.installer tools`.

## 5. Owner steps on a live stick

For a live stick with the power check on its ESP (§1.5). Wi-Fi, Bluetooth and audio steps are in
`docs/g14-audio-net.md` §7.
1. In a normal **"OpenBook"** boot, once the desktop is up: close the lid for about a minute, then open it. The screen
   should come back (lock screen). The next "save logs" boot reads this boot's logs too (`lid_events`).
2. In the same boot: **unplug the charger, then Settings → Battery → Battery Saver → on**, and confirm the dialog.
   Android refuses Battery Saver while the charger is in (`PowerManagerService.setLowPowerModeInternal`). The
   `epp_modes` verdict looks for `balance_power`.
3. In the **"save logs"** boot, use the touchpad (move, two-finger scroll, tap) for about 20 s as soon as the desktop
   appears (`touchpad_clock`, `touchpad_clock_warnings`).
4. Boot **"OpenBook power check: S0i3"** once (§1.5).

## 6. Open items
- S0i3: the Linux baseline with `amd-s2idle` and the "all steps" power check (60 s cycles, every PCI function with
  its link state: ASPM, L1 substates, PTM), then a power-check step for the USB4 router (its D3cold through
  `NHI0.PWRS`) or PTM off on the root ports, then the fix in the kernel lane.
- Battery saver → `balance_power` on the laptop (§5 step 2).
- Fn keys: which key sends what, and whether brightness and keyboard-light keys arrive twice (ACPI video, hid-asus
  and asus-wmi all offer them). This needs the owner to press each key while `getevent` runs, which no save-logs step
  does yet.
- Gesture tuning (`gestureProp.*` in the IDC): wait for the owner's feel of the touchpad with the clock fix in.
- Upstream: the `hid-multitouch` side of the touchpad quirk (ignore every vendor page in a multitouch collection, not
  only `0xFF00`) and Android's `HardwareStateConverter` resetting `MSC_TIMESTAMP` at every report. Both are
  outward-facing, so they wait for the owner's OK; the patches stay in this repo.
- `service list` hangs in QEMU on the Wi-Fi/Bluetooth/audio images at the service after `IAuthSecret` (the Bluetooth
  HAL with no adapter, HYPOTHESIS; ANAL-179's area); save logs bounds it to 30 s.
- amd-pmf (owner decision, `docs/kernel.md`): a Linux run shows whether S0i3 needs it.

## 7. Measured on the G14

From live-stick sessions on 2026-10-17 and 2026-10-18 (default boots with SELinux enforcing, "save logs" boots and
the power check), read with `live-report.py --expect g14`.

### 7.1 Suspend and wake
- Android suspends to idle about 0.1 s after the screen goes off. A touch wakes it (`WAKE_REASON_WAKE_MOTION`); a key
  wakes it on IRQ 7 (`pinctrl_amd`, the GPIO controller) plus the ACPI SCI (`WAKE_REASON_WAKE_KEY`).
- After resume the display (amdgpu SMU) and the speakers (CS35L56 firmware reload) come back; Wi-Fi reconnected 24 s
  after a 20 s s2idle, and the internet check in the same boot passed.
- amd_pmc reports "Last suspend didn't reach deepest state" with 0 µs of hardware sleep after every cycle (§1).

### 7.2 Touchpad clock
- Before the fix, every frame without `MSC_TIMESTAMP` held only `EV_KEY BTN_TOOL_FINGER REPEAT`, 40 ms apart while a
  finger rested, and default boots logged 6,700–19,600 "Clock changed backwards" errors per hour. `MSC_TIMESTAMP`
  itself runs 1.6 % fast against the event clock.
- With fix 1 (§2), an hour-long default boot logged 71 per hour, sparse and right after a tap or click: the palm and
  sticky-release frames that fix 2 covers (C in QEMU; HYPOTHESIS for the laptop's remainder).

### 7.3 Lid and power button
- **Lid close → sleep works** (C): "Sleeping power group … reason=lid_switch", screen off, EPP `power`, then s2idle;
  lid open wakes it (`WAKE_REASON_LID`; IRQ 7 plus the ACPI SCI). A first suspend attempt can stop after about 1 s on a
  pending wakeup from `mmc0` (the card reader); the next one holds.
- On resume the firmware sends the lid notification again with the lid still open ("The lid device is not compliant
  to SW_LID"); the kernel drops the duplicate, so Android sees no lid event.
- `lid_events` matches Android 17's wording of the close and reports `suspended_while_closed`.
- The overlay's power-button values are in force; the power menu's Restart (`reboot,userrequested`) and Power off
  (`shutdown,userrequested`) work.

### 7.4 Battery, CPU power and thermal
- **Health HAL:** the charge counter stays within 4 % of `charge_now`, and health is GOOD. When the firmware
  recalibrated the full charge from 4.063 to 4.023 Ah between two boots, the HAL's state of health followed (88.7 % →
  87.8 %).
- **Battery draw:** about 15.5 W average in an hour of video, Bluetooth audio and Wi-Fi (42 % → 20 % in 51 minutes, so
  about 4 h for a full charge at that load); 9.3–15.6 W in save-logs boots.
- **EPP:** the power HAL sets EPP on all 24 policies: `performance` for app launches, `power` when the screen goes
  off, `balance_performance` otherwise.
- **Temperatures seen:** `acpitz-0` 41–47 °C, `k10temp` 41–47 °C, `amdgpu` 40–41 °C.

### 7.5 What each live-report verdict needs

| Verdict | What it needs |
|---|---|
| `health_hal`, `epp_modes` (except battery saver), `s0i3` (Android's own suspends), `lid_and_power_config`, `key_layouts` | nothing |
| `lid_events` | §5 step 1 in the previous default boot |
| `epp_modes.battery_saver_seen` | §5 step 2 |
| `touchpad_clock`, `touchpad_clock_warnings` | §5 step 3 |
| `hwcheck-NNN.json` (power check) | §5 step 4 |

### 7.6 Power check
All four cycles (baseline, `psp`, `dummy`, `asus`; 19 s each) miss S0i3, which rules out the driverless PSP (§1.3).

### 7.7 Not yet measured
Battery saver (`balance_power`), the Fn keys, S0i3 on the laptop's own Linux with `amd-s2idle`, and the "all steps"
power check.
