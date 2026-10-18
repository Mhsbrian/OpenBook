#!/usr/bin/env bash
# Check OpenBook's brand assets on a booted userdebug device (ANAL-207): wallpapers and their dynamic colour, the
# wallpaper picker, the pointer theme, the sounds. Reboots nothing; changes the wallpaper and the dark theme and puts
# both back (Folio light, dark theme off) at the end.
# usage: device-checks.sh SERIAL OUT          (adb root first; ANDROID_ADB_SERVER_PORT for a private server)
# Writes into OUT: overlays.txt, desktop-{light,dark}.png, monet-device.tsv, wallpaper-<name>.png,
# picker-*.png, pointers/ (+ pointers.tsv), input.txt, sounds.txt, and device-checks.log (PASS/FAIL lines).
set -uo pipefail
S=${1:?usage: device-checks.sh SERIAL OUT}; OUT=${2:?}; R=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$OUT/pointers"; LOG=$OUT/device-checks.log; : > "$LOG"
a(){ adb -s "$S" "$@"; }
sh_(){ a shell "$@" | tr -d '\r'; }
log(){ echo "$*" | tee -a "$LOG"; }
check(){ if [ "$2" = "$3" ]; then log "PASS $1: $2"; else log "FAIL $1: got '$2', want '$3'"; fi; }
shot(){ a exec-out screencap -p > "$OUT/$1.png"; }
JAR=${BRAND_PROBE_JAR:-$HOME/anybook/b6/brand-probe.jar}
[ -s "$JAR" ] || "$R/scripts/brand/probe/build.sh" "$JAR" >/dev/null
a push "$JAR" /data/local/tmp/brand-probe.jar >/dev/null
probe(){ a shell CLASSPATH=/data/local/tmp/brand-probe.jar app_process /system/bin BrandProbe "$@" | tr -d '\r'; }
# WallpaperManagerService checks that the caller's package belongs to its uid: root has no package, system has "android"
setwp(){ a shell "su 1000 sh -c 'CLASSPATH=/data/local/tmp/brand-probe.jar app_process /system/bin BrandProbe set-wallpaper $1'" |
         tr -d '\r'; }
# The dynamic colours as apps see them now: SystemUI's fabricated overlays, which only system_server's lookup includes
# (app_process, BrandProbe's palette, loads only the static overlays).
COLORS="system_accent1_600 system_primary_light system_secondary_light system_tertiary_light \
  system_primary_container_light system_surface_container_light system_on_surface_light system_primary_dark \
  system_secondary_dark system_tertiary_dark system_primary_container_dark system_surface_container_dark"
live(){ for c in $COLORS; do printf '%s\t%s\n' "$c" "$(sh_ cmd overlay lookup android android:color/$c | grep -o '#ff[0-9a-f]*' | sed 's/#ff/#/')"; done; }
seed(){ a shell dumpsys activity service com.android.systemui/.SystemUIService 2>/dev/null | tr -d '\r' |
        sed -n 's/.*mMainWallpaperColor=\([0-9a-f]*\).*/\1/p' | tail -1; }

