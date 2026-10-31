#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Put the OpenBook ARM-apps check (ANAL-200, make-bridge-check.sh) on an OpenBook live IMAGE FILE, through mtools.
# Image files only: it refuses block devices, so it never writes a disk or a stick. An integrated owner stick is
# built as an image (ANAL-192) and written with scripts/installer/write-stick.sh, which names the exact device.
# Writes only new files on the image's ESP: openbook/bridge/ and loader/entries/openbook-bridge.conf. The live
# image's own files are never replaced, so it keeps booting OpenBook exactly as before.
#
# The entry is made from the image's own "save logs" entry (loader/entries/openbook-logs.conf): the same kernel,
# ramdisks and bootconfig (SELinux permissive, logs saved to the stick), plus androidboot.openbook.addon=bridge (the
# stick's openbook-live-init runs the payload once Android is up) and addon_timeout=1800.
#
# usage: add-to-image.sh IMG ADDON_DIR [--template ENTRY] [--default]
#   --template: the entry to derive from (default openbook-logs.conf; the QEMU test uses the VM bundle's console
#   entry openbook-vm-logs.conf); --default: make the check the default entry, no menu timeout (QEMU test)
# Needs mtools (scripts/installer/inst-docker.sh has them).
set -euo pipefail
IMG=${1:?usage: add-to-image.sh IMG ADDON_DIR [--template ENTRY] [--default]}; U=${2:?add-on directory}; shift 2
TEMPLATE=openbook-logs.conf; DEFAULT=0
while [ $# -gt 0 ]; do
  case $1 in --template) TEMPLATE=$2; shift 2 ;; --default) DEFAULT=1; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;; esac
done
[ -f "$IMG" ] && [ ! -b "$IMG" ] || { echo "refusing: $IMG is not a regular image file" >&2; exit 2; }
[ -f "$U/openbook/bridge/payload" ] && [ -f "$U/EXPECT" ] && [ -f "$U/MANIFEST.sha256" ] ||
  { echo "refusing: $U is not a make-bridge-check.sh add-on" >&2; exit 2; }
(cd "$U" && find openbook -type f) | while read -r f; do
  case $f in openbook/bridge/*) ;; *) echo "refusing: the add-on would write $f, outside openbook/bridge/" >&2; exit 2 ;; esac
done
ENTRY=loader/entries/openbook-bridge.conf
E="$IMG@@1M"   # the ESP starts at 1 MiB in every OpenBook image
while read -r f; do mtype -i "$E" "::/$f" >/dev/null 2>&1 || { echo "refusing: $f missing: not an OpenBook live image" >&2; exit 2; }; done < "$U/EXPECT"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mtype -i "$E" "::/loader/entries/$TEMPLATE" > "$T/template.conf" || { echo "refusing: no $TEMPLATE" >&2; exit 2; }
awk '
  /^title / { print "title OpenBook ARM apps check (about 10 min, then powers off)"; next }
  /^sort-key / { print "sort-key openbook-96"; next }
  /^options / { if ($0 ~ /rdinit=\/openbook-live-init/) rd = 1
                $0 = $0 " androidboot.openbook.addon=bridge androidboot.openbook.addon_timeout=1800" }
  { print }
  END { if (!rd) exit 3 }' "$T/template.conf" > "$T/openbook-bridge.conf" ||
  { echo "refusing: $TEMPLATE is not an OpenBook live entry (no rdinit=/openbook-live-init)" >&2; exit 2; }
grep -q 'bootconfig-.*logs.*\.img' "$T/openbook-bridge.conf" ||
  { echo "refusing: $TEMPLATE does not boot the \"save logs\" bootconfig" >&2; exit 2; }
mmd -i "$E" ::/openbook/bridge 2>/dev/null || true
(cd "$U" && find openbook -type f | sort) | while read -r f; do mcopy -o -i "$E" "$U/$f" "::/$f"; done
mcopy -o -i "$E" "$T/openbook-bridge.conf" "::/$ENTRY"
if [ "$DEFAULT" = 1 ]; then
  printf 'timeout 0\ndefault openbook-bridge.conf\nconsole-mode keep\neditor no\n' > "$T/loader.conf"
  mcopy -o -i "$E" "$T/loader.conf" ::/loader/loader.conf
fi
while read -r sum f; do mcopy -o -i "$E" "::/$f" "$T/x" && echo "$sum  $T/x" | sha256sum -c --quiet - \
  || { echo "verify failed: $f" >&2; exit 1; }; done < "$U/MANIFEST.sha256"
echo "added $(wc -l < "$U/MANIFEST.sha256") file(s) and $ENTRY to $IMG and verified them"; cat "$T/openbook-bridge.conf"
