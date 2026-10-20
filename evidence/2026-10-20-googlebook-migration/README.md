# Configured Googlebook migration, 2026-10-20

Scope: move the tested camera25 USB system and its existing encrypted data to
the **same G14**, using a separate offline RAM installer. No physical internal
SSD was written by the agent. Owner-reported webcam and Bluetooth acceptance is
recorded separately from instrumented tests.

## Migration checks

- Eleven synthetic integrity/failure tests pass. They cover copied state,
  relocated GPT validation, new partition GUIDs, boot identity rebinding,
  changed source/system/boot refusal, small/wrong targets, interrupted writes,
  failed readback and power checks before destructive writes.
- The final VM installer performs the real interactive disk selection and
  exact serial confirmation, copies/verifies all nine partitions and registers
  the firmware boot entry. Eight non-EFI partitions are identical before the
  first Android boot.
- The final 480-second Android observation completes; 495.0 seconds includes
  teardown and post-boot verification. Firmware uses the target ESP UUID, and
  Android selects the NVMe metadata, super and userdata partitions while the
  original USB remains attached.
- Existing metadata-encryption files remain identical after Android boot.
  Source USB, original source image, source TPM state and the decoy disk remain
  unchanged. No owner data is used in these VM tests.
- An incorrect serial confirmation cancels without changing source, target or
  decoy. The normal keyboard-console cancellation is also exercised.
- The VM and G14 RAM filesystems contain the same code/modules; only the pinned
  source description differs. `runtime-equivalence.json` records the comparison
  across 1,297 entries and the exact artifact hashes.

The keyboard console's warning text is complete in the recorded images.
Full-resolution pixel comparison confirms it remains identical after
cancellation; raw framebuffer reads also match the exported images. Small
previews were misleading, so enlarged review and pixel checks were used.
`console.json` records that distinction.

## Configured USB deployment

`physical-write.json` records the completed SanDisk update. The current USB
matched a fresh backup already verified by an independent second direct read.
The writer updated its allowed super/vbmeta/EFI set; only EFI changed in content.
All 8,805,941,248 protected bytes, every Android partition and all pre-existing
EFI files remain unchanged. The complete 12,766,412,800-byte used extent passed
direct readback as `95e30c7ae6be28494630c281b6e6b091009dbda36dc427e3c5ea08b63c0ca22b`.
Power-off succeeded and the fresh backup is retained privately.

## Results that limit qualification

This is a migration/data-retention test, **not a clean runtime-stability
qualification**. The final run reaches boot completion but records one
`system_server` SIGSEGV/SEGV_ACCERR, a zygote exit and an execmem denial. An earlier
773.8-second run records the same failure class. This resembles the already
documented Ruby VM instability; its cause is not established by the migration
test. The Android kernel and system partitions are unchanged by this installer.

Another attempt exits before boot completion after 91.7 seconds, despite passing
copy, target-device and metadata-key checks. That older harness did not retain
the QEMU exit code/events, so the reason cannot be determined from that capture.
The final harness records both and requires the full observation window.
Do not discard this failed attempt when assessing reliability.

The first two harness runs also reject an uppercase UUID emitted by OVMF
against a lowercase expected UUID. Inspection confirms the same UUID and NVMe
mounts; the final check normalizes case and additionally checks partition
symlinks and the metadata mount. Earlier failures before disk writes exposed
missing `sd_mod` and iconv conversion modules; both are included in the final
RAM filesystem.

Physical installer display/input, owner PIN unlock and existing apps/accounts/
files on the internal SSD still require the owner's acceptance. The migration
retains an 8 GiB userdata extent and leaves remaining SSD space unallocated.
There is no A/B rollback or qualified automatic Google OS updater. ANAL-229
tracks update containment and automation.

Google payloads, configured images, encryption-key blobs, TPM state and raw
owner logs remain private. Only synthetic test results, source code and
sanitized build/deployment records are published here.
