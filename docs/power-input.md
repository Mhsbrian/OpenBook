# Power and input on the G14 (ANAL-178)

How OpenBook handles suspend, CPU power, battery, lid, keyboard and touchpad on the ASUS ROG Zephyrus G14 2025 (GA403WR, Ryzen AI 9 HX 370), and how each piece is tested. **C** = confirmed by a log or test cited here; **HYPOTHESIS** = not yet shown. Evidence for this document: `evidence/2026-10-17-power-input/`.

## State (2026-10-17)

| Feature | State | Source |
|---|---|---|
| Suspend to idle (s2idle) | Works: cycles complete, the panel and Wi-Fi come back (C). **Also under Android on the laptop** (`anal178c`): the screen timeout led to s2idle, a key woke it after 22 s, and the display, audio and Wi-Fi came back (C). Autosuspend attempts are refused while an alarm is due within 2 s (`alarmtimer` `-EBUSY`), as on any Android device | runs 3–7, `evidence/2026-10-16-g14-hwcheck/`, §7 |
| Deepest sleep (S0i3) | **Not reached by our kernel** (C, runs 2–7, and Android's own s2idle on `anal178c`: "Last suspend didn't reach deepest state"). The laptop's own Linux 7.2 shows no failure in 4 cycles (C, indirect, §1.1). Root cause open; tests ready (§1.4), not run on the laptop yet | §1, §7 |
| CPU power | `amd-pstate-epp` active, EPP `balance_performance` (C). **The power HAL's EPP hints work on the laptop** (C): screen off → `power`, app launch → `performance`, then back to `balance_performance`. Battery saver (→ `balance_power`) not exercised yet | §7 |
| Battery | **The OpenBook health HAL works on the laptop** (C, both sessions): Android's charge counter follows `charge_now` (1,437,000 µAh against 1,430,000), and health is GOOD from a state of health of 88.7 % (`charge_full` 4.063 Ah of 4.580 Ah design). Temperature stays 0: the ACPI battery has no temperature. `cycle_count` reads 0; charge limit 100 % | §3, §7 |
| Backlight | `amdgpu_bl0`, 0–399000 (C) | live-001 |
| Thermal | The thermal HAL runs on the laptop (C) with `acpitz-0` (`THRM`, 41–47 °C, follows the CPU), `acpitz-1` (`TZ01`, a constant 20 °C), `k10temp-Tctl` (CPU), `amdgpu-edge` (GPU) and `mt7925_phy0` (Wi-Fi). **No sensor measures the chassis**, so no skin sensor is declared (§7) | §7 |
| Touchpad | ELAN `04F3:3315`: InputReader classes it `TOUCH \| TOUCH_MT \| TOUCHPAD`, so Android 17's gestures-library mapper drives it (C). **"Clock changed backwards" every 40 ms of finger contact: cause found** (C): the kernel autorepeats `BTN_TOOL_FINGER` on the touchpad. **Fix:** EventHub turns kernel key repeat off for touchpads (`aosp/patches/frameworks/native`); reproduced and fixed in QEMU with the laptop's own HID descriptor (§2, §7) | §2, §7 |
| Keyboard | hid-asus, our layout file, keyboard backlight as an input light (`LIGHT`) (C) | live-001 |
| ASUS hotkeys (WMI) | Own layout, **in force on the laptop** (C, `dumpsys input`: `Asus WMI hotkeys` → `Asus_WMI_hotkeys.kl`, `Asus Keyboard` → `Vendor_0b05_Product_19b6.kl`). Which key sends what is not captured yet | §2, §7 |
| Lid, power and sleep buttons | Input devices present (C). The PC overlay's lid and power-button config is in force **on the laptop** (C, both sessions: `LID_BEHAVIOR_SLEEP`, short press 6 = lock or sleep, long press = power menu). **The lid was not closed in either session**, so lid → sleep → wake is still untested; the power menu's Restart and Power off worked (C) | §7 |

## 1. S0i3

### 1.1 What is known
- **Our kernel (runs 2–7, ANAL-189).** Every s2idle cycle completes, but the SMU reports "Last S0i3 Status: Unknown/Fail" with the OS hint received (Hint Count 0→1) and 0 µs to and in S0i3. The amd_pmc idle mask at S0i3 entry is `0xffef9afd` in runs 5, 6 and 7. Taken away one by one without effect: the driverless dGPU (bridge in D3cold, runs 4–7) and the unused `\_SB.PCI0.GPP0.SWUS` (run 7: every LPI constraint met).
- **Linux 7.2.8 on the same laptop (C, indirect).** The owner's root inventory boot (2026-10-16) has 4 s2idle cycles, up to 15.4 h long, and **no** "Last suspend didn't reach deepest state" line (`s0i3-analysis/linux72-suspend-cycles.txt`). amd_pmc prints that line after every cycle that misses S0i3, in 6.18 and in 7.2.8 alike (`amd_pmc_validate_deepest()`). So this BIOS (GA403WR.309) can reach S0i3, and the difference is on our side. A direct Linux measurement is step A in §1.5.

### 1.2 Checked from the desk (no hardware), all the same on both kernels
1. **amd_pmc.** The 6.18 → 7.2.8 diff (`amd_pmc-s2idle-6.18-vs-7.2.8.diff.gz`) is a refactor for this CPU (root complex `1022:1507`): same SMU message register (`0x938`), scratch register, OS hint and IP table. 7.2 adds a suspend delay for some Lenovo models only. (C)
2. **LPS0.** The G14's `\_SB.PEP` (`AMDI000A`, SSDT "UPEP") answers the AMD UUID with functions 0–1 only (the constraint list) and the Microsoft UUID with mask `0x1F9`. Screen off sends EC command `0x97`, LPS0 entry does nothing, exit re-plugs the card reader. Our kernel makes these three calls (run 5 log), and 7.2.8's `drivers/acpi/x86/s2idle.c` makes the same ones. (C)
3. **IOMMU.** Same IVRS handling; `MSFT0201` (Pluton) is in IOMMU group 0 on both; IVRS virtualization info `0x00203043` has the DMA-protection bit, which is what AMD's `amd-s2idle` checks on this CPU family. (C)
4. **CPU idle.** Same `_CST` (C1 FFH, C2 I/O `0x414`, C3 I/O `0x415`, 350 µs). "Timekeeping suspended for 18.6 s" in runs 5–7 means every CPU went through cpuidle's s2idle path. The ACPI processor-idle change that broke S0i3 on a GA402RJ in 6.19.4 (LKML, 2026-02-28) is reverted in our tree. (C)
5. **amd-pmf's suspend notice.** The APMF "heartbeat" amd-pmf sends at suspend only writes a POST code to port 0x80 in this BIOS (SSDT "OEMPMF", `APXG`). (C) amd-pmf as a whole is not ruled out: it also sets the SMU's power limits.
6. **Drivers.** The only PCI function Linux binds and we don't is **`65:00.2`, the AMD PSP (`ccp`)**. `66:00.0` (a dummy function) has no driver on either. Linux also loads amd-pmf, amdtee, asus-wmi and hid-asus, and drives the dGPU (NVIDIA's driver; vfio-pci after the resume in that log).
7. **USB4_0.** The SMU's "not met" time for USB4_0 is exactly 78 416 µs in runs 5, 6 and 7, across separate boots, so it looks like a fixed figure rather than a live blocker (HYPOTHESIS).

