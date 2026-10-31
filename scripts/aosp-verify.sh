#!/usr/bin/env bash
# Check that the AOSP tree is usable: envsetup + lunch + `m nothing` (Soong/Kati analysis only, no compile).
# Runs inside anybook-aosp:  scripts/aosp-docker.sh /repo/scripts/aosp-verify.sh [TARGET]
# Logs go to /logs (= ~/anybook/logs/aosp): verify-<ts>.log, lunch-<ts>.txt, m-nothing-<ts>.log,
# time-m-nothing-<ts>.txt (GNU time -v), and the container cgroup's peak memory.
set -euo pipefail
TGT=${1:-${AOSP_TARGET:-aosp_cf_x86_64_pc-trunk_staging-userdebug}}
T=/aosp/src; L=/logs; TS=$(date -u +%Y%m%dT%H%M%SZ)
exec > >(tee -a "$L/verify-$TS.log") 2>&1
stamp(){ echo "=== $(date -u +%FT%TZ) $*"; }
cd "$T"
stamp "target $TGT on $(nproc) CPUs"; free -g; ccache -p | grep -E 'max_size|cache_dir|compiler_check'
# envsetup.sh and lunch are not nounset-clean.
set +u
stamp "lunch"
bash -c "source build/envsetup.sh >/dev/null && lunch $TGT" 2>&1 | tee "$L/lunch-$TS.txt"
stamp "m nothing"
/usr/bin/time -v -o "$L/time-m-nothing-$TS.txt" \
  bash -c "source build/envsetup.sh >/dev/null && lunch $TGT >/dev/null && m nothing" 2>&1 | tee "$L/m-nothing-$TS.log"
rc=${PIPESTATUS[0]}
stamp "m nothing exit $rc"
grep -E 'Elapsed|Maximum resident|Percent of CPU|User time|System time' "$L/time-m-nothing-$TS.txt"
echo "container cgroup memory.peak: $(cat /sys/fs/cgroup/memory.peak 2>/dev/null || echo n/a) bytes"
du -sh out 2>/dev/null || true
exit "$rc"
