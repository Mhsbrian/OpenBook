#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# OpenBook ARM-apps check (ANAL-200): the arm64 native bridge (Digitalis) on the device's own CPU, unattended. It is
# run.sh in the bridge add-on's payload (scripts/compat/digitalis/stick/make-bridge-check.sh). The live stick's
# "OpenBook ARM apps check" entry unpacks the payload to /data/local/tmp/openbook-bridge on the stick and runs it as
# root once Android has booted (openbook-live-init, androidboot.openbook.addon=bridge); by hand the same way:
#   su 0 sh /data/local/tmp/openbook-bridge/run.sh OUT_DIR
#   su 0 sh /data/local/tmp/openbook-bridge/run.sh --cleanup
# mksh + toybox. Writes only below OUT_DIR and the payload directory, on the stick; never a disk. Changes, each put
# back by --cleanup (which openbook-live-init always runs afterwards): stay_on_while_plugged_in (the probe app needs
# the screen on), the two probe apps (installed, then uninstalled).
#
# Parts, in this order (the cheapest first, in case the run is cut short):
#   check   /system/bin/arm64/openbook_bridge_check: arm64 exec, ID registers, FRECPE/FRSQRTE, CRC32/NEON
#   probe   the compat probe (scripts/compat/probe): arm64-v8a through the app native bridge, x86_64 as the control
#   bench   CoreMark, ROUNDS interleaved rounds of x86_64 then arm64: the executables (arm64 through binfmt_misc) and
#           the same code in the probe app (arm64 through libnativebridge), as scripts/compat/run-bench.sh does it
# Results: OUT_DIR/facts.txt, bridge-check.txt, probe-<abi>.txt (+ .logcat.gz), bench.csv, raw/, run.log; the host
# turns them into a report with scripts/compat/digitalis/stick/bridge-report.py.
# Env: BRIDGE_PARTS (default "check probe bench"), BRIDGE_ROUNDS (3), BRIDGE_ITER (600000).
PATH=/system/bin:/system_ext/bin:/vendor/bin:$PATH
H=$(cd "${0%/*}" && pwd)
# `am` and `pm` run Java (app_process), which needs init's classpath exports; openbook-live-init's environment is
# minimal. derive_classpath writes them at boot as "export NAME VALUE" lines; zygote's environment has them too.
if [ -z "$BOOTCLASSPATH" ]; then
  if [ -r /data/system/environ/classpath ]; then
    while read -r k n v; do [ "$k" = export ] && [ -n "$n" ] && export "$n=$v"; done < /data/system/environ/classpath
  else
    z=$(pidof zygote64 2>/dev/null | cut -d' ' -f1)
    [ -n "$z" ] && for kv in $(tr '\0' '\n' < /proc/$z/environ | grep -E '^[A-Z_]*CLASSPATH=|^STANDALONE_SYSTEMSERVER_JARS='); do
      export "$kv"; done
  fi
fi
STATE=$H/state.sh
ABIS="x86_64 arm64"

restore() {
  [ -f "$STATE" ] || return 0
  . "$STATE"
  settings put global stay_on_while_plugged_in "${ORIG_STAYON:-0}" 2>/dev/null
}

if [ "$1" = --cleanup ]; then
  echo "cleanup: $(date)"
  restore
  for s in $ABIS; do am force-stop dev.anybook.probe.$s > /dev/null 2>&1; pm uninstall dev.anybook.probe.$s > /dev/null 2>&1; done
  rm -f "$STATE"
  echo "stay_on=$(settings get global stay_on_while_plugged_in)"
  pm list packages | grep dev.anybook.probe || echo "probe apps: none installed"
  exit 0
fi

OUT=${1:?usage: run.sh OUT_DIR | --cleanup}
PARTS=${BRIDGE_PARTS:-check probe bench}
ROUNDS=${BRIDGE_ROUNDS:-3}; ITER=${BRIDGE_ITER:-600000}
mkdir -p "$OUT/raw"
LOG=$OUT/run.log
say() { echo "$(date +%T) $*" | tee -a "$LOG"; echo "openbook-bridge: $*" > /dev/kmsg 2>/dev/null; }
now() { cut -d' ' -f1 /proc/uptime; }

