#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Per-app GPU diagnostics for an OpenBook laptop over adb (ANAL-336, docs/gpu-diagnostics.md): which GPU an app
# got and why, its present timestamps at SurfaceFlinger, start-up time, load, clocks, temperatures, the dGPU's
# power state, battery energy and kernel GPU errors, in the same files every run. gpu-diag-summary.py turns runs
# into tables. Holds the G14 lock (g14-lock.sh) for the whole command.
#
# usage: gpu-diag.sh [-a ADDR[:PORT]] COMMAND [ARGS]
#   idle [MINUTES]        exit 0 when a run may start: no input for MINUTES (default 10), display awake, keyguard
#                         not showing, no audio playing; else print why and exit 3
#   snapshot OUT [PKG...] the bundle's static part: conditions, GPU routing settings and properties, dGPU report,
#                         dumpsys gpu (per-app driver loads), the system Vulkan driver's vkjson. OUT must not exist
#   run OUT PKG [OPTIONS] one scored run of PKG. OUT must not exist. In order: the idle gate (and PKG not running:
#                         a user's session is never touched); conditions, routing and dGPU report before; this run's
#                         per-app GPU (--gpu); a process-cold start (am start -W -S); --warmup seconds sampled but not
#                         scored; SurfaceFlinger TimeStats cleared; --seconds scored; then outside the scored interval
#                         TimeStats, gfxinfo, SurfaceFlinger and GPU dumps, logcat and the kernel log since the start;
#                         PKG force-stopped; --settle seconds; dGPU report, conditions and crash records after.
#                         The gate's activity token is compared before the choice, at the launch (on the device,
#                         just before am start) and through warm-up and measurement: input at any point stops the
#                         run (exit 3: invalid) before anything more is changed. During warm-up and measurement it
#                         also stops (exit 3, the sampler's exit 5 recorded) on a kernel GPU error (Xid/NVRM, off the
#                         bus, GSP, amdgpu ring timeout or reset), on an error in the app's own processes
#                         (device-lost, context loss, crash, fatal signal) or an ANR/crash ActivityManager records for
#                         it, when its process goes away, and when no new frame appears for --stall seconds.
#       --gpu radeon|nvidia|keep  PKG's per-app GPU for this run (default keep). PKG's entries in all three lists are
#                         journalled first and put back afterwards, on failure and on a signal too, verified by a
#                         read-back, unless the owner changed them meanwhile. A restore that fails keeps the journal
#                         and makes the exit status 4; the next run refuses to start until it is restored
#       --component PKG/ACTIVITY  what to start (default PKG's launcher activity)
#       --extra ARG       one more am start argument, repeatable (benchmark intent extras)
#       --warmup S (20)   --seconds S (60, at most 1800: a 30-minute qualification)   --period S (0.25: a --latency dump holds 64 display
#                         frames, 0.53 s at 120 Hz)   --settle S (15)   --idle-min M (10)
#       --stall S (15)    no new frame for this long is a hang: the workload must render continuously
#       --battery         a battery run: refused on external power or below --floor PCT (50)
#       --label TEXT      the workload, scene and settings, recorded in run.json
#   restore               put back a per-app GPU choice that a run could not (its journal); exit 4 if it still can't
#   reap                  stop sampler processes a killed run left on the laptop (its pending-cleanup record).
#                         While that record exists, only reap and run (which reaps first) are allowed; others exit 75
#
# Env: as g14-adb.sh (OPENBOOK_G14_ADDR, ADB, ANDROID_ADB_SERVER_PORT); OPENBOOK_G14_OWNER names the task holding
#      the lock (default gpu-diag); OPENBOOK_G14_LOCK_WAIT waits for another session to end.
# Writes on the laptop: its own files in /data/local/tmp/openbook-gpu-diag (removed at the end), --gpu's per-app
# choice (restored), SurfaceFlinger TimeStats (enabled and cleared; statsd enables it anyway), gfxinfo reset for
# PKG, debug.openbook.dgpu_report. No root, reboot, install or data change. Exit 3: not idle / interrupted.
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/.." && pwd)
ADB=${ADB:-$A/android-sdk/platform-tools/adb}
export ANDROID_ADB_SERVER_PORT=${ANDROID_ADB_SERVER_PORT:-5222}
ADDR=${OPENBOOK_G14_ADDR:-}
D=/data/local/tmp/openbook-gpu-diag
PENDING=${OPENBOOK_G14_LOCK:-$A/locks/g14.lock}.pending-restore
PENDING_CLEANUP=${OPENBOOK_G14_LOCK:-$A/locks/g14.lock}.pending-cleanup
ARGS=("$@")
[ "${1:-}" = -a ] && { ADDR=$2; shift 2; }
CMD=${1:?usage: gpu-diag.sh [-a ADDR[:PORT]] idle|snapshot|run|restore ...}; shift
if [ -z "${OPENBOOK_G14_LOCK_OWNER:-}" ]; then
  exec "$R/scripts/g14-lock.sh" run "${OPENBOOK_G14_OWNER:-gpu-diag}" ${OPENBOOK_G14_LOCK_WAIT:+-w "$OPENBOOK_G14_LOCK_WAIT"} \
    -- "$R/scripts/gpu-diag.sh" "${ARGS[@]}"
