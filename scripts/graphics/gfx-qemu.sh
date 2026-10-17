#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Test the graphics check add-on (ANAL-177) in QEMU/OVMF on a COPY of a live image, the way the owner's stick will
# look: the owner's applier puts the add-on's files and entry on the copy's ESP (its --image mode), derived from the
# VM bundle's console "save logs" entry, with 40 cases per list (openbook.gfx_quick=1), as the default entry. One boot:
# a fresh 16 GiB stick, Android's first boot, then live-init's add-on run (unpack, checksum check, run.sh, cleanup),
# the final capture and power-off. No AMD GPU in QEMU: Vulkan is SwiftShader and GLES is ANGLE on it, so vk14 and
# gles-mesa skip themselves; this tests the plumbing (and the two apps), not a driver.
# The copy is never a stick: image files only. Logs and the stick's results land in
# <data dir>/installer/gfxcheck/NAME/qemu-RUN/ (run/serial.log, run/result.json, logs/).
#
# usage: gfx-qemu.sh NAME RUN [LIVE_IMAGE]    NAME: a make-gfx-check.sh output name; RUN: a label (e.g. quick1)
#   GFX_QEMU_FULL=1: the full case lists instead of 40 per list (hours on SwiftShader)
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); S=$R/scripts/installer; D=$S/inst-docker.sh
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer
NAME=${1:?usage: gfx-qemu.sh NAME RUN [LIVE_IMAGE]}; RUN=${2:?run label}
SRC=$(realpath "${3:-$I/out/openbook-live-20261017-combined.img}")
ADD=$I/out/$NAME-addon; W=$I/gfxcheck/$NAME/qemu-$RUN
[ -d "$ADD" ] || { echo "no add-on $ADD: run make-gfx-check.sh $NAME first" >&2; exit 2; }
[ -d "${SRC%.img}.vm" ] || { echo "${SRC%.img}.vm (the image's VM bundle) is needed" >&2; exit 2; }
rm -rf "$W"; mkdir -p "$W"
cp --reflink=auto "$SRC" "$W/stick.img"; truncate -s 16G "$W/stick.img"
E="$W/stick.img@@1M"   # the ESP starts at 1 MiB in every OpenBook image
Q=--quick; [ "${GFX_QEMU_FULL:-0}" = 1 ] && Q=
"$D" bash -c "mcopy -o -s -m -i '$E' '${SRC%.img}.vm/loader' '${SRC%.img}.vm/openbook' ::/ && minfo -i '$E' :: | grep -E 'free clusters|sectors per cluster'"
"$D" "$R/scripts/graphics/add-to-live-stick.sh" --image "$W/stick.img" "$ADD" --template openbook-vm-logs.conf $Q --default
"$D" mdir -i "$E" -b ::/loader/entries ::/openbook/gfx
cat > "$W/expect.json" <<'EOF'
[
 {"wait": "openbook-live: live boot: boot_part_uuid=", "timeout": 120},
 {"wait": "openbook-live: logs: saving to openbook/logs/live-\\d+ on the stick.s ESP; add-on gfx", "timeout": 60},
 {"wait": "openbook-live: logs: sys.boot_completed=1", "timeout": 900},
 {"wait": "openbook-live: addon gfx: running run.sh", "timeout": 600},
 {"wait": "openbook-live: addon gfx: run.sh exit", "timeout": 5400},
 {"wait": "openbook-live: logs: done: ", "timeout": 900}
]
EOF
set +e
"$D" python3 "$S/qemu-run.py" --usb "$W/stick.img" --out "$W/run" --timeout 7800 --expect "$W/expect.json" \
  --gpu virtio-vga,xres=1920,yres=1200 --usb-input --tpm --mem 8192 --smp 8 --linger 180 --shot 600 1200 1800
echo "qemu-run exit $?"
set -e
"$D" bash -c "rm -rf '$W/logs' && mcopy -s -o -i '$E' ::/openbook/logs '$W/' && ls -la '$W'/logs/live-*"
grep -aE 'openbook-live: (addon|logs: (done|saving|sys.boot))|openbook-gfx: ' "$W/run/serial.log" | sed 's/^.*\] //' | tail -n 40
