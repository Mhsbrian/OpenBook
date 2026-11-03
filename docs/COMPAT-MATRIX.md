# Compatibility matrix

As of 2026-10-19. How ARM-only Android apps, and apps that need Google Play services, behave on OpenBook. OpenBook's arm64 bridge is Digitalis, built from source in the image ([`digitalis.md`](digitalis.md)); the harness and corpus are in [`compat-harness.md`](compat-harness.md).

## ARM-only APKs

**What a verdict means.** "Runs" means the app is alive 15 s after launch, with no crash, ANR or tombstone, plus a screenshot; it does not mean every feature works. For the corpus apps, each column comes from two runs from wiped data with identical outcomes. "—" means not tested.

**Columns.**
- **OpenBook:** `anybook_cf_x86_64_pc-cp2a-userdebug` (Android 17, `CP2A.260605.016`) with Digitalis ported to Android 17 and the ANAL-200 fixes, in Cuttlefish (6 vCPUs, 8 GiB, SwiftShader), 2026-10-17. The G14 product ships the same bridge files.
- **libndk_translation:** Google's AOSP Desktop (Preview) 37.0 emulator image (`CLE1.260506.004`), whose bridge is proprietary; the reference, 2026-10-15 (ANAL-180).
- **houdini:** libhoudini from the Googlebook image, not run yet (the image doesn't boot in a VM; `docs/PLAN.md`).

| App | ABI | OpenBook (Digitalis) | libndk_translation | houdini | Notes |
|---|---|---|---|---|---|
| OpenBook probe (`scripts/compat/probe`) | arm64-v8a | Runs; 18/20 test groups pass | Runs; 15/19 pass | — | OpenBook fails only the x86 NaN rules (`isa`) and the SIGILL `si_code` (`signals`). libndk_translation also fails seq_cst store→load ordering, the `CNTVCT_EL0` rate, `MRS` of the ID registers and `uname` |
| OpenBook probe | armeabi-v7a | **Install fails** | **Install fails** | — | `INSTALL_FAILED_NO_MATCHING_ABIS`: both images are 64-bit only, and neither bridge has an arm32 guest |
| VLC 3.7.1 | arm64-v8a | Runs | Runs | — | x86_64 control runs |
| Fennec F-Droid 158.0.0 | arm64-v8a | **Runs** | Runs (caveat) | — | On OpenBook, Gecko starts and renders a page with JavaScript (the `Build.CPU_ABI` fix, `docs/digitalis.md`). Under libndk_translation only the Java UI runs and Gecko spins at 100% CPU. x86_64 control runs |
| KOReader v2026.07.1 | arm64-v8a | Runs | Runs | — | LuaJIT |
| Lichess 0.29.1 | arm64-v8a | Runs | Runs | — | Flutter; x86_64 control runs |
| LocalSend 1.18.2 | arm64-v8a | Runs | Runs | — | Flutter + Rust; x86_64 control runs |
| Godot Engine 4.7.2 | arm64-v8a | Runs | Runs | — | Opens the all-files-access page; x86_64 control the same |
| Ogre Sample Browser 14.3.0 | arm64-v8a | Runs | Runs | — | GLES3 rendering visible |
| Battle for Wesnoth 1.19.28 | arm64-v8a | Runs | Runs | — | |
| OsmAnd~ 5.4.10 | arm64-v8a | Runs | Runs | — | |
| GCompris 26.2 | arm64-v8a | Runs | Runs | — | Qt 6 |
| TIC-80 1.01.00 | arm64-v8a | Runs | Runs | — | |
| Tux Paint 0.9.35 | arm64-v8a | Runs | Runs | — | |
| SimpleX Chat 7.0.4 | arm64-v8a | Runs (caveat) | Runs (caveat) | — | Window still black at 15 s under both bridges; cause not investigated |
| Tor VPN Beta 1.9.1 | arm64-v8a | **Runs** | **Crash** | — | Its Go runtime reads `ID_AA64ISAR0_EL1`; OpenBook emulates the ID registers as Linux does, libndk_translation raises SIGILL |
| AAAAXY 1.7.239 | arm64-v8a | Crash | Crash | — | The x86_64 control crashes the same way, so not translation |
| Element X 26.09.1 | arm64-v8a | **Crash** | **Crash** | — | `Failed to find JNI_GetCreatedJavaVMs` under both bridges; the x86_64 control runs |
| Chromium 158.0.8111.0 (operator-supplied, not in the corpus) | arm64-v8a | Runs (QEMU, G14 product, 2026-10-19) | — | — | Renders local JavaScript and canvas pages through its managed renderer, with no zygote retry storm (`docs/arm-native-services.md`, ANAL-224). Native-only ARM64 services without such a fallback still can't run |

**arm64-only corpus apps alive at 15 s:** OpenBook 14/16, libndk_translation 13/16. AAAAXY also crashes natively, so for translation it is 14/15 against 13/15.

**CPU speed** (CoreMark arm64 / native x86_64, 600k iterations, 3 interleaved rounds):

| Bridge, where | Executable | In an app |
|---|---|---|
| OpenBook (Digitalis A17), Cuttlefish, 2026-10-17 | 0.394 | 0.399 |
| OpenBook (Digitalis A17), **on the G14** (bare metal, Ryzen AI 9 HX 370, "balanced", on mains), 2026-10-18 | 0.361 | 0.351 |
| Digitalis A17 on Google's emulator image, 2026-10-17 | 0.300 | 0.298 |
| libndk_translation on Google's emulator image, 2026-10-17 | 0.457 | 0.456 |

In the same VM, Digitalis runs at about 65% of libndk_translation's speed. The higher Cuttlefish figure comes from a different VM (HYPOTHESIS: Cuttlefish passes AVX2, BMI and FMA to the guest and the emulator doesn't). CoreMark is integer-only and these VMs render on SwiftShader, so the numbers say nothing about GPU-bound apps.

