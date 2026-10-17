# OpenBook G14 product: `anybook_g14_x86_64` (ANAL-199)

Status as of 2026-10-16. This is the real product for the ASUS ROG Zephyrus G14 2025 (GA403WR), not Cuttlefish: a generic x86_64 PC layer plus a G14 layer, built from the AOSP 17 tree (`cp2a`), packed into a USB-ready GPT disk image and booted in QEMU/OVMF as a PC. Evidence is in `evidence/2026-10-16-g14-product/`, starting with `SUMMARY.md`. Guesses are labelled **HYPOTHESIS**. **Nothing here ran on the laptop:** that is ANAL-176, under the device gate.

## Result

- **The product builds:** `lunch anybook_g14_x86_64-cp2a-userdebug`, `m` exit 0. The first build of the new product took 39 min (30:41 plus an 8:38 resume after a sepolicy fix; peak RSS 45 GB); incremental rebuilds take 0.5–2.3 min. The HAL host test passes 15/15, and `validatekeymaps` accepts the input files.
- **The disk image exists:** `openbook-g14-CP2A.260605.016-20261017.img` is 12,884,901,888 bytes (12 GiB, 1.3 GB allocated), sha256 `f337076d1e115b2b219e3664a4f85a85d09d61ef576be78a6827c5f36b031a46`. The `.img.xz` is 945,529,800 bytes, sha256 `3e6ff3b6c8d990f828581fb1ed609106b17b431ae6252e17aea2bf84596625d3`. Both stay in `<data dir>/installer/out/`; no image is committed.
- **It boots in QEMU/OVMF as a PC, from USB, to `sys.boot_completed=1`.** QEMU 11.1.2 on KVM (q35, 8 vCPUs, 8 GiB, OVMF 202608), the image as a usb-storage stick on qemu-xhci, virtio-vga at 1920×1200, a TPM 2.0 on CRB (swtpm), USB keyboard and tablet, no network, no AMD GPU.
  - **Boot 1** (blank `/metadata` and `/data`, formatted on the way): first-stage init at 3.6 s after power-on, second stage at 5.3 s, `/data` mounted at 6.9 s, `boot_completed` at **29.9 s** uptime. Launcher3 (`QuickstepLauncher`) is the resumed activity and the boot animation has stopped. All 58 console steps ran.
  - **Boot 2, same disk:** `boot_completed` at **11.7 s**, no reformat. The lock-screen PIN set in boot 1 still verifies (`Lock credential verified successfully`), so the software KeyMint, Gatekeeper and Weaver state survives a reboot.
  - The boot disk was found by partition UUID (`init: Boot device …/usb2/2-1/… found via partition UUID`). AVB is orange, dm-verity enforcing on all six logical partitions, SELinux enforcing.
