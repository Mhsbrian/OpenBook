# ANAL-198 evidence: bare-metal packaging for the G14 (GA403WR)

Produced by `scripts/kernel-g14-package.sh --evidence evidence/2026-10-16-kernel-g14` on 2026-10-16 (Ryzen 9 7950X host, QEMU/KVM). Nothing here ran on the laptop. Details and decisions: `docs/kernel.md`, "Bare-metal packaging for the G14".

**Overall: PASS** (`results.json`: module lists, signing check, firmware and all 5 QEMU runs).

| File | What it shows |
|---|---|
| `images.md`, `images.json` | Sizes, sha256 and AVB footers of `vendor_boot.img`, its DLKM ramdisk, `vendor_dlkm.img`, `system_dlkm.img`, `bzImage` and `boot.img`, plus the VM variants. All come from one Kleaf build, release `6.18.21-android17-5-g44a90255c95f` (`linux_banner.txt`, `sha256.txt`) |
| `lists/` | The module lists as built: `vendor_boot.{bm,vm}.modules.load`, `vendor_dlkm.{bm,vm}.modules.{load,blocklist,dep}`, `system_dlkm.modules.load`. The rationale per module is in `kernel/devices/anybook/g14/modules.tsv` |
| `modlists.md`, `.json` | Lists match `modules.tsv`. First stage is closed under its dependencies, and every second-stage dependency loads earlier or comes from `system_dlkm`: 0 problems |
| `sigcheck.md`, `.json` | 100/100 `system_dlkm` modules are signed by key serial `76EEF3B7…F5A4`, whose certificate is in `vmlinux`. 138/138 vendor modules are unsigned |
| `firmware/firmware-manifest.{md,tsv,json}`, `firmware/firmware.mk` | 137 files in the `/vendor/firmware` layout, each with its source path, URL, git blob, WHENCE driver and licence (5 licence files). The GA403WR uses 24 of them. The CS35L56 `10431024` tuning is present (WHENCE links); only `amdnpu/17f0_20/npu.sbin` is absent, and the G14 does not use it |
| `qemu/summary.md`, `qemu/results.json` | 5 runs, all PASS: `usb` (usb-storage on xHCI), `uas`, `nvme`, `both-uuid` (NVMe and USB disks with the same partition names; `boot_part_uuid` picks USB), `vm` |
| `qemu/<run>.first-stage.txt` | Kernel log from disk detection through first-stage init: by-name discovery, `super`, AVB `Success`, dm-verity, the mounts |
| `qemu/<run>.dlkm.txt`, `<run>.modules.txt` | `dlkm_loader` loading `vendor_dlkm` (GKI dependencies come from `/system/lib/modules`), and `/proc/modules` afterwards |
| `qemu/<run>.by_name.txt`, `.sys_block.txt`, `.mounts.txt`, `.dm.txt`, `.props.txt`, `.bootconfig.txt` | Captured from a root shell on the guest's serial console |
| `qemu/<run>.serial.log.gz`, `<run>.json`, `<run>.md` | Full serial log; the run's checks and verdict |
| `build-settings.txt` | Bazel limits of the last build step (that one was a cache hit) |

Expected and not an error: `asus-nb-wmi` returns -ENODEV in the bare-metal runs, because QEMU has no ASUS WMI GUID. That is why the VM variant blocklists it.
