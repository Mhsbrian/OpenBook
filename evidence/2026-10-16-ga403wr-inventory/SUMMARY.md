# GA403WR hardware inventory (2026-10-16)

The owner ran `scripts/hw-inventory.sh` on the laptop without `--with-root`, so there is no `dmesg`, `dmidecode` or ACPI table dump. It ran under Arch (Omarchy), kernel 7.2.8. The files in this directory come from that archive with serials, UUIDs and MAC addresses already redacted by the script. The hostname, kernel command line and OS details are left out. `fwupd.txt` has colour codes and fwupd's per-device ID hashes removed. `cpuinfo-cpu0.txt` is the first CPU's entry from `/proc/cpuinfo`.

A second run with root (13:57 the same day, `root/`) added `dmesg`, `dmidecode`, the EDID, the backlight and the ACPI tables; see [Root run](#root-run-2026-10-16-1357). Rows it changed are marked *(root run)*.

**The board is `GA403WR`** (`dmi.txt`, BIOS `GA403WR.309`, 2025-09-17). `docs/HARDWARE.md` had assumed GA403WP.

| Component | What the inventory shows | Driver on the laptop (7.2) | AnyBook 6.18 kernel (ANAL-171) |
|---|---|---|---|
| CPU | AMD Ryzen AI 9 HX 370 w/ Radeon 890M, 24 threads; `avx_vnni`, `avx512f`, `avx512_vnni`, `avx512_bf16` all present | amd-pstate | `X86_AMD_PSTATE=y` (GKI) |
| RAM | 32 GB (`MemTotal` 31,934,248 kB): LPDDR5(X) 8000 MT/s, 4× 8 GiB Samsung `K3KL9L90DM-MGCU` *(root run)* | — | — |
| iGPU | `1002:150e` rev c1, Strix [Radeon 880M/890M]; eDP 2880×1800 connected | amdgpu | `amdgpu.ko` + `gc_11_5_0`, `dcn_3_5`, `psp_14_0_0`, `sdma_6_1_0`, `vcn_4_0_5` firmware |
| Panel | Samsung `ATNA40CU05-0`, EDID `SDC` product 16796 (`0x419c`), 2880×1800, 48–120 Hz adaptive sync (DisplayID 2.0), HDR static metadata, max 617 cd/m² *(root run)*. amdgpu: `PSR support 0`, sink PSR version 1, DPCD caps 0x3a | amdgpu DC | `amdgpu.ko`; no panel firmware |
| Touchscreen | None. `input-devices.txt` has no touchscreen and no I2C HID device besides the touchpad | — | — |
| dGPU | GB205M **RTX 5070 Ti Laptop `10de:2f58`** plus HDMI audio `10de:2f80` at `64:00.0` behind `00:03.1`, PCIe 4.0 x8 *(root run, from `dmesg`)*. Present at boot; at collection time `supergfxctl -g` = `Integrated`, `-S` = `off`, so it never showed in `lspci`. ASUS: `dgpu_disable=0`, `gpu_mux_mode=1` (Optimus), `nv_base_tgp=80` | nvidia (open kernel module 615.71.09) | Kept off by design |
| NPU | `1022:17f0` rev 10 | amdxdna | `amdxdna.ko` + `amdnpu/17f0_10` |
| Wi-Fi | MediaTek MT7925 `14c3:7925` | mt7925e | `mt7925e.ko` + `mediatek/mt7925/*` |
| Bluetooth | `0489:e11e` (Foxconn MT7925 BT) over USB | btusb + btmtk | `btusb.ko`; 0489:e11e is in the 6.18 MT7925 table |
| Audio codec | Realtek **ALC285**, codec SSID **1043:1024** (`codec-card2-alc285.txt`). lspci's "ALC245" is a BIOS label | snd_hda_intel | Quirk backported from mainline cbd46cbc5470 (`kernel/patches/common/0002-*`) |
| Speaker amps | 2× Cirrus CS35L56 Rev B0 (ROM fw 3.4.4) at I2C `0x30`/`0x31` (`CSC3556:00-cs35l56-hda.0/.1`) | serial-multi-instantiate + cs35l56-hda | built. Firmware *(root run)*: the laptop loads `cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1.wmfw` (DSP v3.11.16, 41 algorithms) and `-amp1.bin`/`-amp2.bin`. In linux-firmware these are WHENCE links to the 10431044 tuning; now in `anybook-amd.rules` (137 files). The earlier "no tuning file" entry here was wrong |
| Capture | Only `ALC285 Analog` (HDA) is a capture device. ACP 7.0 (`1022:15e2` rev 70) is bound by `snd_acp_pci` but registers no capture PCM | snd_hda_intel | The internal mic is on the HDA codec, not an ACP DMIC. ACP modules are still built |
| HDMI/DP audio | `1002:1640`, ATI R6xx HDMI codec | snd_hda_intel | `snd-hda-codec-atihdmi.ko` |
| Touchpad | ELAN `ASCE1206:00 04F3:3315` (PNP0C50) on the DesignWare I2C controller (4× AMDI0010) | i2c_hid_acpi + hid-multitouch | `i2c-hid-acpi.ko`, `i2c-designware-*.ko`, `PINCTRL_AMD=y`, `X86_AMD_PLATFORM_DEVICE=y` |
| Keyboard | `0b05:19b6` "ITE Device(8910)" | hid-asus | `hid-asus.ko` (ROG N-KEY 2 ID is in 6.18) |
| Hotkeys, platform | `asus-nb-wmi`; asus-armoury attributes present | asus_wmi, asus_nb_wmi, asus_armoury | asus-wmi/asus-nb-wmi built (have `dgpu_disable`, `gpu_mux_mode`, `ppt_*`). asus-armoury is 6.19+; mainline has a GA403WR power table |
| Backlight | `amdgpu_bl1` (raw, max 400000) on `card1-eDP-1` *(root run)*. `nvidia_wmi_ec_backlight` loads but registers no backlight device | amdgpu | `amdgpu.ko`. `nvidia-wmi-ec-backlight.ko` stays for a dGPU-only MUX mode, where it would likely be chosen (hypothesis) |
| Webcam | `3277:0060` Shinetech FHD UVC | uvcvideo | `USB_VIDEO_CLASS=y` (GKI) |
| Card reader | Realtek RTS525A `10ec:525a` | rtsx_pci, rtsx_pci_sdmmc | `rtsx_pci.ko`, `rtsx_pci_sdmmc.ko` added |
| NVMe | SK hynix PVC10 `1c5c:1f69`, firmware 61000A60 | nvme | `BLK_DEV_NVME=y` (GKI) |
| USB host | 4× xHCI: `1022:151e`, `151f`, `151a`, `151b` | xhci_hcd | `USB_XHCI_HCD=y`, `USB_XHCI_PCI=y` (GKI) |
| USB4 | `1022:151c` USB4 Router | thunderbolt | `thunderbolt.ko` (GKI module) |
| USB-C | `USBC000` (UCSI), 2 source power supplies | ucsi_acpi | `ucsi_acpi.ko` |
| Power | `AMDI000A` (amd_pmc), `AMDI0103` (amd-pmf), `AMDI0104` (amd_hfi); `mem_sleep` = `[s2idle]` only; battery `BAT1` A32-K55, `ACAD` | amd_pmc, amd-pmf, amd_hfi, battery, ac | amd-pmc, battery, ac built. amd-pmf blocked (`symbols.deny`). `AMD_HFI` is bool (would be a fourth built-in), not enabled |
| TPM | `MSFT0101` + TPM2 ACPI table; fwupd: Microsoft (Pluton) TPM, firmware 10.6.0.4 | tpm_crb_acpi | `tpm_crb.ko` |
| Security processor | CCP/ASP `1022:17e0`; fwupd: AGESA `StrixKrackanPI-FP8 1.1.0.0a`, PSP bootloader 00.3e.04.74 | ccp | **Not built** (`CRYPTO_DEV_CCP` unset). Only amd-pmf needs it (through `AMDTEE`), so it follows the amd-pmf decision. amdgpu and amdxdna don't depend on it |
| SMBus | FCH SMBus `1022:790b` rev 71 | i2c_piix4 | `i2c-piix4.ko` |
| Temperatures, fan | Data Fabric `1022:16fb` (k10temp); ACPI thermal zones `LNXTHERM:00`/`:01`; fan `PNP0C0B` | k10temp, acpi-thermal, acpi-fan | `k10temp.ko`, `thermal.ko`, `fan.ko` (+ `hwmon.ko`) |
| Buttons, lid | Power `PNP0C0C`, lid `PNP0C0D`, sleep `PNP0C0E`; all three are input devices | acpi-button | `ACPI_BUTTON=y` |
| EC, WMI | EC `PNP0C09`; 3× WMI `PNP0C14` | acpi-ec, acpi-wmi | `ACPI_EC=y`, `wmi.ko`, `wmi-bmof.ko` |
| RTC, timers | CMOS RTC `PNP0B00`, HPET `PNP0103` | rtc_cmos | `RTC_DRV_CMOS=y`, `HPET=y` |
| Watchdog | FCH TCO | sp5100_tco | Not enabled (`SP5100_TCO` unset). Not needed |
| Energy counters | RAPL MSRs | intel_rapl_msr | Not enabled (`INTEL_RAPL` unset). It would give package energy readings for power tests; optional |
| IOMMU | `1022:1508`, IVRS table present | amd_iommu | `AMD_IOMMU=y` |
| Boot | UEFI 2.90 (AMI), Secure Boot disabled, Limine boot loader, TPM2 available | — | — |

### ACPI devices with no driver
Checked against the decoded tables *(root run)*:
- `AMDI0060` and `AMDI0016` (4×) have `_STA` 0: the firmware disables them. The five UARTs (`AMDI0020`) are disabled too.
- `AMDI0052` is a bare `PPKG` device (only `_HID` and `_STA`). In 6.18 the same ID is the ACP 6.3 machine-match key (`sound/soc/amd/acp/amd-acpi-mach.c`); the ACP 7.0 table matches `AMDI0029`, which only a UART's `_HID` method can return here, and the UARTs are off. That fits ACP registering no capture PCM.
- `MSFT0201` is the "Microsoft Pluton security processor" (its `_DDN`, SSDT13). `DRTM0001` is a `DRTM` device (SSDT14). `NVDA0820` is returned by a `_HID` method in SSDT5; hypothesis: NVIDIA's platform controller interface for the proprietary driver.
- `ASUS2018` (`ASUP`) and `ASUS9001` (`ARL2`, present only when `AACI` = 1) are bare devices with only `_HID` and `_STA`, most likely hooks for ASUS's Windows services (hypothesis).
- No 6.18 or 7.2 driver binds any of these, and the laptop works under 7.2 without them, so none is treated as needed.
- The third amp client, `CSC3556:00-cs35l56-hda.2`, is I2C address `0x3A`. `_CRS` lists three I2C addresses, but `_DSD` `cirrus,dev-index` names only `0x30` and `0x31`, and the ALC285 driver reports "Found 2 CSC3556". So `0x3A` is not an amp; its staying unbound is expected. The same node has the amp reset GPIO (`0x18`, shared by both amps), a speaker-ID input (`0x68`, which selects `spkid1`) and an interrupt (`0x12`).

### Firmware versions (fwupd)
BIOS `GA403WR.309` (ESRT version 777), CPU microcode `0x0b20401b`, SMU 93.4.0, AGESA `StrixKrackanPI-FP8 1.1.0.0a`, TPM 10.6.0.4, NVMe 61000A60, webcam 1.1.

Secure Boot (disabled during the run): ASUS PK, KEK and db certificates (2023); Microsoft KEK CA 2023, UEFI CA 2023 and Windows UEFI CA 2023 in KEK/db; dbx 20260402. fwupd only reports the 2023 certificates, so whether the 2011 Microsoft CAs are also in db is unknown. That matters for which shim a Secure Boot install image can use.

### Coverage check (2026-10-16, ANAL-175)
Every PCI function in `lspci-nnk.txt` with a bound driver, every USB device in `lsusb.txt`, every bound I2C client and every bound hardware platform device in `platform-devices.txt` is in the table above. Left out are the PCI bridges and data-fabric functions (core kernel), and legacy or software devices: `PCCT` (`PCC=y`), `serial8250` (`SERIAL_8250=y`), `pcspkr` (not enabled), `alarmtimer` and `efivars`.

The only hardware with no driver in the AnyBook kernel is the security processor (`ccp`), the TCO watchdog and the RAPL counters. None of them is needed for bring-up. The dGPU wasn't on the bus in either run, so its driver isn't checked here (`docs/nvidia.md`).

Nothing is left to collect from the owner for this inventory.

## Root run (2026-10-16 13:57)
The owner ran the PR #20 version of `scripts/hw-inventory.sh` (tools installed, root parts through sudo) on the same laptop and kernel (Arch, 7.2.8). Committed in `root/`:
- `dmesg.txt.gz`: 2,818 lines. Redacted here on top of the script's redaction: the hostname (it appeared 10 times, including the DKMS build string), the kernel command line, and 59 firewall (UFW) log lines with local IP addresses.
- `dmidecode.txt` (serial, UUID and asset-tag lines already dropped by the script), `edid-card1-eDP-1.txt` (serial number and date replaced by `edid-decode --replace-unique-ids`), `backlight.txt`, `supergfx.txt`, `vulkaninfo.txt` (device and driver UUIDs redacted).
- `acpi-tables.txt`: the 45 ACPI table headers (signature, length, OEM IDs). MSDM and SLIC were not collected.

**The ACPI tables themselves are not committed.** This repo is public, and the tables are ASUS/AMI firmware. Committing them, about 350 KB raw or 2.2 MB decoded, is the owner's call. They are kept on the build host, outside git, in `~/anybook/hw/ga403wr-20261016-135706/`: the archive as received, plus every table decoded with iasl 20251212.

What the root run showed, beyond the rows marked above:
- **Firmware versions:** `dmidecode`: BIOS `GA403WR.309` (2025-09-17), platform firmware revision 5.35, **EC 3.9**, ASUS part number `90NR0M54-M004R0`. amdgpu: VBIOS `113-STRIXEMU-001`, DMUB `0x09005300`, SMU 93.4.0, DCN 3.5, VCN 4.0.5. The GPU also has an ISP 4.1 camera block, whose optional `amdgpu/isp_4_1_0.bin` isn't in linux-firmware; the webcam is USB UVC, so it doesn't matter.
- **Graphics stack on the laptop:** Mesa 26.2.4 RADV (`STRIX1`), Vulkan 1.4.354.
- **Suspend:** 4 s2idle entry/exit cycles in this boot, with no amd_pmc "didn't reach deepest state" messages.
- **One amdgpu warning:** `WARNING` at `dc_dmub_srv.c:1710` in `dc_dmub_srv_apply_idle_power_optimizations`, once, after about 23.5 h uptime. That is DCN 3.5's idle power path, worth watching on our 6.18.
- **Firmware bugs, harmless on 7.2:** a duplicate `\_SB.PCI0.GPP5.WLAN._S0W` (`AE_ALREADY_EXISTS`; it also made iasl's SSDT-resolved DSDT pass fail, fixed in the script), and a WMI block `WQ00` with no query method.
