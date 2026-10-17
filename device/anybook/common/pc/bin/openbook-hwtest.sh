#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# OpenBook Wi-Fi, Bluetooth and audio checks for the live image's "save logs" entry (live-init runs it as root in
# Android's mount namespace) and for a device agent; also by hand: `su 0 openbook-hwtest [wifi|bt|audio]`.
# mksh + toybox. Prints readable facts plus one "HWTEST {json}" line per result, which live-report.py turns into
# verdicts. Changes nothing persistent: it may switch Wi-Fi and Bluetooth on (the user's own toggles), scans,
# and plays a 2 s, 1 kHz tone on the speakers while it records the built-in mic. docs/g14-audio-net.md.
#
# Settings (environment; live-init passes openbook/hwtest.conf from the stick's ESP as OPENBOOK_HWTEST_<KEY>):
#   OPENBOOK_HWTEST_IPERF3_SERVER   host running `iperf3 -s` on the same network (no default: no throughput test)
#   OPENBOOK_HWTEST_IPERF3_SECONDS  per direction (default 10)
#   OPENBOOK_HWTEST_TONE            0 skips the speaker tone and the loopback tests (default 1)
# No Wi-Fi credentials here: connect once in Settings on the stick; the network stays saved in its /data.
PATH=/system/bin:/system_ext/bin:/vendor/bin:$PATH
IPERF=${OPENBOOK_HWTEST_IPERF3_SERVER:-}
IPERF_S=${OPENBOOK_HWTEST_IPERF3_SECONDS:-10}
TONE=${OPENBOOK_HWTEST_TONE:-1}
case $IPERF in *[!A-Za-z0-9.:-]*) echo "openbook-hwtest: ignoring iperf3 server '$IPERF'"; IPERF= ;; esac
case $IPERF_S in ''|*[!0-9]*) IPERF_S=10 ;; esac

h() { echo; echo "--- $* ---"; }
# Network and device names and hardware addresses stay out of the logs.
red() { sed -E 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/<mac>/g; s/"[^"]*"/"<name>"/g; s/(SSID|Name|ssid|name)[:=] *[^,]*/\1: <name>/g'; }
j() { echo "HWTEST {$*}"; }
q() { printf '"%s"' "$(printf '%s' "$1" | tr -d '"\\' | tr '\n\t' '  ')"; }
num() { case $1 in ''|*[!0-9.-]*) echo null ;; *) echo "$1" ;; esac; }

