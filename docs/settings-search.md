# Ruby Settings search failure (ANAL-234)

## Hardware translator comparison, 2026-10-22

The owner reproduced the crash on the installed RB-20261021-01 system shortly
before 21:22 EDT. The read-only collector found the same chain at 21:21:39 and
21:21:41: Houdini initialization fails, then ARM64 `libicing.so` is rejected
as `EM_AARCH64`. Settings Services crashed three times; Settings itself did not.
This is the installed NVMe system, not only the live stick
(`owner-repro-summary.json`).

With the G14 back on wireless adb, the three translators were compared on the
real Ryzen AI 9 HX 370 under Ruby's kernel and enforcing SELinux. The test ran
in a temporary `/data/local/tmp` directory and was then removed. Nothing in
`/system`, no setting and no app was changed. `icing_probe` loads Google's own
ARM64 `libicing.so`, extracted on the device from its Settings Services APK
(`ab75e8c9…`). It answers `JNI_OnLoad` through a small JNI shim, then:

1. registers all 35 natives;
2. indexes 600 Settings-like documents;
3. runs 10 prefix, AND and OR queries, checking each result set against an
   independent model;
4. persists, restarts on the same directory, and repeats the queries.

| Translator | Icing (600 docs, 10 queries, restart) | `bridge_check` ISA groups | CoreMark vs native x86_64 |
|---|---|---|---|
| Houdini, as configured | `SIGTRAP` at the first guest instruction | `SIGTRAP` | — |
| Ruby's `libndk_translation` | **Pass**, 0.58 ms/search, 269 ms to index | Crashes (`SIGSEGV` in translated code) | 0.737 |
| Source-built Digitalis | **Pass**, 1.31 ms/search, 270 ms to index | **4/4 pass** (exec, ID registers, 6,900 FRECPE/FRSQRTE cases, CRC32/NEON) | 0.362 |

The CoreMark figures are the best of three interleaved 600k-iteration rounds,
all validated: native 27,807, Digitalis 10,073 and ndk 20,500 iterations/s.
An earlier identical run reproduced every pass/fail result and both ratios.

- **Houdini fails in both modes on this CPU.** In app mode it reports
  initialization failure `0x00010002`. Run directly, it traps before the first
  ARM instruction completes. Its banner limits use to Google ALOS under Intel's
  commercial licence. We do not patch, spoof or bypass it.
- **Both alternatives run Google's search engine correctly at native speed.**
  The VM's ANRs hit many apps, including Play Services, Play Store and the
  keyboard. They came from TCG emulation, not from Icing under translation.
- **Recommendation:** Digitalis, the existing experiment. It is open source,
  passes every ISA check here and matches the AOSP track. `libndk_translation`
  is twice as fast on CPU-bound code. However, it crashes in `bridge_check`, and
  in the VM it showed ordering, FRECPE and signal defects, so it stays rejected.

Each run used its own guest set: the probe links `libm`, `liblog`, `libz` and
`libc++` with RUNPATH `$ORIGIN/guest`, so libicing binds only to that set. Only
libc's startup `libnetd_client.so` came from Ruby's `/system/lib64/arm64`;
Icing makes no socket calls. `dl_iterate_phdr` reports the guest linker by its
`PT_INTERP` name.

Berberis' runner ignores `-l`/`-s` on x86_64 and prefers Ruby's
`/system/bin/berberis` linker. `dg_launch` therefore calls the exported
`GuestLoader::StartExecutable` with Digitalis' own linker and vdso.

**Still not tested on hardware:** the full Ruby + Digitalis system. This covers
the init rule and labels, ART loading `libberberis_arm64.so` as the native
bridge, the guest `app_process64`, the Settings UI, result navigation, Voice
Access/YourWidget and the ARM app corpus. This evidence supports, but does not
replace, that acceptance. Evidence: `evidence/2026-10-22-settings-search-hw/`.

```sh
scripts/diagnostics/icing-probe/build.sh /private/new-build
python3 scripts/diagnostics/icing-probe/icing-probe-hw.py --adb ADB --serial EXACT_SERIAL \
  --build /private/new-build --digitalis "$HOME/anybook/digitalis/bundle-a17" --out /private/new-run
```

