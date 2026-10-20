# Reproduce the local update prototype

The native backend and VM implementation added after this staging prototype is
documented in `googlebook-ota-guard.md`. Use that guide for guarded-daemon builds,
Binder/cleanup tests and AVB boot-parameter checks.

Read `googlebook-updates.md` first. These tools do not install an update,
authenticate a Google signing key, or declare the current G14 safe unattended.
Only scripts, profiles and sanitized evidence belong in Git. Images, extracted
APKs, user data, raw diagnostics, keys and TPM state stay local.

## Inventory and runtime capture

Use retained extraction directories from `gbos-unpack.sh` and `compat-audit.py`.
The extraction itself must be tied to a reviewed original; file inventory alone
cannot prove that relationship.

```sh
python3 scripts/installer/recovery-preflight.py --raw "$ORIGINAL_RAW"
python3 scripts/googlebook/update-inventory.py \
  --ruby "$RUBY" --vendor "$CAMERA25_PROBE/vendor" \
  --apex "$CAMERA25_AUDIT/ruby-apex" \
  --live-manifest "$CAMERA25_LIVE/manifest.json" \
  --aapt2 "$ANDROID_BUILD_TOOLS/aapt2" --out "$NEW_INVENTORY"

python3 scripts/googlebook/capture-adb.py \
  --adb "$ADB" --server-port 5222 --serial "$PAIRED_IPV4_PORT" \
  --updates-only --phase ordinary --out "$NEW_PRIVATE_CAPTURE"
```

Capture output is private and includes package/job/log data. Failures and denied
commands remain explicit, even if other commands succeed. Phase names
`idle-charging`, `after-reboot` and `recovery` merely label observations.
The collector never initiates an update, changes settings or reboots.

## Versioned profile and signed review

`config/image-bases/ruby-update-camera25.json` identifies an observed baseline.
It is research-only and has no signed review. Its original digest names the
**raw** recovery, not the enclosing ZIP. Do not treat its source URL as a
signature. New builds need a new profile, exact hashes and independent review.

`update-stage.py` implements a small approval gate and private staging store.
It does **not** run the assembler or turn a passing JSON field into measured
compatibility. The reviewer signs an attestation that named reports have been
reviewed for this exact tuple. The actual native audit remains
`compat-audit.py`; boot, hardware, signing and data evidence require their own
tools. A fresh real stock-update validator is still needed.

The profile contains:

- `schema: openbook-ruby-update-profile/1`, build, target and `local_only: true`;
- original kind `full-recovery`, source URL and SHA-256;
- a nonempty map of flat artifact filenames to SHA-256;
- `hardware_eligible: false` until a separately reviewed profile permits trial.

Put candidate files and report files in a private directory. Name every artifact
needed for the intended transaction, including boot/kernel/modules, super,
vbmeta, firmware/profile metadata and the regenerated installer pin. The
camera25 profile is a baseline inventory, not a complete future transaction.

The review has this shape (placeholders below are not usable approvals):

```json
{
  "schema": "openbook-ruby-update-review/1",
  "stage": "rehearsal",
  "expires_utc": "REQUIRED_RFC3339_EXPIRY",
  "profile_sha256": "SHA256_OF_EXACT_PROFILE_BYTES",
  "tuple_sha256": "COMPUTED_TUPLE_SHA256",
  "checks": {
    "vintf": {
      "passed": true,
      "report": "vintf-report.json",
      "sha256": "SHA256_OF_REVIEWED_REPORT",
      "tuple_sha256": "COMPUTED_TUPLE_SHA256"
    }
  }
}
```

Tuple hashing uses SHA-256 of UTF-8 JSON with sorted keys, compact separators
and the four profile fields `original`, `artifacts`, `target`, `build`; use
`update-stage.py`'s `canonical()` function. The profile hash covers all profile
bytes, including layout notes or other review metadata.

Rehearsal requires `license`, `provenance`, `signatures`, `rollback_indexes`,
`vintf`, `selinux`, `kernel_modules`, `firmware_graphics`, `layout` and
`installer_pin` reports. Trial additionally requires `encrypted_data`,
`boot_health`, `failure_recovery`, `containment`, `data_rollback` and an eligible
profile. Promotion adds `hardware` and `owner_acceptance`. Every report is
hashed and bound to the tuple; missing/false/stale evidence rejects the stage.
Use distinct approvals for each stage.

Sign exact review bytes with an independently managed RSA review key:

```sh
openssl dgst -sha256 -sign "$PRIVATE_REVIEW_KEY" \
  -out "$REVIEW_SIGNATURE" "$REVIEW_JSON"
python3 scripts/googlebook/update-stage.py \
  --original "$ORIGINAL_RAW" --candidate "$PRIVATE_CANDIDATE" \
  --profile "$PROFILE" --review "$REVIEW_JSON" \
  --signature "$REVIEW_SIGNATURE" --trusted-key "$INDEPENDENT_TRUSTED_PUBLIC_KEY" \
  --stage rehearsal --out "$NEW_PRIVATE_STAGE"
```

