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
#   ota PACKAGE [--yes] [--reboot] [--dry-run]
#                           an A/B image update of the inactive slot (ANAL-223, docs/adb-debug.md "Updating the
#                           installed system"): PACKAGE is a full OTA from scripts/ota/make-ota.sh (PACKAGE.json and
#                           PACKAGE's openbook-bootsync next to it). Checks the device and the package, asks for the
#                           device's address as confirmation (--yes skips that), streams the package with AOSP's
#                           update_device.py over this adb connection (update_engine writes the other slot; /data and
#                           the running slot are untouched), then verifies that systemd-boot will start the new slot
#                           next. On a system without openbook-bootsync (older images) it runs the package's copy once
#                           as root for that. Prints the reboot and rollback steps; --reboot also reboots, waits and
#                           runs ota-status. --dry-run: the checks only
#   state [OUT.json]        read-only facts an update must keep: build, slot, users, packages and versions, Settings,
#                           screen lock, Wi-Fi networks and accounts (counted), shared storage size (ANAL-223)
#   ota-status              after the reboot: slot, build, the ESP's entries (openbook-bootsync status), boot HAL,
#                           update_engine and the virtual A/B merge
#   ota-cancel              before rebooting: undo an applied update (update_engine_client --reset_status; the ESP back
#                           to the running slot)
#
# Env: OPENBOOK_G14_ADDR      ADDR[:PORT] (default: the first "OpenBook on ..." device found by mDNS, port 5555)
#      ADB                    default <data dir>/android-sdk/platform-tools/adb
#      ANDROID_ADB_SERVER_PORT default 5222, a private adb server, so other runs' servers are untouched
# Read-only on the G14, except: capture makes adbd root (adb root, undone at the end) and mounts debugfs (as the
# stick does), writes its scripts to /data/local/tmp/openbook-adb/, and --hwtest may switch Wi-Fi and Bluetooth on;
# persist-logs changes the logpersist properties (logpersist.start/stop also close the Settings app so it reloads
# them). Nothing here reboots, flashes or remounts, except ota (writes the inactive slot, the copy-on-write data in
# /data and the ESP's loader entry; reboots only with --reboot) and ota-cancel.
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/.." && pwd)
ADB=${ADB:-$A/android-sdk/platform-tools/adb}
export ANDROID_ADB_SERVER_PORT=${ANDROID_ADB_SERVER_PORT:-5222}
ADDR=${OPENBOOK_G14_ADDR:-}
D=/data/local/tmp/openbook-adb
[ "${1:-}" = -a ] && { ADDR=$2; shift 2; }
CMD=${1:?usage: g14-adb.sh [-a ADDR[:PORT]] find|connect|shell|wait|capture|logcat|persist-logs|pair|state|ota|ota-status|ota-cancel ...}; shift
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
state)
  # Read-only facts that an update must keep (ANAL-223): build and slot, users, every package with its version,
  # Settings (global, secure, system), the screen lock, saved Wi-Fi networks and accounts (counted), the shared
  # storage's size, file count and a hash of its file list (names, sizes, times; while unlocked). JSON to OUT
  # (default stdout). It names the owner's apps and settings: keep it on the build host, not in evidence.
  OUT=${1:-}; resolve; connect; become_root
  a shell 'echo "@prop fingerprint=$(getprop ro.build.fingerprint)"; echo "@prop build_date_utc=$(getprop ro.build.date.utc)"
    echo "@prop slot=$(getprop ro.boot.slot_suffix)"; echo "@prop vbmeta=$(getprop ro.boot.vbmeta.digest)"
    echo "@prop serialno=$(getprop ro.boot.serialno)"; echo "@prop selinux=$(getenforce)"
    echo "@prop boot_completed=$(getprop sys.boot_completed)"; echo "@prop user_state=$(am get-started-user-state 0 2>/dev/null)"
    echo "@prop lock_disabled=$(cmd lock_settings get-disabled 2>/dev/null)"
    echo "@prop wifi_networks=$(cmd wifi list-networks 2>/dev/null | tail -n +2 | grep -c .)"
    echo "@prop accounts=$(dumpsys account 2>/dev/null | sed -n "s/^ *Accounts: //p" | head -n 1)"
    echo "@prop media_files=$(find /data/media/0 -type f 2>/dev/null | wc -l)"; echo "@prop media_kib=$(du -sk /data/media/0 2>/dev/null | cut -f1)"
    # The user'"'"'s files without MediaProvider'"'"'s own databases (.transforms rotates at every boot): names, sizes, times.
    echo "@prop media_list_sha256=$(cd /data/media/0 2>/dev/null && find . -path ./.transforms -prune -o -type f -printf "%p %s %T@\n" | sort | sha256sum | cut -c1-64)"
    echo "@prop media_files_user=$(cd /data/media/0 2>/dev/null && find . -path ./.transforms -prune -o -type f -print | wc -l)"
    pm list users | sed -n "s/.*UserInfo{\(.*\)}.*/@user \1/p"
    pm list packages --show-versioncode -u 2>/dev/null | sed "s/^package:/@pkg /"
    for ns in global secure system; do settings list $ns 2>/dev/null | sed "s/^/@set $ns /"; done' | tr -d '\r' |
    python3 -c "$(cat <<'PYEOF'
