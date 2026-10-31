#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build openbook-install (device/anybook/common/installer/engine) for the host tests, in the openbook-installer
# container. Since ANAL-211 the engine links the decoders it uses on Android: zlib (the container's), the LZMA SDK's
# xz decoder (external/lzma, as liblzma) and brotli's decoder (external/brotli, as libbrotli), compiled from the AOSP
# tree. Engines from before that (main's, for the "same plan" checks) are plain C with libc only.
#
# usage: engine-host-build.sh OUT [ENGINE_SRC_DIR]     (default: this tree's device/anybook/common/installer/engine)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
OUT=$(realpath -m "${1:?usage: engine-host-build.sh OUT [ENGINE_SRC_DIR]}"); SRC=$(realpath "${2:-$R/device/anybook/common/installer/engine}")
X=$A/aosp/src/external; LZ=$X/lzma/C; BR=$X/brotli/c
CF=(-O2 -g -Wall -Wextra -Werror -Wno-sign-compare -Wno-unused-parameter -Wno-format-truncation -Wno-missing-field-initializers)
LIBS=()
if ls "$SRC"/zipr.c >/dev/null 2>&1; then  # engines from before ANAL-211 are plain C with libc only
  LIBS=(-I"$LZ" -I"$BR/include" -DZ7_ST "$LZ"/{Xz,XzDec,XzCrc64,XzCrc64Opt,7zCrc,7zCrcOpt,CpuArch,Alloc,Lzma2Dec,LzmaDec,Bra,Bra86,BraIA64,Delta,Sha256,Sha256Opt}.c
        "$BR"/common/*.c "$BR"/dec/*.c -lz -lm)
fi
mkdir -p "$(dirname "$OUT")"
"$R/scripts/installer/inst-docker.sh" sh -c "gcc ${CF[*]} -o '$OUT' '$SRC'/*.c ${LIBS[*]}"
echo "$OUT"
