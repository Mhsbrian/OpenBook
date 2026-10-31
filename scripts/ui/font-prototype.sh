#!/usr/bin/env bash
# Try Googlebook's typography on a running OpenBook userdebug device, without rebuilding the image:
# push the OFL Google Sans / Google Sans Flex fonts, a fonts_customization.xml that defines the families
# AOSP 17's SystemUI, Launcher3 and SettingsLib ask for (scripts/ui/fonts-customization.py), and a static
# RRO that sets config_headlineFontFamily / config_bodyFontFamily the way Googlebook's FrameworkDesktopOverlay
# does. Needs `adb root` and `adb remount` (overlayfs; verity off). Reboots the device. VM use only.
#
# usage: font-prototype.sh SERIAL FONTDIR WORKDIR
#   FONTDIR: GoogleSans-VF.ttf, GoogleSans-Italic-VF.ttf, GoogleSansFlex-VF.ttf from github.com/google/fonts
#   WORKDIR: scratch dir for the generated XML and the overlay APK
# Env: ADB, AOSP (default ~/anybook/aosp/src, for aapt2, zipalign, signapk, framework-res and the test key),
#      FRAMEWORK_RES (default: the anybook_vsoc_x86_64 product's framework-res.apk)
set -euo pipefail
S=$1; F=$2; W=$3; HERE=$(cd "$(dirname "$0")" && pwd)
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
AOSP=${AOSP:-$HOME/anybook/aosp/src}; B=$AOSP/out/host/linux-x86; K=$AOSP/build/make/target/product/security
FRES=${FRAMEWORK_RES:-$AOSP/out/target/product/anybook_vsoc_x86_64/system/framework/framework-res.apk}
JAVA=$AOSP/prebuilts/jdk/jdk21/linux-x86/bin/java
a(){ "$ADB" -s "$S" "$@"; }
mkdir -p "$W/rro/res/values"

python3 "$HERE/fonts-customization.py" > "$W/fonts_customization.xml"
cat > "$W/rro/AndroidManifest.xml" <<'EOF'
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="dev.openbook.overlay.fonts">
    <application android:hasCode="false" />
    <overlay android:targetPackage="android" android:isStatic="true" android:priority="300" />
</manifest>
EOF
cat > "$W/rro/res/values/config.xml" <<'EOF'
<resources>
    <string name="config_headlineFontFamily" translatable="false">google-sans</string>
    <string name="config_headlineFontFamilyMedium" translatable="false">google-sans-medium</string>
    <string name="config_bodyFontFamily" translatable="false">google-sans-text</string>
    <string name="config_bodyFontFamilyMedium" translatable="false">google-sans-text-medium</string>
</resources>
EOF
( cd "$W/rro"
  "$B/bin/aapt2" compile --dir res -o res.zip
  "$B/bin/aapt2" link -I "$FRES" --manifest AndroidManifest.xml --min-sdk-version 37 --target-sdk-version 37 \
    -o unsigned.apk res.zip
  "$B/bin/zipalign" -f 4 unsigned.apk aligned.apk
  "$JAVA" -Djava.library.path="$B/lib64" -jar "$B/framework/signapk.jar" --min-sdk-version 37 \
    "$K/testkey.x509.pem" "$K/testkey.pk8" aligned.apk OpenBookFontsOverlay.apk )

a root >/dev/null; sleep 2; a wait-for-device; a remount
a shell mkdir -p /product/fonts /product/overlay/OpenBookFontsOverlay
for f in GoogleSans-VF.ttf GoogleSans-Italic-VF.ttf GoogleSansFlex-VF.ttf; do a push "$F/$f" /product/fonts/; done
a push "$W/fonts_customization.xml" /product/etc/fonts_customization.xml
a push "$W/rro/OpenBookFontsOverlay.apk" /product/overlay/OpenBookFontsOverlay/
a shell 'chmod 644 /product/fonts/*.ttf /product/etc/fonts_customization.xml /product/overlay/OpenBookFontsOverlay/*.apk;
         restorecon -R /product/fonts /product/etc/fonts_customization.xml /product/overlay/OpenBookFontsOverlay'
a reboot
