#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# OpenBook Update on Google's Android Desktop emulator (Google APIs, API 37.1, userdebug; Android SDK License,
# local use only), in its own AVD with its own ports and adb server. Kills only the emulator it started.
#   1. engine     openbook-updater-device-test.sh on the emulator's own mksh, toybox, awk and curl
#   2. app        the instrumented tests: the engine as the app's child process (check, download, verify, a
#                 held major release, stop), the check job (notification, history, Wi-Fi-only download), the
#                 real main screen against Google's live listing, and every screen state as PNG
#   3. system     the signed release APK as a privileged system app with its allow-list, default
#                 permissions and power-save exemption, after a restart with existing data (as an OpenBook
#                 update brings it): privileged, REBOOT granted, battery-exempt, started at boot for the
#                 owner, launched; desktop screenshots. The emulator's own SELinux policy has no OpenBook
#                 domain, so here the app runs as Google's priv_app (no update_engine either): the domain,
#                 the app contexts and a first boot are tested in the Ruby VM (update-app-vm.sh)
# Writes OUTDIR/result.json and the evidence beside it.
#
# usage: emulator-test.sh OUTDIR BUILD_DIR      (BUILD_DIR: build.sh output with the three APKs)
# env:   ADAPT_BIN  openbook-adapt (adapt/build.sh) to push into /system/bin for AdapterProcessTest
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
O=${1:?outdir}; B=${2:?build dir}
A=${ANYBOOK_HOME:-$HOME/anybook}; S=$A/android-sdk
D=$A/desktop/avd; AVD=openbook-update-test; P=${OBU_EMU_PORT:-5610}
SYSIMG=system-images/android-37.1/android-desktop/x86_64/
[ -f "$S/$SYSIMG/system.img" ] || { echo "the API 37.1 desktop image is missing (scripts/desktop-ref-emulator.sh)" >&2; exit 2; }
for f in OpenBookUpdate.apk app-debug.apk app-debug-androidTest.apk; do [ -f "$B/$f" ] || { echo "missing $B/$f" >&2; exit 2; }; done
mkdir -p "$O" "$D/$AVD.avd" "$A/desktop/android-user"
printf 'avd.ini.encoding=UTF-8\npath=%s\ntarget=android-37.1\n' "$D/$AVD.avd" > "$D/$AVD.ini"
cat > "$D/$AVD.avd/config.ini" <<CFG
avd.ini.encoding=UTF-8
AvdId=$AVD
PlayStore.enabled=false
abi.type=x86_64
hw.cpu.arch=x86_64
hw.cpu.ncore=4
hw.ramSize=8192
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
tag.ids=android-desktop,google_apis
disk.dataPartition.size=8G
CFG
export ANDROID_SDK_ROOT=$S ANDROID_HOME=$S ANDROID_AVD_HOME=$D ANDROID_USER_HOME=$A/desktop/android-user \
       ANDROID_EMULATOR_HOME=$A/desktop/android-user ANDROID_ADB_SERVER_PORT=${OBU_ADB_SERVER_PORT:-5049}
export ADB=$S/platform-tools/adb
SERIAL=emulator-$P
a() { timeout 600 "$ADB" -s "$SERIAL" "$@"; }
sh_() { a shell "$@" | tr -d '\r'; }
"$S/emulator/emulator" -avd "$AVD" -no-window -no-audio -no-snapshot -no-boot-anim -wipe-data -writable-system \
  -gpu swiftshader_indirect -accel on -ports "$P,$((P+1))" > "$O/emulator.log" 2>&1 &
EPID=$!
trap 'kill $EPID 2>/dev/null; wait $EPID 2>/dev/null; "$ADB" kill-server 2>/dev/null' EXIT
boot() {
  for _ in $(seq 1 120); do
    [ "$(sh_ getprop sys.boot_completed 2>/dev/null)" = 1 ] && return 0
    kill -0 $EPID 2>/dev/null || return 1
    sleep 5
  done; return 1
}
"$ADB" start-server > /dev/null 2>&1
boot || { echo "the emulator did not boot" >&2; exit 1; }
sleep 20
sh_ getprop ro.build.fingerprint > "$O/fingerprint.txt"
{ echo "headless_system_user=$(sh_ getprop ro.fw.mu.headless_system_user)"; echo "current_user=$(sh_ am get-current-user)"; sh_ pm list users; } > "$O/users.txt"

