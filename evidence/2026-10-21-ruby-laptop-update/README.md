# Laptop update/restore from the Ruby USB — 2026-10-21 (ANAL-229)

Sanitized results only. Raw ADB captures, disk images, USB backups, serial logs
and TPM state stay private under the local data root. No physical USB or laptop
byte was written by this work.

## G14 (read-only, `g14-capture.json`)

Paired wireless ADB as the shell user, using `capture-adb.py`'s ordinary and
update-exposure command sets (no root, settings change, reboot or log clearing).

- Installed system: **camera25** on the internal NVMe. The live
  `ro.boot.vbmeta.digest` matches the retained camera25 boot entries, and
  `ro.boot.openbook.ruby_installed=1`. Partitions are single-slot (`_a` only).
- Update exposure: `ro.build.ab_update`, Virtual A/B and compression are true,
  `update_engine` is running, GMS's `SystemUpdateActivity` is enabled and
  `ota_disable_automatic_update` is unset. No system update is registered
  (`system-update-info.xml` absent) and no recovery reboot is pending. This is
  an observation at one moment, not containment.
- Health in the first minutes after boot: RepairMode's boot receiver crashed
  twice (once per user) on `VendorServiceabilityService` binding, matching the
  VM finding. One third-party app crashed. Dropbox has no `system_server_crash`
  among 83 retained entries; no ANR since boot.
- Storage: `/data` 7.9 GB, about 0.4 GB free (95-96 %).

## SanDisk RB01 v2 stick (read-only, `stick-check.json`)

GPT, `misc`, `boot_a`, `init_boot_a`, `vendor_boot_a`, `vbmeta_a` and `super`
are byte-identical to the written RB01 v2 image. `metadata`, `userdata` and the
ESP's `loader/random-seed` changed: Android booted from the stick once after the
write and recorded `shutdown,userrequested` at 07:56 EDT. There are no new saved
log sessions, so this does not show PIN/app/trackpad results.

## Synthetic QEMU rehearsal (`rehearsal.json`)

Synthetic configured camera25 data and its software TPM were installed onto a
64 GiB synthetic NVMe with the migration code the G14 used. The USB was the
synthetic RB01 image (same system bytes as the stick) with the update-capable
installer packaged by `migration-package.py`. The serial driver typed the disk
choice and exact phrase. KVM was used for the installer environment and TCG for
Ruby Android.

| Run / installer initrd | Phase | Result |
|---|---|---|
| run1 `f50e3a6a…` | wrong confirmation | pass: nothing written to the laptop, USB partitions or decoy |
| run1 | update | **stopped before any write**: the identity recheck reopened the exclusively held disk (EBUSY). Fixed. |
| run2 `161ce0a3…` | cancel at confirmation | pass |
| run2 | update | pass: only `EFI`, `super` and `vbmeta_a` changed; GPT, boot, `metadata` and `userdata` unchanged; rollback `updated` |
| run2 | Android after update | pass: boot completed; dm-verity roots for all six logical images equal the new vbmeta (system `b431bd41…`); NVMe storage; 4 key files unchanged |
| run2 | restore | pass: `EFI`, `super`, `vbmeta_a` byte-identical to the original laptop |
| run2 | Android after restore | pass: camera25 system root `2041c1ed…`, on data the newer system had used; 4 key files unchanged |
| run3 `b645eb45…` (final) | update, restore, repeat restore (no-op), cancel | pass |

The first after-update evaluation required the ESP UUID and vbmeta digest to be
printed in the serial log, which this firmware path does not do. The same capture
was re-evaluated against the guest's dm-verity tables and NVMe storage lines; both
results are kept. The Android observations show the known VM system-server
`SEGV_ACCERR`, an execmem denial and one zygote exit. Run3's installer differs from
run2's only in one restore-screen sentence, so the Android boots were not repeated.
No physical interruption, PIN unlock or G14 hardware was tested.

## Real stick candidate (`prepared-stick.json`)

A new backup of the stick's 12,766,412,800-byte used extent was read twice
directly (both `b362347c…`). The update-capable installer bound to the stick's own
pin (`013afc61…`) replaced the old installer in a private clone, with all
8,805,941,248 protected bytes unchanged. The initrd's `laptop-update.py`,
`migrate.py`, `init`, `source.json` and `laptop-update.json` were extracted and
match the repository and the reviewed record. A no-VM image test of that exact
pin and record updated and restored a camera25-installed test disk.

Tests: `tests.json` (178 passed).
