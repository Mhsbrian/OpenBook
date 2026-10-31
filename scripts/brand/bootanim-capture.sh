#!/usr/bin/env bash
# Capture the boot animation of a booting device (ANAL-207). Start it right after the VM is launched (it waits for
# adb), e.g. `scripts/cf-boot.sh up & scripts/brand/bootanim-capture.sh 127.0.0.1:16536 OUT`.
#   1. during boot: screencap frames while init.svc.bootanim is running (each named by ms since the first), plus a
#      screenrecord over the same time when the media services are already up;
#   2. after boot: the animation played again on the desktop (start bootanim, record, then service.bootanim.exit=1),
#      which shows all three parts including the exit.
# Writes OUT/boot-frames/*.png, OUT/boot-screenrecord.mp4 (if it worked), OUT/replay.mp4, OUT/replay-frames/*.png
# and OUT/bootanim-capture.log. Needs adb (ANDROID_ADB_SERVER_PORT for a private server) and ffmpeg.
set -uo pipefail
S=${1:?usage: bootanim-capture.sh SERIAL OUT}; OUT=${2:?usage: bootanim-capture.sh SERIAL OUT}
mkdir -p "$OUT/boot-frames" "$OUT/replay-frames"; LOG=$OUT/bootanim-capture.log
log(){ echo "$(date -u +%FT%T.%3NZ) $*" | tee -a "$LOG"; }
a(){ adb -s "$S" "$@"; }
ms(){ date +%s%3N; }

log "waiting for $S"
for _ in $(seq 1 600); do adb connect "$S" >/dev/null 2>&1; a get-state 2>/dev/null | grep -q device && break; sleep 0.5; done
log "adb up: $(a get-state 2>&1)"
for _ in $(seq 1 600); do
  st=$(a shell getprop init.svc.bootanim 2>/dev/null | tr -d '\r')
  [ "$st" = running ] && break
  [ "$(a shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] && break
  sleep 0.2
done
log "bootanim: ${st:-?}; zip: $(a shell ls -la /product/media/bootanimation.zip 2>&1 | tr -d '\r')"
if [ "$st" = running ]; then
  a shell screenrecord --time-limit 30 /data/local/tmp/boot.mp4 >/dev/null 2>&1 &
  REC=$!
  t0=$(ms); n=0
  while [ "$(a shell getprop init.svc.bootanim 2>/dev/null | tr -d '\r')" = running ]; do
    a exec-out screencap -p > "$OUT/boot-frames/f$(printf '%06d' $(( $(ms) - t0 ))).png" 2>/dev/null && n=$((n + 1))
  done
  log "bootanim stopped after $(( $(ms) - t0 )) ms; $n frames captured"
  a shell pkill -INT screenrecord >/dev/null 2>&1; wait $REC 2>/dev/null
  a pull /data/local/tmp/boot.mp4 "$OUT/boot-screenrecord.mp4" >/dev/null 2>&1 && log "boot screenrecord pulled" ||
    log "no boot screenrecord (screenrecord needs the media services; frames above are the evidence)"
  find "$OUT/boot-frames" -size 0 -delete
else
  log "the boot animation was not seen running"
fi

log "waiting for sys.boot_completed"
for _ in $(seq 1 900); do [ "$(a shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] && break; sleep 1; done
a root >/dev/null 2>&1; sleep 2; adb connect "$S" >/dev/null 2>&1; a wait-for-device
sleep 15   # let the desktop settle
log "replay: start bootanim on the desktop"
a shell setprop service.bootanim.exit 0
a shell screenrecord --time-limit 12 /data/local/tmp/replay.mp4 >/dev/null 2>&1 &
REC=$!; sleep 0.5
a shell start bootanim
sleep 6
a shell setprop service.bootanim.exit 1
sleep 3
log "replay: bootanim now $(a shell getprop init.svc.bootanim | tr -d '\r')"
a shell pkill -INT screenrecord >/dev/null 2>&1; wait $REC 2>/dev/null
a pull /data/local/tmp/replay.mp4 "$OUT/replay.mp4" >/dev/null 2>&1 && log "replay recorded" || log "replay not recorded"
if [ -s "$OUT/replay.mp4" ]; then
  ffmpeg -hide_banner -loglevel error -y -i "$OUT/replay.mp4" -vf fps=5,scale=640:-1 "$OUT/replay-frames/r%03d.png"
  log "replay frames: $(ls "$OUT/replay-frames" | wc -l)"
fi
a logcat -d -b main -s BootAnimation > "$OUT/bootanimation-logcat.txt" 2>&1
log "done"
