#!/usr/bin/env bash
# Which colour hints android.app.WallpaperColors gives a set of synthetic wallpapers on a booted device, so a change
# to persist.wallpapercolors.threshold / max_dark_area can be measured instead of assumed (ANAL-205). Runs the
# public API WallpaperColors.fromBitmap() in an app_process on the device, which reads the two properties the way
# every app and system_server do. Two of the bitmaps sit between AOSP's defaults (70 / 5) and Googlebook's (55 / 12).
#
# usage: wallpaper-hints.sh SERIAL [OUTFILE]
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb), AOSP_SRC (default ~/anybook/aosp/src: its prebuilt
#   JDK, android.jar and out/host d8). Set ANDROID_ADB_SERVER_PORT for a private adb server.
set -euo pipefail
S=$1; OUTF=${2:-/dev/stdout}
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
T=${AOSP_SRC:-$HOME/anybook/aosp/src}
JDK=$T/prebuilts/jdk/jdk21/linux-x86; JAR=$T/prebuilts/sdk/current/public/android.jar; D8=$T/out/host/linux-x86/bin/d8
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
mkdir -p "$W/src" "$W/cls" "$W/dex"
cat > "$W/src/WallpaperHints.java" <<'EOF'
import android.app.WallpaperColors;
import android.graphics.Bitmap;
import android.graphics.Color;

public class WallpaperHints {
    // A 100x100 bitmap: `dark` percent of its rows black (contrast with black below 5.5), the rest grey level `v`.
    static Bitmap make(int v, int dark) {
        Bitmap b = Bitmap.createBitmap(100, 100, Bitmap.Config.ARGB_8888);
        for (int y = 0; y < 100; y++)
            for (int x = 0; x < 100; x++)
                b.setPixel(x, y, y < dark ? Color.BLACK : Color.rgb(v, v, v));
        return b;
    }

    static void report(String name, int v, int dark) {
        int h = WallpaperColors.fromBitmap(make(v, dark)).getColorHints();
        System.out.println(name + " grey=" + v + " dark_rows=" + dark + "% hints=" + h
                + " dark_text=" + ((h & WallpaperColors.HINT_SUPPORTS_DARK_TEXT) != 0)
                + " dark_theme=" + ((h & WallpaperColors.HINT_SUPPORTS_DARK_THEME) != 0));
    }

    public static void main(String[] args) {
        report("white", 255, 0);
        // Relative luminance 0.62: above Googlebook's 55 %, below AOSP's 70 %.
        report("grey-L62", 206, 0);
        // Mean luminance ~0.92, 8 % dark pixels: within Googlebook's 12 %, over AOSP's 5 %.
        report("white-8pc-dark", 255, 8);
        report("white-15pc-dark", 255, 15);
        report("black", 0, 0);
    }
}
EOF
"$JDK/bin/javac" -nowarn --release 17 -cp "$JAR" -d "$W/cls" "$W/src/WallpaperHints.java"
JAVA_HOME=$JDK PATH=$JDK/bin:$PATH "$D8" --min-api 35 --lib "$JAR" --output "$W/dex" "$W/cls/WallpaperHints.class"
"$ADB" -s "$S" push "$W/dex/classes.dex" /data/local/tmp/wallpaper-hints.dex >/dev/null
{
  echo "# $("$ADB" -s "$S" shell getprop ro.build.fingerprint | tr -d '\r')"
  for p in persist.wallpapercolors.threshold persist.wallpapercolors.max_dark_area; do
    echo "$p=[$("$ADB" -s "$S" shell getprop "$p" | tr -d '\r')]"
  done
  "$ADB" -s "$S" shell CLASSPATH=/data/local/tmp/wallpaper-hints.dex app_process /system/bin WallpaperHints | tr -d '\r'
} > "$OUTF"
"$ADB" -s "$S" shell rm -f /data/local/tmp/wallpaper-hints.dex
