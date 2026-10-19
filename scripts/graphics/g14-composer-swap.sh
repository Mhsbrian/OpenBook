#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Try a composer build on the installed G14 without a reinstall (ANAL-212). The drm_hwcomposer service binary is
# copied onto a small tmpfs in init's mount namespace (/mnt/openbook-hwc), given the vendor file's SELinux label and
# bind-mounted over /vendor/bin/hw/android.hardware.composer.hwc3-service.drm; then the composer is restarted.
# - The tmpfs is mounted without nosuid on purpose: init cannot enter the HAL's SELinux domain from a nosuid mount
#   such as /data ("nosuid_transition" denied). The first version of this script bound the file from /data, the
#   composer could not start, and the laptop rebooted itself a minute later.
# - If the new composer is not running 10 s after the restart, the bind mount is removed at once, so init's next
#   restart uses the installed binary.
# Nothing on the disk's partitions changes; a reboot or --revert brings the installed binary back.
# Restarting the composer restarts SurfaceFlinger and the whole UI (vendor.hwcomposer-3 has "onrestart restart
# surfaceflinger"): open apps close. Ask the owner first.
#
# usage: g14-composer-swap.sh [ADDR[:PORT]] BINARY     e.g. out/target/product/anybook_g14/vendor/bin/hw/android.hardware.composer.hwc3-service.drm
#        g14-composer-swap.sh [ADDR[:PORT]] --revert
# env:   ADB, ANDROID_ADB_SERVER_PORT, OPENBOOK_G14_ADDR as in g14-flip-check.sh
set -euo pipefail
A=${OPENBOOK_HOME:-${ANYBOOK_HOME:-$HOME/anybook}}
ADB=${ADB:-$A/android-sdk/platform-tools/adb}
export ANDROID_ADB_SERVER_PORT=${ANDROID_ADB_SERVER_PORT:-5233}
D=${OPENBOOK_G14_ADDR:-192.168.50.11}
if [ $# -eq 2 ]; then D=$1; shift; fi
[[ $D == *:* ]] || D=$D:5555
ARG=${1:?usage: g14-composer-swap.sh [ADDR[:PORT]] BINARY|--revert}
timeout 20 "$ADB" connect "$D" >/dev/null
sh_() { timeout 180 "$ADB" -s "$D" shell "$@"; }

NEW=none
if [ "$ARG" != --revert ]; then
  [ -f "$ARG" ] || { echo "no such file: $ARG" >&2; exit 1; }
  NEW=$(sha256sum "$ARG" | cut -d' ' -f1)
  echo "pushing $ARG (${NEW:0:16}…)"
  timeout 120 "$ADB" -s "$D" push "$ARG" /data/local/tmp/openbook-hwc3-service.new >/dev/null
fi

# On the laptop, as root. $1: BINARY or --revert, $2: the new binary's sha256.
sh_ su 0 sh -s -- "$ARG" "$NEW" <<'DEVICE' || echo "(the adb session ended during the restart)"
set -e
V=/vendor/bin/hw/android.hardware.composer.hwc3-service.drm
N=/data/local/tmp/openbook-hwc3-service.new
M=/mnt/openbook-hwc
ns() { nsenter -t 1 -m -- sh -c "$1"; }
ns "grep -q ' $V ' /proc/self/mountinfo && umount -l $V; grep -q ' $M ' /proc/self/mountinfo && umount -l $M; true"
if [ "$1" != --revert ]; then
  ns "mkdir -p $M && mount -t tmpfs -o mode=0755,size=8m tmpfs $M && cp $N $M/hwc3-service && chmod 755 $M/hwc3-service &&
      chcon u:object_r:hal_graphics_composer_default_exec:s0 $M/hwc3-service && mount --bind $M/hwc3-service $V"
  rm -f $N
  echo "bound: $(ns "sha256sum $V" | cut -c1-16)… over $V; $(ns "ls -Z $V" | cut -d' ' -f1); staging mount: $(ns "grep ' $M ' /proc/self/mountinfo" | grep -o nosuid || echo 'not nosuid')"
else
  rm -f $N
  echo "reverted: $(sha256sum $V | cut -c1-16)… (the installed binary)"
fi
# The restart and the 10 s check run detached: restarting the composer can cut this adb session.
cat > /data/local/tmp/openbook-hwc-guard.sh <<GUARD
V=$V; M=$M
setprop ctl.restart vendor.hwcomposer-3
[ "\$1" = none ] && exit 0
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 1
  p=\$(pidof android.hardware.composer.hwc3-service.drm)
  if [ -n "\$p" ] && [ "\$(sha256sum /proc/\$p/exe 2>/dev/null | cut -d' ' -f1)" = "\$1" ]; then echo "new composer running: pid \$p"; exit 0; fi
done
echo "new composer NOT running after 10 s: removing the bind mount; init restarts the installed one"
nsenter -t 1 -m -- sh -c "umount -l \$V; umount -l \$M; true"
GUARD
echo "restarting the composer (and the UI)"
[ "$1" = --revert ] && h=none || h=$2
setsid nohup sh /data/local/tmp/openbook-hwc-guard.sh "$h" > /data/local/tmp/openbook-hwc-guard.log 2>&1 < /dev/null &
DEVICE

echo "waiting for the UI to come back"
for _ in $(seq 1 60); do
  sleep 2
  [ "$(sh_ getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] &&
    sh_ dumpsys SurfaceFlinger --scheduler 2>/dev/null | grep -q 'renderRate=' && break
done
sleep 2; sh_ su 0 cat /data/local/tmp/openbook-hwc-guard.log 2>/dev/null || true
sh_ 'p=$(pidof android.hardware.composer.hwc3-service.drm); echo "composer pid $p: $(su 0 sha256sum /proc/$p/exe | cut -c1-16)…; surfaceflinger: $(getprop init.svc.surfaceflinger); uptime: $(cut -d" " -f1 /proc/uptime) s"'
