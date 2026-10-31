#!/usr/bin/env bash
# Milestone 0 baseline: boot Google's "AOSP Desktop (Preview)" Android 17 x86_64 emulator image
# headless under KVM, capture props/logcat/dmesg/screenshots. No sudo, no Java needed.
# The SDK images are under the Android SDK Preview License: use locally, do not redistribute.
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; S=$A/android-sdk; Z=$A/dl/sdk-zips; E=${1:-$A/evidence/m0-emulator}
R=https://dl.google.com/android/repository
mkdir -p "$Z" "$E" "$S/system-images/android-37.0/android-desktop" "$A/avd/anybook-desktop.avd" "$A/android-user"
get(){ [ -f "$Z/$1" ] && echo "$2  $Z/$1" | sha1sum -c --quiet - 2>/dev/null || curl -fL -o "$Z/$1" "$3/$1"; echo "$2  $Z/$1" | sha1sum -c -; }
get x86_64-37.0_r01.zip a56c5e2d88a0136bfa4df406157d26a6d418732f $R/sys-img/android-desktop
[ -f "$Z/emulator-linux_x64-16428233.zip" ] || curl -fL -o "$Z/emulator-linux_x64-16428233.zip" $R/emulator-linux_x64-16428233.zip
[ -f "$Z/platform-tools-latest-linux.zip" ] || curl -fL -o "$Z/platform-tools-latest-linux.zip" $R/platform-tools-latest-linux.zip
[ -x "$S/emulator/emulator" ] || unzip -q -o "$Z/emulator-linux_x64-16428233.zip" -d "$S"
[ -x "$S/platform-tools/adb" ] || unzip -q -o "$Z/platform-tools-latest-linux.zip" -d "$S"
[ -f "$S/system-images/android-37.0/android-desktop/x86_64/system.img" ] || unzip -q -o "$Z/x86_64-37.0_r01.zip" -d "$S/system-images/android-37.0/android-desktop"
printf 'avd.ini.encoding=UTF-8\npath=%s\ntarget=android-37.0\n' "$A/avd/anybook-desktop.avd" > "$A/avd/anybook-desktop.ini"
cat > "$A/avd/anybook-desktop.avd/config.ini" <<'CFG'
avd.ini.encoding=UTF-8
AvdId=anybook-desktop
PlayStore.enabled=false
abi.type=x86_64
hw.cpu.arch=x86_64
hw.cpu.ncore=8
hw.ramSize=8192
hw.lcd.width=1920
hw.lcd.height=1080
hw.lcd.density=160
hw.keyboard=yes
hw.mainKeys=no
hw.gpu.enabled=yes
hw.gpu.mode=swiftshader_indirect
hw.initialOrientation=landscape
image.sysdir.1=system-images/android-37.0/android-desktop/x86_64/
tag.id=android-desktop
tag.ids=android-desktop,aosp
disk.dataPartition.size=16G
CFG
export ANDROID_SDK_ROOT=$S ANDROID_HOME=$S ANDROID_AVD_HOME=$A/avd ANDROID_USER_HOME=$A/android-user ANDROID_EMULATOR_HOME=$A/android-user
ADB="$S/platform-tools/adb -s emulator-5580"
"$S/emulator/emulator" -avd anybook-desktop -no-window -no-audio -no-snapshot -no-boot-anim \
  -gpu swiftshader_indirect -accel on -ports 5580,5581 > "$E/emulator.log" 2>&1 &
EPID=$!; trap 'kill $EPID 2>/dev/null; $S/platform-tools/adb kill-server 2>/dev/null' EXIT
T0=$(date +%s); B=
for _ in $(seq 1 150); do
  B=$($ADB shell getprop sys.boot_completed 2>/dev/null | tr -d '\r') || true
  [ "$B" = 1 ] && break; kill -0 $EPID 2>/dev/null || break; sleep 4
done
echo "boot_completed=${B:-0} after $(( $(date +%s) - T0 ))s" | tee "$E/boot-result.txt"
[ "$B" = 1 ] || exit 1
sleep 20
$ADB shell 'getprop ro.build.fingerprint; getprop ro.product.cpu.abilist; getprop ro.dalvik.vm.native.bridge; getprop ro.build.characteristics; uname -a; pm list features | grep -iE "type.pc|freeform"' > "$E/props.txt" 2>&1
$ADB exec-out screencap -p > "$E/screen-desktop.png"
$ADB shell am start -a android.settings.SETTINGS >/dev/null; sleep 4
$ADB shell am start -n com.android.documentsui/.files.FilesActivity >/dev/null; sleep 4
$ADB exec-out screencap -p > "$E/screen-windows.png"
$ADB shell dumpsys activity activities | grep -c 'mWindowingMode=freeform' > "$E/freeform-count.txt" || true
$ADB shell dmesg > "$E/dmesg.txt" 2>&1 || true
$ADB logcat -d -b all > "$E/logcat.txt" 2>&1
cat "$E/props.txt"
