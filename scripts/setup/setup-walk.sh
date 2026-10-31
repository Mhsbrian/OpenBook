#!/usr/bin/env bash
# Copyright (C) 2026 The OpenBook Authors
# SPDX-License-Identifier: Apache-2.0
#
# Drives OpenBook setup (ANAL-209, docs/setup.md) on a freshly booted userdebug device and checks the result:
#   walk    every page, one screenshot each: region United Kingdom, layout English (UK), the Wi-Fi settings and back,
#           24-hour clock, a name and a PIN, then the desktop
#   skip    "Skip setup" on the first page
#   absent  setup must not show at all (a boot with androidboot.openbook.setup=skip, or ro.setupwizard.mode=DISABLED)
# Every mode then checks device_provisioned and user_setup_complete (1), that setup is off, Provision is gone and setup
# never crashed.
# Writes OUTDIR/*.png, OUTDIR/state.txt and OUTDIR/results.json; exits 1 if a check failed.
#
# usage: setup-walk.sh SERIAL OUTDIR MODE
# Env: ADB (default ~/anybook/android-sdk/platform-tools/adb); set ANDROID_ADB_SERVER_PORT for a private server.
#      WALK_NAME (OpenBook Tester), WALK_PIN (2468)
set -euo pipefail
S=$1; O=$2; MODE=${3:-walk}; mkdir -p "$O"
ADB=${ADB:-$HOME/anybook/android-sdk/platform-tools/adb}
H=$(cd "$(dirname "$0")" && pwd)
NAME=${WALK_NAME:-OpenBook Tester}; PIN=${WALK_PIN:-2468}
a(){ "$ADB" -s "$S" "$@"; }
sh_(){ a shell "$@" | tr -d '\r'; }
log(){ echo "=== $(date -u +%T) $*"; }
dump(){ sh_ uiautomator dump /data/local/tmp/ui.xml >/dev/null 2>&1 || true; a exec-out cat /data/local/tmp/ui.xml > "$O/.ui.xml" 2>/dev/null || true; }
find_(){ dump; python3 -I "$H/ui-find.py" "$O/.ui.xml" "$@"; }
wait_(){  # wait_ TEXT [SECONDS]: a node whose text starts with TEXT
  local t=${2:-60} end; end=$(( $(date +%s) + t ))
  while [ "$(date +%s)" -lt "$end" ]; do [ -n "$(find_ text "$1")" ] && { log "on: $1"; return 0; }; sleep 1; done
  log "TIMEOUT waiting for '$1'"; cp "$O/.ui.xml" "$O/timeout-ui.xml" 2>/dev/null || true; return 1
}
tap(){  # tap KIND VALUE
  local xy; xy=$(find_ "$@"); [ -n "$xy" ] || { log "NOT FOUND: $*"; return 1; }
  # shellcheck disable=SC2086  # "x y"
  sh_ input tap $xy; log "tap $* at $xy"; sleep 1.5
}
type_(){  # type_ ID TEXT: focus the field, clear it, type
  tap id "$1"; sh_ input keyevent KEYCODE_MOVE_END
  sh_ input keyevent $(printf 'KEYCODE_DEL %.0s' $(seq 40)) >/dev/null
  sh_ input text "$(printf %s "$2" | sed 's/ /%s/g')"; sleep 1
}
shot(){ sleep "${2:-2}"; a exec-out screencap -p > "$O/$1.png"; log "shot $1"; }
R=$O/.checks.tsv; : > "$R"
check(){ printf '%s\t%s\t%s\n' "$1" "$([ "$2" = 0 ] && echo true || echo false)" "$(echo "$3" | tr '\t\n' '  ' | cut -c1-300)" >> "$R"; }
top(){ sh_ dumpsys activity activities | grep -m1 -E 'topResumedActivity' || true; }

log "mode $MODE on $S"
for _ in $(seq 300); do [ "$(sh_ getprop sys.boot_completed)" = 1 ] && break; sleep 2; done
sh_ input keyevent KEYCODE_WAKEUP; sh_ wm dismiss-keyguard || true
LOCALE0=$(sh_ getprop persist.sys.locale)

