#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the APKs and libraries of ANAL-211's synthetic test package (scripts/gapps/testapps/), without Gradle, in the
# anybook-ndk container (SDK build-tools 37.0.0, android-36, NDK r30 as scripts/compat/build-probes.sh). None of it is
# Google software; it only has the shapes a real Google apps package has:
#   OpenBookTestGsf.apk           package com.google.android.gsf: a stand-in GSF whose gservices provider answers
#                                 android_id with a fixed fake ID (for OpenBook setup's registration screen)
#   OpenBookTestPriv.apk          org.openbook.test.gapps.priv: a privileged app with x86_64 code in its APK, one
#                                 privileged and two runtime permissions
#   OpenBookTestApp.apk           org.openbook.test.gapps.app: an ordinary system app; libobgapps-x86_64.so goes
#                                 next to it as an extracted library
#   OpenBookTestArmOnly.apk       negative test: arm64-v8a code only
#   OpenBookTestPlatformUid.apk   negative test: android:sharedUserId="android.uid.system"
#   OpenBookTestPriv-unsigned.apk negative test: the privileged app, aligned but not signed
#   libobgapps-arm64.so           negative test: an arm64 library to put where x86_64 ones belong
# All signed with a local throwaway key that is never committed. Output: <data dir>/gapps/out/apks.
set -euo pipefail
if [ -z "${ANYBOOK_IN_CONTAINER:-}" ]; then
  REPO=$(cd "$(dirname "$0")/../.." && pwd); A=${ANYBOOK_HOME:-$HOME/anybook}
  mkdir -p "$A/gapps/out" "$A/gapps/keys"
  exec docker run --rm -u "$(id -u):$(id -g)" -e ANYBOOK_IN_CONTAINER=1 -e HOME=/tmp \
    -v "$REPO:/r:ro" -v "$A/compat/sdk:/sdk:ro" -v "$A/gapps/out:/o" -v "$A/gapps/keys:/k" anybook-ndk \
    /r/scripts/gapps/build-synthetic-apks.sh "$@"
fi
BT=/sdk/build-tools/37.0.0; JAR=/sdk/platforms/android-36/android.jar; TC=/sdk/ndk/toolchains/llvm/prebuilt/linux-x86_64
SRC=/r/scripts/gapps/testapps; OUT=/o/apks; W=/tmp/w; API=30
VER=(--min-sdk-version $API --target-sdk-version 36 --version-code 211 --version-name 1.0-anal211-synthetic)
rm -rf "$W" "$OUT"; mkdir -p "$W" "$OUT"
[ -f /k/openbook-gapps-test.keystore ] || keytool -genkeypair -keystore /k/openbook-gapps-test.keystore \
  -storepass android -keypass android -alias test -keyalg RSA -keysize 2048 -validity 10000 \
  -dname "CN=OpenBook synthetic GApps test, O=OpenBook" >/dev/null 2>&1
sign(){  # sign IN OUT
  "$BT/zipalign" -P 16 -f 4 "$1" "$1.aligned"
  "$BT/apksigner" sign --ks /k/openbook-gapps-test.keystore --ks-pass pass:android --key-pass pass:android \
    --out "$2" "$1.aligned"
}
link(){  # link NAME
  mkdir -p "$W/$1"
  "$BT/aapt2" link -o "$W/$1/unsigned.apk" -I "$JAR" --manifest "$SRC/$1/AndroidManifest.xml" "${VER[@]}"
}

for t in x86_64 aarch64; do
  "$TC/bin/clang" --target=$t-linux-android$API -O2 -fPIC -shared -o "$W/libobgapps-$t.so" "$SRC/jni/obgapps.c"
done
cp "$W/libobgapps-x86_64.so" "$OUT/libobgapps-x86_64.so"
cp "$W/libobgapps-aarch64.so" "$OUT/libobgapps-arm64.so"

link gsf
mkdir -p "$W/gsf/classes"
javac --release 11 -nowarn -cp "$JAR" -d "$W/gsf/classes" $(find "$SRC/gsf/java" -name '*.java')
"$BT/d8" --release --min-api $API --lib "$JAR" --output "$W/gsf" $(find "$W/gsf/classes" -name '*.class')
(cd "$W/gsf" && zip -q -X unsigned.apk classes.dex)
sign "$W/gsf/unsigned.apk" "$OUT/OpenBookTestGsf.apk"

link priv   # the library stored, so it can be mapped from the APK (extractNativeLibs=false)
mkdir -p "$W/priv/lib/x86_64" && cp "$W/libobgapps-x86_64.so" "$W/priv/lib/x86_64/libobgapps.so"
(cd "$W/priv" && zip -q -X -0 unsigned.apk lib/x86_64/libobgapps.so)
sign "$W/priv/unsigned.apk" "$OUT/OpenBookTestPriv.apk"
cp "$W/priv/unsigned.apk.aligned" "$OUT/OpenBookTestPriv-unsigned.apk"

link app
sign "$W/app/unsigned.apk" "$OUT/OpenBookTestApp.apk"

link armonly
mkdir -p "$W/armonly/lib/arm64-v8a" && cp "$W/libobgapps-aarch64.so" "$W/armonly/lib/arm64-v8a/libobgapps.so"
(cd "$W/armonly" && zip -q -X -0 unsigned.apk lib/arm64-v8a/libobgapps.so)
sign "$W/armonly/unsigned.apk" "$OUT/OpenBookTestArmOnly.apk"

link platformuid
sign "$W/platformuid/unsigned.apk" "$OUT/OpenBookTestPlatformUid.apk"

{ for f in "$OUT"/*.apk; do
    echo "== ${f##*/}"; "$BT/apksigner" verify --print-certs "$f" 2>&1 | grep -E 'DN|SHA-256|DOES NOT VERIFY|ERROR' || true
  done; } | tee "$OUT/certs.txt"
"$BT/aapt2" dump badging "$OUT/OpenBookTestPriv.apk" | grep -E "^package|native-code" | tee "$OUT/badging.txt"
(cd "$OUT" && sha256sum *.apk *.so > SHA256SUMS && cat SHA256SUMS)
