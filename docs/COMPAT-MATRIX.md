# Compatibility matrix

## Images on hosts and VMs

| Date | Image | Host / VM | Result | Evidence |
|---|---|---|---|---|
| 2026-10-15 | AOSP Desktop (Preview) 37.0 x86_64, `CLE1.260506.004` | Emulator 37.2.12, KVM, Ryzen 9 7950X, SwiftShader | **Boots** (16 s); freeform windows and taskbar work; arm64-v8a listed through libndk_translation | `evidence/2026-10-15-m0/m0-emulator/` |
| 2026-10-15 | Googlebook OS ruby `CL3B.260622.271.R1`, stock kernel and ramdisks | QEMU 11.1.2, KVM `-cpu host`, Ryzen 9 7950X (Zen 4) | **Partial:** first-stage mount OK, about 30 services start, 0 SIGILL; stalls at keystore2 (Trusty/pKVM, GSC) | `evidence/2026-10-15-m0/gbos-boot-zen4-kvm.log` |
| 2026-10-16 | Our build: `aosp_cf_x86_64_pc-cp2a-userdebug`, Android 17 `CP2A.260605.016`, prebuilt android16-6.12 GKI | Cuttlefish (cvd 1.57.0) in Docker, KVM, Ryzen 9 7950X, `guest_swiftshader` | **Boots** (`boot_completed` 17–29 s); Launcher3 at 1920×1080; `type.pc` present; abilist lists `arm64-v8a` but there is **no native bridge** | `evidence/2026-10-16-aosp/` |
| 2026-10-17 | Our build: `anybook_g14_x86_64-cp2a-userdebug` with ANAL-179's audio, Wi-Fi and Bluetooth stack | QEMU 11.1.2, KVM, q35 + OVMF from USB; ICH9 HDA with QEMU's duplex codec; 2× `mac80211_hwsim`, hostapd AP in a netns | **Works in the VM:** codec found and unmuted, a 1 kHz tone reaches the codec through ALSA and through AudioFlinger; Wi-Fi scan, WPA2-PSK connect, DHCP, gateway ping, iperf3 742/644 Mbit/s up/down; Bluetooth HAL up, no controller in a VM. G14 untested | `evidence/2026-10-17-g14-audio-net/` |
| 2026-10-16 | Our build: `anybook_cf_x86_64_pc-cp2a-userdebug` (desktop product), Android 17 `CP2A.260605.016` | Cuttlefish (cvd 1.57.0) in Docker, KVM, Ryzen 9 7950X; `gfxstream_guest_angle` on the **Radeon 610M** (RADV) | **Boots** (17 s) straight to the desktop: freeform windows, pinned desktop taskbar, desktop status bar; matches the AOSP Desktop image (0 desktop flag or prop differences); 0% janky frames scrolling Settings | `evidence/2026-10-16-desktop/` |
| 2026-10-17 | Our build: `anybook_cf_x86_64_pc-cp2a-userdebug` with the Digitalis arm64 bridge (ANAL-200) | Cuttlefish (cvd 1.57.0) in Docker, KVM, Ryzen 9 7950X, 6 vCPUs, `guest_swiftshader` | **arm64 apps run:** `ro.dalvik.vm.native.bridge=libberberis_arm64.so`, abilist `x86_64,arm64-v8a`, 57 guest libraries, binfmt_misc on; 14/16 arm64-only apps alive in two runs | `evidence/2026-10-17-digitalis-a17/` |
| 2026-10-17 | Our build: `anybook_g14_x86_64-cp2a-userdebug` live image with the Digitalis bridge (ANAL-200) | QEMU 11.1.2, KVM `-cpu host`, q35 + OVMF from USB | **Bridge checks pass in the VM:** all five `bridge_*` verdicts true (config, arm64 exec, ID registers, 6,900 `FRECPE`/`FRSQRTE` cases, CRC32/NEON). G14 untested | `evidence/2026-10-17-digitalis-a17/g14-live-qemu/` |
| 2026-10-17 | `openbook-live-20261017-combined` + the graphics check add-on (`openbook-gfxcheck-20261017`, ANAL-177), 40 cases per list | QEMU 11.1.2, KVM, q35 + OVMF from USB, SwiftShader | **The add-on works end to end:** unpacked and checked, every part that applies without an AMD GPU passes (VK 40/40, GLES on ANGLE 111 + 9 not supported, EGL app 40/40, ANGLE end2end 32 + 8 skipped), settings restored, results on the stick, power-off. Plumbing only: no AMD GPU | `evidence/2026-10-17-graphics-cts/qemu/` |
| 2026-10-17 | Our build: `openbook-live-20261017-combined` (`main` + the G14 binfmt_misc policy fix, ANAL-159) | QEMU 11.1.2, KVM `-cpu host`, q35 + OVMF from USB | **Live matrix 39/39; the bridge works in an enforcing boot:** no binfmt_misc denial, and `openbook_bridge_check` as the shell user passes exec, ID registers, 6,900 `FRECPE`/`FRSQRTE` cases and CRC32/NEON. Power check 10/10. G14 untested | `evidence/2026-10-17-g14-combined/` |
| 2026-10-17 | Our build with ANAL-179's G14 fixes (`anal179-g14r-c`: audio HAL patch 0002, PNO, hwtest) | QEMU 11.1.2, KVM, q35 + OVMF from USB; ICH9 HDA (WAV or silent backend); 2× `mac80211_hwsim` | **The AAudio tone reaches the codec whole:** 2.05 s with 2 glitched windows, against 1.65–1.70 s and 22–23 with AOSP's pacing in the same boot. **Capture padding 0, against 7.** Wi-Fi iperf3 681–755 / 702–732 Mbit/s. The PNO path reaches the driver, which hwsim refuses. G14: next stick | `evidence/2026-10-17-g14-audio-net/qemu-l/`, `qemu-m/`, `qemu-n/` |
| 2026-10-17 | Our build: `openbook-live-20261017-anal178c` (`main` at `ea3c25e`), then `anal176s` (+ PR #52) | **ASUS GA403WR (G14), bare metal**, from USB; owner's runs | **The default entry, SELinux enforcing, reaches the desktop:** 28 s (`anal178c`) and 29 s (`anal176s`), no app crashed. Wi-Fi on 5 GHz with internet, Bluetooth pairing, the browser. `anal176s`: 0 dropped frames (151 before), no storage notice for the stick, no lock-screen blackout. Bluetooth audio and app sound were denied by SELinux; the fix is in `anal176t` (QEMU 40/40), not yet run on the G14 | `evidence/2026-10-17-g14-desktop/g14-anal178c/`, `g14-anal176s/`, `anal176t/` |

## Audio, Wi-Fi and Bluetooth on the G14

The owner's two sessions of 2026-10-17 on the **ASUS GA403WR** (Ryzen AI 9 HX 370), live USB, ANAL-179. Session 1 was stick `anal178c` (`main`); session 2 was `anal176s` (`main` + PR #52 as of then). Each had a default boot (SELinux enforcing), then a "save logs" boot (permissive, `openbook-hwtest`). Details: `docs/g14-audio-net.md` §10.

| Date | Function | Hardware, driver | Session 1 | Session 2 | Evidence (`evidence/2026-10-17-g14-audio-net/`) |
|---|---|---|---|---|---|
| 2026-10-17 | Wi-Fi | MediaTek MT7925, `mt7925e`, firmware `20260414`; wpa_supplicant, no vendor HAL | **Works:** scan 91 networks; connected on 5320 MHz (160 MHz, −37 dBm, link rate 1201/1922 Mbit/s); DHCP; gateway ping 0 % loss; internet validated | **Works:** the same (82 networks, ping 7.8 ms) | `g14-anal178c/`, `g14-anal176s/` |
| 2026-10-17 | Wi-Fi throughput | same | not run (no iperf3 server configured) | not run | — |
| 2026-10-17 | Bluetooth | MT7925, `btusb` + `btmtk`; AOSP's AIDL HAL | on, not paired | **paired** (SSP); A2DP with LDAC 96 kHz/32-bit. **Under enforcing, the Bluetooth app aborted at A2DP start** (`bluetooth → hal_audio_default_tmpfs` denied; fixed in PR #52, not yet run on the G14) | `g14-anal176s/tombstones.txt` |
| 2026-10-17 | Speakers → built-in mic, straight on ALSA | Realtek ALC285 (card 2) + 2× Cirrus CS35L56 (`10431024-spkid1` tuning) | **heard**: −32.0 dBFS over −72.5 noise bin, 0 of 33 slices glitched | **heard**: −33.6 over −75.5, 2 of 33 | `report.md` |
| 2026-10-17 | Speakers → built-in mic through Android (AAudio) | same, AOSP's example HAL | **heard, broken**: 24 of 30 slices glitched; the HAL padded the capture with silence 7 times. Fixed by AOSP patch 0002 (QEMU-tested, not yet run on the G14) | not heard: the tone went to the paired Bluetooth device (the test now names its ports) | `report.md`, `digest.txt` |
| 2026-10-17 | App audio under enforcing | — | — | **no sound from the browser**: `untrusted_app_29 → audioserver_tmpfs` denied (fixed in PR #52, not yet run on the G14) | `evidence/2026-10-17-g14-desktop/` (PR #52) |
| 2026-10-17 | Headphone jack | ALC285 pin `0x21`, HDA jack input device | not tested (nothing plugged in) | not tested | `digest.txt` |

## ARM-only APKs

The first baseline is libndk_translation in the AOSP Desktop (Preview) 37.0 emulator, from 2026-10-15 (ANAL-180). Each verdict means the app is alive 15 s after launch, with crash, ANR and tombstone counts and a screenshot. Two wiped-emulator runs gave identical results. Method, probe details and findings are in `docs/compat-harness.md`; evidence is in `evidence/2026-10-15-compat/`. The Digitalis column (2026-10-16, ANAL-181) uses the same image, corpus and harness, with Digitalis built from source and installed as the native bridge on a separate AVD. It also had two identical wiped-emulator runs; details are in `docs/digitalis.md` and evidence in `evidence/2026-10-16-digitalis/`. The houdini column comes next. "—" means not tested yet.

| App | ABI | houdini | ndk_translation | Digitalis | Notes |
|---|---|---|---|---|---|
| OpenBook probe (`scripts/compat/probe`) | arm64-v8a | — | Runs; 15/19 test groups pass | Runs; 16/19 pass | ndk fails: seq_cst store→load ordering, x86 NaN rules, `CNTVCT_EL0` rate, `MRS` ID registers, `uname`, SIGILL `si_code`. Digitalis fixes ordering, `CNTVCT`, `uname` and FMAX NaN; it still fails sNaN/default NaN, `MRS ID_AA64ISAR0_EL1` and `si_code`, and newly fails the `FRECPE` estimate |
| OpenBook probe | armeabi-v7a | — | **Install fails** | **Install fails** | `INSTALL_FAILED_NO_MATCHING_ABIS`: the image is 64-bit only |
| OpenBook probe, on our AOSP build without a bridge (ANAL-168) | arm64-v8a | — | — | — | **Installs, then fails:** `dlopen ... is for EM_AARCH64`. The abilist advertises `arm64-v8a`, but no translator ships (`evidence/2026-10-16-aosp/boot1/arm64-probe-check.txt`) |
| VLC 3.7.1 | arm64-v8a | — | Runs | Runs | x86_64 control runs |
| Fennec F-Droid 158.0.0 | arm64-v8a | — | Runs | **Crash** | x86_64 control runs; launch 690 ms vs 190 ms. Under Digitalis, a Gecko thread hits a NULL+8 SIGSEGV that Berberis's handler catches (no tombstone, so the harness reports EXITED). ANAL-200: both come from Android 17 no longer setting `Build.CPU_ABI` for bridged apps; under ndk_translation only the Java UI runs and Gecko spins at 100% CPU (`docs/digitalis.md`) |
| KOReader v2026.07.1 | arm64-v8a | — | Runs | Runs | LuaJIT |
| Lichess 0.29.1 | arm64-v8a | — | Runs | Runs | Flutter; x86_64 control runs |
| LocalSend 1.18.2 | arm64-v8a | — | Runs | Runs | Flutter + Rust; x86_64 control runs |
| Godot Engine 4.7.2 | arm64-v8a | — | Runs | Runs | Opens the all-files-access page; x86_64 control the same |
| Ogre Sample Browser 14.3.0 | arm64-v8a | — | Runs | Runs | GLES3 rendering visible |
| Battle for Wesnoth 1.19.28 | arm64-v8a | — | Runs | Runs | |
| OsmAnd~ 5.4.10 | arm64-v8a | — | Runs | Runs | |
| GCompris 26.2 | arm64-v8a | — | Runs | Runs | Qt 6 |
| TIC-80 1.01.00 | arm64-v8a | — | Runs | Runs | |
| Tux Paint 0.9.35 | arm64-v8a | — | Runs | Runs | |
| SimpleX Chat 7.0.4 | arm64-v8a | — | Runs (caveat) | Runs (caveat) | Window still black at 15 s under both bridges |
| AAAAXY 1.7.239 | arm64-v8a | — | Crash | Crash | The x86_64 control crashes the same way, so not translation |
| Tor VPN Beta 1.9.1 | arm64-v8a | — | **Crash** | **Crash** | SIGILL: Go runtime `mrs ID_AA64ISAR0_EL1` is not emulated by either bridge |
| Element X 26.09.1 | arm64-v8a | — | **Crash** | **Crash** | `Failed to find JNI_GetCreatedJavaVMs` under both bridges; the x86_64 control runs |

Benchmark: CoreMark translated arm64 / native x86_64 = 0.457 for executables and 0.453 inside an app, in the same emulator (`evidence/2026-10-15-compat/bench/`).

Same-day re-run on a quiet host (2026-10-16): libndk_translation 0.452 / 0.456 and **Digitalis 0.298 / 0.304** (`evidence/2026-10-16-digitalis/bench-ndk/`, `bench/`). Digitalis runs at about two thirds of libndk_translation's speed. arm64-only apps alive at 15 s: libndk_translation 13/16, Digitalis 12/16 (Digitalis loses Fennec).

### Our build with Digitalis (2026-10-17, ANAL-200)

`anybook_cf_x86_64_pc-cp2a-userdebug` with Digitalis ported to Android 17 and the three ANAL-200 fixes, in Cuttlefish with the same resources, corpus and harness. There were two wiped-data runs with identical outcomes (`evidence/2026-10-17-digitalis-a17/run1/`, `run2/`, `repro-check.txt`). Details are in `docs/digitalis.md`.

| App | ABI | Our build (Digitalis A17) | Notes |
|---|---|---|---|
| OpenBook probe | arm64-v8a | Runs; 18/20 test groups pass | Still fails the x86 NaN rules (`isa`) and the SIGILL `si_code` (`signals`); `MRS`, `FRECPE` and the new `regress` group pass |
| VLC, KOReader, Lichess, LocalSend, Godot, Ogre, Wesnoth, OsmAnd, GCompris, TIC-80, Tux Paint | arm64-v8a | Runs | Same as both bridges on Google's image |
| SimpleX Chat 7.0.4 | arm64-v8a | Runs (caveat) | Window still black at 15 s, as under both bridges |
| Fennec F-Droid 158.0.0 | arm64-v8a | **Runs** | Gecko starts and renders a page with JavaScript (`fennec-gecko/`) |
| Tor VPN Beta 1.9.1 | arm64-v8a | **Runs** | `MRS` of the ID registers is emulated as Linux does it |
| AAAAXY 1.7.239 | arm64-v8a | Crash | Same as the x86_64 control |
| Element X 26.09.1 | arm64-v8a | Crash | `JNI_GetCreatedJavaVMs`, as under both bridges |

arm64-only apps alive at 15 s: **14/16**.

CoreMark, translated arm64 / native x86_64 (600k iterations, 3 interleaved rounds, quiet host, 2026-10-17):

| Bridge, image, VM | Executable | In an app | Evidence (`evidence/2026-10-17-digitalis-a17/`) |
|---|---|---|---|
| Digitalis A17, our build, Cuttlefish | **0.394** | **0.399** | `bench/` |
| Digitalis A17 as an overlay, Google's image, emulator | 0.300 | 0.298 | `emulator-overlay/bench/` |
| libndk_translation, Google's image, emulator | 0.457 | 0.456 | `bench-ndk/` |

In the same VM, Digitalis runs at about 65% of libndk_translation's speed. The higher figure on our build is a different VM. HYPOTHESIS: Cuttlefish passes AVX2, BMI and FMA to the guest and the emulator does not.

## Graphics drivers

| Date | Driver build | Host / VM | Result | Evidence |
|---|---|---|---|---|
| 2026-10-15 | Mesa 26.2.5 and AG 26.0.8 radeonsi + RADV, NDK r30, API 37 | AOSP Desktop emulator 37 (`CLE1.260506.004`), KVM, no GPU | **Loads:** Vulkan HAL `open(vk0)` and `vkCreateInstance(1.3)` OK, 0 devices; EGL loads, `eglInitialize` fails (no DRM device). Not tested on AMD hardware | `evidence/2026-10-15-mesa/smoke/` |
| 2026-10-17 | The G14 image's own Mesa 26.2.5 RADV, **android-strict (Vulkan 1.1, as shipped)**; AOSP 17 `deqp-binary64` | Build host, **Radeon 610M (gfx1036, RDNA2), not the G14's 890M**; container, image's bionic, a HAL shim instead of Android's loader (ANAL-177 pre-check) | **dEQP-VK subset, 66,226 cases: 43,248 pass, 57 fail, 1 crash, 3 flakes, 22,917 not supported**, 116 s. 47 of the failures share one cause: Amber needs `vkGetBufferDeviceAddress`, a Vulkan 1.2 entry point android-strict hides | `evidence/2026-10-17-graphics-cts/precheck-610m/vk/` |
| 2026-10-17 | The same RADV built **without android-strict (Vulkan 1.4)** | Same host and path | **Same 66,226 cases: 45,161 pass, 5 fail, 0 crash, 5 flakes**, 96 s. 0 failures that 1.1 does not have; 1,915 more passes. 2 of the 5 come from the pre-check's path (RADV's raw extension lists), 1 from Mesa being newer than Android 17's dEQP (`info.device_extensions`) | `evidence/2026-10-17-graphics-cts/precheck-610m/vk14/` |
| 2026-10-17 | The image's radeonsi through Android's own libEGL | Same host; pbuffer 256×256, `rgba8888d24s8ms0` | **dEQP-GLES2/3/31 subset, 13,671 cases: 13,621 pass, 0 fail, 2 quality warnings, 48 not supported**, 18 s. ANGLE could not run off the device (it spins right after loading without Android's property service) | `evidence/2026-10-17-graphics-cts/precheck-610m/gles-mesa/` |
| 2026-10-17 | Our `anybook_cf_x86_64_pc` build: AOSP's dEQP app and Android 17's ANGLE end2end CTS helper app, run by the graphics check's `run.sh` | Cuttlefish, ANGLE over gfxstream on the **610M** (RADV in the host), SELinux permissive | **dEQP-EGL, 1,287 cases (window surfaces): 822 pass, 0 fail, 463 not supported**, 198 s. **ANGLE end2end, 2,364 of the CTS PASS tests: 1,802 pass, 7 fail** (all `TextureBorderClamp*`), 336 skipped by ANGLE, 219 not in this build, 147 s | `evidence/2026-10-17-graphics-cts/cuttlefish/` |
| 2026-10-17 | **G14 run: graphics check add-on** (`openbook-gfxcheck-20261017`): VK 1.1 and 1.4, GLES on ANGLE and radeonsi, dEQP-EGL (app), ANGLE end2end (Android 17 CTS) | **ASUS GA403WR, Radeon 890M (gfx1150)** | **Not run yet:** waiting for the owner's stick run (`docs/graphics-amd.md`, owner checklist) or the device agent (ANAL-193) | — |
