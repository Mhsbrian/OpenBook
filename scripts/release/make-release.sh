#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Turn a built OpenBook live USB image into a release folder for openbook.page (docs/RELEASE.md):
#   1. checks the image against its build record (<label>.build.json from scripts/installer-image.sh), and what it
#      carries: NVIDIA's own-use GSP firmware, the signing keys and build type, firmware licences;
#   2. compresses it with xz -9 in independent blocks (writers decompress it on the fly; xz 5.4+ uses every core),
#      then decompresses the result and checks it gives the image's sha256 again;
#   3. makes a hybrid v1 + v2 torrent (scripts/release/mktorrent.py) whose web seeds are the --mirror URLs, so a
#      download finishes even with no peers;
#   4. writes SHA256SUMS and, with --sign-key, SHA256SUMS.sig (ssh-keygen -Y sign, namespace openbook-release),
#      verified straight away against the key's public half;
#   5. writes release.json, the record the website reads: files, sizes, hashes, magnet, mirrors, build identity and
#      the publish gates. "public" is true only when every gate passes or is waived on the record.
# Files only, under --out. Nothing is uploaded, published or written to a disk; docs/RELEASE.md has the publish steps.
#
# usage: make-release.sh --image IMG --version V [--out DIR] [--channel preview|stable] [--mirror URL_PREFIX]...
#                        [--site URL_PREFIX] [--tracker URL]... [--no-default-trackers] [--sign-key KEY]
#                        [--source-url URL] [--owner-approved] [--waive GATE[,GATE]] [--private] [--xz-level N]
#   --mirror      a folder URL that will hold the .img.xz (e.g. a GitHub release's download/<tag>/); becomes a web
#                 seed and a direct-download link. Repeatable.
#   --site        where the site serves this release's small files (default https://openbook.page/releases/<V>/)
#   --sign-key    an ssh private key (ed25519). It is read by ssh-keygen only; never copied or logged.
#   --waive       release_keys and/or user_build: publish a developer preview on AOSP test keys or userdebug, on the
#                 record. no_nvidia_firmware, source_offer and owner_approved can't be waived.
#   --private     the image is for the owner's own use (e.g. it carries NVIDIA's GSP firmware): compress and checksum
#                 only. No torrent, no mirrors, and release.json says private.
# Output: --out DIR (default <data dir>/release/out/<V>); log: <data dir>/logs/release/release-<V>-<UTC>.log
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
IMG=; VER=; OUT=; CHANNEL=preview; SITE=; KEY=; SRC=; OWNER=0; WAIVE=; PRIVATE=0; XZL=9; DEFTR=1
MIRRORS=(); TRACKERS=()
DEFAULT_TRACKERS=(
  udp://tracker.opentrackr.org:1337/announce
  udp://open.stealth.si:80/announce
  udp://tracker.torrent.eu.org:451/announce
)
while [ $# -gt 0 ]; do
  case $1 in
    --image) IMG=$(realpath "$2"); shift 2 ;;
    --version) VER=$2; shift 2 ;;
    --out) OUT=$(realpath -m "$2"); shift 2 ;;
    --channel) CHANNEL=$2; shift 2 ;;
    --mirror) MIRRORS+=("${2%/}/"); shift 2 ;;
    --site) SITE=${2%/}/; shift 2 ;;
    --tracker) TRACKERS+=("$2"); shift 2 ;;
    --no-default-trackers) DEFTR=0; shift ;;
    --sign-key) KEY=$(realpath "$2"); shift 2 ;;
    --source-url) SRC=$2; shift 2 ;;
    --owner-approved) OWNER=1; shift ;;
    --waive) WAIVE=$2; shift 2 ;;
    --private) PRIVATE=1; shift ;;
    --xz-level) XZL=$2; shift 2 ;;
    -h|--help) sed -n '3,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
