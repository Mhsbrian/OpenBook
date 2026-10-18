#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Host tests of the bring-your-own GApps step (ANAL-211): build the install engine from this tree and from
# origin/main, build the synthetic packages if needed, and run engine-gapps-test.py against a live image, in the
# openbook-installer container. Image files only; no Google software.
#
# usage: engine-gapps-test.sh LIVE.img RUN      results: <data dir>/logs/installer/RUN/{results.json,SUMMARY.md}
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
D=$R/scripts/installer/inst-docker.sh
IMG=$(realpath "${1:?usage: engine-gapps-test.sh LIVE.img RUN}"); RUN=${2:?run name}
L=$A/logs/installer/$RUN; W=$A/installer/work/$RUN; P=$A/installer/gapps/packages
mkdir -p "$L" "$W"
[ -f "$A/gapps/out/apks/SHA256SUMS" ] || "$R/scripts/gapps/build-synthetic-apks.sh"
"$D" python3 "$R/scripts/gapps/make-synthetic.py" --apks "$A/gapps/out/apks" --etc "$R/scripts/gapps/testapps/etc" --out "$P" >/dev/null
OLD=$W/main-src; rm -rf "$OLD"; mkdir -p "$OLD"
git -C "$R" archive origin/main device/anybook/common/installer/engine | tar -x -C "$OLD"
B=$A/installer/build/openbook-install-host-g2; BM=$A/installer/build/openbook-install-host-main
"$R/scripts/installer/engine-host-build.sh" "$B" >/dev/null
"$R/scripts/installer/engine-host-build.sh" "$BM" "$OLD/device/anybook/common/installer/engine" >/dev/null
echo "engine $(git -C "$R" rev-parse --short HEAD)$( [ -z "$(git -C "$R" status --porcelain)" ] || echo +dirty) vs origin/main $(git -C "$R" rev-parse --short origin/main)" > "$L/engines.txt"
rc=0
"$D" python3 "$R/scripts/gapps/engine-gapps-test.py" --engine "$B" --main "$BM" --image "$IMG" --packages "$P" \
  --apks "$A/gapps/out/apks" --run "$W" || rc=$?
cp "$W/results.json" "$W/SUMMARY.md" "$L/" 2>/dev/null || true
for f in lpdump.txt product_a.avbinfo.txt product_a.verify.txt vbmeta_a.avbinfo.txt labels.json report.json; do
  [ -f "$W/gapps/out/$f" ] && cp "$W/gapps/out/$f" "$L/"
done
cp "$P/SHA256SUMS" "$L/packages.sha256"; cp "$A/gapps/out/apks/certs.txt" "$L/apk-certs.txt"
echo "results: $L/SUMMARY.md"
exit $rc
