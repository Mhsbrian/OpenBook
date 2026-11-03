# ARM compatibility harness and libndk_translation baseline (ANAL-180)

This harness installs, launches and checks ARM-only APKs on an x86_64 Android desktop, and measures translated CPU speed. It runs on Google's AOSP Desktop (Preview) 37.0 x86_64 emulator image, whose native bridge is the proprietary `libndk_translation.so`, or on OpenBook's own Cuttlefish build with its Digitalis bridge (`COMPAT_TARGET=cf`). The current results per app are in [`COMPAT-MATRIX.md`](COMPAT-MATRIX.md); the Digitalis bridge is in [`digitalis.md`](digitalis.md).

**CONFIRMED** means we observed it in our own logs or test output. **HYPOTHESIS** means it is a likely explanation we have not proven.

## Running it

```bash
scripts/m0-emulator.sh                 # once: SDK, emulator, image and AVD (shared with M0)
scripts/compat/build-probes.sh         # toolchain (sha1-verified NDK r30, build-tools 37, platform 36, CoreMark) + probe APKs
scripts/compat/fetch-corpus.sh         # F-Droid APKs, sha256-verified (add --reselect to refresh the index and re-pick)
scripts/compat/run-matrix.sh --fresh   # wipe-boot the emulator, test every APK, stop the emulator
scripts/compat/run-bench.sh            # CoreMark: 3 interleaved rounds, 600k iterations
python3 -I scripts/compat/side-by-side.py <labelA> <runA> <labelB> <runB>   # two bridges or two runs, side by side
```

- Results go to `-o DIR`, by default `$OPENBOOK_EVIDENCE/<date>-compat/run-<time>` (`OPENBOOK_EVIDENCE` defaults to `~/anybook/evidence/openbook`), never inside the repository.
- `run-matrix.sh -o DIR` resumes an interrupted run: APKs already in `DIR/results.csv` are skipped. This lets a long run go in chunks under a timeout.
- `-f REGEX` selects APKs by id, for example `-f 'probe-|vlc'`.
- `-w` changes the 15 s wait.
- Disk use is about 2 GB for the corpus, 3 GB for the toolchain, and a few MB of results per two runs.
- `COMPAT_TARGET=cf` (ANAL-200) runs `run-matrix.sh` and `run-bench.sh` on our own Cuttlefish build and its built-in Digitalis bridge instead of the emulator. `scripts/compat/cf.sh` boots `CF_DEVICE` (default `anybook_vsoc_x86_64`) with the baseline AVD's 6 vCPUs, 8 GiB and SwiftShader, from fresh images each time.
- `COMPAT_AVD` selects another AVD on the same ports (default `anybook-desktop`), `COMPAT_EMU_ARGS` adds emulator flags, and `COMPAT_GLTRANSPORT=` (empty) keeps the emulator's default GL transport. The Digitalis overlay on Google's image uses `COMPAT_AVD=anybook-digitalis COMPAT_EMU_ARGS=-writable-system` (`docs/digitalis.md`), so the libndk_translation AVD stays untouched.
- **Reproducibility:** two runs, each from a freshly wiped device, should give identical outcomes for every APK and probe result. They have on both bridges so far.

### What `run-matrix.sh` does per APK

1. Uninstall any earlier copy, go to the home screen, mark the time, and clear logcat.
2. `adb install -r -g`, timed. `-g` grants runtime permissions so permission prompts don't hide the app.
3. Record `primaryCpuAbi`. Find the first `MAIN`/`LAUNCHER` activity and start it with `am start -W`, recording `TotalTime`.
4. Wait 15 s. Probes get up to 45 s more to print `PROBE_DONE`; they normally finish in about 2 s.
5. Check whether the app process is alive (`pidof`), count its processes, check whether the bridge library is mapped in it, and whether it is the resumed activity.
6. Take a screenshot (halved and palette-reduced PNG).
7. Count Java crashes (`AndroidRuntime: Process: <pkg>`), native crashes (debuggerd `>>> <pkg> <<<`), ANRs, and new files in `/data/tombstones`. Extract a crash signature. Save logcat (main, system, crash) gzipped.
8. Parse probe results into `probe-results.csv`.
9. Force-stop, close system dialogs, and uninstall.

