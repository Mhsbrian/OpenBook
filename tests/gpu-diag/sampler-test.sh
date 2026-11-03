#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The sampler's own output and behaviour, produced on this host: scripts/gpu-diag/device.sh's real functions (sample,
# its monitor and log watchers, up_cs, layers, load_sample...) with only dumpsys, ps and logcat stubbed.
#   - Clean runs (default, newline and comma IFS, an app whose only process is PKG:name): integer timings with end
#     not before start, the layer name intact, epoch bounds, and through gpu-diag-summary.py no malformed line and
#     no gap at the 120 Hz bound, even with a slow log source and a slow `dumpsys power` (the PR #150 review and
#     qualification attempt 2).
#   - Input arriving while those are slow, a new kernel/app/ANR error arriving after old ones, a log stream that
#     ends, a monitor that dies: each stops the run with its reason and exit status.
#   - Coverage (PR #156 review): an error logged after the boundary but before the reader attached stops the run,
#     also when the boundary is the previous phase's end, seconds before this one began; an error earlier
#     in the boundary's own second doesn't (fractions kept); a failure in the last sleep before the end still stops
#     it.
#   - Clean-up: a log stream that ignores TERM, and one whose child ignores TERM (orphaned when its parent goes),
#     are stopped within the bound; `device.sh reap` stops a live run, its dumper included.
#   - After every run, none of the sampler's processes is left (recorded pids, and anything started from the stub),
#     and no run may hang: each has a deadline.
# tests/gpu-diag/sampler-test.sh (tests/run.sh runs it)
set -uo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PKG=org.example.game
LAYER="1 SurfaceView[$PKG/$PKG.Main](BLAST)#9"
export GPU_DIAG_WORK=$T/work GPU_DIAG_KEEP_WORK=1
T0=$(date +%s)

# The device, as far as the sampler asks it: one app layer presenting at 120 Hz, an idle user, no errors.
# SLOW_POWER=S: `dumpsys power` takes S seconds. INPUT_AFTER=S: the activity token changes S seconds into a run.
dumpsys() {
  case "$1 ${2:-}" in
    "SurfaceFlinger --list")
      echo "RequestedLayerState{$LAYER parentId=8}"; echo "RequestedLayerState{other.app/other.app.Main#3 parentId=2}" ;;
    "SurfaceFlinger --latency")
      echo 8333333
      [ -n "${3:-}" ] || return 0
      local _now _k _a; _now=$(date +%s%N); _k=63
      while [ $_k -ge 0 ]; do
        _a=$((_now - _k * 8333333)); printf '%s\t%s\t%s\n' $((_a - 5000000)) "$_a" $((_a - 2000000)); _k=$((_k - 1))
      done ;;
    power*)
      [ -n "${SLOW_POWER:-}" ] && sleep "$SLOW_POWER"
      local ua=1000
      [ -n "${INPUT_AFTER:-}" ] && [ $(( $(date +%s) - RUN_START )) -ge "$INPUT_AFTER" ] && ua=2000
      echo "  lastUserActivityTime=$ua (999999 ms ago)" ;;
  esac
}
# PROC: the app's process name. Some apps run only a "PKG:name" process (glmark2's benchmark).
PROC=$PKG
# APP_GONE_AFTER=S: the app's process is gone S seconds into a run. Anything else (the sampler's process-tree check)
# goes to the real ps.
ps() {
  local proc=$PROC
  [ -n "${APP_GONE_AFTER:-}" ] && awk -v s="$RUN_START_F" -v d="$APP_GONE_AFTER" -v n="$(date +%s.%N)" 'BEGIN {exit !(n - s >= d)}' && proc=
  case "$*" in
    *UID,NAME*) echo "UID NAME"; [ -n "$proc" ] && echo "10200 $proc" ;;
    *PID,NAME*) echo "PID NAME"; [ -n "$proc" ] && echo "999999 $proc" ;;
    *-o\ NAME*|*"-o NAME") echo NAME; [ -n "$proc" ] && echo "$proc" ;;
    *) command ps "$@" ;;
  esac
}
# Streaming logcat (-T <epoch>, no -d), one stream per buffer: a script (the sampler execs it), GPU_DIAG_LOGCAT. Like
# logd it first prints its backlog from the -T time on, then new lines. The boundary is -T + 2 (WATCH_MARGIN).
# Every stream's backlog has an old error line long before the boundary (ignored). Per buffer (kernel|app|events):
#   BACKLOG_ERROR=B  an error logged 0.1 s after the boundary, before the reader attached, then another line
#   FRACTION_OLD=B   an error in the boundary's own second but before it (ignored)
#   NEW_ERROR=B      a new error NEW_ERROR_AFTER s (1) after the stream started
#   LOG_ENDS=B       the stream ends after 0.5 s
#   SLOW_LOG=S       nothing new for S seconds
#   RESIST_TERM=1    the stream ignores TERM (needs KILL); =child: a child of the stream does, the stream doesn't
cat > "$T/logcat" <<'STUB'
#!/usr/bin/env bash
[ "${RESIST_TERM:-}" = 1 ] && trap '' TERM
[ "${RESIST_TERM:-}" = child ] && bash -c 'trap "" TERM; while :; do sleep 1; done' "$0-resistant-child" &
buf=app; from=
case "$*" in *"-b kernel"*) buf=kernel ;; *"-b events"*) buf=events ;; esac
while [ $# -gt 0 ]; do [ "$1" = -T ] && from=$2; shift; done
case $buf in
  kernel) line='W NVRM    : Xid (PCI:0000:01:00): 13, pid=1, name=test, Graphics Exception' ;;
  app)    line='E Game    : vkQueueSubmit returned VK_ERROR_DEVICE_LOST (-4)' ;;
  events) line="I am_anr  : [0,6846,$PKG,952647236,Input dispatching timed out]" ;;
