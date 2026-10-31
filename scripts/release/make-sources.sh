#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The GPL/LGPL source offer for one OpenBook release (docs/RELEASE.md §7, INSTALL.md §9 item 7, ANAL-320): the
# corresponding source of every copyleft component in the image, as tarballs to publish next to the image.
#   openbook-<V>-source-kernel.tar.xz     the kernel exactly as built: Google's common tree with OpenBook's commits
#                                         (working tree of the Kleaf workspace that built the shipped kernel),
#                                         build/kernel (Kleaf, with OpenBook's commit), devices/anybook (OpenBook's
#                                         modules, nouveau, NVIDIA's open modules), the pinned manifest and the
#                                         patch series against the public revisions
#   openbook-<V>-source-userspace.tar.xz  the AOSP projects whose binaries in the image are GPL or LGPL, as checked
#                                         out and built (working trees, so applied patches are included), plus
#                                         elfutils (Mesa's libelf, LGPL-3.0+) and Mesa itself, as built
#   openbook-<V>-source-systemd-boot.tar.xz  systemd's source at the loader's version and Arch's packaging of it
#                                         (systemd-boot on the ESP, LGPL-2.1+), as downloaded from upstream
#   SOURCES.md, SHA256SUMS                what is where and why; aosp-manifest.xml (every AOSP project's revision)
# The copyleft list comes from the image's own NOTICE files (scripts/release/notice-scan.py), so a new GPL binary in
# a later build is reported, not missed. Files only, under --out; nothing is uploaded.
#
# usage: make-sources.sh --version V --image IMG [--kernel-ws DIR] [--out DIR]
#   --image      the live image (its .build.json and .img.json name the build and the loader version)
#   --kernel-ws  the Kleaf workspace that built the image's kernel (default: found by the kernel release's commit
#                among <data dir>/kernel/*/ws and <data dir>/kernel/src)
# Needs network for the systemd sources (GitHub, gitlab.archlinux.org). Log: <data dir>/logs/release/sources-<V>-<UTC>.log
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$A/aosp/src; P=$S/out/target/product/anybook_g14
VER=; IMG=; KWS=; OUT=
while [ $# -gt 0 ]; do
  case $1 in
    --version) VER=$2; shift 2 ;;
    --image) IMG=$(realpath "$2"); shift 2 ;;
    --kernel-ws) KWS=$(realpath "$2"); shift 2 ;;
    --out) OUT=$(realpath -m "$2"); shift 2 ;;
    -h|--help) sed -n '3,22p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
