# Cuttlefish module set: mode `anybook`

Kernel release `6.18.21-android17-5-g44a90255c95f`. Sources: `anybook-amd-gbos-16302624` (bzImage, GKI modules, AnyBook vendor modules) and `anybook-vdev-gbos-16302624` (Cuttlefish board modules).

| source | modules | vendor_ramdisk | vendor_dlkm | system_dlkm | excluded |
|---|---|---|---|---|---|
| gki | 100 | 8 | 0 | 92 | 0 |
| board | 45 | 5 | 22 | 0 | 18 |
| anybook | 138 | 5 | 133 | 0 | 0 |

265 modules in the initramfs; `modules.load` lists all of them. Blocklisted (shipped, not loaded at boot by `dlkm_loader`): snd-aloop.ko, vivid.ko, vkms.ko.

GKI modules missing from the board build's initramfs: none.

## Excluded

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
