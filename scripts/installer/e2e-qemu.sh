#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The installer end to end in QEMU/KVM + OVMF (ANAL-192), image files only: alongside a Windows-like disk, a small
# disk refused, power cuts at every install step with a restart from the stick, the installed disk with and
# without the stick, and a reinstall over a used OpenBook. scripts/installer/e2e-qemu.py describes every case.
# Cases run in the order given and keep their disks in <data dir>/installer/qemu/RUN/, so a long matrix can be run
# in several calls (each case is one QEMU boot of 10 s to 6 min). `check` writes RUN/results.json and SUMMARY.md.
#
# usage: e2e-qemu.sh IMG RUN CASE...
#   CASE: prep live-a al-windows al-fwsetup al-openbook al-console cut-1 ... cut-6 install installed inst-stick
#         reinstall reinstalled check | all
# Results: <data dir>/logs/installer/RUN/<case>/ (serial.log, result.json, sections/, screens/) and RUN/inspect/
# (each disk state, read from outside the VM).
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$R/scripts/installer; D=$S/inst-docker.sh; P="python3 $S/e2e-qemu.py"
IMG=$(realpath "${1:?usage: e2e-qemu.sh IMG RUN CASE...}"); RUN=${2:?run name}; shift 2
CASES=${*:?cases}
[ "$CASES" = all ] && CASES="prep live-a al-windows al-fwsetup al-console al-openbook cut-1 cut-2 cut-3 cut-4 cut-5 cut-6 install installed inst-stick reinstall reinstalled check"
[ -f "$IMG" ] && [ -f "$IMG.json" ] || { echo "$IMG and $IMG.json needed: scripts/installer-image.sh" >&2; exit 1; }
Q=$A/installer/qemu/$RUN; L=$A/logs/installer/$RUN; I=$L/inspect
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
# Android's screenshots (screencap), saved by the expect scripts to a FAT partition: copy them out, then clear them.
fetch_shots() {  # CASE DISK OFFSET
  "$D" bash -c "mkdir -p '$L/$1/screens' && mcopy -n -o -s -i '$2@@$3' ::/openbook/shots/ '$L/$1/screens/' &&
                mdeltree -i '$2@@$3' ::/openbook/shots" >/dev/null 2>&1 || log "no screenshots for $1"
}
part_off() {  # DISK NAME -> byte offset of the GPT partition called NAME
  "$D" python3 -c "
import sys; sys.path.insert(0, '$S'); import importlib.util as u
s = u.spec_from_file_location('e', '$S/e2e-qemu.py'); e = u.module_from_spec(s); s.loader.exec_module(e)
t, _ = e.table_of(e.gpt_read(sys.argv[1])); print(next(p['first'] * 512 for p in t['parts'] if p['name'] == sys.argv[2]))" "$1" "$2"
}
# A copy of an installed disk whose default entry is its OpenBook entry plus the serial console. On XBOOTLDR (alongside)
# there is no loader.conf: the new entry's sort key puts it first.
console_copy() {  # SRC DST PARTNAME
  rm -f "$2"; cp --reflink=auto "$1" "$2"
  local off; off=$(part_off "$2" "$3")
  "$D" bash -c "set -e; cd '$Q'
    mcopy -n -o -i '$2@@$off' ::/loader/entries/openbook-a.conf a.conf
    sed -e 's/^title .*/title OpenBook (serial console test)/' -e 's/^sort-key .*/sort-key 0-console/' \
        -e 's/^options \(.*\)/options \1 console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on/' a.conf > openbook-a-console.conf
    grep -q '^sort-key' openbook-a-console.conf || sed -i '1a sort-key 0-console' openbook-a-console.conf
    mcopy -o -i '$2@@$off' openbook-a-console.conf ::/loader/entries/openbook-a-console.conf
    if [ '$3' = EFI ]; then printf 'timeout 0\ndefault openbook-a-console.conf\nconsole-mode keep\neditor no\n' > lc.conf
      mcopy -o -i '$2@@$off' lc.conf ::/loader/loader.conf; fi
    rm -f a.conf openbook-a-console.conf lc.conf"
}
inspect() {  # DISK NAME [--plan F] [--ref F]
  local d=$1 n=$2; shift 2
  "$D" $P inspect "$d" "$I/$n.json" "$@" | sed "s/^/inspect $n: /" >&2
}
plan_of() { "$D" $P plan-of "$L/$1" "$L/$1/plan.json" || true; }

