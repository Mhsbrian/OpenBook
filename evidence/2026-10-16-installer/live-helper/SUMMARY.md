# Save-logs helper after the G14 run of `openbook-live-20261017a` (ANAL-190, 2026-10-17)

**What the G14 showed** (read back from the owner's stick, `~/anybook/installer/g14/stick-20261017T004141Z/`; ANAL-176 has the redacted copy plan):
- Boot 1 on the freshly written stick spent its first 79 s decompressing APEXes into `/data` on the USB stick (`apexd: Decompressing …`). It looked dead.
- Boot 2 reached `sys.boot_completed=1` at 39 s: the first complete Android boot on the G14.
  - From 33.7 s amdgpu rejected the compositor's commits 76 times: `dc_state_add_plane … can not attach plane_state … Maximum is: 4`. Nothing reached the panel, not even the pointer.
  - At 45 s the machine suspended (s2idle).
- Neither boot left logcat or a capture on the stick. The helper captured at second stage + 90 s and `boot_completed` + 45 s, and the machine was asleep by then. The owner later saw it wake ("flashed the desktop") and power off with the stick removed.

**Why it slept** (QEMU, `logcat-stream`): `PowerManagerService: Going to sleep due to timeout (… screenOffTimeout=60000, activityTimeoutWM=10000 …)`. The lock screen sets a 10 s inactivity timeout right after boot (`lock-screen-qemu.png`: "Press Enter to unlock").

**Helper changes** (`scripts/installer/live-init.c`), all in the save-logs entry only:
- streams `logcat -b all` to `logcat-stream.txt` from early second stage, restarting it until logd is up;
- holds a kernel wake lock (`/sys/power/wake_lock`, retried until Android's shell works), through the shutdown request;
- at `boot_completed`, sets `stay_on_while_plugged_in=7` and sends `KEYCODE_WAKEUP` every 4 s until the final capture, so the lock-screen timeout cannot put the machine to sleep on battery either; the setting is restored before shutdown;
- captures at second stage + 30 s (if not booted) and at `boot_completed` + 20 s; no `cat /sys/power/wakeup_count` (it blocks while a wake lock is held).

**QEMU result (`qemu/SUMMARY.md`): 12 of 12** on `openbook-live-helpertest7-20261017` (ANAL-199's PR #35 product). `boot_completed` at 28 s; captures and a real screenshot saved; Android then shut down and **QEMU powered off ("reboot: Power down")**. The power-off stall of images `b`/`c` was the machine suspending between the release of the wake lock and the shutdown, not a kernel hang. ANAL-199's own boots show the same stall, likely for the same reason (H).
