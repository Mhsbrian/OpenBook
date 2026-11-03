#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# gpu-diag.sh's on-device half (ANAL-336): pushed to /data/local/tmp and run by adb's shell user (mksh, toybox).
# Read-only: no setting, property or sysfs write, except dgpu-report, which asks the vendor helper for its report
# (setprop debug.openbook.dgpu_report), and launch's am start. It never reads PCI config space, an NVIDIA device
# file or an NVIDIA-backed hwmon sensor, so a dGPU in D3cold stays there: of the NVIDIA functions it reads only
# sysfs power/runtime_status (and the cached vendor ID every PCI device has).
# A file the shell user can't read is reported "na", never as zero.
#
# UA is the activity token: the default display group's lastUserActivityTime when the idle gate passed. Every step
# after the gate compares it, so input at any point of a run (setup, launch, warm-up, measurement) stops it.
#
# usage: device.sh idle            user activity (the token), display, keyguard, audio playback
#        device.sh check UA PKG    exit 3 unless the token is still UA and no PKG process runs
#        device.sh launch PKG COMPONENT UA [AM_ARGS...]
#            check, then at once am start -W -S (a process-cold start)
#        device.sh conditions      power source, battery, brightness, refresh, power profile, display, thermals
#        device.sh routing PKG...  Android's updatable-driver and ANGLE settings, graphics properties, packages
#        device.sh dgpu-report TAG the vendor helper's dGPU report (power state, driver, NVRM/Xid counts)
#        device.sh layers PKG      SurfaceFlinger layers of PKG that have presented frames
#        device.sh reap            stop what any sampler left behind, its dumper included (bounded: TERM, then freeze
#                                  and KILL), exit 6 if anything stays
#        device.sh sample PKG SECONDS PERIOD PHASE UA [STALL] [WATCH_FROM]
#            Three kinds of process, so slow work never delays the frame dumps and input is still seen while logs
#            are slow (ANAL-336, attempt 2):
#            - the dumper (this shell): per-layer present timestamps (dumpsys SurfaceFlinger --latency) every
#              PERIOD seconds, each dump with its own start/end time and exit status (@Le);
#            - the monitor, once a second: the activity token (exit 3 when it changed), PKG still running, no new
#              frame for STALL seconds (15), the watchers alive; load samples; the layer list; a heartbeat;
#            - three log watchers, streaming from WATCH_FROM (default the phase's start; logd's backlog first, so
#              lines logged before a reader attached count, then each new line once; fractions of a second kept):
#              the kernel log (an NVIDIA Xid or NVRM error, a GPU off the bus, a GSP error, an amdgpu ring timeout or reset), the app's own processes (a
#              device-lost, context loss, crash or fatal signal) and ActivityManager's ANR/crash events for PKG.
#            Any failure, a watcher's log stream ending, or a monitor heartbeat older than 5 s stops the run (exit 5):
#            stale or lost monitoring is never "no errors". At the end the boundary is taken first, then a whole monitor
#            round begun after it and a drain of the streams are awaited, so a failure in the last moments still
#            counts. All of them, and what they started, are stopped and verified gone within a bounded time (about
#            3 s) before it returns; a failure a watcher found until then counts too (exit 6 if one won't go).
#            On Android 17 a --latency dump holds the last 64 display frames, about 0.53 s at 120 Hz, so PERIOD must
#            stay well under that: gpu-diag-summary.py marks a gap wherever two dumps may be farther apart.
set -u
# The default IFS, whatever the caller had: word splitting below ($(user_activity), $(nvidia_fns)...) relies on it.
DEFAULT_IFS=' 	
'
IFS=$DEFAULT_IFS
# up_cs: CLOCK_BOOTTIME in centiseconds, an integer. Its own IFS, so a caller's IFS can't merge /proc/uptime's two
# fields; anything but "SECONDS.CC" prints "na" (the summary rejects it). GPU_DIAG_UPTIME replaces /proc/uptime.
up_cs() {
  IFS=' ' read -r u _ < "${GPU_DIAG_UPTIME:-/proc/uptime}"
  case $u in ?*.[0-9][0-9]) ;; *) echo na; return 1 ;; esac
  case ${u%.*} in *[!0-9]*) echo na; return 1 ;; esac
  echo "${u%.*}${u#*.}"
}
na() { echo "na $1"; }
rd() { if [ -r "$1" ] && v=$(cat "$1" 2>/dev/null); then echo "$v"; else return 1; fi; }
kv() { if v=$(rd "$2"); then echo "$1=$v"; else echo "$1=na"; fi; }

