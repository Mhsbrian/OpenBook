# G14 images (ANAL-198)

Kleaf dist: `/home/hive/anybook/kernel/dist/anybook-g14-gbos-16302624-anal239` (6.18.21-android17-5-g206eb00bd0c4)

| File | Bytes | MiB | sha256 | AVB hashtree | What |
|---|---|---|---|---|---|
| `boot.img` | 26951680 | 25.7 | `437c45a3971d5f1a3e962676dd019833a24729d9320bff9b25b106fd9d1f2920` | - | GKI boot image of the same build (kernel only) |
| `bzImage` | 26858496 | 25.6 | `7070b69fae0ddfbdf20e1238ced6eed699ea7737c8e0733b5d6f4ce71efd49b6` | - | the kernel |
| `system_dlkm.img` | 18165760 | 17.3 | `add3260a0cda38fabdd4d9d913e80f014b8163ce75ee4af669ff2776af1109fa` | yes | erofs (Kleaf system_dlkm.flatten.erofs.img), 100 GKI modules signed by this build's key |
| `vendor_boot-ramdisk.lz4` | 126705 | 0.1 | `38c4bfa1c093ddde642d3dd4d8c9e958d72b85c81e893dab71175d07a179adf6` | - | that fragment on its own (lib/modules/<release>/), for a product-built vendor_boot |
| `vendor_boot.img` | 133120 | 0.1 | `b499ebf164191767760e9ad8034529e0afa11d12592d164b74ffa777153b7b2e` | - | boot image v4, vendor_boot; one DLKM ramdisk fragment "dlkm" with no modules (first stage needs none) |
| `vendor_dlkm.img` | 60391424 | 57.6 | `99eb64e7f58d3f68ad5bdef2655d74f5ec6f96bc94f6aeec50dad62ece4e9d37` | yes | erofs, unsigned hashtree footer; the vendor modules, Android layout |
| `vm/vendor_boot-ramdisk.lz4` | 310510 | 0.3 | `9b5b63f43d07eec39f20c0b3c1cfd15ba902a6b1d21018a00b1f061a0ec1df46` | - | the VM fragment on its own |
| `vm/vendor_boot.img` | 317440 | 0.3 | `33f12ff4b1803e4fa377cbb6a905ce26fc1e0bfd839830042e9558c5979a4425` | - | the same for VMs; the fragment holds 7 virtio modules |
| `vm/vendor_dlkm.img` | 60391424 | 57.6 | `71249b48cb618f71f0bbec2265b8321b2b627b6b8e91711dff7623bacc2543ed` | yes | the same vendor modules; VM modules.load (no virtio, in first stage) and blocklist (asus-nb-wmi) |
