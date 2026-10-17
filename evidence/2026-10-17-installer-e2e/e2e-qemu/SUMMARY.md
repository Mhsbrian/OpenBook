# Installer end to end in QEMU/OVMF: openbook-live-20261017-anal192c.img

79/79 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| live-a | every expect step matched | PASS | 91/91 (QEMU exited (0)) |
| live-a | SELinux enforcing; booted from the stick (by-name on sda) | PASS | total 0 lrwxrwxrwx 1 root root 15 2026-10-17 16:26 EFI -> /dev/block/sda1 lrwxrwxrwx 1 root root 15 2026-10-17 16:26 boot_a -> /dev/block/sda3 lrwxrwxrwx 1 root root 15 2026-10-17  |
| live-a | disks: the Windows-like disk shows Windows; alongside and whole both possible | PASS | {'whole': {'ok': True, 'why': None}, 'alongside': {'ok': True, 'why': None, 'free_bytes': 106243817472}} |
| live-a | disks: the 32 GiB disk is refused for both layouts (whole: too_small) | PASS | {'whole': {'ok': False, 'why': 'too_small'}, 'alongside': {'ok': False, 'why': 'no_gpt', 'free_bytes': 0}} |
| live-a | plan on the 32 GiB disk: refused (not_eligible: too_small) | PASS | {"ok":false,"code":"not_eligible","error":"too_small"} 16:26:58 plan refused (not_eligible): too_small PLAN-RC=1  |
| live-a | the wizard's disk screen captured (screenshot) | PASS |  |
| live-a | alongside plan: keeps the 4 Windows partitions, erases none | PASS | None |
| live-a | apply without OPENBOOK_INSTALL_ERASE: refused (confirm_mismatch) | PASS | ick OpenBook from the firmware's boot menu or add an entry in its setup"},{"op":"report","text":"Save the install report and log to openbook/logs/ on the stick and on the new xboot |
| live-a | unattended alongside install (--confirm-disk + OPENBOOK_INSTALL_ERASE): ok and verified | PASS | None |
| live-a | machine-readable progress: step and progress events, then the report | PASS | 83 |
| live-a | after the install: Windows and OpenBook on the disk; a second alongside refused (name_clash) | PASS | (['Windows', 'OpenBook'], {'whole': {'ok': True, 'why': None}, 'alongside': {'ok': False, 'why': 'name_clash', 'free_bytes': 0}}) |
| live-a | no SELinux denial for the engine or the app (enforcing) | PASS | [] |
| live-a | MSR, NTFS and recovery partitions byte-identical (S7) | PASS | {'EFI system partition': 'changed', 'Microsoft reserved partition': 'unchanged', 'Basic data partition': 'unchanged', 'Recovery': 'unchanged'} |
| live-a | Windows ESP: only EFI/OpenBook/systemd-bootx64.efi added; bootmgfw.efi, BCD and BOOTX64.EFI unchanged | PASS | ['EFI/OpenBook/systemd-bootx64.efi'] |
| live-a | Windows ESP passes fsck.fat after the install | PASS | {'rc': 0, 'out': ['fsck.fat 4.2 (2021-01-31)', '/home/hive/anybook/logs/installer/e2e-anal192c/inspect/windows-after.json.tmp: 10 files, 409/524252 clusters']} |
| live-a | GPT: both copies valid, 4 + 13 partitions, the Windows ones at the same place | PASS | 17 |
| live-a | XBOOTLDR holds the OpenBook entry; no loader.conf; the fallback path is Windows' | PASS | (['xbootldr'], ['EFI system partition']) |
| al-windows | fresh NVRAM: the firmware starts the disk's fallback path, Windows' boot manager (stand-in) | PASS | ['BdsDxe: loading Boot0003 "UEFI QEMU NVMe Ctrl internal0 1"', 'BdsDxe: starting Boot0003 "UEFI QEMU NVMe Ctrl internal0 1"'] |
| al-fwsetup | a firmware boot option for EFI/OpenBook/systemd-bootx64.efi added (as in the firmware setup) | PASS | -0000:00:01.0-1" from PciRoot(0x0)/Pci(0x1,0x0)/USB(0x0,0x0) BdsDxe: starting Boot0002 "UEFI QEMU QEMU USB HARDDRIVE 1-0000:00:01.0-1" from PciRoot(0x0)/Pci(0x1,0x0)/USB(0x0,0x0) |
| al-openbook | the firmware starts Boot1000 "OpenBook" from the Windows ESP | PASS | ['BdsDxe: loading Boot1000 "OpenBook"', 'BdsDxe: starting Boot1000 "OpenBook"'] |
| al-openbook | OpenBook's screen comes up (a screenshot after 20 s is lit, not a black or firmware screen) | PASS | {'shot-20.png': 0.997, 'shot-40.png': 0.997, 'shot-60.png': 0.997, 'shot-90.png': 0.997, 'shot-120.png': 0.997, 'shot-150.png': 0.997, 'shot-180.png': 0.997} |
| al-openbook | Windows was not started instead | PASS |  |
| al-console | every expect step matched | PASS | 80/80 (QEMU exited (0)) |
| al-console | booted alongside: installed=alongside, boot_part_uuid is XBOOTLDR, enforcing, no live flags | PASS | [ro.boot.boot_part_uuid]: [32dae2e9-6a65-4e41-85c7-ffe033dca3f8] [ro.boot.openbook.installed]: [alongside] [ro.boot.openbook.keyboard]: [us] [ro.boot.openbook.loader]: [sdboot] [ro |
| al-console | Android's by-name links point at the NVMe disk | PASS | Basic_data_partition, EFI_system_partition, Microsoft_reserved_partition, Recovery, boot_a, boot_b, init_boot_a, init_boot_b, metadata, misc, nvme0n1, super, userdata, vbmeta_a, vb |
| al-console | no Windows partition mounted (p1 to p4) | PASS |  /dev/block/nvme0n1p15 /metadata ext4 rw,seclabel,nosuid,nodev,noatime,discard 0 0 Filesystem            1K-blocks   Used Available Use% Mounted on /dev/block/dm-13       90294272  |
| al-console | OpenBook setup, then the desktop | PASS | 1 1       topResumedActivity=ActivityRecord{42815507 u0 com.android.launcher3/.uioverrides.QuickstepLauncher t9}  |
| cut-1 | the install reached its cut point ("check_source" "running" + 1 s) and the power was cut | PASS | QEMU exited (0) |
| cut-1 | restart from the stick: the engine reads the previous state and offers the disk again (whole ok) | PASS | ('whole-before', 'gpt', ['Windows'], {'ok': True, 'why': None}) |
| cut-1 | cut state is one of ['old-table'] (S9: the old table, a blank disk, or the new one, bootable only when complete) | PASS | old-table (mbr protective, primary True, backup True, entry [], fallback ['EFI system partition']) |
| cut-1 | the old table and every old partition unchanged | PASS | {'EFI system partition': 'unchanged', 'Microsoft reserved partition': 'unchanged', 'Basic data partition': 'unchanged', 'Recovery': 'unchanged'} |
| fw-cut-1 | the firmware still starts the old system (Windows stand-in) from the untouched disk | PASS | ['Boot0003 "UEFI QEMU NVMe Ctrl internal0 1"'] |
| cut-2 | the install reached its cut point ("boot_images" "running" + 0 s) and the power was cut | PASS | QEMU exited (0) |
| cut-2 | restart from the stick: the engine reads the previous state and offers the disk again (whole ok) | PASS | ('cut-1', 'gpt', ['Windows'], {'ok': True, 'why': None}) |
| cut-2 | cut state is one of ['blank'] (S9: the old table, a blank disk, or the new one, bootable only when complete) | PASS | blank (mbr none, primary False, backup False, entry [], fallback []) |
| fw-cut-2 | the firmware starts nothing from the cut disk (no table, or not activated) | PASS | ['Boot0002 "UEFI QEMU QEMU USB HARDDRIVE 1-0000:00:01.0-1"', 'Boot0003 "UEFI QEMU NVMe Ctrl internal0 1"'] |
| cut-3 | the install reached its cut point ("system" "running" + 3 s) and the power was cut | PASS | QEMU exited (0) |
| cut-3 | restart from the stick: the engine reads the previous state and offers the disk again (whole ok) | PASS | ('cut-2', 'none', [], {'ok': True, 'why': None}) |
| cut-3 | cut state is one of ['blank'] (S9: the old table, a blank disk, or the new one, bootable only when complete) | PASS | blank (mbr none, primary False, backup False, entry [], fallback []) |
| fw-cut-3 | the firmware starts nothing from the cut disk (no table, or not activated) | PASS | ['Boot0002 "UEFI QEMU QEMU USB HARDDRIVE 1-0000:00:01.0-1"', 'Boot0003 "UEFI QEMU NVMe Ctrl internal0 1"'] |
| cut-4 | the install reached its cut point ("boot_entry" "running" + 0.3 s) and the power was cut | PASS | QEMU exited (0) |
| cut-4 | restart from the stick: the engine reads the previous state and offers the disk again (whole ok) | PASS | ('cut-3', 'none', [], {'ok': True, 'why': None}) |
| cut-4 | cut state is one of ['blank', 'new-not-activated'] (S9: the old table, a blank disk, or the new one, bootable only when complete) | PASS | new-not-activated (mbr protective, primary True, backup True, entry [], fallback []) |
| cut-4 | the new ESP passes fsck.fat | PASS | {'rc': 0, 'out': ['fsck.fat 4.2 (2021-01-31)', '/home/hive/anybook/logs/installer/e2e-anal192c/inspect/cut-4.json.tmp: 7 files, 7327/130812 clusters']} |
| fw-cut-4 | the firmware starts nothing from the cut disk (no table, or not activated) | PASS | ['Boot0002 "UEFI QEMU QEMU USB HARDDRIVE 1-0000:00:01.0-1"', 'Boot0003 "UEFI QEMU NVMe Ctrl internal0 1"'] |
| cut-5 | the install reached its cut point ("verify" "running" + 1 s) and the power was cut | PASS | QEMU exited (0) |
| cut-5 | restart from the stick: the engine reads the previous state and offers the disk again (whole ok) | PASS | ('cut-4', 'gpt', ['OpenBook'], {'ok': True, 'why': None}) |
| cut-5 | cut state is one of ['new-not-activated'] (S9: the old table, a blank disk, or the new one, bootable only when complete) | PASS | new-not-activated (mbr protective, primary True, backup True, entry [], fallback []) |
| cut-5 | the new ESP passes fsck.fat | PASS | {'rc': 0, 'out': ['fsck.fat 4.2 (2021-01-31)', '/home/hive/anybook/logs/installer/e2e-anal192c/inspect/cut-5.json.tmp: 7 files, 7327/130812 clusters']} |
| fw-cut-5 | the firmware starts nothing from the cut disk (no table, or not activated) | PASS | ['Boot0002 "UEFI QEMU QEMU USB HARDDRIVE 1-0000:00:01.0-1"', 'Boot0003 "UEFI QEMU NVMe Ctrl internal0 1"'] |
| cut-6 | the install reached its cut point ("report" "running" + 0 s) and the power was cut | PASS | QEMU exited (0) |
| cut-6 | restart from the stick: the engine reads the previous state and offers the disk again (whole ok) | PASS | ('cut-5', 'gpt', ['OpenBook'], {'ok': True, 'why': None}) |
| cut-6 | cut state is one of ['new-complete'] (S9: the old table, a blank disk, or the new one, bootable only when complete) | PASS | new-complete (mbr protective, primary True, backup True, entry ['EFI'], fallback ['EFI']) |
| cut-6 | the new ESP passes fsck.fat | PASS | {'rc': 0, 'out': ['fsck.fat 4.2 (2021-01-31)', '/home/hive/anybook/logs/installer/e2e-anal192c/inspect/cut-6.json.tmp: 19 files, 7420/130812 clusters']} |
| fw-cut-6 | the firmware starts the complete install (OpenBook's fallback path) | PASS | ['Boot0003 "UEFI QEMU NVMe Ctrl internal0 1"'] |
| install | every expect step matched | PASS | 27/27 (QEMU exited (0)) |
| install | restarted over the last cut disk: ok and verified | PASS | None |
| install | no SELinux denial for the engine (enforcing) | PASS | [] |
| install | the disk: both GPT copies valid, every planned file present and matching, bootable | PASS | new-complete |
| installed | no stick, fresh NVRAM: the firmware starts the installed disk's fallback path | PASS | ['BdsDxe: loading Boot0003 "UEFI QEMU NVMe Ctrl internal0 1"', 'BdsDxe: starting Boot0003 "UEFI QEMU NVMe Ctrl internal0 1"'] |
| installed | OpenBook's first screen comes up (a screenshot after 20 s is lit) | PASS | {'shot-20.png': 0.997, 'shot-40.png': 0.997, 'shot-60.png': 0.997, 'shot-90.png': 0.997, 'shot-120.png': 0.997, 'shot-150.png': 0.997, 'shot-180.png': 0.997} |
| inst-stick | every expect step matched | PASS | 80/80 (QEMU exited (0)) |
| inst-stick | booted from the NVMe disk: by-name links there, installed=whole, enforcing, no live flags | PASS | [ro.boot.boot_part_uuid]: [2158ae5e-f694-4890-b810-0467152dd954] [ro.boot.openbook.installed]: [whole] [ro.boot.openbook.keyboard]: [us] [ro.boot.openbook.loader]: [sdboot] [ro.boo |
| inst-stick | the installer is off (no launcher entry, no daemon); OpenBook setup is the first screen | PASS | ['0', 'daemon=[]', '0', '      topResumedActivity=ActivityRecord{243557731 u0 org.openbook.installer/.SetupActivity t2}'] |
| inst-stick | through setup to the desktop | PASS | 1 1       topResumedActivity=ActivityRecord{84948968 u0 com.android.launcher3/.uioverrides.QuickstepLauncher t9}  |
| inst-stick | the stick plugged in: no partition of it mounted by Android (vold) | PASS |  /dev/block/nvme0n1p11 /metadata ext4 rw,seclabel,nosuid,nodev,noatime,discard 0 0 Filesystem            1K-blocks    Used Available Use% Mounted on /dev/block/dm-13      120756224 |
| inst-stick | the stick's partitions unchanged by the installed system | PASS | {'EFI': True, 'misc': True, 'boot_a': True, 'init_boot_a': True, 'vendor_boot_a': True, 'vbmeta_a': True, 'metadata': True, 'super': True, 'userdata': True} |
| inst-stick | known issue, reported: SystemUI's notification for the plugged-in stick (not gated) | PASS | disk:8,0: 'QEMU USB drive detected' (Tap to set up = format) |
| reinstalled | every expect step matched | PASS | 80/80 (QEMU exited (0)) |
| reinstalled | booted from the NVMe disk: by-name links there, installed=whole, enforcing, no live flags | PASS | [ro.boot.boot_part_uuid]: [9d1d5b64-8cca-47f9-a697-ddc8e7d80a8e] [ro.boot.openbook.installed]: [whole] [ro.boot.openbook.keyboard]: [us] [ro.boot.openbook.loader]: [sdboot] [ro.boo |
| reinstalled | the installer is off (no launcher entry, no daemon); OpenBook setup is the first screen | PASS | ['0', 'daemon=[]', '0', '      topResumedActivity=ActivityRecord{266146649 u0 org.openbook.installer/.SetupActivity t2}'] |
| reinstalled | through setup to the desktop | PASS | 1 1       topResumedActivity=ActivityRecord{201930636 u0 com.android.launcher3/.uioverrides.QuickstepLauncher t9}  |
| reinstalled | a new system: a new serial number, setup again | PASS | ('430AA5EB47C4E25D', '59058F830B632E4F') |
| reinstall | every expect step matched | PASS | 85/85 (QEMU exited (0)) |
| reinstall | the live system boots from the stick with OpenBook installed on the NVMe disk (by-name on sda, nothing of nvme mounted) | PASS | total 0 lrwxrwxrwx 1 root root 15 2026-10-17 16:48 EFI -> /dev/block/sda1 lrwxrwxrwx 1 root root 15 2026-10-17 16:48 boot_a -> /dev/block/sda3 lrwxrwxrwx 1 root root 15 2026-10-17  |
| reinstall | disks: OpenBook found on the NVMe disk, whole possible, alongside refused (name_clash) | PASS | (['OpenBook', 'Linux'], {'whole': {'ok': True, 'why': None}, 'alongside': {'ok': False, 'why': 'name_clash', 'free_bytes': 0}}) |
| reinstall | whole-disk reinstall over the installed OpenBook: ok and verified | PASS | None |
| reinstall | a new disk GUID and new partition GUIDs | PASS | ('27E74A95-3BFD-4542-BE27-FDCE91553A40', 'C4069D3A-CC89-4870-8A7B-4DA1065F5F5E') |
| reinstall | the old system's userdata is gone (its digest changed; the new one starts blank) | PASS | ('6355c48b9462', 'a535d888997d', 'new-complete') |
