#!/usr/bin/env bash
# Load test for the Mesa Android artifacts (scripts/mesa-android-build.sh) on Android 17 x86_64:
# Google's AOSP Desktop emulator image (fetched by scripts/m0-emulator.sh) under KVM. Pushes
# ~/anybook/mesa/out/<tree>/vendor plus a small NDK test (scripts/mesa-android-smoke.c) and runs it.
# The VM has no AMD GPU, so this proves loading, linking and GPU-less entry points only.
# Uses its own AVD, console port 5590 and adb server port 5099: it never touches other emulators
# or the default adb server.
#   scripts/mesa-android-smoke.sh [tree ...]     (default: upstream ag)
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; S=$A/android-sdk; M=$A/mesa; repo=$(cd "$(dirname "$0")/.." && pwd)
API=${API:-37}; PORT=5590; ADBP=5099; E=${E:-$M/evidence/smoke}
trees=("$@"); ((${#trees[@]})) || trees=(upstream ag)
img=system-images/android-37.0/android-desktop/x86_64
[ -f "$S/$img/system.img" ] || { echo "AOSP Desktop image missing: run scripts/m0-emulator.sh first" >&2; exit 1; }
mkdir -p "$E" "$M/avd/anybook-mesa.avd" "$M/android-user" "$M/build/smoke"

docker run --rm -u "$(id -u):$(id -g)" -v "$M:/a/mesa" -v "$repo:/repo:ro" anybook-mesa-android \
  /opt/android-ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android$API-clang -O2 -Wall \
  -I/a/mesa/src/upstream/include/android_stub -I/a/mesa/src/upstream/include \
  /repo/scripts/mesa-android-smoke.c -o /a/mesa/build/smoke/mesa-smoke

printf 'avd.ini.encoding=UTF-8\npath=%s\ntarget=android-37.0\n' "$M/avd/anybook-mesa.avd" > "$M/avd/anybook-mesa.ini"
cat > "$M/avd/anybook-mesa.avd/config.ini" <<CFG
avd.ini.encoding=UTF-8
AvdId=anybook-mesa
PlayStore.enabled=false
abi.type=x86_64
hw.cpu.arch=x86_64
hw.cpu.ncore=4
hw.ramSize=4096
hw.gpu.enabled=yes
hw.gpu.mode=swiftshader_indirect
image.sysdir.1=$img/
tag.id=android-desktop
disk.dataPartition.size=4G
CFG
export ANDROID_SDK_ROOT=$S ANDROID_HOME=$S ANDROID_AVD_HOME=$M/avd ANDROID_USER_HOME=$M/android-user \
       ANDROID_EMULATOR_HOME=$M/android-user ANDROID_ADB_SERVER_PORT=$ADBP
ADBH="$S/platform-tools/adb -P $ADBP"; SER=127.0.0.1:$((PORT + 1)); ADB="$ADBH -s $SER"
"$S/emulator/emulator" -avd anybook-mesa -no-window -no-audio -no-snapshot -no-boot-anim -wipe-data \
  -gpu swiftshader_indirect -accel on -ports $PORT,$((PORT + 1)) > "$E/emulator.log" 2>&1 &
EPID=$!; trap 'kill $EPID 2>/dev/null; wait $EPID 2>/dev/null; $ADBH kill-server 2>/dev/null' EXIT
B=
for _ in $(seq 1 90); do
  $ADBH connect "$SER" >/dev/null 2>&1 || true
  B=$($ADB shell getprop sys.boot_completed 2>/dev/null | tr -d '\r') || true
  [ "$B" = 1 ] && break; kill -0 $EPID 2>/dev/null || break; sleep 4
done
[ "$B" = 1 ] || { echo "emulator did not boot (see $E/emulator.log)" >&2; exit 1; }
$ADB shell 'getprop ro.build.fingerprint; getprop ro.build.version.sdk; uname -r; ls -l /dev/dri 2>&1; true' > "$E/device.txt"

for t in "${trees[@]}"; do
  d=/data/local/tmp/mesa-$t
  $ADB shell "rm -rf $d && mkdir -p $d" && $ADB push -q "$M/out/$t/vendor/." "$d/" && $ADB push -q "$M/build/smoke/mesa-smoke" "$d/"
  $ADB logcat -c || true
  $ADB shell "cd $d && chmod 755 mesa-smoke && LD_LIBRARY_PATH=$d/lib64:$d/lib64/egl ./mesa-smoke \
    lib64/hw/vulkan.radv.so lib64/egl/libEGL_mesa.so lib64/egl/libGLESv2_mesa.so; echo exit=\$?" 2>&1 | tr -d '\r' | tee "$E/$t-smoke.txt"
  $ADB logcat -d 2>&1 | grep -iE 'mesa|radv|MESA|libEGL|vulkan|DEBUG|crash|linker' > "$E/$t-logcat.txt" || true
done
