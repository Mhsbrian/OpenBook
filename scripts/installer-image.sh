#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Build the OpenBook live USB image (ANAL-190; docs/installer.md section 11) from our own builds:
#   1. snapshot the product's images from PRODUCT_OUT (reflinks, under the AOSP lane lock, so it waits for a running
#      build and no build starts during it), or reuse a snapshot with --inputs;
#   2. build openbook-live-init (scripts/installer/live-init.c) and run its host test;
#   3. assemble the image with scripts/installer/mklive.py in the openbook-installer container: GPT, systemd-boot,
#      slot A, super re-packed to its content, blank metadata/userdata, firmware licences from the vendor image;
#   4. write <label>.img, .img.json (layout, bootconfig, hashes), .img.xz, .sha256 and <label>.build.json (size,
#      sha256, build time, inputs, tool versions, repo commit), plus <label>.vm/ (the QEMU-only test entries).
# Image files only: nothing here touches a disk. Writing a stick is scripts/installer/write-stick.sh, which needs
# the owner's confirmation naming the /dev/disk/by-id/... device.
#
# usage: installer-image.sh [--product-out DIR | --inputs DIR] [--label NAME] [--menu-timeout T]
#                           [--userdata-mib N] [--epoch S] [--out DIR] [--no-xz]
#   default product: <data dir>/aosp/src/out/target/product/anybook_g14 (anybook_g14_x86_64-cp2a-userdebug)
#   default label:   openbook-live-<build id>-<UTC date>
#   --epoch:         timestamps inside the image (default: this repo's HEAD commit time), so the same inputs and
#                    label give the same image, byte for byte
# Output: --out DIR (default <data dir>/installer/out/, which must be below <data dir>/installer); log: <data dir>/logs/installer/live-<label>-<UTC>.log
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}   # data dir: ~/anybook until the repo-wide rename
R=$(cd "$(dirname "$0")/.." && pwd)
S=$R/scripts/installer; D=$S/inst-docker.sh
P=$A/aosp/src/out/target/product/anybook_g14
IN=; LABEL=; MENU=menu-hidden; UD=1024; XZ=1; EPOCH=; O=$A/installer/out
while [ $# -gt 0 ]; do
  case $1 in
    --product-out) P=$2; shift 2 ;;
    --inputs) IN=$2; shift 2 ;;
    --label) LABEL=$2; shift 2 ;;
    --menu-timeout) MENU=$2; shift 2 ;;
    --userdata-mib) UD=$2; shift 2 ;;
    --epoch) EPOCH=$2; shift 2 ;;
    --out) O=$(realpath -m "$2"); shift 2 ;;
    --no-xz) XZ=0; shift ;;
    -h|--help) sed -n '3,23p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
EPOCH=${EPOCH:-${SOURCE_DATE_EPOCH:-$(git -C "$R" log -1 --format=%ct)}}
case $O/ in "$A/installer/"*) ;; *) echo "--out must be below $A/installer (the container writes there)" >&2; exit 2 ;; esac
if [ -z "$IN" ]; then
  for f in boot.img init_boot.img vendor_boot.img vbmeta.img super.img system/build.prop; do
    [ -f "$P/$f" ] || { echo "$P/$f missing: build the product first (docs/g14-product.md)" >&2; exit 1; }
  done
  BID=$(sed -n 's/^ro.build.id=//p' "$P/system/build.prop" | head -1)
  LABEL=${LABEL:-openbook-live-${BID:-unknown}-$(date -u +%Y%m%d)}
else
  [ -f "$IN/provenance.txt" ] || { echo "$IN is not a snapshot (no provenance.txt)" >&2; exit 1; }
  LABEL=${LABEL:-openbook-live-$(basename "$IN")}
fi
case $LABEL in *[!A-Za-z0-9._-]*) echo "label: letters, digits, . _ - only" >&2; exit 2 ;; esac
mkdir -p "$O" "$A/logs/installer" "$A/installer/build" "$A/installer/work"
LOG=$A/logs/installer/live-$LABEL-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee -a "$LOG") 2>&1
T0=$(date +%s)
echo "== installer-image.sh $LABEL ($(date -u +%FT%TZ)), repo $(git -C "$R" rev-parse --short HEAD)$(git -C "$R" diff --quiet HEAD -- scripts tools || echo '+dirty'), epoch $EPOCH"

