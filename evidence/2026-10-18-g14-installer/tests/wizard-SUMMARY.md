# Installer wizard in QEMU: openbook-live-20261018-anal191i.img

17/17 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| dryrun | every expect step matched | PASS | 126/126 (all steps done) |
| dryrun | SELinux enforcing | PASS | a38e2ba] [ro.boot.openbook.live]: [1] [ro.boot.openbook.loader]: [sdboot] [ro.build.fingerprint]: [OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/en |
| dryrun | the wizard started by itself after boot | PASS |     topResumedActivity=ActivityRecord{12039836 u0 org.openbook.installer/.MainActivity t11}   ResumedActivity: ActivityRecord{12039836 u0 org.openbook.installer |
| dryrun | openbook_installd runs in its own domain | PASS | ime 0 0 u:object_r:openbook_efivarfs:s0 /sys/firmware/efi/efivars u:object_r:openbook_efivarfs:s0 Boot0000-8be4df61-93ca-11d2-aa0d-00e098032b8c u:object_r:openb |
| dryrun | whole-disk nodes carry openbook_disk_block_device | PASS |  |
| dryrun | CLI dry run: a plan for the NVMe disk | PASS | {"plan_sha256":"897e5e59aab580ca04770d417668814c94ad8955e16e880fdceb420f6c855615","created":"2026-10-18T17:55:35Z","schema":"openbook-install-plan/1","engine":" |
| dryrun | the app's dry run went through the daemon | PASS |  |
| dryrun | screens captured: welcome, hardware, choose, disk, plan | PASS | ['shot-1-welcome.png', 'shot-2-hardware.png', 'shot-3-choose-install.png', 'shot-3-choose.png', 'shot-4-disk-selected.png', 'shot-4-disk.png', 'shot-4-plan.png' |
| dryrun | the NVMe disk has no allocated block after the dry run (nothing written) | PASS | 0 blocks |
| dryrun | no SELinux denial for the app or the daemon | PASS |  |
| install | every expect step matched | PASS | 181/181 (QEMU exited (0)) |
| install | screens captured: confirm, typed, install, done | PASS | ['shot-1-welcome.png', 'shot-2-hardware.png', 'shot-3-choose-install.png', 'shot-3-choose.png', 'shot-4-disk-selected.png', 'shot-4-disk.png', 'shot-4-plan.png' |
| install | the daemon ran the install and it verified | PASS |  re-read the partition table 18:00:23 nvram: created Boot0005 "OpenBook" -> HD(1, GPT, 056a9d7e-7385-4d34-aa78-c54691702be1)/\EFI\OpenBook\systemd-bootx64.efi;  |
| install | no SELinux denial for the app or the daemon (enforcing) | PASS |  |
| install | the run ended with the guest's reboot (Restart now) | PASS | QEMU exited (0) |
| install | firmware entry: one "OpenBook" Boot#### -> HD(1, GPT)/\EFI\OpenBook\systemd-bootx64.efi, first in BootOrder | PASS | {'entry': {'num': '0005', 'description': 'OpenBook', 'active': True, 'partition': 1, 'partuuid': '056a9d7e-7385-4d34-aa78-c54691702be1', 'path': '\\EFI\\OpenBoo |
| install | efivarfs mounted by init with its own label (openbook_efivarfs) | PASS | ime 0 0 u:object_r:openbook_efivarfs:s0 /sys/firmware/efi/efivars u:object_r:openbook_efivarfs:s0 Boot0000-8be4df61-93ca-11d2-aa0d-00e098032b8c u:object_r:openb |