# The default display group's lastUserActivityTime: "N (M ms ago)", uptime ms (PowerGroup.toString).
user_activity() {
  dumpsys power 2>/dev/null | sed -n 's/^ *lastUserActivityTime=\([0-9]*\) (\([0-9]*\) ms ago).*/\1 \2/p' | head -n 1
}

ua_now() { set -- $(user_activity); echo "${1:-}"; }
app_running() { ps -A -o NAME 2>/dev/null | awk -v p="$1" '$1 == p || index($1, p ":") == 1 {f = 1} END {exit !f}'; }
check() {  # UA PKG
  cur=$(ua_now)
  [ -n "$cur" ] && [ "$cur" = "$1" ] || { echo "@abort user-activity ua=${cur:-na} (gate ua=$1)"; return 3; }
  if app_running "$2"; then echo "@abort app-running $2"; return 3; fi
  echo "@ok ua=$cur"
}
launch() {  # PKG COMPONENT UA [AM_ARGS...]
  pkg=$1; comp=$2; ua=$3; shift 3
  check "$ua" "$pkg" || exit 3
  am start -W -S -n "$comp" "$@"
}

idle() {
  set -- $(user_activity)
  echo "user_activity_uptime_ms=${1:-na} idle_ms=${2:-na}"
  echo "wakefulness=$(dumpsys power 2>/dev/null | sed -n 's/^ *mWakefulness=\([A-Za-z]*\).*/\1/p' | head -n 1)"
  echo "keyguard_showing=$(dumpsys activity activities 2>/dev/null | sed -n 's/^ *mKeyguardShowing=\([a-z]*\).*/\1/p' | head -n 1)"
  # Started audio players other than the system's own (uid 1000): music, video, calls.
  echo "audio_started=$(dumpsys audio 2>/dev/null | grep 'AudioPlaybackConfiguration piid:' | grep ' state:started' |
    grep -vc ' u/pid:1000/')"
  echo "top=$(dumpsys activity activities 2>/dev/null | sed -n 's/^ *topResumedActivity=ActivityRecord{[^ ]* [^ ]* \([^ ]*\).*/\1/p' | head -n 1)"
}

hwmon() {  # name=temp_C for every hwmon temp1 the shell user can read, except NVIDIA-backed sensors
  for h in /sys/class/hwmon/hwmon*; do
    d=$(readlink -f "$h/device" 2>/dev/null)
    if [ -n "$d" ] && [ "$(rd "$d/vendor")" = 0x10de ]; then echo "hwmon ${h##*/} skipped=nvidia-device"; continue; fi
    n=$(rd "$h/name") || continue
    case $n in nvidia*|nouveau*) echo "hwmon ${h##*/} skipped=$n"; continue ;; esac
    if t=$(rd "$h/temp1_input"); then echo "hwmon $n temp1_mC=$t"; else echo "hwmon $n temp1_mC=na"; fi
  done
}

amdgpu_dev() {
  for c in /sys/class/drm/card[0-9]; do
    [ "$(rd "$c/device/vendor")" = 0x1002 ] && { echo "$c/device"; return; }
  done
}
nvidia_fns() {
  for p in /sys/bus/pci/devices/*; do [ "$(rd "$p/vendor")" = 0x10de ] && echo "$p"; done
}

battery() {
  for b in /sys/class/power_supply/BAT*; do
    [ -d "$b" ] || continue
    echo "bat ${b##*/} $(kv status "$b/status") $(kv capacity "$b/capacity") $(kv power_uW "$b/power_now")" \
      "$(kv current_uA "$b/current_now") $(kv voltage_uV "$b/voltage_now") $(kv energy_uWh "$b/energy_now")" \
      "$(kv charge_uAh "$b/charge_now")"
  done
  for s in /sys/class/power_supply/*; do
    [ "$(rd "$s/type")" = Mains ] && echo "mains ${s##*/} $(kv online "$s/online")"
  done
}

