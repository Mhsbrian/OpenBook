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
# The tree and out/ are shared: builders take turns under the AOSP lane lock, <data dir>/aosp/.lane.lock (here
# /aosp/.lane.lock), which the caller holds for the whole build:
#   flock ~/anybook/aosp/.lane.lock sh -c 'scripts/aosp-docker.sh -d NAME /repo/scripts/aosp-build.sh ARGS &&
#     docker wait NAME'
# installer-image.sh takes the same lock while it snapshots PRODUCT_OUT. ANYBOOK_LANE_UNLOCKED=1 skips this check
# (a tree of your own).
if [ "${ANYBOOK_LANE_UNLOCKED:-0}" != 1 ] && flock -n /aosp/.lane.lock true; then
  echo "aosp-build.sh: nobody holds the AOSP lane lock; run the build under it:" >&2
  echo "  flock ~/anybook/aosp/.lane.lock sh -c 'scripts/aosp-docker.sh -d NAME /repo/scripts/aosp-build.sh ... && docker wait NAME'" >&2
  exit 1
fi
exec > >(tee -a "$L/build-$TS.log") 2>&1
stamp(){ echo "=== $(date -u +%FT%TZ) $*"; }
cd "$T"
stamp "target $TGT goals ${GOALS[*]} -j$J on $(nproc) CPUs"; free -g
# AnyBook's own device tree (device/anybook in this repo, e.g. anybook_cf_x86_64_pc) is copied into the tree,
# not symlinked: Soong's nsjail sandbox only sees /aosp/src. --delete keeps it an exact mirror of the repo.
if [ -d /repo/device/anybook ]; then
  # --copy-unsafe-links: files the device tree links from elsewhere in this repo (scripts/dgpu-power-check.sh)
  # arrive as copies. Content is compared (--checksum) and times are not kept: builders of different branches take
  # turns in this tree, and a file that keeps its checkout time can look older than an output another branch's
  # build just made from its own version, so the build keeps the stale output (ANAL-176 met ANAL-179's
  # file_contexts that way). A file that changed gets the current time; one that did not keeps its old time.
  rsync -rlpD --checksum --copy-unsafe-links --delete /repo/device/anybook/ "$T/device/anybook/"
  stamp "synced device/anybook from /repo (AnyBook ${ANYBOOK_REV:-unknown})"
fi
# AnyBook's patches to AOSP projects (aosp/patches/<project>), on top of each project's pin.
if [ -d /repo/aosp/patches ]; then
  AOSP_SRC=$T /repo/scripts/aosp-patches.sh
fi
# The Mesa prebuilts graphics-amd.mk needs are staged on the host by scripts/graphics-amd-stage-mesa.sh.
[ -f "$T/vendor/anybook/mesa/PROVENANCE.txt" ] && stamp "vendor/anybook/mesa: $(sed -n 's/^tree: //p' "$T/vendor/anybook/mesa/PROVENANCE.txt")"
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
