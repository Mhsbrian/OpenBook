# Encrypted-data adaptation rehearsal

ANAL-229, 2026-10-21. This is the runtime stage following the fixed camera25
adaptation job in `googlebook-update-workflow.md`. It exercises a **known
synthetic VM**, without owner credentials, physical disks or network access.
It does not implement automatic system fallback or data-schema rollback.

## Input binding and preparation

`update-rehearse.py` accepts a completed `assembled_unqualified` job. It checks
the parent record, profile, audit, assembly and native-input evidence; rehashes
the candidate; and requires the candidate selected by the rehearsal profile.
The assembly job remains unchanged. Each rehearsal creates its own linked
record with the parent's digest, candidate identity and execution history.

The versioned profile pins the initialized synthetic disk, its software TPM,
the **matching initialized-VM manifest**, QEMU, container image and imported
recipe scripts. It also pins the observed encryption-policy fingerprint for
`/data/misc`. A fresh image's manifest cannot replace a used VM's manifest just
because the system version is the same: their disk identifiers may differ.
Preparation retains strict GPT, static-partition and boot-metadata checks.

The current synthetic fixture was produced by the camera24-to-camera25 VM
preservation rehearsal (`evidence/2026-10-20-googlebook-camera-clients/`). Its
prepared source was `9809adcd47420007e9935306b8aca71612cc72afd3e3f524dd1aa448ede68fae`;
the post-observation fixture is
`c45eba1c568f16908391532de278439d54edcfa587281bd01234b7dcfa0918e2`.
The parent adaptation candidate is
`22e93f392882e4a15f2414c3bc3a65ad2aedf89b4756b9c1cf4fbaf6a3536155`.
These are local development identities, not upstream authentication or physical
deployment approval. Unknown candidates, manifests or TPM state stop for review.

The exact transformation is applied to a private clone with `preserve-update.py`'s
internal experiment interface. Only the intended system change is allowed;
kernel/vendor/layout changes are rejected. Protected regions and unrelated EFI
files must remain unchanged during preparation. The output uses the experimental
schema, and the actual physical-write validator must reject it before boot.
No deployment pin or writer allowlist is expanded for this test.

## What the two observations establish

1. Boot the prepared clone for **760 seconds**, with a copy of the original
   software TPM. Collect new serial/persistent diagnostics, excluding old saved
   sessions. Compare the four existing metadata-encryption files before/after.
2. If the first observation completed with intact sources, decoy and encryption
   identity, copy its resulting disk and software TPM for another **760-second
   cold boot**. A recorded runtime failure remains a failure even when enough
   integrity checks pass to permit this diagnostic restart.

The existing harness stops QEMU at the end of each window without requesting an
Android shutdown. The second observation therefore exercises restart of that
guest state. This is **not interruption of a system write**, boot-slot fallback,
restoration of an old Android data schema or proof against arbitrary power loss.
No rollback is attempted.

Each observation gets a separate verdict. Requirements include observed boot
completion and enforcing policy, F2FS `/data` on a device-mapper device with
`inlinecrypt`, the same verified `/data/misc` policy, all four metadata-key files
unchanged, a complete current diagnostic capture, intact source/TPM/decoy, and
no observed kernel panic, SIGILL, fatal exception, system-server crash, zygote
restart, camera/mmd abort or AVB handoff error. A later crash overrides an earlier
boot-complete marker. Merely waiting out the observation is not a health pass.

The reader combines serial with the harness's explicit current saved-file
inventory, verifies exclusion of prior sessions, refuses unsafe/missing files
and hashes the exact bytes it reads. Saved guest logs can contain crashes absent
from serial. Each verdict records the capture inventory's hash and file count.

These checks establish bounded observations of encryption metadata and policy
continuity. They do **not** compare every app database or credential-encrypted
file, unlock an owner's PIN, exercise hardware KeyMint or qualify long-term
stability. The result explicitly records those limits. Successful VM observations
also do not establish production containment of Google's updater.

