#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Synthetic VM only. Replaces the existing read-only serial probe in a private
# test copy; never added to a candidate or physical device image.
echo BRIDGE_VM_BEGIN
id
getenforce
for n in $(seq 1 180); do
    [ "$(getprop sys.boot_completed)" = 1 ] && break
    if [ "$((n % 12))" = 0 ]; then
        echo BRIDGE_VM_WAIT=$n
        logcat -d -v threadtime -t 80 -s AndroidRuntime NativeBridge berberis
    fi
    sleep 5
done
echo BRIDGE_VM_BOOT_COMPLETED=$(getprop sys.boot_completed)
echo BRIDGE_VM_SELECTED=$(getprop ro.dalvik.vm.native.bridge)
echo BRIDGE_VM_SECONDARY_LAYOUT=$(getprop ro.berberis.is_2nd_native_bridge)
echo BRIDGE_VM_ABILIST=$(getprop ro.product.cpu.abilist)
cat /proc/mounts | grep -E 'berberis|/system/lib64/arm64'
logcat -b all -d -v threadtime -s NativeBridge berberis houdini AndroidRuntime
[ "$(getprop sys.boot_completed)" = 1 ] || exit 1
mkdir -p /data/local/tmp/bridge-vm
cd /data/local/tmp/bridge-vm || exit 2
export TMPDIR="$PWD"
# Isolate Binder command descriptors from the serial console SELinux label.
run() {
    echo BRIDGE_VM_COMMAND "$@"
    timeout 60 "$@" </dev/null >command.out 2>&1
    status=$?
    echo BRIDGE_VM_STATUS=$status
    cat command.out
    return "$status"
}
run am get-current-user
user=$(am get-current-user </dev/null 2>/dev/null)
case "$user" in ''|*[!0-9]*) echo BRIDGE_VM_NO_USER; exit 3;; esac
# VM-only hypothesis test: isolate error-dialog rendering from the known
# system_server execmem denial/crash with SwiftShader. Preserve crash logs and
# fail qualification on crashes; this is never a production configuration.
run settings put global hide_error_dialogs 1
run settings put global device_provisioned 1
run settings --user "$user" put secure user_setup_complete 1
run settings --user "$user" put system screen_off_timeout 1800000
run settings put global window_animation_scale 0
run settings put global transition_animation_scale 0
run settings put global animator_duration_scale 0
run wm size 800x600
run wm density 160
run settings put global disable_window_blurs 1
run pm disable-user --user "$user" com.google.android.desktop.setupwizard
run svc power stayon true
run input keyevent KEYCODE_WAKEUP
run wm dismiss-keyguard
run logcat -b main -G 8M
echo BRIDGE_VM_EARLY_SEARCH
run am start --user "$user" -W -a com.android.settings.action.SETTINGS_SEARCH
sleep 10
logcat -d -v threadtime -s AndroidRuntime NativeBridge berberis houdini
# APK_SETUP: the host embeds only the repository's open-source test APKs here.
for abi in arm64 x86_64; do
    run pm install --user "$user" -r "$PWD/$abi.apk"
    run am start --user "$user" -W -n "dev.anybook.probe.$abi/dev.anybook.probe.MainActivity"
    sleep 50
    logcat -d -v threadtime -s AnyBookProbe:V AndroidRuntime NativeBridge berberis houdini
    run run-as "dev.anybook.probe.$abi" --user "$user" cat files/probe-results.txt
    run am force-stop --user "$user" "dev.anybook.probe.$abi"
done
run dumpsys package com.google.android.settings.intelligence
run pm path --user "$user" com.google.android.settings.intelligence
echo BRIDGE_VM_SYSTEM_SERVER_BEFORE=$(pidof system_server)
for attempt in $(seq 1 20); do
    echo BRIDGE_VM_SEARCH_ATTEMPT=$attempt
    if ! run am start --user "$user" -W -a com.android.settings.action.SETTINGS_SEARCH; then
        echo BRIDGE_VM_SEARCH_LAUNCH_FAILED
        break
    fi
    # Clear the previous query even when Android reuses the same activity.
    run input keycombination KEYCODE_CTRL_LEFT KEYCODE_A
    run input keyevent KEYCODE_DEL
    case "$((attempt % 3))" in
        1) query=display;; 2) query=bluetooth;; 0) query=keyboard;;
    esac
    run input text "$query"
    run input keyevent KEYCODE_DEL
    case "$query" in display) last=y;; bluetooth) last=h;; keyboard) last=d;; esac
    run input text "$last"
    sleep 5
    echo BRIDGE_VM_SEARCH_PID=$(pidof com.google.android.settings.intelligence)
    logcat -d -v threadtime -s AndroidRuntime NativeBridge berberis houdini Icing
    if [ "$attempt" = 1 ] || [ "$attempt" = 20 ]; then
        run uiautomator dump --compressed "$PWD/search-$attempt.xml"
        cat "search-$attempt.xml"
        run dumpsys activity activities
    fi
    run input keyevent KEYCODE_BACK
done
run am start --user "$user" -W -a android.settings.DISPLAY_SETTINGS
sleep 20
echo BRIDGE_VM_SETTINGS_PID=$(pidof com.android.settings)
echo BRIDGE_VM_SYSTEM_SERVER_AFTER=$(pidof system_server)
run cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p com.google.android.apps.accessibility.voiceaccess
run cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p com.google.android.apps.yourwidget
for package in com.google.android.apps.accessibility.voiceaccess com.google.android.apps.yourwidget; do
    run am start --user "$user" -W -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p "$package"
    sleep 20
    echo BRIDGE_VM_PACKAGE_PID=$package:$(pidof "$package")
done
logcat -b all -d -v threadtime
echo BRIDGE_VM_SOAK_BEGIN
sleep 300
run dumpsys activity exit-info com.google.android.settings.intelligence
run dumpsys dropbox --print system_app_anr
logcat -b all -d -v threadtime
echo BRIDGE_VM_DONE
