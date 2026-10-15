#!/usr/bin/env bash
# Boot the stock Googlebook OS GKI kernel + ramdisks from an unpacked recovery image in QEMU.
# Purpose: execution test of Google's x86_64 userspace on a given CPU (KVM = real host CPUID,
# TCG = QEMU's emulated "max" CPU). Read-only: the disk is attached with snapshot=on.
#
# usage: gbos-qemu-boot.sh WORKDIR RECOVERY_BIN OUT_LOG [kvm|tcg] [timeout_s]
#   WORKDIR = output dir of gbos-unpack.sh (boot_a/, init_boot_a/, vendor_boot_a/, vendor_cmdline.txt)
set -euo pipefail
W=$1; BIN=$2; LOG=$3; MODE=${4:-kvm}; TMO=${5:-180}
OUT=$(dirname "$LOG"); mkdir -p "$OUT"
INITRD=$OUT/initrd-$MODE.img

# Ramdisk order the bootloader uses for a normal boot: vendor PLATFORM (00) + DLKM (02) + generic.
cat "$W/vendor_boot_a/vendor_ramdisk00" "$W/vendor_boot_a/vendor_ramdisk02" "$W/init_boot_a/ramdisk" > "$INITRD"

python3 - "$INITRD" <<'PY'
import struct, sys
cfg = b"""androidboot.hardware=android-desktop
androidboot.hardware.platform=android-desktop
androidboot.load_modules_parallel=true
androidboot.slot_suffix=_a
androidboot.boot_devices=pci0000:00/0000:00:04.0
androidboot.verifiedbootstate=orange
androidboot.vbmeta.device_state=unlocked
androidboot.force_normal_boot=1
androidboot.serialconsole=1
androidboot.console=ttyS0
"""
cfg += b"\0" * (-len(cfg) % 4)
with open(sys.argv[1], "ab") as f:
    f.write(cfg + struct.pack("<II", len(cfg), sum(cfg) & 0xffffffff) + b"#BOOTCONFIG\n")
PY

VCMD=$(cat "$W/vendor_cmdline.txt")   # written by gbos-unpack.sh
CMD="${VCMD/console=null/console=ttyS0,115200} earlycon=uart8250,io,0x3f8,115200 printk.devkmsg=on loglevel=7 panic=-1"

if [ "$MODE" = kvm ]; then ACC=(-accel kvm -cpu host); else ACC=(-accel tcg,thread=multi -cpu max); fi
{ echo "### mode=$MODE cpu=${ACC[*]}"; echo "### cmdline: $CMD"; } > "$LOG"
timeout --foreground "$TMO" qemu-system-x86_64 -machine q35 "${ACC[@]}" -smp 4 -m 8G \
  -kernel "$W/boot_a/kernel" -initrd "$INITRD" -append "$CMD" \
  -drive file="$BIN",format=raw,if=none,id=d0,snapshot=on,readonly=off \
  -device nvme,drive=d0,serial=gbos0,addr=0x4 \
  -display none -serial file:"$LOG.serial" -no-reboot -monitor none -nodefaults >> "$LOG" 2>&1 || echo "### qemu exit $? (124 = timeout)" >> "$LOG"
cat "$LOG.serial" >> "$LOG"; rm -f "$LOG.serial"
