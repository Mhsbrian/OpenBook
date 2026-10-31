#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# OpenBook graphics check (ANAL-177): dEQP and ANGLE end2end on the device's own graphics drivers, unattended. It is
# run.sh in the graphics add-on's payload (scripts/graphics/mkaddon.py). The live stick's "OpenBook graphics check"
# entry unpacks the payload to /data/local/tmp/openbook-gfx on the stick and runs it as root once Android has booted
# (openbook-live-init, androidboot.openbook.addon=gfx); a device agent can run it by hand the same way:
#   su 0 sh /data/local/tmp/openbook-gfx/run.sh OUT_DIR
#   su 0 sh /data/local/tmp/openbook-gfx/run.sh --cleanup
# mksh + toybox. Writes only below OUT_DIR, the payload directory and /sdcard (the ANGLE helper app's files, through
# its FUSE view as the shell user), all on the stick; never a disk. Changes, each put back by --cleanup (which
# openbook-live-init always runs afterwards): persist.graphics.egl (radeonsi pass), stay_on_while_plugged_in (screen
# stays on for the app-based parts), disable_window_blurs (blur part), two test apps (installed, then uninstalled).
#
# Parts, in this order (the most important first, in case the whole run is cut short; blur first because it measures
# the desktop, which a GPU reset in a later part would restart):
#   blur        background blur on the desktop (ANAL-203): the shade and Quick Settings opened 20 times each, blur on
#               and off twice (blur-check.sh; SystemUI frame stats, SurfaceFlinger TimeStats, blurred layers, four
#               screenshots). Only when the image enables blur (ro.surface_flinger.supports_background_blur=1)
#   vk          dEQP-VK through Android's Vulkan loader and the image's RADV (android-strict: Vulkan 1.1, as shipped)
#   vk14        the same cases against RADV built without android-strict (Vulkan 1.4), bind-mounted over the shipped
#               one in a mount namespace of its own (gfx-nsbind): nothing else on the device sees it. Only when the
#               image's RADV is android-strict (1.1): the payload then carries the second build
#   gles-angle  dEQP-GLES2/3/31 through Android's libEGL on the system driver, ANGLE on RADV (as shipped), pbuffers
#   gles-mesa   the same cases on radeonsi (persist.graphics.egl=mesa for the run's processes, then put back)
#   egl         dEQP-EGL in AOSP's dEQP app (com.drawelements.deqp) with window surfaces, as the CTS runs it
#   angle       ANGLE's end2end tests in Android 17's CTS helper app, with a subset of the CTS expectations
# dEQP runs go through Mesa's deqp-runner (parallel, restarts after a crash or a hang, retries failures to find
# flakes), as Mesa CI runs them. Results: OUT_DIR/<part>/, OUT_DIR/parts.jsonl, OUT_DIR/facts.txt; the host turns
# them into a report with scripts/graphics/gfx-report.py.
# Env: GFX_PARTS (default: all), GFX_JOBS (default: half the CPUs, at most 12), GFX_QUICK=1 (the first 40 cases of
# every list: a plumbing test; also openbook.gfx_quick=1 on the kernel command line, for the QEMU test entry),
# GFX_FORCE=1 (vk14 and gles-mesa on a GPU that is not AMD). GFX_QUICK also cuts the blur part to 3 cycles, on then off.
PATH=/system/bin:/system_ext/bin:/vendor/bin:$PATH
H=$(cd "${0%/*}" && pwd)
# `am instrument` runs Java (app_process), which needs init's classpath exports; openbook-live-init's environment is
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

restore() {
  [ -f "$STATE" ] || return 0
  . "$STATE"
  setprop persist.graphics.egl "$ORIG_EGL"
  settings put global stay_on_while_plugged_in "${ORIG_STAYON:-0}" 2>/dev/null
  settings put global disable_window_blurs "${ORIG_BLUR:-0}" 2>/dev/null
}

