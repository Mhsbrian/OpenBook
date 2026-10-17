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
cmd wifi set-wifi-enabled disabled; sleep 3; cmd wifi set-wifi-enabled enabled
i=0; while [ $i -lt 30 ] && ! cmd wifi status | grep -q 'Wifi is enabled'; do sleep 1; i=$((i + 1)); done
echo "supplicant: $(getprop init.svc.wpa_supplicant)"
cmd wifi start-scan; sleep 8
echo "test network in scan results: $(cmd wifi list-scan-results | grep -c openbook-test)"
cmd wifi connect-network openbook-test wpa2 openbook-test-psk
i=0; while [ $i -lt 60 ] && ! cmd wifi status | grep -q 'Wifi is connected to'; do sleep 1; i=$((i + 1)); done
sleep 5
echo "connected after ${i} s"
OPENBOOK_HWTEST_IPERF3_SERVER=192.168.77.1 OPENBOOK_HWTEST_IPERF3_SECONDS=5 openbook-hwtest wifi
echo "--- dhcpd and hostapd (access point side) ---"
cat "$D/dhcpd.log"; tail -n 20 "$D/hostapd.log"
echo "===WIFI-END==="

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