## Confirmed on the laptop, 2026-10-21

Opening the left-hand search field starts Google Settings Intelligence. Its
ARM64 Icing search library fails to load after the configured Houdini native
bridge fails initialization. Android tears down the embedded search activity
and restarts its service, producing the blinking/resetting search field and
the **Settings Services keeps stopping** dialog.

This is a confirmed failure chain, not an interpretation of Houdini's internal
error code. The reason for `0x00010002` is **unknown**: these logs do not prove
a CPU-vendor restriction, an instruction failure, a licensing check or a
specific missing dependency. No binary patch or bypass is proposed.

| Observation | Evidence |
|---|---|
| Connected target | Ryzen AI 9 HX 370; OpenBook G14 boot properties; 2880×1800 display |
| Runtime | Ruby Android 17 `CL3B.260622.271.R1/16452207`, kernel `6.18.21-android17-5-gfbfdd65b0fd1`, SELinux Enforcing |
| Boot context | `ro.boot.openbook.live=1`, metadata mounted from `sda7`; live environment observed, not proof of the installed NVMe version or exact release-image hash |
| Search package | `com.google.android.settings.intelligence`, `1.1.0.937862210.sr` / `1000299141`, user 10, `primaryCpuAbi=arm64-v8a` |
| Native payload | Three ARM64-only libraries: `libicing.so`, `libgeller_jni_lite_lib.so`, `libandroidx.graphics.path.so`; ELF machine 183 for each |
| APK identity | Device SHA-256 equals retained recovery APK: `ab75e8c9ab4a995f662dcf6c477a7b754016bafac2593f87fc6a185c257dfa47` |
| Translation properties | `libhoudini.so`, `ro.dalvik.vm.isa.arm64=x86_64`, secondary-bridge flag true; presence of these properties/libraries does not establish working translation |
| Failure | `UnsatisfiedLinkError`: ARM64 `libicing.so` is `EM_AARCH64 (183)` instead of `EM_X86_64 (62)` |

Before interaction, the crash buffer contained two matching search crashes at
07:29:17 and 07:29:20 EDT. Three synthetic clicks with query `display` produced
two search launches/crashes at 07:34:15 and 07:34:44; the third click dismissed
the error dialog. A separate direct search intent crashed at 07:35:28 without
typing, so keyboard input is not required to trigger it. `am start -W` returning
`Status: ok` established launch only; the process crashed immediately afterward.

For PID 11462, Houdini initialization failed at 07:34:15.537, before the second
search crashed in that PID at 07:34:44.830. Its successor PID 12024 failed
initialization at 07:34:51.755, then crashed during the direct search launch.
The native loader reported the ARM64/x86_64 mismatch before each fatal exception.

Settings PIDs 1877/2909 and system_server PID 1182 stayed unchanged. We did not
reproduce a new crash of the entire Settings process. Opening Display directly
worked and four samples over 30 seconds kept the same activity/processes alive,
with no additional search crash. The older Settings ANR and Repair Mode startup
exceptions are separate observations, not evidence for this search diagnosis.

Sanitized evidence: `evidence/2026-10-21-settings-search/`. Raw logcat, exit
records, package dumps, APK inventory and screenshots are retained privately.
Screenshots contain account/network information and are not in Git. No APK or
proprietary library was copied into the repository or attached to the issue.

## Reproduce and capture

Use an already authorized device. First capture the existing evidence, open
Settings and click the search field, then capture again. A direct control is
`am start --user current -W -a com.android.settings.action.SETTINGS_SEARCH`;
`android.settings.DISPLAY_SETTINGS` tests a normal Settings page. These activity
launches affect the user's foreground UI; run them only during agreed debugging.
Do not clear logs or app data. Compare new timestamps and exit records rather
than interpreting the entire historical buffer as a new run.

```sh
python3 scripts/diagnostics/settings-search-test.py -v
python3 scripts/diagnostics/settings-search.py \
  --adb /path/to/platform-tools/adb --serial EXACT_AUTHORIZED_SERIAL \
  --out /private/task-directory/new-capture
```

