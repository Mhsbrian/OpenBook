#!/usr/bin/env bash
# Build the ARM-compat probe APKs and CoreMark binaries with NDK r30, without Gradle (ANAL-180):
#   anybook-probe-arm64.apk   lib/arm64-v8a only      (package dev.anybook.probe.arm64)
#   anybook-probe-armv7.apk   lib/armeabi-v7a only    (package dev.anybook.probe.armv7)
#   anybook-probe-x86_64.apk  lib/x86_64 only, native control (package dev.anybook.probe.x86_64)
#   bench/coremark-{arm64,armv7,x86_64}  unmodified CoreMark, posix port, PIE executables
# Output: ~/anybook/compat/out/probes. Re-executes itself inside the anybook-ndk container.
set -euo pipefail
if [ -z "${ANYBOOK_IN_CONTAINER:-}" ]; then
  REPO=$(cd "$(dirname "$0")/../.." && pwd); A=${ANYBOOK_HOME:-$HOME/anybook}
  "$REPO/scripts/compat/setup-toolchain.sh"
  exec docker run --rm -u "$(id -u):$(id -g)" -e ANYBOOK_IN_CONTAINER=1 -e HOME=/tmp \
    -v "$REPO:/r:ro" -v "$A/compat:/c" anybook-ndk /r/scripts/compat/build-probes.sh "$@"
fi
SDK=/c/sdk; BT=$SDK/build-tools/37.0.0; JAR=$SDK/platforms/android-36/android.jar
TC=$SDK/ndk/toolchains/llvm/prebuilt/linux-x86_64
SRC=/r/scripts/compat/probe; CM=/c/src/coremark; OUT=/c/out/probes; W=/c/out/build
API=30
rm -rf "$W" "$OUT"; mkdir -p "$W" "$OUT/bench" /c/keys
KS=/c/keys/probe-debug.keystore   # local throwaway signing key, never committed
[ -f $KS ] || keytool -genkeypair -keystore $KS -storepass android -keypass android -alias probe -keyalg RSA \
  -keysize 2048 -validity 10000 -dname "CN=AnyBook compat probe, O=AnyBook" >/dev/null 2>&1

javac --release 11 -nowarn -cp "$JAR" -d "$W/classes" $(find "$SRC/java" -name '*.java')
"$BT/d8" --release --min-api $API --lib "$JAR" --output "$W" $(find "$W/classes" -name '*.class')

CM_SRCS="$CM/core_list_join.c $CM/core_main.c $CM/core_matrix.c $CM/core_state.c $CM/core_util.c $CM/posix/core_portme.c"
for abi in arm64-v8a armeabi-v7a x86_64; do
  case $abi in
    arm64-v8a)   T=aarch64-linux-android;    S=arm64;  LIBT=aarch64-linux-android; X="" ;;
    armeabi-v7a) T=armv7a-linux-androideabi; S=armv7;  LIBT=arm-linux-androideabi; X="-mfpu=neon" ;;
    x86_64)      T=x86_64-linux-android;     S=x86_64; LIBT=x86_64-linux-android;  X="-mcx16" ;;
  esac
  CC="$TC/bin/clang --target=$T$API"; CXX="$TC/bin/clang++ --target=$T$API"
  L=$W/$S/lib/$abi; mkdir -p "$L"
  CF="-O2 -fPIC -ffp-contract=off -Wall -Wno-unused-function $X"
  $CXX $CF -std=c++20 -shared -o "$L/libprobe.so" "$SRC/jni/probe.cpp" -llog -lEGL -lGLESv3 -landroid
  $CXX $CF -std=c++20 -shared -o "$L/libprobeplugin.so" "$SRC/jni/plugin.cpp"
  cp "$TC/sysroot/usr/lib/$LIBT/libc++_shared.so" "$L/"
  CMF="-O2 $X (NDK r30 clang, $T$API)"
  $CC -O2 -fPIC $X -shared -o "$L/libcmark.so" -I"$CM" -I"$CM/posix" -Dmain=coremark_main -DPERFORMANCE_RUN=1 \
    -DFLAGS_STR="\"$CMF\"" $CM_SRCS "$SRC/jni/cmark_jni.c"
  $CC -O2 $X -o "$OUT/bench/coremark-$S" -I"$CM" -I"$CM/posix" -DPERFORMANCE_RUN=1 -DFLAGS_STR="\"$CMF\"" $CM_SRCS
  sed "s/@PKG@/dev.anybook.probe.$S/; s/@ABI@/$abi/" "$SRC/AndroidManifest.xml" > "$W/$S/AndroidManifest.xml"
  "$BT/aapt2" link -o "$W/$S/unsigned.apk" -I "$JAR" --manifest "$W/$S/AndroidManifest.xml" --min-sdk-version $API \
    --target-sdk-version 36 --version-code 1 --version-name 1.0-anal180
  (cd "$W" && zip -q -X "$S/unsigned.apk" classes.dex)
  (cd "$W/$S" && zip -q -X -r unsigned.apk lib)
  "$BT/zipalign" -P 16 -f 4 "$W/$S/unsigned.apk" "$W/$S/aligned.apk"
  "$BT/apksigner" sign --ks $KS --ks-pass pass:android --key-pass pass:android \
    --out "$OUT/anybook-probe-$S.apk" "$W/$S/aligned.apk"
done
# Same benchmark as a static x86_64 binary, to time the host CPU outside the VM.
$TC/bin/clang --target=x86_64-linux-android$API -O2 -static -o "$OUT/bench/coremark-x86_64-static" -I"$CM" -I"$CM/posix" \
  -DPERFORMANCE_RUN=1 -DFLAGS_STR="\"-O2 -static (NDK r30 clang, x86_64-linux-android$API)\"" $CM_SRCS
"$TC/bin/clang" --version | head -1 > "$OUT/TOOLCHAIN"
echo "NDK r30 (30.0.16248370), build-tools 37.0.0, platform android-36, minSdk $API" >> "$OUT/TOOLCHAIN"
(cd "$OUT" && sha256sum *.apk bench/* > SHA256SUMS && cat SHA256SUMS)
