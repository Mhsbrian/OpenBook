#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Does each frame reach the G14's panel on time? (ANAL-212; docs/graphics-amd.md, "Refresh rate".) Run against the
# installed G14 over adb while something animates on its screen (a scrolling page, testufo.com). Read-only apart from
# kernel tracing, which it turns off again:
#   1. SurfaceFlinger TimeStats for SECONDS: frames, missed frames, present-to-present intervals, RenderEngine time;
#   2. kprobes for 1.5 s: the update type DC gives each commit (dc_check_update_surfaces_for_stream: fast, med or
#      full), how often amdgpu removes and re-adds a plane (a plane reset forces a full update), and how often the
#      CRTC's CTM gets a new blob (72-byte drm_property blobs).
# Healthy at 120 Hz: present-to-present mostly 8 ms, no full updates or plane resets while things move, no new CTM
# blob per frame. The bug fixed by aosp/patches/external/drm_hwcomposer/0001: a new CTM blob and a plane reset with
# every commit, so every flip was a full update that landed a vblank late; present-to-present 16 ms.
#
# usage: g14-flip-check.sh [--scroll] [ADDR[:PORT]] [SECONDS]      default 192.168.50.11:5555 (OPENBOOK_G14_ADDR), 8 s
#   --scroll  make the animation itself: open Settings, scroll its list with `input swipe` for the whole measurement,
#             then go back home (changes what is on the laptop's screen for about SECONDS + 5 s)
# env:   ADB (default <data dir>/android-sdk/platform-tools/adb), ANDROID_ADB_SERVER_PORT (default 5233: a private server)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
ADB=${ADB:-$A/android-sdk/platform-tools/adb}
export ANDROID_ADB_SERVER_PORT=${ANDROID_ADB_SERVER_PORT:-5233}
SCROLL=0; [ "${1:-}" = --scroll ] && { SCROLL=1; shift; }
D=${1:-${OPENBOOK_G14_ADDR:-192.168.50.11}}; [[ $D == *:* ]] || D=$D:5555
S=${2:-8}
case $S in ''|*[!0-9]*) echo "SECONDS must be a number" >&2; exit 2 ;; esac
timeout 20 "$ADB" connect "$D" >/dev/null
sh_() { timeout 120 "$ADB" -s "$D" shell "$@"; }

if [ $SCROLL = 1 ]; then
  # Scroll Settings' list (left pane at 1920x1200 dp) up and down until the measurement ends; stopped below.
  sh_ "am start -W -a android.settings.SETTINGS >/dev/null 2>&1; sleep 2"
  sh_ "nohup sh -c ': openbook-scroll; for i in \$(seq 1 $((S + 6))); do input swipe 340 1050 340 250 500; input swipe 340 250 340 1050 500; done' >/dev/null 2>&1 &"
  trap 'sh_ "pkill -f openbook-scrol[l]; pkill -f \"input swipe 34[0]\"; input keyevent HOME" >/dev/null 2>&1 || true' EXIT
  sleep 1
fi
echo "== $(sh_ getprop ro.build.fingerprint) at $(date -u +%FT%TZ)"
echo "== focus: $(sh_ dumpsys window | sed -n 's/.*mCurrentFocus=//p' | head -n 1)"
sh_ dumpsys SurfaceFlinger --scheduler | grep -E 'renderRate=|activeMode=|displayManagerPolicy=' | sed 's/^ *//'

echo "== TimeStats, $S s"
sh_ "dumpsys SurfaceFlinger --timestats -clear -enable >/dev/null; sleep $S; dumpsys SurfaceFlinger --timestats -dump;
     dumpsys SurfaceFlinger --timestats -disable >/dev/null; dumpsys SurfaceFlinger --timestats -clear >/dev/null" |
  awk '/^Global aggregated/ { exit } /^(totalFrames|missedFrames|clientCompositionFrames|averageRenderEngineTiming)/ { print }
       /histogram is as below/ { h = $1 } /^[0-9]+ms=/ && (h == "presentToPresent" || h == "renderEngineTiming") {
         s = ""; for (i = 1; i <= NF; i++) { split($i, kv, "="); if (kv[2] > 0) s = s " " $i } print h ":" s; h = "" }'

echo "== amdgpu flips and CTM blobs, 1.5 s"
sh_ su 0 sh <<'EOF'
T=/sys/kernel/tracing; I=$T/instances/openbook-flip
cleanup() {
  [ -d $I ] && { echo 0 > $I/events/openbook_flip/enable; rmdir $I; }
  for p in $(grep -oE 'openbook_flip/[A-Za-z0-9_]+' $T/kprobe_events); do echo "-:$p" >> $T/kprobe_events; done
}
cleanup 2>/dev/null
echo 'r:openbook_flip/type dc_check_update_surfaces_for_stream type=$retval:s32' >> $T/kprobe_events
echo 'p:openbook_flip/plane_add dc_state_add_plane' >> $T/kprobe_events
echo 'p:openbook_flip/blob drm_property_replace_blob_from_id blob_id=%dx:u64 size=%cx:s64' >> $T/kprobe_events
mkdir -p $I && echo 2048 > $I/buffer_size_kb && echo 1 > $I/events/openbook_flip/enable
echo 1 > $I/tracing_on; sleep 1.5; echo 0 > $I/tracing_on
t=$(cat $I/trace)
cleanup
echo "DC update types: fast $(echo "$t" | grep -c 'type=0$'), med $(echo "$t" | grep -c 'type=1$'), full $(echo "$t" | grep -c 'type=2$')"
echo "planes (re-)added to the DC state: $(echo "$t" | grep -c ' plane_add:')"
echo "new CTM blobs: $(echo "$t" | grep -c 'size=72$') (ids: $(echo "$t" | sed -n 's/.*blob_id=\([0-9]*\) size=72$/\1/p' | sort -un | head -n 8 | tr '\n' ' '))"
echo "kprobes left: $(grep -c openbook_flip $T/kprobe_events)"
EOF
