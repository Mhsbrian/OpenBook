# Module load status: cf-board-20261016T154654Z

57 modules live after boot. Of 50 modules that first-stage init or dlkm_loader should load, **50 are live and 0 are not**.

| source | stage | expected | live |
|---|---|---|---|
| gki | vendor_ramdisk | 8 | 8 |
| board | vendor_ramdisk | 11 | 11 |
| board | vendor_dlkm | 31 | 31 |

GKI modules from system_dlkm loaded as dependencies or on demand: 14 (bluetooth, btbcm, can_dev, libarc4, rfkill, rust_binder, virtio_blk, virtio_console, virtio_pci, virtio_pci_legacy_dev, virtio_pci_modern_dev, vmw_vsock_virtio_transport, zram, zsmalloc).

Blocklisted, so not loaded by dlkm_loader: vkms.ko (live: loaded explicitly), vivid.ko (not live), snd-aloop.ko (not live).

Loader summary lines:

```
[    1.048957][    T1] init: Loaded 19 kernel modules took 373 ms
[    1.406749][  T384] dlkm_loader: dlkm loader successfully initialized
[    2.951845][  T384] dlkm_loader: module load count is 34
```

## Not live

None.
