#!/usr/bin/env bash
# Run an AnyBook image's own AMD graphics binaries (bionic, Mesa RADV/radeonsi, minigbm amdgpu) on
# this host's AMD GPU: scripts/amd-android-hwtest.c, built with the NDK, started in a container whose
# /system, /vendor and /apex/com.android.runtime are the image's staged output. Only the AMD render
# node is passed in. No root, no Android framework: this checks the drivers, not the HAL plumbing.
#
#   scripts/amd-android-hwtest.sh [PRODUCT_OUT] [OUT_DIR] [PART ...]
# Default PRODUCT_OUT: ~/anybook/aosp/src/out/target/product/anybook_g14. PARTs: vulkan gles gralloc
# swapchain (default: all).
# Env: AMD_RENDER_NODE (default: the first render node bound to amdgpu), API (default 37),
#      MESA_OUT: a scripts/mesa-android-build.sh output (e.g. ~/anybook/mesa/out/upstream/vendor) whose
#        libraries replace the image's Mesa for this run, to test a Mesa change before it is in an image.
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd); A=${ANYBOOK_HOME:-$HOME/anybook}; API=${API:-37}
P=${1:-$A/aosp/src/out/target/product/anybook_g14}
OUT=${2:-$A/logs/graphics-amd/hwtest-$(date -u +%Y%m%dT%H%M%SZ)}
shift $(( $# < 2 ? $# : 2 ))
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
  -I/aosp/external/mesa3d/include/android_stub -I/aosp/frameworks/native/vulkan/include \
  -I/aosp/external/minigbm -I/aosp/external/libdrm/include/drm \
  /repo/scripts/amd-android-hwtest.c -ldl -o /b/amd-android-hwtest

# The image's /vendor as a reflinked copy, so this run can change it:
# - no property service here, so libhardware looks for hw/gralloc.default.so where the device reads
#   ro.hardware.gralloc=minigbm: point that name at minigbm's module (same file, so the same driver
#   instance as the test's own gralloc calls, as on the device);
# - MESA_OUT's libraries over the image's.
V=$B/vendor
rm -rf "$V"; cp -a --reflink=auto "$P/vendor" "$V"
ln -sf gralloc.minigbm.so "$V/lib64/hw/gralloc.default.so"
if [[ -n ${MESA_OUT:-} ]]; then
  (cd "$MESA_OUT" && find lib64 -name '*.so' ! -name libdrm.so) | while read -r f; do cp "$MESA_OUT/$f" "$V/$f"; done
fi

{ echo "image: $P"; cat "$P/system/build.prop" 2>/dev/null | grep -E '^ro.build.(fingerprint|id)='
  sed -n '1,4p' "$T/vendor/anybook/mesa/PROVENANCE.txt"
  [[ -n ${MESA_OUT:-} ]] && { echo "MESA_OUT: $MESA_OUT"; sed -n '1,8p' "$MESA_OUT/../../../evidence/$(basename "$(dirname "$MESA_OUT")")/versions.txt" 2>/dev/null; }
  for f in hw/vulkan.radv.so libgallium_dri.so; do
    echo "$f: $(file -L "$V/lib64/$f" | grep -o 'BuildID\[sha1\]=[0-9a-f]*')"; done
  echo "node: $NODE ($(tr '\n' ' ' < "/sys/class/drm/$(basename "$NODE")/device/uevent"))"; uname -r; } > "$OUT/versions.txt"
# The image's own dynamic linker and bionic (from the runtime APEX's unstripped copies), its /system
# and /vendor libraries. No /dev/__properties__: bionic then reads every property as unset.
set +e
docker run --rm -u "$(id -u):$(id -g)" --device "$NODE" --group-add "$(stat -c %g "$NODE")" \
  -v "$P/system:/system:ro" -v "$V:/vendor:ro" \
  -v "$P/symbols/apex/com.android.runtime:/apex/com.android.runtime:ro" -v "$B:/t:ro" \
  -e HOME=/tmp -e TMPDIR=/tmp alpine:3.21 /t/amd-android-hwtest "$NODE" /vendor/lib64 "$@" 2>&1 | tee "$OUT/hwtest.log"
rc=${PIPESTATUS[0]}
set -e
echo "amd-android-hwtest: rc=$rc, log in $OUT"
exit "$rc"