- **Hardware-independent findings fixed on the way** (each was a full-boot blocker, and each would also have stopped the G14; [What QEMU found](#what-qemu-found)): no `mount_all`, the software Gatekeeper's service label, the minigbm mapper's service label, the allocator's metadata memfds, and an audio policy that creates the modules the audio HAL declares.
- **Not done here:** nothing ran on the GA403WR. That is ANAL-176, under the device gate. The AMD path (amdgpu, RADV/ANGLE, EPP, backlight, battery, thermal zones, UCSI, touchpad, N-KEY) has no hardware in QEMU, so its HALs run only on empty sysfs there.

![QEMU first boot](../evidence/2026-10-16-g14-product/qemu/boot1/shot-boot-completed.png)

**The VM screen** still shows the last boot-animation frame after `boot_completed`, although `init.svc.bootanim=stopped` and Launcher3 is resumed and focused. This is the VM-only software path (SwiftShader under ANGLE, drm_hwcomposer on 2D virtio-gpu, no virgl). The owner asked on 2026-10-16 not to spend more cycles on it; the G14 renders through amdgpu.

## Review against the first G14 live boot (ANAL-190, live-001)

On 2026-10-16 the owner booted ANAL-190's live stick, built from this product's run-6 inputs, on the GA403WR. SELinux was permissive (its "save logs" entry). The evidence is in `evidence/2026-10-16-installer/g14-live/` on PR #34. It confirms on hardware: amdgpu driving `eDP-1` at 2880×1800, the probe's `hal=amdgpu` stack, the backlight (`amdgpu_bl0`), the ELAN touchpad moving the pointer, the N-KEY keyboard, both dGPU functions in D3cold through `openbook-pc-setup dgpu-pm`, `amd-pstate-epp`, battery and AC, and `mt7925e` with `wlan0`.

| Finding on the G14 | Status in this branch |
|---|---|
| Boot animation SIGSEGV, null pointer at `0x60` in `vulkan.radv.so` ← libvulkan `AcquireNextImageKHR` ← ANGLE | **Fixed by avoiding the path.** Symbolized with the unstripped build (same BuildId `301af9c5…`): `radv_BindImageMemory2`. ANGLE creates swapchains with `VK_SWAPCHAIN_CREATE_DEFERRED_MEMORY_ALLOCATION_BIT_EXT`, so libvulkan binds each image at acquire time with `VkNativeBufferANDROID` and `memory = VK_NULL_HANDLE`. RADV 26.2.5 has no such path and dereferences the null memory (Mesa's v3dv, panvk, lavapipe and venus implement it with `vk_android_init_deferred_image`/`vk_android_import_anb_memory`). `graphics-amd.mk` sets `debug.angle.feature_overrides_disabled=supportsSwapchainMaintenance1`, so ANGLE creates its swapchain images up front through RADV's `vkCreateImage` + `VkNativeBufferANDROID` path. Every app's window surface goes through ANGLE too, not just the boot animation. **Not yet run on the G14.** |
| `system_server` watchdog loop in `AudioSystem.setLowRamDevice` | **Fixed** (QEMU run 8 and later): the audio policy now creates the `default`, `r_submix` and `bluetooth` modules the audio APEX declares. The stick predates it |
| 66 SELinux denials from Android services | Allocator memfds, `mlstrustedobject` and wakeup sources were already fixed. **Fixed after the review:** the amdgpu backlight path (`…/card0-eDP-1/amdgpu_bl0` has no `backlight/` component), hwmon outside a `hwmon/` directory (NVMe), the iGPU's PCI identity as `sysfs_gpu` (libdrm in the allocator, the boot animation and every app), the allocator's `getattr` on `/dev/dri/card0`, the keyboard backlight as `sysfs_keyboard_backlight` with system_server access (`sysfs_leds` is off-limits to core domains; Googlebook uses the same type), and the HID `country` file. **Left:** `flags_health_check` reading four platform props, `keystore` → Gatekeeper's shared secret (AOSP forbids it), `bootanim` stat of `/dev/dri/card0` |
| Keyboard backlight LED sits under the USB HID device | `device.additionalSysfsLedsNode` removed from the N-KEY `.idc`: InputReader already finds the LED there and would register it twice |
| No Wi-Fi service, no `regulatory.db` | Open, ANAL-179 |

## Layout

```
device/anybook/
  AndroidProducts.mk                 lunch anybook_g14_x86_64-cp2a-userdebug (and the Cuttlefish product)
  common/pc/                         generic x86_64 UEFI PC, reusable for other laptops
    pc.mk                            product half: AOSP system/system_ext/product, desktop.mk, graphics-amd.mk, HALs
    BoardConfig.mk                   board half: GKI boot images, vendor_boot fragment, partitions, AVB, sepolicy
    fstab.openbook                   first stage (vendor ramdisk) and second stage (/vendor/etc)
    init.openbook.rc                 module loading, dGPU hook, density, the virtio-gpu fallback
    ueventd.openbook.rc              backlight, LED and Type-C attributes for the HALs
    manifest.xml                     FCM target level 202604; HALs bring VINTF fragments
    bin/openbook-pc-setup.sh         dGPU runtime-PM fallback, EPP permissions
    bin/dgpu-power-check.sh          -> scripts/dgpu-power-check.sh (ANAL-187), userdebug only
    bin/openbook-pc-setup-test.sh    -> scripts/openbook-pc-setup-test.sh, userdebug only
    hals/                            lights, power, power.stats, thermal, weaver services + host test
    sepolicy/vendor/                 labels and rules for all of the above
  g14/
    anybook_g14_x86_64.mk            the product: pc.mk + G14 kernel, firmware, input files, density
    anybook_g14/BoardConfig.mk       the board: pc + graphics-amd board halves, G14 boot devices
    kernel.mk                        where the staged kernel lives in the AOSP tree
    input/                           N-KEY keyboard .idc/.kl, ELAN touchpad .idc
scripts/
  g14-stage-kernel.sh                ANAL-198's images and firmware -> vendor/anybook/g14-kernel (checked)
  g14-image.sh                       PRODUCT_OUT -> USB GPT image (+ .json, .sha256, optional .xz)
  g14-qemu.sh                        boot the image in QEMU/OVMF as a USB stick, run the checks
  openbook-pc-setup-test.sh          fixture test for the dGPU hook (host and device)
  installer/mkproduct.py             the image builder (reuses ANAL-189's mkproto.py helpers)
  installer/expect-g14*.json         the console steps for the two QEMU boots
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

- **Loader** (`docs/installer.md`, ANAL-189): systemd-boot, menu hidden. Each entry loads the kernel and three initrds: all vendor ramdisk fragments (each lz4 stream padded), the generic ramdisk, and a bootconfig blob last. `scripts/installer/mkproduct.py` builds it from the product's own images; nothing is re-signed.
- **Bootconfig.** Static, from `vendor_boot` (`BOARD_BOOTCONFIG`): `androidboot.hardware=openbook` and, for loaders that pass no partition UUID, `androidboot.boot_devices` = the GA403WR's NVMe root port `00:02.1` and xHCI root ports `00:08.1`/`00:08.3` (from the bridge lines in the inventory's dmesg). Per boot, from the loader: slot, `orange`/`unlocked`, the vbmeta digest and size, `androidboot.boot_part_uuid` (this disk's ESP), serial number. Init ignores `boot_devices` whenever `boot_part_uuid` is set (`devices.cpp`), so a stick and an internal disk with the same partition names never mix.
- **Kernel command line:** the GKI's built-in one plus `firmware_class.path=/vendor/firmware log_buf_len=1M`. No console, so the firmware logo stays until amdgpu takes over. The serial-console entry adds `console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on` and `androidboot.lcd_density=160`; QEMU runs use it. A test copy switches the default entry in the copy's ESP only.
- **No `androidboot.force_normal_boot`, no recovery:** the product has no recovery ramdisk (`TARGET_NO_RECOVERY`), so first-stage init reads `/first_stage_ramdisk/fstab.openbook` in place.
- **Verified boot:** one vbmeta signed with AOSP's test key; the loader reports **orange**. dm-verity runs on every logical partition, but OpenBook does **not** claim verified boot.

## Kernel, modules and firmware

- `scripts/g14-stage-kernel.sh` copies ANAL-198's packaging into the AOSP tree (`vendor/anybook/g14-kernel`, never committed) and checks every image against its `images.json`, so a `bzImage` and a `system_dlkm` from different builds cannot be staged together (`MODULE_SIG_PROTECT`). It uses the dist's own `firmware/` (137 files plus 5 licence files); `<data dir>/kernel/g14/firmware` is an older staging without the CS35L56 `10431024` tuning.
- `BoardConfig.mk` takes ANAL-198's hand-off as written: prebuilt `vendor_dlkm` and `system_dlkm`, the `dlkm` vendor-ramdisk fragment, `bzImage` as `kernel`.
- **Second-stage modules:** `init.openbook.rc` runs `/vendor/bin/modprobe -b --all=/vendor/lib/modules/modules.load` synchronously at early-init, in AOSP's `vendor_modprobe` domain, which our policy extends to `system_dlkm` (the GKI dependencies come through `modules.dep`). In QEMU it loads 144 modules and exits 1, because `asus-nb-wmi` returns -ENODEV without the ASUS WMI GUID, as in ANAL-198.
- **Firmware:** `firmware.mk` installs the subset to `/vendor/firmware`, which gets its own label so the kernel may read it directly. **AOSP 17 imports nine MediaTek MT7921/MT7922/MT7925 files itself** (`external/linux-firmware`, linux-firmware `0d347a3f`, 2026-04-23), and Soong owns those paths. The product takes AOSP's modules for them and drops ANAL-198's newer copies (`38c1a709`, 2026-10), which differ byte for byte. ANAL-179 decides whether MT7925 needs the newer ones.

## HALs

| HAL | Implementation | Backend | In QEMU |
|---|---|---|---|
| health | **OpenBook** `android.hardware.health-service.openbook` (AOSP's `libhealth_aidl_impl` plus ANAL-178's subclass) | real: `/sys/class/power_supply` (ACPI battery, AC, UCSI); charge counter from `charge_now`, state of health and GOOD/FAIR from `charge_full`/`charge_full_design` where the kernel reports none | runs; "No battery devices found" |
| boot control | AOSP `com.android.hardware.boot` | real: `misc` partition | initialised `misc` on first boot |
| lights | **OpenBook** `android.hardware.lights-service.openbook` | the panel backlight: firmware > platform > raw, so `amdgpu_bl1` (raw, max 400000) in Optimus/Integrated mode and `nvidia_wmi_ec_backlight` (firmware) in a dGPU MUX mode. The keyboard backlight is the N-KEY's input light (`.idc`) | no backlight: reports no lights |
| power | **OpenBook** `android.hardware.power-service.openbook` | amd-pstate EPP per cpufreq policy: screen off → `power`, battery saver → `balance_power`, launch or fixed performance → `performance`, else the boot value. Never touches `platform_profile` or asus-wmi, which persist in firmware | no amd-pstate in the VM: modes accepted, nothing written |
| power stats | **OpenBook** `android.hardware.power.stats-service.openbook` | s2idle hardware-sleep (S0i3) residency from `/sys/power/suspend_stats`; no energy meters (no RAPL powercap in our kernel) | no hardware sleep reported: no entities |
| thermal | **OpenBook** `android.hardware.thermal-service.openbook` | thermal zones and their trip points (passive → SEVERE, hot → CRITICAL, critical → SHUTDOWN), hwmon (amdgpu, NVMe, Wi-Fi), battery; cooling devices; 5 s polling for callbacks. ACPI zones stay `UNKNOWN` (no SKIN) until measured on the laptop | no zones: empty lists, HAL ready |
| USB / Type-C | AOSP `android.hardware.usb-service.example` | real: `/sys/class/typec` (UCSI), role swaps | no Type-C ports |
| KeyMint | AOSP `com.android.hardware.keymint.rust_nonsecure` | **software, no TEE, no hardware attestation**; root of trust from bootconfig (orange) | keys generated; vold metadata key falls back to non-rollback-resistant, as expected |
| Gatekeeper | AOSP `com.android.hardware.gatekeeper.nonsecure` | **software** | PIN set and verified, also after reboot |
| Weaver | **OpenBook** `android.hardware.weaver-service.openbook` | **software, file-backed** (`/data/vendor/weaver`, libgatekeeper's throttling schedule). AOSP's example Weaver keeps slots in RAM, so a reboot would lock the user out. This adds no protection over plain Android | 2 slots written; read back after reboot |
| audio | AOSP `com.android.hardware.audio` + `pc/audio/audio_policy_configuration.xml` | example HAL: primary, remote submix, Bluetooth modules | all three `IModule` instances registered |
| graphics | ANAL-174's graphics-amd (minigbm, drm_hwcomposer, Mesa RADV/radeonsi, ANGLE) | amdgpu, picked at boot | `hal=virtio` fallback (below) |
| authsecret, memtrack, dumpstate | AOSP APEXes | — | registered |

Wi-Fi and Bluetooth HALs are not in the product (ANAL-179). Each OpenBook HAL's logic is plain C++ with a sysfs root, tested on fixture trees: `hals/tests/hals_test.cpp` (G14 backlight, EPP on 24 policies, ACPI zones and amdgpu hwmon, Weaver persistence and throttling).

## Graphics

- **AMD (the G14):** unchanged from ANAL-174. The probe sees amdgpu (or the unbound `1002:*` display controller) at early-init and selects radv/angle/minigbm/drm. This product is the first to build `graphics-amd/sepolicy/platform`; three rules were missing and are added there: the `mapper/minigbm` service label, every process's access to the allocator's metadata memfds, and `mlstrustedobject` on them for apps (see below).
- **Fallback for GPUs no OpenBook driver handles (VMs):** when the probe reports `hal=virtio`, `init.openbook.rc` loads `virtio_pci` (a GKI module in `system_dlkm`), `virtio-gpu` and `virtio_input`, and selects SwiftShader Vulkan under ANGLE, minigbm and drm_hwcomposer. SwiftShader JIT-compiles, so `sepolicy/swiftshader` grants `execmem` to surfaceflinger, system_server, zygote and bootanim, as Cuttlefish does. `OPENBOOK_SOFTWARE_GPU_FALLBACK := false` in a board config drops that policy. **On the G14 the four domains carry `execmem` they never use;** a release image should switch it off.

## Input and display

- `Vendor_0b05_Product_19b6.idc` (N-KEY, USB): `keyboard.builtIn = 1`, `device.internal = 1`, and the keyboard backlight through `device.additionalSysfsLedsNode = /sys/class/leds/asus::kbd_backlight`. With the internal touchpad this is what lets WM Shell switch the panel to desktop mode without the testing property (`docs/aosp-desktop.md`).
- `Vendor_0b05_Product_19b6.kl`: AOSP's `Generic.kl` plus the four keys hid-asus sends as `KEY_PROG1..4` (ROG key, Fn+C, Fn+Space, Fn+F5), mapped to `MACRO_1..4`.
- `Vendor_04f3_Product_3315.idc` (ELAN, I2C HID): `device.internal = 1`. On the G14 InputReader classes it `TOUCHPAD`, so the gestures-library mapper drives it (live-001); gesture tuning waits for measurements (`docs/power-input.md` §2).
- `Asus_WMI_hotkeys.kl` (ANAL-178): the firmware's WMI hotkeys (asus-nb-wmi, no USB IDs) get a layout by device name: `Generic.kl` plus `KEY_PROG1..4` → `MACRO_1..4` and the screenshot key.
- **Density:** `ro.vendor.openbook.lcd_density=240` for the 14" 2880×1800 panel (243 ppi), giving a 1920×1200 dp desktop, overridable per boot with `androidboot.lcd_density`.

## dGPU

- `dgpu-power-check` (ANAL-187's `scripts/dgpu-power-check.sh`, linked into the device tree and copied by `aosp-build.sh`) is in the userdebug image. In QEMU: `WARN: absent-unknown`, exit 2, as expected without ASUS WMI or ACPI power resources.
- **Fallback hook** (`openbook-pc-setup dgpu-pm`, early-init, root, its own domain): when an NVIDIA function is enumerated and its display function has no driver, it unbinds `snd_hda_intel` from the dGPU's HDMI-audio function, sets `power/control=auto` on every dGPU function, and gives `snd_hda_intel` `power_save=10`. Without vga_switcheroo the HDA controller never runtime-suspends while bound, so unbinding is what lets the root port reach D3cold (`docs/nvidia.md`). It never touches asus-wmi. It does nothing when a driver binds the GPU.
- **Tested with fake devices:** `scripts/openbook-pc-setup-test.sh` builds the G14's sysfs for three cases (dGPU enumerated and unbound, `dgpu_disable=1`, nouveau bound) plus the EPP step. It passes 14/14 on the host and 14/14 inside QEMU on the image's own mksh and toybox (installed as `openbook-pc-setup-test` in userdebug). QEMU cannot emulate a `10de:*` device. On the real QEMU sysfs the hook reports "no NVIDIA GPU enumerated".
- **nouveau stays out:** no module list contains it. minigbm and drm_hwcomposer only open devices with a backend they know, which is amdgpu or virtio_gpu.

## SELinux

Enforcing in every run. `sepolicy/vendor` labels the boot disk's partitions (the boot partitions' entries typed `-b`: second-stage init may relabel early-mount links only to a few types), the firmware, the HAL binaries, `/data/vendor/weaver`, and sysfs by class directory (`/sys/devices/.*/power_supply`, backlights, `leds` and keyboard backlights, `hwmon*`, `typec`, `wakeup*`, HID `country`, and the APU's PCI identity as `sysfs_gpu`), because ACPI and PCI paths differ between laptops. ueventd restorecons each device's directory when it appears. Remaining denials in the final QEMU boot (`qemu/boot1/sections/avc.txt`), none blocking: the audio HAL writing a tmpfs memfd (9), SystemUI reading `bluetooth_lea_prop` (2), `init` writing a block queue attribute (1), `keystore` finding Gatekeeper's `ISharedSecret` (1; AOSP forbids granting it), and the test shell itself (1). The G14's own denials are reviewed above.

## What QEMU found

Each of these stopped the boot, and none is specific to the VM except where marked.

| Run | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `/data` read-only, compressed APEXes not activated, `reboot … netbpfload-missing` | AOSP's `init.rc` mounts nothing: the device rc must call `mount_all --early`/`--late` | `init.openbook.rc` |
| 1 | software Gatekeeper aborts | its `ISharedSecret/gatekeeper` instance had no service label | `service_contexts` |
| 1 | boot HAL denied the slot partitions | init may not relabel early-mount links to `boot_block_device` | `-b` entries |
| 2 | allocator exits 1, SurfaceFlinger loops (VM) | `virtio_pci`, the transport, is a GKI module nobody loaded | load it in the fallback |
| 2 | init log lines missing | the kernel rate-limits `/dev/kmsg` | `printk.devkmsg=on` on the console entry |
| 3 | SurfaceFlinger: `gralloc-mapper is missing` | `mapper/minigbm` had no service label in graphics-amd's platform policy | label added |
| 4 | SurfaceFlinger: `output buffer not gpu writeable` | the allocator's metadata memfds carry its tmpfs type on this kernel; importers were denied | access for all buffer users |
| 5 | SurfaceFlinger SIGSEGV in SwiftShader (VM) | `execmem` denied | `sepolicy/swiftshader`, switchable |
| 6 | `system_server` watchdog loop at `AudioSystem.setLowRamDevice` | no `audio_policy_configuration.xml`: the audio HAL created no `IModule/default` | policy configuration |
| 7 | same loop, now at `IModule/bluetooth` | the audio APEX declares `bluetooth` too; audioserver waits for every declared module | primary + r_submix + Bluetooth, as Cuttlefish |
| 8 | apps denied writing buffer metadata | MLS: apps (`s0:cX,cY`) may only write `mlstrustedobject` types | `typeattribute … mlstrustedobject` |

Also found: **AMD laptops get no hardware RNG from the TPM.** `tpm_crb` disables its hwrng on AMD CPUs unless the TPM2 table's start method is Pluton (AMD advisory PA-410). The G14's own Linux logs `tpm_crb_acpi MSFT0101:00: Disabling hwrng` (inventory `root/dmesg.txt.gz`), and so does QEMU. Android's `prng_seeder` then gives up. It drops its listening socket first, so BoringSSL falls back to `getrandom()` and nothing blocks (checked in `prng_seeder` and BoringSSL's `passive.cc`).

## Commands

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

`tools/Dockerfile.installer` gains the QEMU virtio display modules and swtpm (same QEMU 11.1.2, OVMF 202608, systemd 262 as ANAL-189). `qemu-run.py` gains `--gpu`, `--usb-input`, `--tpm` and `{"shot": …}` steps.

## Open items

- **The G14 boot itself** (ANAL-176, with ANAL-190's live stick): amdgpu at second stage with firmware from `/vendor/firmware`, the probe's `hal=amdgpu`, RADV/ANGLE on gfx1150, drm_hwcomposer on DCN 3.5, backlight and EPP through the HALs, touchpad and N-KEY classification, the root ports in `boot_devices`.
- **Thermal types.** ACPI zones `THRM` and `TZ01` stay `UNKNOWN`. `k10temp` is built and loads on the G14 (live-001, `00:18.3` in runs 2–7). `TZ01` reads a constant 20 °C; pick a SKIN sensor once measured under load (`docs/power-input.md` §3).
- **No Wi-Fi or Bluetooth HAL, no `regulatory.db`** (ANAL-179), and the MT79xx firmware version choice above.
- **The SwiftShader `execmem` grant** ships on by default; switch it off for release images.
- **The VM display** stays on the boot-animation frame after `boot_completed` (VM-only; parked by the owner).
- **Recovery and fastbootd** are not in the product (`TARGET_NO_RECOVERY`): OTA through update_engine works without them; sideload and a recovery UI need a decision with the installer (ANAL-190/191).
- **Keystore and Gatekeeper's shared secret:** AOSP forbids keystore from finding a `hal_gatekeeper_service`; PINs work, but the Gatekeeper instance takes no part in the shared-secret negotiation. An AOSP-conformant label for that instance is still to be found.
- **Image size.** `super` is 8 GiB and the image 12 GiB; the live stick shrinks `super` to its contents (ANAL-190).
