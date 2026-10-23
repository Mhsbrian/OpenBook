#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build, test and sign OpenBook Update on the host (the signing key never enters a container).
# Verifies the pinned toolchain, runs the unit tests and lint, builds the release and the emulator-test
# APKs, signs the release with the OpenBook app key (APK signature schemes v2 + v3) and records provenance.
# Gradle and everything it downloads run in a bubblewrap sandbox: the system read-only (the SDK and
# apksigner included), writable only the project, Gradle's cache and the Android user directory, and the
# key directory an empty tmpfs. Only apksigner, after the build, reads the key. With --reproducible-check the release is built a
# second time from clean and must be byte-identical before signing. A build of a commit whose APK inputs
# (app/, the engine, pins.json) are unchanged in the worktree is "clean", the only kind pin-update-app.py
# accepts for a deployable pin.
#
# Output (OUT, default ~/anybook/toolchain/openbook-update-out/<commit>):
#   OpenBookUpdate.apk                       release, signed: the APK the OpenBook system layer installs
#   app-release-unsigned.apk                 the same before signing
#   app-debug.apk, app-debug-androidTest.apk the emulator tests (emulator-test.sh)
#   build.json                               commit, toolchain, SHA-256 of each APK, the signing certificate
#
# usage: build.sh [--out DIR] [--reproducible-check]
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
[ -f /.dockerenv ] && { echo "run on the host: the signing key never enters a container" >&2; exit 1; }
OUT=; CHECK=
while [ $# -gt 0 ]; do
  case $1 in
    --out) OUT=$2; shift 2 ;;
    --reproducible-check) CHECK=1; shift ;;
    *) echo "usage: build.sh [--out DIR] [--reproducible-check]" >&2; exit 2 ;;
  esac
done
command -v bwrap > /dev/null || { echo "bubblewrap (bwrap) is required: Gradle runs without access to the key" >&2; exit 1; }
"$HERE/toolchain.sh" > /dev/null                      # verifies the JDK, SDK revisions and the Gradle wrapper
eval "$("$HERE/toolchain.sh" --env)"
export ANDROID_USER_HOME=${ANDROID_USER_HOME:-$HOME/anybook/toolchain/openbook-update-android-user}
BT=$ANDROID_HOME/build-tools/37.0.0
KEYS_ROOT=${OPENBOOK_KEYS:-$HOME/.local/share/openbook-keys}; KEYS=$KEYS_ROOT/app; N=openbook-update-2026
CERT=$HERE/../openbook-update.x509.pem
commit=$(git -C "$HERE" rev-parse HEAD)
dirty=$(git -C "$HERE/.." status --porcelain -- app openbook-updater pins.json | wc -l)
OUT=${OUT:-$HOME/anybook/toolchain/openbook-update-out/${commit:0:12}$([ "$dirty" = 0 ] || echo -dirty)}
mkdir -p "$OUT"
cmp -s <(openssl x509 -in "$KEYS/$N.x509.pem" -outform DER) <(openssl x509 -in "$CERT" -outform DER) \
  || { echo "the signing certificate differs from $CERT" >&2; exit 1; }

cd "$HERE"
mkdir -p "$ANDROID_USER_HOME" "$GRADLE_USER_HOME"
# Gradle sees the whole system read-only (the SDK and apksigner included), may write only the project,
# its own cache and the Android user directory, and finds an empty directory where the keys are.
gradle() {
  bwrap --ro-bind / / --dev /dev --proc /proc --tmpfs /tmp --unshare-pid --die-with-parent \
    --bind "$HERE" "$HERE" --bind "$GRADLE_USER_HOME" "$GRADLE_USER_HOME" --bind "$ANDROID_USER_HOME" "$ANDROID_USER_HOME" \
    --tmpfs "$KEYS_ROOT" ./gradlew --no-daemon --console=plain "$@"
}
gradle clean testDebugUnitTest lintDebug lintRelease assembleRelease assembleDebug assembleDebugAndroidTest
unsigned=app/build/outputs/apk/release/app-release-unsigned.apk
first=$(sha256sum "$unsigned" | cut -d' ' -f1)
cp app/build/outputs/apk/debug/app-debug.apk app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk "$OUT/"
if [ -n "$CHECK" ]; then
  cp "$unsigned" "$OUT/first-unsigned.apk"
  gradle clean assembleRelease
  second=$(sha256sum "$unsigned" | cut -d' ' -f1)
  [ "$first" = "$second" ] || { echo "release build is not reproducible: $first vs $second" >&2; exit 1; }
  rm "$OUT/first-unsigned.apk"
fi
"$BT/zipalign" -c 4 "$unsigned"
cp "$unsigned" "$OUT/app-release-unsigned.apk"
"$BT/apksigner" sign --key "$KEYS/$N.pk8" --cert "$KEYS/$N.x509.pem" --v1-signing-enabled false \
  --v2-signing-enabled true --v3-signing-enabled true --out "$OUT/OpenBookUpdate.apk" "$OUT/app-release-unsigned.apk"
rm -f "$OUT/OpenBookUpdate.apk.idsig"
"$BT/apksigner" verify --min-sdk-version 36 --print-certs "$OUT/OpenBookUpdate.apk" > "$OUT/verify.txt"
cert_sha=$(openssl x509 -in "$CERT" -outform DER | sha256sum | cut -d' ' -f1)
grep -q "certificate SHA-256 digest: $cert_sha" "$OUT/verify.txt" || { echo "signed with an unexpected certificate" >&2; exit 1; }
sha() { sha256sum "$1" | cut -d' ' -f1; }
cat > "$OUT/build.json" <<JSON
{
  "schema": "openbook-update-app-build/1",
  "commit": "$commit",
  "worktree_clean": $([ "$dirty" = 0 ] && echo true || echo false),
  "toolchain": {"jdk": "temurin-17.0.20+8", "gradle": "9.8.2", "agp": "9.4.1", "kotlin": "2.4.21",
                "compile_sdk": "android-37.0 r2", "build_tools": "37.0.0",
                "jdk_release": "$(sed -n 's/^IMPLEMENTOR_VERSION="\(.*\)"/\1/p' "$JAVA_HOME/release")",
                "jdk_modules_sha256": "$(sha256sum "$JAVA_HOME/lib/modules" | cut -d' ' -f1)"},
  "gradle_sandboxed_without_keys": true,
  "reproducible_check": $([ -n "$CHECK" ] && echo true || echo false),
  "version_code": $("$BT/aapt2" dump badging "$OUT/app-release-unsigned.apk" | sed -n "s/^package: .* versionCode='\([0-9]*\)'.*/\1/p"),
  "version_name": "$("$BT/aapt2" dump badging "$OUT/app-release-unsigned.apk" | sed -n "s/^package: .* versionName='\([^']*\)'.*/\1/p")",
  "engine_sha256": "$(sha ../openbook-updater)",
  "release_unsigned_sha256": "$first",
  "release_signed_sha256": "$(sha "$OUT/OpenBookUpdate.apk")",
  "debug_sha256": "$(sha "$OUT/app-debug.apk")",
  "android_test_sha256": "$(sha "$OUT/app-debug-androidTest.apk")",
  "signing_certificate_sha256": "$cert_sha"
}
JSON
cat "$OUT/build.json"
echo "built and signed: $OUT/OpenBookUpdate.apk"