fi
# Under the lock, before any adb or helper work: while an earlier run's clean-up is unconfirmed, only reap and run
# (which reaps first and stops if it can't) may touch the device. Anything else could delete the sampler's records
# that the reap needs; it is refused like a held lock, and the records stay.
case $CMD in
  reap|run) ;;
  *) if [ -s "$PENDING_CLEANUP" ]; then
       echo "gpu-diag: an earlier run's sampler clean-up is pending ($(cat "$PENDING_CLEANUP")); run 'gpu-diag.sh reap' first" >&2
       exit 75
     fi ;;
esac
[ -x "$ADB" ] || { echo "no adb at $ADB (set ADB=)" >&2; exit 2; }

connect() {
  local out
  out=$("$R/scripts/g14-adb.sh" ${ADDR:+-a "$ADDR"} connect) || { echo "$out" >&2; return 1; }
  SERIAL=$(sed -n 's/^connected: \([^ ]*\).*/\1/p' <<<"$out")
  [ -n "$SERIAL" ] || { echo "gpu-diag: no serial in: $out" >&2; return 1; }
}
a() { "$ADB" -s "$SERIAL" "$@"; }
sh_() { a shell "$@" | tr -d '\r'; }
dev() { sh_ "sh $D/device.sh $*"; }
push_helper() { a shell "mkdir -p $D" && a push -q "$R/scripts/gpu-diag/device.sh" "$D/device.sh" >/dev/null; }
newdir() { [ ! -e "$1" ] || { echo "gpu-diag: $1 exists; each run gets a new directory" >&2; exit 2; }; mkdir -p "$1"; }
sha() { sha256sum "$1" | cut -d' ' -f1; }
tool_rev() {
  echo "tool_commit=$(git -C "$R" rev-parse HEAD 2>/dev/null || echo na)" \
    "tool_dirty=$(git -C "$R" status --porcelain -- scripts/gpu-diag.sh scripts/gpu-diag 2>/dev/null | grep -c . || true)" \
    "gpu_diag_sh=$(sha "$R/scripts/gpu-diag.sh") device_sh=$(sha "$R/scripts/gpu-diag/device.sh")" \
    "choice_sh=$(sha "$R/scripts/gpu-diag/choice.sh")"
}

