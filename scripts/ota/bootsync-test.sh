#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build openbook-bootsync and the install engine for the host and run bootsync's host tests (scripts/ota/
# bootsync-test.py) on a whole-disk install of LIVE.img, in the openbook-installer container. Image files only.
#
# usage: bootsync-test.sh LIVE.img RUN [SLOT_IMAGES_DIR [ALT_IMAGES_DIR]]
#   SLOT_IMAGES_DIR: boot.img, init_boot.img, vendor_boot.img and vbmeta.img of the build to update to (default: the
#   stick's own slot A). Results: <data dir>/logs/ota/RUN/{results.json,SUMMARY.md}
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
D=$R/scripts/installer/inst-docker.sh
IMG=$(realpath "${1:?usage: bootsync-test.sh LIVE.img RUN [SLOT_IMAGES_DIR [ALT_IMAGES_DIR]]}"); RUN=${2:?run name}
L=$A/logs/ota/$RUN; W=$A/installer/work/ota-$RUN; B=$A/installer/build
mkdir -p "$L" "$W" "$B"
"$R/scripts/installer/engine-host-build.sh" "$B/openbook-install-host" >/dev/null
E=$R/device/anybook/common/installer/engine
"$D" sh -c "gcc -O2 -g -Wall -Wextra -Werror -Wno-sign-compare -Wno-unused-parameter -Wno-format-truncation \
  -Wno-missing-field-initializers -I'$E' -o '$B/openbook-bootsync-host' '$R/device/anybook/common/bootsync/bootsync.c' \
  '$E/fat.c' '$E/gpt.c' '$E/util.c'"
X=()
[ -n "${3:-}" ] && X+=(--slot-images "$(realpath "$3")")
[ -n "${4:-}" ] && X+=(--alt-images "$(realpath "$4")")
set +e
"$D" python3 "$R/scripts/ota/bootsync-test.py" --bootsync "$B/openbook-bootsync-host" --engine "$B/openbook-install-host" \
  --image "$IMG" --run "$W" "${X[@]}"
rc=$?
set -e
cp "$W/results.json" "$W/SUMMARY.md" "$L/" 2>/dev/null || true
rm -rf "$L/bootsync" && cp -r "$W/bootsync" "$L/" 2>/dev/null || true
echo "results: $L/SUMMARY.md"
exit $rc
