#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# OpenBook Graphics and the OpenBook NVK driver package in the G14 product, in QEMU/KVM + OVMF (ANAL-323, ANAL-327;
# docs/nvidia-graphics-modes.md §7, docs/nvk-openbook.md §6). One boot of a fresh copy of IMG through
# scripts/g14-qemu.sh, with an expect script made here:
#   pkg      the app is a privileged system_ext app, platform-signed, version 1.3, with REBOOT,
#            WRITE_SECURE_SETTINGS and POST_NOTIFICATIONS granted; org.openbook.nvk is a system package in
#            /vendor/app (vendor_app_file), the image's bytes (NVK_APK_SHA256), and nothing offers it here (no NVIDIA)
#   boot     the games rule's boot sync (with an app driver now) and its periodic job
#   screens  the main screen (the mode, switching off or not available, Apps on the NVIDIA GPU with its switch and
#            button), the "NVIDIA GPU for apps" switch tapped off and on again (updatable_driver_all_apps 3, then 0),
#            the apps screen (the switch, the games rule), the Settings > Display entry (on this VM copy marked
#            provisioned: Settings lists other apps' entries only then); the app's process domain
#   g14      the G14 in Hybrid with NVIDIA's driver bound, as init offers the driver package there
#            (ro.gfx.driver.0=org.openbook.nvk, set by root here; QEMU has no NVIDIA GPU): a code-less test game,
#            installed over the console, is opted in through Android's own list. Starting it shows GraphicsEnvironment
#            choosing the package and Android's GLES and Vulkan loaders loading its libraries (ANGLE, then NVK, which
#            finds no NVIDIA GPU here); with the switch off (all apps 3) it keeps the system driver. The apps screen
#            then lists the game with its choice
#   avc      every SELinux denial (kernel log and logcat), the app's own, and the test game's
# Env: NVK_APK_SHA256: the SHA-256 of the image's OpenBookNvk.apk (default: PRODUCT_OUT's, if present).
# Image files only; nothing is written to a real disk. Results: <data dir>/logs/installer/<RUN>/boot1/ (sections/,
# shot-*.png, result.json), and graphics-app.json beside it (scripts/graphics/graphics-app-report.py).
#
# usage: graphics-app-qemu.sh IMG RUN
# env:   OPENBOOK_APP_SDK  Android SDK with build-tools 37.0.0 and android-37.0 (default: the OpenBook app toolchain's)
#        JAVA_HOME         for keytool and apksigner (default: <data dir>/toolchain/jdk-17.0.21)
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
R=$(cd "$(dirname "$0")/../.." && pwd)
IMG=$(realpath "${1:?usage: graphics-app-qemu.sh IMG RUN}"); RUN=${2:?run name}
SDK=${OPENBOOK_APP_SDK:-$A/toolchain/openbook-update-sdk}
export JAVA_HOME=${JAVA_HOME:-$A/toolchain/jdk-17.0.21}; export PATH=$JAVA_HOME/bin:$PATH
BT=$SDK/build-tools/37.0.0; JAR=$SDK/platforms/android-37.0/android.jar
for f in "$BT/aapt2" "$BT/apksigner" "$BT/zipalign" "$JAR" "$JAVA_HOME/bin/keytool"; do
  [ -e "$f" ] || { echo "missing $f" >&2; exit 2; }
done
L=$A/logs/installer/$RUN; W=$A/installer/qemu/$RUN-gfxapp
rm -rf "$W"; mkdir -p "$W" "$L"
NVK_APK=$A/aosp/src/out/target/product/anybook_g14/vendor/app/OpenBookNvk/OpenBookNvk.apk
NVK_APK_SHA256=${NVK_APK_SHA256:-$( [ -f "$NVK_APK" ] && sha256sum "$NVK_APK" | cut -d' ' -f1 || true)}
echo "${NVK_APK_SHA256:-unknown}  vendor/app/OpenBookNvk/OpenBookNvk.apk (expected)" | tee "$L/nvk-apk.sha256"

