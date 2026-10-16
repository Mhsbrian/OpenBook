#!/usr/bin/env bash
# ARM-only APK compatibility matrix on the AOSP Desktop (Preview) 37.0 x86_64 emulator, whose native
# bridge is libndk_translation (ANAL-180), or Digitalis after scripts/compat/digitalis/install.sh (ANAL-181).
# For each APK: install, launch, wait, check the process is alive, count Java/native crashes, ANRs and
# tombstones, take a screenshot, write a CSV row.
#
#   run-matrix.sh [-o OUTDIR] [-w WAIT_S] [-f REGEX] [--fresh] [--keep-emulator] [--keep-apps]
#     -o   output dir (default <repo>/evidence/<date>-compat/run-<time>); if it already holds a
#          results.csv the run resumes: finished APKs are skipped and new rows are appended
#     -w   seconds to wait after launch (default 15)
#     -f   only APK ids matching this regex (ids: probe-arm64, org.videolan.vlc@arm64-v8a, ...)
#     --fresh          stop our emulator and cold-boot it with wiped data first
#     --keep-emulator  leave the emulator running at the end (default: stop it if this run started it)
#
# Inputs: probe APKs from build-probes.sh, F-Droid APKs from fetch-corpus.sh (scripts/compat/corpus/fdroid.tsv).
# Outputs: results.csv, probe-results.csv, screens/<id>.png, logs/<id>.logcat.gz, env.txt, summary.txt.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}
ADB="$A/android-sdk/platform-tools/adb -s emulator-5580"
AAPT2=$A/compat/sdk/build-tools/37.0.0/aapt2
EMU=$REPO/scripts/compat/emulator.sh
WAIT=15; FILTER=.; FRESH=0; KEEP_EMU=0; KEEP_APPS=0; OUT=
while [ $# -gt 0 ]; do
  case $1 in
    -o) OUT=$2; shift ;; -w) WAIT=$2; shift ;; -f) FILTER=$2; shift ;;
    --fresh) FRESH=1 ;; --keep-emulator) KEEP_EMU=1 ;; --keep-apps) KEEP_APPS=1 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac; shift
done
RUN_ID=$(date +%Y%m%d-%H%M%S)
OUT=${OUT:-$REPO/evidence/$(date +%F)-compat/run-$RUN_ID}
RESUME=0
if [ -f "$OUT/results.csv" ]; then RESUME=1; R=$(sed -n 2p "$OUT/results.csv" | cut -d, -f1); RUN_ID=${R:-$RUN_ID}; fi
mkdir -p "$OUT/screens" "$OUT/logs"
[ -x "$AAPT2" ] || { echo "run scripts/compat/setup-toolchain.sh first" >&2; exit 2; }