conditions() {
  dumpsys battery 2>/dev/null | grep -E '^  (AC powered|USB powered|Charge counter|status|level|voltage|temperature):' |
    sed 's/^  /battery /'
  battery
  echo "brightness=$(settings get system screen_brightness) mode=$(settings get system screen_brightness_mode)" \
    "float=$(settings get system screen_brightness_float)"
  echo "screen_off_timeout_ms=$(settings get system screen_off_timeout)" \
    "stay_on_while_plugged_in=$(settings get global stay_on_while_plugged_in)"
  echo "low_power=$(settings get global low_power)"
  for c in /sys/devices/system/cpu/cpu0/cpufreq; do
    echo "cpu0 $(kv governor "$c/scaling_governor") $(kv epp "$c/energy_performance_preference") $(kv driver "$c/scaling_driver")"
  done
  echo "platform_profile=$(rd /sys/firmware/acpi/platform_profile || echo na)"
  dumpsys display 2>/dev/null | grep -m 4 -E 'mActiveSfDisplayMode|mActiveRenderFrameRate|renderFrameRate=|mRefreshRateInHighZone' |
    sed 's/^ */display /'
  echo "wm $(wm size | tr '\n' ' ') $(wm density | tr '\n' ' ')"
  hwmon
  dumpsys thermalservice 2>/dev/null | sed -n '/^Current temperatures from HAL:/,/^Current cooling devices/p' |
    grep 'Temperature{' | sed 's/^ */thermal /'
}

routing() {
  for k in updatable_driver_all_apps updatable_driver_production_opt_in_apps updatable_driver_prerelease_opt_in_apps \
           updatable_driver_production_opt_out_apps updatable_driver_production_denylist \
           updatable_driver_production_allowlist angle_gl_driver_all_angle angle_gl_driver_selection_pkgs \
           angle_gl_driver_selection_values angle_debug_package; do
    echo "setting $k=$(settings get global "$k")"
  done
  getprop | grep -E 'openbook|gfx|egl|vulkan|angle|hwui|renderengine|ro\.build\.(fingerprint|type|version\.incremental)|ro\.kernel|ro\.board\.platform' |
    sed 's/^/prop /'
  echo "kernel $(uname -r)"
  for p in org.openbook.nvk com.android.angle "$@"; do
    dumpsys package "$p" 2>/dev/null | grep -m 6 -E '^ *(versionCode=|versionName=|flags=\[|privateFlags=\[|codePath=|appId=|userId=)' |
      sed "s|^ *|pkg $p |"
  done
}

dgpu_report() {
  setprop debug.openbook.dgpu_report "$1" || { echo "dgpu-report: setprop refused"; return 1; }
  i=0
  while [ $i -lt 20 ]; do
    out=$(logcat -d -s openbook-pc-setup 2>/dev/null | sed -n "/dgpu-report ($1)/,\$p")
    case $out in *"dgpu-report: health"*) echo "$out" | sed -n '1,/dgpu-report: health/p'; return 0 ;; esac
    sleep 0.5; i=$((i + 1))
  done
  echo "dgpu-report ($1): no report within 10 s"; return 1
}

# RequestedLayerState{NAME parentId=… …}: layer names that contain PKG.
layer_names() {
  dumpsys SurfaceFlinger --list 2>/dev/null | grep -F "$1" |
    sed -E 's/^RequestedLayerState\{//; s/ (parentId|relativeParentId|mirrorId|z|layerStack)=.*$//; s/ !handle.*$//; s/\}$//'
}
layers() {
  layer_names "$1" | while IFS= read -r n; do
    dumpsys SurfaceFlinger --latency "$n" 2>/dev/null | awk 'NR > 1 && $2 > 0 && $2 < 9223372036854775807 {f = 1} END {exit !f}' &&
      echo "$n"
  done
  return 0
}

