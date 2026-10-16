# Kernel: reproducing the Googlebook OS GKI build

Status as of 2026-10-15 (ANAL-170). Every claim below has a log or a report in `evidence/2026-10-15-kernel/`. Guesses are labelled **HYPOTHESIS**.

## Results

- **Googlebook OS ships the public GKI kernel, unmodified.** The ruby `boot_a` kernel (from M0) is byte-identical to the `bzImage` of ci.android.com build **16302624**, target `kernel_x86_64`, branch `aosp_kernel-common-android17-6.18-2026-06`. Both have sha256 `7816c5d5…7f41`. The shipped `.config` is also byte-identical to that build's `kernel_x86_64_dot_config`: sha256 `046971f3…be40` (`repro-gbos-16302624-ab16302624-vs-ci.txt`).
- **The branch.** `kernel/manifest` `common-android17-6.18` exists; it is the development tip. The shipped kernel comes from the monthly GKI release branch **`common-android17-6.18-2026-06`**. CI published that build's repo manifest, which is now `manifests/kernel/gbos-16302624.xml`. It pins `common` at `3938c8d97142d5cf31543aa96f864a2cf832dda0` and `build/kernel` at `5877a401…`.
- **Is `3938c8d97142` reachable?** Yes from `android17-6.18-2026-06`. No from the `android17-6.18` tip and no from `android17-6.18-2026-09` (`common-provenance-*.txt`).
  - It sits 330 commits past the merge-base with `android17-6.18` (`0a24e2b8d9a0`, 2026-06-01). Most of those are backports: pKVM GSMI mediation, fuse-bpf fixes, LTS picks.
  - The `-2026-06` branch is now 80 commits past the shipped SHA.
- **Our local Kleaf build matches.** We built from the pinned manifest with `tools/bazel run --config=stamp //common:kernel_x86_64_dist`:
  - The `.config` is byte-identical to the shipped one.
  - `vmlinux.symvers` (KMI CRCs), `abi_symbollist`, `modules.builtin` and `system_dlkm.modules.load` are identical to CI's.
  - The default build has release string `6.18.21-android17-5-g3938c8d97142`. CI appends `-ab16302624` because it sets `BUILD_NUMBER`.
  - We ran one comparison build with `BUILD_NUMBER=16302624`, for measurement only. It was never published or flashed. In that build `System.map` is identical, and the decompressed `vmlinux` differs from Google's in **1,098 of 62,561,848 bytes**:
    - 1,078 bytes in `system_certificate_list`, the module-signing certificate each build generates;
    - 20 bytes of GNU build ID.
  - Everything else, including code, data and layout, is bit-for-bit the same.
- **Config diff: Google turned nothing on or off beyond `gki_defconfig`.** Our build from `gki_defconfig` alone gives the shipped config: 0 symbols differ, and all 749 `gki_defconfig` lines stick. `//common:kernel_x86_64` uses no defconfig fragments (`common/BUILD.bazel:323`), and CI passed no `--gki_build_config_fragment`.
  - **`CONFIG_PKVM_INTEL=y` is set in the GKI defconfig.** It is `gki_defconfig:100`, added by `002e9fb54954` "ANDROID: GKI: x86: Enable pKVM support on Intel" (2026-02-14). It only compiles pKVM in. The hypervisor starts only with `kvm-intel.pkvm=1`, which Googlebook's vendor cmdline sets. pKVM exists only for Intel VMX (`arch/x86/kvm/pkvm/`); `arch/x86/kvm/svm/` has no pKVM code.
  - **`CONFIG_X86_FRED=y` is in neither the defconfig nor a fragment.** It is selected by `KVM_INTEL` (`arch/x86/kvm/Kconfig:99`, `select X86_FRED if X86_64`). That line comes from upstream Linux commit `28d11e4548b7` "x86/fred: KVM: VMX: Always use FRED for IRQs when CONFIG_X86_FRED=y". `gki_defconfig:99` sets `KVM_INTEL=y`. FRED needs CPU support. The Ryzen 9 7950X doesn't advertise it (no `fred` flag in `/proc/cpuinfo`), so on that CPU the code is compiled in but the hardware path stays unused, even with `fred=on` on the cmdline.
- **It boots.** Our bzImage boots under QEMU/KVM `-cpu host` on the Ryzen 9 7950X with Googlebook's ramdisks (`boot-summary.txt`):
  - Version line `Linux version 6.18.21-android17-5-g3938c8d97142`.
  - The same 31 services start as with the stock kernel, and boot stalls at the same `keystore2` point (blocker 1 in `docs/PLAN.md`).
  - There were no `invalid opcode` traps and no panic.
- **Google's GKI modules don't load on our kernel.** `rust_binder` and `zsmalloc` from the shipped image fail with `Unresolved symbol … (err -13)`:
  - Each build trusts only its own signing key. Under `MODULE_SIG_PROTECT`, a GKI module signed by another build counts as unsigned, and unsigned modules can't use protected symbols. Init falls back to the built-in C binder.
  - Google's vendor modules (`pinctrl-intel`, `i2c-i801`, `intel_rapl_msr` and others) do load. They are unprotected, and their KMI CRCs match.
  - So **boot, `system_dlkm` and our own vendor modules must ship from the same build.** This confirms `docs/PLAN.md`.
- **The tip moved on.** `android17-6.18` at `70a231d0d37b` (2026-10-15) is Linux 6.18.32 and builds as `6.18.32-android17-5-g70a231d0d37b`.
  - Its config differs from the shipped one in 15 symbols: 8 new `gki_defconfig` lines (`ANDROID_WRAPFD`, `CGROUP_FAVOR_DYNMODS`, `EFIVAR_FS`, `HID_HAPTIC`, `NET_APF`, `NINTENDO_FF`, `PAGE_PINNER`, `SW_SYNC`) plus symbols derived from them.
  - None of the 4,038 symbols on the shipped KMI list changed CRC or disappeared. The 10 changed and 3 removed exports are Rust `kernel`-crate symbols outside the list (`kmi-shipped-vs-android17-6.18-tip.txt`).

## Build steps

Host requirements: Docker, with no sudo. `tools/Dockerfile.kernel` is Ubuntu 24.04 with repo, git and python3. Kleaf brings its own clang 22.0.1, Rust, Bazel and build tools from the synced prebuilts.

