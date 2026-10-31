#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The installer wizard end to end in QEMU/KVM + OVMF (ANAL-191), image files only (scripts/installer/wizard-qemu.py
# describes the cases): dryrun and install from a copy of the live stick onto a blank 64 GiB virtual NVMe disk,
# then the installed disk booted alone (installed: unchanged, screenshots; console: a copy with a serial console
# entry). The stick boots a test entry at the G14's 2880x1800 with density 240 on virtio-vga, SELinux enforcing.
# Results: <data dir>/logs/installer/RUN/<case>/ (serial.log, shot-*.png, sections/) and RUN/results.json + SUMMARY.md.
#
# Firmware boot entries (efivarfs, S11): nvram-boot boots a copy of the installed disk with EFI/BOOT/BOOTX64.EFI
# deleted, with the NVRAM the install left (so only OpenBook's Boot#### can start it); alongside installs next to a
# Windows-like disk whose "Windows Boot Manager" entry (a stand-in EFI app, efi-standin.c) is first in BootOrder;
# OpenBook's entry goes last. alongside-default boots that disk with that NVRAM: Windows starts by default, then
# OpenBook is picked in the firmware's boot menu; alongside-boot boots it again through BootNext.
#
# usage: wizard-qemu.sh IMG RUN [CASE...]      default: dryrun install installed console (in that order)
#        cases also: nvram-boot (after install), alongside, alongside-default (after alongside), alongside-boot
#        (after alongside-default)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$R/scripts/installer; D=$S/inst-docker.sh
IMG=$(realpath "${1:?usage: wizard-qemu.sh IMG RUN [CASE...]}"); RUN=${2:?run name}; shift 2
CASES=${*:-dryrun install installed console}
[ -f "$IMG" ] && [ -f "$IMG.json" ] && [ -d "${IMG%.img}.vm" ] || { echo "$IMG, $IMG.json and ${IMG%.img}.vm needed: scripts/installer-image.sh" >&2; exit 1; }
Q=$A/installer/qemu/$RUN; L=$A/logs/installer/$RUN
mkdir -p "$Q" "$L"
ESP_OFF=$(python3 -c 'import json,sys; print(next(p["start"] for p in json.load(open(sys.argv[1]))["partitions"] if p["name"]=="EFI") * 512)' "$IMG.json")
GPU=(--gpu virtio-vga,xres=2880,yres=1800 --usb-input --tpm)
has() { case " $CASES " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }
EXPECT_ARGS=()
run_case() {  # CASE TIMEOUT [qemu-run args...]
  local c=$1 t=$2; shift 2
  rm -rf "$L/$c"; mkdir -p "$L/$c"
  "$D" python3 "$S/wizard-qemu.py" expect "$c" "$L/$c/expect.json" "${EXPECT_ARGS[@]}"
  set +e
  "$D" python3 "$S/qemu-run.py" --out "$L/$c" --expect "$L/$c/expect.json" "${GPU[@]}" --mem 8192 --smp 8 \
    --timeout "$t" --linger 20 "$@" > "$L/$c/driver.log" 2>&1
  local rc=$?
  set -e
  gzip -kf "$L/$c/serial.log" 2>/dev/null || true
  echo "case $c: qemu-run exit $rc ($(tail -n 1 "$L/$c/driver.log" | cut -c1-200))" >&2
}

# Android's screenshots (screencap), which the expect scripts save to the stick's ESP: copy them out, then clear them.
fetch_shots() {  # CASE
  "$D" bash -c "mkdir -p '$L/$1/screens' && mcopy -n -o -s -i '$Q/stick.img@@$ESP_OFF' ::/openbook/shots/ '$L/$1/screens/' &&
                mdeltree -i '$Q/stick.img@@$ESP_OFF' ::/openbook/shots" || echo "no screenshots on the stick for $1" >&2
}

