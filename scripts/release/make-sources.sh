#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The GPL/LGPL source offer for one OpenBook release (docs/RELEASE.md §7, INSTALL.md §9 item 7, ANAL-320, ANAL-341):
# the corresponding source of every copyleft component in the image, with the scripts and configuration that
# compiled and installed it, as tarballs to publish next to the image. It must stand on its own: nothing in it may
# point at OpenBook's development repository, which is private.
#   openbook-<V>-source-kernel.tar.xz     the kernel exactly as built: Google's common tree with OpenBook's commits
#                                         (working tree of the Kleaf workspace that built the shipped kernel),
#                                         build/kernel (Kleaf, with OpenBook's commit), devices/anybook (OpenBook's
#                                         modules, nouveau, NVIDIA's open modules), the pinned manifest, the patch
#                                         series against the public revisions and the build command
#   openbook-<V>-source-userspace.tar.xz  the AOSP projects whose binaries in the image are GPL or LGPL, as checked
#                                         out and built (working trees, so applied patches are included), plus
#                                         elfutils (Mesa's libelf, LGPL-3.0+) and Mesa itself, as built
#   openbook-<V>-source-systemd-boot.tar.xz  systemd's source at the loader's version and Arch's packaging of it
#                                         (systemd-boot on the ESP, LGPL-2.1+), as downloaded from upstream
#   openbook-<V>-source-build.tar.xz      OpenBook's own scripts and configuration that built and installed those
#                                         parts (scripts/release/source-build-files.txt), at the image's commit
#   SOURCES.md, SHA256SUMS                what is where, and how to build it from these files and public sources only;
#                                         aosp-manifest.xml (every AOSP project's revision)
# The owner's attribution in patch headers and trailers is written with the owner's public identity (the repository's
# git identity, ANAL-319); upstream authors are kept. Every output is then searched for a private identity with
# scripts/release/identity-scan.py, and the script fails on a hit or when no identity list exists.
# The copyleft list comes from the image's own NOTICE files (scripts/release/notice-scan.py), so a new GPL binary in
# a later build is reported, not missed. Files only, under --out; nothing is uploaded.
#
# usage: make-sources.sh --version V --image IMG [--kernel-ws DIR] [--out DIR] [--reuse DIR] [--notice-root DIR]
#                        [--home URL] [--contact URL] [--mesa-note FILE] [--install-note FILE]
#   --image        the live image (its .build.json and .img.json name the build, the commit and the loader version)
#   --kernel-ws    the Kleaf workspace that built the image's kernel (default: found by the kernel release's commit
#                  among <data dir>/kernel/*/ws and <data dir>/kernel/src)
#   --reuse DIR    an earlier source folder of this version: its userspace and systemd-boot tarballs are kept
#                  byte for byte when DIR/SHA256SUMS lists them, their hashes match, and the userspace tarball holds
#                  exactly the projects the image's NOTICE files name (for when the AOSP tree has moved on)
#   --notice-root  a directory with the image's {system,system_ext,product,vendor}/etc/NOTICE.xml.gz (default:
#                  read from the image itself with image-notice.py)
#   --home URL     where the release files are published (default https://github.com/Mhsbrian/openbook-releases)
#   --contact URL  where to ask for missing source (default <home>/issues)
#   --mesa-note FILE  Markdown added to SOURCES.md's Mesa section: what a rebuild from these files was checked to give
#   --install-note FILE  the same for the kernel install section
# Needs network for the systemd sources (GitHub, gitlab.archlinux.org). Log: <data dir>/logs/release/sources-<V>-<UTC>.log
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
S=$A/aosp/src; P=$S/out/target/product/anybook_g14
VER=; IMG=; KWS=; OUT=; REUSE=; NROOT=; MNOTE=; INOTE=
HOME_URL=https://github.com/Mhsbrian/openbook-releases; CONTACT=
while [ $# -gt 0 ]; do
  case $1 in
    --version) VER=$2; shift 2 ;;
    --image) IMG=$(realpath "$2"); shift 2 ;;
    --kernel-ws) KWS=$(realpath "$2"); shift 2 ;;
    --out) OUT=$(realpath -m "$2"); shift 2 ;;
    --reuse) REUSE=$(realpath "$2"); shift 2 ;;
    --notice-root) NROOT=$(realpath "$2"); shift 2 ;;
    --home) HOME_URL=${2%/}; shift 2 ;;
    --contact) CONTACT=$2; shift 2 ;;
    --mesa-note) MNOTE=$(realpath "$2"); shift 2 ;;
    --install-note) INOTE=$(realpath "$2"); shift 2 ;;
    -h|--help) sed -n '3,43p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