**On the G14** (bare metal, 2026-10-18): the bridge self-check and the ARM apps check pass. The arm64 probe passes 18/20 groups there, failing only `isa` and `signals`, and the x86_64 control passes 18/18 with 2 skips. **Not yet seen on the laptop:** an arm64 corpus app in an enforcing boot, and the Chromium native-service path.

## Apps that use Google Play services (microG add-on, ANAL-210)

**None of the apps above needs Play services.** They are all F-Droid builds, which leave Google's libraries out. To test microG we use four open-source apps whose official builds use Play services (FCM push, Play location). Each is its own release APK from GitHub, pinned by sha256 in `scripts/microg/gms-apps.tsv`, downloaded locally and never committed.

**How they run:** `scripts/microg/gms-apps.sh` installs each app fresh, launches it and checks it 15 s later, in our `anybook_cf_x86_64_pc` build in Cuttlefish, SELinux enforcing, with internet over the VM's Wi-Fi. "With microG" means microG 0.3.17.252432 installed by `openbook-addons`, with device registration and push turned on in microG; "without" is the same VM after uninstalling it. Logs are redacted by `scripts/microg/redact.sh`.

Results (2026-10-17):

| App (official build) | Without microG | With microG | Notes |
|---|---|---|---|
| Home Assistant 2026.8.4 (`full`) | Runs; Play services missing; no push | **Runs; FCM token issued** | Logs "Play services out of date: requires 261200000, found 252432034" for one internal API, yet registers. First screen: "Connect to my Home Assistant server" |
| Bitwarden 2026.10.0 (standard) | Runs; Play services missing; no push | **Runs; FCM token issued** | Same version note. The window is black in screenshots: Bitwarden blocks screen capture |
| Nextcloud 35.0.1 (`gplay`) | Runs; Play services missing; no push | **Runs; FCM token issued** | Same version note. First screen: log in / sign up |
| Molly 8.19.2-4 (FCM build) | Runs; no complaint | Runs; no complaint; no registration yet | Registers for push only after phone-number sign-up, which the test doesn't do |

- 4/4 apps start with microG and 4/4 without, with 0 crashes and 0 ANRs.
- With microG, 3/4 get a push token from Google at first launch. Without it, none do.
- Delivering a message needs each app's own server, so it is not tested.
- microG itself, and its install on the G14, are in [`gapps.md`](gapps.md).

## Other compatibility results

Hardware, driver and image results live with their topics:

| Area | Where |
|---|---|
| The desktop in Cuttlefish and against Google's AOSP Desktop image | [`aosp-desktop.md`](aosp-desktop.md) |
| The G14 product in QEMU, and on the laptop | [`g14-product.md`](g14-product.md), [`g14-desktop.md`](g14-desktop.md) |
| Audio, Wi-Fi and Bluetooth on the G14 | [`g14-audio-net.md`](g14-audio-net.md) |
| Graphics drivers: dEQP and CTS on the G14 and the build host, YV12 frames (Google Photos) | [`graphics-amd.md`](graphics-amd.md) |
| Touchpad behaviour | [`touchpad-behavior.md`](touchpad-behavior.md) |
| The Googlebook OS image in QEMU | [`PLAN.md`](PLAN.md), [`kernel.md`](kernel.md) |