```bash
scripts/kernel-sync.sh                      # default target gbos-16302624: the exact shipped sources
scripts/kernel-sync.sh android17-6.18       # or the branch tip (any kernel/manifest common-<X> works)
scripts/kernel-build.sh                     # -> ~/anybook/kernel/dist/<target>/
BUILD_NUMBER=16302624 scripts/kernel-build.sh   # comparison only: same release string as Google's CI build

scripts/kernel-fetch-ci.sh 16302624         # Google's public CI artifacts -> ~/anybook/kernel/ci/16302624/
scripts/kernel-compare.py ~/anybook/kernel/dist/gbos-16302624-ab16302624 ~/anybook/kernel/ci/16302624 \
    ~/anybook/work/gbos-ruby/boot_a/kernel  # artifact identity, System.map, vmlinux byte attribution
scripts/kernel-config-diff.py ~/anybook/kernel/dist/gbos-16302624/dot_config \
    evidence/2026-10-15-m0/gbos-kernel-config.txt \
    ~/anybook/kernel/src/common/arch/x86/configs/gki_defconfig ~/anybook/kernel/src/common
scripts/kernel-kmi-diff.py OLD/vmlinux.symvers NEW/vmlinux.symvers OLD/abi_symbollist
scripts/kernel-boot-test.sh ~/anybook/kernel/dist/gbos-16302624/bzImage   # needs M0's unpacked ruby image
```

- **How the scripts run.** `kernel-sync.sh` and `kernel-build.sh` re-run themselves inside the `anybook-kernel` container through `scripts/kernel-docker.sh`. That builds the image on first use. It mounts `~/anybook/kernel` and `~/anybook/logs/kernel` at the same paths, and uses `~/anybook/kernel/home` as `HOME`.
- **Long steps.** Set `KERNEL_DETACH=<name>` to run a step as a detached container, so it survives a shell timeout. Collect it with `docker wait <name>; docker rm <name>`.
- **Resuming.** Both scripts can be rerun after an interruption. `repo sync` resumes, and Bazel keeps its action cache in `src/out`.
- **Layout.** One source tree: `~/anybook/kernel/src`. Switching targets is a `repo init` plus sync, which takes seconds once the objects are present. `src/.anybook-target` names the current target.
- **Pins.** `~/anybook/kernel/pins/<target>.xml` holds the `repo manifest -r` of what was synced. Each dist dir records it again, together with `common-provenance.txt`, `linux_banner.txt`, `dot_config` (the IKCONFIG extracted from the built bzImage), `build-time.txt` and `sha256.txt`.
- **Dist contents.** Each `dist/<label>/` holds `bzImage`, `vmlinux`, `boot.img`, `system_dlkm.*.img`, 100 GKI modules, `abi_symbollist`, `vmlinux.symvers`, `kernel-headers.tar.gz` and DDK archives. That is 613 MB per build.
- **googlesource rate limiting.** It answered HTTP 503 during the second sync. The sync retries with backoff; `SYNC_JOBS=2` got through.

### Timings and resources (Ryzen 9 7950X, 32 threads, 61 GB RAM)

| Step | Wall time | Notes |
|---|---|---|
| `kernel-sync.sh gbos-16302624`, cold | 597 s | 44 GB tree, `-j8` |
| `kernel-sync.sh android17-6.18` after that | 83 s | incremental, `-j2` |
| `kernel-build.sh` gbos-16302624, cold Bazel cache | 337 s | 1,412 actions; critical path 324 s, almost all of it the single `Building kernel (trim)` action |
| `kernel-build.sh` gbos-16302624 with `BUILD_NUMBER=16302624` | 431 s | 18 actions; the stamp change reruns the kernel action |
| `kernel-build.sh` android17-6.18 | 307 s | 35 actions |

- **For comparison:** Google's CI spent 785 s on `kernel_x86_64_abi_dist` plus tests, 1,966 actions (`logs/build.log` of build 16302624). That is a bigger target than ours.
- **Disk:** the source tree is 53 GB with both targets fetched (`.repo` 22 GB, `prebuilts` 19 GB). The Bazel cache in `src/out` is 8.7 GB, plus 0.6 GB per dist.
- **RAM:** peak use was not measured. GNU time only sees the Bazel client. The host had about 44 GB available throughout, with no swapping noticed.
- **Sandbox:** Bazel used `processwrapper-sandbox`, because linux-sandbox's namespaces are not available in Docker's default profile. CI used `linux-sandbox`. The outputs still match.
- **Benign warnings:** `diff: Unknown option 'I'` warnings in `modules_prepare` come from the hermetic toybox `diff`. They appear in Google's CI log too, 24 times.

## KMI symbol list (for the AMD stage)

- **Location.** The lists live in `common/gki/x86_64/symbols/`. At 3938c8d97142 these are:
  - `base` (5 lines)
  - `desktop` (3,725), the list Googlebook's Intel vendor modules use; the tip has 3,803
  - `kunit` (41)
  - `virtual_device` (1,341)

  The build merges them into `dist/abi_symbollist`. The ABI definition is `common/gki/x86_64/abi.stg`, with approved breaks in `abi.stg.allowed_breaks`.
- **Wiring.** `common/BUILD.bazel` sets the following on `kernel_x86_64`:
  - `kmi_symbol_list = "gki/x86_64/symbols/base"`
  - `additional_kmi_symbol_lists = [":x86_64_additional_kmi_symbol_lists"]`, a filegroup listing `desktop`, `kunit` and `virtual_device`
  - `trim_nonlisted_kmi = True`, which is `CONFIG_TRIM_UNUSED_KSYMS`
  - `kmi_symbol_list_strict_mode = True`
  - `kmi_enforced = True`

  Only listed symbols are exported. That is why an out-of-tree amdgpu cannot load on the stock kernel.