# 1. Engine on the emulator's own tools.
"$HERE/../openbook-updater-device-test.sh" --serial "$SERIAL" > "$O/engine-device-test.txt" 2>&1; engine_rc=$?

# 2. The app's instrumented tests.
a install -r -t -g "$B/app-debug.apk" > "$O/install-debug.txt" 2>&1
a install -r -t "$B/app-debug-androidTest.apk" >> "$O/install-debug.txt" 2>&1
a shell am instrument -w -r org.openbook.update.test/androidx.test.runner.AndroidJUnitRunner > "$O/instrumentation.txt" 2>&1
app_ok=$(grep -c '^OK (' "$O/instrumentation.txt")
mkdir -p "$O/screenshots"
U=$(sh_ am get-current-user)
a exec-out run-as org.openbook.update --user "$U" tar -cf - -C files screenshots > "$O/screenshots.tar" 2> "$O/screenshots-pull.txt" \
  && tar -xf "$O/screenshots.tar" -C "$O" && rm "$O/screenshots.tar"
a logcat -d -s OpenBookUpdate:* TestRunner:* > "$O/logcat-app-tests.txt" 2>&1

# 2b. openbook-adapt as the app's child (ADAPT_BIN, an adapt/build.sh output): pushed into /system/bin, then
#     AdapterProcessTest alone, as the owner, under Android's app seccomp filter. Skipped without ADAPT_BIN.
adapter_ok=null
if [ -n "${ADAPT_BIN:-}" ]; then
  a root > /dev/null 2>&1; sleep 3; a wait-for-device
  a remount > "$O/remount-adapter.txt" 2>&1
  if grep -qi reboot "$O/remount-adapter.txt"; then
    a reboot; sleep 10; a wait-for-device; boot; a root > /dev/null 2>&1; sleep 3; a wait-for-device
    a remount >> "$O/remount-adapter.txt" 2>&1
  fi
  a push "$ADAPT_BIN" /system/bin/openbook-adapt > /dev/null && a shell chmod 755 /system/bin/openbook-adapt
  sh_ ls -lZ /system/bin/openbook-adapt > "$O/adapter-file.txt" 2>&1
  # The owner's session after a restart (Googlebook's headless system user switches to it).
  for _ in $(seq 1 90); do
    u=$(sh_ am get-current-user 2>/dev/null | tr -d '\r')
    case $u in [1-9]*) break ;; esac
    sleep 2
  done
  a shell am instrument -w -r --user "$u" -e class org.openbook.update.AdapterProcessTest \
    org.openbook.update.test/androidx.test.runner.AndroidJUnitRunner > "$O/instrumentation-adapter.txt" 2>&1
  if grep -q '^OK (1 test)' "$O/instrumentation-adapter.txt"; then adapter_ok=true; else adapter_ok=false; fi
fi
a uninstall org.openbook.update.test > /dev/null 2>&1; a uninstall org.openbook.update > /dev/null 2>&1

# 3. The signed release as a privileged system app: its files written into /system, then a restart.
a root > /dev/null 2>&1; sleep 3; a wait-for-device
a remount > "$O/remount.txt" 2>&1
if grep -qi reboot "$O/remount.txt"; then a reboot; sleep 10; a wait-for-device; boot; a root > /dev/null 2>&1; sleep 3; a wait-for-device; a remount >> "$O/remount.txt" 2>&1; fi
a shell mkdir -p /system/priv-app/OpenBookUpdate /system/etc/default-permissions
a push "$B/OpenBookUpdate.apk" /system/priv-app/OpenBookUpdate/OpenBookUpdate.apk > /dev/null
a push "$HERE/../privapp-permissions-org.openbook.update.xml" /system/etc/permissions/ > /dev/null
a push "$HERE/../default-permissions-org.openbook.update.xml" /system/etc/default-permissions/ > /dev/null
a push "$HERE/../sysconfig-org.openbook.update.xml" /system/etc/sysconfig/ > /dev/null
a shell chmod 644 /system/priv-app/OpenBookUpdate/OpenBookUpdate.apk /system/etc/permissions/privapp-permissions-org.openbook.update.xml \
  /system/etc/default-permissions/default-permissions-org.openbook.update.xml /system/etc/sysconfig/sysconfig-org.openbook.update.xml
