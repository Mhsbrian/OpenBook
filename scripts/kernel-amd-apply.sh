#!/usr/bin/env bash
# Put the AnyBook AMD kernel changes on top of the tree kernel-sync.sh prepared:
#   1. kernel/patches/common/*.patch -> commits on a detached HEAD at the pinned kernel/common revision
#      (git am with a fixed committer and date, so the resulting SHA and the -g<sha> release string are
#      reproducible; authors, including upstream authors of backports, are kept)
#   1b. kernel/patches/build-kernel/*.patch -> commits on build/kernel (Kleaf) at its pinned revision, the same way
#      (ANAL-297: the AnyBook exception to the GKI symbol denylist, build/kernel/abi/symbols.deny)
#   2. kernel/devices/anybook/       -> ~/anybook/kernel/src/devices/anybook (Kleaf package //devices/anybook)
#   3. scripts/kernel-nouveau-apply.sh: devices/anybook/nvidia/nouveau, the external nouveau the G14 build includes
#   4. scripts/kernel-nvidia-open-apply.sh: devices/anybook/nvidia_open, NVIDIA's open kernel modules (ANAL-297)
# Idempotent: rerun after every kernel-sync.sh (repo sync resets common to the pin).
#
# usage: kernel-amd-apply.sh            apply (default)
#        kernel-amd-apply.sh --export   write the commits above the pin back to kernel/patches/common/ and
#                                       the generated symbol list into the repo (needs a writable repo, so it
#                                       runs on the host, not in the container)
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}; K=$A/kernel; S=${ANYBOOK_KERNEL_SRC:-$K/src}   # env: the kernel tree
T=$(cat "$S/.anybook-target")
BASE=$(sed -n 's/.*path="common" revision="\([0-9a-f]\{40\}\)".*/\1/p' "$K/pins/$T.xml")
[ -n "$BASE" ] || { echo "no kernel/common revision in $K/pins/$T.xml" >&2; exit 1; }
P=$R/kernel/patches/common

BK_BASE=$(sed -n 's/.*path="build\/kernel" revision="\([0-9a-f]\{40\}\)".*/\1/p' "$K/pins/$T.xml")
PB=$R/kernel/patches/build-kernel

if [ "${1:-}" = --export ]; then
  rm -f "$P"/*.patch "$PB"/*.patch
  git -C "$S/common" format-patch -q --zero-commit --no-signature -N -o "$P" "$BASE..HEAD"
  git -C "$S/build/kernel" format-patch -q --zero-commit --no-signature -N -o "$PB" "$BK_BASE..HEAD"
  ls "$P" "$PB"
  exit 0
fi

[ -n "${ANYBOOK_IN_KERNEL_CONTAINER:-}" ] || exec "$R/scripts/kernel-docker.sh" "$R/scripts/kernel-amd-apply.sh" "$@"
cd "$S/common"
want=$(cat "$P"/*.patch | git patch-id --stable | cut -d' ' -f1)
have=$(git log --reverse -p --format='commit %H' "$BASE..HEAD" | git patch-id --stable | cut -d' ' -f1)
if [ -n "$have" ] && [ "$want" = "$have" ] && git diff --quiet HEAD; then
  echo "### common: patches already applied on $T ($BASE)"
else
  git checkout -q --detach "$BASE"
  for f in "$P"/*.patch; do
    GIT_COMMITTER_NAME="AnyBook kernel-amd-apply.sh" GIT_COMMITTER_EMAIL=noreply@anybook.invalid \
      GIT_COMMITTER_DATE=2026-10-16T12:00:00+00:00 git am -q "$f"
  done
fi
echo "### common: $T base ${BASE:0:12} + $(git rev-list --count "$BASE..HEAD") patches -> HEAD $(git rev-parse --short=12 HEAD)"
git log --format='###   %h %s' "$BASE..HEAD"

[ -n "$BK_BASE" ] || { echo "no build/kernel revision in $K/pins/$T.xml" >&2; exit 1; }
cd "$S/build/kernel"
want=$(cat "$PB"/*.patch | git patch-id --stable | cut -d' ' -f1)
have=$(git log --reverse -p --format='commit %H' "$BK_BASE..HEAD" | git patch-id --stable | cut -d' ' -f1)
if [ -n "$have" ] && [ "$want" = "$have" ] && git diff --quiet HEAD; then
  echo "### build/kernel: patches already applied ($BK_BASE)"
else
  git checkout -q --detach "$BK_BASE"
  for f in "$PB"/*.patch; do
    GIT_COMMITTER_NAME="AnyBook kernel-amd-apply.sh" GIT_COMMITTER_EMAIL=noreply@anybook.invalid \
      GIT_COMMITTER_DATE=2026-10-16T12:00:00+00:00 git am -q "$f"
  done
fi
echo "### build/kernel: base ${BK_BASE:0:12} + $(git rev-list --count "$BK_BASE..HEAD") patches -> HEAD $(git rev-parse --short=12 HEAD)"
cd "$S"

mkdir -p "$S/devices/anybook"
rsync -a --delete "$R/kernel/devices/anybook/" "$S/devices/anybook/"
echo "### devices/anybook: $(ls "$S/devices/anybook" | tr '\n' ' ')"
"$R/scripts/kernel-nouveau-apply.sh" "$S"
"$R/scripts/kernel-nvidia-open-apply.sh" "$S"
