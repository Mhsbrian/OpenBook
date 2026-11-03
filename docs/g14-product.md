# OpenBook G14 product: `anybook_g14_x86_64` (ANAL-199)

The real product for the ASUS ROG Zephyrus G14 2025 (GA403WR), as opposed to Cuttlefish: a generic x86_64 UEFI PC layer plus a G14 layer, built from the AOSP 17 tree (`cp2a`), packed into a USB-ready GPT disk image, and testable in QEMU/OVMF as a PC. This doc covers the layout, boot chain, kernel packaging, HALs, graphics, input, the dGPU hook and the SELinux policy. The desktop on the laptop itself is in `docs/g14-desktop.md`; audio, Wi-Fi and Bluetooth are in `docs/g14-audio-net.md`. Guesses are labelled **HYPOTHESIS**.

## Build, image and test

```bash
scripts/g14-stage-kernel.sh                         # ANAL-198's dist -> <AOSP>/vendor/anybook/g14-kernel (checked)
scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug droid openbook_hals_test validatekeymaps
docker wait anybook-aosp-build                      # about 40 min the first time, 0.5–2.3 min after a change
scripts/g14-image.sh [--xz]                         # -> <data dir>/installer/out/openbook-g14-<build id>-<date>.img (+ .json, .sha256), ~20 s
scripts/g14-qemu.sh <img> <run>                     # first boot from a fresh copy: ~3 min, logs in <data dir>/logs/installer/<run>/boot1
scripts/g14-qemu.sh --again <run>                   # second boot on the same disk: ~2 min
out/host/linux-x86/nativetest64/openbook_hals_test/openbook_hals_test
scripts/openbook-pc-setup-test.sh [sh|bash]
```

- **Build cost** (2026-10-16): a first build of the product peaked at 45 GB RSS. `validatekeymaps` checks the input files; `openbook_hals_test` is the HAL host test.
- **Image:** 12 GiB (about 1.3 GB allocated; the `.img.xz` is under 1 GB). Images stay in `<data dir>/installer/out/` and are never committed. The live USB stick is built from the same product by `scripts/installer-image.sh` (`docs/installer.md`).
- **QEMU** (`scripts/g14-qemu.sh`, in `tools/Dockerfile.installer`: QEMU 11.1.2 on KVM, OVMF 202608, systemd 262, swtpm): q35, 8 vCPUs, 8 GiB, the image as a usb-storage stick on qemu-xhci, virtio-vga at 1920×1200, a TPM 2.0 on CRB, USB keyboard and tablet, no network, no AMD GPU. `scripts/installer/qemu-run.py` drives it (`--gpu`, `--usb-input`, `--tpm`, `{"shot": …}` steps); `scripts/installer/expect-g14*.json` hold the console steps for the two boots and `scripts/installer/serial-extract.py` splits the serial log into sections.
- **What a QEMU run shows** (as of 2026-10-16): first boot (blank `/metadata` and `/data`, formatted on the way) reaches `sys.boot_completed=1` at about 30 s uptime with Launcher3 resumed; the second boot on the same disk at about 12 s with no reformat. A lock-screen PIN set in the first boot still verifies in the second, so the software KeyMint, Gatekeeper and Weaver state survives a reboot. The boot disk is found by partition UUID; AVB is orange, dm-verity enforcing on all six logical partitions, SELinux enforcing.
- **What QEMU can't show:** the AMD path (amdgpu, RADV/ANGLE, EPP, backlight, battery, thermal zones, UCSI, touchpad, N-KEY) has no hardware there, so its HALs run on empty sysfs. The VM screen also stays on the last boot-animation frame after `boot_completed`, although the boot animation has stopped and Launcher3 is focused: the VM-only software path (SwiftShader under ANGLE, drm_hwcomposer on 2D virtio-gpu, no virgl). Parked by the owner; the G14 renders through amdgpu.

**Confirmed on the G14** (first live boot, 2026-10-16, permissive): amdgpu driving `eDP-1` at 2880×1800, the probe's `hal=amdgpu` stack, the panel backlight, the ELAN touchpad moving the pointer, the N-KEY keyboard, both dGPU functions in D3cold through `openbook-pc-setup dgpu-pm`, `amd-pstate-epp`, battery and AC, and `mt7925e` with `wlan0`. The enforcing desktop is in `docs/g14-desktop.md`.

## Layout

