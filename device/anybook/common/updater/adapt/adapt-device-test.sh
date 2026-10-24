#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Phase 3 on the laptop itself (ANAL-229): the updater engine downloads Google's real release, then
# openbook-adapt reconstructs and adapts it with the laptop's own tools, reading OpenBook's files from the
# running system. Everything runs as adb's shell user in one temporary directory that is removed at the end;
# no partition, setting or app is touched.
#
# usage: adapt-device-test.sh SERIAL ADAPT_BINARY LISTING CASES OUT
#   LISTING  a local listing file whose ruby entry names Google's real release (Google's URL and MD5)
#   CASES    lines "name layer_dir embed(0|1) expected_system_sha256 expected_vbmeta_sha256" (expected "-" to only record)
#   OUT      new host directory for the results (JSON records and the log; no Google image)
set -euo pipefail
SERIAL=$1 BIN=$2 LISTING=$3 CASES=$4 OUT=$5
HERE=$(cd "$(dirname "$0")" && pwd)
ENGINE=$HERE/../openbook-updater
AVBKEY=${AVBKEY:-$HOME/anybook/aosp/src/external/avb/test/data/testkey_rsa4096.pem}
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
GOOGLE_KEY=8f267440b8c98961ba1ae9f1ca8eb2ae1669093a637027803cf048492b5d35e0
T=/data/local/tmp/openbook-adapt-test
mkdir -m 700 "$OUT"
log() { echo "$(date -u +%FT%TZ) $*" | tee -a "$OUT/log.txt"; }
# adb shell reads stdin; keep it from consuming the case list.
sh_() { "$ADB" -s "$SERIAL" shell "$@" < /dev/null; }
cleanup() { sh_ "rm -rf $T" || true; log "removed $T on the laptop"; }
trap cleanup EXIT

log "laptop: $(sh_ getprop ro.build.fingerprint) slot $(sh_ getprop ro.boot.slot_suffix)"
free_kb=$(sh_ "df -k /data | tail -1" | awk '{print $4}')
log "laptop /data free: $((free_kb / 1048576)) GiB (needs about 30 GiB plus the engine's 20 GiB reserve)"
[ "$free_kb" -gt $((60 * 1048576)) ] || { log "not enough space on the laptop"; exit 1; }
sh_ "rm -rf $T && mkdir -p $T/updater"
"$ADB" -s "$SERIAL" push -q "$ENGINE" "$T/openbook-updater"
"$ADB" -s "$SERIAL" push -q "$BIN" "$T/openbook-adapt"
"$ADB" -s "$SERIAL" push -q "$LISTING" "$T/listing.json"
"$ADB" -s "$SERIAL" push -q "$AVBKEY" "$T/avb-test-key.pem"
sh_ "chmod 755 $T/openbook-adapt"
while read -r name layer _; do
    [ -n "$name" ] || continue
    sh_ "mkdir -p $T/layer-$name"
    "$ADB" -s "$SERIAL" push -q "$layer/layer.json" "$T/layer-$name/layer.json"
done < "$CASES"

env_="OPENBOOK_UPDATER_DIR=$T/updater OPENBOOK_UPDATER_LISTING=$T/listing.json"
log "engine check"
sh_ "$env_ sh $T/openbook-updater check" | tee -a "$OUT/log.txt" || true
log "engine download (Google's real release, full size)"
s=$(date +%s)
sh_ "$env_ sh $T/openbook-updater download" | tee -a "$OUT/log.txt"
log "download finished in $(( $(date +%s) - s )) s"
zip=$(sh_ "ls $T/updater/*/recovery.zip" | tr -d '\r')
sh_ "ls -l $zip" | tee -a "$OUT/log.txt"

log "reconstruct"
s=$(date +%s)
sh_ "$T/openbook-adapt reconstruct --release $zip --out $T/new --google-key $GOOGLE_KEY" 2>&1 | tee -a "$OUT/log.txt"
log "reconstruct finished in $(( $(date +%s) - s )) s"
"$ADB" -s "$SERIAL" pull -q "$T/new/reconstruct.json" "$OUT/reconstruct.json"
# The release zip is no longer needed: free its space before the adaptations.
sh_ "rm -rf $T/updater/[0-9]*"

pass=1 ran=0
while read -r name _ embed want_sys want_vb; do
    [ -n "$name" ] || continue
    ran=$((ran + 1))
    log "adapt $name (embed layer: $embed)"
    s=$(date +%s)
    rc=0
    sh_ "$T/openbook-adapt adapt --layer $T/layer-$name --new $T/new --ours-root / --key $T/avb-test-key.pem \
        --mkfs /system/bin/mkfs.erofs --fsck /system/bin/fsck.erofs --work $T/work-$name --out $T/out-$name \
        --embed-layer=$([ "$embed" = 1 ] && echo true || echo false)" > "$OUT/adapt-$name.txt" 2>&1 || rc=$?
    log "adapt $name: exit $rc in $(( $(date +%s) - s )) s"
    "$ADB" -s "$SERIAL" pull -q "$T/out-$name/adapt.json" "$OUT/adapt-$name.json" || true
    sums=$(sh_ "cd $T/out-$name 2>/dev/null && sha256sum system.img system_ext.img product.img vbmeta.img" | tr -d '\r' || true)
    echo "$sums" > "$OUT/sha256-$name.txt"
    got_sys=$(echo "$sums" | awk '$2 == "system.img" {print $1}')
    got_vb=$(echo "$sums" | awk '$2 == "vbmeta.img" {print $1}')
    for pair in "system $want_sys $got_sys" "vbmeta $want_vb $got_vb"; do
        set -- $pair
        if [ "$2" = - ]; then log "  $1 ${3:-none} (recorded)"
        elif [ "$2" = "${3:-}" ]; then log "  $1 $3 IDENTICAL to the expected"
        else log "  $1 ${3:-none} DIFFERS from the expected $2"; pass=0; fi
    done
    [ "$rc" = 0 ] || pass=0
    sh_ "rm -rf $T/work-$name $T/out-$name"
done < "$CASES"
want_cases=$(grep -c . "$CASES")
[ "$ran" = "$want_cases" ] || { log "only $ran of $want_cases cases ran"; pass=0; }
log "result: $([ $pass = 1 ] && echo PASS || echo FAIL) ($ran cases)"
[ $pass = 1 ]