The public key must come from the local trust configuration, not the artifact
being checked. The output includes a key copy for audit only. Unknown input,
changed artifact/evidence, bad signature, expired approval, changed profile,
path traversal, symlinks, device files and insufficient space are refused.
An interrupted copy leaves a `.partial-*` directory; it never publishes the
completed stage. The prototype restarts into a fresh directory; it does not
implement resumable transport, remote authentication, hardware writes or a
multi-user privileged service. Files are read-only by mode and hash-checked,
not filesystem-immutable against their owner. The host/work directories must
be private and have no concurrent untrusted writers.

## Disposable update-engine suppression experiment

Use the unchanged camera25 native audit inputs with the existing
`hybrid-probe.py` command in `googlebook-live.md`, adding:

```sh
--variant bm --test-update-engine-stop --prepare-only
```

This is a **failed containment experiment, never a deployable image**. The
fresh-data VM rebooted with `Checkpoint commit failed`; an initialized-data
UEFI VM completed boot but reproduced the known system-server crash class.
The flag suppresses auto-start only, not download or arbitrary execution.
The build requires the exact
reviewed update_engine rc text and records the injected fragment digest.
`secilc` still checks neverallow rules. No package or policy permission changes.

Boot with `run-probe.py` and the reviewed ISA-compatible QEMU executable.
For a persisted-data rehearsal, package with `live-image.py`, then run
`preserve-update.py` against a stopped **disposable VM's** used disk and its
matching base manifest. Boot the prepared image using:

```sh
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/run-probe.py" \
  --input "$PRIVATE_PREPARED_VM" --out "$NEW_VM_RUN" \
  --qemu "$RUBY_QEMU" --accel tcg --uefi-usb --usb-logs \
  --tpm --tpm-state-from "$PREVIOUS_VM/tpm-state" --timeout 480
```

The runner has no NIC or physical disks and reaps QEMU/swtpm before returning.
Review engine properties, both service registrations, init actions and crashes;
a zero runner exit is observation completion, not an update pass.
Check metadata-encryption key-file digests before/after with the existing
`migration-qemu.py:metadata_key_hashes` helper, retaining only a boolean/count in
shareable evidence. Do not boot owner data in this disposable environment.

To test reversal, prepare another private clone using the original reviewed
camera25 candidate, then boot with the matching disposable TPM state. Removing
the init fragment restores auto-start in the recorded 480.7-second reversal
run: process and both interfaces return, boot completes, and the same
system-server crash class recurs. All four pre-existing metadata-encryption
files match across both trials. Verify those properties for every new tuple;
this is not a newer-schema rollback test.
No physical containment/reversal is authorized by these experiment instructions.

## Offline installer replacement

Generate a new `source.json` after **any** static system or boot payload change,
then rebuild the offline installer so its embedded pin matches. Do not edit the
old source pin merely to make changed inputs pass.

The packager remains addition-only by default. For an existing installer, first
review its original `ruby-installer/build.json`, retain its SHA-256 independently,
and pass that digest with the new installer:

```sh
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/migration-package.py" add \
  --snapshot "$FRESH_VERIFIED_BACKUP" --snapshot-sha256 "$BACKUP_SHA256" \
  --base-manifest "$CURRENT_BASE/manifest.json" \
  --installer "$NEW_REBUILT_INSTALLER" --out "$NEW_PREPARED_CLONE" \
  --replace-installer-sha256 "$REVIEWED_PREVIOUS_INSTALLER_BUILD_JSON_SHA256"
```

Replacement permits only four known installer files and two exact menu entries.
It checks old file hashes, rejects unfamiliar/missing files or menu drift,
checks all new artifacts, preserves unrelated EFI content and every non-EFI
partition, and emits the existing guarded preserving-update plan. It remains a
single-slot, non-atomic physical write if later applied. This command itself
accepts only regular files; no physical apply is authorized by this document.

## Tests

```sh
python3 scripts/googlebook/update-test.py -v
python3 scripts/googlebook/capture-adb-test.py -v
python3 scripts/googlebook/preserve-update-test.py -v
python3 scripts/googlebook/live-test.py -v
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/migration-package-test.py" -v
scripts/installer/inst-docker.sh python3 "$REPO/scripts/googlebook/migration-test.py" -v
```

The signed positive fixture is synthetic. Its approval is not a signature for
any Google/AMD image. Injected host-copy failure tests neither FAT power-loss
behavior nor a functioning A/B bootloader. See the decision record for the
unimplemented physical recovery and newer-schema rollback matrix.
