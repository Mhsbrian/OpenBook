# Evidence: first OpenBook boot on the ASUS ROG Zephyrus G14 (GA403WR), 2026-10-16

The owner flashed `openbook-hwcheck-20261016.img` (sha256 `9ea27811…`, `evidence/2026-10-16-installer/hwcheck-stick/`) to a SanDisk Ultra 62 GB stick, booted the G14 from it, and plugged the stick back into the build host. Its `openbook/logs/` held:
- `hwcheck-001.txt` (sha256 `033e9756…`): the probe's report;
- `hwcheck-001-dmesg.txt` (sha256 `c9c943e0…`): the full kernel log.

The stick's ESP was mounted read-only to read them. The copies here have the USB devices' serial numbers and the partition UUIDs of the laptop's internal disk replaced with `[redacted]`. The sha256 values above are those of the originals, which are kept on the build host only.

**What ran.**
1. Firmware → systemd-boot 262 (from the stick, Secure Boot off) → our GKI `6.18.21-android17-5-g44a90255c95f`.
2. The hardware-check probe ran as `rdinit`, then loaded ANAL-172's module set (GKI + 138 OpenBook modules) with ANAL-171's firmware subset.
3. The report was written to the stick and the laptop powered off.

The probe skipped the cs35l56 speaker-amp drivers (they download DSP firmware and tuning to the amps; no audio is played in the check), asus-wmi, asus-nb-wmi, hid-asus and test modules. Nothing was written to the laptop's NVMe.

## Results (C: from the report and kernel log)

