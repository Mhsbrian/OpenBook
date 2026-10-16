# G14 images (ANAL-198)

Kleaf dist: `/home/hive/anybook/kernel/dist/anybook-g14-gbos-16302624` (6.18.21-android17-5-g44a90255c95f)

| File | Bytes | MiB | sha256 | AVB hashtree | What |
|---|---|---|---|---|---|
| `boot.img` | 26947584 | 25.7 | `b6cb77e4e783b66b44aa96ede355ff0f4b6a6725c8e7e3df250e3667a34929f9` | - | GKI boot image of the same build (kernel only) |
| `bzImage` | 26854400 | 25.6 | `d92572c9a232138d40070415f551e63d68c79720fbfa2a30caafc63e94fcaa94` | - | the kernel |
| `system_dlkm.img` | 18165760 | 17.3 | `01b64d4491ded8c6896b63065609d3c475390f9b611f014657407bc443b5e61b` | yes | erofs (Kleaf system_dlkm.flatten.erofs.img), 100 GKI modules signed by this build's key |
| `vendor_boot-ramdisk.lz4` | 126489 | 0.1 | `3c80536cc34c000f3bce81e2b9fdc94d16804548b6aee16b5a5bf5759a9bf4d6` | - | that fragment on its own (lib/modules/<release>/), for a product-built vendor_boot |
| `vendor_boot.img` | 133120 | 0.1 | `16780a93a47eb49006fdc2e7eb152508cbc99607b7b6195709d23aef20dc37bb` | - | boot image v4, vendor_boot; one DLKM ramdisk fragment "dlkm" with no modules (first stage needs none) |
| `vendor_dlkm.img` | 53403648 | 50.9 | `f6f57b04090361c8b21b610770941e182a5672f951c7c7e197a6c6d0bcdd39f4` | yes | erofs, unsigned hashtree footer; 138 vendor modules, Android layout |
| `vm/vendor_boot-ramdisk.lz4` | 310291 | 0.3 | `4b1861848a68b606bba8327f7e018f37d3cad15789c6aab1c8dd109cad7c4e17` | - | the VM fragment on its own |
| `vm/vendor_boot.img` | 317440 | 0.3 | `c8ef109a16f3d84ebf18e17aa1e3c8d8700fec5b659e9fb08ad83830a147624a` | - | the same for VMs; the fragment holds 7 virtio modules |
| `vm/vendor_dlkm.img` | 53403648 | 50.9 | `6e082622c1823253d100a40844231535b087ddf782a6459690f2161714b8c6f0` | yes | the same 138 modules; VM modules.load (no virtio, in first stage) and blocklist (asus-nb-wmi) |
