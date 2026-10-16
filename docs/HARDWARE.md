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

**The inventory from the laptop (2026-10-16) shows board `GA403WR`, not GA403WP** (BIOS `GA403WR.309`). Evidence and a component-by-component table are in `evidence/2026-10-16-ga403wr-inventory/SUMMARY.md`. ASUS sells the GA403WR with an RTX 5070 Ti Laptop GPU (12 GB, 110 W; ASUS G14 2025 spec page, checked 2026-10-16 in ANAL-187), which is GB205 (R). The RTX 5070 Laptop (GB206) is the GA403WP/GA403UP. The dGPU was absent from the PCI list during the inventory, so its exact ID is unconfirmed.

Labels: C = confirmed (inventory from the laptop, kernel source, or linux-firmware contents), R = reported (ASUS, reviews or community), U = unknown.

| Component | Part | Linux driver | Firmware | Label |
|---|---|---|---|---|
| CPU | Ryzen AI 9 HX 370: 4× Zen 5 + 8× Zen 5c, 24 threads; AVX-VNNI and AVX-512 (incl. VNNI, BF16) present | amd-pstate | — | C (inventory) |
| RAM | 32 GB LPDDR5(X) at 8000 MT/s, 4× 8 GiB Samsung `K3KL9L90DM-MGCU` (dmidecode) | — | — | C |
| iGPU | Radeon 890M, RDNA 3.5, gfx1150, `1002:150e` rev c1 | amdgpu, Mesa radeonsi/RADV | `amdgpu/gc_11_5_0*`, `dcn_3_5*`, `psp_14_0_0*`, `sdma_6_1_0`, `vcn_4_0_5` | C |
| dGPU | RTX 5070 Ti Laptop: GB205M `10de:2f58`, HDMI audio `10de:2f80`, at `64:00.0` behind `00:03.1`, PCIe 4.0 x8 | nouveau (GB20x since 6.16, in our 6.18 tree) / NVK later | `nvidia/gb202/gsp/*-570.144` (`gb205`/`gb206` link to it) | C (`dmesg` of the root run). Present at boot; at collection time supergfxctl reported `Integrated` with the dGPU `off`, which is why `lspci` never showed it. **Kept off in the first bring-up** (`docs/nvidia.md`) |
| Display | 14" 2880×1800 OLED, Samsung `ATNA40CU05-0` (EDID `SDC` product 16796): 48–120 Hz adaptive sync, HDR static metadata, max 617 cd/m² | amdgpu DC. On 7.2 amdgpu leaves PSR off for this panel (`PSR support 0`; sink PSR version 1) | — | C (EDID) |
| Graphics switching | MUX + NVIDIA Advanced Optimus; inventory: `gpu_mux_mode=1` (Optimus), `dgpu_disable=0` | asus-wmi `dgpu_disable`/`gpu_mux_mode` (6.18), asus-armoury (6.19+) | — | C |
| Backlight | `amdgpu_bl1` (raw, max 400000) on `card1-eDP-1` in Optimus/Integrated mode. `nvidia_wmi_ec_backlight` loads but registers no device | amdgpu | — | C. A dGPU-only MUX mode would likely switch to nvidia-wmi-ec-backlight (hypothesis) |
| NPU | XDNA 2, `1022:17f0` rev 10 | amdxdna | `amdnpu/17f0_10/*` | C |
| Wi-Fi / BT | MediaTek MT7925 `14c3:7925`; BT `0489:e11e` on USB | mt7925e, btusb + btmtk | `mediatek/mt7925/*` | C |
| Audio | Realtek ALC285, codec SSID **1043:1024**, plus 2× Cirrus CS35L56 on I2C (`CSC3556`) | snd-hda-intel with quirk `ALC285_FIXUP_ASUS_GA403U_HEADSET_MIC` (mainline cbd46cbc5470, backported to AnyBook's 6.18), cs35l56-hda-i2c, serial-multi-instantiate | `cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1{.wmfw,-amp1.bin,-amp2.bin}`: WHENCE links to the 10431044 tuning and `CS35L56_Rev3.11.16.wmfw` | C. The laptop loads the spkid1 set (`dmesg`); an earlier note here that linux-firmware lacked it was wrong. Headset mic broken upstream (R) |
| Internal mic | On the HDA codec: `ALC285 Analog` is the only capture device. ACP 7.0 (`1022:15e2` rev 70) binds `snd_acp_pci` but registers no capture PCM | snd-hda-intel | — | C (inventory) |
| Touchpad | ELAN `ASCE1206:00 04F3:3315`, I2C HID on AMDI0010 | i2c-hid-acpi, i2c-designware, pinctrl-amd, hid-multitouch | — | C |
| Keyboard | ASUS N-KEY `0b05:19b6` | hid-asus, asus-wmi | — | C |
| Webcam | `3277:0060` FHD UVC | uvcvideo | — | C |
| Card reader | Realtek RTS525A `10ec:525a` | rtsx_pci, rtsx_pci_sdmmc | — | C |
| Storage | SK hynix PVC10 NVMe | nvme | — | C |
| Ports | USB4 router `1022:151c`, UCSI (`USBC000`), USB-C 3.2, 2× USB-A, HDMI 2.1 | thunderbolt, ucsi_acpi | — | C USB4/UCSI, C spec rest. **HDMI is probably on the dGPU:** amdgpu exposes eDP and 8 DP connectors but no HDMI-A (`drm-connectors.txt`), so with the dGPU off, external displays go through USB-C |
| Power | `AMDI000A` amd_pmc, `AMDI0103` amd-pmf, `AMDI0104` amd_hfi; s2idle only; battery A32-K55 | amd_pmc, amd-pmf, amd_hfi, battery, ac | — | C |
| Security | TPM2 `MSFT0101` (Pluton, firmware 10.6.0.4), Secure Boot disabled, UEFI 2.90. db/KEK hold the Microsoft 2023 CAs (UEFI CA, Windows UEFI CA, KEK CA) and ASUS 2023 keys; dbx 20260402 | tpm_crb | — | C. Whether the 2011 Microsoft CAs are also in db is U |

### Collecting the inventory
Run this on the laptop, as your normal user, from its installed Linux or a live USB:
```bash
git clone https://github.com/Mhsbrian/OpenBook && cd OpenBook
scripts/hw-inventory.sh               # installs the tools, then collects everything (asks for your sudo password)
scripts/hw-inventory.sh --no-install  # same, with the tools already installed
scripts/hw-inventory.sh --no-root     # no sudo: no dmesg, dmidecode or ACPI tables, no install
```
By default it installs read-only diagnostic tools with pacman, apt-get or dnf: pciutils, usbutils, alsa-utils, iw, dmidecode, vulkan-tools, mesa-utils, edid-decode (`v4l-utils` on Arch), acpica (`iasl`) and fwupd. A package that fails to install is skipped. Apart from those packages it changes nothing on the machine. Through sudo it reads `dmesg`, `dmidecode` and the ACPI tables, minus MSDM/SLIC, which hold the Windows product key. It also decodes the tables to `.dsl` with `iasl`.

It writes `anybook-hw-<board>-<date>.tar.gz`, with serials, UUIDs and MAC addresses redacted, and the panel EDID with its serial number and date replaced. Attach that file to ANAL-175.

### Bring-up notes and risks
1. **Run Android on the Radeon 890M.** Keep the MUX in hybrid (iGPU) mode and power the dGPU down with `dgpu_disable=1` from Linux before booting AnyBook. In dGPU-only MUX mode the internal panel is wired to the NVIDIA GPU, which Android cannot drive yet.
   - With `dgpu_disable=0`, the dGPU will most likely stay in D0 for the whole OpenBook session: no driver binds it, and `snd_hda_intel` holds its HDMI-audio function awake.
   - `scripts/dgpu-power-check.sh` verifies the state on Linux and on OpenBook (`docs/nvidia.md` §1).
2. **AVX-VNNI.** The CPU is the HX 370 (Zen 5), so Google's Panther Lake-tuned binaries meet their ISA baseline (PLAN §3.4). The Zen 4 risk applies only to the dev host.
3. **Audio needs several pieces:** the HDA Realtek codec with the 1043:1024 quirk, and the cs35l56 amplifiers. The internal mic is on the HDA codec. linux-firmware has the amps' tuning for 10431024 as links to the 10431044 files; the speaker-ID GPIO selects the spkid1 set on this unit.
4. **Fan and power tuning:** mainline `asus-armoury` has a power-limit table for the GA403WR (6.19+). The 6.18 kernel has the older `asus-wmi` `ppt_*` attributes.
5. **Suspend and panel power saving:** on the laptop's own Linux 7.2, 4 s2idle cycles completed with no amd_pmc errors, and amdgpu kept PSR off for the panel. One `WARNING` in `dc_dmub_srv_apply_idle_power_optimizations` (`dc_dmub_srv.c:1710`) appeared after about 23 hours. All of this is untested on our 6.18; if the display hangs on idle there, turning off DCN idle power states is the first thing to try (hypothesis).
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
| Audio | snd-hda-intel (ALC285, SSID 1043:1024 quirk backported), cs35l56-hda-i2c; internal mic on HDA | audio HAL | Modules built (ANAL-171); CS35L56 tuning for 10431024 added to the firmware list (ANAL-175) |
| Wi-Fi / BT | mt7925e, btmtk | wifi HAL | Modules and firmware list built (ANAL-171); untested |
| NPU | amdxdna (XDNA 2) | — | Module built (ANAL-171); userspace later |
| dGPU | nouveau / NVK (RTX 50 Laptop, GB20x) | — | Later: research track N1–N6 in `docs/nvidia.md`. Kept off with `dgpu_disable=1` (ANAL-176 default) |
| Platform | asus-wmi, asus-armoury, hid-asus | — | asus-wmi/hid-asus built (ANAL-171). 6.18 asus-wmi has `dgpu_disable` and `gpu_mux_mode`; asus-armoury (6.19) not needed for bring-up |
| IOMMU | amd_iommu | — | `AMD_IOMMU=y` in AnyBook GKI; starts with interrupt remapping on QEMU's emulated AMD-Vi (ANAL-171) |
| Boot | UEFI, GPT; EFI loader with bootconfig | AVB orange | systemd-boot, GRUB and GBL boot our kernel and userspace from a USB GPT image in QEMU/OVMF (ANAL-189, `docs/installer.md`); untested on the G14 |
