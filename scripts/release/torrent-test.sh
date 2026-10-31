#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Check scripts/release/mktorrent.py against libtorrent 2 (scripts/release/torrent-test.py) in the
# openbook-release-test container (tools/release/Dockerfile.test), built here if missing.
# usage: torrent-test.sh [REAL_FILE PIECE_KIB]   e.g. a release's .img.xz and 1024
# Log: <data dir>/logs/release/torrent-test-<UTC>.log
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
docker image inspect openbook-release-test > /dev/null 2>&1 \
  || docker build -t openbook-release-test -f "$R/tools/release/Dockerfile.test" "$R/tools/release"
W=$A/release-test/unit-$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$W" "$A/logs/release"
LOG=$A/logs/release/torrent-test-$(date -u +%Y%m%dT%H%M%SZ).log
REAL=()
if [ $# -ge 2 ]; then F=$(realpath "$1"); REAL=(-v "$F:/real/$(basename "$F"):ro"); set -- "/real/$(basename "$F")" "$2"; fi
docker run --rm --user "$(id -u):$(id -g)" -v "$R/scripts/release:/s:ro" -v "$W:/w" "${REAL[@]}" \
  openbook-release-test python3 /s/torrent-test.py /w "$@" 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
rm -rf "$W"
echo "log: $LOG"
exit "$rc"