die() { echo "make-sources: $*" >&2; exit 1; }
[ -n "$VER" ] || die "--version is required"
[ -n "$IMG" ] && [ -f "${IMG%.img}.build.json" ] || die "--image: a live image with its .build.json"
CONTACT=${CONTACT:-$HOME_URL/issues}
OUT=${OUT:-$A/release/out/$VER/sources}
[ "$OUT" != "$REUSE" ] || die "--out and --reuse must differ"
W=$A/release/work/sources-$VER
mkdir -p "$OUT" "$A/logs/release"
LOG=$A/logs/release/sources-$VER-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee -a "$LOG") 2>&1
BJ=${IMG%.img}.build.json
EPOCH=$(jq -r .epoch "$BJ"); KREL=$(jq -r .kernel_release "$BJ"); LOADER=$(jq -r .loader "$BJ")
COMMIT=$(jq -r '.repo.commit // empty' "$BJ"); [ "$(jq -r '.repo.dirty' "$BJ")" = false ] || die "the image was built from a dirty tree"
KSHA=${KREL##*-g}
OWNER_NAME=$(git -C "$R" config user.name); OWNER_EMAIL=$(git -C "$R" config user.email)
case $OWNER_EMAIL in *@users.noreply.github.com) ;; *) die "the repository's git identity is not a no-reply address" ;; esac
ID_SCAN=(python3 "$R/scripts/release/identity-scan.py" --tmp "$W")
python3 - "$R/scripts/release/identity-scan.py" <<'PY' || die "no private identity list: add one with identity-scan.py --add email|word"
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("s", sys.argv[1]); s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s); sys.exit(0 if os.path.exists(s.default_ids()) else 1)
PY
echo "== make-sources.sh $VER ($(date -u +%FT%TZ)), image $(basename "$IMG"), kernel $KREL, $LOADER, commit ${COMMIT:0:12}"
TAR=(tar --sort=name --mtime="@$EPOCH" --owner=0 --group=0 --numeric-owner --format=gnu)
pack() { # pack NAME DIR: deterministic tar of DIR's contents under NAME/, xz -9
  # S: member names only. Without it tar also rewrote symlink targets, and every relative link broke (ANAL-341).
  "${TAR[@]}" -C "$2" --transform "s,^\.,$1,S" -cf - . | xz -T0 -9 > "$OUT/$1.tar.xz.tmp"
  mv "$OUT/$1.tar.xz.tmp" "$OUT/$1.tar.xz"
  echo "   $1.tar.xz: $(stat -c %s "$OUT/$1.tar.xz") bytes"
}
copytree() { # copytree SRC DEST: the working tree without .git (applied patches included)
  mkdir -p "$2"
  (cd "$1" && "${TAR[@]}" --exclude=.git --exclude=.repo -cf - .) | tar -C "$2" -xf -
}
reused() { # reused FILE: DIR's copy, if DIR/SHA256SUMS lists it and the hash matches
  [ -n "$REUSE" ] && [ -f "$REUSE/$1" ] || return 1
  local want name; want=$(awk -v f="$1" '$2==f{print $1}' "$REUSE/SHA256SUMS")
  [ -n "$want" ] || die "--reuse: $1 is not in $REUSE/SHA256SUMS"
  [ "$(sha256sum < "$REUSE/$1" | cut -c1-64)" = "$want" ] || die "--reuse: $1 does not match $REUSE/SHA256SUMS"
  name=${1%.tar.xz}
  if [ "$name" != "$1" ] && tar -tvJf "$REUSE/$1" | awk -v n="$name" '$1 ~ /^l/ && index($NF, n) == 1 {f=1} END {exit !f}'; then
    # made before pack() kept symlink targets: put back the "." the transform replaced, then pack it again
    local d=$W/repair/$name; rm -rf "$d"; mkdir -p "$d"
    tar -C "$d" -xJf "$REUSE/$1" --strip-components=1
    python3 - "$d" "$name" <<'PY2'
import os, sys
root, name = sys.argv[1:]
n = 0
for dp, dns, fns in os.walk(root):
    for f in dns + fns:
        p = os.path.join(dp, f)
        if os.path.islink(p) and os.readlink(p).startswith(name):
            t = "." + os.readlink(p)[len(name):]
            os.unlink(p); os.symlink(t, p); n += 1
print(f"   {n} relative symlinks repaired")
PY2
    pack "$name" "$d"
    echo "   $1: content kept from $REUSE ($want), symlink targets repaired"
    return 0
  fi
  cp --reflink=auto "$REUSE/$1" "$OUT/$1.tmp" && mv "$OUT/$1.tmp" "$OUT/$1"
  echo "   $1: kept from $REUSE ($want)"
}
owner_identity() { # owner_identity PATCH...: the owner's attribution with the public identity; others untouched
  python3 - "$OWNER_NAME" "$OWNER_EMAIL" "$@" <<'PY'
import re, sys
name, email, *files = sys.argv[1:]
line = re.compile(r"^((?:From|[A-Za-z][A-Za-z-]*-by|Co-authored-by|Cc):[ \t]*)" + re.escape(name) + r"[ \t]*<[^>\n]*>", re.M)
n = 0
for f in files:
    s = open(f, encoding="utf-8", errors="surrogateescape").read()
    t, k = line.subn(lambda m: f"{m.group(1)}{name} <{email}>", s)
    if k:
        open(f, "w", encoding="utf-8", errors="surrogateescape").write(t)
    n += k
print(f"   owner attribution: {n} header/trailer lines in {len(files)} patches use {name}'s public identity")
PY
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
# every other project of the workspace must be the public one, clean, at the pin
python3 - "$KWS" "$DIST/manifest-pinned.xml" <<'PY' || die "the Kleaf workspace differs from its pinned manifest"
import subprocess, sys, xml.etree.ElementTree as ET
ws, man = sys.argv[1:]
bad = []
for p in ET.parse(man).getroot().iter("project"):
    path = p.get("path") or p.get("name")
    if path in ("common", "build/kernel"):
        continue
    g = lambda *a: subprocess.run(["git", "-C", f"{ws}/{path}", *a], capture_output=True, text=True).stdout.strip()
    if g("rev-parse", "HEAD") != p.get("revision") or g("status", "--porcelain", "--untracked-files=no"):
        bad.append(path)
print(f"   {sum(1 for _ in ET.parse(man).getroot().iter('project')) - 2} other projects public and clean at the pin"
      if not bad else f"   not at the pin or modified: {bad}")
sys.exit(1 if bad else 0)
PY
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
owner_identity "$K"/provenance/patches/*/*.patch
BCMD=$(sed -n 's/^[[:space:]]*Command being timed: "\(.*\)"$/\1/p' "$DIST/build-time.txt" 2>/dev/null | head -1)
BCMD=${BCMD:-unknown}
BCMD=$(printf '%s' "$BCMD" | sed -E 's/^timeout [0-9]+ //; s/ --destdir=[^ ]*/ --destdir=<dist dir>/')
{
  echo "kernel release: $KREL"
  echo "common: $(git -C "$KWS/common" rev-parse HEAD) = public $BASE + $(git -C "$KWS/common" rev-list --count "$BASE..HEAD") OpenBook commits (patches/common)"
  echo "  tree $(git -C "$KWS/common" rev-parse 'HEAD^{tree}'): git am of patches/common on $BASE gives this tree"
  echo "build/kernel: $(git -C "$KWS/build/kernel" rev-parse HEAD) = public $KBASE + $(git -C "$KWS/build/kernel" rev-list --count "$KBASE..HEAD") OpenBook commits (patches/build-kernel)"
  echo "  tree $(git -C "$KWS/build/kernel" rev-parse 'HEAD^{tree}'): git am of patches/build-kernel on $KBASE gives this tree"
  find "$KWS/devices/anybook" -name .git -prune -print | sort | while read -r g; do
    d=${g%/.git}; echo "devices/anybook${d#"$KWS/devices/anybook"}: $(git -C "$d" rev-parse HEAD) $(git -C "$d" describe --tags --always 2>/dev/null)"
  done
  echo "Every other project of the Kleaf workspace (toolchains, build tools) is public at manifest-pinned.xml's revisions."
  echo "build command, run in the workspace root: $BCMD"
} > "$K/provenance/REVISIONS.txt"
# the patch series, as published, must give the shipped trees: git am on the public revisions
for t in common:"$BASE":patches/common build/kernel:"$KBASE":patches/build-kernel; do
  IFS=: read -r proj base pdir <<< "$t"
  C=$W/am-$(basename "$proj"); git clone -q --shared --no-checkout "$KWS/$proj" "$C"
  git -C "$C" -c advice.detachedHead=false checkout -q "$base"
  git -C "$C" -c gc.auto=0 -c maintenance.auto=false -c user.name=check -c user.email=check@invalid \
    am -q "$K/provenance/$pdir"/*.patch
  [ "$(git -C "$C" rev-parse 'HEAD^{tree}')" = "$(git -C "$KWS/$proj" rev-parse 'HEAD^{tree}')" ] \
    || die "$pdir on $base does not give $proj's tree"
  rm -rf "$C"
done
echo "   patch series checked: git am on the public revisions gives the shipped common and build/kernel trees"
pack "openbook-$VER-source-kernel" "$K"

# 2. userspace: the image's own copyleft list
if [ -z "$NROOT" ]; then
  AOSP_HOST_BIN=${AOSP_HOST_BIN:-$S/out/host/linux-x86/bin} python3 "$R/scripts/release/image-notice.py" "$IMG" "$W/notice" \
    || die "could not read the image's NOTICE files"
  NROOT=$W/notice
fi
echo "-- userspace copyleft components from the image's NOTICE files${NROOT:+ ($NROOT)}"
python3 "$R/scripts/release/notice-scan.py" "$P" "$S" ${NROOT:+--notice-root "$NROOT"} --json "$W/notice-scan.json" > "$W/notice-scan.txt"
cat "$W/notice-scan.txt"
U=$W/userspace; mkdir -p "$U"
if reused "openbook-$VER-source-userspace.tar.xz"; then
  tar -xJf "$OUT/openbook-$VER-source-userspace.tar.xz" -O "openbook-$VER-source-userspace/REVISIONS.txt" > "$U/REVISIONS.txt"
  diff <(jq -r '.source_projects[]' "$W/notice-scan.json" | sort) \
       <(grep -v '^mesa-build/' "$U/REVISIONS.txt" | cut -d' ' -f1 | sort) \
    || die "--reuse: the kept userspace tarball's projects differ from the image's copyleft list"
  echo "   its projects are the image's copyleft list"
else
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
fi

# 3. systemd-boot
SV=$(echo "$LOADER" | sed -n 's/^systemd-boot \([0-9][0-9.]*\)-\([0-9]*\)$/\1 \2/p')
[ -n "$SV" ] || die "can't read the loader version from '$LOADER'"
set -- $SV; SYSV=$1; SYSR=$2
echo "-- systemd-boot: systemd v$SYSV, Arch packaging $SYSV-$SYSR"
if ! reused "openbook-$VER-source-systemd-boot.tar.xz"; then
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
fi

# 4. OpenBook's build and install files, at the commit that built the image
echo "-- build files at ${COMMIT:0:12} (scripts/release/source-build-files.txt)"
[ -n "$COMMIT" ] && git -C "$R" cat-file -e "$COMMIT^{commit}" 2>/dev/null || die "the image's commit '$COMMIT' is not in $R"
mapfile -t SPEC < <(sed -e 's/#.*//' -e 's/[[:space:]]*$//' "$R/scripts/release/source-build-files.txt" | grep -v '^$')
for p in "${SPEC[@]}"; do
  [ -n "$(git -C "$R" ls-tree -r --name-only "$COMMIT" -- "$p")" ] || die "source-build-files.txt: $p is not in $COMMIT"
done
BD=$W/build; mkdir -p "$BD"
git -C "$R" archive --format=tar "$COMMIT" -- "${SPEC[@]}" | tar -C "$BD" -xf -
# OpenBook's own files are published as they are: no home-network address or private identity in them
python3 - "$BD" <<'PY' || die "a build file holds a home-network address"
import os, re, sys
lan = re.compile(rb"(?<![\d.])192\.168\.(?!77\.)\d{1,3}\.\d{1,3}(?![\d.])")
# documented examples, not machines of ours: path -> addresses
EXAMPLES = {"scripts/installer/live-init.c": {b".".join([b"192", b"168", b"1", b"20"])}}  # "e.g. iperf3_server=..." in a comment
bad = []
for d, _, fs in os.walk(sys.argv[1]):
    for f in fs:
        rel = os.path.relpath(os.path.join(d, f), sys.argv[1])
        found = set(lan.findall(open(os.path.join(d, f), "rb").read())) - EXAMPLES.get(rel, set())
        if found:
            bad.append(rel)
print("   home-network addresses: " + (", ".join(bad) if bad else "none"))
sys.exit(1 if bad else 0)
PY
TREE=$(git -C "$R" rev-parse "$COMMIT^{tree}")
echo "-- dependency closure of the build files (source-closure.py)"
python3 "$R/scripts/release/source-closure.py" "$R" "$COMMIT" "$R/scripts/release/source-build-files.txt" \
  "$R/scripts/release/source-build-excluded.txt" > "$W/closure.txt" || { cat "$W/closure.txt"; die "the build files are not closed"; }
tail -1 "$W/closure.txt"
cp "$W/closure.txt" "$BD/CLOSURE.txt"
cp "$R/scripts/release/source-build-excluded.txt" "$BD/EXCLUDED.txt"
# written for the source offer (not used to build the image): the kernel into the image's partitions, public inputs only
mkdir -p "$BD/scripts/release" && cp "$R/scripts/release/kernel-into-image.sh" "$BD/scripts/release/"

# 4b. installing the kernel: the shipped boot images' parameters, read back from the image, and the firmware
# manifests installer-image.sh read when it assembled the image (its LICENSES/firmware/FILES.tsv comes from them)
echo "-- boot-image parameters and installer inputs from the image"
HB=${AOSP_HOST_BIN:-$S/out/host/linux-x86/bin}
for t in avbtool lpdump unpack_bootimg; do [ -x "$HB/$t" ] || die "AOSP host tool $t not found in $HB (set AOSP_HOST_BIN)"; done
python3 - "$IMG" "$W/parts" <<'PY'
import os, struct, sys
img, out = sys.argv[1:]
os.makedirs(out, exist_ok=True)
f = open(img, "rb"); f.seek(512); h = f.read(92)
lba, n, esz = struct.unpack_from("<QII", h, 72); f.seek(lba * 512); t = f.read(n * esz)
for i in range(n):
    e = t[i * esz:(i + 1) * esz]
    if e[:16] == b"\0" * 16:
        continue
    a, b = struct.unpack_from("<QQ", e, 32); name = e[56:128].decode("utf-16le").rstrip("\0")
    if name in ("boot_a", "init_boot_a", "vendor_boot_a", "vbmeta_a", "super", "EFI"):
        f.seek(a * 512); left = (b - a + 1) * 512
        with open(f"{out}/{name}.img", "wb") as o:
            while left:
                d = f.read(min(left, 64 << 20)); o.write(d); left -= len(d)
PY
{
  echo "# The shipped image's boot partitions, as read back from $(basename "$IMG") with AOSP's host tools"
  echo "# (unpack_bootimg --format=mkbootimg prints the mkbootimg arguments that rebuild each image; avbtool"
  echo "# info_image shows each AVB footer and vbmeta; lpdump shows super's logical partitions)."
  for p in boot_a init_boot_a vendor_boot_a; do
    echo; echo "== $p: unpack_bootimg --format=mkbootimg"
    "$HB/unpack_bootimg" --boot_img "$W/parts/$p.img" --out "$W/unpack/$p" --format=mkbootimg | sed "s#$W/unpack/$p/#<unpacked $p>/#g"
    echo; echo; echo "== $p: avbtool info_image"; "$HB/avbtool" info_image --image "$W/parts/$p.img"
  done
  echo; echo "== vbmeta_a: avbtool info_image"; "$HB/avbtool" info_image --image "$W/parts/vbmeta_a.img"
  echo; echo "== super: lpdump"; "$HB/lpdump" "$W/parts/super.img"
} > "$BD/boot-images.txt" 2>&1 || die "could not read the image's boot partitions"
echo "   boot-images.txt: $(wc -l < "$BD/boot-images.txt") lines"
FWM=$S/vendor/anybook/g14-kernel/firmware/firmware-manifest.tsv
NVM=$S/vendor/anybook/g14-kernel/firmware-nvidia-open/firmware-manifest-nvidia-open.json
mkdir -p "$BD/inputs"
for m in "$FWM" "$NVM"; do [ -f "$m" ] && cp "$m" "$BD/inputs/"; done
# FILES.tsv must name a licence for every firmware file (rebuilding the image with these manifests gives the
# shipped bytes: checked for 0.1.0-preview.2 on 2026-11-02, ANAL-341)
if command -v 7z >/dev/null; then
  (cd "$W/parts" && 7z e -y EFI.img LICENSES/firmware/FILES.tsv >/dev/null 2>&1) || true
  python3 - "$W/parts/FILES.tsv" "$BD/inputs" <<'PY' || die "the firmware manifests don't match the image's LICENSES/firmware/FILES.tsv"
import glob, json, os, sys
files, d = sys.argv[1:]
if not os.path.exists(files):
    sys.exit("no LICENSES/firmware/FILES.tsv on the image's ESP")
rows = [r for r in (l.rstrip("\n").split("\t") for l in open(files) if not l.startswith("#") and l.strip())]
bad = [r[0] for r in rows if len(r) < 4 or r[3] == "?"]
print(f"   firmware: {len(rows) - len(bad)} of {len(rows)} files in the image's LICENSES/firmware/FILES.tsv name their "
      f"licence; manifests packed: {', '.join(sorted(os.path.basename(x) for x in glob.glob(d + '/*')))}")
sys.exit(1 if bad else 0)
PY
else
  echo "   7z not found: the firmware manifests were not checked against the image" >&2
fi

# 5. the record: SOURCES.md stands alone; the build tarball carries a copy
# repo runs in the AOSP container, with the local mirror the tree's git alternates point into, and no trace file
if [ -n "$REUSE" ] && [ -f "$REUSE/aosp-manifest.xml" ]; then
  reused aosp-manifest.xml
else
  docker run --rm -u "$(id -u):$(id -g)" -e REPO_TRACE=0 -v "$A/aosp:/aosp:ro" -w /aosp/src anybook-aosp \
    repo manifest -r -o - > "$OUT/aosp-manifest.xml"
fi
[ -s "$OUT/aosp-manifest.xml" ] || die "could not write aosp-manifest.xml"
python3 "$R/scripts/release/sources-md.py" --version "$VER" --kernel-release "$KREL" --loader "$LOADER" \
  --kernel-revisions "$K/provenance/REVISIONS.txt" --userspace-revisions "$U/REVISIONS.txt" \
  --notice-scan "$W/notice-scan.json" --build-files "$BD" --tree "$TREE" --home "$HOME_URL" --contact "$CONTACT" \
  --mesa-provenance <(tar -xJf "$OUT/openbook-$VER-source-userspace.tar.xz" -O "openbook-$VER-source-userspace/mesa-build/PROVENANCE.txt") \
  ${MNOTE:+--mesa-note "$MNOTE"} ${INOTE:+--install-note "$INOTE"} \
  --installer-tools "$(jq -r '(.tools // []) | map(sub(" "; " ")) | join(", ")' "$BJ")" --out "$OUT/SOURCES.md"
cp "$OUT/SOURCES.md" "$BD/SOURCES.md"
pack "openbook-$VER-source-build" "$BD"
(cd "$OUT" && sha256sum openbook-"$VER"-source-*.tar.xz aosp-manifest.xml SOURCES.md > SHA256SUMS)

# 6. gates on what will be published
echo "-- no private identity in any output (identity-scan.py)"
"${ID_SCAN[@]}" "$OUT" || die "a private identity is in the source folder: nothing here may be published"
echo "-- no pointer to the private development repository"
if grep -nE 'github\.com/Mhsbrian/OpenBook([/.#]|$)|\bdocs/[A-Za-z-]+\.md\b' "$OUT/SOURCES.md"; then
  die "SOURCES.md points at the private repository"
fi
rm -rf "$W"
echo "-- done: $OUT"; ls -l "$OUT"; echo "log: $LOG"
