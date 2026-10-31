#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# ARM64-only regression APK and x86_64 bind control, using the existing SDK/NDK.
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}
S=$(cd "$(dirname "$0")" && pwd)
W=$A/compat/out/native-service
BT=$A/compat/sdk/build-tools/37.0.0
TC=$A/compat/sdk/ndk/toolchains/llvm/prebuilt/linux-x86_64
JAR=$A/aosp/src/prebuilts/sdk/current/public/android.jar
# The SDK's flagged nativeService attr has a staging ID (0x01a20005). Link the
# manifest with the tested image's resources, where it is finalized (0x010106ae).
RES=${OPENBOOK_FRAMEWORK_RES:-$A/aosp/src/out/target/product/anybook_g14/system/framework/framework-res.apk}
[ -f "$RES" ] || { echo "Build the G14 image first, or set OPENBOOK_FRAMEWORK_RES" >&2; exit 1; }
export PATH="$A/aosp/src/prebuilts/jdk/jdk21/linux-x86/bin:$PATH"
mkdir -p "$W/classes" "$A/compat/keys"
KS=$A/compat/keys/probe-debug.keystore
if [ ! -f "$KS" ]; then
    keytool -genkeypair -keystore "$KS" -storepass android -keypass android -alias probe \
        -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=OpenBook compat probe"
fi
javac --release 11 -cp "$JAR" -d "$W/classes" "$S"/*.java
mapfile -t classes < <(find "$W/classes" -name '*.class')
"$BT/d8" --release --min-api 30 --lib "$JAR" --output "$W" "${classes[@]}"
for variant in arm64 x86_64; do
    if [ "$variant" = arm64 ]; then abi=arm64-v8a; triple=aarch64; else abi=x86_64; triple=x86_64; fi
    V=$W/$variant
    mkdir -p "$V/lib/$abi"
    "$TC/bin/$triple-linux-android30-clang" -Wall -Wextra -Werror -O2 -fPIC -shared \
        "$S/probe.c" -o "$V/lib/$abi/libfallbackprobe.so"
    "$BT/aapt2" link -o "$V/unsigned.apk" -I "$RES" --manifest "$S/AndroidManifest.xml"
    cp "$W/classes.dex" "$V/"
    (cd "$V" && zip -q -X unsigned.apk classes.dex "lib/$abi/libfallbackprobe.so")
    "$BT/zipalign" -P 16 -f 4 "$V/unsigned.apk" "$V/aligned.apk"
    "$BT/apksigner" sign --ks "$KS" --ks-pass pass:android --key-pass pass:android \
        --out "$W/native-fallback-$variant.apk" "$V/aligned.apk"
    sha256sum "$W/native-fallback-$variant.apk"
done
