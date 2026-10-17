# openbook-install host tests (openbook-live-20261017-anal191e.img)

53/53 checks passed.

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
| refuse-no-env | without OPENBOOK_INSTALL_ERASE: refused | PASS |  |
| refuse-wrong-disk | a different disk named: refused | PASS |  |
| refuse-wrong-disk | target unchanged | PASS |  |
| refuse-boot-disk | planning onto the stick: refused (boot_disk) | PASS |  |
| refuse-mounted | a disk with a partition in use: refused (mounted) | PASS |  |
| refuse-small | a 32 GiB disk: refused (too_small) | PASS |  |
| refuse-changed | the disk changed after the plan: refused (plan_changed, S4) | PASS |  |
| refuse-changed | target unchanged | PASS |  |
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
