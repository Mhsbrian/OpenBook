#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run openbook-updater's scenarios on the laptop itself: its mksh (32-bit arithmetic, close-on-exec
# descriptors), toybox, one-true-awk and curl. The host suite (openbook-updater-test.py) cannot.
#
# Writes only to a temporary directory under /data/local/tmp on the laptop and removes it at the end.
# Installs nothing and changes no system state. The live check is a read-only HTTPS request to
# Google's public listing.
#
# usage: openbook-updater-device-test.sh [LAPTOP_IP]   (default 192.168.50.11; adb must be paired)
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
IP=${1:-192.168.50.11}
D=/data/local/tmp/openbook-updater-test

S=$("$ADB" devices | awk -v ip="$IP" 'index($1, ip ":") == 1 && $2 == "device" {print $1; exit}')
if [ -z "$S" ]; then
  ep=$("$ADB" mdns services 2>/dev/null | awk -v ip="$IP" '/_adb-tls-connect/ && index($NF, ip ":") == 1 {print $NF; exit}')
  [ -n "$ep" ] && "$ADB" connect "$ep" > /dev/null 2>&1
  S=$("$ADB" devices | awk -v ip="$IP" 'index($1, ip ":") == 1 && $2 == "device" {print $1; exit}')
fi
[ -n "$S" ] || { echo "the laptop at $IP is not reachable over adb"; exit 2; }
a() { timeout 300 "$ADB" -s "$S" shell "$@"; }

W=$(mktemp -d); trap 'rm -rf "$W"; a "rm -rf $D" > /dev/null 2>&1' EXIT
head -c 2000000 /dev/urandom > "$W/fake.zip"
MD5=$(md5sum "$W/fake.zip" | cut -c1-32)
entry() { printf '{"device":"%s","channel":"STABLE","buildidentifier":"%s","dateupdated":"%s","url":"file://%s/fake.zip","md5":"%s"}' "$@"; }
printf '[%s,\n %s,\n %s]\n' "$(entry lapis 17999999_X 2026-11-01 $D "$MD5")" \
  "$(entry ruby 16999999_CL3B.TEST "" $D "$MD5")" "$(entry ruby 16658739_CL3B.260622.276.R4 2026-10-22 $D "$MD5")" > "$W/listing.json"
sed "s/$MD5/00000000000000000000000000000000/g" "$W/listing.json" > "$W/listing-badmd5.json"
if ! a "rm -rf $D && mkdir -p $D" || ! "$ADB" -s "$S" push "$HERE/openbook-updater" "$W/fake.zip" \
    "$W/listing.json" "$W/listing-badmd5.json" "$D/" > /dev/null 2>&1; then
  echo "could not stage the test files on the laptop"; exit 2
fi

pass=0; failed=0
expect() {  # NAME EXPECTED_EXIT REMOTE_COMMAND
  out=$(a "cd $D && $3; echo \"exit=\$?\"" 2>&1); got=$(printf '%s' "$out" | sed -n 's/^exit=//p' | tail -1)
  if [ "$got" = "$2" ]; then pass=$((pass + 1)); echo "PASS  $1 (exit $got)"
  else failed=$((failed + 1)); echo "FAIL  $1: exit $got, expected $2"; printf '%s\n' "$out" | sed 's/^/      /'; fi
}
U="sh ./openbook-updater"
expect "live Google listing: this laptop's build is current or older" '0' "$U --dir s1 check > /dev/null"
expect "newer release with an empty date field: download + verify" '0' "$U --dir s2 --listing $D/listing.json download > /dev/null && [ -f s2/16999999/recovery.zip ]"
expect "second download: re-hashed, reported verified" '0' "$U --dir s2 --listing $D/listing.json download | grep -q 'already downloaded and verified'"
expect "MD5 mismatch refused, partial removed" '4' "$U --dir s3 --listing $D/listing-badmd5.json download > /dev/null; r=\$?; [ ! -e s3/16999999/recovery.zip.part ] && (exit \$r)"
expect "reserve above 2^32 KiB refused (no 32-bit wrap)" '5' "OPENBOOK_UPDATER_RESERVE_KB=4294968296 $U --dir s4 --listing $D/listing.json download > /dev/null"
expect "concurrent run refused" '6' "mkdir -p s5; (sh -c 'flock -n 9 && sleep 4' 9>>s5/lock &); sleep 1; $U --dir s5 check"
expect "status reports the verified download" '0' "$U --dir s2 status | grep -q '^verified=16999999_CL3B.TEST$'"
echo "on-laptop: $pass passed, $failed failed"
[ $failed = 0 ]
