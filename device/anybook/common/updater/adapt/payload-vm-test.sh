#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Phase 4 in the VM (ANAL-229): a payload written by openbook-adapt (not delta_generator) installed by the
# real update_engine of a Ruby system in QEMU. The VM's slot A is the apply harness (RB-20261023-02 plus a
# disposable apply driver); the payload installs an adapted release into slot B, then the suite boots slot
# B, merges, compares the slot byte for byte with the release, and checks the fallback with a broken slot.
# Regular image files only; no device. Holds the Ruby release lock for the whole chain.
#
# usage: payload-vm-test.sh WORK ADAPTED_DIR
#   ADAPTED_DIR  an adapt --out directory (system, system_ext, product, vbmeta and adapt.json)
# env: ADAPT (the openbook-adapt host build), OTAKEY/OTACERT (the OpenBook OTA key on this host, never
#      copied), plus ab-ota-suite.sh's.
set -euo pipefail
W=$1 ADAPTED=$(realpath "$2")
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../../../../.." && pwd); G=$REPO/scripts/googlebook
exec 9<>"$HOME/anybook/installer/.ruby-release.lock"
flock -n 9 || { echo "the Ruby release lock is held by another build"; exit 75; }
AOSP=$HOME/anybook/aosp/src/out/host/linux-x86
OTATOOLS=$HOME/anybook/ota/builds/openbook-ota-20261019-quire1/otatools
AVBKEY=$HOME/anybook/aosp/src/external/avb/test/data/testkey_rsa4096.pem
REF_SUPER=$HOME/anybook/work/gbos-ruby/parts/super.img
HARN=$HOME/anybook/installer/work/anal229-ota-test/harness
HARN_SHA=f2a51087fde25580b95f3a41b09ac39615f614f9b3bac286ba2bb41a5e7e9fe5
GOOGLE=$HOME/anybook/private/google-ota/stock-16658739
OTAKEY=${OTAKEY:-$HOME/.local/share/openbook-keys/ota/openbook-ota-2026.key}
OTACERT=${OTACERT:-$REPO/config/security/openbook-ota-2026.x509.pem}
ADAPT=${ADAPT:?set ADAPT to the openbook-adapt binary (a host build)}
VM_BYTES=42949672960
export QEMU=$HOME/anybook/installer/work/anal228-tcg/build/qemu-system-x86_64
export BOOTSYNC=$HOME/anybook/installer/build/openbook-bootsync-host
export AOSP_HOST=$AOSP OTATOOLS
STATIC="boot init_boot vendor_boot vbmeta"
LOGICAL="system system_ext product vendor vendor_dlkm system_dlkm"
mkdir -p -m 700 "$W" "$W/logs"
L=$W/logs
note() { echo "$(date -u +%FT%TZ) $*" | tee -a "$L/progress.txt"; }
run() { "$REPO/scripts/installer/inst-docker.sh" "$@"; }
mshaf() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image_sha256"])' "$1"; }
[ "$(sha256sum "$HARN/ruby-live.img" | cut -d' ' -f1)" = "$HARN_SHA" ] || { note "FAIL harness differs from its pin"; exit 1; }
free=$(df -B1G --output=avail "$W" | tail -1 | tr -d ' ')
note "free ${free} GiB (budget 60 GiB plus the 40 GiB reserve)"
[ "$free" -ge 100 ] || { note "FAIL storage"; exit 1; }

