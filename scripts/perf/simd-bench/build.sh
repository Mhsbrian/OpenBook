#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build simd-bench (ANAL-380, docs/arm-performance.md) for arm64 and x86_64 with the compat harness's NDK r30, from
# one source, then check from the disassembly that every baseline kernel uses vector instructions on both
# (check-isa.py). Re-executes itself inside the anybook-ndk container, as scripts/compat/build-probes.sh does.
#
# Output: ~/anybook/perf/simd-bench/
#   simd-bench-arm64, simd-bench-x86_64                  PIE executables, API 30: what runs on the device
#   simd-bench-arm64-static, simd-bench-x86_64-static    static: for checking results on the build host
#   isa.json                                             check-isa.py's report; SHA256SUMS, TOOLCHAIN
set -euo pipefail
if [ -z "${ANYBOOK_IN_CONTAINER:-}" ]; then
  REPO=$(cd "$(dirname "$0")/../../.." && pwd); A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
  "$REPO/scripts/compat/setup-toolchain.sh"
  mkdir -p "$A/perf"
  exec docker run --rm -u "$(id -u):$(id -g)" -e ANYBOOK_IN_CONTAINER=1 -e HOME=/tmp \
    -v "$REPO:/r:ro" -v "$A/compat/sdk:/sdk:ro" -v "$A/perf:/p" anybook-ndk /r/scripts/perf/simd-bench/build.sh "$@"
fi
TC=/sdk/ndk/toolchains/llvm/prebuilt/linux-x86_64
SRC=/r/scripts/perf/simd-bench
OUT=/p/simd-bench
API=30
rm -rf "$OUT"; mkdir -p "$OUT"
# -ffp-contract=off: a multiply and an add stay two operations on both (arm64 would otherwise fuse them), so the float
# results are bit-identical. -fno-fast-math keeps IEEE semantics.
CF="-O2 -ffp-contract=off -fno-fast-math -Wall -Wextra -Werror"
for abi in arm64 x86_64; do
  case $abi in
    arm64)  T=aarch64-linux-android ;;
    x86_64) T=x86_64-linux-android ;;
  esac
  CC="$TC/bin/clang --target=$T$API"
  $CC $CF -fPIE -pie -o "$OUT/simd-bench-$abi" "$SRC/simd_bench.c"
  $CC $CF -static -o "$OUT/simd-bench-$abi-static" "$SRC/simd_bench.c"
done
"$TC/bin/clang" --version | head -1 > "$OUT/TOOLCHAIN"
sed -n 's/^Pkg.Revision = /NDK /p' /sdk/ndk/source.properties >> "$OUT/TOOLCHAIN"
echo "flags: $CF, API $API" >> "$OUT/TOOLCHAIN"
python3 "$SRC/check-isa.py" --objdump "$TC/bin/llvm-objdump" "$OUT/simd-bench-arm64" "$OUT/simd-bench-x86_64" \
  > "$OUT/isa.json"
( cd "$OUT" && sha256sum simd-bench-* isa.json TOOLCHAIN > SHA256SUMS )
cat "$OUT/isa.json"
