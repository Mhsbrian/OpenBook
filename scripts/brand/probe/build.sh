#!/usr/bin/env bash
# Build brand-probe.jar (BrandProbe.java, a dex for app_process) with the AOSP tree's JDK, public SDK stubs and d8.
# usage: scripts/brand/probe/build.sh OUT_JAR      Env: AOSP_SRC (default ~/anybook/aosp/src, built: needs out/host d8)
set -euo pipefail
D=$(cd "$(dirname "$0")" && pwd); OUT=${1:?usage: build.sh OUT_JAR}
S=${AOSP_SRC:-${ANYBOOK_HOME:-$HOME/anybook}/aosp/src}
JDK=$S/prebuilts/jdk/jdk21/linux-x86; SDK=$S/prebuilts/sdk/current/public/android.jar; D8=$S/out/host/linux-x86/bin/d8
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
"$JDK/bin/javac" --release 17 -cp "$SDK" -d "$T/classes" "$D/BrandProbe.java"
JAVA_HOME=$JDK PATH=$JDK/bin:$PATH "$D8" --min-api 30 --lib "$SDK" --output "$T" "$T"/classes/*.class
mkdir -p "$(dirname "$OUT")"; (cd "$T" && zip -q -X "$(realpath -m "$OUT")" classes.dex)
echo "$OUT"