# The stick: a 16 GiB copy whose default entry is the image's VM entry at density 240 (and the serial console).
if has dryrun || has install; then
  if has dryrun; then
    rm -f "$Q/stick.img" "$Q/stick.vars" "$Q/dryrun-nvme.img"
    cp --reflink=auto "$IMG" "$Q/stick.img"
    truncate -s 16G "$Q/stick.img"
    "$D" bash -c "set -e; cd '$Q'
      mcopy -n -o -i 'stick.img@@$ESP_OFF' ::/openbook/a/bootconfig-vm.img bc-vm.img
      python3 '$S/bootconfig.py' show bc-vm.img | sed 's/^androidboot.lcd_density = .*/androidboot.lcd_density = 240/' > bc-vm240.txt
      python3 '$S/bootconfig.py' make bootconfig-vm240.img --base bc-vm240.txt
      mcopy -n -o -i 'stick.img@@$ESP_OFF' ::/loader/entries/openbook-vm.conf vm.conf
      sed -e 's/^title .*/title OpenBook - wizard test (2880x1800, density 240, serial console)/' \
          -e 's/^sort-key .*/sort-key openbook-9/' -e 's/bootconfig-vm.img/bootconfig-vm240.img/' vm.conf > openbook-vm240.conf
      printf 'timeout 0\ndefault openbook-vm240.conf\nconsole-mode keep\neditor no\n' > loader.conf
      mcopy -o -i 'stick.img@@$ESP_OFF' bootconfig-vm240.img ::/openbook/a/bootconfig-vm240.img
      mcopy -o -i 'stick.img@@$ESP_OFF' openbook-vm240.conf ::/loader/entries/openbook-vm240.conf
      mcopy -o -i 'stick.img@@$ESP_OFF' loader.conf ::/loader/loader.conf"
    truncate -s 64G "$Q/dryrun-nvme.img"
    run_case dryrun 1800 --usb "$Q/stick.img" --nvme "$Q/dryrun-nvme.img" --vars "$Q/stick.vars"
    fetch_shots dryrun
  fi
  if has install; then
    rm -f "$Q/nvme.img"
    truncate -s 64G "$Q/nvme.img"
    run_case install 3000 --usb "$Q/stick.img" --nvme "$Q/nvme.img" --vars "$Q/stick.vars"
    fetch_shots install
    "$D" bash -c "sgdisk -v '$Q/nvme.img'; sgdisk -p '$Q/nvme.img'" > "$L/install/nvme-gpt.txt" 2>&1 || true
  fi
fi
# qemu-run.py wants a USB stick: the installed-disk cases get a tiny blank one that the firmware skips.
if has installed || has console; then
  rm -f "$Q/blank-usb.img"; truncate -s 64M "$Q/blank-usb.img"
fi
# The installed disk alone, as the firmware finds it: no stick, fresh NVRAM, unchanged entries, no serial console.
if has installed; then
  rm -f "$Q/installed.vars"
  run_case installed 480 --usb "$Q/blank-usb.img" --nvme "$Q/nvme.img" --vars "$Q/installed.vars" \
    --shot 10 20 30 45 60 90 120 180 240 300 360 420
fi
# A copy of the installed disk with one more entry: the installed entry plus the serial console.
if has console; then
  rm -f "$Q/console-nvme.img" "$Q/console.vars"
  cp --reflink=auto "$Q/nvme.img" "$Q/console-nvme.img"
  "$D" bash -c "set -e; cd '$Q'
    off=\$(sgdisk -i 1 console-nvme.img | sed -n 's/^First sector: \([0-9]*\).*/\1/p'); off=\$((off * 512))
    mcopy -n -o -i \"console-nvme.img@@\$off\" ::/loader/entries/openbook-a.conf a.conf
    sed -e 's/^title .*/title OpenBook (serial console test)/' -e 's/^sort-key .*/sort-key openbook-0/' \
        -e 's/^options \(.*\)/options \1 console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on/' a.conf > openbook-a-console.conf
    printf 'timeout 0\ndefault openbook-a-console.conf\nconsole-mode keep\neditor no\n' > loader-console.conf
    mcopy -o -i \"console-nvme.img@@\$off\" openbook-a-console.conf ::/loader/entries/openbook-a-console.conf
    mcopy -o -i \"console-nvme.img@@\$off\" loader-console.conf ::/loader/loader.conf"
  run_case console 900 --usb "$Q/blank-usb.img" --nvme "$Q/console-nvme.img" --vars "$Q/console.vars"
  "$D" bash -c "off=\$(sgdisk -i 1 '$Q/console-nvme.img' | sed -n 's/^First sector: \([0-9]*\).*/\1/p'); off=\$((off * 512))
    mkdir -p '$L/console/screens' && mcopy -n -o -s -i \"$Q/console-nvme.img@@\$off\" ::/openbook/shots/ '$L/console/screens/'" ||
    echo "no screenshots on the installed disk copy" >&2
