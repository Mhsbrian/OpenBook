# Compatibility matrix

## Images on hosts and VMs

| Date | Image | Host / VM | Result | Evidence |
|---|---|---|---|---|
| 2026-10-15 | AOSP Desktop (Preview) 37.0 x86_64, `CLE1.260506.004` | Emulator 37.2.12, KVM, Ryzen 9 7950X, SwiftShader | **Boots** (16 s); freeform windows and taskbar work; arm64-v8a listed through libndk_translation | `evidence/2026-10-15-m0/m0-emulator/` |
| 2026-10-15 | Googlebook OS ruby `CL3B.260622.271.R1`, stock kernel and ramdisks | QEMU 11.1.2, KVM `-cpu host`, Ryzen 9 7950X (Zen 4) | **Partial:** first-stage mount OK, about 30 services start, 0 SIGILL; stalls at keystore2 (Trusty/pKVM, GSC) | `evidence/2026-10-15-m0/gbos-boot-zen4-kvm.log` |

## ARM-only APKs

The first baseline is libndk_translation in the AOSP Desktop (Preview) 37.0 emulator, from 2026-10-15 (ANAL-180). Each verdict means the app is alive 15 s after launch, with crash, ANR and tombstone counts and a screenshot. Two wiped-emulator runs gave identical results. Method, probe details and findings are in `docs/compat-harness.md`; evidence is in `evidence/2026-10-15-compat/`. The houdini and Digitalis columns come next. "—" means not tested yet.

| App | ABI | houdini | ndk_translation | Digitalis | Notes |
|---|---|---|---|---|---|
| AnyBook probe (`scripts/compat/probe`) | arm64-v8a | — | Runs; 15/19 test groups pass | — | Fails: seq_cst store→load ordering, x86 NaN rules, `CNTVCT_EL0` rate, `MRS` ID registers, `uname`, SIGILL `si_code` |
| AnyBook probe | armeabi-v7a | — | **Install fails** | — | `INSTALL_FAILED_NO_MATCHING_ABIS`: the image is 64-bit only |
| VLC 3.7.1 | arm64-v8a | — | Runs | — | x86_64 control runs |
| Fennec F-Droid 158.0.0 | arm64-v8a | — | Runs | — | x86_64 control runs; launch 690 ms vs 190 ms |
| KOReader v2026.07.1 | arm64-v8a | — | Runs | — | LuaJIT |
| Lichess 0.29.1 | arm64-v8a | — | Runs | — | Flutter; x86_64 control runs |
| LocalSend 1.18.2 | arm64-v8a | — | Runs | — | Flutter + Rust; x86_64 control runs |
| Godot Engine 4.7.2 | arm64-v8a | — | Runs | — | Opens the all-files-access page; x86_64 control the same |
| Ogre Sample Browser 14.3.0 | arm64-v8a | — | Runs | — | GLES3 rendering visible |
| Battle for Wesnoth 1.19.28 | arm64-v8a | — | Runs | — | |
| OsmAnd~ 5.4.10 | arm64-v8a | — | Runs | — | |
| GCompris 26.2 | arm64-v8a | — | Runs | — | Qt 6 |
| TIC-80 1.01.00 | arm64-v8a | — | Runs | — | |
| Tux Paint 0.9.35 | arm64-v8a | — | Runs | — | |
| SimpleX Chat 7.0.4 | arm64-v8a | — | Runs (caveat) | — | Window still black at 15 s |
| AAAAXY 1.7.239 | arm64-v8a | — | Crash | — | The x86_64 control crashes the same way, so not translation |
| Tor VPN Beta 1.9.1 | arm64-v8a | — | **Crash** | — | SIGILL: Go runtime `mrs ID_AA64ISAR0_EL1` is not emulated |
| Element X 26.09.1 | arm64-v8a | — | **Crash** | — | `Failed to find JNI_GetCreatedJavaVMs`; the x86_64 control runs |

Benchmark: CoreMark translated arm64 / native x86_64 = 0.457 for executables and 0.453 inside an app, in the same emulator (`evidence/2026-10-15-compat/bench/`).
