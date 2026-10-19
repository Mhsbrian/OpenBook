# openbook-install host tests (openbook-live-20261018-anal192e.img)

69/69 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| disks | two disks found, the stick by its USB by-id | PASS |  |
| disks | the stick is the boot disk and not a target (S1) | PASS |  |
| disks | the NVMe disk: by-id nvme-QEMU_NVMe_Ctrl_internal0 | PASS |  |
| disks | blank NVMe: whole ok, alongside refused (no GPT) | PASS |  |
| disks | install source found on the stick | PASS |  |
| disks | hwinfo answers (fixture: no hardware) | PASS |  |
| plan | plan succeeds | PASS |  |
| plan | operations listed in order (check, recheck, wipe, copies, super, format, files, table, verify, activate, nvram, report) | PASS |  |
| plan | whole-disk layout (docs/installer.md 3.2) | PASS |  |
| plan | confirm text is the disk's model | PASS |  |
| plan | the target was only read (sha256 unchanged) | PASS |  |
| nvram | plan: a firmware entry is planned and goes first (consent given) | PASS |  |
| nvram | plan: the firmware's variables were only read | PASS |  |
| nvram | whole: result says Boot0002 created and first in BootOrder | PASS |  |
| nvram | whole: Boot0002 = "OpenBook", active, NV+BS+RT, HD(1, GPT, the new ESP)/\EFI\OpenBook\systemd-bootx64.efi | PASS |  |
| nvram | whole: BootOrder 0002, 0000, 0001 (OpenBook first, the rest in their order) | PASS |  |
| nvram | whole: the other entries are byte-identical | PASS |  |
| nvram | openbook-install nvram lists the entries and the order | PASS |  |
| nvram | alongside: plan puts OpenBook last in BootOrder (no consent), no boot order warning | PASS |  |
| nvram | alongside: result says Boot0002 created and last in BootOrder | PASS |  |
| nvram | alongside: Boot0002 "OpenBook" -> HD(1, GPT, the existing Windows ESP)/\EFI\OpenBook\systemd-bootx64.efi (0001, the stale BootOrder reference, not reused) | PASS |  |
| nvram | alongside: BootOrder 0000, 0001, 0002 (Windows still first, OpenBook appended; owner decision) | PASS |  |
| nvram | alongside: Windows Boot Manager byte-identical; no other variable added or removed (S11) | PASS |  |
| refuse-no-env | without OPENBOOK_INSTALL_ERASE: refused | PASS |  |
| refuse-wrong-disk | a different disk named: refused | PASS |  |
| refuse-wrong-disk | target unchanged | PASS |  |
| refuse-boot-disk | planning onto the stick: refused (boot_disk) | PASS |  |
| refuse-mounted | a disk with a partition in use: refused (mounted) | PASS |  |
| refuse-small | a 32 GiB disk: refused (too_small) | PASS |  |
| refuse-changed | the disk changed after the plan: refused (plan_changed, S4) | PASS |  |
| refuse-changed | target unchanged | PASS |  |
| refuse-power-battery-41 | on battery at 41 %, charger off: refused (power, S8) | PASS |  |
| refuse-power-battery-41 | target unchanged | PASS |  |
| refuse-power-unreadable | power supplies unreadable and no reading given: refused (power; S8 fails closed) | PASS |  |
| refuse-power-unreadable | target unchanged | PASS |  |
| refuse-bad-stick | a corrupted super on the stick: check_source fails (S10) | PASS |  |
| refuse-bad-stick | nothing written to the target | PASS |  |
| whole | apply succeeds and verifies | PASS |  |
| whole | every step done | PASS |  |
| whole | progress events streamed | PASS |  |
| whole | GPT valid (sgdisk -v) | PASS |  |
| whole | 13 partitions as planned | PASS |  |
| whole | partition offsets as planned | PASS |  |
| whole | ESP PARTUUID is the bootconfig's boot_part_uuid | PASS |  |
| whole | ESP passes fsck.fat | PASS |  |
| whole | every ESP file read by mtools matches the plan | PASS |  |
| whole | loader entry: kernel, three initrds with bootconfig last, vendor cmdline | PASS |  |
| whole | bootconfig: the new ESP's PARTUUID, a new serial, no live flags, locale | PASS |  |
| whole | bootconfig trailer checks out (bootconfig.py show) | PASS |  |
| whole | lpdump: super metadata for 12 GiB, virtual A/B, every logical partition at its offset | PASS |  |
| whole | every logical partition's bytes match the product image (sha256) | PASS |  |
| whole | boot_a, init_boot_a, vendor_boot_a, vbmeta_a match the stick (sha256) | PASS |  |
| whole | metadata, userdata, misc and slot B start blank (Android formats them on first boot) | PASS |  |
| whole | install report on the new ESP | PASS |  |
| whole | install report and log on the stick (S6) | PASS |  |
| whole | the stick's ESP still passes fsck.fat after the report | PASS |  |
| whole | the stick's other partitions are unchanged | PASS |  |
| alongside | Windows found on the disk, alongside possible with the free space | PASS |  |
| alongside | plan: an XBOOTLDR partition and the Android partitions in the free space | PASS |  |
| alongside | plan keeps every existing partition and erases none | PASS |  |
| alongside | apply succeeds and verifies | PASS |  |
| alongside | GPT valid (sgdisk -v) | PASS |  |
| alongside | MSR, NTFS and recovery partitions unchanged (S7) | PASS |  |
| alongside | 4 + 13 partitions in the table | PASS |  |
| alongside | the Windows ESP passes fsck.fat | PASS |  |
| alongside | EFI/Microsoft/Boot/bootmgfw.efi and EFI/BOOT/BOOTX64.EFI untouched | PASS |  |
| alongside | EFI/OpenBook/systemd-bootx64.efi added to the existing ESP | PASS |  |
| alongside | XBOOTLDR holds the entry and the boot files, no loader.conf or fallback path | PASS |  |
| alongside | XBOOTLDR has its type GUID | PASS |  |
