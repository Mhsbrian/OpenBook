#!/usr/bin/env bash
# Measure the document fonts (ANAL-208) through the framework, as an Android app would: Typeface.create(family) and
# Paint.measureText, in typeface-probe/TypefaceProbe.java run with app_process. Builds the probe with the AOSP tree's
# javac and d8, pushes it to /data/local/tmp and writes OUT (family, weight, width of string 1, of string 2, at 100 px).
# Then: scripts/ui/doc-fonts-metrics.py --typeface LABEL=OUT ... says which font each family name got.
#
# usage: doc-fonts-typeface.sh SERIAL OUT
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb), AOSP (default ~/anybook/aosp/src)
set -euo pipefail
S=$1; O=$2; HERE=$(cd "$(dirname "$0")" && pwd)
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}; AOSP=${AOSP:-$HOME/anybook/aosp/src}
J=$AOSP/prebuilts/jdk/jdk21/linux-x86/bin
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
"$J/javac" -nowarn -source 8 -target 8 -cp "$AOSP/prebuilts/sdk/current/public/android.jar" -d "$W" \
  "$HERE/typeface-probe/TypefaceProbe.java" 2>&1 | grep -v -i warning || true
PATH=$J:$PATH "$AOSP/out/host/linux-x86/bin/d8" --min-api 30 --output "$W" "$W/TypefaceProbe.class"
"$ADB" -s "$S" push "$W/classes.dex" /data/local/tmp/typeface-probe.dex >/dev/null
"$ADB" -s "$S" shell 'CLASSPATH=/data/local/tmp/typeface-probe.dex app_process /system/bin TypefaceProbe arial \
  "times new roman" "courier new" verdana georgia tahoma "comic sans ms" sans-serif serif monospace' | tr -d '\r' > "$O"
cat "$O"