[ -f "$STATE" ] || printf 'ORIG_STAYON=%s\n' \
  "$(settings get global stay_on_while_plugged_in 2>/dev/null | grep -E '^[0-9]+$')" > "$STATE"
trap 'restore' EXIT

say "start: parts [$PARTS], CoreMark $ROUNDS round(s) of $ITER iterations"
{
  echo "date: $(date -u +%FT%TZ)"; echo "uptime: $(cat /proc/uptime)"
  for p in ro.build.fingerprint ro.product.model ro.boot.selinux ro.boot.openbook.live ro.product.cpu.abilist \
      ro.dalvik.vm.native.bridge ro.dalvik.vm.isa.arm64 ro.enable.native.bridge.exec ro.berberis.flags; do
    echo "$p=$(getprop $p)"; done
  echo "kernel: $(uname -a)"
  echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ *//'), $(nproc) CPUs; $(grep MemTotal /proc/meminfo | tr -s ' ')"
  echo "cpu flags (translator-relevant): $(grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' | grep -xE 'avx2|avx512f|bmi1|bmi2|fma|movbe|adx|sha_ni|vaes' | tr '\n' ' ')"
  c=/sys/devices/system/cpu/cpufreq/policy0
  echo "cpufreq: driver=$(cat $c/scaling_driver 2>/dev/null) governor=$(cat $c/scaling_governor 2>/dev/null)" \
    "epp=$(cat $c/energy_performance_preference 2>/dev/null) max_khz=$(cat $c/cpuinfo_max_freq 2>/dev/null)" \
    "amd_pstate=$(cat /sys/devices/system/cpu/amd_pstate/status 2>/dev/null)"
  echo "platform_profile: $(cat /sys/firmware/acpi/platform_profile 2>/dev/null)"
  echo "power: $(dumpsys battery 2>/dev/null | grep -E 'AC powered|level:' | tr -s ' \n' ' ')"
  echo "binfmt: $(for f in arm64_dyn arm64_exe; do printf '%s=%s ' $f "$(head -n 1 /proc/sys/fs/binfmt_misc/$f 2>&1)"; done)"
  echo "payload: $(tr -d '\n' < "$H/VERSION.json" 2>/dev/null | cut -c1-2000)"
} > "$OUT/facts.txt" 2>&1

screen_on() {
  settings put global stay_on_while_plugged_in 7
  input keyevent KEYCODE_WAKEUP; sleep 1; wm dismiss-keyguard; sleep 2
}

# logcat_wait PATTERN SECONDS: poll the probe's log tag until PATTERN shows up
logcat_wait() {
  i=0
  while [ $i -lt "$2" ]; do
    logcat -d -s AnyBookProbe:I 2>/dev/null | grep -qE "$1" && return 0
    sleep 3; i=$((i + 3))
  done
  return 1
}

install_apk() {  # ABI: stream the APK in, as the stick's own /data/local/tmp is not readable by system_server
  a=$H/apk/anybook-probe-$1.apk
  pm uninstall dev.anybook.probe.$1 > /dev/null 2>&1
  pm install -r -g -t -S "$(stat -c %s "$a")" < "$a" 2>&1 | tail -n 1
}

part_check() {
  c=/system/bin/arm64/openbook_bridge_check
  t0=$(now)
  if [ -x $c ]; then timeout 300 $c > "$OUT/bridge-check.txt" 2>&1; rc=$?; else echo "$c missing" > "$OUT/bridge-check.txt"; rc=127; fi
  echo "exit $rc after $(awk "BEGIN{print $(now)-$t0}") s" >> "$OUT/bridge-check.txt"
  say "check: exit $rc, $(grep -c '"ok": true' "$OUT/bridge-check.txt") check(s) ok"
}

