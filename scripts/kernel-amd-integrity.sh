#!/usr/bin/env bash
# Show that the AMD vendor fragment changes nothing that vmlinux or a GKI module is built from.
# Builds //common:kernel_x86_64_dist a second time with kernel/devices/anybook/anybook_amd.fragment applied on
# top (--defconfig_fragment; minus its MODULE_SIG_ALL line, so the GKI modules stay signed and the GKI's
# signed-module checks pass), then compares it with the normal AnyBook GKI dist:
#   - vmlinux, symbol by symbol (scripts/kernel-equiv-compare.py): symbols only in one build, symbols whose
#     size changed
#   - every GKI module, after dropping the signature (each build signs with its own key), build ID and .BTF
# Any vmlinux difference is built-in code that reads a vendor option (IS_ENABLED(CONFIG_X) with X=m). The
# vendor modules are compiled with it and the shipped vmlinux without it, so each one has to be reviewed.
#
# usage: kernel-amd-integrity.sh GKI_DIST [OUT_REPORT]
#   GKI_DIST    dist of the normal build, e.g. ~/anybook/kernel/dist/anybook-amd-gbos-16302624
#   OUT_REPORT  default GKI_DIST/integrity.txt; the second dist goes to GKI_DIST-integrity
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
[ -n "${ANYBOOK_IN_KERNEL_CONTAINER:-}" ] || exec "$R/scripts/kernel-docker.sh" "$R/scripts/kernel-amd-integrity.sh" "$@"
A=${ANYBOOK_HOME:-$HOME/anybook}; K=$A/kernel; S=$K/src; L=$A/logs/kernel
GA=$(realpath "$1"); GB=$GA-integrity; OUT=${2:-$GA/integrity.txt}
LOG=$L/integrity-$(basename "$GA")-$(date +%Y%m%d-%H%M%S).log
exec > >(tee -a "$LOG") 2>&1
echo "### integrity build: //common:kernel_x86_64_dist + anybook_amd.fragment -> $GB $(date -Is)"
cd "$S"
J=${ANYBOOK_KERNEL_JOBS:-}; JOBS=(${J:+--jobs=$J --make_jobs=$J})
timeout "${BUILD_TIMEOUT:-7200}" tools/bazel run "${JOBS[@]}" --config=stamp \
  --defconfig_fragment=//devices/anybook:anybook_amd_gki_check_fragment --allow_undeclared_modules \
  //common:kernel_x86_64_dist -- --destdir="$GB"

{
  echo "# vendor-fragment equivalence: $(basename "$GA") vs the same GKI built with anybook_amd.fragment"
  echo "# $(date -Is)"
  python3 "$R/scripts/kernel-equiv-compare.py" "$GA" "$GB"
} | tee "$OUT"
echo "### report: $OUT; log: $LOG"
