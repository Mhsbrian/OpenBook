#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run openbook-updater's scenarios on an Android device itself: its mksh (32-bit arithmetic,
# close-on-exec descriptors), toybox, one-true-awk and curl. The host suite (openbook-updater-test.py)
# cannot. Targets the laptop or an emulator; the synthetic listing is built from the device's own
# device name, build number and build ID.
#
# Writes only to a temporary directory under /data/local/tmp on the device and removes it at the end.
# Installs nothing and changes no system state. The live check is a read-only HTTPS request to
# Google's public listing.
#
# usage: openbook-updater-device-test.sh [LAPTOP_IP | --serial ADB_SERIAL]
#        (default 192.168.50.11; adb must be paired)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
D=/data/local/tmp/openbook-updater-test

if [ "${1:-}" = --serial ]; then
  S=${2:?adb serial}
else
  IP=${1:-192.168.50.11}
  S=$("$ADB" devices | awk -v ip="$IP" 'index($1, ip ":") == 1 && $2 == "device" {print $1; exit}')
  if [ -z "$S" ]; then
    ep=$("$ADB" mdns services 2>/dev/null | awk -v ip="$IP" '/_adb-tls-connect/ && index($NF, ip ":") == 1 {print $NF; exit}')
    [ -n "$ep" ] && "$ADB" connect "$ep" > /dev/null 2>&1
    S=$("$ADB" devices | awk -v ip="$IP" 'index($1, ip ":") == 1 && $2 == "device" {print $1; exit}')
  fi
  [ -n "$S" ] || { echo "the laptop at $IP is not reachable over adb"; exit 2; }
fi
a() { timeout 300 "$ADB" -s "$S" shell "$@"; }

DEVICE=$(a getprop ro.product.device | tr -d '\r'); BUILD=$(a getprop ro.build.version.incremental | tr -d '\r')
BUILD_ID=$(a getprop ro.build.id | tr -d '\r')
case $BUILD in ''|*[!0-9]*) echo "the device's build number '$BUILD' is not numeric"; exit 2 ;; esac
# A device whose build ID is not a release-train ID (an emulator's CLE3.260929.004) runs the scenarios with
# Googlebook's own ID (OPENBOOK_UPDATER_TEST_BUILD_ID); everything else is the device's.
TEST_ID=
case $BUILD_ID in [A-Z][A-Z][0-9][A-Z0-9].[0-9][0-9][0-9][0-9][0-9][0-9].*) ;; *) BUILD_ID=CL3B.260622.276.R4; TEST_ID=1 ;; esac
# The same train one branch date later (a monthly update), and the next quarter's train.
NEWER=$((BUILD + 1000))
TRAIN=${BUILD_ID%%.*}; REST=${BUILD_ID#*.}; DATE=${REST%%.*}
MONTHLY=$TRAIN.$((DATE + 100)).001
QUARTER=${TRAIN#??}; QUARTER=${QUARTER%?}
NEXT=$(printf '%.2s' "$TRAIN")$((QUARTER % 9 + 1))A.$((DATE + 300)).001
echo "device $DEVICE, build $BUILD ($BUILD_ID${TEST_ID:+, as a test build ID}); synthetic monthly $NEWER ($MONTHLY), next quarter ($NEXT)"

W=$(mktemp -d); trap 'rm -rf "$W"; a "rm -rf $D" > /dev/null 2>&1' EXIT
head -c 2000000 /dev/urandom > "$W/fake.zip"
MD5=$(md5sum "$W/fake.zip" | cut -c1-32)
entry() { printf '{"device":"%s","channel":"STABLE","buildidentifier":"%s","dateupdated":"%s","url":"file://%s/fake.zip","md5":"%s"}' "$@"; }
printf '[%s,\n %s,\n %s]\n' "$(entry other-device $((NEWER + 5))_X 2026-11-01 $D "$MD5")" \
  "$(entry "$DEVICE" "${NEWER}_$MONTHLY" "" $D "$MD5")" "$(entry "$DEVICE" "${BUILD}_$BUILD_ID" 2026-10-22 $D "$MD5")" > "$W/listing.json"
sed "s/$MD5/00000000000000000000000000000000/g" "$W/listing.json" > "$W/listing-badmd5.json"
printf '[%s]\n' "$(entry "$DEVICE" "${NEWER}_$NEXT" 2027-03-01 $D "$MD5")" > "$W/listing-quarterly.json"
# A transfer that writes part of the file and stalls, standing in for a slow network (only on PATH for that case).
mkdir -p "$W/slow"
printf '%s\n' '#!/system/bin/sh' 'echo $$ > "$OBU_CURL_PID"' \
  'case " $* " in *" -fsSIL "*) printf "HTTP/1.1 200 OK\r\ncontent-length: 2000000\r\n\r\n"; exit 0 ;; esac' \
  'while [ $# -gt 1 ]; do [ "$1" = -o ] && out=$2; shift; done' 'head -c 4096 /dev/zero >> "$out"' 'exec sleep 120' > "$W/slow/curl"
if ! a "rm -rf $D && mkdir -p $D/slow" || ! "$ADB" -s "$S" push "$HERE/openbook-updater" "$W/fake.zip" \
    "$W/listing.json" "$W/listing-badmd5.json" "$W/listing-quarterly.json" "$D/" > /dev/null 2>&1 \
    || ! "$ADB" -s "$S" push "$W/slow/curl" "$D/slow/curl" > /dev/null 2>&1 || ! a "chmod 755 $D/slow/curl"; then
  echo "could not stage the test files on the device"; exit 2
fi

pass=0; failed=0
expect() {  # NAME EXPECTED_EXIT REMOTE_COMMAND
  out=$(a "cd $D || exit 97; $3; echo \"exit=\$?\"" 2>&1); got=$(printf '%s' "$out" | sed -n 's/^exit=//p' | tail -1)
  if [ "$got" = "$2" ]; then pass=$((pass + 1)); echo "PASS  $1 (exit $got)"
  else failed=$((failed + 1)); echo "FAIL  $1: exit $got, expected $2"; printf '%s\n' "$out" | sed 's/^/      /'; fi
}
# Space reserve: the default 20 GiB on the laptop; 1 GiB on a small emulator /data (the 2^32 case sets its own).
case $DEVICE in ruby) UB="sh ./openbook-updater" ;; *) UB="OPENBOOK_UPDATER_RESERVE_KB=1048576 sh ./openbook-updater" ;; esac
[ -n "$TEST_ID" ] && UB="OPENBOOK_UPDATER_TEST_BUILD_ID=$BUILD_ID $UB"
U=$UB
if [ "$DEVICE" = ruby ]; then
  # Up to date (0), or Google already lists a newer build (10): either is a working live check.
  expect "live Google listing: the check completes" '0' "$U --dir s1 check > /dev/null; r=\$?; [ \$r = 10 ] && r=0; (exit \$r)"
