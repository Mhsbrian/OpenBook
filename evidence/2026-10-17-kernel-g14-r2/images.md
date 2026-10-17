# G14 images (ANAL-198)

Kleaf dist: `/home/hive/anybook/kernel/dist/anybook-g14-gbos-16302624` (6.18.21-android17-5-gfbfdd65b0fd1)

| File | Bytes | MiB | sha256 | AVB hashtree | What |
|---|---|---|---|---|---|
| `boot.img` | 26951680 | 25.7 | `10ee14093c6b9a94ae59effd872835a6c67afe3244210ebb3d227df69fc631a3` | - | GKI boot image of the same build (kernel only) |
| `bzImage` | 26858496 | 25.6 | `55b86074614a94592ddecebd2b77b1f2ed9aa38e8ad992b73c78c64d04c516f9` | - | the kernel |
| `system_dlkm.img` | 18165760 | 17.3 | `34185c35cb8bbccd5dfd0bb74eecb8a21e2445730411ef1583e1245628e0d617` | yes | erofs (Kleaf system_dlkm.flatten.erofs.img), 100 GKI modules signed by this build's key |
| `vendor_boot-ramdisk.lz4` | 126543 | 0.1 | `7007f46433a1308293dff52e10ec71626f9892040ed31f4aaa88065244c88f78` | - | that fragment on its own (lib/modules/<release>/), for a product-built vendor_boot |
| `vendor_boot.img` | 133120 | 0.1 | `5ff49fd3a5f453a68e3c3f0cac25094eb8fa67f330ece7b01bc663c9b321c116` | - | boot image v4, vendor_boot; one DLKM ramdisk fragment "dlkm" with no modules (first stage needs none) |
| `vendor_dlkm.img` | 53424128 | 50.9 | `024774373cb9c09c634140ef9504bd5d9d81a9ee2006d5c4c3183a596ee0ce63` | yes | erofs, unsigned hashtree footer; the vendor modules, Android layout |
| `vm/vendor_boot-ramdisk.lz4` | 310299 | 0.3 | `ebda92b42e056acc5f4fa2acf4640fde0a936440948e89be7930f64c68cc98d9` | - | the VM fragment on its own |
| `vm/vendor_boot.img` | 317440 | 0.3 | `b7bd8932d89b9f1fd6d7c5628ca4ab3cef0252a0466e242bd450df02729ae87e` | - | the same for VMs; the fragment holds 7 virtio modules |
| `vm/vendor_dlkm.img` | 53424128 | 50.9 | `14427e5f27accbe78d3bd68365b5365cab91f8f4a7031e09d16ef5062d709521` | yes | the same vendor modules; VM modules.load (no virtio, in first stage) and blocklist (asus-nb-wmi) |