load_sample() {
  echo "@load up_cs=$(up_cs)"
  head -n 1 /proc/stat
  # "pidstat NAME STAT": ps's full process name (the kernel's comm in STAT is cut to 15 characters)
  ps -A -o PID,NAME 2>/dev/null | awk -v p="$1" '$2 == "surfaceflinger" || index($2, p) == 1 || $2 ~ /composer/ {print $1, $2}' |
    while read -r pid name; do [ -r "/proc/$pid/stat" ] && echo "pidstat $name $(cat "/proc/$pid/stat" 2>/dev/null)"; done
  for f in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq; do
    c=${f#/sys/devices/system/cpu/}; echo "freq ${c%%/*} $(rd "$f" || echo na)"
  done
  if g=$(amdgpu_dev) && [ -n "$g" ]; then
    echo "amdgpu $(kv busy "$g/gpu_busy_percent") $(kv mem_busy "$g/mem_busy_percent")" \
      "sclk=$(grep '\*' "$g/pp_dpm_sclk" 2>/dev/null | awk '{print $2}' || echo na)" \
      "mclk=$(grep '\*' "$g/pp_dpm_mclk" 2>/dev/null | awk '{print $2}' || echo na)"
    for h in "$g"/hwmon/hwmon*; do
      echo "amdgpu_hwmon $(kv temp_mC "$h/temp1_input") $(kv power_uW "$h/power1_average") $(kv power_input_uW "$h/power1_input")"
    done
  else
    echo "amdgpu na"
  fi
  for p in $(nvidia_fns); do echo "nvidia ${p##*/} $(kv runtime_status "$p/power/runtime_status")"; done
  hwmon
  battery
}

# logd keeps a kernel line's prefix as its tag ("NVRM    : Xid ..."), dmesg doesn't ("NVRM: Xid ..."): both match.
KERNEL_GPU_ERR='NVRM *: *Xid|NVRM *: .*(error|failed)|fallen off the bus|GSP.*(error|timeout|fail)|amdgpu.*(ring .*timeout|GPU reset|gpu reset)|nouveau.*(fault|timeout)'
# A broad first cut that logcat applies to the message alone (-e); the shell then applies the exact patterns to the
# whole formatted line (tag included).
KERNEL_PREFILTER='Xid|error|failed|fallen off the bus|GSP|timeout|reset|fault'

# App-side failures, from the app's own processes (its uid) and ActivityManager's events naming it.
APP_ERR='VK_ERROR_DEVICE_LOST|DEVICE_LOST|VK_ERROR_OUT_OF_DEVICE_MEMORY|FATAL EXCEPTION|Fatal signal|EGL_CONTEXT_LOST|GL_CONTEXT_LOST|[Cc]ontext lost|GPU hang'
app_uid() { ps -A -o UID,NAME 2>/dev/null | awk -v p="$1" '$2 == p || index($2, p ":") == 1 {print $1; exit}'; }
# epoch_s: wall-clock seconds (with a fraction where toybox date has %N), to match log lines to the phase.
epoch_s() { e=$(date +%s.%N 2>/dev/null); case $e in *N*|*.|'') date +%s ;; *) echo "$e" ;; esac; }
# newest: the newest signalled present time in a --latency dump, as a string (mksh arithmetic is 32-bit)
newest() { awk 'NR > 1 && $2 > 0 && $2 < 9223372036854775807 {if ($2 > m) m = $2} END {printf "%.0f", m}'; }

# The sampler's processes hand over through files in SW, each with exactly one writer, each written to a temporary
# name and renamed (atomic). put NAME TEXT
put() { printf '%s\n' "$2" > "$SW/.$1.tmp" && mv -f "$SW/.$1.tmp" "$SW/$1"; }
# before A B: true when epoch A (seconds, with a fraction) is earlier than epoch B. awk: mksh's arithmetic is
# 32-bit integers.
before() { awk -v a="$1" -v b="$2" 'BEGIN {exit !(a + 0 < b + 0)}'; }

