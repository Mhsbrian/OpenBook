#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
if [ -z "${ANYBOOK_IN_CONTAINER:-}" ]; then
  REPO=$(cd "$(dirname "$0")/../../.." && pwd)
  A=${ANYBOOK_HOME:-$HOME/anybook}
  OUT=$A/installer/audio-diagnostic
  mkdir -p "$OUT"
  chmod 700 "$OUT"
  exec docker run --rm -u "$(id -u):$(id -g)" -e ANYBOOK_IN_CONTAINER=1 -e HOME=/tmp \
    -v "$REPO:/r:ro" -v "$A/compat/sdk:/sdk:ro" -v "$OUT:/o" anybook-ndk \
    bash /r/scripts/googlebook/audio-diagnostic/build.sh
fi
umask 077
BT=/sdk/build-tools/37.0.0
JAR=/sdk/platforms/android-36/android.jar
SRC=/r/scripts/googlebook/audio-diagnostic
W=$(mktemp -d)
mkdir -p "$W/classes"
# Private local diagnostic signing key; never a platform/system signing key.
if [ ! -f /o/diagnostic.keystore ]; then
  keytool -genkeypair -keystore /o/diagnostic.keystore -storepass android -keypass android \
    -alias diagnostic -keyalg RSA -keysize 3072 -validity 3650 \
    -dname "CN=OpenBook local audio diagnostic" >/dev/null 2>&1
fi
javac --release 11 -cp "$JAR" -d "$W/classes" "$SRC/"*.java
mapfile -t CLASSES < <(find "$W/classes" -name '*.class' -print)
"$BT/d8" --release --min-api 31 --lib "$JAR" --output "$W" "${CLASSES[@]}"
"$BT/aapt2" link -o "$W/unsigned.apk" -I "$JAR" --manifest "$SRC/AndroidManifest.xml" \
  --min-sdk-version 31 --target-sdk-version 36 --version-code 1 --version-name 1.0
(cd "$W" && zip -q -X unsigned.apk classes.dex)
"$BT/zipalign" -P 16 -f 4 "$W/unsigned.apk" "$W/aligned.apk"
"$BT/apksigner" sign --ks /o/diagnostic.keystore --ks-pass pass:android --key-pass pass:android \
  --out /o/OpenBookAudioCheck.apk "$W/aligned.apk"
"$BT/apksigner" verify --verbose /o/OpenBookAudioCheck.apk
"$BT/aapt2" dump permissions /o/OpenBookAudioCheck.apk
sha256sum /o/OpenBookAudioCheck.apk