esac
at() { awk -v f="$from" -v d="$1" 'BEGIN {printf "%.6f", f + 2 + d}'; }
printf '--------- beginning of %s\n' "$buf"
printf '      1000.000     0     0 %s (old)\n' "$line"
if [ "${FRACTION_OLD:-}" = "$buf" ]; then
  b=$(at 0); s=${b%%.*}
  printf '      %s  6846  6873 %s (same second, before the boundary)\n' "$(awk -v s="$s" -v b="$b" 'BEGIN {printf "%.6f", s + (b - s) / 2}')" "$line"
fi
if [ "${BACKLOG_ERROR:-}" = "$buf" ]; then
  printf '      %s  6846  6873 %s (in-phase, before the reader attached)\n' "$(at 0.1)" "$line"
  printf '      %s  6846  6873 I Game    : something else\n' "$(at 0.2)"
fi
[ -n "${SLOW_LOG:-}" ] && sleep "$SLOW_LOG"
if [ "${LOG_ENDS:-}" = "$buf" ]; then sleep 0.5; exit 0; fi
if [ "${NEW_ERROR:-}" = "$buf" ]; then
  sleep "${NEW_ERROR_AFTER:-1}"; printf '      %s  6846  6873 %s (new)\n' "$(date +%s.%N)" "$line"
fi
while :; do sleep 1; done
STUB
chmod +x "$T/logcat"
export GPU_DIAG_LOGCAT=$T/logcat GPU_DIAG_OWN_RE='sampler-test|logcat' PKG

GPU_DIAG_DEVICE_LIB=1
# shellcheck source=../../scripts/gpu-diag/device.sh
. "$R/scripts/gpu-diag/device.sh"

fails=0
ok() { echo "ok   $1"; }
bad() { echo "FAIL $1: $2"; fails=$((fails + 1)); }

# up_cs itself, on a fixed /proc/uptime, under each IFS: always the integer centiseconds.
printf '48.05 224.38\n' > "$T/uptime"
for ifs in "$IFS" '
' ','; do
  got=$(IFS=$ifs; GPU_DIAG_UPTIME=$T/uptime up_cs)
  if [ "$got" = 4805 ]; then ok "up_cs under IFS $(printf %q "$ifs")"; else bad "up_cs under IFS $(printf %q "$ifs")" "$got"; fi
done
for b in 'x 1' '48.5 224.38' ''; do
  printf '%s\n' "$b" > "$T/uptime-bad"
  if got=$(GPU_DIAG_UPTIME=$T/uptime-bad up_cs); then bad "up_cs accepted '$b'" "$got"; else ok "up_cs refuses '$b' ($got)"; fi
done

# leftovers DIR: the pids still alive among those the sampler recorded, and any process started from the logcat
# stub (its command line has $T/; an orphan of a stopped stream is caught here)
leftovers() {
  local f p out=
  for f in "$1"/sampler.*/*.pid "$1"/sampler.*/dumper; do
    [ -e "$f" ] || continue; p=$(cat "$f"); kill -0 "$p" 2>/dev/null && out="$out $p"
  done
  out="$out $(pgrep -f "$T/" | tr '\n' ' ')"
  echo $out
}
# finish PID DEADLINE_S: wait for the sampler, at most DEADLINE_S; true when it ended. TOOK: seconds, 0.1 resolution.
finish() {
  local n=0
  while kill -0 "$1" 2>/dev/null && [ $n -lt $(( $2 * 10 )) ]; do sleep 0.1; n=$((n + 1)); done
  TOOK=$(awk -v s="$RUN_START_F" -v n="$(date +%s.%N)" 'BEGIN {printf "%.1f", n - s}')
  ! kill -0 "$1" 2>/dev/null
}

