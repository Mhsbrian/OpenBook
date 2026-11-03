#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Rehearse a live-stick system update (stick-update.py, ANAL-331) on byte copies of the owner's stick, in QEMU/KVM:
#   before  a reflink copy of the stick's backup, booted as it is
#   after   another copy, updated with stick-update.py --write (from the same backup), then booted
# Both boot the stick's own serial-console entry (the test copy's loader.conf only) with expect-live-userdata.json,
# which prints the user-data checks (encryption state, users, third-party apps, Wi-Fi networks, adb keys, internal
# storage, app data, a hash of the Android ID) and the app-data listing. The update keeps the data when every check
# but the new system's own app-data folders reads the same. The copies are the owner's data: they stay below
# <data dir>/installer/qemu/<RUN>/ (private) and are removed with the run once its evidence is kept.
#
# usage: stick-rehearse.sh BACKUP IMG FROM_SUMS RUN       (BACKUP: the stick's read-back, below <data dir>)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$R/scripts/installer; D=$S/inst-docker.sh
BACKUP=$(realpath "$1"); IMG=$(realpath "$2"); FROM=$(realpath "$3"); RUN=$4
Q=$A/installer/qemu/$RUN; L=$A/logs/installer/$RUN
mkdir -p -m 700 "$Q" "$L"
ESP_OFF=$(python3 -c 'import json,sys; print(next(p["start"] for p in json.load(open(sys.argv[1]))["partitions"] if p["name"]=="EFI") * 512)' "$IMG.json")
copy() {
  rm -f "$Q/$1.img" "$Q/$1.vars"
  cp --reflink=always "$BACKUP" "$Q/$1.img"; chmod 600 "$Q/$1.img"
}
console() {  # the test copy boots the stick's own serial-console entry
  printf 'timeout 0\ndefault openbook-vm.conf\nconsole-mode keep\neditor no\n' > "$Q/$1.loader.conf"
  "$D" mcopy -o -i "$Q/$1.img@@$ESP_OFF" "$Q/$1.loader.conf" ::/loader/loader.conf
}
boot() {
  rm -rf "${L:?}/$1"; mkdir -p "$L/$1"
  set +e
  "$D" python3 "$S/qemu-run.py" --usb "$Q/$1.img" --out "$L/$1" --expect "$S/expect-live-userdata.json" \
    --gpu virtio-vga,xres=1920,yres=1200 --usb-input --tpm --mem 6144 --smp 6 --timeout 2400 --linger 60 \
    --vars "$Q/$1.vars" > "$L/$1/driver.log" 2>&1
  echo "$1: qemu-run exit $? ($(tail -n 1 "$L/$1/driver.log" | cut -c1-160))"
  set -e
  gzip -kf "$L/$1/serial.log" 2>/dev/null || true
  grep -a -m1 "^UDATA " "$L/$1/serial.log" > "$L/$1/udata.txt" || echo "UDATA missing" > "$L/$1/udata.txt"
  sed -n '/^===APPDATA-BEGIN===/,/^===APPDATA-END===/p' "$L/$1/serial.log" | tr -d '\r' | grep -v '^===' | sort > "$L/$1/appdata.txt" || true
}
copy before; console before; boot before
copy after
"$D" python3 "$S/stick-update.py" --image "$IMG" --target "$Q/after.img" --from "$FROM" --write \
  --report "$L/update-report.json" | tee "$L/update.log"
console after; boot after
echo "before: $(cat "$L/before/udata.txt")"
echo "after:  $(cat "$L/after/udata.txt")"
echo "app data only after:  $(comm -13 "$L/before/appdata.txt" "$L/after/appdata.txt" | tr '\n' ' ')"
echo "app data only before: $(comm -23 "$L/before/appdata.txt" "$L/after/appdata.txt" | tr '\n' ' ')"
