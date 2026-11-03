# Hardware

The hardware OpenBook targets, the driver and firmware for each component, and how far each one works. The first
target is the ASUS ROG Zephyrus G14 (2025). The topic docs linked from the tables have the details.

## Target device: ASUS ROG Zephyrus G14 (2025)

- **Board `GA403WR`** (BIOS `GA403WR.309`), not GA403WP: Ryzen AI 9 HX 370 (Zen 5), Radeon 890M, and the RTX 5070 Ti
  Laptop GPU (GB205, 12 GB, 110 W; ASUS G14 2025 spec page, checked 2026-10-16 in ANAL-187). The RTX 5070 Laptop
  (GB206) is the GA403WP/GA403UP.
- The facts below come from the laptop's own inventory (2026-10-16), its kernel logs and our G14 sessions.

Labels: C = confirmed (inventory from the laptop, kernel source, or linux-firmware contents), R = reported (ASUS,
reviews or community), U = unknown.

| Component | Part | Linux driver | Firmware | Label |
|---|---|---|---|---|
| CPU | Ryzen AI 9 HX 370: 4× Zen 5 + 8× Zen 5c, 24 threads; AVX-VNNI and AVX-512 (incl. VNNI, BF16) present | amd-pstate | — | C (inventory) |
| RAM | 32 GB LPDDR5(X) at 8000 MT/s, 4× 8 GiB Samsung `K3KL9L90DM-MGCU` (dmidecode) | — | — | C |
| iGPU | Radeon 890M, RDNA 3.5, gfx1150, `1002:150e` rev c1 | amdgpu, Mesa radeonsi/RADV | `amdgpu/gc_11_5_0*`, `dcn_3_5*`, `psp_14_0_0*`, `sdma_6_1_0`, `vcn_4_0_5` | C |
| dGPU | RTX 5070 Ti Laptop: GB205M `10de:2f58`, HDMI audio `10de:2f80`, at `64:00.0` behind `00:03.1`, PCIe 4.0 x8 | NVIDIA's open kernel driver 615.78.08, loaded after boot in Hybrid for runtime power management; nouveau (GB20x since 6.16) built but blocklisted (`docs/nvidia-open.md`) | GSP firmware from NVIDIA's 615.78.08 driver package, `/vendor/firmware/nvidia/615.78.08/`; nouveau would use linux-firmware's `nvidia/gb202/gsp/*-570.144` (`gb205`/`gb206` link to it) | C (`dmesg`). Apps cannot use it on OpenBook yet |
| Display | 14" 2880×1800 OLED, Samsung `ATNA40CU05-0` (EDID `SDC` product 16796): 120 Hz (DisplayID, preferred) and 60 Hz (base EDID) timings, 48–120 Hz adaptive sync, HDR static metadata, max 617 cd/m² | amdgpu DC. On Linux 7.2 amdgpu leaves PSR off for this panel (`PSR support 0`; sink PSR version 1). Android scans out and draws at 120 Hz (`docs/graphics-amd.md`, "Refresh rate"). No VRR in drm_hwcomposer yet | — | C (EDID; G14 dumps) |
| Graphics switching | MUX + NVIDIA Advanced Optimus; today Hybrid: `gpu_mux_mode=1` (Optimus), `dgpu_disable=0` | asus-wmi `dgpu_disable`/`gpu_mux_mode` (6.18), asus-armoury (6.19+) | — | C. Modes and their safety rules: `docs/nvidia-graphics-modes.md` |
| Backlight | `amdgpu_bl1` (raw, max 400000) on `card1-eDP-1` in Optimus/Integrated mode on Linux; `amdgpu_bl0` (0–399000) on OpenBook's kernel. `nvidia_wmi_ec_backlight` loads but registers no device | amdgpu | — | C. A dGPU-only MUX mode would likely switch to nvidia-wmi-ec-backlight (hypothesis) |
| NPU | XDNA 2, `1022:17f0` rev 10 | amdxdna | `amdnpu/17f0_10/*` | C |
| Wi-Fi / BT | MediaTek MT7925 `14c3:7925`; BT `0489:e11e` on USB | mt7925e, btusb + btmtk | `mediatek/mt7925/*` (build `20260414`) | C |
| Audio | Realtek ALC285, codec SSID **1043:1024**, plus 2× Cirrus CS35L56 on I2C (`CSC3556`) | snd-hda-intel with quirk `ALC285_FIXUP_ASUS_GA403U_HEADSET_MIC` (mainline cbd46cbc5470, backported to OpenBook's 6.18), cs35l56-hda-i2c, serial-multi-instantiate | `cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1{.wmfw,-amp1.bin,-amp2.bin}`: WHENCE links to the 10431044 tuning and `CS35L56_Rev3.11.16.wmfw` | C. The laptop loads the spkid1 set (`dmesg`). Headset mic broken upstream (R) |
| Internal mic | On the HDA codec: `ALC285 Analog` is the only capture device. ACP 7.0 (`1022:15e2` rev 70) binds `snd_acp_pci` but registers no capture PCM | snd-hda-intel | — | C (inventory) |
| Touchpad | ELAN `ASCE1206:00 04F3:3315`, I2C HID on AMDI0010: five slots, X 0–3905, Y 0–2382, 31 units/mm, palm tool type, no pressure or contact-size axes | i2c-hid-acpi, i2c-designware, pinctrl-amd, hid-multitouch | — | C |
| Keyboard | ASUS N-KEY `0b05:19b6` | hid-asus, asus-wmi | — | C |
| Webcam | `3277:0060` FHD UVC | uvcvideo | — | C |
| Card reader | Realtek RTS525A `10ec:525a` | rtsx_pci, rtsx_pci_sdmmc | — | C |
| Storage | SK hynix PVC10 NVMe | nvme | — | C |
| Ports | USB4 router `1022:151c`, UCSI (`USBC000`), USB-C 3.2, 2× USB-A, HDMI 2.1 | thunderbolt, ucsi_acpi | — | C USB4/UCSI, C spec rest. **HDMI is on the dGPU:** amdgpu exposes eDP and 8 DP connectors but no HDMI-A, so without the dGPU's display, external displays go through USB-C |
| Power | `AMDI000A` amd_pmc, `AMDI0103` amd-pmf, `AMDI0104` amd_hfi; s2idle only; battery A32-K55, about 65 Wh at full charge (4.063 of 4.580 Ah design, as of 2026-10-17) | amd_pmc, amd-pmf, amd_hfi, battery, ac | — | C |
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

It writes `anybook-hw-<board>-<date>.tar.gz`, with serials, UUIDs and MAC addresses redacted, and the panel EDID with its serial number and date replaced. Attach that file to the device's hardware issue (ANAL-175 for the G14).

### Bring-up notes and risks
1. **Android runs on the Radeon 890M.** Keep the MUX in Hybrid (iGPU) mode. In dGPU-only MUX mode the internal panel is wired to the NVIDIA GPU, which OpenBook cannot drive yet.
   - With no driver bound, the dGPU stays in D0 for the whole session: the PCI core keeps an unbound device in D0, and `snd_hda_intel` holds its HDMI-audio function awake (`docs/nvidia.md` §1).
   - OpenBook powers it down two ways: NVIDIA's open driver takes it to runtime D3cold in Hybrid (`docs/nvidia-open.md`); without the driver, the early-boot `dgpu-pm` hook lets the unbound GPU reach D3cold. `dgpu_disable=1` (Eco) removes it entirely, but darkens HDMI.
   - `scripts/dgpu-power-check.sh` verifies the state on Linux and on OpenBook.
2. **AVX-VNNI.** The CPU is the HX 370 (Zen 5), so Google's Panther Lake-tuned binaries meet their ISA baseline (`docs/PLAN.md` §3, "CPU ISA"). The Zen 4 risk applies only to a Zen 4 build host.
3. **Audio needs several pieces:** the HDA Realtek codec with the 1043:1024 quirk, and the cs35l56 amplifiers. The internal mic is on the HDA codec. linux-firmware has the amps' tuning for 10431024 as links to the 10431044 files; the speaker-ID GPIO selects the spkid1 set on this unit. The codec's ALSA card number changes with the dGPU's presence (`docs/g14-audio-net.md` §2).
4. **Fan and power tuning:** mainline `asus-armoury` has a power-limit table for the GA403WR (6.19+). The 6.18 kernel has the older `asus-wmi` `ppt_*` attributes.
5. **Panel power saving on Linux 7.2** (as of 2026-10-16): 4 s2idle cycles completed with no amd_pmc errors, and amdgpu kept PSR off for the panel. One `WARNING` in `dc_dmub_srv_apply_idle_power_optimizations` (`dc_dmub_srv.c:1710`) appeared after about 23 hours. If the display hangs on idle on our 6.18, turning off DCN idle power states is the first thing to try (hypothesis).
6. **Safety:** nothing on the internal NVMe or the firmware gets flashed, repartitioned or wiped without explicit confirmation that names the device.
7. **No USB device mode.** `/sys/class/udc` is empty and all USB controllers are xHCI hosts; the USB4 router (`67:00.5`) has no driver in our kernel. adb therefore runs over IP only (tcp:5555, Wireless debugging); a USB cable to the build host carries nothing. A USB-Ethernet adapter would need the GKI's `r8152`/`ax88179_178a`/`cdc_ether` modules loaded at boot (they ship in `system_dlkm` but are not loaded). See `docs/adb-debug.md` (ANAL-222).

## Enablement checklist: G14 2025

"On the G14" means shown on the laptop with logs. The dates are in each row's topic doc.

| Area | Kernel / driver | Userspace | Status |
|---|---|---|---|
| GPU | amdgpu, linux-firmware `amdgpu/*` | Mesa radeonsi/RADV (Vulkan 1.4), minigbm, drm_hwcomposer, ANGLE | **On the G14:** amdgpu binds the 890M; SMU, DCN 3.5 and DMUB firmware load; the desktop runs on the panel through ANGLE on RADV, minigbm and drm_hwcomposer at 120 Hz. dEQP and ANGLE end2end ran on the 890M. Known gaps: AHardwareBuffer rendering in RADV, and a GPU hang means a full GPU reset (no per-queue reset on GC 11.5 with our firmware). YV12 buffers needed a RADV format mapping (Mesa patch 0005; a driver defect, not a hardware fault). `docs/graphics-amd.md` |
| CPU power | amd-pstate (EPP) | power HAL | Built into the kernel (`X86_AMD_PSTATE=y`). **On the G14:** `amd-pstate-epp`, status active, max 5.16 GHz; the power HAL's EPP hints work. `docs/power-input.md` |
| Suspend | amd_pmc (s2idle) | system_suspend | **On the G14:** s2idle works under Android (screen timeout or lid, then wake by key, touch or lid), but **S0i3 is never reached**. The dGPU, `\_SB_.PCI0.GPP0.SWUS` and the driverless PSP are ruled out; the SMU points at MPM or the USB4 routers (hypothesis). The laptop's own Linux 7.2 shows no S0i3 failure. `docs/power-input.md` §1 |
| Touchpad / touch | i2c-hid-acpi, pinctrl-amd, hid-multitouch | gestures library (`TouchpadInputMapper`) | `PINCTRL_AMD=y` and `X86_AMD_PLATFORM_DEVICE=y` in OpenBook GKI. **On the G14:** the ELAN touchpad registers as Touchpad + Mouse input devices, and the gestures library drives it. Its descriptor's vendor page `0xFF01` makes hid-input set `EV_REP`, so the kernel autorepeats `BTN_TOOL_FINGER`; Android turns that off (EventHub patch, `docs/power-input.md` §2). Tap dragging is on; a reported tap-drag/scroll failure is not yet reproduced (`docs/touchpad-behavior.md`) |
| Audio | snd-hda-intel (ALC285, SSID 1043:1024 quirk backported), cs35l56-hda-i2c; internal mic on HDA | AOSP's AIDL example HAL, primary module on the codec's card (OpenBook patches + `openbook-audio-setup`) | **On the G14:** speakers, built-in mic, browser and Bluetooth audio work under enforcing, with clean Android playback and capture. Not yet shown: the headphone jack, MediaPlayer sounds with the current SELinux rule. `docs/g14-audio-net.md` |
| Wi-Fi / BT | mt7925e, btmtk | wpa_supplicant + the framework's nl80211 (no vendor HAL, no wificond); AOSP's AIDL Bluetooth HAL on the HCI user channel | **On the G14:** Wi-Fi connects on 2.4 and 5 GHz (DFS included), validates internet and runs PNO; Bluetooth pairs and streams A2DP. Not yet measured: throughput. `docs/g14-audio-net.md` |
| NPU | amdxdna (XDNA 2) | — | Module built; binds on the G14 (`accel0`); userspace later |
| dGPU | NVIDIA's open driver 615.78.08 (nouveau blocklisted) | — (no Vulkan driver for apps on OpenBook) | Loaded after boot in Hybrid; runtime D3cold when idle, waking for clients, shown on the G14 with the Googlebook images that share this kernel and vendor. OpenBook's own image has not run on the laptop with it. Display through the RTX (HDMI, Ultimate) not yet. `docs/nvidia-open.md` |
| Platform | asus-wmi, asus-armoury, hid-asus | — | asus-wmi/hid-asus built. 6.18 asus-wmi has `dgpu_disable` and `gpu_mux_mode`; asus-armoury (6.19) not needed for bring-up. The graphics-mode switcher reads them; firmware writes stay off (`docs/nvidia-graphics-modes.md`) |
| Virtualization (the Linux environment) | kvm_amd, vhost_vsock, tun (all built in: `KVM_AMD=y`, `VHOST_VSOCK=y`, `TUN=y` in the G14 kernel's `dot_config`) | AVF: crosvm, virtmgr, the Terminal app and its Debian guest (ANAL-218) | In both images since Q4. `openbook-pc-setup kvm` sets AVF's `ro.boot.hypervisor.*` properties only when KVM registered its device, so the firmware's SVM switch decides whether the Linux environment is offered. **Untested on the G14**: the check (`scripts/quire/q4-device-check.sh`) records `/dev/kvm`, `kvm_amd` and the guest's boot time |
| IOMMU | amd_iommu | — | `AMD_IOMMU=y` in OpenBook GKI; starts with interrupt remapping on QEMU's emulated AMD-Vi |
| Boot | UEFI, GPT; EFI loader with bootconfig | AVB orange | systemd-boot, GRUB and GBL boot our kernel and userspace from a USB GPT image in QEMU/OVMF. **On the G14:** systemd-boot boots our kernel from USB with Secure Boot off, and Android's first and second stage run from the stick. OpenBook has also run installed on the internal disk (slot A, as of 2026-10-19; `docs/installer.md`) |

## Other candidate devices
- Zen 4 laptops (Ryzen 7040/8040, Radeon 780M), as a secondary target.
- Desktop iGPUs, such as the build host's Radeon 610M, for early bring-up only.

## Reference build host

The machine the project's build and VM numbers come from (confirmed 2026-10-15). `docs/BUILD.md` has the minimum
requirements.

| Item | Value |
|---|---|
| CPU | AMD Ryzen 9 7950X, Zen 4, 16C/32T. Has AVX-512, AVX512-VNNI, GFNI, VAES, SHA-NI. **No AVX-VNNI (VEX)** |
| iGPU | AMD Raphael, Radeon 610M (RDNA2, 2 CU) |
| dGPU | NVIDIA RTX 4090 (AD102) |
| RAM | 61 GiB plus 123 GiB swap |
| Wi-Fi | Intel AX210 |
| OS | Arch Linux (Omarchy), kernel 7.2.8. KVM (AMD-V, AVIC) usable without sudo; Docker 29 |
