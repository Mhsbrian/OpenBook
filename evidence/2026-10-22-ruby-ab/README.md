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
