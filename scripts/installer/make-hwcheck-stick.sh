#!/usr/bin/env bash
# Build the OpenBook USB test stick (ANAL-189): systemd-boot with
#   "OpenBook hardware check" (default): boots our kernel on the laptop, loads the OpenBook modules and firmware,
#       writes openbook/logs/hwcheck-NNN.txt, .json and -dmesg.txt to the stick's ESP and powers off;
#   "OpenBook hardware check + sleep test": the same plus one RTC-woken s2idle cycle;
#   "OpenBook sleep test, NVIDIA GPU powered down": the dGPU is detached for this boot first (docs/nvidia.md §1);
#   "OpenBook preview (virtual machines only)": the Android 17 boot proven in QEMU (serial console, no display).
# Image files only: this script never writes to a disk or USB stick. Flashing (or update-hwcheck-stick.sh) is a
# separate, manual step that needs the owner's confirmation of the exact /dev/disk/by-id device.
#
# usage: make-hwcheck-stick.sh [INPUT_LABEL] [NAME]
#   INPUT_LABEL  snapshot under <data dir>/installer/inputs (default cf-pc-20261016)
#   NAME         output base name (default openbook-hwcheck-<UTC date>)
# Output in <data dir>/installer/out/: NAME.img, NAME.img.xz, NAME.sha256 (HWCHECK_NO_XZ=1: the .img only), and
#   NAME-esp-update/: the files that differ on a stick flashed from an earlier build with the same layout
#   (openbook/check/, the check entries, README), for update-hwcheck-stick.sh.
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); S=$R/scripts/installer; D=$S/inst-docker.sh
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer   # data dir: ~/anybook until the repo-wide rename
IN=$I/inputs/${1:-cf-pc-20261016}
NAME=${2:-openbook-hwcheck-$(date -u +%Y%m%d)}
FW=${HWCHECK_FIRMWARE:-$A/kernel/firmware/anybook-amd}   # ANAL-171 linux-firmware subset
O=$I/out; W=$I/hwcheck/$NAME
mkdir -p "$O" "$W" "$I/build"
"$D" gcc -static -O2 -Wall -Wno-format-truncation -o "$I/build/openbook-probe" "$S/probe-init.c"
# Firmware for the check: the subset plus wireless-regdb (cfg80211 asks for regulatory.db), with its licence.
"$D" bash -c "rm -rf '$W/firmware' && cp -r '$FW' '$W/firmware' && cp /usr/lib/firmware/regulatory.db \
  /usr/lib/firmware/regulatory.db.p7s '$W/firmware/' && mkdir -p '$W/firmware/LICENSES' && \
  cp /usr/share/licenses/wireless-regdb/LICENSE '$W/firmware/LICENSES/LICENSE.wireless-regdb'"
rm -rf "$W/android"   # the probe also lives in vendor_boot: rebuild it
"$D" python3 "$S/mkproto.py" --inputs "$IN" --work "$W" --loader sdboot --hwcheck --label openbook-hwcheck \
  --check-firmware "$W/firmware" --size-gib 11 --out "$O/$NAME.img" > "$W/mkproto.log" 2>&1
# Update bundle: only files under openbook/check/, the two check entries and the README.
U=$O/$NAME-esp-update; rm -rf "$U"; mkdir -p "$U/openbook/check" "$U/loader/entries"
cp "$W/esp-sdboot/openbook/check/hwcheck.img" "$U/openbook/check/"
cp "$W/esp-sdboot/loader/entries/"openbook-1*.conf "$U/loader/entries/"
cp "$W/esp-sdboot/openbook/README.txt" "$U/openbook/"
python3 -c "import json,sys;print([p['uuid'] for p in json.load(open(sys.argv[1]))['partitions'] if p['name']=='EFI'][0])" \
  "$O/$NAME.img.json" > "$U/ESP_PARTUUID"
(cd "$U" && find openbook loader -type f | sort | xargs sha256sum > MANIFEST.sha256)
rm -f "$O/$NAME.img.xz" "$O/$NAME.sha256"
[ -n "${HWCHECK_NO_XZ:-}" ] && exit 0   # quick iteration: image only
xz -T0 -6 -k "$O/$NAME.img"
(cd "$O" && sha256sum "$NAME.img" "$NAME.img.xz" > "$NAME.sha256")
ls -la "$O/$NAME".* "$U"
