#!/usr/bin/env bash
# Build the Digitalis native bridge from source (ANAL-181) and collect it as an overlay bundle. Runs inside the
# container:  scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/build.sh [modules|full|tests]
#   modules (default)  only the native-bridge packages of enable_arm64_to_x86_64.mk: the translator, 22 proxy
#                      libraries, runners, configs and the arm64 guest libraries (NATIVE_BRIDGE_PRODUCT_PACKAGES)
#   full               the whole sdk_phone64_x86_64_digitalis emulator image (`m`, then `m emu_img_zip`
#                      for an SDK-style system-image zip the stock emulator can boot)
#   tests              berberis_arm64_host_tests (host build) and run it
# Output: ~/anybook/digitalis/bundle/ (BERBERIS_DISTRIBUTION_ARTIFACTS_ARM64 at their /system paths, SHA256SUMS,
# MANIFEST.txt). Logs: ~/anybook/logs/digitalis/build-<mode>-<time>.log. Re-run to resume (ninja is incremental).
set -euo pipefail
MODE=${1:-modules}
A=${ANYBOOK_HOME:-$HOME/anybook}; T=$A/digitalis/aosp16; L=$A/logs/digitalis; OUTB=$A/digitalis/bundle
J=${DIGITALIS_JOBS:-16}
mkdir -p "$L"; cd "$T"
exec > >(tee -a "$L/build-$MODE-$(date -u +%Y%m%dT%H%M%SZ).log") 2>&1
stamp(){ echo "=== $(date -u +%FT%TZ) $*"; }
export TARGET_PRODUCT=sdk_phone64_x86_64_digitalis TARGET_RELEASE=trunk_staging TARGET_BUILD_VARIANT=userdebug
export BUILD_USERNAME=anybook BUILD_HOSTNAME=anybook
ccache -M 60G >/dev/null; ccache --set-config=compiler_check=content
set +u; source build/envsetup.sh >/dev/null; set -u
stamp "build $MODE: $TARGET_PRODUCT-$TARGET_RELEASE-$TARGET_BUILD_VARIANT -j$J"
for p in frameworks/libs/binary_translation frameworks/libs/native_bridge_support device/generic/goldfish digitalis bionic; do
  echo "rev $p $(git -C "$p" rev-parse HEAD)"
done
CFG=frameworks/libs/binary_translation/berberis_config.mk
NBS=frameworks/libs/native_bridge_support/native_bridge_support.mk
# Expand the package lists with make itself, so the list is exactly what the product inherits.
packages(){
  command make -s -f - <<EOF  # `command`: envsetup.sh defines a make() function
include $NBS
include $CFG
\$(info \$(sort \$(BERBERIS_PRODUCT_PACKAGES_ARM64_TO_X86_64)))
all: ;
EOF
}
artifacts(){ sed -n '/^BERBERIS_DISTRIBUTION_ARTIFACTS_ARM64 :=/,/^# endregion/p' "$CFG" | grep -oE 'system/[^ \\]+'; }
t0=$(date +%s)
case $MODE in
  modules)
    read -r -a MODS <<< "$(packages)"
    echo "modules (${#MODS[@]}): ${MODS[*]}"
    /usr/bin/time -v m -j"$J" "${MODS[@]}" ;;
  full) /usr/bin/time -v m -j"$J" && m -j"$J" emu_img_zip ;;
  tests)
    /usr/bin/time -v m -j"$J" berberis_arm64_host_tests
    B=$(find out/host/linux-x86 -path '*nativetest64*' -name berberis_arm64_host_tests -type f | head -1)
    echo "running $B"; "$B" --gtest_brief=1 2>&1 | tail -40 ;;
  *) echo "usage: $0 [modules|full|tests]" >&2; exit 2 ;;
esac
stamp "build $MODE done in $(( $(date +%s) - t0 ))s"
[ "$MODE" = tests ] && exit 0
P=out/target/product/emu64xa
rm -rf "$OUTB.tmp"; mkdir -p "$OUTB.tmp"; n=0; miss=0
while read -r rel; do
  if [ -f "$P/$rel" ]; then mkdir -p "$OUTB.tmp/$(dirname "$rel")"; cp -a "$P/$rel" "$OUTB.tmp/$rel"; n=$((n + 1))
  else echo "MISSING $P/$rel"; miss=$((miss + 1)); fi
done < <(artifacts)
( cd "$OUTB.tmp" && find system -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )
{
  echo "Digitalis overlay bundle built by AnyBook scripts/compat/digitalis/build.sh ($MODE) on $(date -u +%FT%TZ)"
  echo "product: $TARGET_PRODUCT-$TARGET_RELEASE-$TARGET_BUILD_VARIANT"
  for p in frameworks/libs/binary_translation frameworks/libs/native_bridge_support device/generic/goldfish digitalis bionic build/soong; do
    echo "$p $(git -C "$p" rev-parse HEAD)"
  done
  echo "manifest $(git -C .repo/manifests rev-parse HEAD)"
  echo "artifacts: $n present, $miss missing"
} > "$OUTB.tmp/MANIFEST.txt"
rm -rf "$OUTB"; mv "$OUTB.tmp" "$OUTB"
cat "$OUTB/MANIFEST.txt"
[ "$miss" = 0 ]
