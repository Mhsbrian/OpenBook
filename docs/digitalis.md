# Digitalis: Track A's arm64 native bridge (ANAL-181, ANAL-200)

As of 2026-10-18. **CONFIRMED** means we observed it in our own build logs, device logs or test output. **HYPOTHESIS** means a likely explanation we have not proven.

Digitalis (https://github.com/DigitalisX64) is an Apache-2.0 fork of AOSP's Berberis binary translator that adds an arm64 guest. It is the arm64 native bridge of OpenBook's Android 17 build: built from source in our tree, shipped in both products (`anybook_cf_x86_64_pc` and `anybook_g14_x86_64`), with our Android 17 port and three fixes. ANAL-181 chose it (2026-10-16); ANAL-200 ported and fixed it (2026-10-17). The app-by-app matrix is in [`COMPAT-MATRIX.md`](COMPAT-MATRIX.md) and the harness in [`compat-harness.md`](compat-harness.md).

## Status

- **It ships in both products** (CONFIRMED). `device/anybook/common/native-bridge` puts into the image:
  - ABI list `x86_64,arm64-v8a`, `ro.dalvik.vm.native.bridge=libberberis_arm64.so`;
  - binfmt_misc runners for arm64 executables;
  - 57 arm64 guest libraries;
  - 89 files, 30 MB, in `/system` (88 for the bridge, plus our self-check `openbook_bridge_check`).
- **arm64 apps get the Android 17 NDK** (CONFIRMED). The guest libraries come from our Android 17 tree. Every export of the host `libandroid`, `libbinder_ndk`, `libGLESv2` and `libnativewindow` is in the guest library. The only differences left are `__cfi_check` and libEGL's internal C++ symbols, which are not API. (With Android 16 guest libraries, `libandroid` alone lacked 43 exports.)
- **arm64-only apps run** (CONFIRMED, Cuttlefish desktop product, two runs from wiped data with identical outcomes). 15 of the 17 arm64-only entries run, which is 14 of the 16 apps, against 13/16 for libndk_translation on Google's image.
  - AAAAXY crashes the same way natively.
  - Element X fails the same way on both bridges (`JNI_GetCreatedJavaVMs`).
- **Three bugs are fixed** (CONFIRMED, [below](#the-three-bugs)): `MRS` of the ID registers (Tor VPN), bit-exact `FRECPE`/`FRSQRTE`, and `Build.CPU_ABI` for bridged apps (Fennec).
- **Speed** (CONFIRMED numbers, CoreMark arm64 / native x86_64): 0.394 (executable) and 0.399 (in an app) in Cuttlefish; 0.361 and 0.351 on the G14. On Google's emulator image the same bridge gives 0.300 / 0.298 and libndk_translation 0.457 / 0.456, so Digitalis reaches about 65% of libndk_translation's speed in the same VM.
- **Licensing is clean** (CONFIRMED). Everything is built from source. The only prebuilt among the bridge's files is AOSP's own toolchain `libc++.so`, the same library the x86_64 system ships. No Digitalis binary is in the image.
- **On the G14** (CONFIRMED, bare metal, Ryzen AI 9 HX 370): the bridge self-check passes all five verdicts, and the ARM apps check passes all five of its own; the arm64 probe app gives the same results as in Cuttlefish and QEMU ([On the G14](#on-the-g14-bare-metal)). An arm64 app in an enforcing boot is still unobserved.

## Why Digitalis

ANAL-181 recommended it for Track A, with conditions (2026-10-16):
- **It is the only redistributable option.** libndk_translation and libhoudini are proprietary, and upstream AOSP Berberis still has no arm64 guest product on `android17-release` (it has only `enable_riscv64_to_x86_64.mk`: no arm64 decoder, interpreter or translator). Without Digitalis, Track A would have no arm64 support, or only QEMU user mode.
- **Google's libndk_translation is the same framework, closed.** In the Desktop 37 image it reports `ro.berberis.version=16.0.0`, and its crash stacks show `berberis::` frames.
- **Nearly the same app coverage, and more correct in several areas** than libndk_translation ([Comparison](#comparison-with-libndk_translation)).

| Condition | Where it stands |
|---|---|
| Port it to Android 17 (the guest NDK must match the platform) | Done (ANAL-200): built against our Android 17 tree, NDK gap closed |
| Close the regressions that block real apps (Fennec, Tor VPN) and make `FRECPE` bit-exact | Done (ANAL-200) |
| Accept the speed gap or close it | Open: about 65% of libndk_translation in the same VM |
| Plan for bus-factor risk | Open: one maintainer wrote 692 of the fork's 716 commits; the project was about 6 months old in 2026-10 |

## What Digitalis is

| Repo (github.com/DigitalisX64) | Pinned commit | What it is |
|---|---|---|
| `platform_frameworks_libs_binary_translation` | `b6b7fc30` (2026-10-13) | The translator. Replaces AOSP `frameworks/libs/binary_translation` |
| `manifest` | `3969040d` (2026-08-05) | AOSP `android16-qpr2-release` plus `digitalis.xml` |
| `device_generic_goldfish` | `bbc2f1e4` | Stock goldfish plus the `sdk_phone64_x86_64_digitalis` product (8 commits, 4 files) |
| `digitalis` | `11062cb0` (2026-09-23) | Docs, test and benchmark tooling, Docker packaging |
| `sample_hello_digitalis` | `ce9aa116` | 158 Gradle sample apps (test suite; not used by the image build) |

- The translator fork is `android16-qpr2-release` plus 716 commits. It changes 230 files (139 new, 91 modified, 0 deleted; +210,027/−87 lines). Commit authors: utzcoz 692, Artem Smirnov 23, kuloPo 1 (CONFIRMED, checked 2026-10-16).
- Three translation tiers: an interpreter, a "lite" JIT and a "heavy" optimizer.
- App-specific workarounds, which add maintenance risk: Qt plugin-path injection into the guest `environ`; a redirect of `/system/bin/linker64` opens to the guest linker; rewriting of `/proc/self/maps` for linker introspection; in-APK library extraction to `cache/berberis_extract`.
- Operational notes: it logs at debug level on every 100th translation (about 1,200 `trans#` lines per Fennec launch), and `libberberis_arm64.so` stays mapped in x86_64 app processes too, so "the bridge is mapped" says nothing about which ABI ran.

## How it is built

The bridge is part of the normal product build (`scripts/aosp-build.sh`). Nothing is installed by hand.

- **Source:** `aosp/patches/frameworks/libs/binary_translation/IMPORT` replaces AOSP's `frameworks/libs/binary_translation` (android17-release, `1290e88c`) with the Digitalis fork at `b6b7fc30`, fetched from GitHub once, on the host, by `aosp-docker.sh` (`aosp-patches.sh --fetch`). `scripts/aosp-patches.sh` makes the import a reproducible commit on the pin and applies our patches on top. Other branches' runs of `aosp-patches.sh` put the project back on its pin, as they do for any branch's patches.
- **Guest world:** `frameworks/libs/native_bridge_support` (the guest bionic, the NDK stub libraries and the proxy trampolines), bionic and the framework all come from our Android 17 tree. That is what closes the NDK gap: guest and host libraries must come from the same tree.
- **Our patches** (`aosp/patches/frameworks/libs/binary_translation/`):
  1. `libberberis_runtime_library_headers`: the android17-release name and path of the runtime library header, which Android 17's `native_bridge_support` includes.
  2. An unused variable that Android 17's clang (`clang-r584948b`) rejects under `-Werror`.
  3. `MRS` of the ID registers.
  4. Bit-exact `FRECPE`/`FRSQRTE`.
- **ART patch** (`aosp/patches/art/`): `libnativebridge` sets `Build.CPU_ABI` and `CPU_ABI2` for bridged apps again (the Fennec fix).
- **Device:** `device/anybook/common/native-bridge/`:
  - `native-bridge.mk` inherits Digitalis's `enable_arm64_to_x86_64.mk` and adds `openbook_bridge_check`;
  - `BoardConfig.mk` sets `TARGET_NATIVE_BRIDGE_ARCH=arm64` (Cuttlefish's `vsoc_x86_64_only` board already sets it);
  - `pc.mk`, `anybook_cf_x86_64_pc.mk` and both BoardConfigs include them.
- **Why not merge android17-release into the fork:** a trial merge gives 64 conflicting files and 219 renames (a `cpu_emulation/` restructure; most conflicts in `cpu_emulation/backend/x86_64` and the arm64 `kernel_api`, `guest_os_primitives`, `runtime` and `native_bridge` code). Upstream android17-release has no arm64 translator; its new arm64 pieces are infrastructure that overlaps the fork's. Building the fork's translator against the Android 17 tree needs only patches 1 and 2. A full merge is worth doing when Digitalis itself moves to Android 17.
- **Cost** (2026-10-17): adding the bridge to an existing `out/` took 11 min 35 s at `-j28`, with the container's memory peaking at 57.7 GB (cgroup `memory.peak`). A first G14 build with the bridge took 29 min 31 s.
- **Host tests:** Digitalis's suite (`berberis_arm64_host_tests`) builds and runs in the build container from the same tree: 3,761 of 3,763 tests pass, 2 are skipped and none fail (2026-10-17).

## The three bugs

### 1. `MRS` of the ID registers (Tor VPN, Go)

**Symptom.** Tor VPN died of SIGILL at `mrs x0, id_aa64isar0_el1` under both bridges.

Go's `golang.org/x/sys/cpu` reads `ID_AA64ISAR0/ISAR1/PFR0` when it can't read `/proc/self/auxv`, and Android apps can't read it. A real arm64 kernel traps these EL0 reads and returns sanitised values (`emulate_mrs` in `arch/arm64/kernel/cpufeature.c`). Digitalis emulated only `MIDR_EL1`, while advertising `cpuid` in its emulated `/proc/cpuinfo`.

**Fix (patch 3).** `guest_id_registers_arm64.h` holds the guest CPU's identity in one place:
- `AT_HWCAP`, which gains `HWCAP_CPUID`;
- the values of `MIDR`/`MPIDR`/`REVIDR` and the `ID_AA64*` registers, built the way the kernel builds them: visible fields from the features the translator implements, hidden fields at the kernel's safe value;
- the rest of the feature ID space (CRm 2–7) reads as zero, and everything outside it still raises SIGILL, as on Linux.

The interpreter and the lite tier return these values. The heavy tier leaves such regions to the lite tier, as it did for `MIDR`.

`ID_AA64ISAR0_EL1` = `0x211120` (AES+PMULL, SHA1, SHA2, CRC32, LSE), matching `AT_HWCAP` = `fp asimd aes pmull sha1 sha2 crc32 atomics cpuid`.

**Result** (CONFIRMED): Tor VPN runs; the probe's `isa/mrs_cpuid_registers` passes; the probe's `regress` group checks 9 ID registers and their agreement with `AT_HWCAP` field by field, as the kernel derives HWCAPs.

### 2. `FRECPE` / `FRSQRTE` bit-exactness

**Symptom.** `FRECPE(1.0)` returned `0x3f800000`, where every Arm CPU returns `0x3f7f8000`.

All three tiers computed full-precision `1/x` and `1/sqrt(x)`. The special cases were wrong too:
- `FRSQRTE(+0)` gave NaN, where Arm gives +inf with DZC;
- NaN payloads were not propagated;
- `FPCR.FZ`, `DN` and `RMode` and the FPSR flags were ignored.

**Fix (patch 4).** `guest_fp_estimate_arm64.h` implements the Arm ARM's `FPRecipEstimate`, `FPRSqrtEstimate`, `RecipEstimate` and `RecipSqrtEstimate` for half, single and double precision.
- **Interpreter:** uses it directly.
- **Lite tier:** does the normal case inline per lane: a table lookup on the top fraction bits plus the result exponent, which needs neither FPCR nor FPSR. Any other lane (zero, denormal, infinity, NaN, negative `FRSQRTE` input, an `FRECPE` whose result would be denormal) calls the shared code out of line, with the caller-saved host registers saved around the call.
- **Heavy tier:** leaves vector `FRECPE`/`FRSQRTE` to the lite tier; it had no scalar forms.
- Digitalis's host tests that asserted the exact reciprocals now assert the Arm values. The tier-coverage table records the heavy tier's change.

**Result** (CONFIRMED):
- **The header against QEMU 11.1:** 0 mismatches in 189,200 cases. That covers scalar and vector, f16/f32/f64, `URECPE`/`URSQRTE`, and FPCR 0/FZ/DN/FZ|DN/RP/RM/RZ/FZ16, with edge cases and 2,000 random inputs per form.
- **On the device** (`scripts/compat/digitalis/fp-estimate.sh device`, an arm64 executable through binfmt_misc): 0 of 154,000 lines differ from QEMU under `two-gear`, `lite-translate-or-interpret` and `interpret-only`. Each input runs 50 times, so the JIT tiers translate the loop.
- **Probe:** `neon/frecpe_bit_exact` passes, and the `regress` group compares scalar and vector forms with QEMU golden values, including FPSR.

### 3. Fennec's SIGSEGV at `libxul.so+0x2b32da0`: not a translation bug

**What happens.** `Preferences::InitializeUserPrefs()` dereferences a NULL `Preferences` object. Gecko's `Preferences::GetInstanceForService()` had failed and dropped it, because `InitInitialObjects()` could not load the default preferences:
- GeckoView exports `MOZ_ANDROID_CPU_ABI` from `android.os.Build.CPU_ABI`;
- Gecko reads `<abi>/greprefs.js` from its omnijar, and then `greprefs.js`;
- the arm64 APK's `omni.ja` holds only `arm64-v8a/greprefs.js`, and `Build.CPU_ABI` was `x86_64`.

The `nsZipArchive` log shows the two failed lookups repeated about 970 times, then the crash.

**Why the ABI was wrong.** libnativebridge used to set `Build.CPU_ABI`/`CPU_ABI2` from the bridge's `getAppEnv()`, and Digitalis reports `arm64-v8a`. AOSP removed that in android17-release (art `b7947b0641`, May 2025: "deprecated since API 21").

**libndk_translation is affected too** (CONFIRMED). On Google's image the same two lookups fail. Its Gecko thread then spins at 100% CPU, and only the Java UI stays up, so a "RUNS" verdict for Fennec there means only "the process is alive". Under Digitalis the NULL dereference is fatal instead. Berberis's `HandleFatalSignal` catches the fault, so debuggerd writes no tombstone and the harness reports EXITED rather than CRASH.

**Fix** (`aosp/patches/art/0001-…`). Restore the two fields in `SetupEnvironment()`, as before android17-release.

**Result** (CONFIRMED): arm64 Fennec runs; Gecko logs "chrome startup finished" and runs its tab, content and GPU processes as arm64; it renders a page served over `adb reverse`, with JavaScript running. The probe's `regress/build_cpu_abi_is_native_abi` checks the field for the arm64 and x86_64 probes.

**Gotcha for future bisections.** Interpret-only mode at first seemed to fix the crash, which pointed at the JIT, and a lite-tier bisection by instruction class and library offset followed. Those runs were only slow enough to miss the crash inside a 20–25 s window, and app data left over between runs changed the timing. Clear app data per run, and confirm a "fix" survives a long wait.

## Results on our image (2026-10-17)

`anybook_cf_x86_64_pc-cp2a-userdebug` (`CP2A.260605.016`) in Cuttlefish (`scripts/compat/cf.sh`, `COMPAT_TARGET=cf`) with 6 vCPUs, 8 GiB and SwiftShader: the same resources, corpus, probes and harness as the emulator baselines. Two runs from wiped data gave identical outcomes.

### Apps

| App | Our build (Digitalis A17) | libndk_translation, Google image (ANAL-180) | Digitalis A16 overlay (ANAL-181) |
|---|---|---|---|
| OpenBook probe arm64 | RUNS, 18 pass / 2 fail (20 groups) | RUNS, 15/4 (19 groups) | RUNS, 16/3 |
| VLC, KOReader, Lichess, LocalSend, Godot, Ogre, Wesnoth, OsmAnd, GCompris, TIC-80, Tux Paint | RUNS | RUNS | RUNS |
| SimpleX | RUNS (window still black at 15 s) | RUNS (same) | RUNS (same) |
| **Fennec 158** | **RUNS** (Gecko works) | RUNS, but Gecko spins at 100% CPU | EXITED (SIGSEGV) |
| **Tor VPN** | **RUNS** | CRASH (SIGILL, `MRS`) | CRASH (SIGILL) |
| AAAAXY | CRASH (as natively) | CRASH | CRASH |
| Element X | CRASH (`JNI_GetCreatedJavaVMs`) | CRASH | CRASH |
| **arm64 apps alive at 15 s** | **14 / 16** | 13 / 16 | 12 / 16 |

- **Probe failures left** are the two known semantic differences: x86 NaN rules (`isa`: sNaN priority, default-NaN sign) and the SIGILL `si_code` (`signals`).
- **Launch times** (`am start -W`) are in the same range as libndk_translation's on the emulator: Fennec 0.62 s, Lichess 1.2 s, OsmAnd 1.0 s. They come from different VMs, so we don't compare them closely.

### CPU speed (CoreMark, 600k iterations, 3 interleaved rounds, quiet host)

| Bridge, image, VM | exe arm64 / x86_64 | apk arm64 / x86_64 |
|---|---|---|
| **Digitalis A17, our image, Cuttlefish** | **0.394** (16,870 / 42,839 it/s) | **0.399** (16,181 / 40,568) |
| Digitalis A17, Google's image, emulator | 0.300 (12,155 / 40,546) | 0.298 |
| libndk_translation, Google's image, emulator | 0.457 (18,516 / 40,532) | 0.456 |
| Digitalis A16, Google's image, emulator (ANAL-181) | 0.298 | 0.304 |
| **Digitalis A17, our image, on the G14** (bare metal, Ryzen AI 9 HX 370; "balanced", on mains; 2026-10-18) | **0.361** (10,012 / 27,724) | **0.351** (9,902 / 28,205) |

- Every round passed CoreMark validation, and the CoreMark binaries are the harness's own (`scripts/compat/build-probes.sh`). The spread between rounds is under 1%.
- The emulator rows with our A17 bridge use the bridge collected from the product (`scripts/compat/digitalis/bundle.sh`) and installed on Google's image ([Running Digitalis on Google's emulator image](#running-digitalis-on-googles-emulator-image)). The port neither helped nor hurt speed there.
- **HYPOTHESIS:** Cuttlefish passes the host's CPU features to the guest (`avx2 bmi1 bmi2 fma movbe adx avx512f`), the emulator's guest has none of these, and the translator selects code by host CPU features.
- **The G14 does not confirm "Cuttlefish or better":** its Zen 5 has the same features and gives 0.361 / 0.351. So CPU features alone don't explain Cuttlefish's 0.394. More HYPOTHESES: the ratio depends on the microarchitecture; or on which core ran the benchmark. The HX 370 has 4 Zen 5 and 8 Zen 5c cores, and native CoreMark there was 27.7k it/s against 37–43k in VMs on the build host's 7950X, which fits a Zen 5c core or the "balanced" power profile. The rounds were steady (within 1%), so each round probably ran on the same kind of core. Pinning each run to a known core would settle it.
- Digitalis's own published numbers (Geekbench 6 at 21–22% of native, its `docs/RELEASE_NOTES.md` of 2026-08-16) point the same way. CoreMark is integer-only and the VMs run SwiftShader, so these numbers say nothing about GPU-bound behaviour (`docs/compat-harness.md`).

## Comparison with libndk_translation

ANAL-181 ran both bridges on the same image (`google/sdk_gdesktop_x86_64/emu64xa:17/CLE1.260506.004`), same emulator (37.2.12), same 6 vCPUs, same corpus, 15 s wait, two runs each from wiped data (2026-10-16). Digitalis was then the upstream Android 16 build:

| Class | libndk_translation | Digitalis A16 (2026-10-16) |
|---|---|---|
| seq_cst store→load ordering (store-buffering test) | **FAIL**: about 2,000 of 200,000 | **PASS**: 0 of 200,000 |
| `MRS` ID registers | `MIDR_EL1` and `ID_AA64ISAR0_EL1` both SIGILL | `MIDR_EL1` emulated (`0x410fd034`); `ID_AA64ISAR0_EL1` SIGILL |
| x86 NaN rules | default NaN negative (`0xffc00000`); qNaN beats sNaN; `FMAX(qNaN,1)` returns the default NaN | default NaN still negative; qNaN still beats sNaN; **`FMAX` propagates the NaN** |
| `CNTVCT_EL0` rate | about 429× too fast (`CNTFRQ` 10.49 MHz) | **correct**: `CNTFRQ` 19.2 MHz, counter/wall = 0.999 |
| `uname -m` for arm64 code | `x86_64` | **`aarch64`** |
| SIGILL `si_code` | `SI_QUEUE` (−1) | `SI_QUEUE` (−1) |
| `FRECPE` estimate | bit-exact (`0x3f7f8000`) | returned exactly 1.0 (`0x3f800000`) |
| Advertised `HWCAP` | fp asimd aes pmull crc32 atomics | adds sha1 and sha2 |
| Element X (`JNI_GetCreatedJavaVMs`) | crash | crash; the probe finds it via `dlopen(libnativehelper)`, but not through `RTLD_DEFAULT` |
| SimpleX black window | black at 15 s | black at 15 s |

Our A17 build fixes the `MRS` and `FRECPE` rows and adds `cpuid` to `HWCAP` ([The three bugs](#the-three-bugs)); its probe fails only `isa` (x86 NaN rules) and `signals` (SIGILL `si_code`). The other 14 probe groups pass under both bridges: JNI, crypto, TLS, threads, syscalls, dlopen, C++ exceptions, JIT and memfd dual mapping, GLES 3.0 and Vulkan 1.3. Neither bridge has an arm32 guest, and the image is 64-bit only, so armeabi-v7a apps don't install.

Digitalis's own Android 16 reference image (`sdk_phone64_x86_64_digitalis`) gave the same arm64 outcomes, probe results and speed (0.295× / 0.297×) as the Android 16 overlay on Google's Android 17 image, so those results belonged to Digitalis itself, not to the mix. Gotcha on that image: emulator 37.2.12 segfaults with the virtio-gpu GL transport our harness forces for the Desktop image; it boots with the default transport (`COMPAT_GLTRANSPORT=`).

## License and provenance of what ships

`scripts/compat/digitalis/audit-shipped.py` lists every bridge file in a product's `PRODUCT_OUT`. For each file it records:
- the Soong module that installs it and its source directory (`module-info.json`);
- whether that source is under `prebuilts/`;
- its SHA-256;
- the licenses the image's own `NOTICE.xml.gz` gives for it, classified by their text.

Both products: 89 files each from the same modules, 1 prebuilt, 1 not covered by NOTICE (2026-10-17).

| What | Source | License (NOTICE) | Verdict |
|---|---|---|---|
| Translator, proxies, exec region, program runners | `frameworks/libs/binary_translation` (Digitalis fork plus our patches), built from source | Apache-2.0 | **OK** |
| binfmt_misc entries, `berberis.rc`, `ld.config.arm64.txt` | the fork's `prebuilt/` directory (text configs, not binaries) | Apache-2.0 | OK |
| Guest stub libraries, guest linker, `app_process64`, vdso | `frameworks/libs/native_bridge_support` (Android 17), built from source | Apache-2.0 | OK |
| Guest bionic, ICU, SQLite, zlib, BoringSSL, libpng, FreeType, liblzma, BLAS, RenderScript, libutils, liblog, … | AOSP projects, built from source for arm64 | Apache-2.0, BSD, MIT, ISC, zlib, Unicode, libpng, SQLite blessing, netlib BLAS | OK: the same projects ship natively in every AOSP image |
| `lib64/arm64/libc++.so` | `prebuilts/clang/host/linux-x86` (AOSP's LLVM toolchain) | not listed in `NOTICE.xml.gz` | OK. Apache-2.0 WITH LLVM-exception; the x86_64 `/system/lib64/libc++.so` is missing from NOTICE too, so this is an AOSP-wide gap, not ours |
| `openbook_bridge_check` | `device/anybook/common/native-bridge/check` | Apache-2.0 (OpenBook) | OK |
| `libnativebridge.so` (ART APEX) | `art` plus our patch | Apache-2.0 | OK |

- "GPL" appears in the NOTICE text of ICU and FreeType. It comes from build-tool files in those projects (autoconf/pkg-config macros, a collision-detection tool), and the x86_64 copies carry the same text. No GPL code is compiled into the bridge.
- Our patches carry Apache-2.0 headers ("The OpenBook Authors").

**The fork's own source** (ANAL-181 audit, CONFIRMED):
- The translator fork is Apache-2.0: 95 new files carry "Copyright (C) 2026 utzcoz" Apache headers, the rest AOSP headers. Its only binaries are upstream test fixtures, not built into the image.
- No copied third-party code turned up: a search of the fork's added lines for GPL/LGPL, QEMU, box64, FEX, dynarmic, SPDX tags, foreign copyright lines and "ported from" found only internal derivation comments.
- 20 new files have no license header (tests and the generated syscall table). Minor; ask upstream to add them.
- **Keep out:** `sample_hello_digitalis` carries third-party prebuilts for its test apps, including `libmsaoaidsec.so` (proprietary MSA OAID SDK, no license); the `digitalis` entry repo's `apkmirror_fetch` tooling downloads proprietary APKs and re-signs merged bundles. Neither is needed to build or run the bridge, and our corpus stays F-Droid only.
- No CLA or DCO. Development is agent-driven (the project's README and `CLAUDE.md` describe a Claude Code agent loop). That doesn't block Apache-2.0 use; the copyright status of AI-assisted code is an open legal question the owner knows about.
- Android and Berberis are Google trademarks, and Digitalis disclaims any affiliation. OpenBook must not imply Google endorsement either.

## On the G14 (bare metal)

### The self-check

`openbook_bridge_check` is an arm64 static binary, built from source in the tree as the bridge's guest architecture. It is installed as `/system/bin/arm64/openbook_bridge_check`; fsgen puts native-bridge modules on the system partition only. binfmt_misc runs it through the translator, and it prints one JSON result per check:
- `bridge-exec`: it ran as arm64;
- `bridge-id-registers`: 9 registers, no SIGILL, agreement with `AT_HWCAP`;
- `bridge-fp-estimates`: 6,900 golden cases from QEMU, with FPSR;
- `bridge-int-simd`: CRC32 and NEON FMA against references computed in the program.

`su 0 openbook-hwtest bridge` adds the configuration (`bridge-config`: the property, both binfmt_misc entries, the guest libraries) and passes the results on as `HWTEST` lines. The live image's "save logs" entry runs it with the other checks, and `scripts/installer/live-report.py` turns the lines into the verdicts `bridge_config`, `bridge_exec`, `bridge_id_registers`, `bridge_fp_estimates` and `bridge_int_simd`.

The check needs no network or user input and changes nothing. It passes in all three translation modes on Cuttlefish, as root and as the shell user, and under QEMU's `-cpu max` and `-cpu cortex-a53` (a real ARM CPU model), which validates the check itself.

**Enforcing policy.** `berberis.rc` mounts binfmt_misc and registers the runners in early-init. The Cuttlefish product inherits Cuttlefish's two rules for that; the PC products carry the same two rules in `device/anybook/common/pc/sepolicy/vendor/init.te` (ANAL-159). Without them, enforcing boots log `mount binfmt_misc ... Permission denied` and arm64 executables can't run, while app libraries still load through libnativebridge. **Gotcha:** the "save logs" entry is permissive, so its verdicts can't catch an enforcing-only gap like this one.

**Results on the G14** (CONFIRMED, 2026-10-17 and 2026-10-18; ROG Zephyrus G14 GA403WR, BIOS GA403WR.309, Ryzen AI 9 HX 370, family 0x1a, model 0x24):
- All five `bridge_*` verdicts pass: 57 guest libraries; `uname` `aarch64`, `AT_HWCAP` 0x9fb; `MIDR` 0x410fd034, `ISAR0` 0x211120; 0 wrong of 6,900 `FRECPE`/`FRSQRTE` cases; CRC32 and NEON FMA correct. Every block was translated by the JIT tiers (`jit=N interp=0`).
- Zygote starts with `-XX:NativeBridge=libberberis_arm64.so` in every boot, and no enforcing boot logged a denial naming binfmt_misc, berberis or a native-bridge path.
- The ARM apps check (below) passes all five of its verdicts. The arm64 probe gives the same results as in Cuttlefish and QEMU: `regress` passes (the ID registers, `FRECPE(1.0)`=`0x3f7f8000`, `Build.CPU_ABI`), `neon` passes, `isa` fails only on the x86 NaN rules and `signals` only on the SIGILL `si_code`. The x86_64 control passes 18 of 18, with 2 skips. CoreMark: 0.361 (executables) and 0.351 (in the app).
- **No arm64 app has been seen in an enforcing boot.** The apps used in normal sessions were all x86_64, and no app process outside the add-on logged a berberis translation line.

### The ARM apps check add-on (probe and CoreMark on the laptop)

The live stick has no adb and no arm64 app, so the probe and CoreMark go on the stick as an add-on. It uses the same live-init hook as the graphics check (`androidboot.openbook.addon=NAME`), and its entry is "OpenBook ARM apps check". It boots like "save logs". Once Android is up, the stick's own `openbook-live-init` unpacks the payload into the stick's `/data` and runs `scripts/compat/digitalis/stick/run.sh` as root. The run takes about 6 minutes in QEMU and 9 on the G14:
- `openbook_bridge_check`;
- the compat probe as arm64 and as x86_64 (the control);
- CoreMark, 600k iterations, 3 interleaved rounds, as executables and inside the probe app, as `run-bench.sh` runs it.

Afterwards it uninstalls the two probe apps, puts the keep-screen-on setting back, saves the results next to the boot's logs and powers off. The laptop's disks are never touched.

```bash
scripts/compat/build-probes.sh                                           # probe APKs and CoreMark (NDK r30)
scripts/compat/digitalis/stick/make-bridge-check.sh openbook-bridgecheck-<date>      # -> <data dir>/installer/out/NAME-addon (5 MB)
scripts/installer/inst-docker.sh "$PWD"/scripts/compat/digitalis/stick/add-to-image.sh IMG <data dir>/installer/out/NAME-addon   # mtools
scripts/compat/digitalis/stick/bridge-qemu.sh NAME RUN [LIVE_IMAGE]      # QEMU/KVM test on a copy of a live image
python3 -I scripts/compat/digitalis/stick/bridge-report.py <live-NNN>    # report-bridge.{json,md}
```

- **Image files only.** `add-to-image.sh` refuses block devices. A stick is written from the finished image with `scripts/installer/write-stick.sh`.
- **Verdicts:**
  - `addon_ran`: the payload checks out, `run.sh` returns 0, cleanup leaves no probe app;
  - `bridge_check`;
  - `probe_x86_64`: no failure;
  - `probe_arm64`: installed as `arm64-v8a`, `Build.CPU_ABI` is `arm64-v8a`, and no failed group beyond `isa` and `signals`, the two known differences;
  - `coremark_valid`: every run passes CRC validation.

  The report also gives the CoreMark ratios for executables and in the app. It keys on the installed ABI and `Build.CPU_ABI`, not on whether `libberberis_arm64.so` is mapped, because the bridge is mapped in x86_64 processes too.
- **In QEMU/KVM** (`-cpu host`, 8 vCPUs on the build host, 2026-10-17): all five verdicts pass, CoreMark 0.362 / 0.372. That is a VM on a busy host, not the laptop.
- **On the laptop:** boot "OpenBook ARM apps check" once, on mains power with the lid open, and leave it for about 10 minutes until it powers off. Results: `openbook/logs/live-NNN/addon-bridge*` on the stick.

## Running Digitalis on Google's emulator image

For like-for-like comparisons with libndk_translation, the bridge can be overlaid on Google's AOSP Desktop (Preview) 37.0 emulator image. `scripts/compat/digitalis/install.sh` uses a separate AVD, `anybook-digitalis`, built from the same system image, so the baseline AVD is never modified.

```bash
scripts/compat/digitalis/bundle.sh [PRODUCT_OUT] [OUT]                                # our A17 bridge -> ~/anybook/digitalis/bundle-a17
scripts/compat/digitalis/install.sh ~/anybook/digitalis/bundle-a17 -o <out dir>       # overlay onto the emulator AVD (port 5580)
COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system scripts/compat/run-matrix.sh -o <dir> --keep-emulator
COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system scripts/compat/run-bench.sh -o <dir> --keep-emulator
python3 -I scripts/compat/side-by-side.py libndk_translation <baseline-run> Digitalis <digitalis-run>
```

`install.sh`:
1. Wipe-boots with `-writable-system`.
2. Runs `adb remount`. The first remount disables verity and needs a reboot. The upper layer then lives on `/mnt/scratch`, an overlayfs on `/system` and `/vendor`.
3. Replaces `/system/{lib64,bin}/arm64` (libndk_translation's guest world) with Digitalis's, and pushes the translator, proxies, runners and configs.
4. Sets `ro.dalvik.vm.native.bridge=libberberis_arm64.so` and `ro.berberis.flags=disable-ir-check` in `/system/build.prop` (the image ships `accurate-sigsegv` for libndk_translation; `disable-ir-check` is what Digitalis's own product sets).
5. Reboots and verifies: zygote starts with `-XX:NativeBridge=libberberis_arm64.so`, binfmt_misc `arm64_dyn` points to `berberis_program_runner_binfmt_misc_arm64`, arm64 apps log `Initialized Berberis (aarch64)`, and the x86_64 control probe still passes.

Gotchas:
- `adb push` lands files as 0666, and init then refuses the binfmt entries with "Skipping insecure file". `install.sh` re-applies the bundle's modes.
- A data wipe also drops the overlay, so every fresh run reinstalls.
- The translator needs only `liblog`, `libandroid`, `libdl_android`, `libc++`, `libc`, `libm` and `libdl`, which is why an Android 16 build loads on the Android 17 image. Its guest libraries then lag the platform, a mix Digitalis's docs call unsupported.

**The upstream Android 16 build** (what ANAL-181 evaluated; not needed for OpenBook's own build):

```bash
scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/sync.sh             # ~/anybook/digitalis/aosp16
DIGITALIS_JOBS=16 scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/build.sh modules
DIGITALIS_JOBS=24 scripts/compat/digitalis/docker.sh /repo/scripts/compat/digitalis/build.sh full   # m + m emu_img_zip
```

- **Container:** the `anybook-aosp` image (Ubuntu 24.04). `docker.sh` mounts `~/anybook/digitalis` read-write and the shared AOSP mirror **read-only**, both at their host paths, so git alternates resolve on both sides.
- **Sync** (`sync.sh`, about 53 min, 115 GB): `repo init` on the Digitalis manifest at `3969040d` with `--reference` to the local AOSP mirror. `manifests/digitalis/digitalis-pinned.xml` pins the four Digitalis projects and switches them to https, because upstream uses `git@github.com:` URLs and floating branches. It also drops `sample_hello_digitalis`, which uses git-LFS and breaks `repo` checkout in the container.
- **Build** (`build.sh modules`): `lunch sdk_phone64_x86_64_digitalis-trunk_staging-userdebug`, then `m` on the 70 packages that `enable_arm64_to_x86_64.mk` installs (expanded by make from `berberis_config.mk` and `native_bridge_support.mk`, not hard-coded). About 44 min at `-j16` on a loaded host, peak RSS 26 GB. The bundle is the 74 files in `BERBERIS_DISTRIBUTION_ARTIFACTS_ARM64`.
- **Full image** (`build.sh full`): about 1 h 22 min at `-j24`, peak RSS 12 GB, `out/` 96 GB. Its 74 bridge files are byte-identical to the module build's.

## Open issues

- **Not fixed, by design:** x86 NaN semantics (default-NaN sign, sNaN priority), the SIGILL `si_code`, Element X's `JNI_GetCreatedJavaVMs`, and AAAAXY (a crash in the app itself).
- **The `Build.CPU_ABI` patch changes Android 17 behaviour back to Android 16's.** It affects every bridged app, as intended. An upstream AOSP report (art `b7947b0641`) would be outward-facing and is for the owner to decide.
- **Upstream reports to Digitalis** (`MRS`, `FRECPE`) wait for the owner's OK. The patches stay in this repo; none was sent anywhere.
- **Speed:** about 65% of libndk_translation in the same VM. The heavy tier leaves regions with vector `FRECPE`/`FRSQRTE` to the lite tier, which costs nothing on CoreMark but may cost a little in NEON-heavy code with estimates (HYPOTHESIS, not measured).
- **The emulated `/proc/cpuinfo`** lists `fphp asimdhp asimdrdm lrcpc dcpop asimddp`, but `AT_HWCAP` and the ID registers do not. The conservative `AT_HWCAP` is what code that probes features uses; the mismatch predates our changes.

## Next

1. An arm64 app in an **enforcing** G14 boot. The default boot has no arm64 app, and the add-on runs permissive. A small arm64 app preinstalled on the live image, or a device agent (ANAL-194), would close this.
2. A like-for-like libndk_translation baseline on the G14. It is proprietary and lives only in Google's images, so it can't go on ours. Google's AOSP Desktop emulator image under KVM on the G14's own Linux would give one (device loop, ANAL-194/195).
3. Why the G14 ratio is 0.36 and Cuttlefish's 0.39: pin CoreMark to a Zen 5 core and to a Zen 5c core in the add-on (`taskset`), and record the core each run used. Low priority.
4. Merge android17-release into the fork once Digitalis tracks Android 17, or do it ourselves (64 conflicts).
5. Upstream reports to DigitalisX64 and AOSP, after the owner's OK.
6. A SIMD/JIT micro-benchmark: CoreMark alone may understate the heavy optimizer's NEON work.
