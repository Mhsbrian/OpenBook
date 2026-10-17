#!/usr/bin/env bash
# Test of the AOSP lane lock (ANAL-176): scripts/aosp-docker.sh takes <data dir>/aosp/.lane.lock and keeps it until
# the container exits, and scripts/aosp-build.sh refuses unless its container owns it. Runs against a scratch data
# directory (its own lock, empty aosp/src, ccache and logs), so neither the shared tree nor the real lane lock is
# touched. A build "entered" when it got past the lane check: it then copies the device tree into the scratch
# aosp/src/device/anybook/ and stops on the missing AOSP projects. Needs docker and the anybook-aosp image.
#
# usage: aosp-lane-test.sh            prints one line per case and "N/N passed"; non-zero on any failure
set -uo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
S=$(mktemp -d "${TMPDIR:-/tmp}/aosp-lane-test.XXXXXX")
mkdir -p "$S/aosp/src" "$S/ccache" "$S/logs/aosp"
LOCK=$S/aosp/.lane.lock; : >> "$LOCK"
HOLDER=
cleanup() { [ -z "$HOLDER" ] || unhold; find "$S" -mindepth 1 -delete; rmdir "$S"; }
trap cleanup EXIT
pass=0 total=0
out=
ok() {
  total=$((total + 1))
  if [ "$1" = 0 ]; then pass=$((pass + 1)); echo "PASS $2"; else echo "FAIL $2"; tail -n 6 <<<"$out" | sed 's/^/     | /'; fi
}
reset() { find "$S/aosp/src" -mindepth 1 -delete; mkdir "$S/aosp/src/device"; }
entered() { [ -d "$S/aosp/src/device/anybook" ]; }
build() { ANYBOOK_HOME=$S "$R/scripts/aosp-docker.sh" "$@" /repo/scripts/aosp-build.sh anybook_g14_x86_64-cp2a-userdebug droid; }
# An unrelated holder for N seconds. -o: sleep does not inherit the lock, so killing flock releases it.
hold() { flock -o "$LOCK" sleep "$1" & HOLDER=$!; until ! flock -n "$LOCK" true; do :; done; }
unhold() { pkill -P "$HOLDER" 2>/dev/null; kill "$HOLDER" 2>/dev/null; wait "$HOLDER" 2>/dev/null; HOLDER=; }

# 1. The finding: an unwrapped build while an unrelated process holds the lock must not enter.
reset; hold 60
out=$(ANYBOOK_LANE_WAIT=5 build 2>&1); rc=$?
! entered && [ $rc != 0 ] && grep -q "no AOSP lane lock after 5 s" <<<"$out"
ok $? "unwrapped build, lock held by an unrelated process: waits, times out, rc $rc, nothing copied"
# 2. The same with aosp-build.sh started by docker run directly (no aosp-docker.sh), with no token and a forged one.
for tok in "" forged; do
  reset
  out=$(docker run --rm -i --init -u "$(id -u):$(id -g)" --security-opt seccomp=unconfined \
    --security-opt systempaths=unconfined -v "$S/aosp:/aosp" -v "$S/ccache:/ccache" -v "$S/logs/aosp:/logs" \
    -v "$R:/repo:ro" ${tok:+-e ANYBOOK_LANE_TOKEN=$tok} anybook-aosp /repo/scripts/aosp-build.sh x droid 2>&1); rc=$?
  ! entered && [ $rc != 0 ] && grep -q "does not hold the AOSP lane lock" <<<"$out"
  ok $? "direct docker run, ${tok:-no} token, lock held by an unrelated process: refused, rc $rc, nothing copied"
done
# 3. When the other holder lets go, the waiting build takes the lock and enters.
reset; unhold; hold 4
out=$(build 2>&1); rc=$?
entered && grep -q "waiting for the AOSP lane lock" <<<"$out"
ok $? "unwrapped build waits for an unrelated holder (4 s), then enters"
unhold
# 4. Lock free: the build takes it itself and enters.
reset; out=$(build 2>&1); entered; ok $? "unwrapped build, lock free: enters"
# 5. The caller holds it (flock around aosp-docker.sh): found in /proc/locks, no wait, no deadlock.
reset; out=$(ANYBOOK_HOME=$S ANYBOOK_LANE_WAIT=5 flock "$LOCK" "$R/scripts/aosp-docker.sh" \
  /repo/scripts/aosp-build.sh x droid 2>&1)
entered && grep -q "the caller holds the AOSP lane lock" <<<"$out"; ok $? "flock <lock> aosp-docker.sh: caller's lock used, enters"
# 6. The caller holds it through an inherited fd: only with ANYBOOK_LANE_LOCK_HELD=1; without it, it waits.
reset; out=$(ANYBOOK_HOME=$S ANYBOOK_LANE_WAIT=3 bash -c 'exec 9>>"$1"; flock 9; "$2/scripts/aosp-docker.sh" /repo/scripts/aosp-build.sh x droid' _ "$LOCK" "$R" 2>&1)
! entered; ok $? "lock held through an fd, no ANYBOOK_LANE_LOCK_HELD: waits, does not enter"
reset; out=$(ANYBOOK_HOME=$S ANYBOOK_LANE_LOCK_HELD=1 bash -c 'exec 9>>"$1"; flock 9; "$2/scripts/aosp-docker.sh" /repo/scripts/aosp-build.sh x droid' _ "$LOCK" "$R" 2>&1)
entered; ok $? "lock held through an fd, ANYBOOK_LANE_LOCK_HELD=1: enters"
# 7. -d keeps the lock until the container exits (a 6 s container under ANYBOOK_LANE=1), then lets it go.
name=aosp-lane-test-$$
ANYBOOK_HOME=$S ANYBOOK_LANE=1 "$R/scripts/aosp-docker.sh" -d "$name" sleep 6 >/dev/null
sleep 2; flock -n "$LOCK" true; held=$?
docker wait "$name" >/dev/null 2>&1; sleep 1; flock -n "$LOCK" true; free=$?
[ $held != 0 ] && [ $free = 0 ]; ok $? "-d: lock held while the container runs, free after it exits"
# 8. ANYBOOK_LANE_UNLOCKED=1: no lane (a tree of one's own), even with the lock held elsewhere.
reset; hold 60; out=$(ANYBOOK_LANE_UNLOCKED=1 build 2>&1); entered; ok $? "ANYBOOK_LANE_UNLOCKED=1: enters without the lane"
unhold
echo "$pass/$total passed"
[ "$pass" = "$total" ]
