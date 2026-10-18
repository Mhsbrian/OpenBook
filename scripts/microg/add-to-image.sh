#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Put the microG add-on (make-addon.sh) on an OpenBook live IMAGE FILE, or take it off again, through mtools.
# Image files only: it refuses block devices, so it never writes a disk or a stick. An owner stick is built as an
# image and written with scripts/installer/write-stick.sh, which names the exact device (ANAL-192).
# Writes only openbook/addons/microg/ on the image's EFI partition (at 1 MiB, as in every OpenBook image). The image's
# own files are never replaced, so it boots exactly as before; openbook-addons installs microG on its first start.
#
# usage: add-to-image.sh IMG ADDON_DIR
#        add-to-image.sh --remove IMG
# Needs mtools (scripts/installer/inst-docker.sh has them).
set -euo pipefail
REMOVE=0; [ "${1:-}" = --remove ] && { REMOVE=1; shift; }
IMG=${1:?usage: add-to-image.sh [--remove] IMG [ADDON_DIR]}; U=${2:-}
[ -f "$IMG" ] && [ ! -b "$IMG" ] || { echo "refusing: $IMG is not a regular image file" >&2; exit 2; }
E="$IMG@@1M"; D=openbook/addons/microg
mtype -i "$E" ::/openbook/MANIFEST.json >/dev/null 2>&1 || { echo "refusing: $IMG is not an OpenBook image" >&2; exit 2; }
if [ $REMOVE = 1 ]; then
  if mdir -i "$E" "::/$D" >/dev/null 2>&1; then mdeltree -i "$E" "::/$D"; echo "removed $D from $IMG"; else echo "$IMG has no $D"; fi
  exit 0
fi
[ -d "$U/$D" ] && [ -f "$U/MANIFEST.sha256" ] && [ -f "$U/EXPECT" ] ||
  { echo "refusing: $U is not a make-addon.sh add-on" >&2; exit 2; }
(cd "$U" && find . -type f ! -name MANIFEST.sha256 ! -name EXPECT | sed 's|^\./||') | while read -r f; do
  case $f in "$D"/*) ;; *) echo "refusing: the add-on would write $f, outside $D/" >&2; exit 2 ;; esac
done
while read -r f; do mtype -i "$E" "::/$f" >/dev/null 2>&1 || { echo "refusing: $f missing: not an OpenBook live image" >&2; exit 2; }; done < "$U/EXPECT"
NEED=$(du -sb "$U/$D" | cut -f1)
OLD=$(mdu -i "$E" -s "::/$D" 2>/dev/null | awk '{print $2 * 512}' || echo 0)
FREE=$(mdir -i "$E" ::/ | sed -n 's/^ *\([0-9 ]*\) bytes free$/\1/p' | tr -d ' ')
[ -n "$FREE" ] && [ $((FREE + ${OLD:-0})) -gt $((NEED + 4194304)) ] ||
  { echo "refusing: the EFI partition has $((${FREE:-0} / 1048576)) MiB free, the add-on needs $((NEED / 1048576)) MiB" \
      "plus 4 MiB (take a check add-on off first)" >&2; exit 2; }
mmd -i "$E" ::/openbook/addons 2>/dev/null || true
mmd -i "$E" "::/$D" 2>/dev/null || true
(cd "$U" && find "$D" -type f | sort) | while read -r f; do mcopy -o -i "$E" "$U/$f" "::/$f"; done
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
while read -r sum f; do mcopy -o -i "$E" "::/$f" "$T/x" && echo "$sum  $T/x" | sha256sum -c --quiet - \
  || { echo "verify failed: $f" >&2; exit 1; }; done < "$U/MANIFEST.sha256"
echo "added $(wc -l < "$U/MANIFEST.sha256") file(s) ($((NEED / 1048576)) MiB) to $IMG and verified them;" \
  "$((FREE / 1048576 - NEED / 1048576)) MiB left on its EFI partition"
