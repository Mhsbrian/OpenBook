# AnyBook release control

The Multica release hub is **ANAL-232**
(`01a15aa2-77a9-76a2-9f34-db99940b0f68`). Its first release record is
**ANAL-233**, `RB-20261020-01`
(`01a15aa3-e12a-7210-b3cf-236c7a4f7458`). The hub is the current index; each
release record keeps its own scope, approvals, artifacts and deployment history.
Feature issues retain their existing parents and technical discussion.

This is agent-operated build orchestration through Multica, not an unattended
CI or deployment service. A ready-state notification updates the queue. A
human build approval starts the approved recipe. No timer repeatedly rebuilds
unchanged work. No PR merge, issue status or successful VM test authorizes a
physical write.

## Current release boundary

The initial track is Ruby/Googlebook on the G14. Keep the existing AOSP track
and its A/B updater separate. ANAL-192's earlier AOSP installer history is
retained; it is not evidence of Ruby update/rollback compatibility.

Fresh28 was built under ANAL-228 and was not written to the owner's stick.
Later ANAL-229 checks found a stale AVB bootconfig size inherited from input27.
It needs a corrected build, a new installer source pin and a new rehearsal
before promotion. The native OTA guard in PR #121 remains a VM experiment and
is excluded from the proposed next USB release.

`config/releases/RB-20261020-01-plan-v1.json` is the first frozen proposal,
also attached to ANAL-233. Its exact-byte SHA-256 is
`abffe5eb4afa2b40d1fd72d0668c412a874d993e1609852beff969579f296f91`.
No approval, build output, deployment or hardware acceptance is claimed by that
file. Source commit `8294358eabd121c92e926768f8fdffa8894b9638` is deliberately
pinned; use its normal input-correction/installer recipe, not its OTA-guard
candidate builder. The source PR remains a draft; approval to build does not
approve merging it.

## Work-item handoff and automatic intake

The AnyBook project description supplies release instructions to every new or
resumed task in that project. Agents, not the owner, are responsible for intake.
Already-running tasks may still have older context. Work outside AnyBook does
not inherit these instructions; bring it into the project or explicitly hand it
off to the hub before considering its output for release.

Every image-affecting work issue records a short release handoff:

- track and intended target;
- PR and full commit SHA, with required ancestor/dependency commits;
- included behavior and explicitly unfinished/experimental behavior;
- test commands, evidence and remaining hardware checks;
- whether the work changes boot, layout, installer pins, data or recovery.

Read the hub and existing wakeups before registering a ready-state watch.
Register once per source issue when it enters the queue; do not register a
watch for the hub itself or for release records. A source reaching `in_review`
wakes the coordinator to reconcile the queue, not to approve or deploy it.
Conditions expire after 90 days; the hub records expiry and renews only for
still-relevant work. Reopened/revised work needs renewed intake rather than
reusing an earlier frozen release approval.

```sh
multica issue wakeup list 01a15aa2-77a9-76a2-9f34-db99940b0f68 --output json
multica issue wakeup create 01a15aa2-77a9-76a2-9f34-db99940b0f68 \
  --agent-id 517b88d9-124d-43e9-a8ca-bb617437e116 \
  --until-issue "$SOURCE_ISSUE_ID" --until-issue-state in_review \
  --expires-in 2160h \
  --instruction-file ./config/releases/intake-instruction.md --output json
```

The instruction file tells the coordinator to read the source issue's bounded
history and linked PR state, record exact heads/test limits in the hub queue,
reuse the existing proposed release and stop before building unless the exact
plan already has valid human approval. It must not dispatch further agents or
add recursive comment/task-completion subscriptions.

If work is already in review, ingest it during reconciliation rather than
creating a batch of immediately satisfied watches. Readiness watches are
one-shot notifications, not subscriptions to every PR commit. Source agents
renew intake for revised work; the coordinator rechecks heads before freezing
and building. Do not make the owner register or renew these watches.

## Catching existing work and new images

Before proposing a plan, and again before executing an approved build, the
coordinator takes a complete project census. Include old in-review items,
blocked work, new tasks and source revisions. A title search alone cannot
establish image impact. Expand relevant issue threads and linked PRs, keeping
the existing bounded comment-read workflow.

```sh
python3 scripts/releases/intake-audit.py --output ./intake-census.json
# Later, use a fresh filename and the prior snapshot to highlight index changes:
python3 scripts/releases/intake-audit.py \
  --previous ./intake-census.json --output ./intake-census-next.json
```

This read-only helper follows pagination through an empty page, rejects
repeated/incomplete pages, and reports new/changed/missing issues and readiness
watch health. It does not read private comments, infer track/eligibility,
subscribe agents or approve anything. Its index-change comparison cannot
detect every PR head change; verify actual heads separately. A failed or
partial census cannot serve as the completed release reconciliation.

