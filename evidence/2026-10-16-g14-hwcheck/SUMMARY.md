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
- The owner confirmed `/dev/disk/by-id/usb-SanDisk_Ultra_4C530001041228122034-0:0`.
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
