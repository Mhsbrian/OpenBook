#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# The provenance gate for NVIDIA app support (ANAL-324, ANAL-327; docs/nvk-openbook.md §2). Two checks:
#  1. mesa/nvk-rm-clean/scripts/scan.py, the clean-room tree's own scanner, reports 0 hits on every path below. It
#     refuses any line that names a library of NVIDIA's closed userspace driver, a section-tagged binary address, a
#     binary-analysis or capture method, or that describes what that driver does.
#  2. Every file taken from the clean-room commit is that commit's file, byte for byte (mesa/nvk-rm-clean/
#     clean-commit.txt: git blob IDs), so the code here is exactly the code ANAL-326 tested.
# scripts/mesa-android-build.sh runs it before it builds the nvk-rm-clean tree, and scripts/nvk-stage.sh before it
# stages the driver package. Run it before every commit that touches these paths.
#   scripts/nvk-provenance-check.sh [--quiet]
set -euo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
SCAN=$R/mesa/nvk-rm-clean/scripts/scan.py
MANIFEST=$R/mesa/nvk-rm-clean/clean-commit.txt
q=; [ "${1:-}" = --quiet ] && q=1
# Every path of NVIDIA app support: the driver and its patches, the driver package, the ANGLE patch the package's
# ANGLE carries, and the scripts and document that build, stage, test and describe them.
ROOTS=(
  mesa/nvk-rm-clean
  mesa/patches/nvk
  mesa/patches/nvk-rm-clean
  device/anybook/common/nvk
  aosp/patches/external/angle
  scripts/nvk-stage.sh
  scripts/nvk-provenance-check.sh
  scripts/graphics/nvk-package-hosttest.sh
  docs/nvk-openbook.md
)
fail=0
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
for r in "${ROOTS[@]}"; do
  p=$R/$r
  [ -e "$p" ] || { echo "nvk-provenance: missing $r" >&2; fail=1; continue; }
  if [ -d "$p" ]; then root=$p; else mkdir -p "$tmp/$r"; cp "$p" "$tmp/$r/"; root=$tmp/$r; fi
  if out=$(python3 -I "$SCAN" "$root"); then
    [ -n "$q" ] || echo "scan $r: ${out##*$'\n'}"
  else
    echo "$out" | sed "s|^|$r: |" >&2; fail=1
  fi
done

# The scanner itself is the clean-room commit's (its own rules are not scanned).
n=0; bad=0
while IFS=$'\t' read -r blob cpath opath check; do
  case $blob in '#'*|'') continue ;; esac
  n=$((n + 1))
  case $check in
    exact)
      if [ ! -f "$R/$opath" ] || [ "$(git hash-object "$R/$opath")" != "$blob" ]; then
        echo "nvk-provenance: $opath is not the clean-room commit's $cpath ($blob)" >&2; bad=$((bad + 1))
      fi ;;
    prefix:*)
      if [ "$(head -c "${check#prefix:}" "$R/$opath" | git hash-object --stdin)" != "$blob" ]; then
        echo "nvk-provenance: $opath does not start with the clean-room commit's $cpath ($blob)" >&2; bad=$((bad + 1))
      fi ;;
    not-imported) ;;
    *) echo "nvk-provenance: unknown check '$check' for $cpath" >&2; bad=$((bad + 1)) ;;
  esac
done < "$MANIFEST"
# Nothing else in the imported paths: a file there that the commit does not have must be OpenBook's, listed here.
OWN=(mesa/nvk-rm-clean/README.md mesa/nvk-rm-clean/clean-commit.txt)
while IFS= read -r f; do
  rel=${f#"$R"/}
  grep -qF "$(printf '\t%s\t' "$rel")" "$MANIFEST" && continue
  printf '%s\n' "${OWN[@]}" | grep -qxF "$rel" && continue
  echo "nvk-provenance: $rel is in an imported path but not in the clean-room commit (clean-commit.txt)" >&2
  bad=$((bad + 1))
done < <(find "$R/mesa/nvk-rm-clean" "$R/mesa/patches/nvk" "$R/mesa/patches/nvk-rm-clean" -type f \
           -not -path '*/target/*' | sort)
[ -n "$q" ] || echo "clean-room files: $n listed, $bad mismatched"
[ "$bad" = 0 ] || fail=1
if [ "$fail" != 0 ]; then echo "nvk-provenance: FAILED" >&2; exit 1; fi
[ -n "$q" ] || echo "nvk-provenance: OK"