Keep the current census attached to the hub. The coordinator records the
disposition of relevant work in its queue: **needs assessment, queued, blocked,
deferred with a reason, or included in a named plan**. Unknown track or impact
stays needs assessment. Unresolved relevant work must be explicitly deferred
with its impact on the proposed release explained; it cannot disappear from
the queue. A census is discovery evidence, not proof that all listed work is
qualified. Catch changes again before building; changed approved inputs require
a new revision, while unrelated work stays in the next batch.

Every new image follows the same handoff, including a new upstream/base image:
record its track, parent image/release, source/input hashes, source issue and
tests. Development/VM images may stay with their feature issue, marked
experimental. An image intended for the stick or laptop must acquire a release
record and pass the plan, validation and device gates before promotion. A
different track/base starts a separately qualified release; “newer” alone is
not compatibility evidence. Historical releases remain immutable.

The PR template repeats the handoff so contributors see it where code changes
are submitted. It takes effect for default PR creation after this PR's template
lands in the repository's default branch; project instructions are live now.
These are agent workflow controls, not a GitHub-required check or a wrapper
that prevents arbitrary manual image builds.

For the owner, the hub is the only place to manage releases: “What's ready?”,
“Prepare the next release”, or “Hold this release” are sufficient requests.
The coordinator presents a short included/deferred list and a concrete plan
for approval. The owner never has to assemble commit lists or copy handoffs
between issues. Approval still identifies the exact plan; final device-write
approval identifies the tested image, operation and exact device.

## Approval and execution

1. **Reconcile.** Read the hub, active release and bounded comment history.
   Complete the project census and dispositions above. Read actual linked PR
   state and exact heads. Check active release runs.
   Preserve unrelated concurrent edits; reread the issue before updating it.
2. **Freeze.** Create a release record under the hub, or reuse its existing
   draft. Record the preceding accepted release separately from any held
   candidate. Pin the source tree, input hashes, recipe and required tests.
   Never substitute a newer branch head for a pinned commit.
3. **Approve build.** Verify B Honey's actual Multica comment author, rather
   than an agent's quotation. Record comment ID, plan revision and exact-byte
   plan hash. “Approve build RB-20261020-01 plan v1” approves only the attached
   proposal. An ambiguous comment needs clarification; changed plan bytes need
   a new approval. Do not infer approval from elapsed time or an issue status.
4. **Build and test.** Use the pinned clean checkout and a fresh private output
   directory. Hold the shared build lock for the whole build/rehearsal command
   chain; never overlap two builds of the same track. Run existing scripts in
   the foreground with durable logs. Record container/tool/package identities.
   No owner data is a VM fixture. Verify output bytes and regenerate the
   installer pin after any static system or boot change.
5. **Review candidate.** Record artifact/manifest/installer hashes, source
   commits, test results and unresolved failures in the release issue. Failed
   or incomplete runs remain visible. VM boot and unchanged encryption keys
   do not prove stability, physical unlock or automatic rollback.
6. **Approve deployment separately.** Review the actual output hash, exact
   device identity, operation, current backup and recovery procedure. Confirm
   the source and target again immediately before any authorized write.
7. **Verify.** Record direct readback, boot/hardware acceptance and remaining
   limitations. Only then update the hub's stick/laptop pointer. Keep prior
   artifacts and distinguish image reversal from data-schema rollback.

A retry reuses the same release record and identifies the failed attempt. It
never overwrites an approved artifact. Resume a completed step only after
verifying its input/output hashes; otherwise use a fresh attempt directory.
Further feature work goes into the next proposed release. A successful build
does not silently advance the current installed release.

The release issue carries build/deployment progress. The hub remains the
index/review desk; do not mark unrelated source issues done or reassign their
owners. Stop with a concrete blocker when an input, approval, source/license
qualification, backup or recovery gate is missing.

## Record retained for each release

| Record | Required contents |
|---|---|
| Plan | Release ID/revision, track, previous accepted release, exact source/input hashes, included/excluded work, recipe and tests |
| Build approval | Verified member comment ID and exact plan hash |
| Build attempt | Tool/container identities, durable logs, step outcomes, final checksums, private artifact location |
| Validation | Exact artifact tested, evidence hashes, failures and explicit untested boundaries |
| Deployment approval | Verified member comment, image checksum, operation, exact device and backup/recovery plan |
| Deployment result | Readback, boot/hardware checks, owner acceptance and installed/stick pointers |

Manifests and sanitized evidence belong in Git. Google images, device backups,
credentials, raw private logs and TPM/key material remain private. GitHub holds
code review; Multica holds the release queue, decisions and operational state.
