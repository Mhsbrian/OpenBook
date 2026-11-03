#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# One G14 session at a time (ANAL-336). Every task that drives the G14 over adb holds this host-side lock for the
# whole session, so two tasks never test, update or capture at once. g14-adb.sh and gpu-diag.sh take it
# themselves; anything else that talks to the G14 runs under `g14-lock.sh run`.
#
# usage: g14-lock.sh run OWNER [-w SECONDS] -- CMD [ARGS...]
#            hold the lock while CMD and every process it starts run, then release it. OWNER names the task, e.g.
#            ANAL-336. Busy: print the holder and exit 75, or wait up to SECONDS for it. CMD sees
#            OPENBOOK_G14_LOCK_OWNER=OWNER; tools started under it don't take the lock again. CMD runs in its own
#            session and process group. The first INT, TERM or HUP to this script reaches the whole group as TERM;
#            later ones are not forwarded, so they can't cut the session's clean-up short. The lock goes only when
#            the group is gone. From that first signal the session, its leader included, has
#            OPENBOOK_G14_LOCK_GRACE seconds (300) to clean up; then the whole group gets KILL. What it leaves
#            running when CMD ends normally gets TERM, then KILL after the same grace.
#            Daemons that leave the group themselves (the adb server) are not part of the session and never hold
#            the lock. Only a SIGKILL to this script releases the lock while the session still runs.
#        g14-lock.sh status
#            "free", or the holder: owner, pid, start time and command. Exit 0 free, 75 held.
#
# A gpu-diag run that could not confirm its sampler's processes on the G14 stopped leaves <lock>.pending-cleanup.
# Until `scripts/gpu-diag.sh reap` (or the next gpu-diag run, which reaps first) clears it, the G14 counts as held:
# `run` refuses every other command (exit 75) and `status` reports it.
#
# Env: OPENBOOK_G14_LOCK  lock file (default <data dir>/locks/g14.lock; the holder record is <lock>.holder)
# Test: tests/g14-lock-test.py
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
LOCK=${OPENBOOK_G14_LOCK:-$A/locks/g14.lock}
HOLDER=$LOCK.holder
CLEANUP=$LOCK.pending-cleanup
BUSY=75
GRACE=${OPENBOOK_G14_LOCK_GRACE:-300}
mkdir -p "$(dirname "$LOCK")"
command -v flock >/dev/null || { echo "g14-lock: flock(1) is missing (util-linux)" >&2; exit 2; }

holder() { [ -s "$HOLDER" ] && cat "$HOLDER" || echo "(no holder record)"; }

case ${1:-} in
  status)
    exec 9>>"$LOCK"
    if flock -n 9; then
      [ -s "$CLEANUP" ] && { echo "held: gpu-diag clean-up pending ($(cat "$CLEANUP")); run scripts/gpu-diag.sh reap"; exit $BUSY; }
      echo free; exit 0
    fi
    echo "held: $(holder)"; exit $BUSY ;;
  run)
    OWNER=${2:?usage: g14-lock.sh run OWNER [-w SECONDS] -- CMD [ARGS...]}; shift 2
    WAIT=
    [ "${1:-}" = -w ] && { WAIT=$2; shift 2; }
    [ "${1:-}" = -- ] && shift
    [ $# -gt 0 ] || { echo "g14-lock: no command" >&2; exit 2; }
    case $OWNER in *[!A-Za-z0-9._:@-]*|'') echo "g14-lock: owner '$OWNER': letters, digits and ._:@- only" >&2; exit 2 ;; esac
    if [ -n "${OPENBOOK_G14_LOCK_OWNER:-}" ]; then
      # Already inside a session: the same owner nests, another owner is a mistake.
      [ "$OPENBOOK_G14_LOCK_OWNER" = "$OWNER" ] && exec "$@"
      echo "g14-lock: this shell already holds the G14 for $OPENBOOK_G14_LOCK_OWNER, not $OWNER" >&2; exit 2
    fi
    exec 9>>"$LOCK"
    if [ -n "$WAIT" ]; then
      flock -w "$WAIT" 9 || { echo "g14-lock: the G14 is still in use after ${WAIT}s: $(holder)" >&2; exit $BUSY; }
    else
      flock -n 9 || { echo "g14-lock: the G14 is in use: $(holder)" >&2; exit $BUSY; }
    fi
    if [ -s "$CLEANUP" ] && [ "$(basename "$1")" != gpu-diag.sh ]; then
      echo "g14-lock: a gpu-diag run could not confirm its sampler stopped on the G14 ($(cat "$CLEANUP"));" \
        "run scripts/gpu-diag.sh reap first" >&2
      exit $BUSY
    fi
    printf 'owner=%s pid=%s since=%s cmd=%s\n' "$OWNER" "$$" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "$(basename "$1") ${*:2}" > "$HOLDER"
    export OPENBOOK_G14_LOCK_OWNER=$OWNER
    trap ': > "$HOLDER"' EXIT
    # Only this shell holds fd 9: a daemon the session starts never keeps the G14 locked. The session gets its own
    # session and process group. A background job of a non-interactive shell is no group leader, so setsid doesn't
    # fork and $child leads the group.
    setsid "$@" 9>&- 0<&0 &
    child=$!
    now_ms() { local t=$EPOCHREALTIME; echo $(( ${t%[.,]*} * 1000 + 10#${t#*[.,]} / 1000 )); }
    group_alive() { kill -0 -- "-$child" 2>/dev/null; }
    leader_alive() { [ -e "/proc/$child" ] && [ "$(sed 's/.*) //' "/proc/$child/stat" 2>/dev/null | cut -d' ' -f1)" != Z ]; }
    deadline= killed=0
    stop() {  # the first INT/TERM/HUP: TERM to the whole session, and the clean-up deadline starts now
      [ -z "$deadline" ] || return 0
      deadline=$(( $(now_ms) + GRACE * 1000 ))
      kill -TERM -- "-$child" 2>/dev/null || kill -TERM "$child" 2>/dev/null || true
    }
    overdue() {  # past the deadline: KILL the whole session, its leader included, once
      [ -n "$deadline" ] && [ $killed = 0 ] && [ "$(now_ms)" -ge "$deadline" ] || return 1
      echo "g14-lock: the session still runs ${GRACE}s after it was told to stop: KILL" >&2
      killed=1
      kill -KILL -- "-$child" 2>/dev/null || true
      kill -KILL "$child" 2>/dev/null || true
    }
    trap stop INT TERM HUP
    while leader_alive; do overdue || sleep 0.1; done
    wait "$child" && rc=0 || rc=$?
    if group_alive; then
      if [ -z "$deadline" ]; then
        echo "g14-lock: ending what the session left running (group $child)" >&2
        deadline=$(( $(now_ms) + GRACE * 1000 ))
        kill -TERM -- "-$child" 2>/dev/null || true
      else
        echo "g14-lock: waiting for the session's clean-up (group $child)" >&2
      fi
      while group_alive && [ $killed = 0 ]; do overdue || sleep 0.1; done
      t=0; while group_alive && [ $t -lt 100 ]; do sleep 0.1; t=$((t + 1)); done
      group_alive && echo "g14-lock: group $child still has unreaped processes; releasing" >&2
    fi
    exit $rc ;;
  *) echo "usage: g14-lock.sh run OWNER [-w SECONDS] -- CMD [ARGS...] | status" >&2; exit 2 ;;
esac