if [ "$1" = --cleanup ]; then
  echo "cleanup: $(date)"
  restore
  pm uninstall com.drawelements.deqp > /dev/null 2>&1
  pm uninstall com.android.angle.test > /dev/null 2>&1
  # Through /sdcard as the shell user, never underneath FUSE (see angle_app).
  su 2000 sh -c 'rm -rf /sdcard/chromium_tests_root /sdcard/output.json /sdcard/out.txt' 
  rm -f "$STATE"
  echo "persist.graphics.egl=[$(getprop persist.graphics.egl)] stay_on=$(settings get global stay_on_while_plugged_in) disable_window_blurs=$(settings get global disable_window_blurs)"
  pm list packages | grep -E 'drawelements|angle.test' || echo "test apps: none installed"
  exit 0
fi

OUT=${1:?usage: run.sh OUT_DIR | --cleanup}
grep -q 'openbook.gfx_quick=1' /proc/cmdline 2>/dev/null && GFX_QUICK=1
PARTS=${GFX_PARTS:-blur vk vk14 gles-angle gles-mesa egl angle}
N=$(nproc 2>/dev/null || echo 4)
J=${GFX_JOBS:-$((N / 2))}; [ "$J" -gt 12 ] && [ -z "$GFX_JOBS" ] && J=12; [ "$J" -lt 1 ] && J=1
HAL=$(getprop vendor.anybook.gpu.hal)
mkdir -p "$OUT"
LOG=$OUT/run.log
say() { echo "$(date +%T) $*" | tee -a "$LOG"; echo "openbook-gfx: $*" > /dev/kmsg 2>/dev/null; }
q() { printf '"%s"' "$(printf '%s' "$1" | tr -d '"\\' | tr '\n\t' '  ')"; }
gpu_events() { dmesg 2>/dev/null | grep -ciE 'amdgpu.*(ring .*timeout|gpu reset|page fault|fault in|hang)'; }

# Settings this run may change, saved once (a second run after a crash keeps the first run's originals).
[ -f "$STATE" ] || printf 'ORIG_EGL=%s\nORIG_STAYON=%s\nORIG_BLUR=%s\n' "$(getprop persist.graphics.egl)" \
  "$(settings get global stay_on_while_plugged_in 2>/dev/null | grep -E '^[0-9]+$')" \
  "$(settings get global disable_window_blurs 2>/dev/null | grep -E '^[01]$')" > "$STATE"
trap 'restore' EXIT

say "start: parts [$PARTS], jobs $J of $N CPUs, gpu hal [$HAL], quick [${GFX_QUICK:-0}]"
{
  echo "date: $(date -u +%FT%TZ)"; echo "uptime: $(cat /proc/uptime)"
  echo "classpath: BOOTCLASSPATH has $(echo "$BOOTCLASSPATH" | tr ':' '\n' | grep -c .) jars"
  for p in ro.build.fingerprint ro.product.model ro.boot.selinux ro.boot.openbook.live vendor.anybook.gpu.hal \
      vendor.anybook.gpu.pci_id vendor.anybook.gpu.driver ro.hardware.egl ro.hardware.vulkan ro.hardware.gralloc \
      ro.hardware.hwcomposer persist.graphics.egl ro.opengles.version ro.vendor.api_level ro.board.first_api_level; do
    echo "$p=$(getprop $p)"; done
  echo "kernel: $(uname -a)"
  echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2-), $N CPUs; $(grep MemTotal /proc/meminfo)"
  for c in /sys/class/drm/card[0-9]; do d=$c/device
    echo "${c##*/}: $(cat $d/vendor $d/device $d/revision $d/subsystem_vendor $d/subsystem_device 2>/dev/null | tr '\n' ' ')driver=$(basename "$(readlink $d/driver)")"; done
  for f in /vendor/lib64/hw/vulkan.radv.so /vendor/lib64/libgallium_dri.so /vendor/lib64/egl/libEGL_mesa.so \
      /system/lib64/libEGL_angle.so /system/lib64/libGLESv2_angle.so; do
    [ -f $f ] && echo "$(sha256sum $f | cut -d' ' -f1)  $f"; done
  echo "power: $(dumpsys battery 2>/dev/null | grep -E 'AC powered|level:' | tr -s ' \n' ' ')"
  echo "keyguard: $(dumpsys window 2>/dev/null | grep -m2 -E 'isKeyguardShowing|mKeyguardShowing|KeyguardShowing' | tr -s ' \n' ' ')"
  echo "amdgpu events before: $(gpu_events)"
  echo "payload: $(cat "$H/VERSION.json" 2>/dev/null | tr -d '\n' | cut -c1-2000)"
} > "$OUT/facts.txt" 2>&1