```
device/anybook/
  AndroidProducts.mk                 lunch anybook_g14_x86_64-cp2a-userdebug (and the Cuttlefish product)
  common/pc/                         generic x86_64 UEFI PC, reusable for other laptops
    pc.mk                            product half: AOSP system/system_ext/product, desktop.mk, graphics-amd.mk, HALs
    BoardConfig.mk                   board half: GKI boot images, vendor_boot fragment, partitions, AVB, sepolicy
    fstab.openbook                   first stage (vendor ramdisk) and second stage (/vendor/etc)
    init.openbook.rc                 module loading, graphics mode, dGPU hook, density, the virtio-gpu fallback
    init.openbook.zram.rc            zram0 before framework memory management starts
    ueventd.openbook.rc              backlight, LED and Type-C attributes for the HALs
    manifest.xml                     FCM target level 202604; HALs bring VINTF fragments
    bin/openbook-pc-setup.sh         dGPU runtime-PM fallback, EPP permissions
    bin/openbook-hwtest.sh           Wi-Fi, Bluetooth, audio and arm64-bridge checks (`su 0 openbook-hwtest`)
    bin/dgpu-power-check.sh          -> scripts/dgpu-power-check.sh (ANAL-187), userdebug only
    bin/openbook-pc-setup-test.sh    -> scripts/openbook-pc-setup-test.sh, userdebug only
    hals/                            health, lights, power, power.stats, thermal, weaver services + host test
    audio/, wifi/, camera/           audio policy and setup, Wi-Fi, UVC camera provider (docs/g14-audio-net.md)
    sepolicy/vendor/                 labels and rules for all of the above
  g14/
    anybook_g14_x86_64.mk            the product: pc.mk + G14 kernel, firmware, input files, density
    anybook_g14/BoardConfig.mk       the board: pc + graphics-amd board halves, G14 boot devices
    kernel.mk                        where the staged kernel lives in the AOSP tree
    gfx-stacks.conf                  the graphics modes this image may switch (docs/nvidia-graphics-modes.md)
    input/                           N-KEY keyboard .idc/.kl, ELAN touchpad .idc, WMI hotkeys .kl
scripts/
  g14-stage-kernel.sh                ANAL-198's images and firmware -> vendor/anybook/g14-kernel (checked)
  g14-image.sh                       PRODUCT_OUT -> USB GPT image (+ .json, .sha256, optional .xz)
  g14-qemu.sh                        boot the image in QEMU/OVMF as a USB stick, run the checks
  openbook-pc-setup-test.sh          fixture test for the dGPU hook (host and device)
  installer/mkproduct.py             the image builder (reuses mkproto.py's helpers)
  installer/expect-g14*.json         the console steps for the QEMU boots
  installer/serial-extract.py        splits the serial log into sections, decodes logcat/dmesg
```

- **Why a PC layer and a G14 layer.** Nothing in `common/pc` names the G14: it is what any UEFI x86_64 laptop with an AMD GPU needs. The G14 layer adds what is specific: the kernel packaging and firmware set (ANAL-198), the NVMe and USB root ports, the built-in keyboard and touchpad, and the panel density.
- **Names.** The product, board and directories keep the `anybook` prefix until the coordinated rename (`docs/installer.md` §7). New identifiers that nothing else uses yet are OpenBook: `androidboot.hardware=openbook`, `init.openbook.rc`, `vendor.openbook.*`, `PRODUCT_BRAND := OpenBook`.

## Boot chain and disk

| Partition | Size | Content |
|---|---|---|
| `EFI` (ESP, FAT32, label `OPENBOOK`) | 256 MiB | systemd-boot 262 as `EFI/BOOT/BOOTX64.EFI`; `loader/entries/openbook-{a,b}+3.conf` (default, boot counting) and `openbook-{a,b}-console.conf`; `openbook/<slot>/{kernel, vendor_ramdisk.img, ramdisk.img, bootconfig.img, bootconfig-console.img}` |
| `misc` | 4 MiB | zeros; the boot control HAL initialises it on first boot |
| `boot_a`/`_b` | 64 MiB | the product's `boot.img`: our GKI `bzImage`, boot image v4 |
| `init_boot_a`/`_b` | 8 MiB | the product's `init_boot.img` (generic ramdisk) |
| `vendor_boot_a`/`_b` | 64 MiB | the product's `vendor_boot.img`: the product ramdisk (fstab), ANAL-198's `dlkm` fragment, cmdline and bootconfig |
| `vbmeta_a`/`_b` | 1 MiB | one vbmeta: hash descriptors for boot, init_boot, vendor_boot; hashtree descriptors for system, system_ext, product, vendor, vendor_dlkm, system_dlkm |
| `metadata` | 64 MiB | blank; ext4 on first boot (`formattable`) |
| `super` | 8 GiB | the six logical partitions, slot A; virtual A/B with lz4 compression |
| `userdata` | rest (3.4 GiB in the 12 GiB image) | blank; f2fs with FBE and metadata encryption on first boot |

