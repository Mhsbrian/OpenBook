# Hardware

## Ruby ARM translation on the G14 (2026-10-22, ANAL-234)

On the installed RB-20261021-01 system (6.18.21-android17, enforcing), Houdini
fails in app mode (`0x00010002`) and traps in executable mode on the HX 370.
Digitalis and Ruby's `libndk_translation` both run Google's ARM64 Icing library
correctly. Digitalis also passes the ID-register, FRECPE/FRSQRTE and NEON checks
on Zen 5. CoreMark: native 27,807 it/s, ndk 20,500 and Digitalis 10,073. No image
with a replaced bridge has booted on the G14 yet. See `docs/settings-search.md`.

## Ruby live search diagnosis (2026-10-21, ANAL-234)

Authorized adb observation confirms Ryzen AI 9 HX 370 and OpenBook G14 boot
properties, running Ruby `CL3B.260622.271.R1` with `ro.boot.openbook.live=1`.
Settings search fails after Houdini initialization and an ARM64 library load
error. The meaning of the bridge's internal error remains unknown; this is not
proof of an AMD instruction or hardware fault. Exact release-image identity and
the NVMe installation were not attested. ADB disconnected during follow-up;
neither alternate-bridge experiment has been tested on the G14. Digitalis
completes the ARM probe in a synthetic UEFI/USB TCG guest with three known
compatibility failures. TCG software-rendering/search restarts cannot establish
AMD hardware acceptance or prove the same cause as the original load failure.
See `docs/settings-search.md`.

## G14 touchpad measurement (2026-10-19, ANAL-226)

