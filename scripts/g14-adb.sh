#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Debug an installed OpenBook G14 over the network with adb, instead of booting the stick's "save logs" entry
# (ANAL-222, docs/adb-debug.md). The G14 has no USB device-mode controller (/sys/class/udc is empty), so adb runs
# over IP only: adbd listens on tcp:5555 whenever it runs (there is no USB gadget to listen on instead), and on a
# random TLS port while Wireless debugging is on. Every command here uses a private adb server and only ever
# talks to the one OpenBook address; other devices on the LAN are never connected to.
#
# usage: g14-adb.sh [-a ADDR[:PORT]] COMMAND [ARGS]
#   find                    OpenBook devices advertising adb on the LAN (mDNS _adb._tcp and _adb-tls-connect._tcp)
#   connect                 connect, then print the build, uptime, SELinux mode and adbd's uid
#   shell [CMD...]          adb shell on the G14
#   wait [SECONDS]          after a reboot: wait (default 600 s) until adb answers and sys.boot_completed=1
#   capture [OPTIONS] [DEST]
#                           what the stick's "save logs" entry saves, from the running system: hwtest-final.txt
#                           (with --hwtest), collect-final.txt (live-init.c's COLLECT script, run as is),
#                           logcat-final.txt, dmesg.txt, screen-final.png, summary.json, prior-boots.{txt,tar.gz}
#                           unpacked into prior/; then report.md/json (live-report.py --expect g14) and avc.md/json
#                           (avc-summary.py). DEST default <data dir>/installer/g14/adb-<UTC>.
#       --hwtest            also run openbook-hwtest first (Wi-Fi, Bluetooth, audio, arm64 bridge). The speaker tone
#                           stays off unless OPENBOOK_HWTEST_TONE=1; OPENBOOK_HWTEST_IPERF3_SERVER=<host> adds iperf3
#       --bugreport         also save adb bugreport (bugreport.zip; a few minutes)
#       --redact OUT        also write a masked copy of the text files for evidence (live-report.py --redact; no
#                           screen capture, no prior/). Full logs of the installed system stay on the host
#       --keep-root         leave adbd running as root (default: back to uid shell if this run made it root)
#   logcat [ARGS...]        follow logcat -v threadtime ARGS (-b kernel: the kernel log), also appended to
#                           <data dir>/installer/g14/adb-logcat-<UTC>.txt; reconnects and resumes after a drop
#   persist-logs on|off|status
#                           logcat, kernel log included, kept across boots in /data/misc/logd (logpersist, 16
#                           files, as device/anybook/common/pc/pc.mk sets it). "off" stops it and keeps the files
#   pair HOST:PORT          pair with Wireless debugging's "Pair device with pairing code" (asks for the code).
#                           Only needed once adbd asks for authorization (ro.adb.secure=1)
#
# Env: OPENBOOK_G14_ADDR      ADDR[:PORT] (default: the first "OpenBook on ..." device found by mDNS, port 5555)
#      ADB                    default <data dir>/android-sdk/platform-tools/adb
#      ANDROID_ADB_SERVER_PORT default 5222, a private adb server, so other runs' servers are untouched
# Read-only on the G14, except: capture makes adbd root (adb root, undone at the end) and mounts debugfs (as the
# stick does), writes its scripts to /data/local/tmp/openbook-adb/, and --hwtest may switch Wi-Fi and Bluetooth on;
# persist-logs changes the logpersist properties (logpersist.start/stop also close the Settings app so it reloads
# them). Nothing here reboots, flashes or remounts.
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/.." && pwd)
ADB=${ADB:-$A/android-sdk/platform-tools/adb}
export ANDROID_ADB_SERVER_PORT=${ANDROID_ADB_SERVER_PORT:-5222}
ADDR=${OPENBOOK_G14_ADDR:-}
D=/data/local/tmp/openbook-adb
[ "${1:-}" = -a ] && { ADDR=$2; shift 2; }
CMD=${1:?usage: g14-adb.sh [-a ADDR[:PORT]] find|connect|shell|wait|capture|logcat|persist-logs|pair ...}; shift
[ -x "$ADB" ] || { echo "no adb at $ADB (set ADB=)" >&2; exit 2; }
utc() { date -u +%Y%m%dT%H%M%SZ; }

