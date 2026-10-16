#!/usr/bin/env bash
# Run an AnyBook image's own AMD graphics binaries (bionic, Mesa RADV/radeonsi, minigbm amdgpu) on
# this host's AMD GPU: scripts/amd-android-hwtest.c, built with the NDK, started in a container whose
# /system, /vendor and /apex/com.android.runtime are the image's staged output. Only the AMD render
# node is passed in. No root, no Android framework: this checks the drivers, not the HAL plumbing.
#
#   scripts/amd-android-hwtest.sh [PRODUCT_OUT] [OUT_DIR]
# Default PRODUCT_OUT: ~/anybook/aosp/src/out/target/product/anybook_vsoc_x86_64.
# Env: AMD_RENDER_NODE (default: the first render node bound to amdgpu), API (default 37).
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd); A=${ANYBOOK_HOME:-$HOME/anybook}; API=${API:-37}
P=${1:-$A/aosp/src/out/target/product/anybook_vsoc_x86_64}
OUT=${2:-$A/logs/graphics-amd/hwtest-$(date -u +%Y%m%dT%H%M%SZ)}
T=$A/aosp/src; B=$A/graphics-amd/hwtest
mkdir -p "$OUT" "$B"
NODE=${AMD_RENDER_NODE:-}
if [[ -z $NODE ]]; then
  for n in /sys/class/drm/renderD*; do
    [[ $(basename "$(readlink -f "$n/device/driver")") == amdgpu ]] && { NODE=/dev/dri/$(basename "$n"); break; }
  done
fi
[[ -n $NODE ]] || { echo "no amdgpu render node" >&2; exit 2; }
for d in system vendor symbols/apex/com.android.runtime; do [[ -d $P/$d ]] || { echo "no $P/$d" >&2; exit 2; }; done

docker run --rm -u "$(id -u):$(id -g)" -v "$T:/aosp:ro" -v "$R:/repo:ro" -v "$B:/b" anybook-mesa-android \
  /opt/android-ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android$API-clang -O2 -Wall \
  -I/aosp/external/mesa3d/include/android_stub \
  -I/aosp/external/minigbm -I/aosp/external/libdrm/include/drm \
  /repo/scripts/amd-android-hwtest.c -ldl -o /b/amd-android-hwtest

{ echo "image: $P"; cat "$P/system/build.prop" 2>/dev/null | grep -E '^ro.build.(fingerprint|id)='
  sed -n '1,4p' "$T/vendor/anybook/mesa/PROVENANCE.txt"
  echo "node: $NODE ($(tr '\n' ' ' < "/sys/class/drm/$(basename "$NODE")/device/uevent"))"; uname -r; } > "$OUT/versions.txt"
# The image's own dynamic linker and bionic (from the runtime APEX's unstripped copies), its /system
# and /vendor libraries. No /dev/__properties__: bionic then reads every property as unset.
docker run --rm -u "$(id -u):$(id -g)" --device "$NODE" --group-add "$(stat -c %g "$NODE")" \
  -v "$P/system:/system:ro" -v "$P/vendor:/vendor:ro" \
  -v "$P/symbols/apex/com.android.runtime:/apex/com.android.runtime:ro" -v "$B:/t:ro" \
  -e HOME=/tmp -e TMPDIR=/tmp alpine:3.21 /t/amd-android-hwtest "$NODE" /vendor/lib64 2>&1 | tee "$OUT/hwtest.log"
rc=${PIPESTATUS[0]}
echo "amd-android-hwtest: rc=$rc, log in $OUT"
exit "$rc"