# The test game: no code, one launcher activity (android.app.Activity), appCategory="game", so starting it starts
# its process and GraphicsEnvironment's choice and nothing else. A throwaway key, made for this run.
cat > "$W/AndroidManifest.xml" <<'XML'
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="org.openbook.test.game"
    android:versionCode="1" android:versionName="1">
  <uses-sdk android:minSdkVersion="26" android:targetSdkVersion="37" />
  <application android:label="Test Game" android:hasCode="false" android:appCategory="game">
    <activity android:name="android.app.Activity" android:exported="true">
      <intent-filter>
        <action android:name="android.intent.action.MAIN" />
        <category android:name="android.intent.category.LAUNCHER" />
      </intent-filter>
    </activity>
  </application>
</manifest>
XML
keytool -genkeypair -keystore "$W/test.jks" -storepass android -keypass android -alias t -keyalg EC -groupname secp256r1 \
  -validity 30 -dname CN=OpenBook-graphics-qemu-test > /dev/null 2>&1
"$BT/aapt2" link --manifest "$W/AndroidManifest.xml" -I "$JAR" -o "$W/unsigned.apk"
"$BT/zipalign" -f 4 "$W/unsigned.apk" "$W/aligned.apk"
"$BT/apksigner" sign --ks "$W/test.jks" --ks-pass pass:android --v1-signing-enabled false --out "$W/game.apk" "$W/aligned.apk"
sha256sum "$W/game.apk" | tee "$L/test-game.sha256"

python3 - "$W/game.apk" "$W/expect.json" <<'PY'
import base64, json, sys
apk, out = sys.argv[1], sys.argv[2]
b64 = base64.b64encode(open(apk, "rb").read()).decode()
P = "console:/ \\$ "
steps = [
    {"wait": "init: init second stage started", "timeout": 120},
    {"send": "\n"},
    {"wait": P, "timeout": 300},
    {"send": "su 0 dmesg -n 1\n"},
    {"wait": P, "timeout": 60},
    {"send": "i=0; while [ \"$(getprop sys.boot_completed)\" != 1 ] && [ $i -lt 900 ]; do sleep 3; i=$((i+3)); done; "
             "echo BOOTDONE=$(getprop sys.boot_completed); sleep 45\n"},
    {"wait": "BOOTDONE=1", "timeout": 960},
    {"wait": P, "timeout": 90},
]
def section(name, cmd, timeout=90):
    steps.append({"send": f"echo ==={name}-BEGIN===; {cmd}; echo ==={name}-END===\n"})
    steps.append({"wait": P, "timeout": timeout})
def shot(name):
    steps.append({"shot": name})
# uiautomator runs on app_process, which needs the boot classpath the console's shell does not have (as in
# scripts/installer/wizard-qemu.py). `ui` prints the screen's hierarchy.
steps.append({"send": "ui() { su 0 sh -c 'while read -r k n v; do [ \"$k\" = export ] && export \"$n=$v\"; done "
                      "< /data/system/environ/classpath; rm -f /data/local/tmp/obg-ui.xml; uiautomator dump "
                      "/data/local/tmp/obg-ui.xml' > /dev/null 2>&1; su 0 cat /data/local/tmp/obg-ui.xml; echo; }\n"})
steps.append({"wait": P, "timeout": 30})
UI = "ui"
# `tap ID` taps the middle of the view whose test tag (resource id) is ID, from a fresh hierarchy dump.
steps.append({"send": "tap() { b=$(ui | tr '>' '\\n' | grep \"resource-id=\\\"$1\\\"\" | "
                      "sed -n 's/.*bounds=\"\\[\\([0-9]*\\),\\([0-9]*\\)\\]\\[\\([0-9]*\\),\\([0-9]*\\)\\]\".*/\\1 \\2 \\3 \\4/p' | head -1); "
                      "set -- $b; [ -n \"$4\" ] && input tap $((($1+$3)/2)) $((($2+$4)/2)) && echo tapped $b; }\n"})
