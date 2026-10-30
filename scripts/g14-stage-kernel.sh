#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Stage ANAL-198's G14 kernel packaging into the AOSP tree for the anybook_g14_x86_64 product (ANAL-199):
#   <data dir>/kernel/g14/<dist>/images/{bzImage,vendor_dlkm.img,system_dlkm.img,vendor_boot-ramdisk.lz4}
#   <data dir>/kernel/g14/<dist>/firmware/{firmware.mk,vendor/firmware/...}   (not kernel/g14/firmware: an older
#   staging without the CS35L56 10431024 tuning)
#   -> <data dir>/aosp/src/vendor/anybook/g14-kernel/   (never committed; reflink copies)
# Checks every image against the dist's images.json, so a bzImage and a system_dlkm from different builds
# (MODULE_SIG_PROTECT rejects that at boot) cannot be staged together. Writes PROVENANCE.txt.
# When the dist's vendor_dlkm carries NVIDIA's open modules (ANAL-297), their GSP firmware is staged too, from
# scripts/kernel-nvidia-open-firmware.py's output (G14_NVIDIA_FIRMWARE, default <packaging>/firmware-nvidia-open),
# into firmware-nvidia-open/; every file must match kernel/firmware/anybook-nvidia-open.tsv. nvidia.ko without its
# firmware is refused: it could never start the GPU.
#
# usage: [G14_NVIDIA_FIRMWARE=DIR] g14-stage-kernel.sh [DIST]     DIST defaults to anybook-g14-gbos-16302624
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
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
NVFW=
if grep -q '^/vendor/lib/modules/nvidia\.ko:' "$K/lists/vendor_dlkm.bm.modules.dep" 2>/dev/null; then
  NVFW=${G14_NVIDIA_FIRMWARE:-$K/firmware-nvidia-open}
  [ -f "$NVFW/firmware-nvidia-open.mk" ] || {
    echo "$DIST carries nvidia.ko but no GSP firmware is staged at $NVFW:" >&2
    echo "  run scripts/kernel-nvidia-open-firmware.py --pin kernel/firmware/anybook-nvidia-open.tsv --out DIR" >&2
    echo "  and set G14_NVIDIA_FIRMWARE=DIR" >&2; exit 1; }
  # Every file and licence row of the pin: kind, package path or URL, install path under /vendor/firmware, sha256.
  while IFS=$'\t' read -r kind _ path sha _; do
    case $kind in file|licence) ;; *) continue ;; esac
    have=$(sha256sum "$NVFW/vendor/firmware/$path" 2>/dev/null | cut -d' ' -f1)
    [ "$have" = "$sha" ] || { echo "NVIDIA firmware $path: sha256 ${have:-missing}, the pin says $sha" >&2; exit 1; }
  done < <(grep -v '^#' "$R/kernel/firmware/anybook-nvidia-open.tsv")
fi

rm -rf "$O.new"
mkdir -p "$O.new/firmware"
for f in "${files[@]}"; do cp --reflink=auto --preserve=timestamps "$K/images/$f" "$O.new/"; done
cp --reflink=auto --preserve=timestamps "$K/images.json" "$K/images.md" "$O.new/"
cp -r --reflink=auto --preserve=timestamps "$FW/vendor" "$FW/firmware.mk" "$FW"/firmware-manifest.* "$O.new/firmware/"
if [ -n "$NVFW" ]; then
  mkdir -p "$O.new/firmware-nvidia-open"
  cp -r --reflink=auto --preserve=timestamps "$NVFW/vendor" "$NVFW/firmware-nvidia-open.mk" \
    "$NVFW"/firmware-manifest-nvidia-open.* "$O.new/firmware-nvidia-open/"
fi
{
  echo "staged: $(date -u +%FT%TZ) by scripts/g14-stage-kernel.sh"
  echo "kernel dist: $A/kernel/dist/$DIST"
  echo "packaging: $K"
  echo "release: $(strings "$O.new/bzImage" | grep -m1 -oE '[0-9]+\.[0-9]+\.[0-9]+-android[0-9]+-[0-9]+-g[0-9a-f]+')"
  echo "firmware: $(find "$O.new/firmware/vendor/firmware" -type f | wc -l) files"
  if [ -n "$NVFW" ]; then
    echo "nvidia firmware: $(find "$O.new/firmware-nvidia-open/vendor/firmware" -type f | wc -l) files from $NVFW"
  else
    echo "nvidia firmware: none (no nvidia.ko in vendor_dlkm)"
  fi
  (cd "$O.new" && sha256sum "${files[@]}")
} > "$O.new/PROVENANCE.txt"
rm -rf "$O"
mv "$O.new" "$O"
cat "$O/PROVENANCE.txt"