# ---- emulator (this harness owns AVD anybook-desktop on port 5580) ----
booted(){ [ "$($ADB shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; }
STARTED=0
[ $FRESH = 1 ] && "$EMU" down
if booted; then "$EMU" up; else "$EMU" up --wipe; STARTED=1; fi
trap '[ $STARTED = 1 ] && [ $KEEP_EMU = 0 ] && "$EMU" down' EXIT

# ---- corpus: id|kind|role|apk ----
mkdir -p "$A/compat/run"; LIST=$A/compat/run/corpus-$RUN_ID.txt; : > "$LIST"
for s in arm64 armv7 x86_64; do
  f=$A/compat/out/probes/anybook-probe-$s.apk
  [ -f "$f" ] || { echo "missing $f: run scripts/compat/build-probes.sh" >&2; exit 2; }
  role=$([ $s = x86_64 ] && echo x86_64-control || echo $s-only)
  echo "probe-$s|probe|$role|$f" >> "$LIST"
done
grep -v '^#' "$REPO/scripts/compat/corpus/fdroid.tsv" | tail -n +2 | while IFS=$'\t' read -r pkg _ role abi _ _ apk _; do
  f=$A/compat/apks/fdroid/$apk
  [ -f "$f" ] || { echo "missing $f: run scripts/compat/fetch-corpus.sh" >&2; exit 2; }
  echo "$pkg@$abi|fdroid|$role|$f" >> "$LIST"
done
grep -E "^[^|]*($FILTER)" "$LIST" > "$LIST.sel" || { echo "no APK matches $FILTER" >&2; exit 2; }

# ---- environment record ----
[ $RESUME = 1 ] && echo "resumed $(date -Is)" >> "$OUT/env.txt"
[ $RESUME = 1 ] || {
  echo "run_id=$RUN_ID date=$(date -Is) wait_s=$WAIT harness=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null)$(git -C "$REPO" status --porcelain -- scripts/compat tools 2>/dev/null | grep -q . && echo -dirty)"
  echo "host: $(uname -sr) / $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs) / load $(cut -d' ' -f1-3 /proc/loadavg)"
  echo "emulator: $("$A/android-sdk/emulator/emulator" -version 2>/dev/null | head -1)"
  $ADB shell 'echo "guest: $(getprop ro.build.fingerprint)"; echo "abilist: $(getprop ro.product.cpu.abilist) abilist32=[$(getprop ro.product.cpu.abilist32)]";
    echo "native_bridge: $(getprop ro.dalvik.vm.native.bridge) exec=$(getprop ro.enable.native.bridge.exec)";
    echo "gpu: egl=$(getprop ro.hardware.egl) vulkan=$(getprop ro.hardware.vulkan) gltransport=$(getprop ro.boot.hardware.gltransport)";
    echo "kernel: $(uname -r) cpus=$(nproc)"' | tr -d '\r'
} > "$OUT/env.txt"
cat "$OUT/env.txt"
NB_LIB=$($ADB shell getprop ro.dalvik.vm.native.bridge | tr -d '\r')  # "native_bridge" column: is it mapped?
NB_LIB=${NB_LIB:-no-native-bridge}

san(){ printf '%s' "$*" | tr -d '\r"' | tr ',\n\t' ';  ' | cut -c1-240; }
COLS=run_id,id,kind,role,package,version,apk_abis,apk_sha256,install,install_ms,primary_abi,launch,launch_ms,alive,procs,native_bridge,foreground,java_crashes,native_crashes,anrs,tombstones,probe_pass,probe_fail,probe_skip,verdict,crash_signature,screenshot
[ -f "$OUT/results.csv" ] || echo "$COLS" > "$OUT/results.csv"
[ -f "$OUT/probe-results.csv" ] || echo "run_id,id,test,status,detail" > "$OUT/probe-results.csv"
SCALE=$(command -v magick >/dev/null && echo 1 || echo 0)

test_apk(){  # id kind role apk
  set +e  # most probes below legitimately return non-zero (grep -c 0, pidof on a dead app)
  local id=$1 kind=$2 role=$3 apk=$4
  local pkg ver abis sha inst inst_ms pabi launch launch_ms comp alive procs nb fg jc nc anr tomb pp pf ps verdict sig shot
  pkg=$($AAPT2 dump packagename "$apk" 2>/dev/null | tr -d '\r')
  local badging; badging=$($AAPT2 dump badging "$apk" 2>/dev/null || true)
  ver=$(sed -n "s/^package: .* versionName='\([^']*\)'.*/\1/p" <<< "$badging")
  abis=$(sed -n "s/^native-code: //p" <<< "$badging" | tr -d "'" | tr ' ' '+')
  sha=$(sha256sum "$apk" | cut -c1-16)
  echo "== $id ($pkg $ver, $abis)"
  $ADB uninstall "$pkg" >/dev/null 2>&1 || true
  $ADB shell 'input keyevent KEYCODE_HOME; touch /data/local/tmp/anybook-mark' >/dev/null 2>&1 || true
  $ADB logcat -b all -c >/dev/null 2>&1 || true
  local t0; t0=$(date +%s%N)
  local out; out=$(timeout 300 $ADB install -r -g "$apk" 2>&1 || true)
  inst_ms=$(( ($(date +%s%N) - t0) / 1000000 ))
  if grep -q '^Success' <<< "$out"; then inst=ok; else inst=$(grep -oE 'INSTALL_[A-Z_]+' <<< "$out" | head -1); inst=${inst:-$(grep -oE 'Failure \[[^]]*\]' <<< "$out" | head -1)}; inst=${inst:-fail}; fi
  pabi=-; launch=-; launch_ms=-; alive=-; procs=0; nb=-; fg=-; jc=0; nc=0; anr=0; tomb=0; pp=-; pf=-; ps=-; sig=; shot=-
  if [ "$inst" = ok ]; then
    pabi=$($ADB shell dumpsys package "$pkg" | grep -m1 -o 'primaryCpuAbi=[^ ]*' | cut -d= -f2 | tr -d '\r')
    # first launcher activity (resolve-activity returns the chooser when an app has two launchers)
    comp=$($ADB shell cmd package query-activities --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER "$pkg" | tr -d '\r' | grep -m1 -oE "^ *$pkg/[^ ]+" | tr -d ' ')
    if [[ $comp == */* ]]; then
      out=$(timeout 90 $ADB shell am start -W -n "$comp" 2>&1 | tr -d '\r' || true)
      launch=$(sed -n 's/^Status: //p' <<< "$out"); launch=${launch:-$(grep -m1 -oE 'Error.*' <<< "$out" | cut -c1-60)}
      launch_ms=$(sed -n 's/^TotalTime: //p' <<< "$out"); launch_ms=${launch_ms:--}
    else
      launch=no-launcher-activity
    fi
    sleep "$WAIT"
    if [ "$kind" = probe ]; then  # our own probes report when they finish; give slow runs up to 45 s more
      for _ in $(seq 1 15); do $ADB logcat -d -s AnyBookProbe:I | grep -q PROBE_DONE && break; sleep 3; done
    fi
    local pid; pid=$($ADB shell pidof "$pkg" 2>/dev/null | tr -d '\r' | awk '{print $1}')
    alive=$([ -n "$pid" ] && echo yes || echo no)
    procs=$($ADB shell ps -A -o NAME 2>/dev/null | tr -d '\r' | grep -c "^$pkg\(:\|$\)" || true)
    if [ -n "$pid" ]; then
      nb=$($ADB shell "grep -c ${NB_LIB%.so} /proc/$pid/maps" 2>/dev/null | tr -d '\r')
      nb=$([ "${nb:-0}" -gt 0 ] && echo yes || echo no)
    fi
    fg=$($ADB shell dumpsys activity activities 2>/dev/null | grep -E 'topResumedActivity|mResumedActivity|ResumedActivity:' | grep -q "$pkg" && echo yes || echo no)
    $ADB exec-out screencap -p > "$OUT/screens/$id.png" 2>/dev/null || true
    if [ -s "$OUT/screens/$id.png" ]; then
      [ "$SCALE" = 1 ] && magick "$OUT/screens/$id.png" -resize 50% -colors 128 "PNG8:$OUT/screens/$id.png"  # ~60 KB each
      shot=screens/$id.png
    fi
  fi
  $ADB logcat -d -b main,system,crash -v threadtime > "$OUT/logs/$id.logcat" 2>/dev/null || true
  local L=$OUT/logs/$id.logcat
  jc=$(grep -c "AndroidRuntime: Process: $pkg\(:\|,\)" "$L" || true)
  nc=$(grep -c ">>> $pkg\(:[^ ]*\)\? <<<" "$L" || true)
  anr=$(grep -c "ANR in $pkg" "$L" || true)
  tomb=$($ADB shell "find /data/tombstones -type f -newer /data/local/tmp/anybook-mark ! -name '*.pb' 2>/dev/null | wc -l" 2>/dev/null | tr -d '\r')
  # native crash: signal line of the tombstone (the "Fatal signal" line truncates the process name)
  sig=$(grep -A4 ">>> $pkg\(:[^ ]*\)\? <<<" "$L" | grep -m1 -oE 'signal [0-9]+ \([A-Z]+\), code -?[0-9]+ \([A-Z_]+\)')
  [ -z "$sig" ] && sig=$(grep -A80 "AndroidRuntime: Process: $pkg" "$L" | grep 'AndroidRuntime: Caused by: ' | tail -1 | sed 's/.*Caused by: //')
  [ -z "$sig" ] && sig=$(grep -A2 "AndroidRuntime: Process: $pkg" "$L" | grep -m1 -oE 'AndroidRuntime: [a-zA-Z0-9_.$]+(Exception|Error)[^ ]*.*' | sed 's/AndroidRuntime: //')
  [ -z "$sig" ] && [ "$anr" -gt 0 ] && sig=$(grep -m1 -A1 "ANR in $pkg" "$L" | tail -1 | sed 's/.*Reason: /ANR: /')
  local PR=$OUT/.probe-rows; : > "$PR"
  if [ "$kind" = probe ] && [ "$inst" = ok ]; then
    grep -E 'AnyBookProbe: PROBE_RESULT ' "$L" | sed 's/.*PROBE_RESULT //' | while read -r t st rest; do
      echo "$RUN_ID,$id,$t,$st,$(san "$rest")" >> "$PR"
    done
    local done_line; done_line=$(grep -m1 -oE 'PROBE_DONE pass=[0-9]+ fail=[0-9]+ skip=[0-9]+' "$L" || true)
    if [ -n "$done_line" ]; then
      pp=$(sed 's/.*pass=\([0-9]*\).*/\1/' <<< "$done_line"); pf=$(sed 's/.*fail=\([0-9]*\).*/\1/' <<< "$done_line")
      ps=$(sed 's/.*skip=\([0-9]*\).*/\1/' <<< "$done_line")
    else
      pf="incomplete:$(grep -oE 'PROBE_BEGIN [a-z_0-9]+' "$L" | tail -1 | cut -d' ' -f2)"
    fi
  fi
  gzip -f "$L"
  if [ "$inst" != ok ]; then verdict=INSTALL_FAIL
  elif [[ $launch != ok ]]; then verdict=LAUNCH_FAIL
  elif [ "$alive" = no ] && [ $((jc + nc)) -gt 0 ]; then verdict=CRASH
  elif [ "$alive" = no ]; then verdict=EXITED
  elif [ "$anr" -gt 0 ]; then verdict=ANR
  elif [ $((jc + nc)) -gt 0 ]; then verdict=RUNS_WITH_CRASH
  else verdict=RUNS; fi
  echo "   install=$inst abi=$pabi launch=$launch alive=$alive nb=$nb fg=$fg java=$jc native=$nc anr=$anr tomb=$tomb probe=$pp/$pf/$ps -> $verdict"
  cat "$PR" >> "$OUT/probe-results.csv"; rm -f "$PR"
  echo "$RUN_ID,$id,$kind,$role,$pkg,$(san "$ver"),$abis,$sha,$(san "$inst"),$inst_ms,$pabi,$(san "$launch"),$launch_ms,$alive,$procs,$nb,$fg,$jc,$nc,$anr,${tomb:-n/a},$pp,$pf,$ps,$verdict,$(san "$sig"),$shot" >> "$OUT/results.csv"
  $ADB shell "am force-stop $pkg; am broadcast -a android.intent.action.CLOSE_SYSTEM_DIALOGS; input keyevent KEYCODE_HOME" >/dev/null 2>&1 || true
  [ $KEEP_APPS = 1 ] || $ADB uninstall "$pkg" >/dev/null 2>&1
  set -e
}

# fd 3 so that adb cannot swallow the list from stdin
while IFS='|' read -r id kind role apk <&3; do
  awk -F, -v r="$RUN_ID" -v i="$id" '$1 == r && $2 == i {f = 1} END {exit !f}' "$OUT/results.csv" && continue  # done earlier
  test_apk "$id" "$kind" "$role" "$apk" < /dev/null
done 3< "$LIST.sel"

{
  echo "run $RUN_ID: $(($(wc -l < "$OUT/results.csv") - 1)) APKs, wait ${WAIT}s"
  cut -d, -f4,25 "$OUT/results.csv" | tail -n +2 | sort | uniq -c | sed 's/^ */  /'
} | tee "$OUT/summary.txt"
echo "results: $OUT"
