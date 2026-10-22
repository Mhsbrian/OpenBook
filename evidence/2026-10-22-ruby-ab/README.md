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

## OpenBook-signed Virtual A/B OTA payload (`build-ruby-ab-ota.py`)

- `ab-ota-payload.json`: a full update_engine payload for a release — the dynamic partition `system`
  (Virtual A/B) plus the static boot chain (`boot`, `init_boot`, `vendor_boot`, `vbmeta`, the
  boot-covering vbmeta). Built with `delta_generator` and signed with the OpenBook OTA key through
  the host-only `sign-ota-payload.sh` (the key never enters a container). 892 MB. Read back
  independently: CrAU v2, all five partitions in the manifest, the metadata signature **verifies
  against the installed OpenBook certificate**, and `payload_properties` match the bytes. This is
  the update that installs into slot B; the in-VM apply + reboot-switch + fallback is the next step.
  `build-ruby-ab-ota-test.py` covers the read-back checks (5).

## OTA apply into slot B through the stock update_engine (`ab-ota-qemu.py`)

`ab-ota-apply-inprogress.json`: a disposable A/B apply-test disk (the certificate candidate plus a
one-shot apply driver) booted with the signed payload on a second drive. The stock update_engine
accepted the OpenBook-signed payload and applied it into slot B: the device reports the OpenBook
`otacerts` (`3e1529c9…`), the metadata signature verified (0 mismatches), and update_engine wrote
171/610 operations (293 MB) into the `system_b` snapshot with 0 errors before the run was stopped —
the full write is slow under TCG emulation, not a correctness limit. Reaching 100% plus the
`bootsync activate b` / reboot-into-B / broken-slot fallback needs a KVM-speed or multi-hour run.
The payload-delivery path to the NIC-less VM was resolved step by step (driver domain, context=
mount permission set, a pinned nvme slot, a world-readable payload, newline-separated headers).
