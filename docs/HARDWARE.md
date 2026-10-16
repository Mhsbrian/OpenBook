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

The owner named this laptop on 2026-10-15. The owner described it as a "2025 G14 with the AMD 370 and an RTX 5070", which matches the **GA403WP** SKU (Ryzen AI 9 HX 370 + RTX 5070 Laptop).

**CPU confirmed by the owner on 2026-10-16:** Ryzen AI 9 HX 370 (Zen 5). That rules out the Zen 4 Ryzen 9 270 variant (GA403UP), so the SKU is the **GA403WP**. Component IDs (Wi-Fi chip, touchpad, ACP version, panel) still need `scripts/hw-inventory.sh` output from the laptop.

Sources: rog.asus.com 2025 G14 spec pages, kernel and linux-firmware sources, and NotebookCheck. All checked 2026-10-15.

Labels: C = confirmed (ASUS spec page, kernel source, or linux-firmware contents), R = reported (reviews or community), U = unknown.

| Component | Part (expected) | Linux driver | Firmware | Label |
|---|---|---|---|---|
| CPU | Ryzen AI 9 HX 370: 4× Zen 5 + 8× Zen 5c | — | — | C (owner). AVX-VNNI and AVX-512 are expected for Zen 5; `/proc/cpuinfo` will show them |
| iGPU | Radeon 890M, RDNA 3.5, gfx1150 | amdgpu, Mesa radeonsi/RADV (Linux 6.10+ and Mesa 24.2+) | `amdgpu/gc_11_5_0*`, `dcn_3_5*`, `psp_14_0_0*`, `vcn_4_0_5*` | C firmware, R minimum versions |
| dGPU | RTX 5070 Laptop, GB206 (Blackwell), 8 GB | nouveau (Blackwell since 6.16, GSP 570.144), NVK (Mesa 25.2+) | `nvidia/gb206` → gb202 | R. **Kept off in the first bring-up** |
| Display | 14" 2880×1800 120 Hz OLED, 16:10, Samsung ATNA40CU05-0 | amdgpu DC (PSR/Panel Replay quirks are possible) | — | C panel spec, R panel ID |
| Graphics switching | MUX + NVIDIA Advanced Optimus | asus-armoury `gpu_mux_mode`, `dgpu_disable` (6.19+) | — | C spec |
| NPU | XDNA 2 | amdxdna (6.14+) | `amdnpu/17f0_*` | C driver, R ID |
| Wi-Fi / BT | MediaTek MT7925 (Wi-Fi 7, BT 5.4) | mt7925e, btmtk | `mediatek/mt7925*` | R (confirmed on GA403WW only) |
| Audio | Realtek ALC285 plus 2× Cirrus CS35L56 (I2C), SSID 1043:1024 | snd-hda-intel with Realtek quirk `ALC285_FIXUP_ASUS_GA403U_HEADSET_MIC`, cs35l56-hda-i2c, serial-multi-instantiate | `cirrus/cs35l56-b0-dsp1-misc-10431024-*` | C quirk and firmware. Headset mic broken upstream (R) |
| Internal mic | AMD ACP 7.x (DMIC) | snd_pci_ps / acp70 | — | R (hypothesis: ACP drives the DMIC) |
| Touchpad | i2c-hid, vendor U | i2c-hid-acpi, pinctrl-amd, hid-multitouch | — | R |
| Keyboard | ASUS N-KEY USB HID | hid-asus, asus-wmi | — | R |
| Webcam | 1080p plus IR | uvcvideo | — | C spec |
| Ports | USB4 40G, USB-C 3.2 (DP/PD), 2× USB-A, HDMI 2.1 | thunderbolt/usb4, ucsi_acpi | — | C spec |
| Security | Pluton, Secured-core | tpm_crb | — | C spec |

### Collecting the inventory (read-only)
Run this on the laptop from its installed Linux or a live USB. It changes nothing on the machine:
```bash
git clone https://github.com/Mhsbrian/AnyBook && cd AnyBook
scripts/hw-inventory.sh               # no root needed
scripts/hw-inventory.sh --with-root   # optional: adds dmesg, dmidecode, acpidump (sudo)
```
It writes `anybook-hw-<board>-<date>.tar.gz`, with serials, UUIDs and MAC addresses redacted. Attach that file to ANAL-175.

### Bring-up notes and risks
1. **Run Android on the Radeon 890M.** Keep the MUX in hybrid (iGPU) mode and power the dGPU down with `dgpu_disable` from Linux before booting AnyBook. In dGPU-only MUX mode the internal panel is wired to the NVIDIA GPU, which Android cannot drive yet.
2. **AVX-VNNI.** The CPU is the HX 370 (Zen 5), so Google's Panther Lake-tuned binaries meet their ISA baseline (PLAN §3.4). The Zen 4 risk applies only to the dev host.
3. **Audio needs several pieces:** the HDA Realtek codec, the cs35l56 amplifiers with their Cirrus firmware, and ACP for the internal mic.
4. **Fan and power tuning:** `asus-armoury` has power-limit tables for GA403WM, GA403WR and GA403WW but **not GA403WP**. That needs an upstream entry later.
5. **Suspend and panel power saving:** Strix Point s2idle and OLED PSR/Replay are untested on this model.
6. **Safety:** first bring-up boots from USB only. Nothing on the internal NVMe or the firmware gets flashed, repartitioned or wiped without explicit confirmation that names the device.

## Other candidate devices
- Zen 4 laptops (Ryzen 7040/8040, Radeon 780M), as a secondary target.
- Desktop iGPUs, such as this host's Radeon 610M, for early bring-up only.

## Enablement checklist: G14 2025

| Area | Kernel / driver | Userspace | Status |
|---|---|---|---|
| GPU | amdgpu, linux-firmware `amdgpu/*` | Mesa radeonsi/RADV, minigbm, drm_hwcomposer, ANGLE | Not started |
| CPU power | amd-pstate (EPP) | power HAL | Built into the stock kernel (`X86_AMD_PSTATE=y`) |
| Suspend | amd_pmc (s2idle) | system_suspend | Not in the stock kernel |
| Touchpad / touch | i2c-hid-acpi, pinctrl-amd, hid-multitouch | — | `PINCTRL_AMD` not in the stock kernel |
| Audio | snd-hda-intel (ALC285), cs35l56-hda-i2c, snd_pci_ps/acp70 (DMIC) | audio HAL | Not in the stock kernel |
| Wi-Fi / BT | mt7925e, btmtk | wifi HAL | Stock kernel has Intel only |
| NPU | amdxdna (XDNA 2) | — | Later |
| dGPU | nouveau / NVK (RTX 5070 Laptop) | — | Later; kept off with `dgpu_disable` |
| Platform | asus-wmi, asus-armoury, hid-asus | — | Not started |
| IOMMU | amd_iommu | — | Not in the stock kernel |
| Boot | UEFI, GPT; EFI loader with bootconfig | AVB orange | QEMU direct-kernel boot works |
