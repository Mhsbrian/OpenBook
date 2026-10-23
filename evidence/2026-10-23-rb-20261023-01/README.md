# RB-20261023-01: two-slot fresh install, written to the stick (ANAL-254, 2026-10-23)

**What:** RB-20261022-01 plus the owner OTA policy (candidate R `3999a99d…`), with the stick entry
**Fresh install Googlebook to SSD (two slots) - ERASE SSD DATA**. Approved by B Honey on ANAL-229
(`01a16647…`: "I approved, update the stick").

| Step | Result |
|---|---|
| Fresh backup of the SanDisk ending 2034 | two direct reads equal, `fddc4345…`; compared with the last write `8834cd89…`, only EFI, metadata and userdata differ (live session) |
| Recompose (tools `4b5d9ef`) | stage A system `745e8b10…`; pin `01f86961…` (`RB-20261023-01-usb`); plan `ab-install.json` (same 36 writes and bundle as the rehearsed development build); proof identical |
| Final image | `6f555e19b854198229400d3263a11214e8ccd157bb9166df42d02baff37bae11` |
| Rehearsal on the final image | QEMU typed through the two-slot entry; 1 TB NVMe installed in 76 s, identical to the reference over 27.7 GB; the installed disk booted 9/9 (`rehearsal-*.json`) |
| Physical preflight | the stick still equals the backup |
| Write (`physical-write.json`) | 01:30:40–01:39:26 UTC; super, vbmeta_a and EFI; readback `6f555e19…` as composed; 8,805,941,248 protected bytes unchanged; powered off |

The laptop has not been touched. Nothing is installed on it until the owner boots the stick and runs the two-slot entry.
