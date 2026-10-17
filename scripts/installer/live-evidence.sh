#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copy a live image's build records and a live-qemu.sh run into the repo's evidence folder (ANAL-190):
#   DEST/build/      <label>.build.json, .img.json, .sha256, the input snapshot's provenance.txt, the build log (gz)
#   DEST/qemu/       results.json, SUMMARY.md; per case result.json, serial.log.gz, shot-*.png, sections/
#   DEST/qemu/logs/  what the "save logs" entry wrote to the stick, redacted (live-report.py --redact: MAC addresses,
#                    USB serials, Wi-Fi names), big text files gzipped, plus report.md/report.json (--expect vm)
#
# usage: live-evidence.sh LABEL RUN DEST
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
LABEL=${1:?usage: live-evidence.sh LABEL RUN DEST}; RUN=${2:?run}; DEST=${3:?dest}
O=$A/installer/out; L=$A/logs/installer/$RUN
mkdir -p "$DEST/build" "$DEST/qemu"
cp "$O/$LABEL.build.json" "$O/$LABEL.img.json" "$O/$LABEL.sha256" "$DEST/build/"
# The snapshot is named after the label unless the image was rebuilt with --inputs; build.json has the hashes either way.
[ -f "$A/installer/inputs/$LABEL/provenance.txt" ] && cp "$A/installer/inputs/$LABEL/provenance.txt" "$DEST/build/inputs-provenance.txt"
log=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["log"])' "$O/$LABEL.build.json")
gzip -9nc "$log" > "$DEST/build/$(basename "$log").gz"
cp "$L/results.json" "$L/SUMMARY.md" "$DEST/qemu/"
for d in "$L"/*/; do
  c=$(basename "$d"); [ -f "$d/result.json" ] || continue
  mkdir -p "$DEST/qemu/$c"
  cp "$d/result.json" "$DEST/qemu/$c/"
  [ -f "$d/serial.log" ] && python3 "$R/scripts/installer/live-report.py" --redact-file "$d/serial.log" | gzip -9n > "$DEST/qemu/$c/serial.log.gz"
  cp "$d"/shot-*.png "$DEST/qemu/$c/" 2>/dev/null || true
  [ -d "$d/sections" ] && cp -r "$d/sections" "$DEST/qemu/$c/"
  for j in "$d"/esp/live-init-*.json; do  # openbook-live-init's own reports; the saved logs are handled below
    [ -f "$j" ] && mkdir -p "$DEST/qemu/$c/esp" && cp "$j" "$DEST/qemu/$c/esp/"
  done
done
for d in "$L"/logs/esp/live-*/; do
  [ -d "$d" ] || continue
  out=$DEST/qemu/logs/$(basename "$d")
  python3 "$R/scripts/installer/live-report.py" "$d" --expect vm --redact "$out" > /dev/null
  for f in "$out"/*.txt; do [ "$(stat -c %s "$f")" -gt 200000 ] && gzip -9n "$f"; done
done
du -sh "$DEST"
