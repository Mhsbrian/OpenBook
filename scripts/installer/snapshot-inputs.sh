#!/usr/bin/env bash
# Snapshot the read-only inputs of the boot-chain prototype into ~/anybook/installer/inputs/<label>:
# Android images from an AOSP PRODUCT_OUT (never built here; the AOSP lane owns that tree) and a kernel dist.
# Copies are reflinks (no data copied on btrfs). Writes provenance.txt with fingerprints and sha256s.
#
# usage: snapshot-inputs.sh [LABEL]
# env: SNAP_PRODUCT  PRODUCT_OUT (default ~/anybook/aosp/src/out/target/product/vsoc_x86_64_only)
#      SNAP_KDIST    kernel dist (default ~/anybook/kernel/dist/anybook-amd-gbos-16302624)
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}
P=${SNAP_PRODUCT:-$A/aosp/src/out/target/product/vsoc_x86_64_only}
K=${SNAP_KDIST:-$A/kernel/dist/anybook-amd-gbos-16302624}
LABEL=${1:-$(date -u +%Y%m%dT%H%M%SZ)}
O=$A/installer/inputs/$LABEL
if docker ps --format '{{.Names}}' | grep -qx anybook-aosp-build; then
  echo "an AOSP build (anybook-aosp-build) is running; PRODUCT_OUT may be half-written. Try later." >&2; exit 1
fi
mkdir -p "$O/product" "$O/kernel"
for f in boot.img init_boot.img vendor_boot.img super.img vbmeta.img vbmeta_system.img vbmeta_system_dlkm.img \
         vendor.img odm.img odm_dlkm.img \
         vbmeta_vendor_dlkm.img vendor-bootconfig.img userdata.img android-info.txt; do
  cp --reflink=auto --preserve=timestamps "$P/$f" "$O/product/"
done
for f in bzImage linux_banner.txt; do cp --reflink=auto --preserve=timestamps "$K/$f" "$O/kernel/"; done
{
  echo "snapshot: $(date -u +%FT%TZ)"
  echo "product_out: $P"
  for f in "$P"/build_fingerprint-*.txt; do echo "fingerprint file $(basename "$f") ($(date -u -r "$f" +%FT%TZ)): $(cat "$f")"; done
  echo "kernel_dist: $K"; cat "$K/linux_banner.txt" | head -1
  (cd "$O" && sha256sum product/* kernel/*)
} > "$O/provenance.txt"
echo "$O"
