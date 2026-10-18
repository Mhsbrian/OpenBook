# Installer wizard in QEMU: openbook-live-20261018-anal192d.img

51/51 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| dryrun | every expect step matched | PASS | 126/126 (all steps done) |
| dryrun | SELinux enforcing | PASS | bdaa893] [ro.boot.openbook.live]: [1] [ro.boot.openbook.loader]: [sdboot] [ro.build.fingerprint]: [OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/en |
| dryrun | the wizard started by itself after boot | PASS |     topResumedActivity=ActivityRecord{218693196 u0 org.openbook.installer/.MainActivity t11}   ResumedActivity: ActivityRecord{218693196 u0 org.openbook.install |
| dryrun | openbook_installd runs in its own domain | PASS | ime 0 0 u:object_r:openbook_efivarfs:s0 /sys/firmware/efi/efivars u:object_r:openbook_efivarfs:s0 Boot0000-8be4df61-93ca-11d2-aa0d-00e098032b8c u:object_r:openb |
| dryrun | whole-disk nodes carry openbook_disk_block_device | PASS |  |
| dryrun | CLI dry run: a plan for the NVMe disk | PASS | {"plan_sha256":"ab3b329f67e12717614e98514411dcb7ff3ac66fa8c86430ae133611f9383725","created":"2026-10-18T10:11:56Z","schema":"openbook-install-plan/1","engine":" |
| dryrun | the app's dry run went through the daemon | PASS |  |
| dryrun | screens captured: welcome, hardware, choose, disk, plan | PASS | ['shot-1-welcome.png', 'shot-2-hardware.png', 'shot-3-choose-install.png', 'shot-3-choose.png', 'shot-4-disk-selected.png', 'shot-4-disk.png', 'shot-4-plan.png' |
| dryrun | the NVMe disk has no allocated block after the dry run (nothing written) | PASS | 0 blocks |
| dryrun | no SELinux denial for the app or the daemon | PASS |  |
| install | every expect step matched | PASS | 181/181 (QEMU exited (0)) |
| install | screens captured: confirm, typed, install, done | PASS | ['shot-1-welcome.png', 'shot-2-hardware.png', 'shot-3-choose-install.png', 'shot-3-choose.png', 'shot-4-disk-selected.png', 'shot-4-disk.png', 'shot-4-plan.png' |
| install | the daemon ran the install and it verified | PASS |  re-read the partition table 10:18:22 nvram: created Boot0005 "OpenBook" -> HD(1, GPT, a8c47b9b-7fd6-4ce9-87fd-fd9a8318dabf)/\EFI\OpenBook\systemd-bootx64.efi;  |
| install | no SELinux denial for the app or the daemon (enforcing) | PASS |  |
| install | the run ended with the guest's reboot (Restart now) | PASS | QEMU exited (0) |
| install | firmware entry: one "OpenBook" Boot#### -> HD(1, GPT)/\EFI\OpenBook\systemd-bootx64.efi, first in BootOrder | PASS | {'entry': {'num': '0005', 'description': 'OpenBook', 'active': True, 'partition': 1, 'partuuid': 'a8c47b9b-7fd6-4ce9-87fd-fd9a8318dabf', 'path': '\\EFI\\OpenBoo |
| install | efivarfs mounted by init with its own label (openbook_efivarfs) | PASS | ime 0 0 u:object_r:openbook_efivarfs:s0 /sys/firmware/efi/efivars u:object_r:openbook_efivarfs:s0 Boot0000-8be4df61-93ca-11d2-aa0d-00e098032b8c u:object_r:openb |
| nvram-boot | every expect step matched | PASS | 21/21 (all steps done) |
| nvram-boot | the copy has no fallback path: EFI/BOOT/BOOTX64.EFI deleted | PASS | ::/EFI/OpenBook/ ::/EFI/BOOT/ ::/EFI/OpenBook/systemd-bootx64.efi |
| nvram-boot | the firmware kept the install's BootOrder (OpenBook first; no bootindex hints) | PASS | ['0005', '0002', '0003', '0000', '0001', '0004'] |
| nvram-boot | OVMF started the installed system through OpenBook's entry (BootCurrent = the entry the install made) | PASS | {'boot_current': '0005', 'entry': '0005', 'installed': '0005'} |
| nvram-boot | Android booted from the NVMe disk (by-name links on nvme0n1, installed=whole) | PASS | 14 |
| alongside | every expect step matched | PASS | 145/145 (all steps done) |
| alongside | before: Windows Boot Manager (Boot0007) first in BootOrder | PASS | ['0007', '0002', '0003', '0000', '0001', '0004'] |
| alongside | the install verified (daemon, enforcing) | PASS |  |
| alongside | one new "OpenBook" entry -> HD(1, GPT, the Windows ESP)/\EFI\OpenBook\systemd-bootx64.efi | PASS | {'num': '0005', 'description': 'OpenBook', 'active': True, 'partition': 1, 'partuuid': '6a3b9ad6-5164-4959-b434-5bca07f9786a', 'path': '\\EFI\\OpenBook\\systemd |
| alongside | Windows Boot Manager byte-identical; BootOrder = the old order plus OpenBook at the end (no consent; owner decision 2026-10-17) | PASS | {'before': ['0007', '0002', '0003', '0000', '0001', '0004'], 'after': ['0007', '0002', '0003', '0000', '0001', '0004', '0005'], 'Boot0007': ['1af1ee5ac97bc2a708 |
| alongside | Confirm and Done say OpenBook is added to the boot menu and Windows stays the default | PASS | ['shot-a4-disk-alongside.png', 'shot-a4-plan.png', 'shot-a5-confirm.png', 'shot-a7-done.png'] |
| alongside | no SELinux denial for the app or the daemon | PASS |  |
| alongside-default | every expect step matched | PASS | 36/36 (all steps done) |
| alongside-default | the install's NVRAM, no hints: the firmware starts Windows Boot Manager by default (the stand-in reports BootCurrent=0007; OpenBook last in BootOrder) | PASS | windows-standin started: BootCurrent=0007 BootOrder=0007,0002,0003,0000,0001,0004,0005 |
| alongside-default | the firmware's boot menu lists OpenBook (it is in BootOrder) | PASS | ['Windows Boot Manager', 'OpenBook'] |
| alongside-default | picked in the boot menu, the firmware started OpenBook's entry (BootCurrent = the new entry) | PASS | {'boot_current': '0005', 'boot_next': None, 'entry': '0005'} |
| alongside-default | Windows still first, OpenBook still last in BootOrder | PASS | ['0007', '0002', '0003', '0000', '0001', '0004', '0005'] |
| alongside-default | Android booted from the Windows disk's new partitions (installed=alongside, enforcing) | PASS | 18 |
| alongside-default | no SELinux denial for OpenBook's domains | PASS |  |
| alongside-default | test step: BootNext points at OpenBook's entry | PASS | 0005 |
| alongside-boot | every expect step matched | PASS | 21/21 (all steps done) |
| alongside-boot | OVMF started OpenBook through its entry once (BootCurrent = the new entry, BootNext used up) | PASS | {'boot_current': '0005', 'boot_next': None, 'entry': '0005'} |
| alongside-boot | Windows stays first in BootOrder; its entry is still there | PASS | ['0007', '0002', '0003', '0000', '0001', '0004', '0005'] |
| alongside-boot | Android booted from the Windows disk's new partitions (installed=alongside) | PASS | 18 |
| installed | the installed disk boots without the stick (screenshots) | PASS | ['shot-10.png', 'shot-120.png', 'shot-180.png', 'shot-20.png', 'shot-240.png', 'shot-30.png', 'shot-300.png', 'shot-360.png', 'shot-420.png', 'shot-45.png', 'sh |
| console | every expect step matched | PASS | 86/86 (all steps done) |
| console | boot_completed from the NVMe disk | PASS |  |
| console | every by-name link points at the NVMe disk | PASS | nvme0n1, nvme0n1p1, nvme0n1p10, nvme0n1p11, nvme0n1p12, nvme0n1p13, nvme0n1p2, nvme0n1p3, nvme0n1p4, nvme0n1p5, nvme0n1p6, nvme0n1p7, nvme0n1p8, nvme0n1p9 |
| console | no live flags; installed=whole; SELinux enforcing | PASS | [init.svc.openbook_addons]: [stopped] [ro.boot.boot_part_uuid]: [a8c47b9b-7fd6-4ce9-87fd-fd9a8318dabf] [ro.boot.openbook.installed]: [whole] [ro.boot.openbook.k |
| console | installer launcher entry off and daemon never started on the installed system | PASS | ['0', 'daemon=[]'] |
| console | first screen of the installed system is OpenBook setup | PASS | 0 daemon=[] 0       topResumedActivity=ActivityRecord{183115265 u0 org.openbook.installer/.SetupActivity t2}  |
| console | after setup: provisioned, setup complete, setup off, the launcher on top | PASS | ['1', '1', '0', '      topResumedActivity=ActivityRecord{215932894 u0 com.android.launcher3/.uioverrides.QuickstepLauncher t9}'] |
| console | setup screens captured | PASS | ['shot-8-setup-language.png', 'shot-8-setup-lock.png', 'shot-8-setup-wifi.png', 'shot-9-desktop.png'] |
| console | AVC denials on the installed system (reported, not gated) | PASS | 50 lines |
