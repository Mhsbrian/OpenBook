#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build glmark2 (GPL-3.0, github.com/glmark2/glmark2) as one APK carrying both arm64-v8a and x86_64 code, for the
# ARM-translation corpus (ANAL-380, docs/arm-performance.md): the same APK installed with --abi arm64-v8a runs through
# the translator, with --abi x86_64 natively. glmark2 runs unattended (`am start ... -e args '...'`) and reports its
# own frame rate, so it measures the cost of a translated app's GL calls.
#
# Source: the pinned commit below, cloned into ~/anybook/perf/src/glmark2 if missing. The one source change is a
# manifest copy: minSdk 26, targetSdk 35 (Android 17 refuses older targets) and android:exported on the activities,
# as ANAL-336's x86_64 build did. Toolchain: NDK r28c, build-tools 37, android-37, JDK 17 under ~/anybook/toolchain.
# Signed with a throwaway local key: a test package, never distributed.
#
# usage: build-glmark2.sh      -> ~/anybook/perf/arm-corpus/glmark2-fat.apk, its .sha256, logs in .../build/
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
COMMIT=22c527cb0556f3a1ac4445aaa52cc532760928d5
S=$A/perf/src/glmark2
O=$A/perf/arm-corpus
W=$O/build/glmark2
NDK=$A/toolchain/android-ndk-r28c
SDK=$A/toolchain/openbook-update-sdk
BT=$SDK/build-tools/37.0.0
JAR=$SDK/platforms/android-37.0/android.jar
export JAVA_HOME=$A/toolchain/jdk-17.0.21
for p in "$NDK/ndk-build" "$BT/aapt2" "$JAR" "$JAVA_HOME/bin/javac"; do
  [ -e "$p" ] || { echo "build-glmark2: missing $p" >&2; exit 2; }
done
if [ ! -d "$S/.git" ]; then
  git clone -q https://github.com/glmark2/glmark2.git "$S"
fi
git -C "$S" -c advice.detachedHead=false checkout -q "$COMMIT"
[ -z "$(git -C "$S" status --porcelain)" ] || { echo "build-glmark2: $S has local changes" >&2; exit 2; }

rm -rf "$W"; mkdir -p "$W"/{gen,obj,dex,root/assets} "$O"
( cd "$S/android" && "$NDK/ndk-build" -j16 "APP_ABI=arm64-v8a x86_64" APP_PLATFORM=android-26 \
    "APP_CPPFLAGS=-std=c++17 -fexceptions -frtti" NDK_OUT="$W/ndk-obj" NDK_LIBS_OUT="$W/root/lib" ) \
  > "$W/ndk.log" 2>&1 || { tail -20 "$W/ndk.log" >&2; exit 1; }
for abi in arm64-v8a x86_64; do
  [ -f "$W/root/lib/$abi/libglmark2-android.so" ] || { echo "build-glmark2: no $abi library" >&2; exit 1; }
done
cp -r "$S/data/." "$W/root/assets/"

python3 - "$S/android/AndroidManifest.xml" "$W/AndroidManifest.xml" <<'PY'
import re, sys
s = open(sys.argv[1]).read()
s = s.replace('<uses-sdk android:minSdkVersion="16"/>', '<uses-sdk android:minSdkVersion="26"/>')
s = s.replace('<uses-sdk android:targetSdkVersion="23"/>', '<uses-sdk android:targetSdkVersion="35"/>')
s = re.sub(r'<activity(\s)', r'<activity android:exported="true"\1', s)
assert s.count('android:exported="true"') == s.count('<activity'), "an activity without exported"
open(sys.argv[2], 'w').write(s)
PY

"$BT/aapt2" compile --dir "$S/android/res" -o "$W/res.zip"
"$BT/aapt2" link -o "$W/base.apk" -I "$JAR" --manifest "$W/AndroidManifest.xml" --java "$W/gen" \
  --min-sdk-version 26 --target-sdk-version 35 "$W/res.zip"
"$JAVA_HOME/bin/javac" -nowarn -source 17 -target 17 -classpath "$JAR" -d "$W/obj" \
  $(find "$S/android/src" "$W/gen" -name '*.java') 2> "$W/javac.log"
"$BT/d8" --min-api 26 --lib "$JAR" --output "$W/dex" $(find "$W/obj" -name '*.class')
cp "$W/dex/classes.dex" "$W/root/"
( cd "$W/root" && zip -q -r "$W/base.apk" classes.dex assets && zip -q -0 -r "$W/base.apk" lib )
"$BT/zipalign" -f -p 4 "$W/base.apk" "$W/aligned.apk"
KS=$A/perf/keys/throwaway.jks   # local, never committed
mkdir -p "$(dirname "$KS")"
[ -f "$KS" ] || "$JAVA_HOME/bin/keytool" -genkeypair -keystore "$KS" -storepass android -keypass android \
  -alias test -keyalg RSA -keysize 2048 -validity 3650 -dname "CN=OpenBook ARM corpus local test build" \
  >/dev/null 2>&1
"$BT/apksigner" sign --ks "$KS" --ks-pass pass:android --out "$O/glmark2-fat.apk" "$W/aligned.apk"
"$BT/apksigner" verify "$O/glmark2-fat.apk"
unzip -l "$O/glmark2-fat.apk" | awk '{print $NF}' | grep '^lib/' | sort
( cd "$O" && sha256sum glmark2-fat.apk | tee glmark2-fat.apk.sha256 )
