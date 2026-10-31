#!/usr/bin/env bash
# Boot Google's AOSP Desktop (Preview) Android 17 emulator image (the reference for ANAL-169) in its own AVD,
# run scripts/desktop-capture.sh against it, then stop it. The SDK, emulator and system image come from
# scripts/m0-emulator.sh (Android SDK Preview License: local use only, never redistributed).
# Separate from other runs on this host: own AVD (~/anybook/desktop/avd), console/adb ports 5600/5601,
# private adb server (port 5047). Only the emulator PID this script started is ever killed.
#
# usage: desktop-ref-emulator.sh OUTDIR
# Env: REF_API=37.1 boots the "Google APIs Desktop (Preview)" image instead (system-images;android-37.1;
#      android-desktop;x86_64, Android SDK License, local use only), in its own AVD.
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; S=$A/android-sdk; O=${1:?outdir}; HERE=$(cd "$(dirname "$0")" && pwd)
D=$A/desktop/avd; P=${REF_PORT:-5600}; API=${REF_API:-37.0}
SYSIMG=system-images/android-$API/android-desktop/x86_64/; AVD=anybook-desktop-ref; [ "$API" = 37.0 ] || AVD=$AVD-$API
[ -f "$S/$SYSIMG/system.img" ] || { echo "run scripts/m0-emulator.sh first (SDK + desktop image)" >&2; exit 1; }
mkdir -p "$O" "$D/$AVD.avd" "$A/desktop/android-user"
printf 'avd.ini.encoding=UTF-8\npath=%s\ntarget=android-%s\n' "$D/$AVD.avd" "$API" > "$D/$AVD.ini"
# Same hardware as the M0 baseline (scripts/m0-emulator.sh): 1920x1080 at 160 dpi, keyboard, no Play Store.
cat > "$D/$AVD.avd/config.ini" <<CFG
avd.ini.encoding=UTF-8
AvdId=$AVD
PlayStore.enabled=false
abi.type=x86_64
hw.cpu.arch=x86_64
hw.cpu.ncore=4
hw.ramSize=${REF_RAM_MB:-8192}
hw.lcd.width=1920
hw.lcd.height=1080
hw.lcd.density=160
hw.keyboard=yes
hw.mainKeys=no
hw.gpu.enabled=yes
hw.gpu.mode=swiftshader_indirect
hw.initialOrientation=landscape
image.sysdir.1=$SYSIMG
tag.id=android-desktop
tag.ids=android-desktop,aosp
disk.dataPartition.size=8G
CFG
export ANDROID_SDK_ROOT=$S ANDROID_HOME=$S ANDROID_AVD_HOME=$D ANDROID_USER_HOME=$A/desktop/android-user \
       ANDROID_EMULATOR_HOME=$A/desktop/android-user ANDROID_ADB_SERVER_PORT=${REF_ADB_SERVER_PORT:-5047}
ADB=$S/platform-tools/adb
"$S/emulator/emulator" -avd "$AVD" -no-window -no-audio -no-snapshot -no-boot-anim -wipe-data \
  -gpu swiftshader_indirect -accel on -ports "$P,$((P+1))" > "$O/emulator.log" 2>&1 &
EPID=$!
trap 'kill $EPID 2>/dev/null || true; wait $EPID 2>/dev/null || true; "$ADB" kill-server 2>/dev/null || true' EXIT
echo "emulator pid $EPID, serial emulator-$P" | tee "$O/ref.log"
ADB=$ADB "$HERE/desktop-capture.sh" "emulator-$P" "$O"
