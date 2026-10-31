# Live image QEMU run: openbook-live-20261031-anal320pub

32/32 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| first | every expect step matched | PASS | 30/30 (QEMU exited (0)) |
| first | by-name links point at the USB stick only | PASS | 10 links: sda |
| first | openbook-live-init grew userdata and moved the backup GPT | PASS | grow: GPT backup moved LBA 6068223 -> 33554431; userdata 2097152 -> 29583360 sectors |
| first | stick GPT valid afterwards, backup at the end (sgdisk -v) | PASS | {"ok": true, "disk_sectors": 33554432, "last_usable": 33554398, "userdata_sectors": 29583360, "userdata_to_end": 2048} |
| first | /data formatted at the grown size | PASS | df /data 14789632 KiB, userdata 14791680 KiB |
| first | Android formatted the blank metadata and userdata | PASS | [    4.001226] init: [libfs_mgr] fs_mgr_mount_all(): /dev/block/sda7 is wiped and /metadata ext4 is formattable. Format it.; [    4.002429] init: [libfs_mgr] fs |
| first | marker file written to /data | PASS | openbook-live-marker-1793452570 |
| first | sys.boot_completed=1 within 600 s (desktop) | PASS | BOOTDONE=1 at uptime 11.57 s |
| first | screenshot after the boot wait | PASS |  |
| first | decoy NVMe disk unchanged after all its boots (sha256) | PASS | 4a307355a4fe9732 / 4a307355a4fe9732 |
| first | live-init report on the ESP | PASS | ['live-init-001.json', 'live-init-002.json'] |
| second | every expect step matched | PASS | 18/18 (QEMU exited (0)) |
| second | by-name links point at the USB stick only | PASS | 10 links: sda |
| second | openbook-live-init: nothing to grow | PASS |  |
| second | marker from the first boot still there | PASS | openbook-live-marker-1793452570 vs openbook-live-marker-1793452570 |
| reset | every expect step matched | PASS | 19/19 (QEMU exited (0)) |
| reset | by-name links point at the USB stick only | PASS | 10 links: sda |
| reset | metadata and userdata zeroed | PASS |  |
| reset | Android formatted them again | PASS |  |
| reset | marker gone | PASS |  |
| reset | reset recorded on the ESP | PASS | ['live-init-001.json', 'live-init-002.json'] |
| logs | every expect step matched | PASS | 4/4 (QEMU exited (0)) |
| logs | Android shut down by itself after saving | PASS | QEMU exited (0) |
| logs | openbook/logs/live-NNN/ on the ESP | PASS | ['live-001'] |
| logs | dmesg, logcat, system facts, screenshot and summary saved | PASS | ['collect-final.txt', 'dmesg.txt', 'hwtest-final.txt', 'logcat-final.txt', 'prior-boots.tar.gz', 'prior-boots.txt', 'screen-final.png', 'summary.json'] |
| logs | summary.json: second stage seen, captures done | PASS | second stage 2.6 s, boot_completed True, 1 capture(s) |
| logs | dmesg.txt non-empty | PASS | 312167 |
| logs | logcat saved | PASS | 2701011 |
| logs | vold leaves the boot stick alone | PASS | not managed: ['8:0'], scanned: [] |
| logs | screenshot is a PNG | PASS | 402494 |
| logs | system facts saved | PASS |  |
| logs | stick GPT valid (sgdisk -v) | PASS |  |
