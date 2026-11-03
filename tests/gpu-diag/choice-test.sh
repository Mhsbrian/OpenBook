#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Tests for scripts/gpu-diag/choice.sh against a stub device (no adb): a directory stands in for Settings.Global, and
# failures are injected into reads, writes and adb itself.   tests/gpu-diag/choice-test.sh (tests/run.sh runs it)
set -uo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
PKG=org.example.game
fails=0 n=0 checks=0

# The stub device. FAIL_READ / FAIL_WRITE: settings exits 1. WRITES_OK=N: only the first N writes succeed.
# SILENT_WRITE=1: put/delete exit 0 but change nothing. ADB_DOWN=1: sh_ itself fails.
settings() {
  local verb=$1 key=$3
  case $verb in
    get) [ "${FAIL_READ:-0}" = 1 ] && return 1
         if [ -f "$ST/$key" ]; then cat "$ST/$key"; else echo null; fi ;;
    put|delete)
      [ "${FAIL_WRITE:-0}" = 1 ] && return 1
      if [ -n "${WRITES_OK:-}" ]; then
        [ "$(cat "$T/writes" 2>/dev/null || echo 0)" -ge "$WRITES_OK" ] && return 1
        echo $(( $(cat "$T/writes" 2>/dev/null || echo 0) + 1 )) > "$T/writes"
      fi
      [ "${SILENT_WRITE:-0}" = 1 ] && return 0
      if [ "$verb" = put ]; then printf '%s\n' "$4" > "$ST/$key"; else rm -f "$ST/$key"; fi ;;
  esac
}
sh_() { [ "${ADB_DOWN:-0}" = 1 ] && return 1; eval "$1"; }

# shellcheck source=../../scripts/gpu-diag/choice.sh
. "$R/scripts/gpu-diag/choice.sh"

reset() {
  ST=$T/settings-$n; mkdir -p "$ST"; PENDING=$T/pending-$n; rm -f "$PENDING" "$T/writes"
  unset FAIL_READ FAIL_WRITE WRITES_OK SILENT_WRITE ADB_DOWN
  printf '%s\n' "a.one,$PKG,b.two" > "$ST/$OPT_IN"   # other apps on both sides of ours
  printf '%s\n' "c.three" > "$ST/$OPT_OUT"
}
lists() { echo "pre=$(cat "$ST/$PRE_IN" 2>/dev/null) in=$(cat "$ST/$OPT_IN" 2>/dev/null) out=$(cat "$ST/$OPT_OUT" 2>/dev/null)"; }
check() {  # NAME CONDITION...
  local name=$1; shift; checks=$((checks + 1))
  if "$@"; then echo "ok   $name"; else echo "FAIL $name ($(lists); journal $( [ -e "$PENDING" ] && echo kept || echo gone))"; fails=$((fails + 1)); fi
}
t() { n=$((n + 1)); reset; }

t; before=$(lists)
choose $PKG radeon >/dev/null
check "choose radeon: only our entries move" [ "$(lists)" = "pre= in=a.one,b.two out=c.three,$PKG" ]
check "choose writes a journal first" [ -s "$PENDING" ]
restore_pending >/dev/null
check "round trip restores every list exactly" [ "$(lists)" = "$before" ]
check "round trip removes the journal" [ ! -e "$PENDING" ]

t; printf '%s\n' "$PKG,x.y" > "$ST/$PRE_IN"; before=$(lists)
choose $PKG nvidia >/dev/null
check "a prerelease entry is removed for the run" [ "$(cat "$ST/$PRE_IN")" = x.y ]
restore_pending >/dev/null
check "a prerelease entry comes back" [ "$(lists)" = "$before" ]

t; choose $PKG radeon >/dev/null; FAIL_READ=1
restore_pending >/dev/null 2>&1; rc=$?
check "read failure: restore fails" [ $rc = 1 ]
check "read failure: journal kept" [ -s "$PENDING" ]
unset FAIL_READ; restore_pending >/dev/null
check "read failure: a later restore completes" [ "$(lists)" = "pre= in=a.one,$PKG,b.two out=c.three" ]

t; choose $PKG radeon >/dev/null; FAIL_WRITE=1
restore_pending >/dev/null 2>&1; rc=$?
check "write failure: restore fails" [ $rc = 1 ]
check "write failure: journal kept" [ -s "$PENDING" ]

