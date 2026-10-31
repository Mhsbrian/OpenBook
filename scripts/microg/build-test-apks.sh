#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the two test APKs of ANAL-210's signature-spoofing checks, without Gradle, in the anybook-ndk container
# (SDK build-tools 37.0.0, android-36, as scripts/compat/build-probes.sh):
#   openbook-sigcheck.apk     org.openbook.test.sigcheck: logs the certificates PackageManager returns for other
#                             packages (GET_SIGNATURES and GET_SIGNING_CERTIFICATES), as microG's self-check reads them;
#                             its .Loc activity asks the network, fused and gps providers for one location each
#   openbook-fakegms.apk      a package named com.google.android.gms that asks for microG's fake signature but is
#                             signed with a throwaway key: the patch must not spoof it (the negative test)
#   sigcheck.dex              the same signature check without an app or a screen, for a laptop in use:
#                             adb shell app_process -cp /data/local/tmp/sigcheck.dex / SigCheck PKG...
# Both are signed with local throwaway keys that are never committed. Output: ~/anybook/microg/out/testapps.
set -euo pipefail
if [ -z "${ANYBOOK_IN_CONTAINER:-}" ]; then
  REPO=$(cd "$(dirname "$0")/../.." && pwd); A=${ANYBOOK_HOME:-$HOME/anybook}
  mkdir -p "$A/microg/out" "$A/microg/keys"
  exec docker run --rm -u "$(id -u):$(id -g)" -e ANYBOOK_IN_CONTAINER=1 -e HOME=/tmp \
    -v "$REPO:/r:ro" -v "$A/compat/sdk:/sdk:ro" -v "$A/microg/out:/o" -v "$A/microg/keys:/k" anybook-ndk \
    /r/scripts/microg/build-test-apks.sh "$@"
fi
BT=/sdk/build-tools/37.0.0; JAR=/sdk/platforms/android-36/android.jar; SRC=/r/scripts/microg/testapps
OUT=/o/testapps; W=/tmp/w; API=30
rm -rf "$W" "$OUT"; mkdir -p "$W/sigcheck/classes" "$OUT"
key(){  # key NAME DNAME
  [ -f "/k/$1.keystore" ] || keytool -genkeypair -keystore "/k/$1.keystore" -storepass android -keypass android \
    -alias "$1" -keyalg RSA -keysize 2048 -validity 10000 -dname "$2" >/dev/null 2>&1
}
sign(){  # sign KEY IN OUT
  "$BT/zipalign" -P 16 -f 4 "$2" "$2.aligned"
  "$BT/apksigner" sign --ks "/k/$1.keystore" --ks-pass pass:android --key-pass pass:android --out "$3" "$2.aligned"
}
key openbook-test "CN=OpenBook test apps, O=OpenBook"
key openbook-fakegms "CN=Not microG (OpenBook negative test), O=OpenBook"

javac --release 11 -nowarn -cp "$JAR" -d "$W/sigcheck/classes" $(find "$SRC/sigcheck/java" -name '*.java')
"$BT/d8" --release --min-api $API --lib "$JAR" --output "$W/sigcheck" $(find "$W/sigcheck/classes" -name '*.class')
"$BT/aapt2" link -o "$W/sigcheck/unsigned.apk" -I "$JAR" --manifest "$SRC/sigcheck/AndroidManifest.xml" \
  --min-sdk-version $API --target-sdk-version 36 --version-code 1 --version-name 1.0-anal210
(cd "$W/sigcheck" && zip -q -X unsigned.apk classes.dex)
sign openbook-test "$W/sigcheck/unsigned.apk" "$OUT/openbook-sigcheck.apk"

mkdir -p "$W/fakegms"
"$BT/aapt2" link -o "$W/fakegms/unsigned.apk" -I "$JAR" --manifest "$SRC/fakegms/AndroidManifest.xml" \
  --min-sdk-version $API --target-sdk-version 36 --version-code 1 --version-name 1.0-anal210-negative-test
sign openbook-fakegms "$W/fakegms/unsigned.apk" "$OUT/openbook-fakegms.apk"

mkdir -p "$W/headless"
javac --release 11 -nowarn -cp "$JAR" -d "$W/headless" "$SRC/headless/SigCheck.java"
"$BT/d8" --release --min-api $API --lib "$JAR" --output "$W/headless" "$W/headless/SigCheck.class"
cp "$W/headless/classes.dex" "$OUT/sigcheck.dex"

for f in "$OUT"/*.apk; do
  echo "== ${f##*/}"; "$BT/apksigner" verify --print-certs "$f" | grep -E 'DN|SHA-256'
done
(cd "$OUT" && sha256sum *.apk sigcheck.dex > SHA256SUMS && cat SHA256SUMS)
