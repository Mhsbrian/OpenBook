#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Release step (ANAL-229 phase 3): give a release its OpenBook layer, the data the laptop needs to adapt
# Google's next build by itself. Runs the same openbook-adapt the laptop runs:
#   1. layer       OpenBook's delta of the release's system against the Google build it was made from;
#   2. adapt       Google's build plus that layer, rebuilt with the next round's layer written into system
#                  (--embed-layer): the release's final system and vbmeta. By construction the laptop,
#                  adapting the same Google build with the layer it finds in this system, gets these bytes.
# Writes OUT/rel (the ten release images: the input ones with system and vbmeta replaced), OUT/layer,
# OUT/adapt.json and OUT/SHA256SUMS. Regular files only; no device. Google's images and the layer stay
# private (the layer holds Google's file rows).
#
# usage: embed-adapter-layer.sh REL_DIR GOOGLE_STOCK GOOGLE_BUILD OUT
#   REL_DIR       the release's ten images, built with openbook-adapt and the AVB test key in its system
#   GOOGLE_STOCK  stage-stock-source.py output for the Google build the release is made from
# env: ADAPT (openbook-adapt host build), AOSP_HOST (out/host/linux-x86: fsck.erofs, mkfs.erofs, secilc),
#      AVBKEY (default the AOSP test key), APP_CERT (OpenBook Update's certificate)
set -euo pipefail
[ $# = 4 ] || { sed -n '3,20p' "$0"; exit 2; }
REL=$(realpath "$1") STOCK=$(realpath "$2") BUILD=$3 OUT=$4
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../.." && pwd)
ADAPT=${ADAPT:?set ADAPT to an openbook-adapt host build}
AOSP_HOST=${AOSP_HOST:-$HOME/anybook/aosp/src/out/host/linux-x86}
AVBKEY=${AVBKEY:-$HOME/anybook/aosp/src/external/avb/test/data/testkey_rsa4096.pem}
APP_CERT=${APP_CERT:-$REPO/device/anybook/common/updater/openbook-update.x509.pem}
export LD_LIBRARY_PATH=$AOSP_HOST/lib64
mkdir -m 700 "$OUT"; OUT=$(realpath "$OUT")
for n in system system_ext product vendor vendor_dlkm system_dlkm boot init_boot vendor_boot vbmeta; do
  [ -f "$REL/$n.img" ] || { echo "missing $REL/$n.img" >&2; exit 1; }
done
"$ADAPT" layer --old-system "$STOCK/system.img" --old-stock "$STOCK" --old-build "$BUILD" --release-dir "$REL" \
  --app-cert "$APP_CERT" --fsck "$AOSP_HOST/bin/fsck.erofs" --work "$OUT/layer-work" --out "$OUT/layer"
rm -rf "$OUT/layer-work"
"$ADAPT" reconstruct --stock "$STOCK" --layer "$OUT/layer" --out "$OUT/google"
mkdir -m 700 "$OUT/tree"
"$AOSP_HOST/bin/fsck.erofs" --extract="$OUT/tree" "$REL/system.img"
"$ADAPT" adapt --layer "$OUT/layer" --new "$OUT/google" --ours-root "$OUT/tree" --key "$AVBKEY" \
  --mkfs "$AOSP_HOST/bin/mkfs.erofs" --fsck "$AOSP_HOST/bin/fsck.erofs" --secilc "$AOSP_HOST/bin/secilc" \
  --work "$OUT/work" --out "$OUT/adapted"
mkdir -m 700 "$OUT/rel"
for n in system_ext product vendor vendor_dlkm system_dlkm boot init_boot vendor_boot; do
  cp --reflink=auto "$REL/$n.img" "$OUT/rel/$n.img"
done
cp --reflink=auto "$OUT/adapted/system.img" "$OUT/adapted/vbmeta.img" "$OUT/rel/"
cp "$OUT/adapted/adapt.json" "$OUT/adapt.json"
# Google's system_ext and product pass through unchanged.
for n in system_ext product; do cmp -s "$OUT/adapted/$n.img" "$REL/$n.img" || { echo "$n changed" >&2; exit 1; }; done
"$ADAPT" verify-vbmeta --image "$OUT/rel/vbmeta.img" --images "$OUT/rel" > "$OUT/verify-vbmeta.txt"
rm -rf "$OUT/tree" "$OUT/work" "$OUT/google" "$OUT/adapted"
(cd "$OUT/rel" && sha256sum *.img > ../SHA256SUMS)
cat "$OUT/SHA256SUMS"
