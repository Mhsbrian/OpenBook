#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Write an OpenBook live image to a USB stick (ANAL-190), on the dev host. This ERASES the whole stick.
#
# Refuses unless:
#   - DISK is a whole-disk /dev/disk/by-id/usb-* path, on the USB bus, at least as large as the image, and holds
#     neither / nor /boot of this host;
#   - OPENBOOK_WRITE_CONFIRM is set to exactly that path (the owner's confirmation names the device);
#   - the image matches its .sha256 file.
# Before writing: OpenBook reports already on the stick (openbook/logs/ on a FAT partition labelled OPENBOOK) are
# copied to <data dir>/installer/stick-backup/<UTC>/, read-only. The stick's partitions are unmounted (udisks).
# Writing: dd in the openbook-installer container, which gets this one device and nothing else (no sudo here).
# Then the stick is read back and compared with the image's sha256, and powered off (safe to unplug).
# --dry-run does every check, shows the stick and what is on it, and writes nothing.
# Log: <data dir>/logs/installer/write-stick-<UTC>.log (and a copy with the stick's serial number redacted).
#
# usage: OPENBOOK_WRITE_CONFIRM=/dev/disk/by-id/usb-<stick> write-stick.sh IMG /dev/disk/by-id/usb-<stick>
#        write-stick.sh --dry-run IMG /dev/disk/by-id/usb-<stick>
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
DRY=0
[ "${1:-}" = --dry-run ] && { DRY=1; shift; }
IMG=${1:?usage: write-stick.sh [--dry-run] IMG /dev/disk/by-id/usb-<stick>}
DISK=${2:?usage: write-stick.sh [--dry-run] IMG /dev/disk/by-id/usb-<stick>}
IMAGE=${OPENBOOK_INSTALLER_IMAGE:-openbook-installer}
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=$A/logs/installer/write-stick-$TS.log
mkdir -p "$A/logs/installer"
exec > >(tee -a "$LOG") 2>&1
die() { echo "REFUSED: $*"; exit 2; }
echo "== write-stick.sh $TS: $IMG -> $DISK$([ $DRY = 1 ] && echo ' (dry run)')"

# The device
case "$DISK" in /dev/disk/by-id/usb-*) ;; *) die "$DISK is not a /dev/disk/by-id/usb-* path" ;; esac
case "$DISK" in *-part[0-9]*) die "name the whole stick, not a partition" ;; esac
[ -b "$DISK" ] || die "$DISK does not exist (is the stick plugged in?)"
if [ $DRY = 0 ] && [ "${OPENBOOK_WRITE_CONFIRM:-}" != "$DISK" ]; then
  die "OPENBOOK_WRITE_CONFIRM must be exactly $DISK (the owner's confirmation naming this device)"
fi
DEV=$(readlink -f "$DISK")
read -r TRAN RM SIZE VENDOR MODEL <<<"$(lsblk -dnbo TRAN,RM,SIZE,VENDOR,MODEL "$DEV" | xargs)"
[ "$TRAN" = usb ] || die "$DEV is on '$TRAN', not USB"
for m in / /boot /home; do
  src=$(findmnt -nvo SOURCE "$m" 2>/dev/null || true)
  [ -n "$src" ] || continue
  for pk in $(lsblk -nsrpo NAME,TYPE "$src" 2>/dev/null | awk '$2=="disk"{print $1}'); do
    [ "$pk" != "$DEV" ] || die "$DEV holds this host's $m"
  done
done
echo "stick: $DISK -> $DEV; $VENDOR $MODEL; $SIZE bytes ($((SIZE / 1000000000)) GB); removable=$RM"
echo "today on it:"; lsblk -o NAME,SIZE,FSTYPE,LABEL,PARTLABEL,MOUNTPOINTS "$DEV" | sed 's/^/  /'

