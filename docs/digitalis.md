# Digitalis: Track A's arm64 native bridge (ANAL-181, ANAL-200)

Status as of 2026-10-17. **CONFIRMED** means we observed it in our own build logs, device logs or test output. **HYPOTHESIS** means a likely explanation we have not proven. Evidence paths in the ANAL-200 sections are relative to `evidence/2026-10-17-digitalis-a17/`.

Digitalis (https://github.com/DigitalisX64) is an Apache-2.0 fork of AOSP's Berberis binary translator that adds an arm64 guest. ANAL-181 evaluated it on Google's emulator image and recommended it with conditions (the evaluation is kept below). Since ANAL-200 it is the arm64 native bridge of OpenBook's own Android 17 build. It is built from source in our tree, ships in both products, and carries our Android 17 port and three fixes.

## Status (ANAL-200)

- **It ships in both products** (CONFIRMED, `install.txt`). `device/anybook/common/native-bridge` puts the bridge into `anybook_cf_x86_64_pc` and `anybook_g14_x86_64`:
  - ABI list `x86_64,arm64-v8a`, `ro.dalvik.vm.native.bridge=libberberis_arm64.so`;
  - binfmt_misc runners for arm64 executables;
  - 57 arm64 guest libraries;
  - 89 files, 30 MB, in `/system` (88 for the bridge, plus our self-check `openbook_bridge_check`).
- **arm64 apps get the Android 17 NDK** (CONFIRMED, `analysis/ndk-api-gap.txt`). The guest libraries now come from our Android 17 tree. Every export of the host `libandroid`, `libbinder_ndk`, `libGLESv2` and `libnativewindow` is in the guest library. The only differences left are `__cfi_check` and libEGL's internal C++ symbols, which are not API. On Android 16 guest libraries, `libandroid` alone lacked 43 exports.
- **arm64-only apps run on our build** (CONFIRMED, `run1`, `run2`, `repro-check.txt`). On the Cuttlefish desktop product, 15 of the 17 arm64-only entries run, which is 14 of the 16 apps. That compares with 13/16 for libndk_translation and 12/16 for Digitalis in ANAL-181. Two runs from wiped data gave identical outcomes.
  - Fennec and Tor VPN are the two newly working apps.
  - AAAAXY crashes the same way natively.
  - Element X fails the same way on both bridges (`JNI_GetCreatedJavaVMs`).
- **The three bugs are fixed** (CONFIRMED). Details are in the next section.
  - `MRS` of the ID registers is emulated as Linux does it, so Tor VPN runs.
  - `FRECPE`/`FRSQRTE` are bit-exact against QEMU's implementation of the Arm pseudocode on 154,000 cases on the device, in all three translation modes.
  - The Fennec crash was not a translation bug. Android 17 stopped reporting the bridged ABI in `Build.CPU_ABI`. An ART patch restores it, and arm64 Firefox now starts Gecko and renders pages.
- **Speed** (CONFIRMED numbers). CoreMark runs at 0.394× native (executable) and 0.399× (in an app) on our Cuttlefish image.
  - On Google's emulator image, the same Android 17 build of the bridge gives 0.300 / 0.298, as Digitalis did in ANAL-181. libndk_translation gives 0.457 / 0.456 there on the same day.
  - So Digitalis reaches about 65% of libndk_translation's speed in the same VM. The port neither helped nor hurt.
  - **HYPOTHESIS:** our VM gives the guest AVX2, BMI1/2, FMA and the other host features the emulator hides, and the translator uses them.
- **Licensing is clean** (CONFIRMED, `audit/`). Everything is built from source. The only prebuilt among the bridge's files is AOSP's own toolchain `libc++.so`, the same library the x86_64 system ships. No Digitalis binary is in the image. The Cuttlefish and G14 products ship the same 89 files from the same modules.
- **On the G14 itself (CONFIRMED, 2026-10-17, `evidence/2026-10-17-digitalis-g14/`):** the bridge runs on real Zen 5 (Ryzen AI 9 HX 370). In both of the owner's sessions (`anal178c`, `anal176s`), all five `bridge_*` verdicts pass:
  - the bridge is configured: 57 guest libraries, binfmt_misc on;
  - an arm64 binary runs;
  - all 9 ID registers read without SIGILL;
  - 6,900 `FRECPE`/`FRSQRTE` cases give 0 wrong results;
  - CRC32 and NEON FMA are correct.

  The owner opened no arm64 app, and the stick has none, so app behaviour, the probe and CoreMark on the G14 are still to come. The "ARM apps check" add-on below runs them; it is on ANAL-192's stick checklist.

## How it is built

The bridge is part of the normal product build (`scripts/aosp-build.sh`). Nothing is installed by hand.

- **Source:** `aosp/patches/frameworks/libs/binary_translation/IMPORT` replaces AOSP's `frameworks/libs/binary_translation` (android17-release, `1290e88c`) with the Digitalis fork at `b6b7fc30`, fetched from GitHub once. `scripts/aosp-patches.sh` makes the import a reproducible commit on the pin and applies our patches on top. Other branches' runs of `aosp-patches.sh` put the project back on its pin, as they do for any branch's patches.
- **Guest world:** `frameworks/libs/native_bridge_support` (the guest bionic, the NDK stub libraries and the proxy trampolines), bionic and the framework all come from our Android 17 tree. That is what closes the NDK gap.
- **Our patches** (`aosp/patches/frameworks/libs/binary_translation/`):
  1. `libberberis_runtime_library_headers`: the android17-release name and path of the runtime library header, which Android 17's `native_bridge_support` includes.
  2. An unused variable that Android 17's clang (`clang-r584948b`) rejects under `-Werror`.
  3. `MRS` of the ID registers.
  4. Bit-exact `FRECPE`/`FRSQRTE`.
- **ART patch** (`aosp/patches/art/`): `libnativebridge` sets `Build.CPU_ABI` and `CPU_ABI2` for bridged apps again (the Fennec fix).
- **Device:** `device/anybook/common/native-bridge/`:
  - `native-bridge.mk` inherits Digitalis's `enable_arm64_to_x86_64.mk` and adds `openbook_bridge_check`;
  - `BoardConfig.mk` sets `TARGET_NATIVE_BRIDGE_ARCH=arm64`;
  - `pc.mk`, `anybook_cf_x86_64_pc.mk` and both BoardConfigs include them.
- **Why not merge android17-release into the fork:** a trial merge gives 64 conflicting files and 219 renames. Upstream android17-release has no arm64 translator (no decoder, interpreter or JIT); its new arm64 pieces are infrastructure that overlaps the fork's. Building the fork's translator, as ANAL-181 tested it, against the Android 17 tree needed only patches 1 and 2. A full merge is worth doing when Digitalis itself moves to Android 17. That is a follow-up, not a blocker.
- **Cost:** adding the bridge to an existing `out/` took two passes. The first stopped on three compile errors that patches 1 and 2 fix; the second took 11 min 35 s at `-j28`, and the container's memory peaked at 57.7 GB (cgroup `memory.peak`). The G14 product's first build with the bridge took 29 min 31 s, and the final Cuttlefish rebuild 2 min 54 s (`build-summary.txt`).
- **Host tests:** Digitalis's suite (`berberis_arm64_host_tests`) builds and runs in the container from the same tree. On the final tree, 3,761 of 3,763 tests pass, 2 are skipped and none fail (`host-tests.txt`).

## The three bugs

### 1. `MRS` of the ID registers (Tor VPN, Go)

**Symptom (ANAL-180/181).** Tor VPN died of SIGILL at `mrs x0, id_aa64isar0_el1` under both bridges.

Go's `golang.org/x/sys/cpu` reads `ID_AA64ISAR0/ISAR1/PFR0` when it cannot read `/proc/self/auxv`, and Android apps cannot read it. A real arm64 kernel traps these EL0 reads and returns sanitised values (`emulate_mrs` in `arch/arm64/kernel/cpufeature.c`). Digitalis emulated only `MIDR_EL1`.

**Fix (patch 3).** `guest_id_registers_arm64.h` holds the guest CPU's identity in one place:
- `AT_HWCAP`, which gains `HWCAP_CPUID`;
- the values of `MIDR`/`MPIDR`/`REVIDR` and the `ID_AA64*` registers, built the way the kernel builds them: visible fields from the features the translator implements, hidden fields at the kernel's safe value;
- the rest of the feature ID space (CRm 2–7) reads as zero, and everything outside it still raises SIGILL, as on Linux.

The interpreter and the lite tier return these values. The heavy tier leaves such regions to the lite tier, as it did for `MIDR`.

`ID_AA64ISAR0_EL1` = `0x211120` (AES+PMULL, SHA1, SHA2, CRC32, LSE), matching `AT_HWCAP` = `fp asimd aes pmull sha1 sha2 crc32 atomics cpuid`.

**Result** (CONFIRMED):
- Tor VPN runs in both runs.
- The probe's `isa/mrs_cpuid_registers` passes.
- The new `regress` group checks 9 ID registers and their agreement with `AT_HWCAP` field by field, as the kernel derives HWCAPs.

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

**Result** (CONFIRMED, `fp-estimate/`):
- **The header against QEMU 11.1:** 0 mismatches in 189,200 cases. That covers scalar and vector, f16/f32/f64, `URECPE`/`URSQRTE`, and FPCR 0/FZ/DN/FZ|DN/RP/RM/RZ/FZ16, with edge cases and 2,000 random inputs per form.
- **On the device** (`scripts/compat/digitalis/fp-estimate.sh device`, an arm64 executable through binfmt_misc): 0 of 154,000 lines differ from QEMU under `two-gear`, `lite-translate-or-interpret` and `interpret-only`. Each input runs 50 times, so the JIT tiers translate the loop.
- **Probe:** `neon/frecpe_bit_exact` passes, and the `regress` group compares scalar and vector forms with QEMU golden values, including FPSR.

### 3. Fennec's SIGSEGV at `libxul.so+0x2b32da0`: not a translation bug

**What happens.** `Preferences::InitializeUserPrefs()` dereferences a NULL `Preferences` object. Gecko's `Preferences::GetInstanceForService()` had failed and dropped it, because `InitInitialObjects()` could not load the default preferences:
- GeckoView exports `MOZ_ANDROID_CPU_ABI` from `android.os.Build.CPU_ABI`;
- Gecko reads `<abi>/greprefs.js` from its omnijar, and then `greprefs.js`;
- the arm64 APK's `omni.ja` holds only `arm64-v8a/greprefs.js`, and `Build.CPU_ABI` was `x86_64`.

The `nsZipArchive` log shows the two failed lookups repeated about 970 times, then the crash (`analysis/fennec-root-cause.md`).

**Why the ABI was wrong.** libnativebridge used to set `Build.CPU_ABI`/`CPU_ABI2` from the bridge's `getAppEnv()`, and Digitalis reports `arm64-v8a`. AOSP removed that in android17-release (art `b7947b0641`, May 2025: "deprecated since API 21").

**libndk_translation is affected too** (CONFIRMED). On Google's image the same two lookups fail. Its Gecko thread then spins at 100% CPU: 155 ticks in 5 s, 1 min 22 s of CPU after 30 s. The Java UI stays up, so ANAL-180's "RUNS" for Fennec there meant only "the process is alive". Under Digitalis the NULL dereference is fatal instead.

**Fix** (`aosp/patches/art/0001-…`). Restore the two fields in `SetupEnvironment()`, as before android17-release.

**Result** (CONFIRMED, `fennec-gecko/`):
- arm64 Fennec runs in both matrix runs.
- Gecko logs "chrome startup finished" and runs its tab, content and GPU processes as arm64.
- It renders a page served over `adb reverse`, with JavaScript running (screenshots arm64 and x86_64; the canvas is missing in both, so that is not translation).
- The probe's `regress/build_cpu_abi_is_native_abi` checks the field for the arm64 and x86_64 probes.

**How we got there.** Interpret-only mode at first seemed to fix it, which pointed at the JIT. A debug knob bisected the lite tier by instruction class and by library offsets (`analysis/lite-bail-bisection.md`) and narrowed it to mozjemalloc and Gecko's `HashString`. Then interpret-only crashed too. Those runs had only been slow enough to miss the crash inside the 20–25 s window, and app data left over between runs changed the timing. With cleared data and longer waits, every mode crashed. The tier-independence and `MOZ_LOG` led to the root cause. Lesson for future bisections: clear app data per run and confirm a "fix" survives a long wait.

## Results on our image (2026-10-17)

`anybook_cf_x86_64_pc-cp2a-userdebug` (`CP2A.260605.016`) runs in Cuttlefish (`scripts/compat/cf.sh`, `COMPAT_TARGET=cf`) with 6 vCPUs, 8 GiB and SwiftShader. These are the same resources as the baseline AVDs, and the corpus, probes and harness are the same too. There were two runs from wiped data, with identical outcomes (`repro-check.txt`).

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

- **Probe failures left** are the two known semantic differences, which this issue did not take on: x86 NaN rules (`isa`: sNaN priority, default-NaN sign) and the SIGILL `si_code` (`signals`).
- **Launch times** (`am start -W`) are in the same range as libndk_translation's on the emulator: Fennec 0.62 s, Lichess 1.2 s, OsmAnd 1.0 s. They come from different VMs, so we don't compare them closely.

### CPU speed (CoreMark, 600k iterations, 3 interleaved rounds, quiet host)

| Bridge, image, VM | exe arm64 / x86_64 | apk arm64 / x86_64 | Evidence |
|---|---|---|---|
| **Digitalis A17, our image, Cuttlefish** | **0.394** (16,870 / 42,839 it/s) | **0.399** (16,181 / 40,568) | `bench/` |
| Digitalis A17, Google's image, emulator | 0.300 (12,155 / 40,546) | 0.298 | `emulator-overlay/bench/` |
| libndk_translation, Google's image, emulator | 0.457 (18,516 / 40,532) | 0.456 | `bench-ndk/` |
| Digitalis A16, Google's image, emulator (ANAL-181) | 0.298 | 0.304 | `evidence/2026-10-16-digitalis/bench/` |

- Every round passed CoreMark validation, and the CoreMark binaries are byte-identical to ANAL-180's.
- The emulator overlay is our Android 17 bridge collected from the product (`scripts/compat/digitalis/bundle.sh`) and installed on the same AVD ANAL-181 used.
- **HYPOTHESIS:** Cuttlefish passes the host's CPU features to the guest (`avx2 bmi1 bmi2 fma movbe adx avx512f`, `install.txt`); the emulator's guest has none of these, and the translator selects code by host CPU features. The G14's Zen 5 has them all, so expect the Cuttlefish figure or better there. The G14 measurement comes from the ARM apps check add-on ("On the G14").

## License and provenance of what ships (ANAL-200)

`scripts/compat/digitalis/audit-shipped.py` lists every bridge file in a product's `PRODUCT_OUT`. For each file it records:
- the Soong module that installs it and its source directory (`module-info.json`);
- whether that source is under `prebuilts/`;
- its SHA-256;
- the licenses the image's own `NOTICE.xml.gz` gives for it, classified by their text.

The results for both products are in `audit/cf/` and `audit/g14/`: 89 files each, 1 prebuilt, 1 not covered by NOTICE.

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
- No file comes from the Digitalis repositories other than the translator source we build. ANAL-181's audit of the fork's source still applies: Apache-2.0, no third-party code copied in, 20 new files without headers, an agent-driven project with a single main author, trademarks.
- Our patches carry Apache-2.0 headers ("The OpenBook Authors").

## On the G14 (bare metal)

`openbook_bridge_check` is an arm64 static binary, built from source in the tree as the bridge's guest architecture. It is installed as `/system/bin/arm64/openbook_bridge_check`; fsgen puts native-bridge modules on the system partition only. binfmt_misc runs it through the translator, and it prints one JSON result per check:
- `bridge-exec`: it ran as arm64;
- `bridge-id-registers`: 9 registers, no SIGILL, agreement with `AT_HWCAP`;
- `bridge-fp-estimates`: 6,900 golden cases from QEMU, with FPSR;
- `bridge-int-simd`: CRC32 and NEON FMA against references computed in the program.

`openbook-hwtest bridge` adds the configuration (`bridge-config`: the property, both binfmt_misc entries, the guest libraries) and passes the results on as `HWTEST` lines. The live image's "save logs" entry runs it with the other checks, and `scripts/installer/live-report.py` turns the lines into the verdicts `bridge_config`, `bridge_exec`, `bridge_id_registers`, `bridge_fp_estimates` and `bridge_int_simd`.

The check needs no network or user input and changes nothing. It passes in all three translation modes on Cuttlefish, as root and as the shell user (`bridge-check-cuttlefish.txt`). Under QEMU's `-cpu max` and `-cpu cortex-a53` (a real ARM CPU model) it passes too, which validates the check itself. The G14 product's live image passes it in QEMU/KVM as part of the "save logs" entry, so all five verdicts are true in its `report.json` (`g14-live-qemu/report.json`, `hwtest-bridge.txt`). It has not run on the G14 hardware yet.

**Enforcing boots on the G14 product (fixed 2026-10-17, ANAL-159).** `berberis.rc` mounts binfmt_misc and registers the runners in early-init. The Cuttlefish product inherits Cuttlefish's two rules for that; the G14 product's policy lacked them, so its enforcing boots logged `mount binfmt_misc ... Permission denied` and arm64 executables could not run. App libraries still loaded through libnativebridge. The same two rules are now in `device/anybook/common/pc/sepolicy/vendor/init.te`. On `openbook-live-20261017-combined`, an enforcing boot has no binfmt_misc denial, and `openbook_bridge_check` run as the shell user passes all four checks (`evidence/2026-10-17-g14-combined/`). The "save logs" entry is permissive, so its verdicts cannot catch an enforcing-only gap like this one.

### Results on the G14 (2026-10-17)

The owner booted two sticks, each with a default (enforcing) boot and then a "save logs" boot:
- `openbook-live-20261017-anal178c`;
- `openbook-live-20261017-anal176s` (`anal178c` plus PR #52's fixes).

ANAL-176 copied both sessions to the build host. We read those copies only, never the stick. Machine: ROG Zephyrus G14 GA403WR, BIOS GA403WR.309, AMD Ryzen AI 9 HX 370 (family 0x1a, model 0x24).

| Verdict (`live-report.py --expect g14`) | `anal178c` | `anal176s` |
|---|---|---|
| `bridge_config` (property, both binfmt_misc entries, guest libraries) | PASS (57 libraries) | PASS (57) |
| `bridge_exec` (an arm64 binary through binfmt_misc) | PASS (`aarch64`, `AT_HWCAP` 0x9fb) | PASS |
| `bridge_id_registers` (9 registers, no SIGILL, agreement with `AT_HWCAP`) | PASS (`MIDR` 0x410fd034, `ISAR0` 0x211120) | PASS |
| `bridge_fp_estimates` (6,900 golden cases from QEMU) | PASS (0 wrong) | PASS (0 wrong) |
| `bridge_int_simd` (CRC32, NEON FMA) | PASS | PASS |

- **Where it ran:** the self-check runs in the "save logs" boot, which is permissive. All 67 berberis log lines come from that process, and every block was translated by the JIT tiers (`jit=N interp=0`).
- **Enforcing boots:** zygote starts with `-XX:NativeBridge=libberberis_arm64.so` in every boot.
  - The default boots logged no denial that names binfmt_misc, berberis or a native-bridge path.
  - The permissive "save logs" boots log denials but don't block them, from 0 s. Their kernel logs have no binfmt_misc or `mounton` denial. So the policy allows the mount (the ANAL-159 fix above is in these images).
  - The default boot's own kernel log is not saved, so in enforcing mode on the G14 this is an inference, not an observation.
- **No arm64 app ran:** the apps brought to the foreground were Settings, Gallery, Dialer and WebView Shell, all x86_64.
- **Evidence:** `evidence/2026-10-17-digitalis-g14/g14-*/`. It holds `report.json`/`report.md` (redacted with `live-report.py --redact`, using PR #52's version of the script, which fixes a crash in the `touchpad_clock` verdict), the bridge section of `hwtest-final.txt`, and `bridge-logs.txt`.

### The ARM apps check add-on (probe and CoreMark on the laptop)

The live stick has no adb and no arm64 app, so the probe and CoreMark go on the stick as an add-on. It uses the same live-init hook as ANAL-177's graphics check (`androidboot.openbook.addon=NAME`), and its entry is "OpenBook ARM apps check". It boots like "save logs". Once Android is up, the stick's own `openbook-live-init` unpacks the payload into the stick's `/data` and runs `scripts/compat/digitalis/stick/run.sh` as root. The run takes about 6 minutes:
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

- **Image files only.** `add-to-image.sh` refuses block devices. The owner's stick is ANAL-192's integrated image, written with `write-stick.sh`.
- **Verdicts:**
  - `addon_ran`;
  - `bridge_check`;
  - `probe_x86_64`: no failure;
  - `probe_arm64`: installed as `arm64-v8a`, `Build.CPU_ABI` is `arm64-v8a`, and no failed group beyond `isa` and `signals`, the two known differences;
  - `coremark_valid`.

  The report also gives the CoreMark ratios for executables and in the app.
- **QEMU proof (2026-10-17):** on a copy of `openbook-live-20261017-anal176s` (the image the owner booted), QEMU/KVM on the Ryzen 9 7950X, `-cpu host`, 8 vCPUs:
  - the add-on ran in 375 s and all five verdicts pass;
  - probes: x86_64 18 pass / 0 fail, arm64 18 pass / 2 fail (`isa`, `signals`);
  - CoreMark arm64 / x86_64: 0.362 for executables, 0.372 in the app;
  - cleanup left no probe app installed (`evidence/2026-10-17-digitalis-g14/qemu-addon/`).

  This is a VM sharing a busy host, not the laptop.
- **A finding from that run:** `libberberis_arm64.so` is mapped in x86_64 app processes too (ANAL-181's finding 8). So "the bridge is mapped" says nothing about which ABI ran. The report keys on the installed ABI and `Build.CPU_ABI` instead.
- **What the owner does (ANAL-192's checklist):** boot "OpenBook ARM apps check" once, on mains power with the lid open, and leave the laptop for about 10 minutes until it powers off. Results: `openbook/logs/live-NNN/addon-bridge*`.

## Open issues

- **Not fixed, by design of this issue:** x86 NaN semantics (default-NaN sign, sNaN priority), the SIGILL `si_code`, Element X's `JNI_GetCreatedJavaVMs`, and AAAAXY (a crash in the app itself).
- **The `Build.CPU_ABI` patch changes Android 17 behaviour back to Android 16's.** It affects every bridged app, as intended. An upstream AOSP report (art `b7947b0641`) would be outward-facing and is for the owner to decide.
- **Upstream reports to Digitalis** (`MRS`, `FRECPE`) are still waiting for the owner's OK. The patches stay in this repo; none was sent anywhere.
- **Speed:** about 65% of libndk_translation in the same VM. The heavy tier now leaves regions with vector `FRECPE`/`FRSQRTE` to the lite tier, which costs nothing on CoreMark but may cost a little in NEON-heavy code with estimates (HYPOTHESIS, not measured).
- **The emulated `/proc/cpuinfo`** lists `fphp asimdhp asimdrdm lrcpc dcpop asimddp`, but `AT_HWCAP` and the ID registers do not. The conservative `AT_HWCAP` is what code that probes features uses; the mismatch predates this work.

## Next

1. ANAL-192's integrated stick carries the ARM apps check. After the owner's boot of it, run `bridge-report.py`, then record the G14 probe and CoreMark rows (COMPAT-MATRIX) and compare them with Cuttlefish's 0.394 / 0.399.
2. An arm64 app in an **enforcing** G14 boot. The default boot has no arm64 app, and the add-on runs permissive. A small arm64 app preinstalled on the live image, or a device agent (ANAL-194), would close this.
3. Merge android17-release into the fork once Digitalis tracks Android 17, or do it ourselves (64 conflicts).
4. Upstream reports to DigitalisX64 and AOSP, after the owner's OK.

## ANAL-181 evaluation (2026-10-16)

Kept as written on 2026-10-16, except for the corrections marked ANAL-200. Its fixes and its Next steps 1 and 2 are covered above.

Digitalis (https://github.com/DigitalisX64) is an Apache-2.0 fork of AOSP's Berberis binary translator that adds an arm64 guest. We built it from source, installed it as the native bridge of the same AOSP Desktop 37.0 emulator image used for the libndk_translation baseline (ANAL-180), and ran the same corpus, probes and CoreMark benchmark on it.

As a control, we also built and booted Digitalis's own reference image (`sdk_phone64_x86_64_digitalis`, AOSP 16) and ran the same tests there.

### Recommendation for Track A: GO, with conditions

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

### What Digitalis is (checked 2026-10-16)

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

### Build from source

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

### Install on the AOSP Desktop 37.0 emulator

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

#### Control: Digitalis's own AOSP 16 reference image

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

### Results, side by side

Same image (`google/sdk_gdesktop_x86_64/emu64xa:17/CLE1.260506.004`), same emulator (37.2.12), same 6 vCPU, same corpus, 15 s wait, both runs from wiped data.
- libndk_translation: `evidence/2026-10-15-compat/run{1,2}`.
- Digitalis: `evidence/2026-10-16-digitalis/run{1,2}`.

Each bridge's two runs agree on every outcome (`repro-check.txt` in each evidence directory).

The `harness=` field in the Digitalis runs' `env.txt` shows pre-squash commit IDs (`4311e70-dirty`, `2743710-dirty`). The scripts that ran are the ones in this PR.

#### Apps

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

#### Probes and the baseline's failure classes

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

#### CPU speed (CoreMark, 600k iterations, 3 interleaved rounds)

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

### License and provenance audit

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

### Track A integration (Android 17)

- `device/google/cuttlefish/vsoc_x86_64_only/BoardConfig.mk` on `android17-release` already sets `TARGET_NATIVE_BRIDGE_ARCH := arm64` (and `TARGET_NATIVE_BRIDGE_ABI := arm64-v8a`). So `aosp_cf_x86_64_pc` needs only `$(call inherit-product, frameworks/libs/binary_translation/enable_arm64_to_x86_64.mk)` and the forked project, once it is ported.
- `device/google/cuttlefish/shared/desktop/common_x86.mk` already switches translators through `AL_BINARY_TRANSLATION_MODE`, using `inherit-product-if-exists` on Google's unbundled `vendor/unbundled_google/libs/ndk_translation`, which is not in AOSP. A `digitalis` mode fits the same switch.
- **Porting effort:** we trial-merged upstream `android17-release` into the fork (`b6b7fc30`, local only, not pushed). It gave 64 conflicting files and 219 renames. Most conflicts are in `cpu_emulation/backend/x86_64` (13 files) and in the arm64 `kernel_api`, `guest_os_primitives`, `runtime` and `native_bridge` code, where upstream added its own arm64 pieces.

### Findings

1. **Clean and redistributable (CONFIRMED).** Apache-2.0, built from source, and nothing prebuilt from Digitalis ships in the image. It is the only arm64 bridge that Track A can legally ship.
2. **One app fewer than libndk_translation (CONFIRMED).** 12/16 against 13/16; Digitalis loses Fennec. Both bridges fail Tor VPN and Element X the same way.
   - **ANAL-200 correction:** libndk_translation's Fennec "RUNS" was its Java UI only. Its Gecko thread spins at 100% of a CPU and Gecko never starts (`evidence/2026-10-17-digitalis-a17/fennec-gecko/libndk-translation.txt`).
3. **Correctness differs (CONFIRMED).** Digitalis fixes seq_cst store→load ordering, `CNTVCT_EL0` rate, `uname` and FMAX NaN propagation. It adds an `FRECPE` estimate failure. It shares the `ID_AA64ISAR0_EL1` SIGILL, the x86 default-NaN sign and sNaN priority, and the `SI_QUEUE` code.
4. **Speed: about 34% slower than libndk_translation on CoreMark (CONFIRMED).** 0.30× against 0.45× native.
5. **`MRS ID_AA64ISAR0_EL1` is the most valuable single fix for both bridges (CONFIRMED symptom).** Go's `x/sys/cpu` falls back to the ID registers when `/proc/self/auxv` is unreadable, and the probe shows it is unreadable under both bridges. Digitalis even advertises `cpuid` in its emulated `/proc/cpuinfo` without emulating these registers. **HYPOTHESIS:** returning a synthetic `ID_AA64ISAR0_EL1` that matches `HWCAP` would fix Tor VPN and other gomobile apps.
6. **Fennec dies under Digitalis; it is a translation bug (CONFIRMED, root cause open).**
   - **ANAL-200 correction: it is not a translation bug.** The crash happens in interpreter-only mode too. Android 17 stopped reporting the bridged ABI in `Build.CPU_ABI`, so Gecko looks for `x86_64/greprefs.js` in an arm64 omnijar and fails ("The three bugs" above, `evidence/2026-10-17-digitalis-a17/analysis/fennec-root-cause.md`). The hypothesis below was wrong.
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

### Next

1. Port the fork to `android17-release` on an OpenBook branch of Digitalis. Build it inside the Track A tree (`aosp_cf_x86_64_pc`, after ANAL-168), boot it in Cuttlefish, and re-run this matrix. Check that the API gap (finding 7) is gone.
2. Report findings 5 and 6, `FRECPE`, and the NaN and `si_code` differences upstream, with the probe and `analysis/fennec-sigsegv.txt` as reproducers. This is outward-facing, so it needs the owner's OK first.
3. Re-run cold-launch timings on a quiet host, and add a SIMD/JIT micro-benchmark. CoreMark alone may understate the heavy optimizer's NEON work.
