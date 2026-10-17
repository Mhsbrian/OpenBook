# Touchpad clock in QEMU: before and after the EventHub patch

`scripts/power/touchpad/touchpad-qemu.sh` on each image: the G14's ELAN descriptor on uhid, four 2 s one-finger strokes, 2,008 reports.

| | before (`anal178c`) | after (EventHub patch) |
|---|---|---|
| image | `openbook-live-20261017-anal178c.img` | `openbook-live-20261017-anal178-eventhub-test.img` |
| EV_REP on the touchpad | True | True |
| classes | TOUCH \| TOUCH_MT \| TOUCHPAD | TOUCH \| TOUCH_MT \| TOUCHPAD |
| BTN_TOOL_FINGER repeat frames | 173 | 0 |
| Clock changed backwards | 172 | 0 |
| frames / with MSC_TIMESTAMP | 2181 / 2008 | 2008 / 2008 |
| touchpad_clock verdict | False | True |

The after image: `openbook-live-20261017-anal178-eventhub-test` (test only, not for a stick), the G14 product built from this branch (`main` `b94d59c` plus the patch; build log `frameworks/native: base ae266dcb706d + 1 patches`). `frameworks/native` differs between the two images by this patch only (both at pin `ae266dcb706d`). The before image's product is `combined`'s (`01750c5`); the after image also has `main`'s later device changes (ANAL-191's installer and setup), none of them in input. The kernel is the same in both.
