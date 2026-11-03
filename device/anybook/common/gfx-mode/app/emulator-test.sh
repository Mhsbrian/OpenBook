#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# OpenBook Graphics 1.1's games rule (ANAL-312, docs/nvidia-offload-ruby.md) on Google's Android Desktop emulator
# (API 37.1, userdebug, a headless system user; Android SDK License, local use only), in its own AVD with its own
# ports and adb server. Kills only the emulator it started.
#   1. upgrade  OpenBook Graphics 1.0 (OLD_APK, the image's) as a privileged system app with its allow-list and
#               "all apps" on, as on the G14; then the signed 1.1 and its allow-list in its place
#               (/system/priv-app/OpenBookGraphics-v2, as build-gfx-mode-candidate.py names it) and a restart with
#               the same data, as an OpenBook image update brings it
#   2. rule     after that boot: privileged, WRITE_SECURE_SETTINGS granted, "all apps" replaced once, the
#               allow-list = the games installed (appCategory, isGame), the periodic job scheduled; a game installed
#               later is not listed until the job runs, then is; a removed game is dropped
#   3. screen   the owner's choices on Apps on the NVIDIA GPU (uiautomator) land in Android's lists; screenshots
#   4. android  with a driver package offered (root sets ro.gfx.driver.0 to a package that is not installed), each
#               test app's own process log shows Android's choice (GraphicsEnvironment): a game and an app chosen
#               for the NVIDIA GPU look for the driver package; another app and a game chosen for the Radeon do not
# The emulator's SELinux policy has no OpenBook domain, so here the app runs as Google's priv_app; the domain and
# its policy are for the Ruby VM check of the release. Writes OUTDIR/result.json and the evidence beside it.
#
# usage: emulator-test.sh OUTDIR BUILD_DIR OLD_APK   (BUILD_DIR: build.sh output; OLD_APK: 1.0, pins.json's 485b1b1c…)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
O=${1:?outdir}; B=${2:?build dir}; OLD=${3:?1.0 apk}
NEW=$B/OpenBookGraphics.apk
for f in "$NEW" "$OLD"; do [ -f "$f" ] || { echo "missing $f" >&2; exit 2; }; done
OLD_COMMIT=f53b1319db11f70265454d1984f31e13a325540d   # 1.0's built_from_commit (ruby/pins.json before 1.1)
eval "$("$HERE/../../updater/app/toolchain.sh" --env)"
BT=$ANDROID_HOME/build-tools/37.0.0; JAR=$ANDROID_HOME/platforms/android-37.0/android.jar
A=${ANYBOOK_HOME:-$HOME/anybook}; S=$A/android-sdk
D=$A/desktop/avd; AVD=openbook-graphics-test; P=${OBG_EMU_PORT:-5620}
SYSIMG=system-images/android-37.1/android-desktop/x86_64/
[ -f "$S/$SYSIMG/system.img" ] || { echo "the API 37.1 desktop image is missing (scripts/desktop-ref-emulator.sh)" >&2; exit 2; }
mkdir -p "$O/apps" "$D/$AVD.avd" "$A/desktop/android-user"
sha256sum "$NEW" "$OLD" > "$O/inputs.sha256"

# Test apps without code: an android.app.Activity in the launcher, so starting one starts its process (and
# GraphicsEnvironment's choice) and nothing else.
keytool -genkeypair -keystore "$O/apps/test.jks" -storepass android -keypass android -alias t -keyalg RSA \
  -keysize 2048 -validity 3650 -dname CN=OpenBook-games-test > /dev/null 2>&1
mkapp() {  # NAME LABEL APPLICATION_ATTRIBUTES
  local d=$O/apps/$1
  mkdir -p "$d"
  cat > "$d/AndroidManifest.xml" <<XML
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="org.openbook.test.$1"
    android:versionCode="1" android:versionName="1">
  <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="37" />
  <application android:label="$2" android:hasCode="false" $3>
    <activity android:name="android.app.Activity" android:exported="true">
      <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
      </intent-filter>
    </activity>
  </application>
</manifest>
XML
  "$BT/aapt2" link --manifest "$d/AndroidManifest.xml" -I "$JAR" -o "$d/unsigned.apk" &&
    "$BT/zipalign" -f 4 "$d/unsigned.apk" "$d/aligned.apk" &&
    "$BT/apksigner" sign --ks "$O/apps/test.jks" --ks-pass pass:android --out "$O/apps/$1.apk" "$d/aligned.apk" 2> /dev/null
}
mkapp game "Test Game" 'android:appCategory="game"' &&
  mkapp legacygame "Test Legacy Game" 'android:isGame="true"' &&
  mkapp app "Test App" '' &&
  mkapp chosen "Test Chosen App" 'android:appCategory="productivity"' &&
  mkapp lategame "Test Late Game" 'android:appCategory="game"' || { echo "could not build the test apps" >&2; exit 1; }

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
       ANDROID_EMULATOR_HOME=$A/desktop/android-user ANDROID_ADB_SERVER_PORT=${OBG_ADB_SERVER_PORT:-5059}
