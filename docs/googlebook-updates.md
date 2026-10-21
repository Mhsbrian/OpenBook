# Ruby/OpenBook updates: decision and qualification boundary

ANAL-229, reviewed **2026-10-20**, starting at migration commit `d904dc2`.
Target: the owner's ASUS GA403WR, Ryzen AI 9 HX 370 / Radeon 890M,
Ruby `16452207_CL3B.260622.271.R1` with OpenBook camera25. PR #119 was
open at the start; this change targets its branch, not `main`.

**Use a local build-host pipeline with explicit review and offline recovery
first. Do not enable unattended OS updates or deliver stock OTAs to this
single-slot hybrid.** An app can later show status and request approval.
Universal automatic AMD patching is not supported by the evidence.

**2026-10-21 review:** `googlebook-update-workstreams.md` records the current
evidence, independent software workstreams, readiness implementation and exact
next gates. Hardware qualification is still pending; it does not block host
adaptation tooling, the app/service contract or disposable recovery development.

Implementation follow-up: the owner reports ordinary app updates working and
requests system OTA/rollback work while using the installed G14.
`googlebook-ota-guard.md` documents the opt-in native installation guard,
preserved real cleanup, disposable Binder harness and current qualification
results. No containment has been installed on the laptop. This supersedes
engine stopping as the implementation direction; the negative results below
remain part of the evidence.

The prototype implements signed review/staging, retained-build inventory,
read-only runtime capture, and reviewed installer replacement. An optional
init fragment experiments with suppressing `update_engine` auto-start.
**Do not deploy it:** the fresh-data VM did not complete boot and rebooted with
`Checkpoint commit failed`. An initialized encrypted-data VM completed boot,
but still reproduced a system-server crash. The experiment is also
**not complete containment**: downloads, privileged restarts, Google
Mainline, networked idle/charging and stock recovery remain unqualified.
No containment was installed on the owner's USB or SSD.

Evidence is in `evidence/2026-10-20-googlebook-updates/`. Read the measured
results and failure history before using the experimental fragment.
Migration/data-copy success in ANAL-228 did not establish runtime stability.

## Exact-build inventory and exposure

`update-inventory.py` hashes the retained filesystem inputs, extracts GMS
update-component declarations with `aapt2`, and records the camera25 layout.
These are local observations, not claims about every Googlebook release.

| Boundary | Observed on this build | Consequence / remaining uncertainty |
|---|---|---|
| OS client | GMS is inside `product/apex/com.google.android.gmssystem.prodvic.apex`, not a top-level GMS APK. Its manifest declares `SystemUpdateService`, `SystemUpdateGcmTaskService`, `SystemUpdatePersistentListenerService`, `UpdateJobService`, update UI/provider and resume-on-reboot escrow. `RECOVERY` and `REBOOT` are requested; the retained privileged allowlists include GMS grants. | Scheduling and downloaded Chimera-module behavior are proprietary and not inferred from component names. Current on-device enabled states require capture. |
| Desktop UI | `GmsCoreOtaDesktopOverlay.apk` targets GMS update presentation and uses `ro.build.version.desktop_os`. Settings and Play Store are retained. | The overlay is not an update-disable policy. `ConfigUpdater` is not assumed to be the OS updater. |
| Native backend | `/system/bin/update_engine`, client and verifier exist. The init service is root, `late_start`, initially disabled, then enabled by `ro.boot.slot_suffix=*`. No separate `update_engine.conf` was found in the retained system tree. | The disabled stanza alone does not disable it. Saved camera25 VM logs show the process and both `android.os.UpdateEngineService` and `android.os.UpdateEngineStableService` registered. |
| Slots and boot control | camera25 has EFI, misc, boot_a, init_boot_a, vendor_boot_a, vbmeta_a, metadata, super and userdata; no physical B boot set. The retained camera25 VM's CRC-valid misc boot-control structure reports **one slot**. The hybrid uses `android.hardware.boot-service.openbook`; stock uses the desktop boot HAL. | The OpenBook HAL synchronizes systemd-boot entries through `openbook-bootsync`. Its AOSP A/B success does not create missing Ruby slots or qualify this layout. No current G14 HAL query was available. |
| Dynamic partitions | One `ruby_probe_a` group with six logical images; lpmake metadata copies/slots are not two bootable OS installations. Both retained stock and hybrid properties advertise compressed userspace Virtual A/B, XOR, io_uring and ublk. | These properties cannot establish a usable inactive slot or snapshot rollback path. Do not change them casually on existing data. |
| Assertions | Stock product's OTA partition list includes `pvmfw`; this hybrid omits that partition. Stock and OpenBook vendor fingerprints and security patch levels differ. | No actual Google OTA was supplied. Its signed device/source assertions, partition operations and postinstall instructions remain unknown. A recovery manifest is not OTA metadata. |
| Recovery / firmware | Stock vendor_boot recovery fragment includes recovery, fastboot/boot HAL, recovery fstab and OTA certificates. Stock system postinstall wrapper invokes `google_desktop_firmware_updater`; stock vendor contains firmware updater wrappers. | The normal hybrid EFI path forces normal boot. The copied stock recovery is not a tested AMD rescue path. No recovery invocation or firmware updater was executed. Use the separate offline Linux medium. |
| Other updates | APK updates and APEX/Mainline installation are separate from the OS update engine. GMS itself is in an APEX. | Updating that module can invalidate a component-level policy. Preserve app updates and security UI; qualify Mainline independently rather than equating it with ordinary apps. |

