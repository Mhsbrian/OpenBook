#!/system/bin/sh
# SPDX-License-Identifier: Apache-2.0
# QEMU only (scripts/audio-net-qemu.sh), as root: swap the laptop's idle Wi-Fi stack for mac80211_hwsim with two
# radios, then put the second radio in its own network namespace with an access point (hostapd), a DHCP server
# and an iperf3 server. Android then sees wlan0 as its Wi-Fi interface, as on the G14.
D=${0%/*}
log() { echo "run-ap: $*"; }
unload() {  # a module and, first, everything that uses it
  for u in $(awk -v m="$1" '$1 == m && $4 != "-" { gsub(",", " ", $4); print $4 }' /proc/modules); do unload "$u"; done
  rmmod "$1" && log "rmmod $1"
}
grep -q '^cfg80211 ' /proc/modules && unload cfg80211
for m in cfg80211 mac80211; do insmod "$D/mods/$m.ko" || { log "insmod $m failed"; exit 1; }; done
insmod "$D/mods/mac80211_hwsim.ko" radios=2 || { log "insmod mac80211_hwsim failed"; exit 1; }
i=0; while [ ! -e /sys/class/net/wlan1 ] && [ $i -lt 50 ]; do sleep 0.2; i=$((i + 1)); done
log "interfaces: $(ls /sys/class/net | tr '\n' ' ')"
unshare -n sh -c "echo \$\$ > $D/ns.pid; exec sleep 100000" &
i=0; while [ ! -s "$D/ns.pid" ] && [ $i -lt 50 ]; do sleep 0.1; i=$((i + 1)); done
ns=$(cat "$D/ns.pid")
phy=$(cat /sys/class/net/wlan1/phy80211/name)
iw phy "$phy" set netns "$ns" && log "$phy (wlan1) -> netns of pid $ns"
# toybox nsenter takes no "sh -c ..." (it parses -c itself): the access point side is its own script.
cat > "$D/ap-ns.sh" <<EOS
ip link set lo up; ip link set wlan1 up; ip addr add 192.168.77.1/24 dev wlan1
LD_LIBRARY_PATH=$D/lib:/vendor/lib64 $D/hostapd -dd -t $D/hostapd.conf > $D/hostapd.log 2>&1 &
echo \$! > $D/hostapd.pid
$D/openbook-test-dhcpd wlan1 > $D/dhcpd.log 2>&1 &
iperf3 -s -D -B 192.168.77.1 --logfile $D/iperf3.log
ip addr show wlan1
EOS
nsenter -t "$ns" -n sh "$D/ap-ns.sh"
sleep 2
log "hostapd: pid $(cat $D/hostapd.pid 2>/dev/null || echo none); $(grep -E 'AP-ENABLED|AP-DISABLED|Could not|failed' $D/hostapd.log 2>/dev/null | tail -n 3 | tr '\n' ' ')"
log "dhcpd: $(head -n 1 $D/dhcpd.log 2>/dev/null)"
log "done"