`results.csv` columns: `run_id, id, kind, role, package, version, apk_abis, apk_sha256, install, install_ms, primary_abi, launch, launch_ms, alive, procs, native_bridge, foreground, java_crashes, native_crashes, anrs, tombstones, probe_pass, probe_fail, probe_skip, verdict, crash_signature, screenshot`.

Verdicts:

- `INSTALL_FAIL`
- `LAUNCH_FAIL`
- `CRASH`: dead at 15 s, with a crash.
- `EXITED`: dead, no crash.
- `ANR`
- `RUNS_WITH_CRASH`: alive, but a process crashed.
- `RUNS`: alive, no crash or ANR.

A `RUNS` verdict means "survived 15 s", not "works". The screenshot is the first check of what the user would see. Two gotchas:
- The `native_bridge` column means "the bridge library is mapped in the process". Digitalis's `libberberis_arm64.so` stays mapped in x86_64 processes too, so under Digitalis it doesn't mean the app is translated.
- A fatal signal that the bridge's own handler catches leaves no tombstone, so the harness reports `EXITED` rather than `CRASH` (seen with Fennec under Digitalis A16).

## Emulator setup

| | |
|---|---|
| Host | Ryzen 9 7950X (Zen 4), Arch Linux, KVM, no sudo; other OpenBook jobs share the host |
| Emulator | 37.2.12.0 (build 16428233), AVD `anybook-desktop`, console port 5580, 6 vCPU, 8 GB RAM |
| Image | `google/sdk_gdesktop_x86_64/emu64xa:17/CLE1.260506.004/15373846:userdebug` |
| Native bridge | `ro.dalvik.vm.native.bridge=libndk_translation.so`, `ro.enable.native.bridge.exec=1` |
| ABIs | `ro.product.cpu.abilist=x86_64,arm64-v8a`, `abilist32` empty |
| GPU | SwiftShader through gfxstream: GLES 3.0 and Vulkan 1.3 (`Virtio-GPU GFXStream (SwiftShader Device)`) |

`scripts/compat/emulator.sh` owns these settings, which differ from M0's:

- **Guest Vulkan is enabled.** The emulator ships with the Vulkan feature off, and the guest's Mesa gfxstream Vulkan driver needs a virtio-gpu render node. `emulator.sh` therefore passes `-feature Vulkan` and sets `hw.gltransport=virtio-gpu` in the AVD's `config.ini`. It re-applies that setting on every boot because `m0-emulator.sh` rewrites the file. Without these, `vkCreateInstance` returns `VK_ERROR_INITIALIZATION_FAILED` for x86_64 code too.
- **Cold boots wipe data** (`-wipe-data`).
- **The device is prepared for testing:** `adb root` (userdebug), animations off, screen kept on.

Facts observed from inside the image (**CONFIRMED**):

- `/system/lib64/arm64/` holds the guest arm64 libraries.
- `/system/bin/ndk_translation_program_runner_binfmt_misc_arm64` runs arm64 executables through binfmt_misc.
- `/system/lib64/libberberis_exec_region.so` is present.
- Crash stacks show libndk_translation frames in the `berberis::` C++ namespace, for example `berberis::(anonymous namespace)::UndefinedInsnThunk`. So this libndk_translation build contains Berberis code.

## Corpus

### Self-built probes (`scripts/compat/probe/`)

One small app is built three times by `build-probes.sh`, with NDK r30, minSdk 30, target 36, and no Gradle:

- `dev.anybook.probe.arm64`: `lib/arm64-v8a` only.
- `dev.anybook.probe.armv7`: `lib/armeabi-v7a` only.
- `dev.anybook.probe.x86_64`: the native control.

The Java side runs every test on a background thread. It logs results as `AnyBookProbe: PROBE_RESULT <test> PASS|FAIL|SKIP checks=N [failed=...] <info>`, shows them on screen, and writes `files/probe-results.txt`. Tests that check AArch64-only semantics are skipped on x86_64. That build exists to validate the probe itself; its own crypto references, for example, are checked against AES-NI, PCLMUL and SSE4.2. Later work added a `regress` group (ID registers, bit-exact `FRECPE`, `Build.CPU_ABI`; `docs/digitalis.md`).

