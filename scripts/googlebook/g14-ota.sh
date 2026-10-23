#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Wireless OpenBook OTA to the G14: stream a signed payload from this host into the laptop's other slot.
#
#   1. preflight   check-ota-fit.py: the payload fits the installed layout (partitions, sizes, snapshot space)
#   2. device      read-only over adb: the OpenBook certificate is installed (else update_engine refuses the
#                  payload anyway), the laptop has two slots, and which slot runs now
#   3. serve       serve-payload.py on this host's address toward the laptop only, for this update only
#   4. apply       adb shell update_engine_client --update --payload=http://HOST:PORT/payload.bin; update_engine
#                  streams it into the other slot, verifies it, and the boot HAL (bootsync) stages that slot
#   5. reboot      only with --reboot; afterwards the new slot must boot and is marked good, or after three
#                  failed boots systemd-boot returns to the old slot by itself
#
# Needs a release with the owner OTA policy (build-ota-trust-candidate.py --owner-ota-policy) on the laptop,
# and the two-slot layout. A physical update needs the owner's approval naming the release and the laptop:
# pass it as --approved "<release> to the G14".
#
# usage: g14-ota.sh SIGNED_DIR --layout LAYOUT.json --approved "RB-... to the G14" [--reboot] [--dry-run]
#        [--laptop 192.168.50.11] [--port 8090] [--via-adb]
#
# --via-adb: serve on this host's 127.0.0.1 only and let the laptop reach it through `adb reverse`
# (update_engine fetches http://127.0.0.1:PORT on the laptop; adb carries it over the encrypted
# wireless-debugging connection). Needed when the host firewall drops inbound LAN connections.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
OPENBOOK_OTACERTS=3e1529c919baf5bbe71c729e2f6884d034a589328af0fb41a1ae730ac3342a59
usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 2; }

SIGNED=; LAYOUT=; APPROVED=; REBOOT=0; DRY=0; LAPTOP=192.168.50.11; PORT=8090; VIA_ADB=0
[ $# -ge 1 ] || usage
SIGNED=$1; shift
while [ $# -gt 0 ]; do
  case $1 in
    --layout) LAYOUT=$2; shift 2 ;;
    --approved) APPROVED=$2; shift 2 ;;
    --reboot) REBOOT=1; shift ;;
    --dry-run) DRY=1; shift ;;
    --laptop) LAPTOP=$2; shift 2 ;;
    --port) PORT=$2; shift 2 ;;
    --via-adb) VIA_ADB=1; shift ;;
    *) usage ;;
  esac
