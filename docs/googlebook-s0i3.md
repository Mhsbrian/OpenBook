# Deep sleep (S0i3) on the G14 under Ruby (ANAL-257)

The G14 (GA403WR, Ryzen AI 9 HX 370, BIOS GA403WR.309) never reaches S0i3 under our kernel, so asleep it draws
about 4.5 W, roughly 14 h from a full charge (ANAL-238). This page has the desk analysis, the diagnostics built for
the Googlebook image and for a Linux live USB, the owner steps, and the fix list. Labels: **CONFIRMED** (seen in a
log, a table or source cited here), **REPORTED** (someone else's measurement), **HYPOTHESIS** (not shown yet).
Evidence: `evidence/2026-10-24-ruby-s0i3/`. Earlier work: `docs/power-input.md` §1 and §7.6 (AOSP image),
`docs/googlebook-sleep.md` (Ruby lid and wake).

## State (2026-10-24)

| Question | Answer |
|---|---|
| Does Ruby reach S0i3? | **No**: 0 of 130 suspends over 7 boots (ANAL-238, CONFIRMED) |
| Can this laptop reach it? | **Yes**, under Linux 7.2.8: 4 cycles up to 15.4 h without amd_pmc's "didn't reach deepest state" (CONFIRMED, indirect: §1.1) |
| What blocks it on our kernel? | **Unknown.** Ruled out: the dGPU driver, PTM as a difference, platform `_OSC`, the PCI `_OSC`, amd_pmc, amd-pmf's suspend notice, the PSP's D-state, the dummy function, the ASUS modules (§1). Left, ranked: the PSP/TEE/amd-pmf drivers, the USB4 complex, amdgpu's display code, the kernel generation (§2) |
| What decides it? | The Linux live-USB run (§4 A), then the Ruby sleep-diagnostics boot (§4 B) |
| Fix proven? | Not yet |

## 1. Desk work: what the two kernels do differently

### 1.1 The Linux comparison, read again
The owner's root inventory of 2026-10-16 (Linux 7.2.8-5-omarchy-bore, `~/anybook/hw/ga403wr-20261016-135706`,
private) is the only Linux run on this laptop. Read again for ANAL-257 (`evidence/.../desk/linux72-dgpu-timeline.txt`):

- **The dGPU had no driver during the long sleep (CONFIRMED).** `supergfxctl -g` reports `Integrated`. NVIDIA's
  driver loaded at 211.6 s and unloaded at 216.6 s (`nvidia-modeset: Unloading`, `Unregistered Nvlink Core`); the
  first s2idle started at 5,539 s and lasted 15.4 h. After every resume pciehp reports `Slot(0-2): Card not
  present / Card present` on `00:03.1` and re-enumerates `64:00.0`: the slot lost power during the sleep. vfio-pci
  took `64:00.0` only after the first resume. So the issue's premise "Linux reached S0i3 with NVIDIA's driver
  managing the dGPU" does not hold: Linux reached it with the dGPU driverless or removed, as on our image.
  A driver for the dGPU (ANAL-239) may still be needed for other reasons, but it is not what Linux had here.
- **The S0i3 signal is sound (CONFIRMED in 7.2.8 source).** `amd_pmc_s2idle_restore()` always calls
  `amd_pmc_validate_deepest()`, which prints the warning when the SMU's `s0i3_last_entry_status` is 0. The dmesg
  covers the whole boot (2,877 lines from 0.000000), and `amd_pmc` is loaded. What is not proven: that it bound
  `AMDI000A` (it prints nothing at probe in either kernel).
- **Not logged** (quiet boot, no `pm_debug_messages`): idle mask, SMU table, wake IRQs. The live-USB run records them.

