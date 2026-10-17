# G14 module lists: check

- plan: `kernel/devices/anybook/g14/modules.tsv`, 144 rows
- dist: `/home/hive/anybook/kernel/dist/anybook-g14-gbos-16302624`

| variant | first stage | vendor_dlkm load | blocklisted |
|---|---|---|---|
| bm | 0 | 137 | 3 |
| vm | 7 | 136 | 1 |

GKI modules (system_dlkm) that second-stage vendor modules link against:

- `bluetooth`: btintel.ko, btmtk.ko, btrtl.ko, btusb.ko
- `btbcm`: btusb.ko
- `libarc4`: mac80211.ko
- `rfkill`: asus-wmi.ko, cfg80211.ko, mt7921e.ko, mt7925e.ko, rtw89_core.ko

**0 problems**.