WATCH_MARGIN=2   # watchers ask logd for everything from this long before the phase's boundary

# watch NAME KIND REGEX LOGCAT_ARGS...: a log watcher. logcat -T <epoch> streams every entry logged since WATCH_FROM
# minus WATCH_MARGIN (logd's backlog first, so lines logged before the reader attached are covered), then each new
# entry as it arrives; nothing is read twice. The watcher's shell ignores lines stamped before WATCH_FROM (compared
# with their fractions) and takes any other line matching REGEX as a failure (abort.NAME "KIND …"). If the stream
# ends, monitoring has lost that log: abort.NAME "monitor-died …". A pipeline, not a fifo (the shell user may not
# create fifos): its left side records its own pid and becomes logcat (NAME.logcat.pid); the reader is the right side
# (NAME.pid). GPU_DIAG_LOGCAT replaces logcat (tests).
watch() {
  name=$1 kind=$2 re=$3; shift 3
  ( put "$name.logcat.pid" "${BASHPID:-$$}"
    exec ${GPU_DIAG_LOGCAT:-logcat} -v epoch -T "$(awk -v f="$watch_from" -v m="$WATCH_MARGIN" 'BEGIN {printf "%.3f", f - m}')" \
      "$@" 2>/dev/null ) |
  (
    trap 'exit 0' TERM
    s0=${watch_from%%.*}
    while IFS= read -r l; do
      set -- $l
      t=${1:-}
      case ${t%%.*} in ''|*[!0-9]*) continue ;; esac   # logcat's own "--------- beginning of" lines
      [ "${t%%.*}" -lt "$s0" ] && continue              # whole seconds before the boundary
      printf '%s\n' "$l" | grep -qE "$re" || continue
      [ "${t%%.*}" = "$s0" ] && before "$t" "$watch_from" && continue   # same second, before the boundary
      put "abort.$name" "$kind up_cs=$(up_cs) $l"; exit 0
    done
    put "abort.$name" "monitor-died: the $name log stream ended"
  ) &
  echo $! > "$SW/$name.pid"
}

# monitor: the slow checks, once a second, off the dumper's clock: the activity token, the app's process, a stall
# (no newer frame in SW/newest for STALL s), the log watchers still running, the dumper still there; every 2nd
# round a load sample (its stdout: SW/loads), every 10th the layer list (SW/layers). Each round ends with a
# heartbeat (SW/hb, up_cs); the dumper stops the run if it goes stale.
monitor() {
  trap 'exit 0' TERM
  r=0; last=; progress=$(up_cs)
  while :; do
    if ! kill -0 "$dumper" 2>/dev/null; then   # the dumper is gone: stop the watchers and their logcats, then go
      for w in kernel app events; do kill "$(cat "$SW/$w.pid" 2>/dev/null)" "$(cat "$SW/$w.logcat.pid" 2>/dev/null)" 2>/dev/null; done
      exit 0
    fi
    now=$(up_cs)
    cur=$(ua_now)
    [ "$cur" = "$ua0" ] || { put abort.monitor "user-activity up_cs=$now ua=${cur:-na}"; exit 0; }
    app_running "$pkg" || { put abort.monitor "app-gone up_cs=$now"; exit 0; }
    nw=$(cat "$SW/newest" 2>/dev/null)
    if [ -n "$nw" ] && [ "$nw" != "$last" ]; then last=$nw; progress=$now; fi
    [ $((now - progress)) -le $((stall * 100)) ] || { put abort.monitor "app-stalled up_cs=$now no new frame for ${stall}s"; exit 0; }
    for w in kernel app events; do
      kill -0 "$(cat "$SW/$w.pid" 2>/dev/null)" 2>/dev/null ||
        { [ -e "$SW/abort.$w" ] || put abort.monitor "monitor-died: the $w watcher is gone"; exit 0; }
    done
    [ $((r % 2)) = 0 ] && load_sample "$pkg"
    lay=$(cat "$SW/layers" 2>/dev/null)
    if [ $((r % 10)) = 9 ] || [ -z "$lay" ]; then put layers "$(layers "$pkg")"; fi
    put hb "$now $(up_cs)"   # this round's start (every check above is from then on) and end
    r=$((r + 1)); sleep 1
  done
}

