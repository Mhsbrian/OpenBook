# ARM64 Chromium native services — 2026-10-19 (ANAL-224)

## Result and scope

The `20261019.armfix1` G14 product passes **32/32 compatibility checks in
QEMU**, enforcing. The unchanged ARM64 Chromium 158.0.8111.0 APK renders
JavaScript and canvas on three pages even with native-only renderers explicitly
enabled. Android selects the browser's declared managed renderer after checking
identical access and sandbox requirements. Unsupported native-only services
without a supported managed fallback fail promptly. ARM64 remains enabled.

This is a prepared image, not a physical G14 result. The laptop was observed
running `20261019.photos1` in slot A. No update was staged on it in this task.
The candidate preserves its installed base, including Quire and RADV's YV12 fix.

The original G14 failure was an ARM64 library loaded by the x86_64 native
framework, followed by repeated 60-second waits on the shared process-start
worker. The issue's prior attachment recorded 12 matching native crashes and
131,976 socket retries. Chromium's own fallback changes native zygote policy,
not service families, so rejecting the bind alone would not restore rendering.
See `docs/arm-native-services.md` for the implementation and primary sources.

## Image and footprint

- Integration tree: [`f72c1753ced270a3a7ad41a07e70ecd1d516030f`](https://github.com/Mhsbrian/OpenBook/tree/f72c1753ced270a3a7ad41a07e70ecd1d516030f),
  retained on `anal-224/g14-armfix1`.
- Installed base tree: `d3e04fd` (`photos1`).
- Pinned frameworks/base: `94b4c163b7df`; after the ten integration patches:
  `a55456682cad`.
- Successful build: `build.txt`, 13m30s, 52.6 GB container memory peak.
- Package: `openbook-ota-20261019-armfix1.zip`, 994,547,625 bytes.
- SHA-256: `fb95dcc49c2af455d2f847bba4814e823f5cf35a6e41953dcb60542ec52ab944`.
- vbmeta: `1a8a2bd1aef13e738230988a1e17fb32b8c56e36732b9882da76789bb5a94930`.
- `framework.jar` grows 316 bytes; `services.jar` grows 1,868 bytes.
- All 86 bridge/ARM guest files, 30,393,207 bytes total, are byte-identical.
- Kernel, RADV, compositor, bootsync and core bridge hashes are unchanged.
  See `binary-comparison.json`, `bridge-comparison.json` and the individual
  hashes in `bridge-files.json`.
- Test APKs and Chromium are not added to the image or redistributed here.

The package, matching bootsync, target-files and OTA tools are retained on the
build host under `~/anybook/ota/`. The `packages/` manifests identify them.
The `-broken` manifest describes a deliberately unbootable **test-only** image.

## Compatibility evidence

The test host is a Ryzen 9 7950X running the installed G14 product through KVM,
q35 and OVMF. Test disks are disposable copies. Input APK hashes are in
`compat/inputs.json`; the browser APK came from the installed device without
its data. Test pages are local and contain no user content.

| Check | Result |
|---|---|
| Old `photos1` image | Correctly flagged ARM64 native-only service bind accepted; the expected failing behavior (`baseline/`) |
| Candidate rejection, three launches | Bind false in 5, 1, 1 ms; isolated managed ARM64 JNI returns 42 |
| Service lifecycle | No native-zygote prewarm or accumulated rejected service records |
| Compatible renderer alias | ARM64 JNI returns 42 and callback retains original component |
| Incompatible permission alias | Refused |
| Actual framework policy and direct API guards | 27/27 assertions pass, including UID/package/process/permission/isolation and ABI cases |
| Native x86_64 control | Native-service bind remains eligible; no child launched by this control |
| Existing ARM64 probe | 18 pass, 2 known failures: `isa`, `signals` |
| Existing x86_64 probe | 18 pass, 0 fail, 2 skip |
| ARM executable/ISA check | 4/4, including 6,900 FP-estimate cases with zero bad results |
| Chromium renderer, three navigations | JavaScript result 42; canvas RGBA `[0,170,68,255]`; screenshot visually checked |
| Settings cold starts during Chromium test | 0.841, 0.954, 0.885 s |
| Chromium launch path | Six managed alias resolutions, isolated managed renderers present |
| Failure signatures | Zero ELF mismatches, exhausted zygote waits or socket retries |

`compat/checks.json` and `compat/driver.log` are the final complete run.
`compat/zygote-log-excerpt.txt` retains relevant ActivityManager messages;
`compat/renderer.png` shows the rendered local test page.

An initial fixture linked against SDK staging resource IDs and did not actually
set `nativeService`. Those observations were discarded and the baseline and
candidate repeated with the image's `framework-res.apk`. The fixture now checks
the resolved service flag before binding. A separate host-control launch entered
the wrong test mode; clearing the task and explicitly selecting and recording
the mode corrected that harness failure. Neither required an image change.

ARMv7 and generic native-only ARM services remain unsupported. This does not
claim complete browser coverage, an ARM application certification suite, fixed
instruction/signal behavior, or physical G14 validation.

## Installed-disk OTA rehearsal

**36/36 pass**, starting from the saved `photos1` slot-A state that matches the
observed laptop image. The harness and update utility come from the exact
integration tree. The PIN/app/setting/file baseline is the existing synthetic
installer fixture; no user data was copied from the laptop.

| Case | Checks | Result |
|---|---:|---|
| A → B upgrade | 13/13 | Correct candidate digest, enforcing, data intact, merge complete, boot HAL and ESP agree, no update-domain denial |
| Deliberately broken boot | 13/13 | Three panics, automatic return to A with data intact; subsequent good update boots B and merges |
| Power cut during write | 10/10 | A boots with data intact; repeating the update succeeds, B boots and merges |

`qemu/results.json` and `qemu/SUMMARY.md` collect the results. Each case retains
checks, driver/update logs and a compressed serial log with the VM serial
redacted. The `-broken` package is for this test only and must never be sent to
the G14. Static validation also passed: ShellCheck, Python compilation, and
applying the production patch with whitespace errors rejected. The PR's ten
framework patches match the built integration's series byte for byte.
