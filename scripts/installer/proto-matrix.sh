#!/usr/bin/env bash
# ANAL-189 boot-chain prototype matrix: build one GPT "USB stick" image per EFI loader from the same Android images
# and kernel, boot each in QEMU/KVM + OVMF as USB mass storage (some with a decoy "internal" NVMe disk that carries
# the same partition names), and summarise what the loader handed over and how far Android got.
# Image files only. Nothing touches a host disk, USB stick or firmware.
#
# usage: proto-matrix.sh [INPUT_LABEL] [RUN_LABEL]
#   INPUT_LABEL  snapshot under <data dir>/installer/inputs (default cf-pc-20261016; make one with snapshot-inputs.sh)
#   RUN_LABEL    default matrix-<UTC timestamp>; logs in <data dir>/logs/installer/<RUN_LABEL>/<variant>/
# env: MATRIX_ONLY="grub sdboot"   run a subset of variants
#      MATRIX_EVIDENCE=DIR         also copy summaries and trimmed logs there
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer   # data dir: ~/anybook until the repo-wide rename
IN=$I/inputs/${1:-cf-pc-20261016}
RUN=${2:-matrix-$(date -u +%Y%m%dT%H%M%SZ)}
L=$A/logs/installer/$RUN; W=$I/$RUN
mkdir -p "$L" "$W"
D=$R/scripts/installer/inst-docker.sh; S=$R/scripts/installer
[ -d "$IN/product" ] || { echo "no input snapshot $IN (run snapshot-inputs.sh)" >&2; exit 2; }
[ -x "$I/build/openbook-probe" ] || "$D" gcc -static -O2 -Wall -o "$I/build/openbook-probe" "$S/probe-init.c"
GBL=${GBL_EFI:-$I/dl/gbl-16633196/gbl_x86_64_dev.efi}
stamp(){ echo "=== $(date -u +%FT%TZ) $*" | tee -a "$L/matrix.log"; }
want(){ [ -z "${MATRIX_ONLY:-}" ] || [[ " $MATRIX_ONLY " == *" $1 "* ]]; }
mk(){ local name=$1 work=$2; shift 2
  stamp "build $name"
  "$D" python3 "$S/mkproto.py" --inputs "$IN" --work "$work" --out "$W/$name.img" "$@" > "$L/mkproto-$name.log" 2>&1
}
boot(){ local name=$1 img=$2; shift 2
  stamp "boot $name"
  mkdir -p "$L/$name"
  "$D" python3 "$S/qemu-run.py" --usb "$img" --out "$L/$name" "$@" > "$L/$name/run.out" 2>&1 || true
  tail -1 "$L/$name/run.out" | tee -a "$L/matrix.log"
}
fresh(){ cp --reflink=auto "$W/$1.img" "$W/run-$2.img"; echo "$W/run-$2.img"; }

stamp "inputs $IN"; cp "$IN/provenance.txt" "$L/input-provenance.txt"
"$D" python3 "$S/mkproto.py" --decoy "$W/decoy-nvme.img" > /dev/null
EXP=$S/expect-android.json

if want grub; then
  mk grub "$W/w-main" --loader grub
  boot grub "$(fresh grub grub)" --nvme "$W/decoy-nvme.img" --timeout 420 --expect "$EXP" --shot 2
  # Second boot of the same stick: the live session must keep /metadata and /data (no re-format).
  boot grub-2nd-boot "$W/run-grub.img" --nvme "$W/decoy-nvme.img" --timeout 420 --expect "$EXP"
fi
if want grub-bad-digest; then
  mk grub-bad-digest "$W/w-main" --loader grub --bad-digest
  boot grub-bad-digest "$(fresh grub-bad-digest grub-bad-digest)" --timeout 420 --expect "$EXP"
fi
if want grub-slot-b; then
  mk grub-slot-b "$W/w-main" --loader grub --slot b --halt
  boot grub-slot-b "$(fresh grub-slot-b grub-slot-b)" --timeout 60
fi
if want sdboot; then
  mk sdboot "$W/w-main" --loader sdboot
  # Menu hidden (product default): screenshots show what the user sees from power-on to Android's init.
  boot sdboot "$(fresh sdboot sdboot)" --nvme "$W/decoy-nvme.img" --timeout 420 --expect "$EXP" --shot 1.5 3 5 8 12
  # Boot counting: systemd-boot renames loader/entries/openbook-a+3.conf on every try.
  off=$(( $(python3 -c "import json;print([p for p in json.load(open('$W/sdboot.img.json'))['partitions'] if p['name']=='EFI'][0]['start'])") * 512 ))
  "$D" mdir -i "$W/run-sdboot.img@@$off" ::/loader/entries > "$L/sdboot/esp-entries-after.txt" 2>&1 || true
fi
if want sdboot-menu; then
  # The same loader with the menu shown (what a key held at power-on brings up), probe only.
  mk sdboot-menu "$W/w-main" --loader sdboot --menu --halt
  boot sdboot-menu "$(fresh sdboot-menu sdboot-menu)" --timeout 60 --shot 3
fi
if want uki; then
  mk uki "$W/w-main" --loader uki --halt
  boot uki "$(fresh uki uki)" --timeout 60
fi
if want gbl; then
  mk gbl "$W/w-main" --loader gbl --gbl-efi "$GBL"
  boot gbl "$(fresh gbl gbl)" --timeout 120 --expect "$EXP"
  mk gbl-uuid "$W/w-gbluuid" --loader gbl --gbl-efi "$GBL" --vendor-boot-part-uuid
  boot gbl-uuid "$(fresh gbl-uuid gbl-uuid)" --timeout 420 --expect "$EXP"
  boot gbl-uuid-decoy "$(fresh gbl-uuid gbl-uuid-decoy)" --nvme "$W/decoy-nvme.img" --timeout 30 --pause-on-reset --shot 20
fi

stamp "summary"
python3 "$S/proto-summary.py" "$L" > "$L/SUMMARY.md"
cat "$L/SUMMARY.md"
if [ -n "${MATRIX_EVIDENCE:-}" ]; then
  mkdir -p "$MATRIX_EVIDENCE"
  cp "$L/SUMMARY.md" "$L/results.json" "$L/matrix.log" "$L/input-provenance.txt" "$MATRIX_EVIDENCE/"
  for d in "$L"/*/; do
    n=$(basename "$d"); mkdir -p "$MATRIX_EVIDENCE/$n"
    cp "$d"/result.json "$MATRIX_EVIDENCE/$n/" 2>/dev/null || true
    cp "$d"/*.png "$d"/esp-entries-after.txt "$MATRIX_EVIDENCE/$n/" 2>/dev/null || true
    [ -f "$d/serial.log" ] && tr -d '\r' < "$d/serial.log" | sed 's/\x1b\[[0-9;?]*[a-zA-Z]//g' | gzip -9 > "$MATRIX_EVIDENCE/$n/serial.log.gz"
    [ -f "$W/$n.img.json" ] && cp "$W/$n.img.json" "$MATRIX_EVIDENCE/$n/image.json"
  done
fi
