# Live image QEMU run: openbook-live-20261017-anal200

10/10 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| logs | every expect step matched | PASS | 4/4 (QEMU exited (0)) |
| logs | Android shut down by itself after saving | PASS | QEMU exited (0) |
| logs | openbook/logs/live-NNN/ on the ESP | PASS | ['live-001'] |
| logs | dmesg, logcat, system facts, screenshot and summary saved | PASS | ['collect-final.txt', 'dmesg.txt', 'hwtest-final.txt', 'logcat-final.txt', 'prior-boots.tar.gz', 'prior-boots.txt', 'screen-final.png', 'summary.json'] |
| logs | summary.json: second stage seen, captures done | PASS | second stage 2.6 s, boot_completed True, 1 capture(s) |
| logs | dmesg.txt non-empty | PASS | 302937 |
| logs | logcat saved | PASS | 2736058 |
| logs | screenshot is a PNG | PASS | 11778 |
| logs | system facts saved | PASS |  |
| logs | stick GPT valid (sgdisk -v) | PASS |  |
