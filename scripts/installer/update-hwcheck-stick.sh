#!/usr/bin/env bash
# Update the OpenBook test stick's hardware check in place (ANAL-189): copy an update bundle from
# make-hwcheck-stick.sh onto the stick's OPENBOOK partition. Writes only that FAT partition, only these files:
# openbook/check/hwcheck.img, loader/entries/openbook-1*.conf, openbook/README.txt. No root needed (udisks).
#
# Refuses unless DISK is a /dev/disk/by-id/usb-* path (the owner names the exact stick), the disk has a partition
# whose PARTUUID matches the bundle's ESP_PARTUUID, that partition is FAT labelled OPENBOOK, and it already holds
# loader/entries/openbook-2-vm.conf (i.e. it is an OpenBook test stick).
#
# usage: update-hwcheck-stick.sh /dev/disk/by-id/usb-<stick> BUNDLE_DIR
set -euo pipefail
DISK=${1:?usage: update-hwcheck-stick.sh /dev/disk/by-id/usb-<stick> BUNDLE_DIR}
U=${2:?bundle dir}
case "$DISK" in /dev/disk/by-id/usb-*) ;; *) echo "refusing: $DISK is not a /dev/disk/by-id/usb-* path" >&2; exit 2 ;; esac
case "$DISK" in *-part[0-9]*) echo "refusing: name the whole stick, not a partition" >&2; exit 2 ;; esac
[ -b "$DISK" ] || { echo "refusing: $DISK does not exist" >&2; exit 2; }
WANT=$(cat "$U/ESP_PARTUUID")
DEV=$(readlink -f "$DISK"); NAME=$(basename "$DEV")
PART=$(lsblk -nrpo NAME,PARTUUID "$DEV" | awk -v u="$WANT" '$2==u {print $1}')
[ -n "$PART" ] || { echo "refusing: no partition with PARTUUID $WANT on $DISK ($NAME)" >&2; exit 2; }
[ "$(lsblk -no LABEL "$PART")" = OPENBOOK ] && [ "$(lsblk -no FSTYPE "$PART")" = vfat ] || \
  { echo "refusing: $PART is not the FAT partition labelled OPENBOOK" >&2; exit 2; }
echo "stick: $DISK -> $DEV ($(lsblk -dno VENDOR,MODEL,SIZE "$DEV" | xargs)); ESP $PART (PARTUUID $WANT)"
MP=$(findmnt -n -o TARGET "$PART" || true)
if [ -n "$MP" ] && findmnt -n -o OPTIONS "$PART" | grep -q '^ro'; then udisksctl unmount -b "$PART" >/dev/null; MP=""; fi
[ -n "$MP" ] || { udisksctl mount -b "$PART" >/dev/null; MP=$(findmnt -n -o TARGET "$PART"); }
[ -f "$MP/loader/entries/openbook-2-vm.conf" ] || { echo "refusing: $MP is not an OpenBook test stick" >&2; exit 2; }
(cd "$U" && find openbook loader -type f) | while read -r f; do
  mkdir -p "$MP/$(dirname "$f")"; cp "$U/$f" "$MP/$f"; done
sync
(cd "$MP" && sha256sum -c "$U/MANIFEST.sha256")
udisksctl unmount -b "$PART" >/dev/null
echo "updated $PART and unmounted it; the stick can be removed"