### 1.2 Ruled out from the desk
| Candidate | Why it is out | Label |
|---|---|---|
| PTM as the difference | Since v7.1 (`e1092d5e15e6`, "Do not enable PTM automatically for Root and Switch Upstream Ports") Linux only records the capability; `pci_suspend_ptm()` acts only where a driver called `pci_enable_ptm()` (ice, idpf, igc, mlx5: none on the G14), and the 7.2 log has no "PTM enabled" line. Both kernels leave the firmware's PTM settings alone through s2idle. Linux 7.2 also restores PTM after D3cold, which the GKI cannot (no save buffer): if anything, Linux has more PTM on, not less | CONFIRMED (source) |
| Platform `_OSC` | Our GKI vmlinux offers `0x00267cee`, Linux `0x006e7eff` (missing: PAD, APEI, fast thermal sampling, battery charge limiting, FFH). The G14's `\_SB._OSC` (SSDT `CPMMSOSC`) only forces `_PR3`, clears PCLPI, honours the USB4 bit (set by both) and calls `M625` the same way on both | CONFIRMED (ACPI table) |
| PCI host bridge `_OSC` | Same result on both: OS controls `PCIeHotplug PME PCIeCapability`; LTR, AER and DPC stay with the firmware | CONFIRMED (both logs) |
| amd_pmc | 6.18 → 7.3: same SMU registers (`0x938`), scratch register, OS hint and 22-entry IP list for family 1Ah model 0x24; the 7.2 suspend delays are for Lenovo models | CONFIRMED (source) |
| amd-pmf's suspend notice | APMF function 16 (heartbeat v2) calls only the OEM method `APXG`, which writes a POST code (SSDT 8, `PMFG`) | CONFIRMED (ACPI table) |
| The dGPU driver | Linux had none during the sleep (§1.1) | CONFIRMED |
| The PSP's D-state, the dummy function, the ASUS modules | ANAL-178's power check on the laptop (`docs/power-input.md` §7.6) | CONFIRMED |
| Thunderbolt's sleep sequence | The GKI's `drivers/thunderbolt` is byte-identical to v6.18; v6.18 → v7.3 changes nothing in `tb_suspend_noirq()`, `tb_switch_suspend()`, `usb4_switch_set_sleep()` or the AMD NHI path. What changed are probe/resume timeouts (§2) | CONFIRMED (source) |

### 1.3 The SMU's own numbers
- **Table layout.** Both kernels read `struct smu_metrics` the same way and name the per-IP slots with
  `soc15_ip_blk` (22 entries) for model 0x24. The two slots that are non-zero after our failed cycles are index 15
  (`USB4_0`) and 17 (`MPM`). Kernels use the newer `soc15_ip_blk_v2` order only for model 0x70; under it the same
  indices would read `USB4_RT0` and `USB4_0`, so either way at least one names the USB4 complex. Slot 15's low half
  is always `0x13250` and its high half reads like a float (`0x43cb0000` = 406.0), so the firmware's table version 3
  probably does not match the kernel's `u64` array (HYPOTHESIS). The Linux run gives the same table where S0i3
  works, which settles whether those slots mean anything.
- **Idle mask.** At the S0i3 attempt `0xffef9afd` (ANAL-189 runs 5–7, ANAL-178 cycles 1–2; `0xffef9abd` and
  `0xffef9abf` once each), after resume `0xfd4c90fd`. The clear bits at entry are 1, 8, 10, 13, 14 and 20. No public
  decode exists: amd_pmc only prints it and AMD's `amd-s2idle` only reports bits that change between cycles. The
  Linux value at entry is the reference we lack.
- **The SMU never started S0i3 entry**: hint count 1, "Time to S0i3: 0" in every cycle (CONFIRMED). The OS hint
  arrives; something the firmware checks before entry is not met.

### 1.4 Test conditions that differ (confounders)
- Every AOSP-image power check booted from a USB 3 stick on the xHCI at `67:00.0` (`usb 4-1 ... SuperSpeed`),
  which sits on the same internal bus as the USB4 router (CONFIRMED). Ruby is installed on the NVMe and missed S0i3 overnight on battery, so the
  stick cannot explain Ruby on its own (HYPOTHESIS: nothing else was plugged in overnight; not recorded).