The saved VM ran without a NIC. **No measured automatic download, successful
stock payload application or stock slot activation is claimed.** A one-slot
failure is not a safety mechanism: a future client could change its behavior,
attempt recovery, or write before discovering a missing partition.

The Android developer switch writes
`Settings.Global.OTA_DISABLE_AUTOMATIC_UPDATE`; the inspected AOSP Settings
controller does not remove a backend, block network I/O, or enforce a recovery
policy. That local source observation does not prove the proprietary client
honors the setting in every path.

## Trust, signatures and compatibility

The official recovery index was fetched again on 2026-10-20. Its Ruby entry still
names build 16452207, updated 2026-10-05; `zipfilesize: 1` is not a usable size.
The raw SHA-256 pin is from the earlier reviewed assembler, not an independently
Google-signed digest record. The new preflight identifies retained bytes only.

`security.json` records the stock vbmeta public-key hash, flags 0, rollback index
**1339** at location 0, and the hybrid's different **public test key**, flags 0
and rollback index **0**. These are different trust domains. The hybrid's
unlocked/orange boot plus dm-verity is not stock verified boot or attestation.
Keeping signed Google filesystem descriptors does not authenticate our kernel,
EFI loader or rebuilt vendor. A release needs owner-controlled signing and a
documented boot trust chain; do not call a public test key release security.

System and recovery `otacerts.zip` contain the same observed certificate/SPKI.
The certificate subject is `CN=test`; neither the subject nor its archive path
establishes key ownership. The stock update-engine binary references
`/system/etc/security/otacerts.zip`. No OTA signature was verified and no
independently authenticated Google payload key was established.

For every proposed update:

- Authenticate the original container/payload against an independently approved
  key and provenance record. Check signed device/build/timestamp/partition
  metadata before extraction. Keep original bytes immutable. A locally signed
  review is separate from Google signature verification.
- Verify AVB descriptors/chains, key identities and all rollback-index
  locations. Retain old-slot boot eligibility until acceptance; an irreversible
  index advance can make the old image unbootable. Do not reset stock indexes to
  make an older image pass.
- Run native `checkvintf` with APEX fragments/kernel requirements and `secilc`
  with neverallow checks. Fail on missing reports, new HALs, mapping versions,
  policy types or changed service labels. Passing static checks is necessary,
  not sufficient for runtime compatibility.
- Keep kernel, system_dlkm and vendor_dlkm together; check exported/imported
  symbols, modversions, namespaces, module signatures and configuration.
  Stable KMI is scoped to a kernel generation, not arbitrary kernel swaps.
