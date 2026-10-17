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
| the lock after the snapshot, checked once a second while the rest of the image built | free in 22 of 22 checks (the log's `tee` starts before the lock is taken, so nothing inherits it), rc 0 |

Logs: `<data dir>/logs/installer/live-anal176-locktest-20261017T0410*Z.log` … `T041213Z.log`. The test images and snapshots were deleted.

## Round 2: the build entry point takes and keeps the lock

The Checker's next finding, at `f7dda31`: a busy lock does not show that a build's caller owns it. An unwrapped build started while an unrelated process held the lock passed the in-container check and copied 209 device files into a scratch tree. Now:
- `scripts/aosp-docker.sh` takes the lane lock for `aosp-build.sh` and `aosp-sync.sh` (any command with `ANYBOOK_LANE=1`) before the container starts. It waits for another holder (`ANYBOOK_LANE_WAIT`, default 4 h) and keeps the lock until the container exits: `docker run` holds it, and with `-d` a background `docker wait` does.
- A caller that already holds the lock is detected as an ancestor in `/proc/locks` (`flock <lock> …`), or says so with `ANYBOOK_LANE_LOCK_HELD=1` (a lock held through an inherited fd). The lock is opened on a new fd (`{LFD}`), so a lock fd the caller passes in stays open. Round 2 found that bug: bash execs the last command of `bash -c`, and `exec 9>>` closed the caller's fd 9.
- The container gets a per-run token, also written to `<data dir>/aosp/.lane.owner`. `aosp-build.sh` refuses unless the lock is held and the token is its own. A direct `docker run` of `aosp-build.sh`, or a forged token, is refused.

`scripts/aosp-lane-test.sh` runs against a scratch data directory (its own lock, tree and logs). It passed **10/10, twice, 22 s each**:

| Case | Result |
|---|---|
| **unwrapped build, lock held by an unrelated process** (the finding's exit condition) | waits, times out (5 s), rc 1, nothing copied |
| `docker run … aosp-build.sh` directly, no token, lock held elsewhere | refused, rc 1, nothing copied |
| the same with a forged token | refused, rc 1, nothing copied |
| unwrapped build, unrelated holder lets go after 4 s | waits, then enters |
| unwrapped build, lock free | takes it, enters |
| `flock <lock> aosp-docker.sh …` | "the caller holds the AOSP lane lock", enters, no deadlock |
| lock held through an fd, no `ANYBOOK_LANE_LOCK_HELD` | waits, does not enter |
| lock held through an fd, `ANYBOOK_LANE_LOCK_HELD=1` | enters |
| `-d` (a 6 s container) | lock held while it runs, free after it exits |
| `ANYBOOK_LANE_UNLOCKED=1` with the lock held elsewhere | enters (no lane) |

The snapshot side again uses a new fd, with the real lane lock. While another process held it, nothing was copied for 10 s; the snapshot ran after release (04:39:36Z), and the lock was free in 20 of 20 probes while the image assembled.

One lesson from that run: util-linux `flock FILE cmd` passes the lock fd to `cmd`, so killing the `flock` process alone does not release the lock (`-o` avoids that). The test's holder uses `flock -o`. An earlier holder without `-o` kept the real lane lock for about 6 minutes (04:33 to 04:39Z) until its orphaned `tail` was stopped.