# 1. snapshot
if [ -z "$IN" ]; then
  # Hold the AOSP lane lock that builds run under (scripts/aosp-build.sh), so no build starts writing PRODUCT_OUT
  # during the snapshot: wait for a running build, up to OPENBOOK_LANE_WAIT seconds (default 2 h). A caller that
  # already holds the lock sets OPENBOOK_LANE_LOCK_HELD=1 (taking it again from here would wait for ever).
  if [ "${OPENBOOK_LANE_LOCK_HELD:-0}" != 1 ]; then
    exec {LFD}>>"$A/aosp/.lane.lock"
    if ! flock -n "$LFD"; then
      echo "waiting for the AOSP lane lock ($A/aosp/.lane.lock): a build is running" >&2
      flock -w "${OPENBOOK_LANE_WAIT:-7200}" "$LFD" || { echo "no AOSP lane lock after ${OPENBOOK_LANE_WAIT:-7200} s" >&2; exit 1; }
    fi
  fi
  # A build started without the lock: lanes name their containers anybook-aosp-build or anybook-aosp-build-<issue>.
  b=$(docker ps --format '{{.Names}}' | grep -E '^anybook-aosp-build(-|$)' | head -1 || true)
  if [ -n "$b" ]; then
    echo "an AOSP build ($b) is running without the lane lock; PRODUCT_OUT may be half-written. Try later." >&2; exit 1
  fi
  IN=$A/installer/inputs/$LABEL
  rm -rf "$IN"; mkdir -p "$IN"
  for f in boot.img init_boot.img vendor_boot.img vbmeta.img super.img android-info.txt; do
    cp --reflink=auto --preserve=timestamps "$P/$f" "$IN/"
  done
  cp --reflink=auto --preserve=timestamps "$P"/build_fingerprint*.txt "$IN/" 2>/dev/null || true
  {
    echo "snapshot: $(date -u +%FT%TZ)"; echo "product_out: $P"
    sed -n 's/^ro.build.fingerprint=/fingerprint: /p' "$P/system/build.prop"
    sed -n 's/^ro.vendor.build.fingerprint=/vendor fingerprint: /p' "$P/vendor/build.prop" 2>/dev/null || true
    K=$A/aosp/src/vendor/anybook/g14-kernel/PROVENANCE.txt
    [ -f "$K" ] && sed 's/^/kernel: /' "$K"
    (cd "$IN" && sha256sum boot.img init_boot.img vendor_boot.img vbmeta.img super.img)
  } > "$IN/provenance.txt"
  echo "snapshot: $IN"
  [ "${OPENBOOK_LANE_LOCK_HELD:-0}" = 1 ] || exec {LFD}>&-  # releases the lane lock
fi
cat "$IN/provenance.txt"
T1=$(date +%s)

# 2. openbook-live-init, and its host test
B=$A/installer/build/openbook-live-init
"$D" gcc -static -O2 -Wall -Wextra -Wno-format-truncation -Wno-sign-compare -o "$B" "$S/live-init.c"
"$S/live-init-test.sh" "$B"

# 3. image
W=$A/installer/work/$LABEL
FWM=$A/aosp/src/vendor/anybook/g14-kernel/firmware/firmware-manifest.tsv
T2=$(date +%s)
"$D" env SOURCE_DATE_EPOCH="$EPOCH" python3 "$S/mklive.py" --inputs "$IN" --live-init "$B" --work "$W" \
  --out "$O/$LABEL.img" --label "$LABEL" --menu-timeout "$MENU" --userdata-mib "$UD" --epoch "$EPOCH" \
  --vm-bundle "$O/$LABEL.vm" --provenance "$IN/provenance.txt" $( [ -f "$FWM" ] && echo --firmware-manifest "$FWM" )
rm -rf "$W"
T3=$(date +%s)

# 4. checksums, xz, build record
cd "$O"
sha256sum "$LABEL.img" > "$LABEL.sha256"
if [ $XZ = 1 ]; then
  rm -f "$LABEL.img.xz"
  xz -T0 -6 -k "$LABEL.img"
  sha256sum "$LABEL.img.xz" >> "$LABEL.sha256"
fi
T4=$(date +%s)
TOOLS=$("$D" bash -c 'pacman -Q gcc glibc systemd dosfstools mtools gptfdisk python | tr "\n" ";"')
python3 - "$O/$LABEL" "$IN" "$R" "$T0" "$T1" "$T2" "$T3" "$T4" "$TOOLS" "$LOG" <<'EOF'
import hashlib, json, os, subprocess, sys
base, inp, repo, t0, t1, t2, t3, t4, tools, log = sys.argv[1:]
t0, t1, t2, t3, t4 = map(int, (t0, t1, t2, t3, t4))
meta = json.load(open(base + ".img.json"))
sums = dict(reversed(l.split()) for l in open(base + ".sha256"))
git = lambda *a: subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout.strip()
rec = {
    "schema": "openbook-live-build/1",
    "label": meta["label"], "image": os.path.basename(base) + ".img",
    "bytes": os.path.getsize(base + ".img"), "sha256": sums[os.path.basename(base) + ".img"],
    "xz_bytes": os.path.getsize(base + ".img.xz") if os.path.exists(base + ".img.xz") else None,
    "xz_sha256": sums.get(os.path.basename(base) + ".img.xz"),
    "allocated_bytes": os.stat(base + ".img").st_blocks * 512,
    "build_seconds": {"total": t4 - t0, "snapshot": t1 - t0, "live_init_and_test": t2 - t1, "image": t3 - t2,
                      "checksums_and_xz": t4 - t3},
    "fingerprint": meta["fingerprint"], "kernel_release": meta["kernel_release"], "loader": meta["loader"],
    "menu_timeout": meta["menu_timeout"], "epoch": meta["epoch"],
    "super": {k: meta["super"][k] for k in ("original_bytes", "live_bytes", "virtual_ab")},
    "firmware": meta["firmware"],
    "inputs": {l.split()[1]: l.split()[0] for l in open(f"{inp}/provenance.txt") if len(l.split()) == 2
               and len(l.split()[0]) == 64},
    "repo": {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain", "--", "scripts", "tools"))},
    "tools": tools.strip(";").split(";"),
    "log": log,
}
json.dump(rec, open(base + ".build.json", "w"), indent=1)
print(json.dumps({k: rec[k] for k in ("image", "bytes", "sha256", "xz_bytes", "xz_sha256", "build_seconds")}, indent=1))
EOF
echo "image: $O/$LABEL.img ($(du -h --apparent-size "$LABEL.img" | cut -f1), $(du -h "$LABEL.img" | cut -f1) allocated)"
echo "log: $LOG"
