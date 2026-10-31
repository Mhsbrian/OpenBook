#!/usr/bin/env bash
# Put AnyBook's changes to AOSP projects on top of the synced tree:
#   aosp/patches/<project path>/*.patch -> commits on a detached HEAD at the project's pinned revision
#   (evidence/2026-10-15-aosp/manifest-pinned.xml.gz), applied with git am, a fixed committer and date,
#   so the resulting SHAs are reproducible. Idempotent: rerun after every repo sync, which resets each
#   project to its pin. scripts/aosp-build.sh runs it before every build.
#   aosp/patches/<project path>/IMPORT (optional; lines "url URL" and "rev SHA") replaces the project's tree with
#   that commit of another repository first (ANAL-200: the Digitalis fork of frameworks/libs/binary_translation).
#   The import is one commit on top of the pin, with the same fixed author, committer and date, so its SHA is
#   reproducible too, and the patches apply on top of it. The commit is fetched from URL once if it is missing.
# The tree is shared by the branches that take turns building in it, so a project another branch patched stays
# patched for the next build. Projects this checkout has no patches for are put back on their pin when the commits
# above it are this script's own (their patch files live in that other branch), and reported otherwise.
#
# usage: aosp-patches.sh                     apply (default)
#        aosp-patches.sh --export PROJECT    write PROJECT's commits above its pin back to aosp/patches/
# Env: AOSP_SRC (default /aosp/src inside anybook-aosp, else ~/anybook/aosp/src)
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
if [ -n "${AOSP_SRC:-}" ]; then T=$AOSP_SRC; elif [ -d /aosp/src/.repo ]; then T=/aosp/src; else T=${ANYBOOK_HOME:-$HOME/anybook}/aosp/src; fi
P=$R/aosp/patches
PIN=$R/evidence/2026-10-15-aosp/manifest-pinned.xml.gz

pin_of(){ zcat "$PIN" | sed -n "s/.* path=\"$(printf '%s' "$1" | sed 's/[.[\/]/\\&/g')\" revision=\"\([0-9a-f]\{40\}\)\".*/\1/p" | head -1; }
ME=(env GIT_AUTHOR_NAME="AnyBook aosp-patches.sh" GIT_AUTHOR_EMAIL=noreply@anybook.invalid GIT_AUTHOR_DATE=2026-10-16T12:00:00+00:00
    GIT_COMMITTER_NAME="AnyBook aosp-patches.sh" GIT_COMMITTER_EMAIL=noreply@anybook.invalid GIT_COMMITTER_DATE=2026-10-16T12:00:00+00:00)
# base_of DIR PIN: the commit DIR's patches apply to: PIN, or the import commit on top of it (run inside the project).
base_of(){
  local f=$P/$1/IMPORT url rev
  [ -f "$f" ] || { echo "$2"; return; }
  url=$(awk '$1 == "url" { print $2 }' "$f"); rev=$(awk '$1 == "rev" { print $2 }' "$f")
  [ -n "$url" ] && [ ${#rev} = 40 ] || { echo "$f: needs 'url URL' and 'rev <40-hex SHA>'" >&2; return 1; }
  git cat-file -e "$rev^{commit}" 2>/dev/null || git fetch -q --no-tags "$url" "$rev" >&2
  "${ME[@]}" git commit-tree "$rev^{tree}" -p "$2" -m "ANYBOOK: import $url $rev" \
    -m "aosp-patches.sh replaces this project's tree with that commit (aosp/patches/$1/IMPORT)."
}

if [ "${1:-}" = --export ]; then
  proj=${2:?usage: aosp-patches.sh --export PROJECT}; base=$(pin_of "$proj")
  [ -n "$base" ] || { echo "$proj is not in $PIN" >&2; exit 1; }
  base=$(cd "$T/$proj" && base_of "$proj" "$base")
  mkdir -p "$P/$proj"; rm -f "$P/$proj"/*.patch
  git -C "$T/$proj" format-patch -q --zero-commit --no-signature -N -o "$P/$proj" "$base..HEAD"
  ls "$P/$proj"
  exit 0
fi

DIRS=$(cd "$P" && find . \( -name '*.patch' -o -name IMPORT \) -printf '%h\n' | sed 's|^\./||' | sort -u)
for dir in $DIRS; do
  pin=$(pin_of "$dir")
  [ -n "$pin" ] || { echo "$dir is not in $PIN" >&2; exit 1; }
  cd "$T/$dir"
  base=$(base_of "$dir" "$pin")
  [ "$base" = "$pin" ] || echo "### $dir: pin ${pin:0:12} + import $(git log -1 --format=%s "$base" | sed 's/.* //' | cut -c1-12) -> ${base:0:12}"
  want=$({ cat "$P/$dir"/*.patch 2>/dev/null || true; } | git patch-id --stable | cut -d' ' -f1)
  have=$(git merge-base --is-ancestor "$base" HEAD 2>/dev/null &&
         git log --reverse -p --format='commit %H' "$base..HEAD" | git patch-id --stable | cut -d' ' -f1) || have=none
  if [ "$have" != none ] && [ "$want" = "$have" ] && git diff --quiet HEAD; then
    echo "### $dir: patches already applied (${base:0:12})"
  else
    git diff --quiet HEAD || { echo "### $dir has uncommitted changes; not touching it" >&2; exit 1; }
    git checkout -q --detach "$base"
    for f in "$P/$dir"/*.patch; do
      [ -e "$f" ] || continue
      GIT_COMMITTER_NAME="AnyBook aosp-patches.sh" GIT_COMMITTER_EMAIL=noreply@anybook.invalid \
        GIT_COMMITTER_DATE=2026-10-16T12:00:00+00:00 git am -q "$f"
    done
  fi
  echo "### $dir: base ${base:0:12} + $(git rev-list --count "$base..HEAD") patches -> HEAD $(git rev-parse --short=12 HEAD)"
  git log --format='###   %h %s' "$base..HEAD"
done

# Patches other checkouts left in the shared tree.
OURS=" $(echo $DIRS) "
while read -r dir base <&3; do
  case "$OURS" in *" $dir "*) continue ;; esac
  [ -e "$T/$dir/.git" ] || continue
  head=$(git -C "$T/$dir" rev-parse -q --verify HEAD 2>/dev/null) || continue
  [ "$head" != "$base" ] || continue
  if [ "$(git -C "$T/$dir" log --format=%cn "$base..HEAD" | sort -u)" = "AnyBook aosp-patches.sh" ] &&
     git -C "$T/$dir" diff --quiet HEAD; then
    git -C "$T/$dir" checkout -q --detach "$base"
    echo "### $dir: back on its pin ${base:0:12} (another checkout's patches; this one has none for it)"
  else
    echo "### WARNING: $dir is at ${head:0:12}, not its pin ${base:0:12}, and this checkout has no patches for it;" \
      "it is built as it is" >&2
  fi
done 3< <(zcat "$PIN" | sed -n 's/.* path="\([^"]*\)" revision="\([0-9a-f]\{40\}\)".*/\1 \2/p')
