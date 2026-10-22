# Ruby A/B building blocks (ANAL-229), 2026-10-22

- `ab-super.json`: `build-ruby-ab-super.py` built a 12 GiB Virtual A/B `super` from our six
  slot-A logical images, with the geometry (VAB flag, 3 metadata slots, group
  `google_dynamic_partitions_a/_b`, group max) read from the pristine Googlebook Ruby `super`.
  Verified: VAB flag set, 3 slots, both groups, slot B an empty group, and slot A unpacked
  byte-for-byte identical to the inputs.
- `vbmeta-coverage.json`: corrects an earlier finding. The pristine Googlebook `vbmeta_a` covers
  the full boot chain (boot/init_boot/vendor_boot/pvmfw + the six partitions). Our research
  reassembler's vbmeta covers only the six super partitions, which is why an earlier check (on the
  research re-pack) suggested Ruby omits boot coverage. The A/B build rebuilds vbmeta the
  Googlebook way, so the existing `openbook-bootsync` works unchanged.

No device or laptop data is involved. The built super stays in the private work dir.

## Assembled A/B disk and first VM boot (`build-ruby-ab-image.py`, `ab-qemu.py`)

- `ab-image.json`: a 32 GiB VM disk assembled from the RB-20261022-01 candidate: the two-slot GPT
  (13 partitions), the A/B super, slot A's boot images, `vbmeta_a` rebuilt to cover the boot chain
  (boot/init_boot/vendor_boot + the six super partitions, AOSP test key), and the ESP with
  systemd-boot and slot A in openbook-bootsync's layout. Slot B, misc, metadata, userdata blank.
- `ab-image-bootsync-status.json`: openbook-bootsync's own `status` on the built disk — slot A
  `images_ok` (signed vbmeta, boot-chain hashes verified), `esp_files: in_sync` byte-for-byte,
  entry `good`, next boot slot A; slot B blank.
- `ab-vm-boot.json`: the disk booted in QEMU (TCG, NVMe, software TPM, no NIC) — all 9 checks pass:
  boot completed on slot A; the A/B boot HAL sees 2 slots and marked slot A successful (the
  markBootSuccessful → bootsync mark-good path); bootsync still in_sync with a good entry; Android
  formatted userdata at its full planned size (19,624 MB on this disk; ~919 GiB on the 1 TB SSD) and
  mounted it through metadata encryption; metadata formatted; no AVB errors. 0 system_server crashes,
  0 zygote restarts. No SELinux denials from bootsync, the boot HAL or the ESP device.