steps.append({"wait": P, "timeout": 30})
section("GFX-PKG",
        "pm path org.openbook.graphics; pm list packages org.openbook.nvk | grep -c . ; "
        "pm path org.openbook.nvk; dumpsys package org.openbook.nvk | grep -E 'versionCode=|versionName=|codePath=|"
        "primaryCpuAbi=|nativeLibraryDir=| flags=|pkgFlags='; su 0 ls -lZ /vendor/app/OpenBookNvk/; "
        "su 0 sha256sum /vendor/app/OpenBookNvk/OpenBookNvk.apk; "
        "echo nvk_offer=$(su 0 getprop vendor.openbook.nvk.offer) dgpu_ready=$(su 0 getprop vendor.openbook.dgpu.ready); "
        "dumpsys package org.openbook.graphics | grep -E 'versionCode=|versionName=|codePath=|flags=|privateFlags=|signatures=|"
        "android.permission.(REBOOT|WRITE_SECURE_SETTINGS|QUERY_ALL_PACKAGES|POST_NOTIFICATIONS|RECEIVE_BOOT_COMPLETED)'; "
        "ls -l /system_ext/priv-app/OpenBookGraphics/ /system_ext/etc/permissions/privapp-permissions-org.openbook.graphics.xml "
        "/system_ext/etc/default-permissions/default-permissions-org.openbook.graphics.xml /system_ext/etc/sysconfig/openbook-graphics.xml; "
        "dumpsys package org.openbook.graphics | grep -m1 -E ' User 0: .*stopped='; "
        "echo control_privapp=$(getprop ro.control_privapp_permissions) gfx_driver=$(getprop ro.gfx.driver.0); "
        "su 0 grep -h openbook.graphics /system_ext/etc/selinux/system_ext_seapp_contexts")
section("GFX-BOOT",
        "su 0 logcat -d -b main -s OpenBookGraphics; "
        "for k in updatable_driver_all_apps updatable_driver_production_allowlist updatable_driver_production_opt_in_apps "
        "updatable_driver_production_opt_out_apps; do echo \"$k=$(settings get global $k)\"; done; "
        "su 0 cmd jobscheduler get-job-state org.openbook.graphics 312; getprop vendor.openbook.gfx.summary")
steps.append({"send": "am start -W -n org.openbook.graphics/.ui.MainActivity; sleep 8\n"})
steps.append({"wait": P, "timeout": 90})
shot("graphics-main")
section("GFX-MAIN", f"ps -A -Z | grep org.openbook.graphics; {UI}")
# "NVIDIA GPU for apps": off, then on again, through the main screen's switch as the owner taps it.
section("GFX-SWITCH",
        "echo before=$(settings get global updatable_driver_all_apps); tap apps-switch-main; sleep 3; "
        "echo off=$(settings get global updatable_driver_all_apps); ui | tr '>' '\\n' | grep -o 'text=\"Off: every app[^\"]*\"'", 90)
shot("graphics-main-off")
section("GFX-SWITCH-ON",
        "tap apps-switch-main; sleep 3; echo on=$(settings get global updatable_driver_all_apps); "
        "su 0 logcat -d -b main -s OpenBookGraphics | grep 'NVIDIA GPU for apps'", 90)
steps.append({"send": "su 0 am start -W -n org.openbook.graphics/.ui.AppsActivity; sleep 6\n"})
steps.append({"wait": P, "timeout": 90})
shot("graphics-apps")
section("GFX-APPS", UI)
# Settings shows other apps' entries (EXTRA_SETTINGS) only on a provisioned device (SettingsLib TileUtils), and the
# VM never finishes OpenBook's first-run setup: mark it provisioned (this VM copy only) and restart Settings. Injected
# entries come last on the page: the hierarchy before and after scrolling to the end.
steps.append({"send": "input keyevent KEYCODE_BACK; settings put global device_provisioned 1; am force-stop com.android.settings; "
                      "am start -W -a android.settings.DISPLAY_SETTINGS; sleep 8\n"})
steps.append({"wait": P, "timeout": 90})
shot("settings-display")
section("GFX-SETTINGS",
        "cmd package query-activities --brief -a com.android.settings.action.EXTRA_SETTINGS | grep -A1 org.openbook; "
        "echo device_provisioned=$(settings get global device_provisioned); "
        "ui; input swipe 960 1000 960 150 400; sleep 2; input swipe 960 1000 960 150 400; sleep 2; ui", 120)
shot("settings-display-end")
# The test game, over the console in 1000-character lines.
steps.append({"send": "rm -f /data/local/tmp/obg-game.b64\n"})
steps.append({"wait": P, "timeout": 30})
for i in range(0, len(b64), 1000):
    steps.append({"send": f"printf %s '{b64[i:i + 1000]}' >> /data/local/tmp/obg-game.b64\n"})
    steps.append({"wait": P, "timeout": 60})
