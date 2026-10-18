#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the install engine twice for the host, from this tree and from origin/main, and run engine-addon-test.py
# (the installer's add-on path, ANAL-210) against a live image and the microG add-on, in the openbook-installer
# container. Image files only.
#
# usage: engine-addon-test.sh LIVE.img ADDON_DIR RUN     results: <data dir>/logs/installer/RUN/{results.json,SUMMARY.md}
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
D=$R/scripts/installer/inst-docker.sh
IMG=$(realpath "${1:?usage: engine-addon-test.sh LIVE.img ADDON_DIR RUN}"); U=$(realpath "${2:?add-on}"); RUN=${3:?run name}
L=$A/logs/installer/$RUN; W=$A/installer/work/$RUN
mkdir -p "$L" "$W" "$A/installer/build"
OLD=$W/old-src; rm -rf "$OLD"; mkdir -p "$OLD"
git -C "$R" archive origin/main device/anybook/common/installer/engine | tar -x -C "$OLD"
CF=(-O2 -g -Wall -Wextra -Werror -Wno-sign-compare -Wno-unused-parameter -Wno-format-truncation -Wno-missing-field-initializers)
B=$A/installer/build/openbook-install-host-g1; BO=$A/installer/build/openbook-install-host-main
"$D" gcc "${CF[@]}" -o "$B" "$R"/device/anybook/common/installer/engine/*.c
"$D" gcc "${CF[@]}" -o "$BO" "$OLD"/device/anybook/common/installer/engine/*.c
echo "engine $(git -C "$R" rev-parse --short HEAD)$( [ -z "$(git -C "$R" status --porcelain)" ] || echo +dirty) vs origin/main $(git -C "$R" rev-parse --short origin/main)" > "$L/engines.txt"
rc=0
"$D" python3 "$R/scripts/microg/engine-addon-test.py" --engine "$B" --old "$BO" --image "$IMG" --addon "$U" \
  --catalog "$R/device/anybook/common/addons/microg.json" --run "$W" || rc=$?
cp "$W/results.json" "$W/SUMMARY.md" "$L/"
echo "results: $L/SUMMARY.md"
exit $rc
