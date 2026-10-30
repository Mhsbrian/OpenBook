#!/usr/bin/env bash
# Boot the given GKI bzImage in a throwaway QEMU guest with openbook_lid_guard.ko and run lidtest.
# usage: run-vm-test.sh BZIMAGE MODULE.ko OUTDIR [SSDT.aml]   (inside scripts/installer/inst-docker.sh)
# Without SSDT: a uinput lid and QEMU's ACPI power button. With lid-transient.aml: an ACPI lid whose
# _LID reads open for 0.5 s after each resume.
set -euo pipefail
K=$1; M=$2; O=$3; A=${4:-}; T=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$O/root/bin" "$O/root/proc" "$O/root/sys" "$O/root/dev"
gcc -static -O2 -Wall -Werror -o "$O/root/lidtest" "$T/lidtest.c"
cp "${BUSYBOX:?set BUSYBOX to a static busybox}" "$O/root/bin/busybox"
cp "$T/init" "$O/root/init"; chmod 755 "$O/root/init" "$O/root/bin/busybox"
cp "$M" "$O/root/openbook_lid_guard.ko"
(cd "$O/root" && find . | cpio -o -H newc --quiet | gzip -9n) > "$O/initramfs.cpio.gz"
timeout 150 qemu-system-x86_64 -machine q35 -accel kvm -cpu host -smp 2 -m 1024 -nographic -no-reboot -global ICH9-LPC.disable_s3=0 ${A:+-acpitable file=$A} \
  -kernel "$K" -initrd "$O/initramfs.cpio.gz" -append "console=ttyS0,115200 8250.nr_uarts=1 rdinit=/init loglevel=7 pm_debug_messages" \
  > "$O/serial.log" 2>&1 || true
grep -aE '^(RESULT|COUNTERS|KLOG|LIDSEQ|acpi lid|==)' "$O/serial.log" || true
