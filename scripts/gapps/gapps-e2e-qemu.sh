#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The bring-your-own GApps step end to end in QEMU/KVM + OVMF (ANAL-211), on the installer's harness
# (scripts/installer/e2e-qemu.sh's prep: the 16 GiB stick copy with a serial-console entry, the Windows-like 128 GiB
# disk the whole-disk runs erase; e2e-qemu.py's disk inspection; qemu-run.py). Image files only, synthetic packages
# only (scripts/gapps/make-synthetic.py). scripts/gapps/gapps-e2e-qemu.py describes every case.
#
# usage: gapps-e2e-qemu.sh IMG RUN CASE...
#   CASE: prep g-cut-1 ... g-cut-5 g-ui g-cli g-installed g-verity check | all (prep, the cuts, g-ui, g-installed,
#         g-verity, check)
# Results: <data dir>/logs/installer/RUN/<case>/ and RUN/inspect/; disks in <data dir>/installer/qemu/RUN/.
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$R/scripts/installer; G=$R/scripts/gapps; D=$S/inst-docker.sh
P="python3 $G/gapps-e2e-qemu.py"; E="python3 $S/e2e-qemu.py"
IMG=$(realpath "${1:?usage: gapps-e2e-qemu.sh IMG RUN CASE...}"); RUN=${2:?run name}; shift 2
CASES=${*:?cases}
[ "$CASES" = all ] && CASES="prep g-cut-1 g-cut-2 g-cut-3 g-cut-4 g-cut-5 g-ui g-installed g-verity check"
Q=$A/installer/qemu/$RUN; L=$A/logs/installer/$RUN; I=$L/inspect; PK=$A/installer/gapps/packages
mkdir -p "$Q" "$L" "$I"
ESP_OFF=$(python3 -c 'import json,sys; print(next(p["start"] for p in json.load(open(sys.argv[1]))["partitions"] if p["name"]=="EFI") * 512)' "$IMG.json")
GPU=(--gpu virtio-vga,xres=2880,yres=1800 --usb-input --tpm)
log() { echo "[$(date -u +%H:%M:%S)] $*" >&2; }
run_case() {  # CASE TIMEOUT [qemu-run args...]
  local c=$1 t=$2; shift 2
  rm -rf "${L:?}/$c"; mkdir -p "$L/$c"
  "$D" $P expect "$c" "$L/$c/expect.json"
  set +e
  "$D" python3 "$S/qemu-run.py" --out "$L/$c" --expect "$L/$c/expect.json" "${GPU[@]}" --mem 8192 --smp 8 \
    --timeout "$t" --linger 5 "$@" > "$L/$c/driver.log" 2>&1
  local rc=$?
  set -e
  gzip -kf "$L/$c/serial.log" 2>/dev/null || true
  log "case $c: qemu-run exit $rc ($(tail -n 1 "$L/$c/driver.log" | cut -c1-160))"
}
fetch_shots() {  # CASE DISK OFFSET
  "$D" bash -c "mkdir -p '$L/$1/screens' && mcopy -n -o -s -i '$2@@$3' ::/openbook/shots/ '$L/$1/screens/' &&
                mdeltree -i '$2@@$3' ::/openbook/shots" >/dev/null 2>&1 || log "no screenshots for $1"
}
part_off() {  # DISK NAME
  "$D" python3 -c "
import sys, importlib.util as u
s = u.spec_from_file_location('e', '$S/e2e-qemu.py'); e = u.module_from_spec(s); s.loader.exec_module(e)
t, _ = e.table_of(e.gpt_read(sys.argv[1])); print(next(p['first'] * 512 for p in t['parts'] if p['name'] == sys.argv[2]))" "$1" "$2"
}
console_copy() {  # SRC DST: the installed disk, default entry = its OpenBook entry plus the serial console (e2e-qemu.sh)
  rm -f "$2"; cp --reflink=auto "$1" "$2"
  local off; off=$(part_off "$2" EFI)
  "$D" bash -c "set -e; cd '$Q'
    mcopy -n -o -i '$2@@$off' ::/loader/entries/openbook-a.conf a.conf
    sed -e 's/^title .*/title OpenBook (serial console test)/' -e 's/^sort-key .*/sort-key 0-console/' \
        -e 's/^options \(.*\)/options \1 console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on/' a.conf > openbook-a-console.conf
    mcopy -o -i '$2@@$off' openbook-a-console.conf ::/loader/entries/openbook-a-console.conf
    printf 'timeout 0\ndefault openbook-a-console.conf\nconsole-mode keep\neditor no\n' > lc.conf
    mcopy -o -i '$2@@$off' lc.conf ::/loader/loader.conf
    rm -f a.conf openbook-a-console.conf lc.conf"
}
inspect() { local d=$1 n=$2; shift 2; "$D" $E inspect "$d" "$I/$n.json" "$@" | sed "s/^/inspect $n: /" >&2; }
plan_of() { "$D" $E plan-of "$L/$1" "$L/$1/plan.json" || true; }
LIVE=(--usb "$Q/stick.img" --nvme "$Q/whole.img" --extra-usb "$Q/gapps-usb.img" --vars "$Q/stick.vars")