# run NAME SECONDS IFS_VALUE: one sample() in the background; prints its exit status into $T/NAME.rc
run() {
  local name=$1 secs=$2
  rm -rf "$GPU_DIAG_WORK"; mkdir -p "$GPU_DIAG_WORK"
  RUN_START=$(date +%s); RUN_START_F=$(date +%s.%N)
  # WATCH_BACK=S: the phase's log boundary is S s before it starts (as the measurement's, at the warm-up's end)
  local wf=; [ -n "${WATCH_BACK:-}" ] && wf=$(awk -v n="$RUN_START_F" -v b="$WATCH_BACK" 'BEGIN {printf "%.3f", n - b}')
  ( IFS=$3; sample "$PKG" "$secs" "${PERIOD:-0.1}" measure 1000 15 $wf ) > "$T/$name.txt" 2> "$T/$name.err" &
  local sp=$!
  [ -n "${KILL_MONITOR_AFTER:-}" ] && { sleep "$KILL_MONITOR_AFTER"; kill "$(cat "$GPU_DIAG_WORK"/sampler.*/monitor.pid)" 2>/dev/null; }
  if [ -n "${REAP_AFTER:-}" ]; then   # gpu-diag.sh's clean-up of a run it gave up on: device.sh reap, from outside
    sleep "$REAP_AFTER"; ( reap_all ) > "$T/$name.reap" 2>&1 &
    local rp=$!
    if ! finish $rp 10; then
      bad "$name" "reap still running at $TOOK s"; kill -9 $rp $sp; pkill -9 -f "$T/"; { wait $rp $sp; } 2>/dev/null; return 1
    fi
    { wait $rp; } 2>/dev/null; echo $? > "$T/$name.reap.rc"
  fi
  if ! finish $sp $(( secs + 15 )); then
    bad "$name" "still running after $TOOK s"; kill -9 $sp; pkill -9 -f "$T/"; { wait $sp; } 2>/dev/null; return 1
  fi
  { wait $sp; } 2>/dev/null; echo $? > "$T/$name.rc"
  local left; left=$(leftovers "$GPU_DIAG_WORK")
  [ -z "$left" ] || { bad "$name" "processes left: $left"; pkill -9 -f "$T/"; return 1; }
  # MAX_TOOK: the whole run (sampling, end coverage, clean-up) must take at most this long
  [ -z "${MAX_TOOK:-}" ] || awk -v t="$TOOK" -v m="$MAX_TOOK" 'BEGIN {exit !(t <= m)}' ||
    { bad "$name" "took $TOOK s (> $MAX_TOOK s)"; return 1; }
}

clean() {  # NAME SECONDS IFS_VALUE: a run that must finish with valid, gap-free output
  run "$@" || return
  local rc; rc=$(cat "$T/$1.rc")
  [ "$rc" = 0 ] || { bad "$1" "exit $rc: $(grep -m1 '^@abort\|^@cleanup' "$T/$1.txt")"; sed 's/^/    /' "$T/$1.err" | head -5; return; }
  if out=$(python3 - "$R" "$T/$1.txt" "$LAYER" "$2" "$TOOK" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("s", f"{sys.argv[1]}/scripts/gpu-diag-summary.py")
S = importlib.util.module_from_spec(spec); spec.loader.exec_module(S)
p = S.parse_samples(open(sys.argv[2]).read())
problems = []
if p["malformed"]:
    problems.append(f"malformed: {p['malformed'][:2]}")
if not p["end"] or p["abort"]:
    problems.append(f"end={bool(p['end'])} abort={p['abort']}")
timed = [s["timing"].get(sys.argv[3]) for s in p["samples"] if "timing" in s]
if len(timed) < 5 or any(t is None or t[1] < t[0] or t[2] != 0 for t in timed):
    problems.append(f"timings: {timed[:3]}")
if any(set(s["layers"]) != {sys.argv[3]} for s in p["samples"]):
    problems.append(f"layer names: {[list(s['layers']) for s in p['samples']][:2]}")
ep = [S.num((p[k] or {}).get("epoch")) for k in ("begin", "end")]
if None in ep or ep[1] < ep[0]:
    problems.append(f"epoch bounds: {ep}")
up = [s["up_cs"] for s in p["samples"]]
if up != sorted(up) or up[-1] - up[0] < 100:
    problems.append(f"sample times: {up[:3]}...{up[-1:]}")
spacing = max((b["timing"][sys.argv[3]][1] - a["timing"][sys.argv[3]][0]) * 10
              for a, b in zip(p["samples"], p["samples"][1:]))
gaps = S.pacing(p)["layers"].get(sys.argv[3], {}).get("coverage_gaps")
if gaps != 0:
    problems.append(f"gaps: {gaps} (widest dump span {spacing} ms, bound 500 ms at 120 Hz)")
if not p["loads"]:
    problems.append("no load samples from the monitor")
if None not in ep and ep[1] - ep[0] > float(sys.argv[4]) + 0.6:
    problems.append(f"epoch interval {ep[1] - ep[0]:.2f} s for a {sys.argv[4]} s phase (drain/cleanup counted)")
print("; ".join(problems) or f"{len(timed)} timed dumps, widest span {spacing} ms, {len(p['loads'])} load samples, run {sys.argv[5]} s")
sys.exit(1 if problems else 0)
PY
  ); then ok "$1 ($out)"; else bad "$1" "$out"; fi
}

