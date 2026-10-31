#!/usr/bin/env bash
# Collect the Digitalis bridge an OpenBook product built (ANAL-200) into an overlay bundle that install.sh puts on the
# AOSP Desktop emulator image: the files of BERBERIS_DISTRIBUTION_ARTIFACTS_ARM64 at their /system paths, SHA256SUMS,
# MANIFEST.txt. That runs the Android 17 build of the bridge in the same VM and image as libndk_translation, for a
# like-for-like comparison (the product itself is measured in Cuttlefish).
#   bundle.sh [PRODUCT_OUT] [OUT]     defaults: the Cuttlefish product in the AOSP tree, ~/anybook/digitalis/bundle-a17
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; T=$A/aosp/src
P=${1:-$T/out/target/product/anybook_vsoc_x86_64}; OUTB=${2:-$A/digitalis/bundle-a17}
CFG=$T/frameworks/libs/binary_translation/berberis_config.mk
[ -f "$CFG" ] || { echo "no $CFG: the AOSP tree does not have the Digitalis import (scripts/aosp-patches.sh)" >&2; exit 2; }
rm -rf "$OUTB.tmp"; mkdir -p "$OUTB.tmp"; n=0; miss=0
while read -r rel; do
  if [ -f "$P/$rel" ]; then mkdir -p "$OUTB.tmp/$(dirname "$rel")"; cp -a "$P/$rel" "$OUTB.tmp/$rel"; n=$((n + 1))
  else echo "MISSING $P/$rel"; miss=$((miss + 1)); fi
done < <(sed -n '/^BERBERIS_DISTRIBUTION_ARTIFACTS_ARM64 :=/,/^# endregion/p' "$CFG" | grep -oE 'system/[^ \\]+')
( cd "$OUTB.tmp" && find system -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )
{
  echo "Digitalis overlay bundle collected by OpenBook scripts/compat/digitalis/bundle.sh on $(date -u +%FT%TZ)"
  echo "product: $(grep -m1 '^ro.system.build.fingerprint=' "$P/system/build.prop" | cut -d= -f2)"
  echo "frameworks/libs/binary_translation $(git -C "$T/frameworks/libs/binary_translation" rev-parse HEAD)"
  echo "frameworks/libs/native_bridge_support $(git -C "$T/frameworks/libs/native_bridge_support" rev-parse HEAD)"
  echo "artifacts: $n present, $miss missing"
} > "$OUTB.tmp/MANIFEST.txt"
rm -rf "$OUTB"; mv "$OUTB.tmp" "$OUTB"
cat "$OUTB/MANIFEST.txt"
[ "$miss" = 0 ]