# 1. The harness disk and its release images (as rb03-build.sh builds them).
if [ ! -f "$W/rel-h/SHA256SUMS" ]; then
  [ -f "$W/staged-h/manifest.json" ] || run python3 "$G/stage-base.py" --source "$HARN" --source-sha256 "$HARN_SHA" \
      --tools "$OTATOOLS/bin" --out "$W/staged-h" > "$L/staged-h.log" 2>&1
  mkdir -p -m 700 "$W/lp"; ln -sf "$AOSP/bin/lpdump" "$W/lp/lpdump"; ln -sf "$AOSP/bin/lpmake" "$W/lp/lpmake"
  ln -sf "$OTATOOLS/bin/lpunpack" "$W/lp/lpunpack"
  [ -f "$W/super-h/result.json" ] || run env LD_LIBRARY_PATH="$AOSP/lib64:$OTATOOLS/lib64" python3 "$G/build-ruby-ab-super.py" \
      --logical "$W/staged-h/logical" --reference-super "$REF_SUPER" --tools "$W/lp" --super-bytes 25769803776 \
      --out "$W/super-h" > "$L/super-h.log" 2>&1
  [ -f "$W/img-h/result.json" ] || run python3 "$G/build-ruby-ab-image.py" --candidate "$HARN" --super-img "$W/super-h/super.img" \
      --tools "$AOSP/bin" --key "$AVBKEY" --out "$W/img-h" --disk-bytes "$VM_BYTES" --vm > "$L/img-h.log" 2>&1
  rm -rf "$W/rel-h"; mkdir -m 700 "$W/rel-h"
  for n in $LOGICAL; do cp --reflink=auto "$W/staged-h/logical/${n}_a.img" "$W/rel-h/$n.img"; done
  for n in $STATIC; do cp --reflink=auto "$W/img-h/${n}_a.img" "$W/rel-h/$n.img"; done
  (cd "$W/rel-h" && sha256sum *.img > SHA256SUMS)
fi
note "harness disk and release images ready"

# 2. The installed release as a layer describes it, and the payload written by openbook-adapt.
rm -rf "$W/layer-h" "$W/layer-h-work"
LD_LIBRARY_PATH=$AOSP/lib64 "$ADAPT" layer --old-system "$GOOGLE/system.img" --old-stock "$GOOGLE" --old-build 16658739 \
  --release-dir "$W/rel-h" --fsck "$AOSP/bin/fsck.erofs" --work "$W/layer-h-work" --out "$W/layer-h" > "$L/layer-h.log" 2>&1
rm -rf "$W/layer-h-work" "$W/payload"
"$ADAPT" payload --adapted "$ADAPTED" --layer "$W/layer-h" --out "$W/payload" --key "$OTAKEY" > "$L/payload.log" 2>&1
python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["properties"]))' "$W/payload/payload.json" \
  > "$W/payload/payload_properties.txt"
openssl x509 -in "$OTACERT" -pubkey -noout > "$W/payload/ota.pub.pem"
LD_LIBRARY_PATH=$AOSP/lib64 "$AOSP/bin/delta_generator" --in_file="$W/payload/payload.bin" \
  --public_key="$W/payload/ota.pub.pem" > "$L/payload-verify.log" 2>&1 || { note "FAIL payload signature"; exit 1; }
note "payload $(sha256sum "$W/payload/payload.bin" | cut -d' ' -f1) ($(stat -c %s "$W/payload/payload.bin") bytes), signature verified"

# 3. The release slot B must hold: the adapted partitions, the rest as installed.
rm -rf "$W/rel-target"; mkdir -m 700 "$W/rel-target"
for n in $LOGICAL $STATIC; do
  if [ -f "$ADAPTED/$n.img" ]; then cp --reflink=auto "$ADAPTED/$n.img" "$W/rel-target/$n.img"
  else cp --reflink=auto "$W/rel-h/$n.img" "$W/rel-target/$n.img"; fi
done

# 4. update_engine in the VM: apply into slot B, boot B and merge, byte compare, fallback.
rm -rf "$W/suite"
"$G/ab-ota-suite.sh" "$W/img-h" "$W/payload" "$W/rel-target" "$W/suite" --fallback > "$L/suite.log" 2>&1 || true
note "suite: $(cat "$W/suite/summary.json" 2>/dev/null | tr -d '\n' | cut -c1-600)"