| Test | What it checks | arm64 via libndk_translation (2026-10-15) | x86_64 control |
|---|---|---|---|
| `java_jni_args` | 20 mixed Java→native args (stack-passed, NaN payloads, −0.0, subnormals), compared bit for bit | PASS | PASS |
| `java_jni_exception`, `java_jni_register_natives` | `ThrowNew`, `RegisterNatives` from `JNI_OnLoad` | PASS | PASS |
| `java_jni_callbacks` | 10k `CallIntMethod`, fields, statics; 13-argument FP callback through varargs and through `jvalue[]`; critical arrays; Java exceptions seen from native code; `NewObject`; local frames; `AttachCurrentThread`; direct buffers | PASS (12 checks) | PASS |
| `abi` | `uname`, `AT_HWCAP`, `/proc/cpuinfo`, page size | **FAIL**: `uname -m` says `x86_64` | PASS |
| `neon` | 16 Advanced SIMD checks: saturating ops, `TBL` out-of-range, `LD3`, `FCVTZS` saturation, bit-exact `FRECPE`, `FMAXNMV`, … | PASS | skip |
| `crypto` | AES (`AESE`+`AESMC`), `PMULL`, CRC32/CRC32C against software references | PASS (aes, pmull, crc32 advertised) | PASS (validates the references) |
| `isa` | 32 AArch64 semantics checks: integer divide by zero, FP→int saturation, NaN rules, `FMADD` single rounding, FPCR rounding and FZ, FPSR flags, flags/carry, PAC/BTI hints, system registers, `SVC` | **FAIL**: 5 checks | skip |
| `atomics` | 8-thread `fetch_add`/CAS, 128-bit CAS, `LDAXR`/`STLXR`, LSE `LDADDAL`, release/acquire message passing, seq_cst store buffering | **FAIL**: seq_cst store buffering | PASS |
| `tls` | `thread_local` isolation and destructors, `pthread_key` destructors, per-thread `errno` | PASS | PASS |
| `threads` | 64 threads, mutex contention, condvar ping-pong, 16 MB stacks, `PR_SET_NAME` | PASS | PASS |
| `syscalls` | Raw `syscall()`, `getrandom`, `openat`/`read`, clocks, `eventfd`, `MAP_FIXED`, 512 MB mapping | PASS | PASS |
| `dlopen` | Plugin by name and full path, `RTLD_NOLOAD`, dynamic TLS, `dladdr`, `dl_iterate_phdr`; all 24 NDK-stable libraries; `libnativehelper` `JNI_GetCreatedJavaVMs`; private `libutils.so` blocked | PASS (13 checks) | PASS |
| `cxx_exceptions` | Unwinding through 20 frames, rethrow, `exception_ptr` across threads, futures, `bad_alloc`, throwing through bionic `qsort`, throwing across a dlopen boundary, `_Unwind_Backtrace` | PASS | PASS |
| `jit` | Generated code: W^X `mprotect` re-patch, RWX hot patch after 200k calls, memfd dual mapping (RW plus RX view, as V8/SpiderMonkey do) with cache flush | PASS | PASS |
| `signals` | `SEGV_MAPERR`/`SEGV_ACCERR` siginfo, `SIGILL`, ucontext PC read and resume, `raise`, `pthread_kill`, `sigaltstack`, async `SIGALRM`, pending mask, `EINTR` vs `SA_RESTART`, nested handlers | **FAIL**: SIGILL `si_code` | PASS |
| `gles` | EGL pbuffer, ES 3.0 shader compile and link, FBO draw, `glReadPixels` | PASS | PASS |
| `vulkan` | Loader, instance, device, `vkCmdFillBuffer` on a host-visible buffer, readback | PASS | PASS |

Gotcha: the probes avoid `SIGUSR1`. ART blocks it in every thread and its Signal Catcher thread consumes it.

### F-Droid apps (`scripts/compat/corpus/fdroid.tsv`)