ADB=$S/platform-tools/adb
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
root_remount() {
  a root > /dev/null 2>&1; sleep 3; a wait-for-device
  a remount > "$O/remount-$1.txt" 2>&1
  if grep -qi reboot "$O/remount-$1.txt"; then
    a reboot; sleep 10; a wait-for-device; boot; a root > /dev/null 2>&1; sleep 3; a wait-for-device
    a remount >> "$O/remount-$1.txt" 2>&1
  fi
}
# The desktop runs a headless system user (0); the owner is the first full user. Bring the owner to the front.
owner_front() {
  OWNER=$(sh_ pm list users | sed -n 's/.*UserInfo{\([1-9][0-9]*\):.*/\1/p' | head -1)
  a shell am switch-user "$OWNER"
  for _ in $(seq 1 60); do [ "$(sh_ am get-current-user)" = "$OWNER" ] && break; sleep 2; done
  sleep "${1:-30}"
}
restart() { a reboot; sleep 10; a wait-for-device; boot || { echo "no boot ($1)" >&2; exit 1; }; owner_front 60; }
g() { sh_ settings get global "$1"; }
"$ADB" start-server > /dev/null 2>&1
boot || { echo "the emulator did not boot" >&2; exit 1; }
sleep 20
sh_ getprop ro.build.fingerprint > "$O/fingerprint.txt"
sh_ getprop ro.gfx.driver.0 > "$O/gfx-driver-before.txt"

# 1. The image's 1.0, "all apps" on, the owner's apps; then 1.1 as an image update brings it.
root_remount v1
a shell mkdir -p /system/priv-app/OpenBookGraphics-v1 /system/etc/default-permissions
a push "$OLD" /system/priv-app/OpenBookGraphics-v1/OpenBookGraphics.apk > /dev/null
git -C "$REPO" show "$OLD_COMMIT:device/anybook/common/gfx-mode/ruby/privapp-permissions-org.openbook.graphics.xml" \
  > "$O/privapp-1.0.xml"
a push "$O/privapp-1.0.xml" /system/etc/permissions/privapp-permissions-org.openbook.graphics.xml > /dev/null
a push "$REPO/device/anybook/common/gfx-mode/ruby/default-permissions-org.openbook.graphics.xml" /system/etc/default-permissions/ > /dev/null
a shell chmod 644 /system/priv-app/OpenBookGraphics-v1/OpenBookGraphics.apk \
  /system/etc/permissions/privapp-permissions-org.openbook.graphics.xml \
  /system/etc/default-permissions/default-permissions-org.openbook.graphics.xml
a shell sync
a shell setprop persist.logd.size 16M
restart "1.0"
for n in game legacygame app chosen; do a install --user "$OWNER" "$O/apps/$n.apk" >> "$O/install-apps.txt" 2>&1; done
a shell settings put global updatable_driver_all_apps 1
a shell settings put global updatable_driver_production_opt_out_apps com.android.chrome
sh_ dumpsys package org.openbook.graphics | grep -E 'versionCode|codePath' > "$O/v1-package.txt"
{ for k in updatable_driver_all_apps updatable_driver_production_allowlist updatable_driver_production_opt_in_apps \
             updatable_driver_production_opt_out_apps; do echo "$k=$(g $k)"; done; } > "$O/settings-before.txt"

root_remount v2
a shell rm -rf /system/priv-app/OpenBookGraphics-v1
a shell mkdir -p /system/priv-app/OpenBookGraphics-v2
a push "$NEW" /system/priv-app/OpenBookGraphics-v2/OpenBookGraphics.apk > /dev/null
a push "$REPO/device/anybook/common/gfx-mode/ruby/privapp-permissions-org.openbook.graphics.xml" /system/etc/permissions/ > /dev/null
a shell chmod 644 /system/priv-app/OpenBookGraphics-v2/OpenBookGraphics.apk /system/etc/permissions/privapp-permissions-org.openbook.graphics.xml
a shell sync
a logcat -c
restart "1.1"
a logcat -d -s OpenBookGraphics:* > "$O/logcat-boot.txt" 2>&1

# 2. The rule after the update.
sh_ dumpsys package org.openbook.graphics > "$O/v2-package.txt"
{ for k in updatable_driver_all_apps updatable_driver_production_allowlist updatable_driver_production_opt_in_apps \
             updatable_driver_production_opt_out_apps; do echo "$k=$(g $k)"; done; } > "$O/settings-after-update.txt"
