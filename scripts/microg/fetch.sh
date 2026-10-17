#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Download microG's signed release APKs for the "Google services compatibility (microG)" add-on (ANAL-210,
# docs/gapps.md section 6) and check every one of them against device/anybook/common/addons/microg.json, the file
# the OpenBook image itself pins them with:
#   - sha256 and size of the file;
#   - microG's OpenPGP signature (.asc next to each GmsCore release file), made by the key with the pinned fingerprint;
#   - the APK's signing certificate (apksigner: one signer, the pinned SHA-256, i.e. microG's release key);
#   - package name and versionCode (aapt2).
# The APKs are not committed (Apache-2.0, but 112 MB): they land in <data dir>/dl/microg/<version>/ with VERIFIED.txt.
#
# usage: fetch.sh [CATALOG]     default device/anybook/common/addons/microg.json
# Env: AOSP_SRC (default ~/anybook/aosp/src): apksigner, aapt2 and a JDK from its prebuilts.
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
CAT=${1:-$R/device/anybook/common/addons/microg.json}
T=${AOSP_SRC:-$A/aosp/src}
JAVA=$T/prebuilts/jdk/jdk21/linux-x86/bin/java; APKSIGNER=$T/prebuilts/sdk/tools/linux/lib/apksigner.jar
AAPT2=$T/prebuilts/sdk/tools/linux/bin/aapt2
for f in "$JAVA" "$APKSIGNER" "$AAPT2"; do [ -e "$f" ] || { echo "missing $f (AOSP_SRC=$T)" >&2; exit 2; }; done
command -v gpg >/dev/null || { echo "gpg is needed for microG's release signatures" >&2; exit 2; }

VER=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$CAT")
FPR=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["gpg_fingerprint"])' "$CAT")
D=$A/dl/microg/$VER; mkdir -p "$D"; cd "$D"
REPORT=$D/VERIFIED.txt.part; : > "$REPORT"
say(){ echo "$*" | tee -a "$REPORT"; }
say "microG $VER, catalog $(realpath --relative-to="$R" "$CAT" 2>/dev/null || echo "$CAT") sha256 $(sha256sum < "$CAT" | cut -d' ' -f1)"
say "checked $(date -u +%FT%TZ) with apksigner $("$JAVA" -jar "$APKSIGNER" version) and $("$AAPT2" version 2>&1 | sed -n 1p)"

# microG's signing key, by fingerprint, in a keyring of our own (never the user's).
export GNUPGHOME=$A/dl/microg/gnupg; mkdir -p -m 700 "$GNUPGHOME"
if ! gpg -q --batch --list-keys "$FPR" >/dev/null 2>&1; then
  curl -fsSL "https://keys.openpgp.org/vks/v1/by-fingerprint/$FPR" -o "$GNUPGHOME/key.asc" ||
    curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$FPR" -o "$GNUPGHOME/key.asc"
  gpg -q --batch --import "$GNUPGHOME/key.asc"
fi

python3 -I -c '
import json, sys
for f in json.load(open(sys.argv[1]))["files"]:
    print(f["file"], f["url"], f["sha256"], f["bytes"], f["cert_sha256"], f["package"], f["version_code"], int(f["gpg"]))
' "$CAT" | while read -r FILE URL SHA BYTES CERT PKG VC GPG; do
  say "== $FILE"
  [ -f "$FILE" ] || { curl -fsSL -o "$FILE.part" "$URL" && mv "$FILE.part" "$FILE"; }
  echo "$SHA  $FILE" | sha256sum -c --quiet - || { say "FAIL sha256 of $FILE (want $SHA)"; exit 1; }
  [ "$(stat -c %s "$FILE")" = "$BYTES" ] || { say "FAIL size of $FILE (want $BYTES)"; exit 1; }
  say "sha256 $SHA ok ($(stat -c %s "$FILE") bytes, $URL)"
  if [ "$GPG" = 1 ]; then
    [ -f "$FILE.asc" ] || { curl -fsSL -o "$FILE.asc.part" "$URL.asc" && mv "$FILE.asc.part" "$FILE.asc"; }
    st=$(gpg --batch --status-fd 1 --verify "$FILE.asc" "$FILE" 2>/dev/null || true)
    echo "$st" | grep -q "^\[GNUPG:\] VALIDSIG $FPR " || { say "FAIL OpenPGP signature of $FILE (want key $FPR)"; exit 1; }
    say "OpenPGP signature ok, key $FPR ($(echo "$st" | sed -n 's/^\[GNUPG:\] GOODSIG [0-9A-F]* //p'))"
  else
    say "no OpenPGP signature published for this file; sha256 and certificate only"
  fi
  certs=$("$JAVA" -jar "$APKSIGNER" verify --print-certs "$FILE" 2>/dev/null) || { say "FAIL apksigner verify $FILE"; exit 1; }
  n=$(echo "$certs" | grep -c '^Signer #[0-9]* certificate SHA-256 digest:')
  got=$(echo "$certs" | sed -n 's/^Signer #1 certificate SHA-256 digest: //p')
  [ "$n" = 1 ] && [ "$got" = "$CERT" ] || { say "FAIL signing certificate of $FILE: $n signer(s), $got (want $CERT)"; exit 1; }
  say "signed by one certificate, SHA-256 $got ($(echo "$certs" | sed -n 's/^Signer #1 certificate DN: //p'))"
  b=$("$AAPT2" dump badging "$FILE" 2>/dev/null | sed -n 1p)
  echo "$b" | grep -q "^package: name='$PKG' versionCode='$VC' " || { say "FAIL $FILE is not $PKG versionCode $VC: $b"; exit 1; }
  say "$(echo "$b" | cut -d' ' -f2-4)"
done
mv "$REPORT" "$D/VERIFIED.txt"
echo "microG $VER verified in $D"