| Area | Result | Where |
|---|---|---|
| Firmware and boot | UEFI boot from USB, Secure Boot disabled, `boot_part_uuid` partition found 1.4 s after the probe started | `efi: booted via UEFI`, `Secure boot disabled`, `block: 1 partition(s) with PARTUUID=3a26490e…` |
| Machine | ASUSTeK ROG Zephyrus G14 GA403WR, BIOS GA403WR.309 (2025-09-17), Ryzen AI 9 HX 370 w/ Radeon 890M, 24 threads, 31.9 GB, **AVX-VNNI present** | `dmi:`, `cpu:` |
| Drivers | **235 loaded, 0 failed**, 29 skipped (safety list, blocklist, tests) | `modules:` |
| Graphics | **amdgpu bound to 1002:150e.** IP blocks psp_v13_0_0, smu_v14_0_0, gfx_v11_0, vcn_v4_0_5, jpeg_v4_0_5. "SMU is initialized successfully", "Display Core v3.2.351 initialized on DCN 3.5", DMUB firmware 0x09005700 loaded via PSP. **eDP-1 detected with PSR** plus 8 DP outputs, `renderD128`, backlight `amdgpu_bl0` (native, not nvidia-wmi-ec) | dmesg 6.03–6.47 s, `class drm`, `class backlight` |
| Wi-Fi | **mt7925e bound to 14c3:7925**, `wlan0` created, WM firmware build 2026-08-13 loaded. **`regulatory.db` missing** (cfg80211 falls back to the world domain) | dmesg 6.72–7.15 s |
| Bluetooth | `hci0` up (btusb + btmtk), firmware build 2026-08-13 | dmesg 4.73, 6.48 s |
| Touchpad | ELAN `ASCE1206:00 04F3:3315` on the AMD I2C controller: Touchpad + Mouse input devices, so i2c-hid works over pinctrl-amd GPIO interrupts | dmesg 6.60 s |
| Keyboard | ITE `0b05:19b6` keyboard (USB HID, bound by hid-generic because hid-asus was skipped) | dmesg 2.55 s |
| Buttons | Lid switch, power button, sleep button | `input:` |
| NPU | amdxdna bound to 1022:17f0, `accel0` | dmesg 4.56 s |
| Power | Battery `BAT1` present, AC adapter offline (ran on battery), `amd-pmc` loaded, "Low-power S0 idle used by default for system suspend" | dmesg 1.30, 4.67 s |
| USB-C / USB4 | UCSI with 2 USB-C ports and 2 power-delivery sources, thunderbolt bound to the USB4 router 1022:151c, 4 xHCI controllers | `class typec`, `class power_supply`, `pci[after]` |
| Storage | NVMe 1c5c:1f69 (SK hynix, 2 partitions; read only by the kernel's partition scan) and card reader rtsx_pci | dmesg 1.68 s |
| Audio | 3 cards: AMD HD-Audio (1022:15e3) with Mic and Headphone jacks (ALC269-family codec driver loaded), Radeon HDMI/DP (1002:1640) and **NVIDIA HDMI/DP (10de:2f80)**. ACP 7.0 found no ASoC machine driver; expected, because the internal mic is on HDA | `class sound`, dmesg 6.93 s |
| NVIDIA dGPU | **Present on the bus** (`10de:2f58`, no driver, as intended). Its HDMI-audio function `10de:2f80` is bound by snd_hda_intel, which can keep the dGPU awake (ANAL-187). `dgpu_disable` was evidently 0 for this boot; the recorded default is to set it to 1 before the first OpenBook boot (ANAL-176) | `pci[after]`, dmesg 6.94 s |
| Not bound | AMD PSP/crypto 1022:17e0 (`ccp`, the open amd-pmf decision); 1022:150d (non-essential instrumentation) | `pci[after]` |
| Kernel log | No oops, warning backtrace or failed firmware load other than `regulatory.db` | the whole log |

**Android on the G14 too (C, indirect).** After the check, the stick's `metadata` partition was found formatted as ext4 at 15:15:06, with second-stage init directories written by 15:15:11 (`aconfig` storage records, `apex`, `ota`, `gsi`).
- So the stick was also booted into the "OpenBook preview" entry.
- On real hardware, Android's first-stage init found the stick by `boot_part_uuid`, mounted `super` with dm-verity and started second stage.
- That preview has no graphics stack for real hardware, so nothing was visible, and no log was kept. `bootstat` is empty, meaning there was no clean shutdown.

## Findings to act on

| # | Finding | Owner |
|---|---|---|
| 1 | Add wireless-regdb (`regulatory.db`, `.p7s`, licence) to the firmware set | Done for the check stick (v2); ANAL-198/179 for the product |
| 2 | The dGPU's HDMI-audio function is bound, which can keep the dGPU in D0. Measure it (v2 records `power_state`/`runtime_status`), then either set `dgpu_disable=1` as decided or blocklist that function | ANAL-176/187 |
| 3 | The backup GPT is not at the end of a stick larger than the image ("GPT: Use GNU Parted to correct GPT errors"). The live image's first-boot grow step must move it | ANAL-190 |
| 4 | The CPU frequency driver, sleep states, screen mode, battery health and temperatures were not recorded | Done in v2 |
| 5 | Suspend (s2idle) is untested on this model | v2 has an opt-in sleep-test entry |

## Not shown
- No screen output was tested: the check runs before any graphics userspace.
- Wi-Fi was not scanned and audio was not played. The speaker amps were deliberately left alone.
- A display-capable OpenBook on the G14 needs the G14 product (ANAL-199) and the AMD graphics userspace (ANAL-174).

## Stick updated to v2 (2026-10-16 15:40, owner's confirmation on ANAL-189)
- The owner confirmed `/dev/disk/by-id/usb-SanDisk_Ultra_[redacted]-0:0`.
- `scripts/installer/update-hwcheck-stick.sh` checked the stick before writing: ESP PARTUUID `3a26490e-…`, label OPENBOOK, existing OpenBook entry. It then replaced `openbook/check/hwcheck.img`, the two check entries and the README on that partition only (`stick-update-v2.log`).
- A read-only remount verified all four files against the bundle manifest (`../2026-10-16-installer/hwcheck-stick/v2/esp-update-MANIFEST.sha256`).
- The menu now offers "OpenBook hardware check" (default), "OpenBook hardware check + sleep test" and "OpenBook preview (virtual machines only)". `hwcheck-001` is still on the stick.

## Runs 2 and 3 (v2 check, 2026-10-16 15:47 and 15:48)
These are `hwcheck-002` (the check) and `hwcheck-003` (the sleep test), with JSON verdicts, reports and kernel logs. The v2 probe redacted the files itself (USB serials, internal-disk UUIDs). sha256 of the originals:
- `002.txt` `5873e37b…`, `002.json` `df3b3be9…`, `002-dmesg` `e0c3bedf…`
- `003.txt` `7e84333a…`, `003.json` `8ce15227…`, `003-dmesg` `15732d5f…`

| Area | Result (C) |
|---|---|
| Drivers | 235 loaded, 0 failed (both runs) |
| CPU power | **amd-pstate-epp, status active**. Governor powersave, EPP `balance_performance` (choices: default, performance, balance_performance, balance_power, power). Max 5.16 GHz |
| Sleep states | `mem_sleep: [s2idle]` only; `state: freeze mem disk` |
| Sleep test (run 3) | **The suspend/resume cycle works.** RTC alarm, s2idle entry, woke after 18.2 s ("Resume caused by IRQ 9, acpi"), `suspend_stats` success 0→1, fail 0, amdgpu SMU resumed, no errors after resume, Wi-Fi present |
| **Deep sleep** | **Not reached.** AMD PMC s0ix residency 0 µs before and after; the kernel log says "amd_pmc AMDI000A:00: Last suspend didn't reach deepest state". The machine idled in a shallow state, so it would drain the battery while asleep |
| dGPU | **D0, runtime active**, no driver on the GPU function. Its HDMI-audio function is bound by snd_hda_intel, also D0/active. On resume the kernel logs "pci 0000:64:00.0: Enabling HDA controller" (the NVIDIA HDA quirk) |
| Wi-Fi regulatory | `regulatory.db` now loads (the v1 "failed to load regulatory.db" is gone) |
| Battery | A32-K55 Li-ion, 63 %, discharging, **charge_full 4.063 Ah of 4.580 Ah design = 88.7 % health**, cycle count not reported (0) |
| Backlight | amdgpu_bl0 at 199500 / 399000 (50 %) |
| Temperatures | acpitz 47 °C and 20 °C before sleep, 45 °C after |
| eDP status | `edp_connected: false`. The connector's sysfs status reads "unknown" because no DRM client has probed it in the check (run 1 showed DC detecting eDP-1 with PSR). v3 asks for a probe first |

**Reading (HYPOTHESIS).** The dGPU sitting in D0 is the prime suspect for the missing S0ix residency. That matches `docs/nvidia.md` §1: with no driver and with VGA_SWITCHEROO off, the HDMI-audio function keeps the link up and the slot can't power down.

**v3 tests this directly.** A new menu entry, "OpenBook sleep test, NVIDIA GPU powered down", unbinds the HDMI-audio function, removes both NVIDIA functions and lets the root port runtime-suspend (option 2 in `docs/nvidia.md` §1, for this boot only). It then repeats the sleep test, records the bridge's power state, and lists every PCI function still awake right before suspend.

## Stick updated to v3 (2026-10-16, owner's confirmation on ANAL-189)
- Same guarded update as for v2 (`stick-update-v3.log`): only `openbook/check/hwcheck.img`, the three check entries and the README on the OPENBOOK partition.
- A read-only remount verified all five files against `../2026-10-16-installer/hwcheck-stick/v3/esp-update-MANIFEST.sha256`.
- Menu order: hardware check (default) → + sleep test → **sleep test, NVIDIA GPU powered down** → preview.
- Reports `hwcheck-001`…`003` are still on the stick.

## Run 4 (v3, "sleep test, NVIDIA GPU powered down", 2026-10-16 16:06)
These are `hwcheck-004.{txt,json,-dmesg.txt}`, redacted by the probe. sha256 of the originals: txt `7f2c5dfc…`, json `d859c177…`, dmesg `75ed536b…`.

| Area | Result (C) |
|---|---|
| eDP | **Fixed check:** `card0-eDP-1 connected`, preferred mode **2880x1800** (the panel) |
| dGPU detach | Both NVIDIA functions handled: `64:00.1` unbound from snd_hda_intel, both removed. Bridge `00:03.1` runtime PM on, and it went from D0 to **D3hot** (read while still "runtime suspending"; v4 waits for the final state) |
| Sleep | s2idle cycle OK (18.9 s, success +1, fail 0). After resume eDP-1 is connected and Wi-Fi present |
| **Deep sleep** | **Still not reached.** s0ix residency 0. The SMU reports "Last S0i3 Status: Unknown/Fail" with Hint Count 0→1, so the OS hint was sent but the SoC did not enter S0i3. SMU active-time counters after the cycle show USB4_0 (implausibly large, 3 655 017 247 312 µs) and MPM (1 356 µs) |
| Awake before suspend | 30 PCI functions in D0 with runtime PM off. This is normal before a system suspend: drivers suspend their devices during it. Functions with no driver include `65:00.2` (PSP/ccp, not loaded, the open amd-pmf decision) and `66:00.0` (non-essential instrumentation) |
| **dGPU on resume** | **The firmware brings it back.** pciehp on `00:03.1` reports "Card not present", then "Card present, Link Up", and re-enumerates `10de:2f58`/`2f80` ("Enabling HDA controller"). A driver-side detach therefore has to be redone after every resume, while `dgpu_disable=1` would keep the GPU off (consistent with `docs/nvidia.md` §1 on Omarchy) |

**Reading.**
- The driverless dGPU is not the only S0i3 blocker. Either detaching it doesn't remove its power (the bridge only reached D3hot), or something else blocks: USB4, MPM, a missing driver (ccp/PSP), or the platform. That remains a HYPOTHESIS.
- The kernel log alone can't tell which: `pm_debug_messages` was off.

**Next.**
1. **v4 stick:** the same entry with `pm_debug_messages` and dynamic debug for amd_pmc, pinctrl_amd and the ACPI LPS0 code. It also dumps amd_pmc's idle mask before and after, lists wakeup sources, and waits for the bridge's final power state, recording `d3cold_allowed`.
2. **Linux baseline on the same laptop:** AMD's `amd-s2idle test` (package amd-debug-tools 0.2.22 in Arch extra, MIT) shows whether this BIOS reaches S0i3 at all, and names the blockers.

## Stick updated to v4 (2026-10-16, owner's confirmation on ANAL-189)
- Same guarded update as for v2 and v3 (`stick-update-v4.log`): only `openbook/check/hwcheck.img`, the three check entries and the README on the OPENBOOK partition.
- A read-only remount verified all five files against `../2026-10-16-installer/hwcheck-stick/v4/esp-update-MANIFEST.sha256`.
- Menu order is unchanged: hardware check (default) → + sleep test → **sleep test, NVIDIA GPU powered down** (now with kernel sleep debugging) → preview.
- Reports `hwcheck-001`…`004` are still on the stick. The next run writes `hwcheck-005`.

## Run 5 (v4, "sleep test, NVIDIA GPU powered down", 2026-10-16 16:30)
These are `hwcheck-005.{txt,json,-dmesg.txt}`, redacted by the probe. sha256 of the originals: txt `883ac83d…`, json `338acb48…`, dmesg `5a638828…`.

| Area | Result (C) |
|---|---|
| dGPU detach | Both functions removed; bridge `00:03.1` went to **D3cold** (runtime suspended, `d3cold_allowed 1`). Run 4 read D3hot only because it didn't wait |
| Sleep | s2idle cycle OK (18.8 s, success +1, fail 0). The LPS0 calls all succeed: "screen off", "lps0 ms entry", "lps0 entry", then the matching exits. Woken by the RTC (IRQ 9, ACPI fixed event) |
| **Deep sleep** | **Still not reached.** s0ix residency 0; the SMU got the hint (Hint Count 0→1) but reports "Last S0i3 Status: Unknown/Fail", time to S0i3 0. During the cycle it logged USB4_0 active 78 416 µs and MPM 2 170 µs. amd_pmc idle mask at S0i3 entry `0xffef9afd` (before `0xf5ce9afd`, after `0xfd4c90fd`; the bits aren't publicly documented) |
| **LPI constraints** (`pm_debug_messages`) | **One constraint is not met: `\_SB_.PCI0.GPP0.SWUS`, "min power state:D3hot current power state:D0".** About 40 others are "Device not power manageable" (skipped). GPP0 and GPP0.SWUS each have their own power resource (`PWRS`) |
| Wakeup sources | Nothing held the system awake: `prevent_suspend_time` is 0 everywhere. The RTC (`00:00`, the wake alarm) has 2 events; single events from ucsi, ACAD, the power button and mmc0 (card reader) |
| dGPU on resume | Back again: IRQ 38 "PCIe PME", then pciehp on `00:03.1` "Card not present"/"Card present, Link Up", re-enumeration, and "PM: parent 0000:00:03.1 should not be sleeping" for both functions |
| Other | No slot power control on any hotplug port (`PwrCtrl-` on `00:01.1`, `00:02.2`, `00:03.1`), so ACPI power resources are the only switch. `00:01.1` bridges to `[bus 01-60]` with nothing behind it. The ACP audio and the NPU are suspended; `65:00.2` (PSP) and `66:00.0` still have no driver |

**Reading (HYPOTHESES).**
- The dGPU is ruled out as the only blocker: S0i3 still fails with its bridge in D3cold.
- **GPP0.SWUS is now the prime suspect.** Per the GA403WM ACPI dump cited in `docs/nvidia.md` (a sibling model, REPORTED), the dGPU is `GPP9.PEGP` on `00:03.1`, so GPP0 is a different port: most likely `00:01.1`, the hotplug bridge with nothing behind it. Its switch-upstream child then has no PCI device to put into D3, so Linux keeps it at its boot state, D0. That may keep its power resource on.
- The dGPU coming back on resume is better explained by the kernel than by the firmware: the root port is powered back up during resume, and that turns the slot on again. (This corrects the run 4 reading.)
- This needs two checks. First, which PCI device each ACPI path belongs to, and which power resources stay on: the v5 check records both. Second, whether Linux on the same laptop meets this constraint and reaches S0i3: `amd-s2idle`, still pending.

**v5 (`openbook-hwcheck-20261016e`, `../2026-10-16-installer/hwcheck-stick/v5/`).**
- Each PCI line now carries its ACPI path (`firmware_node`).
- The sleep entries list every power-manageable ACPI device (state, real state, PCI device) and every ACPI power resource (on/off). The lists are taken before the detach, before suspend and after resume.
- Tested in QEMU on a copy of the v4 image updated with the v5 bundle. Both sleep entries ran to completion; QEMU's firmware has no power-manageable ACPI devices, so those lists are empty there. The sysfs attributes were checked read-only on the dev host.
- The menu entries and README are byte-identical to v4; only `hwcheck.img` changes.

## Stick updated to v5 (2026-10-16, owner's confirmation on ANAL-189)
- Same guarded update as for v2–v4 (`stick-update-v5.log`): only `openbook/check/hwcheck.img`, the three check entries and the README on the OPENBOOK partition.
- A read-only remount verified all five files against `../2026-10-16-installer/hwcheck-stick/v5/esp-update-MANIFEST.sha256`.
- Menu order unchanged; the "sleep test, NVIDIA GPU powered down" entry now also maps ACPI paths and power resources.
- Reports `hwcheck-001`…`005` are still on the stick. The next run writes `hwcheck-006`.

## Run 6 (v5, "sleep test, NVIDIA GPU powered down", 2026-10-16 17:00)
These are `hwcheck-006.{txt,json,-dmesg.txt}`, redacted by the probe. sha256 of the originals: txt `18ba91de…`, json `0c3f8da7…`, dmesg `de33b436…`.

Same outcome as run 5: the dGPU bridge reaches D3cold, the cycle completes (18.6 s), s0ix residency is 0, "Last S0i3 Status: Unknown/Fail", and the only unmet LPI constraint is `\_SB_.PCI0.GPP0.SWUS`. New in v5 is the mapping:

| ACPI | PCI | State around the sleep (C) |
|---|---|---|
| `\_SB_.PCI0.GPP0` | `00:01.1`, the hotplug port to `[bus 01-60]` with nothing behind it | D3cold, its `PWRS` off, from before the detach to after resume |
| **`\_SB_.PCI0.GPP0.SWUS`** | **none** | **D0 (real D0), its `GPP0.SWUS.PWRS` ON**, before the detach, before suspend and after resume |
| `\_SB_.PCI0.GPP9` | `00:03.1`, the dGPU's root port | D0 with `PG00` ON → after the detach D3cold, `PG00` off → after resume D0, `PG00` ON |
| `\_SB_.PCI0.GPP9.PEGP` / `.NHDA` | `64:00.0` / `64:00.1`, the NVIDIA GPU / HDMI audio | removed by the detach; back after resume |
| `GPP3.NVME`, `GPP4.SDCR`, `GPP5.WLAN`, `GPPA.*` (iGPU, audio, xHCI 1), `GPPB.IPU_` (NPU), `GPPC.*` (xHCI 0/3/4, USB4 NHI0) | `61:00.0`, `62:00.0`, `63:00.0`, `65:00.x`, `66:00.1`, `67:00.x` | the devices' own drivers suspend them during the system suspend |

This confirms the run 5 sibling-model reading on this laptop: the dGPU is `GPP9.PEGP`, and GPP0 is the empty port.

**Why GPP0.SWUS stays on (C, from the 6.18 source).** When the PCI core sets up a bridge, `pci_acpi_setup()` calls `acpi_dev_power_up_children_with_adr()`, which puts the bridge's `_ADR` children into D0 so the bus behind it can be scanned (`drivers/pci/pci-acpi.c`, `drivers/acpi/device_pm.c`). Nothing is found behind `00:01.1`, so no PCI device becomes SWUS's companion, and nothing in the kernel ever powers it down again. Its power resource stays referenced and on, and the LPI constraint stays unmet. Whether this is what blocks S0i3 is still a HYPOTHESIS: a power resource left on for an empty port is a plausible blocker, but not a proven one.

**v6 (`openbook-hwcheck-20261016f`, `../2026-10-16-installer/hwcheck-stick/v6/`).** Tests the hypothesis directly with one change from run 6:
- `scripts/installer/kmod/openbook_acpi_d3cold.c`, a test-only module built against this exact kernel by `build-check-kmod.sh`. It puts named ACPI objects that no device uses into D3cold through the normal ACPI PM path (`_PS3`, then the power resource's `_OFF` once unreferenced). It refuses objects that are missing, not power-manageable, or the companion of a device. It holds the parent bridge runtime-resumed during the change, because ACPI PM refuses to change a child while its parent is in a deeper state. It never ships in an image.
- Entry 3 is renamed "OpenBook sleep test, NVIDIA GPU + unused port powered down" and adds `openbook.probe.acpi_d3cold=_SB.PCI0.GPP0.SWUS`. JSON `openbook-hwcheck/5` adds `acpi_d3cold`.
- **Tested in QEMU**, on copies of the v5 image updated with the v6 bundle:
  - **The unchanged entry 3:** the module loads on the check kernel (vermagic, CRCs and CFI all accepted), reports `\_SB.PCI0.GPP0.SWUS: not in the namespace` (QEMU has no such object), and the sleep test runs.
  - **Entry 3 with a fixture SSDT** (`scripts/installer/acpi-d3cold-test.asl`, loaded through the kernel's ACPI table upgrade) that recreates the G14's situation below QEMU's root port `00:04.0`: before the module, `TSWU` is D0 with no device and its `PWRS` is ON, as on the G14. The module logs "`\_SB.PCI0.S20_: companion of 0000:00:04.0, left alone`" and "`\_SB.PCI0.S20_.TSWU: D0 -> D3cold (0), parent held on: 0000:00:04.0`". Before suspend and after resume, `TSWU` is D3cold and `PWRS` is off (`qemu-fixture-report-excerpt.txt`).
  - **Entry 2:** unchanged, passes.
  - **Not covered in the VM:** a parent that starts in D3cold. QEMU's port isn't power-manageable, so on the G14, holding `00:01.1` awake from D3cold is exercised for the first time.
