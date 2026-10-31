#!/usr/bin/env bash
# Translated-vs-native CPU benchmark (ANAL-180). The same unmodified CoreMark source (EEMBC, posix port),
# built by build-probes.sh with NDK r30 clang -O2 for arm64-v8a and x86_64, runs in the same emulator:
#   exe   adb shell runs the executable; arm64 goes through the binfmt_misc runner of libndk_translation
#   apk   inside the probe app (System.loadLibrary path), arm64 through the app native bridge
#   host  the static x86_64 build on the host, outside the VM (shows VM overhead, not translation)
# Rounds are interleaved (x86_64, arm64, x86_64, arm64, ...) so host load drift hits both sides.
#   run-bench.sh [-o OUTDIR] [-n ROUNDS] [-i ITERATIONS] [--keep-emulator]
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}
# COMPAT_TARGET=cf: OpenBook's own Cuttlefish build (scripts/compat/cf.sh) instead of the emulator.
if [ "${COMPAT_TARGET:-emulator}" = cf ]; then EMU=$REPO/scripts/compat/cf.sh; else EMU=$REPO/scripts/compat/emulator.sh; fi
SERIAL=$("$EMU" serial 2>/dev/null || echo emulator-5580)
ADB="$A/android-sdk/platform-tools/adb -s $SERIAL"
P=$A/compat/out/probes
ROUNDS=3; ITER=600000; KEEP_EMU=0; OUT=
while [ $# -gt 0 ]; do
  case $1 in -o) OUT=$2; shift ;; -n) ROUNDS=$2; shift ;; -i) ITER=$2; shift ;; --keep-emulator) KEEP_EMU=1 ;;
    *) echo "unknown option $1" >&2; exit 2 ;; esac; shift
done
RUN_ID=$(date +%Y%m%d-%H%M%S)
OUT=${OUT:-$REPO/evidence/$(date +%F)-compat/bench-$RUN_ID}
mkdir -p "$OUT/raw"
[ -x "$P/bench/coremark-arm64" ] || { echo "run scripts/compat/build-probes.sh first" >&2; exit 2; }