# Case lists (GFX_QUICK: the first 40 of each).
CL=$H/caselists
if [ "${GFX_QUICK:-0}" = 1 ]; then
  CL=$H/caselists-quick; mkdir -p "$CL"
  for f in "$H"/caselists/*.txt; do head -n 40 "$f" > "$CL/${f##*/}"; done
fi

COMMON="\"--deqp-archive-dir=$H/data\", \"--deqp-log-images=disable\", \"--deqp-log-shader-sources=disable\", \"--deqp-shadercache=disable\""
GLES="\"--deqp-surface-width=256\", \"--deqp-surface-height=256\", \"--deqp-surface-type=pbuffer\", \"--deqp-visibility=hidden\", \"--deqp-gl-config-name=rgba8888d24s8ms0\""
# One [[deqp]] entry: caselist, skip list (in skips/: Mesa CI's lists of tests that hang AMD GPUs or take minutes),
# renderer regex ("" for none), extra deqp args (a TOML list body or "").
entry() {
  printf '[[deqp]]\ndeqp = "%s"\ncaselists = ["%s"]\nskips = ["%s"]\ntests_per_group = 500\n' \
    "$H/bin/deqp-binary64" "$1" "$H/skips/$2"
  [ -n "$3" ] && printf 'renderer_check = "%s"\n' "$3"
  printf 'deqp_args = [%s%s]\n[deqp.env]\nLD_PRELOAD = "%s"\n\n' "$COMMON" "${4:+, $4}" "$H/lib/libdeqp_stdout.so"
}
# The renderer checks hold only on the AMD GPU; elsewhere (QEMU: SwiftShader) the run just records what it got.
amd() { [ "$HAL" = amdgpu ] && echo "$1"; }

# deqp-runner on a suite: PART CAP_SECONDS [command prefix...]
runner() {
  p=$1 cap=$2; shift 2
  # From the archive directory: a few dEQP cases open their data relative to the working directory and ignore
  # --deqp-archive-dir (copy_memory_indirect's ./vulkan/data/copy_memory_indirect/sample_text.txt; G14 run 1).
  (cd "$H/data" && timeout -k 10 "$cap" "$@" "$H/bin/deqp-runner" suite --suite "$OUT/$p/suite.toml" \
    --output "$OUT/$p/run" --jobs "$J" --summary-limit 40) > "$OUT/$p/console.txt" 2>&1
  rc=$?
  tail -n 6 "$OUT/$p/console.txt" | tee -a "$LOG"
  return $rc
}

screen_on() {
  settings put global stay_on_while_plugged_in 7
  input keyevent KEYCODE_WAKEUP; sleep 1; wm dismiss-keyguard; sleep 2
  echo "keyguard: $(dumpsys window 2>/dev/null | grep -m2 -E 'isKeyguardShowing|mKeyguardShowing|KeyguardShowing' | tr -s ' \n' ' ')"
}

install_apk() {  # streamed, so system_server needs no access to the payload directory
  pm install -r -g -t -S "$(stat -c %s "$1")" < "$1" 2>&1
}