for c in $CASES; do
  log "=== $c"
  case $c in
  prep)
    "$S/e2e-qemu.sh" "$IMG" "$RUN" prep
    # The USB drive the user brings the package on (FAT32 "GAPPSUSB"): the reference package and a refused one.
    "$D" bash -c "set -e; cd '$Q'; rm -f gapps-usb.img; mkfs.fat -C -F 32 -n GAPPSUSB gapps-usb.img 262144 >/dev/null
      mcopy -i gapps-usb.img '$PK/openbook-synthetic-gapps-x86_64-37.zip' '$PK/neg-framework.zip' ::/
      mdir -i gapps-usb.img ::/" > "$L/gapps-usb.txt"
    sha256sum "$PK/openbook-synthetic-gapps-x86_64-37.zip" "$PK/neg-framework.zip" >> "$L/gapps-usb.txt"
    ;;
  g-cut-[1-5])
    run_case "$c" 1200 "${LIVE[@]}"
    plan_of "$c"
    inspect "$Q/whole.img" "$c" --plan "$L/$c/plan.json" --ref "$I/whole-before.json"
    ;;
  g-cli|g-ui)
    run_case "$c" 2400 "${LIVE[@]}"
    fetch_shots "$c" "$Q/stick.img" "$ESP_OFF"
    "$D" $P report-of "$L/$c" "$L/$c/report.json" || true
    inspect "$Q/whole.img" "$c" --ref "$I/whole-before.json"
    ;;
  g-installed)
    console_copy "$Q/whole.img" "$Q/gapps-console.img"
    rm -f "$Q/g-installed.vars"
    run_case g-installed 1500 --usb "$Q/blank-usb.img" --nvme "$Q/gapps-console.img" --vars "$Q/g-installed.vars"
    fetch_shots g-installed "$Q/gapps-console.img" "$(part_off "$Q/gapps-console.img" EFI)"
    rm -f "$Q/gapps-console.img"
    ;;
  g-verity)
    rep=$(ls "$L"/g-ui/report.json "$L"/g-cli/report.json 2>/dev/null | head -n 1)
    console_copy "$Q/whole.img" "$Q/verity.img"
    mkdir -p "$L/g-verity.prep"
    "$D" $P corrupt "$Q/verity.img" "$rep" app/OpenBookTestApp/lib/x86_64/libobgapps.so "$L/g-verity.prep/corrupted.json" >&2
    rm -f "$Q/g-verity.vars"
    run_case g-verity 600 --usb "$Q/blank-usb.img" --nvme "$Q/verity.img" --vars "$Q/g-verity.vars"
    mv "$L/g-verity.prep/corrupted.json" "$L/g-verity/corrupted.json"; rmdir "$L/g-verity.prep"
    rm -f "$Q/verity.img"
    ;;
  check)
    "$D" $P check --run "$L" --disks "$Q" --packages "$PK" || true
    ;;
  *) echo "unknown case $c" >&2; exit 2 ;;
  esac
done
