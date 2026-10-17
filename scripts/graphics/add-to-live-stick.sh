#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Add the OpenBook graphics check (ANAL-177, scripts/graphics/make-gfx-check.sh) to an OpenBook live USB stick, or
# take it off again. Writes only the stick's FAT partition labelled OPENBOOK, and only new files: openbook/gfx/ and
# loader/entries/openbook-gfx.conf. The live image's own files are never replaced, so the stick keeps booting OpenBook
# exactly as before; the check's entry appears after the normal ones (and after the power check's) in the boot menu.
#
# The entry is made from the stick's own "save logs" entry (loader/entries/openbook-logs.conf): the same kernel,
# ramdisks and bootconfig, plus openbook/gfx/gfx-init.img before the bootconfig, rdinit=/openbook-gfx-init, and
# androidboot.openbook.addon=gfx (run the payload once Android is up), addon_timeout=5400 and logs_settle=90.
#
# Refuses unless DISK is a /dev/disk/by-id/usb-* path (the owner names the exact stick), the disk has a FAT
# partition labelled OPENBOOK, that partition holds every file the add-on's EXPECT lists (an OpenBook live stick with a
# "save logs" entry), no add-on file would overwrite a live-image file, and there is room. Copies are checked against
# the add-on's MANIFEST.sha256. No root needed (udisks).
#
# usage: add-to-live-stick.sh /dev/disk/by-id/usb-<stick> ADDON_DIR
#        add-to-live-stick.sh --remove /dev/disk/by-id/usb-<stick>
#        add-to-live-stick.sh --image IMG ADDON_DIR [--template ENTRY] [--quick] [--default]
#             an image file, through mtools (tests, never a disk). --template: the entry to derive from (default
#             openbook-logs.conf; the QEMU test uses the VM bundle's console entry openbook-vm-logs.conf); --quick: 40
#             cases per list (openbook.gfx_quick=1); --default: make the check the default entry, no menu timeout
set -euo pipefail
MODE=stick; [ "${1:-}" = --remove ] && { MODE=remove; shift; }; [ "${1:-}" = --image ] && { MODE=image; shift; }
TARGET=${1:?usage: add-to-live-stick.sh [--remove|--image] /dev/disk/by-id/usb-<stick>|IMG [ADDON_DIR]}
U=${2:-}; shift $(( $# < 2 ? $# : 2 ))
TEMPLATE=openbook-logs.conf; QUICK=0; DEFAULT=0
while [ $# -gt 0 ]; do
  case $1 in --template) TEMPLATE=$2; shift 2 ;; --quick) QUICK=1; shift ;; --default) DEFAULT=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;; esac
done
[ "$MODE" = image ] || [ "$TEMPLATE$QUICK$DEFAULT" = openbook-logs.conf00 ] ||
  { echo "--template, --quick and --default are for --image (tests) only" >&2; exit 2; }
[ "$MODE" = remove ] || [ -d "$U" ] || { echo "add-on directory $U not found" >&2; exit 2; }
ENTRY=loader/entries/openbook-gfx.conf