t; choose $PKG radeon >/dev/null; SILENT_WRITE=1
restore_pending >/dev/null 2>&1; rc=$?
check "write that changes nothing: read-back catches it" [ $rc = 1 ]
check "write that changes nothing: journal kept" [ -s "$PENDING" ]

t; choose $PKG radeon >/dev/null; ADB_DOWN=1
restore_pending >/dev/null 2>&1; rc=$?
check "adb down: restore fails, journal kept" [ $rc = 1 ] && [ -s "$PENDING" ]

t; before=$(lists); WRITES_OK=1
choose $PKG radeon >/dev/null 2>&1; rc=$?
check "partial set (second write fails): choose fails" [ $rc = 1 ]
check "partial set: journal kept" [ -s "$PENDING" ]
unset WRITES_OK; rm -f "$T/writes"; restore_pending >/dev/null
check "partial set: restore undoes the part applied" [ "$(lists)" = "$before" ]

t; choose $PKG nvidia >/dev/null
check "already the choice: no journal" [ ! -e "$PENDING" ]

t; choose $PKG automatic >/dev/null
printf '%s\n' "c.three,$PKG" > "$ST/$OPT_OUT"            # the owner picks Radeon during the run
restore_pending >/dev/null
check "owner change kept" [ "$(lists)" = "pre= in=a.one,b.two out=c.three,$PKG" ]
check "owner change: journal removed" [ ! -e "$PENDING" ]

t; choose $PKG radeon >/dev/null
printf '%s\n' "a.one,$PKG,b.two" > "$ST/$OPT_IN"; printf '%s\n' "c.three" > "$ST/$OPT_OUT"   # owner put it back
restore_pending >/dev/null
check "already as before: journal removed, nothing written" [ ! -e "$PENDING" ] && [ "$(lists)" = "pre= in=a.one,$PKG,b.two out=c.three" ]

t; printf 'pkg=%s\noriginal=0 1\nset=0 0 1\n' $PKG > "$PENDING"
restore_pending >/dev/null 2>&1; rc=$?
check "unreadable journal: fails and is kept" [ $rc = 1 ] && [ -s "$PENDING" ]

t; printf '%s\n' "a.one,b'c" > "$ST/$OPT_OUT"
choose $PKG radeon >/dev/null 2>&1; rc=$?
check "a list with odd characters is never rewritten" [ $rc = 1 ] && [ "$(cat "$ST/$OPT_OUT")" = "a.one,b'c" ]

t; choose $PKG radeon >/dev/null      # the Checker's case: NVIDIA -> Radeon, set and verified. Automatic (0 0 0) lies
                                      # on that set's way, so only the journal's phase tells the owner's choice apart
check "a completed set is journalled phase=set" grep -qx phase=set "$PENDING"
printf '%s\n' "a.one,b.two" > "$ST/$OPT_IN"; printf '%s\n' "c.three" > "$ST/$OPT_OUT"   # owner picks Automatic
restore_pending >/dev/null
check "after a completed set, the owner's Automatic is kept" [ "$(lists)" = "pre= in=a.one,b.two out=c.three" ]
check "after a completed set, the journal goes" [ ! -e "$PENDING" ]

t; before=$(lists); choose $PKG radeon >/dev/null; WRITES_OK=1
restore_pending >/dev/null 2>&1; rc=$?                    # the restore stops after its first write
check "interrupted restore: fails, journal phase=restoring" [ $rc = 1 ] && grep -qx phase=restoring "$PENDING"
unset WRITES_OK; rm -f "$T/writes"; restore_pending >/dev/null
check "interrupted restore: a later restore completes it" [ "$(lists)" = "$before" ] && [ ! -e "$PENDING" ]

t; choose $PKG radeon >/dev/null; WRITES_OK=1
restore_pending >/dev/null 2>&1
unset WRITES_OK; rm -f "$T/writes"
printf '%s\n' "x.y,$PKG" > "$ST/$PRE_IN"                 # then the owner does something no restore step does
restore_pending >/dev/null
check "interrupted restore: an owner change off its way is kept" grep -qxF "x.y,$PKG" "$ST/$PRE_IN" && [ ! -e "$PENDING" ]

echo "$n cases, $checks checks, $fails failure(s)"
[ $fails = 0 ]
