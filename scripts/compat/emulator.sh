#!/usr/bin/env bash
# Lifecycle for the compat harness emulator: AVD "anybook-desktop" (AOSP Desktop (Preview) 37.0 x86_64,
# native bridge libndk_translation) on console/adb ports 5580/5581, SwiftShader GLES plus guest Vulkan
# (-feature Vulkan plus hw.gltransport=virtio-gpu; both are off by default). The AVD and SDK come from
# scripts/m0-emulator.sh; run that once first. No sudo needed.
# COMPAT_AVD selects another AVD on the same ports (default anybook-desktop); COMPAT_EMU_ARGS adds emulator
# flags. The Digitalis evaluation uses COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system
# (scripts/compat/digitalis/install.sh), so the libndk_translation AVD stays untouched. COMPAT_GLTRANSPORT= (empty)
# keeps the AVD's default GL transport and drops -feature Vulkan: the Digitalis AOSP 16 image (ANGLE on Vulkan)
# crashes emulator 37.2.12 with virtio-gpu, and has guest Vulkan without it.
#   emulator.sh up [--wipe]   boot (or reuse a booted instance), adb root, quiet the UI for testing
#   emulator.sh down          stop the instance this script started (exact PID from the pidfile)
#   emulator.sh status        print state
#   emulator.sh serial        print the adb serial
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; S=$A/android-sdk
RUN=$A/compat/run; LOGS=$A/logs/compat; PIDF=$RUN/emulator.pid
SERIAL=emulator-5580
AVD=${COMPAT_AVD:-anybook-desktop}; EXTRA=${COMPAT_EMU_ARGS:-}; GLT=${COMPAT_GLTRANSPORT-virtio-gpu}
export ANDROID_SDK_ROOT=$S ANDROID_HOME=$S ANDROID_AVD_HOME=$A/avd ANDROID_USER_HOME=$A/android-user ANDROID_EMULATOR_HOME=$A/android-user
ADB="$S/platform-tools/adb -s $SERIAL"
mkdir -p "$RUN" "$LOGS"

booted(){ [ "$($ADB shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; }
ours(){ [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }

prepare(){
  # userdebug image: adb root lets us count tombstones and read /proc/<pid>/maps
  $ADB root >/dev/null 2>&1 || true; sleep 2; $ADB wait-for-device
  for _ in $(seq 1 30); do booted && break; sleep 2; done
  $ADB shell 'settings put global window_animation_scale 0; settings put global transition_animation_scale 0;
    settings put global animator_duration_scale 0; settings put system screen_off_timeout 2147483647;
    svc power stayon true; wm dismiss-keyguard; input keyevent KEYCODE_WAKEUP' >/dev/null 2>&1 || true
}

case ${1:-status} in
up)
  if booted; then echo "reusing booted $SERIAL"; prepare; exit 0; fi
  [ -f "$A/avd/$AVD.avd/config.ini" ] || { echo "AVD $AVD missing: run scripts/m0-emulator.sh once" >&2; exit 2; }
  if ours; then echo "emulator pid $(cat "$PIDF") running but not booted; waiting"; else
    # Guest Vulkan (Mesa gfxstream) needs a virtio-gpu render node; m0-emulator.sh writes the default goldfish pipe.
    CFG=$A/avd/$AVD.avd/config.ini; VK=
    if [ -n "$GLT" ]; then
      grep -qx "hw.gltransport=$GLT" "$CFG" || { sed -i '/^hw.gltransport=/d' "$CFG"; echo "hw.gltransport=$GLT" >> "$CFG"; }
      VK="-feature Vulkan"
    fi
    W=; [ "${2:-}" = --wipe ] && W=-wipe-data
    LOG=$LOGS/emulator-$(date +%Y%m%d-%H%M%S).log
    setsid nohup "$S/emulator/emulator" -avd "$AVD" -no-window -no-audio -no-snapshot -no-boot-anim \
      -gpu swiftshader_indirect $VK -accel on -ports 5580,5581 $W $EXTRA > "$LOG" 2>&1 < /dev/null &
    echo $! > "$PIDF"; echo "started emulator pid $! (log $LOG)"
  fi
  T0=$(date +%s)
  until booted; do
    ours || { echo "emulator exited during boot" >&2; exit 1; }
    [ $(( $(date +%s) - T0 )) -lt 600 ] || { echo "boot timeout" >&2; exit 1; }
    sleep 3
  done
  echo "boot_completed after $(( $(date +%s) - T0 ))s"; prepare ;;
down)
  if ours; then
    P=$(cat "$PIDF"); $ADB emu kill >/dev/null 2>&1 || true
    for _ in $(seq 1 20); do kill -0 "$P" 2>/dev/null || break; sleep 1; done
    kill "$P" 2>/dev/null || true; rm -f "$PIDF"; echo "stopped emulator pid $P"
  else echo "no emulator started by this script"; fi ;;
serial) echo "$SERIAL" ;;
status)
  ours && echo "pid $(cat "$PIDF")" || echo "no pidfile process"
  booted && echo "$SERIAL booted" || echo "$SERIAL not booted" ;;
*) echo "usage: $0 up [--wipe] | down | status | serial" >&2; exit 2 ;;
esac