- The AOSP power check ran 19 s RTC cycles on battery; Linux slept for hours on mains power. Ruby also missed S0i3
  through a 631-minute night (ANAL-238), so short cycles are not the explanation (CONFIRMED).
- **A probe bug, fixed here.** `scripts/installer/probe-init.c` stopped reading cpuidle's s2idle statistics at
  state 0 (POLL has none), so "Deepest C-state: None" in `s0i3-report.md` from probe runs says nothing.

## 2. What is left, ranked

| # | Suspect | For | Against | Decided by |
|---|---|---|---|---|
| 1 | **PSP driver (`ccp`), TEE (`amdtee`) and `amd_pmf`**, absent from the GKI (`CRYPTO_DEV_CCP`, `TEE` unset; amd-pmf needs both and is on the GKI symbol deny-list) | The largest set of firmware-facing drivers Linux has and we lack. Linux logs `ccp 0000:65:00.2: tee enabled / psp enabled` and `amd-pmf ... registered PMF device successfully` | The PSP's D-state alone was ruled out. Nothing public says S0i3 needs them | Live USB phases `no-pmf` and `no-ccp`: if Linux loses S0i3 there, this is it |
| 2 | **The USB4 complex** (router `67:00.5` and its xHCIs behind `00:08.3`) | The SMU's non-zero slots name USB4 under either IP order. `tb_switch_suspend()` ignores a failed sleep handshake, so a router that never reports sleep-ready leaves no trace in our logs. 7.2 also waits longer for Configuration Ready (50 → 500 ms, `ba2cc38511012`) and checks Router Ready (`062023c4364ff`) at probe and resume | Same sleep code in both kernels. The router is in D3 at entry. Slot values look mis-decoded | Ruby `usb4=1` and the snapshot vs the same on Linux; `amd-s2idle` on Linux |
| 3 | **amdgpu's display code** | Display Core v3.2.351 (GKI) vs v3.2.384 (7.2), DMUB firmware `0x09005700` (ours, from `/vendor`) vs `0x09005300`, eDP "PSR support 1" vs 0, no ISP block on the GKI | The SMU's DISPLAY and GFX slots read 0 in every failed cycle | A 6.18 LTS live kernel (generation bisect), or Linux with our DMUB file |
| 4 | **Kernel generation in general** (6.18 vs 7.2) | Everything above that is not config | — | The same live USB booted with a 6.18 LTS kernel |
| 5 | **PTM left on by the firmware** | The GKI never touches it | Linux 7.2 does not either (§1.2) | Ruby `ptm_off=1`; the module also lists what the firmware enabled |
| 6 | **MPM / firmware handshakes** | Slot 17 | No source names the IP | Nothing yet |

## 3. Tools built here

### 3.1 `openbook_sleep_diag` (test-only vendor module)
`kernel/devices/anybook/sleep_diag/`, built as `//devices/anybook:openbook_sleep_diag` on the device
`kernel_build`, like `openbook_lid_guard`. It loads on every boot and stays **inert** ("inactive", one line) unless
kernel command-line parameters turn it on; libmodprobe hands `openbook_sleep_diag.<name>=<value>` to the module
(`system/core/libmodprobe/module_config.cpp`, `ParseKernelCmdlineOptions`).

| Parameter | What it does |
|---|---|
| `ptm_off=1` | PTM Enable and Root Select off on every PCI function before each suspend, deepest first; restored after, parents first (`ptm_plan.h`). The only write the module ever makes |
| `snapshot=1` / `2` | At the S0i3 attempt (LPS0 prepare) and on exit: every PCI function not in D3 (`2`: all) with kernel and hardware D-state, runtime PM, driver, ASPM, L1 substates, link status, LTR, PTM, ACPI state |
| `usb4=1` | The USB4 host routers and the thunderbolt devices below them: runtime PM, D-state, wakeup, bridge state; at load, 60 s later and at every suspend |
| `cycles=N` | Full logs for the first N suspends (default 3), one line each after that |

With any parameter set it also lists every PCI function with a PTM capability once at load, with what the firmware
enabled. The same source builds out of tree on Linux 7.2, which is what the live-USB script loads, so the two
kernels' snapshots compare line by line.

