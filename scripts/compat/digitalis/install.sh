#!/usr/bin/env bash
# Install a Digitalis bundle (scripts/compat/digitalis/build.sh) as the native bridge of the AOSP Desktop
# (Preview) 37.0 emulator image, on a separate AVD "anybook-digitalis" so the libndk_translation AVD of the
# baseline stays untouched (ANAL-181). Leaves the emulator booted on port 5580 for run-matrix.sh / run-bench.sh.
#   install.sh [BUNDLE_DIR] [-o EVIDENCE_DIR]
# Steps: wipe-boot with -writable-system -> adb remount (overlayfs on /mnt/scratch; first remount needs a
# reboot) -> replace the guest arm64 world (/system/{lib64,bin}/arm64) with Digitalis's -> push the translator,
# proxies, runners and configs -> point ro.dalvik.vm.native.bridge at libberberis_arm64.so -> reboot -> verify.
# A data wipe also drops the overlay (checked 2026-10-16), so every fresh run reinstalls.
# The image is Google's (Android SDK Preview License): it is modified only inside the local AVD overlay.
set -euo pipefail
REPO=$(cd "$(dirname "$0")/../../.." && pwd)
A=${ANYBOOK_HOME:-$HOME/anybook}
B=$A/digitalis/bundle; EV=
while [ $# -gt 0 ]; do case $1 in -o) EV=$2; shift ;; *) B=$1 ;; esac; shift; done
ADB="$A/android-sdk/platform-tools/adb -s emulator-5580"
export COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system
EMU=$REPO/scripts/compat/emulator.sh
[ -f "$B/system/lib64/libberberis_arm64.so" ] || { echo "no bundle at $B: run build.sh first" >&2; exit 2; }
( cd "$B" && sha256sum -c --quiet SHA256SUMS ) || { echo "bundle checksum mismatch" >&2; exit 1; }

D=$A/avd/anybook-digitalis.avd
if [ ! -f "$D/config.ini" ]; then
  [ -f "$A/avd/anybook-desktop.avd/config.ini" ] || { echo "run scripts/m0-emulator.sh once first" >&2; exit 2; }
  mkdir -p "$D"; sed 's/^AvdId=.*/AvdId=anybook-digitalis/' "$A/avd/anybook-desktop.avd/config.ini" > "$D/config.ini"
  printf 'avd.ini.encoding=UTF-8\npath=%s\ntarget=android-37.0\n' "$D" > "$A/avd/anybook-digitalis.ini"
fi

wait_boot(){
  local t0; t0=$(date +%s); sleep 5
  until [ "$($ADB shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; do
    [ $(( $(date +%s) - t0 )) -lt 600 ] || { echo "boot timeout" >&2; exit 1; }; sleep 3
  done
  $ADB root >/dev/null 2>&1 || true; sleep 2; $ADB wait-for-device
}

"$EMU" down
"$EMU" up --wipe
$ADB root >/dev/null; sleep 2; $ADB wait-for-device
if ! $ADB remount 2>&1 | tee /dev/stderr | grep -q 'Remount succeeded'; then
  $ADB reboot; wait_boot
  $ADB remount 2>&1 | grep -q 'Remount succeeded' || { echo "adb remount failed" >&2; exit 1; }
fi

# Replace the guest world. Leave libndk_translation.so and its libproxy_* in place (unused once the property
# points elsewhere; its init triggers are conditioned on ro.dalvik.vm.native.bridge=libndk_translation.so).
$ADB shell 'rm -rf /system/lib64/arm64 /system/bin/arm64 && mkdir -p /system/lib64/arm64 /system/bin/arm64'
$ADB push "$B/system/." /system/ >/dev/null
# adb push lands files as 0666; init skips world-writable files ("Skipping insecure file"), so the binfmt_misc
# entries never register. Re-apply the bundle's modes (0755 executables and libraries, 0644 data).
MODES=$(cd "$B" && find system -type f -printf 'chmod %m /%p\n')
# ro.berberis.flags: the image ships "accurate-sigsegv" for libndk_translation (ro.berberis.version=16.0.0);
# use what Digitalis's own product sets (enable_arm64_to_x86_64.mk).
$ADB shell "set -e
  f=/system/build.prop
  sed -i -e 's/^ro.dalvik.vm.native.bridge=.*/ro.dalvik.vm.native.bridge=libberberis_arm64.so/' \
    -e 's/^ro.berberis.flags=.*/ro.berberis.flags=disable-ir-check/' \$f
  grep -q '^ro.berberis.flags=' \$f || echo 'ro.berberis.flags=disable-ir-check' >> \$f
  $MODES
  chown -R root:root /system/lib64/arm64 /system/bin/arm64
  restorecon -R /system/lib64 /system/bin /system/etc 2>/dev/null || true
  sync"
$ADB reboot; wait_boot
"$EMU" up   # re-applies the test settings (animations off, screen on)

R=$($ADB shell 'echo "fingerprint: $(getprop ro.build.fingerprint)"
  echo "native_bridge: $(getprop ro.dalvik.vm.native.bridge) isa.arm64=$(getprop ro.dalvik.vm.isa.arm64) exec=$(getprop ro.enable.native.bridge.exec) flags=$(getprop ro.berberis.flags)"
  echo "abilist: $(getprop ro.product.cpu.abilist)"
  echo "binfmt arm64_dyn: $(cat /proc/sys/fs/binfmt_misc/arm64_dyn 2>&1 | tr "\n" " ")"
  ls -lZ /system/lib64/libberberis_arm64.so /system/bin/berberis_program_runner_binfmt_misc_arm64 /system/bin/arm64/linker64
  echo "guest libs: $(ls /system/lib64/arm64 | wc -l)"
  echo "native bridge in zygote log:"; logcat -d -b main,system | grep -iE "nativebridge|native_bridge|berberis" | head -20' | tr -d '\r')
echo "$R"
{ echo "bundle: $B"; cat "$B/MANIFEST.txt"; echo; echo "$R"; } > "$A/digitalis/install-last.txt"
[ -n "$EV" ] && { mkdir -p "$EV"; cp "$A/digitalis/install-last.txt" "$EV/install.txt"; }
grep -q 'native_bridge: libberberis_arm64.so' <<< "$R"
