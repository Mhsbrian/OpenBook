#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# ANAL-238's vendor dGPU diagnostics and ANAL-257's lab on the real Ruby image, in QEMU. Regular image files only; no device.
#   1. stage-base.py on a reviewed candidate (default RB-20261023-03's candidate C, 71da0228…)
#   2. build-dgpu-diag-candidate.py --check-policy-only, then --vm-check (vendor rebuilt; disposable system report)
#   3. stage-base.py, build-ruby-ab-super.py, build-ruby-ab-image.py --vm   the two-slot disk
#   4. ab-qemu.py (TCG): boot checks and the DGR_* report
#   5. dgpu-vm-judge.py against BASELINE_SERIAL, a fresh boot of the same release without the change
# usage: dgpu-vm.sh WORK [CANDIDATE_DIR CANDIDATE_SHA256 BASELINE_SERIAL]    (WORK under ~/anybook/installer/work)
#        DGPU_VM_BUILD_ONLY=1 stops before the QEMU boot. A rerun on the same WORK resumes finished steps.
#        LAB_MODULE=<openbook_sleep_diag.ko built for the base's kernel> adds it to vendor_dlkm, blocklisted (ANAL-257)
set -euo pipefail
W=$1
CAND=${2:-$HOME/anybook/installer/work/rb-20261023-03/cand-prod}
CAND_SHA=${3:-71da0228488781fa7db6bbb2b07b8559024023b606ae54cd868f780954b9cc24}
BASELINE=${4:-$HOME/anybook/installer/work/rb-20261023-03/appvm/vm/serial.log}
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../.." && pwd)
AOSP=${AOSP_HOST:-$HOME/anybook/aosp/src/out/host/linux-x86}
OTATOOLS=${OTATOOLS:-$HOME/anybook/ota/builds/openbook-ota-20261019-quire1/otatools}
INV=${EROFS_INVENTORY:-$HOME/anybook/installer/work/anal228-input27/erofs-inventory}
KEY=${AVB_KEY:-$HOME/anybook/aosp/src/external/avb/test/data/testkey_rsa4096.pem}
REF_SUPER=${REF_SUPER:-$HOME/anybook/work/gbos-ruby/parts/super.img}
# TCG with the GFNI/VNNI-emulating QEMU build (see update-app-vm.sh).
QEMU=${QEMU:-$HOME/anybook/installer/work/anal228-tcg/build/qemu-system-x86_64}
ACCEL=${ACCEL:-tcg}
BOOTSYNC=${BOOTSYNC:-$HOME/anybook/installer/build/openbook-bootsync-host}
run() { "$REPO/scripts/installer/inst-docker.sh" "$@"; }
mshaf() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["image_sha256"])' "$1"; }
mkdir -p -m 700 "$W"; W=$(realpath "$W")
if [ ! -d "$W/lp" ]; then
  mkdir -m 700 "$W/lp"
  ln -s "$AOSP/bin/lpdump" "$W/lp/lpdump"; ln -s "$AOSP/bin/lpmake" "$W/lp/lpmake"; ln -s "$OTATOOLS/bin/lpunpack" "$W/lp/lpunpack"
fi
step() { [ -f "$W/$1" ] && return 1; rm -rf "$W/${1%%/*}"; }
if step base/manifest.json; then
  run python3 "$HERE/stage-base.py" --source "$CAND" --source-sha256 "$CAND_SHA" --tools "$OTATOOLS/bin" \
    --out "$W/base" > "$W/base.log" 2>&1
fi
common=(--base "$W/base" --base-sha256 "$CAND_SHA" --tools "$AOSP/bin" --inventory "$INV" --key "$KEY")
if step policy-check/policy-check.json; then
  run python3 "$HERE/build-dgpu-diag-candidate.py" "${common[@]}" --out "$W/policy-check" --check-policy-only \
    > "$W/policy-check.log" 2>&1
fi
if step candidate/manifest.json; then
  run python3 "$HERE/build-dgpu-diag-candidate.py" "${common[@]}" --out "$W/candidate" --vm-check \
    ${LAB_MODULE:+--lab-module "$LAB_MODULE"} > "$W/candidate.log" 2>&1
fi
sha=$(mshaf "$W/candidate/manifest.json")
if step staged/manifest.json; then
  run python3 "$HERE/stage-base.py" --source "$W/candidate" --source-sha256 "$sha" --tools "$OTATOOLS/bin" \
    --out "$W/staged" > "$W/stage.log" 2>&1
fi
if step super/result.json; then
  run env LD_LIBRARY_PATH="$AOSP/lib64:$OTATOOLS/lib64" python3 "$HERE/build-ruby-ab-super.py" --logical "$W/staged/logical" \
    --reference-super "$REF_SUPER" --tools "$W/lp" --super-bytes 25769803776 --out "$W/super" > "$W/super.log" 2>&1
fi
if step img/result.json; then
  run python3 "$HERE/build-ruby-ab-image.py" --candidate "$W/candidate" --super-img "$W/super/super.img" --tools "$AOSP/bin" \
    --key "$KEY" --out "$W/img" --disk-bytes 42949672960 --vm > "$W/img.log" 2>&1
fi
[ "${DGPU_VM_BUILD_ONLY:-0}" = 1 ] && { echo "built: candidate $sha; disk in $W/img"; exit 0; }
rm -rf "$W/vm"
run python3 "$HERE/ab-qemu.py" --image-dir "$W/img" --qemu "$QEMU" --bootsync "$BOOTSYNC" --out "$W/vm" \
  --accel "$ACCEL" --seconds "${VM_SECONDS:-2400}" > "$W/vm.log" 2>&1 || true
python3 "$HERE/dgpu-vm-judge.py" "$W" "$BASELINE"