import json, sys
s = {"props": {}, "users": [], "packages": {}, "settings": {"global": {}, "secure": {}, "system": {}}}
for line in sys.stdin:
    line = line.rstrip("\n")
    kind, _, rest = line.partition(" ")
    if kind == "@prop":
        k, _, v = rest.partition("=")
        s["props"][k] = v
    elif kind == "@user":
        s["users"].append(rest)
    elif kind == "@pkg":
        name, _, ver = rest.partition(" versionCode:")
        s["packages"][name] = ver
    elif kind == "@set":
        ns, _, kv = rest.partition(" ")
        k, _, v = kv.partition("=")
        if ns in s["settings"]:
            s["settings"][ns][k] = v
print(json.dumps(s, indent=1, sort_keys=True))
PYEOF
)" > "${OUT:-/dev/stdout}"
  [ -z "$OUT" ] || echo "state of $SERIAL: $OUT" >&2
  unroot
  ;;
ota)
  PKG=; YES=0; REBOOT=0; DRY=0
  while [ $# -gt 0 ]; do
    case $1 in
      --yes) YES=1; shift ;;
      --reboot) REBOOT=1; shift ;;
      --dry-run) DRY=1; shift ;;
      -*) echo "unknown option: $1" >&2; exit 2 ;;
      *) PKG=$1; shift ;;
    esac
  done
  [ -f "$PKG" ] || { echo "usage: g14-adb.sh ota PACKAGE.zip [--yes] [--reboot] [--dry-run]" >&2; exit 2; }
  PKG=$(realpath "$PKG"); MAN=${PKG%.zip}.json; BS=${PKG%.zip}.bootsync
  [ -f "$MAN" ] && [ -f "$BS" ] || { echo "$MAN and $BS missing: build the package with scripts/ota/make-ota.sh" >&2; exit 2; }
  UPD=${UPDATE_DEVICE:-$A/aosp/src/system/update_engine/scripts/update_device.py}
  [ -f "$UPD" ] || { echo "no update_device.py at $UPD (set UPDATE_DEVICE=)" >&2; exit 2; }
  resolve; LOGD=$A/installer/g14/ota-$(utc); mkdir -p "$LOGD"
  exec > >(tee -a "$LOGD/ota.log") 2>&1
  echo "OTA of $SERIAL with $PKG, $(date -u +%FT%TZ); log: $LOGD/ota.log"
  connect; become_root
  T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
  # ---- the package: its manifest (make-ota.sh) against the zip itself
  python3 - "$PKG" "$MAN" "$BS" > "$T/pkg.env" <<'PYEOF'
import hashlib, json, shlex, sys, zipfile
pkg, man, bs = sys.argv[1:4]
m = json.load(open(man))
h = hashlib.sha256()
with open(pkg, "rb") as f:
    for b in iter(lambda: f.read(1 << 22), b""):
        h.update(b)