On `20261019.photos1` slot A: ELAN `04f3:3315`, five slots, X 0–3905,
Y 0–2382, resolution 31 units/mm, palm tool type but no pressure/size axes.
Tap dragging is already enabled in both Settings and the gesture library;
drag lock is off. The reported failure still needs a labeled reproduction.
See `docs/touchpad-behavior.md` and `evidence/2026-10-19-touchpad-behavior/`.

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
| Display | 14" 2880×1800 OLED, Samsung `ATNA40CU05-0` (EDID `SDC` product 16796): 120 Hz (DisplayID, preferred) and 60 Hz (base EDID) timings, 48–120 Hz adaptive sync, HDR static metadata, max 617 cd/m² | amdgpu DC. On 7.2 amdgpu leaves PSR off for this panel (`PSR support 0`; sink PSR version 1). Android scans out at 120 Hz; until ANAL-212 it drew at most 60 frames a second (`docs/graphics-amd.md`, "Refresh rate"). No VRR in drm_hwcomposer yet | — | C (EDID; G14 dumps) |
| Graphics switching | MUX + NVIDIA Advanced Optimus; inventory: `gpu_mux_mode=1` (Optimus), `dgpu_disable=0` | asus-wmi `dgpu_disable`/`gpu_mux_mode` (6.18), asus-armoury (6.19+) | — | C |
| Backlight | `amdgpu_bl1` (raw, max 400000) on `card1-eDP-1` in Optimus/Integrated mode. `nvidia_wmi_ec_backlight` loads but registers no device | amdgpu | — | C. A dGPU-only MUX mode would likely switch to nvidia-wmi-ec-backlight (hypothesis) |
| NPU | XDNA 2, `1022:17f0` rev 10 | amdxdna | `amdnpu/17f0_10/*` | C |
| Wi-Fi / BT | MediaTek MT7925 `14c3:7925`; BT `0489:e11e` on USB | mt7925e, btusb + btmtk | `mediatek/mt7925/*` | C |
| Audio | Realtek ALC285, codec SSID **1043:1024**, plus 2× Cirrus CS35L56 on I2C (`CSC3556`) | snd-hda-intel with quirk `ALC285_FIXUP_ASUS_GA403U_HEADSET_MIC` (mainline cbd46cbc5470, backported to OpenBook's 6.18), cs35l56-hda-i2c, serial-multi-instantiate | `cirrus/cs35l56-b0-dsp1-misc-10431024-spkid1{.wmfw,-amp1.bin,-amp2.bin}`: WHENCE links to the 10431044 tuning and `CS35L56_Rev3.11.16.wmfw` | C. The laptop loads the spkid1 set (`dmesg`); an earlier note here that linux-firmware lacked it was wrong. Headset mic broken upstream (R) |
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
1. **Run Android on the Radeon 890M.** Keep the MUX in hybrid (iGPU) mode and power the dGPU down with `dgpu_disable=1` from Linux before booting OpenBook. In dGPU-only MUX mode the internal panel is wired to the NVIDIA GPU, which Android cannot drive yet.
   - With `dgpu_disable=0`, the dGPU will most likely stay in D0 for the whole OpenBook session: no driver binds it, and `snd_hda_intel` holds its HDMI-audio function awake.
   - `scripts/dgpu-power-check.sh` verifies the state on Linux and on OpenBook (`docs/nvidia.md` §1).
2. **AVX-VNNI.** The CPU is the HX 370 (Zen 5), so Google's Panther Lake-tuned binaries meet their ISA baseline (PLAN §3.4). The Zen 4 risk applies only to the dev host.
3. **Audio needs several pieces:** the HDA Realtek codec with the 1043:1024 quirk, and the cs35l56 amplifiers. The internal mic is on the HDA codec. linux-firmware has the amps' tuning for 10431024 as links to the 10431044 files; the speaker-ID GPIO selects the spkid1 set on this unit.
4. **Fan and power tuning:** mainline `asus-armoury` has a power-limit table for the GA403WR (6.19+). The 6.18 kernel has the older `asus-wmi` `ppt_*` attributes.
5. **Suspend and panel power saving:** on the laptop's own Linux 7.2, 4 s2idle cycles completed with no amd_pmc errors, and amdgpu kept PSR off for the panel. One `WARNING` in `dc_dmub_srv_apply_idle_power_optimizations` (`dc_dmub_srv.c:1710`) appeared after about 23 hours. All of this is untested on our 6.18; if the display hangs on idle there, turning off DCN idle power states is the first thing to try (hypothesis).
6. **Safety:** first bring-up boots from USB only. Nothing on the internal NVMe or the firmware gets flashed, repartitioned or wiped without explicit confirmation that names the device.
7. **No USB device mode.** `/sys/class/udc` is empty and all USB controllers are xHCI hosts; the USB4 router (`67:00.5`) has no driver in our kernel. adb therefore runs over IP only (tcp:5555, Wireless debugging); a USB cable to the build host carries nothing. A USB-Ethernet adapter would need the GKI's `r8152`/`ax88179_178a`/`cdc_ether` modules loaded at boot (they ship in `system_dlkm` but are not loaded). `docs/adb-debug.md` (ANAL-222).

## Other candidate devices
- Zen 4 laptops (Ryzen 7040/8040, Radeon 780M), as a secondary target.
- Desktop iGPUs, such as this host's Radeon 610M, for early bring-up only.

## Enablement checklist: G14 2025

| Area | Kernel / driver | Userspace | Status |
|---|---|---|---|
| GPU | amdgpu, linux-firmware `amdgpu/*` | Mesa radeonsi/RADV, minigbm, drm_hwcomposer, ANGLE | Kernel module and firmware list built, loads in a VM (ANAL-171). Userspace is in the image and picked at boot; its drivers ran on the build host's 610M (ANAL-174, `docs/graphics-amd.md`). **On the G14 (kernel side):** amdgpu binds the 890M; SMU, DCN 3.5 and DMUB firmware load; the eDP panel is detected with PSR; backlight `amdgpu_bl0` (ANAL-189 hardware check). **Userspace on the G14:** the desktop runs on the panel through ANGLE on RADV, minigbm and drm_hwcomposer, in "save logs" boots (ANAL-176). **Conformance:** a dEQP/ANGLE end2end graphics check for the stick is ready, and its 890M run is pending. The 610M pre-check is in `docs/graphics-amd.md` (ANAL-177) |
| CPU power | amd-pstate (EPP) | power HAL | Built into the stock kernel (`X86_AMD_PSTATE=y`). **On the G14:** `amd-pstate-epp`, status active, EPP `balance_performance`, max 5.16 GHz (ANAL-189 hardware check) |
| Suspend | amd_pmc (s2idle) | system_suspend | Module built (ANAL-171). **On the G14:** an RTC-woken s2idle cycle suspends and resumes cleanly, but **S0ix residency is 0** ("Last suspend didn't reach deepest state") while the driverless dGPU stays D0. With the dGPU powered down (bridge D3cold, runs 4 and 5) it is still 0, so the dGPU is not the only blocker. The one unmet LPI constraint is `\_SB_.PCI0.GPP0.SWUS`, an ACPI object below the empty hotplug port `00:01.1` (measured, run 6). The kernel powers it up to scan behind the port and never powers it down, so its power resource stays on. Run 7 powered it down, and with every LPI constraint met, S0i3 still failed. The SMU/BIOS or a driver ACPI doesn't report remains, and ANAL-178 continues it with an `amd-s2idle` Linux baseline (ANAL-189, `evidence/2026-10-16-g14-hwcheck/`) ANAL-178: the laptop's own Linux 7.2 shows no S0i3 failure (indirect); the leading HYPOTHESIS is the driverless AMD PSP keeping its bridge in D0, with a one-boot bisect ready for the owner (`docs/power-input.md`) |
| Touchpad / touch | i2c-hid-acpi, pinctrl-amd, hid-multitouch | — | `PINCTRL_AMD=y` and `X86_AMD_PLATFORM_DEVICE=y` in OpenBook GKI, i2c-designware/i2c-hid-acpi modules (ANAL-171). **On the G14:** the ELAN touchpad registers as Touchpad + Mouse input devices (ANAL-189 hardware check, `evidence/2026-10-16-g14-hwcheck/`). Its descriptor's vendor page `0xFF01` makes hid-input set `EV_REP` on the touchpad, so the kernel autorepeats `BTN_TOOL_FINGER`; Android turns that off (EventHub patch, ANAL-178, `docs/power-input.md` §2) |
| Audio | snd-hda-intel (ALC285, SSID 1043:1024 quirk backported), cs35l56-hda-i2c; internal mic on HDA | AOSP's AIDL example HAL, primary module on the codec's card (OpenBook patch + `openbook-audio-setup`) | Modules built (ANAL-171); CS35L56 tuning for 10431024 added to the firmware list (ANAL-175). Android side (ANAL-179): card found and mixer set at boot, 48 kHz policy; playback through ALSA and through AudioFlinger reaches QEMU's HDA codec. **Untested on the G14** (`docs/g14-audio-net.md`) |
| Wi-Fi / BT | mt7925e, btmtk | wpa_supplicant + the framework's nl80211 (no vendor HAL, no wificond); AOSP's AIDL Bluetooth HAL on the HCI user channel | Modules and firmware list built (ANAL-171). **On the G14:** mt7925e binds, firmware loads, `wlan0` and Bluetooth `hci0` appear (ANAL-189). Android side (ANAL-179): signed `regulatory.db` loads; in QEMU over mac80211_hwsim: scan, WPA2 connect, DHCP, iperf3 about 650–740 Mbit/s. **Untested on the G14** (`docs/g14-audio-net.md`) |
| NPU | amdxdna (XDNA 2) | — | Module built (ANAL-171); binds on the G14 (`accel0`, ANAL-189 hardware check); userspace later |
| dGPU | nouveau / NVK (RTX 50 Laptop, GB20x) | — | Later: research track N1–N6 in `docs/nvidia.md`. Kept off with `dgpu_disable=1` (ANAL-176 default) |
| Platform | asus-wmi, asus-armoury, hid-asus | — | asus-wmi/hid-asus built (ANAL-171). 6.18 asus-wmi has `dgpu_disable` and `gpu_mux_mode`; asus-armoury (6.19) not needed for bring-up |
| Virtualization (the Linux environment) | kvm_amd, vhost_vsock, tun (all built in: `KVM_AMD=y`, `VHOST_VSOCK=y`, `TUN=y` in the G14 kernel's `dot_config`) | AVF: crosvm, virtmgr, the Terminal app and its Debian guest (ANAL-218) | In both images since Q4. `openbook-pc-setup kvm` sets AVF's `ro.boot.hypervisor.*` properties only when KVM registered its device, so the firmware's SVM switch decides whether the Linux environment is offered. **Untested on the G14**: the check (`scripts/quire/q4-device-check.sh`) records `/dev/kvm`, `kvm_amd` and the guest's boot time |
| IOMMU | amd_iommu | — | `AMD_IOMMU=y` in OpenBook GKI; starts with interrupt remapping on QEMU's emulated AMD-Vi (ANAL-171) |
| Boot | UEFI, GPT; EFI loader with bootconfig | AVB orange | systemd-boot, GRUB and GBL boot our kernel and userspace from a USB GPT image in QEMU/OVMF. **On the G14:** systemd-boot boots our kernel from USB with Secure Boot off, and Android's first and second stage ran from the stick (ANAL-189 hardware check) |

## G14 YV12 video import (2026-10-19, ANAL-210)

The Radeon 890M on `20261019.quire9` reproducibly rejects YV12 EGLImage imports.
Photos triggered three SurfaceFlinger aborts with 384×640 YV12 frames. Mesa
patch 0005 supplies the missing RADV format mapping; on this G14, an isolated
headless process passes import and colour readback for RGB, YV12 and flexible
YUV420 at five sizes (15/15), without restarting the desktop. This is a driver
format defect, not evidence of failing hardware. System deployment and the
Photos app check are tracked in `evidence/2026-10-19-photos-yv12/SUMMARY.md`.