section("GFX-G14",
        "base64 -d /data/local/tmp/obg-game.b64 > /data/local/tmp/obg-game.apk; sha256sum /data/local/tmp/obg-game.apk; "
        "pm install -r /data/local/tmp/obg-game.apk; "
        "su 0 setprop ro.gfx.driver.0 org.openbook.nvk; echo gfx_driver=$(getprop ro.gfx.driver.0); "
        "settings put global updatable_driver_production_opt_in_apps org.openbook.test.game; "
        "su 0 setprop log.tag.GraphicsEnvironment VERBOSE; "
        "su 0 logcat -c; am start -W -n org.openbook.test.game/android.app.Activity; sleep 8; "
        "pid=$(pidof org.openbook.test.game); echo game_pid=$pid; "
        "su 0 logcat -d -b all | grep -E 'GraphicsEnvironment|updatable|libEGL|vulkan|ANGLE|angle|nvk|NVK|nv_rm|linker|"
        "AndroidRuntime|DEBUG|F libc' | grep -v -E 'OpenBookGraphics' | head -80; "
        "dumpsys gpu | grep -B2 -A14 org.openbook.test.game | head -60", 180)
shot("test-game")
# The switch off (all apps 3): the same game keeps the system driver.
section("GFX-G14-OFF",
        "am force-stop org.openbook.test.game; settings put global updatable_driver_all_apps 3; su 0 logcat -c; "
        "am start -W -n org.openbook.test.game/android.app.Activity; sleep 6; echo game_pid=$(pidof org.openbook.test.game); "
        "su 0 logcat -d -b all | grep -E 'GraphicsEnvironment|updatable|Load updated gl driver|AndroidRuntime' | head -30; "
        "am force-stop org.openbook.test.game; settings put global updatable_driver_all_apps 0", 120)
steps.append({"send": "input keyevent KEYCODE_HOME; su 0 am start -W -n org.openbook.graphics/.ui.AppsActivity; sleep 6\n"})
steps.append({"wait": P, "timeout": 90})
shot("graphics-apps-g14")
section("GFX-APPS-G14",
        f"{UI}; su 0 logcat -d -b main -s OpenBookGraphics; "
        "for k in updatable_driver_production_allowlist updatable_driver_production_opt_in_apps; do "
        "echo \"$k=$(settings get global $k)\"; done; settings delete global updatable_driver_production_opt_in_apps")
section("GFX-AVC",
        "echo kernel:$(su 0 dmesg | grep -c 'avc:  denied'); su 0 dmesg | grep 'avc:  denied' | head -40; "
        "echo logcat:$(su 0 logcat -d -b all | grep -c 'avc:  denied'); "
        "su 0 logcat -d -b all | grep 'avc:  denied' | grep -E 'openbook_graphics_app|org.openbook.graphics' | head -20; "
        "echo app:$(su 0 logcat -d -b all | grep 'avc:  denied' | grep -cE 'openbook_graphics_app|org.openbook.graphics'); "
        "su 0 dmesg | grep 'avc:  denied' | grep -E 'untrusted_app|vendor_app_file|gpu_device' | head -20; "
        "echo game:$(su 0 dmesg | grep 'avc:  denied' | grep -cE 'untrusted_app|vendor_app_file|gpu_device')", 120)
steps.append({"send": "echo ===LOGCAT-BEGIN===; su 0 logcat -d -b all | gzip | base64; echo ===LOGCAT-END===\n"})
steps.append({"wait": P, "timeout": 300})
steps.append({"send": "echo ===DMESG-BEGIN===; su 0 dmesg | gzip | base64; echo ===DMESG-END===\n"})
steps.append({"wait": P, "timeout": 120})
steps.append({"send": "su 0 sync; su 0 reboot -p\n"})
json.dump(steps, open(out, "w"), indent=0)
print(f"{len(steps)} steps, test game {len(b64)} base64 characters")
PY
cp "$W/expect.json" "$L/expect-graphics-app.json"
set +e
"$R/scripts/g14-qemu.sh" "$IMG" "$RUN" "$W/expect.json"
rc=$?
set -e
B=$(ls -d "$L"/boot* | sort -V | tail -1)
python3 "$R/scripts/graphics/graphics-app-report.py" "$B" "$L/graphics-app.json" "$NVK_APK_SHA256" || rc=1
exit $rc
