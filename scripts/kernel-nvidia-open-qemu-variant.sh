#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# ANAL-297: the QEMU-only test build of nvidia.ko, and the guest data disk for scripts/nvidia-open-guest-check.sh.
# QEMU has no NVIDIA GPU, and the shipped nvidia.ko ends its init with -ENODEV there, by NVIDIA's design; so nothing
# could load on top of it. kernel/patches/nvidia-open/test/*.patch (never shipped) keeps it loaded, as NVIDIA's code
# does with an NVSwitch present. This builds that nvidia.ko from TREE's devices/anybook/nvidia_open (the checkout
# kernel-nvidia-open-apply.sh made) plus the test patches, against TREE's built device kernel (Kleaf's
# modules_prepare output and Module.symvers), with the same Makefile Kleaf runs. Only nvidia.ko is used from it: the
# check loads the shipped nvidia-modeset.ko and nvidia-drm.ko from vendor_dlkm on top, so every nvidia.ko export
# they import must carry the CRC the shipped nvidia.ko has, which is checked here. (With CONFIG_GENDWARFKSYMS a few
# exports they do not use, nvidia_p2p_*, come out with other CRCs outside Kleaf.) Also builds
# scripts/qemu-test/nvidiactl-smoke.c.
#
# usage: kernel-nvidia-open-qemu-variant.sh TREE DIST OUT
#   TREE   the kernel tree the G14 dist was built in (kernel-g14-package.sh, ANYBOOK_KERNEL_SRC)
#   DIST   that dist (its nvidia-modeset.ko and nvidia-drm.ko)
#   OUT    writes OUT/nvidia-qemu-test.ko, OUT/nvidiactl-smoke, OUT/guest-data.tar (both, for --qemu-arg's extra
#          disk), OUT/variant.txt (provenance and the CRC comparison) and OUT/build.log
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
[ $# = 3 ] || { sed -n 3,17p "$0" >&2; exit 2; }
S=$(realpath "$1"); DIST=$(realpath "$2"); O=$(realpath -m "$3")
SYMVERS=$S/bazel-bin/devices/anybook/nvidia_open/nvidia_open/Module.symvers
CLV=$(sed -n 's/^CLANG_VERSION="\(.*\)"/\1/p' "$S/common/build.config.constants")
CL=$S/prebuilts/clang/host/linux-x86/clang-$CLV/bin
PREP=$S/bazel-bin/devices/anybook/anybook_amd_x86_64_modules_prepare/modules_prepare_outdir.tar.gz
KSYMVERS=$S/bazel-bin/devices/anybook/anybook_amd_x86_64/Module.symvers
for f in "$PREP" "$KSYMVERS" "$SYMVERS" "$CL/clang" "$S/devices/anybook/nvidia_open/.git" "$DIST/nvidia-drm.ko"; do
  [ -e "$f" ] || { echo "missing: $f" >&2; exit 1; }
done
rm -rf "$O"; mkdir -p "$O/out/common" "$O/src"
tar xzf "$PREP" -C "$O/out/common"
cp "$KSYMVERS" "$O/out/common/Module.symvers"
ln -s "$S/prebuilts" "$O/out/prebuilts"   # Kleaf's host tools find their musl loader at ${ORIGIN}/../../../prebuilts
cp -a --reflink=auto "$S/devices/anybook/nvidia_open" "$O/src/nvidia_open"
V=$O/src/nvidia_open
for p in "$R"/kernel/patches/nvidia-open/test/*.patch; do
  GIT_COMMITTER_NAME="AnyBook kernel-nvidia-open-qemu-variant.sh" GIT_COMMITTER_EMAIL=noreply@anybook.invalid \
    GIT_COMMITTER_DATE=2026-10-26T00:00:00+00:00 git -C "$V" am -q --no-gpg-sign --directory=open-gpu-kernel-modules "$p"
done
( cd "$V" && env PATH="$CL:/usr/bin:/bin" nice -n 10 make -j"${ANYBOOK_KERNEL_JOBS:-8}" LLVM=1 M="$V" O="$O/out/common" \
    MO="$O/mo" KERNEL_SRC="$S/common" modules ) > "$O/build.log" 2>&1 || { tail -20 "$O/build.log" >&2; exit 1; }
K=$O/mo/open-gpu-kernel-modules/kernel-open
"$CL/llvm-strip" --strip-debug -o "$O/nvidia-qemu-test.ko" "$K/nvidia.ko"
"$CL/clang" --target=x86_64-linux-gnu -static -nostdlib -ffreestanding -fno-stack-protector -fno-builtin -O2 \
  -fuse-ld=lld -Wall -o "$O/nvidiactl-smoke" "$R/scripts/qemu-test/nvidiactl-smoke.c"
# The shipped nvidia-modeset and nvidia-drm resolve nvidia.ko's exports by CRC: those they import must match.
for m in nvidia-modeset nvidia-drm; do "$CL/llvm-nm" -u "$DIST/$m.ko" | awk '{print $2}'; done | sort -u > "$O/imports.txt"
awk -F'\t' '$3 ~ /(^|\/)nvidia$/ {print $2"\t"$1}' "$K/Module.symvers" | sort > "$O/variant-exports.tsv"
awk -F'\t' '$3 ~ /(^|\/)nvidia$/ {print $2"\t"$1}' "$SYMVERS" | sort > "$O/shipped-exports.tsv"
[ -s "$O/shipped-exports.tsv" ] || { echo "no nvidia.ko exports in $SYMVERS" >&2; exit 1; }
used() { awk -F'\t' 'NR==FNR {u[$1]=1; next} ($1 in u)' "$O/imports.txt" "$1"; }
used "$O/variant-exports.tsv" > "$O/variant-used.tsv"; used "$O/shipped-exports.tsv" > "$O/shipped-used.tsv"
tar -C "$O" -cf "$O/guest-data.tar" nvidia-qemu-test.ko nvidiactl-smoke
{
  echo "nvidia_open HEAD $(git -C "$V" rev-parse HEAD) (shipped checkout $(git -C "$S/devices/anybook/nvidia_open" rev-parse HEAD) + $(ls "$R"/kernel/patches/nvidia-open/test/*.patch | wc -l) test patch)"
  echo "kernel $(cat "$O/out/common/include/config/kernel.release")"
  echo "nvidia.ko exports: variant $(wc -l < "$O/variant-exports.tsv"), shipped $(wc -l < "$O/shipped-exports.tsv"); with another CRC: $(diff "$O/variant-exports.tsv" "$O/shipped-exports.tsv" | grep -c '^<')"
  echo "of those the shipped nvidia-modeset.ko and nvidia-drm.ko import: $(wc -l < "$O/shipped-used.tsv")"
  if cmp -s "$O/variant-used.tsv" "$O/shipped-used.tsv"; then echo "their CRCs: identical"; else echo "their CRCs: DIFFER"; fi
  sha256sum "$O/nvidia-qemu-test.ko" "$O/nvidiactl-smoke" "$O/guest-data.tar"
} | tee "$O/variant.txt"
cmp -s "$O/variant-used.tsv" "$O/shipped-used.tsv"
