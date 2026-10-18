#!/usr/bin/env bash
# Try the document fonts (ANAL-208) on a running OpenBook userdebug device without rebuilding it: push the desktop
# fonts and the document fonts to /product/fonts, the committed fonts_customization.xml to /product/etc, and the
# device's own /system/etc/fonts.xml rewritten by fonts-customization.py --legacy-fonts-xml (what the
# frameworks/base patch does at build time). Needs `adb root` and `adb remount` (overlayfs; verity off). Reboots
# the device. VM use only.
#
# usage: doc-fonts-push.sh SERIAL WORKDIR
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb)
set -euo pipefail
S=$1; W=$2; HERE=$(cd "$(dirname "$0")" && pwd); F=$HERE/../../device/anybook/common/desktop/fonts
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
a(){ "$ADB" -s "$S" "$@"; }
mkdir -p "$W"
booted(){ a wait-for-device; until [ "$(a shell getprop sys.boot_completed | tr -d '\r')" = 1 ]; do sleep 2; done; }
a root >/dev/null; sleep 2; a wait-for-device
# The first remount on a device only turns verity off; it takes effect after a reboot.
if a remount 2>&1 | tee "$W/remount.log" | grep -q 'reboot'; then
  a reboot; sleep 5; booted; a root >/dev/null; sleep 2; a wait-for-device; a remount
fi
a pull /system/etc/fonts.xml "$W/fonts.xml.device"
python3 -I "$HERE/fonts-customization.py" --legacy-fonts-xml "$W/fonts.xml.device" > "$W/fonts.xml"
python3 -I "$HERE/fonts-customization.py" --check "$F/fonts_customization.xml"
a shell mkdir -p /product/fonts
for f in "$F"/googlesans*/*.ttf "$F"/documents/*/*.ttf; do a push "$f" /product/fonts/ >/dev/null; done
a push "$F/fonts_customization.xml" /product/etc/fonts_customization.xml
a push "$W/fonts.xml" /system/etc/fonts.xml
a shell 'chmod 644 /product/fonts/*.ttf /product/etc/fonts_customization.xml /system/etc/fonts.xml;
         restorecon -R /product/fonts /product/etc/fonts_customization.xml /system/etc/fonts.xml; ls -lZ /product/fonts'
a reboot