booted(){ [ "$($ADB shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; }
STARTED=0
if booted; then "$EMU" up; else "$EMU" up --wipe; STARTED=1; fi
trap '[ $STARTED = 1 ] && [ $KEEP_EMU = 0 ] && "$EMU" down' EXIT

D=/data/local/tmp/anybook-bench
$ADB shell "rm -rf $D; mkdir -p $D" </dev/null
for s in x86_64 arm64 armv7; do $ADB push "$P/bench/coremark-$s" "$D/" >/dev/null </dev/null; done
$ADB shell "chmod 755 $D/*" </dev/null
for s in x86_64 arm64; do $ADB install -r -g "$P/anybook-probe-$s.apk" >/dev/null </dev/null; done
{
  echo "run_id=$RUN_ID date=$(date -Is) iterations=$ITER rounds=$ROUNDS"
  echo "host: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs), $(nproc) threads; other AnyBook runs share it"
  $ADB shell 'echo "guest: $(getprop ro.build.fingerprint) cpus=$(nproc) bridge=$(getprop ro.dalvik.vm.native.bridge)"' </dev/null | tr -d '\r'
  head -1 "$P/TOOLCHAIN"
  grep coremark "$P/SHA256SUMS"
} > "$OUT/env.txt"
cat "$OUT/env.txt"

echo "run_id,mode,abi,round,iterations,total_secs,iter_per_sec,valid,host_load1" > "$OUT/bench.csv"
row(){  # mode abi round file
  local f=$4 secs ips valid
  secs=$(sed -n 's/.*Total time (secs): *\([0-9.]*\).*/\1/p' "$f" | head -1)
  ips=$(sed -n 's/.*Iterations\/Sec *: *\([0-9.]*\).*/\1/p' "$f" | head -1)
  valid=$(grep -q 'Correct operation validated' "$f" && echo yes || echo no)
  echo "$RUN_ID,$1,$2,$3,$ITER,${secs:-},${ips:-},$valid,$(cut -d' ' -f1 /proc/loadavg)" >> "$OUT/bench.csv"
  echo "  $1 $2 round $3: ${ips:-?} it/s in ${secs:-?} s valid=$valid"
}
apk_run(){  # abi file
  local pkg=dev.anybook.probe.$1
  $ADB shell "am force-stop $pkg; logcat -c" </dev/null
  $ADB shell "am start -n $pkg/dev.anybook.probe.MainActivity --es mode bench --es arg '0x0 0x0 0x66 $ITER'" >/dev/null </dev/null
  for _ in $(seq 1 300); do
    sleep 3
    $ADB logcat -d -s AnyBookProbe:I </dev/null | grep -q 'PROBE_BENCH_DONE\|PROBE_BENCH_FAIL' && break
  done
  $ADB logcat -d -s AnyBookProbe:I </dev/null | grep -E 'PROBE_BENCH' | sed 's/.*PROBE_BENCH[_A-Z]* \{0,1\}//' > "$2"
  $ADB shell "am force-stop $pkg; input keyevent KEYCODE_HOME" </dev/null
}

for r in $(seq 1 "$ROUNDS"); do
  for s in x86_64 arm64; do
    abi=$([ $s = arm64 ] && echo arm64-v8a || echo x86_64)
    f=$OUT/raw/exe-$s-r$r.txt
    timeout 900 $ADB shell "$D/coremark-$s 0x0 0x0 0x66 $ITER" > "$f" 2>&1 </dev/null || true
    row exe "$abi" "$r" "$f"
    f=$OUT/raw/apk-$s-r$r.txt
    apk_run "$s" "$f"
    row apk "$abi" "$r" "$f"
  done
  f=$OUT/raw/host-x86_64-r$r.txt
  (cd /tmp && timeout 900 "$P/bench/coremark-x86_64-static" 0x0 0x0 0x66 "$ITER") > "$f" 2>&1 || true
  row host x86_64 "$r" "$f"
done
# 32-bit ARM: the image registers an arm binfmt handler, but its runner is not installed (64-bit-only image)
timeout 60 $ADB shell "$D/coremark-armv7 0x0 0x0 0x66 1000; echo exit=\$?" > "$OUT/raw/exe-armv7.txt" 2>&1 </dev/null || true

python3 -I - "$OUT" <<'EOF'
import csv, statistics, sys
out = sys.argv[1]
rows = [r for r in csv.DictReader(open(f"{out}/bench.csv")) if r["iter_per_sec"]]
def med(mode, abi):
    v = [float(r["iter_per_sec"]) for r in rows if r["mode"] == mode and r["abi"] == abi]
    return (statistics.median(v), min(v), max(v), len(v), all(r["valid"] == "yes" for r in rows if r["mode"] == mode and r["abi"] == abi)) if v else None
L = ["| mode | ABI | median it/s | min | max | n | valid |", "|---|---|---|---|---|---|---|"]
res = {}
for mode, abi in (("host", "x86_64"), ("exe", "x86_64"), ("exe", "arm64-v8a"), ("apk", "x86_64"), ("apk", "arm64-v8a")):
    m = med(mode, abi)
    if m:
        res[(mode, abi)] = m[0]
        L.append(f"| {mode} | {abi} | {m[0]:.0f} | {m[1]:.0f} | {m[2]:.0f} | {m[3]} | {'yes' if m[4] else 'NO'} |")
L.append("")
for mode in ("exe", "apk"):
    if (mode, "arm64-v8a") in res and (mode, "x86_64") in res:
        L.append(f"- **{mode}: translated arm64 / native x86_64 = {res[(mode,'arm64-v8a')] / res[(mode,'x86_64')]:.3f}** "
                 f"(arm64 runs at {100 * res[(mode,'arm64-v8a')] / res[(mode,'x86_64')]:.1f}% of native speed)")
if ("host", "x86_64") in res and ("exe", "x86_64") in res:
    L.append(f"- VM overhead: emulator x86_64 / host x86_64 = {res[('exe','x86_64')] / res[('host','x86_64')]:.3f}")
open(f"{out}/bench-summary.md", "w").write("\n".join(L) + "\n")
print("\n".join(L))
EOF
echo "results: $OUT"
