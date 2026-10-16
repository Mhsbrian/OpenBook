#!/usr/bin/env bash
# Build the OpenBook USB test stick image (ANAL-189): systemd-boot with two entries,
#   "OpenBook hardware check" (default): boots our kernel on the laptop, loads the OpenBook modules and firmware,
#       writes openbook/logs/hwcheck-NNN.txt (+ -dmesg.txt) to the stick's ESP and powers off;
#   "OpenBook preview (virtual machines only)": the Android 17 boot proven in QEMU (serial console, no display).
# Image files only: this script never writes to a disk or USB stick. Flashing is a separate, manual step.
#
# usage: make-hwcheck-stick.sh [INPUT_LABEL] [NAME]
#   INPUT_LABEL  snapshot under <data dir>/installer/inputs (default cf-pc-20261016)
#   NAME         output base name (default openbook-hwcheck-<UTC date>)
# Output: <data dir>/installer/out/NAME.img, NAME.img.xz, NAME.sha256 (HWCHECK_NO_XZ=1: the .img only)
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); S=$R/scripts/installer; D=$S/inst-docker.sh
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer   # data dir: ~/anybook until the repo-wide rename
IN=$I/inputs/${1:-cf-pc-20261016}
NAME=${2:-openbook-hwcheck-$(date -u +%Y%m%d)}
O=$I/out; W=$I/hwcheck/$NAME
mkdir -p "$O" "$W" "$I/build"
"$D" gcc -static -O2 -Wall -Wno-format-truncation -o "$I/build/openbook-probe" "$S/probe-init.c"
rm -rf "$W/android"   # the probe lives in vendor_boot: rebuild it
"$D" python3 "$S/mkproto.py" --inputs "$IN" --work "$W" --loader sdboot --hwcheck --label openbook-hwcheck \
  --size-gib 11 --out "$O/$NAME.img" > "$W/mkproto.log" 2>&1
rm -f "$O/$NAME.img.xz" "$O/$NAME.sha256"
[ -n "${HWCHECK_NO_XZ:-}" ] && exit 0   # quick iteration: image only
xz -T0 -6 -k "$O/$NAME.img"
(cd "$O" && sha256sum "$NAME.img" "$NAME.img.xz" > "$NAME.sha256")
ls -la "$O/$NAME".*