part_probe() {
  for s in $ABIS; do
    pkg=dev.anybook.probe.$s
    say "probe $s: install: $(install_apk $s)"
    pabi=$(dumpsys package $pkg 2>/dev/null | grep -m1 -o 'primaryCpuAbi=[^ ]*' | cut -d= -f2)
    logcat -b all -c 2>/dev/null
    t0=$(now)
    am start -W -n $pkg/dev.anybook.probe.MainActivity > "$OUT/raw/probe-$s-start.txt" 2>&1
    logcat_wait 'PROBE_DONE' 240; done=$?
    pid=$(pidof $pkg | cut -d' ' -f1)
    nb=-; [ -n "$pid" ] && nb=$(grep -c libberberis_arm64 /proc/$pid/maps 2>/dev/null)
    logcat -d -s AnyBookProbe:I > "$OUT/probe-$s.txt" 2>&1
    logcat -d -b main,system,crash -v threadtime 2>/dev/null | gzip -c > "$OUT/probe-$s.logcat.gz"
    echo "PROBE_SUMMARY abi=$s primary_cpu_abi=$pabi pid=${pid:--} bridge_maps=$nb finished=$([ $done = 0 ] && echo yes || echo no)" \
      "secs=$(awk "BEGIN{print $(now)-$t0}")" >> "$OUT/probe-$s.txt"
    say "probe $s: $(grep -m1 -oE 'PROBE_DONE pass=[0-9]+ fail=[0-9]+ skip=[0-9]+' "$OUT/probe-$s.txt" || echo 'no PROBE_DONE'), primary ABI $pabi, bridge maps $nb"
    am force-stop $pkg
  done
}

row() {  # mode abi round file
  secs=$(sed -n 's/.*Total time (secs): *\([0-9.]*\).*/\1/p' "$4" | head -n 1)
  ips=$(sed -n 's/.*Iterations\/Sec *: *\([0-9.]*\).*/\1/p' "$4" | head -n 1)
  valid=$(grep -q 'Correct operation validated' "$4" && echo yes || echo no)
  echo "$1,$2,$3,$ITER,$secs,$ips,$valid" >> "$OUT/bench.csv"
  say "bench $1 $2 round $3: ${ips:-?} it/s in ${secs:-?} s valid=$valid"
}

part_bench() {
  echo "mode,abi,round,iterations,total_secs,iter_per_sec,valid" > "$OUT/bench.csv"
  for s in $ABIS; do pm path dev.anybook.probe.$s > /dev/null 2>&1 || say "bench: probe $s: $(install_apk $s)"; done
  r=1
  while [ $r -le "$ROUNDS" ]; do
    for s in $ABIS; do
      abi=$s; [ $s = arm64 ] && abi=arm64-v8a
      f=$OUT/raw/exe-$s-r$r.txt
      timeout 900 "$H/bench/coremark-$s" 0x0 0x0 0x66 "$ITER" > "$f" 2>&1
      row exe $abi $r "$f"
      pkg=dev.anybook.probe.$s; f=$OUT/raw/apk-$s-r$r.txt
      am force-stop $pkg; logcat -c 2>/dev/null
      am start -n $pkg/dev.anybook.probe.MainActivity --es mode bench --es arg "0x0 0x0 0x66 $ITER" > /dev/null 2>&1
      logcat_wait 'PROBE_BENCH_DONE|PROBE_BENCH_FAIL' 900
      logcat -d -s AnyBookProbe:I 2>/dev/null | grep -E 'PROBE_BENCH' | sed 's/.*PROBE_BENCH[_A-Z]* \{0,1\}//' > "$f"
      am force-stop $pkg
      row apk $abi $r "$f"
    done
    r=$((r + 1))
  done
}

screen_on
fail=0
for p in $PARTS; do
  case $p in
    check) part_check ;;
    probe) part_probe ;;
    bench) part_bench ;;
    *) say "unknown part $p"; fail=1 ;;
  esac
done
say "done: $(awk "BEGIN{print $(now)}") s uptime"
exit $fail
