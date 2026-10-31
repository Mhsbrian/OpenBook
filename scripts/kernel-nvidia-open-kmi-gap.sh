#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Compile-only check of NVIDIA's open kernel modules (open-gpu-kernel-modules, Dual MIT/GPL) against the Ruby G14
# kernel, and list the kernel symbols they import that the GKI does not export (ANAL-296). Writes no image, loads
# nothing, and leaves the kernel lane's trees untouched: the modules_prepare output is unpacked into WORK.
#
# NVIDIA's conftest decides which kernel API to call from Module.symvers. Google's trimmed symvers hides APIs that
# vmlinux has (close_fd, for one), and the build then fails on a fallback that no longer exists. So the conftest and
# modpost see Google's symvers plus every EXPORT_SYMBOL in the source (CRC 0). The import list is then compared with
# what the shipped kernel really exports, so the result is an upper bound: Tegra/SoC paths the x86 laptop never
# reaches are counted too.
#
# usage: kernel-nvidia-open-kmi-gap.sh [-j N] WORK [TAG]
#   WORK  scratch directory (about 1 GiB); TAG defaults to 615.78.08
# env:  ANYBOOK_HOME (default ~/anybook), KSRC (default $ANYBOOK_HOME/kernel/src),
#       GKI_DIST (Google's GKI dist, default $ANYBOOK_HOME/kernel/dist/gbos-16302624),
#       OUR_DIST (our kernel dist with vendor modules, default .../anybook-g14-gbos-16302624-anal239)
# out:  WORK/report.txt, WORK/gap-google-<module>.txt, WORK/gap-ours-<module>.txt, WORK/build.log
set -euo pipefail
jobs=8
[ "${1:-}" = -j ] && { jobs=$2; shift 2; }
[ $# -ge 1 ] || { sed -n 3,20p "$0" >&2; exit 2; }
W=$(realpath -m "$1"); TAG=${2:-615.78.08}
A=${ANYBOOK_HOME:-${OPENBOOK_HOME:-$HOME/anybook}}
KSRC=${KSRC:-$A/kernel/src}
GKI_DIST=${GKI_DIST:-$A/kernel/dist/gbos-16302624}
OUR_DIST=${OUR_DIST:-$A/kernel/dist/anybook-g14-gbos-16302624-anal239}
PREP=$KSRC/bazel-bin/devices/anybook/anybook_amd_x86_64_modules_prepare/modules_prepare_outdir.tar.gz
CLANG_VERSION=$(sed -n 's/^CLANG_VERSION="\(.*\)"/\1/p' "$KSRC/common/build.config.constants")
CL=$KSRC/prebuilts/clang/host/linux-x86/clang-$CLANG_VERSION/bin
for f in "$PREP" "$CL/clang" "$GKI_DIST/kernel_x86_64_Module.symvers" "$GKI_DIST/System.map" \
         "$OUR_DIST/kernel_x86_64_Module.symvers"; do
  [ -e "$f" ] || { echo "missing: $f" >&2; exit 1; }
done
mkdir -p "$W"
cd "$W"

# 1. NVIDIA's source at TAG and the kernel's modules_prepare output. The Kleaf host tools find their musl loader
#    through ${ORIGIN}/../../../prebuilts, which the symlink provides.
[ -d ogkm ] || git clone --quiet --depth 1 --branch "$TAG" https://github.com/NVIDIA/open-gpu-kernel-modules.git ogkm
rm -rf kout && mkdir kout && tar xf "$PREP" -C kout
ln -sfn "$KSRC/prebuilts" prebuilts

# 2. Symbol sets.
grep -rhoE --include='*.c' --include='*.h' 'EXPORT_SYMBOL(_GPL|_NS_GPL|_NS|_GPL_FOR_MODULES)?\(\s*[A-Za-z_][A-Za-z0-9_]*' \
  "$KSRC/common" | sed -E 's/^EXPORT_SYMBOL[A-Z_]*\(\s*//' | sort -u > src-exports.txt
cut -f2 "$GKI_DIST/kernel_x86_64_Module.symvers" | sort -u > gki-exports.txt
cut -f2 "$OUR_DIST/kernel_x86_64_Module.symvers" | sort -u > ours-exports.txt
awk '{print $3}' "$GKI_DIST/System.map" | sort -u > gki-systemmap.txt
for ko in "$OUR_DIST"/*.ko; do
  "$CL/llvm-nm" --defined-only "$ko" 2>/dev/null | awk '$3 ~ /^__ksymtab_/ {sub(/^__ksymtab_/, "", $3); print $3}'
done | sort -u > module-exports.txt
cp "$GKI_DIST/kernel_x86_64_Module.symvers" kout/Module.symvers
comm -23 src-exports.txt gki-exports.txt |
  awk '{printf "0x00000000\t%s\tvmlinux\tEXPORT_SYMBOL_GPL\t\n", $1}' >> kout/Module.symvers

# 3. Build. IGNORE_CC_MISMATCH: NVIDIA compares version strings, and the kernel's carries LLD's version too.
rm -rf ogkm/kernel-open/conftest
( cd ogkm && env PATH="$CL:/usr/bin:/bin" IGNORE_CC_MISMATCH=1 nice -n 10 make modules -j"$jobs" \
    SYSSRC="$KSRC/common" SYSOUT="$W/kout" TARGET_ARCH=x86_64 LLVM=1 CC=clang LD=ld.lld AR=llvm-ar NM=llvm-nm \
    OBJCOPY=llvm-objcopy HOSTCC=clang HOSTCXX=clang++ ) > build.log 2>&1 ||
  { tail -20 build.log >&2; echo "build failed: $W/build.log" >&2; exit 1; }

# 4. Imports each module needs that the kernel does not export.
sort -u gki-exports.txt module-exports.txt > avail-google.txt
sort -u ours-exports.txt module-exports.txt > avail-ours.txt
mods=(nvidia nvidia-modeset nvidia-drm nvidia-uvm nvidia-peermem)
for m in "${mods[@]}"; do
  "$CL/llvm-nm" --defined-only "ogkm/kernel-open/$m.ko" | awk '$3 ~ /^__ksymtab_/ {sub(/^__ksymtab_/, "", $3); print $3}'
done | sort -u > nv-exports.txt
{
  echo "open-gpu-kernel-modules $TAG ($(git -C ogkm rev-parse HEAD)) against $(cat kout/include/config/kernel.release)"
  echo "compiler: $CLANG_VERSION; GKI dist: $GKI_DIST; our dist: $OUR_DIST"
  printf '%-15s %7s %16s %13s %22s\n' module imports not-in-Google-GKI not-in-ours absent-from-vmlinux
  for m in "${mods[@]}"; do
    "$CL/llvm-nm" -u "ogkm/kernel-open/$m.ko" | awk '{print $2}' | sort -u > "undef-$m.txt"
    comm -23 "undef-$m.txt" nv-exports.txt | comm -23 - avail-google.txt > "gap-google-$m.txt"
    comm -23 "undef-$m.txt" nv-exports.txt | comm -23 - avail-ours.txt > "gap-ours-$m.txt"
    printf '%-15s %7d %16d %13d %22d\n' "$m" "$(wc -l < "undef-$m.txt")" "$(wc -l < "gap-google-$m.txt")" \
      "$(wc -l < "gap-ours-$m.txt")" "$(comm -23 "gap-google-$m.txt" gki-systemmap.txt | wc -l)"
  done
  echo "nvidia + nvidia-modeset + nvidia-drm, distinct: not in Google's GKI $(cat gap-google-nvidia{,-modeset,-drm}.txt |
    sort -u | wc -l), not in ours $(cat gap-ours-nvidia{,-modeset,-drm}.txt | sort -u | wc -l)"
  echo "absent from Google's vmlinux (export alone cannot fix): $(cat gap-google-*.txt | sort -u |
    comm -23 - gki-systemmap.txt | tr '\n' ' ')"
  echo "objtool warnings: $(grep -c 'warning: objtool' build.log || true)"
  sha256sum ogkm/kernel-open/*.ko
} | tee report.txt
