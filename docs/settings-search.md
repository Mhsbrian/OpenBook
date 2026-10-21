# Ruby Settings search failure (ANAL-234)

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

Ruby already includes `libndk_translation.so`, its corresponding 57 guest
libraries, runners and init rules. The smaller first correction selects that
existing bridge instead of introducing the Digitalis fork. The translation
binary and signed APKs remain byte-identical. The secondary-layout property
must stay true: it makes Ruby's existing init rule bind its Berberis guest
libraries onto `/system/lib64/arm64`.

The first property-only VM demonstrated why that change is insufficient:
enforcing SELinux denied init's `mounton` on that directory, labeled
`system_lib_file`. The revised experiment labels **only that directory** as
`system_file`, for which the existing policy permits init's mount. An exact
`-d` entry in `plat_file_contexts` keeps the label consistent with restorecon.
The contained libraries keep their original labels; compiled policy, SELinux
enforcement and dm-verity remain unchanged. No permissive domain or general
mount permission was added.

The source parent is RB01's synthetic pre-installer input,
`554fb78970f94d985c8be86f4b07c42c5f64ea9823eac33816a993a5d88dffe6`.
The corrected experimental image is
`e28abe2988e345b14e3f03b20e2a3a9b9695edadd4e51a62df4cac3d78e0f32d`.
Its verified changes are two text files (`build.prop`, `plat_file_contexts`)
and the one directory label. The 3,464 files/links and 7,292 metadata rows were
compared against that exact allowlist. All six logical payload readbacks match
the AVB-verified inputs; GPT and protected partitions match the parent.
`checkfc` accepts the corrected contexts against the retained camera25 policy.
The five boot variants have matching AVB digests and actual 4,032-byte vbmeta
size. This experiment has no installer and is **not a release or deployment
candidate**.

`scripts/googlebook/build-bridge-candidate.py` verifies the helper files from
PR #123 commit `ca0335c2ae06062cc6b45560b3b57a3b304e6c01` against its local
hash lock. It accepts only the exact RB01 parent, works on regular private
images, verifies all metadata/content differences and readbacks, and preserves
the original. EROFS/AVB output UUID/salt can differ between executions; the
manifest records each actual output hash. The VM instrumentation is a separate
copy, with an open-source JNI test script replacing the existing serial
probe. It is explicitly marked `not_for_release`, uses synthetic userdata and
has no network or physical block-device access.

## Qualification and release requirements

The hardware ADB connection disappeared during this follow-up. No corrected
image has been run on the G14. The first instrumented VM also reproduced the
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

Ruby and its existing Google payloads stay local under the owner's existing
licensed use. No proprietary library or APK is redistributed. This correction
does not patch Houdini, interpret its internal error code, or establish rights
to distribute `libndk_translation`. Digitalis remains a separately qualified
open-source alternative, not the implementation of this experiment.

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