z = zipfile.ZipFile(pkg)
meta = dict(l.split("=", 1) for l in z.read("META-INF/com/android/metadata").decode().splitlines() if "=" in l)
bsh = hashlib.sha256(open(bs, "rb").read()).hexdigest()
problems = []
if h.hexdigest() != m["sha256"]: problems.append("the package's sha256 differs from its manifest")
if bsh != m["bootsync_sha256"]: problems.append("the bootsync binary's sha256 differs from the manifest")
if "payload.bin" not in z.namelist(): problems.append("no payload.bin: not an A/B package")
if meta.get("ota-type") != "AB": problems.append(f"ota-type {meta.get('ota-type')}, not AB")
if meta.get("pre-build"): problems.append("an incremental package: only full packages are supported here")
for k, v in (("PKG_DEVICE", meta.get("pre-device", "")), ("PKG_FP", meta.get("post-build", "")),
             ("PKG_TS", meta.get("post-timestamp", "0")), ("PKG_VBMETA", m.get("vbmeta_digest", "")),
             ("PKG_LABEL", m.get("label", "")), ("PKG_TREE", m.get("tree", "")),
             ("PKG_BYTES", str(m.get("bytes", 0))), ("PKG_PROBLEMS", "; ".join(problems))):
    print(f"{k}={shlex.quote(v)}")  # sourced below: a quote in the manifest's tree must stay text
