#!/usr/bin/env bash
# Rough UI rendering benchmark for one booted device: open Settings (a freeform window on the desktop build),
# scroll its list with scripted swipes, and read HWUI's frame stats from `dumpsys gfxinfo`. Used to compare
# Cuttlefish GPU modes (docs/aosp-desktop.md). Indicative only: a shared host, and swipes are injected.
#
# usage: cf-gfx-bench.sh SERIAL OUTDIR LABEL      appends one line per round to OUTDIR/gfx-bench.csv
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb), BENCH_ROUNDS=2, BENCH_SWIPES=20
set -euo pipefail
S=$1; O=$2; LBL=$3; mkdir -p "$O"
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
a(){ "$ADB" -s "$S" "$@"; }
sh_(){ a shell "$@" | tr -d '\r'; }
PKG=com.android.settings
[ -f "$O/gfx-bench.csv" ] || echo "label,round,frames,janky,janky_pct,p50_ms,p90_ms,p95_ms,p99_ms,gpu_p50_ms,gpu_p90_ms,host_load1,renderer" > "$O/gfx-bench.csv"
REN=$(sh_ dumpsys SurfaceFlinger | sed -nE '/^GLES: /{s/^GLES: //; s/, OpenGL ES.*//; s/,/;/g; p; q}' || true)
sh_ input keyevent KEYCODE_WAKEUP; sh_ wm dismiss-keyguard; sh_ input keyevent KEYCODE_HOME; sleep 3
sh_ am start -W -n $PKG/.Settings >/dev/null; sleep 5
# Swipe inside the Settings list. Freeform bounds differ per build, so aim at the window's own bounds.
B=$(sh_ dumpsys activity activities | grep -m1 -A40 "A=1000:$PKG" | grep -m1 -oE 'mBounds=Rect\([0-9]+, [0-9]+ - [0-9]+, [0-9]+\)' || true)
read -r L T R Bo < <(echo "${B:-mBounds=Rect(0, 0 - 1920, 1080)}" | grep -oE '[0-9]+' | tr '\n' ' '; echo)
[ "$R" -gt 0 ] || { L=0; T=0; R=1920; Bo=1080; }
X=$(( L + (R - L) / 5 )); Y1=$(( T + (Bo - T) * 4 / 5 )); Y2=$(( T + (Bo - T) / 4 ))
for r in $(seq "${BENCH_ROUNDS:-2}"); do
  sh_ dumpsys gfxinfo $PKG reset >/dev/null
  for _ in $(seq "${BENCH_SWIPES:-20}"); do sh_ input swipe $X $Y1 $X $Y2 250; sh_ input swipe $X $Y2 $X $Y1 250; done
  sleep 1
  sh_ dumpsys gfxinfo $PKG > "$O/gfxinfo-$LBL-r$r.txt"
  g(){ grep -m1 "$1" "$O/gfxinfo-$LBL-r$r.txt" | sed -E "s/.*$1 *//" ; }
  fr=$(g 'Total frames rendered:'); jk=$(g 'Janky frames:' | awk '{print $1}'); jp=$(g 'Janky frames:' | grep -oE '[0-9.]+%' | tr -d %)
  p(){ grep -m1 "^$1 percentile:" "$O/gfxinfo-$LBL-r$r.txt" | grep -oE '[0-9]+ms' | tr -d ms; }
  gp(){ grep -m1 "^$1 gpu percentile:" "$O/gfxinfo-$LBL-r$r.txt" | grep -oE '[0-9]+ms' | tr -d ms; }
  echo "$LBL,$r,$fr,$jk,$jp,$(p 50th),$(p 90th),$(p 95th),$(p 99th),$(gp 50th),$(gp 90th),$(cut -d' ' -f1 /proc/loadavg),$REN" \
    | tee -a "$O/gfx-bench.csv"
done
