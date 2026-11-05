#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# app-perf.sh's on-device half (ANAL-378): pushed to /data/local/tmp/openbook-app-perf and run by adb's shell user
# (mksh, toybox), or by root where app-perf.py has made adbd root. Read-only, except launch and home, which start
# activities (launch cold force-stops the app first, as am start -S does).
#
# usage: device.sh power                 amd_pstate status, the platform profile and its choices, every cpufreq policy
#                                        (driver, governor, EPP, frequencies) and every CPU's ranking and top frequency
#        device.sh epp                   the EPP values of all policies, counted: "16:performance,8:balance_power"
#        device.sh launch COMPONENT MODE PERIOD [AM_ARGS...]
#                MODE cold: am start -W -S, a process-cold start (the app is force-stopped; the page cache stays)
#                MODE warm: am start -W --activity-clear-task, the process kept and its activity created again
#                While am start runs, every PERIOD seconds: "@s UPTIME_CS epp=... maxfreq_khz=N", the EPP values seen
#                and the highest current frequency of any policy, so a run shows what the CPU was asked for and gave
#        device.sh home                  am start -W the launcher: the app goes to the background, without an input
#                                        event (an injected key would count as user activity and end the run)
#        device.sh apk APK               the APK's native libraries and dex files, one name per line (unzip -l)
#        device.sh pids PKG              "PID NAME" for each process of PKG (PKG and PKG:*)
#        device.sh maps PID...           "@pid PID", then /proc/PID/maps, for each (root: another app's maps)
set -u
CPUFREQ=/sys/devices/system/cpu/cpufreq
rd() { if [ -r "$1" ] && v=$(cat "$1" 2>/dev/null); then echo "$v"; else return 1; fi; }
# key=value with the value's spaces as commas, "na" when unreadable.
kv() { if v=$(rd "$2"); then echo "$1=$(echo $v | tr ' ' ',')"; else echo "$1=na"; fi; }
up_cs() { IFS=' ' read -r u _ < /proc/uptime; echo "${u%.*}${u#*.}"; }

power() {
  echo "$(kv amd_pstate_status /sys/devices/system/cpu/amd_pstate/status)"
  echo "$(kv platform_profile /sys/firmware/acpi/platform_profile)"
  echo "$(kv platform_profile_choices /sys/firmware/acpi/platform_profile_choices)"
  for p in $CPUFREQ/policy*; do
    [ -d "$p" ] || continue
    echo "policy ${p##*/} $(kv cpus "$p/affected_cpus") $(kv driver "$p/scaling_driver") $(kv governor "$p/scaling_governor")" \
      "$(kv epp "$p/energy_performance_preference") $(kv epp_choices "$p/energy_performance_available_preferences")" \
      "$(kv max_khz "$p/cpuinfo_max_freq") $(kv scaling_max_khz "$p/scaling_max_freq") $(kv cur_khz "$p/scaling_cur_freq")" \
      "$(kv boost "$p/boost")"
  done
  for c in /sys/devices/system/cpu/cpu[0-9]*; do
    echo "cpu ${c##*/} $(kv online "$c/online") $(kv prefcore_ranking "$c/cpufreq/amd_pstate_prefcore_ranking")" \
      "$(kv highest_perf "$c/cpufreq/amd_pstate_highest_perf") $(kv max_khz "$c/cpufreq/cpuinfo_max_freq")"
  done
}

epp() {
  cat $CPUFREQ/policy*/energy_performance_preference 2>/dev/null | sort | uniq -c |
    awk 'BEGIN {s = ""} {s = s (NR > 1 ? "," : "") $1 ":" $2} END {print (s == "" ? "na" : s)}'
}

maxfreq() {
  m=0
  for f in $CPUFREQ/policy*/scaling_cur_freq; do
    v=$(cat "$f" 2>/dev/null) || continue
    [ "${v:-0}" -gt "$m" ] && m=$v
  done
  echo "$m"
}

sampler() {  # PERIOD STOPFILE
  while [ ! -e "$2" ]; do
    echo "@s $(up_cs) epp=$(epp) maxfreq_khz=$(maxfreq)"
    sleep "$1"
  done
}

launch() {  # COMPONENT MODE PERIOD [AM_ARGS...]
  comp=$1; mode=$2; period=$3; shift 3
  stop=/data/local/tmp/openbook-app-perf/.stop.$$
  rm -f "$stop"
  sampler "$period" "$stop" &
  sp=$!
  echo "@t0 $(up_cs)"
  case $mode in
    cold) am start -W -S -n "$comp" "$@"; rc=$? ;;
    warm) am start -W --activity-clear-task -n "$comp" "$@"; rc=$? ;;
    *) echo "@error mode $mode"; rc=2 ;;
  esac
  echo "@t1 $(up_cs) rc=$rc"
  touch "$stop"; wait "$sp"; rm -f "$stop"
  return $rc
}

case ${1:-} in
  power) power ;;
  epp) epp ;;
  launch) shift; launch "$@" ;;
  home) am start -W -a android.intent.action.MAIN -c android.intent.category.HOME ;;
  apk) unzip -l "${2:?APK}" | awk '{print $NF}' | grep -E '^(lib/[^/]+/[^/]+\.so|classes[0-9]*\.dex)$' ;;
  pids) ps -A -o PID,NAME | awk -v p="${2:?PKG}" 'NR > 1 && ($2 == p || index($2, p ":") == 1) {print $1, $2}' ;;
  maps) shift; for p in "$@"; do echo "@pid $p"; cat "/proc/$p/maps"; done ;;
  *) echo "usage: device.sh power|epp|launch|home|apk|pids|maps ..." >&2; exit 2 ;;
esac