26 APKs in all: the 3 probes plus 23 F-Droid APKs, which are 16 apps whose release ships only arm64 native code and 7 x86_64 builds of the same releases as native controls.

`scripts/compat/corpus/select-fdroid.py` reads F-Droid's `index-v2.json`. For each curated package it takes the newest APK whose only native ABI is arm64-v8a. When F-Droid builds one, it also takes the x86_64 APK of the same release as a control.

The index (fetched 2026-10-15) is verified in three steps:

1. `entry.jar` passes `jarsigner -verify`.
2. Its signer's SHA-256 is `43:23:8D:51:…:C9:CC:AB`, the fingerprint f-droid.org publishes.
3. The sha256 of `index-v2.json` matches `entry.json`.

`fetch-corpus.sh` pins every APK by sha256. f-droid.org throttles bulk downloads, so it uses official mirrors listed in the signed index and falls back to f-droid.org.

| App | Package | Version | License | Source | Native stack exercised |
|---|---|---|---|---|---|
| VLC | `org.videolan.vlc` | 3.7.1 | GPL-3.0-only | https://code.videolan.org/videolan/vlc-android | C/C++ media (libvlc, FFmpeg), NEON |
| Fennec F-Droid | `org.mozilla.fennec_fdroid` | 158.0.0 | MPL-2.0 | https://hg.mozilla.org/mozilla-central/file/tip/mobile/android | Gecko, multi-process, SpiderMonkey JIT |
| KOReader | `org.koreader.launcher.fdroid` | v2026.07.1 | AGPL-3.0-only | https://github.com/koreader/koreader | LuaJIT, MuPDF |
| Lichess | `org.lichess.mobileV2` | 0.29.1 | GPL-3.0-or-later | https://github.com/lichess-org/mobile | Flutter (Dart AOT), Stockfish |
| LocalSend | `org.localsend.localsend_app` | 1.18.2 | Apache-2.0 | https://github.com/localsend/localsend | Flutter, Rust |
| Godot Engine 4 | `org.godotengine.editor.v4` | 4.7.2.stable | MIT | https://github.com/godotengine/godot/ | Godot 4 editor, Vulkan/GLES3 |
| Ogre Sample Browser | `org.ogre.browser` | 14.3.0 | MIT | https://github.com/OGRECave/ogre | OGRE 3D, GLES3 |
| The Battle for Wesnoth | `org.wesnoth.Wesnoth` | 1.19.28 | GPL-2.0-or-later | https://github.com/wesnoth/wesnoth | SDL2, C++ |
| OsmAnd~ | `net.osmand.plus` | 5.4.10 | GPL-3.0-only | https://github.com/osmandapp/Osmand | C++ OpenGL map renderer |
| GCompris | `net.gcompris.full` | 26.2 | AGPL-3.0-only | https://invent.kde.org/education/gcompris | Qt 6 / QML |
| TIC-80 | `com.nesbox.tic` | 1.01.00 | MIT | https://github.com/nesbox/TIC-80 | SDL2, Lua/JS/Wren VMs |
| AAAAXY | `io.github.divverent.aaaaxy` | 1.7.239 | Apache-2.0 | https://github.com/divVerent/aaaaxy | Go, Ebitengine |
| SimpleX Chat | `chat.simplex.app` | 7.0.4 | AGPL-3.0-or-later | https://github.com/simplex-chat/simplex-chat | Haskell (GHC) runtime, Compose |
| Tor VPN Beta | `org.torproject.vpn` | 1.9.1Beta | BSD-3-Clause | https://gitlab.torproject.org/tpo/applications/vpn/ | Go (gomobile), Rust (Arti), VpnService |
| Element X | `io.element.android.x` | 26.09.1 | AGPL-3.0-or-later | https://github.com/element-hq/element-x-android | Rust Matrix SDK (UniFFI) |
| Tux Paint | `org.tuxpaint` | 0.9.35 | GPL-2.0-or-later | https://github.com/tux4kids/Tuxpaint-Android | SDL2, C |

x86_64 controls (same release): VLC, Fennec, Lichess, LocalSend, Godot, AAAAXY, Element X.

