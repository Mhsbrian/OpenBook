#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The clean default desktop (ANAL-206) on the G14 product, in QEMU/KVM + OVMF: boots a fresh 16 GiB copy of a live
# image (scripts/installer-image.sh) through its VM-only serial-console entry, the way live-qemu.sh's "first" case
# does, and runs expect-desktop-defaults.json: QuickSearchBox, partner layout and taskbar pins, sound settings,
# the LatinIME and screenshot-sound defaults, the overlays, the crash buffer; screenshots of the desktop (installer
# closed) and All Apps. The VM has no camera, so Camera2 should hide itself and leave five pins.
#
# usage: desktop-defaults-qemu.sh IMG RUN
# Results: <data dir>/logs/installer/<RUN>/desktop/ (serial.log, result.json, shot-*.png, defaults.txt, logcat.txt.gz)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$R/scripts/installer; D=$S/inst-docker.sh
IMG=$(realpath "${1:?usage: desktop-defaults-qemu.sh IMG RUN}"); RUN=${2:?run name}
[ -f "$IMG.json" ] && [ -d "${IMG%.img}.vm" ] || { echo "$IMG.json and ${IMG%.img}.vm needed: scripts/installer-image.sh" >&2; exit 1; }
Q=$A/installer/qemu/$RUN; L=$A/logs/installer/$RUN/desktop
rm -rf "$L"; mkdir -p "$Q" "$L"
ESP_OFF=$(python3 -c 'import json,sys; print(next(p["start"] for p in json.load(open(sys.argv[1]))["partitions"] if p["name"]=="EFI") * 512)' "$IMG.json")

# A copy of the stick that boots "OpenBook (VM, serial console)", as live-qemu.sh's stick() does.
d=$Q/desktop16.img
rm -f "$d" "$Q/desktop16.vars"
cp --reflink=auto "$IMG" "$d"; truncate -s 16G "$d"
printf 'timeout 0\ndefault openbook-vm.conf\nconsole-mode keep\neditor no\n' > "$Q/desktop16.loader.conf"
"$D" bash -c "mcopy -o -s -m -i '$d@@$ESP_OFF' '${IMG%.img}.vm/loader' '${IMG%.img}.vm/openbook' ::/ &&
              mcopy -o -i '$d@@$ESP_OFF' '$Q/desktop16.loader.conf' ::/loader/loader.conf"

set +e
"$D" python3 "$S/qemu-run.py" --usb "$d" --out "$L" --expect "$R/scripts/ui/expect-desktop-defaults.json" \
  --gpu virtio-vga,xres=1920,yres=1200 --usb-input --tpm --mem 6144 --smp 6 --timeout 1500 --linger 60 \
  --vars "$Q/desktop16.vars" > "$L/driver.log" 2>&1
rc=$?
set -e
echo "qemu-run exit $rc: $(tail -n 1 "$L/driver.log" | cut -c1-160)" >&2
tr -d '\r' < "$L/serial.log" | sed -n '/^===DEFAULTS-BEGIN===/,/^===DEFAULTS-END===/p' > "$L/defaults.txt"
tr -d '\r' < "$L/serial.log" | sed -n '/^===LOGCAT-BEGIN===/,/^===LOGCAT-END===/{/===/d;p}' | base64 -d > "$L/logcat.txt.gz" 2>/dev/null || true
gzip -f "$L/serial.log"
rm -f "$d"
cat "$L/defaults.txt"
[ "$rc" = 0 ]
