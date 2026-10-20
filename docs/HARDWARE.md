# Hardware

Update qualification (ANAL-229, 2026-10-20): no connected G14 ADB endpoint was
available for a new update-specific capture. No USB, SSD, firmware or laptop
setting was changed. The retained camera25 VM has one boot-control slot while
advertising Virtual A/B; its stock update engine registers both Binder
interfaces. This is exposure evidence, not proof that an OTA successfully
applies. An offline VM experiment stops the engine, but fails fresh-data boot;
the initialized-data variant boots and reproduces the known system-server
crash. Networked idle/charging, reboot/recovery, Play app-update preservation
and newer-data rollback remain unqualified. See `docs/googlebook-updates.md`.

Camera25 acceptance follow-up (2026-10-20): the owner confirms that the webcam
is fixed and Bluetooth works. These are physical owner reports, not measured
frame-rate/image-quality, Bluetooth-profile, suspend or privacy tests. Evidence:
`evidence/2026-10-20-googlebook-migration/owner-confirmation.json`.
The requested same-G14 migration path is documented in `googlebook-migration.md`;
its disk-copy checks do not substitute for post-install credential unlock.

Latest USB (migration26): camera25 plus the offline migration boot entry is
written to the configured SanDisk. Its latest saved state was backed up and
independently read back first. The complete 12.77 GB used extent verifies as
`95e30c7ae6be2849…`; all non-EFI partitions and existing EFI files are unchanged.
The backup is retained and the stick is powered off. No internal NVMe has been
written by the agent. See `evidence/2026-10-20-googlebook-migration/physical-write.json`.

Camera follow-up (2026-10-20 UTC): wireless ADB reaches camera24 on the G14.
The first HAL queue fix works, but Camera2 fails when cameraserver passes its
result queue to the app: SELinux denies access to `cameraserver_tmpfs`.
A bounded API1 diagnostic bypasses that boundary and starts the `3277:0060`
UVC webcam at 640×480/30; the provider then aborts because graphics-allocator
discovery is denied, leaving the mapper unavailable. Both APIs deliver zero
frames. Camera25 addresses both confirmed policy gaps; actual frames,
orientation and privacy behavior remain hardware gates. No reset is indicated.
See `docs/g14-camera.md` and `evidence/2026-10-20-googlebook-camera-clients/`.

Trackpad follow-up: the owner reports using Settings after the preserving update.
The latest live capture shows user 10 and the effective mapper both have tapping
enabled; it does not reproduce the earlier tap-disabled symptom. Static inspection
confirms the retained Ruby input framework lacks both OpenBook touchpad timing
fixes. The possible Settings-only scroll/activation symptom remains unconfirmed
by a motion trace; no physical fix is claimed. See
`evidence/2026-10-19-googlebook-touchpad-followup/`.

Previous camera25 system update: camera25 was written using a fresh verified
backup of its latest camera24 state and the preserving updater. Full 12.77 GB
direct readback matches the private clone (`c613fd06e2eb2138…`); all
8,805,941,248 protected bytes, including userdata/encryption metadata, remain
byte-identical. Unrelated EFI files are also unchanged. Power-off succeeded
and the fresh backup is retained. The earlier camera24 ADB session confirmed
boot completion and encrypted `/data` mounted. Camera25 boot, credential unlock,
existing app state still require a G14 check in the recorded write result;
the subsequent owner camera/Bluetooth acceptance is noted above. See
`evidence/2026-10-20-googlebook-camera-clients/physical-write.json`.

The Ruby live follow-up confirms ELAN `04f3:3315` is recognized through
TouchpadInputMapper. The older dump has tapping on, while the owner reports
scroll/click interference with tapping off. Current-user preference propagation
and gesture timestamp warnings need a labeled physical trace. Nine synthetic
AOSP replay controls pass, including tap-disabled scrolling; this is not a
physical Ruby touchpad fix. The read-only ADB collector now records the exact
preferences and mapper state. See `docs/touchpad-behavior.md` for the separate
Ruby and installed-OpenBook findings.

Vendor-only preserving updates are implemented for this configured research
USB. Both private prepared clones preserve 8,805,941,248 bytes outside the three
update partitions and retain other ESP files. G14 credential unlock and apps
must still be checked after an update; byte preservation is not that hardware
test. Current validation: `evidence/2026-10-19-googlebook-services-update/`.
The paragraphs below retain the earlier baseline observations.

The owner has completed setup on the net18 USB and requests preserving that
state during future updates. The same SanDisk is attached to the development
host. Read-only inspection confirms separate 8 GiB userdata and 64 MiB metadata
partitions, with the same extents as zram19. This supports offline system-only
updates, but an updated G14 unlock has not been tested. Preserve both data and
encryption metadata; a full fresh-image rewrite is unsuitable for iteration.

