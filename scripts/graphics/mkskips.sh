#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The graphics check's skip lists (ANAL-177), taken from Mesa CI's own files in the Mesa tree the image is built from
# (src/amd/ci): only tests Mesa CI skips because they hang AMD GPUs, time out or take minutes. Tests Mesa skips for
# other reasons stay in (.gitlab-ci/all-skips.txt drops dEQP-VK.info.device_extensions, which the Android CTS runs),
# so the report shows them. deqp-runner reads the lists as regular expressions.
#   radv.txt      radv-skips.txt (GPU hangs) + radv-slow-skips.txt
#   radeonsi.txt  the dEQP lines of radeonsi-mendocino-skips.txt and radeonsi-vangogh-skips.txt (time-outs)
#   angle.txt     nothing yet: ANGLE runs on RADV, and no ANGLE dEQP case is known to hang AMD GPUs
# usage: mkskips.sh MESA_SRC OUT_DIR
set -euo pipefail
M=${1:?usage: mkskips.sh MESA_SRC OUT_DIR}; O=${2:?usage: mkskips.sh MESA_SRC OUT_DIR}; C=$M/src/amd/ci
mkdir -p "$O"
v="Mesa $(cat "$M/VERSION") ($(git -C "$M" rev-parse --short HEAD 2>/dev/null || echo unknown))"
hdr() { echo "# OpenBook graphics check skip list, from $v:"; for f in "$@"; do echo "#   src/amd/ci/$f $(sha256sum "$C/$f" | cut -c1-16)"; done; }
{ hdr radv-skips.txt radv-slow-skips.txt; grep -hvE '^\s*(#|$)' "$C/radv-skips.txt" "$C/radv-slow-skips.txt"; } > "$O/radv.txt"
{ hdr radeonsi-mendocino-skips.txt radeonsi-vangogh-skips.txt
  grep -h '^dEQP-' "$C/radeonsi-mendocino-skips.txt" "$C/radeonsi-vangogh-skips.txt" | sort -u; } > "$O/radeonsi.txt"
echo "# OpenBook graphics check skip list for ANGLE: empty (see scripts/graphics/mkskips.sh)" > "$O/angle.txt"
wc -l "$O"/*.txt | sed 's/^/mkskips: /'
