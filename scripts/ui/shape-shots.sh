#!/usr/bin/env bash
# Screenshots and resolved values for the icon shape and wallpaper defaults (ANAL-205), from a booted userdebug
# device, so two builds can be compared: desktop and taskbar, all apps, the Settings home list and Settings' app list.
# Records what the device actually resolved: the framework config_icon_mask / config_useRoundIcon /
# config_wallpaperDimAmount, the persist.wallpapercolors.* properties, Launcher3's shape options, the wallpaper layer
# in SurfaceFlinger and the crash buffer.
#
# usage: shape-shots.sh SERIAL OUTDIR
#   SHAPE_PICK=KEY  afterwards, pick icon shape KEY (circle, square, four_sided_cookie, seven_sided_cookie, arch)
#                   through Launcher3's grid_control provider, the way Wallpaper & style does, take the all-apps and
#                   desktop shots again as pick-<KEY>-*.png, then clear the pick (back to the system mask).
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb); set ANDROID_ADB_SERVER_PORT for a private server.
set -euo pipefail
S=$1; O=$2; mkdir -p "$O"
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
a(){ "$ADB" -s "$S" "$@"; }
sh_(){ a shell "$@" | tr -d '\r'; }
shot(){ sleep "${2:-3}"; a exec-out screencap -p > "$O/$1.png"; echo "$1.png"; }
GRID=content://com.android.launcher3.grid_control
home(){ sh_ input keyevent KEYCODE_ESCAPE; sh_ input keyevent KEYCODE_HOME; sleep 2; }
apps(){ home; sh_ input keyevent KEYCODE_ALL_APPS; shot "$1"; sh_ input keyevent KEYCODE_ESCAPE; }

a root >/dev/null; a wait-for-device
for _ in $(seq 150); do [ "$(sh_ getprop sys.boot_completed)" = 1 ] && break; sleep 2; done
sleep "${UI_SETTLE:-20}"
sh_ input keyevent KEYCODE_WAKEUP; sh_ wm dismiss-keyguard; sleep 2
sh_ cmd statusbar collapse
home; shot desktop
apps all-apps
sh_ am start -W -n com.android.settings/.Settings >/dev/null
shot settings 5
sh_ am start -W -a android.settings.MANAGE_ALL_APPLICATIONS_SETTINGS >/dev/null
shot settings-apps 5
sh_ am force-stop com.android.settings
home

state(){
  echo "# $(sh_ getprop ro.build.fingerprint)"
  echo "## framework values as resolved (cmd overlay lookup)"
  for r in string/config_icon_mask bool/config_useRoundIcon dimen/config_wallpaperDimAmount; do
    echo "$r = $(sh_ cmd overlay lookup android "android:$r" 2>&1)"
  done
  echo "## enabled overlays targeting android"
  sh_ cmd overlay list android | grep -F '[x]' || true
  echo "## properties"
  for p in persist.wallpapercolors.threshold persist.wallpapercolors.max_dark_area; do echo "$p=[$(sh_ getprop "$p")]"; done
  echo "## Launcher3 shape options (is_default marks the one the picker shows as selected)"
  sh_ content query --uri "$GRID/shape_options" --projection shape_key:is_default 2>&1 || true
  echo "## Wallpaper & style (ThemePicker)"
  sh_ pm list packages com.android.wallpaper || true
  echo "## wallpaper layers in SurfaceFlinger"
  sh_ dumpsys SurfaceFlinger | grep -iE -A12 '^\* Layer.*[Ww]allpaper' | grep -iE 'Layer|alpha|color=' | head -20 || true
  echo "## crash buffer"
  sh_ logcat -b crash -d || true
}
state > "$O/shape-state.txt"

if [ -n "${SHAPE_PICK:-}" ]; then
  sh_ content update --uri "$GRID/shape" --bind "shape_key:s:$SHAPE_PICK"
  sleep 3
  apps "pick-$SHAPE_PICK-all-apps"
  home; shot "pick-$SHAPE_PICK-desktop"
  sh_ am start -W -a android.settings.MANAGE_ALL_APPLICATIONS_SETTINGS >/dev/null
  shot "pick-$SHAPE_PICK-settings-apps" 5
  sh_ am force-stop com.android.settings
  { echo "## after picking $SHAPE_PICK"
    sh_ content query --uri "$GRID/shape_options" --projection shape_key:is_default 2>&1 || true
    sh_ content update --uri "$GRID/shape" --bind "shape_key:s:"
    sleep 3
    echo "## after clearing the pick"
    sh_ content query --uri "$GRID/shape_options" --projection shape_key:is_default 2>&1 || true
    echo "## crash buffer"
    sh_ logcat -b crash -d || true
  } > "$O/pick-$SHAPE_PICK.txt"
  apps "pick-cleared-all-apps"
fi