**Checked** (`evidence/.../module/`):
- Kleaf build `b7855bc7…` (`openbook_sleep_diag.ko`), vermagic `6.18.21-android17-5-gfbfdd65b0fd1` (the G14's
  kernel), all 32 undefined symbols in the G14 KMI list, all 33 modversion CRCs equal to the G14's `vmlinux.symvers`.
- Host test of the PTM order against a mock config space: 10/10 (`ptm_plan_test.c`).
- QEMU with the G14 bzImage, the power check's LPS0 fixture and a PCIe root port with an endpoint: 17/17
  (`run-vm-test.sh`, `check-vm-log.py`): inert load, active load, three s2idle cycles through the LPS0 hooks (woken
  by the ACPI power button over QMP), one S3 cycle, the 60 s USB4 report, `cycles` limiting, clean unloads, no
  kernel warnings. QEMU has no PTM-capable device and no USB4 router, so on hardware the PTM writes and the USB4
  lines are new.
- Builds without warnings against Linux 7.2.8's headers (compiled only, never loaded on the build host).

### 3.2 Ruby sleep-diagnostics entries
`kernel/devices/anybook/sleep_diag/stick-entries.json`, for `scripts/googlebook/stick-entries.py` (allowlist
extended to these four parameters and their value ranges; 5/5 tests):
- **"Googlebook - S0i3 diagnostics, save logs to USB (10 minutes)"**: the save-logs entry plus `pm_debug_messages
  openbook_sleep_diag.snapshot=2 openbook_sleep_diag.usb4=1 openbook_sleep_diag.cycles=4`.
- **"Googlebook - S0i3 test with PTM off, save logs to USB (10 minutes)"**: `pm_debug_messages
  openbook_sleep_diag.ptm_off=1 openbook_sleep_diag.snapshot=1 openbook_sleep_diag.usb4=1
  openbook_sleep_diag.cycles=4`.

They ship through a Ruby release (module in `vendor_dlkm` with `build-module-candidate.py`, entries with
`stick-entries.py`), with the owner's approvals. Neither entry changes security, verity, SELinux or init.

### 3.3 Linux live-USB comparison: `scripts/power/linux-s2idle.py --live-usb`
Phases, in order: `baseline` (2 cycles), `nouveau` (nouveau bound, runtime PM on, waits up to 60 s for the dGPU's
root port to runtime-suspend), `driverless` (nouveau and snd_hda_intel unbound, then exactly what
`openbook-pc-setup dgpu-pm` does), `ptm-off` (the module reloaded with `ptm_off=1`), `no-pmf`, `no-ccp`.
`amd-s2idle test` runs one more cycle at the end of every phase. Everything unbound or unloaded is put back after
its phase, also on errors and Ctrl-C. It refuses to run while any partition of an internal NVMe disk is mounted or
used as swap. An optional `eco` phase (dgpu_disable=1, as supergfxctl's Eco) needs `--allow-firmware-change` and
puts `dgpu_disable` back to 0 with a PCI rescan, also after an error; it never touches `gpu_mux_mode`. Tests: 8/8
on a fake sysfs (`linux-s2idle-test.py`), and a dry run on the build host.

## 4. Owner steps

### A. Linux live USB (about 30 minutes; a spare stick, never the SanDisk ending 2034)
1. Write a current Linux live image with kernel 7.2 or newer to a **spare** stick yourself. It needs nouveau with
   GB20x support and `linux-firmware`'s NVIDIA GSP files (whether nouveau drives the G14's GB205 is ANAL-239's
   question; the `nouveau` phase reports it). A current-month Arch Linux ISO is the suggestion, because its kernel
   then matches the repository's `linux-headers` (untested on this laptop). Nothing on the laptop's SSD is
   installed, mounted or written.
2. Boot the G14 from it with the charger connected, connect Wi-Fi, and do not open the internal disk in a file
   manager.