# mDNS: "proto addr port service given_name" per OpenBook advertisement (avahi, else adb's own mDNS client).
discover() {
  if command -v avahi-browse >/dev/null; then
    for t in _adb._tcp _adb-tls-connect._tcp; do
      timeout 10 avahi-browse -rpt "$t" 2>/dev/null |
        awk -F';' '$1 == "=" && $10 ~ /given_name=OpenBook on/ {
          n = $10; sub(/.*"given_name=/, "", n); sub(/".*/, "", n); print $3, $8, $9, $5, n }'
    done | sort -u
  else
    "$ADB" mdns services 2>/dev/null | awk '/_adb(-tls-connect)?\._tcp/ && /OpenBook|adb-/ {print "IPv4", $NF, "", $2, $1}'
  fi
}

resolve() {
  if [ -z "$ADDR" ]; then
    ADDR=$(discover | awk '$1 == "IPv4" && $4 == "_adb._tcp" {print $2 ":" $3; exit}')
    [ -n "$ADDR" ] || { echo "no OpenBook device advertises adb on this LAN; set OPENBOOK_G14_ADDR or -a ADDR" >&2; exit 2; }
  fi
  case $ADDR in *:*) SERIAL=$ADDR ;; *) SERIAL=$ADDR:5555 ;; esac
}

a() { "$ADB" -s "$SERIAL" "$@"; }

# adbd restarts (adb root, a Developer options toggle) and Wi-Fi power save leave a stale "offline" transport:
# drop it and connect again, up to five times.
connect() {
  local i out st
  for i in 1 2 3 4 5; do
    "$ADB" disconnect "$SERIAL" >/dev/null 2>&1 || true
    out=$(timeout 20 "$ADB" connect "$SERIAL" 2>&1 || true)
    st=$(timeout 20 "$ADB" -s "$SERIAL" get-state 2>&1 || true)
    [ "$st" = device ] && return 0
    case "$out $st" in
      *unauthorized*) echo "$SERIAL: unauthorized: on the G14, allow this computer (\"Always allow\")" >&2 ;;
      *refused*) echo "$SERIAL: connection refused: is USB debugging on (Settings > System > Developer options)?" >&2 ;;
    esac
    sleep 3
  done
  echo "could not connect to $SERIAL: $out $st" >&2
  return 1
}

# grab FILE CMD...: CMD's stdout into FILE; if the link dropped, connect again and run it once more.
grab() {
  local f=$1; shift
  if "$@" > "$f.part" 2>/dev/null; then mv "$f.part" "$f"; return 0; fi
  if connect && "$@" > "$f.part" 2>/dev/null; then mv "$f.part" "$f"; return 0; fi
  mv "$f.part" "$f" 2>/dev/null || true
  echo "  $(basename "$f"): incomplete (the link dropped twice)" >&2
  return 1
}

uid() { a shell id -u 2>/dev/null | tr -d '\r'; }

ROOTED=0
become_root() {
  [ "$(uid)" = 0 ] && return 0
  a root >/dev/null 2>&1 || true
  sleep 3
  connect
  if [ "$(uid)" = 0 ]; then ROOTED=1; else echo "adbd is not root (a user build?); some sections will be partial" >&2; fi
}
unroot() {
  [ $ROOTED = 1 ] || return 0
  a unroot >/dev/null 2>&1 || true
  sleep 3
  connect >/dev/null 2>&1 && echo "adbd back to uid $(uid)"
}

info() {
  a shell 'echo "$(getprop ro.product.model) on $(getprop ro.build.fingerprint)"; echo "up: $(uptime)";
    echo "SELinux $(getenforce); adbd uid $(id -u); boot_completed=$(getprop sys.boot_completed);" \
         "adb_enabled=$(settings get global adb_enabled) adb_wifi_enabled=$(settings get global adb_wifi_enabled)" \
         "ro.adb.secure=[$(getprop ro.adb.secure)]"' | tr -d '\r'
}

case $CMD in
find)
  discover | awk 'BEGIN {print "proto  address          port   service                name"} {printf "%-6s %-16s %-6s %-22s", $1, $2, $3, $4; $1 = $2 = $3 = $4 = ""; sub(/^ +/, ""); print " " $0}'
  ;;
connect)
  resolve; connect; echo "connected: $SERIAL (adb server port $ANDROID_ADB_SERVER_PORT)"; info
  ;;
shell)
  resolve; connect; exec "$ADB" -s "$SERIAL" shell "$@"
  ;;
