# Module load status: cf-anybook-20261016T154431Z

176 modules live after boot. Of 169 modules that first-stage init or dlkm_loader should load, **169 are live and 0 are not**.

| source | stage | expected | live |
|---|---|---|---|
| gki | vendor_ramdisk | 8 | 8 |
| board | vendor_ramdisk | 5 | 5 |
| board | vendor_dlkm | 19 | 19 |
| anybook | vendor_ramdisk | 5 | 5 |
| anybook | vendor_dlkm | 132 | 132 |

GKI modules from system_dlkm loaded as dependencies or on demand: 14 (bluetooth, btbcm, can_dev, libarc4, rfkill, rust_binder, virtio_blk, virtio_console, virtio_pci, virtio_pci_legacy_dev, virtio_pci_modern_dev, vmw_vsock_virtio_transport, zram, zsmalloc).

Blocklisted, so not loaded by dlkm_loader: vkms.ko (live: loaded explicitly), vivid.ko (not live), snd-aloop.ko (not live), asus-nb-wmi.ko (not live).

Loader summary lines:

```
[    0.948339][    T1] init: Loaded 18 kernel modules took 256 ms
[    1.320365][  T385] dlkm_loader: dlkm loader successfully initialized
[    3.206265][  T385] dlkm_loader: module load count is 154
[    3.206265] dlkm_loader: module load count is 154
```

## Not live

None.

## Blocklisted for this VM, then loaded by hand after boot

```
$ modprobe -d /vendor/lib/modules asus-nb-wmi.ko
Loading module /vendor/lib/modules/extra/anybook/hwmon.ko with args ''
Loading module /vendor/lib/modules/extra/anybook/battery.ko with args ''
Loading module /vendor/lib/modules/extra/anybook/wmi.ko with args ''
Loading module /vendor/lib/modules/extra/anybook/video.ko with args ''
Loading module /vendor/lib/modules/extra/anybook/platform_profile.ko with args ''
Loading module /vendor/lib/modules/extra/anybook/sparse-keymap.ko with args ''
Loading module /vendor/lib/modules/extra/anybook/asus-wmi.ko with args ''
Loading module /vendor/lib/modules/extra/anybook/asus-nb-wmi.ko with args ''
modprobe: Failed to insmod '/vendor/lib/modules/extra/anybook/asus-nb-wmi.ko' with args '': No such device
modprobe: LoadWithAliases was unable to load asus-nb-wmi.ko, tried: asus_nb_wmi
modprobe: Failed to load module asus-nb-wmi.ko: No such device
exit=1
```

## Left out of the image by kernel-cf-modset.py

| module | source | reason |
|---|---|---|
| btintel.ko | board | same name as the anybook module `extra/anybook/btintel.ko`, which is used instead |
| btrtl.ko | board | same name as the anybook module `extra/anybook/btrtl.ko`, which is used instead |
| btusb.ko | board | same name as the anybook module `extra/anybook/btusb.ko`, which is used instead |
| virtio-gpu.ko | board | same name as the anybook module `extra/anybook/virtio-gpu.ko`, which is used instead |
| mt76-usb.ko | board | 5 CRC mismatch(es) against mt76.ko (5), e.g. mt76_create_page_pool, mt76_has_tx_pending, mt76_queue_tx_complete |
| mt76.ko | board | same name as the anybook module `extra/anybook/mt76.ko`, which is used instead |
| mt76x0-common.ko | board | 8 CRC mismatch(es) against mt76.ko (8), e.g. ____mt76_poll_msec, __mt76_poll, mt76_eeprom_init |
| mt76x0u.ko | board | 4 CRC mismatch(es) against mt76.ko (4), e.g. ____mt76_poll_msec, __mt76_poll, mt76_alloc_device |
| mt76x02-lib.ko | board | 33 CRC mismatch(es) against mt76.ko (33), e.g. __SCT__tp_func_dev_irq, __SCT__tp_func_mac_txdone, ____mt76_poll_msec |
| mt76x02-usb.ko | board | 6 CRC mismatch(es) against mt76.ko (6), e.g. __mt76_mcu_msg_alloc, __mt76_poll, __mt76_tx_complete_skb |
| mt76x2-common.ko | board | 5 CRC mismatch(es) against mt76.ko (5), e.g. mt76_eeprom_init, mt76_eeprom_override, mt76_get_min_avg_rssi |
| mt76x2u.ko | board | 7 CRC mismatch(es) against mt76.ko (7), e.g. ____mt76_poll_msec, __mt76_poll, mt76_alloc_device |
| mac80211_hwsim.ko | board | 1 CRC mismatch(es) against mac80211.ko (1), e.g. ieee80211_alloc_hw_nm |
| virt_wifi.ko | board | 1 CRC mismatch(es) against cfg80211.ko (1), e.g. wiphy_new_nm |
| virtio_dma_buf.ko | board | same name as the anybook module `extra/anybook/virtio_dma_buf.ko`, which is used instead |
| virtio_input.ko | board | same name as the anybook module `extra/anybook/virtio_input.ko`, which is used instead |
| mac80211.ko | board | same name as the anybook module `extra/anybook/mac80211.ko`, which is used instead |
| cfg80211.ko | board | same name as the anybook module `extra/anybook/cfg80211.ko`, which is used instead |
