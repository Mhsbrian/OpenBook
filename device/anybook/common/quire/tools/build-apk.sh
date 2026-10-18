#!/usr/bin/env bash
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Builds OpenBookQuire.apk outside Soong, for iterating on a running userdebug device (Cuttlefish) without the AOSP
# lane: aapt2, kotlinc, d8 and apksigner from the tree, the same inputs as compile-check.sh, signed with AOSP's
# platform *test* key (build/make/target/product/security/platform.pk8, public), which is what the test images use.
# Install it over the image's copy with `adb install -r -d` (an update of the privileged system app keeps its
# privileges). The image's own build stays Soong's (Android.bp); this script is for development only.
#
# usage: build-apk.sh [OUT_APK]   (default /tmp/quire-dev-apk/OpenBookQuire.apk)
# Env: AOSP (default ~/anybook/aosp/src), VERSION_CODE (default 990000000 + minutes since 2026-01-01, so each build
# installs over the last).
set -euo pipefail
Q="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOSP="${AOSP:-$HOME/anybook/aosp/src}"
APK="${1:-/tmp/quire-dev-apk/OpenBookQuire.apk}"
W="$(dirname "$APK")/work"
case "$W" in /tmp/*) ;; *) echo "build-apk: the work dir must be under /tmp" >&2; exit 2 ;; esac
rm -rf "$W"; mkdir -p "$W/gen" "$W/classes" "$W/dex"

export JAVA_HOME="$AOSP/prebuilts/jdk/jdk21/linux-x86"
export PATH="$JAVA_HOME/bin:$PATH"
KOTLINC="$AOSP/external/kotlinc"
ANDROID_JAR="$AOSP/prebuilts/sdk/current/system/android.jar"
FRAMEWORK_JAR="$AOSP/out/soong/.intermediates/frameworks/base/framework-minus-apex-headers/android_common/turbine-combined/framework.jar"
AAPT2="$AOSP/out/host/linux-x86/bin/aapt2"; [[ -x $AAPT2 ]] || AAPT2="$AOSP/prebuilts/sdk/tools/linux/bin/aapt2"
# The tree's wrappers may lack the executable bit; run the jars directly.
R8_JAR="$AOSP/prebuilts/r8/r8.jar"
APKSIGNER_JAR="$AOSP/prebuilts/sdk/tools/linux/lib/apksigner.jar"
ZIPALIGN="$AOSP/out/host/linux-x86/bin/zipalign"; [[ -x $ZIPALIGN ]] || ZIPALIGN="$AOSP/prebuilts/sdk/tools/linux/bin/zipalign"
KEY="$AOSP/build/make/target/product/security/platform"
for f in "$FRAMEWORK_JAR" "$R8_JAR" "$APKSIGNER_JAR" "$KEY.pk8"; do [[ -e $f ]] || { echo "build-apk: missing $f" >&2; exit 2; }; done
VERSION_CODE="${VERSION_CODE:-$(( 990000000 + ( $(date -u +%s) - 1767225600 ) / 60 ))}"

"$AAPT2" compile --dir "$Q/app/res" -o "$W/res.zip"
"$AAPT2" link -I "$ANDROID_JAR" --manifest "$Q/app/AndroidManifest.xml" --min-sdk-version 36 \
  --target-sdk-version 37 --version-code "$VERSION_CODE" --version-name "q5-dev" --auto-add-overlay \
  --java "$W/gen" -o "$W/res.apk" "$W/res.zip"
javac -nowarn -source 17 -target 17 -cp "$ANDROID_JAR" -d "$W/classes" $(find "$W/gen" -name '*.java')
mapfile -t srcs < <(find "$Q/app/src" -name '*.kt' | sort)
"$KOTLINC/bin/kotlinc" -no-jdk -no-stdlib -jvm-target 17 -language-version 2.2 -nowarn \
  -cp "$FRAMEWORK_JAR:$ANDROID_JAR:$W/classes:$KOTLINC/lib/kotlin-stdlib.jar" -d "$W/classes" "${srcs[@]}"
(cd "$W/classes" && zip -qr "$W/classes.jar" .)
java -cp "$R8_JAR" com.android.tools.r8.D8 --release --min-api 36 --lib "$ANDROID_JAR" --lib "$FRAMEWORK_JAR" --output "$W/dex" \
  "$W/classes.jar" "$KOTLINC/lib/kotlin-stdlib.jar" 2> >(grep -v '^Warning' >&2)
cp "$W/res.apk" "$W/unsigned.apk"
(cd "$W/dex" && zip -q "$W/unsigned.apk" classes*.dex)
"$ZIPALIGN" -f -p 4 "$W/unsigned.apk" "$W/aligned.apk"
mkdir -p "$(dirname "$APK")"
java -jar "$APKSIGNER_JAR" sign --key "$KEY.pk8" --cert "$KEY.x509.pem" --out "$APK" "$W/aligned.apk"
echo "build-apk: $APK (versionCode $VERSION_CODE, $(stat -c %s "$APK") bytes)"
