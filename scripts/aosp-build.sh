#!/usr/bin/env bash
# Build an AOSP product in the synced tree (default aosp_cf_x86_64_pc-cp2a-userdebug), with ccache. Resumable:
# re-running continues where siso/ninja stopped. Runs inside anybook-aosp:
#   scripts/aosp-docker.sh -d anybook-aosp-build /repo/scripts/aosp-build.sh [TARGET] [GOAL...]
#   docker wait anybook-aosp-build          # block until done; docker stop anybook-aosp-build cancels
# GOALs default to `droid` (what plain `m` builds); pass `dist` for out/dist (img zip, cvd-host_package.tar.gz).
# AOSP_JOBS caps parallelism (default: nproc). The host is shared and Soong analysis alone peaks at ~43 GiB RSS.
# Logs go to /logs (= ~/anybook/logs/aosp): build-<ts>.log (console), time-build-<ts>.txt (GNU time -v),
# mem-build-<ts>.csv (container cgroup memory sampled every 15 s), ccache-<ts>-{before,after}.txt, sizes.
set -euo pipefail
TGT=${1:-${AOSP_TARGET:-aosp_cf_x86_64_pc-cp2a-userdebug}}; shift || true
GOALS=("$@"); [ ${#GOALS[@]} -gt 0 ] || GOALS=(droid)
J=${AOSP_JOBS:-$(nproc)}
T=/aosp/src; L=/logs; TS=$(date -u +%Y%m%dT%H%M%SZ); CG=/sys/fs/cgroup
exec > >(tee -a "$L/build-$TS.log") 2>&1
stamp(){ echo "=== $(date -u +%FT%TZ) $*"; }
cd "$T"
stamp "target $TGT goals ${GOALS[*]} -j$J on $(nproc) CPUs"; free -g
ccache -p | grep -E 'max_size|cache_dir|compiler_check'
ccache -z >/dev/null; ccache -s -v > "$L/ccache-$TS-before.txt"
# Memory sampler: container cgroup (this build only), plus host-wide MemAvailable for context.
( echo "utc,cg_mem_bytes,cg_swap_bytes,host_memavail_kb"
  while sleep 15; do
    echo "$(date -u +%FT%TZ),$(cat $CG/memory.current),$(cat $CG/memory.swap.current 2>/dev/null || echo 0),$(awk '/MemAvailable/{print $2}' /proc/meminfo)"
  done ) > "$L/mem-build-$TS.csv" &
SAMPLER=$!; trap 'kill $SAMPLER 2>/dev/null || true' EXIT
# envsetup.sh and lunch are not nounset-clean.
set +u
stamp "m -j$J ${GOALS[*]}"
set +e
/usr/bin/time -v -o "$L/time-build-$TS.txt" \
  bash -c "source build/envsetup.sh >/dev/null && lunch $TGT && m -j$J ${GOALS[*]}"
rc=$?
set -u   # reporting below is best-effort; the exit code is m's
stamp "m exit $rc"
grep -E 'Elapsed|Maximum resident|Percent of CPU|User time|System time' "$L/time-build-$TS.txt"
echo "container cgroup memory.peak: $(cat $CG/memory.peak 2>/dev/null || echo n/a) bytes"
echo "container cgroup memory.swap.peak: $(cat $CG/memory.swap.peak 2>/dev/null || echo n/a) bytes"
ccache -s -v | tee "$L/ccache-$TS-after.txt"
P=$(bash -c "source build/envsetup.sh >/dev/null && lunch $TGT >/dev/null && get_build_var PRODUCT_OUT" 2>/dev/null | tail -1)
{ du -sh out out/soong out/host "$P" 2>/dev/null; ls -la "$P"/*.img 2>/dev/null; } | tee "$L/sizes-build-$TS.txt"
exit "$rc"