### 1.3 Leading hypothesis
In `pci_pm_suspend_noirq()` (6.18 and 7.2 alike), a function with no driver is left in D0, and the PCI core marks **its parent bridge** `skip_bus_pm` so the bridge stays in D0 too. With no `ccp`, the PSP keeps `00:08.1` (`\_SB.PCI0.GPPA`, the internal bridge of the iGPU, display audio, PSP, xHCI 1, ACP and HDA) in D0 through every suspend. Under Linux, `ccp` has PM callbacks, so the PCI core puts the PSP into D3hot and GPPA can follow. **HYPOTHESIS:** the firmware does not list GPPA's D3 as an LPI constraint (`P1D3` = `0x55`), so this is plausible, not shown.

Other candidates, in order: amd-pmf (SMU power limits and policies), asus-wmi's `INIT` call, PTM (`CONFIG_PCIE_PTM` is off in GKI; Linux 7.2 enables PTM on root ports and turns it off at suspend, while ours leaves whatever the firmware set), then firmware.

### 1.4 Tests built in this issue
- **`openbook_s0i3_snapshot`** (`scripts/installer/kmod/`, test-only): hooks the LPS0 prepare step, the moment the SoC may enter S0i3, and logs every PCI function not in D3 with the kernel's and the hardware's (PMCSR) state, `skip_bus_pm`, ASPM, L1 substates, PTM and the ACPI state. The same source builds for 7.2.
- **`openbook_pci_pm`** (test-only): a PCI driver with power management and nothing else, bound with `driver_override`. At suspend it lets the PCI core put the function into its sleep state, which a driverless function never gets.
- **Probe v7** (`scripts/installer/probe-init.c`): several sleep cycles in one boot. After the first, each step adds one change: `psp` (stub on `1022:17e0`), `dummy` (`1022:150d`), `asus` (load asus-wmi, asus-nb-wmi, hid-asus), `pm:VVVV:DDDD`, `mod:NAME`. It stops at the first cycle that reaches S0i3. Every cycle records s0ix residency, `last_hw_sleep`, the SMU's verdict and per-IP times, the idle mask at entry, cpuidle state use per CPU and the snapshot. JSON schema `openbook-hwcheck/6`.
- **Power check add-on** (`scripts/power/make-power-check.sh`): three menu entries added to the owner's **live** stick, next to the normal ones (its own kernel and initrd, the stick's bootconfig). `scripts/power/add-to-live-stick.sh` adds or removes it. It only writes new files and refuses anything that is not an OpenBook live stick.
- **Linux comparison** (`scripts/power/linux-s2idle.py`): on the laptop's own Linux, as root. Baseline cycles, then one cycle with amd-pmf unloaded, then one with `ccp` unloaded as well (modules always reloaded), with the snapshot module built for that kernel when its headers are installed. Optional `--amd-s2idle` adds AMD's own tool. Output is redacted, with JSON.
- **`scripts/power/s0i3-report.py`**: one table from all of the above, with idle-mask bits and PCI functions awake on one side only.

