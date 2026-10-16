#!/usr/bin/env bash
# Download an official Googlebook OS recovery image for YOUR OWN local use and verify it
# against Google's recovery manifest. Never commit or redistribute the result (see docs/PLAN.md#licensing).
# usage: fetch-gbos-recovery.sh CODENAME [DEST_DIR]     e.g. ruby | lapis | moonstone (Intel), mica | quartz (Snapdragon)
set -euo pipefail
DEV=${1:?codename}; DEST=${2:-$HOME/anybook/dl/gbos-$DEV}
MANIFEST=https://dl.google.com/dl/edgedl/device/recovery/production_recovery.json
mkdir -p "$DEST"; cd "$DEST"
curl -fsSL -o production_recovery.json "$MANIFEST"
read -r URL MD5 BUILD < <(python3 -I -c '
import json,sys
for e in json.load(open("production_recovery.json")):
    if e["device"] == sys.argv[1]:
        print(e["url"], e["md5"], e["buildidentifier"]); break
else:
    sys.exit("codename not in manifest")' "$DEV")
echo "device=$DEV build=$BUILD"; echo "url=$URL"
curl -fL -C - -o recovery.zip "$URL"
echo "$MD5  recovery.zip" | md5sum -c -          # manifest md5 is of the zip
BIN=$(unzip -Z1 recovery.zip | head -1)
[ -f "$BIN" ] || unzip -o recovery.zip "$BIN"    # unzip verifies the CRC-32
echo "image: $DEST/$BIN"
