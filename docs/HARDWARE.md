# Hardware

## Dev and build host (confirmed 2026-10-15)

| Item | Value |
|---|---|
| CPU | AMD Ryzen 9 7950X, Zen 4, 16C/32T. Has AVX-512, AVX512-VNNI, GFNI, VAES, SHA-NI. **No AVX-VNNI (VEX)** |
| iGPU | AMD Raphael, Radeon 610M (RDNA2, 2 CU) |
| dGPU | NVIDIA RTX 4090 (AD102) |
| RAM | 61 GiB plus 123 GiB swap |
| Disk | 1.7 TB free |
| Wi-Fi | Intel AX210 |
| OS | Arch Linux (Omarchy), kernel 7.2.8 bore. KVM (AMD-V, AVIC) usable without sudo; Docker 29 |

## Target device: ASUS ROG Zephyrus G14 (2025)

The owner named this laptop on 2026-10-15 and described it as a "2025 G14 with the AMD 370 and an RTX 5070". The owner confirmed the Ryzen AI 9 HX 370 (Zen 5) on 2026-10-16.

**The inventory from the laptop (2026-10-16) shows board `GA403WR`, not GA403WP** (BIOS `GA403WR.309`). Evidence and a component-by-component table are in `evidence/2026-10-16-ga403wr-inventory/SUMMARY.md`. ASUS sells the GA403WR with an RTX 5070 Ti Laptop GPU. That part is **R**: the dGPU was powered off during the inventory and is not in the PCI list.

Labels: C = confirmed (inventory from the laptop, kernel source, or linux-firmware contents), R = reported (ASUS, reviews or community), U = unknown.

