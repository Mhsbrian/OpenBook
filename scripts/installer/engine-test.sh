#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build openbook-install (device/anybook/common/installer/engine) for the host and run its tests
# (scripts/installer/engine-test.py) against a live image, in the openbook-installer container. Image files only.
#
# usage: engine-test.sh LIVE.img RUN      results: <data dir>/logs/installer/RUN/{results.json,SUMMARY.md}
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$R/scripts/installer; D=$S/inst-docker.sh
IMG=$(realpath "${1:?usage: engine-test.sh LIVE.img RUN}"); RUN=${2:?run name}
L=$A/logs/installer/$RUN; W=$A/installer/work/$RUN
mkdir -p "$L" "$W"
B=$A/installer/build/openbook-install-host
"$D" gcc -O2 -g -Wall -Wextra -Werror -Wno-sign-compare -Wno-unused-parameter -Wno-format-truncation \
  -Wno-missing-field-initializers -o "$B" "$R"/device/anybook/common/installer/engine/*.c
# Work files (copies of the stick, sparse targets) under $W; results and logs under $L.
"$D" python3 "$S/engine-test.py" --engine "$B" --image "$IMG" --run "$W"
cp "$W/results.json" "$W/SUMMARY.md" "$L/"
for d in plan whole alongside refuse-changed refuse-bad-stick refuse-mounted refuse-small; do
  [ -d "$W/$d" ] && mkdir -p "$L/$d" && find "$W/$d" -maxdepth 1 -name '*.json' -o -maxdepth 1 -name '*.log' -o -maxdepth 1 -name 'lpdump.txt' | xargs -r cp -t "$L/$d/"
done
echo "results: $L/SUMMARY.md"
