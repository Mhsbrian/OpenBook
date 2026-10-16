#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# QEMU/KVM + OVMF tests of the OpenBook live USB image (ANAL-190). The image is attached as a USB stick (xHCI
# usb-storage) on q35 with virtio-vga 1920x1200, a USB keyboard and tablet, and a TPM; no network, no AMD GPU (the
# product falls back to virtio-gpu with SwiftShader). Every case boots a reflink copy of the image, never the image:
#   first    16 GiB stick next to a decoy NVMe disk with the same partition names: openbook-live-init grows userdata
#            and moves the backup GPT; Android formats /data and /metadata on the stick; a marker file is written;
#            the boot is given 600 s to reach sys.boot_completed; screenshot; dmesg and logcat
#   second   the same stick again: nothing to grow, the marker is still there (the live session persists)
#   reset    the same stick, "start fresh": metadata and userdata are zeroed and formatted again, the marker is gone
#   exact    a stick exactly the size of the image: nothing to grow, /data at its image size
#   logs     16 GiB stick, "save logs": the helper writes openbook/logs/live-001/ on the stick's ESP, then Android
#            shuts down; the files are read back from the ESP
#   default  16 GiB stick with the image's own default entry, nothing changed (no serial console): screenshots
#            over 6 minutes, then the ESP and GPT are read back
# Test copies use the serial-console entries: the image's own "serial console" entry, plus the two VM-only
# entries of <image>.vm/ (console + start fresh, console + save logs), copied into the copy's ESP.
# Results: <data dir>/logs/installer/<RUN>/<case>/ (serial.log, result.json, shot-*.png) and
#          <data dir>/logs/installer/<RUN>/results.json + SUMMARY.md (scripts/installer/live-qemu-check.py).
#
# usage: live-qemu.sh IMG RUN [CASE...]      default: all cases (first, second, reset run in that order)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$R/scripts/installer; D=$S/inst-docker.sh
IMG=$(realpath "${1:?usage: live-qemu.sh IMG RUN [CASE...]}"); RUN=${2:?run name}; shift 2
CASES=${*:-first second reset exact logs default}
[ -f "$IMG" ] && [ -f "$IMG.json" ] && [ -d "${IMG%.img}.vm" ] || { echo "$IMG, $IMG.json and ${IMG%.img}.vm needed: scripts/installer-image.sh" >&2; exit 1; }
Q=$A/installer/qemu/$RUN; L=$A/logs/installer/$RUN
mkdir -p "$Q" "$L"
ESP_OFF=$(python3 -c 'import json,sys; print(next(p["start"] for p in json.load(open(sys.argv[1]))["partitions"] if p["name"]=="EFI") * 512)' "$IMG.json")
GPU=(--gpu virtio-vga,xres=1920,yres=1200 --usb-input --tpm)
has() { case " $CASES " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

# stick NAME SIZE ENTRY: a fresh copy of the image, SIZE GiB ("exact": as built), booting ENTRY ("": unchanged)
stick() {
  local d=$Q/$1.img
  rm -f "$d" "$Q/$1.vars"
  cp --reflink=auto "$IMG" "$d"
  [ "$2" = exact ] || truncate -s "$2G" "$d"
  if [ -n "$3" ]; then
    printf 'timeout 0\ndefault openbook-%s.conf\nconsole-mode keep\neditor no\n' "$3" > "$Q/$1.loader.conf"
    "$D" bash -c "mcopy -o -s -m -i '$d@@$ESP_OFF' '${IMG%.img}.vm/loader' '${IMG%.img}.vm/openbook' ::/ &&
                  mcopy -o -i '$d@@$ESP_OFF' '$Q/$1.loader.conf' ::/loader/loader.conf"
  fi
  echo "stick $1: $2 GiB, entry ${3:-image default}" >&2
}

# boot STICK CASE TIMEOUT [qemu-run args...]
boot() {
  local s=$1 c=$2 t=$3; shift 3
  local exp=(); [ -f "$S/expect-live-$c.json" ] && exp=(--expect "$S/expect-live-$c.json")
  rm -rf "$L/$c"; mkdir -p "$L/$c"
  set +e
  "$D" python3 "$S/qemu-run.py" --usb "$Q/$s.img" --out "$L/$c" "${exp[@]}" "${GPU[@]}" --mem 6144 --smp 6 \
    --timeout "$t" --linger 120 --vars "$Q/$s.vars" "$@" > "$L/$c/driver.log" 2>&1
  local rc=$?
  set -e
  gzip -kf "$L/$c/serial.log" 2>/dev/null || true
  echo "case $c: qemu-run exit $rc ($(tail -n 1 "$L/$c/driver.log" | cut -c1-160))" >&2
}

chain_a() {
  if has first || has second || has reset; then
    if has first; then
      stick s16 16 vm
      rm -f "$Q/decoy.img"; "$D" python3 "$S/mkproto.py" --decoy "$Q/decoy.img" >/dev/null
      sha256sum < "$Q/decoy.img" | cut -d' ' -f1 > "$Q/decoy.sha256.before"
      boot s16 first 1500 --nvme "$Q/decoy.img"
    fi
    if has second; then boot s16 second 600 --nvme "$Q/decoy.img"; fi
    if has reset; then
      "$D" bash -c "printf 'timeout 0\ndefault openbook-vm-reset.conf\nconsole-mode keep\neditor no\n' > '$Q/s16.loader.conf' &&
                    mcopy -o -i '$Q/s16.img@@$ESP_OFF' '$Q/s16.loader.conf' ::/loader/loader.conf"
      boot s16 reset 600 --nvme "$Q/decoy.img"
    fi
  fi
}
chain_b() {
  if has logs; then stick logs16 16 vm-logs; boot logs16 logs 1500; fi
}
chain_c() {
  if has exact; then stick exact exact vm; boot exact exact 600; fi
  if has default; then
    stick default16 16 ""
    boot default16 default 400 --shot 4 15 30 45 60 90 120 180 240 300 360
  fi
}
T0=$(date +%s)
chain_a & pa=$!
chain_b & pb=$!
wait $pa $pb
chain_c
echo "cases done in $(( $(date +%s) - T0 )) s" >&2
"$D" python3 "$S/live-qemu-check.py" --run "$L" --disks "$Q" --image "$IMG" --esp-offset "$ESP_OFF"
