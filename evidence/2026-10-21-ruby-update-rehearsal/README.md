# Ruby encrypted-data adaptation rehearsal

ANAL-229, 2026-10-21. Private synthetic VM observations; no owner data, physical
write, release approval, new Google OTA or automatic rollback.

## Inputs and execution identity

The parent adaptation job is the completed camera25 replay documented in
`../2026-10-21-ruby-update-workflow/`. Its candidate remains
`22e93f392882e4a15f2414c3bc3a65ad2aedf89b4756b9c1cf4fbaf6a3536155`.
The rehearsal applied that exact transform to the retained initialized synthetic
camera25 disk `c45eba1c568f16908391532de278439d54edcfa587281bd01234b7dcfa0918e2`,
using a copy of its software TPM state. The matching manifest is from the
camera24-to-camera25 VM preservation job, not the physical configured stick.

The VM execution used commit `f61bfc6cc4e37a1af5fe8741d8860d28174d8747` and script SHA-256
`6e45bfb8227fc6c91e9bb9528bddbec490d2a8e726fdd611d165c03e605c9e3a`.
The job's immutable profile and parent-record hashes identify the exact inputs.
`execution-profile.json` preserves the profile used. The current source profile
also pins the subsequently added saved-capture reader.
The existing physical writer rejected the experimental prepared image schema.

## Outcome

| Observation | Window | Encrypted mount, four key files and policy | Health |
|---|---:|---|---|
| First boot | 760.6 s | Pass | Held: two RepairMode Java crash events |
| Cold restart | 760.7 s | Pass | Held: two RepairMode Java crash events |

The whole job completed in 1,671.5 seconds with exit 2 / `held`. The source
images, source software TPM and synthetic internal decoys were unchanged.
Both complete current captures excluded the prior saved sessions (five, then
six). No system-server fatal signal, zygote restart, SIGILL or kernel panic was
recorded in these initialized observations. This does not resolve earlier fresh
image failures. `execution-job.json` preserves the original verdicts;
`capture-review.json` assesses the same bytes with the integrated broader reader,
reaching the same holds. `observations.json` is a sanitized harness summary;
`diagnostic-summary.json` identifies the failing process and exception.

116 Python tests pass: 29 rehearsal tests plus 87 existing workflow, readiness,
preservation, compatibility and guard-builder regressions. `tests.json` records
the suite counts. The original 22-test rehearsal log is preserved separately;
the final 29-test command result was collected in the task's tool output.
`final-input-validation.json` records successful validation of the final code
and profile against unchanged originals in the offline container, without
running more VMs. Parser controls use retained logs and are not new VM tests.

Scoped cleanup removed 15 disposable paths, verified absent afterward. Actual
free space: 744.65 GiB before execution; 739.90 before cleanup; 741.22 immediately
after (1.32 GiB observed increase); 743.64 after sync at handoff. These are
filesystem measurements, not sums of sparse-image sizes. The exact manifest is
private; `cleanup-summary.json` records its digest and measurements. Candidate,
source/recovery images, VM TPM state, logs and provenance remain.

## Failure handling and diagnostic review

`refusals.json` retains the first attempt's strict manifest/GPT refusal. It used
the fresh image's manifest, which did not describe the initialized synthetic
disk. No image was allocated or VM started. A new job used the recorded matching
synthetic manifest after its GPT, static partitions and AVB handoff were checked.
Validation was not weakened. A real concurrent invocation also stopped at the
shared track lock without creating another output directory.

The first completed observation reached boot completion, retained all four
metadata-encryption files and the `/data/misc` policy, and still failed health:
RepairMode's boot receiver crashed while binding the missing vendor
serviceability backend. The original camera25 fixture's retained observation
contains the same exception. This agrees with the integration gap documented in
`docs/googlebook-live.md`; it does not prove the failure is harmless or qualify
either image. The restart is a diagnostic continuation only.

Reviewing retained crash logs also exposed that generic fatal errors can occur
only in the saved guest capture. The dedicated system-server gate already read
the harness's combined findings, but the general fatal-error gate initially
examined serial alone. `rehearsal-capture.py` reads the harness's current-file
inventory, rejects old sessions and unsafe/missing paths, and hashes the exact
bytes read. The original observations and job are retained unchanged; broader
capture review is a separate assessment of the same recorded bytes, not a new
VM run. `retained-crash-parser-checks.json` records two old-log negative controls;
neither is counted as a new boot or data-preservation test.

Raw serial/logcat, software TPM state and key-comparison records stay private.
Only sanitized reports and selected diagnostic excerpts are published. A
successful encrypted mount plus key/policy identity does not verify every app
database, owner PIN, hardware KeyMint or data-schema rollback. The cold restart
also does not simulate interruption of an update write.
