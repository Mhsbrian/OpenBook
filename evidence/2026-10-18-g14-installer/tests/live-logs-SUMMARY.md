# Live image QEMU run: openbook-live-20261018-anal191i

11/11 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| logs | every expect step matched | PASS | 4/4 (QEMU exited (0)) |
| logs | Android shut down by itself after saving | PASS | QEMU exited (0) |
| logs | openbook/logs/live-NNN/ on the ESP | PASS | ['live-001'] |
| logs | dmesg, logcat, system facts, screenshot and summary saved | PASS | ['collect-final.txt', 'dmesg.txt', 'hwtest-final.txt', 'logcat-final.txt', 'prior-boots.tar.gz', 'prior-boots.txt', 'screen-final.png', 'summary.json'] |
| logs | summary.json: second stage seen, captures done | PASS | second stage 2.6 s, boot_completed True, 1 capture(s) |
| logs | dmesg.txt non-empty | PASS | 308171 |
| logs | logcat saved | PASS | 2685837 |
| logs | vold leaves the boot stick alone | PASS | not managed: ['8:0'], scanned: [] |
| logs | screenshot is a PNG | PASS | 402809 |
| logs | system facts saved | PASS |  |
| logs | stick GPT valid (sgdisk -v) | PASS |  |
