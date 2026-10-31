#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Background blur check, run on the device itself as root (ANAL-203, docs/googlebook-ui.md §2.3). mksh + toybox.
# Used by scripts/ui/blur-bench.sh (Cuttlefish, over adb) and by the graphics add-on's "blur" part on the G14
# (scripts/graphics/gfx-run.sh, unattended). scripts/ui/blur-report.py turns OUT_DIR into numbers and verdicts.
#
# Blur is switched at runtime through WM's setting Settings.Global.disable_window_blurs (what `wm disable-blur` sets),
# which BlurController passes on to SystemUI and Launcher3 without a restart. Per round (one STATE each):
#   shade  open and close the notification shade BLUR_CYCLES times (`cmd statusbar expand-notifications`)
#   qs     the same for Quick Settings (`cmd statusbar expand-settings`)
# For each it resets, then reads, SystemUI's HWUI frame stats (`dumpsys gfxinfo com.android.systemui`) and
# SurfaceFlinger's global TimeStats (frame duration, RenderEngine time, missed and janky frames). With the panel open
# in a state's first round it saves the SurfaceFlinger layers that carry a blur and, with BLUR_SHOTS=1, a screenshot.
# Around each round: amdgpu fault/reset lines in the kernel log, and the PIDs of SurfaceFlinger, SystemUI and
# system_server (a GPU reset restarts them).
#
# usage: blur-check.sh OUT_DIR [STATE...]     STATE: on | off (default: on off on off)
# Env: BLUR_CYCLES=20, BLUR_HOLD=1.2 (seconds open, and closed, per cycle), BLUR_SHOTS=1, BLUR_FIRST_ROUND=1 (number
#      of the first round's directory, OUT_DIR/r<N>-<state>/). The setting is left as it was found.
# Changes, put back at the end: disable_window_blurs; the shade is left closed.
PATH=/system/bin:/system_ext/bin:/vendor/bin:$PATH
OUT=${1:?usage: blur-check.sh OUT_DIR [on|off ...]}; shift
[ $# -gt 0 ] || set -- on off on off
N=${BLUR_CYCLES:-20}; H=${BLUR_HOLD:-1.2}; n=${BLUR_FIRST_ROUND:-1}
SUI=com.android.systemui
mkdir -p "$OUT"
up() { cut -d' ' -f1 /proc/uptime; }
gpu_events() { dmesg 2>/dev/null | grep -ciE 'amdgpu.*(ring .*timeout|gpu reset|page fault|fault in|hang)'; }
procs() { echo "surfaceflinger=$(pidof surfaceflinger) systemui=$(pidof $SUI) system_server=$(pidof system_server) system_server_starts=$(getprop sys.system_server.start_count)"; }
blurutils() { dumpsys activity service $SUI/.SystemUIService BlurUtils 2>/dev/null | grep -E 'BlurRadius|supportsBlursOnWindows|CROSS_WINDOW|isHighEndGfx'; }
# Layers SurfaceFlinger draws a blur behind, each with its name (the "Layer [id] name" line before the reason).
blurred() { dumpsys SurfaceFlinger 2>/dev/null | grep -B1 -E 'backgroundBlurRadius=|blurRegions' | grep -v '^--$'; }
ORIG=$(settings get global disable_window_blurs 2>/dev/null)

{
  echo "date: $(date -u +%FT%TZ)"; echo "uptime: $(up)"; echo "fingerprint: $(getprop ro.build.fingerprint)"
  for p in ro.product.model vendor.anybook.gpu.hal ro.hardware.egl ro.hardware.vulkan ro.surface_flinger.supports_background_blur \
      ro.config.low_ram ro.config.avoid_gfx_accel persist.sysui.disableBlur debug.renderengine.backend \
      debug.renderengine.vulkan debug.renderengine.graphite_desktop_optin debug.renderengine.blur_algorithm \
      ro.hwui.use_vulkan debug.hwui.renderer; do echo "$p=$(getprop $p)"; done
  echo "disable_window_blurs (as found): $ORIG"
  echo "power save: $(settings get global low_power 2>/dev/null); thermal: $(dumpsys thermalservice 2>/dev/null | grep -m1 'Thermal Status')"
  dumpsys SurfaceFlinger 2>/dev/null | grep -E '^GLES: |RenderEngine' | head -n 5
  dumpsys display 2>/dev/null | grep -m3 -oE 'renderFrameRate [0-9.]+|mActiveSfDisplayMode=[^,]*, [^,]*, [^,]*, [^,]*, [^,]*|refreshRate=[0-9.]+'
  echo "SystemUI BlurUtils:"; blurutils
  echo "amdgpu events: $(gpu_events)"; procs
} > "$OUT/device.txt" 2>&1

cycles() {  # $1 shade|qs, $2 round dir, $3 1: keep evidence of the open panel (mksh: no locals, so own names)
  cmd=expand-notifications; [ "$1" = qs ] && cmd=expand-settings
  cd_=$2/$1; mkdir -p "$cd_"
  cmd statusbar collapse; sleep 1
  dumpsys gfxinfo $SUI reset > /dev/null
  dumpsys SurfaceFlinger --timestats -disable -clear -enable > /dev/null
  t0=$(up); i=1
  while [ $i -le "$N" ]; do
    cmd statusbar $cmd; sleep "$H"
    if [ $i = 1 ] && [ "$3" = 1 ]; then
      blurred > "$cd_/sf-blur-layers.txt"
      [ "${BLUR_SHOTS:-1}" = 1 ] && screencap -p "$cd_/open.png"
    fi
    cmd statusbar collapse; sleep "$H"
    i=$((i + 1))
  done
  echo "cycles=$N hold_s=$H elapsed_s=$(echo "$(up) $t0" | awk '{printf "%.1f", $1 - $2}')" > "$cd_/meta.txt"
  echo "load: $(cat /proc/loadavg)" >> "$cd_/meta.txt"
  dumpsys SurfaceFlinger --timestats -dump > "$cd_/timestats.txt"
  dumpsys SurfaceFlinger --timestats -disable -clear > /dev/null
  dumpsys gfxinfo $SUI > "$cd_/gfxinfo.txt"
}

input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard > /dev/null 2>&1; sleep 1
seen=
for st in "$@"; do
  case $st in on) v=0 ;; off) v=1 ;; *) echo "blur-check: bad state $st" >&2; exit 2 ;; esac
  d=$OUT/r$n-$st; mkdir -p "$d"
  first=0; case " $seen " in *" $st "*) ;; *) first=1; seen="$seen $st" ;; esac
  settings put global disable_window_blurs $v
  # Measure only once SystemUI has the new state (up to 10 s), with the panels closed; a layer still blurred then is
  # recorded (closed-blur-layers.txt) and makes the round suspect in the report.
  want=true; [ $st = off ] && want=false; w=0
  while [ $w -lt 20 ] && [ "$(blurutils | sed -n 's/.*supportsBlursOnWindows: //p')" != $want ]; do sleep 0.5; w=$((w + 1)); done
  cmd statusbar collapse; sleep 2
  blurred > "$d/closed-blur-layers.txt"
  { echo "state=$st disable_window_blurs=$(settings get global disable_window_blurs) waited_s=$((w / 2))"; blurutils
    echo "closed_blur_lines=$(grep -c 'visible reason' "$d/closed-blur-layers.txt")"
    echo "before: $(procs) amdgpu_events=$(gpu_events) uptime=$(up)"; } > "$d/state.txt"
  echo "blur-check: round $n, blur $st"
  cycles shade "$d" $first
  cycles qs "$d" $first
  echo "after: $(procs) amdgpu_events=$(gpu_events) uptime=$(up)" >> "$d/state.txt"
  n=$((n + 1))
done
if [ -n "$ORIG" ] && [ "$ORIG" != null ]; then settings put global disable_window_blurs "$ORIG"
else settings delete global disable_window_blurs > /dev/null; fi
cmd statusbar collapse
echo "blur-check: done, disable_window_blurs back to [$(settings get global disable_window_blurs)]"