## Measured result — 2026-10-21

The known candidate completed a 760.6-second first observation and a 760.7-second
cold restart. All four metadata-key files and the data-policy fingerprint were
retained, with enforcing encrypted mounts and unchanged inputs/decoys. Both
health verdicts are **held** on RepairMode boot-receiver Java crashes: binding
the vendor serviceability service fails. The original camera25 observation has
the same exception. The missing backend was already documented; it is not waived
as harmless or attributed to the new input-library patch.

Execution is pinned to commit `f61bfc6`; broader saved-log assessment was added
afterward and applied to the same retained bytes without replacing the original
job. Future runs use that integrated reader. The final code/profile also passed
read-only validation against the original inputs in the offline container.
29 rehearsal tests and 87 existing regressions pass. See the dated evidence
directory for observations, both verdict versions, hashes, refusals and cleanup.

## Job states and storage

The independent `openbook-ruby-rehearsal-job/1` record progresses through:

`validating → preparing → boot → preparing_restart → restart → verifying → cleaning`

- `rehearsed_unqualified` / exit 0: both bounded observations passed their gates.
- `held` / exit 2: observations were collected but health/evidence gates failed;
  retained verdicts list the failures. An incomplete/changed first observation
  can stop the sequence before restart.
- `failed` / exit 2: input, preparation, execution or integrity checking failed.
  Partial output is not a successful rehearsal and is never resumed/overwritten.

No state grants release or physical-write approval. The shared Ruby track lock
serializes the run with other cooperative builds. Native subprocess groups are
owned and reaped on failure/cancellation/timeout through the existing workflow
runner. A hard host failure can leave a nonterminal record, which is not success.

Budget **64 GiB additional allocated space plus 40 GiB free reserve**, even on
reflink-capable storage. Recheck before cloning and each observation; the runner
also monitors the reserve during native work. This is not a filesystem quota.
After completed observations and input verification, scoped cleanup removes the
job's disposable disk copies, FAT extraction scratch and extracted key blobs.
Candidate/source/recovery images, original TPM state, logs, verdicts and provenance
remain. New VM TPM state and private key-comparison hashes stay private. The exact
cleanup allowlist and actual before/after free space are recorded before deletion.
Incomplete infrastructure failures retain scratch until the task has inspected
the failure and established that no process or remaining check needs it.

## Reproduction

Run from the repository with existing authorized private inputs. Each output
must be new; its parent must already exist. The pinned container must already be
available. Its launcher disables networking, drops capabilities, uses a read-only
root and passes no physical devices, KVM device or Docker socket. QEMU uses TCG,
four virtual CPUs, 8 GiB RAM, emulated audio and software TPM only.

```bash
DATA="$HOME/anybook"
bash scripts/googlebook/run-update-rehearsal.sh \
  --job "$DATA/installer/work/anal229-workflow-20261021-a1" \
  --fixture "$DATA/installer/work/anal228-ruby-run-camera25/usb-test.img" \
  --tpm "$DATA/installer/work/anal228-ruby-run-camera25/tpm-state" \
  --base-manifest "$DATA/installer/work/anal228-vm-preserved-camera25/manifest.json" \
  --qemu "$DATA/installer/work/anal228-tcg/build/qemu-system-x86_64" \
  --out "$DATA/installer/work/ruby-rehearsal-new"

python3 scripts/googlebook/update-rehearse-test.py -v
```

This remains a trusted local CLI. Do not expose its path arguments or internal
preparation worker as a remote API. The future app/service needs authentication,
fixed job identifiers, access controls and separate review requests. The existing
signed-stage verifier remains a separate approval mechanism.

Future deployment still requires qualified upstream provenance, production OTA
containment, recoverable system/data behavior, current-device evidence and the
numbered release/approval process in ANAL-232. This rehearsal does not change the
installed G14 or approved USB image.
