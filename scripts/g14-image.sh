#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# USB-ready GPT disk image of the OpenBook G14 product (ANAL-199):
#   1. snapshots the product's images from PRODUCT_OUT (reflinks; refuses while an AOSP build runs);
#   2. builds the disk with scripts/installer/mkproduct.py in the openbook-installer container: systemd-boot on the
#      ESP, A/B boot partitions, super, blank metadata and userdata (docs/g14-product.md, docs/installer.md);
#   3. writes <name>.img, .img.json (layout, bootconfig, input hashes), .img.sha256 and, with --xz, .img.xz.
# Image files only: nothing here touches a disk. Writing a stick is a separate step that needs the owner's
# confirmation naming the /dev/disk/by-id/... device.
#
# usage: g14-image.sh [--label NAME] [--size-gib N] [--xz] [--product-out DIR]
#   default NAME openbook-g14-<build id>-<UTC date>; output in <data dir>/installer/out/
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/.." && pwd)
P=$A/aosp/src/out/target/product/anybook_g14
LABEL=; SIZE=12; XZ=0
while [ $# -gt 0 ]; do
  case $1 in
    --label) LABEL=$2; shift 2 ;;
    --size-gib) SIZE=$2; shift 2 ;;
    --xz) XZ=1; shift ;;
    --product-out) P=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
if docker ps --format '{{.Names}}' | grep -qx anybook-aosp-build; then
  echo "an AOSP build (anybook-aosp-build) is running; PRODUCT_OUT may be half-written. Try later." >&2; exit 1
fi
for f in boot.img init_boot.img vendor_boot.img vbmeta.img super.img; do
  [ -f "$P/$f" ] || { echo "$P/$f missing: build anybook_g14_x86_64-cp2a-userdebug first" >&2; exit 1; }
done
BID=$(sed -n 's/^ro.build.id=//p' "$P/system/build.prop" 2>/dev/null | head -1)
LABEL=${LABEL:-openbook-g14-${BID:-unknown}-$(date -u +%Y%m%d)}
IN=$A/installer/inputs/$LABEL; OUT=$A/installer/out; W=$A/installer/work/$LABEL
mkdir -p "$IN" "$OUT"

# 1. snapshot
for f in boot.img init_boot.img vendor_boot.img vbmeta.img super.img android-info.txt; do
  cp --reflink=auto --preserve=timestamps "$P/$f" "$IN/"
done
cp "$P"/build_fingerprint*.txt "$IN/" 2>/dev/null || true
{
  echo "snapshot: $(date -u +%FT%TZ)"; echo "product_out: $P"
  sed -n 's/^ro.build.fingerprint=/fingerprint: /p' "$P/system/build.prop"
  sed -n 's/^ro.vendor.build.fingerprint=/vendor fingerprint: /p' "$P/vendor/build.prop"
  [ -f "$A/aosp/src/vendor/anybook/g14-kernel/PROVENANCE.txt" ] && sed 's/^/kernel: /' "$A/aosp/src/vendor/anybook/g14-kernel/PROVENANCE.txt"
  (cd "$IN" && sha256sum boot.img init_boot.img vendor_boot.img vbmeta.img super.img)
} > "$IN/provenance.txt"

# 2. disk image
"$R/scripts/installer/inst-docker.sh" python3 "$R/scripts/installer/mkproduct.py" \
  --inputs "$IN" --work "$W" --out "$OUT/$LABEL.img" --label "$LABEL" --size-gib "$SIZE"
cp "$IN/provenance.txt" "$OUT/$LABEL.img.provenance.txt"
rm -rf "$W"

# 3. checksums
cd "$OUT"
sha256sum "$LABEL.img" > "$LABEL.img.sha256"
if [ $XZ = 1 ]; then
  xz -T0 -6 -k -f "$LABEL.img" && sha256sum "$LABEL.img.xz" > "$LABEL.img.xz.sha256"
fi
echo "image: $OUT/$LABEL.img"
echo "size: $(stat -c %s "$LABEL.img") bytes ($(du -h --apparent-size "$LABEL.img" | cut -f1) apparent, $(du -h "$LABEL.img" | cut -f1) allocated)"
echo "sha256: $(cut -d' ' -f1 "$LABEL.img.sha256")"
[ $XZ = 1 ] && echo "xz: $(stat -c %s "$LABEL.img.xz") bytes, sha256 $(cut -d' ' -f1 "$LABEL.img.xz.sha256")"
exit 0
