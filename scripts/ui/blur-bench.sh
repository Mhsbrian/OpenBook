#!/usr/bin/env bash
# Cost of background blur on one booted userdebug device over adb (ANAL-203, docs/googlebook-ui.md §2.3): Cuttlefish,
# or any device adb reaches. Per STATE, one round of scripts/ui/blur-check.sh on the device (shade and Quick Settings
# opened and closed BLUR_CYCLES times, SystemUI's frame stats, SurfaceFlinger's TimeStats, the blurred layers and a
# screenshot), then a control with the shade closed: Settings scrolled by scripts/cf-gfx-bench.sh (one round), where no
# blur is drawn. Rounds run in the order given, so on and off alternate on a shared host.
#
# usage: blur-bench.sh SERIAL OUTDIR STATE...      STATE: on | off; e.g. on off on off on off
#   OUTDIR/r<N>-<state>/ per round; then scripts/ui/blur-report.py OUTDIR
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb; set ANDROID_ADB_SERVER_PORT for a private server);
#      BLUR_CYCLES, BLUR_HOLD, BLUR_SHOTS (blur-check.sh); BENCH_SWIPES (cf-gfx-bench.sh)
set -euo pipefail
S=$1; O=$2; shift 2
[ $# -gt 0 ] || { sed -n '2,12p' "$0"; exit 2; }
R=$(cd "$(dirname "$0")/../.." && pwd)
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}; export ADB
a(){ "$ADB" -s "$S" "$@"; }
mkdir -p "$O"
a root >/dev/null; a wait-for-device
T=/data/local/tmp/openbook-blur
a shell "rm -rf $T && mkdir -p $T"
a push "$R/scripts/ui/blur-check.sh" $T/blur-check.sh >/dev/null
env=$(for v in BLUR_CYCLES BLUR_HOLD; do [ -n "${!v:-}" ] && printf '%s=%s ' "$v" "${!v}"; done; true)
# Settings' first start after boot is slow (round 1 of the first Cuttlefish run had no frames): start it once first.
a shell am start -W -n com.android.settings/.Settings >/dev/null; sleep 5; a shell am force-stop com.android.settings
n=0; seen=
for st in "$@"; do
  n=$((n + 1))
  echo "=== $(date -u +%FT%TZ) round $n: blur $st, host load $(cut -d' ' -f1 /proc/loadavg)" | tee -a "$O/bench.log"
  # Screenshots in each state's first round only, as one blur-check.sh run over all rounds takes them.
  shots=0; case " $seen " in *" $st "*) ;; *) shots=${BLUR_SHOTS:-1}; seen="$seen $st" ;; esac
  a shell "${env}BLUR_SHOTS=$shots BLUR_FIRST_ROUND=$n sh $T/blur-check.sh $T/out $st" 2>&1 | tr -d '\r' | tee -a "$O/bench.log"
  a shell "settings put global disable_window_blurs $([ "$st" = off ] && echo 1 || echo 0)"
  a shell input keyevent KEYCODE_HOME; sleep 2
  BENCH_ROUNDS=1 "$R/scripts/cf-gfx-bench.sh" "$S" "$O/r$n-$st/settings" "blur-$st" >> "$O/bench.log" 2>&1 ||
    echo "settings scroll failed" | tee -a "$O/bench.log"
  a shell am force-stop com.android.settings
  echo "round $n end: host load $(cut -d' ' -f1 /proc/loadavg)" >> "$O/bench.log"
done
a shell "settings put global disable_window_blurs 0"
rm -rf "$O/.pull"; a pull "$T/out" "$O/.pull" >/dev/null   # a new destination: adb puts the directory's contents there
cp -a "$O/.pull/." "$O/"; rm -rf "$O/.pull"
a shell "rm -rf $T"
echo "=== $(date -u +%FT%TZ) done; blur on" | tee -a "$O/bench.log"
