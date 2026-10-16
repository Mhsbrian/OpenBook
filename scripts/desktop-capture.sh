#!/usr/bin/env bash
# Desktop-windowing evidence from a booted Android device: open two apps the way a user would (no forced
# windowing mode), screenshot, and dump what WM, WM Shell, SurfaceFlinger and Launcher report. Works the same on
# our Cuttlefish build and on Google's AOSP Desktop emulator image, so the two can be diffed
# (scripts/desktop-compare.py).
#
# usage: desktop-capture.sh SERIAL OUTDIR
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb). Set ANDROID_ADB_SERVER_PORT to keep a private adb
#      server; other runs on this host share the default one.
#      DESKTOP_APPS: activities to open, in order (default: Settings, then Files).
set -euo pipefail
S=$1; O=$2; mkdir -p "$O"
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
a(){ "$ADB" -s "$S" "$@"; }
sh_(){ a shell "$@" | tr -d '\r'; }
log(){ echo "=== $(date -u +%FT%TZ) $*" | tee -a "$O/capture.log"; }
APPS=${DESKTOP_APPS:-com.android.settings/.Settings com.android.documentsui/.files.FilesActivity}

log "wait for $S"
timeout 300 "$ADB" -s "$S" wait-for-device
for _ in $(seq 120); do [ "$(sh_ getprop sys.boot_completed)" = 1 ] && break; sleep 2; done
a root >/dev/null 2>&1 || true; sleep 2; timeout 60 "$ADB" -s "$S" wait-for-device
# Let the launcher, taskbar and WM Shell settle after boot_completed.
sleep "${DESKTOP_SETTLE:-20}"
sh_ input keyevent KEYCODE_WAKEUP; sh_ wm dismiss-keyguard; sleep 3
sh_ getprop ro.build.fingerprint | tee -a "$O/capture.log"
a exec-out screencap -p > "$O/screen-desktop.png"

for act in $APPS; do
  log "am start -n $act"
  sh_ am start -W -n "$act" | tee -a "$O/capture.log"
  sleep 5
done
a exec-out screencap -p > "$O/screen-windows.png"
log "dumps"
sh_ dumpsys activity activities > "$O/activities.txt"
sh_ dumpsys window displays > "$O/window-displays.txt"
sh_ dumpsys SurfaceFlinger > "$O/surfaceflinger.txt"
sh_ dumpsys activity service SystemUIService WMShell > "$O/wmshell.txt" 2>&1 || true
sh_ dumpsys activity service com.android.launcher3/com.android.quickstep.TouchInteractionService > "$O/launcher.txt" 2>&1 || true
sh_ getprop > "$O/getprop.txt"
sh_ pm list features | sort > "$O/features.txt"
sh_ cmd overlay list > "$O/overlays.txt"
sh_ aflags list > "$O/aflags.txt" 2>&1 || true
sh_ settings list global | sort > "$O/settings-global.txt"
sh_ wm size > "$O/wm.txt"; sh_ wm density >> "$O/wm.txt"
sh_ dumpsys input | grep -E 'Device [0-9]+:|Sources:|KeyboardType:|Classes:' > "$O/input-devices.txt" || true

# Summaries that are small enough to commit next to the screenshots.
sf_layers(){ awk '/HWC layers \(top to bottom\)/{f=1;next} f&&/^ [A-Za-z]/{n=$0} f&&/\|/&&/CLIENT|DEVICE|SOLID_COLOR|CURSOR|DISPLAY_DECORATION|SIDEBAND|REFRESH_RATE/{split($0,a,"|"); gsub(/ /,"",a[3]); print a[3] "\t" n} f&&/^$/{exit}' "$1"; }
{
  echo "# $(sh_ getprop ro.build.fingerprint)"
  echo "## Tasks (dumpsys activity activities)"
  grep -E '^\s+\* Task\{|mWindowingMode=' "$O/activities.txt" | grep -E 'Task\{|Hist|ActivityRecord' | head -40 || true
  echo "## windowing modes of activities (count)"
  grep -oE 'mWindowingMode=[a-z-]+' "$O/activities.txt" | sort | uniq -c
  echo "## display windowing mode (dumpsys window displays)"
  grep -m3 -E 'mWindowingMode=|windowingMode' "$O/window-displays.txt" || true
} > "$O/windowing-summary.txt"
{
  echo "# dumpsys SurfaceFlinger summary"
  grep -E '^Display [0-9]+ \(HWC display|^GLES:|^Build configuration|RenderEngine chosen blur|usesDeviceComposition=|usesClientComposition=' "$O/surfaceflinger.txt" || true
  echo "## HWC layers (top to bottom): composition type, layer"
  sf_layers "$O/surfaceflinger.txt"
} > "$O/surfaceflinger-summary.txt"
log "freeform activity records: $(grep -c 'mWindowingMode=freeform' "$O/activities.txt" || true)"