- **How to extend it:**
  1. Create `common/gki/x86_64/symbols/anybook_amd` and add it to the `x86_64_additional_kmi_symbol_lists` filegroup.
  2. Generate its contents from the real modules rather than by hand. The model is `virtual_device_x86_64` plus `virtual_device_x86_64_abi` in `common-modules/virtual-device/BUILD.bazel`:
     - Define a device `kernel_build` with `base_kernel = "//common:kernel_x86_64"` and `kmi_symbol_list = "//common:gki/x86_64/symbols/anybook_amd"`.
     - Add a `kernel_abi` whose `kernel_modules` are the AMD modules: amdgpu, pinctrl-amd, amd_pmc, the ACP/SOF drivers and others.
     - Run `tools/bazel run //<pkg>:<name>_abi_update_symbol_list` (Kleaf docs: `build/kernel/kleaf/docs/abi_device.md`).
  3. Rebuild the GKI with `scripts/kernel-build.sh`, so the new symbols are exported. Then refresh the ABI with `tools/bazel run //common:kernel_x86_64_abi_update` and check it with `//common:kernel_x86_64_abi_dist`, which is what CI runs. Adding symbols only adds exports, so existing vendor modules keep loading. Changing an exported struct is a KMI break and needs an entry in `abi.stg.allowed_breaks`.
  4. For quick experiments only: `tools/bazel run --notrim //common:kernel_x86_64_dist` turns off trimming and exports everything.
- **Release string.** With `CONFIG_MODVERSIONS`, `same_magic()` (`kernel/module/version.c:97`) skips the release-string part of vermagic. Modules therefore load across builds with different `-g<sha>`/`-ab<N>` suffixes, as long as the CRCs match. The boot test shows this for Google's vendor modules.

## Open issues

