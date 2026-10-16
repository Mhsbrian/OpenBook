#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copy the reports an OpenBook stick collected (openbook/logs/ on its FAT partition labelled OPENBOOK) to the dev
# host, read-only (ANAL-190). Then summarise every live-NNN/ folder the "save logs" entry wrote, with
# scripts/installer/live-report.py (report.md and report.json next to the files).
# Read-only: the partition is mounted read-only through udisks (or read where it is already mounted), and
# unmounted again if this script mounted it. Nothing on the stick changes.
#
# usage: read-stick-logs.sh /dev/disk/by-id/usb-<stick> [DEST]     DEST default <data dir>/installer/g14/stick-<UTC>
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
DISK=${1:?usage: read-stick-logs.sh /dev/disk/by-id/usb-<stick> [DEST]}
DEST=${2:-$A/installer/g14/stick-$(date -u +%Y%m%dT%H%M%SZ)}
case "$DISK" in /dev/disk/by-id/usb-*) ;; *) echo "refusing: $DISK is not a /dev/disk/by-id/usb-* path" >&2; exit 2 ;; esac
[ -b "$DISK" ] || { echo "$DISK does not exist (is the stick plugged in?)" >&2; exit 2; }
DEV=$(readlink -f "$DISK")
PART=$(lsblk -nrpo NAME,LABEL,FSTYPE "$DEV" | awk '$2=="OPENBOOK" && $3=="vfat" {print $1}' | head -n 1)
[ -n "$PART" ] || { echo "no FAT partition labelled OPENBOOK on $DEV" >&2; exit 2; }
MP=$(findmnt -nfo TARGET "$PART" || true); OURS=0
[ -n "$MP" ] || { udisksctl mount -b "$PART" -o ro >/dev/null; MP=$(findmnt -nfo TARGET "$PART"); OURS=1; }
mkdir -p "$DEST"
if [ -d "$MP/openbook/logs" ]; then cp -r "$MP/openbook/logs/." "$DEST/"; fi
for f in openbook/MANIFEST.json openbook/PROVENANCE.txt loader/loader.conf; do
  [ -f "$MP/$f" ] && cp "$MP/$f" "$DEST/stick-$(basename "$f")"
done
[ $OURS = 0 ] || udisksctl unmount -b "$PART" >/dev/null
echo "copied $(find "$DEST" -type f | wc -l) file(s) from $PART to $DEST$([ $OURS = 1 ] && echo '; unmounted')"
for d in "$DEST"/live-[0-9][0-9][0-9]; do
  [ -d "$d" ] && python3 "$R/scripts/installer/live-report.py" "$d" | head -n 40
done