# dEQP-EGL in the dEQP app: one process for the whole list, as the CTS runs it. After a crash it goes on with the cases
# not begun yet (the CTS's DeqpTestRunner does the same; dEQP runs a list in its own tree order, not the list's), at
# most 20 times. The host's report marks a case begun but never ended as a crash.
egl_app() {
  d=$OUT/egl; chmod 0777 "$d"
  install_apk "$H/apk/com.drawelements.deqp.apk" | tee -a "$LOG"
  screen_on >> "$d/console.txt"
  list=$d/caselist-0.txt; cp "$CL/egl.txt" "$list"; chmod 0644 "$list"
  i=0
  while [ $i -lt 20 ]; do
    log=$d/egl-$i.qpa; : > "$log"; chmod 0666 "$log"
    timeout 900 am instrument -w -r -e deqpLogFilename "$log" -e deqpCmdLine "--deqp-caselist-file=$list \
--deqp-gl-config-name=rgba8888d24s8ms0 --deqp-screen-rotation=unspecified --deqp-surface-type=window \
--deqp-watchdog=enable --deqp-log-images=disable --deqp-log-shader-sources=disable" -e deqpLogData false \
      com.drawelements.deqp/com.drawelements.deqp.testercore.DeqpInstrumentation > "$d/instrument-$i.txt" 2>&1
    rc=$?
    grep '^#beginTestCaseResult' "$log" | cut -d' ' -f2 > "$d/begun-$i.txt"
    awk 'FILENAME == ARGV[1] {seen[$0] = 1; next} !($0 in seen)' "$d/begun-$i.txt" "$list" > "$d/caselist-$((i + 1)).txt"
    echo "instrument $i: exit $rc, $(grep -c . "$d/begun-$i.txt") begun, $(grep -c '^#endTestCaseResult' "$log") ended, $(grep -c . "$d/caselist-$((i + 1)).txt") left" \
      | tee -a "$d/console.txt"
    # Done: nothing left, the session ended (cases left are not in this dEQP build), or nothing ran at all (the app
    # could not start: the console and instrument files say why).
    [ -s "$d/caselist-$((i + 1)).txt" ] || break
    grep -q '^#endSession' "$log" && break
    [ -s "$d/begun-$i.txt" ] || break
    i=$((i + 1)); list=$d/caselist-$i.txt; chmod 0644 "$list"
  done
  n=$(cat "$d"/begun-*.txt 2>/dev/null | grep -c .)
  gzip -f "$d"/egl-*.qpa
  [ "$n" -gt 0 ]  # the part's status: did any case run
}