fi
# OpenBook's firmware entry alone: the installed disk with its fallback path deleted, the NVRAM of the install.
if has nvram-boot; then
  rm -f "$Q/nvboot-nvme.img" "$Q/nvboot.vars"; truncate -s 64M "$Q/blank-usb.img"
  cp --reflink=auto "$Q/nvme.img" "$Q/nvboot-nvme.img"; cp "$Q/stick.vars" "$Q/nvboot.vars"
  "$D" bash -c "set -e; cd '$Q'
    off=\$(sgdisk -i 1 nvboot-nvme.img | sed -n 's/^First sector: \([0-9]*\).*/\1/p'); off=\$((off * 512))
    mdel -i \"nvboot-nvme.img@@\$off\" ::/EFI/BOOT/BOOTX64.EFI
    mcopy -n -o -i \"nvboot-nvme.img@@\$off\" ::/loader/entries/openbook-a.conf a.conf
    sed -e 's/^title .*/title OpenBook (serial console test)/' -e 's/^sort-key .*/sort-key openbook-0/' \
        -e 's/^options \(.*\)/options \1 console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on/' a.conf > openbook-a-console.conf
    printf 'timeout 0\ndefault openbook-a-console.conf\nconsole-mode keep\neditor no\n' > loader-console.conf
    mcopy -o -i \"nvboot-nvme.img@@\$off\" openbook-a-console.conf ::/loader/entries/openbook-a-console.conf
    mcopy -o -i \"nvboot-nvme.img@@\$off\" loader-console.conf ::/loader/loader.conf
    mdir -/ -b -i \"nvboot-nvme.img@@\$off\" ::/EFI" > "$L/nvboot-esp.txt"
  run_case nvram-boot 600 --usb "$Q/blank-usb.img" --nvme "$Q/nvboot-nvme.img" --vars "$Q/nvboot.vars" --no-bootindex
  mv "$L/nvboot-esp.txt" "$L/nvram-boot/esp-EFI-listing.txt"
fi
# Alongside a Windows-like disk whose firmware entry is first, then that disk booted through OpenBook's entry.
if has alongside; then
  [ -f "$Q/stick.img" ] || { echo "alongside needs the stick of a dryrun/install run in $Q" >&2; exit 1; }
  rm -f "$Q/win.img" "$Q/alongside.vars"
  WIN=$("$D" python3 "$S/wizard-qemu.py" mkwin "$Q/win.img")
  echo "$WIN" > "$Q/win.json"
  EXPECT_ARGS=(--win "$WIN")
  run_case alongside 2400 --usb "$Q/stick.img" --nvme "$Q/win.img" --vars "$Q/alongside.vars"
  EXPECT_ARGS=()
  fetch_shots alongside
  "$D" bash -c "sgdisk -v '$Q/win.img'; sgdisk -p '$Q/win.img'" > "$L/alongside/win-gpt.txt" 2>&1 || true
fi
if has alongside-default; then
  rm -f "$Q/winboot.img" "$Q/winboot.vars"; truncate -s 64M "$Q/blank-usb.img"
  cp --reflink=auto "$Q/win.img" "$Q/winboot.img"; cp "$Q/alongside.vars" "$Q/winboot.vars"
  "$D" bash -c "set -e; cd '$Q'
    n=\$(sgdisk -p winboot.img | awk '\$NF == \"xbootldr\" {print \$1}')
    off=\$(sgdisk -i \$n winboot.img | sed -n 's/^First sector: \([0-9]*\).*/\1/p'); off=\$((off * 512))
    mcopy -n -o -i \"winboot.img@@\$off\" ::/loader/entries/openbook-a.conf wa.conf
    sed -e 's/^title .*/title OpenBook (serial console test)/' -e 's/^sort-key .*/sort-key openbook-0/' \
        -e 's/^options \(.*\)/options \1 console=ttyS0,115200 8250.nr_uarts=1 printk.devkmsg=on/' wa.conf > wopenbook-a-console.conf
    mcopy -o -i \"winboot.img@@\$off\" wopenbook-a-console.conf ::/loader/entries/openbook-a-console.conf"
  run_case alongside-default 900 --usb "$Q/blank-usb.img" --nvme "$Q/winboot.img" --vars "$Q/winboot.vars" --no-bootindex
fi
if has alongside-boot; then  # the same disk and NVRAM, BootNext set by alongside-default's last step
  [ -f "$Q/winboot.vars" ] || { echo "alongside-boot needs alongside-default's disk and NVRAM in $Q" >&2; exit 1; }
  run_case alongside-boot 600 --usb "$Q/blank-usb.img" --nvme "$Q/winboot.img" --vars "$Q/winboot.vars" --no-bootindex
fi
"$D" python3 "$S/wizard-qemu.py" check --run "$L" --disks "$Q" --image "$IMG"
