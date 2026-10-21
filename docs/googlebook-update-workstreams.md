# Ruby update workstreams and readiness contract

ANAL-229, evidence reviewed **2026-10-21**. This is a development work plan,
not a frozen release plan or authorization to modify a physical device.

The first execution milestone is now implemented in `googlebook-update-workflow.md`:
a fixed, pinned camera25 replay runs the native audit, reassembly and input
controls, records durable job states and cleans its completed scratch. Real
execution passed and remains `assembled_unqualified`. It does not reconstruct
a new recovery/OTA or close trust, installer-pin, boot, containment or recovery
gates. The table below describes the broader workstream, not completed universal
adaptation. Authenticated service requests and a UI remain follow-on work.

## Current evidence

| Area | Established | Not established |
|---|---|---|
| Native OTA guard, PR #121 at `8294358eabd1` | Both fresh and initialized offline VMs passed 24 ordinary/stable Binder checks; real status/cleanup retained; initialized keys unchanged | G14 installation, Google client/network behavior, recovery/sideload, Mainline, privileged raw writes or unattended safety |
| VM image | Exact content/metadata/AVB audit; enforcing test policy; real native daemon | Production policy: the candidate still includes the probe and four shell test grants, and is rejected by physical packaging/writer gates |
| Runtime | Fresh guard and baseline both exhibit a system-server crash class; initialized guard's bounded run has no recorded fatal signal | A common root cause or stable AMD runtime; similar signals do not prove that crashes are harmless or solely an emulator artifact |
| Host staging | Exact input/profile/evidence hashing, independently supplied review key, signed stage/expiry checks and interrupted-copy refusal | Automatic execution of attested compatibility tests, a Google OTA reconstruction adapter, independent upstream trust or a deployment service |
| Release state | Hub reports RB-20261020-01 v2 written/read back to the approved USB, hash `f47dc88c99b45f5153ed8decc5408709d5280d5e50f18b89d3c6665a5bc239c1` | OTA guard inclusion or laptop update; G14 USB boot/unlock/trackpad acceptance remains pending |

Native/VM evidence: `evidence/2026-10-20-googlebook-ota-guard/`. Source inventory,
one-slot boot record and trust limitations:
`evidence/2026-10-20-googlebook-updates/`. Current deployment truth belongs in
Multica ANAL-232/233; this work does not alter that release.

The new readiness CLI rehashed the retained **19,069,493,760-byte** raw source:
`4f4490415d4db0721fa99ad10abd64b1b05c284b6c0e413907da948561de8c9e`.
It correctly returns `awaiting_review`, not update-ready. Recognizing the local
baseline is distinct from authenticating an upstream signature or approving
modification. No new Google OTA has been supplied/validated in this work.

## Work that does not need the laptop

| Workstream | Next bounded deliverable | Acceptance and dependency | Effort/risk assessment |
|---|---|---|---|
| Host adaptation, ANAL-229 | Wire the known full-recovery path into a versioned job: pinned original and AMD transform profile, native audits, immutable output identities, regenerated installer pin, evidence collection | Reject unknown input/transform/tool identities and missing/failed native checks. Replay a known retained tuple first. Require authorized input and independently established upstream trust before qualifying a new production import. | Substantial integration; existing assemblers help, but arbitrary future framework/vendor changes remain engineering work |
| App/backend contract, ANAL-229 | Read-only assessment delivered here; next add durable job history and authenticated status/review requests with synthetic fixtures | No caller-supplied commands, paths, trust keys or device nodes in a future remote API. UI must show exact blockers and distinguish development, reviewed, trial and deployed states. | Smaller than recovery/compatibility work; starting a polished install button now would hide missing capabilities |
| Containment, ANAL-230 | Build a production-shaped VM candidate without the probe/test grants; use a separately instrumented caller and matched controls | Repeat both APIs, real cleanup, ordinary app/security-UI operation and a network/idle/reboot/recovery/Mainline matrix. Fail on unfamiliar client/build. Physical behavior remains a later gate. | Integration and test heavy; proprietary client paths are not inferred from names or offline results |
| Recoverability, ANAL-231 | Regular-file VM transaction with complete second system set, counted boot attempts, protected shared metadata and an offline rescue path | Interrupt each write/activation boundary; test missing boot files, failure to reach health gates, signature/profile refusal and successful fallback. Add a data-version contract and explicitly reject old-system boot on incompatible newer data. | Highest safety risk; system fallback alone does not solve data/key/schema recovery |

These streams can advance independently in host/VM environments. They converge
before a physical trial: reviewed candidate + qualified containment + demonstrated
recovery/data policy + exact current-device evidence + release/device approvals.
ANAL-229 stays in progress while software work is available; the hardware gate
does not block the entire research effort. ANAL-230/231 remain the existing
unassigned follow-on records; their presence does not mean an agent was started.

The next full-import automation milestone should reproduce a known baseline
before accepting another build. For every transformed component, pin old/new
hashes and the specific recipe; inspect AVB/rollback indexes, VINTF, SELinux,
kernel/modules, firmware/graphics and layout as a tuple. Automate the mechanical
checks; stop for engineering review when the tuple changes incompatibly. Never
execute an upstream postinstall/firmware script on the host or laptop just
because it was present in an authenticated package.

