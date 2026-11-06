#!/usr/bin/env bash
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Host tests for the Terminal app's OpenBook install (ANAL-393, docs/quire-setup.md §4.1 and §8): the Android-free
# classes that aosp/patches/packages/modules/Virtualization/0003 adds (openbook/*.kt), compiled with the AOSP tree's
# kotlinc and JDK together with ImageArchiveTest.kt, against the oldest commons-compress API in the tree (1.8.1, a
# subset of the 1.19 the app links), and run on the JVM. No device, no Soong. A local HTTP server stands in for the
# image's host.
#
# usage: image-archive-test.sh [VIRTUALIZATION_PROJECT]
#   VIRTUALIZATION_PROJECT: packages/modules/Virtualization with the patch applied
#   (default: $AOSP/packages/modules/Virtualization).   Env: AOSP (default ~/anybook/aosp/src)
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AOSP="${AOSP:-$HOME/anybook/aosp/src}"
VIRT="${1:-$AOSP/packages/modules/Virtualization}"
SRC="$VIRT/android/TerminalApp/java/com/android/virtualization/terminal/openbook"
[ -d "$SRC" ] || { echo "image-archive-test: no $SRC (is patch 0003 applied?)" >&2; exit 2; }
export JAVA_HOME="$AOSP/prebuilts/jdk/jdk21/linux-x86"
KOTLINC="$AOSP/external/kotlinc"
CC="$AOSP/prebuilts/devtools/tools/lib/commons-compress-1.8.1.jar"
W="$(mktemp -d "${TMPDIR:-/tmp}/obimg-test.XXXXXX")"
trap 'rm -rf "$W"' EXIT
"$KOTLINC/bin/kotlinc" -jvm-target 17 -language-version 2.2 -nowarn -cp "$CC" -d "$W/classes" \
  "$SRC"/*.kt "$here"/ImageArchiveTest.kt
mkdir -p "$W/tmp"
"$JAVA_HOME/bin/java" -Djava.io.tmpdir="$W/tmp" -cp "$W/classes:$CC:$KOTLINC/lib/kotlin-stdlib.jar" \
  openbook.test.ImageArchiveTestKt
