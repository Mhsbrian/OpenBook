#!/usr/bin/env bash
# Unpack a Googlebook OS recovery image (GPT disk image) for inspection, without root.
# Run inside the anybook-inspect container (tools/Dockerfile.inspect):
#   docker run --rm -u $(id -u):$(id -g) -v $HOME/anybook:/a anybook-inspect \
#     /a/repo/scripts/gbos-unpack.sh /a/dl/gbos-ruby/android-desktop_signed_recovery_image.bin /a/work/gbos-ruby
# Produces: parts/*.img, super/*.img (lpunpack), fs/<partition>/ (erofs extract),
#           boot_a/ init_boot_a/ vendor_boot_a/ (unpack_bootimg), ramdisks/, kernel/{vmlinux,config}, vendor_cmdline.txt
set -euo pipefail
BIN=$1; W=$2; HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$W/parts" "$W/super" "$W/fs" "$W/ramdisks" "$W/kernel"
python3 "$HERE/gpt-list.py" "$BIN" | tee "$W/gpt.txt"
for p in super boot_a init_boot_a vendor_boot_a vbmeta_a EFI-SYSTEM; do
  read -r start sectors < <(awk -v n="$p" '$2==n {print $3, $4}' "$W/gpt.txt")
  dd if="$BIN" of="$W/parts/$p.img" bs=512 skip="$start" count="$sectors" status=none
done
lpdump "$W/parts/super.img" > "$W/lpdump.txt"
lpunpack "$W/parts/super.img" "$W/super" >/dev/null
for img in "$W"/super/*_a.img; do
  n=$(basename "$img" .img); [ -s "$img" ] || continue
  fsck.erofs --extract="$W/fs/$n" "$img" >/dev/null 2>&1 || echo "WARN: $n is not erofs"
done
for b in boot_a init_boot_a vendor_boot_a; do unpack_bootimg --boot_img "$W/parts/$b.img" --out "$W/$b" > "$W/$b.txt"; done
grep '^vendor command line args:' "$W/vendor_boot_a.txt" | cut -d: -f2- | sed 's/^ //' > "$W/vendor_cmdline.txt"
for r in "$W"/init_boot_a/ramdisk "$W"/vendor_boot_a/vendor_ramdisk*; do
  o="$W/ramdisks/$(basename "$(dirname "$r")")_$(basename "$r")"; mkdir -p "$o"
  case "$(file -b "$r")" in *LZ4*) lz4 -dc "$r";; *gzip*) gzip -dc "$r";; *Zstandard*) zstd -dc "$r";; *) cat "$r";; esac \
    | (cd "$o" && cpio -idm --quiet 2>/dev/null || true)
done
python3 "$HERE/kernel-info.py" "$W/boot_a/kernel" "$W/kernel" | tee "$W/kernel/version.txt"
echo "done: $W"
