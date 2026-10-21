# Fixed Ruby adaptation execution — 2026-10-21

The foreground replay completed in **162.4 seconds**, exit 0, with state
`assembled_unqualified`. This is a known retained camera25 input-correction
replay on the Ryzen 7950X host, not a new upstream build, release, VM boot or
device deployment. The private image was not uploaded.

| Result | Evidence |
|---|---|
| 32 pinned file inputs plus the 415-entry audit inventory | Versioned `config/image-bases/ruby-workflow-camera25.json`, digest in `job.json`; all rechecked before/after native work |
| Ruby, OpenBook and reduced-hybrid VINTF/SELinux/service-label checks pass | `audit.json`, `audit-logs/`; 94 APEXes extracted; raw-hybrid policy fails the required negative control |
| Reassembly complete | `assembly.json`, `assembly.log.gz`; all 7,292 metadata rows identical; 3,464 files/symlinks checked; only the known eight-byte library transform; source and protected data/GPT unchanged |
| Eight real native converter/drag checks pass | `input-native.json`; expected linker-configuration warning retained; these are userspace probes, not boot qualification |
| Unknown actual input refused before audit/assembly | `unknown-input.json`; exit 2, durable validating-phase failure |
| Existing deployment gate rejects this new artifact | `deployment-refusal.json`; no installer/source pin silently changed |
| 82 Python tests pass | 23 workflow, 24 signed readiness/staging, 11 preservation, 24 compatibility cases; individual logs and `tests.json` |
| Scoped automatic cleanup completes | `cleanup.json`, sanitized relative allowlist; exact absolute manifest retained with private job |

Candidate SHA-256:
`22e93f392882e4a15f2414c3bc3a65ad2aedf89b4756b9c1cf4fbaf6a3536155`.
Its parent camera25 image is
`df793f2eed3a5c901659014c2ae368d8e5eeb3d504b514d46fc8c0c1959a7af4`.
The separate raw-recovery identity and all executable recipe/tool inputs are in
the profile. Matching them does not establish upstream trust or prove the
raw-to-derived extraction chain; the job explicitly records both as false.
The container is pinned by image ID, offline, without physical-device access.

Execution started from repository base
`2cabd8fa799d29c12d2e12e1ddd5b14173080991` plus the new workflow/profile. Native
recipe dependencies were unchanged and are individually hashed. The executed
workflow hash is recorded in `job.json`. Subsequent review added argument-level
`..` rejection; that change is covered by the final 23 workflow tests and actual
unknown-input invocation, whose current workflow hash is recorded separately.
The large replay was not repeated for this argument validation change.

An initial invocation of `input-candidate-test.py` without its required release
artifact arguments exited 2 before executing tests; its diagnostic is retained.
That release-specific suite was not counted among the 82 tests. Instead, the
actual new candidate was checked against its underlying deployment validator
and correctly rejected as unreviewed. No candidate pin was changed to make a
positive deployment test pass.

Storage checkpoints: **749.07 GiB free before execution**, **738.02 GiB before
cleanup**, **743.23 GiB immediately after cleanup**, and **744.65 GiB at handoff**.
The cleanup's measured immediate free-space increase is **5.21 GiB**; later
filesystem reclamation/other host activity can affect the handoff measurement.
This is measured free space, not apparent sparse/reflink sizes. Only this job's
completed extraction/intermediate assembly scratch was removed. Candidate,
manifests, metadata, original/recovery baselines and logs remain. The tiny
unknown-input fixture and temporary unit-test fixtures were also removed.

Remaining: fresh encrypted-data boot/stability qualification, installer/source
pin review, production OTA guard, recovery/data-compatible rollback, upstream
trust/provenance, authenticated service/UI and eventual hardware trial. No new
OTA payload was supplied or reconstructed. The USB release and installed laptop
were unchanged. Reproduction and failure semantics are in
`docs/googlebook-update-workflow.md`.
