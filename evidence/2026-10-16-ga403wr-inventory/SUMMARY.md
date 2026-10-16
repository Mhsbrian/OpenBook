# GA403WR hardware inventory (2026-10-16)

The owner ran `scripts/hw-inventory.sh` on the laptop without `--with-root`, so there is no `dmesg`, `dmidecode` or ACPI table dump. It ran under Arch (Omarchy), kernel 7.2.8. The files in this directory come from that archive with serials, UUIDs and MAC addresses already redacted by the script. The hostname, kernel command line and OS details are left out.

**The board is `GA403WR`** (`dmi.txt`, BIOS `GA403WR.309`, 2025-09-17). `docs/HARDWARE.md` had assumed GA403WP.

| Component | What the inventory shows | Driver on the laptop (7.2) | AnyBook 6.18 kernel (ANAL-171) |
|---|---|---|---|
| CPU | AMD Ryzen AI 9 HX 370 w/ Radeon 890M, 24 threads; `avx_vnni`, `avx512f`, `avx512_vnni`, `avx512_bf16` all present | amd-pstate | `X86_AMD_PSTATE=y` (GKI) |
| RAM | 32 GB (`MemTotal` 31,934,248 kB) | — | — |
| iGPU | `1002:150e` rev c1, Strix [Radeon 880M/890M]; eDP 2880×1800 connected | amdgpu | `amdgpu.ko` + `gc_11_5_0`, `dcn_3_5`, `psp_14_0_0`, `sdma_6_1_0`, `vcn_4_0_5` firmware |
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
| NVMe | SK hynix PVC10 `1c5c:1f69` | nvme | `BLK_DEV_NVME=y` (GKI) |
| USB4 | `1022:151c` USB4 Router | thunderbolt | `thunderbolt.ko` (GKI module) |
| USB-C | `USBC000` (UCSI), 2 source power supplies | ucsi_acpi | `ucsi_acpi.ko` |
| Power | `AMDI000A` (amd_pmc), `AMDI0103` (amd-pmf), `AMDI0104` (amd_hfi); `mem_sleep` = `[s2idle]` only; battery `BAT1` A32-K55, `ACAD` | amd_pmc, amd-pmf, amd_hfi, battery, ac | amd-pmc, battery, ac built. amd-pmf blocked (`symbols.deny`). `AMD_HFI` is bool (would be a fourth built-in), not enabled |
| TPM | `MSFT0101` + TPM2 ACPI table | tpm_crb_acpi | `tpm_crb.ko` |
| IOMMU | `1022:1508`, IVRS table present | amd_iommu | `AMD_IOMMU=y` |
| Boot | UEFI 2.90 (AMI), Secure Boot disabled, Limine boot loader, TPM2 available | — | — |

Not identified: `AMDI0060`, `AMDI0016` (4×), `ASUS2018`, `ASUS9001`, `NVDA0820`, `MSFT0201`. No 6.18 or 7.2 driver binds to them in this run.

Still useful from a `--with-root` run: `dmesg` (for CS35L56 firmware messages, amdgpu, s2idle and backlight choice) and `ls /sys/class/backlight`. An `lspci -nn` with the dGPU powered would give the NVIDIA device ID.