die() { echo "make-release: $*" >&2; exit 1; }
[ -n "$IMG" ] && [ -f "$IMG" ] || die "--image: a live image (.img) from scripts/installer-image.sh"
[ -n "$VER" ] || die "--version is required (e.g. 0.1.0-preview.1)"
case $VER in *[!A-Za-z0-9._+-]*|.*) die "--version: letters, digits, . _ + - only" ;; esac
case $CHANNEL in preview|stable) ;; *) die "--channel: preview or stable" ;; esac
case $XZL in [0-9]) ;; *) die "--xz-level: 0-9" ;; esac
for w in ${WAIVE//,/ }; do case $w in release_keys|user_build) ;; *) die "--waive: only release_keys, user_build" ;; esac; done
BASE=${IMG%.img}; BJ=$BASE.build.json
[ -f "$BJ" ] || die "$BJ missing: build the image with scripts/installer-image.sh"
[ $DEFTR = 1 ] && TRACKERS=("${DEFAULT_TRACKERS[@]}" "${TRACKERS[@]}")
[ $PRIVATE = 1 ] && [ ${#MIRRORS[@]} -gt 0 ] && die "--private images get no mirrors"
OUT=${OUT:-$A/release/out/$VER}; SITE=${SITE:-https://openbook.page/releases/$VER/}
NAME=openbook-$VER-x86_64-live
mkdir -p "$OUT" "$A/logs/release"
LOG=$A/logs/release/release-$VER-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee -a "$LOG") 2>&1
T0=$(date +%s)
EPOCH=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["epoch"])' "$BJ")
echo "== make-release.sh $VER from $(basename "$IMG") ($(date -u +%FT%TZ)), repo $(git -C "$R" rev-parse --short HEAD)"

# 1. the image and what it carries
WANT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$BJ")
echo "-- checking the image against $(basename "$BJ")"
GOT=$(sha256sum "$IMG" | cut -d' ' -f1)
[ "$GOT" = "$WANT" ] || die "image sha256 $GOT differs from its build record $WANT"
# NVIDIA's GSP firmware names (kernel/firmware/anybook-nvidia-open.tsv). EROFS keeps directory entries
# uncompressed, so the names are visible in the raw image; the G14 image of 2026-10-30 (anal319b) is caught this way.
NV=0; for m in gsp_ga10x.bin gsp_tu10x.bin ucodes_ga10x.bin; do
  if LC_ALL=C grep -a -q -F "$m" "$IMG"; then NV=1; echo "   found NVIDIA firmware: $m"; fi
done
if [ $NV = 1 ] && [ $PRIVATE = 0 ]; then
  die "this image carries NVIDIA's GSP firmware, which the owner uses under its own-use terms (docs/nvidia-open.md). Build a public image without it, or use --private"
fi

# 2. compress, then prove the round trip
echo "-- xz -$XZL, multi-threaded, independent blocks"
rm -f "$OUT/$NAME.img.xz.tmp"
xz -T0 -"$XZL" -c "$IMG" > "$OUT/$NAME.img.xz.tmp"
RT=$(xz -T0 -dc "$OUT/$NAME.img.xz.tmp" | sha256sum | cut -d' ' -f1)
[ "$RT" = "$WANT" ] || die "decompressed sha256 $RT differs from the image's $WANT"
mv "$OUT/$NAME.img.xz.tmp" "$OUT/$NAME.img.xz"
echo "   $(stat -c %s "$OUT/$NAME.img.xz") bytes; decompresses to the image's sha256"

# 3. torrent
TJ=$OUT/.torrent.json
if [ $PRIVATE = 0 ]; then
  echo "-- torrent"
  ARGS=(); for t in "${TRACKERS[@]}"; do ARGS+=(--tracker "$t"); done
  for m in "${MIRRORS[@]}"; do ARGS+=(--webseed "$m$NAME.img.xz"); done
  python3 "$R/scripts/release/mktorrent.py" "$OUT/$NAME.img.xz" --out "$OUT/$NAME.img.xz.torrent" \
    --epoch "$EPOCH" --comment "OpenBook $VER live USB image. Check it: https://openbook.page/verify" \
    "${ARGS[@]}" --json > "$TJ"
else
  rm -f "$OUT/$NAME.img.xz.torrent"; echo '{}' > "$TJ"
fi

# 4. checksums and signature
echo "-- SHA256SUMS"
{
  (cd "$OUT" && sha256sum "$NAME.img.xz")
  if [ $PRIVATE = 0 ]; then (cd "$OUT" && sha256sum "$NAME.img.xz.torrent"); fi
  echo "$WANT  $NAME.img"   # the decompressed image, for people who unpack it first (sha256sum -c --ignore-missing)
} > "$OUT/SHA256SUMS.tmp"
mv "$OUT/SHA256SUMS.tmp" "$OUT/SHA256SUMS"
rm -f "$OUT/SHA256SUMS.sig" "$OUT/openbook-release.pub"
SIGNED=0
if [ -n "$KEY" ]; then
  echo "-- signing SHA256SUMS (ssh-keygen -Y sign, namespace openbook-release)"
  ssh-keygen -q -Y sign -f "$KEY" -n openbook-release "$OUT/SHA256SUMS" < /dev/null
  PUB=$(ssh-keygen -y -f "$KEY" < /dev/null)
  echo "$PUB" > "$OUT/openbook-release.pub"
  echo "release@openbook.page namespaces=\"openbook-release\" $PUB" > "$OUT/.allowed_signers"
  ssh-keygen -q -Y verify -f "$OUT/.allowed_signers" -I release@openbook.page -n openbook-release \
    -s "$OUT/SHA256SUMS.sig" < "$OUT/SHA256SUMS" || die "the new signature does not verify"
  rm -f "$OUT/.allowed_signers"; SIGNED=1
  echo "   verified against $(ssh-keygen -l -f "$OUT/openbook-release.pub" | cut -d' ' -f2)"
fi

# 5. release.json
echo "-- release.json"
python3 - "$BJ" "$OUT" "$NAME" "$VER" "$CHANNEL" "$SITE" "$SRC" "$OWNER" "$WAIVE" "$PRIVATE" "$NV" "$SIGNED" \
  "$TJ" "$XZL" "$EPOCH" "$(git -C "$R" rev-parse HEAD)" "${MIRRORS[@]}" <<'PY'
import datetime, hashlib, json, os, subprocess, sys
(bj, out, name, ver, channel, site, src, owner, waive, private, nv, signed, tj, xzl, epoch, commit,
 *mirrors) = sys.argv[1:]
b = json.load(open(bj))
t = json.load(open(tj))
xzf = f"{out}/{name}.img.xz"
def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()
blocks = None
for line in subprocess.run(["xz", "--robot", "-lv", xzf], capture_output=True, text=True).stdout.splitlines():
    if line.startswith("totals"):
        blocks = int(line.split("\t")[2])  # totals, streams, blocks, ...
fp = b["fingerprint"]
waived = [w for w in waive.split(",") if w]
gates = {
    "no_nvidia_firmware": nv == "0",
    "firmware_licences": not b["firmware"]["without_licence"],
    "release_keys": not fp.endswith("/test-keys"),
    "user_build": ":user/" in fp,
    "checksums_signed": signed == "1",
    "source_offer": bool(src),
    "owner_approved": owner == "1",
}
blocking = [g for g, ok in gates.items() if not ok and g not in waived]
public = private == "0" and not blocking
size = os.path.getsize(xzf)
img = {
    "kind": "live-usb", "arch": "x86_64",
    "file": f"{name}.img.xz", "bytes": size, "sha256": sha(xzf),
    "compression": {"format": "xz", "level": int(xzl), "blocks": blocks, "ratio": round(size / b["bytes"], 4)},
    "image": {"file": f"{name}.img", "bytes": b["bytes"], "sha256": b["sha256"]},
    "stick_min_gb": next(g for g in (4, 8, 16, 32, 64) if g * 10**9 * 0.94 > b["bytes"]),
    "install_min_gb": 64,
    "urls": [m + f"{name}.img.xz" for m in mirrors],
}
if t:
    img["torrent"] = {
        "file": f"{name}.img.xz.torrent", "url": site + f"{name}.img.xz.torrent",
        "bytes": t["torrent_bytes"], "sha256": t["torrent_sha256"],
        "infohash_v1": t["infohash_v1"], "infohash_v2": t["infohash_v2"], "magnet": t["magnet"],
        "piece_bytes": t["piece_length"], "pieces": t["pieces"],
        "trackers": t["trackers"], "webseeds": t["webseeds"],
    }
rel = {
    "schema": "openbook-release/1",
    "version": ver, "channel": channel,
    "date": datetime.datetime.fromtimestamp(int(epoch), datetime.timezone.utc).strftime("%Y-%m-%d"),
    "audience": "private" if private == "1" else ("public" if public else "unpublished"),
    "public": public,
    "gates": gates, "waived": waived, "blocking": blocking,
    "artifacts": [img],
    "checksums": {"file": "SHA256SUMS", "url": site + "SHA256SUMS",
                  "signature": ({"file": "SHA256SUMS.sig", "url": site + "SHA256SUMS.sig",
                                 "public_key": open(f"{out}/openbook-release.pub").read().strip(),
                                 "method": "ssh-keygen -Y verify", "namespace": "openbook-release",
                                 "identity": "release@openbook.page"} if signed == "1" else None)},
    "source": src or None,
    "build": {"label": b["label"], "fingerprint": fp, "kernel": b["kernel_release"], "loader": b["loader"],
              "image_repo_commit": b["repo"]["commit"], "release_repo_commit": commit,
              "firmware_files": b["firmware"]["files"]},
    "hardware": {"first_target": "ASUS ROG Zephyrus G14 (2025, GA403WR)",
                 "status": "pre-alpha", "docs": "https://github.com/Mhsbrian/OpenBook/blob/main/docs/HARDWARE.md"},
}
json.dump(rel, open(f"{out}/release.json.tmp", "w"), indent=1)
os.replace(f"{out}/release.json.tmp", f"{out}/release.json")
print(f"   audience: {rel['audience']}" + (f"; blocking: {', '.join(blocking)}" if blocking else "")
      + (f"; waived: {', '.join(waived)}" if waived else ""))
PY
rm -f "$TJ"
echo "-- done in $(( $(date +%s) - T0 )) s: $OUT"
ls -l "$OUT"
echo "log: $LOG"