The collector performs bounded read-only commands against that explicit serial;
it does not launch UI, pair, root, remount, install, alter settings or reboot.
Output is private (directory 0700, files 0600), refuses an existing directory,
records command failures and hashes, and reserves 40 GiB host free space plus
128 MiB capture budget. Exit zero means collection completed, **not** that search
works. An empty buffer is inconclusive. Historical package/PID/timestamp matching
prevents unrelated library crashes from being classified as this failure.
The nine parser checks and actual 13-command device capture passed.

## Shared footprint and correction experiment

The 2026-10-21 retained-tree audit inspected **248 APKs**, including 48 with
embedded native libraries. Three are ARM64-only: Settings Intelligence,
Voice Access and YourWidget. All embedded ELF headers agree with their ABI
folder names. The 471 external ARM ELF files are confined to the expected
Houdini/Berberis guest directories. This is a static exposure inventory, not a
claim that all three apps crash. APEX contents, downloaded libraries and apps
installed after the retained image need separate runtime coverage.

```sh
python3 scripts/diagnostics/native-footprint.py \
  --root /private/retained-ruby/fs --out /private/new-footprint.json
```

Two alternatives were built and tested against Ruby, keeping the signed apps,
kernel, data format and enforcing policy intact. Neither is release qualified.

### Rejected: Ruby's shipped alternate translator

The first experiment selected `libndk_translation.so` and its existing guest
libraries. A property-only attempt exposed an init `mounton` denial. Labeling
only `/system/lib64/arm64` as `system_file` (and adding an exact directory rule
to `plat_file_contexts`) fixed that mount without changing compiled policy.
The corrected image is
`e28abe2988e345b14e3f03b20e2a3a9b9695edadd4e51a62df4cac3d78e0f32d`.
Its two text-file changes and one directory label passed exact metadata/content
comparison, `checkfc`, AVB and all six logical-payload readbacks.

Runtime testing **rejected** this candidate: the ARM probe had 15 passing and
four failing groups before a fatal `SIGILL` in `frecpe d0,d0`. Sequentially
consistent atomics violated the ordering test 137,431 times in 200,000 trials.
ABI reporting, counter/ID-register behavior and signal semantics also failed.
The native control completed with 18 passes and two architecture-specific skips.
Search no longer showed the original ELF mismatch in the captured logs, but it
ANRed and restarted; results/navigation were not verified. Twenty launch/input
attempts are not twenty successful search cycles. Evidence:
`ndk-vm-results.json` and `ndk-probe-log.txt` in the evidence directory.
The builder retains this mode only behind `--reproduce-rejected-ndk`.

### Experimental: source-built AOSP17 Digitalis

The next experiment uses the existing source-built AOSP17 Digitalis bundle,
not a downloaded proprietary translator. Bundle manifest SHA-256:
`b1e2e2f7d5883fa650510fc5faef59824b7f1d7de02a536f38b8e78cbcf88604`;
bridge SHA-256:
`75e51d4de98bfd926996435216c19ff0d43596883b6060bcffa18198348c0f5e`.
The 74-file bundle matches the retained AOSP product outputs. Its import,
Apache-2.0 license review and source patches are documented in `docs/digitalis.md`.
Those earlier AOSP results do not qualify this Ruby integration.

`digitalis-overlay.py` verifies every bundle hash and inventory entry, selects
`libberberis_arm64.so`, installs its matching guest environment and runners,
and replaces Ruby's existing Berberis init rule. It removes the previous guest
library directory contents instead of mixing incompatible libraries. Of 70
created paths, 42 recreate existing paths; there are 28 net-new paths (including
one directory), and 370 old guest paths are not recreated. The exact filesystem
diff covers 445 changed file paths; metadata rows change from 7,292 to 6,608.
Unrelated content/metadata, all APKs, compiled SELinux policy, kernel, partition
layout and protected data ranges are verified unchanged.

Parent synthetic image:
`554fb78970f94d985c8be86f4b07c42c5f64ea9823eac33816a993a5d88dffe6`.
Digitalis experimental image:
`dd69a06f00de8873a6d7c3fc9276302ddad8fc4ac62f49db793fdee76017a1a8`.
AVB, all six logical readbacks, source immutability and exact metadata/content
checks passed. The five boot variants carry coherent new AVB digests and the
actual 4,032-byte vbmeta size. This image has no installer and is **not for
physical deployment**.

