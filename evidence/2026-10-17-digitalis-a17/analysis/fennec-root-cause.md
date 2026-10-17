# Fennec 158 arm64: SIGSEGV at libxul.so+0x2b32da0 (ANAL-181) — root cause (ANAL-200, 2026-10-17)

Not a translation bug. The crash reproduces in Digitalis's interpreter-only mode as well as its JIT tiers. The
cause is the ABI Android 17 reports to bridged apps, and the fix is a platform patch
(`aosp/patches/art/0001-OPENBOOK-libnativebridge-bridged-apps-see-the-bridge.patch`).

## Chain of events

1. GeckoView's `GeckoLoader.setupGeckoEnvironment()` exports
   `putenv("MOZ_ANDROID_CPU_ABI=" + android.os.Build.CPU_ABI)`. This is in the dex: `classes3.dex`, method
   `setupGeckoEnvironment`, at `const-string "MOZ_ANDROID_CPU_ABI="` / `sget-object Landroid/os/Build;.CPU_ABI`.
2. `Preferences::InitInitialObjects()` (libxul `0x2b19e50`) calls `getenv("MOZ_ANDROID_CPU_ABI")`. It reads
   `"%s/greprefs.js"` from the GRE omnijar, then `"greprefs.js"`, and fails if neither exists.
3. The arm64 APK's `assets/omni.ja` contains `arm64-v8a/greprefs.js` only. The x86_64 APK's contains
   `x86_64/greprefs.js` only. There is no root `greprefs.js` in either.
4. On Android 17, `Build.CPU_ABI` is `SUPPORTED_64_BIT_ABIS[0]` = `x86_64` for every app. AOSP art `b7947b0641`
   (2025-05-20, "libnativebridge: Don't set deprecated CPU_ABI prop") removed the code that set it to the bridge's
   `NativeBridgeRuntimeValues.cpu_abi` (Digitalis: `arm64-v8a`).
5. Both lookups fail (`before-fix-digitalis.txt`: about 970 pairs of `GetItem x86_64/greprefs.js` /
   `GetItem greprefs.js`). `GetInstanceForService()` (libxul `0x2b198e4`) takes its error path at `0x2b19d9c` and
   drops `sPreferences`. The teardown (`0x2b1af84`) also clears the preferences state object (`0x97a95c0`) and the
   hash table (`0x97aa598`). `pref_SetPref` then returns `NS_ERROR_OUT_OF_MEMORY` (`0x8007000e`, seen in x21 at the
   crash) because the table is NULL.
6. `Preferences::InitializeUserPrefs()` (`0x2b32d78`) loads the state object again after `ReadUserOverridePrefs()`
   and dereferences it: `ldr x0, [x8, #0x8]` with x8 = NULL, a fault at address 0x8.

## libndk_translation (Google's image)

The same two lookups fail (`libndk-translation.txt`). There the Gecko thread does not die: it spins at 100% of a
CPU (155 ticks in 5 s, 1:21.8 of CPU time after 30 s). The app's Java UI stays alive, which is why ANAL-180's
harness reported RUNS. Gecko itself never started.

## After the fix (our image)

`Build.CPU_ABI` = `arm64-v8a` for arm64 apps. The probe now logs `cpu_abi=arm64-v8a`, and
`regress/build_cpu_abi_is_native_abi` passes. Fennec arm64:
- RUNS in matrix runs 1 and 2;
- Gecko logs "chrome startup finished";
- the tab, content and GPU child processes run;
- a test page served through `adb reverse` renders, with JavaScript (`../fennec-gecko/fennec-arm64-page.png`);
- the Gecko thread is idle after load (2 ticks in 5 s).

The x86_64 build renders the same page the same way (`../fennec-gecko/fennec-x86_64-page.png`). The page's canvas
is missing in both, so that is an environment issue (SwiftShader), not translation.

## Addresses (libxul.so of org.mozilla.fennec_fdroid_1580020.apk)

Identified from code shape and string references; HYPOTHESIS for the names.

| vaddr | function |
|---|---|
| 0x2b198e4 | Preferences::GetInstanceForService |
| 0x2b19e50 | Preferences::InitInitialObjects (getenv MOZ_ANDROID_CPU_ABI, "%s/greprefs.js", "greprefs.js") |
| 0x2b1ae54 | Preferences::Shutdown (sets sShutdown, 0x97a95d0) |
| 0x2b1af84 | teardown of the preferences state (0x97a95c0) and hash table (0x97aa598) |
| 0x2b32d78 | Preferences::InitializeUserPrefs (crash at 0x2b32da0) |
| 0x2b732dc | pref_SetPref ("Attempt to write pref %s after XPCOMShutdownThreads started", NS_ERROR_OUT_OF_MEMORY if no table) |
