# Source review: GKI 6.18.21 vs Linux v7.2/v7.3 on the S0i3 path (ANAL-257)

GKI tree: `~/anybook/kernel/src/common` at `fbfdd65b0fd1` (the G14's kernel). Upstream: tags v6.18, v7.2, v7.3.
CONFIRMED means read in source; impact on S0i3 is HYPOTHESIS unless stated.

## PTM
- v7.2 `pci_ptm_init()` (`drivers/pci/pcie/ptm.c`) records the capability and adds a save buffer; it no longer
  enables PTM on Root or Switch Upstream Ports: `e1092d5e15e6` (v7.1-rc1), "PCI/PTM: Do not enable PTM automatically
  for Root and Switch Upstream Ports". CONFIRMED.
- `pci_suspend_ptm()` / `pci_resume_ptm()` run from `pci_pm_suspend()`/`pci_pm_resume()` and the runtime-PM pair,
  for every function, but act only where a driver called `pci_enable_ptm()` (ice, idpf, igc, mlx5). None of those
  is on the G14, and the 7.2 log has no "PTM enabled" line. CONFIRMED.
- GKI 6.18 with `CONFIG_PCIE_PTM=n`: every PTM function is a stub and there is no save buffer, so the firmware's
  value stays while the function has power and is lost (reset to off) after D3cold. CONFIRMED.
- Net: neither kernel turns PTM off for suspend on this laptop. PTM cannot be the difference.

## Thunderbolt / USB4
- GKI `drivers/thunderbolt` is byte-identical to v6.18 (no Android or 6.18.1–21 stable changes). CONFIRMED.
- System suspend of the AMD host router (1022:151c, generic USB4 class match, no NHI ops): `nhi_suspend_noirq()` →
  `tb_suspend_noirq()` → `tb_switch_suspend(root, false)` → `usb4_switch_set_wake()` then `usb4_switch_set_sleep()`
  (sets ROUTER_CS_5.SLP, polls ROUTER_CS_6.SLPR up to 500 ms); then the PCI core puts 67:00.5 into D3 with wake.
  The same in v7.3. CONFIRMED.
- `tb_switch_suspend()` returns void and ignores errors from both calls; `tb_sw_dbg` is compiled out in the GKI. A
  router that never reports sleep-ready leaves no trace. CONFIRMED (code), effect HYPOTHESIS.
- v6.18..v7.3 changes on the probe/resume path: Configuration Ready timeout 50 → 500 ms (`ba2cc38511012`, per the
  USB4 CM guide), Router Ready check after enumeration (`062023c4364ff`), notification timeout 10 → 255 ms
  (`e24f3c0df4837`), interrupt throttling set by service drivers (`c51777370ac2e`). None touches the sleep
  handshake itself. CONFIRMED (commits).
- GKI builds Type-C in and USB4 as a module; `include/linux/thunderbolt.h` uses `IS_REACHABLE(CONFIG_USB4)`, so the
  built-in typec code gets the stub `usb4_usb3_port_match()` and never links Type-C ports to USB4 ports. Sysfs links
  only; power effect unlikely. CONFIRMED (code).

## PCI core
- Only suspend-path difference: GKI `pci_set_low_power_state()` re-applies the ASPM policy to the parent link after a
  D3hot entry; removed in v7.2 by `c855c9921da72`. Normally a no-op. CONFIRMED (code), impact low.
- Identical in GKI and v7.2: `pci_bridge_d3_possible`, `pci_target_state`, `pci_prepare_to_sleep`,
  `pci_finish_runtime_suspend`, `__pci_enable_wake`, `pci_dev_run_wake`, `pci_bridge_d3_update`,
  `platform_pci_bridge_d3`, `pci_save_state`, `pci_restore_state`; `drivers/acpi/device_pm.c`, `power.c`. CONFIRMED.

## amd_pmc
- `c3a2521bcc8e4` (v7.2) is a refactor with no change for 1Ah model 0x24: SMU message registers 0x938/0x9BC/0x980,
  scratch register 0xF14, `soc15_ip_blk` (22 entries), OS hint `MSG_OS_HINT_RN`. CONFIRMED.
- v7.2 suspend-delay commits apply to listed Lenovo models (or `delay_suspend=1`); the 2.5 s over-voltage delay after
  a cycle that reached S0i3 is in both. CONFIRMED.
- v7.3 STB fixes matter only with `enable_stb=1`. CONFIRMED.
