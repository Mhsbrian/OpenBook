#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build mman-bench (ANAL-379, docs/arm-performance.md) for arm64 and x86_64 with the compat harness's NDK, from one
# source, in the same container as simd-bench.
#
# Output: ~/anybook/perf/mman-bench/
#   mman-bench-arm64, mman-bench-x86_64                  PIE executables, API 30: what runs on the device
#   mman-bench-arm64-static, mman-bench-x86_64-static    static: for checking results on the build host
set -euo pipefail
if [ -z "${ANYBOOK_IN_CONTAINER:-}" ]; then
  REPO=$(cd "$(dirname "$0")/../../.." && pwd); A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
  "$REPO/scripts/compat/setup-toolchain.sh"
  mkdir -p "$A/perf"
  exec docker run --rm -u "$(id -u):$(id -g)" -e ANYBOOK_IN_CONTAINER=1 -e HOME=/tmp \
    -v "$REPO:/r:ro" -v "$A/compat/sdk:/sdk:ro" -v "$A/perf:/p" anybook-ndk /r/scripts/perf/mman-bench/build.sh "$@"
fi
TC=/sdk/ndk/toolchains/llvm/prebuilt/linux-x86_64
SRC=/r/scripts/perf/mman-bench
OUT=/p/mman-bench
API=30
rm -rf "$OUT"; mkdir -p "$OUT"
CF="-O2 -Wall -Wextra -Werror"
for abi in arm64 x86_64; do
  case $abi in
    arm64)  T=aarch64-linux-android ;;
    x86_64) T=x86_64-linux-android ;;
  esac
  CC="$TC/bin/clang --target=$T$API"
  $CC $CF -fPIE -pie -o "$OUT/mman-bench-$abi" "$SRC/mman_bench.c"
  $CC $CF -static -o "$OUT/mman-bench-$abi-static" "$SRC/mman_bench.c"
done
"$TC/bin/clang" --version | head -1 > "$OUT/TOOLCHAIN"
sed -n 's/^Pkg.Revision = /NDK /p' /sdk/ndk/source.properties >> "$OUT/TOOLCHAIN"
echo "flags: $CF, API $API" >> "$OUT/TOOLCHAIN"
( cd "$OUT" && sha256sum mman-bench-* TOOLCHAIN > SHA256SUMS )
cat "$OUT/SHA256SUMS"
