#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# The ARM-translation corpus on an OpenBook laptop over adb (ANAL-380, docs/arm-performance.md): fetch and check the
# pinned APKs, install a corpus app with its native code forced to arm64 (translated) or x86_64 (native), remove what
# was installed, and run CoreMark and simd-bench as arm64 and x86_64 executables on each core type.
# scripts/perf/arm-corpus.py does the work; this wrapper takes the G14 lock and connects.
#
# usage: arm-corpus.sh [-a ADDR[:PORT] | -s SERIAL] COMMAND [ARGS]     (python3 scripts/perf/arm-corpus.py --help)
#   list | fetch | install OUT ID --abi arm64-v8a|x86_64 | remove OUT [ID...] | exe OUT [--rounds N] [--poll S]
#   -a ADDR  the G14 (default: the first OpenBook device found by mDNS, as g14-adb.sh). The command holds the G14
#            lock (g14-lock.sh) while it runs, and the idle gate wants 10 minutes without input
#   -s SERIAL another device on this adb server, such as a test VM: no lock, and the gate wants no idle minutes
#
# Env: as app-perf.sh (OPENBOOK_G14_ADDR, ADB, ANDROID_ADB_SERVER_PORT, OPENBOOK_G14_OWNER, OPENBOOK_G14_LOCK_WAIT);
#      OPENBOOK_ARM_CORPUS_IDLE_MIN sets the gate's minutes.
# Writes on the device: install adds one corpus test package (refused if that package is installed and isn't this
# tool's own install: journalled on the host per device, and its installed APK one this tool installs) and marks its
# ungranted runtime permissions user-fixed, so no prompt covers its starts; remove uninstalls only this tool's own
# installs, each removal confirmed; exe runs its executables from /data/local/tmp/openbook-arm-corpus, stops them on
# input, failure or a signal, and removes the directory only once none is confirmed running. Without a confirmed
# answer from the device nothing is installed, replaced, removed or deleted. No owner app or data is touched, nothing
# is cleared, no setting is changed, no reboot.
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
ADB=${ADB:-$A/android-sdk/platform-tools/adb}
export ANDROID_ADB_SERVER_PORT=${ANDROID_ADB_SERVER_PORT:-5222}
ARGS=("$@")
ADDR=${OPENBOOK_G14_ADDR:-}
SERIAL=
case ${1:-} in
  -a) ADDR=$2; shift 2 ;;
  -s) SERIAL=$2; shift 2 ;;
esac
CMD=${1:?usage: arm-corpus.sh [-a ADDR[:PORT] | -s SERIAL] list|fetch|install|remove|exe ...}
case $CMD in list|fetch) exec python3 "$R/scripts/perf/arm-corpus.py" "$@" ;; esac
[ -x "$ADB" ] || { echo "no adb at $ADB (set ADB=)" >&2; exit 2; }
mkdir -p "$A/locks"
JOURNAL=$A/locks/arm-corpus-installs.json
if [ -z "$SERIAL" ]; then
  if [ -z "${OPENBOOK_G14_LOCK_OWNER:-}" ]; then
    exec "$R/scripts/g14-lock.sh" run "${OPENBOOK_G14_OWNER:-arm-corpus}" ${OPENBOOK_G14_LOCK_WAIT:+-w "$OPENBOOK_G14_LOCK_WAIT"} \
      -- "$R/scripts/perf/arm-corpus.sh" "${ARGS[@]}"
  fi
  out=$("$R/scripts/g14-adb.sh" ${ADDR:+-a "$ADDR"} connect) || { echo "$out" >&2; exit 2; }
  SERIAL=$(sed -n 's/^connected: \([^ ]*\).*/\1/p' <<<"$out")
  [ -n "$SERIAL" ] || { echo "arm-corpus: no serial in: $out" >&2; exit 2; }
  IDLE=${OPENBOOK_ARM_CORPUS_IDLE_MIN:-10}
else
  IDLE=${OPENBOOK_ARM_CORPUS_IDLE_MIN:-0}
fi
exec python3 "$R/scripts/perf/arm-corpus.py" --serial "$SERIAL" --adb "$ADB" --journal "$JOURNAL" --idle-min "$IDLE" "$@"
