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

## Proposed fix and acceptance plan

This is the requested investigation and plan for review. No runtime fix or image
has been built. Preferred experiment: integrate OpenBook's existing **open-source
Digitalis ARM64 bridge** with Ruby, preserving the signed Settings package and
all three native libraries. Its previous AOSP/G14 results are useful starting
evidence, but do not qualify it for Ruby's ART, linker namespaces and SELinux.

1. **Freeze a disposable experiment.** Pin the current Ruby parent image and
   its full hashes, OpenBook integration source, guest-library bundle and bridge
   build. Start from the existing import
   `b6b7fc30f5e1cb2d2b9b465e3fdaa905616c31dc` plus the reviewed Android 17
   patches in `aosp/patches/frameworks/libs/binary_translation/`. Check Ruby's
   native-bridge ABI, linker/guest-library dependencies and strict SELinux
   compilation before packaging. Use synthetic userdata. Keep the release
   hub's current candidate and owner data out of this experiment.
2. **Change translation as a coherent set.** Provide the compatible bridge,
   guest libraries and linker configuration, and select it for ARM64 apps.
   Pin every changed input. Avoid a one-library Icing swap: the package has two
   other ARM64 libraries and its exact JNI/protobuf compatibility with public
   Icing has not been established. A matching, legitimately available native
   x86_64 package would be a separate alternative requiring its own identity,
   signing, version and permission review.
3. **Rehearse before hardware.** Ruby requires AVX-VNNI absent from this Zen 4
   host; reuse the established TCG-capable Ruby VM lane. First run the ARM64 JNI
   probe and x86_64 control. Then test both search entry points, rapid typing,
   backspace, empty query, repeated open/close, result navigation, and restart
   with retained synthetic search data. Require 20 consecutive open/type/select
   cycles, correct results for `display`, `bluetooth` and `keyboard`, and five
   minutes without a new search crash, ANR or Settings/system_server restart.
   Compare native Settings navigation and the existing ARM-app regression corpus.
4. **Prepare a release only after evidence.** Report the complete diff, hashes,
   successful tests and failures to ANAL-232 for a numbered Ruby release plan.
   A bridge change can affect every ARM64 app. Assume system/boot/AVB and
   installer pin impact until the actual packaging proves otherwise; no intended
   partition-layout, data-format or firmware change. Check preserving-update
   support and rehearse recovery; Ruby has no qualified automatic A/B rollback.
5. **Hardware acceptance.** After approval of the exact final image, operation,
   device and current backup/recovery plan, deploy via the Ruby procedure and
   repeat the search tests on the G14, including physical typing and reboot.
   Verify PIN, apps and data retention. Do not use the AOSP A/B updater for Ruby.

The proposed experiment has no measured disk budget yet. Before building,
calculate peak additional allocated space and keep at least 40 GiB free at every
phase. Approximately 53 GiB was available during diagnosis, which is not blanket
permission for another full image/VM copy. Preserve recovery baselines, candidate
images and evidence; clean only this task's completed reproducible scratch.

Houdini's log explicitly names a commercial license restriction. This plan does
not patch that library or infer rights to reuse/redistribute it. Ruby and Google
package artifacts remain private under the owner's existing authorized use;
any new proprietary input needs its licensing settled before inclusion. Public
AOSP source has not been matched to this Google Settings package version.

## Source checks (2026-10-21)

- [Android adb documentation](https://developer.android.com/tools/adb): explicit
  device selection, authorized connection and activity/shell diagnostics.
- [AOSP bug-report interpretation](https://source.android.com/docs/core/tests/debug/read-bug-reports):
  logcat/event timestamps, process identity and crash/ANR evidence.
- [Public Icing source](https://android.googlesource.com/platform/external/icing/+/refs/heads/main/):
  open-source embedded search engine; availability alone does not establish
  compatibility with the shipped proprietary APK.
- [Public Berberis README](https://android.googlesource.com/platform/frameworks/libs/binary_translation/+/refs/heads/main/README.md)
  describes a RISC-V guest on its main branch. The ARM64 candidate above is the
  separately pinned Digitalis fork, not an assumed upstream ARM64 product.
  Existing import, license inventory, patches and measured limits are in
  `docs/digitalis.md`; AOSP results remain separate from Ruby qualification.
