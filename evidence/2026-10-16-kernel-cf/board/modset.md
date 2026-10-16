# Cuttlefish module set: mode `board`

Kernel release `6.18.21-android17-5-g44a90255c95f`. Sources: `anybook-amd-gbos-16302624` (bzImage, GKI modules, AnyBook vendor modules) and `anybook-vdev-gbos-16302624` (Cuttlefish board modules).

| source | modules | vendor_ramdisk | vendor_dlkm | system_dlkm | excluded |
|---|---|---|---|---|---|
| gki | 100 | 8 | 0 | 92 | 0 |
| board | 45 | 11 | 34 | 0 | 0 |

145 modules in the initramfs; `modules.load` lists all of them. Blocklisted (shipped, not loaded at boot by `dlkm_loader`): snd-aloop.ko, vivid.ko, vkms.ko.

GKI modules missing from the board build's initramfs: none.

