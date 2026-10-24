# Test once: RB-20261023-03 replayed (2026-10-24)

B Honey asked on ANAL-229 whether source work and the release were building and testing the same
things twice. They were, in part. The owner approved the fix ("Apply it, I just want quality,
streamlined work"). The rule is in `docs/release-control.md`, "Test once"; the check is
`scripts/releases/evidence-reuse.py`.

## What RB-20261023-03 repeated

| Work | ANAL-229 (source) | RB-20261023-03 (release) |
|---|---|---|
| Production candidate | Built on RB-20261023-02 (`candidate-production-check.json`), then deleted | Built again: candidate C |
| Fresh-boot Ruby VM test of the app | 16/16 (`vm/judge.json`) | 16/16 again (T2) |
| Engine and builder unit suites | 32/32, 11/11 | Re-run (T6) |

Both candidates' logical `system` image is `2e7b342585b70b4829831ec32b6ec39681a58c8cc5735c414b6139724dbdb532`,
and the other five logical images match too. The second build produced the same bytes. The inputs
were the same: parent candidate `75fa0196…`, APK `f3308832…`, and the same candidate builder and
updater files at the source commit `a05f832` and the release tooling commit `d65594b`.

The release's other work was new and needed: the signed laptop payload, the control rebuild of
RB-20261023-02, the update rehearsal into each slot, the fallback test and the after-update app
check. That last check found two differences from a fresh install: notifications are not
pre-granted, and the app is also installed, stopped, for the headless system user.

## Replay with the check

- `handoff-ANAL-229.json`: the handoff ANAL-229 would now write. It was written after the fact from
  its evidence (PR #121, `a05f832`).
- `plan-RB-20261023-03.json`: the plan's image inputs, reconstructed from the release's `build.json`
  (PR #128). How each hash was taken is in its `note`.
- `reuse-laptop.json`/`.txt`: the release as it was, a laptop update. All five source checks are
  cited. The release runs its five own steps.
- `reuse-laptop-and-stick.json`/`.txt`: the same plan with a stick target. The fresh boot is cited
  from ANAL-229; the stick image and the stick install still run.

Commands, with `--repo` pointing at a checkout of `a05f832` so evidence paths are confirmed:

```sh
python3 -I scripts/releases/evidence-reuse.py --plan plan-RB-20261023-03.json \
  handoff-ANAL-229.json --repo <checkout> --output reuse-laptop.json
python3 -I scripts/releases/evidence-reuse-test.py   # 9/9
```

Under the rule, RB-20261023-03 would have skipped the production candidate build in ANAL-229, the
second fresh-boot VM run and the repeated unit suites, with the same release tests on the laptop
path.
