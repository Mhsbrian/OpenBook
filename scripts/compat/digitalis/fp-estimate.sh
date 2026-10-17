#!/usr/bin/env bash
# FRECPE / FRSQRTE / URECPE / URSQRTE bit-exactness, end to end (ANAL-200). The reference is QEMU's implementation
# of the Arm pseudocode (qemu-aarch64 -cpu max on the host); the device is an arm64 static executable run through
# the native bridge's binfmt_misc runner, once per translation mode, so every tier is compared with it.
#   fp-estimate.sh build                 NDK r30: estimates-arm64 and golden-arm64 (static); host clang: check
#   fp-estimate.sh reference             estimates under QEMU -> reference.txt (no FP16), reference-fp16.txt
#   fp-estimate.sh header [BT_SRC]       check guest_fp_estimate_arm64.h against reference-fp16.txt
#   fp-estimate.sh device [-o DIR]       push and run on the compat device (COMPAT_TARGET=cf: our Cuttlefish build)
#                                        under BERBERIS_MODE two-gear, lite-translate-or-interpret, interpret-only;
#                                        diff each against reference.txt; DIR gets the summary and the diffs
#   fp-estimate.sh golden                print the probe's golden table (scripts/compat/probe/jni/probe.cpp)
# Outputs in ~/anybook/compat/out/fp-estimate/. BT_SRC: the patched binary_translation project (default: the AOSP
# tree's, after scripts/aosp-patches.sh).
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}
O=$A/compat/out/fp-estimate; S=$REPO/scripts/compat/digitalis/fp-estimate
TC=$A/compat/sdk/ndk/toolchains/llvm/prebuilt/linux-x86_64/bin
QEMU=${QEMU_AARCH64:-qemu-aarch64-static}
NRAND=${FPEST_RANDOM:-2000}
mkdir -p "$O"

case ${1:-} in
build)
  [ -x "$TC/clang" ] || "$REPO/scripts/compat/setup-toolchain.sh"
  "$TC/clang" --target=aarch64-linux-android30 -O2 -static -march=armv8-a -o "$O/estimates-arm64" "$S/estimates.c"
  "$TC/clang" --target=aarch64-linux-android30 -O1 -static -march=armv8-a -o "$O/golden-arm64" "$S/golden.c"
  BT=${2:-$A/aosp/src/frameworks/libs/binary_translation}
  clang++ -std=c++20 -O2 -Wall -Wextra -I "$BT/guest_state/arm64/include" -o "$O/check" "$S/check.cc"
  ( cd "$O" && sha256sum estimates-arm64 golden-arm64 check ) ;;
reference)
  "$QEMU" --version | head -1 | tee "$O/reference-qemu.txt"
  "$QEMU" -cpu max "$O/estimates-arm64" "$NRAND" 1 0 > "$O/reference.txt"
  "$QEMU" -cpu max "$O/estimates-arm64" "$NRAND" 1 1 > "$O/reference-fp16.txt"
  wc -l "$O/reference.txt" "$O/reference-fp16.txt" ;;
header)
  [ -n "${2:-}" ] && "$0" build "$2" >/dev/null
  "$O/check" < "$O/reference-fp16.txt" ;;
device)
  OUT=; [ "${2:-}" = -o ] && OUT=$3
  if [ "${COMPAT_TARGET:-emulator}" = cf ]; then EMU=$REPO/scripts/compat/cf.sh; else EMU=$REPO/scripts/compat/emulator.sh; fi
  ADB="$A/android-sdk/platform-tools/adb -s $("$EMU" serial)"
  [ -s "$O/reference.txt" ] || { echo "run '$0 reference' first" >&2; exit 2; }
  D=/data/local/tmp/fp-estimate
  $ADB shell "rm -rf $D; mkdir -p $D" </dev/null
  $ADB push "$O/estimates-arm64" "$D/" >/dev/null </dev/null
  $ADB shell "chmod 755 $D/estimates-arm64" </dev/null
  rc=0; SUM=$O/device-summary.txt
  { echo "device: $($ADB shell getprop ro.build.fingerprint </dev/null | tr -d '\r') bridge=$($ADB shell getprop ro.dalvik.vm.native.bridge </dev/null | tr -d '\r')"
    echo "reference: $(cat "$O/reference-qemu.txt"), $(wc -l < "$O/reference.txt") lines, $NRAND random inputs per form"; } > "$SUM"
  for mode in two-gear lite-translate-or-interpret interpret-only; do
    # 50 iterations per input: the JIT tiers translate the loop body before the recorded run.
    $ADB shell "BERBERIS_MODE=$mode $D/estimates-arm64 $NRAND 50 0" > "$O/device-$mode.txt" 2>"$O/device-$mode.err" </dev/null || true
    n=$(wc -l < "$O/device-$mode.txt")
    d=$(diff "$O/reference.txt" "$O/device-$mode.txt" | grep -c '^>' || true)
    echo "$mode: $n lines, $d differ from the reference" | tee -a "$SUM"
    diff "$O/reference.txt" "$O/device-$mode.txt" | head -200 > "$O/device-$mode.diff" || true
    awk '{print $1}' "$O/device-$mode.txt" | sort | uniq -c | sed 's/^/    /' >> "$SUM"
    if [ "$d" != 0 ] || [ "$n" != "$(wc -l < "$O/reference.txt")" ]; then
      rc=1
      # per-op mismatch counts
      diff <(cat -n "$O/reference.txt") <(cat -n "$O/device-$mode.txt") | grep '^>' | awk '{print $3}' | sort | uniq -c |
        sed 's/^/    mismatches: /' >> "$SUM"
    fi
  done
  cat "$SUM"
  if [ -n "$OUT" ]; then mkdir -p "$OUT"; cp "$SUM" "$O"/device-*.diff "$O/reference-qemu.txt" "$OUT/"; fi
  exit "$rc" ;;
golden) "$QEMU" -cpu max "$O/golden-arm64" ;;
*) sed -n '2,13p' "$0"; exit 2 ;;
esac
