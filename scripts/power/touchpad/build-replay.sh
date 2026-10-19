#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Compile an isolated copy of AOSP's gestures library and the offline G14 replay.
# Never writes the AOSP tree, opens input devices, or injects host input.
set -euo pipefail
SRC=${1:?usage: build-replay.sh AOSP_EXTERNAL_LIBCHROME_GESTURES OUTPUT_DIR}
OUT=${2:?usage: build-replay.sh AOSP_EXTERNAL_LIBCHROME_GESTURES OUTPUT_DIR}
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$(realpath "$SRC")
mkdir -p "$OUT"
OUT=$(realpath "$OUT")
if [ -e "$OUT/gestures" ]; then
  echo "choose a fresh output directory: $OUT/gestures already exists" >&2
  exit 1
fi
pkg-config --exists jsoncpp gtest
command -v clang++ >/dev/null
mkdir "$OUT/gestures"
cp -a "$SRC/src" "$SRC/include" "$SRC/Makefile" "$SRC/LICENSE" "$OUT/gestures/"
git -C "$SRC" rev-parse HEAD > "$OUT/source-commit.txt"
# Include source dirtiness in provenance; a revision alone is insufficient.
git -C "$SRC" status --short > "$OUT/source-status.txt"
git -C "$SRC" diff HEAD --binary > "$OUT/source-diff.patch"
make -C "$OUT/gestures" -j"${JOBS:-8}" CXX=clang++ \
  CXXFLAGS="-std=c++20 -O2 -fPIC -DGESTURES_INTERNAL=1 -DVCSID=\\\"OpenBook-reference\\\" -I. $(pkg-config --cflags jsoncpp gtest)" \
  > "$OUT/build.log" 2>&1
clang++ -std=c++20 -Wall -Wextra -Werror -Wno-unused-parameter -O2 \
  -I"$OUT/gestures" $(pkg-config --cflags jsoncpp gtest) \
  "$HERE/gesture-replay.cc" "$OUT/gestures/obj/libgestures.so.0" \
  $(pkg-config --libs jsoncpp) -Wl,-rpath,'$ORIGIN/gestures/obj' -o "$OUT/gesture-replay"
echo "built $OUT/gesture-replay; source $(cat "$OUT/source-commit.txt")"