wifi() {
  h "wifi: driver and regulatory"
  iface=$(getprop wifi.interface); iface=${iface:-wlan0}
  ls -l /sys/class/net/$iface/device/driver 2>&1 | sed 's/.*-> //'
  iw dev 2>&1 | grep -vE 'addr|ssid' | head -n 30 | red
  iw reg get 2>&1 | head -n 20
  regdb=$(dmesg | grep -iE 'regulatory|regdb|cfg80211' | tail -n 8)
  echo "$regdb"
  regdb_ok=false; [ -f /vendor/firmware/regulatory.db ] && ! echo "$regdb" | grep -q 'failed to load regulatory.db' && regdb_ok=true
  country=$(iw reg get 2>/dev/null | sed -n 's/^country \([A-Z0-9][A-Z0-9]\).*/\1/p' | head -n 1)
  j "\"test\": \"wifi-driver\", \"iface\": $(q "$iface"), \"present\": $([ -e /sys/class/net/$iface ] && echo true || echo false), \"driver\": $(q "$(basename "$(readlink /sys/class/net/$iface/device/driver)" 2>/dev/null)"), \"regdb_loaded\": $regdb_ok, \"country\": $(q "$country")"

  h "wifi: framework"
  echo "supplicant: $(getprop init.svc.wpa_supplicant)"
  if ! cmd wifi status 2>&1 | grep -q 'Wifi is enabled'; then
    cmd wifi set-wifi-enabled enabled 2>&1
    i=0; while [ $i -lt 20 ] && ! cmd wifi status 2>&1 | grep -q 'Wifi is enabled'; do sleep 1; i=$((i + 1)); done
  fi
  st=$(cmd wifi status 2>&1)
  echo "$st" | head -n 25 | red
  enabled=false; echo "$st" | grep -q 'Wifi is enabled' && enabled=true
  j "\"test\": \"wifi-enabled\", \"ok\": $enabled, \"supplicant\": $(q "$(getprop init.svc.wpa_supplicant)")"

  h "wifi: scan"
  cmd wifi start-scan 2>&1
  sleep 10
  res=$(cmd wifi list-scan-results 2>&1)
  n=$(echo "$res" | grep -cE '^ *[0-9a-f]{2}(:[0-9a-f]{2}){5}')
  f2=$(echo "$res" | awk '$2 ~ /^2[0-9][0-9][0-9]$/' | wc -l)
  f5=$(echo "$res" | awk '$2 ~ /^5[0-9][0-9][0-9]$/ && $2 < 5925' | wc -l)
  f6=$(echo "$res" | awk '$2 ~ /^[5-7][0-9][0-9][0-9]$/ && $2 >= 5925' | wc -l)
  echo "$n networks: $f2 on 2.4 GHz, $f5 on 5 GHz, $f6 on 6 GHz"
  j "\"test\": \"wifi-scan\", \"ok\": $([ "$n" -gt 0 ] && echo true || echo false), \"networks\": $n, \"ghz2\": $f2, \"ghz5\": $f5, \"ghz6\": $f6"

  h "wifi: connection"
  conn=false; echo "$st" | grep -q 'Wifi is connected to' && conn=true
  link=$(iw dev "$iface" link 2>&1)
  echo "$link" | grep -vE 'SSID|Connected to' | head -n 12 | red
  freq=$(echo "$link" | sed -n 's/.*freq: *\([0-9.]*\).*/\1/p' | head -n 1)
  sig=$(echo "$link" | sed -n 's/.*signal: *\(-*[0-9]*\) dBm.*/\1/p' | head -n 1)
  tx=$(echo "$link" | sed -n 's/.*tx bitrate: *\([0-9.]*\) MBit.*/\1/p' | head -n 1)
  rx=$(echo "$link" | sed -n 's/.*rx bitrate: *\([0-9.]*\) MBit.*/\1/p' | head -n 1)
  ip4=$(ip -4 addr show "$iface" 2>/dev/null | sed -n 's/.*inet \([0-9.]*\/[0-9]*\).*/\1/p' | head -n 1)
  gw=$(ip route show table all 2>/dev/null | sed -n "s/^default via \([0-9.]*\) dev $iface .*/\1/p" | head -n 1)
  echo "IPv4 ${ip4:-none}, gateway ${gw:-none}"
  j "\"test\": \"wifi-connect\", \"ok\": $conn, \"freq_mhz\": $(num "$freq"), \"signal_dbm\": $(num "$sig"), \"tx_mbit\": $(num "$tx"), \"rx_mbit\": $(num "$rx")"
  j "\"test\": \"wifi-dhcp\", \"ok\": $([ -n "$ip4" ] && echo true || echo false), \"prefix\": $(q "${ip4#*/}"), \"gateway\": $([ -n "$gw" ] && echo true || echo false)"
  if [ -n "$gw" ]; then
    p=$(ping -c 5 -W 2 "$gw" 2>&1 | tail -n 2)
    echo "$p"
    loss=$(echo "$p" | sed -n 's/.* \([0-9]*\)% packet loss.*/\1/p')
    avg=$(echo "$p" | sed -n 's/.*= [0-9.]*\/\([0-9.]*\)\/.*/\1/p')
    j "\"test\": \"wifi-ping-gateway\", \"ok\": $([ "${loss:-100}" -lt 100 ] && echo true || echo false), \"loss_pct\": $(num "$loss"), \"avg_ms\": $(num "$avg")"
  fi
  v=$(dumpsys connectivity 2>/dev/null | grep -E 'NetworkAgentInfo.*WIFI' | head -n 1)
  valid=false; echo "$v" | grep -q 'VALIDATED' && valid=true
  j "\"test\": \"wifi-validated\", \"ok\": $valid"
  if [ -n "$IPERF" ] && [ "$conn" = true ]; then
    h "wifi: iperf3 to the configured server, $IPERF_S s each way"
    for dir in up down; do
      r=; [ $dir = down ] && r=-R
      out=$(timeout $((IPERF_S + 20)) iperf3 -c "$IPERF" -t "$IPERF_S" -f m $r 2>&1)
      echo "$out" | tail -n 6
      mbit=$(echo "$out" | awk '/receiver$/ {for (i = 1; i < NF; i++) if ($(i + 1) == "Mbits/sec") v = $i} END {print v}')
      j "\"test\": \"wifi-iperf3-$dir\", \"ok\": $([ -n "$mbit" ] && echo true || echo false), \"mbit_s\": $(num "$mbit"), \"seconds\": $IPERF_S"
    done
  fi
}

bt() {
  h "bluetooth: controller and HAL"
  dmesg | grep -iE 'bluetooth: hci|btmtk|btusb' | tail -n 8 | red
  echo "HAL: $(getprop init.svc.vendor.bluetooth-default)"
  if ! dumpsys bluetooth_manager 2>/dev/null | grep -q 'State: *ON'; then
    cmd bluetooth_manager enable 2>&1
    timeout 30 cmd bluetooth_manager wait-for-state:STATE_ON 2>&1
  fi
  d=$(dumpsys bluetooth_manager 2>&1)
  echo "$d" | grep -E '^ *State:|Bluetooth crashed' | head -n 4
  echo "$d" | sed -n '/^Enabled Profile Services:/,/^$/p' | head -n 30
  on=false; echo "$d" | grep -q 'State: *ON' && on=true
  bonded=$(echo "$d" | sed -n 's/^ *Bonded devices: *\([0-9]*\).*/\1/p' | head -n 1)
  a2dp=$(echo "$d" | grep -cE 'A2DP.*(Connected|STATE_CONNECTED)|mActiveDevice: *[0-9A-FX:]{6}')
  j "\"test\": \"bt-enabled\", \"ok\": $on, \"hal\": $(q "$(getprop init.svc.vendor.bluetooth-default)")"
  j "\"test\": \"bt-bonded\", \"ok\": $([ "${bonded:-0}" -gt 0 ] && echo true || echo false), \"bonded\": $(num "${bonded:-0}"), \"audio_lines\": $a2dp"
}

audio() {
  h "audio: cards, PCMs and mixer"
  openbook-audio-setup list 2>&1 | head -n 150
  card=$(getprop vendor.audio.primary.card)
  pcm=$(grep "^$(printf '%02d' "${card:-0}" 2>/dev/null)-" /proc/asound/pcm 2>/dev/null | head -n 1)
  j "\"test\": \"audio-card\", \"ok\": $([ -n "$card" ] && [ "$card" != -1 ] && echo true || echo false), \"card\": $(num "$card"), \"pcm\": $(q "$pcm")"
  h "audio: policy"
  dumpsys media.audio_policy 2>&1 | grep -A4 -E 'Available (output|input) devices' | head -n 20
  dumpsys media.audio_flinger 2>&1 | grep -E 'Hardware status|Output devices|Input device|Standby|Sample rate|HAL format' | head -n 20
  if [ "$TONE" = 1 ]; then
    h "audio: speaker -> built-in mic, direct ALSA (2 s at 1 kHz)"
    r=$(openbook-audio-setup test --wav /data/local/tmp/openbook-alsa-loopback.wav 2>&1 | tail -n 1)
    echo "$r"; case $r in '{'*) echo "HWTEST ${r}" ;; esac
    sleep 2
    h "audio: speaker -> built-in mic through Android (AAudio)"
    r=$(timeout 30 openbook-audio-test --wav /data/local/tmp/openbook-aaudio-loopback.wav 2>&1 | tail -n 1)
    echo "$r"; case $r in '{'*) echo "HWTEST ${r}" ;; esac
  fi
}

case ${1:-all} in
  wifi) wifi ;;
  bt) bt ;;
  audio) audio ;;
  all) audio; wifi; bt ;;
  *) echo "usage: openbook-hwtest [wifi|bt|audio|all]" >&2; exit 2 ;;
esac
exit 0
