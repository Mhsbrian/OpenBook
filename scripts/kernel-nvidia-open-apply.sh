#!/usr/bin/env bash
# Prepare the external build of NVIDIA's open kernel modules (ANAL-297) in a kernel tree that kernel-amd-apply.sh made:
#   1. take open-gpu-kernel-modules at kernel/patches/nvidia-open/PIN from a local mirror (no network here) and check
#      the commit and its tree;
#   2. <tree>/devices/anybook/nvidia_open becomes a git repository of its own: the package files from
#      kernel/devices/anybook/nvidia_open plus that source as open-gpu-kernel-modules/, then
#      kernel/patches/nvidia-open/*.patch as commits (fixed committer and dates, so HEAD is the same everywhere).
#      kernel-build.sh adds it to KLEAF_EXTRA_GIT_PROJECTS, and Kleaf stamps HEAD into the modules as scmversion;
#   3. check the patched source against kernel/patches/nvidia-open/TREE.
# Run after kernel-nouveau-apply.sh, whose rsync --delete of devices/anybook would remove this checkout.
# Idempotent: an existing nvidia_open/ is replaced.
#
# usage: kernel-nvidia-open-apply.sh [TREE]   TREE defaults to $ANYBOOK_KERNEL_SRC or ~/anybook/kernel/src
# env:   ANYBOOK_NVIDIA_OPEN_GIT  the mirror (default ~/anybook/kernel/upstream/open-gpu-kernel-modules.git), made once
#        on the host with: git clone --bare --depth 1 --branch <tag> https://github.com/NVIDIA/open-gpu-kernel-modules.git
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}
S=$(realpath "${1:-${ANYBOOK_KERNEL_SRC:-$A/kernel/src}}")
P=$R/kernel/patches/nvidia-open
MIRROR=${ANYBOOK_NVIDIA_OPEN_GIT:-$A/kernel/upstream/open-gpu-kernel-modules.git}
read -r TAG COMMIT PTREE < <(grep -v '^#' "$P/PIN")
TREE=$(cat "$P/TREE")
V=$S/devices/anybook/nvidia_open

[ -d "$MIRROR" ] || { echo "no mirror at $MIRROR; see the header of $0" >&2; exit 1; }
got=$(git -C "$MIRROR" rev-parse "$TAG^{commit}") || { echo "$MIRROR has no tag $TAG" >&2; exit 1; }
[ "$got" = "$COMMIT" ] || { echo "tag $TAG is $got in $MIRROR, expected $COMMIT" >&2; exit 1; }
got=$(git -C "$MIRROR" rev-parse "$COMMIT^{tree}")
[ "$got" = "$PTREE" ] || { echo "commit $COMMIT has tree $got, expected $PTREE" >&2; exit 1; }

rm -rf "${V:?}"
mkdir -p "$V/open-gpu-kernel-modules"
rsync -a "$R/kernel/devices/anybook/nvidia_open/" "$V/"
git -C "$MIRROR" archive "$COMMIT" | tar -x -C "$V/open-gpu-kernel-modules"
export GIT_AUTHOR_NAME="AnyBook kernel-nvidia-open-apply.sh" GIT_AUTHOR_EMAIL=noreply@anybook.invalid
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME" GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
export GIT_AUTHOR_DATE=2026-10-26T00:00:00+00:00 GIT_COMMITTER_DATE=2026-10-26T00:00:00+00:00
git -C "$V" init -q -b anal297
git -C "$V" add -A
git -C "$V" commit -q --no-gpg-sign -m "nvidia_open: AnyBook package files; open-gpu-kernel-modules/ is NVIDIA's $TAG ($COMMIT)"
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_AUTHOR_DATE
for f in "$P"/[0-9]*.patch; do git -C "$V" am -q --no-gpg-sign --directory=open-gpu-kernel-modules "$f"; done

got=$(git -C "$V" rev-parse 'HEAD:open-gpu-kernel-modules')
[ "$got" = "$TREE" ] || { echo "patched open-gpu-kernel-modules tree is $got, expected $TREE" >&2; exit 1; }
echo "### devices/anybook/nvidia_open: NVIDIA $TAG + $(($(git -C "$V" rev-list --count HEAD) - 1)) patches -> HEAD $(git -C "$V" rev-parse --short=12 HEAD), tree $got"
