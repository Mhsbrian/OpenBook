#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run inside inst-docker.sh; OUT must be a new directory of regular test files.
set -euo pipefail
log_repo=$(cd "$(dirname "$0")/../.." && pwd)
log_engine=$log_repo/device/anybook/common/installer/engine
log_out=${1:?usage: usb-log-test.sh NEW_OUT_DIRECTORY}
[ ! -e "$log_out" ] && [ ! -L "$log_out" ] || { echo 'Output already exists' >&2; exit 2; }
mkdir -p "$log_out"
gcc -static -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -Wl,--gc-sections \
  -I "$log_engine" "$log_repo/scripts/googlebook/usb-log-test.c" "$log_engine/fat.c" "$log_engine/util.c" \
  -o "$log_out/test"
"$log_out/test" "$log_out/fat.img"
fsck.fat -n "$log_out/fat.img"
