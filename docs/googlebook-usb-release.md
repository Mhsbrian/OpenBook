# Configured Ruby USB release packaging

Reviewed 2026-10-20 for ANAL-233, with source work under ANAL-228/229.
This path retains the existing disk layout, Android data, encryption metadata,
boot identity, logs and menu default. It does not update the laptop.

The ordinary `preserve-update.py` path still rejects framework changes.
`--reviewed-release RB-20261020-01` recognizes only three exact camera25
baseline manifests (configured migration26-v7, pristine synthetic, and the
previous encrypted synthetic rehearsal) and the exact corrected RB01 input
manifest. The full image, static partitions, initrd bodies and GPT are then
checked independently. Only the reviewed eight-byte input-library patch and
AVB size 4352 → 4032 correction are accepted. No vendor, kernel, module,
encryption or enforcement changes are admitted by this profile.

Preparation has three stages, all on regular private files:

1. Run `preserve-update.py` with the fresh verified backup, its SHA-256, the
   matching baseline manifest, the pinned RB01 input directory and a new output
   directory. The release profile deliberately produces `complete: false`;
   the physical writer refuses this intermediate state.
2. Run `migration-package.py pin` on that stage and build the offline installer
   using the retained, hash-identified RB01 installer container. Android boot
   payloads are pinned; installer menus are excluded because they are replaced
   with the installer. Run `add`, supplying `--replace-installer-sha256` for an
   existing installer. Replacement checks its build record and every old file,
   rejects unknown files, preserves unrelated EFI content, and validates the
   final image against the new source pin.
3. Run `finalize-usb-release.py` with the system stage, packaged directory,
   original backup and rebuilt installer. It checks the stage chain and all
   protected ranges against the original backup. Only then does the final
   `update.json` become usable by `apply-preserved-update.py`.

Run the transition/preservation/migration tests and a synthetic encrypted-data
UEFI rehearsal with its matching software TPM. Never boot owner data with a
synthetic TPM. Compare synthetic metadata-key hashes before and after. The
actual configured image receives complete byte-preservation and installer-pin
checks; physical unlock and trackpad behavior require the G14.

The authorized physical operation uses `apply-preserved-update.py`: an exact
whole-USB by-id confirmation, unmounted-device checks, another independent
direct read against the backup, only super/vbmeta/EFI writes, then full direct
readback and power-off. No internal disk enters that container. This is a
single-slot update, not power-loss atomic. Keep the original private backup
and its hashes. If writing fails, do not boot the stick: verify the protected
ranges, restore those same three partition ranges from the backup on that
same confirmed USB, and verify the entire used extent against the backup.
The range-restoration test simulates a partial system write and checks recovery
without changing surrounding bytes; it does not claim automatic rollback.

Budget additional *allocated* space per phase with at least 40 GiB free beyond
that budget. Use reflinks only after verifying support, retain candidates,
backups and evidence, and remove only explicitly listed completed scratch.

Known runtime limitation: earlier VM observations contain system-server
SIGSEGVs and execmem denials. They do not establish a cause or prove a Radeon
hardware failure. Do not weaken SELinux to obtain a passing test. Report each
new observation separately; preservation checks are not stability acceptance.

Primary references checked 2026-10-20:
[AOSP AVB](https://source.android.com/docs/security/features/verifiedboot/avb)
describes the signed partition metadata;
[AOSP metadata encryption](https://source.android.com/docs/security/features/encryption/metadata)
describes the separate key metadata and boot requirements. This narrowly
pinned update retains those encryption inputs; it does not qualify a new base.

## Qualified run

The configured SanDisk write and full direct readback completed under B Honey’s
recorded approval. See `evidence/2026-10-20-rb01-usb/README.md` for the exact
qualification, reused installer regression evidence and remaining hardware limits.