# ANGLE end2end in Android 17's CTS helper app (CtsAngleEnd2EndTestCases): it runs what the expectations file marks
# PASS, prints gtest's progress to /sdcard/out.txt as it goes and writes /sdcard/output.json (per test: actual,
# expected) at the end. ANGLE's own per-test watchdog does not run in the app (only in its child-process mode), so one
# hanging test would hold the whole part (CapturedTest.MultiFrame did for 12 minutes in an early Cuttlefish run, while
# /sdcard was broken as described below). Here, when
# out.txt stops growing for ANGLE_STALL seconds (default 120), the app is stopped; the test it was in is a time-out
# (gfx-report.py reads it from out-<round>.txt) and the next round runs only the PASS tests not started yet. At most
# 8 rounds, 25 minutes each.
# /sdcard is MediaProvider's FUSE view of /data/media/0. Its files are created and deleted only through /sdcard, as
# the shell user (sdcard_rw): a file deleted underneath FUSE leaves a stale entry, and the app then cannot create
# /sdcard/out.txt ("No such file or directory"; seen in Cuttlefish). Results are read from /data/media/0, read-only.
sdcard() { su 2000 sh -c "$1"; }
angle_app() {
  d=$OUT/angle; S=/data/media/0; stall=${ANGLE_STALL:-120}
  install_apk "$H/apk/AngleEnd2EndTestsHelper.apk" | tee -a "$LOG"
  appops set com.android.angle.test MANAGE_EXTERNAL_STORAGE allow 2>&1 | tee -a "$d/console.txt"
  sdcard 'mkdir -p /sdcard/chromium_tests_root/src/tests' 2>&1 | tee -a "$d/console.txt"
  exp=$d/exp-0.txt
  if [ "${GFX_QUICK:-0}" = 1 ]; then
    { grep -v '= PASS$' "$H/caselists/angle_end2end_tests_expectations.txt" | grep -v ' : \* = SKIP$'
      grep '= PASS$' "$H/caselists/angle_end2end_tests_expectations.txt" | head -n 40
      grep ' : \* = SKIP$' "$H/caselists/angle_end2end_tests_expectations.txt"; } > "$exp"
  else
    cp "$H/caselists/angle_end2end_tests_expectations.txt" "$exp"
  fi
  i=0; left=$(grep -c '= PASS$' "$exp")
  while [ $i -lt 8 ]; do
    sdcard 'cat > /sdcard/chromium_tests_root/src/tests/angle_end2end_tests_expectations.txt; rm -f /sdcard/output.json' \
      < "$exp" 2>&1 | tee -a "$d/console.txt"
    screen_on >> "$d/console.txt"
    am instrument -w -r -e class com.android.angle.test.AngleEnd2EndTest#testAngleEnd2End \
      com.android.angle.test/androidx.test.runner.AndroidJUnitRunner > "$d/instrument-$i.txt" 2>&1 &
    ip=$!; t0=$(date +%s); last=-1; idle=0; why=
    while kill -0 $ip 2>/dev/null; do
      sleep 5
      sz=$(stat -c %s "$S/out.txt" 2>/dev/null || echo 0)
      if [ "$sz" = "$last" ]; then idle=$((idle + 5)); else idle=0; last=$sz; fi
      [ $idle -ge "$stall" ] && why="no progress for $stall s"
      [ $(( $(date +%s) - t0 )) -ge 1500 ] && why="round over 1500 s"
      if [ -n "$why" ]; then am force-stop com.android.angle.test; sleep 2; kill $ip 2>/dev/null; break; fi
    done
    wait $ip; rc=$?
    [ -f "$S/out.txt" ] && cp "$S/out.txt" "$d/out-$i.txt"
    [ -f "$S/output.json" ] && cp "$S/output.json" "$d/output-$i.json"
    # Tests this round started (gtest's "[ RUN      ] name"), then the PASS lines not started yet.
    sed -n 's/^\[ RUN      \] //p' "$d/out-$i.txt" 2>/dev/null | sed 's/ *$//' > "$d/started-$i.txt"
    awk 'FILENAME == ARGV[1] {seen[$0] = 1; next}
         /= PASS$/ {t = $0; sub(/^[^:]*: /, "", t); sub(/ = PASS$/, "", t); if (t in seen) next} {print}' \
      "$d/started-$i.txt" "$exp" > "$d/exp-$((i + 1)).txt"
    was=$left; left=$(grep -c '= PASS$' "$d/exp-$((i + 1)).txt")
    echo "round $i: exit $rc$([ -n "$why" ] && echo ", stopped: $why"), $(grep -c . "$d/started-$i.txt") started, $left of $was PASS tests left, output.json $([ -f "$d/output-$i.json" ] && echo yes || echo no)" \
      | tee -a "$d/console.txt"
    # Done when the round finished on its own (output.json), nothing is left, or nothing new started.
    [ -f "$d/output-$i.json" ] && break
    [ "$left" -gt 0 ] && [ "$left" -lt "$was" ] || break
    i=$((i + 1)); exp=$d/exp-$i.txt
  done
  tail -n 4 "$d/instrument-$i.txt" | tee -a "$LOG"
  n=$(cat "$d"/started-*.txt 2>/dev/null | grep -c .)
  gzip -f "$d"/output-*.json "$d"/out-*.txt "$d"/started-*.txt 2>/dev/null  # every test, skipped ones too (~6 MB)
  [ "$n" -gt 0 ]  # the part's status: did any test start
}

