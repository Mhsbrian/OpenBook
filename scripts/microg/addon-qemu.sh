#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The microG add-on on the G14 product in QEMU/KVM + OVMF (ANAL-210), image files only, never a stick or a disk:
# the live stick without and with the add-on, a second boot, the image from main for comparison, an install to a
# blank NVMe disk with the add-on ticked, and that disk's first start. scripts/microg/addon-qemu.py describes the cases
# and the checks. Each stick is a 16 GiB copy whose default entry is the image's serial-console VM entry (SELinux
# enforcing); the installed disk gets a serial-console copy of its own entry (as e2e-qemu.sh).
#
# usage: addon-qemu.sh IMG MAIN_IMG ADDON_DIR RUN CASE...
#   CASE: prep-main prep plain main addon addon-2 addon-logs install installed check | all
# Results: <data dir>/logs/installer/RUN/<case>/ (serial.log, result.json, screens/), RUN/results.json, SUMMARY.md
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$R/scripts/installer; D=$S/inst-docker.sh; P="python3 $R/scripts/microg/addon-qemu.py"
IMG=$(realpath "${1:?usage: addon-qemu.sh IMG MAIN_IMG ADDON_DIR RUN CASE...}"); MAIN=$(realpath "${2:?main image}")
U=$(realpath "${3:?add-on}"); RUN=${4:?run}; shift 4
CASES=${*:?cases}; [ "$CASES" = all ] && CASES="prep-main prep plain main addon addon-2 addon-logs install installed check"
Q=$A/installer/qemu/$RUN; L=$A/logs/installer/$RUN; mkdir -p "$Q" "$L"
esp_off() { python3 -c 'import json,sys; print(next(p["start"] for p in json.load(open(sys.argv[1]))["partitions"] if p["name"]=="EFI") * 512)' "$1.json"; }
log() { echo "[$(date -u +%H:%M:%S)] $*" >&2; }

stick() {  # SRC DST: a 16 GiB copy booting the image's serial-console entry (openbook-vm.conf)
  local off; off=$(esp_off "$1")
  rm -f "$2" "${2%.img}.vars"; cp --reflink=auto "$1" "$2"; truncate -s 16G "$2"
  printf 'timeout 0\ndefault openbook-vm.conf\nconsole-mode keep\neditor no\n' > "$Q/loader.conf"
  "$D" mcopy -o -i "$2@@$off" "$Q/loader.conf" ::/loader/loader.conf
}
run_case() {  # CASE TIMEOUT [qemu-run args...]
  local c=$1 t=$2; shift 2
  rm -rf "${L:?}/$c"; mkdir -p "$L/$c"
  "$D" $P expect "$c" "$L/$c/expect.json"
  set +e
  "$D" python3 "$S/qemu-run.py" --out "$L/$c" --expect "$L/$c/expect.json" --gpu virtio-vga,xres=1920,yres=1200 \
    --usb-input --tpm --mem 8192 --smp 8 --timeout "$t" --linger 5 "$@" > "$L/$c/driver.log" 2>&1
  local rc=$?; set -e
  log "case $c: qemu-run exit $rc ($(tail -n 1 "$L/$c/driver.log" | cut -c1-160))"
}
fetch_shots() {  # CASE DISK OFFSET: Android's screenshots, saved by the expect script to a FAT partition
  "$D" bash -c "mkdir -p '$L/$1/screens' && mcopy -n -o -s -i '$2@@$3' ::/openbook/shots/ '$L/$1/screens/' &&
                mdeltree -i '$2@@$3' ::/openbook/shots" >/dev/null 2>&1 || log "no screenshots for $1"
}
part_off() {  # DISK NAME -> byte offset of the GPT partition called NAME
  "$D" python3 -c "
import importlib.util as u, sys
s = u.spec_from_file_location('e', '$S/e2e-qemu.py'); e = u.module_from_spec(s); s.loader.exec_module(e)
t, _ = e.table_of(e.gpt_read(sys.argv[1])); print(next(p['first'] * 512 for p in t['parts'] if p['name'] == sys.argv[2]))" "$1" "$2"
}

