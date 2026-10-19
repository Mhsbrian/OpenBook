#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Shell-domain read-only diagnostics. Sink bounds storage and lifetime.
for wait in $(seq 1 60); do
    [ -p /dev/ruby-log-stream ] && break
    sleep 1
done
[ -p /dev/ruby-log-stream ] || exit 1
exec > /dev/ruby-log-stream 2>&1
echo 'RUBY_ANDROID_LOG_BEGIN'
id
getenforce
cat /proc/cmdline /proc/bootconfig
cat /sys/module/firmware_class/parameters/path
ls -l /dev/dri
# Continuous Android buffers alongside bounded periodic service snapshots.
timeout 600 logcat -b all -v threadtime &
logpid=$!
trap 'kill "$logpid" 2>/dev/null' EXIT
for checkpoint in $(seq 1 18); do
    echo "RUBY_CHECKPOINT=$checkpoint"
    date
    cat /proc/uptime /proc/meminfo /proc/swaps /proc/modules
    getprop
    ps -AZ
    ls -l /dev/block/by-name
    cat /proc/mounts
    for service in SurfaceFlinger display window activity power; do
        echo "=== dumpsys $service ==="
        timeout 8 dumpsys "$service"
    done
    sleep 15
done
echo 'RUBY_SNAPSHOTS_END'
# Fast failing services make the 18 snapshots finish in about 4.5 minutes.
# Keep logcat alive for the remaining capture window; the sink closes its FIFO
# at 600 seconds (or its byte limit), and timeout also bounds a silent logcat.
wait "$logpid"
echo 'RUBY_ANDROID_LOG_END'