Full OTA reconstruction comes after that path. Incremental reconstruction is
later still: it must start from exact stock source partitions, never the modified
AMD system. It requires a real authorized payload, authenticated signing trust,
supported operation versions and verified destination hashes. A downloaded
package or locally signed approval is not evidence that these steps happened.
This is why universal automatic OTA patching has no supported completion date.

## Read-only backend slice delivered now

`scripts/googlebook/update-assess.py` outputs
`openbook-ruby-update-assessment/1`. It reuses the signed staging evaluator;
there is no second approval implementation or route around it.

```sh
python3 scripts/googlebook/update-assess.py \
  --profile config/image-bases/ruby-update-camera25.json \
  --original "$RETAINED_RAW_RECOVERY"

python3 scripts/googlebook/update-assess.py \
  --profile "$PROFILE" --original "$ORIGINAL" --candidate "$CANDIDATE" \
  --review "$REVIEW" --signature "$SIGNATURE" \
  --trusted-key "$LOCALLY_CONFIGURED_REVIEW_PUBLIC_KEY" \
  --stage rehearsal --stage-parent "$EXISTING_PRIVATE_STAGING_DIRECTORY"
```

| State | Meaning for an eventual UI |
|---|---|
| `awaiting_source` | The source file has not been supplied |
| `unknown_input` | Source bytes do not match the selected local profile; no automatic patch selection |
| `awaiting_review` | Source identity matches, but candidate/review/signature/trust inputs are incomplete |
| `blocked` | Validation failed, evidence is incomplete/expired, stage is inappropriate, or storage is not sufficient/checked |
| `ready_for_local_staging` | Exact files and signed reviewer attestations passed at this moment, with space budget checked; no installation permission |

Exit 0 means only ready for **local staging**; exit 2 accompanies all other
states. `verified_attestations` names reviewed claims, not tests executed by
this command. The upstream-authentication field explicitly says this assessment
does not establish it. `physical_install_available` and
`automatic_install_authorized` are always false, even for a promotion-stage
review. No network request, extraction, build, partition access or persistent
job mutation is performed. OpenSSL uses temporary verification files, removed
on return. Local inputs and paths must be private and trusted.

Readiness is not a transferable authorization token. The staging operation
revalidates source, profile, signature, expiry, artifacts and evidence immediately
before copying. The CLI does not discover trust: the review public key must
come from independently managed local configuration, never from a download.
A future privileged/remote service must enforce that configuration and caller
authentication itself; exposing these CLI path arguments as an RPC is prohibited.

Staging budgets complete file copies plus review material and 64 MiB filesystem
overhead, with a **40 GiB free host reserve**. It rechecks before allocation,
between files and before writing metadata. These checks are not a filesystem
quota or lock on other tasks' storage. Failed copies retain a private partial
directory without publishing readiness; the task owns its later scoped cleanup.
Assessment itself writes only the caller's redirected small report. This run
created no image copies; synthetic test directories are automatically removed.

## App/service boundary and trial order

The first app-facing behavior is status, evidence, failure reasons and request
for review. Then add authenticated job requests and resumable downloads of
already reviewed complete artifacts, with per-chunk and final verification,
bounded disk usage, cancellation and durable audit history. Signing stays off
the laptop. A normal APK is the UI, not a partition writer or OTA assembler.

The eventual service uses a fixed operation vocabulary, authenticated/pinned
caller identity, least privilege and no arbitrary shell/path/device operations.
A trial approval binds artifact, device, source version, operation, expiry and
nonce; revalidate power, disk space, pending snapshot state and recovery before
any write. Never turn the native guard into a user-toggleable stock-OTA bypass.
The proposed controlled writer is a separate reviewed path with its own gates.

When G14 access returns, first collect the **current paired** ADB endpoint,
fingerprint, package/module versions, GPT/slots, pending OTA/snapshot state and
available storage read-only. Do not reuse a stale wireless port. Then establish
a fresh matching recovery backup and concrete recovery procedure; prepare the
production-shaped candidate, rehearse, and obtain exact-device approval.
Test normal use, charging/idle, reboot, recovery and app updates separately.
The owner can keep using the installed laptop while host/VM work proceeds.

## Primary sources rechecked 2026-10-21

- [AOSP OTA tools](https://source.android.com/docs/core/ota/tools): incremental
  packages require the exact source build; this supports retaining immutable
  stock inputs, not applying a stock delta to the hybrid.
- [AOSP update engine](https://android.googlesource.com/platform/system/update_engine/+/refs/heads/main/README.md)
  and [A/B lifecycle](https://source.android.com/docs/core/ota/ab): payload
  metadata/signature checks, inactive-system writing, verification and
  postinstall/activation are separate steps. They do not qualify Ruby's current
  one-slot layout or its proprietary client.
- [VINTF](https://source.android.com/docs/core/architecture/vintf): framework and
  device manifests/matrices must reconcile at update time; runtime is an
  additional qualification.
- [Mainline](https://source.android.com/docs/core/ota/modular-system): Google
  Play system updates can deliver system modules independently of the normal
  OS release cycle. Working ordinary app updates do not qualify this path.

Estimates above are relative engineering assessments, not measured schedules.
The critical uncertainties are actual payload/trust availability, proprietary
client behavior, runtime crashes and data-compatible recovery. Track them as
explicit evidence gates rather than substituting a UI demo or repeated boot
success for the missing results.
