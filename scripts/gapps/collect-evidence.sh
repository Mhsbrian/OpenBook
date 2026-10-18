#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copy a gapps-e2e-qemu.sh run's results into the repo's evidence (ANAL-211): SUMMARY.md and results.json, each case's
# sections and result, the disk inspections, the install report (without the plan) and the screenshots.
# usage: collect-evidence.sh RUN DEST
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
L=$A/logs/installer/${1:?usage: collect-evidence.sh RUN DEST}; O=${2:?dest}
mkdir -p "$O/inspect" "$O/screens"
cp "$L/SUMMARY.md" "$L/results.json" "$L/gapps-usb.txt" "$O/" 2>/dev/null || true
cp "$L"/inspect/g-*.json "$L"/inspect/whole-before.json "$O/inspect/" 2>/dev/null || true
for d in "$L"/g-*; do
  c=$(basename "$d"); mkdir -p "$O/$c"
  cp "$d/result.json" "$O/$c/" 2>/dev/null || true
  [ -d "$d/sections" ] && cp -r "$d/sections" "$O/$c/"
  [ -f "$d/corrupted.json" ] && cp "$d/corrupted.json" "$O/$c/"
  [ -f "$d/serial.log.gz" ] && cp "$d/serial.log.gz" "$O/$c/"
  [ -f "$d/report.json" ] && python3 -c "import json,sys; r=json.load(open(sys.argv[1])); r.pop('plan', None); json.dump(r, open(sys.argv[2], 'w'), indent=1)" "$d/report.json" "$O/$c/report.json"
  for s in "$d"/screens/shots/*.png; do [ -f "$s" ] && cp "$s" "$O/screens/"; done
done
rm -f "$O/screens/g-desktop.png"  # the wallpaper, 3.6 MB: not this step's evidence
du -sh "$O"
