#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build scripts/graphics/vk-compute-bench.c twice, for Android (NDK, bionic) and for Linux (glibc), and measure one
# NVIDIA GPU under both drivers (ANAL-296): NVK on NVIDIA's kernel module, from the AnyBook image's bionic through
# scripts/nvidia-android-hosttest.sh, and NVIDIA's own Vulkan driver on this host through its loader.
#
#   scripts/graphics/vk-compute-bench.sh BUNDLE OUT_DIR [ROUNDS]
# BUNDLE: an extracted Android NVIDIA driver bundle (payload/vendor_extra/lib64/libvulkan_nouveau.so).
# ROUNDS (default 3): alternating runs of each driver. Results: OUT_DIR/bench.csv and the raw logs.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); repo=$(cd "$here/../.." && pwd)
[ $# -ge 2 ] || { sed -n 3,9p "$0" >&2; exit 2; }
BUNDLE=$(realpath "$1"); OUT=$(realpath -m "$2"); ROUNDS=${3:-3}; API=${API:-33}
mkdir -p "$OUT/bin"
for s in fma copy; do
  glslangValidator -V --target-env vulkan1.1 --vn "${s}_spv" -o "$OUT/bin/vk-compute-bench-$s.h" \
    "$here/vk-compute-bench-$s.comp" > /dev/null
done
docker run --rm --network none -u "$(id -u):$(id -g)" -v "$here:/src:ro" -v "$OUT/bin:/o" anybook-mesa-android sh -ec "
  nd=/opt/android-ndk/toolchains/llvm/prebuilt/linux-x86_64
  \$nd/bin/x86_64-linux-android$API-clang -O2 -Wall -I/o /src/vk-compute-bench.c -ldl -o /o/vk-compute-bench-android
  mkdir -p /tmp/inc && cp -r \$nd/sysroot/usr/include/vulkan \$nd/sysroot/usr/include/vk_video /tmp/inc/
  cc -O2 -Wall -I/o -I/tmp/inc /src/vk-compute-bench.c -ldl -o /o/vk-compute-bench-linux"
echo "driver,round,device,fp32_tflops_median,copy_gbps_median" > "$OUT/bench.csv"
row() { printf '%s,%s,%s,%s,%s\n' "$1" "$2" "$(sed -n 's/^device=//p' "$3")" \
          "$(sed -n 's/^fp32_tflops_median=//p' "$3")" "$(sed -n 's/^copy_gbps_median=//p' "$3")" >> "$OUT/bench.csv"; }
for r in $(seq "$ROUNDS"); do
  EXTRA_MOUNT="$OUT/bin:/bench" CASE_NAME=nvk-rm-$r "$repo/scripts/nvidia-android-hosttest.sh" "$BUNDLE" "$OUT" -- \
    /bench/vk-compute-bench-android /b/payload/vendor_extra/lib64/libvulkan_nouveau.so > /dev/null
  row nvk-on-nvidia.ko "$r" "$OUT/nvk-rm-$r.log"
  "$OUT/bin/vk-compute-bench-linux" libvulkan.so.1 "RTX" > "$OUT/nvidia-$r.log" 2>&1
  row nvidia-proprietary "$r" "$OUT/nvidia-$r.log"
done
grep -h '^driver=' "$OUT"/nvk-rm-1.log "$OUT"/nvidia-1.log
column -s, -t < "$OUT/bench.csv"
