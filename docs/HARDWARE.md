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

## Target devices

No device has been confirmed yet. **The owner needs to pick one.** Our recommendation:

1. **Zen 5 laptop with Ryzen AI 300 (Strix Point) or Ryzen AI Max (Strix Halo).** It has AVX-VNNI, so it matches Google's Panther Lake-tuned binaries most closely. It also has an RDNA 3.5 iGPU, XDNA2 NPU (amdxdna), and usually MediaTek MT7925 or Realtek Wi-Fi.
2. **Zen 4 laptop with Ryzen 7040/8040 (Phoenix/Hawk Point, Radeon 780M).** It is the most widely tested in Mesa and Waydroid. It lacks AVX-VNNI, which is an open risk for Track B (see PLAN §3.4).
3. Desktop iGPUs (this host's Radeon 610M) for early bring-up only.

## Per-device enablement checklist (fill in once a target is chosen)

| Area | Kernel / driver | Userspace | Status |
|---|---|---|---|
| GPU | amdgpu, linux-firmware `amdgpu/*` | Mesa radeonsi/RADV, minigbm, drm_hwcomposer, ANGLE | Not started |
| CPU power | amd-pstate (EPP) | power HAL | Built into the stock kernel (`X86_AMD_PSTATE=y`) |
| Suspend | amd_pmc (s2idle) | system_suspend | Not in the stock kernel |
| Touchpad / touch | i2c-hid-acpi, pinctrl-amd, hid-multitouch | — | `PINCTRL_AMD` not in the stock kernel |
| Audio | snd_acp / SOF-AMD | audio HAL | Not in the stock kernel |
| Wi-Fi / BT | mt7921e/mt7925e, rtw89, ath11k/12k | wifi HAL | Stock kernel has Intel only |
| NPU | amdxdna | — | Later |
| IOMMU | amd_iommu | — | Not in the stock kernel |
| Boot | UEFI, GPT; EFI loader with bootconfig | AVB orange | QEMU direct-kernel boot works |
