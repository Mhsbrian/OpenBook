#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# ANAL-177 pre-check off the laptop: the graphics check's dEQP case lists, run by the same deqp-runner and the image's
# own deqp-binary64 against the image's own Mesa on this build host's AMD GPU (a Radeon 610M, gfx1036, RDNA2; NOT the
# G14's Radeon 890M). Like scripts/amd-android-hwtest.sh, the image's /system, /vendor and APEX libraries run in a
# container with only the AMD render node passed in: bionic and the drivers, no Android framework.
# What differs from the G14 run, because there is no property service here:
#   - Vulkan goes through libvk_hal_shim.so (scripts/graphics/vk-hal-shim.c), which opens RADV's HAL the way Android's
#     loader does, instead of through Android's libvulkan;
#   - GLES goes through Android's own libEGL, which finds radeonsi by its exact file name (egl/libEGL.so etc. are
#     symlinked to the _mesa libraries in this run's copy of /vendor) instead of through ro.hardware.egl;
#   - ANGLE cannot run here: it spins in user space right after loading (no system call for 25 s, 2026-10-17), so the
#     ANGLE passes, the EGL module (APK) and ANGLE end2end (APK) run on the G14 only.
#
# usage: pre-check.sh CASELIST_DIR [PART ...]     PARTs: vk vk14 gles-mesa (default: all three)
# Env: OUT (default <data dir>/logs/gfx-cts/precheck-<ts>), JOBS (default 12), PRODUCT_OUT (default the G14 product),
#      FRACTION (deqp-runner --fraction, default 1: every listed case), NONSTRICT (default <data dir>/mesa/out/
#      upstream-nonstrict/vendor/lib64/hw/vulkan.radv.so), AMD_RENDER_NODE.
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; G=$A/gfx-cts
CL=$(cd "${1:?usage: pre-check.sh CASELIST_DIR [PART ...]}" && pwd); shift
PARTS=("$@"); [ ${#PARTS[@]} -gt 0 ] || PARTS=(vk vk14 gles-mesa)
P=${PRODUCT_OUT:-$A/aosp/src/out/target/product/anybook_g14}
D=$P/data/nativetest64/deqp-binary
NS=${NONSTRICT:-$A/mesa/out/upstream-nonstrict/vendor/lib64/hw/vulkan.radv.so}
OUT=${OUT:-$A/logs/gfx-cts/precheck-$(date -u +%Y%m%dT%H%M%SZ)}; JOBS=${JOBS:-12}; FRACTION=${FRACTION:-1}
B=$G/precheck; mkdir -p "$OUT" "$B/bin"
for f in "$D/deqp-binary64" "$G/bin/deqp-runner" "$NS" "$CL/vk.txt"; do [ -e "$f" ] || { echo "missing: $f" >&2; exit 2; }; done
NODE=${AMD_RENDER_NODE:-}
if [ -z "$NODE" ]; then
  for n in /sys/class/drm/renderD*; do
    [ "$(basename "$(readlink -f "$n/device/driver")")" = amdgpu ] && { NODE=/dev/dri/$(basename "$n"); break; }
  done
fi
[ -n "$NODE" ] || { echo "no amdgpu render node" >&2; exit 2; }
exec > >(tee -a "$OUT/pre-check.log") 2>&1
echo "== pre-check.sh ${PARTS[*]} ($(date -u +%FT%TZ)), repo $(git -C "$R" rev-parse --short HEAD), jobs $JOBS, fraction $FRACTION"

# The NDK libraries (the Vulkan HAL shim; dEQP's console output to stdout, scripts/graphics/deqp-stdout.c) and this
# run's /vendor: a reflinked copy with the exact-name EGL links and gralloc.default.
docker run --rm -u "$(id -u):$(id -g)" -v "$A/aosp/src:/aosp:ro" -v "$R:/repo:ro" -v "$B/bin:/b" anybook-mesa-android \
  sh -c 'CC="/opt/android-ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android37-clang -shared -fPIC -O2 -Wall"
    $CC -I/aosp/external/mesa3d/include/android_stub -I/aosp/frameworks/native/vulkan/include \
      /repo/scripts/graphics/vk-hal-shim.c -ldl -o /b/libvk_hal_shim.so &&
    $CC /repo/scripts/graphics/deqp-stdout.c -ldl -o /b/libdeqp_stdout.so'
V=$B/vendor; rm -rf "$V"; cp -a --reflink=auto "$P/vendor" "$V"
ln -sf gralloc.minigbm.so "$V/lib64/hw/gralloc.default.so"
for k in EGL GLESv1_CM GLESv2; do ln -sfn "lib${k}_mesa.so" "$V/lib64/egl/lib${k}.so"; done
mkdir -p "$B/nonstrict"; cp "$NS" "$B/nonstrict/vulkan.radv.so"
cp "$G/bin/deqp-runner" "$B/bin/"
{ echo "image: $P"; grep -E '^ro.(system.)?build.(fingerprint|id)=' "$P/system/build.prop"
  sed -n '1,4p' "$A/aosp/src/vendor/anybook/mesa/PROVENANCE.txt"
  echo "deqp-binary64: $(sha256sum "$D/deqp-binary64" | cut -d' ' -f1)"
  echo "vulkan.radv.so (strict, image): $(sha256sum "$V/lib64/hw/vulkan.radv.so" | cut -d' ' -f1)"
  echo "vulkan.radv.so (nonstrict): $(sha256sum "$NS" | cut -d' ' -f1)"
  head -n 1 "$G/bin/deqp-runner.txt"
  echo "caselists: $CL ($(sha256sum "$CL/caselists.json" | cut -d' ' -f1))"
  echo "node: $NODE ($(tr '\n' ' ' < "/sys/class/drm/$(basename "$NODE")/device/uevent"))"; uname -r
  grep -m1 'model name' /proc/cpuinfo; } > "$OUT/versions.txt"
cat "$OUT/versions.txt"

# The device run's skip lists (Mesa CI's tests that hang AMD GPUs or take minutes), from Mesa's own tree.
SK=$B/skips; "$R/scripts/graphics/mkskips.sh" "$A/mesa/src/upstream" "$SK"
LP=/system/lib64:/apex/com.android.tethering/lib64:/apex/com.android.i18n/lib64
COMMON='"--deqp-archive-dir=/deqp", "--deqp-log-images=disable", "--deqp-log-shader-sources=disable", "--deqp-shadercache=disable"'
GLES='"--deqp-surface-width=256", "--deqp-surface-height=256", "--deqp-surface-type=pbuffer", "--deqp-visibility=hidden", "--deqp-gl-config-name=rgba8888d24s8ms0"'
ENV='[deqp.env]
LD_PRELOAD = "/b/libdeqp_stdout.so"'
suite() {  # NAME: writes $OUT/NAME/suite.toml
  local n=$1 o=$OUT/$1; mkdir -p "$o"
  case $n in
    vk|vk14) printf '[[deqp]]\ndeqp = "/deqp/deqp-binary64"\ncaselists = ["/cl/vk.txt"]\nskips = ["/skips/radv.txt"]\ntests_per_group = 500\nrenderer_check = "RADV"\ndeqp_args = [%s, "--deqp-vk-library-path=/b/libvk_hal_shim.so"]\n%s\n' "$COMMON" "$ENV" ;;
    gles-mesa) for m in gles2 gles3 gles31; do
        printf '[[deqp]]\ndeqp = "/deqp/deqp-binary64"\ncaselists = ["/cl/%s.txt"]\nskips = ["/skips/radeonsi.txt"]\ntests_per_group = 500\nrenderer_check = "radeonsi"\ndeqp_args = [%s, %s]\n%s\n\n' "$m" "$COMMON" "$GLES" "$ENV"; done ;;
    *) echo "unknown part $n" >&2; return 2 ;;
  esac > "$o/suite.toml"
}
for part in "${PARTS[@]}"; do
  suite "$part"
  HAL=/vendor/lib64/hw/vulkan.radv.so; [ "$part" = vk14 ] && HAL=/nonstrict/vulkan.radv.so
  echo "== $part ($(date -u +%FT%TZ))"
  t0=$(date +%s)
  set +e
  docker run --rm -u "$(id -u):$(id -g)" --device "$NODE" --group-add "$(stat -c %g "$NODE")" \
    -v "$P/system:/system:ro" -v "$V:/vendor:ro" -v "$P/apex:/apex:ro" -v "$D:/deqp:ro" -v "$CL:/cl:ro" -v "$SK:/skips:ro" \
    -v "$B/bin:/b:ro" -v "$B/nonstrict:/nonstrict:ro" -v "$OUT/$part:/out" -w /out \
    -e HOME=/tmp -e TMPDIR=/tmp -e LD_LIBRARY_PATH="$LP" -e OPENBOOK_VK_HAL="$HAL" alpine:3.21 \
    /b/deqp-runner suite --suite /out/suite.toml --output /out/run --jobs "$JOBS" --fraction "$FRACTION" \
      --summary-limit 30 > "$OUT/$part/deqp-runner.txt" 2>&1
  rc=$?
  set -e
  echo "$part: deqp-runner rc=$rc, $(( $(date +%s) - t0 )) s"; tail -n 14 "$OUT/$part/deqp-runner.txt"
  echo "{\"part\": \"$part\", \"rc\": $rc, \"seconds\": $(( $(date +%s) - t0 )), \"jobs\": $JOBS, \"fraction\": $FRACTION}" \
    > "$OUT/$part/part.json"
done
echo "pre-check: $OUT"