a shell sync
a shell setprop persist.logd.size 16M
# A restart with the same fingerprint and existing data, as on a laptop updated by an OpenBook update
# (default permissions apply on a first boot or a new fingerprint: the Ruby VM test covers that path).
a logcat -c
a reboot; sleep 10; a wait-for-device; boot || { echo "no boot with the system app" >&2; exit 1; }
# The desktop runs a headless system user (0); the owner is user 10. Bring the owner back to the front.
OWNER=$(sh_ pm list users | sed -n 's/.*UserInfo{\([1-9][0-9]*\):.*/\1/p' | head -1)
a shell am switch-user "$OWNER"
for _ in $(seq 1 60); do [ "$(sh_ am get-current-user)" = "$OWNER" ] && break; sleep 2; done
sleep 60
a logcat -d -s OpenBookUpdate:* AndroidRuntime:E > "$O/logcat-system-boot.txt" 2>&1
{ echo "current_user=$(sh_ am get-current-user)"; sh_ pm list users; } > "$O/system-users.txt"
sh_ ls -l /system/priv-app/OpenBookUpdate > "$O/system-files.txt"
sh_ dumpsys package org.openbook.update > "$O/system-package.txt"
sh_ dumpsys deviceidle whitelist > "$O/system-deviceidle.txt"
sh_ dumpsys jobscheduler | grep -A6 'org.openbook.update/androidx.work.impl.background.systemjob.SystemJobService' > "$O/system-jobs.txt"
sh_ ps -AZ | grep -E 'org.openbook.update' > "$O/system-process.txt"
a shell am start -W --user current -n org.openbook.update/.ui.MainActivity > "$O/system-launch.txt" 2>&1
sleep 25
a exec-out screencap -p > "$O/system-desktop.png"
# Notifications switched off (as on an image updated without a fresh install): the banner offers them.
a shell pm revoke --user current org.openbook.update android.permission.POST_NOTIFICATIONS
a shell am force-stop --user current org.openbook.update
a shell am start -W --user current -n org.openbook.update/.ui.MainActivity > /dev/null 2>&1
sleep 15
a exec-out screencap -p > "$O/system-desktop-notifications-off.png"
a logcat -d -s OpenBookUpdate:* PackageManager:W SystemConfig:W ActivityManager:W > "$O/logcat-system.txt" 2>&1
a logcat -d | grep -E 'avc: denied.*openbook|AndroidRuntime.*(FATAL|Process: org.openbook.update)' > "$O/system-problems.txt"

priv=$(grep -c 'PRIVILEGED' "$O/system-package.txt")
reboot_granted=$(grep -c 'android.permission.REBOOT: granted=true' "$O/system-package.txt")
notify_granted=$(grep -c 'android.permission.POST_NOTIFICATIONS: granted=true' "$O/system-package.txt")
idle=$(grep -c 'org.openbook.update' "$O/system-deviceidle.txt")
started_at_boot=$(grep -cE 'BOOT_COMPLETED: regular checks scheduled' "$O/logcat-system-boot.txt")
problems=$(wc -l < "$O/system-problems.txt")
cat > "$O/result.json" <<JSON
{
  "schema": "openbook-update-emulator/1",
  "fingerprint": "$(cat "$O/fingerprint.txt")",
  "engine_device_test": {"exit": $engine_rc, "summary": "$(tail -1 "$O/engine-device-test.txt")"},
  "instrumentation": {"ok": $([ "$app_ok" -ge 1 ] && echo true || echo false), "summary": "$(grep -E '^(OK|FAILURES|Tests run)' "$O/instrumentation.txt" | tr '\n' ' ')"},
  "adapter_in_app_process": $adapter_ok,
  "screenshots": $(ls "$O/screenshots" | wc -l),
  "system_app": {"privileged": $([ "$priv" -ge 1 ] && echo true || echo false),
                 "reboot_granted": $([ "$reboot_granted" -ge 1 ] && echo true || echo false),
                 "notifications_granted_without_first_boot": $([ "$notify_granted" -ge 1 ] && echo true || echo false),
                 "power_save_exempt": $([ "$idle" -ge 1 ] && echo true || echo false),
                 "started_at_boot": $([ "$started_at_boot" -ge 1 ] && echo true || echo false),
                 "problems": $problems}
}
JSON
cat "$O/result.json"
[ $engine_rc = 0 ] && [ "$app_ok" -ge 1 ] && [ "$priv" -ge 1 ] && [ "$reboot_granted" -ge 1 ] \
  && [ "$idle" -ge 1 ] && [ "$started_at_boot" -ge 1 ] && [ "$problems" = 0 ]
