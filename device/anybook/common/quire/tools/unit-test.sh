#!/usr/bin/env bash
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Quire's host tests: the parts of the app with no Android types (note/SessionRoutes.kt, invocation/IntakePolicy.kt),
# compiled with the tree's kotlinc together with tests/unit/ and run on the tree's JDK. No device, no Soong.
#
# usage: unit-test.sh        Env: AOSP (default ~/anybook/aosp/src)
set -euo pipefail
Q="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOSP="${AOSP:-$HOME/anybook/aosp/src}"
export JAVA_HOME="$AOSP/prebuilts/jdk/jdk21/linux-x86"
KOTLINC="$AOSP/external/kotlinc"
W="$(mktemp -d /tmp/quire-unit.XXXXXX)"
trap 'rm -rf "$W"' EXIT
"$KOTLINC/bin/kotlinc" -jvm-target 17 -language-version 2.2 -nowarn -d "$W/classes" \
  "$Q/app/src/dev/openbook/quire/note/SessionRoutes.kt" \
  "$Q/app/src/dev/openbook/quire/invocation/IntakePolicy.kt" \
  "$Q"/tests/unit/*.kt
"$JAVA_HOME/bin/java" -cp "$W/classes:$KOTLINC/lib/kotlin-stdlib.jar" dev.openbook.quire.test.CheckKt
