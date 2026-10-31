#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Host test of the save-logs helper's archive of earlier boots (ANAL-176): runs the PRIOR_BOOTS and PRIOR_LIST shell
# strings, as compiled into openbook-live-init, with bash and AOSP's host toybox on a scratch directory instead of
# /data. Checks the exit statuses that summary.json's prior_boots_rc reports: 0 complete, 4 nothing to archive,
# 3 no /data, non-zero (SIGPIPE: 141) when the 96 MiB cap cut the archive (tested with a 1000-byte cap).
# bash's pipefail and mksh's (Android's sh) both return the rightmost failing command's status.
#
# usage: prior-boots-test.sh [BINARY] [TOYBOX]
#   BINARY default <data dir>/installer/build/openbook-live-init
#   TOYBOX default <data dir>/aosp/src/out/host/linux-x86/bin/toybox
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
BIN=${1:-$A/installer/build/openbook-live-init}
TB=${2:-$A/aosp/src/out/host/linux-x86/bin/toybox}
X=$(mktemp -d)
trap 'find "$X" -mindepth 1 -delete; rmdir "$X"' EXIT
mkdir -p "$X/bin" "$X/data"
for t in tar gzip head du cut find wc; do ln -s "$TB" "$X/bin/$t"; done
CMD=$(strings "$BIN" | grep -F "head -c 100663296" | head -1 || true)
LIST=$(strings "$BIN" | grep -F 'echo "$d missing"' | head -1 || true)
[ -n "$CMD" ] && [ -n "$LIST" ] || { echo "PRIOR_BOOTS/PRIOR_LIST not found in $BIN" >&2; exit 1; }
pass=0 total=0
run() {  # NAME EXPECTED_RC EXPECTED_ENTRIES [CAP]
  local c rc n
  c=$(printf '%s' "$CMD" | sed "s|cd /data|cd $X/data|; s|head -c 100663296|head -c ${4:-100663296}|")
  rc=0; PATH=$X/bin:/usr/bin bash -c "$c" > "$X/out.bin" || rc=$?
  n=$("$TB" gzip -dc < "$X/out.bin" 2>/dev/null | "$TB" tar -tf - 2>/dev/null | wc -l || true)
  total=$((total + 1))
  if [ "$rc" = "$2" ] && [ "$n" -ge "$3" ]; then pass=$((pass + 1)); echo "PASS $1: rc $rc, $n entries, $(stat -c %s "$X/out.bin") bytes"
  else echo "FAIL $1: rc $rc (want $2), $n entries (want >= $3)"; fi
}
run "nothing to archive" 4 0
mkdir -p "$X/data/misc/logd" "$X/data/tombstones"
echo hello > "$X/data/misc/logd/logcat"; echo t > "$X/data/tombstones/tombstone_00"
run "two of the four directories" 0 4
out=$(cd / && PATH=$X/bin:/usr/bin bash -c "$(printf '%s' "$LIST" | sed "s|cd /data|cd $X/data|")")
total=$((total + 1))
if grep -qx "anr missing" <<<"$out" && grep -q "^misc/logd [0-9]* KiB, 1 files$" <<<"$out"; then pass=$((pass + 1)); echo "PASS list: $(tr '\n' ';' <<<"$out")"
else echo "FAIL list: $out"; fi
head -c 3000000 /dev/urandom > "$X/data/tombstones/big"
run "cut by the cap" 141 1 1000
run "3 MB under the normal cap" 0 5
find "$X/data" -mindepth 1 -delete; rmdir "$X/data"
run "no /data" 3 0
echo "$pass/$total passed"
[ "$pass" = "$total" ]
