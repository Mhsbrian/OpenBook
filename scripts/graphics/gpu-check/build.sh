#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build GPU Check (ANAL-247, gpucheck.c) on the host with the Android SDK and NDK: OUT/GpuCheck.apk, signed with a
# throwaway test key made in OUT/key on first use (a test app; never part of an image).
#   scripts/graphics/gpu-check/build.sh OUT
# ANDROID_SDK (default ~/Android/Sdk), NDK (default the newest under $ANDROID_SDK/ndk).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
OUT=$(realpath -m "${1:?usage: build.sh OUT}")
SDK=${ANDROID_SDK:-$HOME/Android/Sdk}
NDK=${NDK:-$(ls -d "$SDK"/ndk/*/ | sort -V | tail -1)}
BT=$(ls -d "$SDK"/build-tools/*/ | sort -V | tail -1)
JAR=$SDK/platforms/android-37.0/android.jar
CC=$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/x86_64-linux-android29-clang
mkdir -p "$OUT/stage/lib/x86_64" "$OUT/key"
"$CC" -shared -fPIC -O2 -Wall -Werror -Wl,-z,max-page-size=16384 -Wl,--build-id=none -o "$OUT/stage/lib/x86_64/libgpucheck.so" \
  "$here/gpucheck.c" -landroid -llog -lEGL -lGLESv3 -lvulkan -lm
"$BT/aapt2" link -o "$OUT/base.apk" -I "$JAR" --manifest "$here/AndroidManifest.xml"
cp "$OUT/base.apk" "$OUT/raw.apk"
(cd "$OUT/stage" && touch -d @1230768000 lib lib/x86_64 lib/x86_64/libgpucheck.so && zip -q -X -0 -r "$OUT/raw.apk" lib)
"$BT/zipalign" -f -P 16 4 "$OUT/raw.apk" "$OUT/GpuCheck-unsigned.apk"
if [ ! -f "$OUT/key/test.pk8" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "$OUT/key/test.pem" -subj "/CN=GPU Check test key" -days 3650 \
    -out "$OUT/key/test.x509.pem" 2> /dev/null
  openssl pkcs8 -topk8 -nocrypt -inform PEM -outform DER -in "$OUT/key/test.pem" -out "$OUT/key/test.pk8"
fi
"$BT/apksigner" sign --key "$OUT/key/test.pk8" --cert "$OUT/key/test.x509.pem" --out "$OUT/GpuCheck.apk" \
  "$OUT/GpuCheck-unsigned.apk"
"$BT/apksigner" verify "$OUT/GpuCheck.apk"
rm -f "$OUT/base.apk" "$OUT/raw.apk" "$OUT/GpuCheck.apk.idsig"
sha256sum "$OUT/GpuCheck.apk" "$OUT/stage/lib/x86_64/libgpucheck.so"
