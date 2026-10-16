# Digitalis evaluation: an open arm64→x86_64 native bridge for Track A (ANAL-181)

Status as of 2026-10-16. **CONFIRMED** means we observed it in our own build logs, device logs or test output. **HYPOTHESIS** means a likely explanation we have not proven.

Digitalis (https://github.com/DigitalisX64) is an Apache-2.0 fork of AOSP's Berberis binary translator that adds an arm64 guest. We built it from source, installed it as the native bridge of the same AOSP Desktop 37.0 emulator image used for the libndk_translation baseline (ANAL-180), and ran the same corpus, probes and CoreMark benchmark on it.

As a control, we also built and booted Digitalis's own reference image (`sdk_phone64_x86_64_digitalis`, AOSP 16) and ran the same tests there.

## Recommendation for Track A: GO, with conditions

Use Digitalis as Track A's arm64 bridge. Carry it as a pinned fork, and ship it as the default bridge only after the conditions below are met.

Why go:
- **It is the only redistributable option.** libndk_translation and libhoudini are proprietary, and upstream AOSP Berberis still has no arm64 guest product on `android17-release`. Without Digitalis, Track A would have no arm64 support, or only QEMU user mode.
- **The licensing is clean.** Everything that goes into the image is Apache-2.0 or ordinary AOSP licensing, built from source. No prebuilt binary from the Digitalis repos ends up in the image (see the license audit below).
- **It builds and runs.** The 70 native-bridge modules build from source in 44 minutes, and the full reference image in 82 minutes. Overlaid on Google's Android 17 image, zygote loads it, binfmt_misc runs arm64 executables, and apps launch. Its own AOSP 16 image gives the same results.
- **Nearly the same app coverage as libndk_translation.** 12 of 16 arm64-only F-Droid apps stay alive under Digitalis, against 13 under libndk_translation; Fennec is the only difference. AAAAXY also crashes natively, so for translation it is 12 of 15 against 13 of 15. Two runs from wiped data gave identical outcomes.
- **It is more correct in several areas.** Digitalis fixes 4 of libndk_translation's 8 failing probe checks: seq_cst ordering, `CNTVCT_EL0` rate, `uname`, and FMAX NaN propagation. It adds 1 new failure (`FRECPE`).

Conditions before it becomes the default:
1. **Port it to Android 17.** Digitalis tracks AOSP 16 (`android16-qpr2-release`). This is more than a rebuild:
   - **API gap:** its guest libraries come from the same tree, so on an Android 17 system arm64 apps see the Android 16 NDK. Exports present in A17 but missing from the guest: 43 in `libandroid`, 15 in `libbinder_ndk`, 10 in `libmediandk` (finding 7). Google's A17 libndk_translation guest has all of the `libandroid` and `libbinder_ndk` ones.
   - **Merge conflicts:** a trial merge of upstream `android17-release` into the fork gives 64 conflicting files plus 219 upstream renames (a `cpu_emulation/` restructure).
   - **Overlap:** upstream A17 also adds its own arm64 guest pieces (`kernel_api/arm64`, `guest_abi/arm64`, `runtime/arm64_to_x86_64`), which overlap with Digitalis.

   Estimate: days, not hours.
2. **Close the regressions that block real apps.** Two app failures matter:
   - **Fennec** works on libndk_translation but dies under Digitalis. This is a translation bug at `libxul.so+0x2b32da0`, reproduced on Digitalis's own image.
   - **Tor VPN** still dies on the unemulated `MRS ID_AA64ISAR0_EL1`. Any Go-based library hits this.

   `FRECPE` also needs to be bit-exact.
3. **Accept the speed gap or close it.** CoreMark under Digitalis runs at **0.30× native**, against **0.45×** for libndk_translation on the same image the same day, so Digitalis is about 34% slower. libndk_translation is 1.5× faster. Digitalis's own image gives the same 0.30×.
4. **Plan for bus-factor risk.** One maintainer wrote 692 of the 716 fork commits, and the project is about 6 months old.

## What Digitalis is (checked 2026-10-16)

| Repo (github.com/DigitalisX64) | Pinned commit | What it is |
|---|---|---|
| `platform_frameworks_libs_binary_translation` | `b6b7fc30` (2026-10-13) | The translator. Replaces AOSP `frameworks/libs/binary_translation` |
| `manifest` | `3969040d` (2026-08-05) | AOSP `android16-qpr2-release` plus `digitalis.xml` |
| `device_generic_goldfish` | `bbc2f1e4` | Stock goldfish plus the `sdk_phone64_x86_64_digitalis` product (8 commits, 4 files) |
| `digitalis` | `11062cb0` (2026-09-23) | Docs, test and benchmark tooling, Docker packaging |
| `sample_hello_digitalis` | `ce9aa116` | 158 Gradle sample apps (test suite; not used by the image build) |

**CONFIRMED** (git history against our local AOSP mirror):
- The translator fork is `android16-qpr2-release` plus 716 commits. It changes 230 files (139 new, 91 modified, 0 deleted; +210,027/−87 lines).
- Commit authors: utzcoz 692, Artem Smirnov 23, kuloPo 1.
- Upstream Berberis on `android17-release` still has only `enable_riscv64_to_x86_64.mk`. It has no arm64 decoder, interpreter or translator.
- Google's libndk_translation in the Desktop 37 image reports `ro.berberis.version=16.0.0`, and its crash stacks show `berberis::` frames. So it is Google's closed arm64 build of the same framework.

Digitalis has three translation tiers: an interpreter, a "lite" JIT and a "heavy" optimizer. It also contains app-specific workarounds, which add maintenance risk:
- Qt plugin-path injection into the guest `environ`.
- A redirect of `/system/bin/linker64` opens to the guest linker.
- Rewriting of `/proc/self/maps` for linker introspection.
- In-APK library extraction to `cache/berberis_extract`.

## Build from source

```bash
scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/sync.sh             # ~/anybook/digitalis/aosp16
DIGITALIS_JOBS=16 scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/build.sh modules
scripts/compat/digitalis/install.sh -o evidence/<date>-digitalis                     # overlay onto the emulator
COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system scripts/compat/run-matrix.sh -o <dir> --keep-emulator
COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system scripts/compat/run-bench.sh -o <dir> --keep-emulator
python3 -I scripts/compat/side-by-side.py libndk_translation <baseline-run> Digitalis <digitalis-run>
# Control: Digitalis's own AOSP 16 reference image
DIGITALIS_JOBS=24 scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/build.sh full   # m + m emu_img_zip
scripts/compat/digitalis/a16-avd.sh                                                  # AVD anybook-digitalis-a16
COMPAT_AVD=anybook-digitalis-a16 COMPAT_GLTRANSPORT= scripts/compat/run-matrix.sh -o <dir> --keep-emulator
```

- **Container:** the existing `anybook-aosp` image (Ubuntu 24.04). `docker.sh` mounts `~/anybook/digitalis` read-write and the shared AOSP mirror **read-only**, both at their host paths, so git alternates resolve on both sides.
- **Sync** (`sync.sh`, 53 min, 115 GB): it runs `repo init` on the Digitalis manifest at `3969040d` with `--reference` to the ANAL-167 mirror, which already holds `android16-qpr2-release` history. Prebuilts are shallow, using the same split as the A17 tree. `manifests/digitalis/digitalis-pinned.xml` pins the four Digitalis projects and switches them to https, because upstream uses `git@github.com:` URLs and floating branches. It also drops `sample_hello_digitalis`, which uses git-LFS and breaks `repo` checkout in the container. The pinned manifest is `evidence/2026-10-16-digitalis/manifest-pinned.xml.gz`.
- **Build** (`build.sh modules`): `lunch sdk_phone64_x86_64_digitalis-trunk_staging-userdebug`, then `m` on the 70 packages that `enable_arm64_to_x86_64.mk` installs. The package list is expanded by make from `berberis_config.mk` and `native_bridge_support.mk`, not hard-coded.
  - **44 min** wall clock at `-j16`, with another AOSP build running on the host (load 70–150).
  - Peak RSS 26 GB (Soong).
  - 19,997 ninja actions.
  - `#### build completed successfully ####`.
- **Bundle:** the 74 files in `BERBERIS_DISTRIBUTION_ARTIFACTS_ARM64`, with none missing:
  - the translator `libberberis_arm64.so` (3.0 MB);
  - 22 proxy libraries and `libberberis_exec_region`;
  - 2 program runners;
  - 43 guest arm64 libraries plus `linker64` and `app_process64`;
  - linker, init and binfmt configs.

  `MANIFEST.txt` and `SHA256SUMS` are in the evidence.
- **Full image** (`build.sh full`, the control): `m` plus `m emu_img_zip`.
  - 1 h 22 min at `-j24`. 136,569 actions, of which the 20k from the module build were already done. Peak RSS 12 GB.
  - `out/` is 96 GB.
  - The 74 bridge files it produces are byte-identical to the module build's.
- **Dependencies:** the translator needs only `liblog`, `libandroid`, `libdl_android`, `libc++`, `libc`, `libm` and `libdl`. That is why an A16 build loads on the A17 image.

We made **no source changes** to Digitalis.

## Install on the AOSP Desktop 37.0 emulator

`install.sh` uses a separate AVD, `anybook-digitalis`, built from the same system image, so the baseline AVD is never modified. Steps:

1. Wipe-boot with `-writable-system`.
2. `adb remount`. The first remount disables verity and needs a reboot. The upper layer then lives on `/mnt/scratch`, an overlayfs on `/system` and `/vendor`.
3. Replace `/system/{lib64,bin}/arm64` (libndk_translation's guest world) with Digitalis's.
4. Push the translator, proxies, runners and configs.
5. In `/system/build.prop`, set:
   - `ro.dalvik.vm.native.bridge=libberberis_arm64.so`
   - `ro.berberis.flags=disable-ir-check`. The image ships `accurate-sigsegv` for libndk_translation; `disable-ir-check` is what Digitalis's own product sets.
6. Reboot and verify.

What we verified (**CONFIRMED**, `evidence/2026-10-16-digitalis/install.txt`):
- zygote starts with `-XX:NativeBridge=libberberis_arm64.so`.
- binfmt_misc `arm64_dyn` points to `berberis_program_runner_binfmt_misc_arm64`.
- arm64 apps log `Initialized Berberis (aarch64), version 16.0.0`.
- The x86_64 control probe still passes all 17 applicable groups.

Gotchas we hit:
- `adb push` lands files as 0666, and init then refuses the binfmt entries with "Skipping insecure file". `install.sh` re-applies the bundle's modes.
- A data wipe also drops the overlay (checked), so every fresh run reinstalls.

**Caveat:** this runs AOSP 16 guest libraries and proxies on an Android 17 image, a mix Digitalis's docs call unsupported. Two consequences:
- **The guest API level lags the platform.** arm64 apps see the Android 16 NDK surface (finding 7).
- **Some results could come from the mix rather than from Digitalis.** To rule that out, we ran the control below.

### Control: Digitalis's own AOSP 16 reference image

`build.sh full` builds `sdk_phone64_x86_64_digitalis-trunk_staging-userdebug`, a stock phone emulator product. Its build fingerprint is `Android/sdk_phone64_x86_64_digitalis/emu64xa:Baklava/BP4A.251205.006`, it uses ANGLE as GLES, and Digitalis is built in. `a16-avd.sh` boots it with the same hardware settings (6 vCPU, 8 GB).

- **GL transport:** with the virtio-gpu GL transport our harness forces for the Desktop image, emulator 37.2.12 segfaults on this image. It boots in 18 s with the default transport (`COMPAT_GLTRANSPORT=`), and guest Vulkan still works there (ANGLE runs on it).
- **Result (CONFIRMED, `evidence/2026-10-16-digitalis/a16-control/`):** every arm64 outcome and every probe result matches the Android 17 overlay:
  - 12/16 apps alive;
  - Fennec arm64 dies at the same guest PC;
  - Tor VPN and Element X fail the same way;
  - probe 16 pass / 3 fail with the same 3 failures;
  - CoreMark 0.295× / 0.297× native.
- **One difference, outside translation:** the **x86_64** Fennec control also crashes on this image. It throws `java.lang.NoSuchMethodError` on the hidden `MessageQueue.next()`, which the Android 16 framework lacks, and then hits `MOZ_CRASH`. That is a Fennec-vs-Android-16 problem, not a translation one.

So the Fennec arm64 crash, the probe results and the speed belong to Digitalis itself, not to the A16-on-A17 overlay.

## Results, side by side

Same image (`google/sdk_gdesktop_x86_64/emu64xa:17/CLE1.260506.004`), same emulator (37.2.12), same 6 vCPU, same corpus, 15 s wait, both runs from wiped data.
- libndk_translation: `evidence/2026-10-15-compat/run{1,2}`.
- Digitalis: `evidence/2026-10-16-digitalis/run{1,2}`.

Each bridge's two runs agree on every outcome (`repro-check.txt` in each evidence directory).

The `harness=` field in the Digitalis runs' `env.txt` shows pre-squash commit IDs (`4311e70-dirty`, `2743710-dirty`). The scripts that ran are the ones in this PR.

### Apps

| App | arm64 via libndk_translation | arm64 via Digitalis | Notes |
|---|---|---|---|
| OpenBook probe | RUNS, 15 pass / 4 fail | RUNS, 16 pass / 3 fail | See the probe table |
| OpenBook probe armeabi-v7a | INSTALL_FAIL | INSTALL_FAIL | The image is 64-bit only, and Digitalis has no arm32 guest either |
| VLC 3.7.1 | RUNS | RUNS | |
| **Fennec F-Droid 158.0.0** | RUNS | **EXITED (SIGSEGV)** | Digitalis regression, see finding 6 |
| KOReader | RUNS | RUNS | |
| Lichess (Flutter) | RUNS | RUNS | |
| LocalSend (Flutter + Rust) | RUNS | RUNS | |
| Godot 4 | RUNS | RUNS | |
| Ogre Sample Browser | RUNS | RUNS | |
| Wesnoth | RUNS | RUNS | |
| OsmAnd~ | RUNS | RUNS | |
| GCompris (Qt 6) | RUNS | RUNS | |
| TIC-80 | RUNS | RUNS | |
| Tux Paint | RUNS | RUNS | |
| SimpleX Chat | RUNS, black window | RUNS, black window | Same black window at 15 s under both bridges, so it is probably not the translator (**HYPOTHESIS**) |
| AAAAXY | CRASH | CRASH | Same `NullPointerException` natively on x86_64 |
| **Tor VPN** | CRASH, SIGILL | CRASH, SIGILL | Both: `MRS X0, ID_AA64ISAR0_EL1` (`0xd5380600`) is not emulated |
| **Element X** | CRASH | CRASH | Both: `InternalException: Failed to find JNI_GetCreatedJavaVMs`; x86_64 runs |
| **arm64 apps alive at 15 s** | **13 / 16** | **12 / 16** | AAAAXY also crashes natively, so for translation: 13/15 against 12/15 |

All 7 x86_64 controls behave the same under both bridges.

One difference in the `native_bridge` column: under Digitalis, `libberberis_arm64.so` stays mapped in x86_64 app processes too, and it is unmapped under libndk_translation. So for Digitalis, that column means "the library is mapped", not "the app is translated". The arm64 rows also log `Initialized Berberis (aarch64)`.

### Probes and the baseline's failure classes

| Class (ANAL-180 finding) | libndk_translation | Digitalis |
|---|---|---|
| seq_cst store→load ordering (store-buffering test) | **FAIL**: 2,138 and 1,972 of 200,000 | **PASS**: 0 of 200,000 in both runs |
| `MRS` ID registers | `MIDR_EL1` and `ID_AA64ISAR0_EL1` both SIGILL | `MIDR_EL1` emulated (`0x410fd034`); **`ID_AA64ISAR0_EL1` still SIGILL**, even though the emulated `/proc/cpuinfo` lists `cpuid` |
| x86 NaN rules | default NaN negative (`0xffc00000`); qNaN beats sNaN; `FMAX(qNaN,1)` returns the default NaN | default NaN still negative; qNaN still beats sNaN; **`FMAX` now propagates the NaN** |
| `CNTVCT_EL0` rate | about 429× too fast (`CNTFRQ` 10.49 MHz) | **correct**: `CNTFRQ` 19.2 MHz, counter/wall = 0.999 |
| `uname -m` for arm64 code | `x86_64` | **`aarch64`** |
| SIGILL `si_code` | `SI_QUEUE` (−1) | `SI_QUEUE` (−1) |
| `FRECPE` estimate | bit-exact (`0x3f7f8000`) | **FAIL**: returns exactly 1.0 (`0x3f800000`), not ARM's estimate |
| Advertised `HWCAP` | fp asimd aes pmull crc32 atomics | adds sha1 and sha2 |
| Element X (`JNI_GetCreatedJavaVMs`) | crash | crash; the probe again finds it via `dlopen(libnativehelper)`, but not through `RTLD_DEFAULT` |
| SimpleX black window | black at 15 s | black at 15 s |

The other 14 groups pass under both bridges: JNI, crypto, TLS, threads, syscalls, dlopen, C++ exceptions, JIT and memfd dual mapping, GLES 3.0 and Vulkan 1.3.

### CPU speed (CoreMark, 600k iterations, 3 interleaved rounds)

Both bridges were measured on the same day on a quiet host (load 1.4–8.3). The Digitalis run is `evidence/2026-10-16-digitalis/bench`; the libndk_translation run is `evidence/2026-10-16-digitalis/bench-ndk` (a re-run of the baseline).

| Mode | x86_64 native, median it/s | arm64, libndk_translation | arm64, Digitalis | Digitalis / ndk |
|---|---|---|---|---|
| executable (binfmt runner) | 39,604 / 39,979 | 17,899 (**0.452×** native) | 11,908 (**0.298×** native) | 0.665 |
| in an app (native bridge) | 38,412 / 38,256 | 17,515 (**0.456×**) | 11,631 (**0.304×**) | 0.664 |

- Every run passed CoreMark validation. The spread between rounds is under 1% for both bridges.
- The re-run reproduces yesterday's libndk_translation baseline (0.457 / 0.453).
- An earlier Digitalis run under heavy host load (`bench-loaded`, load 16–85) gave 0.314 / 0.315, consistent with the quiet result.
- Digitalis's own published numbers (Geekbench 6 at 21–22% of native, `docs/RELEASE_NOTES.md` 2026-08-16) point the same way. The limits listed in `docs/compat-harness.md` apply: CoreMark is integer-only and runs on SwiftShader, so these numbers say nothing about GPU-bound behaviour.

Cold launch times (`am start -W`) are also slower under Digitalis. In run 2, for example, Lichess took 3.2 s against 1.9 s and LocalSend 4.4 s against 2.1–2.3 s. The host was still loaded during those runs, so we don't tabulate them.

## License and provenance audit

| Component | License | Binaries in it | Goes into a Track A image? | Verdict |
|---|---|---|---|---|
| Translator fork (`binary_translation`) | Apache-2.0. 95 new files carry "Copyright (C) 2026 utzcoz" Apache headers; the rest carry AOSP headers; `Android.bp` declares `Android-Apache-2.0` | Only upstream test fixtures: 8 `tiny_loader` ELFs and a PDF, byte-identical to AOSP. Not built into the image | Yes, built from source | **OK** |
| `native_bridge_support`, bionic and the guest libraries | AOSP (Apache-2.0, BSD, plus the usual third-party licenses: BoringSSL, ICU, zlib, SQLite, libc++) | none | Yes, built from source | **OK**. Ship Soong's NOTICE files with the image, as for any AOSP build |
| `device_generic_goldfish` fork | Apache-2.0 | none | Emulator product only | OK (reference) |
| `digitalis` entry repo | Apache-2.0 | none | No | OK. Its `apkmirror_fetch` tooling downloads proprietary APKs and re-signs merged bundles. **We do not use it**, and our corpus stays F-Droid only |
| `sample_hello_digitalis` | Apache-2.0 | Third-party prebuilts for test apps: libGDX/Bullet, Cronet jars, a MediaPipe model, ncnn, wireguard-go, and **`libmsaoaidsec.so` (proprietary MSA OAID SDK, no license)** | No | Keep it out of Track A. It is not needed to build or run the bridge |
| Build toolchain | AOSP prebuilts (clang, Go, JDK, …) at `android16-qpr2-release` | toolchains | No (build host only) | OK |

What we found in the audit (**CONFIRMED**):
- **Third-party code:** no copied third-party code turned up. We searched the fork's added lines for GPL/LGPL, QEMU, box64, FEX, dynarmic, SPDX tags, foreign copyright lines and "ported from"; every hit was an internal derivation comment.
- **Missing headers:** 20 new files have no license header (tests and the generated syscall table). That is minor; ask upstream to add them.
- **No CLA or DCO.** Development is agent-driven: the project's README and `CLAUDE.md` describe a Claude Code `/dispatch` agent loop, and 12 fork commits mention `CLAUDE.md` or `.claude/` scripts in their messages. That does not block Apache-2.0 use. The copyright status of AI-assisted code is still an open legal question, so the owner should know about it.
- **Trademarks:** Android and Berberis are Google trademarks, and Digitalis disclaims any affiliation. Track A must not imply Google endorsement either.

## Track A integration (Android 17)

- `device/google/cuttlefish/vsoc_x86_64_only/BoardConfig.mk` on `android17-release` already sets `TARGET_NATIVE_BRIDGE_ARCH := arm64` (and `TARGET_NATIVE_BRIDGE_ABI := arm64-v8a`). So `aosp_cf_x86_64_pc` needs only `$(call inherit-product, frameworks/libs/binary_translation/enable_arm64_to_x86_64.mk)` and the forked project, once it is ported.
- `device/google/cuttlefish/shared/desktop/common_x86.mk` already switches translators through `AL_BINARY_TRANSLATION_MODE`, using `inherit-product-if-exists` on Google's unbundled `vendor/unbundled_google/libs/ndk_translation`, which is not in AOSP. A `digitalis` mode fits the same switch.
- **Porting effort:** we trial-merged upstream `android17-release` into the fork (`b6b7fc30`, local only, not pushed). It gave 64 conflicting files and 219 renames. Most conflicts are in `cpu_emulation/backend/x86_64` (13 files) and in the arm64 `kernel_api`, `guest_os_primitives`, `runtime` and `native_bridge` code, where upstream added its own arm64 pieces.

## Findings

1. **Clean and redistributable (CONFIRMED).** Apache-2.0, built from source, and nothing prebuilt from Digitalis ships in the image. It is the only arm64 bridge that Track A can legally ship.
2. **One app fewer than libndk_translation (CONFIRMED).** 12/16 against 13/16; Digitalis loses Fennec. Both bridges fail Tor VPN and Element X the same way.
3. **Correctness differs (CONFIRMED).** Digitalis fixes seq_cst store→load ordering, `CNTVCT_EL0` rate, `uname` and FMAX NaN propagation. It adds an `FRECPE` estimate failure. It shares the `ID_AA64ISAR0_EL1` SIGILL, the x86 default-NaN sign and sNaN priority, and the `SI_QUEUE` code.
4. **Speed: about 34% slower than libndk_translation on CoreMark (CONFIRMED).** 0.30× against 0.45× native.
5. **`MRS ID_AA64ISAR0_EL1` is the most valuable single fix for both bridges (CONFIRMED symptom).** Go's `x/sys/cpu` falls back to the ID registers when `/proc/self/auxv` is unreadable, and the probe shows it is unreadable under both bridges. Digitalis even advertises `cpuid` in its emulated `/proc/cpuinfo` without emulating these registers. **HYPOTHESIS:** returning a synthetic `ID_AA64ISAR0_EL1` that matches `HWCAP` would fix Tor VPN and other gomobile apps.
6. **Fennec dies under Digitalis; it is a translation bug (CONFIRMED, root cause open).**
   - **Where:** the "Gecko" thread faults at `libxul.so+0x2b32da0` (arm64), `ldr x0, [x8, #0x8]`, where `x8` is a global (vaddr `0x97a95c0`) that reads as NULL right after `bl 0x2b33244` returns. Berberis reports the region start `…d9c` as the guest PC.
   - **Reproducibility:** it is the same in both processes of every launch: run 1, run 2 and Digitalis's own A16 image (`analysis/fennec-sigsegv.txt`).
   - **Not the app itself:** Fennec runs natively on x86_64 and as arm64 under libndk_translation on the same A17 image.
   - **Why the harness says EXITED:** Berberis's `HandleFatalSignal` catches the fault, so debuggerd writes no tombstone, and the harness reports EXITED instead of CRASH.
   - **Probably unrelated:** the `BAD proxy PRE-EXTRACT` lines before it are Digitalis's own heuristic logging. They fire when a proxied call's first pointer argument is below 0x10000. Fennec logs 1,257 such lines, but OsmAnd logs 220 and runs, so on their own they don't mean failure.
   - **HYPOTHESIS:** a missed store, or wrong ordering of a static initialisation, in a translated region. The probe's memory-ordering tests pass, so it isn't the store-buffering case.
7. **The guest NDK is Android 16 even on Android 17 (CONFIRMED, `analysis/ndk-api-gap.txt`).** We compared dynamic exports of the A17 host libraries with each bridge's arm64 guest libraries.

   | Library | Exports in the A17 host missing from the Digitalis guest | … missing from the libndk_translation guest |
   |---|---|---|
   | `libandroid` | 43 | 0 |
   | `libbinder_ndk` | 15 | 0 |
   | `libmediandk` | 10 | 1 |
   | `libaaudio` | 7 | 1 |
   | `libEGL` | 7 | 7 |

   The `libandroid` gap includes `AActivityManager_*`, `ANativeService_*`, `ANpuManager_*` and `android_getnetworkblockedreason`; Fennec 158 references the last one by name.
   - **Effect:** arm64 apps that look up newer APIs get NULL where x86_64 apps on the same device don't.
   - **Fix:** porting to A17 fixes this, because guest and host libraries must come from the same tree.
8. **Operational notes (CONFIRMED):**
   - It logs at debug level on every 100th translation (about 1,200 `trans#` lines per Fennec launch).
   - `libberberis_arm64.so` stays mapped in x86_64 processes.

## Next

1. Port the fork to `android17-release` on an OpenBook branch of Digitalis. Build it inside the Track A tree (`aosp_cf_x86_64_pc`, after ANAL-168), boot it in Cuttlefish, and re-run this matrix. Check that the API gap (finding 7) is gone.
2. Report findings 5 and 6, `FRECPE`, and the NaN and `si_code` differences upstream, with the probe and `analysis/fennec-sigsegv.txt` as reproducers. This is outward-facing, so it needs the owner's OK first.
3. Re-run cold-launch timings on a quiet host, and add a SIMD/JIT micro-benchmark. CoreMark alone may understate the heavy optimizer's NEON work.