3. In a terminal:
   ```bash
   pacman -Sy --needed git python make gcc linux-headers amd-debug-tools   # Arch; elsewhere the same packages
   git clone https://github.com/Mhsbrian/OpenBook.git && cd OpenBook && git checkout <this PR's branch>
   sudo python3 scripts/power/linux-s2idle.py --live-usb
   ```
   On a live ISO, `linux-headers` must match the running kernel (`uname -r`); without them the run still works but
   loses the PCI snapshot and the `ptm-off` phase.
4. Attach the `openbook-linux-s2idle-<time>.tar.gz` it writes to ANAL-257 (redacted: no MAC, serial, UUID, IP or
   host name).
5. *Optional, only after you approve it here naming the G14:* `sudo python3 scripts/power/linux-s2idle.py --phases
   baseline,eco --allow-firmware-change` (sets the firmware's `dgpu_disable` to 1 for one cycle and back to 0).
6. *Optional:* the same run from a live image whose kernel is 6.18 LTS, which splits "kernel generation" from
   "kernel configuration" (suspects 3 and 4).

### B. Ruby sleep diagnostics (after a Ruby release carries the module and the entries)
Boot **"Googlebook - S0i3 diagnostics"**, close the lid for about a minute twice, let it finish its 10 minutes;
then the same with **"S0i3 test with PTM off"**. The agent reads the stick logs on the build host
(`scripts/googlebook/usb-log-collect.sh`) and reports with `scripts/power/s0i3-report.py`.

## 5. Reading the results

| Live USB | Ruby diagnostics | Meaning | Fix |
|---|---|---|---|
| S0i3 in `baseline`, lost in `no-ccp` (or `no-pmf`) | — | The firmware needs the PSP/TEE (or amd-pmf) driver | Suspect 1 fix (§6) |
| S0i3 in every phase | `ptm_off=1` reaches S0i3 | The firmware's PTM setting blocks it under our kernel | `openbook_sleep_diag`'s PTM step as a product module, then a GKI request for `CONFIG_PCIE_PTM` |
| S0i3 in every phase | USB4 router not runtime-suspended, or its parent awake, only on Ruby | The USB4 complex | Suspect 2 fix (§6) |
| S0i3 in every phase; a 6.18 LTS kernel loses it | — | Kernel generation | Bisect amdgpu and thunderbolt first (suspects 2–3) |
| S0i3 nowhere on the live USB | — | Firmware state or distro config, not our kernel | Compare with the 2026-10-16 inventory; `amd-s2idle`'s report |
| `driverless` loses S0i3 where `nouveau` keeps it | — | The dGPU needs a driver after all | ANAL-239/243 |

## 6. Fix list (conditional, in order)
1. **PSP/TEE/amd-pmf**, if the live USB implicates them: `ccp` + `tee` + `amdtee` (+ `amd_pmf`) as vendor modules.
   The blocker is the GKI symbol deny-list (`docs/kernel.md`, the amd-pmf/SEV decision): an owner decision, then a
   KMI symbol-list request, or a minimal module that performs only the init the firmware needs. Ruby image, new
   issue.
2. **USB4**: if Ruby's snapshot shows the router or its xHCIs awake, fix that state; if it shows them asleep but the
   SMU still names USB4, backport v7.2's router-ready and timeout changes as a vendor `thunderbolt` (blocklisting
   the GKI one). Ruby image, new issue.
3. **amdgpu**: if the generation bisect implicates it, test v7.2's DMUB file first (firmware only), then DC fixes
   for DCN 3.5. Ruby image.
4. **PTM**: only if `ptm_off=1` reaches S0i3 on Ruby.
5. A dGPU-related fix goes to ANAL-239/243.

## 7. Release impact
- Diagnosis (this page, `linux-s2idle.py`, the probe fix): **none** (owner-run tools; the probe only matters when an
  AOSP check image is rebuilt).
- `openbook_sleep_diag` and its two boot entries: **Ruby**, test-only, inert unless the entry is chosen. Handoff:
  `evidence/2026-10-24-ruby-s0i3/handoff-ANAL-257.json`.
