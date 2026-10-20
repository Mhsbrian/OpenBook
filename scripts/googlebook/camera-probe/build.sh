#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Diagnostic only: signed with a local throwaway key, never included in an image.
set -euo pipefail
if [ -z "${ANYBOOK_IN_CONTAINER:-}" ]; then
  REPO=$(cd "$(dirname "$0")/../../.." && pwd)
  A=${ANYBOOK_HOME:-$HOME/anybook}
  OUT=$A/installer/camera-probe
  mkdir -p "$OUT"
  chmod 700 "$OUT"
  exec docker run --rm -u "$(id -u):$(id -g)" -e ANYBOOK_IN_CONTAINER=1 -e HOME=/tmp \
    -v "$REPO:/r:ro" -v "$A/compat/sdk:/sdk:ro" -v "$OUT:/o" anybook-ndk \
    bash /r/scripts/googlebook/camera-probe/build.sh
fi
umask 077
BT=/sdk/build-tools/37.0.0
JAR=/sdk/platforms/android-36/android.jar
SRC=/r/scripts/googlebook/camera-probe
W=$(mktemp -d)
mkdir -p "$W/classes"
if [ ! -f /o/test.keystore ]; then
  keytool -genkeypair -keystore /o/test.keystore -storepass android -keypass android \
    -alias test -keyalg RSA -keysize 2048 -validity 3650 \
    -dname "CN=OpenBook disposable camera diagnostic" >/dev/null 2>&1
fi
javac --release 11 -cp "$JAR" -d "$W/classes" "$SRC/CameraProbeActivity.java"
mapfile -t CLASSES < <(find "$W/classes" -name '*.class' -print)
"$BT/d8" --release --min-api 30 --lib "$JAR" --output "$W" "${CLASSES[@]}"
"$BT/aapt2" link -o "$W/unsigned.apk" -I "$JAR" --manifest "$SRC/AndroidManifest.xml" \
  --min-sdk-version 30 --target-sdk-version 36 --version-code 1 --version-name 1
(cd "$W" && zip -q -X unsigned.apk classes.dex)
"$BT/zipalign" -P 16 -f 4 "$W/unsigned.apk" "$W/aligned.apk"
"$BT/apksigner" sign --ks /o/test.keystore --ks-pass pass:android --key-pass pass:android \
  --out /o/OpenBookCameraProbe.apk "$W/aligned.apk"
"$BT/apksigner" verify /o/OpenBookCameraProbe.apk
sha256sum /o/OpenBookCameraProbe.apk