- **Loader** (`docs/installer.md`): systemd-boot, menu hidden. Each entry loads the kernel and three initrds: all vendor ramdisk fragments (each lz4 stream padded), the generic ramdisk, and a bootconfig blob last. `scripts/installer/mkproduct.py` builds it from the product's own images; nothing is re-signed.
- **Bootconfig.** Static, from `vendor_boot` (`BOARD_BOOTCONFIG`): `androidboot.hardware=openbook` and, for loaders that pass no partition UUID, `androidboot.boot_devices` = the GA403WR's NVMe root port `00:02.1` and xHCI root ports `00:08.1`/`00:08.3` (from the bridge lines in the laptop's dmesg). Per boot, from the loader: slot, `orange`/`unlocked`, the vbmeta digest and size, `androidboot.boot_part_uuid` (this disk's ESP), serial number. Init ignores `boot_devices` whenever `boot_part_uuid` is set (`devices.cpp`), so a stick and an internal disk with the same partition names never mix.
- **Kernel command line:** the GKI's built-in one plus `firmware_class.path=/vendor/firmware log_buf_len=1M`. No console, so the firmware logo stays until amdgpu takes over. The serial-console entry adds `console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on` and `androidboot.lcd_density=160`; QEMU runs use it. A test copy switches the default entry in the copy's ESP only.
- **No `androidboot.force_normal_boot`, no recovery:** the product has no recovery ramdisk (`TARGET_NO_RECOVERY`), so first-stage init reads `/first_stage_ramdisk/fstab.openbook` in place.
- **Verified boot:** one vbmeta signed with AOSP's test key; the loader reports **orange**. dm-verity runs on every logical partition, but OpenBook does **not** claim verified boot.
- **APEXes ship uncompressed** (`PRODUCT_COMPRESSED_APEX := false`), so the first boot of a fresh `/data` doesn't decompress them first (`docs/g14-desktop.md` §11).

## Kernel, modules and firmware

- `scripts/g14-stage-kernel.sh` copies ANAL-198's packaging into the AOSP tree (`vendor/anybook/g14-kernel`, never committed) and checks every image against its `images.json`, so a `bzImage` and a `system_dlkm` from different builds can't be staged together (`MODULE_SIG_PROTECT`). It uses the dist's own `firmware/` (137 files plus 5 licence files). Gotcha: `<data dir>/kernel/g14/firmware` is an older staging without the CS35L56 `10431024` tuning; don't use it.
- `BoardConfig.mk` takes ANAL-198's hand-off as written: prebuilt `vendor_dlkm` and `system_dlkm`, the `dlkm` vendor-ramdisk fragment, `bzImage` as `kernel`.
- **Second-stage modules:** `init.openbook.rc` runs `/vendor/bin/modprobe -b --all=/vendor/lib/modules/modules.load` synchronously at early-init, in AOSP's `vendor_modprobe` domain, which our policy extends to `system_dlkm` (the GKI dependencies come through `modules.dep`). `-b` applies the blocklist that keeps the VM-only virtio modules out on real hardware. In QEMU, modprobe exits 1 because `asus-nb-wmi` returns -ENODEV without the ASUS WMI GUID; that is expected.
- **Firmware:** `firmware.mk` installs the subset to `/vendor/firmware`, which gets its own label so the kernel may read it directly (`docs/g14-desktop.md` §4). **AOSP 17 imports nine MediaTek MT7921/MT7922/MT7925 files itself** (`external/linux-firmware`, linux-firmware `0d347a3f`, 2026-04-23), and Soong owns those paths. The product takes AOSP's modules for them and drops ANAL-198's newer copies (`38c1a709`, 2026-10), which differ byte for byte; ANAL-179 keeps AOSP's (firmware build 20260414, the one the G14 loaded).
- **NVIDIA GSP firmware** for NVIDIA's open kernel modules (ANAL-297) is staged only when the kernel carries `nvidia.ko` (`docs/nvidia-open.md`).

## HALs

| HAL | Implementation | Backend | In QEMU |
|---|---|---|---|
| health | **OpenBook** `android.hardware.health-service.openbook` (AOSP's `libhealth_aidl_impl` plus ANAL-178's subclass) | real: `/sys/class/power_supply` (ACPI battery, AC, UCSI); charge counter from `charge_now`, state of health and GOOD/FAIR from `charge_full`/`charge_full_design` where the kernel reports none | runs; "No battery devices found" |
| boot control | `android.hardware.boot-service.openbook` (AOSP's AIDL default on `libboot_control`, plus `openbook-bootsync` for systemd-boot's ESP entries; ANAL-223, `docs/installer.md` §2.5) | real: `misc` partition and the ESP | A/B updates over adb (`docs/installer.md` §13.13) |
| lights | **OpenBook** `android.hardware.lights-service.openbook` | the panel backlight: firmware > platform > raw, so `amdgpu_bl1` (raw, max 400000) in Optimus/Integrated mode and `nvidia_wmi_ec_backlight` (firmware) in a dGPU MUX mode. The keyboard backlight is the N-KEY's input light | no backlight: reports no lights |
| power | **OpenBook** `android.hardware.power-service.openbook` | amd-pstate EPP per cpufreq policy: screen off → `power`, battery saver → `balance_power`, launch or fixed performance → `performance`, else the boot value. Never touches `platform_profile` or asus-wmi, which persist in firmware | no amd-pstate in the VM: modes accepted, nothing written |
| power stats | **OpenBook** `android.hardware.power.stats-service.openbook` | s2idle hardware-sleep (S0i3) residency from `/sys/power/suspend_stats`; no energy meters (no RAPL powercap in our kernel) | no hardware sleep reported: no entities |
| thermal | **OpenBook** `android.hardware.thermal-service.openbook` | thermal zones and their trip points (passive → SEVERE, hot → CRITICAL, critical → SHUTDOWN), hwmon (amdgpu, NVMe, Wi-Fi), battery; cooling devices; 5 s polling for callbacks. ACPI zones stay `UNKNOWN` (no SKIN) until measured on the laptop | no zones: empty lists, HAL ready |
| USB / Type-C | AOSP `android.hardware.usb-service.example` | real: `/sys/class/typec` (UCSI), role swaps | no Type-C ports |
| KeyMint | AOSP `com.android.hardware.keymint.rust_nonsecure` | **software, no TEE, no hardware attestation**; root of trust from bootconfig (orange) | keys generated; vold metadata key falls back to non-rollback-resistant, as expected |
| Gatekeeper | AOSP `com.android.hardware.gatekeeper.nonsecure` | **software** | PIN set and verified, also after reboot |
| Weaver | **OpenBook** `android.hardware.weaver-service.openbook` | **software, file-backed** (`/data/vendor/weaver`, libgatekeeper's throttling schedule). AOSP's example Weaver keeps slots in RAM, so a reboot would lock the user out. This adds no protection over plain Android | slots written and read back after reboot |
| audio | AOSP `com.android.hardware.audio` with OpenBook's HAL patch, `openbook-audio-setup` and `pc/audio/audio_policy_configuration.xml` | primary module on the built-in codec, remote submix, Bluetooth (`docs/g14-audio-net.md`) | the modules register |
| Wi-Fi | AOSP's wpa_supplicant on the laptop's mac80211 driver, no vendor Wi-Fi HAL (`pc/wifi/wifi.mk`) | `mt7925e` on the G14 | see `docs/g14-audio-net.md` |
| Bluetooth | AOSP `android.hardware.bluetooth-service.default` over the kernel's HCI user channel | btusb + btmtk on the G14 | no controller |
| graphics | ANAL-174's graphics-amd (minigbm, drm_hwcomposer, Mesa RADV/radeonsi, ANGLE) | amdgpu, picked at boot | `hal=virtio` fallback (below) |
| authsecret, memtrack, dumpstate | AOSP APEXes | — | registered |

Each OpenBook HAL's logic is plain C++ with a sysfs root, tested on fixture trees by `hals/tests/hals_test.cpp` (G14 backlight, EPP on 24 policies, ACPI zones and amdgpu hwmon, Weaver persistence and throttling).

**The audio policy must create every module the audio APEX declares** (`default`, `r_submix` and `bluetooth`). audioserver waits for each declared module, so a missing one leaves `system_server` in a watchdog loop at `AudioSystem.setLowRamDevice`.

## Graphics

- **AMD (the G14):** ANAL-174's graphics-amd (`docs/graphics-amd.md`). The probe sees amdgpu (or the unbound `1002:*` display controller) at early-init and selects radv/angle/minigbm/drm. This product builds `graphics-amd/sepolicy/platform`, which carries the `mapper/minigbm` service label, every process's access to the allocator's metadata memfds, and `mlstrustedobject` on them for apps.
- **ANGLE stays off RADV's deferred swapchain path** (`debug.angle.feature_overrides_disabled=supportsSwapchainMaintenance1` in `graphics-amd.mk`). Unpatched RADV 26.2.5 crashes there, and every app's window surface goes through ANGLE, not just the boot animation (`docs/g14-desktop.md` §2, §3).
- **Fallback for GPUs no OpenBook driver handles (VMs):** when the probe reports `hal=virtio`, `init.openbook.rc` loads `virtio_pci` (a GKI module in `system_dlkm`; without it the allocator exits and SurfaceFlinger loops), `virtio-gpu` and `virtio_input`, and selects SwiftShader Vulkan under ANGLE, minigbm and drm_hwcomposer. SwiftShader JIT-compiles, so `sepolicy/swiftshader` grants `execmem` to surfaceflinger, system_server, zygote and bootanim, as Cuttlefish does. `OPENBOOK_SOFTWARE_GPU_FALLBACK := false` in a board config drops that policy. **On the G14 the four domains carry `execmem` they never use;** a release image should switch it off.

## Input and display

- `Vendor_0b05_Product_19b6.idc` (N-KEY, USB): `keyboard.builtIn = 1`, `device.internal = 1`. With the internal touchpad this is what lets WM Shell switch the panel to desktop mode without the testing property (`docs/aosp-desktop.md`). The keyboard backlight (`asus::kbd_backlight`) is a child of this HID device, so InputReader finds it by itself; `device.additionalSysfsLedsNode` would register it twice, so the file doesn't set it.
- `Vendor_0b05_Product_19b6.kl`: AOSP's `Generic.kl` plus the four keys hid-asus sends as `KEY_PROG1..4` (ROG key, Fn+C, Fn+Space, Fn+F5), mapped to `MACRO_1..4`.
- `Vendor_04f3_Product_3315.idc` (ELAN, I2C HID): `device.internal = 1`, `touch.deviceType = touchPad`. On the G14 InputReader classes it `TOUCHPAD`, so the gestures-library mapper drives it; tuning is in `docs/power-input.md` §2 and `docs/touchpad-behavior.md`.
- `Asus_WMI_hotkeys.kl` (ANAL-178): the firmware's WMI hotkeys (asus-nb-wmi, no USB IDs) get a layout by device name: `Generic.kl` plus `KEY_PROG1..4` → `MACRO_1..4` and the screenshot key.
- **Density:** `ro.vendor.openbook.lcd_density=240` for the 14" 2880×1800 panel (243 ppi), giving a 1920×1200 dp desktop, overridable per boot with `androidboot.lcd_density`. Without either, `init.openbook.rc` uses 160.

## dGPU

- `dgpu-power-check` (ANAL-187's `scripts/dgpu-power-check.sh`, linked into the device tree and copied by `aosp-build.sh`; test `tests/dgpu-power-check-test.sh`) is in the userdebug image. In QEMU it reports `WARN: absent-unknown` and exits 2, as expected without ASUS WMI or ACPI power resources.
- **Fallback hook** (`openbook-pc-setup dgpu-pm`, early-init, root, its own domain): when an NVIDIA function is enumerated and its display function has no driver, it unbinds `snd_hda_intel` from the dGPU's HDMI-audio function, sets `power/control=auto` on every dGPU function, and gives `snd_hda_intel` `power_save=10`. Without vga_switcheroo the HDA controller never runtime-suspends while bound, so unbinding is what lets the root port reach D3cold (`docs/nvidia.md`). It never touches asus-wmi. It does nothing when a driver binds the GPU.
- **Tested with fake devices:** `scripts/openbook-pc-setup-test.sh` builds the G14's sysfs for three cases (dGPU enumerated and unbound, `dgpu_disable=1`, nouveau bound) plus the EPP step. It runs on the host and inside the image on its own mksh and toybox (installed as `openbook-pc-setup-test` in userdebug). QEMU can't emulate a `10de:*` device; on the real QEMU sysfs the hook reports "no NVIDIA GPU enumerated".
- **NVIDIA drivers and graphics modes** (nouveau, NVIDIA's open modules, the MUX switch) run before the hook, so it leaves a bound dGPU to its driver: `docs/nvidia.md`, `docs/nvidia-open.md`, `docs/nvidia-graphics-modes.md`.

## SELinux

Enforcing in every boot of the default entry. `sepolicy/vendor` labels the boot disk's partitions, the firmware, the HAL binaries, `/data/vendor/weaver`, and sysfs by class directory (`/sys/devices/.*/power_supply`, backlights, `leds` and keyboard backlights, `hwmon*`, `typec`, `wakeup*`, HID `country`, and the APU's PCI identity as `sysfs_gpu`), because ACPI and PCI paths differ between laptops. ueventd restorecons each device's directory when it appears. The G14's own denials and rules are in `docs/g14-desktop.md` §4.

Gotchas, each of which once stopped the boot (none VM-specific unless marked):

| Symptom | Cause | Fix |
|---|---|---|
| `/data` read-only, compressed APEXes not activated, `reboot … netbpfload-missing` | AOSP's `init.rc` mounts nothing: the device rc must call `mount_all --early`/`--late` | `init.openbook.rc` |
| software Gatekeeper aborts | its `ISharedSecret/gatekeeper` instance had no service label | `service_contexts` |
| boot HAL denied the slot partitions | second-stage init may relabel early-mount links only to a few types, not `boot_block_device` | the boot partitions' entries are typed `-b` |
| init log lines missing (VM) | the kernel rate-limits `/dev/kmsg` | `printk.devkmsg=on` on the console entry |
| SurfaceFlinger: `gralloc-mapper is missing` | `mapper/minigbm` had no service label | label in graphics-amd's platform policy |
| SurfaceFlinger: `output buffer not gpu writeable` | the allocator's metadata memfds carry its tmpfs type on this kernel; importers were denied | access for all buffer users |
| SurfaceFlinger SIGSEGV in SwiftShader (VM) | `execmem` denied | `sepolicy/swiftshader`, switchable |
| apps denied writing buffer metadata | MLS: apps (`s0:cX,cY`) may only write `mlstrustedobject` types | `typeattribute … mlstrustedobject` |
| keyboard backlight unreadable by system_server | `sysfs_leds` is off-limits to core domains | `sysfs_keyboard_backlight` with system_server access (Googlebook uses the same type) |
| amdgpu backlight and NVMe hwmon unlabelled | `…/card0-eDP-1/amdgpu_bl0` has no `backlight/` component; NVMe hwmon sits outside a `hwmon/` directory | path patterns that match them |

**AMD laptops get no hardware RNG from the TPM.** `tpm_crb` disables its hwrng on AMD CPUs unless the TPM2 table's start method is Pluton (AMD advisory PA-410). The G14's own Linux logs `tpm_crb_acpi MSFT0101:00: Disabling hwrng`, and so does QEMU. Android's `prng_seeder` then gives up. It drops its listening socket first, so BoringSSL falls back to `getrandom()` and nothing blocks (checked in `prng_seeder` and BoringSSL's `passive.cc`).

## Known limits

As of 2026-10-16 unless dated otherwise:

- **Thermal types.** ACPI zones `THRM` and `TZ01` stay `UNKNOWN`. `k10temp` is built and loads on the G14. `TZ01` reads a constant 20 °C; pick a SKIN sensor once measured under load (`docs/power-input.md` §3).
- **The SwiftShader `execmem` grant** ships on by default; switch it off for release images.
- **The VM display** stays on the boot-animation frame after `boot_completed` (VM-only; parked by the owner).
- **Recovery and fastbootd** are not in the product (`TARGET_NO_RECOVERY`): OTA through update_engine works without them; sideload and a recovery UI need a decision with the installer (ANAL-190/191).
- **Keystore and Gatekeeper's shared secret:** AOSP forbids keystore from finding a `hal_gatekeeper_service`. PINs work, but the Gatekeeper instance takes no part in the shared-secret negotiation. An AOSP-conformant label for that instance is still to be found.
- **Image size.** `super` is 8 GiB and the image 12 GiB; the live stick shrinks `super` to its contents (`docs/installer.md`).
