# Live image QEMU run: openbook-live-helpertest7-20261017

12/12 checks passed.

| Case | Check | Result | Detail |
|---|---|---|---|
| logs | every expect step matched | PASS | 4/4 (QEMU exited (0)) |
| logs | Android shut down by itself after saving | PASS | QEMU exited (0) |
| logs | openbook/logs/live-NNN/ on the ESP | PASS | ['live-001'] |
| logs | dmesg, logcat, system facts, screenshot and summary saved | PASS | ['collect-final.txt', 'dmesg.txt', 'logcat-final.txt', 'logcat-stream.txt', 'screen-final.png', 'summary.json'] |
| logs | summary.json: second stage seen, captures done | PASS | second stage 2.6 s, boot_completed True, 1 capture(s) |
| logs | dmesg.txt non-empty | PASS | 403659 |
| logs | logcat saved | PASS | 2966899 |
| logs | screenshot is a PNG | PASS | 1973789 |
| logs | logcat streamed to the stick from early second stage | PASS | 5769926 |
| logs | wake lock held while recording (no suspend) | PASS |  |
| logs | system facts saved | PASS |  |
| logs | stick GPT valid (sgdisk -v) | PASS |  |
