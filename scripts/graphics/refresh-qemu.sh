#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Refresh-rate check of a live image in QEMU/OVMF (ANAL-212; docs/graphics-amd.md, "Refresh rate"). One boot of a
# reflink copy of the image as a 16 GiB stick, on the image's serial-console entry, with virtio-vga at 1920x1200
# (QEMU's display offers one mode, 75 Hz). After boot (expect-refresh.json): the framework RRO and the two refresh
# configs it sets, DisplayModeDirector's votes, SurfaceFlinger's scheduler dump; then Settings scrolled with
# `input swipe` while SurfaceFlinger's render rate is sampled, and the scheduler dump again. With AOSP's
# config_defaultRefreshRate of 60 the primary render range stops at 60, so on a 75 Hz display SurfaceFlinger draws
# at 37.5; without that cap it may draw at 75. Image files only, as live-qemu.sh.
# Results: <data dir>/logs/installer/<RUN>/refresh/ (serial.log, result.json, shot-*.png, refresh.json, refresh.md).
#
# usage: refresh-qemu.sh IMG RUN
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$R/scripts/installer; D=$S/inst-docker.sh
IMG=$(realpath "${1:?usage: refresh-qemu.sh IMG RUN}"); RUN=${2:?run name}
[ -f "$IMG" ] && [ -f "$IMG.json" ] && [ -d "${IMG%.img}.vm" ] || { echo "$IMG, $IMG.json and ${IMG%.img}.vm needed: scripts/installer-image.sh" >&2; exit 1; }
Q=$A/installer/qemu/$RUN; L=$A/logs/installer/$RUN/refresh
mkdir -p "$Q"; rm -rf "$L"; mkdir -p "$L"
ESP_OFF=$(python3 -c 'import json,sys; print(next(p["start"] for p in json.load(open(sys.argv[1]))["partitions"] if p["name"]=="EFI") * 512)' "$IMG.json")

# The stick, as live-qemu.sh's `stick refresh 16 vm`: the VM bundle's loader files, and the console entry as default.
d=$Q/refresh.img
rm -f "$d" "$Q/refresh.vars"
cp --reflink=auto "$IMG" "$d"
truncate -s 16G "$d"
printf 'timeout 0\ndefault openbook-vm.conf\nconsole-mode keep\neditor no\n' > "$Q/refresh.loader.conf"
"$D" bash -c "mcopy -o -s -m -i '$d@@$ESP_OFF' '${IMG%.img}.vm/loader' '${IMG%.img}.vm/openbook' ::/ &&
              mcopy -o -i '$d@@$ESP_OFF' '$Q/refresh.loader.conf' ::/loader/loader.conf"

set +e
"$D" python3 "$S/qemu-run.py" --usb "$d" --out "$L" --expect "$R/scripts/graphics/expect-refresh.json" \
  --gpu virtio-vga,xres=1920,yres=1200 --usb-input --tpm --mem 6144 --smp 6 --timeout 1500 --linger 30 \
  --vars "$Q/refresh.vars" > "$L/driver.log" 2>&1
rc=$?
set -e
gzip -kf "$L/serial.log" 2>/dev/null || true
echo "qemu-run exit $rc ($(tail -n 1 "$L/driver.log" | cut -c1-160))" >&2
python3 -I "$R/scripts/graphics/refresh-report.py" "$L"
