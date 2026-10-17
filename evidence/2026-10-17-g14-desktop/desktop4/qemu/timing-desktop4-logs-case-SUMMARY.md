# Live image QEMU run: openbook-live-20261017-desktop4

8/10 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| logs | every expect step matched | PASS | 4/4 (all steps done) |
| logs | Android shut down by itself after saving | FAIL | all steps done |
| logs | openbook/logs/live-NNN/ on the ESP | PASS | ['live-001'] |
| logs | dmesg, logcat, system facts, screenshot and summary saved | PASS | ['collect-final.txt', 'dmesg.txt', 'logcat-final.txt', 'prior-boots.tar.gz', 'screen-final.png', 'summary.json'] |
| logs | summary.json: second stage seen, captures done | PASS | second stage 2.7 s, boot_completed True, 1 capture(s) |
| logs | dmesg.txt non-empty | PASS | 360119 |
| logs | logcat saved | PASS | 3008320 |
| logs | screenshot is a PNG | FAIL | 0 |
| logs | system facts saved | PASS |  |
| logs | stick GPT valid (sgdisk -v) | PASS |  |
