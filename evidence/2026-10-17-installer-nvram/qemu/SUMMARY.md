# Installer wizard in QEMU: openbook-live-20261017-anal191g.img

33/33 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| dryrun | every expect step matched | PASS | 126/126 (all steps done) |
| dryrun | SELinux enforcing | PASS | c07a41c] [ro.boot.openbook.live]: [1] [ro.boot.openbook.loader]: [sdboot] [ro.build.fingerprint]: [OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/en |
| dryrun | the wizard started by itself after boot | PASS |     topResumedActivity=ActivityRecord{88447240 u0 org.openbook.installer/.MainActivity t11}   ResumedActivity: ActivityRecord{88447240 u0 org.openbook.installer |
| dryrun | openbook_installd runs in its own domain | PASS | ime 0 0 u:object_r:openbook_efivarfs:s0 /sys/firmware/efi/efivars u:object_r:openbook_efivarfs:s0 Boot0000-8be4df61-93ca-11d2-aa0d-00e098032b8c u:object_r:openb |
| dryrun | whole-disk nodes carry openbook_disk_block_device | PASS |  |
| dryrun | CLI dry run: a plan for the NVMe disk | PASS | {"plan_sha256":"bb09d5f31ee41548dc1e2b0e7f02514c09e9f7c7e8e03b0394d8fd991426d7e7","created":"2026-10-17T20:42:50Z","schema":"openbook-install-plan/1","engine":" |
| dryrun | the app's dry run went through the daemon | PASS |  |
| dryrun | screens captured: welcome, hardware, choose, disk, plan | PASS | ['shot-1-welcome.png', 'shot-2-hardware.png', 'shot-3-choose-install.png', 'shot-3-choose.png', 'shot-4-disk-selected.png', 'shot-4-disk.png', 'shot-4-plan.png' |
| dryrun | the NVMe disk has no allocated block after the dry run (nothing written) | PASS | 0 blocks |
| dryrun | no SELinux denial for the app or the daemon | PASS |  |
| install | every expect step matched | PASS | 181/181 (QEMU exited (0)) |
| install | screens captured: confirm, typed, install, done | PASS | ['shot-1-welcome.png', 'shot-2-hardware.png', 'shot-3-choose-install.png', 'shot-3-choose.png', 'shot-4-disk-selected.png', 'shot-4-disk.png', 'shot-4-plan.png' |
| install | the daemon ran the install and it verified | PASS |  re-read the partition table 20:47:19 nvram: created Boot0005 "OpenBook" -> HD(1, GPT, 4d3c50e8-c6c8-48dd-a2cf-54ad54b22046)/\EFI\OpenBook\systemd-bootx64.efi;  |
| install | no SELinux denial for the app or the daemon (enforcing) | PASS |  |
| install | the run ended with the guest's reboot (Restart now) | PASS | QEMU exited (0) |
| install | firmware entry: one "OpenBook" Boot#### -> HD(1, GPT)/\EFI\OpenBook\systemd-bootx64.efi, first in BootOrder | PASS | {'entry': {'num': '0005', 'description': 'OpenBook', 'active': True, 'partition': 1, 'partuuid': '4d3c50e8-c6c8-48dd-a2cf-54ad54b22046', 'path': '\\EFI\\OpenBoo |
| install | efivarfs mounted by init with its own label (openbook_efivarfs) | PASS | ime 0 0 u:object_r:openbook_efivarfs:s0 /sys/firmware/efi/efivars u:object_r:openbook_efivarfs:s0 Boot0000-8be4df61-93ca-11d2-aa0d-00e098032b8c u:object_r:openb |
| nvram-boot | every expect step matched | PASS | 21/21 (all steps done) |
| nvram-boot | the copy has no fallback path: EFI/BOOT/BOOTX64.EFI deleted | PASS | ::/EFI/OpenBook/ ::/EFI/BOOT/ ::/EFI/OpenBook/systemd-bootx64.efi |
| nvram-boot | the firmware kept the install's BootOrder (OpenBook first; no bootindex hints) | PASS | ['0005', '0002', '0003', '0000', '0001', '0004'] |
| nvram-boot | OVMF started the installed system through OpenBook's entry (BootCurrent = the entry the install made) | PASS | {'boot_current': '0005', 'entry': '0005', 'installed': '0005'} |
| nvram-boot | Android booted from the NVMe disk (by-name links on nvme0n1, installed=whole) | PASS | 14 |
| alongside | every expect step matched | PASS | 144/144 (all steps done) |
| alongside | before: Windows Boot Manager (Boot0007) first in BootOrder | PASS | ['0007', '0002', '0003', '0000', '0001', '0004'] |
| alongside | the install verified (daemon, enforcing) | PASS |  |
| alongside | one new "OpenBook" entry -> HD(1, GPT, the Windows ESP)/\EFI\OpenBook\systemd-bootx64.efi | PASS | {'num': '0005', 'description': 'OpenBook', 'active': True, 'partition': 1, 'partuuid': '33cb431f-bfe9-4edf-af4c-c9bf576582f4', 'path': '\\EFI\\OpenBook\\systemd |
| alongside | Windows Boot Manager and BootOrder byte-identical (no consent to change the boot order, S11) | PASS | {'before': {'Boot0007': '3e182ed8419b4f030d4e5677312458e2584cd6c23922f55c2486b0df1b6ed056', 'BootOrder': 'a5a4a12b5826a4f4613fd697908f2d941fb713923d1aa9cb4d0b24 |
| alongside | no SELinux denial for the app or the daemon | PASS |  |
| alongside | test step: BootNext points at OpenBook's entry | PASS | 0005 |
| alongside-boot | every expect step matched | PASS | 21/21 (all steps done) |
| alongside-boot | OVMF started OpenBook through its entry once (BootCurrent = the new entry, BootNext used up) | PASS | {'boot_current': '0005', 'boot_next': None, 'entry': '0005'} |
| alongside-boot | Windows stays first in BootOrder; its entry is still there | PASS | ['0007', '0002', '0003', '0000', '0001', '0004'] |
| alongside-boot | Android booted from the Windows disk's new partitions (installed=alongside) | PASS | 18 |