wait)
  resolve; T=${1:-600}; t0=$(date +%s)
  while :; do
    if timeout 10 "$ADB" connect "$SERIAL" 2>/dev/null | grep -q '^connected\|already' &&
       [ "$(timeout 10 "$ADB" -s "$SERIAL" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; then
      echo "$SERIAL: boot completed, $(( $(date +%s) - t0 )) s after waiting started"; info; exit 0
    fi
    [ $(( $(date +%s) - t0 )) -lt "$T" ] || { echo "$SERIAL: no completed boot within $T s" >&2; exit 1; }
    "$ADB" disconnect "$SERIAL" >/dev/null 2>&1 || true
    sleep 5
  done
  ;;
capture)
  HWTEST=0; BUGREPORT=0; KEEP=0; RED=; DEST=
  while [ $# -gt 0 ]; do
    case $1 in
      --hwtest) HWTEST=1; shift ;;
      --bugreport) BUGREPORT=1; shift ;;
      --keep-root) KEEP=1; shift ;;
      --redact) RED=$2; shift 2 ;;
      -*) echo "unknown option: $1" >&2; exit 2 ;;
      *) DEST=$1; shift ;;
    esac
  done
  resolve; DEST=${DEST:-$A/installer/g14/adb-$(utc)}
  mkdir -p "$DEST"; LOG=$DEST/capture.log
  exec > >(tee -a "$LOG") 2>&1
  echo "capture of $SERIAL into $DEST, $(date -u +%FT%TZ)"
  T=$(mktemp -d); trap 'rm -rf "$T"; [ $KEEP = 1 ] || unroot' EXIT
  connect; become_root
  for n in COLLECT PRIOR_LIST PRIOR_BOOTS; do
    python3 "$R/scripts/installer/live-init-script.py" "$n" > "$T/$n.sh"
  done
  a shell "mkdir -p $D" && a push -q "$T"/COLLECT.sh "$T"/PRIOR_LIST.sh "$T"/PRIOR_BOOTS.sh "$D/" >/dev/null
  # The stick's order: hwtest first, so the logcat and system facts include what it did.
  if [ $HWTEST = 1 ]; then
    echo "openbook-hwtest (tone ${OPENBOOK_HWTEST_TONE:-0}; Wi-Fi scans may slow this link for a few seconds)"
    env="OPENBOOK_HWTEST_TONE=${OPENBOOK_HWTEST_TONE:-0}"
    [ -n "${OPENBOOK_HWTEST_IPERF3_SERVER:-}" ] && env="$env OPENBOOK_HWTEST_IPERF3_SERVER=$OPENBOOK_HWTEST_IPERF3_SERVER"
    grab "$DEST/hwtest-final.txt" a shell "$env timeout 360 /system_ext/bin/openbook-hwtest" || true
  fi
  echo "system facts (live-init.c COLLECT, about 30 s)"
  grab "$DEST/collect-final.txt" a shell "timeout 240 sh $D/COLLECT.sh" || true
  echo "logcat, kernel log, screen"
  grab "$DEST/logcat-final.txt" a shell logcat -d -b all -v threadtime || true
  grab "$DEST/dmesg.txt" a shell dmesg || true
  grab "$DEST/screen-final.png" a exec-out screencap -p || true
  echo "earlier boots: /data/misc/logd, tombstones, anr, dropbox"
  grab "$DEST/prior-boots.txt" a shell "sh $D/PRIOR_LIST.sh" || true
  grab "$DEST/prior-boots.tar.gz" a exec-out "sh $D/PRIOR_BOOTS.sh" || true
  if [ -s "$DEST/prior-boots.tar.gz" ]; then
    mkdir -p "$DEST/prior"
    tar -xzf "$DEST/prior-boots.tar.gz" -C "$DEST/prior" --no-same-owner --no-same-permissions 2>/dev/null ||
      echo "note: prior-boots.tar.gz is cut or damaged; unpacked what it holds"
  fi
  if [ $BUGREPORT = 1 ]; then
    echo "bugreport (a few minutes)"
    timeout 900 "$ADB" -s "$SERIAL" bugreport "$DEST/bugreport.zip" >/dev/null || echo "bugreport failed"
  fi
  a shell "rm -rf $D" || true
  # summary.json in the stick's schema, from what was just saved: props from collect's PROPS section, boot timing
  # from the kernel log (init's second stage) and the events log (boot_progress_enable_screen, sf_stop_bootanim).
  python3 "$R/scripts/installer/live-init-script.py" SUMMARY_PROPS > "$T/props.txt"
  python3 - "$DEST" "$T/props.txt" "$SERIAL" <<'EOF'
