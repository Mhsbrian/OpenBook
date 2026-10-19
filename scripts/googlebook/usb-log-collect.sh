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
ls -l /dev/dri
# Continuous Android buffers alongside bounded periodic service snapshots.
timeout 600 logcat -b all -v threadtime &
logpid=$!
trap 'kill "$logpid" 2>/dev/null' EXIT
# Binder shell commands may pass stdout to the service. Use an ordinary shell
# pipe (already allowed by the platform) so system_server need not access the
# logger's private named FIFO. Only this shell's cat writes the named FIFO.
service_dump() {
    "$@" 2>&1 | cat
}
for checkpoint in $(seq 1 36); do
    kill -0 "$logpid" 2>/dev/null || break
    echo "RUBY_CHECKPOINT=$checkpoint"
    date
    cat /proc/uptime /proc/meminfo /proc/modules
    cat /proc/asound/cards /proc/asound/pcm
    ls -l /dev/snd
    for prop in sys.boot_completed init.svc.wpa_supplicant init.svc.wifi_mainline_supplicant \
        init.svc.audioserver init.svc.ruby-usb-log; do
        echo "$prop=$(getprop "$prop")"
    done
    ps -AZ
    ls -l /dev/block/by-name
    cat /proc/mounts
    # Wi-Fi dumps contain network identifiers: keep raw captures private.
    # No credentials, saved network XML, or microphone samples are requested.
    service_dump timeout 8 cmd wifi status
    service_dump timeout 8 cmd overlay list --user 0
    for resource in config_wifiMainlineSupplicantEnabled config_wifi_connected_mac_randomization_supported \
        config_wifiDropConnectionWhenMacConfigurationFails; do
        echo "=== resource $resource ==="
        service_dump timeout 8 cmd overlay lookup --user 0 com.google.android.wifi.resources "com.google.android.wifi.resources:bool/$resource"
    done
    for service in wifi connectivity audio media.audio_flinger media.audio_policy; do
        echo "=== dumpsys $service ==="
        service_dump timeout 8 dumpsys "$service"
    done
    # Keep occasional desktop context without filling the log budget with
    # complete SurfaceFlinger/window dumps every fifteen seconds.
    if [ "$checkpoint" = 1 ] || [ "$checkpoint" = 18 ] || [ "$checkpoint" = 36 ]; then
        for service in SurfaceFlinger display window power; do
            echo "=== dumpsys $service ==="
            service_dump timeout 8 dumpsys "$service"
        done
    fi
    sleep 15
done
echo 'RUBY_SNAPSHOTS_END'
# Fast failing services make the 18 snapshots finish in about 4.5 minutes.
# Keep logcat alive for the remaining capture window; the sink closes its FIFO
# at 600 seconds (or its byte limit), and timeout also bounds a silent logcat.
wait "$logpid"
echo 'RUBY_ANDROID_LOG_END'