sh_ dumpsys jobscheduler | grep -A8 'org.openbook.graphics/.GamesJob' > "$O/jobs.txt"
allow_boot=$(g updatable_driver_production_allowlist)
all_apps_after=$(g updatable_driver_all_apps)
a install --user "$OWNER" "$O/apps/lategame.apk" >> "$O/install-apps.txt" 2>&1
sleep 15
allow_before_job=$(g updatable_driver_production_allowlist)
a shell cmd jobscheduler run -f -u "$OWNER" org.openbook.graphics 312 > "$O/job-run.txt" 2>&1
sleep 15
allow_after_job=$(g updatable_driver_production_allowlist)
a uninstall --user "$OWNER" org.openbook.test.legacygame >> "$O/install-apps.txt" 2>&1
sleep 15
allow_after_removal=$(g updatable_driver_production_allowlist)
a logcat -d -s OpenBookGraphics:* > "$O/logcat-rule.txt" 2>&1
printf 'boot=%s\nlategame_installed_before_job=%s\nafter_job=%s\nafter_legacygame_removed=%s\n' \
  "$allow_boot" "$allow_before_job" "$allow_after_job" "$allow_after_removal" > "$O/allowlist.txt"

# 4a. Android's choice for each test app, before the owner's choices: the driver package offered by root.
a root > /dev/null 2>&1; sleep 3; a wait-for-device
a shell setprop log.tag.GraphicsEnvironment VERBOSE
[ -n "$(cat "$O/gfx-driver-before.txt")" ] || a shell setprop ro.gfx.driver.0 org.openbook.nvk.absent
offered=$(sh_ getprop ro.gfx.driver.0)
choice() {  # PACKAGE TAG: one start of the app's process, its GraphicsEnvironment lines
  local pkg=org.openbook.test.$1 pid=
  a shell am force-stop --user "$OWNER" "$pkg"
  a logcat -c
  a shell am start -W --user "$OWNER" -n "$pkg/android.app.Activity" > "$O/start-$2.txt" 2>&1
  sleep 3
  pid=$(sh_ pidof "$pkg")
  if [ -n "$pid" ]; then a logcat -d --pid="$pid" -s GraphicsEnvironment:V > "$O/ge-$2.txt" 2>&1
  else a logcat -d -s GraphicsEnvironment:V > "$O/ge-$2.txt" 2>&1; fi
  a shell am force-stop --user "$OWNER" "$pkg"
}
looks_for_driver() { grep -q "updatable driver package '$offered' not installed" "$O/ge-$1.txt"; }
choice game game-auto
choice lategame lategame-auto
choice app app-auto
choice chosen chosen-auto

