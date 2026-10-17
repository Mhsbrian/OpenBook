# Installer wizard in QEMU: openbook-live-20261017-anal191e.img

25/25 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| dryrun | every expect step matched | PASS | 122/122 (all steps done) |
| dryrun | SELinux enforcing | PASS | fe52d13] [ro.boot.openbook.live]: [1] [ro.boot.openbook.loader]: [sdboot] [ro.build.fingerprint]: [OpenBook/anybook_g14_x86_64/anybook_g14:17/CP2A.260605.016/en |
| dryrun | the wizard started by itself after boot | PASS |     topResumedActivity=ActivityRecord{168418101 u0 org.openbook.installer/.MainActivity t9}   ResumedActivity: ActivityRecord{168418101 u0 org.openbook.installe |
| dryrun | openbook_installd runs in its own domain | PASS | 040 282332 do_epoll_wait       0 S org.openbook.installer u:r:openbook_installd:s0       root          3084     1   10802140   3876 do_sys_poll         0 S open |
| dryrun | whole-disk nodes carry openbook_disk_block_device | PASS |  |
| dryrun | CLI dry run: a plan for the NVMe disk | PASS | {"plan_sha256":"6b811c27aa510b04a3474cde920d3f710f356e3994c2a2089a2c9f062a2e4b91","created":"2026-10-17T13:49:03Z","schema":"openbook-install-plan/1","engine":" |
| dryrun | the app's dry run went through the daemon | PASS |  |
| dryrun | screens captured: welcome, hardware, choose, disk, plan | PASS | ['shot-1-welcome.png', 'shot-2-hardware.png', 'shot-3-choose-install.png', 'shot-3-choose.png', 'shot-4-disk-selected.png', 'shot-4-disk.png', 'shot-4-plan.png' |
| dryrun | the NVMe disk has no allocated block after the dry run (nothing written) | PASS | 0 blocks |
| dryrun | no SELinux denial for the app or the daemon | PASS |  |
| install | every expect step matched | PASS | 174/174 (QEMU exited (0)) |
| install | screens captured: confirm, typed, install, done | PASS | ['shot-1-welcome.png', 'shot-2-hardware.png', 'shot-3-choose-install.png', 'shot-3-choose.png', 'shot-4-disk-selected.png', 'shot-4-disk.png', 'shot-4-plan.png' |
| install | the daemon ran the install and it verified | PASS | nf (72 bytes) 13:53:28 wrote EFI/OpenBook/systemd-bootx64.efi (160256 bytes) 13:53:28 wrote EFI/BOOT/BOOTX64.EFI (160256 bytes) 13:53:28 the kernel re-read the  |
| install | no SELinux denial for the app or the daemon (enforcing) | PASS |  |
| install | the run ended with the guest's reboot (Restart now) | PASS | QEMU exited (0) |
| installed | the installed disk boots without the stick (screenshots) | PASS | ['shot-10.png', 'shot-120.png', 'shot-180.png', 'shot-20.png', 'shot-240.png', 'shot-30.png', 'shot-300.png', 'shot-360.png', 'shot-420.png', 'shot-45.png', 'sh |
| console | every expect step matched | PASS | 82/82 (all steps done) |
| console | boot_completed from the NVMe disk | PASS |  |
| console | every by-name link points at the NVMe disk | PASS | nvme0n1, nvme0n1p1, nvme0n1p10, nvme0n1p11, nvme0n1p12, nvme0n1p13, nvme0n1p2, nvme0n1p3, nvme0n1p4, nvme0n1p5, nvme0n1p6, nvme0n1p7, nvme0n1p8, nvme0n1p9 |
| console | no live flags; installed=whole; SELinux enforcing | PASS | [ro.boot.boot_part_uuid]: [13b7d7f4-c866-4c78-a5bf-59daa958d137] [ro.boot.openbook.installed]: [whole] [ro.boot.openbook.keyboard]: [us] [ro.boot.openbook.loade |
| console | installer launcher entry off and daemon never started on the installed system | PASS | ['0', 'daemon=[]'] |
| console | first screen of the installed system is OpenBook setup | PASS | 0 daemon=[] 0       topResumedActivity=ActivityRecord{60166576 u0 org.openbook.installer/.SetupActivity t2}  |
| console | after setup: provisioned, setup complete, setup off, the launcher on top | PASS | ['1', '1', '0', '      topResumedActivity=ActivityRecord{36378505 u0 com.android.launcher3/.uioverrides.QuickstepLauncher t9}'] |
| console | setup screens captured | PASS | ['shot-8-setup-language.png', 'shot-8-setup-lock.png', 'shot-8-setup-wifi.png', 'shot-9-desktop.png'] |
| console | AVC denials on the installed system (reported, not gated) | PASS | 54 lines |
