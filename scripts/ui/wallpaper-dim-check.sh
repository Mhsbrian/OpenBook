#!/usr/bin/env bash
# Measures the wallpaper dim WallpaperService applies by default (config_wallpaperDimAmount, ANAL-205). For each grey
# level it installs a flat grey wallpaper, restarts the framework, takes a screenshot of the empty desktop and reads
# the wallpaper's colour. AOSP dims a wallpaper with neither the dark-text nor the dark-theme hint by
# config_wallpaperDimAmount (0.05), so the screen shows the grey darker than the file; with 0 the two match.
# Userdebug VMs only: it writes /data/system/users/0 as root and restarts the framework (`stop`/`start`). The last
# step removes the test wallpaper again (the default comes back).
#
# usage: wallpaper-dim-check.sh SERIAL OUTDIR [GREY...]      (default greys: 180 206)
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb); set ANDROID_ADB_SERVER_PORT for a private server.
set -euo pipefail
S=$1; O=$2; shift 2; GREYS=("$@"); [ ${#GREYS[@]} -gt 0 ] || GREYS=(180 206)
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
a(){ "$ADB" -s "$S" "$@"; }
sh_(){ a shell "$@" | tr -d '\r'; }
U=/data/system/users/0
mkdir -p "$O"
restart(){
  # The crash buffer is cleared after `stop`: stopping the framework itself logs DeadSystemExceptions.
  sh_ stop; sh_ "$1"; sh_ setprop sys.boot_completed 0; sh_ logcat -b crash -c; sh_ start
  for _ in $(seq 120); do [ "$(sh_ getprop sys.boot_completed)" = 1 ] && break; timeout 2 tail -f /dev/null || true; done
  timeout "${UI_SETTLE:-20}" tail -f /dev/null || true
  sh_ input keyevent KEYCODE_WAKEUP; sh_ wm dismiss-keyguard; sh_ cmd statusbar collapse; sh_ input keyevent KEYCODE_HOME
  timeout 3 tail -f /dev/null || true
}
a root >/dev/null; a wait-for-device
echo "# $(sh_ getprop ro.build.fingerprint)" > "$O/wallpaper-dim.txt"
echo "config_wallpaperDimAmount = $(sh_ cmd overlay lookup android android:dimen/config_wallpaperDimAmount)" >> "$O/wallpaper-dim.txt"
for g in "${GREYS[@]}"; do
  magick -size 1920x1080 "xc:rgb($g,$g,$g)" "PNG24:$O/grey-$g.png"
  a push "$O/grey-$g.png" /data/local/tmp/wp.png >/dev/null
  restart "rm -f $U/wallpaper_info.xml $U/wallpaper $U/wallpaper_orig $U/wallpaper_lock $U/wallpaper_lock_orig; \
           cp /data/local/tmp/wp.png $U/wallpaper_orig; cp /data/local/tmp/wp.png $U/wallpaper; \
           chown system:system $U/wallpaper $U/wallpaper_orig; chmod 600 $U/wallpaper $U/wallpaper_orig; \
           restorecon $U/wallpaper $U/wallpaper_orig"
  a exec-out screencap -p > "$O/screen-grey-$g.png"
  # Red channel (the image is grey) of a 200x200 patch in the middle of the desktop, clear of the status bar,
  # taskbar and widgets: mean, min, max.
  m=$(magick "$O/screen-grey-$g.png" -crop 200x200+860+300 +repage \
        -format '%[fx:round(255*mean.r)] (min %[fx:round(255*minima.r)], max %[fx:round(255*maxima.r)])' info:)
  echo "grey=$g screen=$m (0.95 x grey = $(awk "BEGIN { printf \"%.1f\", $g * 0.95 }"))" | tee -a "$O/wallpaper-dim.txt"
  echo "## crash buffer, grey $g" >> "$O/wallpaper-dim.txt"; sh_ logcat -b crash -d >> "$O/wallpaper-dim.txt" || true
done
restart "rm -f $U/wallpaper_info.xml $U/wallpaper $U/wallpaper_orig /data/local/tmp/wp.png"
echo "## crash buffer since the last framework start" >> "$O/wallpaper-dim.txt"
sh_ logcat -b crash -d >> "$O/wallpaper-dim.txt" || true