**Tested in QEMU** (`evidence/2026-10-17-power-input/qemu/`, on a copy of `openbook-live-20261017-desktop2.img` with the add-on applied by `add-to-live-stick.sh --image`):
- *VM entry* (an LPS0 fixture SSDT and `mem_sleep_default=s2idle`): 14/14 steps. The snapshot registered and logged at each "S0i3 attempt" and on exit. The stub took the virtio-rng from `virtio-pci` and put it into D3hot at suspend ("suspend: D3hot (0)", "resume: D0"). The `asus` step loaded asus-wmi and hid-asus (asus-nb-wmi: no ASUS WMI in a VM). Three cycles ran.
- *The add-on's own entry, unchanged*: 10/10, four cycles (S3 in QEMU), report written, powered off.
- QEMU's RTC does not wake a guest from s2idle; the VM test presses the ACPI power button instead (`qemu-run.py` gains `pause` and `monitor` steps).
- The applier refuses a hardware-check image, a bundle that would write outside its folders, and a non-`by-id` path.

### 1.5 Owner steps (until the device agent, ANAL-194/197)
**A. Linux comparison** (on the laptop's own Linux, about 5 minutes, 4 suspends of 20 s; save your work first):
```bash
cd OpenBook && git fetch origin && git checkout <this PR's branch>      # or main once merged
sudo pacman -S --needed make gcc "$(pacman -Qoq /usr/lib/modules/$(uname -r)/vmlinuz)-headers"   # optional: PCI snapshot
sudo pacman -S --needed amd-debug-tools                                                         # optional: --amd-s2idle
sudo python3 scripts/power/linux-s2idle.py --amd-s2idle
```
Attach the `openbook-linux-s2idle-<time>.tar.gz` it writes to the issue. The snapshot module taints the kernel until the next reboot; `--no-snapshot` skips it.

**B. Power check on the OpenBook stick** (about 5 minutes):
1. The `anal178b` image (§5) already carries it. On a stick written from another live image, plug the stick into the build host and reply with `Add the power check to /dev/disk/by-id/usb-<stick>`. The agent then runs `scripts/power/add-to-live-stick.sh /dev/disk/by-id/usb-<stick> ~/anybook/installer/out/openbook-powercheck-anal178-a-addon`, which writes only new files to the stick's OPENBOOK partition and verifies them. Or run that command yourself.
2. Boot the G14 from the stick, open the boot menu and pick **"OpenBook power check: S0i3"**. The screen stays black; the laptop powers off by itself after about 3 minutes.
3. Plug the stick into the build host: `scripts/installer/read-stick-logs.sh /dev/disk/by-id/usb-<stick>`, then `scripts/power/s0i3-report.py <dest>/hwcheck-NNN.json <linux>/summary.json`.

### 1.6 Reading the results
| Result | Meaning | Fix |
|---|---|---|
| OpenBook reaches S0i3 at step `psp` | The driverless PSP was the blocker | A vendor module that gives the PSP PCI power management (the stub's logic, ~40 lines, no SEV code, so no GKI deny-list problem), or `ccp` via the amd-pmf decision (`docs/kernel.md`) |
| at step `dummy` | Same for `1022:150d` | The same module, bound to both |
| at step `asus` | asus-wmi/hid-asus loaded is what the firmware needs | Nothing to change in Android (the product loads them); fix the check's safety list |
| Never, and Linux misses S0i3 only without `ccp` | The PSP needs its real driver, not just D3 | `ccp` for OpenBook: the amd-pmf/SEV decision |
| Never, and Linux misses it only without amd-pmf | amd-pmf's SMU setup matters | Unblock amd-pmf (same decision) |
| Never, Linux reaches it in every phase | Something else; compare the snapshots and idle masks in the report | Next bisect steps (`mod:`/`pm:`), PTM, USB4 |

## 2. Input

| Device (G14, our kernel) | Driver | Android | File |
|---|---|---|---|
| Asus Keyboard (USB `0b05:19b6`) | hid-asus | built-in keyboard, backlight light | `device/anybook/g14/input/Vendor_0b05_Product_19b6.{kl,idc}` |
| Asus WMI hotkeys (`0000:0000`) | asus-nb-wmi | key layout by device name | **new** `Asus_WMI_hotkeys.kl` |
| ELAN touchpad (I2C `04F3:3315`) | i2c-hid-acpi + hid-multitouch | `TouchpadInputMapper` (gestures library) | `Vendor_04f3_Product_3315.idc` |
| ELAN "Mouse" collection | hid-multitouch | cursor device (silent in precision-touchpad mode) | — |
| Power Button, Sleep Button, Lid Switch | ACPI button | `POWER`/`WAKEUP`, `SLEEP`, `SW_LID` | Generic, overlay (§3) |
| Video Bus ×2 | ACPI video | brightness keys | Generic.kl |

- **WMI hotkeys.** AOSP's `Generic.kl` plus `KEY_PROG1..4` → `MACRO_1..4` (as on the keyboard) and `KEY_SELECTIVE_SCREENSHOT` → `SCREENSHOT`. Android 17 has no key code for touchpad toggle, airplane mode, Bluetooth, Wi-Fi or ALS toggle, so those stay unmapped. Fn+F5 (power profile) and the keyboard-backlight codes are handled inside asus-wmi and never reach Android as keys.
- **Touchpad.** Android 17 classes a multitouch device with `INPUT_PROP_POINTER` and no stylus tool as a touchpad and gives it the gestures library: tap to click, two-finger scroll and swipes, palm rejection. `touch.deviceType` only matters to the older mapper. Gesture tuning (`gestureProp.*`) waits for `getevent -lp` from the laptop, which the save-logs capture now records.
- **"Clock changed backwards": found and fixed** (§7.2). The ELAN touchpad's report descriptor has eight input usages on the vendor page `0xFF01`. `hid-input` reads that page as `HID_UP_HPVENDOR2` and turns on `EV_REP` before `hid-multitouch` drops the usages, so the touchpad's input device can autorepeat keys (its `/proc/bus/input/devices` entry says `EV=10001b`; bit 20 is `EV_REP`). While a finger rests on the pad, the input core then repeats the last key, `BTN_TOOL_FINGER`, every 40 ms in a frame of its own, without `MSC_TIMESTAMP`. Android's `HardwareStateConverter` resets the timestamp to 0 at every `SYN_REPORT`, so the gestures library's `TimestampFilterInterpreter` re-bases its clock on each repeat frame, and the next real frame lands ahead by the time since the finger went down. `LookaheadFilterInterpreter` then logs "Clock changed backwards. Flushing queue." at the next repeat. On the laptop every frame without `MSC_TIMESTAMP` is such a repeat (105 of 2,130 and 32 of 1,662 frames), and the errors come every 40 ms while a finger is down (180 and 162 per save-logs boot). Android already turns kernel key repeat off on keyboards, because it repeats keys itself. **Fix:** `aosp/patches/frameworks/native/0001-…`: EventHub does the same for touchpads. The bug was reproduced and the fix checked in QEMU, with the laptop's own descriptor on a `uhid` device (`scripts/power/touchpad/`).
- **To check on the laptop:** whether brightness and keyboard-backlight keys arrive twice (ACPI video, hid-asus and asus-wmi all advertise them), and what each Fn key sends.

## 3. Android power

**PC framework overlay** (`device/anybook/common/pc/overlays/framework`, vendor RRO `OpenBookPcFrameworkOverlay`). Values from Google's Googlebook image for a real laptop (ruby, `FrameworkDesktopOverlay.apk`; `evidence/2026-10-17-power-input/android/googlebook-ruby-laptop-config.txt`):

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

- **Why the lid needed this (C, Android 17 source).** PhoneWindowManager acts on `Settings.Global.lid_behavior`, which SettingsProvider sets on first boot from `config_lidControlsSleep`. On real Googlebooks a desktop flag sets it to "none" instead (`ro.boot.hardware=android-desktop`). With `LID_BEHAVIOR_SLEEP`, closing the lid calls `goToSleep(…LID_SWITCH…)`; Android then lets the kernel suspend to idle. A stick whose `/data` predates the overlay keeps the old value until "start fresh".
- **Checked:** `aapt2` links the overlay against the G14 product's own `framework-res.apk`, and `idmap2` maps all 14 values under the vendor policy with overlayable checks on (`android/overlay-check.txt`). **Built and booted in QEMU** (`anal178b`, §5): the RRO carries these 14 values plus ANAL-179's jack setting, and `dumpsys window` shows them in force.
- **Save logs** (`scripts/installer/live-init.c` COLLECT) now also records suspend statistics (`hw_sleep` is S0i3 time on AMD), Android's power and lid state with the lid and power-button behaviour in force, EPP per CPU policy, thermal sensors, the battery and its charge limit, LEDs, and `getevent -lp`. `live-report.py --expect g14` gains verdicts: `touchpad_gestures`, `key_layouts`, `lid_switch`, `lid_and_power_config`, `s0i3`, `kbd_backlight`, `epp`; after the first laptop sessions also `health_hal`, `lid_events`, `epp_modes` and `touchpad_clock_warnings` (§7.5). Run inside Android 17 in QEMU with `scripts/power/collect-qemu.sh`: every section runs on the image's own mksh and toybox (`qemu/collect-*`). The VM also suspended itself after its screen timeout, one attempt failing with EBUSY.
- **Health HAL** (`device/anybook/common/pc/hals/health`, `android.hardware.health-service.openbook`). AOSP's example HAL reads the ACPI battery but reports health "unknown", temperature 0 and charge counter 0 (C), because AOSP's `BatteryMonitor` takes those from `health`, `temp`, `charge_counter` and `state_of_health`, which phone fuel gauges have and ACPI batteries don't. The OpenBook HAL is AOSP's (`libhealth_aidl_impl`) plus a subclass: charge counter from `charge_now`, state of health from `charge_full`/`charge_full_design` (88 % on this battery, run 2), and health GOOD at 80 % and above, FAIR below (the 80 % line is a choice, HYPOTHESIS), only where the kernel reports nothing. `energy_*` batteries are converted with `voltage_min_design`. Values the kernel does report are untouched; no battery temperature exists. Host tests: 18/18 with three battery fixtures (the G14's BAT1, an energy-based worn battery, a mouse and an empty bay to skip). In QEMU the service runs (`init.svc.vendor.health-openbook=running`); a VM has no battery. **On the laptop** (both sessions, §7): `dumpsys battery` shows the charge counter at `charge_now` and health 2 (GOOD), from a state of health of 88.7 %; the live report's `health_hal` verdict checks both.
- **Thermal.** No skin sensor (§7.4): the laptop exposes no chassis temperature. `TZ01` reads a constant 20 °C, and `THRM` follows the CPU (41–47 °C beside `k10temp` 41–47 °C). The thermal HAL reports CPU, GPU and Wi-Fi temperatures, and leaves SKIN undeclared rather than standing in a CPU sensor for it, which would trip the skin throttling levels on CPU load alone.

## 4. Commands
```bash
OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178 scripts/power/make-power-check.sh NAME     # add-on, ~1 min
OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178 scripts/power/power-check-qemu.sh NAME vm   # LPS0 fixture, s2idle
OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178 scripts/power/power-check-qemu.sh NAME real # the entry as shipped
OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178 scripts/power/collect-qemu.sh RUN           # save-logs facts in Android
scripts/power/add-to-live-stick.sh /dev/disk/by-id/usb-<stick> ~/anybook/installer/out/NAME-addon   # owner-confirmed
scripts/power/add-to-live-stick.sh --remove /dev/disk/by-id/usb-<stick>
sudo python3 scripts/power/linux-s2idle.py [--amd-s2idle] [--dry-run]                            # on the laptop's Linux
scripts/power/s0i3-report.py hwcheck-NNN.json summary.json [--json out.json]
# The product and a live image with these pieces, in one lane-lock hold (docs/BUILD.md has the full form):
flock ~/anybook/aosp/.lane.lock bash -c 'scripts/aosp-docker.sh -d anybook-aosp-build-anal178 /repo/scripts/aosp-build.sh \
  anybook_g14_x86_64-cp2a-userdebug droid openbook_hals_test validatekeymaps && docker wait anybook-aosp-build-anal178'
scripts/installer-image.sh --product-out <PRODUCT_OUT snapshot> --label openbook-live-<date>-<name> --menu-timeout 10
scripts/power/add-to-live-stick.sh --image ~/anybook/installer/out/<label>.img ~/anybook/installer/out/NAME-addon  # then redo .sha256/.xz
```
The installer image needs `make` for the test modules: `docker build -t openbook-installer:anal178 -f tools/Dockerfile.installer tools` (the `latest` tag on the build host predates it).

## 5. The `anal178b` stick (2026-10-17)
> **Superseded image (2026-10-17):** write **`openbook-live-20261017-anal178c`** instead (`evidence/2026-10-17-power-input/anal178c/`). It contains `combined` (this image plus ANAL-200's arm64 bridge), is built from `main` at `ea3c25e`, and carries ANAL-177's graphics check next to the power check. The steps below are unchanged; use that file name in the `write-stick.sh` command, and boot "OpenBook graphics check" after them (`docs/STATUS.md`, "Next G14 stick").

`openbook-live-20261017-anal178b` is one stick for all the open G14 tests:
- **Contents.** Built from `anal-178/stick-integration`: ANAL-179's `stick-integration` (Wi-Fi, Bluetooth, audio and their save-logs tests, with ANAL-176's desktop4 fixes and `main`), merged with this issue's branch (PR #41: overlay, layouts, save-logs facts), plus the health HAL. The power check add-on is on its ESP.
- **Image:** sha256 `be09ebb7…` (xz `96600a6e…`), with the add-on; the build record (`.build.json`) says so.
- **Tests (QEMU):**
  - the live image matrix (`scripts/installer/live-qemu.sh`, ANAL-190's six cases): **39/39**. In its save-logs case the helper recorded the new sections through `END`, and the health HAL ran ("No battery devices found" in a VM);
  - the save-logs facts inside Android (`collect-qemu.sh`): COLLECT completes, the lid and power config is in force, `vendor.health-openbook` runs;
  - the power check entry, unchanged: 10/10.
  - Evidence: `evidence/2026-10-17-power-input/anal178b/`.
- **Owner steps.** Write it instead of `audionet3` (it contains it). ANAL-179's steps (`docs/g14-audio-net.md` §7) apply unchanged; for this issue:
  1. In a normal **"OpenBook"** boot, once the desktop is up: close the lid for about a minute, then open it. The screen should come back (lock screen). Note it if it doesn't; the next "save logs" boot collects this boot's logs too.
  2. In the **"save logs"** boot, use the touchpad (move, two-finger scroll, tap) for about 20 s as soon as the desktop appears.
  3. Boot **"OpenBook power check: S0i3"** once.
  4. Optionally, step A of §1.5 on the laptop's Linux.

## 6. Open items
- S0i3: the power-check boot or the Linux run (§7.5) on ANAL-192's stick, then the fix in the kernel lane (§1.6). Android's own suspends on the laptop miss S0i3 too (§7.3).
- On ANAL-192's stick (§7.5): lid close → sleep → wake, battery saver → `balance_power`, and the touchpad without repeat frames and clock errors (the EventHub fix).
- Fn keys: which key sends what, and whether brightness and keyboard-light keys arrive twice (ACPI video, hid-asus and asus-wmi all offer them). This needs the owner to press each key while `getevent` runs, which no save-logs step does yet.
- Gesture tuning (`gestureProp.*` in the IDC): wait for the owner's feel of the touchpad with the clock fix in.
- Upstream: the `hid-multitouch` side of the touchpad quirk (ignore every vendor page in a multitouch collection, not only `0xFF00`) and Android's `HardwareStateConverter` resetting `MSC_TIMESTAMP` at every report. Both are outward-facing, so they wait for the owner's OK; the patch stays in this repo.
- `service list` hangs in QEMU on the Wi-Fi/Bluetooth/audio images at the service after `IAuthSecret` (the Bluetooth HAL with no adapter, HYPOTHESIS; ANAL-179's area); save logs now bounds it to 30 s.
- amd-pmf (owner decision, `docs/kernel.md`): the §1.5 Linux run shows whether S0i3 needs it.

## 7. The owner's G14 sessions (2026-10-17)

### 7.1 What was run
| Session (host copy, read-only) | Stick image | Boots | Not booted |
|---|---|---|---|
| `g14/stick-20261017T122351Z` | `openbook-live-20261017-anal178c` | 1: default entry (enforcing), desktop at 28 s, Wi-Fi connected; 2: "save logs" | power check, graphics check |
| `g14/stick-20261017T135624Z` | `openbook-live-20261017-anal176s` (`anal178c` plus ANAL-176's PR #52) | 1: default entry; 2: "save logs" | power check, graphics check |

ANAL-176 copied both sessions read-only; this issue read the copies only. Everything below comes from `live-001/` (collect, dmesg, logcat) and the earlier boot's logcat in `prior-boots.tar.gz`. It is reported with `live-report.py --expect g14` and redacted (`evidence/2026-10-17-power-input/g14-sessions/`).

### 7.2 Touchpad: "Clock changed backwards"
- **Laptop.** In the save-logs captures (`TOUCHPADEV`, 20 s of `getevent -lt`), every frame without `MSC_TIMESTAMP` holds only `EV_KEY BTN_TOOL_FINGER REPEAT`. That is 105 of 2,130 frames on `anal178c` and 32 of 1,662 on `anal176s`, 40 ms apart while a finger rests, starting 250 ms after it lands (the input core's repeat delay). The gestures library logged "Clock changed backwards" 180 and 162 times in those boots, 40 ms apart. Otherwise `MSC_TIMESTAMP` behaves: it runs 1.6 % fast against the event clock and goes backwards once (after a pause).
- **Cause** (§2): `EV_REP` on the touchpad's input device (`EV=10001b`), from the vendor page `0xFF01` in its HID descriptor (`HID_UP_HPVENDOR2` in `hid-input.c`), and Android's converter turning every repeat frame into a clock reset.
- **Fix:** `aosp/patches/frameworks/native/0001-OPENBOOK-EventHub-disable-kernel-key-repeat-on-touch.patch`. EventHub sends `EVIOCSREP {0, 0}` to touchpads as it does to keyboards. The kernel and the touchpad stay as they are. The kernel side (`hid-multitouch` ignoring all vendor pages, not only `0xFF00`) would be an upstream patch to GKI's built-in driver; Android's change covers every touchpad with this descriptor quirk.
- **QEMU** (`scripts/power/touchpad/touchpad-qemu.sh`). A static `uhid` program creates the touchpad from the laptop's own report descriptor (`elan-04f3-3315.rdesc.hex`), so GKI's built-in `hid-multitouch` binds as on the G14 and gives the same `EV=10001b`. It then plays four 2 s one-finger strokes: a report every 4 ms, Scan Time +41 per report as on the laptop.

  | Image | `EV_REP` on the touchpad | Repeat frames | "Clock changed backwards" | `touchpad_clock` |
  |---|---|---|---|---|
  | `anal178c` (before the fix) | yes | 173 | 172 | NO (2,008 of 2,181 frames with MSC) |
  | `anal178-eventhub-test` (this branch: `main` plus the patch; test image only) | yes, but its repeat delay and period are now 0 | **0** | **0** | **yes** (2,008 of 2,008) |

  `frameworks/native` differs between the two images only by the patch. The emulator waits 3 s after creating the device before the first stroke. On an earlier run it started at once, before Android had opened the new touchpad, and the one repeat the kernel had already scheduled still fired (`evidence/2026-10-17-power-input/g14-sessions/qemu/`).

### 7.3 Suspend, lid and power button
- **`anal178c`, default boot.** After 11 s on the desktop the screen went off: the 10 s activity timeout that ANAL-176's PR #52 removes. Android suspended to idle 0.1 s after the screen went off, and the owner's touch woke it 0.24 s later (`WAKE_REASON_WAKE_MOTION`).
- **`anal178c`, save-logs boot.** The screen timed out again at 29 s. Three autosuspend attempts were refused by `alarmtimer` (`-EBUSY`: an alarm due within 2 s; Android retries), then one s2idle of 20 s (kernel 40.8 → 60.9 s). It woke on IRQ 7 (`pinctrl_amd`, the GPIO controller) plus the ACPI SCI, which Android reports as `WAKE_REASON_WAKE_KEY`. The display (amdgpu SMU) and the speakers (CS35L56 firmware reload) came back. Wi-Fi reconnected 24 s after the resume, and the internet check in the same boot passed. amd_pmc: "Last suspend didn't reach deepest state" with 0 µs of hardware sleep, the same S0i3 miss as the hardware-check runs (§1).
- **Lid.** Not closed in either session: no `lid_switch` sleep and no `WAKE_REASON_LID` wake in any of the four boots. On resume the firmware sends the lid notification again with the lid still open ("The lid device is not compliant to SW_LID"); the kernel drops the duplicate, so Android sees no lid event.
- **Power button and menu.** The overlay's values are in force in all four boots. The power menu's Restart (`anal178c`: next boot `reboot,userrequested`) and Power off (`anal176s`: `shutdown,userrequested`) worked. The logs don't show whether the menu came from the key or from Quick Settings.

### 7.4 Battery, CPU power and thermal
- **Battery and health HAL.** `vendor.health-openbook` runs. Android's charge counter is 1,437,000 µAh against `charge_now` 1,430,000 (`anal178c`) and 1,230,000 against 1,206,000 (`anal176s`, read seconds apart), and health is 2 (GOOD) from 88.7 % state of health (4.063 of 4.580 Ah). The kernel gives no counter and no health: the HAL fills both. The battery draws 9.3 W and 15.6 W in the two save-logs boots (`current_now` × `voltage_now`), with the panel at 83 % of its backlight range. `cycle_count` reads 0 (firmware), and the charge limit is 100 % (`charge_control_end_threshold`).
- **EPP.** The power HAL (ANAL-199) sets EPP on all 24 policies as designed: `performance` for app launches (21 and 28 times), `power` when the screen went off (3 times, `anal178c`), and `balance_performance` otherwise. Battery saver was not turned on: `anal176s` shows its confirmation dialog at 13:48:07 but no `balance_power`.
- **Thermal.** The thermal HAL lists `acpitz-0` (41–47 °C, tracking `k10temp-Tctl`), `acpitz-1` (20 °C, constant), `k10temp-Tctl`, `amdgpu-edge` and `mt7925_phy0`. There is no chassis sensor (the `asus` hwmon has fans only), so no skin sensor is declared (§3).

### 7.5 This issue's checks on ANAL-192's stick
ANAL-192 builds the single integrated stick from `main` once PR #52 is merged. For this issue it needs the following.

| Owner step | What it needs on the stick | Read by (`live-report.py --expect g14`, `s0i3-report.py`) |
|---|---|---|
| Boot **"OpenBook power check: S0i3"** once (about 3 min, powers off) | The power check add-on: `scripts/power/make-power-check.sh`, then `scripts/power/add-to-live-stick.sh --image IMG <add-on>`, as for `anal178c` | `hwcheck-NNN.json` → `scripts/power/s0i3-report.py` (§1.5–1.6) |
| Or, on the laptop's own Linux: `sudo python3 scripts/power/linux-s2idle.py --amd-s2idle` | nothing | `s0i3-report.py <hwcheck> <summary.json>` |
| Default boot, desktop up: **close the lid for 1 min, open it** | nothing new | `lid_events` in the next save-logs boot (it reads the earlier boot's logcat) |
| Default boot: **Quick Settings → Battery Saver, confirm** | nothing new | `epp_modes.battery_saver_seen` (`balance_power`) |
| Save-logs boot: **use the touchpad for 20 s** after the desktop appears | `main` with this PR (the EventHub patch) | `touchpad_clock` (0 repeat frames, every frame with MSC), `touchpad_clock_warnings` (0) |
| Nothing to do | — | `health_hal`, `epp_modes`, `s0i3` (Android's own suspends), `lid_and_power_config`, `key_layouts` |