else
  expect "live Google listing: no release listed for $DEVICE" '7' "$U --dir s1 check > /dev/null"
fi
expect "newer monthly release with an empty date field: download + verify" '0' "$U --dir s2 --listing $D/listing.json download > /dev/null && [ -f s2/$NEWER/recovery.zip ] && grep -q '^kind=monthly$' s2/state"
expect "second download: re-hashed, reported verified" '0' "$U --dir s2 --listing $D/listing.json download | grep -q 'already downloaded and verified'"
expect "MD5 mismatch refused, partial removed" '4' "$U --dir s3 --listing $D/listing-badmd5.json download > /dev/null; r=\$?; [ ! -e s3/$NEWER/recovery.zip.part ] && (exit \$r)"
expect "next quarter's release held, nothing downloaded" '8' "$U --dir s6 --listing $D/listing-quarterly.json download > /dev/null; r=\$?; grep -q '^kind=quarterly$' s6/state && [ ! -e s6/$NEWER ] && (exit \$r)"
expect "stop request ends the transfer and keeps the partial" '130' "PATH=$D/slow:\$PATH OBU_CURL_PID=$D/curl.pid $UB --dir s7 --listing $D/listing.json download > s7.out 2>&1 & p=\$!; i=0; while [ ! -s s7/$NEWER/recovery.zip.part ] && [ \$i -lt 60 ]; do sleep 1; i=\$((i + 1)); done; kill -TERM \$p; wait \$p; r=\$?; sleep 1; if ! kill -0 \"\$(cat $D/curl.pid)\" 2> /dev/null && [ \"\$(stat -c %s s7/$NEWER/recovery.zip.part 2>&1)\" = 4096 ] && grep -q '^result=stopped$' s7/state; then (exit \$r); else cat s7.out s7/state; false; fi"
expect "reserve above 2^32 KiB refused (no 32-bit wrap)" '5' "${TEST_ID:+OPENBOOK_UPDATER_TEST_BUILD_ID=$BUILD_ID }OPENBOOK_UPDATER_RESERVE_KB=4294968296 sh ./openbook-updater --dir s4 --listing $D/listing.json download > /dev/null"
expect "concurrent run refused" '6' "mkdir -p s5; (sh -c 'flock -n 9 && sleep 4' 9>>s5/lock &); sleep 1; $U --dir s5 check"
expect "status reports the verified download" '0' "$U --dir s2 status | grep -q '^verified=${NEWER}_$MONTHLY$'"
echo "on $DEVICE: $pass passed, $failed failed"
[ $failed = 0 ]
