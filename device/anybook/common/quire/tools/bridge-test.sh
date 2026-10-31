#!/usr/bin/env bash
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Quire's Linux-environment adapter on a device's Android runtime (tests/bridge/BridgeCheck.kt): the app's own
# acp/AcpAgent.kt, acp/AcpConnection.kt, note/Agents.kt and note/SessionRoutes.kt, compiled with stubs for the Terminal
# app's connector and Quire's constants, dexed, and run with app_process over a real socket pair. No app is installed
# and nothing on the device changes but the jar in /data/local/tmp, which is removed afterwards.
#
# usage: bridge-test.sh SERIAL [OUT_DIR]      Env: AOSP (default ~/anybook/aosp/src), ADB, ANDROID_ADB_SERVER_PORT
set -euo pipefail
Q="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOSP="${AOSP:-$HOME/anybook/aosp/src}"
ADB="${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}"
SERIAL=${1:?usage: bridge-test.sh SERIAL [OUT_DIR]}
W="${2:-$(mktemp -d /tmp/quire-bridge.XXXXXX)}"; mkdir -p "$W"
export JAVA_HOME="$AOSP/prebuilts/jdk/jdk21/linux-x86"
ANDROID_JAR="$AOSP/prebuilts/sdk/current/system/android.jar"
S="$Q/app/src/dev/openbook/quire"
"$AOSP/external/kotlinc/bin/kotlinc" -jvm-target 17 -language-version 2.2 -nowarn -cp "$ANDROID_JAR" -include-runtime \
  -d "$W/bridge.jar" "$S/acp/AcpAgent.kt" "$S/acp/AcpConnection.kt" "$S/note/Agents.kt" "$S/note/SessionRoutes.kt" \
  "$Q"/tests/bridge/*.kt
"$JAVA_HOME/bin/java" -cp "$AOSP/prebuilts/r8/r8.jar" com.android.tools.r8.D8 --min-api 36 --lib "$ANDROID_JAR" \
  --output "$W/bridge-dex.jar" "$W/bridge.jar" 2> >(grep -v '^Warning' >&2)
J=/data/local/tmp/quire-bridge-test.jar
"$ADB" -s "$SERIAL" push "$W/bridge-dex.jar" "$J" >/dev/null
set +e
"$ADB" -s "$SERIAL" shell "CLASSPATH=$J timeout 60 app_process /system/bin checker.BridgeCheckKt" | tr -d '\r' | tee "$W/bridge-check.txt"
rc=${PIPESTATUS[0]}
set -e
"$ADB" -s "$SERIAL" shell rm -f "$J"
grep -q '^RESULT .* 0 failed' "$W/bridge-check.txt" && [ "$rc" = 0 ]