for c in $CASES; do
  log "=== $c"
  case $c in
    prep-main) stick "$MAIN" "$Q/main.img" ;;
    prep)
      stick "$IMG" "$Q/plain.img"
      stick "$IMG" "$Q/addon.img"
      "$D" "$R/scripts/microg/add-to-image.sh" "$Q/addon.img" "$U" | tee "$L/add-to-image.txt"
      cp --reflink=auto "$Q/addon.img" "$Q/addon-inst.img"   # a second, unbooted copy for the install case
      rm -f "$Q/whole.img" "$Q/plain-target.img" "$Q/blank-usb.img"
      truncate -s 64G "$Q/whole.img"; truncate -s 64G "$Q/plain-target.img"; truncate -s 64M "$Q/blank-usb.img"
      ;;
    plain) run_case plain 1500 --usb "$Q/plain.img" --nvme "$Q/plain-target.img" --vars "$Q/plain.vars"
      fetch_shots plain "$Q/plain.img" "$(esp_off "$IMG")" ;;
    main) run_case main 1500 --usb "$Q/main.img" --vars "$Q/main.vars" ;;
    addon) run_case addon 1500 --usb "$Q/addon.img" --vars "$Q/addon.vars"; fetch_shots addon "$Q/addon.img" "$(esp_off "$IMG")" ;;
    addon-2) run_case addon-2 1500 --usb "$Q/addon.img" --vars "$Q/addon.vars" ;;
    addon-logs)  # the same stick's "save logs" entry (the image's VM bundle): the helper's capture, read back
      off=$(esp_off "$IMG")
      "$D" mcopy -o -s -m -i "$Q/addon.img@@$off" "${IMG%.img}.vm/loader" "${IMG%.img}.vm/openbook" ::/
      printf 'timeout 0\ndefault openbook-vm-logs.conf\nconsole-mode keep\neditor no\n' > "$Q/loader.conf"
      "$D" mcopy -o -i "$Q/addon.img@@$off" "$Q/loader.conf" ::/loader/loader.conf
      run_case addon-logs 1500 --usb "$Q/addon.img" --vars "$Q/addon.vars"
      "$D" bash -c "rm -rf '$L/addon-logs/stick-logs' && mkdir -p '$L/addon-logs/stick-logs' &&
                    mcopy -s -n -i '$Q/addon.img@@$off' ::/openbook/logs '$L/addon-logs/stick-logs/'"
      ;;
    install) run_case install 2400 --usb "$Q/addon-inst.img" --nvme "$Q/whole.img" --vars "$Q/addon-inst.vars"
      fetch_shots install "$Q/addon-inst.img" "$(esp_off "$IMG")" ;;
    installed)
      # A copy of the installed disk whose default entry is its own OpenBook entry plus the serial console.
      rm -f "$Q/installed.img"; cp --reflink=auto "$Q/whole.img" "$Q/installed.img"
      off=$(part_off "$Q/installed.img" EFI)
      "$D" bash -c "set -e; cd '$Q'
        mcopy -n -o -i 'installed.img@@$off' ::/loader/entries/openbook-a.conf a.conf
        sed -e 's/^title .*/title OpenBook (serial console test)/' -e 's/^sort-key .*/sort-key 0-console/' \
            -e 's/^options \(.*\)/options \1 console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on/' a.conf > openbook-a-console.conf
        mcopy -o -i 'installed.img@@$off' openbook-a-console.conf ::/loader/entries/openbook-a-console.conf
        printf 'timeout 0\ndefault openbook-a-console.conf\nconsole-mode keep\neditor no\n' > lc.conf
        mcopy -o -i 'installed.img@@$off' lc.conf ::/loader/loader.conf
        mdir -/ -b -i 'installed.img@@$off' ::/openbook/addons > '$L/installed-esp-addons.txt'
        rm -f a.conf openbook-a-console.conf lc.conf"
      rm -f "$Q/installed.vars"
      run_case installed 1500 --usb "$Q/blank-usb.img" --nvme "$Q/installed.img" --vars "$Q/installed.vars"
      fetch_shots installed "$Q/installed.img" "$off"
      ;;
    check) "$D" $P check --run "$L" || true ;;
    *) echo "unknown case $c" >&2; exit 2 ;;
  esac
done
