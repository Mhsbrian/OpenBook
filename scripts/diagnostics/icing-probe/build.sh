#!/usr/bin/env bash
# Build the ANAL-234 hardware probes with NDK r30 in the anybook-ndk container:
#   icing_probe              arm64 PIE, RUNPATH $ORIGIN/guest, runs an app's libicing.so through a JNI shim;
#                            it links libm/liblog/libz/libc++ so they load from guest/ before libc starts
#   coremark-arm64           unmodified CoreMark (as scripts/compat/build-probes.sh), RUNPATH $ORIGIN/guest
#   coremark-x86_64          the same benchmark as the native control
#   bridge_check-arm64       device/anybook/common/native-bridge/check, static
#   dg_launch                x86_64, starts an arm64 executable through Digitalis with explicit guest paths
#   icing-input.bin          synthetic schema, documents and queries (icing-probe.py inputs)
# RUNPATH lets each translator use the guest libraries copied beside the binary instead of
# whatever /system/lib64/arm64 holds. Usage: build.sh OUT_DIR (must not exist).
set -euo pipefail
if [ -z "${ANYBOOK_IN_CONTAINER:-}" ]; then
  [ $# -eq 1 ] || { echo "usage: $0 OUT_DIR" >&2; exit 2; }
  [ ! -e "$1" ] || { echo "$1 exists" >&2; exit 2; }
  REPO=$(cd "$(dirname "$0")/../../.." && pwd); A=${ANYBOOK_HOME:-$HOME/anybook}
  "$REPO/scripts/compat/setup-toolchain.sh" >/dev/null
  mkdir -p "$1"; OUT=$(cd "$1" && pwd)
  docker run --rm -u "$(id -u):$(id -g)" -e ANYBOOK_IN_CONTAINER=1 -e HOME=/tmp \
    -v "$REPO:/r:ro" -v "$A/compat:/c:ro" -v "$OUT:/o" anybook-ndk /r/scripts/diagnostics/icing-probe/build.sh
  python3 "$REPO/scripts/diagnostics/icing-probe/icing-probe.py" inputs "$OUT/icing-input.bin"
  (cd "$OUT" && sha256sum icing_probe coremark-arm64 coremark-x86_64 bridge_check-arm64 dg_launch icing-input.bin > SHA256SUMS)
  cat "$OUT/SHA256SUMS"
  exit 0
fi
TC=/c/sdk/ndk/toolchains/llvm/prebuilt/linux-x86_64; CM=/c/src/coremark; API=30
CM_SRCS="$CM/core_list_join.c $CM/core_main.c $CM/core_matrix.c $CM/core_state.c $CM/core_util.c $CM/posix/core_portme.c"
RP='-Wl,--enable-new-dtags,-rpath,$ORIGIN/guest'
A64="$TC/bin/clang --target=aarch64-linux-android$API"
X64="$TC/bin/clang --target=x86_64-linux-android$API"
# The platform libc++.so is not in the NDK; link a stub with its soname to record the dependency.
mkdir -p /tmp/stub && echo > /tmp/stub/empty.c
$A64 -shared -nostdlib -Wl,-soname,libc++.so -o /tmp/stub/libc++.so /tmp/stub/empty.c
$A64 -O2 -Wall -Wextra -Werror -o /o/icing_probe /r/scripts/diagnostics/icing-probe/icing_probe.c \
  -Wl,--no-as-needed -ldl -lm -llog -lz -L/tmp/stub -lc++ -Wl,--as-needed "$RP"
$A64 -O2 -o /o/coremark-arm64 -I"$CM" -I"$CM/posix" -DPERFORMANCE_RUN=1 \
  -DFLAGS_STR="\"-O2  (NDK r30 clang, aarch64-linux-android$API)\"" $CM_SRCS "$RP"
$X64 -O2 -mcx16 -o /o/coremark-x86_64 -I"$CM" -I"$CM/posix" -DPERFORMANCE_RUN=1 \
  -DFLAGS_STR="\"-O2 -mcx16 (NDK r30 clang, x86_64-linux-android$API)\"" $CM_SRCS
$A64 -O2 -static -o /o/bridge_check-arm64 /r/device/anybook/common/native-bridge/check/bridge_check.c
$X64 -O2 -Wall -Wextra -Werror -o /o/dg_launch /r/scripts/diagnostics/icing-probe/dg_launch.c -ldl
"$TC/bin/clang" --version | head -1 > /o/TOOLCHAIN
