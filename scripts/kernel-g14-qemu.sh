#!/usr/bin/env bash
# Run scripts/kernel-g14-qemu.py (first-stage mount over USB storage and NVMe, vendor_dlkm load) in the
# anybook-qemu image (tools/Dockerfile.qemu) with /dev/kvm. Inputs are read only; the disk images are built in
# the work dir and every QEMU run uses a throwaway overlay, so reruns start from the same state.
#
# usage: kernel-g14-qemu.sh [DIST] [ARGS...]   ARGS go to kernel-g14-qemu.py, e.g. --runs usb,nvme --force
# env: G14_PRODUCT  Cuttlefish PRODUCT_OUT to take the userspace from (default: ANAL-172's snapshot)
#      G14_WORK     scratch dir (default ~/anybook/kernel/g14/qemu-work, about 9 GB sparse)
#      G14_OUT      evidence dir (default ~/anybook/kernel/g14/qemu/<dist name>)
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}; K=$A/kernel
D=$(realpath "${1:-$K/dist/anybook-g14-gbos-16302624}"); [ $# -gt 0 ] && shift
P=${G14_PRODUCT:-$K/cf/snapshot/out/target/product/vsoc_x86_64_only}
W=${G14_WORK:-$K/g14/qemu-work}; O=${G14_OUT:-$K/g14/qemu/$(basename "$D")}
mkdir -p "$W/tmp" "$O"
docker image inspect anybook-qemu >/dev/null 2>&1 || docker build -q -t anybook-qemu -f "$R/tools/Dockerfile.qemu" "$R/tools"
exec docker run --rm -i --init --device /dev/kvm -u "$(id -u):$(id -g)" -e HOME="$W/tmp" -e TMPDIR="$W/tmp" \
  -v "$K:$K" -v "$R:$R:ro" -w "$W" anybook-qemu \
  python3 -u "$R/scripts/kernel-g14-qemu.py" --dist "$D" --product "$P" \
    --tools "$K/src/prebuilts/kernel-build-tools/linux_musl-x86/bin" \
    --key "$K/src/external/avb/test/data/testkey_rsa4096.pem" \
    --fstab "$R/kernel/devices/anybook/g14/test/fstab.qemu" --work "$W" --out "$O" "$@"
