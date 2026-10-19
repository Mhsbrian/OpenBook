#!/usr/bin/env bash
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Compile-checks Quire (OpenBookQuire, and the QuireSecureProbe test helper) outside Soong: no lunch, no m, no lane
# lock. aapt2 compiles and links res/ and the manifest against android.jar (and generates R.java), then kotlinc
# compiles the sources against the framework header jar with hidden APIs (framework-minus-apex-headers
# turbine-combined, from any earlier build of the tree) and android.jar. Same approach as
# ../../installer/app/tools/compile-check.sh.
# Writes only under $OUT (default /tmp/quire-compile). Reads the AOSP tree at $AOSP (default ~/anybook/aosp/src).
set -euo pipefail
Q="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AOSP="${AOSP:-$HOME/anybook/aosp/src}"
OUT="${OUT:-/tmp/quire-compile}"
case "$OUT" in /tmp/*) ;; *) echo "compile-check: OUT must be under /tmp" >&2; exit 2 ;; esac

export JAVA_HOME="$AOSP/prebuilts/jdk/jdk21/linux-x86"
export PATH="$JAVA_HOME/bin:$PATH"
KOTLINC="$AOSP/external/kotlinc"
ANDROID_JAR="$AOSP/prebuilts/sdk/current/system/android.jar"
FRAMEWORK_JAR="$AOSP/out/soong/.intermediates/frameworks/base/framework-minus-apex-headers/android_common/turbine-combined/framework.jar"
[[ -f "$FRAMEWORK_JAR" ]] || { echo "compile-check: no $FRAMEWORK_JAR (build framework-minus-apex once)" >&2; exit 2; }
AAPT2=""
for cand in "$AOSP/out/host/linux-x86/bin/aapt2" "$AOSP/prebuilts/sdk/tools/linux/bin/aapt2"; do
  [[ -x "$cand" ]] && { AAPT2="$cand"; break; }
done
[[ -n "$AAPT2" ]] || { echo "compile-check: aapt2 not found" >&2; exit 2; }

# check NAME MANIFEST RES_DIR(or -) SRC_DIR CLASSPATH
check() {
  local name=$1 manifest=$2 res=$3 src=$4 cp=$5 o="$OUT/$1"
  rm -rf "$o"; mkdir -p "$o/gen" "$o/r-classes" "$o/classes"
  local flat=()
  if [[ $res != - ]]; then
    "$AAPT2" compile --dir "$res" -o "$o/res.zip"
    flat=("$o/res.zip")
  fi
  "$AAPT2" link -I "$ANDROID_JAR" --manifest "$manifest" --min-sdk-version 36 --target-sdk-version 37 \
    --auto-add-overlay --java "$o/gen" -o "$o/res-only.apk" "${flat[@]}"
  local rjava; rjava=$(find "$o/gen" -name '*.java')
  [[ -z $rjava ]] || javac -nowarn -source 17 -target 17 -cp "$ANDROID_JAR" -d "$o/r-classes" $rjava
  mapfile -t srcs < <(find "$src" -name '*.kt' | sort)
  set +e
  "$KOTLINC/bin/kotlinc" -no-jdk -no-stdlib -jvm-target 17 -language-version 2.2 \
    -cp "$cp:$o/r-classes:$KOTLINC/lib/kotlin-stdlib.jar" -d "$o/classes" "${srcs[@]}" 2>&1 | tee "$o/kotlinc.log"
  local rc=${PIPESTATUS[0]}
  set -e
  local errors; errors=$(grep -c ': error:\|^error:' "$o/kotlinc.log" || true)
  if [[ $rc -ne 0 || $errors -ne 0 ]]; then
    echo "compile-check: $name FAILED (kotlinc exit $rc, $errors errors; log: $o/kotlinc.log)"
    return 1
  fi
  echo "compile-check: $name OK (${#srcs[@]} Kotlin files, $(find "$o/classes" -name '*.class' | wc -l) classes," \
    "$(grep -c ': warning:\|^warning:' "$o/kotlinc.log" || true) warnings)"
}

check OpenBookQuire "$Q/app/AndroidManifest.xml" "$Q/app/res" "$Q/app/src" "$FRAMEWORK_JAR:$ANDROID_JAR"
check QuireSecureProbe "$Q/tests/secureprobe/AndroidManifest.xml" - "$Q/tests/secureprobe/src" \
  "$AOSP/prebuilts/sdk/current/public/android.jar"
