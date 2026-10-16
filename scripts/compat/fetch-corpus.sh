#!/usr/bin/env bash
# Download the F-Droid part of the ARM-compat corpus listed in scripts/compat/corpus/fdroid.tsv into
# ~/anybook/compat/apks/fdroid, checking every APK against its pinned sha256.
#   fetch-corpus.sh             download what is missing
#   fetch-corpus.sh --reselect  refresh the F-Droid index, verify its signature, regenerate fdroid.tsv
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}; FD=$A/compat/fdroid; D=$A/compat/apks/fdroid
TSV=$REPO/scripts/compat/corpus/fdroid.tsv
# SHA-256 of F-Droid's repo signing certificate, as published on f-droid.org
FDROID_CERT=43:23:8D:51:2C:1E:5E:B2:D6:56:9F:4A:3A:FB:F5:52:34:18:B8:2E:0A:3E:D1:55:27:70:AB:B9:A9:C9:CC:AB
MIRRORS=${FDROID_MIRRORS:-https://plug-mirror.rcac.purdue.edu/fdroid/repo https://mirror.fcix.net/fdroid/repo}
mkdir -p "$FD" "$D"

if [ "${1:-}" = --reselect ]; then
  curl -fL -o "$FD/entry.jar" https://f-droid.org/repo/entry.jar
  curl -fL -o "$FD/index-v2.json" https://f-droid.org/repo/index-v2.json
  docker run --rm -u "$(id -u):$(id -g)" -v "$FD:/f:ro" anybook-ndk sh -c \
    "jarsigner -verify /f/entry.jar | grep -q 'jar verified' && keytool -printcert -jarfile /f/entry.jar | grep -q 'SHA256: $FDROID_CERT'" \
    || { echo "entry.jar signature check failed" >&2; exit 1; }
  rm -rf "$FD/entry" && mkdir "$FD/entry" && unzip -q -o "$FD/entry.jar" entry.json -d "$FD/entry"
  WANT=$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))['index']['sha256'])" "$FD/entry/entry.json")
  echo "$WANT  $FD/index-v2.json" | sha256sum -c -
  python3 -I "$REPO/scripts/compat/corpus/select-fdroid.py" "$FD/index-v2.json" "$TSV"
fi

grep -v '^#' "$TSV" | tail -n +2 | while IFS=$'\t' read -r pkg name role abi vn vc apk sha size lic src why; do
  f=$D/$apk
  if [ -f "$f" ] && echo "$sha  $f" | sha256sum -c --quiet - 2>/dev/null; then continue; fi
  echo "fetching $apk ($role, $((size / 1000000)) MB)"
  ok=0
  # f-droid.org throttles bulk downloads; official mirrors (listed in the signed index) serve the same
  # files, and the pinned sha256 makes the source irrelevant. Old releases move to /archive.
  for base in $MIRRORS https://f-droid.org/repo https://f-droid.org/archive; do
    rm -f "$f.part"
    curl -fsSL --retry 2 --connect-timeout 15 -o "$f.part" "$base/$apk" || continue
    if echo "$sha  $f.part" | sha256sum -c --quiet - 2>/dev/null; then ok=1; break; fi
    echo "sha256 mismatch from $base, trying next source" >&2
  done
  [ $ok = 1 ] || { echo "could not fetch a verified $apk" >&2; exit 1; }
  mv "$f.part" "$f"
done
echo "corpus ready in $D ($(ls "$D" | wc -l) APKs)"