stops() {  # NAME SECONDS EXPECTED_RC EXPECTED_ABORT_PREFIX MAX_SECONDS: a run that must stop for that reason in time
  local t0=$(date +%s) took
  run "$1" "$2" "$IFS" || return
  took=$(( $(date +%s) - t0 ))
  local rc ab; rc=$(cat "$T/$1.rc"); ab=$(grep -m1 '^@abort' "$T/$1.txt")
  case "$rc:$ab" in
    "$3:@abort $4"*) [ "$took" -le "$5" ] && ok "$1 ($ab; ${took}s)" || bad "$1" "took ${took}s (> $5 s): $ab" ;;
    *) bad "$1" "exit $rc, '${ab:-no @abort}'"; sed 's/^/    /' "$T/$1.err" | head -5 ;;
  esac
}

clean default-ifs 2 "$IFS"
PROC=$PKG:bench clean sub-process-only 2 "$IFS"
clean newline-ifs 2 '
'
clean comma-ifs 2 ','
SLOW_LOG=4 SLOW_POWER=2 clean slow-logs-and-power 4 "$IFS"
SLOW_LOG=4 SLOW_POWER=2 INPUT_AFTER=1 stops input-while-slow 8 3 user-activity 6
NEW_ERROR=kernel stops new-kernel-error 6 5 kernel-gpu-error 4
NEW_ERROR=app stops new-app-error 6 5 app-error 4
NEW_ERROR=events stops new-anr 6 5 app-error 4
LOG_ENDS=kernel stops kernel-stream-ends 6 5 "monitor-died: the kernel log stream ended" 3
KILL_MONITOR_AFTER=1 stops monitor-killed 12 5 monitor-stale 9
BACKLOG_ERROR=kernel stops error-before-attach 4 5 kernel-gpu-error 3
# Between the phases: logged 2.9 s before this phase started, after the previous one's end (its boundary).
BACKLOG_ERROR=app WATCH_BACK=3 stops error-between-phases 4 5 app-error 3
FRACTION_OLD=kernel clean same-second-before-boundary 2 "$IFS"
PERIOD=0.8 APP_GONE_AFTER=0.9 stops abort-in-last-sleep 1 5 app-gone 6
# The bound: 2 s sampling, the end coverage (DRAIN 1 s, a monitor round begun after the end), TERM 2 s, KILL.
RESIST_TERM=1 MAX_TOOK=8 clean term-resistant-stream 2 "$IFS"
RESIST_TERM=child MAX_TOOK=8 clean term-resistant-child 2 "$IFS"
# A run gpu-diag.sh gave up on: reap stops it (its dumper too) within the bound and says so.
reaped() {
  local name=reap-a-live-run
  RESIST_TERM=1 REAP_AFTER=1.5 MAX_TOOK=7 run "$name" 30 "$IFS" || return
  local rrc; rrc=$(cat "$T/$name.reap.rc")
  if [ "$rrc" = 0 ] && grep -q '^@reaped ' "$T/$name.reap" && ! grep -q '^@end' "$T/$name.txt" &&
     [ -z "$(ls "$GPU_DIAG_WORK")" ]; then
    ok "$name (reap exit 0, $(grep -c '^@reaped' "$T/$name.reap") dir; sampler exit $(cat "$T/$name.rc"); ${TOOK}s)"
  else
    bad "$name" "reap exit $rrc: $(tr '\n' ' ' < "$T/$name.reap"); sampler exit $(cat "$T/$name.rc"); left: $(ls "$GPU_DIAG_WORK")"
  fi
}
reaped
echo "$fails failure(s)"
[ $fails = 0 ]