PYEOF
  . "$T/pkg.env"
  # ---- the device
  a shell 'echo "DEV_DEVICE=$(getprop ro.product.device)"; echo "DEV_FP=$(getprop ro.build.fingerprint)";
    echo "DEV_TS=$(getprop ro.build.date.utc)"; echo "DEV_SLOT=$(getprop ro.boot.slot_suffix)";
    echo "DEV_VBMETA=$(getprop ro.boot.vbmeta.digest)"; echo "DEV_VAB=$(getprop ro.virtual_ab.enabled)";
    echo "DEV_INSTALLED=$(getprop ro.boot.openbook.installed)"; echo "DEV_DATA_FREE=$(df -k /data | tail -n 1 | awk "{print \$4}")";
    echo "DEV_BOOTSYNC=$([ -x /vendor/bin/openbook-bootsync ] && echo yes || echo no)";
    echo "DEV_AC=$(dumpsys battery | grep -cE "(AC|USB|Wireless) powered: true")"; echo "DEV_BATT=$(dumpsys battery | sed -n "s/^ *level: //p")";
    echo "DEV_PRESENT=$(dumpsys battery | sed -n "s/^ *present: //p")";
    echo "DEV_UE=$(timeout 10 update_engine_client --follow 2>&1 | grep -o "UPDATE_STATUS_[A-Z_]*" | tail -n 1)"' |
    tr -d '\r' | sed -n "s/^\(DEV_[A-Z_]*\)=\(.*\)$/\1='\2'/p" > "$T/dev.env"
  . "$T/dev.env"
  CUR=${DEV_SLOT#_}; case $CUR in a) TGT=b ;; b) TGT=a ;; *) echo "no A/B slot on $SERIAL (ro.boot.slot_suffix='$DEV_SLOT')" >&2; exit 1 ;; esac
  echo
  echo "device    $SERIAL: $DEV_FP"
  echo "          slot $CUR, vbmeta $DEV_VBMETA, installed=${DEV_INSTALLED:-?}, virtual A/B ${DEV_VAB:-?}"
  echo "package   $PKG_LABEL ($(( PKG_BYTES / 1000000 )) MB): $PKG_FP"
  echo "          tree $PKG_TREE, vbmeta $PKG_VBMETA"
  echo "update    slot $CUR -> slot $TGT; /data and slot $CUR are kept; slot $CUR stays the fallback until slot $TGT boots"
  echo "bootsync  $([ "$DEV_BOOTSYNC" = yes ] && echo "on the device: the boot HAL moves the loader entry" ||
               echo "not on the device (older image): the package's copy runs once as root after update_engine")"
  bad=$PKG_PROBLEMS
  [ "$PKG_DEVICE" = "$DEV_DEVICE" ] || bad="$bad; the package is for '$PKG_DEVICE', the device is '$DEV_DEVICE'"
  [ "${PKG_TS:-0}" -ge "${DEV_TS:-0}" ] || bad="$bad; the package is older than the running build (a downgrade)"
  [ "$DEV_VAB" = true ] || bad="$bad; the device has no virtual A/B"
  [ "$DEV_INSTALLED" = whole ] || bad="$bad; not a whole-disk OpenBook install (installed='$DEV_INSTALLED')"
  [ "$DEV_UE" = UPDATE_STATUS_IDLE ] || bad="$bad; update_engine is not idle ($DEV_UE): an update or merge is pending (ota-status)"
  [ "${DEV_DATA_FREE:-0}" -gt $(( PKG_BYTES / 512 )) ] || bad="$bad; /data has ${DEV_DATA_FREE} KiB free, at least twice the package is needed"
  [ "$DEV_PRESENT" != true ] || [ "${DEV_AC:-0}" -gt 0 ] || [ "${DEV_BATT:-0}" -ge 50 ] ||
    bad="$bad; on battery at ${DEV_BATT}%: plug the charger in (or charge to 50%)"
  bad=${bad#; }
  if [ -n "$bad" ]; then echo; echo "refused: $bad" >&2; exit 1; fi
  echo "checks    passed"
  [ $DRY = 1 ] && { echo "dry run: nothing written"; exit 0; }
  if [ $YES != 1 ]; then
    read -rp "Type the device's address (${SERIAL%:*}) to write slot $TGT: " ans
    [ "$ans" = "${SERIAL%:*}" ] || { echo "not confirmed: nothing written" >&2; exit 1; }
  fi
  # ---- stream it: update_engine downloads from the host through adb reverse and writes slot TGT
  echo; echo "== update_engine writes slot $TGT (DOWNLOADING: the write, then VERIFYING, FINALIZING)"
  t0=$(date +%s)
  PATH="$(dirname "$ADB"):$PATH" python3 "$UPD" -s "$SERIAL" "$PKG" 2>&1 | tee "$LOGD/update_device.log" |
    grep --line-buffered -E "onStatusUpdate|onPayloadApplicationComplete|ERROR|Error|error:" |
    awk -v t0="$t0" '
      match($0, /onStatusUpdate\(([A-Z_]+) \([0-9]+\), ([0-9.e+-]+)\)/, m) {
        k = m[1] " " int(m[2] * 100); if (k == last) next; last = k
        printf "[%4ds] %s %d%%\n", systime() - t0, m[1], int(m[2] * 100); fflush(); next }
      { printf "[%4ds] %s\n", systime() - t0, $0; fflush() }' || true
  connect >/dev/null; become_root
  UE=$(a shell 'timeout 10 update_engine_client --follow 2>&1; true' | tr -d '\r' | grep -o "UPDATE_STATUS_[A-Z_]*" | tail -n 1 || true)
  if ! grep -q "onPayloadApplicationComplete(ErrorCode::kSuccess" "$LOGD/update_device.log" || [ "$UE" != UPDATE_STATUS_UPDATED_NEED_REBOOT ]; then
    echo "update_engine did not finish (status $UE); nothing will switch at the next boot. Its log: $LOGD/update_device.log" >&2
    a shell "logcat -d -s update_engine | tail -n 40" | tr -d '\r' >&2 || true
    exit 1
  fi
  echo "update_engine: slot $TGT written in $(( $(date +%s) - t0 )) s ($UE)"
  # ---- the loader entry
  if [ "$DEV_BOOTSYNC" = yes ]; then
    BSX=/vendor/bin/openbook-bootsync
  else
    echo "openbook-bootsync from the package (first update onto a system without it), as root"
    a shell "mkdir -p $D" && a push -q "$BS" "$D/openbook-bootsync" >/dev/null && a shell "chmod 755 $D/openbook-bootsync"
    BSX=$D/openbook-bootsync
    if ! a shell "$BSX --json activate $TGT" > "$LOGD/bootsync-activate.json" 2> "$LOGD/bootsync-activate.log"; then
      cat "$LOGD/bootsync-activate.log" "$LOGD/bootsync-activate.json" >&2
      echo "bootsync failed: undoing the update (update_engine_client --reset_status); slot $CUR stays" >&2
      a shell "update_engine_client --reset_status" >&2 || true
      exit 1
    fi
    tr -d '\r' < "$LOGD/bootsync-activate.log" | sed 's/^/  /'
  fi
  a shell "$BSX --json status" | tr -d '\r' > "$LOGD/bootsync-status.json"
  python3 - "$LOGD/bootsync-status.json" "$TGT" "$PKG_VBMETA" <<'PYEOF' || { echo "verification failed: run ota-cancel before rebooting" >&2; exit 1; }
import json, sys
s, t, vb = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
sl = s["slots"][t]
ok = (s.get("next_boot_slot") == t and sl.get("images_ok") and sl.get("vbmeta_digest") == vb and
      sl.get("esp_files") == "in_sync" and sl.get("entry_state") == "pending")
print(f"verified  slot {t}: images match vbmeta_{t} ({sl.get('vbmeta_digest', '')[:16]}..., the package's), ESP files "
      f"{sl.get('esp_files')}, entry {sl.get('entry')}; systemd-boot starts slot {s.get('next_boot_slot')} next"
      if ok else f"NOT verified: {json.dumps(s)[:600]}")
sys.exit(0 if ok else 1)
PYEOF
  cat <<EOM

Slot $TGT is ready. Nothing changes until the next boot; slot $CUR and /data are as they were.
  Reboot:     g14-adb.sh -a $SERIAL shell reboot      then: g14-adb.sh -a $SERIAL wait && g14-adb.sh -a $SERIAL ota-status
  Not yet:    g14-adb.sh -a $SERIAL ota-cancel        (before rebooting: slot $CUR stays, as if nothing happened)
If slot $TGT does not come up: it gets 3 tries. Hold the power button 10 s to force each restart; after the third
failed start systemd-boot starts slot $CUR again by itself, with /data as it was. To pick a slot by hand: hold a key
while powering on and choose "OpenBook (17 · slot ${CUR^^})". Slot $TGT counts as good once Android has booted it
(markBootSuccessful); from then on update_engine merges, and slot $CUR is no longer a fallback.
EOM
  a shell "rm -rf $D" >/dev/null 2>&1 || true
  if [ $REBOOT = 1 ]; then
    echo; echo "rebooting $SERIAL"; a reboot >/dev/null 2>&1 || true; sleep 20
    "$0" -a "$SERIAL" wait 900 && "$0" -a "$SERIAL" ota-status
  fi
  ;;
ota-status)
  resolve; connect; become_root
  a shell 'echo "build: $(getprop ro.build.fingerprint) ($(getprop ro.build.date))"
    echo "slot: $(getprop ro.boot.slot_suffix)  vbmeta: $(getprop ro.boot.vbmeta.digest)"
    echo "boot HAL: openbook [$(getprop init.svc.vendor.boot-openbook)] AOSP default [$(getprop init.svc.vendor.boot-default)]"
    echo "update_engine: $(timeout 10 update_engine_client --follow 2>&1 | grep -o "UPDATE_STATUS_[A-Z_]*" | tail -n 1)"
    echo "snapshots: $(snapshotctl dump 2>&1 | grep -iE "update.?state" | head -n 1)"
    logcat -d -b all 2>/dev/null | grep -E "Merge finished|bootsync|fell back" | grep -v " adbd " | tail -n 12
    [ -x /vendor/bin/openbook-bootsync ] && /vendor/bin/openbook-bootsync --json status 2>/dev/null ||
      echo "(no openbook-bootsync on this image)"' | tr -d '\r' | python3 -c "$(cat <<'PYEOF'
