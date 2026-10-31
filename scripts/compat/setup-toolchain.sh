#!/usr/bin/env bash
# Fetch the pinned, checksum-verified toolchain for the ARM-compat probes into ~/anybook/compat and build
# the anybook-ndk container. The Android SDK parts fall under the Android SDK License: local use only.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}; C=$A/compat; D=$C/dl; SDK=$C/sdk
R=https://dl.google.com/android/repository
mkdir -p "$D" "$SDK/build-tools" "$SDK/platforms" "$C/src"

sha1get(){  # file sha1 url
  if [ -f "$D/$1" ] && echo "$2  $D/$1" | sha1sum -c --quiet - 2>/dev/null; then return 0; fi
  curl -fL -o "$D/$1" "$3"; echo "$2  $D/$1" | sha1sum -c -
}
# Versions and checksums from https://dl.google.com/android/repository/repository2-3.xml (2026-10-15)
sha1get android-ndk-r30-linux.zip 5107f898313790e449e87eee2183d9a20602dee9 $R/android-ndk-r30-linux.zip
sha1get build-tools_r37_linux.zip 70954e99f4c3d9d46ee70fa32624672fe7cd6ebe $R/build-tools_r37_linux.zip
sha1get platform-36_r02.zip 2c1a80dd4d9f7d0e6dd336ec603d9b5c55a6f576 $R/platform-36_r02.zip
[ -x "$SDK/ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/clang" ] || {
  rm -rf "$SDK/android-ndk-r30"; unzip -q "$D/android-ndk-r30-linux.zip" -d "$SDK"; rm -rf "$SDK/ndk"; mv "$SDK/android-ndk-r30" "$SDK/ndk"; }
[ -x "$SDK/build-tools/37.0.0/aapt2" ] || {
  unzip -q -o "$D/build-tools_r37_linux.zip" -d "$SDK/build-tools"; rm -rf "$SDK/build-tools/37.0.0"
  mv "$SDK/build-tools/android-37.0" "$SDK/build-tools/37.0.0"; }
[ -f "$SDK/platforms/android-36/android.jar" ] || unzip -q -o "$D/platform-36_r02.zip" -d "$SDK/platforms"

# CoreMark (EEMBC), pinned commit; Apache-2.0 code plus the CoreMark trademark acceptable-use terms
CM_REV=1f483d5b8316753a742cbf5590caf5bd0a4e4777
CM_SHA256=4067e7f260218df13f2875d8f821a8ff32a84153c6e0759d7c89f96c0a8bf987
CM_TGZ=$D/coremark-$CM_REV.tar.gz
[ -f "$CM_TGZ" ] && echo "$CM_SHA256  $CM_TGZ" | sha256sum -c --quiet - 2>/dev/null || \
  curl -fL -o "$CM_TGZ" "https://github.com/eembc/coremark/archive/$CM_REV.tar.gz"
echo "$CM_SHA256  $CM_TGZ" | sha256sum -c -
[ -f "$C/src/coremark/core_main.c" ] || {
  rm -rf "$C/src/coremark" "$C/src/coremark-$CM_REV"; tar xzf "$CM_TGZ" -C "$C/src"; mv "$C/src/coremark-$CM_REV" "$C/src/coremark"; }

docker image inspect anybook-ndk >/dev/null 2>&1 || docker build -t anybook-ndk -f "$REPO/tools/Dockerfile.ndk" "$REPO/tools"
echo "toolchain ready in $SDK"