check_bundle() {  # the add-on itself: only openbook/gfx/
  (cd "$U" && find openbook -type f) | while read -r f; do
    case $f in openbook/gfx/*) ;; *) echo "refusing: the add-on would write $f, outside openbook/gfx/" >&2; exit 2 ;; esac
  done
  [ -f "$U/openbook/gfx/payload" ] && [ -f "$U/openbook/gfx/gfx-init.img" ] || { echo "refusing: $U is incomplete" >&2; exit 2; }
}

# make_entry TEMPLATE_FILE OUT_FILE: the check's entry from the stick's own "save logs" entry
make_entry() {
  awk -v quick="$QUICK" '
    /^title / { print "title OpenBook graphics check (about 30 min, then powers off)"; next }
    /^sort-key / { print "sort-key openbook-95"; next }
    /^initrd .*bootconfig/ { print "initrd /openbook/gfx/gfx-init.img"; ins = 1 }
    /^options / {
      if (sub(/rdinit=\/openbook-live-init/, "rdinit=/openbook-gfx-init")) rd = 1
      $0 = $0 " androidboot.openbook.addon=gfx androidboot.openbook.addon_timeout=5400 androidboot.openbook.logs_settle=90"
      if (quick == 1) $0 = $0 " openbook.gfx_quick=1"
    }
    { print }
    END { if (!ins || !rd) exit 3 }' "$1" > "$2" ||
    { echo "refusing: $TEMPLATE is not an OpenBook live entry (no bootconfig initrd or rdinit=/openbook-live-init)" >&2; exit 2; }
}

T=$(mktemp -d); trap 'rm -rf "$T"' EXIT

if [ "$MODE" = image ]; then  # image file: mtools, the ESP at 1 MiB as in every OpenBook image
  [ -f "$TARGET" ] && [ ! -b "$TARGET" ] || { echo "refusing: $TARGET is not a regular image file" >&2; exit 2; }
  check_bundle
  E="$TARGET@@1M"
  while read -r f; do mtype -i "$E" "::/$f" >/dev/null 2>&1 || { echo "refusing: $f missing: not an OpenBook live image" >&2; exit 2; }; done < "$U/EXPECT"
  mtype -i "$E" "::/loader/entries/$TEMPLATE" > "$T/template.conf" || { echo "refusing: no $TEMPLATE" >&2; exit 2; }
  make_entry "$T/template.conf" "$T/openbook-gfx.conf"
  mmd -i "$E" ::/openbook/gfx 2>/dev/null || true
  (cd "$U" && find openbook -type f | sort) | while read -r f; do mcopy -o -i "$E" "$U/$f" "::/$f"; done
  mcopy -o -i "$E" "$T/openbook-gfx.conf" "::/$ENTRY"
  if [ "$DEFAULT" = 1 ]; then
    printf 'timeout 0\ndefault openbook-gfx.conf\nconsole-mode keep\neditor no\n' > "$T/loader.conf"
    mcopy -o -i "$E" "$T/loader.conf" ::/loader/loader.conf
  fi
  while read -r sum f; do mcopy -o -i "$E" "::/$f" "$T/x" && echo "$sum  $T/x" | sha256sum -c --quiet - \
    || { echo "verify failed: $f" >&2; exit 1; }; done < "$U/MANIFEST.sha256"
  echo "added $(wc -l < "$U/MANIFEST.sha256") file(s) and $ENTRY to $TARGET and verified them"; cat "$T/openbook-gfx.conf"
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
finish() { sync; [ $OURS = 0 ] || udisksctl unmount -b "$PART" >/dev/null; rm -rf "$T"; }
trap finish EXIT
[ -f "$MP/loader/entries/openbook-live.conf" ] || { echo "refusing: $MP is not an OpenBook live stick" >&2; exit 2; }

if [ "$MODE" = remove ]; then
  rm -f "$MP/$ENTRY"
  rm -rf "$MP/openbook/gfx"
  echo "removed the graphics check from $PART; the live entries are untouched (results stay in openbook/logs/)"
  exit 0
fi
check_bundle
while read -r f; do [ -e "$MP/$f" ] || { echo "refusing: $f missing: not an OpenBook live stick" >&2; exit 2; }; done < "$U/EXPECT"
make_entry "$MP/loader/entries/$TEMPLATE" "$T/openbook-gfx.conf"
# Room for the add-on, and 48 MiB to spare for the run's results (at most 32 MiB, usually a few) and the boot's logs (live-init needs
# 24 MiB free for its capture).
NEED=$(du -sk "$U/openbook/gfx" | cut -f1); FREE=$(df -k --output=avail "$MP" | tail -n 1 | tr -d ' ')
OLD=$( [ -d "$MP/openbook/gfx" ] && du -sk "$MP/openbook/gfx" | cut -f1 || echo 0)
if [ $((FREE + OLD)) -lt $((NEED + 49152)) ]; then
  echo "refusing: $((FREE + OLD)) KiB free, $NEED KiB needed plus 48 MiB for results and logs." >&2
  echo "  Make room first: copy old logs off (scripts/installer/read-stick-logs.sh) and delete openbook/logs/live-*" >&2
  echo "  and hwcheck-* on the stick, or take the power check off after its run" >&2
  echo "  (scripts/power/add-to-live-stick.sh --remove $TARGET), or build the add-on without the two test apps" >&2
  echo "  (GFX_APPS=0 scripts/graphics/make-gfx-check.sh: no EGL or ANGLE end2end part, about 40 MB smaller)." >&2
  exit 2
fi
mkdir -p "$MP/openbook/gfx"
(cd "$U" && find openbook -type f | sort) | while read -r f; do cp "$U/$f" "$MP/$f"; done
cp "$T/openbook-gfx.conf" "$MP/$ENTRY"
sync
(cd "$MP" && sha256sum -c "$U/MANIFEST.sha256")
cmp "$T/openbook-gfx.conf" "$MP/$ENTRY"
echo "added the graphics check to $PART; unmounting. Boot the laptop from the stick, plugged in, and pick"
echo "\"OpenBook graphics check\"; it powers off by itself when done (about 30 minutes)."
