# Power and input on the G14 (ANAL-178)

How OpenBook handles suspend, CPU power, battery, lid, keyboard and touchpad on the ASUS ROG Zephyrus G14 2025 (GA403WR, Ryzen AI 9 HX 370), and how each piece is tested. **C** = confirmed by a log or test cited here; **HYPOTHESIS** = not yet shown. Evidence for this document: `evidence/2026-10-17-power-input/`.

## State (2026-10-17)

| Feature | State | Source |
|---|---|---|
| Suspend to idle (s2idle) | Works: cycles complete, the panel and Wi-Fi come back (C) | runs 3–7, `evidence/2026-10-16-g14-hwcheck/` |
| Deepest sleep (S0i3) | **Not reached by our kernel** (C, runs 2–7). The laptop's own Linux 7.2 shows no failure in 4 cycles (C, indirect, §1.1). Root cause open; tests ready (§1.4) | §1 |
| CPU power | `amd-pstate-epp` active, EPP `balance_performance` (C). The power HAL's EPP hints (ANAL-199) are not yet observed on the laptop | runs 2–7, live-001 |
| Battery | Level, status and voltage reach Android; **health "unknown", temperature 0, charge counter 0** (C): the ACPI battery has no `health`, `temp` or `charge_counter` file. **The OpenBook health HAL** fills charge counter, state of health and health from the files it has (host tests; built into `anal178b`, runs in QEMU; not yet on the laptop) | live-001 `dumpsys battery`, §3 |
| Backlight | `amdgpu_bl0`, 0–399000 (C) | live-001 |
| Thermal | Zones `THRM` (about 40 °C) and `TZ01` (a constant 20 °C), `k10temp` bound. The thermal HAL has not run with a booted framework on the laptop yet | runs 2–7, live-001 |
| Touchpad | ELAN `04F3:3315`: InputReader classes it `TOUCH \| TOUCH_MT \| TOUCHPAD`, so Android 17's gestures-library mapper drives it (C). The gestures library logs "Clock changed backwards" about every 40 ms of finger movement (C, ANAL-176's desktop2 boots); cause open, capture added (§2) | live-001 `dumpsys input`, desktop2 logcat |
| Keyboard | hid-asus, our layout file, keyboard backlight as an input light (`LIGHT`) (C) | live-001 |
| ASUS hotkeys (WMI) | Used AOSP's `Generic.kl` (C); **now has its own layout** (`validatekeymaps`; in the `anal178b` image; not yet on the laptop) | §2 |
| Lid, power and sleep buttons | Input devices present (C). **Closing the lid did nothing** in AOSP's default config; the new PC overlay makes it sleep. Booted in QEMU, the `anal178b` image reports `getLidBehavior=LID_BEHAVIOR_SLEEP`, short press 6 (lock or sleep), long press = power menu (C, QEMU); not yet on the laptop | §2, §3, §5 |

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
- **"Clock changed backwards"** (ANAL-176's desktop2 boots: 325 and 300 lines, about every 40 ms while a finger moves). The gestures library's `TimestampFilterInterpreter` rebuilds its time base from `MSC_TIMESTAMP`, re-syncing to the event clock when it goes backwards or is 0, and `LookaheadFilterInterpreter` logs this when a new state is due before the queued one. hid-multitouch derives `MSC_TIMESTAMP` from the device's Scan Time, assumed in 100 µs units, and restarts it at 0 after a second without reports. Neither path explains a jump every 40 ms with a correct device clock, so the device's Scan Time unit or its reports are the suspects (HYPOTHESIS). The save-logs capture now records every HID report descriptor (`HIDDESC`, for the Scan Time unit) and, after `boot_completed`, 20 s of the touchpad's raw events (`TOUCHPADEV`); `live-report.py` turns them into `touchpad_clock` (MSC frames, backward steps, MSC seconds per event second). For that capture, use the touchpad during the 20 s after the desktop appears in a save-logs boot. Possible fixes after that: a gestures property (`Fake Timestamp Delta`) in the IDC, or a hid-multitouch quirk in the kernel lane.
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
- **Save logs** (`scripts/installer/live-init.c` COLLECT) now also records suspend statistics (`hw_sleep` is S0i3 time on AMD), Android's power and lid state with the lid and power-button behaviour in force, EPP per CPU policy, thermal sensors, the battery and its charge limit, LEDs, and `getevent -lp`. `live-report.py --expect g14` gains verdicts: `touchpad_gestures`, `key_layouts`, `lid_switch`, `lid_and_power_config`, `s0i3`, `kbd_backlight`, `epp`. Run inside Android 17 in QEMU with `scripts/power/collect-qemu.sh`: every section runs on the image's own mksh and toybox (`qemu/collect-*`). The VM also suspended itself after its screen timeout, one attempt failing with EBUSY.
- **Health HAL** (`device/anybook/common/pc/hals/health`, `android.hardware.health-service.openbook`). AOSP's example HAL reads the ACPI battery but reports health "unknown", temperature 0 and charge counter 0 (C), because AOSP's `BatteryMonitor` takes those from `health`, `temp`, `charge_counter` and `state_of_health`, which phone fuel gauges have and ACPI batteries don't. The OpenBook HAL is AOSP's (`libhealth_aidl_impl`) plus a subclass: charge counter from `charge_now`, state of health from `charge_full`/`charge_full_design` (88 % on this battery, run 2), and health GOOD at 80 % and above, FAIR below (the 80 % line is a choice, HYPOTHESIS), only where the kernel reports nothing. `energy_*` batteries are converted with `voltage_min_design`. Values the kernel does report are untouched; no battery temperature exists. Host tests: 18/18 with three battery fixtures (the G14's BAT1, an energy-based worn battery, a mouse and an empty bay to skip). In QEMU the service runs (`init.svc.vendor.health-openbook=running`); a VM has no battery.
- **Thermal.** `TZ01` reads a constant 20 °C, so it is no skin sensor; picking one needs readings under load (the save-logs `SENSORS` section).

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
> **Superseded image (2026-10-17):** write **`openbook-live-20261017-combined`** instead (`evidence/2026-10-17-g14-combined/`). It contains this image's contents plus ANAL-200's arm64 bridge, and it passes the same tests in QEMU. The steps below are unchanged; use that file name in the `write-stick.sh` command.

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
- S0i3: results of §1.5 A and B, then the fix in the kernel lane (§1.6).
- On the laptop (the `anal178b` steps, §5): lid close → sleep → wake, the health HAL's values, EPP hints, the touchpad clock capture; then double brightness/backlight steps and the Fn key map.
- Touchpad "Clock changed backwards": decide the fix from the `touchpad_clock` capture (§2).
- Thermal skin sensor and gesture tuning: need readings and feel from the laptop.
- `service list` hangs in QEMU on the Wi-Fi/Bluetooth/audio images at the service after `IAuthSecret` (the Bluetooth HAL with no adapter, HYPOTHESIS; ANAL-179's area); save logs now bounds it to 30 s.
- amd-pmf (owner decision, `docs/kernel.md`): the §1.5 Linux run shows whether S0i3 needs it.
