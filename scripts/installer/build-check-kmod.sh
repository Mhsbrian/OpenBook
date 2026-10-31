#!/usr/bin/env bash
# Build the hardware check's test-only kernel module(s) in scripts/installer/kmod/ against the exact OpenBook kernel
# the check boots (ANAL-189): its source tree (read-only), its .config, vmlinux.symvers and release string, and the
# same prebuilt clang. Plain kbuild in a private O= directory under ~/anybook/installer; the kernel lane's tree and
# Kleaf outputs are never written. Runs in the openbook-installer container.
#
# usage: build-check-kmod.sh            -> $I/build/kmod/*.ko (and vermagic printed)
#   CHECK_KMOD_OUT=DIR: write the modules to DIR (below $I) instead, so parallel work does not share outputs
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd); S=$R/scripts/installer
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; I=$A/installer
KSRC=${CHECK_KSRC:-$A/kernel/src/common}
DIST=${CHECK_KDIST:-$A/kernel/dist/anybook-amd-gbos-16302624}   # bzImage 6d964789..., the check's kernel
CLANG=${CHECK_CLANG:-$A/kernel/src/prebuilts/clang/host/linux-x86/clang-r584948c/bin}
REL=$(sed -n 's/^Linux version \([^ ]*\) .*/\1/p' "$DIST/linux_banner.txt")
O=$I/kbuild/$REL; OUT=${CHECK_KMOD_OUT:-$I/build/kmod}; M=$OUT-src
[ -n "$REL" ] || { echo "no release in $DIST/linux_banner.txt" >&2; exit 2; }
mkdir -p "$O" "$OUT"
rm -rf "$M" && mkdir -p "$M" && cp "$S"/kmod/* "$M/"
"$S/inst-docker.sh" bash -c "set -e
  export PATH=$CLANG:\$PATH
  MK='make -s -C $KSRC O=$O LLVM=1 HOSTCC=gcc HOSTCXX=g++ -j$(nproc)'
  if [ ! -f $O/scripts/mod/modpost ]; then
    cp $DIST/dot_config $O/.config
    \$MK olddefconfig >/dev/null
    \$MK modules_prepare
  fi
  # vermagic must match the kernel exactly: take the release string from its banner, and its export CRCs.
  echo '$REL' > $O/include/config/kernel.release
  echo '#define UTS_RELEASE \"$REL\"' > $O/include/generated/utsrelease.h
  cp $DIST/vmlinux.symvers $O/Module.symvers
  : > $O/protected_module_names_list   # modules of this build whose exports GKI protects: none (we export nothing)
  make -s -C $O M=$M LLVM=1 HOSTCC=gcc modules
  cp $M/*.ko $OUT/"
for k in "$OUT"/*.ko; do echo "$(basename "$k"): vermagic '$(modinfo -F vermagic "$k")', sha256 $(sha256sum "$k" | cut -c1-16)"; done
echo "kernel: vermagic '$(modinfo -F vermagic "$DIST/amd-pmc.ko")'"
