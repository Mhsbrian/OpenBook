# The G14 under GKI 6.18.21 (AOSP power check, 2026-10-17) vs Linux 7.2.8 (2026-10-16): kernel logs (ANAL-257)

Inputs: `evidence/2026-10-17-power-input/g14-anal176t/hwcheck-001-dmesg.txt.gz` (pm_debug on, 4 RTC cycles of 19 s,
battery) and the owner's Linux inventory (quiet boot, no PM debug, 4 sleeps of 7.5 min to 15.4 h, mains). Same
board and BIOS (`GA403WR.309 09/17/2025`). A line missing from the Linux log means "not logged", not "did not happen".

| Area | GKI 6.18.21 | Linux 7.2.8 |
|---|---|---|
| PSP 65:00.2 | no driver | `ccp 0000:65:00.2: tee enabled`, `psp enabled` |
| amd-pmf | not built | `amd-pmf AMDI0103:00: registered PMF device successfully` ("No Smart PC policy present") |
| amdgpu DMUB | `Loading DMUB firmware via PSP: version=0x09005700` (from `/vendor/etc`) | `version=0x09005300` |
| Display Core | `v3.2.351 initialized on DCN 3.5` | `v3.2.384` |
| eDP PSR | `PSR support 1` | `PSR support 0` |
| amdgpu IP blocks | 0–11 | 0–11 plus `isp_v4_1_0` |
| USB on 67:00.0 (bus 4) | the boot stick, `usb 4-1: new SuperSpeed USB device` | nothing |
| dGPU during the sleep | cycle 0 removed (00:03.1 D3cold), cycles 1–3 present without a driver | NVIDIA unloaded at 216 s; re-enumerated by pciehp after every resume |
| pciehp after resume | 00:03.1 only in cycle 0 | 00:03.1 every cycle, 00:02.2 (card reader) after the 15.4 h sleep |
| amd_pmc | "Last suspend didn't reach deepest state" every cycle; idle mask at entry `0xffef9afd` (`0xffef9abd`, `0xffef9abf` once each), after `0xfd4c90fd`; table v3, hint count 1, time to S0i3 0 | no warning in 4 cycles |
| LPS0 | Microsoft-UUID screen off / entry / exit / screen on; no "Constraint not met" | not logged |
| Root `_OSC` | `OS supports [ExtendedConfig ASPM ClockPM Segments MSI HPX-Type3]` | adds `EDR` |
| Clocks | TSC; HZ 250, NO_HZ_IDLE | TSC + acpi_pm; HZ 1000, NO_HZ_FULL |
| Same on both | pcieport, nvme ("simple suspend"), rtsx_pci, mt7925e, xhci 65:00.4/67:00.0/.3/.4, thunderbolt 67:00.5, amdxdna, amd_sfh, ucsi_acpi, pinctrl_amd, mem_sleep s2idle, amd-pstate active, ASPM default, IOMMU features | |
