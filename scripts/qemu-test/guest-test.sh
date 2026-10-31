#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# QEMU only (scripts/audio-net-qemu.sh), as root on the guest: the audio, Wi-Fi and Bluetooth checks against QEMU's
# HDA card and the mac80211_hwsim access point. Prints ===NAME-BEGIN/END=== sections for serial-extract.py, and
# the HWTEST lines of openbook-hwtest. The loopback tests play two 2 s tones into QEMU's WAV file; QEMU's codec
# records silence, so "heard" is false here by design.
D=${0%/*}
echo "===AUDIO-BEGIN==="
echo "primary card $(getprop vendor.audio.primary.card) device $(getprop vendor.audio.primary.device)"
cat /proc/asound/cards /proc/asound/pcm
dmesg | grep 'openbook-audio-setup'
echo "audio HAL: $(getprop init.svc.vendor.audio-hal-aidl) $(getprop init.svc.vendor.audio-hal)"
openbook-hwtest audio
echo "===AUDIO-END==="

echo "===WIFI-BEGIN==="
sh "$D/run-ap.sh"
# The framework resolved nl80211's generic-netlink family when it started; reloading cfg80211 renumbered it. Restart
# the framework so it finds the new one (on a laptop cfg80211 loads at early-init, before system_server).
stop; start
i=0; while [ $i -lt 120 ] && ! cmd wifi status > /dev/null 2>&1; do sleep 2; i=$((i + 2)); done
echo "framework back after ${i} s"; sleep 15
cmd wifi set-wifi-enabled disabled; sleep 3; cmd wifi set-wifi-enabled enabled
i=0; while [ $i -lt 30 ] && ! cmd wifi status | grep -q 'Wifi is enabled'; do sleep 1; i=$((i + 1)); done
echo "supplicant: $(getprop init.svc.wpa_supplicant)"
i=0; while [ $i -lt 40 ] && ! cmd wifi list-scan-results | grep -q openbook-test; do cmd wifi start-scan; sleep 4; i=$((i + 4)); done
echo "test network in scan results after ${i} s: $(cmd wifi list-scan-results | grep -c openbook-test)"
cmd wifi connect-network openbook-test wpa2 openbook-test-psk
i=0; while [ $i -lt 60 ] && ! cmd wifi status | grep -q 'Wifi is connected to'; do sleep 1; i=$((i + 1)); done
sleep 5
echo "connected after ${i} s"
OPENBOOK_HWTEST_IPERF3_SERVER=192.168.77.1 OPENBOOK_HWTEST_IPERF3_SECONDS=5 openbook-hwtest wifi
echo "--- dhcpd and hostapd (access point side) ---"
ps -A -o PID,NAME | grep -E 'hostapd|dhcpd|iperf3'
nsenter -t "$(cat "$D/ns.pid")" -n iw dev wlan1 info 2>&1 | grep -E 'type|ssid|channel'
cat "$D/dhcpd.log"; grep -vE 'hexdump|^$' "$D/hostapd.log" | tail -n 40
echo "===WIFI-END==="

echo "===PNO-BEGIN==="
# Screen off and disconnected, the framework scans only through PNO, i.e. the driver's scheduled scan
# (config_wifi_background_scan_support). hwsim has none, so here the attempt fails; without the setting it is never
# made ("PNO is not available"). The test network has no internet, so after its failed validation Android keeps it out
# of autojoin and PNO ("No saved network for starting disconnected PNO"): reconnect with validation off (this step
# only), then take the access point away with the screen off.
settings put global captive_portal_mode 0
cmd wifi connect-network openbook-test wpa2 openbook-test-psk
i=0; while [ $i -lt 30 ] && ! cmd wifi status | grep -q 'Wifi is connected to'; do sleep 1; i=$((i + 1)); done
sleep 8; echo "reconnected after ${i} s, validation off"
t0=$(date +'%m-%d %H:%M:%S.000')
input keyevent SLEEP; sleep 2
kill "$(cat "$D/hostapd.pid")"; sleep 25
logcat -d -b main -T "$t0" | grep -E 'PNO|Pno|pno|SchedScan|sched scan' | tail -n 30
input keyevent WAKEUP
settings delete global captive_portal_mode
echo "===PNO-END==="

echo "===BT-BEGIN==="
openbook-hwtest bt
echo "===BT-END==="

echo "===PACED-BEGIN==="
# For comparison, the same AAudio loopback with AOSP's wall-clock pacing back on (patch 0002 off): a third tone in
# the WAV file, and the HAL's padding and drops counted the way openbook-hwtest counts them.
setprop vendor.audio.primary.pacing true
setprop ctl.restart vendor.audio-hal-aidl
sleep 5; i=0; while [ $i -lt 60 ] && ! dumpsys media.audio_policy 2>/dev/null | grep -q 'Port ID: [0-9]*; "Speaker"'; do sleep 2; i=$((i + 2)); done
sleep 5
pol=$(dumpsys media.audio_policy 2>&1)
spk=$(echo "$pol" | sed -n 's/.*Port ID: \([0-9]*\); "Speaker".*/\1/p' | head -n 1)
mic=$(echo "$pol" | sed -n 's/.*Port ID: \([0-9]*\); "Built-In Mic".*/\1/p' | head -n 1)
echo "audio back after ${i} s, pacing $(getprop vendor.audio.primary.pacing), ports $spk $mic"
cmd media_session volume --stream 3 --set 10 > /dev/null 2>&1
t0=$(date +'%m-%d %H:%M:%S.000')
r=$(timeout 30 openbook-audio-test --wav /data/local/tmp/openbook-aaudio-paced.wav ${spk:+--out-device $spk} \
      ${mic:+--in-device $mic} 2>&1 | tail -n 1)
hal=$(logcat -d -b main -T "$t0" 2>/dev/null | grep 'AHAL_')
echo "PACED ${r%\}}, \"hal_input_pads\": $(echo "$hal" | grep -c 'inserting [0-9]* frames of silence'), \"hal_output_drops\": $(echo "$hal" | grep -c 'dropping [0-9]* frames'), \"hal_skipped_transfers\": $(echo "$hal" | grep -c 'skipping transfer')}"
echo "===PACED-END==="

echo "===HALLOG-BEGIN==="
logcat -d -b all | grep -iE 'wpa_supplicant|WifiNative|WifiVendorHal|wificond|AHAL_|audioserver|AudioFlinger.*(open|fail)|BluetoothHci|bluetooth-service|openbook' | tail -n 250
echo "===HALLOG-END==="
echo "===AVCNEW-BEGIN==="
dmesg | grep 'avc:  denied' | grep -E 'hal_wifi_supplicant|wificond|hal_bluetooth|bluetooth|hal_audio|audioserver|openbook_audio|rfkill' | sed -E 's/^\[[ 0-9.]*\] //' | sort | uniq -c | sort -rn | head -40
echo "===AVCNEW-END==="
echo GUEST-TEST-DONE