import json, sys
for line in sys.stdin:
    line = line.rstrip("\n")
    if not line.startswith('{"schema":"openbook-bootsync/1"'):
        print(line)
        continue
    s = json.loads(line)
    lc = s.get("loader_conf", {})
    print(f"ESP: systemd-boot starts slot {s.get('next_boot_slot')} next; loader.conf default {lc.get('default')}, "
          f"preferred {lc.get('preferred')}")
    for k, v in s.get("slots", {}).items():
        print(f"  slot {k}: entry {v.get('entry')} ({v.get('entry_state')}), images {'ok' if v.get('images_ok') else '-'}, "
              f"ESP files {v.get('esp_files', '-')}, vbmeta {(v.get('vbmeta_digest') or '-')[:16]}")
PYEOF
)"
  unroot
  ;;
ota-cancel)
  resolve; connect; become_root
  a shell 'update_engine_client --reset_status; sleep 2; timeout 10 update_engine_client --follow 2>&1 | grep -o "UPDATE_STATUS_[A-Z_]*" | tail -n 1' | tr -d '\r'
  CUR=$(a shell getprop ro.boot.slot_suffix | tr -d '\r'); CUR=${CUR#_}
  if a shell '[ -x /vendor/bin/openbook-bootsync ]'; then
    a shell "/vendor/bin/openbook-bootsync activate $CUR" | tr -d '\r'
  else
    echo "this image has no openbook-bootsync: push the package's copy and run 'activate $CUR' as root, or let the" \
         "boot fall back (the new slot's entry has 3 tries)" >&2
  fi
  unroot
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