die() { echo "make-sources: $*" >&2; exit 1; }
[ -n "$VER" ] || die "--version is required"
[ -n "$IMG" ] && [ -f "${IMG%.img}.build.json" ] || die "--image: a live image with its .build.json"
OUT=${OUT:-$A/release/out/$VER/sources}
W=$A/release/work/sources-$VER
mkdir -p "$OUT" "$A/logs/release"
LOG=$A/logs/release/sources-$VER-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee -a "$LOG") 2>&1
BJ=${IMG%.img}.build.json
EPOCH=$(jq -r .epoch "$BJ"); KREL=$(jq -r .kernel_release "$BJ"); LOADER=$(jq -r .loader "$BJ")
KSHA=${KREL##*-g}
echo "== make-sources.sh $VER ($(date -u +%FT%TZ)), image $(basename "$IMG"), kernel $KREL, $LOADER"
TAR=(tar --sort=name --mtime="@$EPOCH" --owner=0 --group=0 --numeric-owner --format=gnu)
pack() { # pack NAME DIR: deterministic tar of DIR's contents under NAME/, xz -9
  "${TAR[@]}" -C "$2" --transform "s,^\.,$1," -cf - . | xz -T0 -9 > "$OUT/$1.tar.xz.tmp"
  mv "$OUT/$1.tar.xz.tmp" "$OUT/$1.tar.xz"
  echo "   $1.tar.xz: $(stat -c %s "$OUT/$1.tar.xz") bytes"
}
copytree() { # copytree SRC DEST: the working tree without .git (applied patches included)
  mkdir -p "$2"
  (cd "$1" && "${TAR[@]}" --exclude=.git --exclude=.repo -cf - .) | tar -C "$2" -xf -
}
rm -rf "$W"; mkdir -p "$W"

# 1. the kernel
if [ -z "$KWS" ]; then
  for c in "$A"/kernel/*/ws "$A"/kernel/src; do
    [ -d "$c/common/.git" ] || [ -f "$c/common/.git" ] || continue
    if [ "$(git -C "$c/common" rev-parse --short=12 HEAD 2>/dev/null)" = "$KSHA" ]; then KWS=$c; break; fi
  done
fi
[ -n "$KWS" ] || die "no Kleaf workspace has common/ at $KSHA (the image's kernel); pass --kernel-ws"
[ "$(git -C "$KWS/common" rev-parse --short=12 HEAD)" = "$KSHA" ] || die "$KWS/common is not at $KSHA"
[ -z "$(git -C "$KWS/common" status --porcelain)" ] || die "$KWS/common has uncommitted changes; the source would not match"
DIST=$(jq -r '.kernel_dist // empty' "$BJ" 2>/dev/null || true)
DIST=${DIST:-$(sed -n 's/^kernel: kernel dist: //p' "${IMG%.img}.img.provenance.txt" 2>/dev/null || true)}
DIST=${DIST:-$(sed -n 's/^kernel dist: //p' "$S/vendor/anybook/g14-kernel/PROVENANCE.txt")}
[ -f "$DIST/manifest-pinned.xml" ] || die "no manifest-pinned.xml in the kernel dist $DIST"
echo "-- kernel: $KWS (common $KSHA), dist $DIST"
K=$W/kernel
copytree "$KWS/common" "$K/common"
copytree "$KWS/build/kernel" "$K/build/kernel"
copytree "$KWS/devices/anybook" "$K/devices/anybook"
mkdir -p "$K/provenance/patches"
cp "$DIST/manifest-pinned.xml" "$DIST/common-provenance.txt" "$DIST/gki-info.txt" "$K/provenance/"
BASE=$(sed -n 's/.*name="kernel\/common" path="common" revision="\([0-9a-f]*\)".*/\1/p' "$DIST/manifest-pinned.xml")
KBASE=$(sed -n 's/.*name="kernel\/build" path="build\/kernel" revision="\([0-9a-f]*\)".*/\1/p' "$DIST/manifest-pinned.xml")
git -C "$KWS/common" format-patch -q -o "$K/provenance/patches/common" "$BASE..HEAD"
git -C "$KWS/build/kernel" format-patch -q -o "$K/provenance/patches/build-kernel" "$KBASE..HEAD"
{
  echo "kernel release: $KREL"
  echo "common: $(git -C "$KWS/common" rev-parse HEAD) = public $BASE + $(git -C "$KWS/common" rev-list --count "$BASE..HEAD") OpenBook commits (patches/common)"
  echo "build/kernel: $(git -C "$KWS/build/kernel" rev-parse HEAD) = public $KBASE + $(git -C "$KWS/build/kernel" rev-list --count "$KBASE..HEAD") OpenBook commits (patches/build-kernel)"
  find "$KWS/devices/anybook" -name .git -prune -print | sort | while read -r g; do
    d=${g%/.git}; echo "devices/anybook${d#"$KWS/devices/anybook"}: $(git -C "$d" rev-parse HEAD) $(git -C "$d" describe --tags --always 2>/dev/null)"
  done
  echo "Every other project of the Kleaf workspace (toolchains, build tools) is public at manifest-pinned.xml's revisions."
} > "$K/provenance/REVISIONS.txt"
pack "openbook-$VER-source-kernel" "$K"

# 2. userspace: the image's own copyleft list
echo "-- userspace copyleft components from the image's NOTICE files"
python3 "$R/scripts/release/notice-scan.py" "$P" "$S" --json "$W/notice-scan.json" > "$W/notice-scan.txt"
cat "$W/notice-scan.txt"
U=$W/userspace
while read -r proj; do
  copytree "$S/$proj" "$U/aosp/$proj"
  echo "$proj $(git -C "$S/$proj" rev-parse HEAD)$( [ -n "$(git -C "$S/$proj" status --porcelain)" ] && echo ' (working tree with applied patches)')" >> "$U/REVISIONS.txt"
done < <(jq -r '.source_projects[]' "$W/notice-scan.json")
MP=$(sed -n 's/^from: //p' "$S/vendor/anybook/mesa/PROVENANCE.txt"); MS=${MP%/out/*}/src
[ -d "$MS/deps/elfutils" ] && [ -d "$MS/upstream" ] || die "Mesa's sources not found at $MS (from vendor/anybook/mesa/PROVENANCE.txt)"
copytree "$MS/deps/elfutils" "$U/mesa-build/elfutils"
copytree "$MS/upstream" "$U/mesa-build/mesa"
cp "$S/vendor/anybook/mesa/PROVENANCE.txt" "$U/mesa-build/PROVENANCE.txt"
echo "mesa-build/elfutils $(git -C "$MS/deps/elfutils" rev-parse HEAD) (libelf_mesa.so, LGPL-3.0+ / GPL-2.0+)" >> "$U/REVISIONS.txt"
echo "mesa-build/mesa $(git -C "$MS/upstream" rev-parse HEAD) (Mesa, MIT; for relinking against a changed libelf)" >> "$U/REVISIONS.txt"
pack "openbook-$VER-source-userspace" "$U"

# 3. systemd-boot
SV=$(echo "$LOADER" | sed -n 's/^systemd-boot \([0-9][0-9.]*\)-\([0-9]*\)$/\1 \2/p')
[ -n "$SV" ] || die "can't read the loader version from '$LOADER'"
set -- $SV; SYSV=$1; SYSR=$2
echo "-- systemd-boot: systemd v$SYSV, Arch packaging $SYSV-$SYSR"
D=$W/download; mkdir -p "$D"   # downloaded files are data: only hashed and repacked, never run
curl -fsSL --retry 3 -o "$D/systemd-$SYSV.tar.gz" "https://github.com/systemd/systemd/archive/refs/tags/v$SYSV.tar.gz"
curl -fsSL --retry 3 -o "$D/arch-systemd-$SYSV-$SYSR.tar.gz" \
  "https://gitlab.archlinux.org/archlinux/packaging/packages/systemd/-/archive/$SYSV-$SYSR/systemd-$SYSV-$SYSR.tar.gz"
B=$W/systemd-boot; mkdir -p "$B"
cp "$D/systemd-$SYSV.tar.gz" "$D/arch-systemd-$SYSV-$SYSR.tar.gz" "$B/"
(cd "$B" && sha256sum ./*.tar.gz > SHA256SUMS.download)
{
  echo "systemd-boot on the image's ESP comes from Arch Linux's systemd $SYSV-$SYSR package (the openbook-installer"
  echo "container, tools/Dockerfile.installer). systemd-$SYSV.tar.gz is upstream's v$SYSV tag; arch-systemd-$SYSV-$SYSR.tar.gz"
  echo "is Arch's packaging (PKGBUILD and its patches) at the $SYSV-$SYSR tag. Downloaded $(date -u +%F) from:"
  echo "  https://github.com/systemd/systemd/archive/refs/tags/v$SYSV.tar.gz"
  echo "  https://gitlab.archlinux.org/archlinux/packaging/packages/systemd/-/archive/$SYSV-$SYSR/systemd-$SYSV-$SYSR.tar.gz"
} > "$B/README.txt"
pack "openbook-$VER-source-systemd-boot" "$B"

# 4. the record
# repo runs in the AOSP container, with the local mirror the tree's git alternates point into, and no trace file
docker run --rm -u "$(id -u):$(id -g)" -e REPO_TRACE=0 -v "$A/aosp:/aosp:ro" -w /aosp/src anybook-aosp \
  repo manifest -r -o - > "$OUT/aosp-manifest.xml"
[ -s "$OUT/aosp-manifest.xml" ] || die "could not write aosp-manifest.xml"
python3 - "$W/notice-scan.json" "$OUT" "$VER" "$KREL" "$K/provenance/REVISIONS.txt" "$U/REVISIONS.txt" "$LOADER" <<'PY'
import json, os, sys
scan, out, ver, krel, krev, urev, loader = sys.argv[1:]
s = json.load(open(scan))
L = [f"# Source for OpenBook {ver}", "",
     "OpenBook's image contains software under the GNU GPL and LGPL. This is its complete corresponding source,",
     "published next to the image so you can get it from the same place. OpenBook's own code is in",
     "https://github.com/Mhsbrian/OpenBook (Apache-2.0).", "",
     "| File | What it is |", "|---|---|",
     f"| `openbook-{ver}-source-kernel.tar.xz` | Linux {krel}: Google's Android common kernel with OpenBook's commits, the Kleaf build files with OpenBook's commit, OpenBook's kernel modules, nouveau and NVIDIA's open modules (Dual MIT/GPL), the pinned manifest and the patch series. Build: `docs/kernel.md` in the OpenBook repository |",
     f"| `openbook-{ver}-source-userspace.tar.xz` | the Android projects below, as built, and Mesa's libelf (elfutils, LGPL-3.0+) with Mesa itself |",
     f"| `openbook-{ver}-source-systemd-boot.tar.xz` | {loader} (LGPL-2.1+): systemd's upstream source and Arch Linux's packaging |",
     "| `aosp-manifest.xml` | every Android project in the build, at its exact revision (all public at android.googlesource.com) |", "",
     "## Kernel revisions", "", "```", open(krev).read().rstrip(), "```", "",
     "## Userspace: copyleft binaries in the image, and their source", "",
     "From the image's own NOTICE files (`scripts/release/notice-scan.py`).", "",
     "| Source | Licence texts | Binaries in the image |", "|---|---|---|"]
for p in s["included"]:
    L.append(f"| `{p['project']}` | {p['kinds']} | {', '.join('`'+f+'`' for f in p['files'][:6])}{' …' if len(p['files']) > 6 else ''} |")
L += ["", "```", open(urev).read().rstrip(), "```", "",
      "## Licence texts that name the GPL but need no source here", "",
      "These binaries' notices carry a GPL or LGPL text for a component that is not under it in the binary, so the",
      "source is not included above. All of it is public at the revisions in `aosp-manifest.xml`.", "",
      "| Source | Binaries | Why |", "|---|---|---|"]
for p in s["not_included"]:
    L.append(f"| `{p['project']}` | {len(p['files'])}: {', '.join('`'+f+'`' for f in p['files'][:3])}{' …' if len(p['files']) > 3 else ''} | {p['why']} |")
L += ["", "If something here is missing or wrong, open an issue at https://github.com/Mhsbrian/OpenBook/issues and we will",
      "publish it. This offer is valid for three years from the release date, for anyone who has the image."]
open(os.path.join(out, "SOURCES.md"), "w").write("\n".join(L) + "\n")
PY
(cd "$OUT" && sha256sum openbook-"$VER"-source-*.tar.xz aosp-manifest.xml SOURCES.md > SHA256SUMS)
rm -rf "$W"
echo "-- done: $OUT"; ls -l "$OUT"; echo "log: $LOG"
