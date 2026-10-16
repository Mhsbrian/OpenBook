| variant | loader | /proc/bootconfig | slot | AVB state | boot_part_uuid | boot device found | 1st / 2nd stage | /data formatted | console dump | failure | run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gbl | GBL gbl-mainline:6296919847ee | 40 lines | _a | orange | - | - | yes / no | no | no | Failed to create devices required for first stage mount | 1/23 steps, 7.5 s |
| gbl-uuid | GBL gbl-mainline:6296919847ee | 41 lines | _a | orange | 5c2e760d | USB (0000:00:02.0) | yes / yes | yes | yes | - | 23/23 steps, 23.1 s |
| gbl-uuid-decoy | GBL gbl-mainline:6296919847ee | - | - | - | - | - | no / no | no | no | Failed to read bootloader message from misc partition: NotUnique | 0/0 steps, 30.5 s |
| grub | GRUB | 28 lines | _a | orange | 5c2e760d | USB (0000:00:02.0) | yes / yes | yes | yes | - | 23/23 steps, 24.0 s |
| grub-2nd-boot | GRUB | 28 lines | _a | orange | 5c2e760d | USB (0000:00:02.0) | yes / yes | no | yes | - | 23/23 steps, 23.9 s |
| grub-bad-digest | GRUB | 28 lines | _a | orange | 5c2e760d | USB (0000:00:02.0) | yes / yes | yes | yes | - | 23/23 steps, 23.9 s |
| grub-slot-b | GRUB | 28 lines | _b | orange | 5c2e760d | - | no / no | no | no | - | 0/0 steps, 8.6 s |
| sdboot | systemd-boot | 29 lines | _a | orange | 5c2e760d | USB (0000:00:02.0) | yes / yes | yes | yes | - | 23/23 steps, 28.9 s |
| uki | - | **empty** | - | - | - | - | no / no | no | no | - | 0/0 steps, 6.8 s |

- **gbl-uuid**: by-name: EFI->/dev/block/sda1, boot_a->/dev/block/sda3, metadata->/dev/block/sda17, misc->/dev/block/sda2, super->/dev/block/sda18, userdata->/dev/block/sda19, vbmeta_a->/dev/block/sda9
- **grub**: by-name: EFI->/dev/block/sda1, boot_a->/dev/block/sda3, metadata->/dev/block/sda17, misc->/dev/block/sda2, super->/dev/block/sda18, userdata->/dev/block/sda19, vbmeta_a->/dev/block/sda9; BOOT_IMAGE=(hd0,gpt1)/anybook/a/kernel
- **grub-2nd-boot**: by-name: EFI->/dev/block/sda1, boot_a->/dev/block/sda3, metadata->/dev/block/sda17, misc->/dev/block/sda2, super->/dev/block/sda18, userdata->/dev/block/sda19, vbmeta_a->/dev/block/sda9; BOOT_IMAGE=(hd0,gpt1)/anybook/a/kernel
- **grub-bad-digest**: libfs_avb reported a vbmeta digest mismatch; by-name: EFI->/dev/block/sda1, boot_a->/dev/block/sda3, metadata->/dev/block/sda17, misc->/dev/block/sda2, super->/dev/block/sda18, userdata->/dev/block/sda19, vbmeta_a->/dev/block/sda9; BOOT_IMAGE=(hd0,gpt1)/anybook/a/kernel
- **grub-slot-b**: BOOT_IMAGE=(hd0,gpt1)/anybook/b/kernel
- **sdboot**: by-name: EFI->/dev/block/sda1, boot_a->/dev/block/sda3, metadata->/dev/block/sda17, misc->/dev/block/sda2, super->/dev/block/sda18, userdata->/dev/block/sda19, vbmeta_a->/dev/block/sda9
- **uki**: kernel: 'bootconfig' found on command line, but no bootconfig found