The running G14 is now paired over wireless ADB. Two captures and a complete
bugreport confirm net18 Wi-Fi association and validated internet, Radeon 890M
hardware rendering at 2880×1800/120 Hz, and sound-effects decoding with a
speaker output route. Audibility remains unverified; speaker volume is low (1).
Thermal HAL reports live CPU/GPU/Wi-Fi sensors and no throttling at capture.
The physical machine also exposes missing zram and a framework watchdog blocked
in a property-service connection. A module-loading correction is prepared for
the next image; it has not changed the currently booted USB. See
`evidence/2026-10-19-googlebook-live-adb/investigation.md`.
The following paragraphs preserve earlier test history.

The owner has now booted fw10 into Googlebook setup through both normal and
save-logs entries. The new G14 capture confirms Radeon initialization, MT7925
firmware and both CS35L56 amplifier firmware loads. Wi-Fi scanning is reported
working, but joining remains unverified: the saved capture ends at 66 seconds,
with no authentication attempt recorded. Audio has confirmed Codec2 shared-buffer denials;
silence at startup alone does not establish speaker failure. Follow-up evidence
and compatibility changes: `evidence/2026-10-19-googlebook-wifi-audio/`.
The SanDisk now contains net18 (`74c5270b2c37b658…`), with full 12.77 GB
write/readback verification and safe power-off. Its Wi-Fi override, decoder
fix and expanded diagnostics passed VM checks; actual joining and speaker
playback await the next G14 boot. The prior used extent and logs are preserved.
Earlier records below describe the preceding iterations.

The returned **2026-10-19 G14 Googlebook capture** identifies a firmware-path
packaging error: the live entry dropped `firmware_class.path=/vendor/firmware`.
Radeon firmware lookup fails at 6.047 seconds and GPU initialization aborts;
XDNA and MT7925 firmware lookup fail too. Minigbm and SurfaceFlinger subsequently
fail. The firmware files are present in vendor. The corrected image
`048bacf5934bcd22…` now holds the vendor command line on the owner's SanDisk:
the full 12.77 GB write/readback matches, and the stick was powered off. It has
subsequently been tested as described above.
The original 160 log files are backed up privately and the FAT check passes.
See `evidence/2026-10-19-googlebook-g14-black-screen/` for the physical findings
and their limits. Earlier trial notes below describe the preceding builds.

The owner subsequently reported a black screen after selecting the experimental
Googlebook USB entry. Inspection found initialized Android metadata but no saved
ESP reports, bootstat entries or watchdog files. The original candidate only
logged to a VM serial console. Its used disk extent was backed up privately for
investigation. Persistent USB diagnostics are described in
`docs/googlebook-live.md`; a VM capture is not proof of a physical Radeon fix.
The preceding diagnostic candidate was `19b9a9492f6b09ba…`: the full
12.8 GB write/readback matches and the device was powered off. Its returned
save-logs capture is analyzed above. That used image extent and all 160 reports
were preserved privately before the corrected candidate replaced it.

On 2026-10-19, the owner attached the previously identified 62 GB SanDisk Ultra
and requested the experimental Googlebook image. The guarded write and full
12.8 GB readback passed, then the stick was powered off. This verifies the
physical medium, not G14 boot or Radeon/TPM compatibility. The installed G14
and firmware were not modified. See `evidence/2026-10-19-googlebook-usb/`.

The 2026-10-19 follow-up adds a TCG execution baseline for Ruby's AVX-VNNI
instructions and an emulated USB/UEFI path (`docs/googlebook-live.md`). This
does not change the 7950X's native ISA or qualify the G14. OpenBook already
packages TPM core and CRB as vendor modules; the VM can exercise them against
a disposable software TPM. No physical USB was attached during the initial
VM bring-up inventory; the later stick write is recorded above.

## Googlebook VM CPU baseline (2026-10-19, ANAL-228)

The first mixed Ruby/OpenBook KVM boot runs on the Ryzen 9 7950X build host,
not the GA403WR. Zygote and boot animation both trap on VEX `vpdpwssd`, requiring
AVX-VNNI. CPUID and an isolated instruction probe confirm that the 7950X lacks
it despite having AVX512-VNNI. The retained HX 370 inventory reports AVX-VNNI;
that hardware still needs an actual Googlebook boot trial. No physical-device
write or update occurred. See `docs/googlebook-bringup.md`.

## Googlebook recovery base (2026-10-19, ANAL-228)

The alternative targets the existing GA403WR / HX 370 / Radeon 890M `1002:150e`
inventory below, with NVIDIA off for initial trials. Current G14 AOSP evidence
does not establish Googlebook recovery compatibility. GBRUNCH's AMD evidence is
kernel/module admission in QEMU only; its physical desktop report is Intel HP.
No G14 Googlebook boot or hardware change was performed for this review. See
`docs/googlebook-image-base.md` for the required graphics/security/interface checks.

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
