#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Per-app performance of an OpenBook laptop over adb (ANAL-378, docs/app-performance.md): is an app's native code
# translated, is its code compiled, how long its process-cold and warm starts take, and where its CPU time goes,
# measured the same way every time. scripts/perf/app-perf.py does the work; this wrapper takes the G14 lock and
# connects. Frames come from scripts/gpu-diag.sh run.
#
# usage: app-perf.sh [-a ADDR[:PORT] | -s SERIAL] COMMAND [ARGS]       (python3 scripts/perf/app-perf.py --help)
#   state OUT | inventory OUT [PKG...] | start OUT PKG | cpu OUT PKG [--translator] | dexopt OUT PKG --filter F --yes |
#   table DIR... | restore
#   -a ADDR  the G14 (default: the first OpenBook device found by mDNS, as g14-adb.sh). The command holds the G14
#            lock (g14-lock.sh) while it runs, and the idle gate wants 10 minutes without input
#   -s SERIAL another device on this adb server, such as a test VM: no lock, and the gate wants no idle minutes
#
# Env: as g14-adb.sh (OPENBOOK_G14_ADDR, ADB, ANDROID_ADB_SERVER_PORT); OPENBOOK_G14_OWNER names the task holding the
#      lock (default app-perf); OPENBOOK_G14_LOCK_WAIT waits for another session; OPENBOOK_APP_PERF_IDLE_MIN sets the
#      gate's minutes.
# Writes on the device: its files in /data/local/tmp/openbook-app-perf (removed at the end); the app is started and
# force-stopped (only an app that wasn't running); cpu makes adbd root (undone at the end); cpu --translator sets
# berberis.stats and berberis.profiling for the run (put back after) and removes the perf maps the app wrote into its
# data directory; start and cpu --pcache MODE set berberis.pcache to MODE:PKG for the run (root), put back after the
# app is stopped, and record the size of the cache it left (arm-corpus.sh pcache-clear removes it); start --fixed-performance
# and --platform-profile change one power setting for the run, journalled on the host first and put back (exit 4 and
# a kept journal if that fails; then only `restore` runs); dexopt --yes recompiles one app. No install, uninstall,
# data clearing or reboot.
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
CMD=${1:?usage: app-perf.sh [-a ADDR[:PORT] | -s SERIAL] state|inventory|start|cpu|dexopt|table|restore ...}
[ "$CMD" = table ] && exec python3 "$R/scripts/perf/app-perf.py" "$@"
[ -x "$ADB" ] || { echo "no adb at $ADB (set ADB=)" >&2; exit 2; }
mkdir -p "$A/locks"
if [ -z "$SERIAL" ]; then
  if [ -z "${OPENBOOK_G14_LOCK_OWNER:-}" ]; then
    exec "$R/scripts/g14-lock.sh" run "${OPENBOOK_G14_OWNER:-app-perf}" ${OPENBOOK_G14_LOCK_WAIT:+-w "$OPENBOOK_G14_LOCK_WAIT"} \
      -- "$R/scripts/perf/app-perf.sh" "${ARGS[@]}"
  fi
  out=$("$R/scripts/g14-adb.sh" ${ADDR:+-a "$ADDR"} connect) || { echo "$out" >&2; exit 2; }
  SERIAL=$(sed -n 's/^connected: \([^ ]*\).*/\1/p' <<<"$out")
  [ -n "$SERIAL" ] || { echo "app-perf: no serial in: $out" >&2; exit 2; }
  JOURNAL=${OPENBOOK_G14_LOCK:-$A/locks/g14.lock}.app-perf-restore
  IDLE=${OPENBOOK_APP_PERF_IDLE_MIN:-10}
else
  JOURNAL=$A/locks/app-perf-restore-${SERIAL//[^A-Za-z0-9._-]/_}
  IDLE=${OPENBOOK_APP_PERF_IDLE_MIN:-0}
fi
exec python3 "$R/scripts/perf/app-perf.py" --serial "$SERIAL" --adb "$ADB" --journal "$JOURNAL" --idle-min "$IDLE" "$@"