| Component | Part | Linux driver | Firmware | Label |
|---|---|---|---|---|
| CPU | Ryzen AI 9 HX 370: 4× Zen 5 + 8× Zen 5c, 24 threads; AVX-VNNI and AVX-512 (incl. VNNI, BF16) present | amd-pstate | — | C (inventory) |
| RAM | 32 GB | — | — | C |
| iGPU | Radeon 890M, RDNA 3.5, gfx1150, `1002:150e` rev c1 | amdgpu, Mesa radeonsi/RADV | `amdgpu/gc_11_5_0*`, `dcn_3_5*`, `psp_14_0_0*`, `sdma_6_1_0`, `vcn_4_0_5` | C |
| dGPU | RTX 5070 Ti Laptop (GA403WR SKU) | nouveau / NVK later | `nvidia/gb20x` | R. Not on the PCI bus during the inventory. **Kept off in the first bring-up** |
| Display | 14" 2880×1800 eDP, 120 Hz OLED | amdgpu DC (PSR/Panel Replay quirks are possible) | — | C resolution, R panel model |
| Graphics switching | MUX + NVIDIA Advanced Optimus; inventory: `gpu_mux_mode=1` (Optimus), `dgpu_disable=0` | asus-wmi `dgpu_disable`/`gpu_mux_mode` (6.18), asus-armoury (6.19+) | — | C |
| Backlight | `nvidia_wmi_ec_backlight` loads on the laptop | nvidia-wmi-ec-backlight or amdgpu, chosen by `acpi/video_detect.c` | — | U which one is active (needs `ls /sys/class/backlight`) |
| NPU | XDNA 2, `1022:17f0` rev 10 | amdxdna | `amdnpu/17f0_10/*` | C |
| Wi-Fi / BT | MediaTek MT7925 `14c3:7925`; BT `0489:e11e` on USB | mt7925e, btusb + btmtk | `mediatek/mt7925/*` | C |
| Audio | Realtek ALC285, codec SSID **1043:1024**, plus 2× Cirrus CS35L56 on I2C (`CSC3556`) | snd-hda-intel with quirk `ALC285_FIXUP_ASUS_GA403U_HEADSET_MIC` (mainline cbd46cbc5470, backported to AnyBook's 6.18), cs35l56-hda-i2c, serial-multi-instantiate | `cirrus/cs35l56-b0-dsp1-misc-10431024-*` | C hardware and quirk. **No tuning file for 10431024 in linux-firmware** (2026-10-16). Headset mic broken upstream (R) |
| Internal mic | On the HDA codec: `ALC285 Analog` is the only capture device. ACP 7.0 (`1022:15e2` rev 70) binds `snd_acp_pci` but registers no capture PCM | snd-hda-intel | — | C (inventory) |
| Touchpad | ELAN `ASCE1206:00 04F3:3315`, I2C HID on AMDI0010 | i2c-hid-acpi, i2c-designware, pinctrl-amd, hid-multitouch | — | C |
| Keyboard | ASUS N-KEY `0b05:19b6` | hid-asus, asus-wmi | — | C |
| Webcam | `3277:0060` FHD UVC | uvcvideo | — | C |
| Card reader | Realtek RTS525A `10ec:525a` | rtsx_pci, rtsx_pci_sdmmc | — | C |
| Storage | SK hynix PVC10 NVMe | nvme | — | C |
| Ports | USB4 router `1022:151c`, UCSI (`USBC000`), USB-C 3.2, 2× USB-A, HDMI 2.1 | thunderbolt, ucsi_acpi | — | C USB4/UCSI, C spec rest |
| Power | `AMDI000A` amd_pmc, `AMDI0103` amd-pmf, `AMDI0104` amd_hfi; s2idle only; battery A32-K55 | amd_pmc, amd-pmf, amd_hfi, battery, ac | — | C |
| Security | TPM2 `MSFT0101` (fTPM/Pluton), Secure Boot disabled, UEFI 2.90 | tpm_crb | — | C |

### Collecting the inventory (read-only)
Run this on the laptop from its installed Linux or a live USB. It changes nothing on the machine:
```bash
git clone https://github.com/Mhsbrian/OpenBook && cd OpenBook
scripts/hw-inventory.sh               # no root needed
scripts/hw-inventory.sh --with-root   # optional: adds dmesg, dmidecode, ACPI tables minus MSDM/SLIC (sudo)
```
It writes `anybook-hw-<board>-<date>.tar.gz`, with serials, UUIDs and MAC addresses redacted. Attach that file to ANAL-175.

### Bring-up notes and risks
1. **Run Android on the Radeon 890M.** Keep the MUX in hybrid (iGPU) mode and power the dGPU down with `dgpu_disable` from Linux before booting AnyBook. In dGPU-only MUX mode the internal panel is wired to the NVIDIA GPU, which Android cannot drive yet.
2. **AVX-VNNI.** The CPU is the HX 370 (Zen 5), so Google's Panther Lake-tuned binaries meet their ISA baseline (PLAN §3.4). The Zen 4 risk applies only to the dev host.
3. **Audio needs several pieces:** the HDA Realtek codec with the 1043:1024 quirk, and the cs35l56 amplifiers. The internal mic is on the HDA codec. The amps' Cirrus tuning file for 10431024 is not in linux-firmware, so the speakers may run uncalibrated (quiet) until Cirrus/ASUS publish it.
4. **Fan and power tuning:** mainline `asus-armoury` has a power-limit table for the GA403WR (6.19+). The 6.18 kernel has the older `asus-wmi` `ppt_*` attributes.
5. **Suspend and panel power saving:** Strix Point s2idle and OLED PSR/Replay are untested on this model.
6. **Safety:** first bring-up boots from USB only. Nothing on the internal NVMe or the firmware gets flashed, repartitioned or wiped without explicit confirmation that names the device.

## Other candidate devices
- Zen 4 laptops (Ryzen 7040/8040, Radeon 780M), as a secondary target.
- Desktop iGPUs, such as this host's Radeon 610M, for early bring-up only.

## Enablement checklist: G14 2025

| Area | Kernel / driver | Userspace | Status |
|---|---|---|---|
| GPU | amdgpu, linux-firmware `amdgpu/*` | Mesa radeonsi/RADV, minigbm, drm_hwcomposer, ANGLE | Kernel module and firmware list built, loads in a VM (ANAL-171); untested on hardware |
| CPU power | amd-pstate (EPP) | power HAL | Built into the stock kernel (`X86_AMD_PSTATE=y`) |
| Suspend | amd_pmc (s2idle) | system_suspend | Module built (ANAL-171); untested |
| Touchpad / touch | i2c-hid-acpi, pinctrl-amd, hid-multitouch | — | `PINCTRL_AMD=y` and `X86_AMD_PLATFORM_DEVICE=y` in AnyBook GKI, i2c-designware/i2c-hid-acpi modules (ANAL-171); untested |
| Audio | snd-hda-intel (ALC285, SSID 1043:1024 quirk backported), cs35l56-hda-i2c; internal mic on HDA | audio HAL | Modules built (ANAL-171); CS35L56 tuning file for 10431024 not in linux-firmware |
| Wi-Fi / BT | mt7925e, btmtk | wifi HAL | Modules and firmware list built (ANAL-171); untested |
| NPU | amdxdna (XDNA 2) | — | Module built (ANAL-171); userspace later |
| dGPU | nouveau / NVK (RTX 5070 Laptop) | — | Later; kept off with `dgpu_disable` |
| Platform | asus-wmi, asus-armoury, hid-asus | — | asus-wmi/hid-asus built (ANAL-171). 6.18 asus-wmi has `dgpu_disable` and `gpu_mux_mode`; asus-armoury (6.19) not needed for bring-up |
| IOMMU | amd_iommu | — | `AMD_IOMMU=y` in AnyBook GKI; starts with interrupt remapping on QEMU's emulated AMD-Vi (ANAL-171) |
| Boot | UEFI, GPT; EFI loader with bootconfig | AVB orange | QEMU direct-kernel boot works |
