# Config diff: our gbos-16302624 rebuild vs shipped Googlebook kernel

- Ours: `dist/gbos-16302624/dot_config`, built with Kleaf from `common` 3938c8d97142 using `manifests/kernel/gbos-16302624.xml`.
- Shipped: `evidence/2026-10-15-m0/gbos-kernel-config.txt`, the IKCONFIG of ruby `boot_a` (6.18.21-android17-5-g3938c8d97142-ab16302624).
- Defconfig and Kconfig tree: `common/arch/x86/configs/gki_defconfig` at 3938c8d97142, the only defconfig `//common:kernel_x86_64` uses (no fragments).

## 1. Our build vs shipped

- `dot_config`: 6745 symbols; `gbos-kernel-config.txt`: 6745 symbols.
- Symbols that differ: **0**.

## 2. Shipped config vs the defconfig

- `gki_defconfig` sets 749 symbols explicitly. 749 end up with that value in the shipped config.
- Defconfig lines that did **not** stick (dependency unmet, renamed, or overridden): **0**.
- Enabled in the shipped config without being in the defconfig: 1765 symbols. These come from Kconfig defaults and `select`, so a build from the defconfig alone reproduces them.

## 3. Where selected symbols come from

| Symbol | Shipped | Ours | Explicit in defconfig | Enabled selectors / implies (Kconfig) | Kconfig default |
|---|---|---|---|---|---|
| `CONFIG_PKVM_INTEL` | y | y | line 100: `y` | - | none |
| `CONFIG_PKVM_X86` | y | y | no | `PKVM_INTEL` (select, `arch/x86/kvm/Kconfig:144`) | none |
| `CONFIG_X86_FRED` | y | y | no | `KVM_INTEL` (select if X86_64, `arch/x86/kvm/Kconfig:99`) | none |
| `CONFIG_KVM_INTEL` | y | y | line 99: `y` | - | none |
| `CONFIG_KVM_AMD` | y | y | line 101: `y` | - | none |
| `CONFIG_DRM_AMDGPU` | n | n | no | - | none |
| `CONFIG_DRM_AMD_DC` | unset | unset | no | - | `y` |
| `CONFIG_PINCTRL_AMD` | n | n | no | - | none |
| `CONFIG_AMD_PMC` | n | n | no | - | none |
| `CONFIG_AMD_IOMMU` | n | n | no | - | none |
| `CONFIG_X86_AMD_PSTATE` | y | y | no | `SCHED_MC_PRIO` (select if CPU_SUP_AMD && ACPI, `arch/x86/Kconfig:1076`) | none |
| `CONFIG_CRYPTO_DEV_CCP` | n | n | no | - | none |
| `CONFIG_AMD_SFH_HID` | n | n | no | - | none |
| `CONFIG_I2C_DESIGNWARE_PLATFORM` | unset | unset | no | - | `I2C_DESIGNWARE_CORE` |
| `CONFIG_I2C_HID_ACPI` | n | n | no | - | none |
| `CONFIG_SND_SOC_SOF_AMD_TOPLEVEL` | unset | unset | no | - | none |
| `CONFIG_SND_SOC_AMD_ACP` | n | n | no | - | none |
| `CONFIG_MT7921E` | unset | unset | no | - | none |
| `CONFIG_MT7925E` | unset | unset | no | - | none |
| `CONFIG_DRM_VIRTIO_GPU` | n | n | no | - | none |
| `CONFIG_TRIM_UNUSED_KSYMS` | y | y | no | - | none |
| `CONFIG_MODULE_SIG_PROTECT` | y | y | no | - | `y` |
