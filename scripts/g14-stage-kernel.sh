#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Stage ANAL-198's G14 kernel packaging into the AOSP tree for the anybook_g14_x86_64 product (ANAL-199):
#   <data dir>/kernel/g14/<dist>/images/{bzImage,vendor_dlkm.img,system_dlkm.img,vendor_boot-ramdisk.lz4}
#   <data dir>/kernel/g14/<dist>/firmware/{firmware.mk,vendor/firmware/...}   (not kernel/g14/firmware: an older
#   staging without the CS35L56 10431024 tuning)
#   -> <data dir>/aosp/src/vendor/anybook/g14-kernel/   (never committed; reflink copies)
# Checks every image against the dist's images.json, so a bzImage and a system_dlkm from different builds
# (MODULE_SIG_PROTECT rejects that at boot) cannot be staged together. Writes PROVENANCE.txt.
#
# usage: g14-stage-kernel.sh [DIST]     DIST defaults to anybook-g14-gbos-16302624
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
DIST=${1:-anybook-g14-gbos-16302624}
K=$A/kernel/g14/$DIST
FW=$K/firmware
O=$A/aosp/src/vendor/anybook/g14-kernel
if docker ps --format '{{.Names}}' | grep -qx anybook-aosp-build; then
  echo "an AOSP build (anybook-aosp-build) is running; stage before or after it" >&2; exit 1
fi
[ -f "$K/images.json" ] || { echo "no packaging at $K: run scripts/kernel-g14-package.sh" >&2; exit 1; }
[ -f "$FW/firmware.mk" ] || { echo "no firmware staging at $FW: run scripts/kernel-g14-package.sh" >&2; exit 1; }

files=(bzImage vendor_dlkm.img system_dlkm.img vendor_boot-ramdisk.lz4)
for f in "${files[@]}"; do
  want=$(python3 -c 'import json,sys; print(next(e["sha256"] for e in json.load(open(sys.argv[1])) if e["file"] == sys.argv[2]))' "$K/images.json" "$f")
  have=$(sha256sum "$K/images/$f" | cut -d' ' -f1)
  [ "$want" = "$have" ] || { echo "$f: sha256 $have, images.json says $want" >&2; exit 1; }
done

rm -rf "$O.new"
mkdir -p "$O.new/firmware"
for f in "${files[@]}"; do cp --reflink=auto --preserve=timestamps "$K/images/$f" "$O.new/"; done
cp --reflink=auto --preserve=timestamps "$K/images.json" "$K/images.md" "$O.new/"
cp -r --reflink=auto --preserve=timestamps "$FW/vendor" "$FW/firmware.mk" "$FW"/firmware-manifest.* "$O.new/firmware/"
{
  echo "staged: $(date -u +%FT%TZ) by scripts/g14-stage-kernel.sh"
  echo "kernel dist: $A/kernel/dist/$DIST"
  echo "packaging: $K"
  echo "release: $(strings "$O.new/bzImage" | grep -m1 -oE '[0-9]+\.[0-9]+\.[0-9]+-android[0-9]+-[0-9]+-g[0-9a-f]+')"
  echo "firmware: $(find "$O.new/firmware/vendor/firmware" -type f | wc -l) files"
  (cd "$O.new" && sha256sum "${files[@]}")
} > "$O.new/PROVENANCE.txt"
rm -rf "$O"
mv "$O.new" "$O"
cat "$O/PROVENANCE.txt"
