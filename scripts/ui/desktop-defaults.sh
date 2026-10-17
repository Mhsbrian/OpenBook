#!/usr/bin/env bash
# Checks the clean default desktop (ANAL-206) on a booted userdebug device with a fresh /data: no search box or
# QuickSearchBox, the partner layout's taskbar pins, touch, keypress and screenshot sounds off, and the lock sound
# left on. Prints one PASS/FAIL line per check (also to OUTDIR/defaults-check.txt) and keeps the raw outputs.
# Run it before opening any app, so the taskbar shows the pins alone.
#
# usage: desktop-defaults.sh SERIAL OUTDIR
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb); set ANDROID_ADB_SERVER_PORT for a private server.
#      EXPECT_PINS: the taskbar's packages in order (default: Files, Settings, WebView Shell, Calendar, Gallery,
#      Camera). Camera only when the device has a camera feature; otherwise Camera2 hides itself and drops out.
set -euo pipefail
S=$1; O=$2; mkdir -p "$O"
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
a(){ "$ADB" -s "$S" "$@"; }
sh_(){ a shell "$@" | tr -d '\r'; }
R=$O/defaults-check.txt; : > "$R"; fails=0
chk(){ local ok=$1; shift; if [ "$ok" = 1 ]; then echo "PASS $*"; else echo "FAIL $*"; fails=$((fails + 1)); fi | tee -a "$R"; }
is(){ [ "$1" = "$2" ] && echo 1 || echo 0; }

for _ in $(seq 150); do [ "$(sh_ getprop sys.boot_completed)" = 1 ] && break; sleep 2; done
a root >/dev/null 2>&1 || true; sleep 2; timeout 60 "$ADB" -s "$S" wait-for-device
sleep "${DEFAULTS_SETTLE:-20}"
sh_ input keyevent KEYCODE_WAKEUP; sh_ wm dismiss-keyguard; sleep 3
echo "# $(sh_ getprop ro.build.fingerprint)" | tee -a "$R"

# Search box and QuickSearchBox.
qsb=$(sh_ pm path com.android.quicksearchbox || true)
chk "$(is "$qsb" "")" "QuickSearchBox not installed (pm path: '${qsb}')"
gs=$(sh_ cmd package query-activities --brief -a android.search.action.GLOBAL_SEARCH | grep -c / || true)
chk "$(is "$gs" 0)" "no global search activity ($gs)"
sh_ dumpsys appwidget > "$O/appwidget.txt"
w=$(grep -c 'quicksearchbox' "$O/appwidget.txt" || true)
chk "$(is "$w" 0)" "no QuickSearchBox widget bound (dumpsys appwidget: $w lines)"
for _ in 1 2 3; do sh_ uiautomator dump /data/local/tmp/ui.xml >/dev/null 2>&1 && break; sleep 2; done
sh_ cat /data/local/tmp/ui.xml > "$O/home-ui.xml"
hv=$(grep -o 'AppWidgetHostView\|quicksearchbox\|text="Search"' "$O/home-ui.xml" | wc -l)
chk "$(is "$hv" 0)" "Home has no search widget or Search button (uiautomator: $hv nodes)"
sh_ cmd overlay list > "$O/overlays.txt"
for p in launcher latinime settingsprovider; do
  chk "$(grep -qF "[x] dev.anybook.overlay.desktop.$p" "$O/overlays.txt" && echo 1 || echo 0)" "overlay dev.anybook.overlay.desktop.$p enabled"
done

# Taskbar pins from the partner customization package.
pr=$(sh_ cmd package query-receivers --brief -a com.android.launcher3.action.PARTNER_CUSTOMIZATION | grep / || true)
chk "$(is "$pr" dev.anybook.desktop.partner/.PartnerCustomization)" "partner customization package found ($pr)"
sh_ dumpsys activity service com.android.launcher3/com.android.quickstep.TouchInteractionService > "$O/launcher.txt" 2>&1 || true
pins=$(grep -m1 -o 'shownHotseatItems=\[[^]]*\]' "$O/launcher.txt" | sed 's/shownHotseatItems=//' || true)
cam=$(sh_ pm list features | grep -cE 'feature:android.hardware.camera(\.front|\.external)?$' || true)
want=${EXPECT_PINS:-"[com.android.documentsui, com.android.settings, org.chromium.webview_shell, com.android.calendar, com.android.gallery3d$([ "$cam" -gt 0 ] && echo ", com.android.camera2")]"}
chk "$(is "$pins" "$want")" "taskbar pins $pins (want $want; camera features: $cam)"
sh_ logcat -d -b main | grep -E 'DefaultLayoutParser|AutoInstalls|LoaderTask: loading default|Favorite not found' > "$O/layout-log.txt" || true

# Sounds.
se=$(sh_ settings get system sound_effects_enabled)
chk "$(is "$se" 0)" "touch sounds off (system sound_effects_enabled=$se)"
ls=$(sh_ settings get system lockscreen_sounds_enabled)
chk "$(is "$ls" 1)" "lock sounds unchanged (system lockscreen_sounds_enabled=$ls)"
kb=$(sh_ cmd overlay lookup com.android.inputmethod.latin com.android.inputmethod.latin:bool/config_default_sound_enabled)
chk "$(is "$kb" false)" "on-screen keyboard keypress sound default off (LatinIME config_default_sound_enabled=$kb)"
fl=$(sh_ aflags list 2>/dev/null | grep -F 'com.android.systemui.screenshot_remove_nonforced_sound' | awk '{print $2}' || true)
chk "$(is "$fl" enabled)" "screenshot shutter sound only when forced (com.android.systemui.screenshot_remove_nonforced_sound=$fl)"
# Take a screenshot: SystemUI must not create its non-forced shutter MediaPlayer.
sui=$(sh_ pidof com.android.systemui || true); suid=$(sh_ stat -c %u "/proc/$sui" 2>/dev/null || true)
sh_ input keyevent KEYCODE_SYSRQ; sleep 4; sh_ input keyevent KEYCODE_ESCAPE || true; sleep 1
sh_ dumpsys audio > "$O/audio.txt"
mp=$(grep -E 'new player piid:' "$O/audio.txt" | grep -E "uid/pid:${suid:-x}/" | grep -c 'MediaPlayer' || true)
grep -E 'new player piid:' "$O/audio.txt" > "$O/audio-new-players.txt" || true
chk "$(is "$mp" 0)" "no SystemUI MediaPlayer after a screenshot (uid ${suid:-?}: $mp)"

sh_ logcat -d -b crash > "$O/crash.txt" || true
cr=$(grep -c . "$O/crash.txt" || true)
chk "$(is "$cr" 0)" "crash buffer empty ($cr lines)"
echo "$fails failed" | tee -a "$R"
[ "$fails" = 0 ]
