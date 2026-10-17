#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Test the ARM-apps check add-on (ANAL-200) in QEMU/KVM + OVMF on a COPY of a live image, the way the owner's stick
# will look: add-to-image.sh puts the add-on's files and entry on the copy's ESP, derived from the VM bundle's console
# "save logs" entry, as the default entry. One boot: a fresh 16 GiB stick, Android's first boot, then live-init's
# add-on run (unpack, checksum check, run.sh, cleanup), the final capture and power-off. The guest CPU is the host's
# (-cpu host), so this tests the plumbing and gives a VM number, not the laptop's.
# Image files only, never a stick. Logs and the stick's results land in
# <data dir>/installer/bridgecheck/NAME/qemu-RUN/ (run/serial.log, run/result.json, logs/).
#
# usage: bridge-qemu.sh NAME RUN [LIVE_IMAGE]    NAME: a make-bridge-check.sh output name; RUN: a label
set -euo pipefail
R=$(cd "$(dirname "$0")/../../../.." && pwd); S=$R/scripts/installer; D=$S/inst-docker.sh
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer
NAME=${1:?usage: bridge-qemu.sh NAME RUN [LIVE_IMAGE]}; RUN=${2:?run label}
SRC=$(realpath "${3:-$I/out/openbook-live-20261017-anal176s.img}")
ADD=$I/out/$NAME-addon; W=$I/bridgecheck/$NAME/qemu-$RUN
[ -d "$ADD" ] || { echo "no add-on $ADD: run make-bridge-check.sh $NAME first" >&2; exit 2; }
[ -d "${SRC%.img}.vm" ] || { echo "${SRC%.img}.vm (the image's VM bundle) is needed" >&2; exit 2; }
rm -rf "$W"; mkdir -p "$W"
cp --reflink=auto "$SRC" "$W/stick.img"; truncate -s 16G "$W/stick.img"
E="$W/stick.img@@1M"
"$D" mcopy -o -s -m -i "$E" "${SRC%.img}.vm/loader" "${SRC%.img}.vm/openbook" ::/
"$D" "$R/scripts/compat/digitalis/stick/add-to-image.sh" "$W/stick.img" "$ADD" --template openbook-vm-logs.conf --default
cat > "$W/expect.json" <<'EOF'
[
 {"wait": "openbook-live: live boot: boot_part_uuid=", "timeout": 120},
 {"wait": "openbook-live: logs: saving to openbook/logs/live-\\d+ on the stick.s ESP; add-on bridge", "timeout": 60},
 {"wait": "openbook-live: logs: sys.boot_completed=1", "timeout": 900},
 {"wait": "openbook-live: addon bridge: running run.sh", "timeout": 600},
 {"wait": "openbook-live: addon bridge: run.sh exit", "timeout": 1800},
 {"wait": "openbook-live: logs: done: ", "timeout": 900}
]
EOF
set +e
"$D" python3 "$S/qemu-run.py" --usb "$W/stick.img" --out "$W/run" --timeout 4200 --expect "$W/expect.json" \
  --gpu virtio-vga,xres=1920,yres=1200 --usb-input --tpm --mem 8192 --smp 8 --linger 180 --shot 300 600
echo "qemu-run exit $?"
set -e
"$D" bash -c "rm -rf '$W/logs' && mcopy -s -o -i '$E' ::/openbook/logs '$W/' && ls -la '$W'/logs/live-*"
grep -aE 'openbook-live: (addon|logs: (done|saving|sys.boot))|openbook-bridge: ' "$W/run/serial.log" | sed 's/^.*\] //' | tail -n 40
