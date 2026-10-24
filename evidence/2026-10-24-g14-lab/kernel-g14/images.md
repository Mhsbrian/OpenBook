# G14 images (ANAL-198)

Kleaf dist: `/home/hive/anybook/kernel/dist/anybook-g14-gbos-16302624-anal257` (6.18.21-android17-5-g206eb00bd0c4)

| File | Bytes | MiB | sha256 | AVB hashtree | What |
|---|---|---|---|---|---|
| `boot.img` | 26951680 | 25.7 | `944da373d7c898305648771fdfccf152b3846afbf02512bb90387b2b54a68f79` | - | GKI boot image of the same build (kernel only) |
| `bzImage` | 26858496 | 25.6 | `d8590aee9c0469ac8b27751c78bc6e158a8c4c4b76e3ab2a487c165c39988134` | - | the kernel |
| `system_dlkm.img` | 18165760 | 17.3 | `c635f0af3b4e5b153514ee98f2fcbe148c897a8e53531360a7cfaa7a47f9d1d0` | yes | erofs (Kleaf system_dlkm.flatten.erofs.img), 100 GKI modules signed by this build's key |
| `vendor_boot-ramdisk.lz4` | 126705 | 0.1 | `38c4bfa1c093ddde642d3dd4d8c9e958d72b85c81e893dab71175d07a179adf6` | - | that fragment on its own (lib/modules/<release>/), for a product-built vendor_boot |
| `vendor_boot.img` | 133120 | 0.1 | `b499ebf164191767760e9ad8034529e0afa11d12592d164b74ffa777153b7b2e` | - | boot image v4, vendor_boot; one DLKM ramdisk fragment "dlkm" with no modules (first stage needs none) |
| `vendor_dlkm.img` | 60350464 | 57.6 | `c74c86c1299f9598cc71c96eaaf7770f2a8fae737737ffb697d49ccfed30e073` | yes | erofs, unsigned hashtree footer; the vendor modules, Android layout |
| `vm/vendor_boot-ramdisk.lz4` | 310474 | 0.3 | `10276396b8e8dd60279458f446e37f23a7c2049bc37e8786ca4aadfcde57edc6` | - | the VM fragment on its own |
| `vm/vendor_boot.img` | 317440 | 0.3 | `48f835b21efa31c659741d3d68909bd014490136111b0887c4f7267c7b256fce` | - | the same for VMs; the fragment holds 7 virtio modules |
| `vm/vendor_dlkm.img` | 60350464 | 57.6 | `7d9f9b81fc0a63e7dc56d3cf93c1e53caf35186c76202ca4d419094ebd9384fe` | yes | the same vendor modules; VM modules.load (no virtio, in first stage) and blocklist (asus-nb-wmi) |
