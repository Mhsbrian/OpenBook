#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Launch apps whose official builds use Google Play services (FCM push, Play location) on an Android device, with or
# without microG, and record what happens (ANAL-210, docs/COMPAT-MATRIX.md "Apps that use Play services"):
# installed fresh (uninstalled before and after), alive 15 s after launch, crashes and ANRs in that time, whether the app saw Play services (its own
# GoogleApiAvailability log lines), whether microG received a push registration from it, and a screenshot.
# The APKs are the apps' own release files from their GitHub releases, pinned by sha256 in scripts/microg/gms-apps.tsv;
# they are downloaded to <data dir>/dl/microg-compat/ and never committed.
#
# usage: gms-apps.sh LABEL OUTDIR        ADB (env): the adb command for the device, e.g. "adb -s 127.0.0.1:6520"
# Output: OUTDIR/LABEL.tsv (one row per app), OUTDIR/LABEL-<package>.png, OUTDIR/LABEL-<package>.log (its logcat)
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}; D=$A/dl/microg-compat
LABEL=${1:?usage: gms-apps.sh LABEL OUTDIR}; OUT=${2:?outdir}; mkdir -p "$OUT" "$D"
read -r -a ADBC <<< "${ADB:?set ADB to the adb command for the device}"
adb_(){ "${ADBC[@]}" "$@" < /dev/null; }
PUSH=${PUSH:-}   # optional: a command "PUSH HOSTFILE DEVICEPATH" when adb cannot read host paths (a containerised adb)
printf 'package\tname\tinstalled\talive_15s\tcrashes\tanrs\tplay_services_seen\tpush_registered\tnotes\n' > "$OUT/$LABEL.tsv"
grep -v '^#' "$R/scripts/microg/gms-apps.tsv" | while IFS=$'\t' read -r pkg name url sha; do
  f=$D/$(basename "$url")
  [ -f "$f" ] || { curl -fsSL -o "$f.part" "$url" && mv "$f.part" "$f"; }
  echo "$sha  $f" | sha256sum -c --quiet - || { echo "$f: sha256 mismatch" >&2; exit 1; }
  if [ -n "$PUSH" ]; then $PUSH "$f" /data/local/tmp/app.apk; else adb_ push "$f" /data/local/tmp/app.apk >/dev/null; fi
  adb_ shell pm uninstall "$pkg" >/dev/null 2>&1 || true   # a first start every time: no cached token or state
  inst=$(adb_ shell pm install -g /data/local/tmp/app.apk 2>&1 | tr -d '\r' | tail -1)
  adb_ shell rm -f /data/local/tmp/app.apk
  if [ "$inst" != Success ]; then
    printf '%s\t%s\tno\t-\t-\t-\t-\t-\t%s\n' "$pkg" "$name" "$inst" >> "$OUT/$LABEL.tsv"; continue
  fi
  adb_ shell logcat -c
  adb_ shell monkey -p "$pkg" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true
  sleep 15
  pid=$(adb_ shell pidof "$pkg" | tr -d '\r' || true)
  adb_ exec-out screencap -p > "$OUT/$LABEL-$pkg.png" || true
  adb_ shell logcat -d -b main,system,crash > "$OUT/$LABEL-$pkg.log" || true
  # Device credentials never go into evidence: MCS login tokens, check-in security tokens and registration tokens.
  "$R/scripts/microg/redact.sh" "$OUT/$LABEL-$pkg.log"
  crashes=$(grep -A2 'FATAL EXCEPTION' "$OUT/$LABEL-$pkg.log" | grep -c "Process: $pkg" || true)
  anrs=$(grep -c "ANR in $pkg" "$OUT/$LABEL-$pkg.log" || true)
  # What the app's own Play services client said: missing, or present but older than it was built for.
  old=$(grep -Eo 'Requires [0-9]+ but found [0-9]+' "$OUT/$LABEL-$pkg.log" | head -1 || true)
  missing=$(grep -Eic 'SERVICE_MISSING|SERVICE_INVALID|Google Play services (is )?(missing|not available|invalid)' "$OUT/$LABEL-$pkg.log" || true)
  reg=$(grep -E 'GmsGcmRegister' "$OUT/$LABEL-$pkg.log" | grep -c "package=$pkg" || true)
  tok=$(grep -c 'onNewToken\|<fcm-token>\|GmsHttpFormClient: token=' "$OUT/$LABEL-$pkg.log" || true)
  if [ "$missing" -gt 0 ]; then seen="missing"; elif [ -n "$old" ]; then seen="older (${old#Requires })"; else seen="no complaint"; fi
  printf '%s\t%s\tyes\t%s\t%s\t%s\t%s\t%s\t\n' "$pkg" "$name" "$([ -n "$pid" ] && echo yes || echo no)" "$crashes" "$anrs" \
    "$seen" "$([ "$reg" -gt 0 ] && echo "requested$([ "$tok" -gt 0 ] && echo ', token issued')" || echo no)" >> "$OUT/$LABEL.tsv"
  adb_ shell pm uninstall "$pkg" >/dev/null 2>&1 || true
done
column -t -s $'\t' "$OUT/$LABEL.tsv"
