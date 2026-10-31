#!/usr/bin/env bash
# Sync an Android GKI kernel tree (repo + kernel/manifest) into ~/anybook/kernel/src for Kleaf builds.
# Runs itself inside the anybook-kernel container. Resumable: rerun it after a timeout or network error.
#
# usage: kernel-sync.sh [TARGET]
#   gbos-16302624  (default) exact sources of the kernel Googlebook OS ships, 6.18.21-android17-5-g3938c8d97142-ab16302624:
#                  branch common-android17-6.18-2026-06, pinned by manifests/kernel/gbos-16302624.xml
#                  (the repo manifest ci.android.com published for build 16302624, kernel_x86_64)
#   android17-6.18 tip of kernel/manifest common-android17-6.18
#   <other>        tip of kernel/manifest common-<other>, e.g. android-mainline-desktop
# env: SYNC_JOBS (8), SYNC_TIMEOUT per attempt in s (3000), SYNC_TRIES (5)
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
[ -n "${ANYBOOK_IN_KERNEL_CONTAINER:-}" ] || exec "$R/scripts/kernel-docker.sh" "$R/scripts/kernel-sync.sh" "$@"
A=${ANYBOOK_HOME:-$HOME/anybook}; K=$A/kernel; S=$K/src; L=$A/logs/kernel
T=${1:-gbos-16302624}; SHIPPED=3938c8d97142d5cf31543aa96f864a2cf832dda0
case $T in
  gbos-16302624) B=common-android17-6.18-2026-06; M=$R/manifests/kernel/gbos-16302624.xml ;;
  *) B=common-$T; M= ;;
esac
mkdir -p "$S" "$K/pins" "$L"
LOG=$L/sync-$T-$(date +%Y%m%d-%H%M%S).log
exec > >(tee -a "$LOG") 2>&1
echo "### kernel-sync target=$T branch=$B manifest=${M:-default.xml} $(date -Is)"
git config --global color.ui false
cd "$S"
repo init -u https://android.googlesource.com/kernel/manifest -b "$B"
if [ -n "$M" ]; then cp "$M" .repo/manifests/anybook-$T.xml; repo init -m anybook-$T.xml; fi
T0=$(date +%s); ok=
for i in $(seq 1 "${SYNC_TRIES:-5}"); do
  echo "### repo sync attempt $i"
  if timeout "${SYNC_TIMEOUT:-3000}" repo sync -c -j"${SYNC_JOBS:-8}" --no-tags --fail-fast; then ok=1; break; fi
  sleep $((i * 60))   # googlesource answers HTTP 503 when rate limited; back off before retrying
done
echo "### repo sync ${ok:+done}${ok:-FAILED} in $(( $(date +%s) - T0 ))s"
[ -n "$ok" ]
echo "$T" > .anybook-target
repo manifest -r -o "$K/pins/$T.xml"

# Provenance of kernel/common: pinned SHA, and whether the shipped Googlebook SHA is on the public branches.
P=$K/pins/$T.common.txt
{
  echo "target=$T branch=$B date=$(date -Is)"
  echo "common HEAD=$(git -C common rev-parse HEAD) ($(git -C common log -1 --format='%cI %s'))"
  echo "Makefile version=$(sed -n 's/^\(VERSION\|PATCHLEVEL\|SUBLEVEL\) = //p' common/Makefile | paste -sd.)"
  for h in android17-6.18 android17-6.18-2026-06 android17-6.18-2026-09; do
    for _ in 1 2 3 4 5; do git -C common fetch -q --no-tags aosp "+refs/heads/$h:refs/remotes/anybook/$h" && break; sleep 20; done
    if git -C common merge-base --is-ancestor "$SHIPPED" "refs/remotes/anybook/$h" 2>/dev/null; then r=yes; else r=no; fi
    echo "shipped ${SHIPPED:0:12} reachable from $h ($(git -C common rev-parse --short=12 refs/remotes/anybook/$h)): $r"
  done
} | tee "$P"
du -sh "$S" 2>/dev/null | sed 's/^/### tree size: /'