### Licensing

- **F-Droid apps:** every app is free software under the license above. APKs are downloaded locally to `~/anybook/compat/apks/` and are **not** committed or redistributed. The repo holds only names, versions and sha256 pins.
- **Proprietary APKs:** none in the corpus. Before any is added, its terms must allow this kind of testing, and those terms get recorded here.
- **CoreMark** (EEMBC, commit `1f483d5`): the code is Apache-2.0 and the name is a trademark under EEMBC's acceptable-use terms. We build the **unmodified** sources with the stock `posix` port. The in-app variant only renames `main` with `-Dmain=coremark_main`. Runs follow the 10-second rule and pass CoreMark's CRC validation. These are our own measurements, not certified or submitted scores. CoreMark® is a trademark of EEMBC.
- **Emulator image:** covered by the Android SDK (Preview) License, local use only. libndk_translation is proprietary and stays inside the image. We observe its behaviour only, and do not extract or ship it.

## CPU benchmark (`run-bench.sh`)

- The same unmodified CoreMark source is built by NDK r30 clang `-O2` for `aarch64-linux-android30` and `x86_64-linux-android30`. The x86_64 baseline is the NDK default, SSE4.2 with no AVX.
- Both run on the same device, one thread, 600,000 iterations, for 3 interleaved rounds. Every run lasts over 10 s and must pass CoreMark's validation.
- Modes:
  - `exe`: `adb shell`; arm64 goes through the binfmt_misc runner.
  - `apk`: `System.loadLibrary` inside the probe app; arm64 goes through the app native bridge.
  - `host`: the static x86_64 build on bare metal.
- **Limits:** CoreMark is integer and control-flow heavy, so SIMD-heavy and JIT-heavy code will scale differently. The emulator's guest CPU model hides AVX2/FMA, which the NDK x86_64 baseline doesn't use anyway. There is no Intel or ARM Googlebook baseline yet.

## The libndk_translation baseline (2026-10-15)

Google's emulator image, two runs from a wiped emulator with identical outcomes for all 26 APKs and all 38 probe-test results. Per-app outcomes are in the libndk_translation column of [`COMPAT-MATRIX.md`](COMPAT-MATRIX.md).

- **Apps:** 13 of 16 arm64-only apps stay alive after 15 s. AAAAXY crashes the same way natively; Tor VPN and Element X fail only under translation; SimpleX stays alive with a black window at 15 s.
- **Probes:** arm64 passes 15 of 19 test groups; the x86_64 control passes all 17 applicable groups.
- **CPU speed** (host load 1.0–2.5 on 32 threads; spread between rounds under 1%):

  | Mode | ABI | Median iterations/s |
  |---|---|---|
  | host | x86_64 | 44,108 |
  | emulator, executable | x86_64 | 40,429 |
  | emulator, executable | arm64-v8a | 18,479 |
  | emulator, in app | x86_64 | 39,303 |
  | emulator, in app | arm64-v8a | 17,819 |

  Translated / native: 0.457 for executables and 0.453 in an app, so arm64 code runs at about 45% of native speed. VM overhead (emulator x86_64 / bare host) is 0.917.
- **Cold launch** (`am start -W`) is slower under translation, for example Fennec about 0.7 s against 0.19 s and Lichess 1.9 s against 0.45–0.49 s (two samples each, indicative).