- Qualify firmware, DRM ioctls, Mesa/ANGLE, gralloc buffer handles, composer,
  camera and audio as a tuple. Mesa's internal library/driver ABI is not stable.
  The owner's camera25 webcam/Bluetooth report does not qualify another tuple.
- Check super geometry, filesystem features, metadata space, userdata capacity,
  key services, credential unlock and application/database migrations. Never
  format data automatically to recover from a compatibility failure.

[AVB documentation](https://android.googlesource.com/platform/external/avb/+/refs/heads/main/README.md),
[VINTF](https://source.android.com/docs/core/architecture/vintf),
[SELinux compatibility](https://source.android.com/docs/security/features/selinux/compatibility),
[stable KMI](https://source.android.com/docs/core/architecture/kernel/stable-kmi) and
[Mesa EGL packaging](https://docs.mesa3d.org/egl.html#packaging), checked 2026-10-20,
support these distinct boundaries; none certifies this proprietary hybrid.

## Update strategy comparison

Maintenance ratings are engineering estimates, not measured development costs.

| Method | Supported work / prerequisites | Unsupported or dangerous assumptions | Maintenance and security |
|---|---|---|---|
| **Full recovery re-import — first implementation** | Identify an authorized complete input; reconstruct a fresh AMD candidate off-device; keep original; audit and rehearse before promotion. | Recovery may contain factory data/layout and is not itself a data-preserving updater. No automatic acceptance of unknown versions. | Medium/high: large downloads and storage, but simplest reproducible stock baseline. Requires separate trust and data-migration review. |
| Full OTA reassembly | Verify signed metadata/payload, materialize stock destination partitions in a sandbox, then perform the same adaptation. | Not implemented here. Google target-files are not assumed available. Do not execute embedded postinstall or firmware tools on the host or G14. | High: payload parser, compression/operation versions, partition metadata and postinstall requirements must be supported. Better bandwidth than recovery in some releases. |
| Incremental reconstruction | Apply verified operations to an **exact immutable stock source**, verify every destination digest, then adapt. | Never apply a Google delta to our changed vendor/boot/super or treat the installed hybrid as the stock baseline. Unknown operation/source hash must fail. | Highest: retain source chains, reconstruct missing releases, handle payload-format drift. Saves transfer, increases state and verification burden. |
| On-device patching | A narrow privileged service can stage an already reviewed signed complete candidate into an inactive set. | No running-kernel patching, arbitrary shell commands from an APK, blind stock payload acceptance or generic binary patching of unknown frameworks. | High on current layout: resource pressure, privileged attack surface and interrupted-write risk. Defer assembly to a host; introduce a writer only after recovery design is proven. |

[AOSP OTA tooling](https://source.android.com/docs/core/ota/tools) documents the
exact-source requirement for incremental packages and device/build metadata.
[Release signing](https://source.android.com/docs/core/ota/sign_builds) distinguishes
release keys from public test keys. Checked 2026-10-20.

## Containment experiment and release gate

The optional `--test-update-engine-stop` flag is a negative research experiment.
It inserts `stop update_engine` at early-init and after the stock slot-property
enable action. On the tested ordering, stopping an unstarted service marks it
disabled before `late_start`. Removing the fragment and rebuilding the reviewed
vendor reverses it next boot. It changes no APK, Settings UI or SELinux grant.

This is **auto-start suppression, not an execution boundary**. A privileged
explicit start/enable can defeat it. It does not cancel or block a GMS download,
stop Mainline, or constrain a separate recovery environment. Do not deploy it
as the acceptance criterion's complete containment mechanism.

Rejected experiments are evidence too: missing-user and cross-Treble service
overrides were ignored/rejected while stock update_engine ran; a root-ramdisk
fragment disappeared at system-as-root switching; masking the executable
requires a grant forbidden by `neverallow domain exec_type:file mounton`.
The neverallow was retained. None of these failures counts as containment.

The final stop-action experiment recorded the engine stopped and both Binder
interfaces absent. A fresh-data direct-kernel VM rebooted at 275.7 seconds with
`Checkpoint commit failed`, without boot completion. The initialized encrypted
UEFI VM reached boot completion at guest 153.4 seconds but later reproduced the
known system-server crash class. The differing boot paths and prior checkpoint
failures in camera25 prevent attributing the fresh-data failure solely to
stopping the engine. It remains a failed qualification, not a deployable fix.
No network or Play app-update checks were possible in these offline VMs.

Reversal is measured on a second private clone of that initialized VM:
restoring the original camera25 candidate restores the process and both Binder
interfaces, and boot completes at guest 156.5 seconds during a 480.7-second
observation. The same system-server SIGSEGV class recurs. All four pre-existing
metadata-encryption files match the original before and after both trials;
source images, source TPM state and decoy disks remain unchanged. This is a
same-build vendor reversal with synthetic data, not newer-schema rollback,
owner credential unlock or proof of stock-update safety.

Before unattended use, the remaining qualification must:

1. Capture the actual G14 fingerprint, package versions/component states,
   boot-control/snapshot state, enabled jobs and backend state using
   `capture-adb.py --updates-only`. Repeat during normal use, idle/charging,
   after a controlled reboot and through the approved recovery path.
   The `--phase` option labels a capture; it does not force any device state.
2. Establish the proprietary client's supported inhibition contract or a
   narrowly tested OS-only component policy, recording original per-user
   enabled states for exact restoration. Do not disable all GMS, Play Store,
   download manager, recovery UI or security settings. Test client/module
   self-reenable, queued downloads, explicit check and reboot-after-download.
3. Measure both network delivery and attempted block writes/activation in a
   disposable instrumented environment, including idle/charging. Absence of
   traffic in an offline VM is not evidence of download inhibition.
4. Verify Play app install/update and security UI operation; qualify APEX
   separately. Fail if an unrecognized package/build appears. Test reversal
   using the recorded prior states, not blanket `pm enable`.
5. Provide a validated offline recovery route and a backend denial that remains
   effective across reboot and recovery. A current networked/paired G14 session
   and an authorized OTA/test input were unavailable in this run.

Deferral has a security cost: framework SPL here is 2026-09-01; OpenBook vendor
reports 2026-06-05. Neither dates nor newer app updates prove that specific CVEs
are fixed. Track upstream bulletins and component commits, assign an owner to
each exposure, and set a review deadline. Emergency fixes go through an expedited
signed candidate, focused regression/data rehearsal and explicit owner trial;
if no safe candidate exists, use the retained recovery OS or take the affected
system offline. Never quietly re-enable stock OTA as an emergency workaround.

[AOSP A/B](https://source.android.com/docs/core/ota/ab),
[Virtual A/B](https://source.android.com/docs/core/ota/virtual_ab),
[init semantics](https://android.googlesource.com/platform/system/core/+/refs/heads/main/init/README.md)
and [Mainline](https://source.android.com/docs/core/ota/modular-system),
checked 2026-10-20, explain why client, backend, slot and APEX controls differ.

## Recoverable storage transition

The present migration retains 8 GiB userdata and leaves spare SSD space
unallocated. Do not assume that space is available until reading the installed
GPT. Repartitioning or writing the physical SSD requires fresh confirmation
naming that device. Keep the configured USB and a verified offline backup.

First design a **complete second system set**, including boot/init_boot/
vendor_boot/vbmeta, logical images and versioned EFI kernel/initrds, leaving the
known-good set unchanged. Prefer this explicit duplication for the first
prototype over enabling unproven Virtual A/B snapshots. Shared `super` metadata,
misc and ESP remain shared failure points; protect them with redundant records,
flush/readback and a rescue boot path. A second partition name alone is not A/B.
Bind every initrd to its intended disk identity, not the first matching label.

Offline migration must verify both GPT copies, sector size, free extents,
target identity, power and source pin; stage the new payloads, verify all bytes,
and only then publish a counted candidate entry. Bootloader attempts must be
bounded, with fallback when boot files are missing or boot fails. Mark good
only after crypto unlock, core services and agreed hardware checks, not merely
`sys.boot_completed=1`. Test sudden failure around each payload, GPT/ESP record
and activation boundary; an atomic host directory rename proves none of these.

**System rollback does not roll back userdata.** Before a candidate touches
shared data, require an application/framework downgrade compatibility contract
or a consistent offline backup of userdata **and metadata keys** plus necessary
TPM/security state. Never clone a hardware TPM identity onto another machine.
A schema-upgrading trial must use disposable data first. After irreversible
schema or KeyMint/key changes, reject ordinary old-slot boot against that data;
restore the matching backup explicitly (with its data-loss implications), or
recover forward. Preserve newly created files separately if restoration is
chosen. Android fs checkpoints are not a generic whole-device backup.

The current host prototype tests interrupted staging, incompatible/missing
evidence and missing boot artifacts. Existing migration tests exercise synthetic
write interruption/readback failure. Actual Ruby dual-slot failed-boot rollback,
missing EFI fallback, real power cuts and newer-schema restoration remain
follow-on implementation gates, not completed tests.

[Metadata encryption](https://source.android.com/docs/security/features/encryption/metadata)
and [file-based encryption](https://source.android.com/docs/security/features/encryption/file-based),
checked 2026-10-20, support retaining key material as well as filesystem bytes.

## App and service scope

The first implementation is a single-user build-host CLI. It keeps large
artifacts, native audit tools and signing separate from the laptop. Signed
profiles, input hashes and stage approvals are mandatory; the shipped camera25
profile is research-only. See `googlebook-update-prototype.md`.

A future ordinary APK may display installed/candidate versions, stale security
status, download progress and review evidence; schedule a user-approved download;
and ask a narrow service to prepare or request a reboot. It cannot obtain root,
write protected partitions, silently install arbitrary privileged packages,
re-sign Google code, or safely replace a running kernel by normal SDK APIs.

The service should accept only versioned operations such as `status`,
`stage(digest)` and `request_trial(digest, approval)`, with Binder caller UID,
signature permission and pinned app signing identity checks. No caller-supplied
shell command or arbitrary device/path. Bind approval to artifact digest, exact
device, source version, nonce, expiry and stage; recheck all immediately before
writing. Keep artifact-signing keys off-device, separate review from transport
keys, and support explicit rotation/revocation.

Host communication needs authenticated pairing and TLS with pinned identity
(or mutual TLS), user-specific access and replay resistance. Use resumable
range delivery into private temporary files, checking chunk hashes and the final
signed length/digest; never execute a partially downloaded artifact. Require AC
or a reviewed battery threshold, sufficient staging/backup/ESP space, no active
snapshot merge, a valid rescue path and exclusive device access. Journal each
state transition with hashes, verification results and approvals; exclude
credentials, user content and private keys. Reject unknown profiles and require
manual review rather than guessing patches. This service/app is a design, not
an implemented root daemon in this change.

## Licensing and unresolved prerequisites

No Google payload, derived image, owner data, TPM state or private key is
redistributed. Existing retained inputs were inspected locally.
[Google's additional terms](https://www.google.com/chrome/terms/), checked
2026-10-20, name GooglebookOS but do not by themselves establish permission to
transfer/modify this recovery for a G14. Public kernel source is not a public
source release or redistribution license for Google's framework/apps.
Record an appropriate usage basis and independently approved source trust
before a new production import. Do not bypass DRM, Play Integrity, licenses or
verified boot on devices the owner does not own.

Outstanding acceptance: complete stock-update containment, networked/idle/
charging/reboot/recovery qualification, a real update input, stable runtime,
recoverable Ruby writer and userdata rollback. This issue is not complete merely
because a research PR and host tests are available.

The follow-on work is parked without agent assignment: **ANAL-230** covers
boot-compatible containment and current-device/network qualification;
**ANAL-231** covers recoverable system transactions and data-schema rollback.
The app remains a later consumer of those qualified operations.
