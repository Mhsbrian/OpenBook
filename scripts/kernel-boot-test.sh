#!/usr/bin/env bash
# Boot a locally built bzImage with the ramdisks of a user-downloaded Googlebook OS image, under QEMU/KVM,
# to get a real "Linux version" line and compare how far boot gets with the stock kernel (docs/kernel.md).
# Read-only: reuses gbos-qemu-boot.sh, which attaches the recovery image with snapshot=on.
#
# usage: kernel-boot-test.sh BZIMAGE [OUT_LOG] [timeout_s]
#   BZIMAGE  e.g. ~/anybook/kernel/dist/gbos-16302624/bzImage
#   OUT_LOG  default ~/anybook/kernel/boottest/<dist label>-zen4-kvm.log
# env: GBOS_WORK (~/anybook/work/gbos-ruby, from gbos-unpack.sh), GBOS_BIN (the recovery .bin)
set -euo pipefail
A=${ANYBOOK_HOME:-$HOME/anybook}; R=$(cd "$(dirname "$0")/.." && pwd)
BZ=$(realpath "$1"); W0=${GBOS_WORK:-$A/work/gbos-ruby}
BIN=${GBOS_BIN:-$A/dl/gbos-ruby/android-desktop_signed_recovery_image.bin}
B=$A/kernel/boottest; W=$B/w-$(basename "$(dirname "$BZ")")
LOG=${2:-$B/$(basename "$(dirname "$BZ")")-zen4-kvm.log}
rm -rf "$W"; mkdir -p "$W/boot_a" "$W/init_boot_a" "$(dirname "$LOG")"
cp "$BZ" "$W/boot_a/kernel"; cp -r "$W0/vendor_boot_a" "$W/"; cp "$W0/init_boot_a/ramdisk" "$W/init_boot_a/"
cp "$W0/vendor_cmdline.txt" "$W/"
# Container paths: ~/anybook read-only at /a, our kernel area writable at /a/kernel.
c(){ echo "/a/${1#"$A"/}"; }
docker run --rm -u "$(id -u):$(id -g)" --device /dev/kvm -v "$A:/a:ro" -v "$A/kernel:/a/kernel" -v "$R/scripts:/s:ro" \
  anybook-qemu /s/gbos-qemu-boot.sh "$(c "$W")" "$(c "$BIN")" "$(c "$LOG")" kvm "${3:-150}"
grep -m1 -o "Linux version [^ ]*" "$LOG"
for p in "init: starting service" "keystore2" "invalid opcode" "Kernel panic" "Unresolved symbol"; do
  printf '%-28s %s\n' "$p" "$(grep -c -- "$p" "$LOG")"
done