**What it gets wrong** (CONFIRMED; the Digitalis column of the comparison is in `docs/digitalis.md`):
1. **Sequentially consistent atomics lose store→load ordering.** In the store-buffering (Dekker) test, both threads read 0 in about 2,000 of 200,000 seq_cst iterations (2,138 and 1,972 in two runs); the x86_64 control and real arm64 hardware give 0. The arm64 code is `stlr` followed by `ldar`, which ARMv8 orders. **HYPOTHESIS:** `STLR`/`LDAR` become plain x86 moves with no store→load fence. This can break Dekker-style and lock-free code, and the failures are rare and timing-dependent.
2. **AArch64 floating-point NaN rules follow x86.** `0 × ∞` gives `0xffc00000` (the x86 default NaN) instead of ARM's `0x7fc00000`; with a quiet and a signaling NaN, the first operand wins instead of the signaling one; `FMAX(qNaN, 1)` returns the default NaN instead of propagating the operand. Rounding modes, FZ, FPSR flags, `FMADD`, saturation and `FRECPE` are exact. Impact is probably small: it matters to bit-exact code and NaN-payload tricks.
3. **`CNTVCT_EL0` ticks about 429× faster than `CNTFRQ_EL0` says.** `CNTFRQ_EL0` reads 10,485,760 Hz, but the counter advances about 4.5 G ticks per second (**HYPOTHESIS:** the host TSC, unscaled). Code that times itself with the generic timer sees time running about 400× too fast.
4. **`MRS` of CPU ID registers raises SIGILL** (breaks Tor VPN). arm64 Linux traps and emulates `MIDR_EL1`/`ID_AA64*_EL1` reads from userspace; here they end in `berberis::UndefinedInsnThunk`, which raises `SIGILL` (code `SI_QUEUE`). Tor VPN's Go runtime (`libgojni.so`, gomobile) executes `mrs x0, ID_AA64ISAR0_EL1` at startup and dies. Apps can't read `/proc/self/auxv` on this image, even on x86_64, so Go's `x/sys/cpu` falls back to the ID registers. This hits any Go-based Android library.
5. **Element X (Rust Matrix SDK) can't find the JavaVM under translation** (cause open). It throws `InternalException: Failed to find JNI_GetCreatedJavaVMs` from `matrix-sdk-ffi` `android_platform.rs`; the x86_64 build runs. An explicit `dlopen("libnativehelper.so")` + `dlsym` works under translation; `dlopen("libart.so")` and `dlsym(RTLD_DEFAULT, …)` fail for x86_64 code too, so neither explains the difference; the library imports only `dlopen`/`dlsym`. Next step: trace its lookup with the linker debug property, or disassemble the call path.
6. **No 32-bit ARM.** `abilist32` is empty and `/system/lib/arm` doesn't exist; armeabi-v7a APKs fail with `INSTALL_FAILED_NO_MATCHING_ABIS`; binfmt_misc registers `arm_exe`/`arm_dyn` with a runner that isn't installed, so arm32 executables exit with 126.
7. **Smaller differences:** `uname()` reports `x86_64` to arm64 code, while `/proc/cpuinfo` is rewritten as an ARM CPU (`CPU implementer 0x41`, `Features: fp asimd aes pmull crc32 atomics`); `AT_PLATFORM` is absent; synthetic `SIGILL`s carry `si_code = SI_QUEUE` instead of `ILL_ILLOPC`; the advertised `HWCAP` is ARMv8.0 plus AES, PMULL, CRC32 and LSE only (no SHA1/SHA2, dot product, FP16 or `cpuid`), so apps take baseline code paths.

**What works under it:** all JNI patterns tested, NEON, AES/PMULL/CRC32 and LSE atomics, 128-bit CAS and exclusive load/store, TLS, C++ exceptions (including through guest libc and across libraries), JIT code patching with memfd dual mappings, signals with ucontext PC resume, all 24 NDK-stable libraries, and GLES 3.0 and Vulkan 1.3 through the bridge.

## Limitations

- **Software GPU:** the emulator and Cuttlefish runs use SwiftShader, not AMD hardware, so GPU-bound behaviour says nothing about radeonsi/RADV.
- **Smoke test only:** a 15-second launch shows startup compatibility, not function. There is no input, login or media playback, and runtime permissions are pre-granted.
- **Corpus bias:** it is free software only. Popular proprietary ARM-only apps (games, banking) behave differently, and many of them also use Play Integrity, which this project will not bypass.
- **Bridges covered:** libndk_translation and Digitalis. libhoudini (from the Googlebook image) is not run yet.

## Next steps

1. Run the same corpus under libhoudini once the Googlebook image boots in a VM.
2. Root-cause Element X and the SimpleX black window.
3. Add scripted interaction (UI Automator) for deeper checks, and a SIMD/JIT micro-benchmark next to CoreMark.
