## 1. Our build vs shipped

- `dot_config`: 6747 symbols; `gbos-kernel-config.txt`: 6745 symbols.
- Symbols that differ: **5**.

| Symbol | Ours | Shipped |
|---|---|---|
| `CONFIG_AMD_IOMMU` | y | n |
| `CONFIG_DRM_ACCEL_AMDXDNA` | n | unset |
| `CONFIG_IOMMU_IO_PGTABLE` | y | unset |
| `CONFIG_PINCTRL_AMD` | y | n |
| `CONFIG_X86_AMD_PLATFORM_DEVICE` | y | n |

## 2. Shipped config vs the defconfig

- `gki_defconfig` sets 750 symbols explicitly. 747 end up with that value in the shipped config.
- Defconfig lines that did **not** stick (dependency unmet, renamed, or overridden): **3**.

| Symbol | Defconfig asks | Shipped has |
|---|---|---|
| `CONFIG_AMD_IOMMU` | y | n |
| `CONFIG_PINCTRL_AMD` | y | n |
| `CONFIG_X86_AMD_PLATFORM_DEVICE` | y | n |
- Enabled in the shipped config without being in the defconfig: 1767 symbols. These come from Kconfig defaults and `select`, so a build from the defconfig alone reproduces them.

## 3. Where selected symbols come from

| Symbol | Shipped | Ours | Explicit in defconfig | Enabled selectors / implies (Kconfig) | Kconfig default |
|---|---|---|---|---|---|
| `CONFIG_PKVM_INTEL` | y | y | line 101: `y` | - | none |
| `CONFIG_PKVM_X86` | y | y | no | `PKVM_INTEL` (select, `arch/x86/kvm/Kconfig:144`) | none |
| `CONFIG_X86_FRED` | y | y | no | `KVM_INTEL` (select if X86_64, `arch/x86/kvm/Kconfig:99`) | none |
| `CONFIG_KVM_INTEL` | y | y | line 100: `y` | - | none |
| `CONFIG_KVM_AMD` | y | y | line 102: `y` | - | none |
| `CONFIG_DRM_AMDGPU` | n | n | no | - | none |
| `CONFIG_DRM_AMD_DC` | unset | unset | no | - | `y` |
| `CONFIG_PINCTRL_AMD` | n | y | line 447: `y` | - | none |
| `CONFIG_AMD_PMC` | n | n | no | - | none |
| `CONFIG_AMD_IOMMU` | n | y | line 583: `y` | - | none |
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