# idle_gate MINUTES: 0 when a run may start; prints the facts and the reason otherwise. Sets UA, the activity token
# every later step compares (device.sh check, launch, sample).
UA=
idle_gate() {
  local f ms
  f=$(dev idle); echo "$f"
  UA=$(sed -n 's/^user_activity_uptime_ms=\([0-9]*\) .*/\1/p' <<<"$f")
  [ -n "$UA" ] || { echo "not idle: no activity token"; return 3; }
  ms=$(sed -n 's/.*idle_ms=\([0-9]*\).*/\1/p' <<<"$f")
  [ -n "$ms" ] || { echo "not idle: user activity unreadable"; return 3; }
  [ "$ms" -ge $(( $1 * 60000 )) ] || { echo "not idle: input $(( ms / 1000 )) s ago (< $1 min)"; return 3; }
  grep -q '^wakefulness=Awake' <<<"$f" || { echo "not runnable: the display is not awake"; return 3; }
  grep -q '^keyguard_showing=false' <<<"$f" || { echo "not runnable: the lock screen is showing"; return 3; }
  grep -q '^audio_started=0' <<<"$f" || { echo "not idle: audio is playing"; return 3; }
}

dgpu_report() { dev dgpu-report "gpu-diag-$1" > "$2" || echo "  dgpu-report $1: unavailable (see $(basename "$2"))" >&2; }

# reap_device: device.sh reap (twice, reconnecting in between), true only when it confirms nothing is left (no
# sampler work dir at all also counts). PENDING_CLEANUP keeps a failure for the next run and for g14-lock.sh.
reap_device() {
  local r
  local q="if [ -f $D/device.sh ]; then sh $D/device.sh reap; echo @rc=\$?;"
  q+=" elif ls -d $D/sampler.* >/dev/null 2>&1; then echo 'sampler work dirs but no device.sh to reap with'; echo @rc=6;"
  q+=" else echo @rc=0; fi"
  r=$(sh_ "$q") && case $r in *@rc=0) echo "$r"; return 0 ;; esac
  connect >/dev/null 2>&1 || return 1
  r=$(sh_ "$q") && case $r in *@rc=0) echo "$r"; return 0 ;; esac
  echo "$r"; return 1
}

# The per-app GPU choice, its journal and its verified restore (PENDING).
# shellcheck source=gpu-diag/choice.sh
. "$R/scripts/gpu-diag/choice.sh"

cmd_snapshot() {
  local out=${1:?usage: snapshot OUT [PKG...]}; shift
  newdir "$out"; connect; push_helper
  { date -u +utc=%Y-%m-%dT%H:%M:%SZ; tool_rev; } > "$out/meta.txt"
  dev conditions > "$out/conditions.txt"
  dev routing "$@" > "$out/routing.txt"
  dgpu_report "snap-$(date -u +%H%M%S)" "$out/dgpu-report.txt"
  sh_ "dumpsys gpu" > "$out/dumpsys-gpu.txt" || true
  sh_ "cmd gpu vkjson" > "$out/vkjson-system.json" || true
  sh_ "dumpsys SurfaceFlinger" | grep -m 3 -E '^(GLES|Vulkan|RenderEngine)' > "$out/surfaceflinger-renderer.txt" || true
  a shell "rm -rf $D" || true
  echo "snapshot: $out"
}

# The run's state is global: finish runs from the EXIT trap, after cmd_run's locals are gone.
out= pkg= launched=0 child=
# bg CMD...: run CMD and wait for it, so that a signal's trap runs at once instead of after CMD.
bg() { "$@" & child=$!; local r=0; wait $child || r=$?; child=; return $r; }
finish() {
  local s=$?
  # Clean-up must not be cut short: a second signal is ignored (g14-lock.sh forwards only the first, then waits).
  trap - EXIT; trap '' INT TERM HUP
  [ -n "$child" ] && kill -TERM "$child" 2>/dev/null
  # The sampler's processes and the log streams they started must be gone before their records and the lock go:
  # device.sh reap stops them (bounded) and says so. If that can't be established, the device files stay and a
  # pending-cleanup record next to the lock makes the next run reap first (exit 4).
  if reap_device >> "$out/restore.txt" 2>&1; then rm -f "$PENDING_CLEANUP"; else
    echo "$D" > "$PENDING_CLEANUP"; echo "cleanup=failed" >> "$out/meta.txt"
    echo "gpu-diag: could not confirm the sampler's processes on the laptop stopped; run 'gpu-diag.sh reap'" >&2
    [ "$s" = 0 ] && s=4
  fi
  if [ "$launched" = 1 ]; then
    a shell "am force-stop $pkg" >/dev/null 2>&1 || { connect && a shell "am force-stop $pkg" >/dev/null; } || true
  fi
  if ! { restore_pending >> "$out/restore.txt" 2>&1 || { connect && restore_pending >> "$out/restore.txt" 2>&1; }; }; then
    echo "gpu-diag: the per-app GPU choice is NOT restored; the journal stays: run 'gpu-diag.sh restore' ($PENDING)" >&2
    echo "restore=failed" >> "$out/meta.txt"
    [ "$s" = 0 ] && s=4
  fi
  [ -s "$PENDING_CLEANUP" ] || a shell "rm -rf $D" >/dev/null 2>&1 || true
  echo "exit=$s" >> "$out/meta.txt"
  exit $s
}