# --- installed files and overlays
{ for f in /product/media/bootanimation.zip /product/media/audio/*/OpenBook_*.ogg; do sh_ ls -la "$f"; done
  sh_ cmd overlay list android; sh_ cmd overlay list com.android.providers.settings
  for r in android:drawable/default_wallpaper android:drawable/pointer_arrow_vector android:drawable/pointer_hand_vector; do
    echo "lookup $r: $(sh_ cmd overlay lookup android "$r")"; done
  sh_ pm list packages -f dev.anybook; } > "$OUT/overlays.txt" 2>&1
check "pointer overlay enabled" "$(sh_ cmd overlay list android | grep -c '\[x\] dev.anybook.overlay.pointer')" 1
check "sounds overlay enabled" "$(sh_ cmd overlay list com.android.providers.settings | grep -c '\[x\] dev.anybook.overlay.sounds.settingsprovider')" 1
check "boot animation installed" "$(sh_ ls /product/media/bootanimation.zip)" /product/media/bootanimation.zip
check "default_wallpaper resolves to the overlay" \
  "$(sh_ cmd overlay lookup android android:drawable/default_wallpaper | grep -o 'default_wallpaper.jpg' | head -1)" default_wallpaper.jpg

# --- the default wallpaper, light and dark, and the dynamic colour each gives
sh_ cmd uimode night no >/dev/null; sleep 5
shot desktop-light; live > "$OUT/palette-default.tsv"
echo "default seed (SystemUI mMainWallpaperColor): $(seed)" >> "$LOG"
sh_ cmd uimode night yes >/dev/null; sleep 5
shot desktop-dark
sh_ cmd uimode night no >/dev/null; sleep 3
a shell dumpsys activity service com.android.systemui/.SystemUIService 2>/dev/null | tr -d '\r' |
  grep -E "mSystemColors=|mMainWallpaperColor=|mColorScheme=|mThemeStyle=" > "$OUT/theme-default.txt"

# --- each wallpaper of the set: set it as the picker would (the 2880x1800 image), record the seed and the
# palette SystemUI derives, take the desktop
printf 'wallpaper\tseed_device\t%s\n' "$(echo $COLORS | tr ' ' '\t')" > "$OUT/monet-device.tsv"
for f in "$R"/assets/wallpapers/2880x1800/*.jpg; do
  n=$(basename "$f" .jpg)
  a push "$f" /data/local/tmp/wp.jpg >/dev/null
  setwp /data/local/tmp/wp.jpg >> "$LOG"
  sleep 6
  shot "wallpaper-$n"
  sd=$(seed)
  printf '%s\t#%s\t%s\n' "$n" "${sd: -6}" "$(live | cut -f2 | tr '\n' '\t' | sed 's/\t$//')" >> "$OUT/monet-device.tsv"
done
a push "$R/assets/wallpapers/2880x1800/openbook-folio-light.jpg" /data/local/tmp/wp.jpg >/dev/null
setwp /data/local/tmp/wp.jpg >> "$LOG"; sleep 4

# --- the wallpaper picker lists the OpenBook category: Wallpaper & style -> (More) wallpapers -> Collections -> OpenBook
ui(){ a shell uiautomator dump /data/local/tmp/ui.xml >/dev/null 2>&1; a pull /data/local/tmp/ui.xml "$OUT/$1.xml" >/dev/null 2>&1; }
tap_text(){ # file text: tap the centre of the first node with that text
  local b; b=$(grep -o "text=\"$2\"[^>]*bounds=\"[^\"]*\"" "$OUT/$1.xml" 2>/dev/null | grep -o 'bounds="[^"]*"' | head -1)
  [ -n "$b" ] || return 1
  set -- $(echo "$b" | tr -dc '0-9,[]' | tr '[],' '   ')
  sh_ input tap $(( ($1 + $3) / 2 )) $(( ($2 + $4) / 2 ))
}
sh_ am start -W -a android.intent.action.SET_WALLPAPER -p com.android.wallpaper >> "$LOG" 2>&1; sleep 6
shot picker-home; ui picker-home
# the button is "More wallpapers" when the home page shows a wallpaper carousel, "Wallpapers" otherwise
{ tap_text picker-home "More wallpapers" || tap_text picker-home Wallpapers; } && sleep 5
shot picker-collections; ui picker-collections
check "picker lists the OpenBook collection" "$(grep -c 'text="OpenBook"' "$OUT/picker-collections.xml")" 1
if tap_text picker-collections OpenBook; then
  sleep 5; shot picker-openbook; ui picker-openbook
  log "OpenBook collection shows: $(grep -o 'content-desc="[^"]*"' "$OUT/picker-openbook.xml" | sort -u | tr '\n' ' ')"
fi
sh_ input keyevent KEYCODE_HOME; sleep 2

# --- pointer theme: the framework's own rendering of every icon in every fill and stroke style, plus input state
a shell rm -rf /data/local/tmp/ptr; a shell mkdir -p /data/local/tmp/ptr
probe pointers /data/local/tmp/ptr 2 > "$OUT/pointers.tsv"
a pull /data/local/tmp/ptr/. "$OUT/pointers/" >/dev/null
log "pointer icons rendered: $(($(wc -l < "$OUT/pointers.tsv") - 1)) (types x 6 fills x 3 strokes)"
a shell dumpsys input > "$OUT/input.txt" 2>&1

# --- sounds
{ for k in ringtone notification_sound alarm_alert; do echo "system $k = $(sh_ settings get system $k)"; done
  for k in lock_sound unlock_sound trusted_sound low_battery_sound charging_started_sound \
           wireless_charging_started_sound; do echo "global $k = $(sh_ settings get global $k)"; done
  for k in sound_effects_enabled; do echo "system $k = $(sh_ settings get system $k)"; done
  for k in ro.config.ringtone ro.config.notification_sound ro.config.alarm_alert; do echo "$k = $(sh_ getprop $k)"; done
  sh_ "content query --uri content://media/internal/audio/media \
    --projection _id:_display_name:title:duration:is_ringtone:is_notification:is_alarm --where \"_display_name LIKE 'OpenBook%'\""
} > "$OUT/sounds.txt" 2>&1
check "ringtone default" "$(sh_ getprop ro.config.ringtone)" OpenBook_Pages.ogg
check "lock sound" "$(sh_ settings get global lock_sound)" /product/media/audio/ui/OpenBook_Lock.ogg
check "MediaProvider indexed the set" "$(grep -c '_display_name=OpenBook_' "$OUT/sounds.txt")" 8
log "done"
