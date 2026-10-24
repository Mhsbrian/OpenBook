#!/usr/bin/env bash
# Prepare the external nouveau build (ANAL-239) in a kernel tree that kernel-sync.sh and kernel-amd-apply.sh made:
#   1. check that common is exactly kernel/patches/nouveau/BASE (kernel/patches/common applied), and clean;
#   2. kernel/devices/anybook/ -> <tree>/devices/anybook, as kernel-amd-apply.sh does;
#   3. <tree>/devices/anybook/nvidia becomes a git repository of its own: the package files from the repo plus
#      common's drivers/gpu/drm/nouveau (at BASE) as nouveau/, then kernel/patches/nouveau/*.patch as commits
#      (git am -p5 --directory=nouveau, fixed committer and dates, authors kept), so its HEAD is the same on every
#      machine. kernel-build.sh sets KLEAF_EXTRA_GIT_PROJECTS=devices/anybook/nvidia, and Kleaf stamps that HEAD into
#      nouveau.ko as scmversion;
#   4. check the patched directory against kernel/patches/nouveau/TREE (its git tree id).
# Idempotent: an existing nvidia/ checkout is replaced.
#
# usage: kernel-nouveau-apply.sh [TREE]     TREE defaults to $ANYBOOK_KERNEL_SRC or ~/anybook/kernel/src
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
S=$(realpath "${1:-${ANYBOOK_KERNEL_SRC:-${ANYBOOK_HOME:-$HOME/anybook}/kernel/src}}")
P=$R/kernel/patches/nouveau
BASE=$(cat "$P/BASE"); TREE=$(cat "$P/TREE")
V=$S/devices/anybook/nvidia

head=$(git -C "$S/common" rev-parse HEAD)
[ "$head" = "$BASE" ] || { echo "common is at $head, not $BASE (run kernel-amd-apply.sh)" >&2; exit 1; }
git -C "$S/common" diff --quiet HEAD -- || { echo "common has uncommitted changes" >&2; exit 1; }

mkdir -p "$S/devices/anybook"
rm -rf "${V:?}"
rsync -a --delete "$R/kernel/devices/anybook/" "$S/devices/anybook/"
mkdir "$V/nouveau"
git -C "$S/common" archive "$BASE" drivers/gpu/drm/nouveau | tar -x -C "$V/nouveau" --strip-components=4
export GIT_AUTHOR_NAME="OpenBook kernel-nouveau-apply.sh" GIT_AUTHOR_EMAIL=noreply@anybook.invalid
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
export GIT_AUTHOR_DATE=2026-10-24T00:00:00+00:00 GIT_COMMITTER_DATE=2026-10-24T00:00:00+00:00
git -C "$V" init -q -b anal239
git -C "$V" add -A
git -C "$V" commit -q -m "nvidia: OpenBook package files; nouveau/ is drivers/gpu/drm/nouveau of kernel/common $BASE"
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_AUTHOR_DATE
for f in "$P"/[0-9]*.patch; do git -C "$V" am -q -p5 --directory=nouveau "$f"; done

got=$(git -C "$V" rev-parse 'HEAD:nouveau')
[ "$got" = "$TREE" ] || { echo "patched nouveau tree is $got, expected $TREE" >&2; exit 1; }
echo "### devices/anybook/nvidia: common ${BASE:0:12}'s nouveau + $(($(git -C "$V" rev-list --count HEAD) - 1)) patches -> HEAD $(git -C "$V" rev-parse --short=12 HEAD), nouveau tree $got"
