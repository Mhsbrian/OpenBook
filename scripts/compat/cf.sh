#!/usr/bin/env bash
# Lifecycle for the compat harness on OpenBook's own Cuttlefish build (ANAL-200), the counterpart of emulator.sh:
# run-matrix.sh, run-bench.sh and digitalis/fp-estimate.sh use it with COMPAT_TARGET=cf. It boots the product in
# CF_OUT/target/product/CF_DEVICE (default anybook_vsoc_x86_64, the anybook_cf_x86_64_pc desktop product) through
# scripts/cf-boot.sh, keeps it running, and connects the SDK's adb to it on 127.0.0.1:CF_ADB_PORT. Every `up` from
# down stages the images afresh, so it starts from wiped data, like the emulator's -wipe-data.
#   cf.sh up [--wipe]   boot (or reuse a booted instance; --wipe reboots from fresh images), adb root, quiet the UI
#   cf.sh down          cvd reset and remove the container (its name, CF_NAME, is the cleanup handle)
#   cf.sh status        print state
#   cf.sh serial        print the adb serial
# Defaults match the emulator AVDs of the baseline: 6 vCPUs (CF_CPUS), 8 GiB (CF_MEMORY_MB), SwiftShader GLES and
# Vulkan in the guest (CF_GPU_MODE=guest_swiftshader). No sudo needed.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}
export CF_DEVICE=${CF_DEVICE:-anybook_vsoc_x86_64} CF_NAME=${CF_NAME:-anybook-cf-compat}
export CF_ADB_PORT=${CF_ADB_PORT:-16530} CF_WEBRTC_PORT=${CF_WEBRTC_PORT:-11453}
export CF_CPUS=${CF_CPUS:-6} CF_MEMORY_MB=${CF_MEMORY_MB:-8192} CF_GPU_MODE=${CF_GPU_MODE:-guest_swiftshader}
export CF_STAGE=${CF_STAGE:-$A/compat/cf/product} CF_KEEP=1
SERIAL=127.0.0.1:$CF_ADB_PORT
ADB="$A/android-sdk/platform-tools/adb"

running(){ [ "$(docker inspect -f '{{.State.Running}}' "$CF_NAME" 2>/dev/null)" = true ]; }
booted(){ running && $ADB -s "$SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' | grep -qx 1; }
connect(){ $ADB connect "$SERIAL" >/dev/null 2>&1 || true; }

prepare(){
  # userdebug image: adb root lets the harness count tombstones and read /proc/<pid>/maps
  connect; $ADB -s "$SERIAL" root >/dev/null 2>&1 || true; sleep 2; connect; $ADB -s "$SERIAL" wait-for-device
  for _ in $(seq 1 30); do booted && break; sleep 2; connect; done
  $ADB -s "$SERIAL" shell 'settings put global window_animation_scale 0; settings put global transition_animation_scale 0;
    settings put global animator_duration_scale 0; settings put system screen_off_timeout 2147483647;
    svc power stayon true; wm dismiss-keyguard; input keyevent KEYCODE_WAKEUP' >/dev/null 2>&1 || true
}

down(){
  if running || docker inspect "$CF_NAME" >/dev/null 2>&1; then
    $ADB disconnect "$SERIAL" >/dev/null 2>&1 || true
    "$REPO/scripts/cf-boot.sh" down; echo "stopped $CF_NAME"
  else echo "no $CF_NAME container"; fi
}

case ${1:-status} in
up)
  [ "${2:-}" = --wipe ] && down
  connect
  if booted; then echo "reusing booted $SERIAL ($CF_NAME)"; prepare; exit 0; fi
  running && down
  mkdir -p "$CF_STAGE"
  CF_LOGS=${CF_LOGS:-$A/logs/compat/cf-$(date -u +%Y%m%dT%H%M%SZ)} "$REPO/scripts/cf-boot.sh" up
  "$REPO/scripts/cf-boot.sh" wait
  connect; prepare
  echo "booted $SERIAL ($CF_NAME, $CF_DEVICE)" ;;
down) down ;;
status)
  running && echo "$CF_NAME running" || echo "$CF_NAME not running"
  booted && echo "$SERIAL booted" || echo "$SERIAL not booted" ;;
serial) echo "$SERIAL" ;;
*) sed -n '2,13p' "$0"; exit 2 ;;
esac
