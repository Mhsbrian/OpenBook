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
# made ("PNO is not available").
t0=$(date +'%m-%d %H:%M:%S.000')
input keyevent SLEEP; sleep 2
cmd wifi set-wifi-enabled disabled; sleep 3; cmd wifi set-wifi-enabled enabled; sleep 20
logcat -d -b main -T "$t0" | grep -E 'PNO|Pno|pno|SchedScan|sched scan' | tail -n 30
input keyevent WAKEUP
echo "===PNO-END==="

echo "===BT-BEGIN==="
openbook-hwtest bt
echo "===BT-END==="

echo "===HALLOG-BEGIN==="
logcat -d -b all | grep -iE 'wpa_supplicant|WifiNative|WifiVendorHal|wificond|AHAL_|audioserver|AudioFlinger.*(open|fail)|BluetoothHci|bluetooth-service|openbook' | tail -n 250
echo "===HALLOG-END==="
echo "===AVCNEW-BEGIN==="
dmesg | grep 'avc:  denied' | grep -E 'hal_wifi_supplicant|wificond|hal_bluetooth|bluetooth|hal_audio|audioserver|openbook_audio|rfkill' | sed -E 's/^\[[ 0-9.]*\] //' | sort | uniq -c | sort -rn | head -40
echo "===AVCNEW-END==="
echo GUEST-TEST-DONE
