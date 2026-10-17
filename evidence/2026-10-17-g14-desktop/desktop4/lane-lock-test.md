# AOSP lane lock for builds and the image snapshot (ANAL-176, 2026-10-17)

The Checker's follow-up on PR #42 at `a81c25e`: `installer-image.sh` checked the build container names once and refused, rather than waiting, and nothing stopped a build from starting during its snapshot of `PRODUCT_OUT`. Builds now have to hold the lane lock (`~/anybook/aosp/.lane.lock`, `/aosp/.lane.lock` in the build container), and the snapshot waits for and holds the same lock. The images are unaffected: `desktop4`'s snapshot predates ANAL-179's build (its newest file is 02:53:15Z, the build started writing later; see `SUMMARY.md`).

| Test | Result |
|---|---|
| `aosp-build.sh` without the lock (scratch `ANYBOOK_HOME`, so neither the shared tree nor the real lock is touched) | refused, rc 1: `aosp-build.sh: nobody holds the AOSP lane lock; run the build under it` |
| the same under `flock <scratch>/aosp/.lane.lock` | passes the check: `=== … target anybook_g14_x86_64-cp2a-userdebug goals droid` (then stops on the empty scratch tree) |
| the lock as seen from inside the build container | free when free, held while the host holds it (`flock -n /aosp/.lane.lock`) |
| `installer-image.sh` while another process held the real lane lock for 20 s (04:10:58 to 04:11:18Z) | printed `waiting for the AOSP lane lock …`, took its snapshot at 04:11:19Z, image built, rc 0 |
| the same with the lock free | no wait, snapshot at once |
| `OPENBOOK_LANE_LOCK_HELD=1` under the caller's own `flock` | no second lock (which would wait for ever), image built, rc 0 |

Logs: `<data dir>/logs/installer/live-anal176-locktest-20261017T0410*Z.log` … `T041213Z.log`. The test images and snapshots were deleted.
