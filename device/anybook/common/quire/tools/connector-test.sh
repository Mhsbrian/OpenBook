#!/usr/bin/env bash
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# agents/Connectors.kt itself (the Linux environment's start and wait) on the host JVM, against fakes of the Android
# classes it uses and a scripted agent bridge (tests/connectors/). No device.
#
# usage: connector-test.sh        Env: AOSP (default ~/anybook/aosp/src), CONNECTORS_SRC (another Connectors.kt)
set -euo pipefail
Q="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOSP="${AOSP:-$HOME/anybook/aosp/src}"
export JAVA_HOME="$AOSP/prebuilts/jdk/jdk21/linux-x86"
W="$(mktemp -d /tmp/quire-connectors.XXXXXX)"
trap 'rm -rf "$W"' EXIT
SRC="${CONNECTORS_SRC:-$Q/app/src/dev/openbook/quire/agents/Connectors.kt}"  # CONNECTORS_SRC: another version, e.g. an older commit's
# Quire's TAG and the R.string ids Connectors uses.
{
  echo "package dev.openbook.quire"
  echo 'object Quire { const val TAG = "Quire" }'
  echo "object R { object string {"
  grep -o 'R\.string\.[a-z_]*' "$SRC" | sort -u | awk -F. '{ printf "const val %s = %d\n", $3, NR }'
  echo "} }"
} > "$W/QuireStub.kt"
"$AOSP/external/kotlinc/bin/kotlinc" -nowarn -jvm-target 17 -language-version 2.2 -include-runtime -d "$W/c.jar" \
  "$SRC" "$W/QuireStub.kt" "$Q"/tests/connectors/*.kt 2> >(grep -v "unable to find kotlin-stdlib" >&2)
"$JAVA_HOME/bin/java" -cp "$W/c.jar" dev.openbook.quire.test.ConnectorsCheckKt
