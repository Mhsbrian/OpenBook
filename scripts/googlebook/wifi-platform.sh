#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# A mutable RRO can take precedence over Ruby's retained product RRO without
# changing its signed framework images. Wi-Fi runs in the system user (0).
# No saved networks, credentials, Wi-Fi toggle or supplicant choice is changed.
# Init must enter the shell domain through sh (its permitted entrypoint), not
# toybox. Once inside that domain, timeout bounds service discovery and binder
# calls without granting a new executable entrypoint.
if [ "${1:-}" != --bounded ]; then
    exec timeout 180 /system/bin/sh "$0" --bounded
fi
package=org.openbook.ruby.wifi
for attempt in $(seq 1 90); do
    if cmd overlay list --user 0 "$package" 2>/dev/null | grep -q "$package"; then
        if cmd overlay enable --user 0 "$package" &&
            cmd overlay set-priority --user 0 "$package" highest; then
            result=ok
            for resource in config_wifi_connected_mac_randomization_supported config_wifiDropConnectionWhenMacConfigurationFails; do
                value=$(cmd overlay lookup --user 0 com.google.android.wifi.resources "com.google.android.wifi.resources:bool/$resource")
                log -t OpenBookRubyWifi "$resource=$value"
                [ "$value" = false ] || result=failed
            done
            log -t OpenBookRubyWifi "platform overlay verification=$result"
            [ "$result" = ok ] && exit 0
        fi
    fi
    sleep 2
done
log -p e -t OpenBookRubyWifi 'platform overlay could not be applied; inspect overlay diagnostics'
exit 1
