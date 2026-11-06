#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run OpenBook's fast host tests: no hardware, no images, no containers, a few seconds in all. CI runs this on every
# pull request (.github/workflows/ci.yml, "Unit tests"); run it before you push.
#
# usage: tests/run.sh       one line per test, then "N/N passed"; non-zero if any failed
set -uo pipefail
R=$(cd "$(dirname "$0")/.." && pwd)
TESTS=(
  "python3 $R/tests/ci/check-hygiene-test.py"
  "bash $R/tests/aosp-patches-import-test.sh"
  "bash $R/tests/dgpu-power-check-test.sh bash"
  "bash $R/tests/quire/unmount-build-loops-test.sh"
  "python3 $R/tests/gpu-diag-summary-test.py"
  "bash $R/tests/gpu-diag/choice-test.sh"
  "bash $R/tests/gpu-diag/sampler-test.sh"
  "python3 $R/tests/gpu-diag/pending-cleanup-test.py"
  "python3 $R/tests/perf/app-perf-test.py"
  "python3 $R/tests/perf/arm-corpus-test.py"
  "python3 $R/tests/g14-lock-test.py"
  "python3 $R/tests/release/identity-scan-test.py"
  "python3 $R/tests/release/source-closure-test.py"
  "python3 $R/tests/release/sources-links-test.py"
  # Ships in userdebug images as /vendor/bin/openbook-pc-setup-test (device/anybook/common/pc links it), so it stays
  # next to the scripts the device tree links.
  "bash $R/scripts/openbook-pc-setup-test.sh bash"
)
pass=0
for t in "${TESTS[@]}"; do
  name=${t#* }; name=${name#"$R"/}; name=${name%% *}
  if out=$($t 2>&1); then
    pass=$((pass + 1)); echo "PASS $name"
  else
    echo "FAIL $name"; printf '%s\n' "$out" | tail -n 20 | sed 's/^/    /'
  fi
done
echo "$pass/${#TESTS[@]} passed"
[ "$pass" = "${#TESTS[@]}" ]
