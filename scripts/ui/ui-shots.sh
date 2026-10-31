#!/usr/bin/env bash
# Screenshots of the desktop surfaces a font/theme change touches, from a booted userdebug device, so two
# builds (or before/after a change) can be compared side by side: desktop and taskbar, Settings window,
# Quick Settings, notification shade, all apps. Also records the font config the device actually loaded.
#
# usage: ui-shots.sh SERIAL OUTDIR
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb); set ANDROID_ADB_SERVER_PORT for a private server.
set -euo pipefail
S=$1; O=$2; mkdir -p "$O"
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
a(){ "$ADB" -s "$S" "$@"; }
sh_(){ a shell "$@" | tr -d '\r'; }
shot(){ sleep "${2:-3}"; a exec-out screencap -p > "$O/$1.png"; echo "$1.png"; }

for _ in $(seq 150); do [ "$(sh_ getprop sys.boot_completed)" = 1 ] && break; sleep 2; done
sleep "${UI_SETTLE:-20}"
sh_ input keyevent KEYCODE_WAKEUP; sh_ wm dismiss-keyguard; sleep 2
sh_ cmd statusbar collapse
shot desktop
sh_ am start -W -n com.android.settings/.Settings >/dev/null
shot settings 5
sh_ cmd statusbar expand-settings
shot quick-settings
sh_ cmd statusbar collapse; sleep 1
sh_ cmd statusbar expand-notifications
shot notifications
sh_ cmd statusbar collapse
sh_ input keyevent KEYCODE_ALL_APPS
shot all-apps
sh_ input keyevent KEYCODE_ESCAPE
{
  echo "# $(sh_ getprop ro.build.fingerprint)"
  echo "ro.surface_flinger.supports_background_blur=$(sh_ getprop ro.surface_flinger.supports_background_blur)"
  echo "## /product/etc/fonts_customization.xml families"
  { sh_ 'cat /product/etc/fonts_customization.xml 2>/dev/null' | grep -o 'name="[^"]*"' | tr '\n' ' '; } || true; echo
  echo "## /product/fonts"
  sh_ 'ls -l /product/fonts 2>/dev/null' || true
  echo "## enabled overlays targeting android"
  sh_ cmd overlay list android | grep -F '[x]' || true
  echo "## config_headlineFontFamily / config_bodyFontFamily as resolved"
  sh_ cmd overlay lookup android android:string/config_headlineFontFamily 2>/dev/null || true
  sh_ cmd overlay lookup android android:string/config_bodyFontFamily 2>/dev/null || true
} > "$O/ui-state.txt"
