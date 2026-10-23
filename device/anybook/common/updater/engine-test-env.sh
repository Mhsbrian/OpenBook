#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# A device-like shell environment for the engine's host tests: Android's own mksh (R59) and one-true-awk,
# built from the AOSP tree, with toybox applets from the OpenBook OTA tools, first on PATH as sh and awk.
# The laptop runs exactly these (openbook-updater-device-test.sh checks the laptop itself).
#
# usage: engine-test-env.sh      prints the bin directory; then
#        OPENBOOK_UPDATER_TEST_ENV=$(engine-test-env.sh) python3 openbook-updater-test.py
# env:   AOSP_SRC (default ~/anybook/aosp/src), OTATOOLS (default ~/anybook/ota/builds/ota-dev1/otatools),
#        OUT (default ~/anybook/toolchain/engine-test)
set -euo pipefail
AOSP_SRC=${AOSP_SRC:-$HOME/anybook/aosp/src}
OTATOOLS=${OTATOOLS:-$HOME/anybook/ota/builds/ota-dev1/otatools}
OUT=${OUT:-$HOME/anybook/toolchain/engine-test}
BIN=$OUT/bin
if [ ! -x "$OUT/mksh/mksh" ]; then
  rm -rf "$OUT/mksh"; mkdir -p "$OUT"; cp -r "$AOSP_SRC/external/mksh/src" "$OUT/mksh"
  (cd "$OUT/mksh" && sh Build.sh > build.log 2>&1) || { tail -20 "$OUT/mksh/build.log" >&2; exit 1; }
fi
if [ ! -x "$OUT/awk/a.out" ]; then
  rm -rf "$OUT/awk"; cp -r "$AOSP_SRC/external/one-true-awk" "$OUT/awk"
  (cd "$OUT/awk" && make YACC="bison -d" a.out > build.log 2>&1) || { tail -20 "$OUT/awk/build.log" >&2; exit 1; }
fi
mkdir -p "$BIN"
ln -sf "$OUT/mksh/mksh" "$BIN/sh"; ln -sf "$OUT/mksh/mksh" "$BIN/mksh"; ln -sf "$OUT/awk/a.out" "$BIN/awk"
for t in cat cp cut date flock grep head md5sum mkdir mv printf rm rmdir sed sleep sort stat tail tee timeout tr; do
  ln -sf "$OTATOOLS/bin/toybox" "$BIN/$t"
done
"$BIN/sh" -c 'case $KSH_VERSION in *R59*) ;; *) echo "unexpected mksh: $KSH_VERSION" >&2; exit 1 ;; esac'
echo "$BIN"