# The image
[ -f "$IMG" ] || die "$IMG not found"
SUMS=${IMG%.img}.sha256
[ -f "$SUMS" ] || die "$SUMS not found (scripts/installer-image.sh writes it)"
WANT=$(awk -v f="$(basename "$IMG")" '$2==f {print $1}' "$SUMS")
[ -n "$WANT" ] || die "$SUMS has no line for $(basename "$IMG")"
ISIZE=$(stat -c %s "$IMG")
[ "$SIZE" -ge "$ISIZE" ] || die "stick ($SIZE bytes) is smaller than the image ($ISIZE bytes)"
echo "image: $IMG, $ISIZE bytes; checking sha256 against $SUMS ..."
HAVE=$(sha256sum "$IMG" | cut -d' ' -f1)
[ "$HAVE" = "$WANT" ] || die "image sha256 $HAVE does not match $WANT"
echo "image sha256 OK: $HAVE"

# Back up OpenBook reports already on the stick (read-only mount)
for p in $(lsblk -nrpo NAME "$DEV" | tail -n +2); do
  [ "$(lsblk -no LABEL "$p")" = OPENBOOK ] && [ "$(lsblk -no FSTYPE "$p")" = vfat ] || continue
  mp=$(findmnt -nfo TARGET "$p" || true); ours=0
  [ -n "$mp" ] || { udisksctl mount -b "$p" -o ro >/dev/null && mp=$(findmnt -nfo TARGET "$p") && ours=1; }
  if [ -d "$mp/openbook/logs" ]; then
    n=$(find "$mp/openbook/logs" -type f | wc -l)
    echo "reports on $p: $n file(s) in openbook/logs/"
    if [ $DRY = 0 ] && [ "$n" -gt 0 ]; then
      B=$A/installer/stick-backup/$TS; mkdir -p "$B"; cp -r "$mp/openbook/logs" "$B/"
      echo "backed up to $B"
    fi
  fi
  [ $ours = 0 ] || udisksctl unmount -b "$p" >/dev/null || true
done
if [ $DRY = 1 ]; then echo "dry run: nothing written"; exit 0; fi

# Unmount everything on the stick, then write it from a container that gets only this device
for p in $(lsblk -nrpo NAME "$DEV" | tail -n +2); do
  if findmnt -n "$p" >/dev/null; then udisksctl unmount -b "$p" >/dev/null || die "cannot unmount $p"; fi
done
lsblk -nrpo NAME,MOUNTPOINTS "$DEV" | awk 'NF>1' | grep -q . && die "something on $DEV is still mounted"
echo "writing $ISIZE bytes to $DEV ..."
T0=$(date +%s)
docker run --rm --device "$DEV:/dev/openbook-target" -v "$(dirname "$(realpath "$IMG")"):/img:ro" "$IMAGE" \
  sh -c "dd if=/img/$(basename "$IMG") of=/dev/openbook-target bs=4M iflag=fullblock oflag=direct conv=fsync status=progress && sync"
T1=$(date +%s)
echo "written in $((T1 - T0)) s; reading it back ..."
BACK=$(docker run --rm --device "$DEV:/dev/openbook-target" "$IMAGE" \
  sh -c "dd if=/dev/openbook-target bs=1M count=$((ISIZE / 1048576)) iflag=direct status=none | sha256sum" | cut -d' ' -f1)
T2=$(date +%s)
[ "$BACK" = "$WANT" ] || { echo "VERIFY FAILED: read back $BACK, image $WANT"; exit 1; }
echo "verified in $((T2 - T1)) s: the stick's first $ISIZE bytes match sha256 $WANT"
udisksctl power-off -b "$DEV" >/dev/null 2>&1 && echo "stick powered off: safe to unplug" || echo "unplug the stick when its light stops"
sed -E "s#(usb-[A-Za-z0-9_]+_)[A-Za-z0-9]{6,}(-0:0)#\1[redacted]\2#g" "$LOG" > "${LOG%.log}-redacted.log"
echo "log: $LOG"
