#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Boot the G14 product's disk image in QEMU/KVM + OVMF as a generic PC (ANAL-199): the image on a USB stick
# (qemu-xhci + usb-storage), virtio-vga at 1920x1200, a USB keyboard and tablet, no network, no AMD GPU. The
# product falls back to virtio-gpu with SwiftShader (init.openbook.rc). Runs the expect script on the serial
# console, takes screenshots, and splits the captured sections into files.
#
# The run boots a reflink copy of the image, never the image itself, with one change: in the copy's ESP,
# loader.conf defaults to "OpenBook (serial console)" (the image's own default entry has no console).
#
# usage: g14-qemu.sh IMG RUN [EXPECT]            fresh copy of IMG, then boot (default expect-g14.json)
#        g14-qemu.sh --again RUN [EXPECT]        boot RUN's disk again, data kept (default expect-g14-reboot.json)
# Logs: <data dir>/logs/installer/<RUN>/ (serial.log, result.json, shot-*.png, sections/)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/.." && pwd)
I=$R/scripts/installer
if [ "${1:-}" = --again ]; then
  RUN=$2; EXPECT=${3:-$I/expect-g14-reboot.json}; IMG=
else
  IMG=$1; RUN=$2; EXPECT=${3:-$I/expect-g14.json}
fi
D=$A/installer/qemu/$RUN
L=$A/logs/installer/$RUN
if [ -n "$IMG" ]; then
  [ -f "$IMG" ] && [ -f "$IMG.json" ] || { echo "$IMG (and $IMG.json) needed: scripts/g14-image.sh" >&2; exit 1; }
  rm -rf "$D"; mkdir -p "$D"
  cp --reflink=auto "$IMG" "$D/disk.img"
  cp "$IMG.json" "$D/disk.img.json"
  off=$(python3 -c 'import json,sys; p=next(x for x in json.load(open(sys.argv[1]))["partitions"] if x["name"]=="EFI"); print(p["start"]*512)' "$IMG.json")
  printf 'timeout 0\ndefault openbook-a-console.conf\nconsole-mode keep\neditor no\n' > "$D/loader.conf"
  "$I/inst-docker.sh" mcopy -o -i "$D/disk.img@@$off" "$D/loader.conf" ::/loader/loader.conf
  echo "test copy: $D/disk.img (ESP loader.conf -> console entry)" >&2
fi
[ -f "$D/disk.img" ] || { echo "no disk for run $RUN" >&2; exit 1; }
n=1; while [ -d "$L/boot$n" ]; do n=$((n + 1)); done
O=$L/boot$n
mkdir -p "$O"
set +e
"$I/inst-docker.sh" python3 "$I/qemu-run.py" --usb "$D/disk.img" --out "$O" --expect "$EXPECT" \
  --gpu virtio-vga,xres=1920,yres=1200 --usb-input --tpm --mem 8192 --smp 8 --timeout 2400 --linger 60 --vars "$D/OVMF_VARS.fd"
rc=$?
set -e
python3 "$I/serial-extract.py" "$O/serial.log" "$O/sections" || true
gzip -kf "$O/serial.log"
echo "run: $O (qemu-run exit $rc)"
exit $rc
