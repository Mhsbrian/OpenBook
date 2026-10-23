#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Reproducible toolchain for OpenBook Update (this directory). Idempotent; every download is pinned:
#   JDK        Temurin 17.0.20+8 through mise (mise.toml)
#   SDK        Android command-line tools 23.0 (SHA-256 pinned below), then its Android CLI
#              (`android sdk`, which replaces the deprecated sdkmanager) installs the platform,
#              build-tools and platform-tools, checking each archive against Google's repository
#              checksums; the installed revisions are checked afterwards
#   Gradle     9.8.2 through the committed wrapper (distributionSha256Sum in gradle-wrapper.properties;
#              the wrapper jar is checked here against Gradle's published SHA-256)
#   Libraries  every Maven artifact is checked against gradle/verification-metadata.xml (SHA-256)
# The Android SDK packages are under the Android Software Development Kit License Agreement. The Android
# CLI no longer asks; installing them accepts it, so the first install needs
# OPENBOOK_ACCEPT_ANDROID_SDK_LICENSE=1 as that explicit acceptance.
#
# usage: toolchain.sh            install or verify, then print the environment
#        eval "$(toolchain.sh --env)"   the environment only (JAVA_HOME, ANDROID_HOME, GRADLE_USER_HOME)
# env:   OPENBOOK_APP_SDK  (default ~/anybook/toolchain/openbook-update-sdk)
#        OPENBOOK_APP_GRADLE_HOME (default ~/anybook/toolchain/openbook-update-gradle)
#        OPENBOOK_DL (default ~/anybook/dl/sdk-zips)
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}
SDK=${OPENBOOK_APP_SDK:-$A/toolchain/openbook-update-sdk}
GHOME=${OPENBOOK_APP_GRADLE_HOME:-$A/toolchain/openbook-update-gradle}
DL=${OPENBOOK_DL:-$A/dl/sdk-zips}
JAVA=temurin-17.0.20+8
CMDLINE_ZIP=commandlinetools-linux-16111833_latest.zip      # cmdline-tools;23.0
CMDLINE_SHA256=0877a1d048fe4a24efe2eff536ca4223f7adeb58648bb81909d33c446918cfa8
CMDLINE_VERSION=23.0
PACKAGES=("platforms/android-37.0" "build-tools/37.0.0" "platform-tools")
EXPECT=("platforms/android-37.0 2.0.0" "build-tools/37.0.0 37.0.0" "platform-tools 37.0.1")
WRAPPER_JAR_SHA256=3b8a25775a69158b5ad2b1d17a80a88dc7b40a352a73eb27d06c612a7ce68e98   # gradle-9.8.2-wrapper.jar.sha256

env_lines() {
  printf 'export JAVA_HOME=%q\nexport ANDROID_HOME=%q\nexport ANDROID_SDK_ROOT=%q\nexport GRADLE_USER_HOME=%q\n' \
    "$(mise where "java@$JAVA")" "$SDK" "$SDK" "$GHOME"
}
if [ "${1:-}" = --env ]; then env_lines; exit 0; fi

command -v mise > /dev/null || { echo "mise is required (https://mise.jdx.dev)" >&2; exit 1; }
(cd "$HERE" && mise install --quiet "java@$JAVA")
JAVA_HOME=$(mise where "java@$JAVA"); export JAVA_HOME PATH="$JAVA_HOME/bin:$PATH"
java -version 2>&1 | grep -q '"17.0.20"' || { echo "unexpected JDK: $(java -version 2>&1 | head -1)" >&2; exit 1; }

mkdir -p "$DL" "$SDK" "$GHOME"
if [ ! -x "$SDK/cmdline-tools/$CMDLINE_VERSION/bin/android" ]; then
  [ -f "$DL/$CMDLINE_ZIP" ] || curl -fL --proto =https -o "$DL/$CMDLINE_ZIP.part" "https://dl.google.com/android/repository/$CMDLINE_ZIP"
  [ -f "$DL/$CMDLINE_ZIP" ] || mv "$DL/$CMDLINE_ZIP.part" "$DL/$CMDLINE_ZIP"
  echo "$CMDLINE_SHA256  $DL/$CMDLINE_ZIP" | sha256sum -c --quiet - || { echo "cmdline-tools checksum mismatch" >&2; exit 1; }
  T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
  unzip -q "$DL/$CMDLINE_ZIP" -d "$T"
  mkdir -p "$SDK/cmdline-tools"; rm -rf "$SDK/cmdline-tools/$CMDLINE_VERSION"
  mv "$T/cmdline-tools" "$SDK/cmdline-tools/$CMDLINE_VERSION"
fi
CLI=("$SDK/cmdline-tools/$CMDLINE_VERSION/bin/android" "--sdk=$SDK")
if [ ! -f "$SDK/licenses/android-sdk-license" ] && [ "${OPENBOOK_ACCEPT_ANDROID_SDK_LICENSE:-}" != 1 ]; then
  echo "Installing the Android SDK packages accepts the Android SDK License Agreement" \
       "(https://developer.android.com/studio/terms); rerun with OPENBOOK_ACCEPT_ANDROID_SDK_LICENSE=1" >&2
  exit 1
fi
"${CLI[@]}" sdk install "${PACKAGES[@]}"
installed=$("${CLI[@]}" sdk list 2>/dev/null | awk '/^Installed packages:/ { on = 1; next } /^[^ ]/ { on = 0 } on')
for e in "${EXPECT[@]}"; do
  set -- $e
  printf '%s\n' "$installed" | awk -v p="$1" -v v="$2" '$1 == p && $2 == v { f = 1 } END { exit !f }' \
    || { echo "unexpected revision of $1 (want $2)" >&2; printf '%s\n' "$installed" >&2; exit 1; }
done
echo "$WRAPPER_JAR_SHA256  $HERE/gradle/wrapper/gradle-wrapper.jar" | sha256sum -c --quiet - \
  || { echo "gradle-wrapper.jar differs from Gradle 9.8.2's published checksum" >&2; exit 1; }
grep -q '^distributionSha256Sum=21bd5da2de49b642904077f38c0efdc7778e92b3ed0889392dca61b97e389607$' \
  "$HERE/gradle/wrapper/gradle-wrapper.properties" || { echo "the wrapper's distribution checksum is not pinned" >&2; exit 1; }
printf 'sdk.dir=%s\n' "$SDK" > "$HERE/local.properties"
echo "toolchain ready: JDK $JAVA, SDK $SDK (${PACKAGES[*]}), Gradle 9.8.2 (wrapper)"
env_lines