import json, re, sys
d, names, serial = sys.argv[1], open(sys.argv[2]).read().split(), sys.argv[3]
def read(f):
    try:
        return open(f"{d}/{f}", errors="replace").read()
    except OSError:
        return ""
col = read("collect-final.txt")
props = dict(re.findall(r"^\[([^\]]+)\]: \[(.*)\]$", col, re.M))
m = re.search(r"^\[\s*([\d.]+)\] init: init second stage started", read("dmesg.txt"), re.M)
lc = read("logcat-final.txt")
ev = {k: int(v) for k, v in re.findall(r" I (boot_progress_enable_screen|sf_stop_bootanim): (\d+)", lc)}
up = re.search(r"^===INFO===\n.*\n([\d.]+) ", col, re.M)
s = {"schema": "openbook-live-logs/1", "source": "adb", "serial": serial, "dir": d.rstrip("/").split("/")[-1],
     "uptime_s": float(up.group(1)) if up else None,
     "second_stage_s": float(m.group(1)) if m else None, "boot_completed": props.get("sys.boot_completed") == "1",
     "boot_completed_s": ev["boot_progress_enable_screen"] / 1000 if "boot_progress_enable_screen" in ev else None,
     "desktop_s": ev["sf_stop_bootanim"] / 1000 if "sf_stop_bootanim" in ev else None,
     "captures": [{"phase": "final"}], "props": {n: props.get(n, "") for n in names}}
json.dump(s, open(f"{d}/summary.json", "w"), indent=1)
EOF
  echo
  python3 "$R/scripts/installer/live-report.py" "$DEST" --expect g14 ${RED:+--redact "$RED"} | head -n 60 || true
  python3 "$R/scripts/installer/avc-summary.py" "$DEST" --json "$DEST/avc.json" --md "$DEST/avc.md" > /dev/null || true
  # The masked copy gets the AVC summary too, but not the screen capture: on the installed system it is the owner's
  # own screen, which no masking covers. It stays in DEST.
  [ -z "$RED" ] || { cp "$DEST/avc.json" "$DEST/avc.md" "$RED/" 2>/dev/null || true; rm -f "$RED/screen-final.png"; }
  echo; echo "saved: $(find "$DEST" -maxdepth 1 -type f | wc -l) files, $(du -sh "$DEST" | cut -f1), in $DEST"
  ;;
logcat)
  resolve; connect; F=$A/installer/g14/adb-logcat-$(utc).txt; mkdir -p "${F%/*}"
  echo "following logcat on $SERIAL; also in $F (Ctrl-C ends)" >&2
  since=()
  while :; do
    a logcat -v threadtime "${since[@]}" "$@" | tee -a "$F" || true
    echo "--- link dropped $(date -u +%TZ); reconnecting" | tee -a "$F" >&2
    connect || sleep 10
    # Resume after the last line saved, so nothing is shown twice.
    last=$(grep -oE '^[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{3}' "$F" | tail -n 1 || true)
    [ -z "$last" ] || since=(-T "$last")
  done
  ;;
persist-logs)
  resolve; connect
  case ${1:-status} in
    on) become_root; a shell 'logpersist.start --size=16' | tr -d '\r'; sleep 2; unroot ;;
    off) become_root; a shell 'logpersist.stop' | tr -d '\r'; sleep 2; unroot ;;
    status) ;;
    *) echo "usage: g14-adb.sh persist-logs on|off|status" >&2; exit 2 ;;
  esac
  a shell 'echo "persist.logd.logpersistd=[$(getprop persist.logd.logpersistd)] size=[$(getprop persist.logd.logpersistd.size)]" \
    "logcatd: $(getprop init.svc.logcatd)"' | tr -d '\r'
  ;;
pair)
  HP=${1:?usage: g14-adb.sh pair HOST:PORT (from Wireless debugging > Pair device with pairing code)}
  read -rsp "pairing code shown on the G14: " CODE; echo
  "$ADB" pair "$HP" "$CODE"
  ;;
*)
  echo "unknown command: $CMD" >&2; exit 2
  ;;
esac
