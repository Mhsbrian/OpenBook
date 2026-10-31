#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the OpenBook power check (ANAL-178): an add-on for an OpenBook live USB stick that boots the hardware-check
# probe (scripts/installer/probe-init.c, v7) with the S0i3 investigation, writes its report to the stick and powers
# off. See scripts/power/mkaddon.py for what goes on the stick and docs/power-input.md for the owner steps.
# Image files only: this script never writes to a disk or USB stick. Adding it to a stick is
# scripts/power/add-to-live-stick.sh, which needs the owner's confirmation of the exact /dev/disk/by-id device.
#
# usage: make-power-check.sh [NAME]          NAME default openbook-powercheck-<UTC date>
# Output in <data dir>/installer/out/: NAME-addon/ (the files, MANIFEST.sha256, EXPECT) and NAME-addon.json.
# Needs the installer image built from tools/Dockerfile.installer (make, for the test modules):
#   docker build -t openbook-installer:anal178 -f tools/Dockerfile.installer tools
#   OPENBOOK_INSTALLER_IMAGE=openbook-installer:anal178 scripts/power/make-power-check.sh
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); S=$R/scripts/installer; D=$S/inst-docker.sh
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer
NAME=${1:-openbook-powercheck-$(date -u +%Y%m%d)}
case $NAME in *[!A-Za-z0-9._-]*) echo "name: letters, digits, . _ - only" >&2; exit 2 ;; esac
DIST=${CHECK_KDIST:-$A/kernel/dist/anybook-amd-gbos-16302624}   # the check's kernel (bzImage 6d964789...)
MODS=${CHECK_MODULES:-$A/kernel/cf/modset-anybook/root/lib/modules}   # ANAL-172's module set for that kernel
FW=${HWCHECK_FIRMWARE:-$A/kernel/firmware/anybook-amd}   # ANAL-171 linux-firmware subset
W=$I/powercheck/$NAME; O=$I/out
REL=$(sed -n 's/^Linux version \([^ ]*\) .*/\1/p' "$DIST/linux_banner.txt")
[ -n "$REL" ] && [ -d "$MODS/$REL" ] || { echo "no module set for '$REL' in $MODS" >&2; exit 2; }
"$D" sh -c 'command -v make >/dev/null' || {
  echo "the installer image has no make: build it from tools/Dockerfile.installer (see the header)" >&2; exit 2; }
mkdir -p "$W" "$O" "$I/build"
LOG=$A/logs/power/powercheck-$NAME-$(date -u +%Y%m%dT%H%M%SZ).log
mkdir -p "$(dirname "$LOG")"
exec > >(tee -a "$LOG") 2>&1
echo "== make-power-check.sh $NAME ($(date -u +%FT%TZ)), repo $(git -C "$R" rev-parse --short HEAD)$(git -C "$R" diff --quiet HEAD -- scripts || echo '+dirty')"

# 1. probe and test-only modules, each in this build's own directory
"$D" gcc -static -O2 -Wall -Wno-format-truncation -o "$W/openbook-probe" "$S/probe-init.c"
CHECK_KMOD_OUT=$W/kmod "$S/build-check-kmod.sh"
# 2. firmware: the subset plus wireless-regdb (cfg80211 asks for regulatory.db), with its licence
"$D" bash -c "rm -rf '$W/firmware' && cp -r '$FW' '$W/firmware' && cp /usr/lib/firmware/regulatory.db \
  /usr/lib/firmware/regulatory.db.p7s '$W/firmware/' && mkdir -p '$W/firmware/LICENSES' && \
  cp /usr/share/licenses/wireless-regdb/LICENSE '$W/firmware/LICENSES/LICENSE.wireless-regdb'"
# 3. the add-on
"$D" python3 "$R/scripts/power/mkaddon.py" --kernel "$DIST/bzImage" --modules "$MODS/$REL" --firmware "$W/firmware" \
  --kmod "$W/kmod" --probe "$W/openbook-probe" --out "$O/$NAME-addon" --name "$NAME"
du -sh "$O/$NAME-addon"
echo "add-on: $O/$NAME-addon ($O/$NAME-addon.json); log: $LOG"