for c in $CASES; do
  log "=== $c"
  case $c in
  prep)
    # Test EFI apps (scripts/installer/e2e/obtest-efi.c): the Windows boot manager stand-in and the firmware-setup helper.
    "$D" bash -c "set -e; cd '$Q'
      CF='-O2 -Wall -Wextra -Werror -ffreestanding -fno-stack-protector -fno-stack-check -mno-red-zone -fpie -fno-asynchronous-unwind-tables -fno-builtin -fno-ident'
      gcc \$CF -DOBTEST_MARK='\"windows-bootmgr\"' -c '$S/e2e/obtest-efi.c' -o mark.o
      gcc \$CF -DOBTEST_ADDBOOT -c '$S/e2e/obtest-efi.c' -o addboot.o
      for x in mark addboot; do objcopy -R .note.gnu.property \$x.o; ld -m i386pep --subsystem 10 -e efi_main --dynamicbase --image-base 0x10000000 -o \$x.efi \$x.o; rm \$x.o; done
      sha256sum mark.efi addboot.efi
      rm -f helper.img blank-usb.img; mkfs.fat -C -F 32 helper.img 65536 >/dev/null
      mmd -i helper.img ::/EFI ::/EFI/BOOT; mcopy -i helper.img addboot.efi ::/EFI/BOOT/BOOTX64.EFI
      truncate -s 64M blank-usb.img" > "$L/efi-apps.txt"
    # The stick: a 16 GiB copy whose default entry is the image's serial-console VM entry at density 240 (as wizard-qemu.sh).
    rm -f "$Q/stick.img" "$Q"/*.vars
    cp --reflink=auto "$IMG" "$Q/stick.img"; truncate -s 16G "$Q/stick.img"
    "$D" bash -c "set -e; cd '$Q'
      mcopy -n -o -i 'stick.img@@$ESP_OFF' ::/openbook/a/bootconfig-vm.img bc-vm.img
      python3 '$S/bootconfig.py' show bc-vm.img | sed 's/^androidboot.lcd_density = .*/androidboot.lcd_density = 240/' > bc-vm240.txt
      python3 '$S/bootconfig.py' make bootconfig-vm240.img --base bc-vm240.txt
      mcopy -n -o -i 'stick.img@@$ESP_OFF' ::/loader/entries/openbook-vm.conf vm.conf
      sed -e 's/^title .*/title OpenBook - e2e test (2880x1800, density 240, serial console)/' \
          -e 's/^sort-key .*/sort-key openbook-9/' -e 's/bootconfig-vm.img/bootconfig-vm240.img/' vm.conf > openbook-vm240.conf
      printf 'timeout 0\ndefault openbook-vm240.conf\nconsole-mode keep\neditor no\n' > loader.conf
      mcopy -o -i 'stick.img@@$ESP_OFF' bootconfig-vm240.img ::/openbook/a/bootconfig-vm240.img
      mcopy -o -i 'stick.img@@$ESP_OFF' openbook-vm240.conf ::/loader/entries/openbook-vm240.conf
      mcopy -o -i 'stick.img@@$ESP_OFF' loader.conf ::/loader/loader.conf
      rm -f bc-vm.img bc-vm240.txt bootconfig-vm240.img vm.conf openbook-vm240.conf loader.conf"
    # The disks: a Windows-like 200 GiB disk (alongside), a 32 GiB blank one (too small), a Windows-like 128 GiB disk
    # (the whole-disk runs erase it).
    "$D" $P mkdisk windows "$Q/win.img" --gib 200 --mark "$Q/mark.efi" >&2
    "$D" $P mkdisk windows "$Q/whole.img" --gib 128 --mark "$Q/mark.efi" >&2
    rm -f "$Q/small.img"; truncate -s 32G "$Q/small.img"
    inspect "$Q/win.img" windows-before
    inspect "$Q/whole.img" whole-before
    inspect "$Q/stick.img" stick-prep
    ;;
  live-a)
    run_case live-a 1500 --usb "$Q/stick.img" --nvme "$Q/win.img" --nvme2 "$Q/small.img" --vars "$Q/stick.vars"
    fetch_shots live-a "$Q/stick.img" "$ESP_OFF"
    plan_of live-a
    inspect "$Q/win.img" windows-after --plan "$L/live-a/plan.json" --ref "$I/windows-before.json"
    ;;
  al-windows)  # fresh NVRAM: what the firmware finds by itself
    rm -f "$Q/al-win.vars"
    run_case al-windows 60 --usb "$Q/blank-usb.img" --nvme "$Q/win.img" --vars "$Q/al-win.vars"
    ;;
  al-fwsetup)  # the user adds a boot option for OpenBook (firmware setup); its NVRAM is kept for al-openbook
    rm -f "$Q/al.vars"
    run_case al-fwsetup 60 --usb "$Q/helper.img" --nvme "$Q/win.img" --vars "$Q/al.vars"
    cp "$Q/al.vars" "$Q/al-console.vars"
    ;;
  al-console)
    console_copy "$Q/win.img" "$Q/win-console.img" xbootldr
    run_case al-console 900 --usb "$Q/blank-usb.img" --nvme "$Q/win-console.img" --vars "$Q/al-console.vars"
    fetch_shots al-console "$Q/win-console.img" "$(part_off "$Q/win-console.img" xbootldr)"
    rm -f "$Q/win-console.img"
    ;;
  al-openbook)  # the unchanged alongside disk, as the user boots it: screenshots only (no serial console)
    run_case al-openbook 200 --usb "$Q/blank-usb.img" --nvme "$Q/win.img" --vars "$Q/al.vars" --shot 20 40 60 90 120 150 180
    ;;
  cut-[1-6])
    run_case "$c" 900 --usb "$Q/stick.img" --nvme "$Q/whole.img" --vars "$Q/stick.vars"
    plan_of "$c"
    inspect "$Q/whole.img" "$c" --plan "$L/$c/plan.json" --ref "$I/whole-before.json"
    # What the firmware starts from the cut disk (a copy: a complete install would start its first boot).
    rm -f "$Q/fw.img" "$Q/fw.vars"; cp --reflink=auto "$Q/whole.img" "$Q/fw.img"
    run_case "fw-$c" 30 --usb "$Q/blank-usb.img" --nvme "$Q/fw.img" --vars "$Q/fw.vars"
    rm -f "$Q/fw.img"
    ;;
  install)
    run_case install 1500 --usb "$Q/stick.img" --nvme "$Q/whole.img" --vars "$Q/stick.vars"
    plan_of install
    inspect "$Q/whole.img" install --plan "$L/install/plan.json" --ref "$I/whole-before.json"
    ;;
  installed)  # the installed disk alone, unchanged, fresh NVRAM, as the firmware finds it
    rm -f "$Q/installed.vars"
    run_case installed 200 --usb "$Q/blank-usb.img" --nvme "$Q/whole.img" --vars "$Q/installed.vars" --shot 20 40 60 90 120 150 180
    ;;
  inst-stick)  # the stick left plugged in, the disk first in the boot order
    console_copy "$Q/whole.img" "$Q/used.img" EFI
    inspect "$Q/stick.img" stick-before-inst-stick
    rm -f "$Q/inst.vars"
    run_case inst-stick 900 --usb "$Q/stick.img" --nvme "$Q/used.img" --nvme-first --vars "$Q/inst.vars"
    inspect "$Q/stick.img" stick-after-inst-stick
    fetch_shots inst-stick "$Q/used.img" "$(part_off "$Q/used.img" EFI)"
    ;;
  reinstall)
    inspect "$Q/used.img" used
    run_case reinstall 1500 --usb "$Q/stick.img" --nvme "$Q/used.img" --vars "$Q/stick.vars"
    fetch_shots reinstall "$Q/stick.img" "$ESP_OFF"
    plan_of reinstall
    inspect "$Q/used.img" reinstall --plan "$L/reinstall/plan.json"
    ;;
  reinstalled)
    console_copy "$Q/used.img" "$Q/reinst-console.img" EFI
    rm -f "$Q/reinst.vars"
    run_case reinstalled 900 --usb "$Q/blank-usb.img" --nvme "$Q/reinst-console.img" --vars "$Q/reinst.vars"
    fetch_shots reinstalled "$Q/reinst-console.img" "$(part_off "$Q/reinst-console.img" EFI)"
    ;;
  check)
    "$D" $P check --run "$L" --disks "$Q" --image "$IMG" || true
    ;;
  *) echo "unknown case $c" >&2; exit 2 ;;
  esac
done
