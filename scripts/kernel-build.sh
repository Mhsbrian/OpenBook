#!/usr/bin/env bash
# Build the x86_64 GKI kernel with Kleaf from the tree kernel-sync.sh prepared, then collect evidence.
# Runs itself inside the anybook-kernel container. Bazel caches under ~/anybook/kernel/src/out, so a
# rerun after an interruption only redoes unfinished actions.
#
# usage: kernel-build.sh [LABEL]
#   Outputs go to ~/anybook/kernel/dist/LABEL. LABEL defaults to the synced target (src/.anybook-target),
#   plus -ab$BUILD_NUMBER when that is set.
# env: BUILD_NUMBER   unset: release string ends in -g<sha12>. ci.android.com sets it, which appends -ab<N>.
#      KERNEL_TARGET  Kleaf target to run (default //common:kernel_x86_64_dist)
#      ANYBOOK_KERNEL_JOBS  cap Bazel and make parallelism (default: all CPUs)
#      BAZEL_ARGS     extra Bazel flags; BUILD_TIMEOUT per attempt in s (default 7200)
#      ANYBOOK_KERNEL_SRC  the kernel tree (default ~/anybook/kernel/src), e.g. a task's own copy
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
[ -n "${ANYBOOK_IN_KERNEL_CONTAINER:-}" ] || exec "$R/scripts/kernel-docker.sh" "$R/scripts/kernel-build.sh" "$@"
A=${ANYBOOK_HOME:-$HOME/anybook}; K=$A/kernel; S=${ANYBOOK_KERNEL_SRC:-$K/src}; L=$A/logs/kernel
T=$(cat "$S/.anybook-target"); LABEL=${1:-$T${BUILD_NUMBER:+-ab$BUILD_NUMBER}}
TGT=${KERNEL_TARGET:-//common:kernel_x86_64_dist}; D=$K/dist/$LABEL
J=${ANYBOOK_KERNEL_JOBS:-}; JOBS=(${J:+--jobs=$J --make_jobs=$J})
mkdir -p "$D" "$L"
LOG=$L/build-$LABEL-$(date +%Y%m%d-%H%M%S).log
exec > >(tee -a "$LOG") 2>&1
echo "### kernel-build target=$T label=$LABEL kleaf=$TGT BUILD_NUMBER=${BUILD_NUMBER:-unset} $(date -Is)"
echo "### host: $(nproc) CPUs, $(free -g | awk '/Mem:/{print $2}') GB RAM; common HEAD $(git -C "$S/common" rev-parse HEAD)"
cd "$S"
T0=$(date +%s)
# nouveau (ANAL-239) and NVIDIA's open modules (ANAL-297) are external modules with git repositories of their own;
# Kleaf stamps their HEADs as scmversion.
X=; for p in devices/anybook/nvidia devices/anybook/nvidia_open; do [ -d "$p/.git" ] && X=${X:+$X:}$p; done
[ -n "$X" ] && export KLEAF_EXTRA_GIT_PROJECTS=$X
/usr/bin/time -v -o "$L/time-$LABEL.txt" timeout "${BUILD_TIMEOUT:-7200}" \
  tools/bazel run "${JOBS[@]}" --config=stamp ${BAZEL_ARGS:-} "$TGT" -- --destdir="$D"
echo "### build done in $(( $(date +%s) - T0 ))s"
cp "$L/time-$LABEL.txt" "$D/build-time.txt"

# Evidence: what was built from what, the release string, and the .config embedded in the image.
cp "$K/pins/$T.xml" "$D/manifest-pinned.xml"; cp "$K/pins/$T.common.txt" "$D/common-provenance.txt"
python3 "$R/scripts/kernel-info.py" "$D/bzImage" "$D/ikconfig" | tee "$D/linux_banner.txt"
cp "$D/ikconfig/config" "$D/dot_config"; rm -f "$D/ikconfig/vmlinux"
sha256sum "$D/bzImage" "$D/dot_config" "$D/vmlinux" 2>/dev/null | tee "$D/sha256.txt"
echo "### dist: $D ($(du -sh "$D" | cut -f1), $(find "$D" -name '*.ko' | wc -l) modules); log: $LOG"
