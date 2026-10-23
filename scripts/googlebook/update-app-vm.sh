#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# OpenBook Update on the real Ruby image, in QEMU (ANAL-229). Regular image files only; no device.
#   1. build-update-app-candidate.py --vm-check  on a reviewed base (default RB-20261023-02, 75fa0196…)
#   2. stage-base.py, build-ruby-ab-super.py, build-ruby-ab-image.py --vm   the two-slot disk
#   3. ab-qemu.py (TCG): boot checks, the serial report of the disposable check service (OBU_* lines),
#      a screenshot when the app is on screen
#   4. update-app-vm-judge.py: installed as a privileged app for the owner (not the headless system user),
#      in its own domain, REBOOT and notifications granted, update_engine watched, a check ran, no
#      denials or crashes for it
# usage: update-app-vm.sh WORK APK [BASE_DIR BASE_SHA256]     (WORK under ~/anybook/installer/work)
# A rerun on the same WORK resumes: finished steps (their result files exist) are kept.
set -euo pipefail
W=$1; APK=$(realpath "$2")
BASE=${3:-$HOME/anybook/installer/work/anal229-updater-p2/base}
BASE_SHA=${4:-75fa0196090558519fbb33d079ed51e2b9fd86ee102013c089bc8e9122fe9391}
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../.." && pwd)
AOSP=${AOSP_HOST:-$HOME/anybook/aosp/src/out/host/linux-x86}
OTATOOLS=${OTATOOLS:-$HOME/anybook/ota/builds/openbook-ota-20261019-quire1/otatools}
INV=${EROFS_INVENTORY:-$HOME/anybook/installer/work/anal228-input27/erofs-inventory}
KEY=${AVB_KEY:-$HOME/anybook/aosp/src/external/avb/test/data/testkey_rsa4096.pem}
REF_SUPER=${REF_SUPER:-$HOME/anybook/work/gbos-ruby/parts/super.img}
# TCG with the GFNI/VNNI-emulating QEMU build: Google's Ruby build uses instructions a Zen 4 host lacks
# (zygote dies with SIGILL under KVM there); ACCEL=kvm with QEMU=/usr/sbin/qemu-system-x86_64 on a host
# CPU that has them.
QEMU=${QEMU:-$HOME/anybook/installer/work/anal228-tcg/build/qemu-system-x86_64}
ACCEL=${ACCEL:-tcg}
BOOTSYNC=${BOOTSYNC:-$HOME/anybook/installer/build/openbook-bootsync-host}
run() { "$REPO/scripts/installer/inst-docker.sh" "$@"; }
mkdir -p -m 700 "$W"; W=$(realpath "$W")
if [ ! -d "$W/lp" ]; then
  mkdir -m 700 "$W/lp"
  ln -s "$AOSP/bin/lpdump" "$W/lp/lpdump"; ln -s "$AOSP/bin/lpmake" "$W/lp/lpmake"; ln -s "$OTATOOLS/bin/lpunpack" "$W/lp/lpunpack"
fi
# A step left unfinished by an earlier run is redone from scratch.
step() { [ -f "$W/$1" ] && return 1; rm -rf "$W/${1%%/*}"; }
if step candidate/manifest.json; then
  run python3 "$HERE/build-update-app-candidate.py" --base "$BASE" --base-sha256 "$BASE_SHA" --tools "$AOSP/bin" \
    --inventory "$INV" --key "$KEY" --apk "$APK" --out "$W/candidate" --vm-check > "$W/candidate.log" 2>&1
fi
sha=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image_sha256"])' "$W/candidate/manifest.json")
if step staged/manifest.json; then
  run python3 "$HERE/stage-base.py" --source "$W/candidate" --source-sha256 "$sha" --tools "$OTATOOLS/bin" \
    --out "$W/staged" > "$W/stage.log" 2>&1
fi
if step super/result.json; then
  run env LD_LIBRARY_PATH="$AOSP/lib64:$OTATOOLS/lib64" python3 "$HERE/build-ruby-ab-super.py" --logical "$W/staged/logical" \
    --reference-super "$REF_SUPER" --tools "$W/lp" --super-bytes 25769803776 --out "$W/super" > "$W/super.log" 2>&1
fi
# 40 GiB (sparse): the two-slot system leaves Android its 8 GiB minimum of userdata.
if step img/result.json; then
  run python3 "$HERE/build-ruby-ab-image.py" --candidate "$W/candidate" --super-img "$W/super/super.img" --tools "$AOSP/bin" \
    --key "$KEY" --out "$W/img" --disk-bytes 42949672960 --vm > "$W/img.log" 2>&1
fi
rm -rf "$W/vm"
run python3 "$HERE/ab-qemu.py" --image-dir "$W/img" --qemu "$QEMU" --bootsync "$BOOTSYNC" --out "$W/vm" \
  --accel "$ACCEL" --seconds "${VM_SECONDS:-2400}" --screenshot-on OBU_SCREEN_READY > "$W/vm.log" 2>&1 || true
python3 "$HERE/update-app-vm-judge.py" "$W"
