# OpenBook documentation

Where things stand: [`STATUS.md`](STATUS.md). Where things are going: [`PLAN.md`](PLAN.md). How to contribute:
[`CONTRIBUTING.md`](../CONTRIBUTING.md).

The docs are grouped below by purpose. Their file names stay as they are, because comments throughout `device/` and
`kernel/` cite them by path and section.

## Install and use

| Doc | What it covers |
|---|---|
| [`INSTALL.md`](INSTALL.md) | Installing OpenBook from a USB stick: on a whole disk or alongside Windows |
| [`setup.md`](setup.md) | The first-run setup flow |
| [`gapps.md`](gapps.md) | Google apps: the microG option or your own GApps package, installed by you |
| [`quire-howto.md`](quire-howto.md) | Using Quire, the agent layer, on your laptop |
| [`adb-debug.md`](adb-debug.md) | Debugging an installed laptop over the network with adb, and A/B updates |
| [`gpu-diagnostics.md`](gpu-diagnostics.md) | Per-app GPU diagnostics over adb: Radeon vs NVIDIA runs, frame pacing, stops, the summary table |
| [`touchpad-behavior.md`](touchpad-behavior.md) | How the G14's touchpad behaves and how to check it |

## Build and release

| Doc | What it covers |
|---|---|
| [`BUILD.md`](BUILD.md) | Building OpenBook: host, containers, AOSP, kernel, Mesa and the G14 image |
| [`aosp-build.md`](aosp-build.md) | The AOSP 17 source tree, its pin (`manifests/aosp/`) and its build environment |
| [`kernel.md`](kernel.md) | Reproducing the GKI kernel and building OpenBook's vendor modules with Kleaf |
| [`mesa.md`](mesa.md) | Building Mesa radeonsi and RADV for Android with the NDK |
| [`RELEASE.md`](RELEASE.md) | Turning a built image into a release: checks, signatures, source offer, publishing |
| [`../tests/README.md`](../tests/README.md) | The three test levels and where each test lives |

## Architecture

| Doc | What it covers |
|---|---|
| [`HARDWARE.md`](HARDWARE.md) | The driver and firmware map for each component of the target laptops |
| [`g14-product.md`](g14-product.md) | The G14 product (`anybook_g14_x86_64`): partitions, packages, vendor layer |
| [`g14-desktop.md`](g14-desktop.md) | The desktop on real hardware: swapchain, SELinux and the live image |
| [`aosp-desktop.md`](aosp-desktop.md) | Desktop windowing and VM graphics in the AOSP 17 PC build |
| [`graphics-amd.md`](graphics-amd.md) | AMD graphics in the device tree: Mesa, minigbm, the composer and ANGLE |
| [`nvidia-open.md`](nvidia-open.md) | NVIDIA's open kernel driver and GSP firmware in OpenBook |
| [`nvidia-graphics-modes.md`](nvidia-graphics-modes.md) | Graphics modes (Eco, Hybrid, Ultimate) with automatic rollback |
| [`nvidia.md`](nvidia.md) | Research: nouveau, NVK and PRIME offload for the RTX 50 Laptop GPU |
| [`power-input.md`](power-input.md) | Power and input: amd-pstate, sleep, the lid, the touchpad and the keyboard |
| [`g14-audio-net.md`](g14-audio-net.md) | Audio, Wi-Fi and Bluetooth |
| [`installer.md`](installer.md) | The installer: USB image, boot chain, install engine, wizard and A/B updates |
| [`digitalis.md`](digitalis.md) | Digitalis, the open arm64 native bridge |
| [`arm-native-services.md`](arm-native-services.md) | ARM64 native services and Chromium's renderers |
| [`compat-harness.md`](compat-harness.md) | The ARM compatibility harness and its baseline |
| [`COMPAT-MATRIX.md`](COMPAT-MATRIX.md) | Which ARM-only apps run |
| [`googlebook-ui.md`](googlebook-ui.md) | Why Googlebook looks cleaner than AOSP, and what OpenBook matches |
| [`googlebook-flags.md`](googlebook-flags.md) | The Googlebook desktop flags AOSP 17 declares and what OpenBook sets |
| [`quire.md`](quire.md) | Quire: the agent layer, its harness host and its OS tools |
| [`RESEARCH.md`](RESEARCH.md) | Research on Googlebook OS and prior art |

## Design

| Doc | What it covers |
|---|---|
| [`quire-design.md`](quire-design.md) | Quire's note: glass and ink, states and interaction. The source is [`quire-design/index.html`](quire-design/index.html). |
| [`launcher-design.md`](launcher-design.md) | OpenBook Launcher's M2 design: the taskbar, the All Apps panel, menus, Overview for desks and one motion system, on Quire's glass. The source is [`launcher-design/index.html`](launcher-design/index.html). |
| [`quire-pairing.md`](quire-pairing.md) | Quire: pairing a second computer (a design, not built yet) |
| [`installer-design/index.html`](installer-design/index.html) | The installer's high-fidelity design. Open it in a browser. |

Design renders, test results, logs and screenshots don't go in the repository. Renders go to the maintainers' design
store (`scripts/installer/render-design.sh` and `scripts/quire/render-design.sh` write them there). Results go on the
issue.
