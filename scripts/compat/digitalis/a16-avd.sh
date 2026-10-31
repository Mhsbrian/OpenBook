#!/usr/bin/env bash
# Control for ANAL-181: Digitalis as its authors ship it. Unpacks the sdk_phone64_x86_64_digitalis image
# (AOSP 16, built by `build.sh full`, which also runs `m emu_img_zip`) into ~/anybook/digitalis/sysimg and
# creates AVD "anybook-digitalis-a16" with the same hardware settings as the compat AVDs. Then:
#   COMPAT_AVD=anybook-digitalis-a16 COMPAT_GLTRANSPORT= scripts/compat/run-matrix.sh -o <dir> --keep-emulator
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}
OUT=$A/digitalis/aosp16/out/target/product/emu64xa
Z=$(ls -t "$OUT"/sdk-repo-linux-system-images*.zip 2>/dev/null | head -1)
[ -n "$Z" ] || { echo "no emu_img_zip output in $OUT: run build.sh full" >&2; exit 2; }
S=$A/digitalis/sysimg; rm -rf "$S"; mkdir -p "$S"
unzip -q "$Z" -d "$S"
SYS=$(dirname "$(find "$S" -name system.img | head -1)")
# The emu_img_zip lacks advancedFeatures.ini; without it the emulator picks other guest features.
[ -f "$SYS/advancedFeatures.ini" ] || cp "$OUT/advancedFeatures.ini" "$SYS/"
echo "image: $Z -> $SYS"; ls "$SYS"
D=$A/avd/anybook-digitalis-a16.avd; mkdir -p "$D"
# Same hardware as anybook-desktop (m0-emulator.sh), but the system image is the Digitalis AOSP 16 build.
sed -e 's/^AvdId=.*/AvdId=anybook-digitalis-a16/' -e "s|^image.sysdir.1=.*|image.sysdir.1=$SYS/|" \
    -e 's/^tag.id=.*/tag.id=default/' -e 's/^tag.ids=.*/tag.ids=default/' -e '/^hw.gltransport=/d' \
    "$A/avd/anybook-desktop.avd/config.ini" > "$D/config.ini"
printf 'avd.ini.encoding=UTF-8\npath=%s\ntarget=android-36\n' "$D" > "$A/avd/anybook-digitalis-a16.ini"
cat "$D/config.ini"
