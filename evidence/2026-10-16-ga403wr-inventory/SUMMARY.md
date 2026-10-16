# GA403WR hardware inventory (2026-10-16)

The owner ran `scripts/hw-inventory.sh` on the laptop without `--with-root`, so there is no `dmesg`, `dmidecode` or ACPI table dump. It ran under Arch (Omarchy), kernel 7.2.8. The files in this directory come from that archive with serials, UUIDs and MAC addresses already redacted by the script. The hostname, kernel command line and OS details are left out. `fwupd.txt` has colour codes and fwupd's per-device ID hashes removed. `cpuinfo-cpu0.txt` is the first CPU's entry from `/proc/cpuinfo`.

**The board is `GA403WR`** (`dmi.txt`, BIOS `GA403WR.309`, 2025-09-17). `docs/HARDWARE.md` had assumed GA403WP.

| Component | What the inventory shows | Driver on the laptop (7.2) | AnyBook 6.18 kernel (ANAL-171) |
|---|---|---|---|
| CPU | AMD Ryzen AI 9 HX 370 w/ Radeon 890M, 24 threads; `avx_vnni`, `avx512f`, `avx512_vnni`, `avx512_bf16` all present | amd-pstate | `X86_AMD_PSTATE=y` (GKI) |
| RAM | 32 GB (`MemTotal` 31,934,248 kB) | — | — |
| iGPU | `1002:150e` rev c1, Strix [Radeon 880M/890M]; eDP 2880×1800 connected | amdgpu | `amdgpu.ko` + `gc_11_5_0`, `dcn_3_5`, `psp_14_0_0`, `sdma_6_1_0`, `vcn_4_0_5` firmware |
| Panel | eDP-1, 2880×1800 (`drm-connectors.txt`). fwupd lists it under the GPU with vendor `PNP:SDC` (Samsung Display). No EDID: the script's `[ -s edid ]` test is always false on sysfs (fixed in ANAL-175's follow-up PR) | amdgpu DC | `amdgpu.ko`; no panel firmware. Product code unknown until an EDID is captured |
| Touchscreen | None. `input-devices.txt` has no touchscreen and no I2C HID device besides the touchpad | — | — |
| dGPU | **Not on the PCI bus during the run.** The GPP bridge 00:03.1 has no device behind it; nvidia-smi found no driver. ASUS reports `dgpu_disable=0`, `gpu_mux_mode=1` (Optimus), `nv_base_tgp=80` | none | Kept off by design |
| NPU | `1022:17f0` rev 10 | amdxdna | `amdxdna.ko` + `amdnpu/17f0_10` |
| Wi-Fi | MediaTek MT7925 `14c3:7925` | mt7925e | `mt7925e.ko` + `mediatek/mt7925/*` |
| Bluetooth | `0489:e11e` (Foxconn MT7925 BT) over USB | btusb + btmtk | `btusb.ko`; 0489:e11e is in the 6.18 MT7925 table |
| Audio codec | Realtek **ALC285**, codec SSID **1043:1024** (`codec-card2-alc285.txt`). lspci's "ALC245" is a BIOS label | snd_hda_intel | Quirk backported from mainline cbd46cbc5470 (`kernel/patches/common/0002-*`) |
| Speaker amps | 2× Cirrus CS35L56 on I2C (`CSC3556:00-cs35l56-hda.0/.1`) | serial-multi-instantiate + cs35l56-hda | built; **linux-firmware has no `cs35l56-b0-dsp1-misc-10431024*` tuning file** |
| Capture | Only `ALC285 Analog` (HDA) is a capture device. ACP 7.0 (`1022:15e2` rev 70) is bound by `snd_acp_pci` but registers no capture PCM | snd_hda_intel | The internal mic is on the HDA codec, not an ACP DMIC. ACP modules are still built |
| HDMI/DP audio | `1002:1640`, ATI R6xx HDMI codec | snd_hda_intel | `snd-hda-codec-atihdmi.ko` |
| Touchpad | ELAN `ASCE1206:00 04F3:3315` (PNP0C50) on the DesignWare I2C controller (4× AMDI0010) | i2c_hid_acpi + hid-multitouch | `i2c-hid-acpi.ko`, `i2c-designware-*.ko`, `PINCTRL_AMD=y`, `X86_AMD_PLATFORM_DEVICE=y` |
| Keyboard | `0b05:19b6` "ITE Device(8910)" | hid-asus | `hid-asus.ko` (ROG N-KEY 2 ID is in 6.18) |
| Hotkeys, platform | `asus-nb-wmi`; asus-armoury attributes present | asus_wmi, asus_nb_wmi, asus_armoury | asus-wmi/asus-nb-wmi built (have `dgpu_disable`, `gpu_mux_mode`, `ppt_*`). asus-armoury is 6.19+; mainline has a GA403WR power table |
| Backlight | `nvidia_wmi_ec_backlight` is loaded on the laptop (which backlight device is active is unknown without `ls /sys/class/backlight`) | nvidia_wmi_ec_backlight and/or amdgpu | `nvidia-wmi-ec-backlight.ko` added, because the 6.18 built-in `video_detect.c` picks it when the EC owns brightness |
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
- `AMDI0060` and `AMDI0016` (4×) have `_STA` 0: the firmware disables them.
- `AMDI0052` is present. In 6.18 it is the ACP 6.3 machine-match ID (`sound/soc/amd/acp/amd-acpi-mach.c`); the ACP 7.0 table matches `AMDI0029`, which this laptop doesn't expose. That fits ACP registering no capture PCM.
- `ASUS2018`, `ASUS9001`, `NVDA0820`, `MSFT0201` and `DRTM0001` are present, and no 6.18 or 7.2 driver binds them. The laptop works under 7.2 without them, so for now none is treated as needed. Hypothesis: `NVDA0820` is NVIDIA's platform controller interface, and `DRTM0001` is Windows' dynamic root of trust.
- A third amp client, `CSC3556:00-cs35l56-hda.2`, is created from ACPI but stays unbound while `.0` and `.1` bind. Hypothesis: the ACPI node lists a third I2C address with no amp behind it. `dmesg` would confirm it.

