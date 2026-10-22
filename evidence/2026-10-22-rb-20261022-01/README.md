# RB-20261022-01 release plan (OpenBook OTA certificate on RB-20261021-02), 2026-10-22

`release-plan.json` records the composed release. It is not written yet.

- **Candidate `18235b45…`:** RB-20261021-02's system candidate (`5a466ee6…`) with only
  `/system/etc/security/otacerts.zip` changed, carrying the OpenBook certificate (archive
  `3e1529c9…`). Digitalis and the lid guard are retained.
- **Final USB image `39f4f1f0…`:** composed against the verified RB-20261021-02 stick image
  `233eed28…` with the frozen tools (`b75b573`) and the same installer image. The laptop record
  goes RB-20261021-01 → RB-20261022-01, `system` only. The physical writer's validator accepts
  it: `EFI`, `vbmeta_a` and `super` only, with all protected bytes unchanged.
- **VM:**
  - boot completes with SELinux enforcing, the lid guard loaded, Digitalis' init rule parsed
    and no AVB errors;
  - the certificate harness (`vm-release-cert.json`) passes 19/19;
  - the VM-only system_server crash was followed by Android's checkpoint-commit reboot, the
    same as on unchanged camera25.
- **Not tested:** G14 hardware, a real Google OTA file, app/Mainline updates after the change,
  and a synthetic-laptop rehearsal of this exact record. RB-20261021-02's rehearsal covers the
  same mechanism.

## Written to the SanDisk (2026-10-22 22:12 UTC)

`physical-write.json`: RB-20261022-01 written to the owner's SanDisk Ultra USB stick ending 2034 and
verified. The owner had run the stick's Update entry (laptop on RB-20261021-02), so a fresh two-read
backup (`83b0ff2c…`, both reads equal) differed from the last write only in EFI and metadata. The plan
was recomposed with the frozen tools `b75b573` against that backup, with the laptop record re-targeted
to RB-20261021-02 → RB-20261022-01 (`260bbf78…`, byte-identical to the prepared record; pin `435915f8…`
identical; installer initrd contents identical). Read-only physical preflight passed. The writer wrote
only super, vbmeta_a and EFI (8,805,941,248 protected bytes unchanged), read back the whole 12.77 GB
used extent: `8834cd896a59b0322b6d8aa5166b3f75144c4cc2595eaf972c02329a1c2163c7` as composed, and
powered the stick off. The laptop was not written. Its Update entry now goes RB-20261021-02 →
RB-20261022-01 (system only, data kept); Restore returns the saved system.