done
[ -f "$SIGNED/payload.bin" ] && [ -f "$SIGNED/payload_properties.txt" ] || { echo "no signed payload in $SIGNED"; exit 2; }
[ -f "$LAYOUT" ] || { echo "--layout: the installed layout JSON (plan-ruby-ab.py) is required"; exit 2; }
say() { printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*"; }

say "1/5 preflight"
python3 "$HERE/check-ota-fit.py" --layout "$LAYOUT" --payload "$SIGNED/payload.bin"

say "2/5 device"
S=$($ADB devices | awk -v ip="$LAPTOP" '($1 ~ /^adb-RUBYLIVERESEARCH-/ || index($1, ip ":") == 1) && $2 == "device" {print $1; exit}')
if [ -z "$S" ]; then
  port=$($ADB mdns services 2>/dev/null | awk '/^adb-RUBYLIVERESEARCH-.*_adb-tls-connect/ {print $NF; exit}' | sed 's/.*://')
  [ -n "$port" ] && $ADB connect "$LAPTOP:$port" > /dev/null 2>&1 || true
  S=$($ADB devices | awk -v ip="$LAPTOP" '($1 ~ /^adb-RUBYLIVERESEARCH-/ || index($1, ip ":") == 1) && $2 == "device" {print $1; exit}')
fi
[ -n "$S" ] || { echo "the G14 is not reachable over adb"; exit 3; }
a() { timeout 60 "$ADB" -s "$S" shell "$@"; }
certs=$(a sha256sum /system/etc/security/otacerts.zip | cut -d' ' -f1)
slot=$(a getprop ro.boot.slot_suffix | tr -d '\r')
other=$([ "$slot" = _a ] && echo _b || echo _a)
a ls "/dev/block/by-name/boot$other" > /dev/null 2>&1 && two_slots=1 || two_slots=0
say "   running slot $slot; OpenBook certificate $([ "$certs" = "$OPENBOOK_OTACERTS" ] && echo yes || echo NO); second slot $([ $two_slots = 1 ] && echo yes || echo NO)"
[ "$certs" = "$OPENBOOK_OTACERTS" ] || { echo "the laptop does not carry the OpenBook OTA certificate; it would refuse this payload"; exit 4; }
[ $two_slots = 1 ] || { echo "the laptop has one slot; an OTA needs the two-slot layout (fresh install)"; exit 4; }

if [ $VIA_ADB = 1 ]; then
  HOST=127.0.0.1
else
  HOST=$(ip -4 route get "$LAPTOP" | sed -n 's/.* src \([0-9.]*\).*/\1/p')
  [ -n "$HOST" ] || { echo "no route to $LAPTOP"; exit 3; }
fi
URL="http://$HOST:$PORT/payload.bin"
HEADERS=$(cat "$SIGNED/payload_properties.txt")
say "   will stream $URL ($(stat -c %s "$SIGNED/payload.bin") bytes) into slot $other"
if [ $DRY = 1 ]; then say "dry run: nothing served or applied"; exit 0; fi
[ -n "$APPROVED" ] || { echo "a physical update needs --approved \"<release> to the G14\" (the owner's approval)"; exit 5; }
say "   approval: $APPROVED"

say "3/5 serve"
LOG=$(mktemp -t g14-ota-serve.XXXXXX)
python3 "$HERE/serve-payload.py" --dir "$SIGNED" --bind "$HOST" --port "$PORT" --idle-seconds 900 > "$LOG" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; [ $VIA_ADB = 1 ] && "$ADB" -s "$S" reverse --remove "tcp:$PORT" 2>/dev/null; say "   server log: $LOG"' EXIT
sleep 1; kill -0 $SERVER 2>/dev/null || { cat "$LOG"; echo "the payload server did not start"; exit 6; }
if [ $VIA_ADB = 1 ]; then
  "$ADB" -s "$S" reverse "tcp:$PORT" "tcp:$PORT" > /dev/null || { echo "adb reverse failed"; exit 6; }
  say "   laptop 127.0.0.1:$PORT -> this host's 127.0.0.1:$PORT through adb"
fi

say "4/5 apply"
set +e
# Snapshot setup, the hash-tree pass and postinstall take minutes: give the client up to an hour.
timeout 3600 "$ADB" -s "$S" shell "update_engine_client --update --follow --payload=$URL --headers=\"$HEADERS\"" 2>&1 | grep --line-buffered -E "onStatusUpdate|onPayloadApplicationComplete" | awk 'NR % 20 == 1 || /Complete/'
set -e
result=$(a logcat -d -s update_engine:I | grep -oE "ErrorCode::k[A-Za-z]+" | tail -1)
say "   update_engine: ${result:-unknown}"
[ "$result" = "ErrorCode::kSuccess" ] || { echo "the update did not complete; the running slot is unchanged"; exit 7; }
# OpenBook Update (if this image has it) shows "Restart to finish" now, not at its next check. The receiver
# takes the refresh only from the shell or the system; an image without the app ignores it.
a am broadcast --user current -a org.openbook.update.action.REFRESH -n org.openbook.update/.work.RefreshReceiver > /dev/null 2>&1 || true

if [ $REBOOT = 0 ]; then say "5/5 applied; reboot the laptop to switch to slot $other (or rerun with --reboot)"; exit 0; fi
say "5/5 reboot"
"$ADB" -s "$S" reboot || true
for _ in $(seq 1 120); do
  sleep 10
  "$ADB" connect "$LAPTOP" > /dev/null 2>&1 || true
  S=$($ADB devices | awk -v ip="$LAPTOP" '($1 ~ /^adb-RUBYLIVERESEARCH-/ || index($1, ip ":") == 1) && $2 == "device" {print $1; exit}')
  [ -n "$S" ] && [ "$(a getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] && break
done
now=$(a getprop ro.boot.slot_suffix | tr -d '\r')
say "   booted slot $now (expected $other); vbmeta $(a getprop ro.boot.vbmeta.digest | cut -c1-16)"
[ "$now" = "$other" ] || { echo "the laptop came back on $now: the new slot did not boot, systemd-boot fell back"; exit 8; }
