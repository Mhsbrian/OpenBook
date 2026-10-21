# Ruby update process review — 2026-10-21

This follow-up starts the host/app readiness contract while the G14 containment
and recovery gates remain unqualified. It does not build an image, run a new VM,
install an APK or touch any physical device.

- `tests.txt`: 24 staging/inventory/readiness tests pass. Ten added tests cover
  nonwriting status, identity-versus-trust, unknown/missing/unsupported input,
  forged/expired approvals, changed artifacts, missing evidence/stage escalation,
  host reserve boundaries, space consumed between copies, disallowed input types,
  JSON/CLI behavior and revalidation after a previously ready status. Some cases
  combine related boundaries. Existing interrupted-copy checks remain.
- `retained-source-assessment.json`: the actual 19,069,493,760-byte raw recovery
  was rehashed and matched the retained camera25 profile. The command exited 2
  with `awaiting_review`, no verified attestations and no staging/install access.
  This is measured byte identity, not an upstream signature or new-OTA test.
- `validation.json`: scope, test count and measured host free space. No large
  copies or disk fixtures were created. Temporary synthetic files and generated
  test keys were removed by the test fixtures. No owner/recovery artifact was
  removed. Storage reserve is tested with injected capacities so the tiny tests
  work on CI or a tmpfs smaller than 40 GiB; retained-source inspection uses the
  actual host and only streams bytes.

The earlier 77 Python cases, 19 native assertions, 20 policy assertions and
24-assertion VM probes are historical evidence in the 2026-10-20 directories,
not freshly rerun native/VM qualification in this step. The normal engine and
guard binary/policy were not changed. The update readiness evaluator reuses
`update-stage.py`; signed reports remain reviewer attestations rather than
automatically performed compatibility tests. Production upstream trust,
automated native audit orchestration, full/incremental OTA reconstruction,
remote authentication, an APK, recoverable writer and hardware qualification
remain unfinished. See `docs/googlebook-update-workstreams.md`.