- **Signing key.** Our GKI cannot load Google-signed GKI modules, so the next stage must install our `system_dlkm` too. For M1a/M3, that means rebuilding `super`'s `system_dlkm_a` or overlaying it, and that is not done yet. **HYPOTHESIS:** once `system_dlkm` matches the kernel, boot behaves exactly like the stock kernel. ANAL-172 tested this in Cuttlefish with the AnyBook build: with its own `system_dlkm`, Android 17 boots to `boot_completed` with timings close to the stock 6.12 kernel's (see [Booting in Cuttlefish](#booting-in-cuttlefish-with-our-aosp-17-userspace-anal-172)).
- **Release-branch choice.** Track B KMI compatibility favours staying on `android17-6.18-2026-06` at the shipped SHA, or on a later monthly release branch. For new AMD features, the tip (6.18.32) or `android-mainline-desktop` is better. The AMD fragment should be checked against both.
- **Unconfirmed upstream version.** `28d11e4548b7` is upstream (no `ANDROID:` prefix) and in mainline before the `android-mainline-6.18` tag. We did not confirm which Linux release first shipped it.

## AMD laptop enablement (ANAL-171)

Status as of 2026-10-16. Evidence is in `evidence/2026-10-16-kernel-amd/`. Guesses are labelled **HYPOTHESIS**. **Nothing here has run on AMD laptop hardware yet.** The load test below ran under QEMU/KVM on the Ryzen 9 7950X host.

### Results

- **The build works.** `//devices/anybook:anybook_amd_x86_64_dist` builds on the shipped tree (target `gbos-16302624`, `common` 3938c8d97142 plus 3 AnyBook patches, which gives `44a90255c95f`).
  - Release string: `6.18.21-android17-5-g44a90255c95f`.
  - The dist holds `bzImage`, `boot.img`, the `system_dlkm` images with the 100 GKI modules signed by this build's key, and **138 vendor modules**.
  - A full rebuild of the GKI plus all vendor modules took 996–1,178 s. An AOSP build was loading the host at the same time (load average 50–100). Without that load, the GKI alone took 337 s in ANAL-170.
- **vermagic and modinfo match the kernel** (`modules-check.md`, `modinfo-selected.txt`). Every one of the 138 vendor modules:
  - has vermagic `6.18.21-android17-5-g44a90255c95f SMP preempt mod_unload modversions`, the same as the kernel and the GKI modules;
  - reports `intree: Y`;
  - has every `__versions` CRC equal to `vmlinux.symvers`;
  - resolves every import from vmlinux, a GKI module or another vendor module;
  - imports from vmlinux and GKI modules only symbols on the KMI list. That matters because the vendor modules are unsigned, so under `MODULE_SIG_PROTECT` they may use KMI-listed symbols only.
- **The modules load on the running kernel** (`modload-summary.txt`, full serial log `modload-kvm.log.gz`). Setup: our `bzImage` boots under QEMU/KVM on a q35 machine with an emulated AMD IOMMU, virtio-gpu and virtio input, with a busybox initramfs that runs `modprobe` on each vendor module.
  - **137 modules load. 1 returns -ENODEV:** `asus-nb-wmi`, because QEMU has no ASUS WMI GUID.
  - **0 errors** of any kind: symbol, CRC, format or signature. 144 modules are live afterwards, and the taint flag is 0.
  - The built-in AMD IOMMU starts: `AMD-Vi: Interrupt remapping enabled`.
  - virtio-gpu binds to the emulated device: `[drm] Initialized virtio_gpu 0.1.0 for 0000:00:04.0 on minor 0`, which creates `card0` and `renderD128`. virtio input binds too.
  - The VM has no AMD GPU, NPU, Wi-Fi or audio hardware. amdgpu, amdxdna, mt7925e, the HDA driver and the rest load and register their drivers, but probing on real hardware is untested.
- **Symbol list.** `common/gki/x86_64/symbols/anybook_amd` holds 1,887 symbols, generated by Kleaf (`anybook_amd_x86_64_abi_update_symbol_list`). Of those, 1,673 are already on the stock KMI list, and **214 are new** (`symlist-diff.md`, `anybook_amd-added-symbols.txt`).
  - 199 of the new ones are vmlinux exports. The other 15 were already exported by GKI modules such as `bluetooth.ko` and are now listed.
  - **amdgpu alone imports 129 symbols the stock GKI does not export.** GBRUNCH reported 131. **HYPOTHESIS:** the gap of 2 comes from a different kernel release or config.
  - 22 of the 138 modules need at least one new export. After amdgpu: amdxdna needs 25, asus-wmi 16, ACPI thermal 13 and amd-pmc 10.
- **The KMI is unchanged for existing symbols** (`kmi-stock-vs-anybook-amd.txt`). Comparing stock `vmlinux.symvers` with ours: 0 CRCs changed, 0 symbols removed, 199 added. Every one of the 4,038 entries on the stock KMI list keeps its CRC. **HYPOTHESIS:** modules built for the stock GKI would therefore also load on this kernel. That is untested; it is relevant to Track B.
- **The vendor fragment changes no GKI value.** `scripts/kernel-config-check.py` compares the device `.config` with the GKI `.config` and finds:
  - 147 new modules;
  - 35 new options that only the new modules read, such as `DRM_AMD_DC=y` and `BT_HCIBTUSB_MTK=y`;
  - 6 build-only symbols that Kleaf sets for mixed builds;
  - **0 GKI values changed** (`config-check.md`).
- **Equivalence build: vmlinux differs in 5 places, all harmless** (`equivalence-gki-vs-gki-plus-fragment.txt`). The check rebuilds the GKI with the vendor fragment applied on top, then compares it symbol by symbol with the real GKI. Built-in code can test a vendor option with `IS_ENABLED(CONFIG_X)`, which no `.config` comparison shows. The vendor modules are compiled with the option, and the shipped vmlinux without it.
  - `vmlinux.symvers`, `abi_symbollist` and `modules.builtin` are identical, so no exported interface or CRC changes.
  - 79 of 80 `system_dlkm` modules are identical once the signature, build ID and `.BTF` are dropped. `.BTF` is split BTF whose type IDs follow vmlinux. The 80th, `kheaders.ko`, embeds the config, so its `.rodata` and allocation-tag section differ.
  - The 5 vmlinux differences are listed in [Equivalence differences](#equivalence-differences). Adding the card reader and backlight modules after the inventory added no new ones. Each is the same pattern Google's own Intel vendor build has, since that build ships `i2c-smbus.ko`, `snd-ctl-led.ko`, `snd-hda-intel.ko` and HID vendor modules too.
- **Firmware subset: 131 files, 52.5 MB, all redistributable** (`firmware-subset.md`, `firmware-subset.tsv`). Source: linux-firmware `38c1a709` (2026-10-16). Each file's licence is recorded from WHENCE. Details are in [Firmware](#firmware-subset).

### Checked against the GA403WR inventory

On 2026-10-16 the owner ran `scripts/hw-inventory.sh` on the laptop (`evidence/2026-10-16-ga403wr-inventory/SUMMARY.md`). **The board is a GA403WR, not the GA403WP assumed before.** Every device it lists has a driver in this kernel, and the inventory changed three things:

- **Audio quirk backported.** The codec is an ALC285 with SSID 1043:1024. The 6.18 tree had no entry for it; mainline commit cbd46cbc5470 adds one, and patch 0002 carries it. The built `snd-hda-codec-alc269.ko` contains the 1043:1024 table entry. The internal mic is on the HDA codec, not on ACP.
- **Card reader added.** The Realtek RTS525A needs `rtsx_pci`, `rtsx_pci_sdmmc` and, through them, `mfd-core`.
- **Backlight module added.** `nvidia-wmi-ec-backlight` is loaded on the laptop under Linux. Our built-in `video_detect.c` would choose it when the EC owns brightness, so without the module there could be no backlight device. Which backlight is actually active still needs `ls /sys/class/backlight` from the laptop.

Already matched without changes:

| Inventory | Our kernel |
|---|---|
| NPU rev 10 | `17f0_10` firmware |
| MT7925 Wi-Fi and Bluetooth `0489:e11e` | the btusb table has that ID |
| ELAN I2C HID touchpad on AMDI0010 | i2c-designware and i2c-hid-acpi |
| ASUS N-KEY keyboard `0b05:19b6` | hid-asus |
| 2× CS35L56 amps (`CSC3556`) | serial-multi-instantiate and cs35l56-hda |
| `MSFT0101` TPM | tpm_crb |
| UCSI | ucsi_acpi |
| UVC webcam, NVMe, USB4 | already in the GKI |

Not covered:
- `AMD_HFI` (`AMDI0104`, Zen 5/Zen 5c core ranking). It is bool, so it would be a fourth built-in.
- amd-pmf, which the laptop does use under Linux. It is blocked, see below.

### Layout

The AnyBook kernel is the shipped GKI tree plus the following. `scripts/kernel-amd-apply.sh` puts everything in place. It can be rerun after every `kernel-sync.sh`, because `repo sync` resets `common` to the pin.

| Path in this repo | Goes to | What it is |
|---|---|---|
| `kernel/patches/common/0001-…` | commit on `common` | 3 built-in options in `gki_defconfig` (see [Deviations](#deviations-from-gki)) |
| `kernel/patches/common/0002-…` | commit on `common` | Backport of mainline cbd46cbc5470, the ALC285 quirk for the G14 2025 (codec SSID 1043:1024). It only changes `snd-hda-codec-alc269.ko`, a vendor module |
| `kernel/patches/common/0003-…` | commit on `common` | `gki/x86_64/symbols/anybook_amd`, added to `x86_64_additional_kmi_symbol_lists` |
| `kernel/devices/anybook/BUILD.bazel` | `devices/anybook/` | Kleaf mixed build: `kernel_build` with `base_kernel = //common:kernel_x86_64`, plus `kernel_abi`, `kernel_modules_install` and dist |
| `kernel/devices/anybook/anybook_amd.fragment` | `devices/anybook/` | the vendor-module fragment (`post_defconfig_fragments`); Kleaf checks every line after `olddefconfig` |
| `kernel/firmware/anybook-amd.rules` | — | which linux-firmware files the modules need |

`git am` runs with a fixed committer and date, and keeps each patch's author, including the upstream author of the backport. So the patched SHA, and with it the `-g<sha>` release string, is the same on every machine.

### Deviations from GKI

The GKI rules allow vendor modules and partner symbol lists. Anything else in vmlinux is a deviation. AnyBook has three, all bool options that upstream does not offer as modules:

| Change | Why it cannot be a module | Effect on the GKI |
|---|---|---|
| `CONFIG_AMD_IOMMU=y` | bool. DMA and interrupt remapping on AMD; `DRM_ACCEL_AMDXDNA` depends on it; USB4/Thunderbolt DMA protection needs an IOMMU. The x86 GKI already has `INTEL_IOMMU=y` | Adds `IOMMU_IO_PGTABLE=y`. Everything else it selects (`PCI_MSI`, `PCI_ATS/PRI/PASID`, `IOMMU_SVA/IOPF`, `MMU_NOTIFIER`, `IRQ_MSI_LIB`) was already `y` |
| `CONFIG_PINCTRL_AMD=y` | bool upstream. The AMD GPIO controller (AMDI0030) supplies the I2C HID touchpad interrupt and many ACPI GPIO events | GPIO driver only |
| `CONFIG_X86_AMD_PLATFORM_DEVICE=y` | bool. Adds the AMD ACPI IDs (AMDI0010 I2C, AMDI0020 UART, …) to `drivers/acpi/acpi_apd.c`, which gives the DesignWare I2C controller its clock. The Intel counterpart `X86_INTEL_LPSS=y` is already set | Table entries and clock setup in `acpi_apd.c` |
| `anybook_amd` KMI list | Part of the normal GKI process: partners send symbol lists to ACK. AnyBook keeps it local | +214 KMI entries, 199 of them new vmlinux exports; no existing CRC changes |

`gki_defconfig` also loses its explicit `CONFIG_PCI_MSI=y` and `CONFIG_GPIOLIB=y` lines. AMD_IOMMU and PINCTRL_AMD now select them, so `savedefconfig` drops the lines, which Kleaf requires. Both values stay `y`. The resulting `.config` differs from the shipped one in 5 symbols (`config-diff-anybook-gki-vs-shipped.md`): the 3 options above, `IOMMU_IO_PGTABLE`, and `DRM_ACCEL_AMDXDNA` going from absent to visible-but-unset.

### The AMD fragment

Everything below is `=m` unless stated otherwise. The 138 module files it produces are listed in `vendor-modules.txt`.

| Area | Options | Why |
|---|---|---|
| GPU | `DRM_AMDGPU`, `DRM_AMD_DC=y`, `DRM_AMDGPU_USERPTR=y`; SI, CIK, ACP, secure display off; `HSA_AMD` (KFD) off | Radeon 890M (gfx1150, DCN 3.5) and other RDNA 2/3 APUs. DC is needed for the display. Android does not use KFD, and `HSA_AMD_SVM` would need `ZONE_DEVICE` in vmlinux. amdgpu selects `HWMON`, so `hwmon.ko` becomes a vendor module (Google's Intel build has no HWMON); `k10temp` is added for CPU temperatures |
| NPU | `DRM_ACCEL_AMDXDNA` | XDNA 2 on Ryzen AI 300 |
| VM | `DRM_VIRTIO_GPU`, `VIRTIO_INPUT` | QEMU/crosvm test target for ANAL-172 |
| Power | `AMD_PMC`, `AMD_SFH_HID`, `ACPI_PLATFORM_PROFILE`, `ACPI_AC`, `ACPI_BATTERY`, `ACPI_FAN`, `ACPI_THERMAL` | s2idle (amd_pmc), sensor hub, battery, AC adapter, fan, thermal zones. `X86_AMD_PSTATE=y` is already in the GKI. **amd-pmf is off**, see Blocked |
| Input | `I2C_DESIGNWARE_CORE`/`_PLATFORM`, `I2C_HID_ACPI`, `I2C_PIIX4`, `SPI_AMD`, `HID_ASUS` | I2C HID touchpad on AMDI0010; SMBus; the ASUS N-KEY keyboard. `HID_MULTITOUCH=y` is already in the GKI |
| Platform | `ACPI_WMI`, `ACPI_VIDEO`, `NVIDIA_WMI_EC_BACKLIGHT`, `ASUS_WMI`, `ASUS_NB_WMI`, `INPUT_SPARSEKMAP`, `SERIAL_MULTI_INSTANTIATE` | ASUS hotkeys, fan profiles, `dgpu_disable`, `gpu_mux_mode`, `ppt_*` limits. serial-multi-instantiate creates the two CS35L56 I2C devices. Backlight: on MUX laptops, the built-in `acpi/video_detect.c` picks `nvidia_wmi_ec` when the EC owns brightness, and then only nvidia-wmi-ec-backlight provides a backlight device. The GA403WR loads that module under Linux |
| Storage | `MISC_RTSX_PCI`, `MMC_REALTEK_PCI` | The GA403WR's RTS525A SD card reader. These select `MFD_CORE`, so `mfd-core.ko` becomes a vendor module, as in Google's Intel build. `MMC=y` and the NVMe driver are already in the GKI |
| Ports, security | `UCSI_ACPI`, `TCG_TPM`, `TCG_CRB` | USB-C role and alt mode; firmware TPM (Pluton/fTPM over CRB). `thunderbolt.ko` (USB4) already ships as a GKI module |
| Audio, HDA | `SND_HDA_INTEL`, `SND_HDA_GENERIC`, `SND_HDA_CODEC_REALTEK`/`ALC269`, `SND_HDA_CODEC_HDMI`/`_ATI`, `SND_HDA_SCODEC_CS35L56_I2C`, `SND_HDA_PATCH_LOADER=y` | ALC285 (the ALC269 family module), 2× CS35L56 amplifiers, HDMI/DP audio. The menu builds the other Realtek codec modules too, as Google's Intel build does |
| Audio, ACP | `SND_SOC_AMD_PS`/`_PS_MACH`, `SND_SOC_AMD_ACP_COMMON`/`_ACP_PCI`, `SND_AMD_ASOC_ACP70`, `SND_SOC_AMD_LEGACY_MACH`, `SND_SOC_SOF_TOPLEVEL=y`, `SND_SOC_SOF_PCI`, `SND_SOC_SOF_AMD_TOPLEVEL`/`REMBRANDT`/`ACP63`/`ACP70`, `SND_SOC_AMD_SOF_MACH` | Internal DMIC on ACP 7.x. `snd_pci_ps` binds when `acp-config` has no DMI quirk for the machine; quirked machines use the SOF or generic ACP driver, so all three are built. The machine drivers pull in a few Chromebook codec modules (rt5682, nau8821, max98357a, …) |
| Wi-Fi, BT | `CFG80211`, `MAC80211`, `MT7921E`, `MT7925E`, `RTW89` with 8851BE/8852AE/8852BE/8852CE/8922AE, `BT_HCIBTUSB` with `_MTK=y` | MT7925 (GA403WR), MT7921/MT7922 and the Realtek Wi-Fi 6/6E/7 cards that ship in other AMD laptops. cfg80211, mac80211 and btusb are vendor modules, as in Google's own Intel build; `bluetooth.ko` and `rfkill.ko` come from the GKI |
| Signing | `# CONFIG_MODULE_SIG_ALL is not set` | Build-time only. The device build's key would mean nothing to the GKI's vmlinux anyway |

**Not needed in the kernel for bring-up: asus-armoury.** asus-armoury landed in 6.19, and `asus-wmi` in this 6.18 tree already exposes `dgpu_disable`, `gpu_mux_mode` and the `ppt_*` power limits (`drivers/platform/x86/asus-wmi.c`). That is enough to keep the RTX 5070 off and the MUX in hybrid mode. A backport only matters for the firmware-attributes interface.

### Equivalence differences

Built-in code that tests a vendor option. The real GKI is built without these options, so it behaves as described in the last column.

| Symbol in vmlinux | Option the vendor build sets | Effect on the shipped GKI |
|---|---|---|
| `i2c_setup_smbus_alert` (absent) and `i2c_register_adapter` (+10 bytes) | `I2C_SMBUS=m`, which `I2C_PIIX4` selects | Adapters do not set up an SMBus-alert IRQ from a firmware `interrupt-names = "smbus_alert"` property. No vendor module calls the function; the module check and the load test would have caught it |
| `hid_have_special_driver` (+192 bytes) | `HID_ASUS=m` | ASUS HID devices lack `HID_QUIRK_HAVE_SPECIAL_DRIVER`, so hid-generic may bind first. When hid-asus registers, the HID bus re-probes and hands the device over |
| `input_leds_connect` (+37 bytes) | `SND_CTL_LED=m`, which the HDA codec LED support selects | Keyboard mute/mic-mute LEDs get no default `audio-mute` trigger. Userspace can set it through sysfs |
| `snd_intel_dsp_driver_probe` (+3 bytes) | `SND_HDA_INTEL=m` | Only Intel PCI audio devices are affected; the function returns before this point for AMD |

### Firmware subset

`scripts/kernel-firmware-subset.py` reads `modinfo -F firmware` from the built modules and filters it with `kernel/firmware/anybook-amd.rules`. It adds files that drivers load by runtime-built names, then copies everything plus the cited licence files and `WHENCE` to `~/anybook/kernel/firmware/anybook-amd/`. The repo holds only the list; the blobs are never committed.

| Licence (WHENCE) | Files | MB | For |
|---|---|---|---|
| `LICENSE.amdgpu` (redistributable) | 78 | 17.4 | Phoenix/Hawk Point (GC 11.0.1/11.0.4), Strix Point (GC 11.5.0), Strix Halo and Krackan (GC 11.5.1–11.5.3) |
| `LICENCE.rtlwifi_firmware.txt` (redistributable) | 30 | 26.7 | rtw89 Wi-Fi and the matching `rtl_bt` Bluetooth files |
| `LICENSE.amdnpu` (redistributable) | 12 | 4.2 | XDNA NPU (1502_00, 17f0_10, 17f0_11) |
| `LICENCE.mediatek` (redistributable) | 11 | 6.2 | MT7925, MT7921, MT7922 Wi-Fi and BT |
| `LICENSE.cirrus` (redistributable) | 6 | 0.1 | CS35L56 tuning for SSID 1043:1b13 (GA403U, see Blocked) |

- **GA403WR set (Strix Point), all present:** `gc_11_5_0_{imu,pfp,me,mec,rlc,mes_2,mes1}`, `psp_14_0_0_{toc,ta}`, `dcn_3_5_dmcub`, `sdma_6_1_0`, `vcn_4_0_5`, `vpe_6_1_0`, `umsch_mm_4_0_0`, `mediatek/mt7925/*`, `amdnpu/17f0_1x/*`.
- **amdxdna declares `amdnpu/17f0_20/npu.sbin`, which linux-firmware does not have.** It is not needed here: the GA403WR's NPU is `1022:17f0` rev 10, so it uses `17f0_10`.
- **Install the files uncompressed.** The GKI has `FW_LOADER_COMPRESS` off, so `.zst`/`.xz` files from distro packages will not load.
- **SOF firmware for ACP is not included.** It comes from sof-bin, not linux-firmware, and `snd_pci_ps`, the expected path for the G14, needs none.

### Build steps

```bash
scripts/kernel-sync.sh                      # gbos-16302624, as in ANAL-170
scripts/kernel-amd-apply.sh                 # patches -> common, kernel/devices/anybook -> devices/anybook
KERNEL_TARGET=//devices/anybook:anybook_amd_x86_64_dist scripts/kernel-build.sh anybook-amd-gbos-16302624

D=~/anybook/kernel/dist/anybook-amd-gbos-16302624
scripts/kernel-config-check.py $D/kernel_x86_64_dot_config DEVICE_CONFIG   # from //devices/anybook:anybook_amd_x86_64_config
scripts/kernel-modules-check.py $D evidence/2026-10-16-kernel-amd/vendor-modules.txt
scripts/kernel-symlist-diff.py ~/anybook/kernel/src/common/gki/x86_64/symbols/anybook_amd \
    ~/anybook/kernel/dist/gbos-16302624/abi_symbollist $D evidence/2026-10-16-kernel-amd/vendor-modules.txt
scripts/kernel-modload-test.sh $D evidence/2026-10-16-kernel-amd/vendor-modules.txt    # QEMU/KVM, tools/Dockerfile.modtest
scripts/kernel-amd-integrity.sh $D          # second GKI build with the fragment on top, then compare
scripts/kernel-firmware-subset.py --fw ~/anybook/kernel/firmware/linux-firmware --modules $D \
    --rules kernel/firmware/anybook-amd.rules --out ~/anybook/kernel/firmware/anybook-amd
```

- The Python checks need `modinfo`/`modprobe` (kmod) and `nm`. The `anybook-kernel` image has them: `scripts/kernel-docker.sh python3 scripts/…`.
- **Changing the module set.** Edit the fragment, then:
  1. Build once with `--notrim --allow_undeclared_modules`. Kleaf prints the module list for `module_outs`.
  2. Reset `anybook_amd` to its `[abi_symbol_list]` header.
  3. Run `tools/bazel run //devices/anybook:anybook_amd_x86_64_abi_update_symbol_list`.
  4. Amend the list into the last `common` commit and run `scripts/kernel-amd-apply.sh --export`.
  5. Rebuild. Kleaf refuses to build the trimmed GKI while a vendor module still imports an unlisted symbol.

### Blocked and open

- **Blocked: amd-pmf.** `AMD_PMF` needs `AMDTEE`, which needs `CRYPTO_DEV_SP_PSP`. With that option set, `ccp.ko` always links `sev-dev.o`, and `sev-dev.o` calls `kernel_read`/`kernel_write`. `build/kernel/abi/symbols.deny` forbids both for GKI vendor modules, and Kleaf fails the build. There are three ways forward, and this needs an owner decision:
  1. Keep PMF off. ASUS power profiles still work through asus-wmi and `platform_profile`.
  2. Carry a patch that splits SEV out of `ccp.ko` behind its own Kconfig symbol. That code is outside GKI.
  3. Waive the deny-list entry locally. That breaks a GKI rule.
- **GA403WR speaker tuning is missing.** The codec SSID is 1043:1024 (inventory). The kernel quirk is backported (patch 0002), but linux-firmware at `38c1a709` has no `cirrus/cs35l56-b0-dsp1-misc-10431024-*` tuning file. **HYPOTHESIS:** the amps then run on their ROM defaults, which usually means quiet or uncalibrated speakers. Only Cirrus or ASUS can publish the file. Upstream also notes that the headset-jack mic does not work on this model yet.
- **Not built yet:** the `android17-6.18` tip (6.18.32) with this fragment, and an ABI definition update (`//common:kernel_x86_64_abi_update`). Kleaf's strict-mode and symbol-violation checks passed. `abi.stg` was not regenerated.
- **Left out on purpose:** KFD (`HSA_AMD`); `AMD_WBRF` (bool, Wi-Fi/GPU RF-band mitigation, would be a fourth built-in deviation); `X86_MCE_AMD` (the GKI has no `X86_MCE`); the camera ISP (the G14 webcam is UVC).
- **Packaging is ANAL-172's job:** `vendor_dlkm`/`vendor_boot` images, module load order and blocklists, firmware placement.
- **Unsigned vendor modules leave the taint flag at 0 on this kernel.** Upstream would set `E`. **HYPOTHESIS:** Android's `MODULE_SIG_PROTECT` change skips that taint. The same holds inside Android: in ANAL-172's Cuttlefish boot, no AnyBook module sets a taint flag.

## Booting in Cuttlefish with our AOSP 17 userspace (ANAL-172)

Status as of 2026-10-16. Evidence is in `evidence/2026-10-16-kernel-cf/`, starting with `SUMMARY.md`. Guesses are labelled **HYPOTHESIS**. This is a VM: no AMD driver probed real hardware.

### Results

- **The AnyBook kernel boots Android 17.** The ANAL-171 `bzImage` (`6.18.21-android17-5-g44a90255c95f`, sha256 `6d964789…`) and its own signed GKI modules run under ANAL-168's `aosp_cf_x86_64_pc-cp2a-userdebug` userspace.
  - `sys.boot_completed=1` comes 30–33 s after `cvd create`.
  - From kernel start, the screen is up at 7.8–8.1 s. ANAL-168's warm boots of the stock 6.12 kernel took 9.1–9.3 s, so the two are close. Host load differed between those runs, so treat that as indicative.
  - Repeated twice with the same reproducible initramfs, then once as a control with only the Cuttlefish board modules.
- **All 169 modules that the AnyBook image asks init to load are live.** Init loads 18 in first stage; `dlkm_loader` loads 154 more, including 3 GKI dependencies. That covers 137 of the 138 AnyBook vendor modules (5 in first stage, 132 from `vendor_dlkm`).
  - 0 `Unknown symbol`, 0 CRC (`disagrees about version`) and 0 signature errors; no Oops or WARNING.
  - `vendor.dlkm.modules.ready=true`. No AnyBook module taints the kernel.
- **The 138th, `asus-nb-wmi`, returns -ENODEV.** crosvm has no ASUS WMI GUID. Left in `dlkm_loader`'s list, that one failure makes the loader's final `CHECK` fail before it sets `vendor.dlkm.modules.ready`. Cuttlefish's virtual Bluetooth (`bt_vhci_forwarder`) waits for that property. So the VM image blocklists the module, and the boot script loads it by hand after boot to record the error.
- **Display: virtio-gpu.** AnyBook's `virtio-gpu.ko` loads in first stage and binds `0000:00:02.0` as `card0`/`renderD128`. SurfaceFlinger shows the lock screen at 1920×1080.
- **amd-pstate does not register in the VM:** `amd_pstate: the _CPC object is not present in SBIOS or ACPI disabled`. The guest CPU has the CPPC flag, but crosvm's ACPI tables have no `_CPC` object. Testing it needs bare metal.
- **amdgpu loads for symbol resolution only.** It is `live` and its PCI driver is registered with no device bound. amdxdna, amd_pmc, amd_sfh, the MT7921/MT7925 and rtw89 Wi-Fi drivers, ACP/SOF and HDA load the same way.
- **The VM has no virtual Wi-Fi with the AnyBook module set.** The board's `mac80211_hwsim`, `virt_wifi` and 7 mt76 USB modules are left out, because they disagree on CRCs with AnyBook's cfg80211, mac80211 and mt76. The cause is in [Module set](#module-set). The board-only control boot keeps virtual Wi-Fi.

### How the kernel is swapped

Android is not rebuilt, and nothing under `~/anybook/aosp` is written. Cuttlefish's own kernel-developer path does the work:

- `cvd create --kernel_path=<bzImage> --initramfs_path=<initramfs>`. `assemble_cvd` (`device/google/cuttlefish/host/commands/assemble_cvd/vendor_dlkm_utils.cc`) unpacks the initramfs, which must hold `lib/modules/<release>/` with `modules.load` and `modules.dep`, and sorts the modules:
  - Its fixed list of first-stage virtio, vsock and Wi-Fi modules, plus their dependencies, stays in the vendor ramdisk.
  - Signed modules go to `system_dlkm`; unsigned ones go to `vendor_dlkm`.
- It then rebuilds both DLKM images as ext4. The fstab has ext4 and erofs entries for both partitions. It also rebuilds their vbmeta images, repacks `super.img` and repacks `boot`/`vendor_boot`.
- The device is unlocked (`orange`), as in ANAL-168.

`scripts/kernel-cf-boot.sh` wraps that around ANAL-168's `scripts/cf-boot.sh`:
1. On the first run, it snapshots the product images and `cvd-host_package.tar.gz` into `~/anybook/kernel/cf/snapshot/` as reflink copies and writes their sha256 to `provenance.txt`. It refuses while an `anybook-aosp-build` container is running.
2. It builds the module set with `scripts/kernel-cf-modset.py`, in the `anybook-kernel` image.
3. It boots in its own container with its own ports and vsock CID: `anybook-cf-kernel`, adb `127.0.0.1:16572`, WebRTC `127.0.0.1:11472`, guest CID 172. vhost-vsock CIDs are global to the host, and other Cuttlefish runs use CID 3.
4. After `boot_completed`, it captures `/proc/modules`, driver bindings, cpufreq, DRM, the PCI list and the hand-loaded blocklisted modules, on top of `cf-boot.sh`'s captures. Then it tears the VM down.
5. `scripts/kernel-cf-modstatus.py` turns the logs into `modload-status.md`: every expected module, whether it is live, and the log lines for any that are not.

### Module set

`kernel-cf-modset.py` merges three sources:

| Source | From | Count |
|---|---|---|
| GKI | the ANAL-171 dist's `system_dlkm_staging_archive.tar.gz`, signed by that build | 100 |
| AnyBook vendor modules | the same dist (`vendor-modules.txt`) | 138 |
| Cuttlefish board modules | `//common-modules/virtual-device:virtual_device_x86_64_dist`, built on the same patched tree | 45 |

- **Board modules come from source.** `KERNEL_TARGET=//common-modules/virtual-device:virtual_device_x86_64_dist scripts/kernel-build.sh anybook-vdev-gbos-16302624` took 367 s.
- **Only their unsigned modules are used.** That build compiled the GKI again with a new random module-signing key (`4A:60…` for ANAL-171, `76:EE…` here). Its `bzImage` therefore differs, but `vmlinux.symvers`, `Module.symvers`, `System.map` and `abi_symbollist` are byte-identical (`board-build.txt`).
  - **Rule: a `bzImage` and its `system_dlkm` must come from the same dist.** `MODULE_SIG_PROTECT` rejects GKI modules signed by any other build.
- **Name clashes keep the AnyBook module.** It is the product.
- **Every import is checked against the provider actually chosen,** repeating until nothing more drops out:
  - Each `__versions` CRC must match the provider's `__kcrctab` or `vmlinux.symvers`.
  - Each undefined symbol must resolve.
  - Unsigned modules may import only KMI-listed symbols from vmlinux and GKI modules.
- **That check drops 9 board modules.** Cuttlefish's `virtual_device.fragment` sets `CONFIG_NL80211_TESTMODE=y`, and the AnyBook fragment does not. The option adds `testmode_*` members to `struct cfg80211_ops`, `struct ieee80211_ops` and the mt76 structs, so the CRCs differ:
  - cfg80211: `wiphy_new_nm`;
  - mac80211: `ieee80211_alloc_hw_nm`;
  - mt76: 83 of 128 exports.

  Without the check, `mac80211_hwsim` would fail in first stage, where any module failure is fatal.
- **Blocklist:** the image ships Cuttlefish's `shared/modules.blocklist` (vkms, vivid, snd-aloop, ptp_kvm), not Kleaf's copy, which lacks snd-aloop. `--block` appends VM-only entries; the default is `asus-nb-wmi.ko`.
- **Output:** a reproducible `initramfs.img` (fixed mtimes and owners, sorted cpio, lz4 legacy format), plus `modset.md`/`modset.tsv` listing each module's source, where `assemble_cvd` will put it, and the reason for each exclusion.

### Commands

```bash
# Once: the Cuttlefish board modules on our GKI (6 min). The ANAL-171 dist must already exist.
KERNEL_TARGET=//common-modules/virtual-device:virtual_device_x86_64_dist scripts/kernel-build.sh anybook-vdev-gbos-16302624
# Boot, capture, tear down: about 1.5 min on a quiet host. Logs: ~/anybook/logs/kernel/cf-<mode>-<ts>/
scripts/kernel-cf-boot.sh               # anybook: GKI + AnyBook 138 + compatible board modules
scripts/kernel-cf-boot.sh board         # control: GKI + Cuttlefish board modules only
KCF_RESNAP=1 scripts/kernel-cf-boot.sh  # take a new snapshot of ~/anybook/aosp/src/out first
```

- **The snapshot is not refreshed automatically.** ANAL-169 builds `anybook_cf_x86_64_pc` into the same `PRODUCT_OUT` (`vsoc_x86_64_only`). A `KCF_RESNAP=1` run after that build therefore picks up ANAL-169's images. `provenance.txt` names every fingerprint file it finds and warns when there is more than one. The device's `ro.*.build.fingerprint` values in `getprop.txt` settle which build booted.
- **Disk:** the snapshot is 4.1 GB of reflinks, so it shares blocks with `out/`. Each boot stages a 3.3 GB product copy in `~/anybook/kernel/cf/product`; it has 12 GB apparent size, because `assemble_cvd` de-sparses `super.img`.
- **Guest:** 4 vCPUs and 8 GiB of RAM.

### Open items

- **Virtual Wi-Fi with the AnyBook set.** Build `mac80211_hwsim` and `virt_wifi` against the AnyBook config, for example as a VM-only Kleaf target on `anybook_amd.fragment` without `NL80211_TESTMODE`. `kernel-cf-modset.py` would then check their CRCs against AnyBook's cfg80211/mac80211. **HYPOTHESIS:** they link cleanly, because both use testmode only when the option is set.
- **Hardware probing** (amdgpu, amdxdna, amd-pstate, amd-pmc s2idle, Wi-Fi, audio) needs the bare-metal epic, or VFIO passthrough of the Radeon 610M. VFIO needs host root and the owner's approval.
- **Module-signing key.** Each GKI rebuild generates a new key, so a dist's `bzImage` and `system_dlkm` cannot be mixed with another build's. For releases, a fixed key kept outside the repo would make rebuilds interchangeable. That is not done.
- **`adb shell dmesg` loses the first ~3 s of boot,** because audit messages wrap the ring buffer. Use `kernel.log`, the host-side console capture.
