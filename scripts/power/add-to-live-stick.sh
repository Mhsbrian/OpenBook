#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Add the OpenBook power check (ANAL-178, scripts/power/make-power-check.sh) to an OpenBook live USB stick, or take
# it off again. Writes only the stick's FAT partition labelled OPENBOOK, and only new files: openbook/check/ and
# loader/entries/openbook-check-*.conf. The live image's own files are never replaced, so the stick keeps booting
# OpenBook exactly as before; the check entries appear after the normal ones in the boot menu.
#
# Refuses unless DISK is a /dev/disk/by-id/usb-* path (the owner names the exact stick), the disk has a FAT
# partition labelled OPENBOOK, that partition holds every file the add-on's EXPECT lists (i.e. it is an OpenBook
# live stick), no add-on file would overwrite a live-image file, and there is room. Copies are checked against the
# add-on's MANIFEST.sha256. No root needed (udisks).
#
# usage: add-to-live-stick.sh /dev/disk/by-id/usb-<stick> ADDON_DIR
#        add-to-live-stick.sh --remove /dev/disk/by-id/usb-<stick>
#        add-to-live-stick.sh --image IMG ADDON_DIR      (an image file, through mtools: tests, never a disk)
set -euo pipefail
MODE=stick; [ "${1:-}" = --remove ] && { MODE=remove; shift; }; [ "${1:-}" = --image ] && { MODE=image; shift; }
TARGET=${1:?usage: add-to-live-stick.sh [--remove|--image] /dev/disk/by-id/usb-<stick>|IMG [ADDON_DIR]}
U=${2:-}
[ "$MODE" = remove ] || [ -d "$U" ] || { echo "add-on directory $U not found" >&2; exit 2; }

check_bundle() {  # the add-on itself: only openbook/check/ and loader/entries/openbook-check-*.conf
  (cd "$U" && find openbook loader -type f) | while read -r f; do
    case $f in openbook/check/*|loader/entries/openbook-check-*.conf) ;;
      *) echo "refusing: the add-on would write $f, outside openbook/check/ and the check entries" >&2; exit 2 ;; esac
  done
}

if [ "$MODE" = image ]; then  # image file: mtools, the ESP at 1 MiB as in every OpenBook image
  [ -f "$TARGET" ] && [ ! -b "$TARGET" ] || { echo "refusing: $TARGET is not a regular image file" >&2; exit 2; }
  check_bundle
  E="$TARGET@@1M"
  while read -r f; do mtype -i "$E" "::/$f" >/dev/null 2>&1 || { echo "refusing: $f missing: not an OpenBook live image" >&2; exit 2; }; done < "$U/EXPECT"
  mmd -i "$E" ::/openbook/check 2>/dev/null || true
  (cd "$U" && find openbook loader -type f | sort) | while read -r f; do mcopy -o -i "$E" "$U/$f" "::/$f"; done
  T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
  while read -r sum f; do mcopy -o -i "$E" "::/$f" "$T/x" && echo "$sum  $T/x" | sha256sum -c --quiet - \
    || { echo "verify failed: $f" >&2; exit 1; }; done < "$U/MANIFEST.sha256"
  echo "added $(wc -l < "$U/MANIFEST.sha256") file(s) to $TARGET and verified them"
  exit 0
fi

case "$TARGET" in /dev/disk/by-id/usb-*) ;; *) echo "refusing: $TARGET is not a /dev/disk/by-id/usb-* path" >&2; exit 2 ;; esac
case "$TARGET" in *-part[0-9]*) echo "refusing: name the whole stick, not a partition" >&2; exit 2 ;; esac
[ -b "$TARGET" ] || { echo "refusing: $TARGET does not exist" >&2; exit 2; }
DEV=$(readlink -f "$TARGET")
PART=$(lsblk -nrpo NAME,LABEL,FSTYPE "$DEV" | awk '$2=="OPENBOOK" && $3=="vfat" {print $1}' | head -n 1)
[ -n "$PART" ] || { echo "refusing: no FAT partition labelled OPENBOOK on $TARGET" >&2; exit 2; }
echo "stick: $TARGET -> $DEV ($(lsblk -dno VENDOR,MODEL,SIZE "$DEV" | xargs)); OPENBOOK partition $PART"
MP=$(findmnt -nfo TARGET "$PART" || true); OURS=0
if [ -n "$MP" ] && findmnt -nfo OPTIONS "$PART" | grep -q '^ro'; then udisksctl unmount -b "$PART" >/dev/null; MP=""; fi
[ -n "$MP" ] || { udisksctl mount -b "$PART" >/dev/null; MP=$(findmnt -nfo TARGET "$PART"); OURS=1; }
finish() { sync; [ $OURS = 0 ] || udisksctl unmount -b "$PART" >/dev/null; }
trap finish EXIT
[ -f "$MP/loader/entries/openbook-live.conf" ] || { echo "refusing: $MP is not an OpenBook live stick" >&2; exit 2; }

if [ "$MODE" = remove ]; then
  rm -f "$MP"/loader/entries/openbook-check-*.conf
  rm -rf "$MP/openbook/check"
  echo "removed the power check from $PART; the live entries are untouched"
  exit 0
fi
check_bundle
while read -r f; do [ -e "$MP/$f" ] || { echo "refusing: $f missing: not an OpenBook live stick" >&2; exit 2; }; done < "$U/EXPECT"
NEED=$(du -sk "$U/openbook/check" | cut -f1); FREE=$(df -k --output=avail "$MP" | tail -n 1 | tr -d ' ')
OLD=$( [ -d "$MP/openbook/check" ] && du -sk "$MP/openbook/check" | cut -f1 || echo 0)
[ $((FREE + OLD)) -gt $((NEED + 4096)) ] || { echo "refusing: $((FREE + OLD)) KiB free, $NEED KiB needed" >&2; exit 2; }
mkdir -p "$MP/openbook/check" "$MP/loader/entries"
(cd "$U" && find openbook loader -type f | sort) | while read -r f; do cp "$U/$f" "$MP/$f"; done
sync
(cd "$MP" && sha256sum -c "$U/MANIFEST.sha256")
echo "added the power check to $PART; unmounting. Boot the laptop from the stick and pick \"OpenBook power check: S0i3\"."
