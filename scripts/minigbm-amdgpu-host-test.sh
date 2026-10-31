#!/usr/bin/env bash
# Build AOSP's minigbm amdgpu backend (amdgpu.c + AnyBook's dri_gbm.c, from the AOSP tree with
# aosp/patches applied) for Linux and run scripts/minigbm-amdgpu-host-test.c on a real AMD GPU.
# No root: the render node is passed into the anybook-minigbm-host container.
#
#   scripts/minigbm-amdgpu-host-test.sh [OUT_DIR]
# Env: MINIGBM_SRC (default ~/anybook/aosp/src/external/minigbm), AMD_RENDER_NODE (default: the
#      first /dev/dri/renderD* bound to amdgpu).
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd); A=${ANYBOOK_HOME:-$HOME/anybook}
SRC=${MINIGBM_SRC:-$A/aosp/src/external/minigbm}
OUT=${1:-$A/logs/graphics-amd/minigbm-host-$(date -u +%Y%m%dT%H%M%SZ)}
mkdir -p "$OUT"
NODE=${AMD_RENDER_NODE:-}
if [[ -z $NODE ]]; then
  for n in /sys/class/drm/renderD*; do
    [[ $(basename "$(readlink -f "$n/device/driver")") == amdgpu ]] && { NODE=/dev/dri/$(basename "$n"); break; }
  done
fi
[[ -n $NODE ]] || { echo "no amdgpu render node" >&2; exit 2; }
grep -q 'dri_gbm' "$SRC/Android.bp" || { echo "$SRC lacks the AnyBook dri_gbm patch (scripts/aosp-patches.sh)" >&2; exit 2; }
docker image inspect anybook-minigbm-host >/dev/null 2>&1 ||
  docker build -t anybook-minigbm-host -f "$R/tools/Dockerfile.minigbm-host" "$R/tools"

# Only the AMD render node goes in, so EGL's surfaceless platform can only pick that GPU.
docker run --rm -u "$(id -u):$(id -g)" --device "$NODE" --group-add "$(stat -c %g "$NODE")" \
  -v "$SRC:/minigbm:ro" -v "$R/scripts:/s:ro" -v "$OUT:/out" anybook-minigbm-host bash -euo pipefail -c '
  cd /out
  { pacman -Q mesa libdrm libglvnd; uname -r; echo "node: '"$NODE"' ($(cat /sys/class/drm/$(basename '"$NODE"')/device/uevent | tr "\n" " "))"
    git -C /minigbm log -3 --format="%h %s" 2>/dev/null || true; } > versions.txt
  srcs=$(cd /minigbm && ls amdgpu.c dri_gbm.c drv.c drv_array_helpers.c drv_helpers.c dumb_driver.c backend_mock.c \
         i915.c mediatek.c msm.c rockchip.c vc4.c virtgpu.c virtgpu_cross_domain.c virtgpu_virgl.c xe.c | sed "s|^|/minigbm/|")
  gcc -std=gnu11 -O1 -g -Wall -Wno-unused-parameter -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64 -DDRV_AMDGPU \
    $(pkg-config --cflags libdrm) -I/minigbm -o minigbm-amdgpu-host-test /s/minigbm-amdgpu-host-test.c $srcs \
    $(pkg-config --libs libdrm egl glesv2) -ldl -lpthread 2>&1 | tee build.log
  ./minigbm-amdgpu-host-test '"$NODE"' 2>&1 | tee test.log' && rc=0 || rc=$?
echo "minigbm host test: rc=$rc, logs in $OUT"
exit $rc