# procs: "PID PPID STATE START" for every process, from /proc (START: its start time in clock ticks since boot, so a
# reused pid is told apart). Not ps: toybox's and procps's field names differ.
procs() {
  cat /proc/[0-9]*/stat 2>/dev/null | awk '{r = $0; sub(/^.*\) /, "", r); split(r, f, " "); print $1, f[2], f[1], f[20]}'
}
# tree DIR [PID:START...]: as sorted PID:START, the live processes (a zombie counts as gone) among DIR's recorded
# workers (DIR/*.pid; also DIR/dumper when with_dumper is set), the given ones still alive with that start time, and
# all their descendants. A recorded pid counts only while its command line is ours (pids are reused). Passing the
# last result back keeps a process that its parent's death orphaned.
tree() {
  td=$1; shift
  roots=
  for tf in "$td"/*.pid ${with_dumper:+"$td/dumper"}; do
    [ -e "$tf" ] || continue
    tp=$(cat "$tf" 2>/dev/null)
    case $tp in ''|*[!0-9]*) continue ;; esac
    tr '\0' ' ' 2>/dev/null < "/proc/$tp/cmdline" | grep -qE "${GPU_DIAG_OWN_RE:-device[.]sh|logcat}" && roots="$roots $tp"
  done
  procs | awk -v roots="$roots" -v known="$*" '
    $3 !~ /^Z/ {pp[$1] = $2; st[$1] = $4}
    END {
      n = split(roots, r, " "); for (i = 1; i <= n; i++) if (r[i] in pp) keep[r[i]] = 1
      n = split(known, k, " ")
      for (i = 1; i <= n; i++) {split(k[i], x, ":"); if ((x[1] in st) && st[x[1]] == x[2]) keep[x[1]] = 1}
      do {more = 0; for (p in pp) if (!(p in keep) && (pp[p] in keep)) {keep[p] = 1; more = 1}} while (more)
      for (p in keep) print p ":" st[p]
    }' | sort
}
pids() { for t in "$@"; do printf '%s ' "${t%%:*}"; done; }
# reap_dir DIR: stop DIR's workers and everything they started, in bounded time, and verify it. TERM, up to 2 s for
# them to go; then the rest is frozen (STOP can't be caught or ignored) until no new process appears, so none can
# fork between the last look and the KILL; KILL, up to 1 s more. Every process seen once stays tracked, also after
# its parent is gone. Waits only on processes already gone (a blocking wait on a live child could last for ever).
# Exit 0 when none is left, else prints what is (pids) and exits 1.
reap_dir() {
  rs=$(tree "$1"); [ -n "$rs" ] && kill $(pids $rs) 2>/dev/null
  n=0; while rs=$(tree "$1" $rs); [ -n "$rs" ] && [ $n -lt 20 ]; do sleep 0.1; n=$((n + 1)); done
  n=0
  while [ -n "$rs" ] && [ $n -lt 20 ]; do
    kill -STOP $(pids $rs) 2>/dev/null
    rs2=$(tree "$1" $rs); [ "$rs2" = "$rs" ] && break
    rs=$rs2; n=$((n + 1))
  done
  n=0; while [ -n "$rs" ] && [ $n -lt 10 ]; do kill -9 $(pids $rs) 2>/dev/null; sleep 0.1; rs=$(tree "$1" $rs); n=$((n + 1)); done
  live=" $(pids $rs)"
  for tf in "$1"/*.pid; do
    [ -e "$tf" ] || continue
    tp=$(cat "$tf" 2>/dev/null)
    case $live in *" $tp "*) ;; *) wait "$tp" 2>/dev/null ;; esac   # our children's exit status; gone by now
  done
  [ -z "$rs" ] && return 0
  pids $rs; return 1
}

# abort_files: report the first abort file (exit status in rc); true when there is one.
abort_files() {
  for af in "$SW"/abort.*; do
    [ -e "$af" ] || continue
    reason=$(cat "$af"); echo "@abort $reason"
    case $reason in user-activity*) rc=3 ;; *) rc=5 ;; esac
    return 0
  done
  return 1
}
# pending_abort: an abort file, or a heartbeat older than 5 s (stale monitoring is never "no errors"). SW/hb holds the
# monitor's last round: "START END" (up_cs).
pending_abort() {
  abort_files && return 0
  hb=$(cat "$SW/hb" 2>/dev/null); hb=${hb##* }
  case $hb in ''|*[!0-9]*) hb=0 ;; esac
  if [ $(( $(up_cs) - hb )) -gt 500 ]; then echo "@abort monitor-stale up_cs=$(up_cs) heartbeat=$hb"; rc=5; return 0; fi
  return 1
}

finish_phase() {  # stop the workers, take any failure they found before they stopped, then the loads, then the files
  left=$(reap_dir "$SW") || { echo "@cleanup-failed left=$left"; rc=6; }
  [ $rc != 0 ] || abort_files
  [ -s "$SW/loads" ] && cat "$SW/loads"
  [ -n "${GPU_DIAG_KEEP_WORK:-}" ] || [ $rc = 6 ] || rm -rf "$SW"
}

# sample PKG SECONDS PERIOD PHASE UA [STALL] [WATCH_FROM]: the dumper. Only the timed frame dumps run on its clock;
# everything slow is the monitor's and the watchers'. Each round it stops the run on any abort file or a heartbeat
# older than 5 s (stale monitoring is never "no errors"). WATCH_FROM: the epoch the log watchers cover from (default
# this phase's start; gpu-diag.sh passes the warm-up's end, so the gap between phases is covered too).
# At the end: the end boundary is taken first; then a whole monitor round begun after it and a drain of the log
# streams (DRAIN s) are awaited, and any failure found by then, or by the watchers until they are stopped, still
# stops the run. Exit 0 with @end, 3 on input, 5 on any other failure, 6 when a worker could not be stopped.
DRAIN=${GPU_DIAG_DRAIN:-1}
sample() {
  IFS=$DEFAULT_IFS
  pkg=$1; secs=$2; period=$3; phase=$4; ua0=${5:-}; stall=${6:-15}
  end=$(( $(up_cs) + secs * 100 ))
  [ -n "$ua0" ] || { echo "@abort no-activity-token"; exit 4; }
  uid=$(app_uid "$pkg")
  [ -n "$uid" ] || { echo "@abort app-gone up_cs=$(up_cs) (no process when the phase began)"; exit 5; }
  dumper=${BASHPID:-$$}   # this shell's own pid, also when a test runs it in a subshell
  SW=${GPU_DIAG_WORK:-/data/local/tmp/openbook-gpu-diag}/sampler.$dumper
  rm -rf "$SW"; mkdir -p "$SW" || { echo "@abort monitor-died: no work dir $SW"; exit 5; }
  put dumper "$dumper"   # for reap (gpu-diag.sh's clean-up); never a *.pid: the dumper doesn't reap itself
  start_up=$(up_cs); start_epoch=$(epoch_s)
  watch_from=${7:-$start_epoch}
  case $watch_from in ''|*[!0-9.]*) watch_from=$start_epoch ;; esac
  rc=0
  trap 'finish_phase; exit 143' TERM HUP INT
  put layers "$(layers "$pkg")"
  t=$(up_cs); put hb "$t $t"
  watch kernel kernel-gpu-error "$KERNEL_GPU_ERR" -b kernel -e "$KERNEL_PREFILTER"
  watch app app-error "$APP_ERR" -b main,system,crash --uid="$uid"
  watch events app-error "am_(anr|crash).*$pkg" -b events am_anr:I am_crash:I '*:S'
  monitor > "$SW/loads" 2>/dev/null &
  echo $! > "$SW/monitor.pid"
  echo "@begin phase=$phase up_cs=$start_up epoch=$start_epoch watch_from=$watch_from period=$period ua=$ua0 stall_s=$stall uid=$uid watch=stream vsync_ns=$(dumpsys SurfaceFlinger --latency 2>/dev/null | head -n 1)"
  L=
  while [ "$(up_cs)" -lt "$end" ]; do
    pending_abort && break
    Ln=$(cat "$SW/layers" 2>/dev/null)
    if [ "$Ln" != "$L" ] || [ -z "$L" ]; then
      L=$Ln
      echo "@layers up_cs=$(up_cs) $(echo "$L" | grep -c .)"
      [ -n "$L" ] && echo "$L" | sed 's/^/@layer /'
    fi
    echo "@t up_cs=$(up_cs)"
    # Each dump between its own start and end times (@Le) with dumpsys's exit status: the summary bounds the time
    # between two dumps' snapshots by the first one's start and the second one's end. One layer name per line
    # (spaces and [] kept); a redirected loop runs in this shell, so nw_all survives it.
    nw_all=
    while IFS= read -r ln_; do
      [ -n "$ln_" ] || continue
      ds=$(up_cs); dout=$(dumpsys SurfaceFlinger --latency "$ln_" 2>/dev/null); drc=$?; de=$(up_cs)
      echo "@L $ln_"; echo "$dout"; echo "@Le s=$ds e=$de rc=$drc"
      nw_all="$nw_all$(echo "$dout" | newest) "
    done <<EOF
$L
EOF
    put newest "$nw_all"
    sleep "$period"
  done
  # The end boundary, before anything else takes time.
  end_up=$(up_cs); end_epoch=$(epoch_s)
  # Coverage through it: a whole monitor round begun after it (input, the app, a stall, the watchers alive) and
  # DRAIN s for the log streams to deliver what was logged up to it. A failure found by then, or by the watchers
  # before finish_phase stops them, stops the run; no such round within 10 s is a stale monitor.
  while [ $rc = 0 ]; do
    pending_abort && break
    hs=$(cat "$SW/hb" 2>/dev/null); hs=${hs%% *}; case $hs in ''|*[!0-9]*) hs=0 ;; esac
    now=$(up_cs)
    [ "$hs" -gt "$end_up" ] && [ $((now - end_up)) -ge $((DRAIN * 100)) ] && break
    [ $((now - end_up)) -lt 1000 ] || { echo "@abort monitor-stale up_cs=$now no monitor round after the end"; rc=5; break; }
    sleep 0.1
  done
  trap - TERM HUP INT
  finish_phase
  [ $rc = 0 ] || exit $rc
  echo "@end phase=$phase up_cs=$end_up epoch=$end_epoch watch=stream"
}

# reap: stop what any sampler left (gpu-diag.sh's clean-up, after a run or a killed session): exit 0 when every
# sampler.* work dir's workers are gone (the dirs are removed), 6 with the pids left otherwise.
reap_all() {
  bad=0 with_dumper=1
  for d in "${GPU_DIAG_WORK:-/data/local/tmp/openbook-gpu-diag}"/sampler.*; do
    [ -d "$d" ] || continue
    if left=$(reap_dir "$d"); then rm -rf "$d"; echo "@reaped $d"; else echo "@left $d $left"; bad=1; fi
  done
  [ $bad = 0 ] || exit 6
}

# GPU_DIAG_DEVICE_LIB=1: sourced by tests/gpu-diag/sampler-test.sh for its functions, nothing run.
[ -z "${GPU_DIAG_DEVICE_LIB:-}" ] || return 0

case ${1:-} in
  idle) idle ;;
  check) check "${2:?UA}" "${3:?package}"; exit $? ;;
  launch) shift; launch "$@" ;;
  conditions) conditions ;;
  routing) shift; routing "$@" ;;
  dgpu-report) dgpu_report "${2:?tag}" ;;
  layers) layers "${2:?package}" ;;
  sample) shift; sample "$@" ;;
  reap) reap_all ;;
  *) echo "usage: device.sh idle|check UA PKG|launch PKG COMPONENT UA [ARGS]|conditions|routing PKG...|dgpu-report TAG|layers PKG|sample PKG SECONDS PERIOD PHASE UA" >&2; exit 2 ;;
esac
