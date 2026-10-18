#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Smoke test of background blur on the G14 product's disk image in QEMU (ANAL-203): scripts/g14-qemu.sh boots a copy of
# the image (virtio-gpu, so SwiftShader Vulkan under ANGLE: a CPU renderer, whose timings say nothing about the G14).
# It first finishes OpenBook setup (a fresh image starts in it, with the shade disabled). From the serial console it
# records what decides blur (the property, SystemUI's BlurUtils, SurfaceFlinger's
# renderer), takes QEMU screenshots of Quick Settings with blur on and off, types scripts/ui/blur-check.sh into the
# guest (gzip + base64) and runs one short round per state, then brings its output back over the serial port.
#
# usage: blur-qemu.sh IMG RUN          IMG from scripts/g14-image.sh; logs in <data dir>/logs/installer/RUN/boot1/
#   then: OUT=<that dir>/blur (unpacked here) and scripts/ui/blur-report.py OUT
# Env: BLUR_CYCLES (default 5 here)
set -euo pipefail
R=$(cd "$(dirname "$0")/../.." && pwd)
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
IMG=${1:?usage: blur-qemu.sh IMG RUN}; RUN=${2:?run label}
W=$A/installer/qemu/$RUN.blur; mkdir -p "$W"
python3 - "$R/scripts/ui/blur-check.sh" "$W/expect.json" "${BLUR_CYCLES:-5}" <<'EOF'
import base64, gzip, json, sys
script, out, cycles = sys.argv[1], sys.argv[2], sys.argv[3]
b64 = base64.encodebytes(gzip.compress(open(script, "rb").read(), 9)).decode()
P = "console:/ \\$ "
def cmd(text, timeout=60):
    return [{"send": text + "\n"}, {"wait": P, "timeout": timeout}]
steps = [
    {"wait": "init: init first stage started", "timeout": 120},
    {"wait": "init: init second stage started", "timeout": 120},
    {"wait": "Command 'mount_all --late' action=late-fs \\S+ took \\d+ms and succeeded", "timeout": 300},
    {"send": "\n"}, {"wait": P, "timeout": 120},
    *cmd("su 0 dmesg -n 1"),
    {"send": "i=0; while [ \"$(getprop sys.boot_completed)\" != 1 ] && [ $i -lt 900 ]; do sleep 3; i=$((i+3)); done; "
             "echo BOOTDONE=$(getprop sys.boot_completed) uptime=$(cut -d' ' -f1 /proc/uptime)\n"},
    {"wait": "BOOTDONE=\\S* uptime=[0-9.]+", "timeout": 960}, {"wait": P, "timeout": 30},
    *cmd("sleep 30", 90),
    # A fresh image boots into OpenBook setup, where the shade and Quick Settings are disabled. Finish it the way
    # SetupActivity does (the provisioned bits, then the activity leaves the home list), and go home.
    *cmd("su 0 settings put global device_provisioned 1; su 0 settings put secure user_setup_complete 1; "
         "su 0 pm disable org.openbook.installer/.SetupActivity; "
         "su 0 am start -a android.intent.action.MAIN -c android.intent.category.HOME; sleep 10; "
         "su 0 am start -a android.intent.action.MAIN -c android.intent.category.HOME; sleep 10; "
         "su 0 dumpsys activity activities | grep -m2 -E 'ResumedActivity|topResumedActivity'", 120),
    *cmd("echo ===BLURFACTS-BEGIN===; for p in ro.surface_flinger.supports_background_blur vendor.anybook.gpu.hal "
         "ro.hardware.egl ro.hardware.vulkan ro.hwui.use_vulkan debug.renderengine.backend; do echo $p=$(getprop $p); "
         "done; su 0 dumpsys activity service com.android.systemui/.SystemUIService BlurUtils | grep -E "
         "'Radius|supports|CROSS|HighEnd'; su 0 dumpsys SurfaceFlinger | grep -E '^GLES: |RenderEngine'; "
         "echo ===BLURFACTS-END===", 120),
    *cmd("su 0 input keyevent KEYCODE_WAKEUP; su 0 wm dismiss-keyguard; su 0 settings put global disable_window_blurs 0; "
         "sleep 2; su 0 cmd statusbar expand-settings; sleep 4; echo QS-ON"),
    {"shot": "qs-blur-on"},
    *cmd("echo ===QSLAYERS-ON-BEGIN===; su 0 dumpsys SurfaceFlinger | grep -E 'backgroundBlurRadius=|blurRegions'; "
         "echo ===QSLAYERS-ON-END===; su 0 cmd statusbar collapse; su 0 settings put global disable_window_blurs 1; "
         "sleep 2; su 0 cmd statusbar expand-settings; sleep 4; echo QS-OFF"),
    {"shot": "qs-blur-off"},
    *cmd("echo ===QSLAYERS-OFF-BEGIN===; su 0 dumpsys SurfaceFlinger | grep -E 'backgroundBlurRadius=|blurRegions'; "
         "echo ===QSLAYERS-OFF-END===; su 0 cmd statusbar collapse; su 0 settings put global disable_window_blurs 0"),
    # mksh keeps a here-document in a temp file, in TMPDIR (default /data/local, which the shell user can't write).
    *cmd("export TMPDIR=/data/local/tmp"),
    {"send": "su 0 sh -c 'base64 -d | gzip -d > /data/local/tmp/blur-check.sh' <<'EOF'\n" + b64 + "EOF\n"},
    {"wait": P, "timeout": 120},
    *cmd("su 0 sha256sum /data/local/tmp/blur-check.sh"),
    *cmd(f"su 0 env BLUR_SHOTS=0 BLUR_CYCLES={cycles} sh /data/local/tmp/blur-check.sh /data/local/tmp/blur-out on off; "
         "echo BLURCHECK-EXIT=$?", 1800),
    *cmd("echo ===BLUROUT-BEGIN===; su 0 tar -C /data/local/tmp/blur-out -czf - . | base64; echo ===BLUROUT-END===", 300),
    *cmd("echo ===CRASH-BEGIN===; su 0 logcat -d -b crash | tail -n 60; echo ===CRASH-END===; "
         "echo ===AVC-BEGIN===; su 0 dmesg | grep -c 'avc:  denied'; echo ===AVC-END===", 120),
    *cmd("echo ===LOGCAT-BEGIN===; su 0 logcat -d -b all | gzip | base64; echo ===LOGCAT-END===", 300),
    {"send": "su 0 sync; su 0 reboot -p\n"},
]
json.dump(steps, open(out, "w"), indent=1)
EOF
echo "expect: $W/expect.json"
set +e
"$R/scripts/g14-qemu.sh" "$IMG" "$RUN" "$W/expect.json"
rc=$?
set -e
L=$A/logs/installer/$RUN; O=$(ls -d "$L"/boot* | sort -V | tail -n 1)
if [ -s "$O/sections/blurout.txt" ]; then   # serial-extract.py names sections in lower case
  rm -rf "$O/blur"; mkdir -p "$O/blur"
  tr -d ' \r' < "$O/sections/blurout.txt" | base64 -d | tar -xzf - -C "$O/blur" && echo "blur-check output: $O/blur"
fi
echo "run: $O (g14-qemu.sh exit $rc)"
exit $rc