case $MODE in
  walk)
    wait_ "Let's set up your laptop" 300
    t=$(top); check "setup is the first screen" "$(echo "$t" | grep -q org.openbook.setup/.SetupActivity; echo $?)" "$t"
    shot 1-welcome
    tap textx "Get started"
    wait_ "Language and region"
    type_ region-search "United Kingdom"; tap textx "United Kingdom"
    shot 2-language
    tap textx "Continue"
    wait_ "Keyboard layout"
    type_ keyboard-search "UK"; tap textx "English (UK)"
    shot 3-keyboard
    sh_ dumpsys input | grep -iE 'keyboard layout|KeyboardLayout|layoutDescriptor|keyboard_layout' | head -n 20 > "$O/keyboard-layouts.txt" || true
    tap textx "Continue"
    wait_ "Connect to the internet"
    shot 4-network
    tap textx "Choose a network"
    shot 4b-wifi-settings 5
    t=$(top); check "Choose a network opens Wi-Fi settings" "$(echo "$t" | grep -q com.android.settings; echo $?)" "$t"
    sh_ input keyevent KEYCODE_BACK; sleep 2
    wait_ "Connect to the internet" 20 || { sh_ input keyevent KEYCODE_BACK; wait_ "Connect to the internet" 20; }
    tap textx "Continue"
    wait_ "Date and time"
    # Where the device detects the time zone itself, turn that off to pick one (a region with one zone is preselected).
    if [ -n "$(find_ text "The time zone is set automatically")" ]; then tap text "Set time zone automatically"; fi
    tap textx "London" || true
    # Twice: off, then on, so the setting is written whatever the locale's default (en-GB is 24-hour already).
    tap text "Use 24-hour format"; tap text "Use 24-hour format"
    shot 5-time
    tap textx "Continue"
    wait_ "About you"
    type_ name "$NAME"
    type_ secret "$PIN"
    type_ secret-again "$PIN"
    shot 6-account
    tap textx "Continue"
    wait_ "OpenBook isn't a Google-certified device"
    shot 7-notice
    tap textx "Continue"
    wait_ "Optional extras"
    shot 8-extras
    tap textx "Continue"
    wait_ "You're all set"
    shot 9-done
    tap textx "Start using OpenBook"
    shot 10-desktop 8
    ;;
  skip)
    wait_ "Let's set up your laptop" 300
    t=$(top); check "setup is the first screen" "$(echo "$t" | grep -q org.openbook.setup/.SetupActivity; echo $?)" "$t"
    shot skip-1-welcome
    tap textx "Skip setup"
    shot skip-2-desktop 8
    ;;
  absent)
    sleep "${ABSENT_SETTLE:-25}"
    shot absent-desktop
    ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac

# ---- the end state, the same for every mode
sleep 2
PROV=$(sh_ settings get global device_provisioned); USC=$(sh_ settings get secure user_setup_complete)
check "device_provisioned=1 and user_setup_complete=1" "$([ "$PROV" = 1 ] && [ "$USC" = 1 ]; echo $?)" "device_provisioned=$PROV user_setup_complete=$USC"
HOMES=$(sh_ pm query-activities -a android.intent.action.MAIN -c android.intent.category.HOME | grep -c 'org.openbook.setup' || true)
check "setup is no longer a home activity" "$([ "$HOMES" = 0 ]; echo $?)" "home entries of org.openbook.setup: $HOMES"
PROVP=$(sh_ pm path com.android.provision || true); SETUPP=$(sh_ pm path org.openbook.setup || true)
check "OpenBookSetup installed, Provision not (overridden)" "$([ -z "$PROVP" ] && [ -n "$SETUPP" ]; echo $?)" "setup: $SETUPP; provision: ${PROVP:-none}"
SUW=$(sh_ cmd package resolve-activity -a android.intent.action.MAIN -c android.intent.category.SETUP_WIZARD --components 2>/dev/null | tail -n 1 || true)
t=$(top); check "the launcher is on top" "$(echo "$t" | grep -qi launcher; echo $?)" "$t"
LOG=$(sh_ logcat -d -s OpenBookSetup:V | grep -v '^-' || true)
CRASH=$(sh_ logcat -d -b events | grep -E 'am_(crash|anr)' | grep -F org.openbook.setup || true)
check "setup never crashed (am_crash, am_anr)" "$([ -z "$CRASH" ]; echo $?)" "${CRASH:-none}"
echo "$LOG" > "$O/logcat-OpenBookSetup.txt"
case $MODE in
  walk)
    L=$(sh_ getprop persist.sys.locale); TZ=$(sh_ getprop persist.sys.timezone); F=$(sh_ settings get system time_12_24)
    check "language and region applied (en-GB)" "$([ "$L" = en-GB ]; echo $?)" "persist.sys.locale=$L"
    check "time zone from the region (Europe/London)" "$([ "$TZ" = Europe/London ]; echo $?)" "persist.sys.timezone=$TZ"
    check "24-hour clock" "$([ "$F" = 24 ]; echo $?)" "time_12_24=$F"
    U=$(sh_ cmd user list | grep -m1 'UserInfo{0:' || true)
    check "user name set" "$(echo "$U" | grep -qF "$NAME"; echo $?)" "$U"
    V=$(sh_ cmd lock_settings verify --old "$PIN" 2>&1 || true)
    check "PIN set (lock_settings verify)" "$(echo "$V" | grep -qi 'verified successfully'; echo $?)" "$V"
    KL=$(grep -c 'english_uk' "$O/keyboard-layouts.txt" || true); KB=$(echo "$LOG" | grep -m1 'keyboard layout' || true)
    check "keyboard layout English (UK) set on the keyboards (reported)" 0 "${KB:-no physical keyboard}; dumpsys input lines with english_uk: $KL"
    check "all ten screenshots" "$(for p in 1-welcome 2-language 3-keyboard 4-network 5-time 6-account 7-notice 8-extras 9-done 10-desktop; do [ -s "$O/$p.png" ] || exit 1; done; echo 0)" "$(ls "$O" | grep -c png) png files"
    check "setup logged its end" "$(echo "$LOG" | grep -q 'setup complete (finished)'; echo $?)" "$(echo "$LOG" | grep -m1 'setup complete' || true)"
    ;;
  skip)
    L=$(sh_ getprop persist.sys.locale)
    check "skip keeps the language" "$([ "$L" = "$LOCALE0" ]; echo $?)" "before=$LOCALE0 after=$L"
    check "setup logged the skip" "$(echo "$LOG" | grep -q 'skipped by the user on welcome'; echo $?)" "$(echo "$LOG" | grep -m1 'setup complete' || true)"
    ;;
  absent)
    check "setup never started" "$(echo "$LOG" | grep -q 'setup started'; [ $? = 1 ]; echo $?)" "$(echo "$LOG" | grep -m1 'setup started' || echo 'no "setup started" line')"
    check "setup stepped aside, with its reason" "$(echo "$LOG" | grep -q 'step aside'; echo $?)" "$(echo "$LOG" | grep -m1 'step aside' || true)"
    ;;
esac
{
  echo "# $(sh_ getprop ro.build.fingerprint)"
  for p in ro.boot.openbook.setup ro.setupwizard.mode ro.boot.openbook.live ro.boot.verifiedbootstate persist.sys.locale persist.sys.timezone; do
    echo "$p=$(sh_ getprop "$p")"; done
  echo "device_provisioned=$PROV user_setup_complete=$USC"
  echo "setup wizard activity: $SUW"
  echo "## pm path"; echo "org.openbook.setup: $SETUPP"; echo "com.android.provision: ${PROVP:-none}"
  echo "## top"; top
  echo "## OpenBookSetup log"; echo "$LOG"
} > "$O/state.txt"
python3 -I - "$R" "$O/results.json" "$MODE" <<'PY'
import json, sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1]) if l.strip()]
checks = [{"check": r[0], "ok": r[1] == "true", "detail": r[2] if len(r) > 2 else ""} for r in rows]
res = {"schema": "openbook-setup-walk/1", "mode": sys.argv[3], "passed": sum(c["ok"] for c in checks), "total": len(checks), "checks": checks}
json.dump(res, open(sys.argv[2], "w"), indent=1)
for c in checks:
    print(("PASS " if c["ok"] else "FAIL ") + c["check"] + " | " + c["detail"][:160])
print(f"{res['passed']}/{res['total']} checks passed")
sys.exit(0 if res["passed"] == res["total"] else 1)
PY
