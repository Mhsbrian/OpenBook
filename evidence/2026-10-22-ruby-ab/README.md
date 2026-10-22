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

## Milestone 3 complete: OTA into slot B, reboot into it, automatic fallback (2026-10-22, later)

Supersedes `ab-ota-apply-inprogress.json` and corrects `ab-ota-payload.json`: that earlier full
payload listed only `system` as a dynamic partition. update_engine rebuilds the target slot's
partition table from exactly the payload's list (`UpdatePartitionMetadata`), so slot B would have
had no vendor/product/system_ext/module partitions and could not have booted. The payload now
carries all six dynamic partitions plus the boot chain.

- `ab-ota-delta-payload.json`: a complete **incremental** update (all 10 partitions) computed
  against the installed slot A, signed with the OpenBook key: 2.66 MB instead of 892 MB, because
  unchanged blocks become source copies. Its signature verifies against the installed certificate.
- `ab-ota-apply.json` — **11/11**: the stock update_engine applied it on the A/B disk (TCG); the
  on-device payload hash matched; libsnapshot reached `Unverified` (all writes and verification
  done); update_engine called setActiveBootSlot, and bootsync verified slot B's images, exported
  them and staged `openbook-b+3.conf` as preferred; slot B's four static partitions equal the
  release byte for byte; the system then rebooted in order (`svc power reboot`). The first verdict
  (kept in the file) relied on console lines that the driver's console dropped; the checks now use
  on-disk state.
- `ab-ota-boot-slot-b.json` — **7/7**: the next boot started slot B, completed, and was marked
  successful (bootsync: `openbook-b+2-1.conf -> openbook-b.conf`, slot A's entry removed, B the
  default); all six snapshots merged ("Merge completed" ×6) and libsnapshot's state returned to None.
- `ab-ota-verify-slot-b-post-merge.json` — after the merge, slot B's six logical partitions (read
  through slot B's own metadata) and four boot partitions are **byte-identical to the release**.
  `...-pre-merge.json` is the negative control: before the merge `system` differs (its changes are
  still in the snapshot). COW partitions stay listed after a merge until the next update starts
  (libsnapshot `CreateUpdateSnapshots` reclaims them), so content decides.
- `ab-ota-fallback.json` — **7/7**: a post-apply copy with vbmeta_b corrupted (a bad update). Boots
  1–3 started slot B and each failed first-stage verification (`Failed to verify vbmeta digest`,
  fatal reboot); systemd-boot counted the entry down and boot 4 started **slot A by itself**, which
  completed boot; slot B's entry is retired, slot A boots next, and the update was rolled back.
- KVM is not usable for Ruby on this build host: zygote gets SIGILL because Ruby's userspace uses
  AVX-VNNI, which this Zen 4 CPU lacks (the G14's CPU has it). TCG with the VNNI/GFNI-emulating QEMU
  build stays the VM path; incremental payloads keep apply times short.
