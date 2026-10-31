#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build openbook-addons (device/anybook/common/addons) for the host and run its tests (addons-test.py), in the
# openbook-installer container. Image files only.
#
# usage: addons-test.sh RUN      results: <data dir>/logs/installer/RUN/{results.json,SUMMARY.md}
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
D=$R/scripts/installer/inst-docker.sh
RUN=${1:?usage: addons-test.sh RUN}
L=$A/logs/installer/$RUN; W=$A/installer/work/$RUN
mkdir -p "$L" "$W" "$A/installer/build"
B=$A/installer/build/openbook-addons-host
E=$R/device/anybook/common/installer/engine
"$D" gcc -O2 -g -Wall -Wextra -Werror -Wno-sign-compare -Wno-unused-parameter -Wno-format-truncation \
  -Wno-missing-field-initializers -I"$E" -o "$B" "$R/device/anybook/common/addons/addons.c" "$E/util.c" "$E/gpt.c" "$E/fat.c"
rc=0; "$D" python3 "$R/scripts/microg/addons-test.py" --addons "$B" --run "$W" || rc=$?
cp "$W/results.json" "$W/SUMMARY.md" "$L/"
echo "results: $L/SUMMARY.md"
exit $rc