### Firmware versions (fwupd)
BIOS `GA403WR.309` (ESRT version 777), CPU microcode `0x0b20401b`, SMU 93.4.0, AGESA `StrixKrackanPI-FP8 1.1.0.0a`, TPM 10.6.0.4, NVMe 61000A60, webcam 1.1.

Secure Boot (disabled during the run): ASUS PK, KEK and db certificates (2023); Microsoft KEK CA 2023, UEFI CA 2023 and Windows UEFI CA 2023 in KEK/db; dbx 20260402. fwupd only reports the 2023 certificates, so whether the 2011 Microsoft CAs are also in db is unknown. That matters for which shim a Secure Boot install image can use.

### Coverage check (2026-10-16, ANAL-175)
Every PCI function in `lspci-nnk.txt` with a bound driver, every USB device in `lsusb.txt`, every bound I2C client and every bound hardware platform device in `platform-devices.txt` is in the table above. Left out are the PCI bridges and data-fabric functions (core kernel), and legacy or software devices: `PCCT` (`PCC=y`), `serial8250` (`SERIAL_8250=y`), `pcspkr` (not enabled), `alarmtimer` and `efivars`.

The only hardware with no driver in the AnyBook kernel is the security processor (`ccp`), the TCO watchdog and the RAPL counters. None of them is needed for bring-up. The dGPU wasn't on the bus, so it isn't checked.

Still to collect from the owner (`scripts/hw-inventory.sh --with-root`; the fixed script also captures the EDID without root):
- `dmesg`: CS35L56 firmware messages, amdgpu, s2idle and the backlight choice.
- `dmidecode`, and the ACPI tables minus MSDM/SLIC, for a decoded DSDT/SSDT.
- The panel EDID, for the product code. Install `v4l-utils` for `edid-decode`.
- `ls /sys/class/backlight`.
- `lspci -nn` with the dGPU powered, for the NVIDIA device ID.