On Ruby/TCG the ARM probe completes: **17 pass, 3 fail**. Atomics, ID-register
reads and scalar/vector reciprocal-estimate regressions now pass; native x86_64
completes **18 pass, 0 fail, 2 skip**. Remaining failures are NaN semantics,
SIGILL signal metadata and `Build.CPU_ABI=x86_64` in an ARM64 app. Ruby does not
contain our AOSP ART CPU_ABI compatibility patch. Its public-source rationale
is Android's removal of deprecated CPU_ABI updates in ART commit
`b7947b064177a2fd65e8d80059bf49fd3fed12f5`, checked in the local primary-source
checkout; the web endpoint was unavailable. Copying an AOSP ART library into
Ruby without qualifying its interface is not a completed fix.

Search UI launches and accepts input, but observed process restarts and missing
result-navigation evidence prevent a pass. ANRs include startup, service and
input timeouts with guest CPU pressure around 89–96%; this does not establish
that translation is their cause. A manual cleared `display` query accepted all
letters but showed **No results**. Absence of the original ELF error does not
prove that Icing loaded or indexing works. The fresh VM script also accumulated
query text across reused activities; the next harness revision explicitly clears
it and rotates `display`, `bluetooth`, and `keyboard`. These harness improvements
are not retroactive test results. See the runtime evidence for final collection
status and the retained-data rehearsal.

The fresh observation stopped at its 1,800-second bound during final log output;
the completion marker was not reached. All 20 launch/input attempts were
observed, with missing/replaced search PIDs. Settings/system-server control
samples kept system_server PID 803; no fatal system-server signal was present
in the collected logs. The USB logger completed its separate ten-minute capture.
Neither a full log stream nor a crash-free search soak is claimed. Exact
results: `digitalis-fresh-runtime.json` and `digitalis-retained-runtime.json`.

The exact synthetic RB01 encrypted-data fixture was prepared with the new
system and VM diagnostic vendor image. Output SHA-256:
`1bc520a025d3d81cc05ff89862c59edb18fd421a2abd039778d2bf5331215ddf`.
It booted in a 502.2-second observation using a copied software TPM, verified
the same persistent fscrypt policy as its predecessor, and repeated the ARM
17/3 and native 18/0/2 results. Source image, source TPM and internal decoy were
unchanged; no system-server fatal signal or zygote exit was observed. Search
still ANRed. This run was deliberately stopped after boot/probe collection and
one search attempt; it is not a completed search soak or a PIN/owner-app test.
The preparation remains `complete=false` / `requires_installer_rebind=true`.

The builder imports PR #123 helper files at
`ca0335c2ae06062cc6b45560b3b57a3b304e6c01`, verified by a checked-in hash lock.
It accepts only the exact synthetic parent and regular private images, verifies
all metadata/content differences and readbacks, and preserves its source.
EROFS/AVB UUID/salt may vary; each actual output hash is recorded. VM
instrumentation is a separate copy, marked `not_for_release`; only the existing
vendor diagnostic script is replaced, with our open-source JNI probes embedded.
It has no physical device or guest network access.

## Qualification and release requirements

Update 2026-10-22: the translator and Google's Icing library now pass on the
G14 itself (section above). No corrected *system image* has run on the G14.
The laptop has since moved to RB-20261021-01, whose USB **Update** entry keeps
data and whose **Restore** entry returns to the previous system. That is now the
expected delivery path: the next Ruby release is RB-20261021-01 plus this
overlay. The overlay builder is still pinned to the synthetic RB01 parent and
must be rebased onto that release's inputs. The hardware gates below then run
after Update, with Restore available.

**Release, 2026-10-22:** B Honey approved the release, and RB-20261021-02 (ANAL-252) was built from RB-20261021-01's candidate with this overlay. `build-bridge-candidate.py` and `bridge-vm-input.py` now copy unchanged partitions out of the reviewed parent.