cmd_run() {
  out=${1:?usage: run OUT PKG [OPTIONS]} pkg=${2:?usage: run OUT PKG [OPTIONS]}; shift 2
  local gpu=keep comp= warm=20 secs=60 period=0.25 settle=15 idlemin=10 battery=0 floor=50 label= extras=() stall=15
  while [ $# -gt 0 ]; do
    case $1 in
      --gpu) gpu=$2; shift 2 ;; --component) comp=$2; shift 2 ;; --extra) extras+=("$2"); shift 2 ;;
      --warmup) warm=$2; shift 2 ;; --seconds) secs=$2; shift 2 ;; --period) period=$2; shift 2 ;;
      --settle) settle=$2; shift 2 ;; --idle-min) idlemin=$2; shift 2 ;; --battery) battery=1; shift ;;
      --floor) floor=$2; shift 2 ;; --label) label=$2; shift 2 ;; --stall) stall=$2; shift 2 ;;
      *) echo "gpu-diag run: unknown option $1" >&2; exit 2 ;;
    esac
  done
  case $gpu in radeon|nvidia|keep) ;; *) echo "--gpu radeon|nvidia|keep" >&2; exit 2 ;; esac
  [[ $pkg =~ ^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$ ]] || { echo "bad package $pkg" >&2; exit 2; }
  for n in "$warm" "$secs" "$settle" "$idlemin" "$floor" "$stall"; do [[ $n =~ ^[0-9]+$ ]] || { echo "not a number: $n" >&2; exit 2; }; done
  [[ $period =~ ^[0-9]+(\.[0-9]+)?$ ]] || { echo "not a number: $period" >&2; exit 2; }
  [ "$secs" -ge 5 ] && [ "$secs" -le 1800 ] || { echo "--seconds: 5 to 1800" >&2; exit 2; }
  newdir "$out"; connect
  if [ -s "$PENDING_CLEANUP" ]; then
    reap_device > "$out/reap-pending.txt" 2>&1 && rm -f "$PENDING_CLEANUP" ||
      { cat "$out/reap-pending.txt" >&2; echo "gpu-diag: an earlier run's sampler may still run on the laptop; not starting" >&2; exit 4; }
  fi
  restore_pending > "$out/restore-pending.txt" 2>&1 ||
    { cat "$out/restore-pending.txt" >&2; echo "gpu-diag: an earlier run's GPU choice is not restored; not starting" >&2; exit 4; }
  push_helper

  local rc=0 t0 run_id
  run_id=$(basename "$out")
  trap finish EXIT; trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP

  { date -u +utc_start=%Y-%m-%dT%H:%M:%SZ; echo "run_id=$run_id pkg=$pkg gpu=$gpu warmup_s=$warm seconds=$secs" \
      "period_s=$period settle_s=$settle idle_min=$idlemin battery=$battery floor=$floor stall_s=$stall"; echo "label=$label"
    echo "component=${comp:-launcher} extras=${extras[*]:-}"; echo "owner=${OPENBOOK_G14_LOCK_OWNER}"; tool_rev; } > "$out/meta.txt"

  idle_gate "$idlemin" > "$out/idle-before.txt" || { cat "$out/idle-before.txt"; echo "skipped=not-idle" >> "$out/meta.txt"; exit 3; }
  echo "ua=$UA" >> "$out/meta.txt"
  # gate PHASE: the token unchanged and PKG not running, or stop here (before anything is changed or launched).
  gate() {
    dev check "$UA" "$pkg" >> "$out/checks.txt" && return 0
    echo "skipped=$1 $(tail -n 1 "$out/checks.txt")" >> "$out/meta.txt"
    echo "gpu-diag: stopped $1: $(tail -n 1 "$out/checks.txt")" >&2; exit 3
  }
  gate at-start

  dev conditions > "$out/conditions-before.txt"
  local ac
  ac=$(grep -cE '^battery (AC|USB) powered: true' "$out/conditions-before.txt" || true)
  if [ $battery = 1 ]; then
    [ "$ac" = 0 ] || { echo "skipped=on-external-power" >> "$out/meta.txt"; echo "battery run: on external power" >&2; exit 3; }
    local lvl; lvl=$(sed -n 's/^battery level: //p' "$out/conditions-before.txt")
    [ "${lvl:-0}" -ge "$floor" ] || { echo "skipped=below-floor level=$lvl" >> "$out/meta.txt"; echo "battery $lvl% < $floor%" >&2; exit 3; }
  else
    [ "$ac" != 0 ] || { echo "skipped=on-battery" >> "$out/meta.txt"; echo "AC run: the laptop is on battery" >&2; exit 3; }
  fi
  dev routing "$pkg" > "$out/routing-before.txt"
  sh_ "pm path $pkg" | sed -n 's/^package://p' | while read -r p; do echo "$p $(sh_ "sha256sum $p" | cut -d' ' -f1)"; done > "$out/apk.txt" || true
  dgpu_report "$run_id-before" "$out/dgpu-before.txt"
  sh_ "dumpsys dropbox" > "$out/dropbox-before.txt" || true

  gate before-choice
  if [ "$gpu" != keep ]; then
    choose "$pkg" "$gpu" > "$out/choice.txt" 2>&1 ||
      { cat "$out/choice.txt" >&2; echo "invalid=choice-failed" >> "$out/meta.txt"; exit 3; }   # finish undoes a part
  fi

  [ -n "$comp" ] || comp=$(sh_ "cmd package resolve-activity --brief -c android.intent.category.LAUNCHER $pkg" | tail -n 1)
  [[ $comp == */* ]] || { echo "no launcher activity for $pkg: $comp" >&2; exit 2; }
  t0=$(sh_ 'date +%s')
  local q=() e; for e in "${extras[@]}"; do q+=("$(printf %q "$e")"); done
  # The device checks the token and that PKG isn't running, then starts it at once.
  launched=1
  sh_ "sh $D/device.sh launch $pkg $comp $UA ${q[*]:-}" > "$out/am-start.txt" || true
  if grep -q '^@abort' "$out/am-start.txt"; then
    launched=0
    echo "skipped=at-launch $(grep -m 1 '^@abort' "$out/am-start.txt")" >> "$out/meta.txt"
    echo "gpu-diag: stopped at launch: $(grep -m 1 '^@abort' "$out/am-start.txt")" >&2; exit 3
  fi
  # Not scored: start-up, shader compiles, loading. Both phases compare the gate's token.
  bg timeout $(( warm + 60 )) "$ADB" -s "$SERIAL" shell "sh $D/device.sh sample $pkg $warm $period warmup $UA $stall > $D/warmup.txt" || rc=$?
  if [ $rc = 0 ]; then
    echo "ts_clear_up_s=$(sh_ "dumpsys SurfaceFlinger --timestats -enable -clear >/dev/null; cut -d' ' -f1 /proc/uptime")" >> "$out/meta.txt"
    sh_ "dumpsys gfxinfo $pkg reset" >/dev/null
    # The measurement's log watchers cover from the warm-up's end, so the gap between the phases is covered too.
    local wf; wf=$(sh_ "sed -n 's/^@end .* epoch=\([0-9.]*\) .*/\1/p' $D/warmup.txt" | head -n 1)
    bg timeout $(( secs + 60 )) "$ADB" -s "$SERIAL" shell "sh $D/device.sh sample $pkg $secs $period measure $UA $stall $wf > $D/measure.txt" || rc=$?
  fi
  a pull -q "$D/warmup.txt" "$out/warmup.txt" >/dev/null 2>&1 || true
  a pull -q "$D/measure.txt" "$out/measure.txt" >/dev/null 2>&1 || true
  if [ $rc != 0 ]; then
    a shell "am force-stop $pkg" >/dev/null 2>&1 || true
    grep -hE '^@(abort|cleanup-failed)' "$out/warmup.txt" "$out/measure.txt" 2>/dev/null | tee -a "$out/meta.txt" >&2 || true
    echo "invalid=sampler-exit-$rc" >> "$out/meta.txt"
    echo "run stopped (sampler exit $rc); not scored" >&2
    exit 3
  fi
  # Outside the scored interval.
  sh_ "cut -d' ' -f1 /proc/uptime; dumpsys SurfaceFlinger --timestats -dump" > "$out/timestats.txt" || true
  echo "ts_dump_up_s=$(head -n 1 "$out/timestats.txt")" >> "$out/meta.txt"
  sh_ "dumpsys gfxinfo $pkg framestats" > "$out/gfxinfo.txt" || true
  sh_ "dumpsys SurfaceFlinger" > "$out/surfaceflinger.txt" || true
  sh_ "dumpsys window windows" | grep -A 12 -F "$pkg" > "$out/window.txt" || true
  sh_ "dumpsys gpu" > "$out/dumpsys-gpu.txt" || true
  sh_ "ps -A -o PID,UID,NAME" | awk -v p="$pkg" 'index($3, p) == 1' > "$out/processes.txt" || true
  sh_ "logcat -d -v threadtime,uid -T $t0.000 -b main,system,crash,events" > "$out/logcat.txt" || true
  # The app's own lines with epoch timestamps, for its self-reported frame rate over the scored interval.
  local auid; auid=$(sed -n 's/^@begin .* uid=\([0-9]*\) .*/\1/p' "$out/measure.txt" | head -n 1)
  [ -n "$auid" ] && { sh_ "logcat -d -v epoch -T $t0.000 -b main --uid=$auid" > "$out/app-logcat.txt" || true; }
  sh_ "logcat -d -v threadtime -T $t0.000 -b kernel" > "$out/kernel.txt" 2>&1 || true
  a shell "am force-stop $pkg" >/dev/null; launched=0
  bg sleep "$settle"
  dgpu_report "$run_id-after" "$out/dgpu-after.txt"
  dev conditions > "$out/conditions-after.txt"
  sh_ "dumpsys dropbox" > "$out/dropbox-after.txt" || true
  date -u +utc_end=%Y-%m-%dT%H:%M:%SZ >> "$out/meta.txt"
  echo "run: $out"
}

case $CMD in
  idle) connect; push_helper; rc=0; idle_gate "${1:-10}" || rc=$?; a shell "rm -rf $D" || true; exit $rc ;;
  snapshot) cmd_snapshot "$@" ;;
  run) cmd_run "$@" ;;
  restore) connect; restore_pending || exit 4 ;;
  reap) connect; sh_ "[ -f $D/device.sh ] && echo present" | grep -q present || push_helper   # never over a running copy
        reap_device && rm -f "$PENDING_CLEANUP" || exit 4 ;;
  *) echo "usage: gpu-diag.sh [-a ADDR[:PORT]] idle|snapshot|run|restore ..." >&2; exit 2 ;;
esac