# 3. The owner's choices on the screen: Test Chosen App on the NVIDIA GPU, Test Game on the Radeon.
tap_tag() {  # TAG: find the node whose resource-id is TAG (scrolling down if needed) and tap its centre
  local b
  for _ in 1 2 3 4 5 6; do
    a shell uiautomator dump /sdcard/ui.xml > /dev/null 2>&1
    a pull /sdcard/ui.xml "$O/ui.xml" > /dev/null 2>&1
    b=$(python3 -I - "$O/ui.xml" "$1" <<'PY'
import re, sys, xml.etree.ElementTree as ET
for n in ET.parse(sys.argv[1]).iter("node"):
    if n.get("resource-id") == sys.argv[2]:
        x1, y1, x2, y2 = map(int, re.findall(r"\d+", n.get("bounds")))
        print((x1 + x2) // 2, (y1 + y2) // 2)
        break
PY
)
    if [ -n "$b" ]; then a shell input tap $b; return 0; fi
    a shell input swipe 960 900 960 300 400
    sleep 1
  done
  return 1
}
a shell am start -W --user "$OWNER" -n org.openbook.graphics/.ui.MainActivity > "$O/launch.txt" 2>&1
sleep 8
a exec-out screencap -p > "$O/screen-main.png"
ui_open=false; ui_nvidia=false; ui_radeon=false
tap_tag apps-open && ui_open=true
sleep 6
a exec-out screencap -p > "$O/screen-apps.png"
tap_tag choice-org.openbook.test.chosen-nvidia && ui_nvidia=true
sleep 3
tap_tag choice-org.openbook.test.game-radeon && ui_radeon=true
sleep 3
a exec-out screencap -p > "$O/screen-apps-chosen.png"
opt_in=$(g updatable_driver_production_opt_in_apps); opt_out=$(g updatable_driver_production_opt_out_apps)
printf 'opt_in=%s\nopt_out=%s\n' "$opt_in" "$opt_out" > "$O/settings-after-choices.txt"

# 4b. Android's choice after the owner's choices.
choice game game-radeon
choice chosen chosen-nvidia

a logcat -d | grep -E 'avc: denied.*openbook|AndroidRuntime.*(FATAL|Process: org.openbook.graphics)|FATAL EXCEPTION' > "$O/problems.txt"
a logcat -d -s OpenBookGraphics:* > "$O/logcat-final.txt" 2>&1

bool() { "$@" && echo true || echo false; }
has() { grep -qE "$1" "$2"; }
r_priv=$(bool has 'PRIVILEGED' "$O/v2-package.txt")
r_version=$(bool has 'versionCode=2 ' "$O/v2-package.txt")
r_wss=$(bool has 'android.permission.WRITE_SECURE_SETTINGS: granted=true' "$O/v2-package.txt")
r_reboot=$(bool has 'android.permission.REBOOT: granted=true' "$O/v2-package.txt")
r_v1=$(bool has 'versionCode=1 ' "$O/v1-package.txt")
r_all_before=$(bool has '^updatable_driver_all_apps=1$' "$O/settings-before.txt")
r_replaced=$(bool [ "$all_apps_after" = 0 ])
r_logged=$(bool [ "$(grep -c '"all apps" replaced by the games rule' "$O/logcat-rule.txt")" = 1 ])
r_boot_list=$(bool [ "$allow_boot" = "org.openbook.test.game,org.openbook.test.legacygame" ])
r_job=$(bool has 'PERIODIC|period' "$O/jobs.txt")
r_failsafe=$(bool [ "$allow_before_job" = "org.openbook.test.game,org.openbook.test.legacygame" ])
r_late=$(bool [ "$allow_after_job" = "org.openbook.test.game,org.openbook.test.lategame,org.openbook.test.legacygame" ])
r_removed=$(bool [ "$allow_after_removal" = "org.openbook.test.game,org.openbook.test.lategame" ])
r_optout_kept=$(bool has '^updatable_driver_production_opt_out_apps=com.android.chrome$' "$O/settings-after-update.txt")
r_ui_in=$(bool [ "$opt_in" = "org.openbook.test.chosen" ])
r_ui_out=$(bool [ "$opt_out" = "com.android.chrome,org.openbook.test.game" ])
r_game=$(bool looks_for_driver game-auto)
r_late_ge=$(bool looks_for_driver lategame-auto)
r_app=$(bool has 'App is not on the allowlist for updatable production driver' "$O/ge-app-auto.txt")
r_chosen_before=$(bool has 'App is not on the allowlist for updatable production driver' "$O/ge-chosen-auto.txt")
r_game_radeon=$(bool has 'App opts out for updatable production driver' "$O/ge-game-radeon.txt")
r_chosen_nvidia=$(bool looks_for_driver chosen-nvidia)
problems=$(wc -l < "$O/problems.txt")
cat > "$O/result.json" <<JSON
{
  "schema": "openbook-graphics-games-emulator/1",
  "fingerprint": "$(cat "$O/fingerprint.txt")",
  "apk_sha256": "$(sha256sum "$NEW" | cut -d' ' -f1)",
  "old_apk_sha256": "$(sha256sum "$OLD" | cut -d' ' -f1)",
  "owner_user": "$OWNER",
  "driver_offered_for_the_check": "$offered",
  "upgrade": {"v1_installed": $r_v1, "all_apps_on_before": $r_all_before, "v2_version": $r_version,
              "privileged": $r_priv, "write_secure_settings_granted": $r_wss, "reboot_granted": $r_reboot},
  "rule": {"all_apps_replaced": $r_replaced, "replaced_exactly_once": $r_logged, "boot_allowlist_is_the_games": $r_boot_list,
           "periodic_job": $r_job, "new_game_waits_for_the_sync": $r_failsafe, "job_lists_the_new_game": $r_late,
           "removed_game_dropped": $r_removed, "owner_opt_out_kept": $r_optout_kept},
  "screen": {"opened": $ui_open, "tapped_nvidia": $ui_nvidia, "tapped_radeon": $ui_radeon,
             "opt_in_written": $r_ui_in, "opt_out_written": $r_ui_out},
  "android": {"game_gets_driver": $r_game, "late_game_gets_driver": $r_late_ge, "other_app_stays": $r_app,
              "unchosen_app_stays": $r_chosen_before, "game_chosen_radeon_stays": $r_game_radeon,
              "app_chosen_nvidia_gets_driver": $r_chosen_nvidia},
  "problems": $problems
}
JSON
cat "$O/result.json"
! grep -q false "$O/result.json" && [ "$problems" = 0 ]