for p in $PARTS; do
  mkdir -p "$OUT/$p"
  skip=
  case $p in
    vk14|gles-mesa) [ "$HAL" = amdgpu ] || [ "${GFX_FORCE:-0}" = 1 ] || skip="needs the AMD GPU (hal=$HAL)" ;;
    vk|gles-angle|egl|angle) ;;
    blur) [ "$(getprop ro.surface_flinger.supports_background_blur)" = 1 ] || skip="the image does not enable blur" ;;
    *) skip="unknown part" ;;
  esac
  case $p in
    vk14) [ -f "$H/radv-nonstrict/vulkan.radv.so" ] || skip="no second RADV in the payload (the image's reports Vulkan 1.4)" ;;
    egl) [ -f "$H/apk/com.drawelements.deqp.apk" ] || skip="no dEQP app in the payload" ;;
    angle) [ -f "$H/apk/AngleEnd2EndTestsHelper.apk" ] || skip="no ANGLE end2end app in the payload" ;;
    blur) [ -f "$H/blur-check.sh" ] || skip="no blur check in the payload" ;;
  esac
  if [ -n "$skip" ]; then
    say "$p: skipped: $skip"
    echo "{\"part\": \"$p\", \"skipped\": $(q "$skip")}" >> "$OUT/parts.jsonl"
    continue
  fi
  say "$p: start"
  ev0=$(gpu_events); t0=$(date +%s)
  case $p in
    vk) entry "$CL/vk.txt" radv.txt "$(amd RADV)" > "$OUT/vk/suite.toml"; runner vk 1200 ;;
    vk14) entry "$CL/vk.txt" radv.txt "$(amd RADV)" > "$OUT/vk14/suite.toml"
          runner vk14 1200 "$H/bin/gfx-nsbind" "$H/radv-nonstrict/vulkan.radv.so" /vendor/lib64/hw/vulkan.radv.so ;;
    gles-angle|gles-mesa)
      r=ANGLE k=angle.txt; [ $p = gles-mesa ] && r=radeonsi k=radeonsi.txt
      for m in gles2 gles3 gles31; do entry "$CL/$m.txt" $k "$(amd $r)" "$GLES"; done > "$OUT/$p/suite.toml"
      [ $p = gles-mesa ] && setprop persist.graphics.egl mesa
      runner $p 1200
      rc=$?; [ $p = gles-mesa ] && setprop persist.graphics.egl "$(. "$STATE"; echo "$ORIG_EGL")"; (exit $rc) ;;
    egl) egl_app ;;
    angle) angle_app ;;
    blur) screen_on > "$OUT/blur/console.txt"
          if [ "${GFX_QUICK:-0}" = 1 ]; then BLUR_CYCLES=3 timeout 600 sh "$H/blur-check.sh" "$OUT/blur" on off
          else timeout 900 sh "$H/blur-check.sh" "$OUT/blur" on off on off; fi >> "$OUT/blur/console.txt" 2>&1
          rc=$?; tail -n 2 "$OUT/blur/console.txt" | tee -a "$LOG"; (exit $rc) ;;
  esac
  rc=$?; t=$(( $(date +%s) - t0 )); ev=$(( $(gpu_events) - ev0 ))
  # The big per-run files go compressed (the results land on the stick's ESP): results.csv lists every case, and
  # deqp-runner keeps each group's dEQP console log and case list (c<group>.r<run>.*), about 10 MB for a Vulkan pass.
  if [ -d "$OUT/$p/run" ]; then
    gzip -f "$OUT/$p/run/results.csv" 2>/dev/null
    (cd "$OUT/$p/run" && set -- c[0-9]*.r[0-9]*.* && [ -e "$1" ] && tar -czf ../groups.tar.gz "$@" && rm -f "$@")
  fi
  say "$p: done, exit $rc, $t s, $ev new amdgpu fault/reset line(s)"
  echo "{\"part\": \"$p\", \"rc\": $rc, \"seconds\": $t, \"jobs\": $J, \"amdgpu_events\": $ev, \"quick\": ${GFX_QUICK:-0}}" >> "$OUT/parts.jsonl"
done
dmesg 2>/dev/null | grep -iE 'amdgpu' | tail -n 200 > "$OUT/dmesg-amdgpu.txt"
echo "amdgpu events after: $(gpu_events)" >> "$OUT/facts.txt"
say "finished"
