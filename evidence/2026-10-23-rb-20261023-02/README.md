# RB-20261023-02: Google 16658739 patched for the G14, written to the stick (ANAL-255, 2026-10-23)

Fixes the setup block on a fresh install (ANAL-254): Google's setup requires the current Google build,
and Google's own package is refused by the OpenBook certificate. Requested by B Honey on ANAL-229
(`01a1667e…`: "Can you just redo the USB with the newest patched OS?").

| Step | Result |
|---|---|
| Rebase (`rebase-google-build.py`, `rebase-result.json`, `rebase-delta.json`) | candidate R → Google 16658739: `system` = Google's new tree + OpenBook's exact delta (28 added, 370 removed, 53 changed; `build.prop` three-way merged), `system_ext`/`product` verbatim; rebuilt `system` matched its expected inventory; candidate `75fa0196…` |
| VM boot on two slots (`vm-boot-two-slot.json`) | 9/9; setup welcome reached; no system_server fatal signals; runtime fingerprint CL3B.260622.276.R4/16658739; Digitalis native-bridge action ran |
| Stick plan (`ab-install*.json`) | pin `6f3245ac…`; 36 writes; proof identical to the reference |
| Rehearsal (`rehearsal-*.json`) | QEMU typed through the two-slot entry; 1 TB NVMe installed in 85 s, identical to the reference; installed disk booted 9/9 |
| Fresh backup | two reads equal, `d995319b…`; compared with the last write `6f555e19…`, only EFI (random seed) and metadata differ |
| Write (`physical-write.json`) | super, vbmeta_a, EFI; readback `bfb8e276…` as composed; protected bytes unchanged; powered off |

The final image matches the rehearsed one except for the ESP's random seed, the backup identity in the
ESP record and the stick's own metadata. The pin, plan and installer are identical. The laptop has not
been touched.