- In the instrumented Ruby VM, Digitalis is selected and boot completes with the lid guard present. Over 20 search cycles there were no Settings Services crashes, ANRs or `libicing` load errors. ARM probe 17/3 as before.
- The synthetic laptop takes RB-20261021-01 → RB-20261021-02 with data kept, boots, and restores byte for byte.

The SanDisk write waits for a fresh backup of the stick and the identified-write confirmation.

The hardware ADB connection disappeared during the 2026-10-21 follow-up. The first instrumented VM also reproduced the
previously known system-server crash and checkpoint-commit reboot. Its JNI
installation failed because the test shell's temporary directory was not
writable; that harness error was corrected, and it is not a translator verdict.
Full functional results must be reviewed before release qualification.

Require the ARM64 JNI probe and native x86_64 control, both Settings search
entry points, typing/backspace/empty queries, result navigation, 20 consecutive
open/type/select cycles and five minutes without a new search crash or
Settings/system-server restart. Test `display`, `bluetooth` and `keyboard`,
restart with retained synthetic data, and cover Voice Access/YourWidget and the
ARM regression corpus. VM software rendering and physical AMD graphics must
be distinguished when assessing failures.

The next Ruby release must retain the existing live/logging, fresh-install and
saved-data migration USB choices. The system hash, AVB/initrds and installer
source pin change; no partition layout, kernel, firmware or data-format change
is intended. PR #123's preserving updater only authorizes the exact RB01
transition, so a new exact transition and matching installer must be qualified.
Never overwrite a configured USB with this synthetic image. Preserve an offline
backup, verify all protected bytes and rehearse boot/unlock/recovery first.
Automatic Ruby A/B rollback remains unavailable; the AOSP updater is separate.

The release hub owns the next numbered plan. Complete project census, actual
PR-head reconciliation, approval of the frozen plan, foreground build/tests,
and separate approval of the final checksum/operation/exact device are still
required. An experiment's successful build does not approve promotion.

Builds and tests keep a 40 GiB host reserve. The revised builder copies only
needed logical extents and releases extraction scratch before comparing a
second extraction. The VM observer records minimum free space and stops near
the reserve. Exact private cleanup manifests retain evidence of removed,
reproducible task-owned scratch; source/recovery/owner artifacts are preserved.
At this implementation handoff, 44.68 GiB was free; the lowest recorded VM
observation was 43.63 GiB. Completed disposable VM disks were removed only after
collection and an open-file check. `implementation-storage.json` records actual
before/after measurements separately from the earlier diagnosis-only record.

Ruby and its existing Google payloads stay local under the owner's existing
licensed use. No proprietary library or APK is redistributed. These experiments
do not patch Houdini, interpret its internal error code, or establish rights
to redistribute the shipped alternate translator. Only source/tooling and
sanitized evidence are published.

## Source checks (2026-10-21)

- [Android adb documentation](https://developer.android.com/tools/adb): explicit
  device selection, authorized connection and activity/shell diagnostics.
- [AOSP bug-report interpretation](https://source.android.com/docs/core/tests/debug/read-bug-reports):
  logcat/event timestamps, process identity and crash/ANR evidence.
- [Public Icing source](https://android.googlesource.com/platform/external/icing/+/refs/heads/main/):
  open-source embedded search engine; availability alone does not establish
  compatibility with the shipped proprietary APK.
- [Public Berberis README](https://android.googlesource.com/platform/frameworks/libs/binary_translation/+/refs/heads/main/README.md)
  describes a RISC-V guest on its main branch. The separately pinned Digitalis
  ARM64 fork is not an assumed upstream ARM64 product.
  Existing import, license inventory, patches and measured limits are in
  `docs/digitalis.md`; AOSP results remain separate from Ruby qualification.

- [AOSP Native Bridge README](https://android.googlesource.com/platform/art/+/refs/heads/main/libnativebridge/README.md):
  translation uses a separate guest linker and library environment.
- Local primary-source checkout: `device/google/cuttlefish`, commit
  `283645aacf6cdb56cc31a9362f54d412dbc132a1`, `shared/desktop/common_x86.mk`
  contains `ndk_translation_only`, `houdini_only` and combined modes. The web
  endpoint was unavailable during verification; this source observation does
  not establish redistribution rights for the referenced vendor binaries.
